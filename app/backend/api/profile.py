from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from backend.db import get_db
from backend.models import CandidateSkill, Competency, User, InterviewSession, Snapshot, MatchRun, AuthToken
from backend.security import current_user

router = APIRouter(prefix="/profile", tags=["candidate profile"])


class UpdateProfile(BaseModel):
    display_name: str = Field(min_length=2, max_length=120)
    track: str
    desired_title: str = Field(default="", max_length=160)
    years_experience: int | None = Field(default=None, ge=0, le=70)
    location: str = Field(default="", max_length=120)


class UpdateSkill(BaseModel):
    level: int | None = Field(default=None, ge=0, le=3)
    context: str = Field(default="", max_length=1200)


def profile_data(db: Session, user: User) -> dict:
    skills = db.scalars(select(CandidateSkill).where(CandidateSkill.user_id == user.id)).all()
    return {"id": user.id, "email": user.email, "display_name": user.display_name,
            "track": user.track, "desired_title": user.desired_title,
            "years_experience": user.years_experience, "location": user.location,
            "skills": [{"competency_id": s.competency_id, "level": s.level,
                        "context": s.context, "source": "SELF_REPORT"} for s in skills],
            "levels": {s.competency_id: s.level for s in skills}}


@router.get("")
def get_profile(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return profile_data(db, user)


@router.put("")
def update_profile(data: UpdateProfile, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if data.track not in ("python", "marketing", "design"):
        raise HTTPException(422, "Unknown track")
    for key, val in data.model_dump().items():
        setattr(user, key, val)
    db.commit()
    return profile_data(db, user)


@router.put("/skills/{competency_id}")
def set_skill(competency_id: str, data: UpdateSkill,
              db: Session = Depends(get_db), user: User = Depends(current_user)):
    comp = db.get(Competency, competency_id)
    if not comp:
        raise HTTPException(404, "Competency not found")
    if comp.track != user.track:
        raise HTTPException(422, "Competency belongs to another professional track")
    record = db.get(CandidateSkill, (user.id, competency_id))
    if record is None:
        record = CandidateSkill(user_id=user.id, competency_id=competency_id)
        db.add(record)
    record.level = data.level
    record.context = data.context
    db.commit()
    return {"competency_id": competency_id, "level": data.level, "context": data.context, "source": "SELF_REPORT"}


@router.delete("/data", status_code=204)
def delete_assessment_data(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Purge user's profile evidence, frozen sets and results; keep login account."""
    from backend.models import InterviewSession, Snapshot, MatchRun
    # Delete dependent records in FK-safe order; cascades remove interview turns.
    for item in db.scalars(select(MatchRun).where(MatchRun.user_id == user.id)).all():
        db.delete(item)
    for item in db.scalars(select(InterviewSession).where(InterviewSession.user_id == user.id)).all():
        db.delete(item)
    db.flush()
    for item in db.scalars(select(Snapshot).where(Snapshot.user_id == user.id)).all():
        db.delete(item)
    db.execute(delete(CandidateSkill).where(CandidateSkill.user_id == user.id))
    db.commit()
