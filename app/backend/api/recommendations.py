"""Deterministic ranked vacancies for a frozen cohort. Server-side only; no LLM scoring here."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.core import _owned_cohort, _revisions, latest_scores
from backend.db import get_db
from backend.domain.core_flow import explain_vacancy, rank_vacancy
from backend.domain.ranking import rank as order
from backend.models import CohortSnapshot, Competency, User
from backend.security import current_user

router = APIRouter(tags=["recommendations"])
TOP_N = 5
NOTE = "Порядок детермінований; це не ймовірність працевлаштування."


class RankBody(BaseModel):
    cohort_id: str


def rank_items(db: Session, years_experience: int | None, snap: CohortSnapshot,
               scores: dict[str, float | None]) -> list[dict]:
    """All vacancies of a frozen cohort in deterministic ranking order (shared by legacy and profile results)."""
    by_id = {r["id"]: r for r in _revisions(snap)}
    ranked = [rank_vacancy({"id": vid, "years_min": by_id[vid]["years_min"], "groups": by_id[vid]["groups"]},
                           scores, years_experience) for vid in snap.vacancy_ids]
    names = {c.id: c.label_uk for c in db.query(Competency).all()}
    return [{"vacancy_id": r.vacancy_id,
             **{k: by_id[r.vacancy_id].get(k) for k in ("title", "company", "location", "work_mode", "seniority",
                                                          "years_min")},
             "label": r.label, "z": r.z, "x": r.x,
             "confirmed_share": round(r.confirmed_share * 100),
             **explain_vacancy(by_id[r.vacancy_id], scores, names),
             "l_mandatory": r.l_m, "l_preferred": r.l_p, "w_mandatory": r.w_m, "w_preferred": r.w_p,
             "has_mandatory": r.has_mandatory, "has_preferred": r.has_preferred}
            for r in order(ranked)]


@router.post("/recommendations")
def rank(data: RankBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    snap = _owned_cohort(db, user, data.cohort_id)
    scores = latest_scores(db, user)
    ordered = rank_items(db, user.years_experience, snap, scores)
    return {"cohort_id": snap.id, "policy": "ORDER_LEXICOGRAPHIC_V1", "items": ordered[:TOP_N],
            "total": len(ordered), "assessed_actions": sum(1 for v in scores.values() if v is not None),
            "note": NOTE}
