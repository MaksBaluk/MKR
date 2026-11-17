"""candidate_profiles: target_level, work_mode (additive) and a nullable track (the candidate chooses it).

Existing rows keep their track; new columns are NULL (unknown)."""
import sqlalchemy as sa
from alembic import op

revision = "0008_profile_level_mode"
down_revision = "0007_assessment_sufficient"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    insp = sa.inspect(op.get_bind())
    if "candidate_profiles" not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns("candidate_profiles")}


def upgrade():
    cols = _columns()
    if not cols:
        return
    if "target_level" not in cols:
        op.add_column("candidate_profiles", sa.Column("target_level", sa.String(16), nullable=True))
    if "work_mode" not in cols:
        op.add_column("candidate_profiles", sa.Column("work_mode", sa.String(16), nullable=True))
    with op.batch_alter_table("candidate_profiles") as batch:
        batch.alter_column("track", existing_type=sa.String(32), nullable=True)


def downgrade():
    pass  # additive columns; a nullable track is harmless for old code paths that always set it
