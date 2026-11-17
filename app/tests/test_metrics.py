import math

import pytest

from backend.experiments.metrics import (
    MissingLabelsError, coverage_curve, criterion_coverage, evaluator_mae, interview_duration,
    ndcg_at_k, precision_at_k, questions_to_coverage, unresolved_requirements_rate,
)

L = {"a": 3, "b": 0, "c": 2, "d": 3}


def test_p5():
    # relevant (>=2) in top 5: v1(3), v3(2), v5(2) -> 3/5
    labels = {"v1": 3, "v2": 1, "v3": 2, "v4": 0, "v5": 2, "v6": 3}
    assert precision_at_k([f"v{i}" for i in range(1, 7)], labels) == pytest.approx(0.6)


def test_p_fewer_than_k_denominator_k():
    # 2 ranked, 1 relevant -> 1/5
    assert precision_at_k(["a", "b"], L) == pytest.approx(0.2)


def test_ndcg_linear_hand():
    # DCG = 3/log2(2) + 0/log2(3) + 2/log2(4) = 3 + 0 + 1 = 4
    # ideal = [3,3,2,0] -> 3/1 + 3/log2(3) + 2/2 + 0 = 4 + 3/log2(3)
    expected = 4 / (4 + 3 / math.log2(3))
    assert ndcg_at_k(["a", "b", "c"], L) == pytest.approx(expected)


def test_ndcg_exp_differs():
    # exp gains: a=7, b=0, c=3, d=7. DCG = 7 + 0 + 3/2 = 8.5; ideal = 7 + 7/log2(3) + 3/2 + 0
    expected = 8.5 / (8.5 + 7 / math.log2(3))
    got = ndcg_at_k(["a", "b", "c"], L, gain="exp")
    assert got == pytest.approx(expected)
    assert got != pytest.approx(ndcg_at_k(["a", "b", "c"], L))


def test_ndcg_perfect_and_reversed():
    assert ndcg_at_k(["a", "d", "c", "b"], L) == pytest.approx(1.0)
    # reversed [b,c,d,a] = rels 0,2,3,3: DCG = 0 + 2/log2(3) + 3/log2(4) + 3/log2(5)
    # ideal = 3 + 3/log2(3) + 2/2 = 4 + 3/log2(3)
    exp = (2 / math.log2(3) + 1.5 + 3 / math.log2(5)) / (4 + 3 / math.log2(3))
    assert ndcg_at_k(["b", "c", "d", "a"], L) == pytest.approx(exp)
    assert exp < 1.0
    # ties: a and d both grade 3, either order is perfect
    assert ndcg_at_k(["d", "a", "c", "b"], L) == pytest.approx(1.0)


def test_ndcg_k_truncation_and_args():
    # k=2, ranked [b,a]: DCG = 0 + 3/log2(3); ideal[:2] = 3 + 3/log2(3)
    got = ndcg_at_k(["b", "a"], L, k=2)
    assert got == pytest.approx((3 / math.log2(3)) / (3 + 3 / math.log2(3)))
    assert got == pytest.approx(0.3868528, abs=1e-6)
    for k in (0, -1):
        with pytest.raises(ValueError):
            ndcg_at_k(["a"], L, k=k)
        with pytest.raises(ValueError):
            precision_at_k(["a"], L, k=k)
    with pytest.raises(ValueError):
        ndcg_at_k(["a"], L, gain="bad")
    with pytest.raises(ValueError):
        ndcg_at_k(["a"], L, unlabeled="bad")
    with pytest.raises(ValueError):
        precision_at_k(["a"], L, unlabeled="bad")
    # empty ranking: DCG 0, ideal > 0 -> 0.0; P@5 0.0
    assert ndcg_at_k([], L) == 0.0
    assert precision_at_k([], L) == 0.0


def test_all_zero_labels():
    z = {"a": 0, "b": 0}
    assert ndcg_at_k(["a", "b"], z) is None
    assert precision_at_k(["a", "b"], z) == 0.0


def test_unlabeled():
    with pytest.raises(MissingLabelsError, match=r"\['x', 'y'\]"):
        precision_at_k(["y", "a", "x"], L)
    with pytest.raises(MissingLabelsError):
        ndcg_at_k(["a", "x"], L)
    # skip: x dropped -> top = a, c; relevant 2 -> 2/5
    assert precision_at_k(["a", "x", "c"], L, unlabeled="skip") == pytest.approx(0.4)
    # skip before top k: k=2 -> [a, c] both relevant -> 1.0
    assert precision_at_k(["x", "a", "c"], L, k=2, unlabeled="skip") == pytest.approx(1.0)
    assert ndcg_at_k(["x", "a"], L, unlabeled="skip") is not None


def test_invalid_inputs():
    with pytest.raises(ValueError):
        ndcg_at_k(["a", "a"], L)
    with pytest.raises(ValueError):
        precision_at_k(["a", "a"], L)
    for bad in (4, -1, True, 1.5):
        with pytest.raises(ValueError):
            ndcg_at_k(["a"], {"a": bad})


def test_criterion_coverage():
    rel = ["c1", "c2", "c3", "c4", "c5"]
    assert criterion_coverage(["c1", "c2", "c3"], rel) == pytest.approx(0.6)
    assert criterion_coverage(["c1", "c2", "c3", "zz"], rel) == pytest.approx(0.6)
    assert criterion_coverage(["c1"], []) is None


def test_curve():
    rel = ["c1", "c2", "c3", "c4"]
    qa = [{"sufficient_criteria_after": []}, {"sufficient_criteria_after": ["c1", "z"]},
          {"sufficient_criteria_after": ["c1", "c2"]}, {"sufficient_criteria_after": ["c1", "c2", "c3"]}]
    curve = coverage_curve(qa, rel)
    assert curve == [0.0, 0.25, 0.5, 0.75]
    assert questions_to_coverage(curve, 0.5) == 3
    assert questions_to_coverage(curve, 0.9) is None
    assert coverage_curve([], rel) == []


def test_unresolved_rate():
    items = [{"unknown_count": 1, "groups_total": 4}, {"unknown_count": 2, "groups_total": 4},
             {"unknown_count": 0, "groups_total": 0}]
    assert unresolved_requirements_rate(items) == pytest.approx(3 / 8)
    assert unresolved_requirements_rate([{"unknown_count": 0, "groups_total": 0}]) is None
    assert unresolved_requirements_rate([]) is None


def test_mae():
    asm = [
        {"action_id": "x", "criterion_id": "1", "score": 0.8},
        {"action_id": "x", "criterion_id": "2", "score": 0.5},
        {"action_id": "x", "criterion_id": "3", "score": None},
        {"action_id": "x", "criterion_id": "4", "score": 0.3},
        {"action_id": "x", "criterion_id": "5", "score": 0.0},
        {"action_id": "x", "criterion_id": "6", "score": 0.9},
    ]
    exp = {("x", "1"): 0.6, ("x", "2"): 0.5, ("x", "3"): 0.4, ("x", "4"): None, ("x", "5"): None}
    r = evaluator_mae(asm, exp)
    # |0.8-0.6|=0.2, |0.5-0.5|=0 -> 0.1; 0.0 vs None not compared; crit 6 has no expert row
    assert r.mae == pytest.approx(0.1)
    assert (r.n_compared, r.n_evaluator_unknown, r.n_expert_unknown, r.n_missing_expert) == (2, 1, 2, 1)
    assert evaluator_mae([], {}).mae is None


def test_duration():
    assert interview_duration({"total_s": 10, "llm_wait_s": 4}) == {
        "total_s": 10.0, "llm_wait_s": 4.0, "excluding_llm_s": 6.0}
    assert interview_duration({"total_s": 3, "llm_wait_s": 5})["excluding_llm_s"] == 0.0


def test_curve_empty_relevant_is_not_zero():
    qa = [{"sufficient_criteria_after": ["c1"]}, {"sufficient_criteria_after": []}]
    curve = coverage_curve(qa, [])
    assert curve == []
    assert questions_to_coverage(curve, 0.0) is None


def test_mae_rejects_bad_scores():
    base = {"action_id": "x", "criterion_id": "1"}
    for bad in (True, float("nan"), float("inf"), 1.1, -0.1, "0.5"):
        with pytest.raises(ValueError):
            evaluator_mae([{**base, "score": bad}], {("x", "1"): 0.5})
        with pytest.raises(ValueError):
            evaluator_mae([{**base, "score": 0.5}], {("x", "1"): bad})


def test_unresolved_rate_validation():
    for bad in ({"unknown_count": 1, "groups_total": None}, {"unknown_count": -1, "groups_total": 2},
                {"unknown_count": 3, "groups_total": 2}, {"unknown_count": 1.5, "groups_total": 2},
                {"unknown_count": True, "groups_total": 2}):
        with pytest.raises(ValueError):
            unresolved_requirements_rate([bad])


def test_duration_validation():
    for bad in (-1, float("nan"), float("inf"), True):
        with pytest.raises(ValueError):
            interview_duration({"total_s": bad})
        with pytest.raises(ValueError):
            interview_duration({"total_s": 1, "llm_wait_s": bad})
