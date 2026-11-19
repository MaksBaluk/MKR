"""criterion_assessments.no_experience: validated Evaluator flag "the quoted answer declares no experience with this
criterion's tool" (audit fix I-3). Additive, nullable, idempotent; legacy rows stay NULL (= not declared)."""
import sqlalchemy as sa
from alembic import op

revision = "0018_assessment_no_experience"
down_revision = "0017_attempt_start_snapshot"
branch_labels = None
depends_on = None

TABLE, COLUMN = "criterion_assessments", "no_experience"


def _columns() -> set[str] | None:
    insp = sa.inspect(op.get_bind())
    return {c["name"] for c in insp.get_columns(TABLE)} if TABLE in insp.get_table_names() else None


def _has() -> bool:
    return COLUMN in (_columns() or set())


def upgrade():
    if _columns() is not None and not _has():
        op.add_column(TABLE, sa.Column(COLUMN, sa.Boolean(), nullable=True))


def downgrade():
    if _has():
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_column(COLUMN)
