"""Read-only fixture catalog and creation of immutable selected-vacancy snapshots."""
import hashlib
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload
from backend.db import get_db
from backend.models import Competency, Vacancy, RequirementGroup, Snapshot, User
from backend.security import current_user
from .common import serialize_snapshot, serialize_vacancy, require_snapshot

router = APIRouter(tags=["catalog & frozen snapshots"])


@router.get("/tracks")
def tracks():
    return [{"id": "python", "title": "Python-розробка", "description": "Backend, API, дані та інфраструктура"},
            {"id": "marketing", "title": "Маркетинг", "description": "Performance, аналітика, CRM і контент"},
            {"id": "design", "title": "Дизайн", "description": "Product, UX/UI, візуальні системи"}]


@router.get("/competencies")
def competencies(track: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Competency)
    if track:
        stmt = stmt.where(Competency.track == track)
    rows = db.scalars(stmt.order_by(Competency.track, Competency.label)).all()
    return [{"id": a.id, "label": a.label, "label_uk": a.label_uk, "track": a.track,
             "summary": a.summary, "aliases": a.aliases, "catalog_version": a.catalog_version} for a in rows]


@router.get("/vacancies")
def vacancies(track: str | None = None, q: str | None = None, seniority: str | None = None,
              work_mode: str | None = None, page: int = Query(1, ge=1),
              page_size: int = Query(30, ge=1, le=100), db: Session = Depends(get_db)):
    conditions = [Vacancy.is_active.is_(True)]
    if track:
        conditions.append(Vacancy.track == track)
    if seniority:
        conditions.append(Vacancy.seniority == seniority.upper())
    if work_mode:
        conditions.append(Vacancy.work_mode == work_mode.upper())
    if q:
        search = f"%{q.strip()}%"
        conditions.append(Vacancy.title.ilike(search) | Vacancy.company.ilike(search) | Vacancy.summary.ilike(search))
    total = db.scalar(select(func.count()).select_from(Vacancy).where(*conditions)) or 0
    stmt = select(Vacancy).where(*conditions).options(selectinload(Vacancy.groups)).order_by(Vacancy.id)
    items = db.scalars(stmt.offset((page-1)*page_size).limit(page_size)).all()
    return {"items": [serialize_vacancy(v, with_groups=False) for v in items],
            "total": total, "page": page, "page_size": page_size, "source": "DEMO_CURATED"}


@router.get("/vacancies/{vacancy_id}")
def vacancy_details(vacancy_id: str, db: Session = Depends(get_db)):
    stmt = select(Vacancy).where(Vacancy.id == vacancy_id).options(
        selectinload(Vacancy.groups).selectinload(RequirementGroup.alternatives))
    vacancy = db.scalar(stmt)
    if not vacancy:
        raise HTTPException(404, "Vacancy not found")
    return serialize_vacancy(vacancy)


class SnapshotCreate(BaseModel):
    vacancy_ids: list[str] = Field(min_length=1, max_length=30)
    name: str = Field(default="Мій набір вакансій", min_length=2, max_length=180)


@router.post("/snapshots", status_code=201)
def create_snapshot(data: SnapshotCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ids = list(dict.fromkeys(data.vacancy_ids))
    if len(ids) != len(data.vacancy_ids):
        raise HTTPException(422, "Duplicate vacancy IDs are not allowed")
    stmt = select(Vacancy).where(Vacancy.id.in_(ids), Vacancy.is_active.is_(True)).options(
        selectinload(Vacancy.groups).selectinload(RequirementGroup.alternatives))
    records = db.scalars(stmt).all()
    if len(records) != len(ids):
        raise HTTPException(422, "One or more vacancies are invalid")
    if len({r.track for r in records}) != 1:
        raise HTTPException(422, "Choose vacancies from one professional track")
    by_id = {v.id: v for v in records}
    payload = [serialize_vacancy(by_id[vid]) for vid in ids]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    snap = Snapshot(user_id=user.id, name=data.name.strip(), track=records[0].track,
                    status="FROZEN", vacancy_payload=payload,
                    sha256=hashlib.sha256(serialized.encode()).hexdigest())
    db.add(snap)
    db.commit()
    return serialize_snapshot(snap, with_vacancies=True)


@router.get("/snapshots")
def snapshots(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(Snapshot).where(Snapshot.user_id == user.id).order_by(Snapshot.frozen_at.desc())).all()
    return [serialize_snapshot(s) for s in rows]


@router.get("/snapshots/{snapshot_id}")
def snapshot_details(snapshot_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return serialize_snapshot(require_snapshot(db, user.id, snapshot_id), with_vacancies=True)
