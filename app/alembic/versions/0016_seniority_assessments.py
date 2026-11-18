"""New table seniority_assessments: immutable assessed level per (attempt, policy version). Additive, idempotent.

Historical finished attempts get no row here; the level API computes and stores it lazily on first read."""
import sqlalchemy as sa
from alembic import op

revision = "0016_seniority_assessments"
down_revision = "0015_vacancy_source_name"
branch_labels = None
depends_on = None

TABLE = "seniority_assessments"


def _has_table() -> bool:
    return TABLE in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if _has_table():
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("interview_id", sa.String(36), sa.ForeignKey("core_interviews.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("track", sa.String(32), nullable=True),
        sa.Column("policy_id", sa.String(64), nullable=True),
        sa.Column("policy_version", sa.String(32), nullable=True),
        sa.Column("policy_status", sa.String(32), nullable=True),
        sa.Column("assessed_level", sa.String(16), nullable=False),
        sa.Column("highest_supported_level", sa.String(16), nullable=False),
        sa.Column("assessment_status", sa.String(32), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("rubric_versions", sa.JSON(), nullable=False),
        sa.Column("desired_level", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("interview_id", "policy_version", name="uq_seniority_attempt_policy"),
    )
    for col in ("user_id", "profile_id", "interview_id"):
        op.create_index(f"ix_{TABLE}_{col}", TABLE, [col])
    # one no-policy row per attempt: NULL policy_version escapes the unique constraint above
    op.create_index("uq_seniority_attempt_no_policy", TABLE, ["interview_id"], unique=True,
                    sqlite_where=sa.text("policy_version IS NULL"), postgresql_where=sa.text("policy_version IS NULL"))


def downgrade():
    if not _has_table():
        return
    op.drop_table(TABLE)  # drops its indexes too, including ones an earlier revision of 0016 did not create
