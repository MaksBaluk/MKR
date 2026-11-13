"""Read-only catalog of professional actions and vacancies."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.db import get_db
from backend.models import Competency, RequirementGroup, Vacancy

from .common import source_label

router = APIRouter(tags=["catalog"])

LIST_FIELDS = ["id", "track", "title", "company", "seniority", "location", "work_mode", "employment",
               "salary_min", "salary_max", "currency", "summary", "stack", "years_min", "years_max"]


@router.get("/competencies")
def competencies(track: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Competency)
    if track:
        stmt = stmt.where(Competency.track == track)
    rows = db.scalars(stmt.order_by(Competency.track, Competency.label)).all()
    return [{"id": a.id, "label_uk": a.label_uk, "track": a.track, "summary": a.summary} for a in rows]


def _like(text: str) -> str:
    escaped = text.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _list_item(v: Vacancy) -> dict:
    data = {key: getattr(v, key) for key in LIST_FIELDS}
    data["source_label"] = source_label(v)
    data["requirements_count"] = len(v.groups)
    return data


@router.get("/vacancies")
def vacancies(
    track: Literal["python", "marketing", "design"] | None = None,
    work_mode: str | None = None, seniority: str | None = None, location: str | None = None,
    q: str | None = None, salary_min: int | None = None,
    sort: Literal["newest", "salary_desc", "salary_asc", "title"] = "title",
    page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=50),
    db: Session = Depends(get_db),
):
    conds = {
        "track": Vacancy.track == track if track else None,
        "work_mode": func.lower(Vacancy.work_mode) == work_mode.lower() if work_mode else None,
        "seniority": func.lower(Vacancy.seniority) == seniority.lower() if seniority else None,
        "location": func.lower(Vacancy.location).like(_like(location), escape="\\") if location else None,
        "q": or_(*(func.lower(col).like(_like(q), escape="\\")
                   for col in (Vacancy.title, Vacancy.company, cast(Vacancy.stack, String)))) if q else None,
        "salary_min": or_(Vacancy.salary_max.is_(None), Vacancy.salary_max >= salary_min)
        if salary_min is not None else None,
    }
    active = Vacancy.is_active.is_(True)

    def where(skip: str | None = None):
        return [active, *(c for k, c in conds.items() if c is not None and k != skip)]

    total = db.scalar(select(func.count()).select_from(Vacancy).where(*where())) or 0
    order = {"title": [Vacancy.title, Vacancy.id], "newest": [Vacancy.id.desc()],
             "salary_desc": [Vacancy.salary_max.desc().nulls_last(), Vacancy.id],
             "salary_asc": [Vacancy.salary_max.asc().nulls_last(), Vacancy.id]}[sort]
    rows = db.scalars(select(Vacancy).where(*where()).order_by(*order)
                      .options(selectinload(Vacancy.groups)).limit(page_size).offset((page - 1) * page_size)).all()
    facets = {}
    for name in ("track", "work_mode", "seniority"):
        col = getattr(Vacancy, name)
        facets[name] = dict(db.execute(select(col, func.count()).where(*where(skip=name)).group_by(col)
                                       .order_by(col)).all())
    return {"items": [_list_item(v) for v in rows], "total": total, "page": page, "page_size": page_size,
            "facets": facets}


@router.get("/vacancies/{vacancy_id}")
def vacancy_detail(vacancy_id: str, db: Session = Depends(get_db)):
    v = db.scalar(select(Vacancy).where(Vacancy.id == vacancy_id, Vacancy.is_active.is_(True))
                  .options(selectinload(Vacancy.groups).selectinload(RequirementGroup.alternatives)))
    if v is None:
        raise HTTPException(404, "Вакансію не знайдено")
    names = dict(db.execute(select(Competency.id, Competency.label_uk)).all())
    data = _list_item(v)
    data.update({key: getattr(v, key) for key in ["description", "responsibilities", "benefits", "source_type",
                                                  "source_url", "fixture_version"]})
    data["requirements"] = [
        {"id": g.id, "kind": g.kind, "label": g.label, "excerpt": g.excerpt,
         "alternatives": [{"competency_id": a.competency_id, "name": names.get(a.competency_id, a.competency_id),
                           "required_level": a.required_level} for a in g.alternatives]}
        for g in v.groups]
    return data
