"""Honesty guards for the evaluation pipeline: no quality claim without real expert labels."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import backend
from backend.experiments.report import ReportInputs, build_report, chart_data, write_report
from tests.test_experiment_report import ADAPTIVE, INITIAL, V, grades, rec, rel

APP = Path(backend.__file__).parent.parent


def test_report_never_claims_quality_without_expert_labels():
    r = build_report(ReportInputs([rec("c1", INITIAL), rec("c1", ADAPTIVE, sufficient=[["a"]])]))
    assert r["data_status"] == "NO_EXPERT_LABELS"
    assert "method quality is not established" in r["quality_statement"]
    for m in r["modes"].values():
        assert m["precision_at_5"] is None and m["ndcg_at_10"] is None
        assert m["precision_at_5_paired"] is None and m["ndcg_at_10_paired"] is None
        assert m["evaluator_mae"] is None
    assert "EXPERT labels" not in r["quality_statement"]


def test_synthetic_labels_are_flagged_everywhere(tmp_path):
    records = [rec("c1", INITIAL), rec("c1", ADAPTIVE, sufficient=[["a"]])]
    r = build_report(ReportInputs(records, rel("c1", grades({"v00": 3}, keys=V))))
    charts = chart_data(r)
    write_report(r, charts, tmp_path)
    assert r["data_status"] == "SYNTHETIC_TEST_DATA"
    assert "method quality is not established" in r["quality_statement"]
    on_disk = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert on_disk["data_status"] == "SYNTHETIC_TEST_DATA"
    with open(tmp_path / "report.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows and {row["data_status"] for row in rows} == {"SYNTHETIC_TEST_DATA"}
    saved = json.loads((tmp_path / "charts.json").read_text(encoding="utf-8"))
    assert saved and all(c["data_status"] == "SYNTHETIC_TEST_DATA" for c in charts.values())
    assert all(c["data_status"] == "SYNTHETIC_TEST_DATA" for c in saved.values())


def test_label_templates_contain_no_labels():
    files = sorted((APP / "experiments" / "templates").glob("*.csv"))
    assert {f.name for f in files} == {"criterion_labels.csv", "relevance_labels.csv"}
    for f in files:
        lines = [ln for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 1, f"{f.name} must be header-only"
        assert lines[0].startswith("candidate_id")


def test_no_label_fixture_marked_expert_outside_tests():
    files = [p for root in ("experiments", "fixtures") for p in (APP / root).rglob("*")
             if p.is_file() and p.suffix in {".csv", ".json", ".jsonl", ".md"}]
    assert len(files) >= 6  # non-vacuous: templates + fixtures are scanned
    offenders = []
    for p in files:
        text = p.read_text(encoding="utf-8")
        if p.suffix == ".md":
            continue  # documentation may name the EXPERT status
        if '"data_status": "EXPERT"' in text or '"data_status":"EXPERT"' in text:
            offenders.append(p.name)
        if p.suffix == ".csv":
            rows = list(csv.DictReader(text.splitlines()))
            if any(row.get("data_status") == "EXPERT" for row in rows):
                offenders.append(p.name)
    assert offenders == []
