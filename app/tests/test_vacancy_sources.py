"""Display sources of example vacancies: catalog-level owner statement, deterministic, stored with its assignment note."""
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from backend.config import get_settings
from backend.seed import read_fixture

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.assign_vacancy_sources import SOURCES, pick  # noqa: E402


def test_mapping_is_deterministic_complete_and_declares_its_nature():
    doc = read_fixture("vacancy_sources.json")
    rows = read_fixture("vacancies.json")
    assert doc["assignment"] == "OWNER_STATEMENT_CATALOG_LEVEL" and "not the provenance" in doc["_note"]
    assert set(doc["by_vacancy"]) == {r["id"] for r in rows}
    for r in rows:
        assert doc["by_vacancy"][r["id"]] == pick(r["id"], r["track"]) and doc["by_vacancy"][r["id"]] in SOURCES[r["track"]]


def test_seed_sets_source_name_only_for_example_vacancies(db):
    from backend.models import Vacancy
    s = db()
    for v in s.query(Vacancy).all():
        assert (v.source_name is None) == (v.source_type == "REAL_IMPORTED"), v.id


def test_0015_adds_column_and_is_reversible(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm15.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "0014_vacancy_provenance")
        eng = create_engine(url)
        with eng.begin() as c:
            c.execute(sa.text("ALTER TABLE vacancies DROP COLUMN source_name"))
        command.upgrade(cfg, "head")
        assert "source_name" in {c["name"] for c in sa.inspect(eng).get_columns("vacancies")}
        command.downgrade(cfg, "0014_vacancy_provenance")
        assert "source_name" not in {c["name"] for c in sa.inspect(eng).get_columns("vacancies")}
        command.upgrade(cfg, "head")
    finally:
        get_settings.cache_clear()
