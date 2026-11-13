"""Materialized, reproducible per-user match runs over frozen vacancy revisions."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.db import get_db
from backend.models import MatchRun, User
from backend.security import current_user
from backend.domain.matching import effective_profile, rank_snapshot
from backend.domain.adaptive import observed_successes
from .common import require_snapshot, require_interview, require_match
from .profile import profile_data
from backend.domain.profile_versions import ensure_p1

router = APIRouter(prefix="/matches", tags=["explainable matching"])


class CreateMatch(BaseModel):
    snapshot_id: str
    interview_id: str | None = None


def serialize_match(row: MatchRun, *, with_details=True) -> dict:
    result = {"id": row.id, "snapshot_id": row.snapshot_id, "interview_id": row.interview_id,
              "matcher_version": row.matcher_version,
              "profile": row.profile_payload,
              "profile_version_id": row.profile_version_id,
              "unchanged_reason": (row.profile_payload or {}).get("unchanged_reason"),
              "total": len(row.results_payload),
              "created_at": row.created_at.isoformat() if row.created_at else None}
    if with_details:
        result["items"] = row.results_payload
    return result


@router.post("", status_code=201)
def create_match(data: CreateMatch, db: Session = Depends(get_db), user: User = Depends(current_user)):
    snap = require_snapshot(db, user.id, data.snapshot_id)
    if data.interview_id:
        interview = require_interview(db, user.id, data.interview_id)
        if interview.snapshot_id != snap.id:
            raise HTTPException(422, "Interview belongs to a different frozen snapshot")
        if snap.track != user.track:
            raise HTTPException(409, detail={"code": "TRACK_CHANGED", "message": "Трек змінено після створення набору"})
        if interview.status != "COMPLETED":
            raise HTTPException(409, "Complete the interview before matching")
        version = ensure_p1(db, interview)
        profile = {**effective_profile(interview.baseline_profile, observed_successes(interview.turns)),
                   "levels": version.levels, "provenance": version.provenance}
        source = "POST_INTERVIEW"
        accepted = {"HUMAN_REVIEW", "DEMO_OBSERVED_LEVEL_1"}
        unchanged = None if any(isinstance(value, str) and value in accepted for value in version.provenance.values()) else "NO_ACCEPTED_EVIDENCE"
    else:
        profile = effective_profile(profile_data(db, user)["levels"])
        source = "SELF_REPORT_BASELINE"
        version = None
        unchanged = None
    ranked = rank_snapshot(snap.vacancy_payload, profile, years_experience=user.years_experience)
    row = MatchRun(user_id=user.id, snapshot_id=snap.id, interview_id=data.interview_id,
                   profile_payload={**profile, "source": source, "unchanged_reason": unchanged},
                   results_payload=ranked, profile_version_id=version.id if version else None)
    db.add(row)
    db.commit()
    return serialize_match(row)


@router.get("")
def list_matches(db: Session = Depends(get_db), user: User = Depends(current_user)):
    results = db.scalars(select(MatchRun).where(MatchRun.user_id == user.id)
                         .order_by(MatchRun.created_at.desc())).all()
    return [serialize_match(r, with_details=False) for r in results]


@router.get("/{match_id}")
def get_match(match_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return serialize_match(require_match(db, user.id, match_id))


@router.get("/{match_id}/vacancies/{vacancy_id}")
def explanation(match_id: str, vacancy_id: str,
                db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = require_match(db, user.id, match_id)
    found = next((item for item in row.results_payload if item["vacancy_id"] == vacancy_id), None)
    if found is None:
        raise HTTPException(404, "Vacancy not in this match run")
    return found
