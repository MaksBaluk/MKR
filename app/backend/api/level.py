"""Assessed professional level (§3e) of a finished attempt: stored once per (attempt, policy version), owner-only API.

The level is evidence-based and never feeds the vacancy ranking. Rows are immutable: a new policy version adds a row
and never rewrites an earlier one; attempts are never mixed (evidence comes from one attempt's rows only).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api.core import SEEDED_SOURCES, _interview_track, _owned_interview, is_practice, seniority_evidence
from backend.db import get_db
from backend.domain.seniority import CriterionEvidence, estimate, result_to_json
from backend.domain.seniority_policy import SeniorityPolicy, policy_for
from backend.models import (CandidateProfile, CoreInterview, CoreTurn, CriterionAssessment, Rubric, RubricCriterion,
                            SeniorityAssessment, User)
from backend.security import current_user

router = APIRouter(tags=["assessed level"])
log = logging.getLogger("competencematch.level")
WORKING_ASSUMPTION_NOTE = "Потребує експертної валідації"


def _attempt_rows(db: Session, interview_id: str) -> list[CriterionAssessment]:
    return list(db.scalars(select(CriterionAssessment).where(CriterionAssessment.session_id == interview_id)
                           .order_by(CriterionAssessment.created_at, CriterionAssessment.revision)).all())


def attempt_evidence(db: Session, interview_id: str) -> dict[str, CriterionEvidence]:
    """Estimator input from this attempt only (topic criteria via effective_rows, practice per source topic)."""
    topics = {t.id: t.action_id for t in db.scalars(select(CoreTurn).where(CoreTurn.interview_id == interview_id))}
    return seniority_evidence(_attempt_rows(db, interview_id), topics)


def _rubric_versions(db: Session, rows: list[CriterionAssessment]) -> dict[str, str]:
    out: dict[str, str] = {}
    for rid in dict.fromkeys(r.rubric_id for r in rows if r.rubric_id):
        rubric = db.get(Rubric, rid)
        if rubric is not None:
            out[rubric.action_id] = rubric.version
    return dict(sorted(out.items()))


def _stored(db: Session, interview_id: str, version: str | None) -> SeniorityAssessment | None:
    cond = (SeniorityAssessment.policy_version.is_(None) if version is None
            else SeniorityAssessment.policy_version == version)
    return db.scalar(select(SeniorityAssessment).where(SeniorityAssessment.interview_id == interview_id, cond)
                     .order_by(SeniorityAssessment.created_at))


def finalize_level(db: Session, iv: CoreInterview, policy: SeniorityPolicy | None = None) -> SeniorityAssessment:
    """Store the level of a finished attempt under `policy` (default: the track's current policy). Idempotent per
    (attempt, policy version): an existing row is returned unchanged, never overwritten. The caller commits.
    Raises ValueError for a malformed stored score (the estimator never guesses)."""
    track = _interview_track(db, iv)
    policy = policy if policy is not None else policy_for(track)
    version = policy.version if policy else None
    existing = _stored(db, iv.id, version)
    if existing is not None:
        return existing
    result = estimate(policy, attempt_evidence(db, iv.id))
    prof = db.get(CandidateProfile, iv.profile_id) if iv.profile_id else None
    row = SeniorityAssessment(
        user_id=iv.user_id, profile_id=iv.profile_id, interview_id=iv.id, track=track,
        policy_id=policy.policy_id if policy else None, policy_version=version,
        policy_status=policy.status if policy else None, assessed_level=result.assessed_level,
        highest_supported_level=result.highest_supported_level, assessment_status=result.assessment_status,
        result=result_to_json(result), rubric_versions=_rubric_versions(db, _attempt_rows(db, iv.id)),
        desired_level=prof.target_level if prof else None)
    try:
        with db.begin_nested():
            db.add(row)
    except IntegrityError:  # a parallel request stored the same (attempt, version) first: keep that row
        winner = _stored(db, iv.id, version)
        if winner is None:
            raise
        return winner
    return row


def finalize_on_finish(db: Session, iv: CoreInterview) -> None:
    """Hook for every transition to FINISHED: storing the level must never block finishing the interview (any error is
    logged and the level is left to the lazy computation on first read)."""
    try:
        with db.begin_nested():  # a failure rolls back only the level write, never the finish itself
            finalize_level(db, iv)
    except Exception as exc:  # noqa: BLE001 - the level is computed lazily on first read instead
        log.warning("level not stored for a finished attempt kind=%s", type(exc).__name__, exc_info=True)


def _titles(db: Session) -> dict[str, str]:
    rows = db.execute(select(RubricCriterion.criterion_id, RubricCriterion.anchors).join(
        Rubric, Rubric.id == RubricCriterion.rubric_id).where(Rubric.version == "v1",
                                                              Rubric.source.in_(SEEDED_SOURCES))).all()
    return {cid: (anchors or {}).get("title") or cid for cid, anchors in rows}


def level_payload(db: Session, row: SeniorityAssessment) -> dict:
    """User-facing level block: every criterion carries a Ukrainian title; explanation lines name titles, not ids."""
    titles = _titles(db)
    r = row.result

    def item(cid: str) -> dict:
        return {"id": cid, "title": titles.get(cid, cid), "kind": "PRACTICE" if is_practice(cid) else "COMPETENCY"}

    ids = {c for cov in r["coverage_by_level"].values()
           for key in ("confirmed_ids", "gap_ids", "unassessed_ids") for c in cov[key]}
    explanation = []
    for line in r["explanation"]:
        for cid in sorted(ids, key=len, reverse=True):
            line = line.replace(cid, f"«{titles.get(cid, cid)}»")
        explanation.append(line)
    def pool(p: dict) -> dict:
        return {"id": p["pool_id"], "title": p["title"], "status": p["status"],
                "criteria": [item(x) for x in p["members"]]}

    coverage = {lvl: {"status": c["status"], "critical_total": c["critical_total"], "assessed_count": c["assessed"],
                      "confirmed_count": c["confirmed"], "gap_count": c["gaps"],
                      "assessed_share": c["assessed_share"], "confirmed_share": c["confirmed_share"],
                      "competencies_confirmed": c["competencies_confirmed"], "reasons": c["reasons"],
                      "confirmed": [item(x) for x in c["confirmed_ids"]], "gaps": [item(x) for x in c["gap_ids"]],
                      "unassessed": [item(x) for x in c["unassessed_ids"]],
                      **({"pools": [pool(p) for p in c["pools"]]} if "pools" in c else {})}
                for lvl, c in r["coverage_by_level"].items()}
    # Pooled policies (v2, v3): the "not checked" list names whole capabilities (pool titles), not every alternative tool.
    unassessed = set(r["unassessed_criteria"])
    unassessed_pools = list({p["pool_id"]: {"id": p["pool_id"], "title": p["title"]}
                             for c in r["coverage_by_level"].values() for p in c.get("pools", ())
                             if p["status"] == "UNASSESSED" and set(p["members"]) <= unassessed}.values())
    return {"interview_id": row.interview_id, "desired_level": row.desired_level,
            "assessed_level": row.assessed_level, "highest_supported_level": row.highest_supported_level,
            "assessment_status": row.assessment_status,
            "policy": {"id": row.policy_id, "version": row.policy_version, "status": row.policy_status},
            "coverage_by_level": coverage,
            "confirmed_strengths": [item(c) for c in r["confirmed_strengths"]],
            "critical_gaps": [item(c) for c in r["critical_gaps"]],
            "unassessed_criteria": [item(c) for c in r["unassessed_criteria"]],
            "unassessed_pools": unassessed_pools,
            "evidence_references": [{**item(c), "turn_ids": t} for c, t in r["evidence_references"].items()],
            "explanation": explanation,
            "note": WORKING_ASSUMPTION_NOTE if row.policy_status == "WORKING_ASSUMPTION" else None,
            "created_at": _iso_utc(row.created_at)}


def _iso_utc(value: datetime | None) -> str | None:
    """Stored instants are UTC; SQLite returns them naive, PostgreSQL aware: one stable representation."""
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def level_for_attempt(db: Session, iv: CoreInterview) -> dict | None:
    """Payload of the attempt's stored level: the row of the track's current policy when it exists, otherwise the latest
    stored row (e.g. a v1 row of an attempt finished before v2: rendered as stored, never rewritten). Only a finished
    attempt without any row is assessed now, under the current policy, and stored.
    None when the attempt is not finished or its stored scores are malformed."""
    if iv.status != "FINISHED":
        return None
    current = policy_for(_interview_track(db, iv))
    rows = list(db.scalars(select(SeniorityAssessment).where(SeniorityAssessment.interview_id == iv.id)
                           .order_by(SeniorityAssessment.created_at.desc())))
    # The current policy's row if stored, else the latest stored row (an older version is never re-assessed on read).
    key = (current.policy_id, current.version) if current is not None else None
    row = next((x for x in rows if (x.policy_id, x.policy_version) == key), rows[0] if rows else None)
    try:
        if row is None:
            with db.begin_nested():
                row = finalize_level(db, iv)
            db.commit()
        return level_payload(db, row)
    except Exception as exc:  # noqa: BLE001 - a level failure never breaks results; the endpoint answers 409
        log.warning("level not available for a finished attempt kind=%s", type(exc).__name__, exc_info=True)
        return None


@router.get("/interviews/{interview_id}/level")
def interview_level(interview_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    iv = _owned_interview(db, user, interview_id)
    if iv.status != "FINISHED":
        raise HTTPException(409, "Рівень визначається після завершення співбесіди")
    payload = level_for_attempt(db, iv)
    if payload is None:
        raise HTTPException(409, "Рівень не вдалося визначити за збереженими оцінками")
    return payload


@router.get("/profiles/{profile_id}/level")
def profile_level(profile_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Level of the profile's latest finished attempt only (attempts are never combined)."""
    prof = db.scalar(select(CandidateProfile).where(CandidateProfile.id == profile_id,
                                                    CandidateProfile.user_id == user.id))
    if prof is None:
        raise HTTPException(404, "Профіль не знайдено")
    iv = db.scalar(select(CoreInterview).where(CoreInterview.profile_id == prof.id, CoreInterview.status == "FINISHED")
                   .order_by(CoreInterview.created_at.desc(), CoreInterview.attempt_no.desc()))
    payload = level_for_attempt(db, iv) if iv is not None else None
    if payload is None:
        raise HTTPException(404, "Результатів ще немає")
    return payload
