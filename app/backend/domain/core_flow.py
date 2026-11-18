"""Pure assembly of planner state and vacancy ranking from frozen revisions. MATH_SPEC §2, §4–5.

Targets: legacy integer levels map to τ via LEGACY_MIGRATION policy (not employer-stated).
Scores come only from accepted LLM assessments; self-ratings never substitute.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .criteria import experience_status, fulfilment_bounds, mandatory_status
from .planner import OpenState
from .ranking import VacancyRanking, z_status
from .topic_summary import RubricCriteria

RubricMap = Mapping[str, RubricCriteria]  # action_id -> criteria; missing action => [(action_id, 1.0)]

TAU_BY_LEVEL = {1: 0.50, 2: 0.75, 3: 0.90}  # LEGACY_MIGRATION: 1→.50, 2→.75, 3→.90
TAU_SOURCE_LEVEL_MAP = "WORKING_ASSUMPTION_LEVEL_MAP"  # vacancies carry no employer-stated threshold: tau is a working assumption


def tau_for(level: int) -> float:
    return TAU_BY_LEVEL.get(level, 0.75)


def alt_tau(alt: Mapping) -> float | None:
    """Pass threshold of one requirement alternative: its own explicit `tau`, else the working-assumption level map.
    A level outside the map with no explicit tau has no reliable threshold: the alternative is not evaluable (None)."""
    if alt.get("tau") is not None:
        return float(alt["tau"])
    return TAU_BY_LEVEL.get(alt["required_level"])


@dataclass(frozen=True)
class GroupEval:
    status: str  # SATISFIED | FAILED | UNRESOLVED
    lower: float
    upper: float
    open_alternatives: frozenset[str]


def alt_criteria(alt: Mapping, rubrics: RubricMap) -> list[tuple[str, float]]:
    """D_vga: the rubric criteria this requirement needs, in rubric order, with rubric weights.

    An explicit `criterion_ids` is authoritative: ids missing from the rubric are dropped and an empty result means the
    requirement cannot be assessed (never widened to the whole rubric). Only a legacy alternative with no
    `criterion_ids` at all (rows created before migration 0013) falls back to the whole rubric."""
    cid = alt["competency_id"]
    rubric = list(rubrics.get(cid) or [(cid, 1.0)])
    ids = alt.get("criterion_ids")
    if ids is None:
        return rubric
    wanted = set(ids)
    return [(c, w) for c, w in rubric if c in wanted]


def eval_alternative(alt: Mapping, scores: Mapping[str, float | None], rubrics: RubricMap) -> GroupEval:
    """SATISFIED iff every required criterion meets tau; FAILED iff any definitely fails. MATH_SPEC §4.

    No resolvable D_vga or no reliable tau => UNRESOLVED with the widest interval [0, 1]: unknown stays unknown."""
    tau = alt_tau(alt)
    crit = alt_criteria(alt, rubrics)
    if tau is None or not crit:
        return GroupEval("UNRESOLVED", 0.0, 1.0, frozenset({alt["competency_id"]}))
    ids = [c for c, _ in crit]
    sts = [mandatory_status(scores.get(c), tau) for c in ids]
    if all(st == "SATISFIED" for st in sts):
        status = "SATISFIED"
    elif any(st == "FAILED" for st in sts):
        status = "FAILED"
    else:
        status = "UNRESOLVED"
    lo, up = fulfilment_bounds(scores, {c: tau for c in ids}, dict(crit), ids)
    return GroupEval(status, lo, up, frozenset() if status == "FAILED" else frozenset({alt["competency_id"]}))


def eval_group(alts: Sequence[Mapping], scores: Mapping[str, float | None], rubrics: RubricMap) -> GroupEval:
    """OR over alternatives: SATISFIED if any satisfies, FAILED only if all fail."""
    evs = [eval_alternative(a, scores, rubrics) for a in alts]
    statuses = [e.status for e in evs]
    if "SATISFIED" in statuses:
        status = "SATISFIED"
    elif statuses and all(st == "FAILED" for st in statuses):
        status = "FAILED"
    else:
        status = "UNRESOLVED"
    open_alts = frozenset().union(*(e.open_alternatives for e in evs)) if evs else frozenset()
    return GroupEval(status, max((e.lower for e in evs), default=0.0),
                     max((e.upper for e in evs), default=0.0), open_alts)


def _used_criteria(groups: Sequence[Mapping], rubrics: RubricMap) -> set[str]:
    return {c for g in groups for a in g["alternatives"] for c, _ in alt_criteria(a, rubrics)}


def planner_state(revisions: Sequence[Mapping], scores: Mapping[str, float | None], rubrics: RubricMap,
                  self_flags: frozenset[str] = frozenset()) -> tuple[OpenState, dict]:
    open_groups: set[tuple[str, int]] = set()
    open_alts: dict[tuple[str, int], frozenset[str]] = {}
    mandatory: set[tuple[str, int]] = set()
    weights: dict[tuple[str, int], float] = {}
    n = len(revisions)
    for v in revisions:
        for gi, g in enumerate(v["groups"]):
            key = (v["id"], gi)
            weights[key] = 1.0 / (n * len(v["groups"])) if n and v["groups"] else 0.0
            if g["kind"] == "MANDATORY":
                mandatory.add(key)
            ev = eval_group(g["alternatives"], scores, rubrics)
            if ev.status != "SATISFIED":
                open_groups.add(key)
                open_alts[key] = ev.open_alternatives
    state = OpenState(frozenset(open_groups), open_alts, frozenset(mandatory), frozenset(self_flags))
    return state, weights


def self_claim_metrics(groups: Sequence[Mapping], self_ratings: Mapping[str, float | None]) -> tuple[float, float]:
    """(T_v, J_v): b_vg = best known self-rating among group alternatives; normalised by all |G_v| groups."""
    if not groups:
        return 0.0, 0.0
    bs = []
    for g in groups:
        known = [self_ratings[a["competency_id"]] for a in g["alternatives"]
                 if self_ratings.get(a["competency_id"]) is not None]
        if known:
            bs.append(max(known))
    return sum(bs) / len(groups), len(bs) / len(groups)


def rank_vacancy(vacancy: Mapping, scores: Mapping[str, float | None], rubrics: RubricMap,
                 user_years: int | None, self_ratings: Mapping[str, float | None] | None = None) -> VacancyRanking:
    groups = vacancy["groups"]
    if not groups:
        return VacancyRanking(vacancy["id"], 1, 1, 0.0, 0.0, 0.0, 0.0, False, False, "NOT_EVALUABLE")
    m_L, m_U, p_L, p_U, m_status = [], [], [], [], []
    for g in groups:
        ev = eval_group(g["alternatives"], scores, rubrics)
        if g["kind"] == "MANDATORY":
            m_L.append(ev.lower); m_U.append(ev.upper); m_status.append(ev.status)
        else:
            p_L.append(ev.lower); p_U.append(ev.upper)
    def mean(xs): return sum(xs) / len(xs) if xs else 0.0
    l_m, l_p = mean(m_L), mean(p_L)
    w_m = mean([u - l for u, l in zip(m_U, m_L)])
    w_p = mean([u - l for u, l in zip(p_U, p_L)])
    any_score = any(scores.get(c) is not None for c in _used_criteria(groups, rubrics))
    x = experience_status(user_years, vacancy["years_min"], True)
    share = mean(m_L + p_L)
    t_v, j_v = self_claim_metrics(groups, self_ratings or {})
    return VacancyRanking(vacancy["id"], z_status(m_status), x, l_m, l_p, w_m, w_p,
                          bool(m_L), bool(p_L), "RANKED" if any_score else "LOW_INFORMATION", t_v, j_v, share)


def explain_vacancy(vacancy: Mapping, scores: Mapping[str, float | None], rubrics: RubricMap,
                    names: Mapping[str, str], limit: int = 3) -> dict:
    """Human-readable strengths, gaps and unknown count from the same group evaluation as the ranking."""
    strengths: list[str] = []
    gaps: list[str] = []
    unknown = 0
    met_total = gap_total = 0  # uncapped: the display lists below are cut to `limit`
    assessed = 0
    tags: list[str] = []
    for g in vacancy["groups"]:
        if any(scores.get(c) is not None for c in _used_criteria([g], rubrics)):
            assessed += 1
        label = " / ".join(names.get(a["competency_id"], a["competency_id"]) for a in g["alternatives"])
        for a in g["alternatives"]:
            n = names.get(a["competency_id"], a["competency_id"])
            if n not in tags:
                tags.append(n)
        ev = eval_group(g["alternatives"], scores, rubrics)
        if ev.status == "SATISFIED":
            strengths.append(label)
            met_total += 1
        elif ev.status == "FAILED":
            gaps.append(label)
            gap_total += 1
        else:
            unknown += 1
    return {"strengths": strengths[:limit], "gaps": gaps[:limit], "unknown_count": unknown,
            "met_count": met_total, "gap_count": gap_total, "tags": tags[:5],
            "groups_total": len(vacancy["groups"]), "groups_assessed": assessed}
