"""core_interviews: desired level and level-policy version captured at attempt start (audit D-11, D-12).

Additive, nullable, idempotent. Existing attempts keep NULL: they are finalized as before (current policy, desired level
from the profile at finish). No data is rewritten."""
import sqlalchemy as sa
from alembic import op

revision = "0017_attempt_start_snapshot"
down_revision = "0016_seniority_assessments"
branch_labels = None
depends_on = None

TABLE = "core_interviews"
COLUMNS = (("start_desired_level", 16), ("start_policy_id", 64), ("start_policy_version", 32))


def _columns() -> set[str] | None:
    insp = sa.inspect(op.get_bind())
    return {c["name"] for c in insp.get_columns(TABLE)} if TABLE in insp.get_table_names() else None


def upgrade():
    have = _columns()
    if have is None:  # partial legacy schema without the table: nothing to extend
        return
    for name, size in COLUMNS:
        if name not in have:
            op.add_column(TABLE, sa.Column(name, sa.String(size), nullable=True))


def downgrade():
    drop = [name for name, _ in COLUMNS if name in (_columns() or set())]
    if drop:
        with op.batch_alter_table(TABLE) as batch:
            for name in drop:
                batch.drop_column(name)
