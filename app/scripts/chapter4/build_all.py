"""Rebuild every generated file of artifacts/chapter4/ (no real LLM, no network). Run from app/:
    uv run python -m scripts.chapter4.build_all [--with-sweep] [--with-timing] [--workers N] [--allow-dirty]
    uv run python -m scripts.chapter4.build_all --phase3-only [--with-timing]   # no re-simulation (~30 s)

Order: product-tree check -> dataset summary + environment -> math (E1) -> S01-S12 (Phase 1; rewrites
seniority_results.csv/interview_turns.jsonl with Phase-1 rows) -> modes experiment (SIMULATED A/B/C/D + ablation +
stub check) -> analysis (appends suite rows) -> adaptivity evidence -> data package -> phase 3: annotation merge (pilot
passes + third pass -> ADJUDICATED) -> E2-E5 metrics -> hypotheses, tables 4.1-4.7, figures, evidence report,
missing_evidence.md, self-audit (final_report). --phase3-only runs just the phase-3 steps on the stored runs.
--with-sweep adds the Phase-1 level sweeps (~12 min); --with-timing re-measures E6 (raw/timing_e6.json, ~20 s; the
measured values change between runs, everything else is byte-identical on rerun).
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


def phase3(step, args, annotation_merge, chapter4_metrics, final_report, timing_e6) -> None:
    step("annotation_merge", annotation_merge.build)
    step("E2_E5_metrics", chapter4_metrics.build)
    if args.with_timing:
        step("E6_timing", timing_e6.build)
    step("final_report", final_report.build)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-sweep", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true", help="run although product code has uncommitted changes")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--phase3-only", action="store_true", help="only annotation merge, metrics, tables, figures, report")
    ap.add_argument("--with-timing", action="store_true", help="re-measure E6 deterministic latencies")
    args = ap.parse_args(argv)
    dirty = product_tree_dirty()
    if dirty and not args.allow_dirty:
        print("refusing: product code differs from HEAD (experiments must run on the frozen commit):\n" + "\n".join(dirty))
        return 2
    from scripts.chapter4 import (adaptivity_evidence, annotation_merge, chapter4_metrics, data_package, dataset,
                                  environment, final_report, math_validation_ch4, modes_analysis, modes_experiment,
                                  seniority_scenarios_ch4, timing_e6)
    t0, steps = time.time(), {}

    def step(name, fn):
        s = time.time()
        fn()
        steps[name] = round(time.time() - s, 1)
        print(f"[{name}] {steps[name]} s", flush=True)

    if args.phase3_only:
        phase3(step, args, annotation_merge, chapter4_metrics, final_report, timing_e6)
        print(json.dumps({"total_s": round(time.time() - t0, 1), "steps": steps, "dirty_product_tree": dirty}))
        return 0
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
    phase3(step, args, annotation_merge, chapter4_metrics, final_report, timing_e6)
    print(json.dumps({"total_s": round(time.time() - t0, 1), "steps": steps, "dirty_product_tree": dirty}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
