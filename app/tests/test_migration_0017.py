import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from backend.config import get_settings

COLS = {"start_desired_level", "start_policy_id", "start_policy_version"}


def _cols(eng, table="core_interviews") -> set[str]:
    return {c["name"] for c in sa.inspect(eng).get_columns(table)}


def _drop(eng, cols, table="core_interviews"):
    with eng.begin() as c:
        for col in cols:
            c.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN {col}"))


def test_0017_adds_nullable_start_snapshot_columns_and_is_reversible(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm17.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "0016_seniority_assessments")
        eng = create_engine(url)
        # 0001 builds tables from current metadata: drop the new columns to emulate a pre-0017 database
        _drop(eng, COLS)
        assert not COLS & _cols(eng)
        command.upgrade(cfg, "0017_attempt_start_snapshot")
        info = {c["name"]: c for c in sa.inspect(eng).get_columns("core_interviews")}
        assert COLS <= set(info) and all(info[c]["nullable"] for c in COLS)
        # real re-run of the upgrade body over existing columns (alembic would otherwise skip a stamped revision)
        command.stamp(cfg, "0016_seniority_assessments")
        command.upgrade(cfg, "0017_attempt_start_snapshot")
        assert COLS <= _cols(eng)
        command.downgrade(cfg, "0016_seniority_assessments")
        assert not COLS & _cols(eng)
        # real re-run of the downgrade body over missing columns
        command.stamp(cfg, "0017_attempt_start_snapshot")
        command.downgrade(cfg, "0016_seniority_assessments")
        assert not COLS & _cols(eng)
        command.upgrade(cfg, "head")
        assert COLS <= _cols(eng)
    finally:
        get_settings.cache_clear()


def test_0018_adds_nullable_no_experience_and_is_reversible(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm18.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "0017_attempt_start_snapshot")
        eng = create_engine(url)
        _drop(eng, {"no_experience"}, "criterion_assessments")
        command.upgrade(cfg, "0018_assessment_no_experience")
        info = {c["name"]: c for c in sa.inspect(eng).get_columns("criterion_assessments")}
        assert info["no_experience"]["nullable"]
        command.stamp(cfg, "0017_attempt_start_snapshot")
        command.upgrade(cfg, "0018_assessment_no_experience")  # guard: column already there
        command.downgrade(cfg, "0017_attempt_start_snapshot")
        assert "no_experience" not in _cols(eng, "criterion_assessments")
        command.stamp(cfg, "0018_assessment_no_experience")
        command.downgrade(cfg, "0017_attempt_start_snapshot")  # guard: column already gone
        command.upgrade(cfg, "head")
        assert "no_experience" in _cols(eng, "criterion_assessments")
    finally:
        get_settings.cache_clear()
