"""Automatic frozen cohort and market profile. Client never supplies vacancy IDs. MATH_SPEC §0–1."""
from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.db import get_db
from backend.domain.market import VacancyInput, compute_market
from backend.models import CandidateProfile, Competency, CohortSnapshot, RequirementGroup, User, Vacancy
from backend.security import current_user

router = APIRouter(prefix="/cohorts", tags=["cohorts"])
POLICY_ID = "TRACK_ALL_VALID_V2"


def _vacancy_revisions(db: Session, track: str) -> list[dict]:
    stmt = (select(Vacancy).where(Vacancy.track == track, Vacancy.is_active.is_(True))
            .options(selectinload(Vacancy.groups).selectinload(RequirementGroup.alternatives))
            .order_by(Vacancy.id))
    out = []
    for v in db.scalars(stmt).all():
        out.append({
            "id": v.id,
            "years_min": v.years_min,
            "title": v.title,
            "company": v.company,
            "seniority": v.seniority,
            "location": v.location,
            "work_mode": v.work_mode,
            "groups": [
                {"id": g.id, "kind": g.kind,
                 "alternatives": sorted(
                     ({"competency_id": a.competency_id, "required_level": a.required_level} for a in g.alternatives),
                     key=lambda a: a["competency_id"])}
                for g in v.groups
            ],
        })
    return out


def _market_input(revisions: list[dict]) -> list[VacancyInput]:
    return [
        VacancyInput(r["id"], tuple(tuple(a["competency_id"] for a in g["alternatives"]) for g in r["groups"]))
        for r in revisions
    ]


def get_or_create_cohort(db: Session, user: User, track: str) -> tuple[CohortSnapshot | None, str | None]:
    """Idempotent frozen cohort of all active vacancies of a track; (None, None) when the track has none."""
    revisions = _vacancy_revisions(db, track)
    if not revisions:
        return None, None
    canonical = json.dumps(revisions, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    existing = db.scalar(select(CohortSnapshot).where(
        CohortSnapshot.user_id == user.id, CohortSnapshot.sha256 == digest, CohortSnapshot.policy_id == POLICY_ID))
    if existing is not None:
        return existing, digest
    keys = ("years_min", "title", "company", "seniority", "location", "work_mode", "groups")
    snap = CohortSnapshot(user_id=user.id, vacancy_ids=[r["id"] for r in revisions],
                          requirement_revisions={r["id"]: {k: r[k] for k in keys} for r in revisions},
                          policy_id=POLICY_ID, sha256=digest)
    db.add(snap)
    db.commit()
    return snap, digest


@router.post("/auto", status_code=201)
def create_auto_cohort(profile_id: str | None = None, db: Session = Depends(get_db),
                       user: User = Depends(current_user)):
    track = user.track
    if profile_id is not None:
        prof = db.scalar(select(CandidateProfile).where(CandidateProfile.id == profile_id,
                                                        CandidateProfile.user_id == user.id))
        if prof is None:
            raise HTTPException(404, "Профіль не знайдено")
        track = prof.track
    snap, digest = get_or_create_cohort(db, user, track)
    if snap is None:
        return {"cohort_id": None, "vacancy_count": 0, "sha256": None, "empty": True, "policy": POLICY_ID}
    return {"cohort_id": snap.id, "vacancy_count": len(snap.vacancy_ids), "sha256": digest,
            "empty": False, "policy": POLICY_ID}


@router.get("/{cohort_id}/market")
def cohort_market(cohort_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    snap = db.scalar(select(CohortSnapshot).where(CohortSnapshot.id == cohort_id, CohortSnapshot.user_id == user.id))
    if snap is None:
        raise HTTPException(404, "Cohort not found")
    revisions = [{"id": vid, **snap.requirement_revisions[vid]} for vid in snap.vacancy_ids]
    entries = compute_market(_market_input(revisions))
    names = {c.id: c.label_uk for c in db.scalars(select(Competency)).all()}
    # Public response: ordered names only — no F/I values, counts or percentages.
    return {"skills": [{"order": i + 1, "action_id": e.action_id,
                        "name": names.get(e.action_id, e.action_id)} for i, e in enumerate(entries)]}
