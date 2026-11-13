"""Core loop tables: self-ratings, rubrics, criterion assessments, cohort snapshots (additive only)."""
import sqlalchemy as sa
from alembic import op

revision = "0003_core_loop"
down_revision = "0002_discovery_evidence"
branch_labels = None
depends_on = None

NEW_TABLES = ["candidate_self_ratings", "rubrics", "rubric_criteria", "criterion_assessments", "cohort_snapshots", "core_interviews", "core_turns"]


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    _core_tables()  # core_interviews must exist before criterion_assessments references it
    existing = _tables()
    if "candidate_self_ratings" not in existing:
        op.create_table(
            "candidate_self_ratings",
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("action_id", sa.String(120), primary_key=True),
            sa.Column("revision", sa.Integer(), primary_key=True),
            sa.Column("value", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "rubrics" not in existing:
        op.create_table(
            "rubrics",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("action_id", sa.String(120), nullable=False, index=True),
            sa.Column("version", sa.String(32), nullable=False),
            sa.Column("source", sa.String(16), nullable=False),
            sa.UniqueConstraint("action_id", "version", name="uq_rubric_action_version"),
        )
    if "rubric_criteria" not in existing:
        op.create_table(
            "rubric_criteria",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("rubric_id", sa.String(36), sa.ForeignKey("rubrics.id", ondelete="CASCADE"), index=True),
            sa.Column("criterion_id", sa.String(120), nullable=False),
            sa.Column("weight", sa.Float(), nullable=False),
            sa.Column("anchors", sa.JSON(), nullable=False),
            sa.UniqueConstraint("rubric_id", "criterion_id", name="uq_rubric_criterion"),
        )
    if "criterion_assessments" not in existing:
        op.create_table(
            "criterion_assessments",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
            sa.Column("session_id", sa.String(36), sa.ForeignKey("core_interviews.id", ondelete="CASCADE"),
                      index=True),
            sa.Column("action_id", sa.String(120), nullable=False),
            sa.Column("criterion_id", sa.String(120), nullable=False),
            sa.Column("rubric_id", sa.String(36), sa.ForeignKey("rubrics.id"), nullable=False),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("evidence", sa.JSON(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("session_id", "action_id", "criterion_id", "revision", name="uq_assessment_revision"),
        )
    if "cohort_snapshots" not in existing:
        op.create_table(
            "cohort_snapshots",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
            sa.Column("vacancy_ids", sa.JSON(), nullable=False),
            sa.Column("requirement_revisions", sa.JSON(), nullable=False),
            sa.Column("policy_id", sa.String(64), nullable=False),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade():
    existing = _tables()
    for name in reversed(NEW_TABLES):
        if name in existing:
            op.drop_table(name)


def _core_tables():
    existing = _tables()
    if "core_interviews" not in existing:
        op.create_table(
            "core_interviews",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
            sa.Column("cohort_id", sa.String(36), sa.ForeignKey("cohort_snapshots.id", ondelete="CASCADE"), index=True),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "core_turns" not in existing:
        op.create_table(
            "core_turns",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("interview_id", sa.String(36), sa.ForeignKey("core_interviews.id", ondelete="CASCADE"), index=True),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("action_id", sa.String(120), nullable=False),
            sa.Column("question_text", sa.Text(), nullable=False),
            sa.Column("question_source", sa.String(24), nullable=False),
            sa.Column("answer_text", sa.Text(), nullable=True),
            sa.Column("idempotency_key", sa.String(120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("interview_id", "sequence", name="uq_core_turn_sequence"),
            sa.UniqueConstraint("interview_id", "idempotency_key", name="uq_core_turn_idem"),
        )
