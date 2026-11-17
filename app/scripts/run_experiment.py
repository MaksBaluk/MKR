"""Run interview-mode experiments (A: INITIAL_PROFILE, B: STATIC_INTERVIEW, C: ADAPTIVE_INTERVIEW) on a separate DB.

Run from app/:
    uv run python scripts/run_experiment.py --db sqlite:///experiments.db --candidates candidates.json \
        --answers answers.json --modes INITIAL_PROFILE STATIC_INTERVIEW ADAPTIVE_INTERVIEW \
        --llm configured --total-budget 12 --out out/

--db is required and must be a SQLite URL: the schema is created and the catalog seeded there (like the tests),
the product database is never used. --modes defaults to INITIAL_PROFILE (no LLM). Interview modes need an explicit
--llm choice: `configured` sends questions, scripted answers, vacancy and rubric text to the provider configured in
the server settings (LLM_PROVIDER, LLM_MODEL, ...); `none` uses no model and needs --allow-ungraded (answers are then
stored UNGRADED). STATIC and ADAPTIVE together need an explicit --total-budget (equal question budgets).
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
from sqlalchemy.engine import make_url  # noqa: E402
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


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {text!r}") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1: {value}")
    return value


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--db", required=True, help="sqlite URL of a separate experiment database (required)")
    p.add_argument("--candidates", required=True, type=Path, help="JSON list of CandidateSpec objects")
    p.add_argument("--answers", required=True, type=Path, help="ScriptedProvider JSON file")
    p.add_argument("--modes", nargs="+", choices=[m.value for m in InterviewMode],
                   default=[InterviewMode.INITIAL_PROFILE.value])
    p.add_argument("--flags", nargs="*", choices=sorted(FLAGS), default=None,
                   help="ablations for ADAPTIVE_INTERVIEW (STATIC always has all adaptive flags off)")
    p.add_argument("--total-budget", type=_positive_int, default=None, help="max shown questions per interview")
    p.add_argument("--llm", choices=["configured", "none"], default=None,
                   help="required for interview modes: use the configured provider, or no model")
    p.add_argument("--experiment-id", default=None)
    p.add_argument("--allow-ungraded", action="store_true", help="with --llm none: store answers ungraded")
    p.add_argument("--out", required=True, type=Path)
    return p


def _config(mode: InterviewMode, flags: Sequence[str], total_budget: int | None):
    if mode is InterviewMode.ADAPTIVE_INTERVIEW:
        return config_for(mode, total_budget=total_budget, **{FLAGS[f]: False for f in flags})
    return config_for(mode, total_budget=total_budget)


def _sqlite_target(url: str) -> str | None:
    """Resolved file path of a sqlite URL, ":memory:" for in-memory, None when not sqlite (or unparsable)."""
    try:
        u = make_url(url)
    except Exception:  # noqa: BLE001 - any unparsable URL is simply refused
        return None
    if u.get_backend_name() != "sqlite":
        return None
    db = u.database or ""
    return ":memory:" if db in ("", ":memory:") else str(Path(db).expanduser().resolve())


def _db_error(url: str) -> str | None:
    target = _sqlite_target(url)
    if target is None:
        return "--db must be a sqlite URL"
    product = get_settings().database_url
    if _sqlite_target(product) == target or url == product:  # same file under any spelling, or both in-memory
        return "--db resolves to the product database configured in settings; use a separate file"
    return None


def _args_error(args, modes: list[InterviewMode]) -> str | None:
    """Checks that need no model call and no DB access."""
    problem = _db_error(args.db)
    if problem:
        return problem
    interviewing = any(m is not InterviewMode.INITIAL_PROFILE for m in modes)
    if args.flags is not None and InterviewMode.ADAPTIVE_INTERVIEW not in modes:
        return "--flags apply only to ADAPTIVE_INTERVIEW; add it to --modes"
    if InterviewMode.STATIC_INTERVIEW in modes and InterviewMode.ADAPTIVE_INTERVIEW in modes \
            and args.total_budget is None:
        return "comparing STATIC_INTERVIEW and ADAPTIVE_INTERVIEW needs an explicit --total-budget"
    if interviewing and args.llm is None:
        return ("interview modes need --llm configured (sends questions, answers, vacancy and rubric text to the "
                "configured provider) or --llm none --allow-ungraded")
    if interviewing and args.llm == "none" and not args.allow_ungraded:
        return "--llm none stores answers ungraded; pass --allow-ungraded to confirm"
    return None


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 2


def main(argv: Sequence[str] | None = None, model_factory: Callable[[], object] | None = None) -> int:
    """model_factory: test hook replacing the configured chat model for this call only (no env, no network).
    Exit codes: 0 ok, 1 some runs failed (the rest are exported), 2 refused before any run."""
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:  # argparse already printed "error: ..." (or --help)
        return int(exc.code or 0)
    modes = [InterviewMode(m) for m in dict.fromkeys(args.modes)]
    problem = _args_error(args, modes)
    if problem:
        return _fail(problem)
    try:
        configs = [_config(m, args.flags or [], args.total_budget) for m in modes]
    except ValueError as exc:
        return _fail(f"invalid experiment config: {exc}")
    interviewing = any(m is not InterviewMode.INITIAL_PROFILE for m in modes)
    original = core.get_chat_model
    if interviewing and args.llm == "none":
        core.get_chat_model = lambda: None  # no model at all: questions from the bank, answers UNGRADED
    elif model_factory is not None:
        core.get_chat_model = model_factory
    try:
        if interviewing and args.llm == "configured":
            model = core.get_chat_model()
            if model is None:
                return _fail("--llm configured but no LLM is configured in settings (LLM_PROVIDER/LLM_API_KEY)")
            s = get_settings()
            # provider and model name only: never the key or the base URL
            print(f"llm: provider=injected model={type(model).__name__}" if model_factory is not None
                  else f"llm: provider={s.llm_provider} model={s.llm_model}")
        elif interviewing:
            print("llm: none (answers stored UNGRADED)")
        candidates = [CandidateSpec.from_json(d) for d in json.loads(args.candidates.read_text(encoding="utf-8"))]
        provider = ScriptedProvider.from_file(args.answers)
        memory = _sqlite_target(args.db) == ":memory:"  # one shared connection, else each session sees an empty DB
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
        records, run_ids, failures = [], [], []
        try:
            with TestClient(app) as client, Session() as db:
                for cand in candidates:
                    for cfg in configs:
                        try:  # one failing run must not discard the batch
                            rec = run_experiment(experiment_id, cfg, cand, provider, client, db)
                            run_ids.append(save_record(db, rec))
                            records.append(rec)
                        except Exception as exc:  # noqa: BLE001 - reported below, exit code non-zero
                            db.rollback()
                            failures.append(f"{cand.candidate_id} {cfg.mode.value}: {type(exc).__name__}: {exc}")
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(saved)
            engine.dispose()
        export_records(records, args.out)
        print(f"experiment {experiment_id}: {len(records)} runs written to {args.out}")
        for rid, rec in zip(run_ids, records):
            print(f"run {rid} {rec.candidate_id} {rec.mode} errors={rec.errors}")
        for f in failures:
            print(f"FAILED {f}")
        return 1 if failures else 0
    finally:
        core.get_chat_model = original


if __name__ == "__main__":
    raise SystemExit(main())
