"""Deterministic lexicographic vacancy ranking. MATH_SPEC §5."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

Label = Literal["RANKED", "LOW_INFORMATION", "NOT_EVALUABLE"]


@dataclass(frozen=True)
class VacancyRanking:
    vacancy_id: str
    z: Literal[0, 1, 2]
    x: Literal[0, 1, 2]
    l_m: float
    l_p: float
    w_m: float
    w_p: float
    has_mandatory: bool
    has_preferred: bool
    label: Label
    t_v: float = 0.0  # self-claim tie-break only (2.3.5); never shown as a percent
    j_v: float = 0.0
    confirmed_share: float = 0.0  # mean lower bound over all groups; display only, not a probability


def z_status(mandatory_group_statuses: Sequence[str]) -> Literal[0, 1, 2]:
    """Z=0 if any mandatory group FAILED; Z=2 only if non-empty and all SATISFIED; else 1."""
    if any(s == "FAILED" for s in mandatory_group_statuses):
        return 0
    if mandatory_group_statuses and all(s == "SATISFIED" for s in mandatory_group_statuses):
        return 2
    return 1


def sort_key(r: VacancyRanking) -> tuple:
    """Ascending sort key equivalent to (Z DESC, X DESC, L^M DESC, L^P DESC, W^M ASC, W^P ASC, T_v DESC, J_v DESC, id ASC)."""
    return (-r.z, -r.x, -r.l_m, -r.l_p, r.w_m, r.w_p, -r.t_v, -r.j_v, r.vacancy_id)


def rank(rankings: Sequence[VacancyRanking]) -> list[VacancyRanking]:
    evaluable = [r for r in rankings if r.label != "NOT_EVALUABLE"]
    return sorted(evaluable, key=sort_key)
