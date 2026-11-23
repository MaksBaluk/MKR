"""E6 latency split: deterministic components timed in-process on the frozen product code, separate from LLM time.

Setup (not timed): in-memory SQLite app seeded from fixtures, one product interview (mode D, budget 50, UaModel stub,
seed 0) per selected simulated candidate, so the timed functions see a realistic attempt. Timed with
time.perf_counter_ns, `--repeats` measurements per component and candidate after `--warmup` untimed calls:
  matching   - rank_vacancy (eval_group over every requirement group) for all 90 cohort vacancies, pure Python;
  ranking    - backend.domain.ranking.rank (lexicographic key 2.15) over the 90 VacancyRanking rows;
  results    - backend.api.recommendations.rank_items (DB reads + matching + ranking + explanations);
  estimator  - backend.domain.seniority.estimate on prepared evidence (pure);
  estimator_with_db - attempt_evidence (DB read) + estimate;
  market     - compute_market over the cohort (F(c), I(c)).
LLM latency is NOT measured: no local or production LLM call happened; stub interview time is not LLM latency.
Run from app/:  uv run python -m scripts.chapter4.timing_e6 [--repeats 200]  -> artifacts/chapter4/raw/timing_e6.json
"""
from __future__ import annotations

import argparse
import os
import platform
import statistics
import subprocess
import time

from scripts.chapter4.common import OUT, REPO, write_json


def _stats(ns: list[int]) -> dict:
    ms = sorted(x / 1e6 for x in ns)
    return {"n": len(ms), "median_ms": round(statistics.median(ms), 4),
            "p95_ms": round(ms[min(len(ms) - 1, int(round(0.95 * len(ms))) - 1)], 4),
            "min_ms": round(ms[0], 4), "max_ms": round(ms[-1], 4), "mean_ms": round(statistics.fmean(ms), 4)}


def _machine() -> dict:
    cpu = ""
    if platform.system() == "Darwin":
        cpu = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
    return {"platform": platform.platform(), "machine": platform.machine(), "cpu": cpu or platform.processor(),
            "logical_cpus": os.cpu_count(), "python": platform.python_version(),
            "db": "SQLite in-memory (StaticPool), seeded fixtures", "process": "single process, no parallel load"}


def build(repeats: int = 200, warmup: int = 10, candidates=("C02", "C09", "C15")) -> dict:
    import backend.api.core as core
    from backend.api.core import _revisions, cohort_actions, rubric_map
    from backend.api.cohorts import _market_input
    from backend.api.level import attempt_evidence
    from backend.api.recommendations import rank_items
    from backend.domain.core_flow import rank_vacancy
    from backend.domain.market import compute_market
    from backend.domain.ranking import rank as order
    from backend.domain.seniority import estimate
    from backend.domain.seniority_policy import policy_for
    from backend.experiments.config import InterviewMode, config_for
    from backend.experiments.runner import run_experiment
    from backend.models import CohortSnapshot
    from scripts.chapter4.candidate_model import BY_ID, TruthProvider
    from scripts.chapter4.modes_experiment import GOAL, PER_Q
    from scripts.chapter4.realistic_runs import UaModel
    from scripts.chapter4.scenarios import Env
    from scripts.seniority_realistic import Noise

    results: dict = {"components": {}, "per_candidate": {}}
    pooled: dict[str, list[int]] = {}
    with Env() as env:
        for pid in candidates:
            prof = BY_ID[pid]
            model = UaModel(PER_Q, GOAL, {}, Noise(0))
            original = core.get_chat_model
            core.get_chat_model = lambda: model
            t0 = time.perf_counter()
            try:
                rec = run_experiment("ch4-timing", config_for(InterviewMode.ADAPTIVE_INTERVIEW, total_budget=50),
                                     prof.spec(), TruthProvider(model, prof.candidate("insensitive")), env.client, env.db)
            finally:
                core.get_chat_model = original
            setup_s = time.perf_counter() - t0
            env.db.expire_all()
            snap = env.db.get(CohortSnapshot, rec.cohort_id)
            revs = _revisions(snap)
            by_id = {r["id"]: r for r in revs}
            scores = {a["criterion_id"]: a["score"] for a in rec.assessments}
            rubrics = rubric_map(env.db, cohort_actions(revs), scores)
            pol = policy_for(prof.track)
            evidence = attempt_evidence(env.db, rec.interview_id)
            vac = [{"id": v, "years_min": by_id[v]["years_min"], "groups": by_id[v]["groups"]} for v in snap.vacancy_ids]
            ranked = [rank_vacancy(v, scores, rubrics, prof.years) for v in vac]
            market_in = _market_input(revs)
            fns = {
                "matching": lambda: [rank_vacancy(v, scores, rubrics, prof.years) for v in vac],
                "ranking": lambda: order(ranked),
                "results": lambda: rank_items(env.db, prof.years, snap, scores),
                "estimator": lambda: estimate(pol, evidence),
                "estimator_with_db": lambda: estimate(pol, attempt_evidence(env.db, rec.interview_id)),
                "market": lambda: compute_market(market_in),
            }
            per = {"interview_setup_s_stub": round(setup_s, 3), "n_questions": len(rec.qa), "vacancies": len(vac)}
            for name, fn in fns.items():
                for _ in range(warmup):
                    fn()
                ns = []
                for _ in range(repeats):
                    s = time.perf_counter_ns()
                    fn()
                    ns.append(time.perf_counter_ns() - s)
                per[name] = _stats(ns)
                pooled.setdefault(name, []).extend(ns)
            results["per_candidate"][pid] = per
    results["components"] = {k: _stats(v) for k, v in pooled.items()}
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "app/backend", "app/fixtures"], cwd=REPO,
                           capture_output=True, text=True).stdout.strip()
    results.update({
        "experiment": "E6", "status": "MEASURED_DETERMINISTIC_ONLY", "repeats_per_candidate": repeats, "warmup": warmup,
        "candidates": list(candidates), "git_commit": commit, "product_tree_clean": not dirty,
        "product_code": "frozen 282f6fb (backend/fixtures unchanged since)", "machine": _machine(),
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "llm_latency": {"status": "NOT_RUN", "reason": "no local or production LLM was called; stub-interview time "
                        "(interview_setup_s_stub, experiment_runs.csv total_s) is not LLM latency"},
        "excluded": "pytest durations are not used as performance measurements"})
    write_json(OUT / "raw" / "timing_e6.json", results)
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=200)
    ap.add_argument("--warmup", type=int, default=10)
    a = ap.parse_args(argv)
    r = build(a.repeats, a.warmup)
    for k, v in r["components"].items():
        print(f"{k:18s} median {v['median_ms']:.3f} ms  p95 {v['p95_ms']:.3f} ms  n={v['n']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
