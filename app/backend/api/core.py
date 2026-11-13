"""Adaptive open-text interview, Evaluator assessments and read-only LLM scores. CLAUDE_PROMPT §4.

Budgets: ≤10 distinct actions, ≤5 shown questions per action. Pending question is never regenerated.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api.common import create_attempt, default_profile
from backend.db import get_db
from backend.domain.core_flow import planner_state
from backend.domain.interview_budget import can_ask_question, can_start_topic
from backend.domain.market import VacancyInput, compute_market
from backend.domain.planner import choose_next
from backend.agents.graphs import run_answer, run_ask
from backend.agents.model import get_chat_model
from backend.models import (CohortSnapshot, CoreInterview, CoreTurn, Competency, CriterionAssessment, Rubric,
                            RubricCriterion, User)
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


def current_criteria_rows(rows) -> list:
    """Drop a legacy holistic row (criterion_id == action_id) for actions that also have seeded
    `<action>.<slug>` criterion rows; otherwise keep every row. Order is preserved."""
    dotted = {r.action_id for r in rows if "." in r.criterion_id}
    return [r for r in rows if not (r.action_id in dotted and r.criterion_id == r.action_id)]


def _action_scores(rows) -> dict[str, float | None]:
    """Per action: mean (weights 1) of non-null scores of the latest revision per criterion; None if all null."""
    latest: dict[tuple[str, str], float | None] = {}
    for r in current_criteria_rows(rows):  # rows arrive oldest first
        latest[(r.action_id, r.criterion_id)] = r.score
    by_action: dict[str, list[float]] = {}
    for (action, _), score in latest.items():
        vals = by_action.setdefault(action, [])
        if score is not None:
            vals.append(score)
    return {a: (sum(v) / len(v) if v else None) for a, v in by_action.items()}


def latest_scores(db: Session, user: User) -> dict[str, float | None]:
    """Action score per action (MATH_SPEC §3 M_c), across this user's interviews."""
    rows = db.scalars(select(CriterionAssessment).where(CriterionAssessment.user_id == user.id)
                      .order_by(CriterionAssessment.created_at, CriterionAssessment.revision)).all()
    return _action_scores(rows)


def attempt_scores(db: Session, interview_id: str) -> dict[str, float | None]:
    """Action scores from one attempt only."""
    rows = db.scalars(select(CriterionAssessment).where(CriterionAssessment.session_id == interview_id)
                      .order_by(CriterionAssessment.created_at, CriterionAssessment.revision)).all()
    return _action_scores(rows)


SEEDED_SOURCES = ("CURATED", "CURATED_TEMPLATE", "REVIEWED")
BAND_LABELS = {"0-0.25": "[0,0.25)", "0.25-0.5": "[0.25,0.5)", "0.5-0.75": "[0.5,0.75)", "0.75-0.9": "[0.75,0.9)",
               "0.9-1": "[0.9,1]"}


def _seeded_rubric(db: Session, action_id: str) -> Rubric | None:
    return db.scalar(select(Rubric).where(Rubric.action_id == action_id, Rubric.version == "v1",
                                          Rubric.source.in_(SEEDED_SOURCES)))


def _seeded_criteria(db: Session, action_id: str) -> list[RubricCriterion]:
    rubric = _seeded_rubric(db, action_id)
    if rubric is None:
        return []
    return list(db.scalars(select(RubricCriterion).where(RubricCriterion.rubric_id == rubric.id)
                           .order_by(RubricCriterion.criterion_id)).all())


def criteria_for(db: Session, action_id: str) -> list[str]:
    """Criterion ids of the seeded rubric (sorted), else the action itself."""
    return [c.criterion_id for c in _seeded_criteria(db, action_id)] or [action_id]


def criterion_bands(db: Session, action_id: str) -> dict[str, str] | None:
    """Per-criterion title + five anchored bands for the Evaluator; None keeps the default policy bands."""
    out = {}
    for c in _seeded_criteria(db, action_id):
        bands = (c.anchors or {}).get("bands") or {}
        text = " ".join(f"{BAND_LABELS.get(k, k)} {v}" for k, v in bands.items())
        out[c.criterion_id] = f"{(c.anchors or {}).get('title', c.criterion_id)}. {text}".strip()
    return out or None


def _label(db: Session, action_id: str) -> str:
    c = db.get(Competency, action_id)
    return c.label_uk if c else action_id


def _names(db: Session) -> dict[str, str]:
    return {c.id: c.label_uk for c in db.scalars(select(Competency)).all()}


def _turn_dict(t: CoreTurn, names: dict[str, str] | None = None) -> dict:
    return {"id": t.id, "sequence": t.sequence, "action_id": t.action_id,
            "action_name": (names or {}).get(t.action_id, t.action_id), "question_text": t.question_text,
            "question_source": t.question_source, "answer_text": t.answer_text,
            "created_at": t.created_at.isoformat() if t.created_at else None,
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
    prof = default_profile(db, user)
    iv, _ = create_attempt(db, user, prof.id, snap.id)
    return {"id": iv.id, "status": iv.status, "version": iv.version}


@router.get("/interviews/active")
def latest_open_interview(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Server-side resume: newest interview that is not finished. Survives browser storage loss."""
    iv = db.scalar(select(CoreInterview).where(CoreInterview.user_id == user.id, CoreInterview.status != "FINISHED")
                   .order_by(CoreInterview.created_at.desc()))
    if iv is None:
        return {"interview": None}
    return {"interview": {"id": iv.id, "cohort_id": iv.cohort_id, "status": iv.status, "version": iv.version}}


@router.get("/interviews/latest-finished")
def latest_finished_interview(db: Session = Depends(get_db), user: User = Depends(current_user)):
    iv = db.scalar(select(CoreInterview).where(CoreInterview.user_id == user.id, CoreInterview.status == "FINISHED")
                   .order_by(CoreInterview.created_at.desc()))
    if iv is None:
        return {"interview": None}
    return {"interview": {"id": iv.id, "cohort_id": iv.cohort_id, "status": iv.status, "version": iv.version}}


@router.get("/interviews/{interview_id}")
def get_interview(interview_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    iv = _owned_interview(db, user, interview_id)
    turns = db.scalars(select(CoreTurn).where(CoreTurn.interview_id == iv.id).order_by(CoreTurn.sequence)).all()
    pending = next((t for t in turns if t.answer_text is None), None)
    names = _names(db)
    return {"id": iv.id, "status": iv.status, "version": iv.version,
            "turns": [_turn_dict(t, names) for t in turns],
            "pending_turn": _turn_dict(pending, names) if pending else None,
            "topics_used": len({t.action_id for t in turns})}


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
        return {"turn": _turn_dict(pending, _names(db)), "version": iv.version}  # never regenerate a shown question
    snap = db.get(CohortSnapshot, iv.cohort_id)
    revisions = _revisions(snap)
    state, weights = planner_state(revisions, attempt_scores(db, iv.id))
    shown: dict[str, int] = {}
    for t in turns:
        shown[t.action_id] = shown.get(t.action_id, 0) + 1
    used = set(shown)
    mass = {e.action_id: e.mass for e in compute_market([
        VacancyInput(r["id"], tuple(tuple(a["competency_id"] for a in g["alternatives"]) for g in r["groups"]))
        for r in revisions])}
    latest_in_session = _action_scores(db.scalars(select(CriterionAssessment).where(
        CriterionAssessment.session_id == iv.id).order_by(CriterionAssessment.revision)).all())
    # A topic is re-asked only when the Evaluator found insufficient evidence (null score).
    def eligible(a: str) -> bool:
        if a not in used:
            return can_start_topic(len(used))
        return can_ask_question(shown[a]) and a in latest_in_session and latest_in_session[a] is None

    available = sorted({a for alts in state.open_alternatives.values() for a in alts if eligible(a)})
    action = choose_next(state, weights, available, mass)
    if action is None:
        return {"turn": None, "version": iv.version, "done": True}
    label = _label(db, action)
    answered = [t for t in turns if t.action_id == action and t.answer_text]
    comp = db.get(Competency, action)
    result = run_ask({"action_id": action, "action_name": label, "summary": comp.summary if comp else "",
                      "unmet_criteria": criteria_for(db, action),
                      "previous_answers": [t.answer_text for t in answered][-3:], "followup_goal": None,
                      "off_topic_detected": bool(answered and answered[-1].off_topic)}, get_chat_model())
    question, source = result.question_text, result.source
    turn = CoreTurn(interview_id=iv.id, sequence=len(turns) + 1, action_id=action, question_text=question,
                    question_source=source)
    iv.version += 1
    db.add(turn)
    db.commit()
    return {"turn": _turn_dict(turn, _names(db)), "version": iv.version, "done": False}


def _assess_action(db: Session, user: User, iv: CoreInterview, turn: CoreTurn) -> str:
    """Run the answer graph on the current action series; returns ACCEPTED | UNGRADED."""
    action_id = turn.action_id
    model = get_chat_model()
    if model is None:
        return "UNGRADED"
    turns = db.scalars(select(CoreTurn).where(CoreTurn.interview_id == iv.id, CoreTurn.action_id == action_id,
                                              CoreTurn.answer_text.is_not(None), CoreTurn.off_topic.is_(False))
                       .order_by(CoreTurn.sequence)).all()
    if not turns:
        return "UNGRADED"
    criteria = criteria_for(db, action_id)
    rubric = _seeded_rubric(db, action_id)
    version = "v1" if rubric else "auto-1"
    result = run_answer({"action_id": action_id, "rubric_version": version, "allowed_criterion_ids": criteria,
                         "bands": criterion_bands(db, action_id), "turns": {t.id: t.answer_text for t in turns}},
                        model)
    if result.status != "ACCEPTED":
        return "UNGRADED"
    if rubric is None:
        rubric = db.scalar(select(Rubric).where(Rubric.action_id == action_id, Rubric.version == "auto-1"))
    if rubric is None:
        rubric = Rubric(action_id=action_id, version="auto-1", source="LLM_PROPOSED")
        db.add(rubric)
        db.flush()
    rev = (db.scalar(select(func.max(CriterionAssessment.revision)).where(
        CriterionAssessment.session_id == iv.id, CriterionAssessment.action_id == action_id)) or 0) + 1
    if result.off_topic:  # null scores make the planner re-ask this action; nothing reaches ranking
        turn.off_topic = True
        for cid in criteria:
            db.add(CriterionAssessment(user_id=user.id, session_id=iv.id, action_id=action_id, criterion_id=cid,
                                       rubric_id=rubric.id, score=None, reason="Відповідь поза темою співбесіди.",
                                       evidence=[], revision=rev))
        return "ACCEPTED"
    for c in result.output.criteria:
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
        return {"turn": _turn_dict(replay, _names(db)), "version": iv.version, "replayed": True}
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
    status = _assess_action(db, user, iv, turn)
    db.commit()
    return {"turn": _turn_dict(turn, _names(db)), "version": iv.version, "replayed": False,
            "assessment_status": status}


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
    names = _names(db)
    return {"items": [{"interview_id": r.session_id, "action_id": r.action_id,
                       "action_name": names.get(r.action_id, r.action_id), "criterion_id": r.criterion_id,
                       "score": r.score, "reason": r.reason, "evidence": r.evidence, "revision": r.revision,
                       "source": "LLM_EVALUATOR", "editable": False} for r in rows]}
