"""requirement_alternatives: criterion_ids (D_vga), criteria_source, tau, tau_source. Additive, nullable, idempotent.

Legacy rows keep NULL (whole rubric, level-map tau as a working assumption) until the seed backfills them."""
import sqlalchemy as sa
from alembic import op

revision = "0013_requirement_criteria_tau"
down_revision = "0012_experiment_run_fields"
branch_labels = None
depends_on = None

COLUMNS = {"criterion_ids": sa.JSON(), "criteria_source": sa.String(32), "tau": sa.Float(), "tau_source": sa.String(40)}


def _columns() -> set[str] | None:
    insp = sa.inspect(op.get_bind())
    if "requirement_alternatives" not in insp.get_table_names():
        return None
    return {c["name"] for c in insp.get_columns("requirement_alternatives")}


def upgrade():
    cols = _columns()
    if cols is None:
        return
    for name, type_ in COLUMNS.items():
        if name not in cols:
            op.add_column("requirement_alternatives", sa.Column(name, type_, nullable=True))


def downgrade():
    cols = _columns()
    if cols is None:
        return
    drop = [n for n in COLUMNS if n in cols]
    if drop:
        with op.batch_alter_table("requirement_alternatives") as batch:
            for name in drop:
                batch.drop_column(name)
