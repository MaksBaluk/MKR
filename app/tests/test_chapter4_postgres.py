"""Chapter-4 Stage 8: integration checks on a real PostgreSQL (skipped unless CH4_PG_URL is set).

Use a THROWAWAY database only, never the project database: the schema is built by Alembic (not create_all), the
catalogue is seeded, and test users are created. Example (see artifacts/chapter4/README.md):
    docker run -d --rm --name ch4-pg -e POSTGRES_PASSWORD=ch4 -e POSTGRES_DB=ch4 -p 55432:5432 pgvector/pgvector:pg16
    CH4_PG_URL=postgresql+psycopg://postgres:ch4@127.0.0.1:55432/ch4 uv run pytest -q tests/test_chapter4_postgres.py
Interviews use the realistic SIMULATED stub (no LLM)."""
import os
import uuid

import pytest
import sqlalchemy as sa

PG_URL = os.environ.get("CH4_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="CH4_PG_URL not set: PostgreSQL integration not run")
API = "/api/v1"


class PgEnv:
    """Same shape as scripts.chapter4.scenarios.Env (client, db) but on PostgreSQL with the Alembic schema."""

    def __enter__(self):
        from alembic import command
        from alembic.config import Config
        from fastapi.testclient import TestClient
        from sqlalchemy.orm import sessionmaker

        import backend.api.core as core
        from backend.config import get_settings
        from backend.db import get_db
        from backend.main import app
        from backend.seed import seed_database

        self._old_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = PG_URL
        get_settings.cache_clear()
        self.engine = sa.create_engine(PG_URL)
        with self.engine.begin() as c:  # fresh schema each run: the database is throwaway by contract
            c.execute(sa.text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
        self.cfg = Config("alembic.ini")
        command.upgrade(self.cfg, "head")
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.Session() as s:
            seed_database(s, demo_mode=False)

        def override():
            with self.Session() as session:
                yield session

        self.core, self.app, self.saved = core, app, (core.get_chat_model, dict(app.dependency_overrides))
        app.dependency_overrides[get_db] = override
        self.client = TestClient(app).__enter__()
        self.db = self.Session()
        return self

    def __exit__(self, *exc):
        from backend.config import get_settings
        self.core.get_chat_model = self.saved[0]
        self.app.dependency_overrides.clear()
        self.app.dependency_overrides.update(self.saved[1])
        self.db.close()
        self.client.__exit__(*exc)
        self.engine.dispose()
        if self._old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self._old_url
        get_settings.cache_clear()


@pytest.fixture(scope="module")
def pg():
    with PgEnv() as env:
        yield env


def _user(c):
    tok = c.post(f"{API}/auth/register", json={"email": f"pg-{uuid.uuid4().hex}@example.test", "display_name": "PG",
                                               "password": uuid.uuid4().hex}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_alembic_head_on_postgres_and_one_step_reversible(pg):
    from alembic import command
    with pg.engine.connect() as c:
        assert c.execute(sa.text("select version_num from alembic_version")).scalar() == "0018_assessment_no_experience"
    command.downgrade(pg.cfg, "-1")
    command.upgrade(pg.cfg, "head")
    cols = {c["name"] for c in sa.inspect(pg.engine).get_columns("criterion_assessments")}
    assert "no_experience" in cols


def test_end_to_end_senior_level_is_stored_once_and_immutable_on_postgres(pg):
    from backend.models import SeniorityAssessment
    from scripts.chapter4.realistic_runs import run_detailed
    from scripts.seniority_realistic import profiles
    r = run_detailed(pg, "senior", profiles()["senior"], "junior", 2, "OPEN", None, "ch4-pg-s07-e2e")
    assert r["assessed"] == "SENIOR" and r["policy"] == "v4"
    rows = pg.db.scalars(sa.select(SeniorityAssessment).where(SeniorityAssessment.interview_id == r["interview_id"])).all()
    assert len(rows) == 1 and rows[0].desired_level == "junior" and rows[0].policy_version == "v4"
    stored_at = rows[0].created_at
    pg.db.expire_all()
    again = pg.db.scalars(sa.select(SeniorityAssessment).where(SeniorityAssessment.interview_id == r["interview_id"])).all()
    assert len(again) == 1 and again[0].created_at == stored_at


def test_policy_version_change_adds_a_row_and_keeps_the_old_one_on_postgres(pg):
    from backend.api.level import finalize_level
    from backend.domain.seniority_policy import POLICY_VERSIONS
    from backend.models import CoreInterview, SeniorityAssessment
    from scripts.chapter4.realistic_runs import run_detailed
    from scripts.seniority_realistic import profiles
    r = run_detailed(pg, "middle", profiles()["middle"], "middle", 2, "OPEN", None, "ch4-pg-policy")
    iv = pg.db.get(CoreInterview, r["interview_id"])
    v4 = pg.db.scalars(sa.select(SeniorityAssessment).where(SeniorityAssessment.interview_id == iv.id)).one()
    before = (v4.assessed_level, dict(v4.result))
    finalize_level(pg.db, iv, POLICY_VERSIONS[("python-backend", "v3")])
    pg.db.commit()
    rows = {x.policy_version: x for x in pg.db.scalars(
        sa.select(SeniorityAssessment).where(SeniorityAssessment.interview_id == iv.id))}
    assert set(rows) == {"v3", "v4"} and (rows["v4"].assessed_level, rows["v4"].result) == before
    assert pg.client.get(f"{API}/interviews/{iv.id}/level", headers={"Authorization": "x"}).status_code in (401, 403)


def test_idempotent_replay_stale_version_and_isolation_on_postgres(pg):
    c = pg.client
    a, b = _user(c), _user(c)
    pid = c.get(f"{API}/profiles", headers=a).json()["items"][0]["id"]
    c.put(f"{API}/profiles/{pid}", headers=a, json={"name": "pg", "track": "python", "target_level": "middle",
                                                    "years_experience": 3}).raise_for_status()
    cohort = c.post(f"{API}/cohorts/auto", headers=a, params={"profile_id": pid}).json()["cohort_id"]
    again = c.post(f"{API}/cohorts/auto", headers=a, params={"profile_id": pid}).json()["cohort_id"]
    assert again == cohort  # idempotent cohort
    iv = c.post(f"{API}/interviews", headers=a, json={"cohort_id": cohort}).json()
    q = c.post(f"{API}/interviews/{iv['id']}/next-question", headers=a, json={"version": iv["version"]}).json()
    assert c.post(f"{API}/interviews/{iv['id']}/next-question", headers=a,
                  json={"version": iv["version"]}).status_code == 409  # stale version
    state = c.get(f"{API}/interviews/{iv['id']}", headers=a).json()
    assert state["pending_turn"]["id"] == q["turn"]["id"]  # recovery: the pending question comes from the server
    body = {"turn_id": q["turn"]["id"], "text": "Працював із цим на проєкті.", "version": q["version"],
            "idempotency_key": "pg-replay-1"}
    r1 = c.post(f"{API}/interviews/{iv['id']}/answers", headers=a, json=body)
    r2 = c.post(f"{API}/interviews/{iv['id']}/answers", headers=a, json=body)
    assert r1.status_code == r2.status_code == 200 and r1.json()["version"] == r2.json()["version"]
    turns = [t for t in c.get(f"{API}/interviews/{iv['id']}", headers=a).json()["turns"] if t.get("answer_text")]
    assert len(turns) == 1  # the replay stored nothing twice
    assert c.get(f"{API}/interviews/{iv['id']}", headers=b).status_code in (403, 404)
    assert c.get(f"{API}/profiles/{pid}/results", headers=b).status_code in (403, 404)
