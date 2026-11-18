"""math_validation.csv: control scenarios for the thesis formulas of chapter 2. Expected values are worked out by hand
in this file (see the `why` column); actual values come from the production domain code. Unit-level checks only:
they say nothing about empirical quality."""
from __future__ import annotations

import json
import math
from types import SimpleNamespace

from backend.api.core import effective_rows
from backend.domain.assessment import CriterionResult, EvaluatorOutput, EvidenceRef, validate_against_context
from backend.domain.core_flow import alt_criteria, eval_alternative, eval_group, planner_state, rank_vacancy, self_claim_metrics
from backend.domain.criteria import epsilon, fulfilment_bounds, mandatory_status
from backend.domain.interview_budget import can_ask_question, can_start_topic, needs_min_followup, topic_open_for_question
from backend.domain.market import VacancyInput, compute_market
from backend.domain.planner import OpenState, choose_next, coverage
from backend.domain.ranking import VacancyRanking, rank, z_status
from backend.domain.topic_summary import criterion_state, topic_summary
from scripts.chapter4.common import OUT, write_csv

HEADER = ["id", "area", "formula", "input", "expected", "actual", "status", "why"]
ROWS: list[dict] = []


def same(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return isinstance(a, (int, float)) and isinstance(b, (int, float)) and math.isclose(a, b, abs_tol=1e-9)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    return a == b


def check(cid, area, formula, inp, expected, actual, why=""):
    ok = same(expected, actual)
    if isinstance(inp, set):  # a set literal of one string is just a description
        inp = ", ".join(sorted(inp))
    ROWS.append({"id": cid, "area": area, "formula": formula, "input": json.dumps(inp, ensure_ascii=False, default=str),
                 "expected": json.dumps(expected, ensure_ascii=False, default=str),
                 "actual": json.dumps(actual, ensure_ascii=False, default=str), "status": "PASS" if ok else "FAIL", "why": why})


def r4(x):
    return round(x, 9) if isinstance(x, float) else x


# ---- market (2.1)-(2.3): F(c), I(c)
V = [VacancyInput("v1", (("a",), ("b", "c"))), VacancyInput("v2", (("a",),)), VacancyInput("v3", (("c",),))]
m = {e.action_id: (r4(e.prevalence), r4(e.mass)) for e in compute_market(V)}
check("M01", "market", "F(c)=|V_c|/N", {"vacancies": "v1:(a)(b|c), v2:(a), v3:(c)"},
      {"a": 2 / 3, "b": 1 / 3, "c": 2 / 3}, {k: r4(v[0]) for k, v in m.items()}, "N=3; a in v1,v2; b in v1; c in v1,v3")
check("M02", "market", "I(c)=sum_v sum_g w_vg/|A_vg|, w_vg=1/(N*G_v)", {"same": "as M01"},
      {"a": 0.5, "b": 1 / 12, "c": 5 / 12}, {k: r4(v[1]) for k, v in m.items()},
      "a: 1/6+1/3; b: (1/6)/2; c: (1/6)/2+1/3")
check("M03", "market", "sum I(c)=1", {}, 1.0, r4(sum(v[1] for v in m.values())), "mass is normalised")
check("M04", "market", "order F desc, I desc, id", {}, ["a", "c", "b"], [e.action_id for e in compute_market(V)],
      "a and c tie on F=2/3; a has larger I")
check("M05", "market", "duplicate action in one vacancy counts once", {"v": "(a)(a|b)"}, 1.0,
      next(e.prevalence for e in compute_market([VacancyInput("v", (("a",), ("a", "b")))]) if e.action_id == "a"))
check("M06", "market", "vacancy without groups is outside N", {"v": [(), "(a)"]}, 1.0,
      compute_market([VacancyInput("e", ()), VacancyInput("v", (("a",),))])[0].prevalence)

# ---- planner (2.4)-(2.5): greedy Q_t
g1, g2 = ("v1", 0), ("v2", 0)
st = OpenState(frozenset({g1, g2}), {g1: frozenset({"x", "z"}), g2: frozenset({"y", "z"})}, frozenset({g1}), frozenset())
w = {g1: 0.6, g2: 0.4}
check("P01", "planner", "Q_t(T)=sum w*1[T∩A_open≠∅]", {"weights": "g1=0.6, g2=0.4", "note": "z covers both groups"}, [0.6, 0.4, 1.0],
      [coverage(st, w, frozenset({"x"})), coverage(st, w, frozenset({"y"})), coverage(st, w, frozenset({"z"}))])
check("P02", "planner", "argmax marginal coverage", {"available": ["x", "y", "z"]}, "z", choose_next(st, w, ["x", "y", "z"], {}))
st2 = OpenState(frozenset({g1, g2}), {g1: frozenset({"x"}), g2: frozenset({"y"})}, frozenset({g2}), frozenset())
check("P03", "planner", "tie 1: open mandatory groups touched", {"equal gain 0.5/0.5; y hits mandatory"}, "y",
      choose_next(st2, {g1: 0.5, g2: 0.5}, ["x", "y"], {"x": 0.9, "y": 0.1}))
st3 = OpenState(frozenset({g1, g2}), {g1: frozenset({"x"}), g2: frozenset({"y"})}, frozenset(), frozenset({"y"}))
check("P04", "planner", "tie 2: self-rating needs verification", {"y flagged"}, "y",
      choose_next(st3, {g1: 0.5, g2: 0.5}, ["x", "y"], {"x": 0.9, "y": 0.1}))
st4 = OpenState(frozenset({g1, g2}), {g1: frozenset({"x"}), g2: frozenset({"y"})}, frozenset(), frozenset())
check("P05", "planner", "tie 3: market mass I(c), then id", {"I(x)=.1, I(y)=.9"}, "y",
      choose_next(st4, {g1: 0.5, g2: 0.5}, ["x", "y"], {"x": 0.1, "y": 0.9}))
check("P06", "planner", "no positive gain => stop", {"all groups closed"}, None,
      choose_next(OpenState(frozenset(), {}, frozenset(), frozenset()), {}, ["x"], {}))

# ---- AND / OR requirements
RUB = {"c": [("c.a", 1.0), ("c.b", 1.0), ("c.c", 1.0), ("c.d", 1.0), ("c.e", 1.0)],
       "o": [("o.a", 1.0), ("o.b", 1.0)]}


def alt(cid="c", level=2, ids=None):
    return {"competency_id": cid, "required_level": level, **({"criterion_ids": ids} if ids is not None else {})}


S_OK = {"c.a": 0.8, "c.b": 0.8, "c.c": 0.8, "c.d": 0.8, "c.e": 0.8}
S_BAD = {k: 0.1 for k in S_OK}
OR_ok_fail = eval_group([alt("c"), alt("o")], {**S_OK, "o.a": 0.0, "o.b": 0.0}, RUB).status
check("A01", "AND/OR", "OR group: SATISFIED if any alternative SATISFIED", {"alt1": "satisfied", "alt2": "failed"}, "SATISFIED", OR_ok_fail)
check("A02", "AND/OR", "OR group: FAILED only if all alternatives FAILED", {"both failed"}, "FAILED",
      eval_group([alt("c"), alt("o")], {**S_BAD, "o.a": 0.0, "o.b": 0.0}, RUB).status)
check("A03", "AND/OR", "OR group: failed + unknown => UNRESOLVED", {"alt1 failed, alt2 unassessed"}, "UNRESOLVED",
      eval_group([alt("c"), alt("o")], S_BAD, RUB).status)
vac = lambda groups: {"id": "v", "years_min": 0, "groups": groups}
G = lambda kind, *alts: {"id": "g", "kind": kind, "alternatives": list(alts)}
check("A04", "AND/OR", "Z: any mandatory FAILED => 0", {"mandatory g1 satisfied, g2 failed"}, 0,
      rank_vacancy(vac([G("MANDATORY", alt("c")), G("MANDATORY", alt("o"))]), {**S_OK, "o.a": 0.0, "o.b": 0.0}, RUB, 3).z)
check("A05", "AND/OR", "Z: all mandatory SATISFIED => 2", {"both satisfied"}, 2,
      rank_vacancy(vac([G("MANDATORY", alt("c")), G("MANDATORY", alt("o"))]), {**S_OK, "o.a": 0.9, "o.b": 0.9}, RUB, 3).z)
check("A06", "AND/OR", "Z: unknown mandatory => 1, not 0", {"g2 unassessed"}, 1,
      rank_vacancy(vac([G("MANDATORY", alt("c")), G("MANDATORY", alt("o"))]), S_OK, RUB, 3).z)
check("A07", "AND/OR", "z_status(empty mandatory)=1", {}, 1, z_status([]))

# ---- budget
check("B01", "budget", "max 10 topics", {"topics_so_far": [9, 10]}, [True, False], [can_start_topic(9), can_start_topic(10)])
check("B02", "budget", "max 5 questions per topic", {"shown": [4, 5]}, [True, False], [can_ask_question(4), can_ask_question(5)])
check("B03", "budget", "min two questions unless sufficient & >=0.75", {"shown=1,graded,score=.6,suff"}, True,
      needs_min_followup(1, graded=True, score=0.6, sufficient=True))
check("B04", "budget", "early close: sufficient & score>=0.75", {"shown=1,score=.8,suff"}, False,
      needs_min_followup(1, graded=True, score=0.8, sufficient=True))
check("B05", "budget", "started topic not re-asked at cap", {"shown=5,goal open"}, False,
      topic_open_for_question(used=True, distinct_topics=3, shown=5, latest_score_is_null=True, goal_open=True))
check("B06", "budget", "no new topic after ten", {"distinct=10"}, False,
      topic_open_for_question(used=False, distinct_topics=10, shown=0, latest_score_is_null=False))

# ---- criteria s_cd, coverage E_c, M_c (2.8)-(2.9)
rub5 = [(f"k.{i}", 1.0) for i in range(5)]
t1 = topic_summary(rub5, {"k.0": 1.0, "k.1": None, "k.2": None, "k.3": None, "k.4": None})
check("C01", "criteria", "E_c=assessed weight/total weight", {"1 of 5 assessed, score 1.0"}, 0.2, t1.e)
check("C02", "criteria", "M_c=weighted mean of assessed", {"same"}, 1.0, t1.m)
check("C03", "criteria", "1 of 5 confirmed does not allow an overall level", {"same", "MIN_COVERAGE 0.6"}, False, t1.overall_level_allowed)
t2 = topic_summary(rub5, {f"k.{i}": 0.9 for i in range(4)} | {"k.4": None})
check("C04", "criteria", "overall level needs E_c >= 0.6", {"4 of 5 assessed"}, True, t2.overall_level_allowed)
check("C05", "criteria", "criterion state: null=UNKNOWN, <.75=WEAK, >=.75=CONFIRMED, <=.05 & sufficient=DECLINED", {"scores": [None, .5, .75, .0]},
      ["UNKNOWN", "WEAK", "CONFIRMED", "DECLINED"],
      [criterion_state(None, False), criterion_state(0.5, False), criterion_state(0.75, False), criterion_state(0.0, True)])
check("C06", "criteria", "weights beta: heavier criterion moves M_c", {"b=3 score 1, b=1 score 0"}, 0.75,
      topic_summary([("a", 3.0), ("b", 1.0)], {"a": 1.0, "b": 0.0}).m)
check("C07", "criteria", "requirement needing all 5 criteria with 1 assessed => UNRESOLVED", {"1 of 5 criteria >= tau"}, "UNRESOLVED",
      eval_alternative(alt("c", ids=[f"c.{x}" for x in "abcde"]), {"c.a": 1.0}, RUB).status)
check("C08", "criteria", "D_vga subset: requirement needs only c.a,c.b", {"c.a=.8,c.b=.8, others unknown"}, "SATISFIED",
      eval_alternative(alt("c", ids=["c.a", "c.b"]), {"c.a": 0.8, "c.b": 0.8}, RUB).status)

# ---- bounds (2.10)-(2.13)
L, U = fulfilment_bounds({"a": 0.75, "b": None}, {"a": 0.75, "b": 0.75}, {"a": 1.0, "b": 1.0}, ["a", "b"])
check("L01", "bounds", "L=sum_known beta*h/sum beta; U=L+unknown/sum", {"a=0.75=tau, b unknown"}, [0.5, 1.0], [L, U])
L, U = fulfilment_bounds({"a": 0.375}, {"a": 0.75}, {"a": 1.0}, ["a"])
check("L02", "bounds", "h=min(1,s/tau)", {"s=.375,tau=.75"}, [0.5, 0.5], [L, U])
L, U = fulfilment_bounds({"a": 0.99}, {"a": 0.75}, {"a": 1.0}, ["a"])
check("L03", "bounds", "h capped at 1", {"s=.99,tau=.75"}, [1.0, 1.0], [L, U])
L, U = fulfilment_bounds({"a": None, "b": None}, {"a": 0.75, "b": 0.75}, {"a": 1.0, "b": 1.0}, ["a", "b"])
check("L04", "bounds", "all unknown => [0,1]", {}, [0.0, 1.0], [L, U])
check("L05", "bounds", "new evidence never widens: U-L shrinks", {"unknown -> known"}, True,
      (lambda a, b: (b[1] - b[0]) <= (a[1] - a[0]))(
          fulfilment_bounds({"a": 0.9, "b": None}, {"a": .75, "b": .75}, {"a": 1., "b": 1.}, ["a", "b"]),
          fulfilment_bounds({"a": 0.9, "b": 0.2}, {"a": .75, "b": .75}, {"a": 1., "b": 1.}, ["a", "b"])))

# ---- tau and epsilon
for tau in (0.5, 0.75, 0.9):
    e = epsilon(tau)
    check(f"T{int(tau * 100)}", "tau/epsilon", "eps=min(.05,tau/2); s>=tau SATISFIED; [tau-eps,tau) UNRESOLVED; <tau-eps FAILED",
          {"tau": tau, "scores": [tau, tau - e, tau - e - 0.001]}, ["SATISFIED", "UNRESOLVED", "FAILED"],
          [mandatory_status(tau, tau), mandatory_status(tau - e, tau), mandatory_status(tau - e - 0.001, tau)])
check("T00", "tau/epsilon", "eps(tau)=tau/2 for tau<.1", {"tau": 0.06}, 0.03, epsilon(0.06))
check("T01", "tau/epsilon", "unknown score => UNRESOLVED (not FAILED)", {"score": None}, "UNRESOLVED", mandatory_status(None, 0.75))

# ---- lexicographic ranking (2.15) and T_v, J_v
RK = lambda vid, z, x, lm, lp, wm=0.0, wp=0.0, t=0.0, j=0.0: VacancyRanking(vid, z, x, lm, lp, wm, wp, True, True, "RANKED", t, j)
check("R01", "ranking", "Z dominates every later term", {"A Z=0 L^M=.9; B Z=2 L^M=.1"}, ["B", "A"],
      [r.vacancy_id for r in rank([RK("A", 0, 2, .9, .9), RK("B", 2, 0, .1, 0.)])])
check("R02", "ranking", "X after Z", {"equal Z; A X=0, B X=2"}, ["B", "A"], [r.vacancy_id for r in rank([RK("A", 1, 0, .9, .9), RK("B", 1, 2, .1, 0.)])])
check("R03", "ranking", "L^M, then L^P, then narrower W^M", {"equal Z,X"}, ["B", "C", "A"],
      [r.vacancy_id for r in rank([RK("A", 1, 1, .4, .9), RK("B", 1, 1, .6, .0), RK("C", 1, 1, .4, .95)])])
check("R04", "ranking", "narrower interval W^M ranks first", {"equal L"}, ["B", "A"],
      [r.vacancy_id for r in rank([RK("A", 1, 1, .5, .5, wm=.5), RK("B", 1, 1, .5, .5, wm=.1)])])
check("R05", "ranking", "T_v then J_v only break exact ties", {"equal key; A T=.9, B T=.2"}, ["A", "B"],
      [r.vacancy_id for r in rank([RK("B", 1, 1, .5, .5, t=.2), RK("A", 1, 1, .5, .5, t=.9)])])
check("R06", "ranking", "T_v never overrides L^M", {"B has high T but lower L^M"}, ["A", "B"],
      [r.vacancy_id for r in rank([RK("B", 1, 1, .4, .5, t=1.0, j=1.0), RK("A", 1, 1, .5, .5)])])
check("R07", "ranking", "id breaks the final tie (deterministic)", {"identical keys"}, ["A", "B"],
      [r.vacancy_id for r in rank([RK("B", 1, 1, .5, .5), RK("A", 1, 1, .5, .5)])])
groups = [G("MANDATORY", alt("c")), G("DESIRED", alt("o"))]
check("R08", "ranking", "T_v=mean of best self-rating per group over all |G_v|; J_v=share of groups with a rating", {"self c=.8"}, [0.4, 0.5],
      list(self_claim_metrics(groups, {"c": 0.8})))
rv_a = rank_vacancy(vac(groups), {"c.a": 0.8, "c.b": 0.8, "c.c": 0.8, "c.d": 0.8, "c.e": 0.8}, RUB, 3, {})
rv_b = rank_vacancy(vac(groups), {"c.a": 0.8, "c.b": 0.8, "c.c": 0.8, "c.d": 0.8, "c.e": 0.8}, RUB, 3, {"c": 1.0, "o": 1.0})
check("R09", "ranking", "self-ratings are not evidence: Z, L^M, L^P unchanged", {"self-rating 1.0 vs none"}, True,
      (rv_a.z, rv_a.l_m, rv_a.l_p) == (rv_b.z, rv_b.l_m, rv_b.l_p) and rv_b.t_v > rv_a.t_v)

# ---- unknown vs failed
check("U01", "unknown", "unknown criterion is not a failed one", {"all required criteria unassessed"}, ["UNRESOLVED", 0.0, 1.0],
      (lambda e: [e.status, e.lower, e.upper])(eval_alternative(alt("c"), {}, RUB)))
check("U02", "unknown", "known failure outweighs unknowns", {"c.a=0.1, rest unknown"}, "FAILED", eval_alternative(alt("c"), {"c.a": 0.1}, RUB).status)
check("U03", "unknown", "all-unknown vacancy has Z=1 not 0, label LOW_INFORMATION", {}, [1, "LOW_INFORMATION"],
      (lambda r: [r.z, r.label])(rank_vacancy(vac([G("MANDATORY", alt("c"))]), {}, RUB, 3)))
check("U04", "unknown", "criterion ids not in rubric => UNRESOLVED [0,1], never widened", {"ids": ["x.none"]}, ["UNRESOLVED", 0.0, 1.0],
      (lambda e: [e.status, e.lower, e.upper])(eval_alternative(alt("c", ids=["x.none"]), S_OK, RUB)))
check("U05", "unknown", "level outside tau map has no tau => UNRESOLVED", {"required_level": 7}, "UNRESOLVED",
      eval_alternative(alt("c", level=7, ids=["c.a"]), {"c.a": 1.0}, RUB).status)

# ---- revisions: null / off-topic never erase an accepted score
row = lambda cid, score, rev: SimpleNamespace(action_id="c", criterion_id=cid, score=score, revision=rev)
eff = {r.criterion_id: r.score for r in effective_rows([row("c.a", 0.8, 1), row("c.a", None, 2), row("c.b", 0.4, 1), row("c.b", 0.2, 2)])}
check("V01", "revisions", "later null does not erase; later number supersedes", {"c.a: .8 then null; c.b: .4 then .2"}, {"c.a": 0.8, "c.b": 0.2}, eff)
check("V02", "revisions", "history kept", {"4 rows in -> 2 effective"}, 2,
      len(effective_rows([row("c.a", 0.8, 1), row("c.a", None, 2), row("c.b", 0.4, 1), row("c.b", 0.2, 2)])))

# ---- evaluator validation (structural acceptance)
T = {"t1": "Використовував індекси та аналізував EXPLAIN."}
mk = lambda *cs: EvaluatorOutput(action_id="a", rubric_version="v1", criteria=list(cs))
cr = lambda cid, score, *ex: CriterionResult(criterion_id=cid, score=score, reason="r", evidence=[EvidenceRef(turn_id="t1", exact_excerpt=e) for e in ex])
AL = {"a.x", "a.y"}
check("E01", "evaluator", "valid output accepted", {}, [], validate_against_context(mk(cr("a.x", 0.8, "індекси"), cr("a.y", None)), AL, T))
for cid, name, out, key in [("E02", "score without evidence", mk(cr("a.x", 0.9)), "without evidence"),
                            ("E03", "duplicate criterion", mk(cr("a.x", .5, "індекси"), cr("a.x", .9, "EXPLAIN")), "duplicate"),
                            ("E04", "unknown criterion id", mk(cr("a.q", .5, "індекси")), "unknown criterion"),
                            ("E05", "invented quote", mk(cr("a.x", .5, "вигадана цитата")), "not in turn"),
                            ("E06", "blank excerpt", mk(cr("a.x", .5, "  ")), "blank")]:
    check(cid, "evaluator", f"reject: {name}", {}, True, any(key in e for e in validate_against_context(out, AL, T)))


def build() -> list[dict]:
    write_csv(OUT / "math_validation.csv", HEADER, ROWS)
    return ROWS


if __name__ == "__main__":
    rows = build()
    bad = [r for r in rows if r["status"] != "PASS"]
    print(len(rows), "checks;", len(bad), "failed")
    for r in bad:
        print(r["id"], r["expected"], r["actual"])
