"""core_turns.off_topic: Evaluator flagged the answer as off-topic or an injection attempt (additive)."""
import sqlalchemy as sa
from alembic import op

revision = "0005_turn_off_topic"
down_revision = "0004_assessment_fk"
branch_labels = None
depends_on = None


def _has_column() -> bool:
    insp = sa.inspect(op.get_bind())
    return "core_turns" in insp.get_table_names() and "off_topic" in {c["name"] for c in insp.get_columns("core_turns")}


def upgrade():
    if _has_column():
        return
    op.add_column("core_turns", sa.Column("off_topic", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    pass  # additive column; historical rows are kept
