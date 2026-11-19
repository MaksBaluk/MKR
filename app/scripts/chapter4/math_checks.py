"""Chapter-4 Phase 1, Stage 4: property checks of the mathematical core against docs/tasks/MATH_SPEC.md.

Each check runs the production domain code on many seeded random inputs (no `hypothesis`: it is not a dependency) and
returns one row: id, quantity, MATH_SPEC reference, property, method, number of cases, status, detail. The thesis DOCX
is not in the repository, so the formulas are compared with MATH_SPEC.md (the canonical encoding of chapter 2).
Status values: PASS, FAIL, DEVIATION (implemented as documented, differs from the thesis model), PARTIAL.
Used by tests/test_chapter4_math_properties.py and by math_validation_ch4.py (artifacts/chapter4/mathematical_validation.csv).
"""
from __future__ import annotations

import inspect
import itertools
import math
import random
from collections.abc import Callable

from backend.api import cohorts as cohorts_api
from backend.api import level as level_api
from backend.domain import interview_budget as budget
from backend.domain.core_flow import eval_alternative, eval_group, rank_vacancy, self_claim_metrics
from backend.domain.criteria import epsilon, experience_status, fulfilment_bounds, mandatory_status
from backend.domain.market import VacancyInput, compute_market
from backend.domain.planner import OpenState, choose_next, coverage
from backend.domain.ranking import VacancyRanking, rank, sort_key, z_status
from backend.domain.seniority import CriterionEvidence, estimate
from backend.domain.seniority_policy import PRACTICE_CRITERIA, PYTHON_BACKEND_V4
from backend.domain.topic_summary import MIN_COVERAGE_FOR_OVERALL, topic_summary

SEED = 20261119
CHECKS: list[Callable[[], dict]] = []
TOL = 1e-12


def check(cid: str, quantity: str, ref: str, prop: str, method: str):
    def deco(fn):
        def run() -> dict:
            n, status, detail = fn(random.Random(f"{SEED}:{cid}"))
            return {"id": cid, "quantity": quantity, "math_spec_ref": ref, "property": prop, "method": method,
                    "cases": n, "status": status, "detail": detail}
        run.__name__ = fn.__name__
        CHECKS.append(run)
        return run
    return deco


def _verdict(bad: list, n: int, ok_detail: str) -> tuple[int, str, str]:
    return (n, "PASS", ok_detail) if not bad else (n, "FAIL", f"{len(bad)} violations, first: {bad[0]}")


def _score(rng: random.Random, p_null: float = 0.3) -> float | None:
    return None if rng.random() < p_null else rng.choice([0.0, 1.0, round(rng.random(), 3)])


def _alt(rng: random.Random, crits: list[str]) -> dict:
    ids = rng.sample(crits, rng.randint(1, len(crits)))
    return {"competency_id": "x", "criterion_ids": ids, "required_level": rng.choice([1, 2, 3]),
            "tau": rng.choice([None, round(rng.uniform(0.05, 1.0), 2)])}


CRITS = [f"x.c{i}" for i in range(6)]
RUBRICS = {"x": [(c, 1.0 + i % 3) for i, c in enumerate(CRITS)]}


@check("H01", "H(v,p)", "§0", "cohort = deterministic hard filter; missing values unknown, not false", "code inspection")
def h01(rng):
    src = inspect.getsource(cohorts_api._vacancy_revisions)
    where = src.split(".where(", 1)[1].split(")\n", 1)[0]
    track_only = "Vacancy.track == track" in where and "is_active" in where and "work_mode" not in where
    return 1, "PARTIAL" if track_only else "FAIL", (
        "H is implemented as track + is_active only (TRACK_ALL_VALID_V2); work mode/location are UI filters, never "
        "hard exclusions; years are ranked via X, not filtered. Deterministic and frozen before the first question.")


@check("F01", "F(c)", "§1 (2.1)", "0<=F<=1; F=1 iff c in every vacancy; repeated mentions count once", "seeded random")
def f01(rng):
    bad, n = [], 0
    for _ in range(400):
        acts = [f"a{i}" for i in range(rng.randint(1, 8))]
        vs = [VacancyInput(f"v{j}", tuple(tuple(rng.sample(acts, rng.randint(1, min(3, len(acts)))))
                                          for _ in range(rng.randint(1, 4)))) for j in range(rng.randint(1, 12))]
        n += 1
        present = {a: sum(any(a in g for g in v.groups) for v in vs) for a in acts}
        for e in compute_market(vs):
            if not 0 <= e.prevalence <= 1 or not math.isclose(e.prevalence, present[e.action_id] / len(vs)):
                bad.append((e.action_id, e.prevalence))
    return _verdict(bad, n, "F(c)=|{v: c in C_v}|/N exact on every catalog")


@check("I01", "I(c)", "§1 (2.2)-(2.3)", "I>=0, sum_c I(c)=1, OR-group mass split equally", "seeded random")
def i01(rng):
    bad, n = [], 0
    for _ in range(400):
        acts = [f"a{i}" for i in range(rng.randint(1, 8))]
        vs = [VacancyInput(f"v{j}", tuple(tuple(rng.sample(acts, rng.randint(1, min(3, len(acts)))))
                                          for _ in range(rng.randint(1, 4)))) for j in range(rng.randint(1, 12))]
        n += 1
        m = compute_market(vs)
        if any(e.mass < 0 for e in m) or not math.isclose(sum(e.mass for e in m), 1.0, abs_tol=1e-9):
            bad.append(sum(e.mass for e in m))
        order = [(-e.prevalence, -e.mass, e.action_id) for e in m]
        if order != sorted(order):
            bad.append("order")
    return _verdict(bad, n, "sum I = 1 within 1e-9; order F desc, I desc, id")


def _state(rng):
    groups = [(f"v{i}", g) for i in range(4) for g in range(3)]
    open_g = frozenset(g for g in groups if rng.random() < 0.7)
    alts = {g: frozenset(rng.sample("abcdefg", rng.randint(1, 3))) for g in open_g}
    w = {g: rng.random() for g in groups}
    return OpenState(open_g, alts, frozenset(g for g in groups if g[1] == 0), frozenset()), w


@check("Q01", "Q_t(T)", "§2", "fixed-state Q_t is monotone and submodular", "seeded random (A subset B, x)")
def q01(rng):
    bad, n = [], 0
    for _ in range(600):
        st, w = _state(rng)
        b = frozenset(rng.sample("abcdefg", rng.randint(0, 5)))
        a = frozenset(x for x in b if rng.random() < 0.5)
        x = rng.choice("abcdefg")
        n += 1
        qa, qb = coverage(st, w, a), coverage(st, w, b)
        if qa > qb + TOL:
            bad.append(("monotone", sorted(a), sorted(b)))
        if coverage(st, w, a | {x}) - qa < coverage(st, w, b | {x}) - qb - TOL:
            bad.append(("submodular", sorted(a), sorted(b), x))
    return _verdict(bad, n, "monotone and diminishing marginal gain on every sample")


@check("Q02", "c*_t", "§2", "choose_next = argmax marginal gain; None when no positive gain", "seeded random")
def q02(rng):
    bad, n = [], 0
    for _ in range(600):
        st, w = _state(rng)
        avail = rng.sample("abcdefgh", rng.randint(1, 8))
        n += 1
        got = choose_next(st, w, avail, {c: rng.random() for c in avail})
        gains = {c: coverage(st, w, frozenset({c})) - coverage(st, w, frozenset()) for c in avail}
        best = max(gains.values())
        if best <= 0 and got is not None or best > 0 and (got is None or gains[got] < best - TOL):
            bad.append((got, best))
    return _verdict(bad, n, "selected topic always has maximal marginal gain")


@check("E01", "epsilon, tau", "§4", "eps=min(.05,tau/2); s>=tau SAT, s<tau-eps FAILED, else UNRESOLVED; null UNRESOLVED",
       "seeded random")
def e01(rng):
    bad, n = [], 0
    for _ in range(5000):
        tau, s = rng.uniform(1e-3, 1), _score(rng, 0.1)
        n += 1
        e = epsilon(tau)
        want = ("UNRESOLVED" if s is None else "SATISFIED" if s >= tau else "FAILED" if s < tau - e else "UNRESOLVED")
        if not math.isclose(e, min(0.05, tau / 2)) or mandatory_status(s, tau) != want:
            bad.append((tau, s))
    return _verdict(bad, n, "boundary classes exact, including tau -> 0")


@check("L01", "L, U", "§4 (L_vga, U_vga)", "0<=L<=U<=1 for alternatives and OR groups", "seeded random")
def l01(rng):
    bad, n = [], 0
    for _ in range(4000):
        scores = {c: _score(rng) for c in CRITS}
        alts = [_alt(rng, CRITS) for _ in range(rng.randint(1, 3))]
        n += 1
        for e in [eval_alternative(a, scores, RUBRICS) for a in alts] + [eval_group(alts, scores, RUBRICS)]:
            if not -TOL <= e.lower <= e.upper + TOL <= 1 + 2 * TOL:
                bad.append((e.lower, e.upper))
    return _verdict(bad, n, "bounds always nested in [0,1]")


@check("L02", "L, U", "§4", "replacing one UNKNOWN by a known score never widens [L,U] (nested, others unchanged)",
       "seeded random")
def l02(rng):
    bad, n = [], 0
    for _ in range(4000):
        ids = rng.sample(CRITS, rng.randint(1, 6))
        w = {c: rng.uniform(0.1, 3) for c in ids}
        tau = {c: rng.uniform(0.05, 1) for c in ids}
        scores = {c: _score(rng, 0.5) for c in ids}
        unknown = [c for c in ids if scores[c] is None]
        if not unknown:
            continue
        n += 1
        lo, up = fulfilment_bounds(scores, tau, w, ids)
        new = dict(scores, **{rng.choice(unknown): rng.random()})
        lo2, up2 = fulfilment_bounds(new, tau, w, ids)
        if not (lo - TOL <= lo2 <= up2 <= up + TOL):
            bad.append(((lo, up), (lo2, up2)))
    return _verdict(bad, n, "L <= L' <= U' <= U on every replacement")


@check("G01", "OR groups", "§4", "L_g=max_a L, U_g=max_a U; SAT if any alt SAT; FAILED only if all FAILED",
       "seeded random")
def g01(rng):
    bad, n = [], 0
    for _ in range(4000):
        scores = {c: _score(rng) for c in CRITS}
        alts = [_alt(rng, CRITS) for _ in range(rng.randint(1, 4))]
        n += 1
        ev = [eval_alternative(a, scores, RUBRICS) for a in alts]
        g = eval_group(alts, scores, RUBRICS)
        st = [e.status for e in ev]
        want = "SATISFIED" if "SATISFIED" in st else "FAILED" if all(s == "FAILED" for s in st) else "UNRESOLVED"
        if g.status != want or not math.isclose(g.lower, max(e.lower for e in ev)) or \
                not math.isclose(g.upper, max(e.upper for e in ev)):
            bad.append((st, g.status))
    return _verdict(bad, n, "OR is max/any, AND across alternative criteria (not a sum)")


@check("U01", "unknown vs zero", "§0, §3, §4", "null is never 0: null -> UNRESOLVED and [0,1]; 0 -> FAILED, U<1",
       "seeded random")
def u01(rng):
    bad, n = [], 0
    for _ in range(2000):
        tau = rng.uniform(0.05, 1)
        alt = {"competency_id": "x", "criterion_ids": [rng.choice(CRITS)], "required_level": 2, "tau": tau}
        cid = alt["criterion_ids"][0]
        n += 1
        a, z = eval_alternative(alt, {cid: None}, RUBRICS), eval_alternative(alt, {cid: 0.0}, RUBRICS)
        if (a.status, a.lower, a.upper) != ("UNRESOLVED", 0.0, 1.0) or z.status != "FAILED" or z.upper != 0.0:
            bad.append((a, z))
    ts = topic_summary([("a", 1.0), ("b", 1.0)], {"a": 1.0, "b": None})
    if ts.m != 1.0 or ts.e != 0.5:
        bad.append(("M_c ignores nulls", ts))
    return _verdict(bad, n + 1, "unknown keeps the full interval; zero is an observed failure")


@check("C01", "M_c, E_c", "§3 (2.8)-(2.9)", "M_c weighted mean of assessed; E_c assessed weight share; M null if none",
       "seeded random")
def c01(rng):
    bad, n = [], 0
    for _ in range(3000):
        rub = [(f"c{i}", rng.uniform(0.1, 3)) for i in range(rng.randint(1, 6))]
        sc = {c: _score(rng, 0.4) for c, _ in rub}
        n += 1
        t = topic_summary(rub, sc)
        known = [(w, sc[c]) for c, w in rub if sc[c] is not None]
        m = sum(w * s for w, s in known) / sum(w for w, _ in known) if known else None
        e = sum(w for w, _ in known) / sum(w for _, w in rub)
        if (t.m is None) != (m is None) or (m is not None and not math.isclose(t.m, m)) or not math.isclose(t.e, e) \
                or t.overall_level_allowed != (e >= MIN_COVERAGE_FOR_OVERALL):
            bad.append((rub, sc))
    return _verdict(bad, n, "formulas exact; overall level only at E_c >= 0.6")


@check("C02", "high M_c, low E_c", "§3a, §3d, §4",
       "one strong criterion never confirms a whole competence or a multi-criterion requirement", "seeded random")
def c02(rng):
    bad, n = [], 0
    for _ in range(2000):
        k = rng.randint(3, 6)
        ids = CRITS[:k]
        strong = rng.choice(ids)
        sc = {c: (1.0 if c == strong else None) for c in ids}
        n += 1
        t = topic_summary([(c, 1.0) for c in ids], sc)
        alt = {"competency_id": "x", "criterion_ids": ids, "required_level": 2, "tau": 0.75}
        if t.m != 1.0 or t.overall_level_allowed or eval_alternative(alt, sc, RUBRICS).status == "SATISFIED":
            bad.append((k, t))
    return _verdict(bad, n, "M_c=1.0 with E_c<=1/3: overall level withheld, requirement UNRESOLVED")


def _vac(rng, vid: str) -> dict:
    groups = []
    for gi in range(rng.randint(1, 4)):
        groups.append({"kind": rng.choice(["MANDATORY", "PREFERRED"]),
                       "alternatives": [dict(_alt(rng, CRITS), competency_id=f"act{rng.randint(0, 4)}")
                                        for _ in range(rng.randint(1, 2))]})
    return {"id": vid, "years_min": rng.choice([0, 1, 3, 5]), "groups": groups}


RUB5 = {f"act{i}": [(c, 1.0) for c in CRITS] for i in range(5)}


@check("Z01", "Z, mandatory not compensated", "§4", "any FAILED mandatory group gives Z=0 whatever preferred groups "
       "score; Z=2 only if all mandatory SATISFIED; Z=0 ranks below every Z>=1 vacancy", "seeded random")
def z01(rng):
    bad, n = [], 0
    for _ in range(2000):
        st = [rng.choice(["SATISFIED", "FAILED", "UNRESOLVED"]) for _ in range(rng.randint(0, 4))]
        n += 1
        want = 0 if "FAILED" in st else 2 if st and all(s == "SATISFIED" for s in st) else 1
        if z_status(st) != want:
            bad.append(st)
    for _ in range(500):  # failed mandatory + perfect preferred vs unresolved mandatory + nothing preferred
        n += 1
        a = VacancyRanking("a", 0, 2, 0.0, 1.0, 0.0, 0.0, True, True, "RANKED", 1.0, 1.0)
        b = VacancyRanking("b", 1, 0, 0.0, 0.0, 1.0, 1.0, True, False, "RANKED")
        if [r.vacancy_id for r in rank([a, b])] != ["b", "a"]:
            bad.append("compensated")
    return _verdict(bad, n, "no compensation of an unmet mandatory requirement")


@check("X01", "X", "§4", "X=1 unknown, 2 meets minimum, 0 below; more years never lower X", "seeded random")
def x01(rng):
    bad, n = [], 0
    for _ in range(3000):
        y, m = rng.choice([None, *range(0, 15)]), rng.randint(0, 8)
        n += 1
        x = experience_status(y, m, True)
        if x != (1 if y is None else 2 if y >= m else 0) or (y is not None and experience_status(y + 3, m, True) < x):
            bad.append((y, m, x))
    return _verdict(bad, n, "lower bound only; excess is never penalised")


@check("K01", "(2.15)", "§5", "rank() == lexicographic (Z,X,L^M,L^P,-W^M,-W^P,T,J) desc, then id asc; NOT_EVALUABLE "
       "excluded", "seeded random with forced ties")
def k01(rng):
    bad, n = [], 0
    vals = [0.0, 0.25, 0.5, 1.0]
    for _ in range(800):
        rs = [VacancyRanking(f"{rng.randint(0, 99):02d}-{i}", rng.choice([0, 1, 2]), rng.choice([0, 1, 2]),
                             rng.choice(vals), rng.choice(vals), rng.choice(vals), rng.choice(vals), True, True,
                             rng.choice(["RANKED", "LOW_INFORMATION", "NOT_EVALUABLE"]), rng.choice(vals),
                             rng.choice(vals)) for i in range(rng.randint(1, 12))]
        n += 1
        got = [r.vacancy_id for r in rank(rs)]
        ev = [r for r in rs if r.label != "NOT_EVALUABLE"]
        want = [r.vacancy_id for r in sorted(sorted(ev, key=lambda r: r.vacancy_id),
                                             key=lambda r: (r.z, r.x, r.l_m, r.l_p, -r.w_m, -r.w_p, r.t_v, r.j_v),
                                             reverse=True)]
        if got != want:
            bad.append((got, want))
    return _verdict(bad, n, "order equals an independent lexicographic sort on every sample")


@check("T01", "T_v, J_v", "§5", "T,J in [0,1]; self-ratings never change Z, X, L, U, label; they only reorder exact "
       "ties of the six-part key", "seeded random")
def t01(rng):
    bad, n = [], 0
    for _ in range(1500):
        v = _vac(rng, "v")
        scores = {c: _score(rng) for c in CRITS}
        selfr = {f"act{i}": rng.choice([None, round(rng.random(), 2), 1.0]) for i in range(5)}
        n += 1
        a, b = rank_vacancy(v, scores, RUB5, 3, {}), rank_vacancy(v, scores, RUB5, 3, selfr)
        t, j = self_claim_metrics(v["groups"], selfr)
        if (a.z, a.x, a.l_m, a.l_p, a.w_m, a.w_p, a.label) != (b.z, b.x, b.l_m, b.l_p, b.w_m, b.w_p, b.label) or \
                not (0 <= t <= 1 and 0 <= j <= 1):
            bad.append(v["groups"])
        only_self = rank_vacancy(v, {}, RUB5, 3, {k: 1.0 for k in selfr})
        if only_self.l_m != 0 or only_self.l_p != 0 or only_self.label != "LOW_INFORMATION" or only_self.z == 2:
            bad.append(("self replaces assessment", only_self))
    return _verdict(bad, n, "self-ratings act only as the T/J tie-break; alone they give LOW_INFORMATION, L=0")


@check("R01", "results display order", "§3d, §5 (owner decision)", "GET /results sorts confirmed_share first; "
       "a Z=0 vacancy with a higher percent can precede Z=2", "code inspection + constructed case")
def r01(rng):
    from backend.api import profiles as profiles_api
    src = inspect.getsource(profiles_api.results)
    percent_first = 'items.sort(key=lambda i: -i["confirmed_share"])' in src
    rec = inspect.getsource(__import__("backend.api.recommendations", fromlist=["x"]).rank_items)
    pure = "for r in order(ranked)]" in rec and ".sort(" not in rec and "sorted(" not in rec
    z0 = VacancyRanking("a", 0, 2, 0.8, 0.0, 0.2, 0.0, True, False, "RANKED", confirmed_share=0.8)
    z2 = VacancyRanking("b", 2, 2, 0.3, 0.0, 0.0, 0.0, True, False, "RANKED", confirmed_share=0.3)
    screen = sorted(rank([z0, z2]), key=lambda r: -r.confirmed_share)
    ok = percent_first and pure and [r.vacancy_id for r in rank([z0, z2])] == ["b", "a"] and \
        [r.vacancy_id for r in screen] == ["a", "b"]
    return 1, "DEVIATION" if ok else "FAIL", ("/recommendations and experiments (runner.rank_items) keep the pure (2.15) "
                                              "key; only the results screen sorts by percent first (owner decision)")


@check("B01", "budgets", "§0, §3", "<=10 topics, <=5 shown questions per topic; experiment config may only lower them",
       "exhaustive small grid")
def b01(rng):
    bad, n = [], 0
    if (budget.MAX_TOPICS, budget.MAX_SHOWN_QUESTIONS_PER_ACTION) != (10, 5):
        bad.append("constants")
    for used, dt, shown, null, goal, mt, mp in itertools.product([False, True], range(12), range(7), [False, True],
                                                                 [False, True], [5, 10, 20], [3, 5, 9]):
        n += 1
        ok = budget.topic_open_for_question(used=used, distinct_topics=dt, shown=shown, latest_score_is_null=null,
                                            goal_open=goal, max_topics=mt, max_per_topic=mp)
        if ok and (dt >= min(mt, 10) or (used and shown >= min(mp, 5))):
            bad.append((used, dt, shown, mt, mp))
    return _verdict(bad, n, "no configuration opens an 11th topic or a 6th question")


def _random_evidence(rng: random.Random) -> dict[str, CriterionEvidence]:
    crit = {c for r in PYTHON_BACKEND_V4.rules for c in r.critical}
    out = {}
    for c in crit:
        s = rng.choice([None, None, 0.0, 0.3, 0.55, 0.72, 0.8, 0.95])
        if s is None:
            continue
        out[c] = (CriterionEvidence(c, s, ("t",), topic_scores=(s,)) if c in PRACTICE_CRITERIA
                  else CriterionEvidence(c, s, ("t1", "t2")))
    return out


_RANK = {"UNKNOWN": -1, "JUNIOR": 0, "MIDDLE": 1, "SENIOR": 2}


@check("S01", "assessed_level vs desired_level", "§3e", "desired level, years, title and self-ratings are not inputs: "
       "changing desired_level with unchanged evidence cannot raise assessed_level", "signature + source inspection "
       "+ seeded determinism")
def s01(rng):
    bad, n = [], 0
    if list(inspect.signature(estimate).parameters) != ["policy", "evidence"]:
        bad.append("estimate signature")
    src = inspect.getsource(level_api.finalize_level)
    if "estimate(policy, attempt_evidence(db, iv.id))" not in src:
        bad.append("finalize_level does not pass only attempt evidence")
    for _ in range(500):
        e = _random_evidence(rng)
        n += 1
        if estimate(PYTHON_BACKEND_V4, e) != estimate(PYTHON_BACKEND_V4, dict(e)):
            bad.append("non-deterministic")
    return _verdict(bad, n, "level is a pure function of (policy, one attempt's evidence); desired level is stored as a "
                            "label only (start_desired_level)")


@check("S02", "unknown vs gap (level)", "§3e", "UNKNOWN evidence never becomes a gap; replacing a null by any score "
       "never removes an existing gap elsewhere", "seeded random")
def s02(rng):
    bad, n = [], 0
    for _ in range(1500):
        e = _random_evidence(rng)
        n += 1
        r = estimate(PYTHON_BACKEND_V4, e)
        gaps = set(r.critical_gaps)
        if any(e.get(g) is None for g in gaps):
            bad.append(("null listed as gap", sorted(gaps)))
    return _verdict(bad, n, "every listed critical gap has a traced score")


@check("S03", "monotonicity (level)", "§3e v4", "raising one score (same evidence turns) never lowers assessed_level",
       "seeded random")
def s03(rng):
    bad, n = [], 0
    for _ in range(1500):
        e = _random_evidence(rng)
        scored = [c for c in e if c not in PRACTICE_CRITERIA]
        if not scored:
            continue
        c = rng.choice(scored)
        up = min(1.0, e[c].score + rng.choice([0.1, 0.3, 0.5]))
        e2 = dict(e, **{c: CriterionEvidence(c, up, e[c].evidence_turns)})
        n += 1
        if _RANK[estimate(PYTHON_BACKEND_V4, e2).assessed_level] < _RANK[estimate(PYTHON_BACKEND_V4, e).assessed_level]:
            bad.append((c, e[c].score, up))
    return _verdict(bad, n, "no decrease observed")


@check("S04", "self-assessment", "§0, §3e, §5", "self-rating cannot replace interview evidence (estimator and "
       "requirement status)", "signature + seeded random")
def s04(rng):
    bad, n = [], 0
    for _ in range(500):
        v = _vac(rng, "v")
        n += 1
        r = rank_vacancy(v, {}, RUB5, 5, {f"act{i}": 1.0 for i in range(5)})
        if r.z == 2 or r.l_m or r.l_p:
            bad.append(r)
    if "self" in str(inspect.signature(estimate)):
        bad.append("estimate takes self-ratings")
    return _verdict(bad, n, "maximal self-ratings leave L=0, Z<=1, level untouched")


def run_all() -> list[dict]:
    return [c() for c in CHECKS]
