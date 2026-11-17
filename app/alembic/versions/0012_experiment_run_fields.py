"""experiment_runs: relevant_criteria (JSON), answer_source (String 16), both nullable. Idempotent.

Older rows keep NULL; load_record falls back to the answer_source stored in config."""
import sqlalchemy as sa
from alembic import op

revision = "0012_experiment_run_fields"
down_revision = "0011_experiments"
branch_labels = None
depends_on = None

COLUMNS = {"relevant_criteria": sa.JSON(), "answer_source": sa.String(16)}


def _columns() -> set[str] | None:
    insp = sa.inspect(op.get_bind())
    if "experiment_runs" not in insp.get_table_names():
        return None
    return {c["name"] for c in insp.get_columns("experiment_runs")}


def upgrade():
    cols = _columns()
    if cols is None:
        return
    for name, type_ in COLUMNS.items():
        if name not in cols:
            op.add_column("experiment_runs", sa.Column(name, type_, nullable=True))


def downgrade():
    cols = _columns()
    if cols is None:
        return
    drop = [n for n in COLUMNS if n in cols]
    if drop:
        with op.batch_alter_table("experiment_runs") as batch:
            for name in drop:
                batch.drop_column(name)
