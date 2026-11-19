"""Evaluator output schema and structural acceptance checks. MATH_SPEC §3."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence, Set

from pydantic import BaseModel, Field, field_validator


class EvidenceRef(BaseModel):
    turn_id: str
    exact_excerpt: str = Field(min_length=1)


NO_EXPERIENCE_MAX_SCORE = 0.25  # a no-experience declaration grades the criterion in the lowest band only


class CriterionResult(BaseModel):
    criterion_id: str
    score: float | None
    reason: str
    evidence: list[EvidenceRef]
    # Topic criteria only: the quoted answer is the candidate's own statement of no experience with this criterion's
    # tool. Optional; absent or false means "not declared". Checked in validate_against_context.
    no_experience: bool = False

    @field_validator("no_experience", mode="before")
    @classmethod
    def _coerce_no_experience(cls, v):
        return False if v is None else v


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
    practice: list[CriterionResult] = []  # professional-practice criteria graded from the same answers (optional)

    @field_validator("practice", mode="before")
    @classmethod
    def _coerce_practice(cls, v):
        """A missing/null practice list means "not graded"; its items are still validated strictly."""
        return [] if v is None else v

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
    allowed_practice: Set[str] = frozenset(),
) -> list[str]:
    """Return a list of errors; empty means the output is structurally acceptable.

    Practice criteria (optional, possibly a subset) follow the same id, range and verbatim-evidence rules."""
    errors: list[str] = []
    seen: set[str] = set()
    for c, allowed in [(c, allowed_criteria) for c in out.criteria] + [(c, allowed_practice) for c in out.practice]:
        if c.criterion_id in seen:
            errors.append(f"duplicate criterion {c.criterion_id}")
        seen.add(c.criterion_id)
        if c.criterion_id not in allowed:
            errors.append(f"unknown criterion {c.criterion_id}")
        if c.score is not None and (not math.isfinite(c.score) or not 0.0 <= c.score <= 1.0):
            errors.append(f"score out of range for {c.criterion_id}")
        if c.score is not None and not any(ev.exact_excerpt.strip() for ev in c.evidence):
            errors.append(f"score without evidence for {c.criterion_id}")  # a number must rest on a quoted excerpt
        if c.no_experience and (allowed is allowed_practice or c.score is None or c.score >= NO_EXPERIENCE_MAX_SCORE
                                or not c.evidence):
            # a declaration must be a quoted statement (verbatim, checked below) graded in the lowest band
            errors.append(f"invalid no_experience for {c.criterion_id}")
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
