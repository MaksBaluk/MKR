"""vacancies: source_name (display source of example vacancies). Additive, nullable, idempotent."""
import sqlalchemy as sa
from alembic import op

revision = "0015_vacancy_source_name"
down_revision = "0014_vacancy_provenance"
branch_labels = None
depends_on = None


def _columns() -> set[str] | None:
    insp = sa.inspect(op.get_bind())
    if "vacancies" not in insp.get_table_names():
        return None
    return {c["name"] for c in insp.get_columns("vacancies")}


def upgrade():
    cols = _columns()
    if cols is not None and "source_name" not in cols:
        op.add_column("vacancies", sa.Column("source_name", sa.String(40), nullable=True))


def downgrade():
    cols = _columns()
    if cols is not None and "source_name" in cols:
        with op.batch_alter_table("vacancies") as batch:
            batch.drop_column("source_name")
