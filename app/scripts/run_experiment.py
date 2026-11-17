"""Run interview-mode experiments (A: INITIAL_PROFILE, B: STATIC_INTERVIEW, C: ADAPTIVE_INTERVIEW) on a separate DB.

Run from app/:
    uv run python scripts/run_experiment.py --db sqlite:///experiments.db --candidates candidates.json \
        --answers answers.json --modes INITIAL_PROFILE STATIC_INTERVIEW ADAPTIVE_INTERVIEW --out out/

--db is required and must be a SQLite URL: the schema is created and the catalog seeded there (like the tests),
the product database is never used. The LLM comes from the server-side settings (LLM_PROVIDER, LLM_API_KEY, ...);
interview modes without a configured LLM are refused unless --allow-ungraded (answers are then stored UNGRADED).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

if __package__ in (None, ""):  # direct `python scripts/run_experiment.py`: make `backend` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import backend.api.core as core  # noqa: E402
import backend.models  # noqa: E402,F401
from backend.config import get_settings  # noqa: E402
from backend.db import Base, get_db  # noqa: E402
from backend.experiments.config import InterviewMode, config_for  # noqa: E402
from backend.experiments.providers import CandidateSpec, ScriptedProvider  # noqa: E402
from backend.experiments.runner import run_experiment  # noqa: E402
from backend.experiments.store import export_records, save_record  # noqa: E402
from backend.main import app  # noqa: E402
from backend.seed import seed_database  # noqa: E402

FLAGS = {"no_adaptive_topics": "adaptive_topics", "no_adaptive_followup": "adaptive_followup",
         "no_adaptive_difficulty": "adaptive_difficulty"}


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--db", required=True, help="sqlite URL of a separate experiment database (required)")
    p.add_argument("--candidates", required=True, type=Path, help="JSON list of CandidateSpec objects")
    p.add_argument("--answers", required=True, type=Path, help="ScriptedProvider JSON file")
    p.add_argument("--modes", nargs="+", choices=[m.value for m in InterviewMode],
                   default=[m.value for m in InterviewMode])
    p.add_argument("--flags", nargs="*", choices=sorted(FLAGS), default=[],
                   help="ablations for ADAPTIVE_INTERVIEW (STATIC always has all adaptive flags off)")
    p.add_argument("--total-budget", type=int, default=None, help="max shown questions per interview")
    p.add_argument("--experiment-id", default=None)
    p.add_argument("--allow-ungraded", action="store_true", help="run interview modes without an LLM")
    p.add_argument("--out", required=True, type=Path)
    return p


def _config(mode: InterviewMode, flags: Sequence[str], total_budget: int | None):
    if mode is InterviewMode.ADAPTIVE_INTERVIEW:
        return config_for(mode, total_budget=total_budget, **{FLAGS[f]: False for f in flags})
    return config_for(mode, total_budget=total_budget)


def main(argv: Sequence[str] | None = None, model_factory: Callable[[], object] | None = None) -> int:
    """model_factory: test hook replacing the configured chat model for this call only (no env, no network)."""
    args = _parser().parse_args(argv)
    if not args.db.startswith("sqlite") or args.db == get_settings().database_url:
        print("error: --db must be a separate sqlite URL (never the product database)", file=sys.stderr)
        return 2
    modes = [InterviewMode(m) for m in args.modes]
    configs = [_config(m, args.flags, args.total_budget) for m in modes]
    original = core.get_chat_model
    if model_factory is not None:
        core.get_chat_model = model_factory
    try:
        interviewing = any(m is not InterviewMode.INITIAL_PROFILE for m in modes)
        if interviewing and core.get_chat_model() is None and not args.allow_ungraded:
            print("error: no LLM configured for interview modes; set LLM_* or pass --allow-ungraded",
                  file=sys.stderr)
            return 2
        candidates = [CandidateSpec.from_json(d) for d in json.loads(args.candidates.read_text(encoding="utf-8"))]
        provider = ScriptedProvider.from_file(args.answers)
        memory = args.db.rstrip("/") in ("sqlite://", "sqlite+pysqlite://") or ":memory:" in args.db
        engine = create_engine(args.db, connect_args={"check_same_thread": False},
                               **({"poolclass": StaticPool} if memory else {}))
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        with Session() as s:
            seed_database(s, demo_mode=False)

        def override():
            with Session() as session:
                yield session

        experiment_id = args.experiment_id or time.strftime("exp-%Y%m%dT%H%M%S")
        saved = dict(app.dependency_overrides)
        app.dependency_overrides[get_db] = override
        records, run_ids = [], []
        try:
            with TestClient(app) as client, Session() as db:
                for cand in candidates:
                    for cfg in configs:
                        rec = run_experiment(experiment_id, cfg, cand, provider, client, db)
                        records.append(rec)
                        run_ids.append(save_record(db, rec))
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(saved)
            engine.dispose()
        export_records(records, args.out)
        print(f"experiment {experiment_id}: {len(records)} runs written to {args.out}")
        for rid, rec in zip(run_ids, records):
            print(f"run {rid} {rec.candidate_id} {rec.mode} errors={rec.errors}")
        return 0
    finally:
        core.get_chat_model = original


if __name__ == "__main__":
    raise SystemExit(main())
