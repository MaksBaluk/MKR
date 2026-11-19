import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from backend.config import get_settings

COLS = {"start_desired_level", "start_policy_id", "start_policy_version"}


def _cols(eng) -> set[str]:
    return {c["name"] for c in sa.inspect(eng).get_columns("core_interviews")}


def test_0017_adds_nullable_start_snapshot_columns_and_is_reversible(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm17.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "0016_seniority_assessments")
        eng = create_engine(url)
        # 0001 builds tables from current metadata: drop the new columns to emulate a pre-0017 database with a legacy row
        with eng.begin() as c:
            for col in COLS:
                c.execute(sa.text(f"ALTER TABLE core_interviews DROP COLUMN {col}"))
        assert not COLS & _cols(eng)
        command.upgrade(cfg, "head")
        info = {c["name"]: c for c in sa.inspect(eng).get_columns("core_interviews")}
        assert COLS <= set(info) and all(info[c]["nullable"] for c in COLS)
        command.upgrade(cfg, "head")  # idempotent
        command.downgrade(cfg, "0016_seniority_assessments")
        assert not COLS & _cols(eng)
        command.downgrade(cfg, "0016_seniority_assessments")
        command.upgrade(cfg, "head")
        assert COLS <= _cols(eng)
    finally:
        get_settings.cache_clear()
