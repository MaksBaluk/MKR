"""vacancies: retrieved_at, date_posted, import_version for REAL_IMPORTED rows. Additive, nullable, idempotent."""
import sqlalchemy as sa
from alembic import op

revision = "0014_vacancy_provenance"
down_revision = "0013_requirement_criteria_tau"
branch_labels = None
depends_on = None

COLUMNS = {"retrieved_at": sa.String(10), "date_posted": sa.String(10), "import_version": sa.String(60)}


def _columns() -> set[str] | None:
    insp = sa.inspect(op.get_bind())
    if "vacancies" not in insp.get_table_names():
        return None
    return {c["name"] for c in insp.get_columns("vacancies")}


def upgrade():
    cols = _columns()
    if cols is None:
        return
    for name, type_ in COLUMNS.items():
        if name not in cols:
            op.add_column("vacancies", sa.Column(name, type_, nullable=True))


def downgrade():
    cols = _columns()
    if cols is None:
        return
    drop = [n for n in COLUMNS if n in cols]
    if drop:
        with op.batch_alter_table("vacancies") as batch:
            for name in drop:
                batch.drop_column(name)
