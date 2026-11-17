import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from backend.config import get_settings

NEW = {"target_criteria", "followup_reason", "eval_goal"}


def _cols(eng) -> set[str]:
    return {c["name"] for c in sa.inspect(eng).get_columns("core_turns")}


def test_0009_upgrade_downgrade_keeps_turns(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm9.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
        eng = create_engine(url)
        assert NEW <= _cols(eng)
        with eng.begin() as c:
            c.execute(sa.text("INSERT INTO core_turns (id,interview_id,sequence,action_id,question_text,question_source,"
                              "off_topic,target_criteria,followup_reason,eval_goal,created_at) VALUES ('t1','i1',1,'a',"
                              "'Q?','LLM_INTERVIEWER',0,'[\"a.x\"]','OPEN_CRITERIA',NULL,'2026-01-01')"))
        command.downgrade(cfg, "0008_profile_level_mode")
        assert not (NEW & _cols(eng))
        with eng.connect() as c:
            assert c.execute(sa.text("SELECT id,action_id,question_text FROM core_turns")).all() == [("t1", "a", "Q?")]
        names = {u["name"] for u in sa.inspect(eng).get_unique_constraints("core_turns")}
        assert {"uq_core_turn_sequence", "uq_core_turn_idem"} <= names
        command.upgrade(cfg, "head")
        assert NEW <= _cols(eng)
        with eng.connect() as c:
            row = c.execute(sa.text("SELECT target_criteria,followup_reason,eval_goal FROM core_turns")).one()
        assert tuple(row) == (None, None, None)  # historical turns: no recorded target or goal
        command.upgrade(cfg, "head")  # idempotent
    finally:
        get_settings.cache_clear()
