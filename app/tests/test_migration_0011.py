import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models import ExperimentRun

NEW = {"mode_config", "static_plan"}


def _cols(eng, table="core_interviews") -> set[str]:
    return {c["name"] for c in sa.inspect(eng).get_columns(table)}


def test_0011_upgrade_downgrade_keeps_interviews(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm11.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "0010_turn_difficulty")
        eng = create_engine(url)
        command.upgrade(cfg, "head")
        assert NEW <= _cols(eng)
        assert {"id", "experiment_id", "cohort_sha256", "errors", "created_at"} <= _cols(eng, "experiment_runs")
        assert {"ix_experiment_runs_experiment_id"} <= {i["name"] for i in sa.inspect(eng).get_indexes("experiment_runs")}
        assert sa.inspect(eng).get_foreign_keys("experiment_runs") == []
        with Session(eng) as s:
            s.add(ExperimentRun(
                experiment_id="e1", candidate_id="c1", mode="STATIC_INTERVIEW", config={"a": 1}, cohort_id="co",
                cohort_sha256="0" * 64, profile_snapshot={}, rubric_versions={}, prompt_version="p1", model_info={},
                algorithm_version="v1", interview_id=None, qa=[], assessments=[], ranking=[], timings={}, errors=[]))
            s.commit()
        with Session(eng) as s:
            r = s.query(ExperimentRun).one()
            assert (r.id, r.mode, r.config, r.interview_id, r.created_at) == (r.id, "STATIC_INTERVIEW", {"a": 1}, None, r.created_at)
            assert r.id and r.created_at
        command.upgrade(cfg, "head")  # idempotent
        command.downgrade(cfg, "0010_turn_difficulty")
        assert not (NEW & _cols(eng))
        assert "experiment_runs" not in sa.inspect(eng).get_table_names()
        command.upgrade(cfg, "head")
        assert NEW <= _cols(eng)
        command.upgrade(cfg, "head")
    finally:
        get_settings.cache_clear()


def test_0011_legacy_interview_rows_read_null(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm11b.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "0010_turn_difficulty")
        eng = create_engine(url)
        with eng.begin() as c:
            c.execute(sa.text("PRAGMA foreign_keys=OFF"))
            c.execute(sa.text("INSERT INTO core_interviews (id,user_id,cohort_id,status,version,created_at,attempt_no) "
                              "VALUES ('i1','u','c','ACTIVE',0,'2026-01-01',1)"))
        command.upgrade(cfg, "head")
        with eng.connect() as c:
            assert tuple(c.execute(sa.text("SELECT mode_config,static_plan FROM core_interviews")).one()) == (None, None)
        command.downgrade(cfg, "0010_turn_difficulty")
        with eng.connect() as c:
            assert c.execute(sa.text("SELECT id,status FROM core_interviews")).all() == [("i1", "ACTIVE")]
    finally:
        get_settings.cache_clear()
