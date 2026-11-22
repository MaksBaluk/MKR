"""Rebuild every generated file of artifacts/chapter4/ (no real LLM, no network). Run from app/:
    uv run python -m scripts.chapter4.build_all [--with-sweep] [--workers N] [--allow-dirty]

Order: product-tree check -> dataset summary + environment -> math (E1) -> S01-S12 (Phase 1; rewrites
seniority_results.csv/interview_turns.jsonl with Phase-1 rows) -> modes experiment (SIMULATED A/B/C/D + ablation +
stub check) -> analysis (appends suite rows) -> adaptivity evidence -> data package -> E2-E5 metrics, tables, figures,
missing_evidence.md. --with-sweep adds the Phase-1 level sweeps (~12 min).
Hand-written files (implementation_snapshot.md, *_audit.md, test_results.md, failure_cases.md, annotation
instructions) are not touched; annotation files are never overwritten once they hold rows.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time

from scripts.chapter4.common import REPO


def product_tree_dirty() -> list[str]:
    out = subprocess.run(["git", "status", "--porcelain", "--", "app/backend", "app/fixtures", "app/alembic"],
                         cwd=REPO, capture_output=True, text=True).stdout
    return [line for line in out.splitlines() if line.strip()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-sweep", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true", help="run although product code has uncommitted changes")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args(argv)
    dirty = product_tree_dirty()
    if dirty and not args.allow_dirty:
        print("refusing: product code differs from HEAD (experiments must run on the frozen commit):\n" + "\n".join(dirty))
        return 2
    from scripts.chapter4 import (adaptivity_evidence, chapter4_metrics, data_package, dataset, environment,
                                  math_validation_ch4, modes_analysis, modes_experiment, seniority_scenarios_ch4)
    t0, steps = time.time(), {}

    def step(name, fn):
        s = time.time()
        fn()
        steps[name] = round(time.time() - s, 1)
        print(f"[{name}] {steps[name]} s", flush=True)

    step("dataset_summary", dataset.build)
    step("environment", environment.build)
    step("E1_math", math_validation_ch4.build)
    step("S01_S12", seniority_scenarios_ch4.main)
    if args.with_sweep:
        from scripts.chapter4 import seniority_sweep_ch4
        step("sweep", lambda: seniority_sweep_ch4.main([]))
        step("sweep_ua", lambda: seniority_sweep_ch4.main(["--stub-ua"]))
    step("modes_experiment", lambda: modes_experiment.main(["--workers", str(args.workers)]))
    step("modes_analysis", modes_analysis.build)
    step("adaptivity_evidence", adaptivity_evidence.build)
    step("data_package", data_package.build)
    step("E2_E5_metrics", chapter4_metrics.build)
    print(json.dumps({"total_s": round(time.time() - t0, 1), "steps": steps, "dirty_product_tree": dirty}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
