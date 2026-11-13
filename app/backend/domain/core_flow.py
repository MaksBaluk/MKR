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

TAU_BY_LEVEL = {1: 0.50, 2: 0.75, 3: 0.90}  # LEGACY_MIGRATION: 1→.50, 2→.75, 3→.90


def tau_for(level: int) -> float:
    return TAU_BY_LEVEL.get(level, 0.75)


@dataclass(frozen=True)
class GroupEval:
    status: str  # SATISFIED | FAILED | UNRESOLVED
    lower: float
    upper: float
    open_alternatives: frozenset[str]


def eval_group(alts: Sequence[Mapping], scores: Mapping[str, float | None]) -> GroupEval:
    """OR over alternatives: SATISFIED if any satisfies, FAILED only if all fail."""
    statuses: list[str] = []
    lower = upper = 0.0
    open_alts: set[str] = set()
    for a in alts:
        cid, tau = a["competency_id"], tau_for(a["required_level"])
        s = scores.get(cid)
        st = mandatory_status(s, tau)
        statuses.append(st)
        if st != "FAILED":
            open_alts.add(cid)
        lo, up = fulfilment_bounds({cid: s}, {cid: tau}, {cid: 1.0}, [cid])
        lower, upper = max(lower, lo), max(upper, up)
    if any(st == "SATISFIED" for st in statuses):
        group_status = "SATISFIED"
    elif statuses and all(st == "FAILED" for st in statuses):
        group_status = "FAILED"
    else:
        group_status = "UNRESOLVED"
    return GroupEval(group_status, lower, upper, frozenset(open_alts))


def planner_state(revisions: Sequence[Mapping], scores: Mapping[str, float | None]) -> tuple[OpenState, dict]:
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
            ev = eval_group(g["alternatives"], scores)
            if ev.status != "SATISFIED":
                open_groups.add(key)
                open_alts[key] = ev.open_alternatives
    state = OpenState(frozenset(open_groups), open_alts, frozenset(mandatory), frozenset())
    return state, weights


def rank_vacancy(vacancy: Mapping, scores: Mapping[str, float | None], user_years: int | None) -> VacancyRanking:
    groups = vacancy["groups"]
    if not groups:
        return VacancyRanking(vacancy["id"], 1, 1, 0.0, 0.0, 0.0, 0.0, False, False, "NOT_EVALUABLE")
    m_L, m_U, p_L, p_U, m_status = [], [], [], [], []
    for g in groups:
        ev = eval_group(g["alternatives"], scores)
        if g["kind"] == "MANDATORY":
            m_L.append(ev.lower); m_U.append(ev.upper); m_status.append(ev.status)
        else:
            p_L.append(ev.lower); p_U.append(ev.upper)
    def mean(xs): return sum(xs) / len(xs) if xs else 0.0
    l_m, l_p = mean(m_L), mean(p_L)
    w_m = mean([u - l for u, l in zip(m_U, m_L)])
    w_p = mean([u - l for u, l in zip(p_U, p_L)])
    any_score = any(scores.get(a["competency_id"]) is not None for g in groups for a in g["alternatives"])
    x = experience_status(user_years, vacancy["years_min"], True)
    share = mean(m_L + p_L)
    return VacancyRanking(vacancy["id"], z_status(m_status), x, l_m, l_p, w_m, w_p,
                          bool(m_L), bool(p_L), "RANKED" if any_score else "LOW_INFORMATION", share)


def explain_vacancy(vacancy: Mapping, scores: Mapping[str, float | None], names: Mapping[str, str],
                    limit: int = 3) -> dict:
    """Human-readable strengths, gaps and unknown count from the same group evaluation as the ranking."""
    strengths: list[str] = []
    gaps: list[str] = []
    unknown = 0
    assessed = 0
    tags: list[str] = []
    for g in vacancy["groups"]:
        if any(scores.get(a["competency_id"]) is not None for a in g["alternatives"]):
            assessed += 1
        label = " / ".join(names.get(a["competency_id"], a["competency_id"]) for a in g["alternatives"])
        for a in g["alternatives"]:
            n = names.get(a["competency_id"], a["competency_id"])
            if n not in tags:
                tags.append(n)
        ev = eval_group(g["alternatives"], scores)
        if ev.status == "SATISFIED":
            strengths.append(label)
        elif ev.status == "FAILED":
            gaps.append(label)
        else:
            unknown += 1
    return {"strengths": strengths[:limit], "gaps": gaps[:limit], "unknown_count": unknown, "tags": tags[:5],
            "groups_total": len(vacancy["groups"]), "groups_assessed": assessed}
