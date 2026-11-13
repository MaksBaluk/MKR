"""criterion_assessments.sufficient_evidence: Evaluator judged the action series sufficiently evidenced (additive).

NULL on historical rows means unknown and is treated as not sufficient by the interview planner."""
import sqlalchemy as sa
from alembic import op

revision = "0007_assessment_sufficient"
down_revision = "0006_profiles_attempts"
branch_labels = None
depends_on = None


def _needed() -> bool:
    insp = sa.inspect(op.get_bind())
    return "criterion_assessments" in insp.get_table_names() and "sufficient_evidence" not in {
        c["name"] for c in insp.get_columns("criterion_assessments")}


def upgrade():
    if not _needed():  # table absent (partial legacy schema) or column already present
        return
    op.add_column("criterion_assessments", sa.Column("sufficient_evidence", sa.Boolean(), nullable=True))


def downgrade():
    pass  # additive column; historical rows are kept
