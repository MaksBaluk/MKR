"""Build the evaluation report (report.json, report.csv, charts.json) from exported experiment runs.

Run from app/:
    uv run python scripts/evaluate_experiments.py --runs out/runs.json --relevance relevance.csv \
        --criteria criteria.csv --out report/ [--coverage-threshold 0.8] [--allow-synthetic-labels]

Label files are optional (CSV or JSON, see backend/experiments/expert_labels.py). Without labels the report has
data_status NO_EXPERT_LABELS and only the label-free metrics. SYNTHETIC_TEST_DATA labels are refused unless
--allow-synthetic-labels is given; such a report checks the pipeline only. Reads files only: no database, no model,
no network. Exit codes: 0 ok, 2 refused (missing or malformed runs/label files, synthetic labels without the flag,
an --out path that cannot be written); every refusal prints one `error: ...` line, never a traceback.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

if __package__ in (None, ""):  # direct `python scripts/evaluate_experiments.py`: make `backend` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.experiments.expert_labels import (DataStatus, LabelError, load_criterion_labels,  # noqa: E402
                                               load_relevance_labels)
from backend.experiments.report import ReportInputs, build_report, chart_data, write_report  # noqa: E402
from backend.experiments.store import load_exported_records  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--runs", required=True, type=Path, help="runs.json written by scripts/run_experiment.py")
    p.add_argument("--relevance", type=Path, default=None, help="relevance labels (final, adjudicated)")
    p.add_argument("--criteria", type=Path, default=None, help="criterion labels (final, adjudicated)")
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--coverage-threshold", type=float, default=0.8)
    p.add_argument("--min-labeled-vacancies", type=int, default=10)
    p.add_argument("--allow-synthetic-labels", action="store_true",
                   help="accept SYNTHETIC_TEST_DATA labels (pipeline check; method quality is not established)")
    return p


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    for name in ("runs", "relevance", "criteria"):
        path = getattr(args, name)
        if path is not None and not path.is_file():
            return _fail(f"--{name} file not found: {path}")
    try:
        records = load_exported_records(args.runs)
        relevance = load_relevance_labels(args.relevance) if args.relevance else None
        criteria = load_criterion_labels(args.criteria) if args.criteria else None
    except LabelError as exc:
        return _fail("invalid labels: " + "; ".join(exc.errors))
    except (ValueError, TypeError, OSError) as exc:  # json.JSONDecodeError is a ValueError
        return _fail(str(exc))
    synthetic = sum(lb.data_status is DataStatus.SYNTHETIC_TEST_DATA for lb in [*(relevance or []), *(criteria or [])])
    if synthetic and not args.allow_synthetic_labels:
        return _fail(f"{synthetic} label(s) are SYNTHETIC_TEST_DATA (test fixtures, not expert annotations); "
                     "pass --allow-synthetic-labels to build a pipeline-check report")
    try:
        report = build_report(ReportInputs(records, relevance, criteria, args.coverage_threshold,
                                           args.min_labeled_vacancies))
        charts = chart_data(report)
    except LabelError as exc:
        return _fail("invalid labels: " + "; ".join(exc.errors))
    except (KeyError, TypeError, AttributeError, ValueError) as exc:  # malformed runs.json content
        return _fail(f"cannot build report ({type(exc).__name__}): {exc}")
    try:
        write_report(report, charts, args.out)
    except OSError as exc:  # e.g. --out is an existing file
        return _fail(f"cannot write report to {args.out}: {exc}")
    print(f"report written to {args.out}")
    print(f"data_status: {report['data_status']}")
    print(report["quality_statement"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
