from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.config import get_settings
from backend.db import get_db
from backend.models import Competency, User
from backend.security import current_user
from backend.providers.llm import assessment_proposal, status as llm_status, LLMUnavailable
from .common import require_interview

router = APIRouter(prefix="/llm", tags=["optional opt-in LLM"])


@router.get("/status")
def get_status():
    return llm_status()


class AssessmentInput(BaseModel):
    interview_id: str
    turn_id: str


@router.post("/review-proposal")
def propose_review(data: AssessmentInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not get_settings().llm_ready:
        raise HTTPException(503, "LLM provider not enabled; configure .env first")
    interview = require_interview(db, user.id, data.interview_id)
    turn = next((t for t in interview.turns if t.id == data.turn_id), None)
    if not turn or turn.status != "ANSWERED" or not turn.answer_text:
        raise HTTPException(422, "An answered free-text turn is required")
    competency = db.get(Competency, turn.competency_id)
    try:
        proposal = assessment_proposal(competency.label_uk if competency else turn.competency_id,
                                       turn.question_text, turn.answer_text)
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    turn.llm_proposal = proposal
    db.commit()
    return proposal
