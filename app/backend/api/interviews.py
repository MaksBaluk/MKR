"""One shared, version-guarded interview per immutable selected-vacancy snapshot."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from backend.db import get_db
from backend.models import InterviewSession, InterviewTurn, Competency, User
from backend.security import current_user
from backend.domain.adaptive import choose_topic, priorities, observed_successes, asked_by_action
from backend.domain.matching import effective_profile
from backend.providers.questions import next_question as question_from_bank
from backend.providers.llm import rephrase_bank_question, generate_interview_question, status as llm_status, LLMUnavailable
from .common import require_snapshot, require_interview
from .profile import profile_data
from backend.domain.profile_versions import create_profile_version, ensure_p1, verification_topics

router = APIRouter(prefix="/interviews", tags=["one shared adaptive interview"])


class CreateInterview(BaseModel):
    snapshot_id: str
    mode: str = "ADAPTIVE"
    question_budget: int = Field(default=8, ge=4, le=15)


class VersionGuard(BaseModel):
    state_version: int = Field(ge=0)


class AnswerInput(VersionGuard):
    turn_id: str
    option_id: str | None = None
    answer_text: str | None = Field(default=None, max_length=4000)
    idempotency_key: str = Field(min_length=8, max_length=120)

    @model_validator(mode="after")
    def requires_answer(self):
        if not self.option_id and not (self.answer_text or "").strip():
            raise ValueError("Provide an option or answer_text")
        return self


class SkipInput(VersionGuard):
    turn_id: str


def serialize_turn(t: InterviewTurn) -> dict:
    return {"id": t.id, "sequence": t.sequence, "competency_id": t.competency_id,
            "question_id": t.question_id, "question_text": t.question_text,
            "question_kind": t.question_kind, "question_options": t.question_options,
            "question_mode": t.question_mode, "question_source": t.question_source, "priority": t.priority,
            "question_format": "OPTIONAL_CHECK" if t.question_kind == "MULTIPLE_CHOICE" else "OPEN",
            "status": t.status, "answer_option": t.answer_option, "answer_text": t.answer_text,
            "assessment_status": t.assessment_status, "llm_proposal": t.llm_proposal,
            "delivered_at": t.delivered_at.isoformat() if t.delivered_at else None}


def serialize_interview(session: InterviewSession, include_turns: bool = True) -> dict:
    all_turns = sorted(session.turns, key=lambda t: t.sequence)
    passed = observed_successes(all_turns)
    profile = effective_profile(session.baseline_profile, passed)
    current = next((t for t in all_turns if t.status == "UNANSWERED"), None)
    payload = {"id": session.id, "snapshot_id": session.snapshot_id, "mode": session.mode,
               "status": session.status, "question_budget": session.question_budget,
               "used_questions": session.used_questions, "state_version": session.state_version,
               "baseline_profile": session.baseline_profile, "effective_profile": profile,
               "current_question": serialize_turn(current) if current else None,
               "created_at": session.created_at.isoformat() if session.created_at else None,
               "completed_at": session.completed_at.isoformat() if session.completed_at else None,
               "provider_mode": "LLM_WITH_CURATED_FALLBACK" if llm_status()["question_generation"] else "CURATED_QUESTION_BANK"}
    if include_turns:
        payload["turns"] = [serialize_turn(t) for t in all_turns]
    return payload


def assert_track_current(snap, user: User):
    """A running interview belongs to the track it was created for; a track change requires a new set."""
    if snap.track != user.track:
        raise HTTPException(409, detail={"code": "TRACK_CHANGED", "message": "Трек змінено після створення набору"})


def assert_version(session: InterviewSession, received: int):
    if session.state_version != received:
        raise HTTPException(409, detail={"code": "STALE_SESSION_VERSION", "current_version": session.state_version})


@router.post("", status_code=201)
def create_interview(data: CreateInterview, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if data.mode not in ("ADAPTIVE", "STATIC"):
        raise HTTPException(422, "mode must be ADAPTIVE or STATIC")
    snap = require_snapshot(db, user.id, data.snapshot_id)
    if snap.track != user.track:
        raise HTTPException(422, "Snapshot track differs from candidate profile track")
    baseline = profile_data(db, user)["levels"]
    plan = ([p["competency_id"] for p in priorities(snap.vacancy_payload, baseline)][:data.question_budget]
            if data.mode == "STATIC" else [])
    interview = InterviewSession(user_id=user.id, snapshot_id=snap.id, mode=data.mode,
                                 status="READY", question_budget=data.question_budget,
                                 baseline_profile=baseline, static_plan=plan)
    db.add(interview)
    db.flush()
    create_profile_version(db, user_id=user.id, kind="P0", interview_id=interview.id,
                           levels=baseline, provenance={k: "SELF_REPORT" for k, v in baseline.items() if v is not None})
    db.commit()
    db.refresh(interview)
    return serialize_interview(interview)


@router.get("")
def list_interviews(db: Session = Depends(get_db), user: User = Depends(current_user)):
    interviews = db.scalars(select(InterviewSession).where(InterviewSession.user_id == user.id)
                            .order_by(InterviewSession.created_at.desc())).all()
    return [serialize_interview(i, include_turns=False) for i in interviews]


@router.get("/{interview_id}")
def get_interview(interview_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return serialize_interview(require_interview(db, user.id, interview_id))


@router.post("/{interview_id}/next-question")
def deliver_question(interview_id: str, guard: VersionGuard,
                     db: Session = Depends(get_db), user: User = Depends(current_user)):
    interview = require_interview(db, user.id, interview_id, lock=True)
    assert_version(interview, guard.state_version)
    if interview.status not in ("READY",):
        raise HTTPException(409, "Interview is not ready for a new question")
    if any(t.status == "UNANSWERED" for t in interview.turns):
        raise HTTPException(409, "A question is already outstanding")
    if interview.used_questions >= interview.question_budget:
        # Ruling: no auto-completion. The last answer stays gradable; only POST /finish completes.
        return {**serialize_interview(interview), "llm_warning": None}
    snap = require_snapshot(db, user.id, interview.snapshot_id)
    assert_track_current(snap, user)
    counts = asked_by_action(interview.turns)
    topic = choose_topic(snap.vacancy_payload, interview.baseline_profile,
                         observed_successes(interview.turns), counts,
                         static_plan=interview.static_plan if interview.mode == "STATIC" else None,
                         needs_verification=verification_topics(db, interview))
    if not topic:
        return {**serialize_interview(interview), "llm_warning": None}
    action = topic["competency_id"]
    question = question_from_bank(action, counts.get(action, 0))
    if question is None:
        raise HTTPException(409, detail={"code": "QUESTION_BANK_EMPTY", "action": action})
    competency = db.get(Competency, action)
    warning = None
    text = question["text"]
    question_id = question["id"]
    question_kind = question["kind"]
    options = question["options"]
    correct_option = question["correct_option"]
    source = "CURATED_BANK"
    from backend.config import get_settings
    config = get_settings()
    generate = config.llm_question_generation and config.llm_ready and (
        config.llm_question_strategy == "dynamic" or question_kind == "FREE_TEXT"
    )
    if generate:
        previous = [{"topic": t.competency_id, "question": t.question_text[:240],
                     "answer": (t.answer_text or t.answer_option or "")[:450]}
                    for t in sorted(interview.turns, key=lambda row: row.sequence)[-4:]]
        related = []
        for vacancy in snap.vacancy_payload:
            for group in vacancy.get("groups", []):
                if any(alt["competency_id"] == action for alt in group.get("alternatives", [])):
                    related.append({"vacancy_title": vacancy["title"], "kind": group["kind"],
                                    "requirement": group.get("excerpt", "")[:240]})
        try:
            generated = generate_interview_question(
                competency_label=competency.label_uk if competency else action,
                mode=topic["mode"], baseline_level=interview.baseline_profile.get(action),
                vacancy_requirements=related[:5], recent_turns=previous,
                previous_question=question["text"],
            )
            text = generated["question"]
            question_id = f"llm-{question['id']}-{interview.used_questions+1}"
            question_kind = "FREE_TEXT"
            options = []
            correct_option = None
            source = "LLM_GENERATED"
        except LLMUnavailable:
            warning = "LLM unavailable: curated question bank used instead"
    elif config.llm_question_rephrasing and config.llm_ready:
        try:
            text = rephrase_bank_question(text, competency.label_uk if competency else action, question_kind)
            source = "LLM_REPHRASED" if text != question["text"] else "CURATED_BANK"
        except LLMUnavailable:
            warning = "LLM unavailable: original curated question used"
    turn = InterviewTurn(session_id=interview.id, sequence=interview.used_questions + 1,
                         competency_id=action, question_id=question_id, question_text=text,
                         question_kind=question_kind, question_options=options,
                         correct_option=correct_option, question_mode=topic["mode"],
                         question_source=source, priority=topic["priority"])
    interview.turns.append(turn)
    interview.used_questions += 1
    interview.state_version += 1
    interview.status = "WAITING_FOR_ANSWER"
    db.commit()
    return {**serialize_interview(interview), "llm_warning": warning}


@router.post("/{interview_id}/answers")
def answer_question(interview_id: str, data: AnswerInput,
                    db: Session = Depends(get_db), user: User = Depends(current_user)):
    interview = require_interview(db, user.id, interview_id, lock=True)
    assert_track_current(require_snapshot(db, user.id, interview.snapshot_id), user)
    turn = next((t for t in interview.turns if t.id == data.turn_id), None)
    if turn is None:
        raise HTTPException(404, "Turn not found")
    # The idempotency replay is checked BEFORE stale-version rejection.
    if turn.idempotency_key == data.idempotency_key:
        if turn.answer_option == data.option_id and (turn.answer_text or "") == (data.answer_text or ""):
            return {**serialize_interview(interview), "idempotent_replay": True}
        raise HTTPException(409, "IDEMPOTENCY_CONFLICT")
    assert_version(interview, data.state_version)
    if interview.status != "WAITING_FOR_ANSWER" or turn.status != "UNANSWERED":
        raise HTTPException(409, "No matching outstanding question")
    if turn.question_kind == "MULTIPLE_CHOICE":
        if data.option_id not in {item["id"] for item in turn.question_options}:
            raise HTTPException(422, "Choose a valid option ID")
        turn.assessment_status = ("DEMO_OBSERVED_LEVEL_1" if data.option_id == turn.correct_option
                                  else "INSUFFICIENT_EVIDENCE")
    else:
        if data.option_id is not None or not (data.answer_text or "").strip():
            raise HTTPException(422, "Open-ended question requires answer_text only")
        turn.assessment_status = "PENDING_REVIEW"
    turn.answer_option = data.option_id
    turn.answer_text = (data.answer_text or "").strip() or None
    turn.status = "ANSWERED"
    turn.idempotency_key = data.idempotency_key
    turn.answered_at = datetime.now(timezone.utc)
    interview.state_version += 1
    interview.status = "READY"
    db.commit()
    return {**serialize_interview(interview), "idempotent_replay": False}


@router.post("/{interview_id}/skip")
def skip_question(interview_id: str, data: SkipInput,
                  db: Session = Depends(get_db), user: User = Depends(current_user)):
    interview = require_interview(db, user.id, interview_id, lock=True)
    assert_version(interview, data.state_version)
    turn = next((t for t in interview.turns if t.id == data.turn_id and t.status == "UNANSWERED"), None)
    if interview.status != "WAITING_FOR_ANSWER" or not turn:
        raise HTTPException(409, "No matching unanswered question")
    turn.status = "SKIPPED"
    turn.assessment_status = "INSUFFICIENT_EVIDENCE"
    interview.status = "READY"
    interview.state_version += 1
    db.commit()
    return serialize_interview(interview)


@router.post("/{interview_id}/finish")
def finish(interview_id: str, guard: VersionGuard,
           db: Session = Depends(get_db), user: User = Depends(current_user)):
    interview = require_interview(db, user.id, interview_id, lock=True)
    assert_version(interview, guard.state_version)
    if interview.status in ("CANCELLED", "COMPLETED"):
        raise HTTPException(409, "Interview already terminated")
    for turn in interview.turns:
        if turn.status == "UNANSWERED":
            turn.status = "SKIPPED"
            turn.assessment_status = "INSUFFICIENT_EVIDENCE"
    interview.status = "COMPLETED"
    interview.completed_at = datetime.now(timezone.utc)
    interview.state_version += 1
    ensure_p1(db, interview)
    db.commit()
    return serialize_interview(interview)


@router.post("/{interview_id}/pause")
def pause(interview_id: str, guard: VersionGuard,
          db: Session = Depends(get_db), user: User = Depends(current_user)):
    interview = require_interview(db, user.id, interview_id, lock=True)
    assert_version(interview, guard.state_version)
    if interview.status not in ("READY", "WAITING_FOR_ANSWER"):
        raise HTTPException(409, "Cannot pause in this state")
    interview.status = "PAUSED"
    interview.state_version += 1
    db.commit()
    return serialize_interview(interview)


@router.post("/{interview_id}/resume")
def resume(interview_id: str, guard: VersionGuard,
           db: Session = Depends(get_db), user: User = Depends(current_user)):
    interview = require_interview(db, user.id, interview_id, lock=True)
    assert_version(interview, guard.state_version)
    if interview.status != "PAUSED":
        raise HTTPException(409, "Interview is not paused")
    interview.status = "WAITING_FOR_ANSWER" if any(t.status == "UNANSWERED" for t in interview.turns) else "READY"
    interview.state_version += 1
    db.commit()
    return serialize_interview(interview)
