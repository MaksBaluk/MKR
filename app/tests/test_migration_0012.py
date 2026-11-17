import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models import ExperimentRun

NEW = {"relevant_criteria", "answer_source"}


def _cols(eng) -> set[str]:
    return {c["name"] for c in sa.inspect(eng).get_columns("experiment_runs")}


def test_0012_upgrade_downgrade_keeps_rows(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm12.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "0011_experiments")
        eng = create_engine(url)
        # 0001 builds tables from current metadata, so strip the columns to emulate a pre-0012 database
        with eng.begin() as c:
            for name in NEW:
                c.execute(sa.text(f"ALTER TABLE experiment_runs DROP COLUMN {name}"))
        assert not (NEW & _cols(eng))
        command.upgrade(cfg, "head")
        assert NEW <= _cols(eng)
        with Session(eng) as s:
            s.add(ExperimentRun(
                experiment_id="e1", candidate_id="c1", mode="STATIC_INTERVIEW", config={"a": 1}, cohort_id="co",
                cohort_sha256="0" * 64, profile_snapshot={}, rubric_versions={}, prompt_version="p1", model_info={},
                algorithm_version="v1", interview_id=None, qa=[], assessments=[], ranking=[], timings={}, errors={},
                relevant_criteria=["c"], answer_source="SCRIPTED"))
            s.commit()
        command.upgrade(cfg, "head")  # idempotent
        command.downgrade(cfg, "0011_experiments")
        assert not (NEW & _cols(eng))
        with Session(eng) as s:
            assert s.execute(sa.text("SELECT experiment_id FROM experiment_runs")).scalars().all() == ["e1"]
        command.upgrade(cfg, "head")
        assert NEW <= _cols(eng)
        command.upgrade(cfg, "head")
    finally:
        get_settings.cache_clear()
