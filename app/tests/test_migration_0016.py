import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from backend.config import get_settings

TABLE = "seniority_assessments"


def _tables(eng) -> set[str]:
    return set(sa.inspect(eng).get_table_names())


def test_0016_adds_seniority_table_and_is_reversible(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm16.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "0015_vacancy_source_name")
        eng = create_engine(url)
        # 0001 builds tables from current metadata, so drop the new table to emulate a pre-0016 database
        with eng.begin() as c:
            c.execute(sa.text(f"DROP TABLE IF EXISTS {TABLE}"))
        assert TABLE not in _tables(eng)
        command.upgrade(cfg, "head")
        assert TABLE in _tables(eng)
        cols = {c["name"] for c in sa.inspect(eng).get_columns(TABLE)}
        assert {"interview_id", "policy_version", "result", "rubric_versions", "created_at"} <= cols
        uniques = [set(u["column_names"]) for u in sa.inspect(eng).get_unique_constraints(TABLE)]
        assert {"interview_id", "policy_version"} in uniques
        command.upgrade(cfg, "head")  # idempotent
        command.downgrade(cfg, "0015_vacancy_source_name")
        assert TABLE not in _tables(eng)
        command.downgrade(cfg, "0015_vacancy_source_name")
        command.upgrade(cfg, "head")
        assert TABLE in _tables(eng)
    finally:
        get_settings.cache_clear()
