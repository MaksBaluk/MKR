"""Experiment configuration for interview modes A/B/C and ablations. Pure: no DB."""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum

from backend.domain.interview_budget import MAX_SHOWN_QUESTIONS_PER_ACTION, MAX_TOPICS

_FLAGS = ("adaptive_topics", "adaptive_followup", "adaptive_difficulty")


class InterviewMode(str, Enum):
    INITIAL_PROFILE = "INITIAL_PROFILE"
    STATIC_INTERVIEW = "STATIC_INTERVIEW"
    ADAPTIVE_INTERVIEW = "ADAPTIVE_INTERVIEW"


@dataclass(frozen=True)
class ExperimentConfig:
    mode: InterviewMode
    adaptive_topics: bool = True
    adaptive_followup: bool = True
    adaptive_difficulty: bool = True
    max_topics: int = MAX_TOPICS
    max_per_topic: int = MAX_SHOWN_QUESTIONS_PER_ACTION
    total_budget: int | None = None  # None = unlimited (product behaviour)
    static_questions_per_topic: int = 2

    def __post_init__(self) -> None:
        if not 1 <= self.max_topics <= MAX_TOPICS:
            raise ValueError(f"max_topics must be in 1..{MAX_TOPICS}")
        if not 1 <= self.max_per_topic <= MAX_SHOWN_QUESTIONS_PER_ACTION:
            raise ValueError(f"max_per_topic must be in 1..{MAX_SHOWN_QUESTIONS_PER_ACTION}")
        if not 1 <= self.static_questions_per_topic <= self.max_per_topic:
            raise ValueError("static_questions_per_topic must be in 1..max_per_topic")
        if self.total_budget is not None and self.total_budget < 1:
            raise ValueError("total_budget must be >= 1 or None")

    def to_json(self) -> dict:
        d = {f.name: getattr(self, f.name) for f in fields(self)}
        d["mode"] = self.mode.value
        return d

    @classmethod
    def from_json(cls, d: dict) -> "ExperimentConfig":
        """Also reads a raw experiment_runs.config, which carries the run's `answer_source` (ignored here)."""
        d = {k: v for k, v in d.items() if k != "answer_source"}
        return cls(**{**d, "mode": InterviewMode(d["mode"])})


def config_for(mode: InterviewMode, **overrides) -> ExperimentConfig:
    """STATIC forces the three adaptive flags off (overrides of them are rejected)."""
    if mode is InterviewMode.STATIC_INTERVIEW:
        bad = [k for k in _FLAGS if k in overrides]
        if bad:
            raise ValueError(f"static interview fixes flags off; cannot override {bad}")
        overrides = {**overrides, **{k: False for k in _FLAGS}}
    return ExperimentConfig(mode=mode, **overrides)
