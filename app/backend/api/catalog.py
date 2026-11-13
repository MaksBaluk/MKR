"""Read-only catalog of professional actions and vacancies (fixture-backed, synthetic provenance)."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.db import get_db
from backend.models import Competency, RequirementGroup, Vacancy

from .common import serialize_vacancy

router = APIRouter(tags=["catalog"])


@router.get("/competencies")
def competencies(track: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Competency)
    if track:
        stmt = stmt.where(Competency.track == track)
    rows = db.scalars(stmt.order_by(Competency.track, Competency.label)).all()
    return [{"id": a.id, "label_uk": a.label_uk, "track": a.track, "summary": a.summary} for a in rows]


@router.get("/vacancies")
def vacancies(track: str | None = None, db: Session = Depends(get_db)):
    stmt = (select(Vacancy).where(Vacancy.is_active.is_(True))
            .options(selectinload(Vacancy.groups).selectinload(RequirementGroup.alternatives))
            .order_by(Vacancy.id))
    if track:
        stmt = stmt.where(Vacancy.track == track)
    return [serialize_vacancy(v) for v in db.scalars(stmt).all()]
