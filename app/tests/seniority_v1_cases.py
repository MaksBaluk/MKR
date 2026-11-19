"""Deterministic evidence cases for the policy v1 golden regression (tests/data/seniority_v1_golden.json).

The golden file was produced by the v1 estimator before policy v2 existed; v1 results must stay byte-identical."""
from __future__ import annotations

import hashlib

from backend.domain.seniority import CriterionEvidence
from backend.domain.seniority_policy import PYTHON_BACKEND_V1

V1_IDS = sorted({c for r in PYTHON_BACKEND_V1.rules for c in r.critical} | {"fastapi.validation", "kafka.errors"})
SCORES = (None, 0.0, 0.2, 0.44, 0.46, 0.5, 0.66, 0.69, 0.7, 0.72, 0.75, 0.8, 0.9, 1.0)


def _u(*parts) -> int:
    return int(hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def cases(n: int = 90) -> list[dict[str, CriterionEvidence]]:
    out: list[dict[str, CriterionEvidence]] = [{}]
    for k in range(n):
        density = 4 if k % 3 == 0 else 1 + _u(k, "d") % 4  # 1..4 of 4 criteria get an entry
        ev: dict[str, CriterionEvidence] = {}
        for cid in V1_IDS:
            if _u(k, cid, "in") % 4 >= density:
                continue
            score = SCORES[_u(k, cid, "s") % len(SCORES)] if k % 3 else (0.9 if _u(k, cid) % 23 else 0.3 if k % 2 else 0.72)
            turns = () if score is None or _u(k, cid, "t") % 9 == 0 else (f"t{_u(k, cid) % 7}",)
            ev[cid] = CriterionEvidence(cid, score, turns)
        out.append(ev)
    return out
