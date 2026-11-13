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
