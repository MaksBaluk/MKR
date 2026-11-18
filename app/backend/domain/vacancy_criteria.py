"""D_vga for the SYNTHETIC vacancy fixtures: which rubric criteria one requirement needs. MATH_SPEC §3d.

This is a documented synthetic rule, not employer data: the fixture vacancies have no real criterion-level text. A real
import must supply criterion_ids with a source excerpt instead (CLAUDE.md data honesty)."""
from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence

CRITERIA_SOURCE = "SYNTHETIC_RULE_V1"
SHARE_BY_LEVEL = {1: 0.5, 2: 0.75, 3: 1.0}  # fraction of the rubric a requirement of this level needs (working assumption)


def derive_required_criteria(vacancy_id: str, competency_id: str, level: int,
                             rubric_criteria: Sequence[str]) -> list[str]:
    """Deterministic subset of `rubric_criteria` (rubric order kept): ceil(n * share) criteria, picked by a stable hash of
    (vacancy, competency, criterion) so different vacancies of one competency need different parts of its rubric."""
    n = len(rubric_criteria)
    if n == 0:
        return []
    k = max(1, math.ceil(n * SHARE_BY_LEVEL.get(level, 1.0)))
    ranked = sorted(rubric_criteria, key=lambda c: hashlib.sha256(f"{vacancy_id}|{competency_id}|{c}".encode()).hexdigest())
    keep = set(ranked[:k])
    return [c for c in rubric_criteria if c in keep]
