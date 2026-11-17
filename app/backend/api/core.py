"""Adaptive open-text interview, Evaluator assessments and read-only LLM scores. CLAUDE_PROMPT §4.

Budgets: ≤10 distinct actions, ≤5 shown questions per action. Pending question is never regenerated.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api.common import create_attempt, default_profile
from backend.db import get_db
from backend.domain.core_flow import RubricMap, planner_state
from backend.domain.assessment import FollowupGoal, sanitize_goal
from backend.domain.topic_summary import TopicSummary, open_criteria, topic_summary
from backend.domain.candidate_level import resolve_level
from backend.domain.interview_budget import needs_min_followup, topic_open_for_question
from backend.domain.market import VacancyInput, compute_market
from backend.domain.planner import choose_next
from backend.agents.graphs import run_answer, run_ask
from backend.agents.model import get_chat_model
from backend.models import (CandidateProfile, CohortSnapshot, CoreInterview, CoreTurn, Competency,
                            CriterionAssessment, Rubric, RubricCriterion, User)
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


def criterion_scores(rows) -> dict[str, float | None]:
    """Latest revision per criterion_id (rows arrive oldest first); legacy holistic rows per current_criteria_rows."""
    return {r.criterion_id: r.score for r in current_criteria_rows(rows)}


def action_summary(rows, rubrics: RubricMap, fallback: Mapping[str, list[str]] | None = None) -> dict[str, TopicSummary]:
    """Per action M_c / E_c from criterion scores. A legacy holistic row (criterion_id == action_id) scores the action."""
    cur = current_criteria_rows(rows)
    scores = criterion_scores(rows)
    out = {}
    for a in dict.fromkeys(r.action_id for r in cur):
        seen = [(c, 1.0) for c in dict.fromkeys(r.criterion_id for r in cur if r.action_id == a)]
        # No rubric: weight 1 over fallback criteria (criteria_for) so E_c has the full denominator; else criteria seen.
        rubric = rubrics.get(a) or ([(c, 1.0) for c in fallback[a]] if fallback and a in fallback else seen)
        if a in scores and not any(c in scores for c, _ in rubric):
            rubric = [(a, 1.0)]
        out[a] = topic_summary(rubric, scores)
    return out


def _action_scores(rows) -> dict[str, float | None]:
    """Display score per action: M_c with default weights (weighted by beta when a rubric is passed via action_summary)."""
    return {a: t.m for a, t in action_summary(rows, {}).items()}


def _rows_for_user(db: Session, user: User) -> list:
    return db.scalars(select(CriterionAssessment).where(CriterionAssessment.user_id == user.id)
                      .order_by(CriterionAssessment.created_at, CriterionAssessment.revision)).all()


def latest_scores(db: Session, user: User) -> dict[str, float | None]:
    """Criterion scores (MATH_SPEC §3), across this user's interviews."""
    return criterion_scores(_rows_for_user(db, user))


def attempt_scores(db: Session, interview_id: str) -> dict[str, float | None]:
    """Criterion scores from one attempt only."""
    rows = db.scalars(select(CriterionAssessment).where(CriterionAssessment.session_id == interview_id)
                      .order_by(CriterionAssessment.created_at, CriterionAssessment.revision)).all()
    return criterion_scores(rows)


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


def rubric_map(db: Session, action_ids: Iterable[str], scores: Mapping[str, float | None] | None = None) -> RubricMap:
    """action_id -> [(criterion_id, weight)] from seeded rubrics. Actions with only a legacy holistic score keep [(a,1)]."""
    out = {}
    for a in dict.fromkeys(action_ids):
        crit = [(c.criterion_id, c.weight) for c in _seeded_criteria(db, a)]
        if crit and not (scores and a in scores and not any(c in scores for c, _ in crit)):
            out[a] = crit
    return out


def cohort_actions(revisions) -> set[str]:
    return {x["competency_id"] for r in revisions for g in r["groups"] for x in g["alternatives"]}


def criteria_for(db: Session, action_id: str) -> list[str]:
    """Criterion ids of the seeded rubric (sorted), else the action itself."""
    return [c.criterion_id for c in _seeded_criteria(db, action_id)] or [action_id]


def open_criteria_for(db: Session, action_id: str, scores: Mapping[str, float | None], sufficient: bool) -> list[str]:
    """Criteria of the action (criteria_for order) that are still UNKNOWN or WEAK."""
    return open_criteria([(c, 1.0) for c in criteria_for(db, action_id)], scores, sufficient)


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
    cscores = attempt_scores(db, iv.id)
    state, weights = planner_state(revisions, cscores, rubric_map(db, cohort_actions(revisions), cscores))
    shown: dict[str, int] = {}
    for t in turns:
        shown[t.action_id] = shown.get(t.action_id, 0) + 1
    used = set(shown)
    mass = {e.action_id: e.mass for e in compute_market([
        VacancyInput(r["id"], tuple(tuple(a["competency_id"] for a in g["alternatives"]) for g in r["groups"]))
        for r in revisions])}
    session_rows = db.scalars(select(CriterionAssessment).where(
        CriterionAssessment.session_id == iv.id).order_by(CriterionAssessment.revision)).all()
    latest_in_session = {a: t.m for a, t in action_summary(
        session_rows, rubric_map(db, {r.action_id for r in session_rows}, cscores)).items()}
    sufficient = {r.action_id: bool(r.sufficient_evidence) for r in session_rows}  # latest revision wins

    open_memo: dict[str, list[str]] = {}

    def open_ids(a: str) -> list[str]:
        if a not in open_memo:
            open_memo[a] = open_criteria_for(db, a, cscores, sufficient.get(a, False))
        return open_memo[a]

    def closed(a: str) -> bool:
        """A graded topic with no open criterion left (all CONFIRMED or DECLINED) gets no more questions."""
        return a in latest_in_session and not open_ids(a)

    def needs_second(a: str) -> bool:
        """Min two shown questions per graded topic while criteria stay open, unless the first answer was
        sufficient and >= 0.75 (or declined)."""
        return not closed(a) and needs_min_followup(shown[a], graded=a in latest_in_session,
                                                    score=latest_in_session.get(a), sufficient=sufficient.get(a, False))

    # Otherwise a started topic is re-asked only when the Evaluator found insufficient evidence (null score).
    def eligible(a: str) -> bool:
        return not (a in used and closed(a)) and topic_open_for_question(
            used=a in used, distinct_topics=len(used), shown=shown.get(a, 0),
            latest_score_is_null=a in latest_in_session and latest_in_session[a] is None)

    # A topic below its minimum continues before the planner opens anything (even if its groups closed/failed).
    followup = next((t.action_id for t in reversed(turns) if needs_second(t.action_id)), None)
    if followup is not None:
        action = followup
    else:
        available = sorted({a for alts in state.open_alternatives.values() for a in alts if eligible(a)})
        action = choose_next(state, weights, available, mass)
    if action is None:
        # Plan exhausted: the interview completes itself, so results open and answers stop.
        iv.status = "FINISHED"
        iv.version += 1
        db.commit()
        return {"turn": None, "version": iv.version, "done": True, "status": iv.status}
    label = _label(db, action)
    answered = [t for t in turns if t.action_id == action and t.answer_text]
    comp = db.get(Competency, action)
    unmet = open_ids(action)
    # The last answer's goal, re-checked against criteria still open now (the Evaluator may have just confirmed it).
    last_goal = answered[-1].eval_goal if answered else None
    goal = sanitize_goal(FollowupGoal.model_validate(last_goal), set(criteria_for(db, action)), unmet) if last_goal else None
    goal_dict = goal.model_dump() if goal else None
    result = run_ask({"action_id": action, "action_name": label, "summary": comp.summary if comp else "",
                      "unmet_criteria": unmet,
                      "previous_answers": [t.answer_text for t in answered][-3:],
                      "asked_questions": [t.question_text for t in turns if t.action_id == action],
                      "followup_goal": goal_dict,
                      "off_topic_detected": bool(answered and answered[-1].off_topic),
                      **_level_context(db, iv)}, get_chat_model())
    question, source = result.question_text, result.source
    targeted = source == "LLM_INTERVIEWER"  # a bank fallback question is not aimed at specific criteria
    turn = CoreTurn(interview_id=iv.id, sequence=len(turns) + 1, action_id=action, question_text=question,
                    question_source=source,
                    target_criteria=(goal.criterion_ids if goal else unmet) if targeted else None,
                    followup_reason=(goal.reason if goal else "OPEN_CRITERIA") if targeted else None)
    iv.version += 1
    db.add(turn)
    try:
        db.commit()
    except IntegrityError:  # a parallel request created the same sequence first: return its pending question
        db.rollback()
        winner = db.scalar(select(CoreTurn).where(CoreTurn.interview_id == iv.id, CoreTurn.answer_text.is_(None))
                           .order_by(CoreTurn.sequence))
        if winner is None:
            raise HTTPException(409, "Стан інтерв'ю змінився, оновіть сторінку")
        db.refresh(iv)
        return {"turn": _turn_dict(winner, _names(db)), "version": iv.version, "done": False}
    return {"turn": _turn_dict(turn, _names(db)), "version": iv.version, "done": False}


def _level_context(db: Session, iv: CoreInterview) -> dict:
    """Desired title / years from the attempt's profile (falls back to the user) for Interviewer question depth."""
    src = db.get(CandidateProfile, iv.profile_id) if iv.profile_id else None
    src = src or db.get(User, iv.user_id)
    years = getattr(src, "years_experience", None)
    return {"candidate_level": resolve_level(getattr(src, "target_level", None), getattr(src, "desired_title", None), years),
            "years_experience": years}


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
    prior = db.scalars(select(CriterionAssessment).where(
        CriterionAssessment.session_id == iv.id, CriterionAssessment.action_id == action_id)
        .order_by(CriterionAssessment.created_at, CriterionAssessment.revision)).all()
    open_ids = open_criteria_for(db, action_id, criterion_scores(prior), bool(prior and prior[-1].sufficient_evidence))
    result = run_answer({"action_id": action_id, "rubric_version": version, "allowed_criterion_ids": criteria,
                         "bands": criterion_bands(db, action_id), "turns": {t.id: t.answer_text for t in turns},
                         "open_criterion_ids": open_ids}, model)
    if result.status != "ACCEPTED":
        return "UNGRADED"
    goal = result.output.followup_goal  # already sanitized against allowed + open criteria by the answer graph
    turn.eval_goal = goal.model_dump() if goal and not result.off_topic else None
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
                                       evidence=[], revision=rev, sufficient_evidence=False))
        return "ACCEPTED"
    for c in result.output.criteria:
        db.add(CriterionAssessment(user_id=user.id, session_id=iv.id, action_id=action_id,
                                   criterion_id=c.criterion_id, rubric_id=rubric.id, score=c.score,
                                   reason=c.reason, evidence=[e.model_dump() for e in c.evidence], revision=rev,
                                   sufficient_evidence=result.output.sufficient_evidence))
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
    if iv.status != "ACTIVE":
        raise HTTPException(409, "Інтерв'ю не активне")
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
