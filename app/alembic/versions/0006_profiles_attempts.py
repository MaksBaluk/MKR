"""Candidate profiles and interview attempts: additive columns plus an idempotent backfill."""
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0006_profiles_attempts"
down_revision = "0005_turn_off_topic"
branch_labels = None
depends_on = None

DEFAULT_PROFILE_NAME = "Основний профіль"
# table -> (extra column or None, unique constraint name, unique columns)
TABLES = {
    "candidate_self_ratings": (None, "uq_self_rating_profile_action_rev", ["profile_id", "action_id", "revision"]),
    "core_interviews": (
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
        "uq_attempt_profile_no", ["profile_id", "attempt_no"]),
}


def _ensure_schema(bind) -> None:
    from backend.models import CandidateProfile
    CandidateProfile.__table__.create(bind, checkfirst=True)
    for table, (extra, uq_name, uq_cols) in TABLES.items():
        insp = sa.inspect(bind)
        cols = {c["name"] for c in insp.get_columns(table)}
        if "profile_id" in cols and (extra is None or extra.name in cols):
            continue
        with op.batch_alter_table(table) as batch:
            if "profile_id" not in cols:
                batch.add_column(sa.Column("profile_id", sa.String(36), nullable=True))
                batch.create_foreign_key(f"fk_{table}_profile_id", "candidate_profiles", ["profile_id"], ["id"], ondelete="CASCADE")
            if extra is not None and extra.name not in cols:
                batch.add_column(extra)
    for table, (_, uq_name, uq_cols) in TABLES.items():
        insp = sa.inspect(bind)
        if uq_name not in {u["name"] for u in insp.get_unique_constraints(table)}:
            with op.batch_alter_table(table) as batch:
                batch.create_unique_constraint(uq_name, uq_cols)
        if f"ix_{table}_profile_id" not in {i["name"] for i in insp.get_indexes(table)}:
            op.create_index(f"ix_{table}_profile_id", table, ["profile_id"])


def backfill_profiles(bind) -> None:
    """One default profile per profile-less user; link orphan rows; number attempts by created_at. Idempotent."""
    users = bind.execute(sa.text(
        "SELECT id, track, desired_title, years_experience, location FROM users "
        "WHERE id NOT IN (SELECT user_id FROM candidate_profiles)")).mappings().all()
    for u in users:
        bind.execute(sa.text(
            "INSERT INTO candidate_profiles (id, user_id, track, name, desired_title, years_experience, location, archived, created_at) "
            "VALUES (:id, :uid, :track, :name, :title, :years, :loc, :arch, :ts)"),
            {"id": str(uuid.uuid4()), "uid": u["id"], "track": u["track"], "name": DEFAULT_PROFILE_NAME,
             "title": u["desired_title"] or "", "years": u["years_experience"], "loc": u["location"] or "",
             "arch": False, "ts": datetime.now(timezone.utc)})
    first_profile = ("(SELECT p.id FROM candidate_profiles p WHERE p.user_id = {t}.user_id "
                     "ORDER BY p.created_at, p.id LIMIT 1)")
    bind.execute(sa.text("UPDATE candidate_self_ratings SET profile_id = " + first_profile.format(t="candidate_self_ratings")
                         + " WHERE profile_id IS NULL"))
    orphans = bind.execute(sa.text("SELECT id, user_id FROM core_interviews WHERE profile_id IS NULL ORDER BY created_at, id")).all()
    if not orphans:
        return
    for row in orphans:  # link and number in one UPDATE per row so (profile_id, attempt_no) stays unique
        prof = bind.execute(sa.text("SELECT id FROM candidate_profiles WHERE user_id = :u ORDER BY created_at, id LIMIT 1"),
                            {"u": row.user_id}).scalar()
        used = bind.execute(sa.text("SELECT COALESCE(MAX(attempt_no), 0) FROM core_interviews WHERE profile_id = :p"), {"p": prof}).scalar()
        bind.execute(sa.text("UPDATE core_interviews SET profile_id = :p, attempt_no = :n WHERE id = :i"),
                     {"p": prof, "n": used + 1, "i": row.id})


def upgrade():
    bind = op.get_bind()
    _ensure_schema(bind)
    backfill_profiles(bind)


def downgrade():
    pass  # additive columns and a table holding user data; dropping them would lose profile links
