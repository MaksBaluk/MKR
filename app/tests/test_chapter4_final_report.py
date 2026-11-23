"""Phase-3 helpers: pool-restricted ranking metrics, hypothesis status rules, independent self-audit."""
import pytest

from scripts.chapter4 import chapter4_metrics as cm
from scripts.chapter4 import final_report as fr
from scripts.chapter4 import self_audit


def test_pool_ranking_keeps_run_order_and_appends_missing_pool_vacancies():
    ranked, missing = cm.pool_ranking(["v9", "v2", "x", "v1"], ["v1", "v2", "v3"])
    assert ranked == ["v2", "v1", "v3"] and missing == 1


def test_run_pool_metrics_uses_pool_only():
    run = {"profile_id": "C1", "ranking": ["out", "a", "b", "c", "d", "e", "f"]}
    ann = {"relevance": {"C1": {"a": 3, "b": 0, "c": 2, "d": 2, "e": 1, "f": 0}}}
    m = cm.run_pool_metrics(run, ann, {"C1": ["a", "b", "c", "d", "e", "f"]})
    assert m["p5"] == pytest.approx(3 / 5) and m["missing"] == 0 and m["pool_relevant"] == 3
    assert 0 < m["ndcg10"] < 1


def _cmp(metric, a, b, lows, highs):
    return [{"metric": metric, "a": a, "b": b, "budget": bud, "ci95_low": lo, "ci95_high": hi, "mean_a_minus_b": (lo + hi) / 2,
             "profiles_a_gt_b": 0, "profiles_a_lt_b": 18} for bud, lo, hi in zip(fr.BUDGETS, lows, highs)]


def test_hypothesis_rules_cap_pilot_ground_truth_and_follow_ci():
    rows = (_cmp("relevant_coverage", fr.C, fr.B, [-.2] * 4, [-.1] * 4) + _cmp("relevant_coverage", fr.D, fr.B, [-.2] * 4, [-.1] * 4)
            + _cmp("relevant_coverage", fr.D, fr.C, [.01, .01, -.01, -.01], [.03] * 4))
    for m, a, b in (("p_at_5", fr.D, fr.A), ("p_at_5", fr.D, fr.B), ("ndcg_at_10", fr.D, fr.A), ("ndcg_at_10", fr.D, fr.B)):
        rows += _cmp(m, a, b, [.1] * 4, [.3] * 4)
    st = {h["hypothesis"]: h["status"] for h in fr.hypotheses(rows, {"ground_truth_version": "PILOT_LLM_ANNOTATOR"})}
    assert st == {"H1": "NOT_SUPPORTED", "H2": "INCONCLUSIVE", "H3": "INCONCLUSIVE", "H4": "INCONCLUSIVE"}
    st = {h["hypothesis"]: h["status"] for h in fr.hypotheses(rows, {"ground_truth_version": "HUMAN_EXPERT"})}
    assert st["H2"] == "SUPPORTED"
    st = {h["hypothesis"]: h["status"] for h in fr.hypotheses(rows, {"ground_truth_version": None})}
    assert st["H2"] == "NOT_TESTED" and st["H4"] == "NOT_TESTED"


def test_self_audit_matches_published_tables():
    if not (self_audit.OUT / "tables" / "table_4_5_recommendations.csv").exists():
        pytest.skip("phase-3 tables not built")
    res = self_audit.run()
    assert not res["discrepancies"], res["discrepancies"]
