"""Evaluation report, chart datasets and the evaluate_experiments CLI.

Every label built here is a test fixture, not an expert annotation. Labels marked EXPERT exist only inside this
file to exercise the EXPERT code path."""
import csv
import json
import math
from dataclasses import asdict

import pytest

from backend.experiments.config import InterviewMode, config_for
from backend.experiments.expert_labels import ExpertCriterionLabel, ExpertRelevanceLabel, LabelError
from backend.experiments.report import (CHART_KEYS, REPORT_CSV_FIELDS, ReportInputs, build_report, chart_data,
                                        mode_key, write_report)
from backend.experiments.store import ExperimentRecord, export_records, load_exported_records
from scripts.evaluate_experiments import main

INITIAL = InterviewMode.INITIAL_PROFILE
STATIC = InterviewMode.STATIC_INTERVIEW
ADAPTIVE = InterviewMode.ADAPTIVE_INTERVIEW
V = [f"v{i:02d}" for i in range(12)]


def rec(cid, mode=ADAPTIVE, ranking=V, sufficient=(), relevant=("a", "b", "c", "d"), errors=None, timings=None,
        assessments=(), rubric_versions=None, source="SCRIPTED", **flags):
    cfg = config_for(mode, **flags)
    return ExperimentRecord(
        experiment_id="exp-t", candidate_id=cid, mode=mode.value, config=cfg.to_json(), cohort_id="coh",
        cohort_sha256="sha", profile_snapshot={}, rubric_versions=rubric_versions or {}, prompt_version="p",
        model_info={}, algorithm_version="alg",
        qa=[{"action_id": "A", "sufficient_criteria_after": list(s)} for s in sufficient],
        assessments=list(assessments),
        ranking=[{"vacancy_id": v, "unknown_count": 1, "groups_total": 4} for v in ranking],
        timings=timings or {"total_s": 10.0, "llm_wait_s": 4.0, "calls": 2},
        errors=errors or {"ungraded_answers": 0, "fallback_questions": 0, "llm_exceptions": 0,
                          "evaluator_rejections": 0, "empty_cohort": False, "criteria_outside_relevant": []},
        answer_source=source if mode is not INITIAL else "NONE", relevant_criteria=list(relevant))


def rel(cid, grades, status="SYNTHETIC_TEST_DATA", review="ADJUDICATED", ann="adj"):
    return [ExpertRelevanceLabel(candidate_id=cid, vacancy_id=v, grade=g, rationale="fixture rationale",
                                 annotator_id=ann, label_version="t1", data_status=status, review_status=review)
            for v, g in grades.items()]


def crit(cid, action, criterion, score, version="v1", status="SYNTHETIC_TEST_DATA", review="ADJUDICATED"):
    return ExpertCriterionLabel(candidate_id=cid, action_id=action, criterion_id=criterion, rubric_version=version,
                                expert_score=score, evidence_reference="answer 1" if score is not None else "",
                                annotator_id="adj", label_version="t1", data_status=status, review_status=review)


def grades(top, default=0, keys=V):
    return {v: top.get(v, default) for v in keys}


# --- (a) no labels -----------------------------------------------------------------------------------------------

def test_no_labels_gives_label_free_metrics_and_honest_status():
    r = build_report(ReportInputs([rec("c1", sufficient=[["a"], ["a", "b"]]), rec("c1", INITIAL, sufficient=[])]))
    assert r["data_status"] == "NO_EXPERT_LABELS"
    assert "method quality is not established" in r["quality_statement"]
    assert "SCRIPTED" in r["quality_statement"] and "not evidence of real-candidate performance" in r["quality_statement"]
    assert list(r["modes"]) == ["INITIAL_PROFILE", "ADAPTIVE_INTERVIEW"] and r["answer_sources"] == ["NONE", "SCRIPTED"]
    m = r["modes"]["ADAPTIVE_INTERVIEW"]
    assert m["precision_at_5"] is None and m["ndcg_at_10"] is None and m["evaluator_mae"] is None
    assert m["n_included"] == 0 and m["n_excluded_lt_10_labeled"] == 0
    assert m["criterion_coverage_mean"] == pytest.approx(0.5) and m["questions_mean"] == 2
    assert m["unresolved_requirements_rate_mean"] == pytest.approx(0.25)
    assert m["duration"] == {"total_s_mean": 10.0, "llm_wait_s_mean": 4.0, "excluding_llm_s_mean": 6.0}
    assert r["modes"]["INITIAL_PROFILE"]["criterion_coverage_mean"] == 0.0  # nothing evidenced without answers


# --- (c) hand-computed ranking metrics, exclusions ----------------------------------------------------------------

def test_hand_computed_ranking_means_and_exclusions():
    c1 = grades({"v00": 3, "v01": 3})
    c2 = grades({"v00": 2})
    c3 = {v: 3 for v in V[:9]}  # only 9 labelled vacancies
    c4 = {v: 1 for v in V if v != "v10"}  # v10 unlabelled and ranked 3rd
    static_c1 = V[2:10] + ["v00", "v01"] + V[10:]
    records = [rec("c1", ADAPTIVE, V), rec("c1", STATIC, static_c1),
               rec("c2", ADAPTIVE, ["v01", "v00"] + V[2:]), rec("c2", STATIC, V),
               rec("c3", ADAPTIVE, V), rec("c3", STATIC, V),
               rec("c4", ADAPTIVE, ["v00", "v01", "v10"] + V[2:10] + ["v11"]), rec("c4", STATIC, V)]
    labels = rel("c1", c1) + rel("c2", c2) + rel("c3", c3) + rel("c4", c4)
    r = build_report(ReportInputs(records, labels))
    a, s = r["modes"]["ADAPTIVE_INTERVIEW"], r["modes"]["STATIC_INTERVIEW"]
    # ADAPTIVE: c1 P@5 = 2/5, NDCG = 1; c2 P@5 = 1/5, NDCG = (2/log2 3) / 2
    assert a["precision_at_5"] == pytest.approx((0.4 + 0.2) / 2)
    assert a["ndcg_at_10"] == pytest.approx((1 + 1 / math.log2(3)) / 2)
    # STATIC: c1 relevant at ranks 9 and 10: DCG = 3/log2 10 + 3/log2 11, ideal = 3 + 3/log2 3; c2 perfect
    # c4 STATIC: v10 is 11th, so the top 10 is fully labelled; all grade 1 -> P@5 0, NDCG 1
    ndcg_c1 = (3 / math.log2(10) + 3 / math.log2(11)) / (3 + 3 / math.log2(3))
    assert s["precision_at_5"] == pytest.approx((0.0 + 0.2 + 0.0) / 3)
    assert s["ndcg_at_10"] == pytest.approx((ndcg_c1 + 1.0 + 1.0) / 3)
    assert a["n_included"] == 2 and a["n_excluded_lt_10_labeled"] == 1 and a["n_excluded_unlabeled_in_top"] == 1
    assert s["n_included"] == 3 and s["n_excluded_unlabeled_in_top"] == 0
    ex = r["excluded_candidates"]
    assert ex["lt_min_labeled"] == {"STATIC_INTERVIEW": ["c3"], "ADAPTIVE_INTERVIEW": ["c3"]}
    assert ex["unlabeled_in_top"]["ADAPTIVE_INTERVIEW"] == {"c4": ["v10"]}
    assert "too few labelled vacancies" in r["quality_statement"]
    assert r["data_status"] == "SYNTHETIC_TEST_DATA" and "method quality is not established" in r["quality_statement"]


def test_static_mean_with_included_unlabeled_tail_candidate():
    """c4 in STATIC: all-grade-1 labels -> P@5 0, NDCG 1 (ideal ranking of all-ones)."""
    c4 = {v: 1 for v in V if v != "v10"}
    r = build_report(ReportInputs([rec("c4", STATIC, V)], rel("c4", c4)))
    m = r["modes"]["STATIC_INTERVIEW"]
    assert m["precision_at_5"] == 0.0 and m["ndcg_at_10"] == pytest.approx(1.0) and m["n_included"] == 1


def test_all_zero_labels_ndcg_undefined_p5_counted():
    r = build_report(ReportInputs([rec("c5", ADAPTIVE, V)], rel("c5", grades({}))))
    m = r["modes"]["ADAPTIVE_INTERVIEW"]
    assert m["precision_at_5"] == 0.0 and m["ndcg_at_10"] is None and m["n_ndcg_undefined"] == 1
    assert "undefined" in r["quality_statement"] and r["excluded_candidates"]["ndcg_undefined"]["ADAPTIVE_INTERVIEW"] == ["c5"]


def test_labels_outside_ranked_cohort_do_not_count():
    labels = rel("c1", {**grades({"v00": 3}, keys=V[:9]), "x1": 3, "x2": 3})  # 11 labels, only 9 in the cohort
    m = build_report(ReportInputs([rec("c1")], labels))["modes"]["ADAPTIVE_INTERVIEW"]
    assert m["n_excluded_lt_10_labeled"] == 1 and m["precision_at_5"] is None


def test_min_labeled_vacancies_configurable():
    m = build_report(ReportInputs([rec("c3")], rel("c3", {v: 3 for v in V[:9]}), min_labeled_vacancies=5))
    assert m["modes"]["ADAPTIVE_INTERVIEW"]["n_included"] == 0  # v09.. unlabeled in top 10
    assert m["modes"]["ADAPTIVE_INTERVIEW"]["n_excluded_unlabeled_in_top"] == 1


# --- coverage / errors / MAE --------------------------------------------------------------------------------------

def test_coverage_errors_and_duration_hand_values():
    errs = {"ungraded_answers": 1, "fallback_questions": 2, "llm_exceptions": 3, "evaluator_rejections": 4,
            "empty_cohort": False, "criteria_outside_relevant": ["zz"]}
    records = [rec("c1", sufficient=[["a"], ["a", "b"], ["a", "b", "c", "d"]], errors=errs),
               rec("c2", sufficient=[["a"]], timings={"total_s": 2.0, "llm_wait_s": 3.0}),
               rec("c3", sufficient=[[]], relevant=())]
    m = build_report(ReportInputs(records))["modes"]["ADAPTIVE_INTERVIEW"]
    assert m["criterion_coverage_mean"] == pytest.approx((1.0 + 0.25) / 2)
    assert m["questions_to_coverage_mean"] == 3 and m["n_reached"] == 1
    assert m["n_excluded_no_relevant_criteria"] == 1 and m["llm_errors"] == 10
    assert m["questions_mean"] == pytest.approx(5 / 3)
    assert m["duration"]["excluding_llm_s_mean"] == pytest.approx((6.0 + 0.0 + 6.0) / 3)
    charts = chart_data(build_report(ReportInputs(records)))
    pts = charts["coverage_vs_questions"]["data"]["ADAPTIVE_INTERVIEW"]
    assert [p["n_questions"] for p in pts] == [0, 1, 2, 3]
    assert [p["coverage_mean"] for p in pts] == pytest.approx([0.0, 0.25, 0.375, 0.625])
    assert {p["n_candidates"] for p in pts} == {2}


def test_threshold_changes_questions_to_coverage():
    records = [rec("c1", sufficient=[["a"], ["a", "b"], ["a", "b", "c", "d"]])]
    assert build_report(ReportInputs(records, coverage_threshold=0.5))["modes"]["ADAPTIVE_INTERVIEW"][
        "questions_to_coverage_mean"] == 2
    with pytest.raises(ValueError):
        build_report(ReportInputs(records, coverage_threshold=0))


def test_evaluator_mae_pooled_and_by_criterion():
    assess = [{"action_id": "A", "criterion_id": "A.1", "score": 0.8},
              {"action_id": "A", "criterion_id": "A.2", "score": None},
              {"action_id": "A", "criterion_id": "A.3", "score": 0.5},
              {"action_id": "B", "criterion_id": "B.1", "score": 0.4}]
    labels = [crit("c1", "A", "A.1", 0.6), crit("c1", "A", "A.2", 0.9), crit("c1", "A", "A.3", None),
              crit("c1", "B", "B.1", 0.1, version="old")]
    r = build_report(ReportInputs([rec("c1", assessments=assess, rubric_versions={"A": "v1", "B": "v2"})],
                                  criteria=labels))
    mae = r["modes"]["ADAPTIVE_INTERVIEW"]["evaluator_mae"]
    assert mae["mae"] == pytest.approx(0.2) and mae["n_compared"] == 1
    assert (mae["n_evaluator_unknown"], mae["n_expert_unknown"], mae["n_missing_expert"]) == (1, 1, 1)
    assert mae["n_rubric_version_mismatch"] == 1
    rows = chart_data(r)["evaluator_quality_by_criterion"]["data"]
    assert [(x["criterion_id"], x["n_compared"]) for x in rows] == [("A.1", 1), ("A.2", 0), ("A.3", 0), ("B.1", 0)]
    assert rows[0]["mae"] == pytest.approx(0.2) and rows[1]["mae"] is None
    assert r["modes"]["ADAPTIVE_INTERVIEW"]["precision_at_5"] is None  # no relevance labels
    assert "No relevance labels were supplied" in r["quality_statement"]


# --- (d) mode keys -------------------------------------------------------------------------------------------------

def test_ablation_mode_keys_distinct():
    records = [rec("c1", STATIC), rec("c1", ADAPTIVE), rec("c1", ADAPTIVE, adaptive_followup=False),
               rec("c1", ADAPTIVE, adaptive_topics=False, adaptive_difficulty=False), rec("c1", INITIAL)]
    keys = [mode_key(r) for r in records]
    assert keys == ["STATIC_INTERVIEW", "ADAPTIVE_INTERVIEW", "ADAPTIVE_INTERVIEW-followup",
                    "ADAPTIVE_INTERVIEW-topics-difficulty", "INITIAL_PROFILE"]
    assert list(build_report(ReportInputs(records))["modes"]) == [
        "INITIAL_PROFILE", "STATIC_INTERVIEW", "ADAPTIVE_INTERVIEW", "ADAPTIVE_INTERVIEW-followup",
        "ADAPTIVE_INTERVIEW-topics-difficulty"]


def test_duplicate_candidate_or_mixed_config_in_mode_rejected():
    with pytest.raises(ValueError, match="more than once"):
        build_report(ReportInputs([rec("c1"), rec("c1")]))
    with pytest.raises(ValueError, match="different configs"):
        build_report(ReportInputs([rec("c1", total_budget=4), rec("c2", total_budget=6)]))


def test_candidates_matched_across_modes():
    r = build_report(ReportInputs([rec("c1", STATIC), rec("c1", ADAPTIVE), rec("c2", ADAPTIVE)]))
    assert r["excluded_candidates"]["missing_in_modes"] == {"c2": ["STATIC_INTERVIEW"]}
    q = chart_data(r)["questions_static_vs_adaptive"]["data"]
    assert [x["candidate_id"] for x in q] == ["c1"]


# --- (e) chart shapes ----------------------------------------------------------------------------------------------

def test_chart_keys_and_shapes():
    records = [rec("c1", STATIC, sufficient=[["a"], ["a", "b", "c", "d"]]),
               rec("c1", ADAPTIVE, sufficient=[["a", "b", "c", "d"]])]
    labels = rel("c1", grades({"v00": 3}))
    r = build_report(ReportInputs(records, labels, [crit("c1", "A", "A.1", 0.5)]))
    charts = chart_data(r)
    assert tuple(charts) == CHART_KEYS
    assert all(set(c) == {"data_status", "data"} and c["data_status"] == "SYNTHETIC_TEST_DATA" for c in charts.values())
    assert all(set(x) >= {"mode", "precision_at_5", "ndcg_at_10"} for x in charts["ranking_by_mode"]["data"])
    assert set(charts["coverage_vs_questions"]["data"]) == {"STATIC_INTERVIEW", "ADAPTIVE_INTERVIEW"}
    assert all(set(p) >= {"n_questions", "coverage_mean"} for pts in charts["coverage_vs_questions"]["data"].values()
               for p in pts)
    assert charts["questions_static_vs_adaptive"]["data"] == [
        {"candidate_id": "c1", "static": 2, "adaptive": 1, "static_asked": 2, "adaptive_asked": 1}]
    assert charts["evaluator_quality_by_criterion"]["data"] == []  # no assessments in these records


# --- (f) files -----------------------------------------------------------------------------------------------------

def test_write_report_files_reload_equal(tmp_path):
    records = [rec("c1", INITIAL), rec("c1", STATIC, sufficient=[["a"]]), rec("c1", ADAPTIVE, sufficient=[["a"]])]
    r = build_report(ReportInputs(records, rel("c1", grades({"v00": 3}))))
    charts = chart_data(r)
    write_report(r, charts, tmp_path / "rep")
    assert json.loads((tmp_path / "rep" / "report.json").read_text(encoding="utf-8")) == r
    assert json.loads((tmp_path / "rep" / "charts.json").read_text(encoding="utf-8")) == charts
    with open(tmp_path / "rep" / "report.csv", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert reader.fieldnames == REPORT_CSV_FIELDS
    assert [row["mode"] for row in rows] == list(r["modes"])
    for row in rows:
        m = r["modes"][row["mode"]]
        assert row["data_status"] == "SYNTHETIC_TEST_DATA" and int(row["n_candidates"]) == m["n_candidates"]
        assert float(row["precision_at_5"]) == pytest.approx(m["precision_at_5"])
        assert json.loads(row["config"]) == m["config"] and row["mae"] == ""  # None stays empty, never 0


# --- (g) old-style records -------------------------------------------------------------------------------------------

def test_old_style_records_without_relevant_criteria(tmp_path):
    old = asdict(rec("c1", sufficient=[["a"]]))
    del old["relevant_criteria"]
    for q in old["qa"]:
        del q["sufficient_criteria_after"]
    (tmp_path / "runs.json").write_text(json.dumps([old]), encoding="utf-8")
    loaded = load_exported_records(tmp_path / "runs.json")
    assert loaded[0].relevant_criteria == []
    r = build_report(ReportInputs(loaded))
    m = r["modes"]["ADAPTIVE_INTERVIEW"]
    assert m["criterion_coverage_mean"] is None and m["questions_to_coverage_mean"] is None and m["n_reached"] == 0
    assert m["n_excluded_no_relevant_criteria"] == 1 and "without relevant_criteria" in r["quality_statement"]
    assert chart_data(r)["coverage_vs_questions"]["data"]["ADAPTIVE_INTERVIEW"] == []


def test_load_exported_records_rejects_bad_input(tmp_path):
    p = tmp_path / "runs.json"
    p.write_text(json.dumps({"x": 1}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_exported_records(p)
    p.write_text(json.dumps([{**asdict(rec("c1")), "bogus": 1}]), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown keys"):
        load_exported_records(p)


# --- (i) EXPERT path, adjudication, mixing ---------------------------------------------------------------------------

def test_expert_adjudicated_labels_give_expert_status():
    """Test fixtures only: hand-made labels marked EXPERT exercise the EXPERT path; they are not real annotations."""
    labels = rel("c1", grades({"v00": 3}), status="EXPERT")
    r = build_report(ReportInputs([rec("c1")], labels, [crit("c1", "A", "A.1", 0.5, status="EXPERT")]))
    assert r["data_status"] == "EXPERT" and "not established" not in r["quality_statement"]
    assert "not adjudicated" not in r["quality_statement"]
    assert "not evidence of real-candidate performance" in r["quality_statement"]  # answers were scripted
    assert r["labels"]["relevance"] == {"n_used": 12, "adjudicated": True}


def test_expert_single_annotator_labels_flagged_not_adjudicated():
    """Test fixtures only: EXPERT-marked labels built here are not real annotations."""
    labels = rel("c1", grades({"v00": 3}), status="EXPERT", review="REVIEWED", ann="ann1")
    r = build_report(ReportInputs([rec("c1")], labels))
    assert r["data_status"] == "EXPERT" and r["modes"]["ADAPTIVE_INTERVIEW"]["n_included"] == 1
    assert "relevance labels are not adjudicated" in r["quality_statement"]


def test_adjudicated_labels_preferred_over_annotator_rows():
    """Test fixtures only."""
    final = rel("c1", grades({"v00": 3}))
    raw = rel("c1", grades({"v05": 3}), review="PENDING", ann="ann1")
    r = build_report(ReportInputs([rec("c1")], final + raw))
    assert r["modes"]["ADAPTIVE_INTERVIEW"]["ndcg_at_10"] == pytest.approx(1.0)
    assert "12 non-adjudicated relevance label(s) were ignored" in r["quality_statement"]
    with pytest.raises(LabelError, match="more than once"):  # two annotators, nothing adjudicated
        build_report(ReportInputs([rec("c1")], raw + rel("c1", grades({}), review="PENDING", ann="ann2")))


def test_mixed_status_across_files_rejected():
    """Test fixtures only."""
    with pytest.raises(LabelError, match="mixed data_status"):
        build_report(ReportInputs([rec("c1")], rel("c1", grades({}), status="EXPERT"),
                                  [crit("c1", "A", "A.1", 0.5)]))


# --- (b), (h) CLI ------------------------------------------------------------------------------------------------------

def _dump(path, labels):
    path.write_text(json.dumps([lb.model_dump(mode="json") for lb in labels], ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_cli_synthetic_needs_flag(tmp_path, capsys):
    export_records([rec("c1", sufficient=[["a"]])], tmp_path / "runs")
    args = ["--runs", str(tmp_path / "runs" / "runs.json"),
            "--relevance", _dump(tmp_path / "rel.json", rel("c1", grades({"v00": 3}))), "--out", str(tmp_path / "rep")]
    assert main(args) == 2
    assert "error:" in capsys.readouterr().err and not (tmp_path / "rep").exists()
    assert main(args + ["--allow-synthetic-labels"]) == 0
    out = capsys.readouterr().out
    assert str(tmp_path / "rep") in out and "SYNTHETIC_TEST_DATA" in out
    r = json.loads((tmp_path / "rep" / "report.json").read_text(encoding="utf-8"))
    assert r["data_status"] == "SYNTHETIC_TEST_DATA" and "method quality is not established" in r["quality_statement"]


def test_cli_without_labels_and_bad_inputs(tmp_path, capsys):
    export_records([rec("c1")], tmp_path / "runs")
    runs = str(tmp_path / "runs" / "runs.json")
    assert main(["--runs", runs, "--out", str(tmp_path / "rep")]) == 0
    assert json.loads((tmp_path / "rep" / "report.json").read_text(encoding="utf-8"))["data_status"] == "NO_EXPERT_LABELS"
    assert main(["--runs", str(tmp_path / "missing.json"), "--out", str(tmp_path / "x")]) == 2
    bad = tmp_path / "bad.csv"
    bad.write_text("candidate_id,vacancy_id,grade\nc1,v00,7\n", encoding="utf-8")
    assert main(["--runs", runs, "--relevance", str(bad), "--out", str(tmp_path / "x")]) == 2
    assert main(["--runs", runs, "--out", str(tmp_path / "x"), "--coverage-threshold", "1.5"]) == 2
    (tmp_path / "junk.json").write_text("{not json", encoding="utf-8")
    assert main(["--runs", str(tmp_path / "junk.json"), "--out", str(tmp_path / "x")]) == 2
    err = capsys.readouterr().err
    assert err.count("error:") == 4 and "row 2" in err and not (tmp_path / "x").exists()


def test_cli_end_to_end_from_runner(client, db, monkeypatch, tmp_path, capsys):
    """Phase 3 runner with the fake model -> export_records -> CLI with synthetic (test fixture) labels."""
    from tests.test_experiment_comparability import _run
    records = [_run(client, db, monkeypatch, m, eid="e2e") for m in (INITIAL, STATIC, ADAPTIVE)]
    records.append(_run(client, db, monkeypatch, ADAPTIVE, eid="e2e", adaptive_followup=False))
    export_records(records, tmp_path / "runs")
    assert load_exported_records(tmp_path / "runs" / "runs.json") == records
    ranked = [i["vacancy_id"] for i in records[0].ranking]
    assert len(ranked) >= 10
    rel_labels = rel("c1", {v: (3 - i % 4) for i, v in enumerate(ranked)})
    crit_labels = [crit("c1", a["action_id"], a["criterion_id"], 0.5,
                        version=records[2].rubric_versions.get(a["action_id"], "v1"))
                   for a in records[2].assessments]
    rc = main(["--runs", str(tmp_path / "runs" / "runs.json"), "--relevance", _dump(tmp_path / "r.json", rel_labels),
               "--criteria", _dump(tmp_path / "c.json", crit_labels), "--out", str(tmp_path / "rep"),
               "--allow-synthetic-labels"])
    assert rc == 0, capsys.readouterr().err
    r = json.loads((tmp_path / "rep" / "report.json").read_text(encoding="utf-8"))
    assert list(r["modes"]) == ["INITIAL_PROFILE", "STATIC_INTERVIEW", "ADAPTIVE_INTERVIEW",
                                "ADAPTIVE_INTERVIEW-followup"]
    assert all(m["n_included"] == 1 and m["precision_at_5"] is not None for m in r["modes"].values())
    assert all(r["modes"][k]["criterion_coverage_mean"] is not None for k in r["modes"])
    assert r["modes"]["ADAPTIVE_INTERVIEW"]["evaluator_mae"]["n_compared"] > 0
    assert r["modes"]["INITIAL_PROFILE"]["questions_mean"] == 0
    charts = json.loads((tmp_path / "rep" / "charts.json").read_text(encoding="utf-8"))
    assert tuple(charts) == CHART_KEYS and charts["questions_static_vs_adaptive"]["data"][0]["candidate_id"] == "c1"
    assert (tmp_path / "rep" / "report.csv").is_file()


def test_engine_never_imports_report_or_metrics():
    """Ground-truth evaluation code stays out of recommendation/ranking code (extends the expert-label AST scan)."""
    import ast

    from tests.test_experiment_comparability import SCANNED, BACKEND
    banned = {"backend.experiments.report", "backend.experiments.metrics", "backend.experiments.expert_labels"}

    def imports(src):
        out = []
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                out += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                out += [node.module or "", *(f"{node.module or ''}.{a.name}" for a in node.names)]
        return out

    assert imports("from backend.experiments import report") == ["backend.experiments", "backend.experiments.report"]
    offenders = {str(p.relative_to(BACKEND)): sorted(set(imports(p.read_text(encoding="utf-8"))) & banned)
                 for p in SCANNED}
    assert {k: v for k, v in offenders.items() if v} == {}
