import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from backend.config import get_settings

NEW = {"candidate_self_ratings", "rubrics", "rubric_criteria", "criterion_assessments", "cohort_snapshots"}


def test_head_has_new_tables_and_keeps_existing_tables(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), "head")
        names = set(sa.inspect(create_engine(url)).get_table_names())
        assert NEW <= names
        assert {"users", "vacancies", "interview_sessions", "snapshots"} <= names
    finally:
        get_settings.cache_clear()


def test_assessment_session_fk_points_at_core_interviews():
    from backend.models import CriterionAssessment
    targets = {fk.column.table.name for fk in CriterionAssessment.__table__.c.session_id.foreign_keys}
    assert targets == {"core_interviews"}


def test_0005_adds_turn_off_topic_column_idempotently(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm5.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
        cols = {c["name"]: c for c in sa.inspect(create_engine(url)).get_columns("core_turns")}
        assert "off_topic" in cols and cols["off_topic"]["nullable"] is False
        command.stamp(cfg, "0004_assessment_fk")
        command.upgrade(cfg, "head")  # column already present: no error
    finally:
        get_settings.cache_clear()


def test_0007_adds_assessment_sufficient_evidence_idempotently(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm7.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
        cols = {c["name"]: c for c in sa.inspect(create_engine(url)).get_columns("criterion_assessments")}
        assert "sufficient_evidence" in cols and cols["sufficient_evidence"]["nullable"] is True
        command.stamp(cfg, "0006_profiles_attempts")
        command.upgrade(cfg, "head")  # column already present: no error
    finally:
        get_settings.cache_clear()
