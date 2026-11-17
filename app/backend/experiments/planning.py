"""Deterministic static topic plan: greedy coverage with no answers. Pure: no DB."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from backend.domain.core_flow import RubricMap, planner_state
from backend.domain.planner import OpenState, choose_next
from backend.experiments.config import ExperimentConfig


def plan_topics(revisions: Sequence[Mapping], rubrics: RubricMap, mass: Mapping[str, float],
                max_topics: int) -> list[str]:
    """Greedy over the fixed-Q state; a chosen action closes every group it appears in (assumed covered)."""
    state, weights = planner_state(revisions, {}, rubrics)
    open_groups = set(state.open_groups)
    topics: list[str] = []
    while len(topics) < max_topics:
        st = OpenState(frozenset(open_groups), state.open_alternatives, state.mandatory_groups,
                       state.self_rating_needs_verification)
        available = sorted({a for g in open_groups for a in state.open_alternatives.get(g, frozenset())})
        pick = choose_next(st, weights, available, mass)
        if pick is None:
            break
        topics.append(pick)
        open_groups = {g for g in open_groups if pick not in state.open_alternatives.get(g, frozenset())}
    return topics


def slot_targets(criteria: Sequence[str], k: int, slot: int) -> tuple[str, ...]:
    """Round-robin partition of criteria over k question slots."""
    if k < 1 or not 0 <= slot < k:
        raise ValueError("need k >= 1 and 0 <= slot < k")
    return tuple(criteria[slot::k])


def static_plan_json(topics: Sequence[str], cfg: ExperimentConfig) -> dict:
    return {"topics": list(topics), "questions_per_topic": cfg.static_questions_per_topic,
            "total_budget": cfg.total_budget}
