"""Point criterion_assessments.session_id at core_interviews (0003 first shipped it against interview_sessions)."""
import sqlalchemy as sa
from alembic import op

revision = "0004_assessment_fk"
down_revision = "0003_core_loop"
branch_labels = None
depends_on = None

FK = "criterion_assessments_session_id_fkey"


def _targets_core(bind) -> bool:
    for fk in sa.inspect(bind).get_foreign_keys("criterion_assessments"):
        if fk["constrained_columns"] == ["session_id"]:
            return fk["referred_table"] == "core_interviews"
    return True


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or _targets_core(bind):
        return  # SQLite does not enforce this FK; fresh databases already use core_interviews
    op.execute(f"DELETE FROM criterion_assessments WHERE session_id NOT IN (SELECT id FROM core_interviews)")
    op.drop_constraint(FK, "criterion_assessments", type_="foreignkey")
    op.create_foreign_key(FK, "criterion_assessments", "core_interviews", ["session_id"], ["id"], ondelete="CASCADE")


def downgrade():
    pass  # the previous FK was a defect; nothing to restore
