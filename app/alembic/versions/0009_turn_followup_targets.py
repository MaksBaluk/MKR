"""core_turns: target_criteria, followup_reason, eval_goal for criterion-targeted follow-ups (additive, nullable).

Historical turns keep NULL: no target recorded and no Evaluator goal."""
import sqlalchemy as sa
from alembic import op

revision = "0009_turn_followup_targets"
down_revision = "0008_profile_level_mode"
branch_labels = None
depends_on = None

COLUMNS = (("target_criteria", sa.JSON), ("followup_reason", sa.Text), ("eval_goal", sa.JSON))


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
