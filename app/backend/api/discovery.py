"""Candidate-centric discovery: ranked recommendations and automatic frozen cohorts (no manual picks)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload
from backend.db import get_db
from backend.models import Competency, MatchRun, RequirementGroup, Snapshot, User, Vacancy
from backend.security import current_user
from backend.domain.discovery import select_cohort
from backend.domain.matching import effective_profile, rank_snapshot
from .common import serialize_snapshot, serialize_vacancy, freeze_payload
from .profile import profile_data

router = APIRouter(prefix="/discovery", tags=["automatic discovery & frozen cohort"])


class CohortFilters(BaseModel):
    work_mode: str | None = Field(default=None, max_length=24)
    seniority: str | None = Field(default=None, max_length=30)
    location_contains: str | None = Field(default=None, max_length=120)
    respect_experience: bool = False
    name: str = Field(default="Мої рекомендовані вакансії", min_length=2, max_length=180)


def _track_vacancies(db: Session, track: str) -> list[dict]:
    stmt = (select(Vacancy).where(Vacancy.track == track, Vacancy.is_active.is_(True))
            .options(selectinload(Vacancy.groups).selectinload(RequirementGroup.alternatives))
            .order_by(Vacancy.id))
    return [serialize_vacancy(v) for v in db.scalars(stmt).all()]


@router.get("/recommendations")
def recommendations(db: Session = Depends(get_db), user: User = Depends(current_user),
                    work_mode: str | None = None, seniority: str | None = None,
                    location: str | None = None, respect_experience: bool = False):
    profile = profile_data(db, user)
    from backend.domain.discovery import eligible
    pool = eligible(_track_vacancies(db, user.track), work_mode=work_mode, seniority=seniority,
                    location_contains=location, respect_experience=respect_experience,
                    years_experience=user.years_experience)
    ranked = rank_snapshot(pool, {"levels": profile["levels"]}, user.years_experience)
    track_competencies = db.scalar(select(func.count()).select_from(Competency).where(Competency.track == user.track)) or 0
    track_ids = set(db.scalars(select(Competency.id).where(Competency.track == user.track)).all())
    assessed = sum(1 for cid, level in profile["levels"].items() if level is not None and cid in track_ids)
    return {"items": ranked, "total": len(ranked), "track": user.track,
            "profile_source": "SELF_REPORT_BASELINE",
            "evidence_quality": {"assessed_competencies": assessed, "total_competencies": track_competencies}}


@router.post("/snapshots", status_code=201)
def create_cohort(data: CohortFilters, db: Session = Depends(get_db), user: User = Depends(current_user)):
    profile = profile_data(db, user)
    try:
        cohort, policy = select_cohort(_track_vacancies(db, user.track), levels=profile["levels"],
                                       years_experience=user.years_experience,
                                       work_mode=data.work_mode, seniority=data.seniority,
                                       location_contains=data.location_contains,
                                       respect_experience=data.respect_experience)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    payload, digest = freeze_payload(cohort)
    snap = Snapshot(user_id=user.id, name=data.name.strip(), track=user.track, status="FROZEN",
                    vacancy_payload=payload, sha256=digest, cohort_policy=policy)
    db.add(snap)
    db.flush()
    baseline = effective_profile(profile["levels"])
    run = MatchRun(user_id=user.id, snapshot_id=snap.id, interview_id=None,
                   profile_payload={**baseline, "source": "SELF_REPORT_BASELINE"},
                   results_payload=rank_snapshot(payload, baseline, user.years_experience))
    db.add(run)
    db.commit()
    return {**serialize_snapshot(snap, with_vacancies=True), "baseline_match_id": run.id}
