from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from backend.config import get_settings


def test_upgrade_head_creates_p1_tables_and_keeps_snapshot_columns(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'migrate.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), "head")
        inspector = inspect(create_engine(url))
        tables = set(inspector.get_table_names())
        assert {"profile_versions", "evidence_items"} <= tables
        assert "cohort_policy" in {c["name"] for c in inspector.get_columns("snapshots")}
        assert "profile_version_id" in {c["name"] for c in inspector.get_columns("match_runs")}
    finally:
        get_settings.cache_clear()
