"""Deterministic ranked vacancies for a frozen cohort. Server-side only; no LLM scoring here."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.core import _owned_cohort, _revisions, latest_scores
from backend.db import get_db
from backend.domain.core_flow import rank_vacancy
from backend.domain.ranking import rank as order
from backend.models import User
from backend.security import current_user

router = APIRouter(tags=["recommendations"])


class RankBody(BaseModel):
    cohort_id: str


@router.post("/recommendations")
def rank(data: RankBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    snap = _owned_cohort(db, user, data.cohort_id)
    scores = latest_scores(db, user)
    ranked = []
    by_id = {r["id"]: r for r in _revisions(snap)}
    for vid in snap.vacancy_ids:
        rev = by_id[vid]
        ranked.append(rank_vacancy({"id": vid, "years_min": rev["years_min"], "groups": rev["groups"]},
                                   scores, user.years_experience))
    items = [{"vacancy_id": r.vacancy_id, "label": r.label, "z": r.z, "x": r.x,
              "l_mandatory": r.l_m, "l_preferred": r.l_p, "w_mandatory": r.w_m, "w_preferred": r.w_p,
              "has_mandatory": r.has_mandatory, "has_preferred": r.has_preferred}
             for r in order(ranked)]
    return {"cohort_id": snap.id, "policy": "ORDER_LEXICOGRAPHIC_V1", "items": items,
            "note": "Порядок детермінований; це не ймовірність працевлаштування."}
