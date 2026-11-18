"""Evaluator output schema and structural acceptance checks. MATH_SPEC §3."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field, field_validator


class EvidenceRef(BaseModel):
    turn_id: str
    exact_excerpt: str = Field(min_length=1)


class CriterionResult(BaseModel):
    criterion_id: str
    score: float | None
    reason: str
    evidence: list[EvidenceRef]


GOAL_TEXT_MAX = 200  # goal reason / expected_evidence are untrusted model text: bounded before storage and prompting


class FollowupGoal(BaseModel):
    criterion_ids: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=GOAL_TEXT_MAX)
    expected_evidence: str = Field(default="", max_length=GOAL_TEXT_MAX)

    @field_validator("reason", "expected_evidence", mode="before")
    @classmethod
    def _truncate(cls, v):
        """Truncate instead of rejecting: an over-long goal must never discard a valid assessment."""
        if v is None:
            return ""
        return v.strip()[:GOAL_TEXT_MAX] if isinstance(v, str) else v


class EvaluatorOutput(BaseModel):
    action_id: str
    rubric_version: str
    criteria: list[CriterionResult]
    sufficient_evidence: bool = False
    needs_followup: bool = False
    followup_goal: FollowupGoal | None = None
    limitations: str = ""
    off_topic: bool = False

    @field_validator("limitations", mode="before")
    @classmethod
    def _coerce_limitations(cls, v):
        """Models return null or a list here; keep the text, never reject an otherwise valid assessment."""
        if v is None:
            return ""
        if isinstance(v, list):
            return "; ".join(str(x) for x in v)
        return v

    @field_validator("followup_goal", mode="before")
    @classmethod
    def _coerce_goal(cls, v):
        """Legacy free-text/list goals carry no concrete gap; malformed dicts must not discard the assessment."""
        if not isinstance(v, dict):
            return None
        try:
            return FollowupGoal.model_validate(v)
        except ValueError:
            return None


def validate_against_context(
    out: EvaluatorOutput,
    allowed_criteria: set[str],
    turn_texts: Mapping[str, str],
) -> list[str]:
    """Return a list of errors; empty means the output is structurally acceptable."""
    errors: list[str] = []
    seen: set[str] = set()
    for c in out.criteria:
        if c.criterion_id in seen:
            errors.append(f"duplicate criterion {c.criterion_id}")
        seen.add(c.criterion_id)
        if c.criterion_id not in allowed_criteria:
            errors.append(f"unknown criterion {c.criterion_id}")
        if c.score is not None and (not math.isfinite(c.score) or not 0.0 <= c.score <= 1.0):
            errors.append(f"score out of range for {c.criterion_id}")
        if c.score is not None and not any(ev.exact_excerpt.strip() for ev in c.evidence):
            errors.append(f"score without evidence for {c.criterion_id}")  # a number must rest on a quoted excerpt
        for ev in c.evidence:
            text = turn_texts.get(ev.turn_id)
            if not ev.exact_excerpt.strip():
                errors.append(f"blank excerpt for {c.criterion_id}")
            elif text is None:
                errors.append(f"unknown turn {ev.turn_id}")
            elif ev.exact_excerpt not in text:
                errors.append(f"excerpt not in turn {ev.turn_id}")
    return errors


def sanitize_goal(
    goal: FollowupGoal | None, allowed: set[str], open_ids: Sequence[str]
) -> FollowupGoal | None:
    """Keep only criteria that are allowed and still open; no remainder means no goal."""
    if goal is None:
        return None
    still_open = set(open_ids)
    keep = [c for c in dict.fromkeys(goal.criterion_ids) if c in allowed and c in still_open]
    return goal.model_copy(update={"criterion_ids": keep}) if keep else None
