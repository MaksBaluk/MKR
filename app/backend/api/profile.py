"""Candidate metadata and editable self-ratings. Self-ratings never change LLM assessments."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import (CandidateSelfRating, Competency, CohortSnapshot, CoreInterview, CriterionAssessment,
                            User)
from backend.security import current_user

router = APIRouter(prefix="/profile", tags=["candidate profile"])


class UpdateProfile(BaseModel):
    display_name: str = Field(min_length=2, max_length=120)
    track: str
    desired_title: str = Field(default="", max_length=160)
    years_experience: int | None = Field(default=None, ge=0, le=70)
    location: str = Field(default="", max_length=120)


class UpdateSelfRating(BaseModel):
    value: float | None = Field(default=None, ge=0.0, le=1.0)


def latest_self_ratings(db: Session, user: User) -> dict[str, float | None]:
    rows = db.scalars(select(CandidateSelfRating).where(CandidateSelfRating.user_id == user.id)
                      .order_by(CandidateSelfRating.revision)).all()
    return {r.action_id: r.value for r in rows}


def profile_data(db: Session, user: User) -> dict:
    return {"id": user.id, "email": user.email, "display_name": user.display_name,
            "track": user.track, "desired_title": user.desired_title,
            "years_experience": user.years_experience, "location": user.location,
            "self_ratings": [{"action_id": k, "value": v, "source": "SELF_REPORT", "editable": True}
                             for k, v in latest_self_ratings(db, user).items()]}


@router.get("")
def get_profile(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return profile_data(db, user)


@router.put("")
def update_profile(data: UpdateProfile, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if data.track not in ("python", "marketing", "design"):
        raise HTTPException(422, "Невідомий професійний трек")
    for key, val in data.model_dump().items():
        setattr(user, key, val)
    db.commit()
    return profile_data(db, user)


@router.put("/self-ratings/{action_id}")
def set_self_rating(action_id: str, data: UpdateSelfRating,
                    db: Session = Depends(get_db), user: User = Depends(current_user)):
    comp = db.get(Competency, action_id)
    if comp is None:
        raise HTTPException(404, "Професійну дію не знайдено")
    if comp.track != user.track:
        raise HTTPException(422, "Дія належить до іншого треку")
    revision = (db.scalar(select(func.max(CandidateSelfRating.revision)).where(
        CandidateSelfRating.user_id == user.id, CandidateSelfRating.action_id == action_id)) or 0) + 1
    db.add(CandidateSelfRating(user_id=user.id, action_id=action_id, revision=revision, value=data.value))
    db.commit()
    return {"action_id": action_id, "value": data.value, "revision": revision, "source": "SELF_REPORT",
            "editable": True}


@router.delete("/data", status_code=204)
def delete_assessment_data(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Purge this user's interview, assessment, cohort and self-rating records; keep the login account."""
    db.execute(delete(CriterionAssessment).where(CriterionAssessment.user_id == user.id))
    db.execute(delete(CoreInterview).where(CoreInterview.user_id == user.id))
    db.execute(delete(CohortSnapshot).where(CohortSnapshot.user_id == user.id))
    db.execute(delete(CandidateSelfRating).where(CandidateSelfRating.user_id == user.id))
    db.commit()
