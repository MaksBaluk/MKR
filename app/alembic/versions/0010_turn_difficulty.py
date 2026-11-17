"""core_turns: difficulty, difficulty_reason, controller_before/after for the DifficultyController (additive, nullable).

Historical turns keep NULL: no difficulty or controller state recorded."""
import sqlalchemy as sa
from alembic import op

revision = "0010_turn_difficulty"
down_revision = "0009_turn_followup_targets"
branch_labels = None
depends_on = None

COLUMNS = (("difficulty", lambda: sa.String(16)), ("difficulty_reason", lambda: sa.String(64)),
           ("controller_before", sa.JSON), ("controller_after", sa.JSON))


def _columns() -> set[str] | None:
    insp = sa.inspect(op.get_bind())
    if "core_turns" not in insp.get_table_names():
        return None
    return {c["name"] for c in insp.get_columns("core_turns")}


def upgrade():
    cols = _columns()
    if cols is None:
        return
    for name, type_ in COLUMNS:
        if name not in cols:
            op.add_column("core_turns", sa.Column(name, type_(), nullable=True))


def downgrade():
    cols = _columns()
    if cols is None:
        return
    drop = [name for name, _ in COLUMNS if name in cols]
    if drop:
        with op.batch_alter_table("core_turns") as batch:
            for name in drop:
                batch.drop_column(name)
