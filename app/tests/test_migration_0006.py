import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError

from backend.config import get_settings

OLD_SELF = """CREATE TABLE candidate_self_ratings (user_id VARCHAR(36) NOT NULL, action_id VARCHAR(120) NOT NULL,
 revision INTEGER NOT NULL, value FLOAT, created_at DATETIME NOT NULL,
 PRIMARY KEY (user_id, action_id, revision), FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE)"""
OLD_CORE = """CREATE TABLE core_interviews (id VARCHAR(36) NOT NULL PRIMARY KEY, user_id VARCHAR(36) NOT NULL,
 cohort_id VARCHAR(36) NOT NULL, status VARCHAR(16) NOT NULL, version INTEGER NOT NULL, created_at DATETIME NOT NULL,
 FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
 FOREIGN KEY(cohort_id) REFERENCES cohort_snapshots (id) ON DELETE CASCADE)"""


def _setup(tmp_path, monkeypatch, name="m6.db"):
    url = f"sqlite:///{tmp_path / name}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    return url, Config("alembic.ini")


def _seed(conn):
    for uid_, track in (("u1", "python"), ("u2", "java")):
        conn.execute(sa.text("INSERT INTO users (id,email,display_name,password_hash,track,desired_title,years_experience,location,created_at)"
                             " VALUES (:i,:e,'N','h',:t,'Dev',3,'Kyiv','2026-01-01')"), {"i": uid_, "e": uid_ + "@x", "t": track})
    conn.execute(sa.text("INSERT INTO cohort_snapshots (id,user_id,vacancy_ids,requirement_revisions,policy_id,sha256,created_at)"
                         " VALUES ('c1','u1','[]','{}','p','s','2026-01-01')"))
    for i, ts in (("i3", "2026-03-01"), ("i1", "2026-01-01"), ("i2", "2026-02-01")):
        conn.execute(sa.text("INSERT INTO core_interviews (id,user_id,cohort_id,status,version,created_at) VALUES (:i,'u1','c1','FINISHED',0,:t)"), {"i": i, "t": ts})
    for rev in (1, 2):
        conn.execute(sa.text("INSERT INTO candidate_self_ratings (user_id,action_id,revision,value,created_at) VALUES ('u1','a',:r,0.5,'2026-01-01')"), {"r": rev})
    conn.execute(sa.text("INSERT INTO candidate_self_ratings (user_id,action_id,revision,value,created_at) VALUES ('u2','a',1,0,'2026-01-01')"))


def _migrate_old_shape(tmp_path, monkeypatch, old_shape):
    url, cfg = _setup(tmp_path, monkeypatch)
    command.upgrade(cfg, "0005_turn_off_topic")
    eng = create_engine(url)
    with eng.begin() as c:
        if old_shape:
            c.execute(sa.text("DROP TABLE criterion_assessments")); c.execute(sa.text("DROP TABLE core_turns"))
            for t in ("candidate_self_ratings", "core_interviews", "candidate_profiles"):
                c.execute(sa.text(f"DROP TABLE IF EXISTS {t}"))
            c.execute(sa.text(OLD_SELF)); c.execute(sa.text(OLD_CORE))
        _seed(c)
        c.execute(sa.text("DELETE FROM alembic_version")); c.execute(sa.text("INSERT INTO alembic_version VALUES ('0005_turn_off_topic')"))
    return url, cfg, eng


def _check_backfill(eng):
    with eng.connect() as c:
        profs = c.execute(sa.text("SELECT id,user_id,name,track,desired_title,years_experience,location FROM candidate_profiles ORDER BY user_id")).all()
        assert [(p.user_id, p.name, p.track, p.desired_title, p.years_experience, p.location) for p in profs] == [
            ("u1", "Основний профіль", "python", "Dev", 3, "Kyiv"), ("u2", "Основний профіль", "java", "Dev", 3, "Kyiv")]
        pid = {p.user_id: p.id for p in profs}
        ivs = c.execute(sa.text("SELECT id,profile_id,attempt_no FROM core_interviews ORDER BY attempt_no")).all()
        assert [(i.id, i.attempt_no) for i in ivs] == [("i1", 1), ("i2", 2), ("i3", 3)]
        assert {i.profile_id for i in ivs} == {pid["u1"]}
        rows = c.execute(sa.text("SELECT user_id,profile_id FROM candidate_self_ratings")).all()
        assert len(rows) == 3 and all(r.profile_id == pid[r.user_id] for r in rows)


def test_backfill_on_current_schema_is_idempotent(tmp_path, monkeypatch):
    try:
        url, cfg, eng = _migrate_old_shape(tmp_path, monkeypatch, old_shape=False)
        command.upgrade(cfg, "head")
        _check_backfill(eng)
        command.stamp(cfg, "0005_turn_off_topic")
        command.upgrade(cfg, "head")
        _check_backfill(eng)
        with eng.connect() as c:
            assert c.execute(sa.text("SELECT count(*) FROM candidate_profiles")).scalar() == 2
    finally:
        get_settings.cache_clear()


def test_upgrade_from_old_shape_adds_columns_and_backfills(tmp_path, monkeypatch):
    try:
        url, cfg, eng = _migrate_old_shape(tmp_path, monkeypatch, old_shape=True)
        command.upgrade(cfg, "head")
        insp = sa.inspect(eng)
        assert {"profile_id", "attempt_no"} <= {c["name"] for c in insp.get_columns("core_interviews")}
        assert "profile_id" in {c["name"] for c in insp.get_columns("candidate_self_ratings")}
        _check_backfill(eng)
        command.stamp(cfg, "0005_turn_off_topic")
        command.upgrade(cfg, "head")
        _check_backfill(eng)
    finally:
        get_settings.cache_clear()


def test_attempt_unique_constraint(tmp_path, monkeypatch):
    try:
        url, cfg, eng = _migrate_old_shape(tmp_path, monkeypatch, old_shape=True)
        command.upgrade(cfg, "head")
        event.listen(eng, "connect", lambda d, _: d.execute("PRAGMA foreign_keys=ON"))
        with eng.connect() as c:
            pid = c.execute(sa.text("SELECT profile_id FROM core_interviews WHERE id='i1'")).scalar()
        names = {u["name"] for u in sa.inspect(eng).get_unique_constraints("core_interviews")}
        assert "uq_attempt_profile_no" in names
        try:
            with eng.begin() as c:
                c.execute(sa.text("INSERT INTO core_interviews (id,user_id,cohort_id,status,version,created_at,profile_id,attempt_no)"
                                  " VALUES ('dup','u1','c1','ACTIVE',0,'2026-04-01',:p,1)"), {"p": pid})
            raise AssertionError("expected IntegrityError")
        except IntegrityError:
            pass
    finally:
        get_settings.cache_clear()


def test_orm_candidate_profile_roundtrip():
    from backend.db import Base
    from backend.models import CandidateProfile, User
    from sqlalchemy.orm import Session
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(User(id="u", email="e@x", display_name="n", password_hash="h"))
        s.add(CandidateProfile(id="p", user_id="u", track="python", name="Профіль"))
        s.commit()
        p = s.get(CandidateProfile, "p")
        assert (p.desired_title, p.location, p.archived, p.years_experience) == ("", "", False, None)
        assert p.created_at is not None
