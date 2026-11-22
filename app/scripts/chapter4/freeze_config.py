"""Freeze the chapter-4 experiment configuration (Stage 1) into artifacts/chapter4/experiment_manifest.json.

Writes `frozen_config` (commit, dataset snapshot hashes, cohort digest per track on a fresh seed, rubric versions,
level policy and its digest, difficulty controller, prompt version, budgets, LLM settings without secrets) and keeps an
existing `runs` list untouched, so Phase 2 appends its runs under the same frozen configuration. The previous package's
manifest (older code) is kept only as a summary under `superseded_previous_package`.

Run from app/:  uv run python -m scripts.chapter4.freeze_config
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import time

from scripts.chapter4.common import APP, OUT, REPO, sh, write_json
from scripts.chapter4.environment import env_settings
from backend.api.cohorts import POLICY_ID, _vacancy_revisions
from backend.api.common import freeze_payload
from backend.domain.core_flow import TAU_BY_LEVEL, TAU_SOURCE_LEVEL_MAP
from backend.domain.difficulty import DEFAULT_CONFIG
from backend.domain.interview_budget import MAX_SHOWN_QUESTIONS_PER_ACTION, MAX_TOPICS, MIN_SHOWN_QUESTIONS_PER_ACTION
from backend.domain.seniority_policy import MIN_CONFIRMING_TURNS, POLICY_VERSIONS, policy_for
from backend.domain.topic_summary import CONFIRMED_SCORE, MIN_COVERAGE_FOR_OVERALL
from backend.experiments.runner import ALGORITHM_VERSION, prompt_version
from backend.seed import read_fixture

FIXTURES = ("vacancies.json", "vacancies_real.json", "vacancy_criteria.json", "vacancy_sources.json", "rubrics.json",
            "practice_rubrics.json", "competencies.json", "questions.json")


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _policy_digest(p) -> str:
    return hashlib.sha256(json.dumps(dataclasses.asdict(p), sort_keys=True, default=str).encode()).hexdigest()


def cohort_digests() -> dict:
    """sha256 of the frozen auto-cohort payload per track on a fresh seed (same code path as POST /cohorts/auto)."""
    from scripts.chapter4.scenarios import Env
    out = {}
    with Env() as env:
        for track in ("python", "marketing", "design"):
            revs = _vacancy_revisions(env.db, track)
            _, digest = freeze_payload(revs)
            out[track] = {"vacancies": len(revs), "sha256": digest,
                          "requirement_alternatives": sum(len(g["alternatives"]) for v in revs for g in v["groups"])}
    return out


def frozen_config() -> dict:
    files = {f: _sha(APP / "fixtures" / f) for f in FIXTURES}
    dataset = hashlib.sha256("".join(f"{k}:{v}\n" for k, v in sorted(files.items())).encode()).hexdigest()
    rubrics = read_fixture("rubrics.json")["rubrics"] + read_fixture("practice_rubrics.json")["rubrics"]
    cur = policy_for("python")
    s = env_settings()
    return {
        "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "commit": sh("git", "rev-parse", "HEAD"), "branch": sh("git", "branch", "--show-current"),
        "working_tree_clean_at_freeze": sh("git", "status", "--porcelain", "--", "app/backend", "app/frontend/src",
                                           "app/fixtures", "app/alembic") == "",
        "dataset_snapshot": {"sha256": dataset, "files": files,
                             "note": "Походження вакансій наведено за приміткою власника про дані; технічні метадані "
                                     "імпорту збережені в репозиторії (поля import_version, retrieved_at, source_name). "
                                     "tau WORKING_ASSUMPTION_LEVEL_MAP"},
        "cohorts_fresh_seed": cohort_digests(), "cohort_policy": POLICY_ID,
        "rubric_versions": sorted({f"{r['action_id']}:{r['version']}:{r['source']}" for r in rubrics}),
        "rubric_count": len(rubrics), "criterion_count": sum(len(r["criteria"]) for r in rubrics),
        "seniority_policy": {"current_python": f"{cur.policy_id}/{cur.version}", "status": cur.status,
                             "sha256": _policy_digest(cur), "min_confirming_turns": MIN_CONFIRMING_TURNS,
                             "addressable_versions": [f"{p}/{v}" for p, v in POLICY_VERSIONS],
                             "marketing": None, "design": None},
        "scoring_policy": {"confirmed_score": CONFIRMED_SCORE, "min_coverage_for_overall": MIN_COVERAGE_FOR_OVERALL,
                           "tau_by_level": TAU_BY_LEVEL, "tau_source": TAU_SOURCE_LEVEL_MAP,
                           "epsilon": "min(0.05, tau/2)"},
        "difficulty_controller": dataclasses.asdict(DEFAULT_CONFIG),
        "ranking": {"algorithm_version": ALGORITHM_VERSION, "experiments_and_recommendations": "pure (2.15)+T_v/J_v+id",
                    "results_screen": "confirmed_share first (owner decision, deviation from (2.15))"},
        "prompt_version": prompt_version(),
        "interview_limits": {"max_topics": MAX_TOPICS, "max_questions_per_topic": MAX_SHOWN_QUESTIONS_PER_ACTION,
                             "min_questions_per_open_topic": MIN_SHOWN_QUESTIONS_PER_ACTION,
                             "total_budget": "experiment-specific (set per run)"},
        "llm": {"configured_provider": s.get("LLM_PROVIDER"), "configured_model": s.get("LLM_MODEL"),
                "temperature": 0.3, "max_retries_client": 0, "evaluator_validation_retry": 1,
                "timeout_s": s.get("LLM_TIMEOUT_SECONDS"),
                "used_in_phase1": "none (SIMULATED stubs only; configured endpoint unreachable: connection refused)"},
    }


def main() -> int:
    path = OUT / "experiment_manifest.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    superseded = old.get("superseded_previous_package") or (
        {k: old.get(k) for k in ("generated", "kind", "prompt_version", "run_count", "algorithm_version", "command")}
        | {"note": "produced on older code (before policy v4, WP-B, WS-1); not comparable on prompts; regenerate"}
        if old and "frozen_config" not in old else None)
    manifest = {"schema": "ch4-manifest/v2", "frozen_config": frozen_config(),
                "phase1_evidence": old.get("phase1_evidence", []), "runs": old.get("runs", []),
                "superseded_previous_package": superseded}
    write_json(path, manifest)
    print(json.dumps({k: manifest["frozen_config"][k] for k in ("commit", "prompt_version")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
