"""Candidate specs and answer providers for experiment runs. Answers are data typed into the real interview API."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

DEFAULT_ANSWER = "Не знаю."


@dataclass(frozen=True)
class CandidateSpec:
    candidate_id: str
    desired_title: str
    years_experience: int | None
    target_level: str | None
    track: str | None
    location: str
    work_mode: str | None
    self_ratings: dict[str, float] = field(default_factory=dict)  # action_id -> 0..1; absent = unknown

    @classmethod
    def from_json(cls, d: Mapping[str, Any]) -> "CandidateSpec":
        return cls(candidate_id=str(d["candidate_id"]), desired_title=d.get("desired_title", ""),
                   years_experience=d.get("years_experience"), target_level=d.get("target_level"),
                   track=d.get("track"), location=d.get("location", ""), work_mode=d.get("work_mode"),
                   self_ratings={str(k): float(v) for k, v in (d.get("self_ratings") or {}).items()})


class AnswerProvider(Protocol):
    source: str  # "SCRIPTED" | "HUMAN" | "SIMULATED"

    def answer(self, candidate: CandidateSpec, turn: Mapping[str, Any]) -> str:
        """turn has action_id, question_text, ordinal_in_topic (1-based)."""
        ...


class ScriptedProvider:
    """{"<candidate_id>": {"<action_id>": ["answer1", ...], "default": "..."}}; missing => default => DEFAULT_ANSWER."""

    source = "SCRIPTED"

    def __init__(self, data: Mapping[str, Mapping[str, Any]]):
        self._data = data

    @classmethod
    def from_file(cls, path: Path | str) -> "ScriptedProvider":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def answer(self, candidate: CandidateSpec, turn: Mapping[str, Any]) -> str:
        script = self._data.get(candidate.candidate_id) or {}
        answers = script.get(turn["action_id"])
        n = int(turn["ordinal_in_topic"])
        if isinstance(answers, list) and 1 <= n <= len(answers):
            return str(answers[n - 1])
        return str(script.get("default") or DEFAULT_ANSWER)
