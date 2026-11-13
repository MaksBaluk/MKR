"""Evaluator output schema and structural acceptance checks. MATH_SPEC §3."""

from __future__ import annotations

import math
from collections.abc import Mapping

from pydantic import BaseModel, Field, field_validator


class EvidenceRef(BaseModel):
    turn_id: str
    exact_excerpt: str = Field(min_length=1)


class CriterionResult(BaseModel):
    criterion_id: str
    score: float | None
    reason: str
    evidence: list[EvidenceRef]


class EvaluatorOutput(BaseModel):
    action_id: str
    rubric_version: str
    criteria: list[CriterionResult]
    sufficient_evidence: bool = False
    needs_followup: bool = False
    followup_goal: str | None = None
    limitations: str = ""

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
        return "; ".join(str(x) for x in v) if isinstance(v, list) else v


def validate_against_context(
    out: EvaluatorOutput,
    allowed_criteria: set[str],
    turn_texts: Mapping[str, str],
) -> list[str]:
    """Return a list of errors; empty means the output is structurally acceptable."""
    errors: list[str] = []
    for c in out.criteria:
        if c.criterion_id not in allowed_criteria:
            errors.append(f"unknown criterion {c.criterion_id}")
        if c.score is not None and (not math.isfinite(c.score) or not 0.0 <= c.score <= 1.0):
            errors.append(f"score out of range for {c.criterion_id}")
        for ev in c.evidence:
            text = turn_texts.get(ev.turn_id)
            if text is None:
                errors.append(f"unknown turn {ev.turn_id}")
            elif ev.exact_excerpt not in text:
                errors.append(f"excerpt not in turn {ev.turn_id}")
    return errors
