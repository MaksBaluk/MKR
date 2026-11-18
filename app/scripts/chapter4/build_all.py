"""Rebuild every generated file of artifacts/chapter4/ (no real LLM, no network). Run from app/:
    uv run python -m scripts.chapter4.build_all
Hand-written files (test_results.md, failure_cases.md, annotation protocol) are not touched."""
from __future__ import annotations

import shutil

from scripts import evaluate_experiments
from scripts.chapter4 import dataset, environment, experiments, math_validation, report, scenarios
from scripts.chapter4.common import APP, OUT


def main() -> int:
    dataset.build()
    math_validation.build()
    manifest = experiments.build()
    code = evaluate_experiments.main(["--runs", str(OUT / "raw" / "runs.json"), "--out", str(OUT / "evaluation_report")])
    if code != 0:
        return code
    shutil.copy(OUT / "evaluation_report" / "report.csv", OUT / "evaluation_metrics.csv")
    scenarios.build()
    tmpl = OUT / "expert_annotation_templates"
    tmpl.mkdir(parents=True, exist_ok=True)
    for f in (APP / "experiments" / "templates").iterdir():
        shutil.copy(f, tmpl / f.name)
    environment.build()
    (OUT / "chapter4_evidence_report.md").write_text(report.build(), encoding="utf-8")
    print("ok: run_count", manifest["run_count"], "reproducible", manifest["reproducibility"]["identical"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
