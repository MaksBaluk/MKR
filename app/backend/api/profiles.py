"""Candidate profiles: owner-scoped CRUD (archive), self-ratings, attempts and ranked results per profile."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.cohorts import _market_input, get_or_create_cohort
from backend.api.common import create_attempt, open_attempt
from backend.api.core import _action_scores, _names, _revisions, attempt_scores, current_criteria_rows
from backend.api.recommendations import NOTE, rank_items
from backend.db import get_db
from backend.domain.market import compute_market
from backend.models import (CandidateProfile, CandidateSelfRating, CohortSnapshot, Competency, CoreInterview,
                            CoreTurn, CriterionAssessment, User)
from backend.security import current_user

router = APIRouter(prefix="/profiles", tags=["profiles"])


class ProfileBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    track: Literal["python", "marketing", "design"]
    desired_title: str = Field(default="", max_length=160)
    years_experience: int | None = Field(default=None, ge=0, le=70)
    location: str = Field(default="", max_length=120)


class SelfRatingBody(BaseModel):
    value: float | None = Field(default=None, ge=0.0, le=1.0)


def _owned_profile(db: Session, user: User, profile_id: str) -> CandidateProfile:
    prof = db.scalar(select(CandidateProfile).where(CandidateProfile.id == profile_id,
                                                    CandidateProfile.user_id == user.id))
    if prof is None:
        raise HTTPException(404, "Профіль не знайдено")
    return prof


def _profile_dict(db: Session, p: CandidateProfile) -> dict:
    attempts = db.scalars(select(CoreInterview).where(CoreInterview.profile_id == p.id)
                          .order_by(CoreInterview.attempt_no.desc())).all()
    finished = next((a for a in attempts if a.status == "FINISHED"), None)
    return {"id": p.id, "name": p.name, "track": p.track, "desired_title": p.desired_title,
            "years_experience": p.years_experience, "location": p.location, "archived": p.archived,
            "attempts_count": len(attempts), "latest_finished_attempt_id": finished.id if finished else None,
            "created_at": p.created_at.isoformat() if p.created_at else None}


def _latest_finished(db: Session, profile_id: str) -> CoreInterview | None:
    return db.scalar(select(CoreInterview).where(CoreInterview.profile_id == profile_id,
                                                 CoreInterview.status == "FINISHED")
                     .order_by(CoreInterview.created_at.desc(), CoreInterview.attempt_no.desc()))


@router.get("")
def list_profiles(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(CandidateProfile).where(CandidateProfile.user_id == user.id,
                                                     CandidateProfile.archived.is_(False))
                      .order_by(CandidateProfile.created_at, CandidateProfile.id)).all()
    return {"items": [_profile_dict(db, p) for p in rows]}


@router.post("", status_code=201)
def create_profile(data: ProfileBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    prof = CandidateProfile(user_id=user.id, **data.model_dump())
    db.add(prof)
    db.commit()
    return _profile_dict(db, prof)


@router.get("/{profile_id}")
def get_profile(profile_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _profile_dict(db, _owned_profile(db, user, profile_id))


@router.put("/{profile_id}")
def update_profile(profile_id: str, data: ProfileBody, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    prof = _owned_profile(db, user, profile_id)
    for k, v in data.model_dump().items():
        setattr(prof, k, v)
    db.commit()
    return _profile_dict(db, prof)


@router.delete("/{profile_id}", status_code=204)
def archive_profile(profile_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Archive only: attempts and assessments stay."""
    _owned_profile(db, user, profile_id).archived = True
    db.commit()


# ---- self-ratings ----------------------------------------------------------------------------------------

def _latest_profile_ratings(db: Session, profile_id: str) -> dict[str, float | None]:
    rows = db.scalars(select(CandidateSelfRating).where(CandidateSelfRating.profile_id == profile_id)
                      .order_by(CandidateSelfRating.revision)).all()
    return {r.action_id: r.value for r in rows}


@router.get("/{profile_id}/self-ratings")
def get_self_ratings(profile_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    prof = _owned_profile(db, user, profile_id)
    return {"items": [{"action_id": k, "value": v, "source": "SELF_REPORT", "editable": True}
                      for k, v in _latest_profile_ratings(db, prof.id).items()]}


@router.put("/{profile_id}/self-ratings/{action_id}")
def set_self_rating(profile_id: str, action_id: str, data: SelfRatingBody, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    prof = _owned_profile(db, user, profile_id)
    comp = db.get(Competency, action_id)
    if comp is None:
        raise HTTPException(404, "Професійну дію не знайдено")
    if comp.track != prof.track:
        raise HTTPException(422, "Дія належить до іншого треку")
    # PK is (user_id, action_id, revision): number revisions per user+action so profiles never collide.
    revision = (db.scalar(select(func.max(CandidateSelfRating.revision)).where(
        CandidateSelfRating.user_id == user.id, CandidateSelfRating.action_id == action_id)) or 0) + 1
    db.add(CandidateSelfRating(user_id=user.id, profile_id=prof.id, action_id=action_id, revision=revision,
                               value=data.value))
    db.commit()
    return {"action_id": action_id, "value": data.value, "revision": revision, "source": "SELF_REPORT",
            "editable": True}


# ---- attempts --------------------------------------------------------------------------------------------

def _open_attempt(db: Session, profile_id: str) -> CoreInterview | None:
    return open_attempt(db, profile_id)


def _attempt_brief(iv: CoreInterview) -> dict:
    return {"id": iv.id, "attempt_no": iv.attempt_no, "status": iv.status, "version": iv.version,
            "cohort_id": iv.cohort_id}


@router.post("/{profile_id}/attempts", status_code=201)
def start_attempt(profile_id: str, response: Response, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    prof = _owned_profile(db, user, profile_id)
    if prof.archived:
        raise HTTPException(409, "Профіль архівовано")
    open_iv = _open_attempt(db, prof.id)
    if open_iv is not None:
        response.status_code = 200
        return _attempt_brief(open_iv)
    snap, _ = get_or_create_cohort(db, user, prof.track)
    if snap is None:
        raise HTTPException(422, "Для цього треку немає вакансій для добірки")
    iv, created = create_attempt(db, user, prof.id, snap.id)
    if not created:
        response.status_code = 200
    return _attempt_brief(iv)


@router.get("/{profile_id}/attempts")
def list_attempts(profile_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    prof = _owned_profile(db, user, profile_id)
    items = []
    for iv in db.scalars(select(CoreInterview).where(CoreInterview.profile_id == prof.id)
                         .order_by(CoreInterview.attempt_no.desc())).all():
        turns = db.scalars(select(CoreTurn).where(CoreTurn.interview_id == iv.id)).all()
        items.append({"id": iv.id, "attempt_no": iv.attempt_no, "status": iv.status, "cohort_id": iv.cohort_id,
                      "created_at": iv.created_at.isoformat() if iv.created_at else None,
                      "topics_used": len({t.action_id for t in turns}),
                      "answers_count": sum(1 for t in turns if t.answer_text is not None)})
    return {"items": items}


# ---- results ---------------------------------------------------------------------------------------------

def _competencies(db: Session, iv: CoreInterview) -> list[dict]:
    rows = current_criteria_rows(db.scalars(
        select(CriterionAssessment).where(CriterionAssessment.session_id == iv.id)
        .order_by(CriterionAssessment.revision, CriterionAssessment.created_at)).all())
    latest_rev: dict[str, int] = {}
    for r in rows:
        latest_rev[r.action_id] = max(latest_rev.get(r.action_id, 0), r.revision)
    cur = [r for r in rows if r.revision == latest_rev[r.action_id]]
    scores = _action_scores(rows)
    names = _names(db)
    out = []
    for action in scores:
        mine = [r for r in cur if r.action_id == action]
        scored = [r for r in mine if r.score is not None] or mine
        out.append({"action_id": action, "action_name": names.get(action, action), "score": scores[action],
                    "reason": " ".join(dict.fromkeys(r.reason for r in scored if r.reason)),
                    "evidence": [e for r in scored for e in (r.evidence or [])]})
    return out


@router.get("/{profile_id}/results")
def results(profile_id: str, page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=50),
            work_mode: str = "", seniority: str = "", q: str = "",
            min_share: int | None = Query(None, ge=0, le=100),
            db: Session = Depends(get_db), user: User = Depends(current_user)):
    prof = _owned_profile(db, user, profile_id)
    iv = _latest_finished(db, prof.id)
    base = {"profile_id": prof.id, "page": page, "page_size": page_size, "note": NOTE}
    if iv is None:
        return {"has_results": False, "attempt_id": None, "total": 0, "items": [], "competencies": [],
                "market": [], **base}
    snap = db.get(CohortSnapshot, iv.cohort_id)
    items = rank_items(db, prof.years_experience, snap, attempt_scores(db, iv.id))
    if work_mode:
        items = [i for i in items if (i["work_mode"] or "").lower() == work_mode.lower()]
    if seniority:
        items = [i for i in items if (i["seniority"] or "").lower() == seniority.lower()]
    if q:
        needle = q.lower()
        items = [i for i in items if needle in (i["title"] or "").lower() or needle in (i["company"] or "").lower()]
    if min_share is not None:
        items = [i for i in items if i["confirmed_share"] >= min_share]
    start = (page - 1) * page_size
    names = _names(db)
    market = compute_market(_market_input(_revisions(snap)))
    return {"has_results": True, "attempt_id": iv.id, "total": len(items), "items": items[start:start + page_size],
            "competencies": _competencies(db, iv),
            "market": [{"order": i + 1, "action_id": e.action_id, "name": names.get(e.action_id, e.action_id)}
                       for i, e in enumerate(market)], **base}
