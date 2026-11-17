"""Deterministic question-difficulty controller. Pure: no DB, no API. Never changes or caps criterion scores.

Seniority is only the initial hypothesis; level moves one step at a time from evidence on targeted criteria."""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from backend.domain.interview_budget import can_ask_question, needs_min_followup


class Difficulty(str, Enum):
    BASIC = "BASIC"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"


_ORDER = (Difficulty.BASIC, Difficulty.INTERMEDIATE, Difficulty.ADVANCED)


def rank(d: Difficulty) -> int:
    return _ORDER.index(d)


@dataclass(frozen=True)
class DifficultyConfig:
    up_score: float = 0.75
    down_score: float = 0.50
    min_known_share: float = 0.5
    diagnostic_floor: Difficulty = Difficulty.BASIC


DEFAULT_CONFIG = DifficultyConfig()

Action = Literal["CONTINUE", "FOLLOWUP", "CLOSE"]


@dataclass(frozen=True)
class ControllerState:
    level: Difficulty
    shown: int
    history: tuple[Difficulty, ...]  # levels of questions already shown in this topic


@dataclass(frozen=True)
class DifficultyDecision:
    next_level: Difficulty
    reason: str
    action: Action
    target_criteria: tuple[str, ...]


def market_level(years_min: Sequence[float | None]) -> Literal["junior", "middle", "senior"] | None:
    known = [y for y in years_min if y is not None]
    if not known:
        return None
    m = statistics.median(known)
    return "junior" if m < 2 else "middle" if m < 5 else "senior"


_BY_LEVEL = {"junior": Difficulty.BASIC, "middle": Difficulty.INTERMEDIATE, "senior": Difficulty.ADVANCED}


def initial_difficulty(candidate_level: str | None, market: str | None) -> tuple[Difficulty, str]:
    if candidate_level in _BY_LEVEL:
        return _BY_LEVEL[candidate_level], f"LEVEL:{candidate_level}"
    if market in _BY_LEVEL:
        return _BY_LEVEL[market], f"MARKET:{market}"
    return Difficulty.INTERMEDIATE, "DEFAULT"


def next_step(state: ControllerState, cfg: DifficultyConfig, *, targeted: Sequence[str],
              scores: Mapping[str, float | None], topic_score: float | None, sufficient: bool,
              open_criteria: Sequence[str], goal_open: bool = False) -> DifficultyDecision:
    targets = tuple(open_criteria)
    level = state.level
    if not targets:
        return DifficultyDecision(level, "NO_OPEN_CRITERIA", "CLOSE", targets)
    if not can_ask_question(state.shown):
        return DifficultyDecision(level, "QUESTION_CAP", "CLOSE", targets)
    # Rule 7 close check comes before NO_EVIDENCE: an early close (min-two not owed) also holds after a bank or
    # untargeted question, whose targeted criteria carry no score.
    # The continuation rule lives in three places that must stay equivalent: `enough` here,
    # interview_budget.needs_min_followup and interview_budget.topic_open_for_question (planner eligibility).
    # graded=True: the caller decides only for topics with an accepted assessment (ungraded topics never continue).
    owed = needs_min_followup(state.shown, graded=True, score=topic_score, sufficient=sufficient)
    enough = not (owed or topic_score is None or goal_open)
    known = [s for c in targeted if (s := scores.get(c)) is not None]
    if not known:
        return DifficultyDecision(level, "NO_EVIDENCE+ENOUGH" if enough else "NO_EVIDENCE",
                                  "CLOSE" if enough else "FOLLOWUP", targets)
    share = len(known) / len(targeted)
    mean = sum(known) / len(known)
    r = rank(level)
    if sufficient and share >= cfg.min_known_share and mean >= cfg.up_score:
        new, reason = _ORDER[min(r + 1, 2)], "STRONG"
    elif share == 1.0 and mean < cfg.down_score:
        new, reason = _ORDER[max(r - 1, rank(cfg.diagnostic_floor))], "WEAK"
    else:
        new, reason = level, "PARTIAL"
    if enough:
        return DifficultyDecision(new, reason + "+ENOUGH", "CLOSE", targets)
    return DifficultyDecision(new, reason, "CONTINUE" if new != level else "FOLLOWUP", targets)
