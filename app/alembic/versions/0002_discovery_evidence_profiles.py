"""Discovery cohort policy, P0/P1 profile versions and graded evidence (additive only)."""
import sqlalchemy as sa
from alembic import op

# Ruling: 0001 builds the schema from the CURRENT models, so fresh databases already have
# these objects. Every step checks first, so old databases upgrade and fresh ones are a no-op.

revision = "0002_discovery_evidence"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _columns(table):
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    if "cohort_policy" not in _columns("snapshots"):
        op.add_column("snapshots", sa.Column("cohort_policy", sa.JSON(), nullable=True))
    if "profile_versions" not in _tables():
        _create_profile_versions()
    if "evidence_items" not in _tables():
        _create_evidence_items()
    if "profile_version_id" not in _columns("match_runs"):
        with op.batch_alter_table("match_runs") as batch:
            batch.add_column(sa.Column("profile_version_id", sa.String(36),
                                       sa.ForeignKey("profile_versions.id", ondelete="SET NULL"), nullable=True))


def _create_profile_versions():
    op.create_table(
        "profile_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kind", sa.String(4), nullable=False),
        sa.Column("interview_id", sa.String(36), sa.ForeignKey("interview_sessions.id", ondelete="CASCADE"),
                  nullable=True, index=True),
        sa.Column("levels", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "interview_id", "kind", name="uq_profile_version_kind"),
    )


def _create_evidence_items():
    op.create_table(
        "evidence_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("interview_id", sa.String(36), sa.ForeignKey("interview_sessions.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("turn_id", sa.String(36), sa.ForeignKey("interview_turns.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("competency_id", sa.String(90), sa.ForeignKey("competencies.id"), nullable=False),
        sa.Column("level", sa.Integer(), nullable=True),
        sa.Column("provenance", sa.String(20), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("rubric_version", sa.String(32), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(8), nullable=False),
        sa.Column("uncertainty", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    with op.batch_alter_table("match_runs") as batch:
        batch.drop_column("profile_version_id")
    op.drop_table("evidence_items")
    op.drop_table("profile_versions")
    op.drop_column("snapshots", "cohort_policy")
