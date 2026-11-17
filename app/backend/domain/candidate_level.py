"""Candidate seniority for the Interviewer context: explicit title words win, otherwise years of experience."""
from __future__ import annotations

import re

_TITLE_LEVELS = (
    ("junior", re.compile(r"\b(junior|jun|trainee|intern|entry|джуніор|джун|стажер|стажист|початківець)\b", re.I)),
    ("middle", re.compile(r"\b(middle|mid|мідл|міддл)\b", re.I)),
    ("senior", re.compile(r"\b(senior|sr|lead|principal|head|staff|architect|сеньйор|сеніор|лід|керівник|архітектор)\b",
                          re.I)),
)


def candidate_level(desired_title: str | None, years_experience: int | None) -> str | None:
    """junior | middle | senior | None. Years: <2 junior, 2-4 middle, 5+ senior."""
    for level, pattern in _TITLE_LEVELS:
        if desired_title and pattern.search(desired_title):
            return level
    if years_experience is None:
        return None
    if years_experience < 2:
        return "junior"
    return "middle" if years_experience < 5 else "senior"


def resolve_level(target_level: str | None, desired_title: str | None, years_experience: int | None) -> str | None:
    """The level the candidate chose wins; «lead» uses the senior depth. Otherwise title words, then years."""
    if target_level:
        return "senior" if target_level == "lead" else target_level
    return candidate_level(desired_title, years_experience)
