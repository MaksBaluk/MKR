"""Candidate profiles: owner-scoped CRUD (archive), self-ratings, attempts and ranked results per profile."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.cohorts import _market_input, get_or_create_cohort
from backend.api.common import create_attempt, open_attempt
from backend.api.core import (_names, _revisions, action_summary, attempt_scores, cohort_actions, current_criteria_rows,
                              effective_rows,
                              profile_self_ratings, rubric_map)
from backend.api.level import level_for_attempt
from backend.api.recommendations import NOTE, rank_items
from backend.db import get_db
from backend.domain.core_flow import (TAU_SOURCE_LEVEL_MAP, alt_criteria, alt_tau, eval_alternative, eval_group,
                                      tau_for)
from backend.domain.topic_summary import topic_summary
from backend.domain.market import compute_market
from backend.models import (CandidateProfile, CandidateSelfRating, CohortSnapshot, Competency, CoreInterview,
                            CoreTurn, CriterionAssessment, User)
from backend.security import current_user

router = APIRouter(prefix="/profiles", tags=["profiles"])


class ProfileBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    track: Literal["python", "marketing", "design"] | None = None
    desired_title: str = Field(default="", max_length=160)
    target_level: Literal["junior", "middle", "senior", "lead"] | None = None
    work_mode: Literal["remote", "hybrid", "office", "any"] | None = None
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
    open_attempt = next((a for a in attempts if a.status in ("ACTIVE", "PAUSED")), None)
    return {"id": p.id, "name": p.name, "track": p.track, "desired_title": p.desired_title,
            "target_level": p.target_level, "work_mode": p.work_mode,
            "years_experience": p.years_experience, "location": p.location, "archived": p.archived,
            "attempts_count": len(attempts), "latest_finished_attempt_id": finished.id if finished else None,
            "open_attempt": ({"id": open_attempt.id, "cohort_id": open_attempt.cohort_id, "status": open_attempt.status}
                             if open_attempt else None),
            "latest_finished_attempt": ({"id": finished.id, "cohort_id": finished.cohort_id} if finished else None),
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

@router.get("/{profile_id}/self-ratings")
def get_self_ratings(profile_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    prof = _owned_profile(db, user, profile_id)
    return {"items": [{"action_id": k, "value": v, "source": "SELF_REPORT", "editable": True}
                      for k, v in profile_self_ratings(db, prof.id).items()]}


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
    missing = [label for label, value in (("напрям", prof.track), ("рівень, на який ви претендуєте", prof.target_level),
                                           ("роки досвіду", prof.years_experience)) if value in (None, "")]
    if missing:
        raise HTTPException(422, "Для початку співбесіди вкажіть: " + ", ".join(missing))
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

def _short_reason(reasons: list[str], limit: int = 2) -> str:
    """Join at most `limit` explanations, dropping ones that start like an earlier one (the evaluator repeats itself)."""
    seen: set[str] = set()
    kept: list[str] = []
    for text in reasons:
        key = " ".join(text.lower().split()[:5])
        if not text.strip() or key in seen:
            continue
        seen.add(key)
        kept.append(text.strip())
        if len(kept) == limit:
            break
    return " ".join(kept)


def _competencies(db: Session, iv: CoreInterview) -> list[dict]:
    rows = current_criteria_rows(db.scalars(
        select(CriterionAssessment).where(CriterionAssessment.session_id == iv.id)
        .order_by(CriterionAssessment.revision, CriterionAssessment.created_at)).all())
    cur = effective_rows(rows)  # current score per criterion across all revisions (a later null never erases one)
    cscores = attempt_scores(db, iv.id)
    summaries = action_summary(rows, rubric_map(db, {r.action_id for r in rows}, cscores))
    names = _names(db)
    ratings = profile_self_ratings(db, iv.profile_id)
    out = []
    for action, t in summaries.items():
        mine = [r for r in cur if r.action_id == action]
        scored = [r for r in mine if r.score is not None] or mine
        out.append({"action_id": action, "action_name": names.get(action, action), "score": t.m,
                    "interview_score": t.m, "coverage": t.e, "overall_level_allowed": t.overall_level_allowed, "self_rating": ratings.get(action),
                    "reason": _short_reason([r.reason for r in scored if r.reason]),
                    "sufficient_evidence": bool(mine) and all(bool(r.sufficient_evidence) for r in mine),
                    "evidence": [e for r in scored for e in (r.evidence or [])]})
    return out


def _seniority_band(level: str | None) -> str | None:
    """JUNIOR | MIDDLE | SENIOR; lead (candidate or vacancy) counts as SENIOR."""
    if not level:
        return None
    up = level.upper()
    return "SENIOR" if up == "LEAD" else up


def _section(item: dict, desired: str | None) -> str:
    """A label over the unchanged ranking (no new order): desired level, other fitting, or unresolved/gaps."""
    if desired and _seniority_band(item["seniority"]) == desired:
        return "DESIRED_LEVEL"
    return "OTHER_FITTING" if item["fits"] and item["z"] != 0 else "UNRESOLVED_OR_GAPS"


def _with_fit(item: dict) -> dict:
    """Add fit flag (some requirement is confirmed) and short Ukrainian reasons."""
    reasons = [f"Підтверджено: {x}" for x in item["strengths"]] + [f"Прогалина: {x}" for x in item["gaps"]]
    if item["unknown_count"]:
        reasons.append(f"Не оцінено: {item['unknown_count']} вимог")
    fits = item["confirmed_share"] > 0
    return {**item, "fits": fits, "reasons": reasons or ["Недостатньо даних для пояснення"]}


@router.get("/{profile_id}/results")
def results(profile_id: str, page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=50),
            work_mode: str = "", seniority: str = "", q: str = "",
            min_share: int | None = Query(None, ge=0, le=100),
            fitting: Literal["fitting", "all", "nonfitting"] = "fitting",
            db: Session = Depends(get_db), user: User = Depends(current_user)):
    prof = _owned_profile(db, user, profile_id)
    iv = _latest_finished(db, prof.id)
    base = {"profile_id": prof.id, "page": page, "page_size": page_size, "note": NOTE}
    if iv is None:
        return {"has_results": False, "attempt_id": None, "total": 0, "fitting_total": 0, "all_total": 0, "items": [],
                "competencies": [], "level": None,
                "market": [], **base}
    snap = db.get(CohortSnapshot, iv.cohort_id)
    level = level_for_attempt(db, iv)
    # the desired level stored with the attempt's level (shown in the level block); profile value only without one
    desired = _seniority_band(level["desired_level"] if level else prof.target_level)
    items = [{**f, "section": _section(f, desired)} for f in (
        _with_fit(i) for i in rank_items(db, prof.years_experience, snap, attempt_scores(db, iv.id),
                                         profile_self_ratings(db, prof.id)))]
    # Display order (owner decision, deviates from thesis (2.15)): displayed confirmed_share percent first. The sort is
    # stable over rank_items' (2.15) + T_v/J_v + id order, so equal percents keep that key. Filters keep relative order.
    # POST /recommendations keeps the pure (2.15) key.
    items.sort(key=lambda i: -i["confirmed_share"])
    if work_mode:
        items = [i for i in items if (i["work_mode"] or "").lower() == work_mode.lower()]
    if seniority:
        items = [i for i in items if (i["seniority"] or "").lower() == seniority.lower()]
    if q:
        needle = q.lower()
        items = [i for i in items if needle in (i["title"] or "").lower() or needle in (i["company"] or "").lower()]
    if min_share is not None:
        items = [i for i in items if i["confirmed_share"] >= min_share]
    fitting_total = sum(1 for i in items if i["fits"])
    all_total = len(items)
    if fitting != "all":
        items = [i for i in items if i["fits"] == (fitting == "fitting")]
    start = (page - 1) * page_size
    names = _names(db)
    market = compute_market(_market_input(_revisions(snap)))
    return {"has_results": True, "attempt_id": iv.id, "total": len(items), "fitting_total": fitting_total,
            "all_total": all_total, "items": items[start:start + page_size],
            "competencies": _competencies(db, iv), "level": level,
            "market": [{"order": i + 1, "action_id": e.action_id, "name": names.get(e.action_id, e.action_id)}
                       for i, e in enumerate(market)], **base}


LEVEL_WORDS = {1: "базовий", 2: "робочий", 3: "просунутий"}


@router.get("/{profile_id}/results/{vacancy_id}")
def result_detail(profile_id: str, vacancy_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Where the candidate fits one vacancy and why: every requirement with the needed level, the interview grade and a state."""
    prof = _owned_profile(db, user, profile_id)
    iv = _latest_finished(db, prof.id)
    if iv is None:
        raise HTTPException(404, "Результатів ще немає")
    snap = db.get(CohortSnapshot, iv.cohort_id)
    revision = next((r for r in _revisions(snap) if r["id"] == vacancy_id), None)
    if revision is None:
        raise HTTPException(404, "Вакансії немає у вашій добірці")
    scores = attempt_scores(db, iv.id)
    rubrics = rubric_map(db, cohort_actions(_revisions(snap)), scores)
    names = _names(db)
    item = next(_with_fit(i) for i in rank_items(db, prof.years_experience, snap, scores, profile_self_ratings(db, prof.id)) if i["vacancy_id"] == vacancy_id)
    groups = []
    for g in revision["groups"]:
        ev = eval_group(g["alternatives"], scores, rubrics)
        alternatives = []
        for a in g["alternatives"]:
            tau = alt_tau(a)
            tau = tau_for(a["required_level"]) if tau is None else tau
            required = alt_criteria(a, rubrics)
            req = topic_summary(required, scores)  # M_c / E_c over the alternative's required criteria
            score = req.m
            status = eval_alternative(a, scores, rubrics).status  # criterion-level, same as ranking
            # BORDERLINE only when every required criterion is graded; a partly graded topic stays UNKNOWN.
            state = {"SATISFIED": "MET", "FAILED": "GAP"}.get(
                status, "BORDERLINE" if score is not None and not req.unknown else "UNKNOWN")
            level = min(3, max(1, a["required_level"]))
            alternatives.append({"competency_id": a["competency_id"], "name": names.get(a["competency_id"], a["competency_id"]),
                                 "required_level": level, "required_label": LEVEL_WORDS[level], "threshold": tau,
                                 "threshold_source": a.get("tau_source") or TAU_SOURCE_LEVEL_MAP,
                                 "required_criteria": [c for c, _ in required],
                                 "candidate_score": score, "coverage": req.e, "state": state})
        groups.append({"id": g.get("id"), "kind": g["kind"], "label": g.get("label", ""), "excerpt": g.get("excerpt", ""),
                       "status": ev.status, "alternatives": alternatives})
    summary = {"met": sum(1 for g in groups if g["status"] == "SATISFIED"),
               "gap": sum(1 for g in groups if g["status"] == "FAILED"),
               "unknown": sum(1 for g in groups if g["status"] == "UNRESOLVED")}
    return {"vacancy_id": vacancy_id, "title": revision.get("title"), "company": revision.get("company"),
            "confirmed_share": item["confirmed_share"], "fits": item["fits"], "label": item["label"], "z": item["z"],
            "groups": groups, "summary": summary}
