import pytest

from backend.domain.topic_summary import (
    TopicSummary,
    criterion_state,
    open_criteria,
    topic_summary,
)


def test_one_of_five_high_is_not_overall():
    rubric = [(f"c{i}", 1.0) for i in range(1, 6)]
    s = topic_summary(rubric, {"c1": 0.95})
    assert s.m == pytest.approx(0.95)
    assert s.e == pytest.approx(0.2)
    assert s.overall_level_allowed is False
    assert s.assessed == ("c1",)
    assert s.unknown == ("c2", "c3", "c4", "c5")


def test_all_null():
    s = topic_summary([("a", 1.0), ("b", 1.0)], {"a": None})
    assert s.m is None
    assert s.e == 0.0
    assert s.overall_level_allowed is False


def test_weights():
    s = topic_summary([("a", 1.0), ("b", 3.0)], {"a": 1.0, "b": 0.5})
    assert s.m == pytest.approx(0.625)
    assert s.e == pytest.approx(1.0)
    assert s.overall_level_allowed is True


def test_empty_rubric_and_bad_weight():
    assert topic_summary([], {}) == TopicSummary(None, 0.0, (), (), False)
    with pytest.raises(ValueError):
        topic_summary([("a", 0.0)], {})


def test_state():
    assert criterion_state(None, False) == "UNKNOWN"
    assert criterion_state(0.5, True) == "WEAK"
    assert criterion_state(0.75, False) == "CONFIRMED"
    assert criterion_state(0.0, True) == "DECLINED"
    assert criterion_state(0.0, False) == "WEAK"


def test_open_criteria_skips_confirmed_and_declined():
    rubric = [("a", 1.0), ("b", 1.0), ("c", 1.0), ("d", 1.0)]
    scores = {"a": 0.9, "b": 0.0, "c": 0.4}
    assert open_criteria(rubric, scores, True) == ["c", "d"]
    assert open_criteria(rubric, scores, False) == ["b", "c", "d"]
