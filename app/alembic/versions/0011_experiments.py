"""core_interviews: mode_config, static_plan (nullable); new table experiment_runs (no foreign keys).

Historical interviews keep NULL: product behaviour, fully adaptive. Idempotent."""
import sqlalchemy as sa
from alembic import op

revision = "0011_experiments"
down_revision = "0010_turn_difficulty"
branch_labels = None
depends_on = None

COLUMNS = ("mode_config", "static_plan")


def _columns() -> set[str] | None:
    insp = sa.inspect(op.get_bind())
    if "core_interviews" not in insp.get_table_names():
        return None
    return {c["name"] for c in insp.get_columns("core_interviews")}


def _has_runs() -> bool:
    return "experiment_runs" in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    cols = _columns()
    if cols is not None:
        for name in COLUMNS:
            if name not in cols:
                op.add_column("core_interviews", sa.Column(name, sa.JSON(), nullable=True))
    if not _has_runs():
        op.create_table(
            "experiment_runs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("experiment_id", sa.String(64), nullable=False),
            sa.Column("candidate_id", sa.String(120), nullable=False),
            sa.Column("mode", sa.String(24), nullable=False),
            sa.Column("config", sa.JSON(), nullable=False),
            sa.Column("cohort_id", sa.String(36), nullable=False),
            sa.Column("cohort_sha256", sa.String(64), nullable=False),
            sa.Column("profile_snapshot", sa.JSON(), nullable=False),
            sa.Column("rubric_versions", sa.JSON(), nullable=False),
            sa.Column("prompt_version", sa.String(64), nullable=False),
            sa.Column("model_info", sa.JSON(), nullable=False),
            sa.Column("algorithm_version", sa.String(64), nullable=False),
            sa.Column("interview_id", sa.String(36), nullable=True),
            sa.Column("qa", sa.JSON(), nullable=False),
            sa.Column("assessments", sa.JSON(), nullable=False),
            sa.Column("ranking", sa.JSON(), nullable=False),
            sa.Column("timings", sa.JSON(), nullable=False),
            sa.Column("errors", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_experiment_runs_experiment_id", "experiment_runs", ["experiment_id"])


def downgrade():
    if _has_runs():
        op.drop_index("ix_experiment_runs_experiment_id", table_name="experiment_runs")
        op.drop_table("experiment_runs")
    cols = _columns()
    if cols is None:
        return
    drop = [n for n in COLUMNS if n in cols]
    if drop:
        with op.batch_alter_table("core_interviews") as batch:
            for name in drop:
                batch.drop_column(name)
