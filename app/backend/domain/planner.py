"""Fixed-state greedy weighted coverage planner. MATH_SPEC §2."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

GroupKey = tuple[str, int]


@dataclass(frozen=True)
class OpenState:
    open_groups: frozenset[GroupKey]
    open_alternatives: Mapping[GroupKey, frozenset[str]]
    mandatory_groups: frozenset[GroupKey]
    self_rating_needs_verification: frozenset[str]


def coverage(state: OpenState, weights: Mapping[GroupKey, float], topic: frozenset[str]) -> float:
    """Q_t(T) = sum w_vg * u_t(v,g) * 1[T ∩ A_open ≠ ∅]."""
    total = 0.0
    for g in state.open_groups:
        if topic & state.open_alternatives.get(g, frozenset()):
            total += weights.get(g, 0.0)
    return total


def choose_next(
    state: OpenState,
    weights: Mapping[GroupKey, float],
    available: Sequence[str],
    market_mass: Mapping[str, float],
) -> str | None:
    """argmax marginal coverage; ties: open mandatory groups influenced, needs-verify, I(c), id ASC."""
    base = coverage(state, weights, frozenset())
    best: tuple | None = None
    best_action: str | None = None
    for c in available:
        gain = coverage(state, weights, frozenset({c})) - base
        if gain <= 0.0:
            continue
        mandatory_hit = sum(
            1
            for g in state.mandatory_groups
            if g in state.open_groups and c in state.open_alternatives.get(g, frozenset())
        )
        key = (
            -gain,
            -mandatory_hit,
            0 if c in state.self_rating_needs_verification else 1,
            -market_mass.get(c, 0.0),
            c,
        )
        if best is None or key < best:
            best, best_action = key, c
    return best_action
