"""Requirement thresholds, fulfilment bounds and mandatory statuses. MATH_SPEC §4."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

MandatoryStatus = Literal["SATISFIED", "FAILED", "UNRESOLVED"]


def epsilon(tau: float) -> float:
    """Gray-zone margin ε(τ) = min(0.05, τ/2)."""
    return min(0.05, tau / 2.0)


def mandatory_status(score: float | None, tau: float) -> MandatoryStatus:
    if score is None:
        return "UNRESOLVED"
    if score >= tau:
        return "SATISFIED"
    if score < tau - epsilon(tau):
        return "FAILED"
    return "UNRESOLVED"


def fulfilment_bounds(
    scores: Mapping[str, float | None],
    targets: Mapping[str, float],
    weights: Mapping[str, float],
    required_ids: Sequence[str],
) -> tuple[float, float]:
    """Return (L, U) for one alternative. Unknown criteria contribute [0, weight]."""
    total = sum(weights[d] for d in required_ids)
    if total <= 0:
        raise ValueError("required criteria must have positive total weight")
    known = 0.0
    unknown = 0.0
    for d in required_ids:
        s = scores.get(d)
        if s is None:
            unknown += weights[d]
        else:
            known += weights[d] * min(1.0, s / targets[d])
    lower = known / total
    return lower, lower + unknown / total


Experience = Literal[0, 1, 2]


def experience_status(declared_years: float | None, minimum_years: float, is_hard: bool) -> Experience:
    """X: 2 meets minimum, 0 below, 1 unknown. Excess is never penalized. `is_hard` is recorded upstream."""
    del is_hard  # hard vs ranking is decided by the cohort filter H, not here
    if declared_years is None:
        return 1
    return 2 if declared_years >= minimum_years else 0
