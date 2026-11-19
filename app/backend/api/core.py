"""Adaptive open-text interview, Evaluator assessments and read-only LLM scores. CLAUDE_PROMPT §4.

Budgets: ≤10 distinct actions, ≤5 shown questions per action. Pending question is never regenerated.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api.common import create_attempt, default_profile
from backend.db import get_db
from backend.domain.core_flow import RubricMap, planner_state
from backend.domain.assessment import GOAL_TEXT_MAX, FollowupGoal, sanitize_goal
from backend.domain.topic_summary import (DECLINED_SCORE, TopicSummary, needs_verification, open_criteria,
                                          topic_summary)
from backend.domain.candidate_level import resolve_level
from backend.domain.difficulty import (DEFAULT_CONFIG, ControllerState, Difficulty, DifficultyDecision,
                                       initial_difficulty, market_level, next_step)
from backend.domain.interview_budget import MIN_SHOWN_QUESTIONS_PER_ACTION, topic_open_for_question
from backend.domain.market import VacancyInput, compute_market
from backend.domain.planner import choose_next
from backend.domain.level_probe import MAX_ASKS_PER_CRITERION, continuation_targets, practice_gaps, probe_order
from backend.domain.seniority import CriterionEvidence, estimate
from backend.domain.seniority_policy import PRACTICE_ACTION, SeniorityPolicy, policy_by_version, policy_for
from backend.experiments.config import ExperimentConfig, InterviewMode
from backend.experiments.planning import plan_topics, slot_targets, static_plan_json
from backend.agents.graphs import run_answer, run_ask
from backend.agents.model import get_chat_model
from backend.models import (CandidateProfile, CohortSnapshot, CoreInterview, CoreTurn, Competency,
                            CandidateSelfRating, CriterionAssessment, Rubric, RubricCriterion, User)
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


def effective_rows(rows) -> list:
    """Current assessment per (action, criterion) from the full revision history (rows arrive oldest first).

    The latest row with a score wins; a later null row (off-topic answer, criterion not covered by the new answer) never
    erases an earlier score, but every revision stays stored. If no revision ever had a score, the latest row stays."""
    best: dict[tuple[str, str], object] = {}
    for r in current_criteria_rows(rows):
        key = (r.action_id, r.criterion_id)
        if r.score is not None or key not in best or best[key].score is None:
            best[key] = r
    return list(best.values())


def criterion_scores(rows) -> dict[str, float | None]:
    """Current score per criterion_id via effective_rows (history is kept, null never overrides a score)."""
    return {r.criterion_id: r.score for r in effective_rows(rows)}


def action_summary(rows, rubrics: RubricMap) -> dict[str, TopicSummary]:
    """Per action M_c / E_c from criterion scores. A legacy holistic row (criterion_id == action_id) scores the action.
    Professional-practice rows (PRACTICE_ACTION) are not a competency: never summarised here."""
    cur = [r for r in current_criteria_rows(rows) if r.action_id != PRACTICE_ACTION]
    scores = criterion_scores(rows)
    out = {}
    for a in dict.fromkeys(r.action_id for r in cur):
        seen = [(c, 1.0) for c in dict.fromkeys(r.criterion_id for r in cur if r.action_id == a)]
        rubric = rubrics.get(a) or seen  # no rubric: weight 1 over the criteria seen
        if a in scores and not any(c in scores for c, _ in rubric):
            rubric = [(a, 1.0)]
        out[a] = topic_summary(rubric, scores)
    return out


def _turn_ids(row) -> list[str]:
    return [e["turn_id"] for e in (row.evidence or []) if isinstance(e, dict) and e.get("turn_id")]


def seniority_evidence(rows, turn_topics: Mapping[str, str]) -> dict[str, CriterionEvidence]:
    """Estimator input from ONE attempt's rows (oldest first). Null stays null (unknown), never 0.

    evidence_turns = distinct turn ids quoted by every non-null revision of the criterion (sorted).
    Topic criteria: effective_rows score. Practice criteria (graded alongside every topic) are combined order-
    independently: per source topic (the topic of the quoted turns, `turn_topics`) the latest non-null score wins, then
    the max over topics, so one topic's confirmation is never erased by a later, weaker topic. A non-null score that
    quotes no turn is kept only when no traced score exists; it then has no evidence turn and stays unresolved.
    `score` (max) is what policies v1-v3 read. Policy v4 reads `topic_scores` instead (every traced per-topic score,
    descending) and classifies their median (MATH_SPEC §3e v4, audit D-5); topic criteria additionally carry
    `declined`: the effective revision carries the validated Evaluator flag `no_experience` (legacy rows: never)."""
    turns: dict[str, set[str]] = {}
    for r in current_criteria_rows(rows):
        if r.score is not None:
            turns.setdefault(r.criterion_id, set()).update(_turn_ids(r))
    topic_rows = [r for r in effective_rows(rows) if r.action_id != PRACTICE_ACTION]
    out = {r.criterion_id: r.score for r in topic_rows}
    declined = {r.criterion_id for r in topic_rows if getattr(r, "no_experience", None) is True}
    per_topic: dict[str, dict[str | None, float]] = {}
    for r in rows:
        if r.action_id == PRACTICE_ACTION:
            per_topic.setdefault(r.criterion_id, {})
            if r.score is not None:
                topic = next((turn_topics[t] for t in _turn_ids(r) if t in turn_topics), None)
                per_topic[r.criterion_id][topic] = r.score
    spread: dict[str, tuple[float, ...]] = {}
    for cid, by_topic in per_topic.items():
        traced = [v for k, v in by_topic.items() if k is not None]
        out[cid] = max(traced) if traced else by_topic.get(None)
        spread[cid] = tuple(sorted(traced, reverse=True))
    return {cid: CriterionEvidence(cid, score, tuple(sorted(turns.get(cid, ()))) if score is not None else (),
                                   cid in declined, spread.get(cid, ()))
            for cid, score in out.items()}


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


def cohort_mass(revisions) -> dict[str, float]:
    """Market mass per action of a cohort (§1), the planner's tie-break weight."""
    return {e.action_id: e.mass for e in compute_market([
        VacancyInput(r["id"], tuple(tuple(a["competency_id"] for a in g["alternatives"]) for g in r["groups"]))
        for r in revisions])}


def static_plan_for(db: Session, revisions, cfg: ExperimentConfig, mass: Mapping[str, float] | None = None) -> dict:
    """Fixed STATIC topic plan: greedy coverage over the cohort with no scores (shared by the engine and the runner)."""
    rubrics = rubric_map(db, sorted(cohort_actions(revisions)), {})
    return static_plan_json(plan_topics(revisions, rubrics, cohort_mass(revisions) if mass is None else mass,
                                        cfg.max_topics), cfg)


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


def practice_criteria_for(db: Session, track: str | None) -> list[str]:
    """Practice criterion ids graded alongside topic answers: only for tracks with a level policy and a seeded rubric."""
    return [c.criterion_id for c in _seeded_criteria(db, PRACTICE_ACTION)] if policy_for(track) else []


def is_practice(criterion_id: str) -> bool:
    return criterion_id.startswith(f"{PRACTICE_ACTION}.")


def _interview_track(db: Session, iv: CoreInterview) -> str | None:
    prof = db.get(CandidateProfile, iv.profile_id) if iv.profile_id else None
    if prof is not None:
        return prof.track
    user = db.get(User, iv.user_id)
    return user.track if user else None


def attempt_policy(db: Session, iv: CoreInterview) -> SeniorityPolicy | None:
    """The policy an attempt is assessed under: the version captured when it started (migration 0017), else (attempts
    started before 0017) the track's current policy. A start version that is no longer known falls back the same way."""
    if iv.start_policy_version is not None:
        started = policy_by_version(iv.start_policy_id, iv.start_policy_version)
        if started is not None:
            return started
    return policy_for(_interview_track(db, iv))


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


def _profile_ratings(db: Session, iv: CoreInterview, user: User) -> dict[str, float | None]:
    """Self-ratings of the attempt's own profile only (legacy attempts without profile: user's default profile)."""
    if iv.profile_id is None:
        from backend.api.profile import latest_self_ratings
        return latest_self_ratings(db, user)
    return profile_self_ratings(db, iv.profile_id)


def _mode_config(iv: CoreInterview) -> ExperimentConfig:
    """Server-side experiment config of the attempt; NULL (product and legacy attempts) = adaptive defaults."""
    return ExperimentConfig.from_json(iv.mode_config) if iv.mode_config else ExperimentConfig(InterviewMode.ADAPTIVE_INTERVIEW)


def profile_self_ratings(db: Session, profile_id: str) -> dict[str, float | None]:
    """Latest self-rating per action of one profile (revisions oldest first, last wins)."""
    rows = db.scalars(select(CandidateSelfRating).where(CandidateSelfRating.profile_id == profile_id)
                      .order_by(CandidateSelfRating.revision)).all()
    return {r.action_id: r.value for r in rows}


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
    cfg = _mode_config(iv)
    snap = db.get(CohortSnapshot, iv.cohort_id)
    revisions = _revisions(snap)
    cscores = attempt_scores(db, iv.id)
    session_rows = db.scalars(select(CriterionAssessment).where(
        CriterionAssessment.session_id == iv.id).order_by(CriterionAssessment.revision)).all()
    summaries = action_summary(session_rows, rubric_map(db, {r.action_id for r in session_rows}, cscores))
    own = _profile_ratings(db, iv, user)
    state, weights = planner_state(revisions, cscores, rubric_map(db, cohort_actions(revisions), cscores),
                                   frozenset(a for a in cohort_actions(revisions)
                                             if needs_verification(own.get(a), summaries.get(a))))
    shown: dict[str, int] = {}
    for t in turns:
        shown[t.action_id] = shown.get(t.action_id, 0) + 1
    used = set(shown)
    mass = cohort_mass(revisions)
    if not cfg.adaptive_topics and iv.static_plan is None:  # fixed once, before any answer; never rebuilt
        iv.static_plan = static_plan_for(db, revisions, cfg, mass)
    latest_in_session = {a: t.m for a, t in summaries.items()}
    sufficient = {r.action_id: bool(r.sufficient_evidence) for r in session_rows}  # latest revision wins

    open_memo: dict[str, list[str]] = {}

    def open_ids(a: str) -> list[str]:
        if a not in open_memo:
            open_memo[a] = open_criteria_for(db, a, cscores, sufficient.get(a, False))
        return open_memo[a]

    goal_memo: dict[str, FollowupGoal | None] = {}

    def goal_for(a: str) -> FollowupGoal | None:
        """Goal of the topic's last answered turn, re-checked against criteria open now; malformed stored goal => None."""
        if a not in goal_memo:
            last = next((t for t in reversed(turns) if t.action_id == a and t.answer_text), None)
            goal = None
            if last is not None and last.eval_goal:
                try:
                    goal = sanitize_goal(FollowupGoal.model_validate(last.eval_goal), set(criteria_for(db, a)), open_ids(a))
                except ValidationError:
                    goal = None
            # D-2: a goal that keeps re-asking criteria already in focus of MAX_ASKS questions yields to Python's level
            # continuation when unresolved level-critical criteria remain (no level policy: never applies).
            if goal is not None and level_targets(a) and all(asked(a).get(c, 0) >= MAX_ASKS_PER_CRITERION
                                                             for c in goal.criterion_ids):
                goal = None
            goal_memo[a] = goal
        return goal_memo[a]

    # Level probe estimate. Without a policy it is None; without a capability policy (v4) continuation_targets is
    # empty, so the level rules below are inert there (marketing, design, attempts started under v1-v3).
    policy = attempt_policy(db, iv) if cfg.adaptive_followup else None
    try:
        probe = (estimate(policy, seniority_evidence(session_rows, {t.id: t.action_id for t in turns}))
                 if policy else None)
    except ValueError:  # a malformed legacy score must never block the next question: probe off, order unchanged
        probe = None
    focus = DEFAULT_CONFIG.focus

    def asked(a: str) -> dict[str, int]:
        """How many graded questions of topic `a` had each criterion in focus (the first targeted ones)."""
        out: dict[str, int] = {}
        for t in turns:
            if t.action_id == a and t.answer_text and t.target_criteria:
                for c in t.target_criteria[:focus]:
                    out[c] = out.get(c, 0) + 1
        return out

    def weak_answers(a: str) -> bool:
        """The topic's answers so far are weak or declined: M_c or the last question's focus mean below the down score,
        or a declaration (validated no_experience flag, or a sufficient ~0 score). Then no level continuation."""
        m = latest_in_session.get(a)
        if m is None or m < DEFAULT_CONFIG.down_score:
            return True
        crit = set(criteria_for(db, a))
        latest = {r.criterion_id: r for r in session_rows if r.criterion_id in crit}  # latest revision wins
        if any(r.no_experience or (r.score is not None and r.score <= DECLINED_SCORE and r.sufficient_evidence)
               for r in latest.values()):
            return True
        last = next((t for t in reversed(turns) if t.action_id == a and t.answer_text), None)
        known = [x for c in (last.target_criteria or [])[:focus] if (x := cscores.get(c)) is not None] if last else []
        return bool(known) and sum(known) / len(known) < DEFAULT_CONFIG.down_score

    level_memo: dict[str, list[str]] = {}

    def level_targets(a: str) -> list[str]:
        """Python-owned continuation (D-2): unresolved level-critical criteria of the topic, unless answers are weak."""
        if a not in level_memo:
            level_memo[a] = ([] if probe is None or a not in latest_in_session or weak_answers(a) else
                             [c for c in continuation_targets(policy, probe, criteria_for(db, a), cscores, asked(a))
                              if c in set(open_ids(a))])
        return level_memo[a]

    def level_open(a: str) -> bool:
        """Only the topic just answered is kept open by the level rule; older topics behave as before."""
        return bool(turns) and turns[-1].action_id == a and bool(level_targets(a))

    level_ctx = _level_context(db, iv)
    start_level, start_reason = initial_difficulty(level_ctx["candidate_level"],
                                                   market_level([r.get("years_min") for r in revisions]))
    decision_memo: dict[str, tuple[ControllerState, DifficultyDecision]] = {}

    def opening() -> tuple[Difficulty, str]:
        """Start level of a new topic. Controller v2 (D-3): the level the previous topic reached (its decision's
        next_level, bounded to BASIC..ADVANCED by the controller); the desired-level hypothesis only for the first."""
        if not turns:
            return start_level, start_reason
        prev = decision(turns[-1].action_id)[1]
        return prev.next_level, f"CARRY:{prev.reason}"

    def decision(a: str) -> tuple[ControllerState, DifficultyDecision]:
        """Controller state replayed from the topic's stored turns, then the decision for its next question.
        A topic without turns starts at opening(); a legacy last turn (NULL difficulty) restarts at the initial level."""
        if a not in decision_memo:
            mine = [t for t in turns if t.action_id == a]
            history = tuple(Difficulty(t.difficulty) for t in mine if t.difficulty in Difficulty.__members__)
            if not mine:
                lvl, why = opening()
                st = ControllerState(lvl, 0, ())
                decision_memo[a] = st, DifficultyDecision(lvl, why, "CONTINUE", tuple(open_ids(a)))
            else:
                last = mine[-1]
                legacy = last.difficulty not in Difficulty.__members__
                st = ControllerState(start_level if legacy else Difficulty(last.difficulty), len(mine), history)
                d = next_step(st, DEFAULT_CONFIG, targeted=last.target_criteria or [], scores=cscores,
                              topic_score=latest_in_session.get(a), sufficient=sufficient.get(a, False),
                              open_criteria=open_ids(a), goal_open=goal_for(a) is not None, level_open=level_open(a))
                if legacy:
                    d = DifficultyDecision(start_level, "LEGACY_RESTART", d.action, d.target_criteria)
                decision_memo[a] = st, d
        return decision_memo[a]

    def closed(a: str) -> bool:
        """A graded topic the controller closes (no open criterion, question cap, or enough evidence) gets no more
        questions. Ungraded topics (no accepted assessment) are never continued: see eligible()."""
        return a in latest_in_session and decision(a)[1].action == "CLOSE"

    def needs_second(a: str) -> bool:
        """Min two shown questions per graded topic: the controller keeps it open (needs_min_followup) below two."""
        return (a in latest_in_session and shown[a] < min(MIN_SHOWN_QUESTIONS_PER_ACTION, cfg.max_per_topic)
                and not closed(a))

    # Otherwise a started topic is re-asked only when the Evaluator found insufficient evidence (null score) or its
    # last answer left a validated goal on a still-open criterion; the 5-question and 10-topic caps still apply.
    def eligible(a: str) -> bool:
        if not cfg.adaptive_followup:  # static slots: a started topic continues only through its fixed slots
            return a not in used and len(used) < cfg.max_topics
        return not (a in used and closed(a)) and topic_open_for_question(
            used=a in used, distinct_topics=len(used), shown=shown.get(a, 0),
            latest_score_is_null=a in latest_in_session and latest_in_session[a] is None,
            goal_open=a in used and (goal_for(a) is not None or level_open(a)), max_topics=cfg.max_topics,
            max_per_topic=cfg.max_per_topic)

    # A topic below its minimum continues before the planner opens anything (even if its groups closed/failed);
    # so does the topic just answered while its goal-driven follow-up is still eligible.
    # Static slots: the last started topic gets exactly k questions whatever its scores (no goal, no early close).
    k = cfg.static_questions_per_topic
    if not cfg.adaptive_followup:
        followup = turns[-1].action_id if turns and shown[turns[-1].action_id] < k else None
    else:
        followup = next((t.action_id for t in reversed(turns) if needs_second(t.action_id)), None)
        last_topic = turns[-1].action_id if turns else None
        if followup is None and last_topic and (goal_for(last_topic) is not None or level_open(last_topic)) \
                and eligible(last_topic):
            followup = last_topic  # validated LLM goal, or Python's level continuation (D-2), within the caps
    if cfg.total_budget is not None and len(turns) >= cfg.total_budget:
        action = None  # experiment budget spent: completes exactly like plan exhaustion; unasked criteria stay null
    elif followup is not None:
        action = followup
    elif not cfg.adaptive_topics:  # fixed topic order stored on the attempt; the planner is not called
        action = next((a for a in iv.static_plan["topics"] if eligible(a)), None)
    else:
        available = sorted({a for alts in state.open_alternatives.values() for a in alts if eligible(a)})
        action = choose_next(state, weights, available, mass)
    if action is None:
        # Plan exhausted: the interview completes itself, so results open and answers stop.
        iv.status = "FINISHED"
        iv.version += 1
        _store_level(db, iv)
        db.commit()
        return {"turn": None, "version": iv.version, "done": True, "status": iv.status}
    label = _label(db, action)
    answered = [t for t in turns if t.action_id == action and t.answer_text]
    comp = db.get(Competency, action)
    gaps: list[str] = []
    if cfg.adaptive_followup:
        # Level probe: reorders this topic's open criteria (unresolved level-critical ones first, D-2) and hints
        # practice gaps (D-6). No policy: order unchanged, no hints.
        goal = goal_for(action)  # the Evaluator may have just confirmed the criterion it named: re-checked in goal_for
        lead = (continuation_targets(policy, probe, criteria_for(db, action), cscores, asked(action))
                if probe is not None and not (action in latest_in_session and weak_answers(action)) else [])
        # a validated follow-up goal wins: practice gaps are hinted only when no goal drives the question
        unmet, gaps = probe_order(open_ids(action), policy, probe, lead), [] if goal else practice_gaps(policy, probe)
    else:  # slot i of k targets a fixed round-robin share of the rubric (all criteria if the share is empty)
        crit = criteria_for(db, action)
        unmet, goal = list(slot_targets(crit, k, shown.get(action, 0)) or crit), None
    goal_dict = goal.model_dump() if goal else None
    before, chosen = decision(action)
    # the controller state advances for bank fallback questions too; fixed difficulty takes no controller step
    level, level_reason = ((chosen.next_level, chosen.reason) if cfg.adaptive_difficulty
                           else (start_level, f"FIXED:{start_reason}"))
    result = run_ask({"action_id": action, "action_name": label, "summary": comp.summary if comp else "",
                      "unmet_criteria": unmet,
                      "previous_answers": [t.answer_text for t in answered][-3:],
                      "asked_questions": [t.question_text for t in turns if t.action_id == action],
                      "followup_goal": goal_dict,
                      "off_topic_detected": bool(answered and answered[-1].off_topic),
                      "difficulty": level.value, "practice_gaps": gaps, **level_ctx}, get_chat_model())
    question, source = result.question_text, result.source
    targeted = source == "LLM_INTERVIEWER"  # a bank fallback question is not aimed at specific criteria
    after = ControllerState(level, before.shown + 1, before.history + (level,))
    turn = CoreTurn(interview_id=iv.id, sequence=len(turns) + 1, action_id=action, question_text=question,
                    question_source=source,
                    target_criteria=(goal.criterion_ids if goal else unmet) if targeted else None,
                    followup_reason=((goal.reason[:GOAL_TEXT_MAX] if goal else
                                      "OPEN_CRITERIA" if cfg.adaptive_followup else "STATIC_SLOT") if targeted
                                     else "BANK_FALLBACK"),
                    difficulty=level.value,
                    difficulty_reason=(level_reason if targeted else f"FALLBACK:{level_reason}")[:64],
                    controller_before=_controller_json(before), controller_after=_controller_json(after))
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


def _store_level(db: Session, iv: CoreInterview) -> None:
    """Immutable assessed-level row for the attempt that just finished (never an input of the ranking)."""
    from backend.api.level import finalize_on_finish  # level builds on this module's helpers
    finalize_on_finish(db, iv)


def _controller_json(st: ControllerState) -> dict:
    return {"level": st.level.value, "shown": st.shown, "history": [d.value for d in st.history],
            "version": DEFAULT_CONFIG.version}


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
    practice_ids = practice_criteria_for(db, _interview_track(db, iv))
    result = run_answer({"action_id": action_id, "rubric_version": version, "allowed_criterion_ids": criteria,
                         "bands": criterion_bands(db, action_id), "turns": {t.id: t.answer_text for t in turns},
                         "open_criterion_ids": open_ids,
                         "turn_meta": {t.id: {"target_criteria": t.target_criteria} for t in turns},
                         "allowed_practice_ids": practice_ids,
                         "practice_bands": criterion_bands(db, PRACTICE_ACTION) if practice_ids else None}, model)
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
    _store_practice(db, user, iv, result.output.practice)  # already nulled by the answer graph when off-topic
    if result.off_topic:  # recorded as a null revision (history); effective_rows keeps earlier scores intact
        turn.off_topic = True
        inherited = bool(prior and prior[-1].sufficient_evidence)
        for cid in criteria:
            db.add(CriterionAssessment(user_id=user.id, session_id=iv.id, action_id=action_id, criterion_id=cid,
                                       rubric_id=rubric.id, score=None, reason="Відповідь поза темою співбесіди.",
                                       evidence=[], revision=rev, sufficient_evidence=inherited))
        return "ACCEPTED"
    for c in result.output.criteria:
        db.add(CriterionAssessment(user_id=user.id, session_id=iv.id, action_id=action_id,
                                   criterion_id=c.criterion_id, rubric_id=rubric.id, score=c.score,
                                   reason=c.reason, evidence=[e.model_dump() for e in c.evidence], revision=rev,
                                   sufficient_evidence=result.output.sufficient_evidence,
                                   no_experience=c.no_experience))
    return "ACCEPTED"


def _store_practice(db: Session, user: User, iv: CoreInterview, practice) -> None:
    """One practice revision per Evaluator call under PRACTICE_ACTION with its own revision counter, so it never mixes
    with a topic's M_c/E_c; a null item is history only (effective_rows keeps an earlier score)."""
    rubric = _seeded_rubric(db, PRACTICE_ACTION) if practice else None
    if rubric is None:
        return
    rev = (db.scalar(select(func.max(CriterionAssessment.revision)).where(
        CriterionAssessment.session_id == iv.id, CriterionAssessment.action_id == PRACTICE_ACTION)) or 0) + 1
    for c in practice:
        db.add(CriterionAssessment(user_id=user.id, session_id=iv.id, action_id=PRACTICE_ACTION,
                                   criterion_id=c.criterion_id, rubric_id=rubric.id, score=c.score, reason=c.reason,
                                   evidence=[e.model_dump() for e in c.evidence], revision=rev,
                                   sufficient_evidence=None))


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
    if target == "FINISHED":
        _store_level(db, iv)
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
