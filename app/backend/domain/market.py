"""Market profile: prevalence F(c) and normalized planning mass I(c). MATH_SPEC §1."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class VacancyInput:
    vacancy_id: str
    # Each group is a tuple of alternative atomic action IDs (OR within group, AND across groups).
    groups: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class MarketEntry:
    action_id: str
    prevalence: float  # F(c): unique vacancies containing c / N
    mass: float        # I(c): group-normalized planning weight


def compute_market(vacancies: Sequence[VacancyInput]) -> list[MarketEntry]:
    """Return actions sorted by F DESC, I DESC, action_id ASC.

    Vacancies with no groups are excluded from N and mass (they carry no requirements).
    Duplicate actions within a vacancy count once.
    """
    valid = [v for v in vacancies if v.groups]
    n = len(valid)
    if n == 0:
        return []
    prevalence_count: dict[str, int] = defaultdict(int)
    mass: dict[str, float] = defaultdict(float)
    for v in valid:
        present: set[str] = set()
        for group in v.groups:
            alts = set(group)
            present |= alts
            w = 1.0 / (n * len(v.groups))
            for c in alts:
                mass[c] += w / len(alts)
        for c in present:
            prevalence_count[c] += 1
    entries = [
        MarketEntry(c, prevalence_count[c] / n, mass[c]) for c in prevalence_count
    ]
    entries.sort(key=lambda e: (-e.prevalence, -e.mass, e.action_id))
    return entries
