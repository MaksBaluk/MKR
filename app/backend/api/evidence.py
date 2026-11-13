"""Rubric grading proposals and candidate review. Proposals never change the profile by themselves."""
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from backend.config import get_settings
from backend.db import get_db
from backend.models import Competency, EvidenceItem, InterviewSession, InterviewTurn, User
from backend.security import current_user
from backend.domain.rubric import RUBRIC_VERSION
from backend.providers.llm import grade_answer, LLMUnavailable
from .common import require_interview

router = APIRouter(tags=["rubric grading & candidate review"])


class ReviewInput(BaseModel):
    decision: Literal["ACCEPT", "REJECT"]


def serialize_evidence(e: EvidenceItem) -> dict:
    return {"id": e.id, "interview_id": e.interview_id, "turn_id": e.turn_id, "competency_id": e.competency_id,
            "level": e.level, "provenance": e.provenance, "status": e.status, "rubric_version": e.rubric_version,
            "evidence_quote": e.excerpt, "confidence": e.confidence, "uncertainty": e.uncertainty,
            "reviewed_at": e.reviewed_at.isoformat() if e.reviewed_at else None}


@router.post("/interviews/{interview_id}/turns/{turn_id}/grade")
def grade_turn(interview_id: str, turn_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not get_settings().llm_ready:
        raise HTTPException(503, "LLM provider not enabled; configure .env first")
    interview = require_interview(db, user.id, interview_id)
    if interview.status == "COMPLETED":
        raise HTTPException(409, "Interview completed; grading is no longer possible")
    turn = next((t for t in interview.turns if t.id == turn_id), None)
    if turn is None or turn.status != "ANSWERED" or turn.question_kind != "FREE_TEXT" or not turn.answer_text:
        raise HTTPException(422, "An answered free-text turn is required")
    existing = db.scalar(select(EvidenceItem).where(EvidenceItem.turn_id == turn.id))
    if existing is not None:
        return serialize_evidence(existing)
    competency = db.get(Competency, turn.competency_id)
    try:
        graded = grade_answer(question=turn.question_text, answer=turn.answer_text,
                              competency_label=competency.label_uk if competency else turn.competency_id)
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    item = EvidenceItem(user_id=user.id, interview_id=interview.id, turn_id=turn.id,
                        competency_id=turn.competency_id, level=graded["level"], provenance="LLM_PROPOSAL",
                        status="PROPOSED", rubric_version=RUBRIC_VERSION, excerpt=graded["evidence_quote"],
                        confidence=graded["confidence"], uncertainty=graded["uncertainty"])
    db.add(item)
    turn.assessment_status = "RUBRIC_PROPOSED"
    try:
        db.commit()
    except IntegrityError:
        # Concurrent grade for the same turn: return the row that won the race.
        db.rollback()
        winner = db.scalar(select(EvidenceItem).where(EvidenceItem.turn_id == turn.id))
        if winner is None:
            raise HTTPException(409, "Grading conflict, retry")
        return serialize_evidence(winner)
    db.refresh(item)
    return serialize_evidence(item)


@router.post("/evidence/{evidence_id}/review")
def review_evidence(evidence_id: str, data: ReviewInput, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    item = db.scalar(select(EvidenceItem).where(EvidenceItem.id == evidence_id, EvidenceItem.user_id == user.id))
    if item is None:
        raise HTTPException(404, "Evidence not found")
    if item.status != "PROPOSED":
        raise HTTPException(409, "Evidence already reviewed")
    # Lock the interview so a concurrent finish cannot write P1 between this check and the confirmation.
    interview = require_interview(db, user.id, item.interview_id, lock=True)
    db.refresh(item)
    if item.status != "PROPOSED":
        raise HTTPException(409, "Evidence already reviewed")
    if interview.status == "COMPLETED":
        raise HTTPException(409, "Interview completed; review before finishing")
    turn = db.get(InterviewTurn, item.turn_id)
    if data.decision == "ACCEPT":
        if item.level is None:
            raise HTTPException(422, "Proposal has no level to confirm")
        item.status, item.provenance = "CONFIRMED", "HUMAN_REVIEW"
        turn.assessment_status = "CONFIRMED"
    else:
        item.status = "REJECTED"
        turn.assessment_status = "REJECTED"
    item.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return serialize_evidence(item)


@router.get("/interviews/{interview_id}/evidence")
def list_evidence(interview_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_interview(db, user.id, interview_id)
    rows = db.scalars(select(EvidenceItem).where(EvidenceItem.interview_id == interview_id,
                                                 EvidenceItem.user_id == user.id)).all()
    return [serialize_evidence(r) for r in rows]
