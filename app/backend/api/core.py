"""Adaptive open-text interview, Evaluator assessments and read-only LLM scores. CLAUDE_PROMPT §4.

Budgets: ≤10 distinct actions, ≤5 shown questions per action. Pending question is never regenerated.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.domain.core_flow import planner_state
from backend.domain.interview_budget import can_ask_question, can_start_topic
from backend.domain.market import VacancyInput, compute_market
from backend.domain.planner import choose_next
from backend.models import (CohortSnapshot, CoreInterview, CoreTurn, Competency, CriterionAssessment, Rubric,
                            User)
from backend.providers.llm import get_transport
from backend.providers.roles import LLMError, evaluator_assess, interviewer_question
from backend.security import current_user

router = APIRouter(tags=["adaptive interview"])


def _owned_interview(db: Session, user: User, interview_id: str) -> CoreInterview:
    iv = db.scalar(select(CoreInterview).where(CoreInterview.id == interview_id, CoreInterview.user_id == user.id))
    if iv is None:
        raise HTTPException(404, "Інтерв'ю не знайдено")
    return iv


def _owned_cohort(db: Session, user: User, cohort_id: str) -> CohortSnapshot:
    snap = db.scalar(select(CohortSnapshot).where(CohortSnapshot.id == cohort_id, CohortSnapshot.user_id == user.id))
    if snap is None:
        raise HTTPException(404, "Добірку не знайдено")
    return snap


def _revisions(snap: CohortSnapshot) -> list[dict]:
    return [{"id": vid, **snap.requirement_revisions[vid]} for vid in snap.vacancy_ids]


def latest_scores(db: Session, user: User) -> dict[str, float | None]:
    """Most recent accepted LLM score per action, across this user's interviews."""
    rows = db.scalars(select(CriterionAssessment).where(CriterionAssessment.user_id == user.id)
                      .order_by(CriterionAssessment.created_at, CriterionAssessment.revision)).all()
    out: dict[str, float | None] = {}
    for r in rows:
        out[r.action_id] = r.score
    return out


def _label(db: Session, action_id: str) -> str:
    c = db.get(Competency, action_id)
    return c.label_uk if c else action_id


def _turn_dict(t: CoreTurn) -> dict:
    return {"id": t.id, "sequence": t.sequence, "action_id": t.action_id, "question_text": t.question_text,
            "question_source": t.question_source, "answer_text": t.answer_text,
            "graded": t.question_source == "LLM_INTERVIEWER"}


class CreateInterview(BaseModel):
    cohort_id: str


class VersionBody(BaseModel):
    version: int = Field(ge=0)


class AnswerBody(VersionBody):
    turn_id: str
    text: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=8, max_length=120)


@router.post("/interviews", status_code=201)
def create_interview(data: CreateInterview, db: Session = Depends(get_db), user: User = Depends(current_user)):
    snap = _owned_cohort(db, user, data.cohort_id)
    iv = CoreInterview(user_id=user.id, cohort_id=snap.id, status="ACTIVE", version=0)
    db.add(iv)
    db.commit()
    return {"id": iv.id, "status": iv.status, "version": iv.version}


@router.get("/interviews/{interview_id}")
def get_interview(interview_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    iv = _owned_interview(db, user, interview_id)
    turns = db.scalars(select(CoreTurn).where(CoreTurn.interview_id == iv.id).order_by(CoreTurn.sequence)).all()
    pending = next((t for t in turns if t.answer_text is None), None)
    return {"id": iv.id, "status": iv.status, "version": iv.version,
            "turns": [_turn_dict(t) for t in turns],
            "pending_turn": _turn_dict(pending) if pending else None}


@router.post("/interviews/{interview_id}/next-question")
def next_question(interview_id: str, data: VersionBody, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    iv = _owned_interview(db, user, interview_id)
    if data.version != iv.version:
        raise HTTPException(409, "Стан інтерв'ю змінився, оновіть сторінку")
    if iv.status != "ACTIVE":
        raise HTTPException(409, "Інтерв'ю не активне")
    turns = db.scalars(select(CoreTurn).where(CoreTurn.interview_id == iv.id).order_by(CoreTurn.sequence)).all()
    pending = next((t for t in turns if t.answer_text is None), None)
    if pending is not None:
        return {"turn": _turn_dict(pending), "version": iv.version}  # never regenerate a shown question
    snap = db.get(CohortSnapshot, iv.cohort_id)
    revisions = _revisions(snap)
    state, weights = planner_state(revisions, latest_scores(db, user))
    shown: dict[str, int] = {}
    for t in turns:
        shown[t.action_id] = shown.get(t.action_id, 0) + 1
    used = set(shown)
    mass = {e.action_id: e.mass for e in compute_market([
        VacancyInput(r["id"], tuple(tuple(a["competency_id"] for a in g["alternatives"]) for g in r["groups"]))
        for r in revisions])}
    available = sorted({a for alts in state.open_alternatives.values() for a in alts
                        if can_ask_question(shown.get(a, 0)) and (a in used or can_start_topic(len(used)))})
    action = choose_next(state, weights, available, mass)
    if action is None:
        return {"turn": None, "version": iv.version, "done": True}
    label = _label(db, action)
    prior = [t.answer_text for t in turns if t.action_id == action and t.answer_text]
    question, source = None, "FALLBACK_UNGRADED"
    transport = get_transport()
    if transport is not None:
        try:
            question = interviewer_question(transport, action_name=label, rubric_criteria=[action],
                                            previous_turns=prior, followup_goal=None)
            source = "LLM_INTERVIEWER"
        except LLMError:
            question = None
    if question is None:
        question = f"Розкажіть про ваш практичний досвід: {label}. Наведіть конкретний приклад."
    turn = CoreTurn(interview_id=iv.id, sequence=len(turns) + 1, action_id=action, question_text=question,
                    question_source=source)
    iv.version += 1
    db.add(turn)
    db.commit()
    return {"turn": _turn_dict(turn), "version": iv.version, "done": False}


def _assess_action(db: Session, user: User, iv: CoreInterview, action_id: str) -> str:
    """Run Evaluator on the whole current action series; returns ACCEPTED | UNGRADED."""
    transport = get_transport()
    if transport is None:
        return "UNGRADED"
    turns = db.scalars(select(CoreTurn).where(CoreTurn.interview_id == iv.id, CoreTurn.action_id == action_id,
                                              CoreTurn.question_source == "LLM_INTERVIEWER",
                                              CoreTurn.answer_text.is_not(None)).order_by(CoreTurn.sequence)).all()
    if not turns:
        return "UNGRADED"
    rubric = db.scalar(select(Rubric).where(Rubric.action_id == action_id, Rubric.version == "auto-1"))
    if rubric is None:
        rubric = Rubric(action_id=action_id, version="auto-1", source="LLM_PROPOSED")
        db.add(rubric)
        db.flush()
    text_by_turn = {t.id: t.answer_text for t in turns}
    try:
        out = evaluator_assess(transport, action_id=action_id, rubric_version="auto-1",
                               allowed_criteria={action_id}, turns=text_by_turn)
    except LLMError:
        return "UNGRADED"
    rev = (db.scalar(select(func.max(CriterionAssessment.revision)).where(
        CriterionAssessment.session_id == iv.id, CriterionAssessment.action_id == action_id)) or 0) + 1
    for c in out.criteria:
        db.add(CriterionAssessment(user_id=user.id, session_id=iv.id, action_id=action_id,
                                   criterion_id=c.criterion_id, rubric_id=rubric.id, score=c.score,
                                   reason=c.reason, evidence=[e.model_dump() for e in c.evidence], revision=rev))
    return "ACCEPTED"


@router.post("/interviews/{interview_id}/answers")
def submit_answer(interview_id: str, data: AnswerBody, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    iv = _owned_interview(db, user, interview_id)
    replay = db.scalar(select(CoreTurn).where(CoreTurn.interview_id == iv.id,
                                              CoreTurn.idempotency_key == data.idempotency_key))
    if replay is not None:
        return {"turn": _turn_dict(replay), "version": iv.version, "replayed": True}
    if data.version != iv.version:
        raise HTTPException(409, "Стан інтерв'ю змінився, оновіть сторінку")
    turn = db.scalar(select(CoreTurn).where(CoreTurn.id == data.turn_id, CoreTurn.interview_id == iv.id))
    if turn is None:
        raise HTTPException(404, "Питання не знайдено")
    if turn.answer_text is not None:
        raise HTTPException(409, "На це питання вже відповідено")
    turn.answer_text = data.text.strip()
    turn.idempotency_key = data.idempotency_key
    iv.version += 1
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Відповідь уже збережено в іншому запиті")
    status = _assess_action(db, user, iv, turn.action_id)
    db.commit()
    return {"turn": _turn_dict(turn), "version": iv.version, "replayed": False, "assessment_status": status}


@router.post("/interviews/{interview_id}/{action}")
def lifecycle(interview_id: str, action: str, data: VersionBody, db: Session = Depends(get_db),
              user: User = Depends(current_user)):
    if action not in ("pause", "resume", "finish"):
        raise HTTPException(404, "Невідома дія")
    iv = _owned_interview(db, user, interview_id)
    if data.version != iv.version:
        raise HTTPException(409, "Стан інтерв'ю змінився, оновіть сторінку")
    target = {"pause": "PAUSED", "resume": "ACTIVE", "finish": "FINISHED"}[action]
    allowed = {"pause": {"ACTIVE"}, "resume": {"PAUSED"}, "finish": {"ACTIVE", "PAUSED"}}[action]
    if iv.status not in allowed:
        raise HTTPException(409, "Недопустимий перехід стану")
    iv.status = target
    iv.version += 1
    db.commit()
    return {"id": iv.id, "status": iv.status, "version": iv.version}


@router.get("/assessments")
def list_assessments(interview_id: str | None = None, db: Session = Depends(get_db),
                     user: User = Depends(current_user)):
    """Read-only accepted assessments. There is intentionally no write endpoint for LLM scores."""
    query = select(CriterionAssessment).where(CriterionAssessment.user_id == user.id)
    if interview_id:
        query = query.where(CriterionAssessment.session_id == interview_id)
    rows = db.scalars(query.order_by(CriterionAssessment.created_at, CriterionAssessment.revision)).all()
    return {"items": [{"interview_id": r.session_id, "action_id": r.action_id, "criterion_id": r.criterion_id,
                       "score": r.score, "reason": r.reason, "evidence": r.evidence, "revision": r.revision,
                       "source": "LLM_EVALUATOR", "editable": False} for r in rows]}
