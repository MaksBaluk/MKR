"""Relational entities. Immutable vacancy snapshots store revision-safe JSON copies."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, false, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


def uid() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    track: Mapped[str] = mapped_column(String(32), default="python", nullable=False)
    desired_title: Mapped[str] = mapped_column(String(160), default="")
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CandidateProfile(Base):
    """A candidate's named profile (track, target title, experience). Interview attempts belong to a profile."""
    __tablename__ = "candidate_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    track: Mapped[str | None] = mapped_column(String(32), nullable=True)  # chosen by the candidate, no default
    name: Mapped[str] = mapped_column(String(120))
    desired_title: Mapped[str] = mapped_column(String(160), default="")
    target_level: Mapped[str | None] = mapped_column(String(16), nullable=True)  # junior|middle|senior|lead
    work_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)  # remote|hybrid|office|any
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str] = mapped_column(String(120), default="")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Competency(Base):
    __tablename__ = "competencies"
    id: Mapped[str] = mapped_column(String(90), primary_key=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    label_uk: Mapped[str] = mapped_column(String(120), nullable=False)
    track: Mapped[str] = mapped_column(String(32), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    catalog_version: Mapped[str] = mapped_column(String(40), default="local-curated-v1")


class Vacancy(Base):
    __tablename__ = "vacancies"
    id: Mapped[str] = mapped_column(String(90), primary_key=True)
    track: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    company: Mapped[str] = mapped_column(String(160), nullable=False)
    seniority: Mapped[str] = mapped_column(String(30), index=True)
    years_min: Mapped[int] = mapped_column(Integer)
    years_max: Mapped[int | None] = mapped_column(Integer)
    location: Mapped[str] = mapped_column(String(90))
    work_mode: Mapped[str] = mapped_column(String(24))
    employment: Mapped[str] = mapped_column(String(70), default="Full-time")
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(6), default="USD")
    summary: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    responsibilities: Mapped[list] = mapped_column(JSON, default=list)
    benefits: Mapped[list] = mapped_column(JSON, default=list)
    stack: Mapped[list] = mapped_column(JSON, default=list)
    source_type: Mapped[str] = mapped_column(String(30), default="DEMO_CURATED")
    source_url: Mapped[str | None] = mapped_column(String(600), nullable=True)
    fixture_version: Mapped[str] = mapped_column(String(32), default="fixtures-v1")
    # provenance of REAL_IMPORTED rows (NULL for fixtures): when fetched, when posted, importer + level-rule version
    # display source of fixture vacancies: owner statement at catalog level, not a per-posting provenance (see vacancy_sources.json)
    source_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    retrieved_at: Mapped[str | None] = mapped_column(String(10), nullable=True)
    date_posted: Mapped[str | None] = mapped_column(String(10), nullable=True)
    import_version: Mapped[str | None] = mapped_column(String(60), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    groups: Mapped[list["RequirementGroup"]] = relationship(
        back_populates="vacancy", cascade="all,delete-orphan", order_by="RequirementGroup.sort_order"
    )


class RequirementGroup(Base):
    __tablename__ = "requirement_groups"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    vacancy_id: Mapped[str] = mapped_column(ForeignKey("vacancies.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)  # MANDATORY | DESIRED
    label: Mapped[str] = mapped_column(String(240))
    excerpt: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    vacancy: Mapped[Vacancy] = relationship(back_populates="groups")
    alternatives: Mapped[list["RequirementAlternative"]] = relationship(
        back_populates="group", cascade="all,delete-orphan", order_by="RequirementAlternative.id"
    )


class RequirementAlternative(Base):
    __tablename__ = "requirement_alternatives"
    id: Mapped[str] = mapped_column(String(150), primary_key=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("requirement_groups.id", ondelete="CASCADE"), index=True)
    competency_id: Mapped[str] = mapped_column(ForeignKey("competencies.id"), index=True)
    required_level: Mapped[int] = mapped_column(Integer)
    normalization_status: Mapped[str] = mapped_column(String(25), default="ACCEPTED_CURATED")
    # D_vga: rubric criteria this requirement needs (None = legacy row, whole rubric). tau: pass threshold with its source.
    criterion_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    criteria_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tau: Mapped[float | None] = mapped_column(Float, nullable=True)
    tau_source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    group: Mapped[RequirementGroup] = relationship(back_populates="alternatives")


class CandidateSkill(Base):
    __tablename__ = "candidate_skills"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    competency_id: Mapped[str] = mapped_column(ForeignKey("competencies.id"), primary_key=True)
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Snapshot(Base):
    __tablename__ = "snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    track: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20), default="FROZEN")
    frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    vacancy_payload: Mapped[list] = mapped_column(JSON, nullable=False)
    cohort_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class InterviewSession(Base):
    __tablename__ = "interview_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(12), default="ADAPTIVE")
    status: Mapped[str] = mapped_column(String(30), default="READY")
    question_budget: Mapped[int] = mapped_column(Integer, default=8)
    used_questions: Mapped[int] = mapped_column(Integer, default=0)
    state_version: Mapped[int] = mapped_column(Integer, default=0)
    baseline_profile: Mapped[dict] = mapped_column(JSON, nullable=False)
    static_plan: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    turns: Mapped[list["InterviewTurn"]] = relationship(
        back_populates="session", cascade="all,delete-orphan", order_by="InterviewTurn.sequence"
    )


class InterviewTurn(Base):
    __tablename__ = "interview_turns"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    competency_id: Mapped[str] = mapped_column(ForeignKey("competencies.id"))
    question_id: Mapped[str] = mapped_column(String(120))
    question_text: Mapped[str] = mapped_column(Text)
    question_kind: Mapped[str] = mapped_column(String(22))
    question_options: Mapped[list] = mapped_column(JSON, default=list)
    correct_option: Mapped[str | None] = mapped_column(String(12), nullable=True)
    question_mode: Mapped[str] = mapped_column(String(16), default="DISCOVER")
    question_source: Mapped[str] = mapped_column(String(18), default="CURATED_BANK")
    priority: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="UNANSWERED")
    answer_option: Mapped[str | None] = mapped_column(String(12), nullable=True)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    assessment_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    llm_proposal: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session: Mapped[InterviewSession] = relationship(back_populates="turns")
    __table_args__ = (UniqueConstraint("session_id", "sequence"),)


class MatchRun(Base):
    __tablename__ = "match_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"), index=True)
    interview_id: Mapped[str | None] = mapped_column(ForeignKey("interview_sessions.id", ondelete="SET NULL"), nullable=True)
    matcher_version: Mapped[str] = mapped_column(String(32), default="matcher-v1")
    profile_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    results_payload: Mapped[list] = mapped_column(JSON, nullable=False)
    profile_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("profile_versions.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProfileVersion(Base):
    """Immutable P0 (baseline) / P1 (post-interview) effective profile with provenance."""
    __tablename__ = "profile_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(4), nullable=False)  # P0 | P1
    interview_id: Mapped[str | None] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=True, index=True)
    levels: Mapped[dict] = mapped_column(JSON, nullable=False)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False)
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("user_id", "interview_id", "kind", name="uq_profile_version_kind"),)


class EvidenceItem(Base):
    """One graded answer. Only CONFIRMED items may change effective levels."""
    __tablename__ = "evidence_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    interview_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True)
    turn_id: Mapped[str] = mapped_column(ForeignKey("interview_turns.id", ondelete="CASCADE"), unique=True)
    competency_id: Mapped[str] = mapped_column(ForeignKey("competencies.id"))
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provenance: Mapped[str] = mapped_column(String(20), nullable=False)  # LLM_PROPOSAL | HUMAN_REVIEW | OBJECTIVE_TASK
    status: Mapped[str] = mapped_column(String(12), nullable=False)  # PROPOSED | CONFIRMED | REJECTED
    rubric_version: Mapped[str] = mapped_column(String(32), default="rubric-v1")
    excerpt: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String(8), default="LOW")
    uncertainty: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


Index("ix_vacancy_track_active", Vacancy.track, Vacancy.is_active)


class CandidateSelfRating(Base):
    """Editable self-rating per professional action. value NULL means unknown; 0 is a real rating."""
    __tablename__ = "candidate_self_ratings"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    action_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=True, index=True)
    __table_args__ = (UniqueConstraint("profile_id", "action_id", "revision", name="uq_self_rating_profile_action_rev"),)


class Rubric(Base):
    __tablename__ = "rubrics"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    action_id: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # CURATED | LLM_PROPOSED | REVIEWED
    __table_args__ = (UniqueConstraint("action_id", "version", name="uq_rubric_action_version"),)


class RubricCriterion(Base):
    __tablename__ = "rubric_criteria"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    rubric_id: Mapped[str] = mapped_column(ForeignKey("rubrics.id", ondelete="CASCADE"), index=True)
    criterion_id: Mapped[str] = mapped_column(String(120), nullable=False)
    weight: Mapped[float] = mapped_column(nullable=False, default=1.0)
    anchors: Mapped[dict] = mapped_column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint("rubric_id", "criterion_id", name="uq_rubric_criterion"),)


class CriterionAssessment(Base):
    """Append-only Evaluator revision for one action series. score NULL means insufficient evidence."""
    __tablename__ = "criterion_assessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("core_interviews.id", ondelete="CASCADE"), index=True)
    action_id: Mapped[str] = mapped_column(String(120), nullable=False)
    criterion_id: Mapped[str] = mapped_column(String(120), nullable=False)
    rubric_id: Mapped[str] = mapped_column(ForeignKey("rubrics.id"), nullable=False)
    score: Mapped[float | None] = mapped_column(nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    sufficient_evidence: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # NULL = unknown (legacy)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint("session_id", "action_id", "criterion_id", "revision", name="uq_assessment_revision"),
    )


class CohortSnapshot(Base):
    """Frozen cohort: ordered vacancy IDs, requirement revisions, policy and SHA-256."""
    __tablename__ = "cohort_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    vacancy_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    requirement_revisions: Mapped[dict] = mapped_column(JSON, nullable=False)
    policy_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CoreInterview(Base):
    """One adaptive interview over a frozen cohort. `version` guards concurrent writes."""
    __tablename__ = "core_interviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    cohort_id: Mapped[str] = mapped_column(ForeignKey("cohort_snapshots.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")  # ACTIVE | PAUSED | FINISHED
    version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=True, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    # Experiment-only, set server-side by the runner: ExperimentConfig (mode + ablation flags) and the fixed STATIC topic plan.
    # NULL for product interviews (= fully adaptive).
    mode_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    static_plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    __table_args__ = (UniqueConstraint("profile_id", "attempt_no", name="uq_attempt_profile_no"),)


class CoreTurn(Base):
    __tablename__ = "core_turns"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    interview_id: Mapped[str] = mapped_column(ForeignKey("core_interviews.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    action_id: Mapped[str] = mapped_column(String(120), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_source: Mapped[str] = mapped_column(String(24), nullable=False)  # LLM_INTERVIEWER | FALLBACK_UNGRADED
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    off_topic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    # Criteria this question is meant to test, why (Evaluator goal reason or OPEN_CRITERIA); NULL for bank fallback.
    target_criteria: Mapped[list | None] = mapped_column(JSON, nullable=True)
    followup_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Validated Evaluator follow-up goal produced after this turn's answer; NULL when none or ungraded.
    eval_goal: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Question difficulty level + why, and DifficultyController state before/after; internal, never candidate-facing.
    difficulty: Mapped[str | None] = mapped_column(String(16), nullable=True)
    difficulty_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    controller_before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    controller_after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("interview_id", "sequence", name="uq_core_turn_sequence"),
                      UniqueConstraint("interview_id", "idempotency_key", name="uq_core_turn_idem"))


class SeniorityAssessment(Base):
    """Assessed level of one finished attempt under one level-policy version. Immutable: written once, never updated.
    A new policy version adds a row; it never rewrites an earlier one. Never an input of the vacancy ranking."""
    __tablename__ = "seniority_assessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=True, index=True)
    interview_id: Mapped[str] = mapped_column(ForeignKey("core_interviews.id", ondelete="CASCADE"), index=True)
    track: Mapped[str | None] = mapped_column(String(32), nullable=True)
    policy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # NULL: no level policy for the track
    policy_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    policy_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    assessed_level: Mapped[str] = mapped_column(String(16), nullable=False)
    highest_supported_level: Mapped[str] = mapped_column(String(16), nullable=False)
    assessment_status: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)  # result_to_json(SeniorityResult)
    rubric_versions: Mapped[dict] = mapped_column(JSON, nullable=False)  # {action_id: rubric version} of the evidence
    desired_level: Mapped[str | None] = mapped_column(String(16), nullable=True)  # display copy only, never an input
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    __table_args__ = (UniqueConstraint("interview_id", "policy_version", name="uq_seniority_attempt_policy"),)


class ExperimentRun(Base):
    """One reproducible experiment run. No foreign keys: records must survive cohort/interview cleanup.
    `config` is ExperimentConfig.to_json(); older rows (before 0012) also hold `answer_source` there."""
    __tablename__ = "experiment_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    experiment_id: Mapped[str] = mapped_column(String(64), index=True)
    candidate_id: Mapped[str] = mapped_column(String(120))
    mode: Mapped[str] = mapped_column(String(24))
    config: Mapped[dict] = mapped_column(JSON)
    cohort_id: Mapped[str] = mapped_column(String(36))
    cohort_sha256: Mapped[str] = mapped_column(String(64))
    profile_snapshot: Mapped[dict] = mapped_column(JSON)
    rubric_versions: Mapped[dict] = mapped_column(JSON)
    prompt_version: Mapped[str] = mapped_column(String(64))
    model_info: Mapped[dict] = mapped_column(JSON)
    algorithm_version: Mapped[str] = mapped_column(String(64))
    interview_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    qa: Mapped[list] = mapped_column(JSON)
    assessments: Mapped[list] = mapped_column(JSON)
    ranking: Mapped[list] = mapped_column(JSON)
    timings: Mapped[dict] = mapped_column(JSON)
    errors: Mapped[dict] = mapped_column(JSON)
    relevant_criteria: Mapped[list | None] = mapped_column(JSON, nullable=True)
    answer_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
