from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.models import (CandidateProfile, CoreInterview, User, Vacancy, Snapshot, InterviewSession, MatchRun)


def require_snapshot(db: Session, user_id: str, snapshot_id: str) -> Snapshot:
    snap = db.scalar(select(Snapshot).where(Snapshot.id == snapshot_id, Snapshot.user_id == user_id))
    if snap is None:
        raise HTTPException(404, "Snapshot not found")
    return snap


def require_interview(db: Session, user_id: str, interview_id: str, *, lock=False) -> InterviewSession:
    query = select(InterviewSession).where(InterviewSession.id == interview_id, InterviewSession.user_id == user_id)
    if lock:
        query = query.with_for_update()
    session = db.scalar(query)
    if session is None:
        raise HTTPException(404, "Interview not found")
    return session


def require_match(db: Session, user_id: str, match_id: str) -> MatchRun:
    result = db.scalar(select(MatchRun).where(MatchRun.id == match_id, MatchRun.user_id == user_id))
    if not result:
        raise HTTPException(404, "Match run not found")
    return result


def serialize_vacancy(v: Vacancy, *, with_groups: bool = True) -> dict:
    fields = ["id","track","title","company","seniority","years_min","years_max","location","work_mode",
              "employment","salary_min","salary_max","currency","summary","description","responsibilities",
              "benefits","stack","source_type","source_url","fixture_version"]
    data = {key: getattr(v, key) for key in fields}
    if with_groups:
        data["groups"] = [{"id": g.id, "kind": g.kind, "label": g.label, "excerpt": g.excerpt,
                           "alternatives": [{"competency_id": a.competency_id, "required_level": a.required_level,
                                             "normalization_status": a.normalization_status} for a in g.alternatives]}
                          for g in v.groups]
    else:
        data["requirements_count"] = len(v.groups)
    return data


def source_label(v: Vacancy) -> str:
    """User-facing provenance label: «Djinni» only for vacancies imported from Djinni (REAL_IMPORTED); the curated and
    generated fixtures are invented example vacancies: the label «Приклад» must never be replaced by a real job board name."""
    return "Djinni" if v.source_type == "REAL_IMPORTED" else "Приклад"


def freeze_payload(records: list[dict]) -> tuple[list[dict], str]:
    """Canonical payload and sha256 for a frozen vacancy list (order as given)."""
    import hashlib
    import json
    payload = list(records)
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return payload, hashlib.sha256(serialized.encode()).hexdigest()


def serialize_snapshot(s: Snapshot, *, with_vacancies: bool = False) -> dict:
    payload = {"id": s.id, "name": s.name, "track": s.track, "status": s.status,
               "frozen_at": s.frozen_at.isoformat() if s.frozen_at else None,
               "sha256": s.sha256, "vacancy_count": len(s.vacancy_payload),
               "vacancy_ids": [v["id"] for v in s.vacancy_payload], "cohort_policy": s.cohort_policy}
    if with_vacancies:
        payload["vacancies"] = s.vacancy_payload
    return payload


def make_default_profile(db: Session, user: User) -> CandidateProfile:
    prof = CandidateProfile(user_id=user.id, track=None, name="Основний профіль",
                            desired_title=user.desired_title or "", years_experience=user.years_experience,
                            location=user.location or "")
    db.add(prof)
    db.flush()
    return prof


def default_profile(db: Session, user: User) -> CandidateProfile:
    """Oldest non-archived profile of the user; created on demand."""
    prof = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id,
                                                    CandidateProfile.archived.is_(False))
                     .order_by(CandidateProfile.created_at, CandidateProfile.id))
    return prof or make_default_profile(db, user)


def next_attempt_no(db: Session, profile_id: str) -> int:
    from sqlalchemy import func
    return (db.scalar(select(func.max(CoreInterview.attempt_no)).where(CoreInterview.profile_id == profile_id)) or 0) + 1


def open_attempt(db: Session, profile_id: str) -> CoreInterview | None:
    return db.scalar(select(CoreInterview).where(CoreInterview.profile_id == profile_id,
                                                 CoreInterview.status != "FINISHED")
                     .order_by(CoreInterview.attempt_no.desc()))


def create_attempt(db: Session, user: User, profile_id: str, cohort_id: str) -> tuple[CoreInterview, bool]:
    """Insert the next attempt. A concurrent racer hits uq (profile_id, attempt_no): return its open attempt."""
    from sqlalchemy.exc import IntegrityError
    iv = CoreInterview(user_id=user.id, cohort_id=cohort_id, status="ACTIVE", version=0, profile_id=profile_id,
                       attempt_no=next_attempt_no(db, profile_id))
    db.add(iv)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = open_attempt(db, profile_id)
        if existing is None:
            raise HTTPException(409, "Не вдалося створити спробу, повторіть запит")
        return existing, False
    return iv, True
