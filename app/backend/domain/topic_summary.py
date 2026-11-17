"""Criterion states and per-topic coverage summary. MATH_SPEC (2.8) M_c, (2.9) E_c."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

RubricCriteria = Sequence[tuple[str, float]]  # (criterion_id, weight beta > 0)

CONFIRMED_SCORE = 0.75
DECLINED_SCORE = 0.05
MIN_COVERAGE_FOR_OVERALL = 0.6
SELF_CLAIM_THRESHOLD = 0.7
SELF_GAP = 0.25

CriterionState = Literal["UNKNOWN", "WEAK", "CONFIRMED", "DECLINED"]


def criterion_state(score: float | None, sufficient: bool) -> CriterionState:
    if score is None:
        return "UNKNOWN"
    if score >= CONFIRMED_SCORE:
        return "CONFIRMED"
    if score <= DECLINED_SCORE and sufficient:
        return "DECLINED"
    return "WEAK"


def open_criteria(
    rubric: RubricCriteria, scores: Mapping[str, float | None], sufficient: bool
) -> list[str]:
    """Criteria still worth asking about, in rubric order: UNKNOWN or WEAK."""
    return [
        cid
        for cid, _ in rubric
        if criterion_state(scores.get(cid), sufficient) in ("UNKNOWN", "WEAK")
    ]


@dataclass(frozen=True)
class TopicSummary:
    m: float | None
    e: float
    assessed: tuple[str, ...]
    unknown: tuple[str, ...]
    overall_level_allowed: bool


def topic_summary(rubric: RubricCriteria, scores: Mapping[str, float | None]) -> TopicSummary:
    if any(w <= 0 for _, w in rubric):
        raise ValueError("rubric weights must be positive")
    assessed = tuple(c for c, _ in rubric if scores.get(c) is not None)
    unknown = tuple(c for c, _ in rubric if scores.get(c) is None)
    total = sum(w for _, w in rubric)
    if total <= 0:
        return TopicSummary(None, 0.0, (), (), False)
    known_w = sum(w for c, w in rubric if scores.get(c) is not None)
    m = (
        sum(w * scores[c] for c, w in rubric if scores.get(c) is not None) / known_w  # type: ignore[operator]
        if known_w > 0
        else None
    )
    e = known_w / total
    return TopicSummary(m, e, assessed, unknown, e >= MIN_COVERAGE_FOR_OVERALL)


def needs_verification(self_rating: float | None, summary: TopicSummary | None) -> bool:
    """High self-claim not yet backed by enough evidence, or contradicted by M_c. Planner tie-break only."""
    if self_rating is None or self_rating < SELF_CLAIM_THRESHOLD:
        return False
    if summary is None or summary.e < MIN_COVERAGE_FOR_OVERALL:
        return True
    return summary.m is not None and self_rating - summary.m >= SELF_GAP
