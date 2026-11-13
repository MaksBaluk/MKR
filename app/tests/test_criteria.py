import pytest

from backend.domain.criteria import (
    epsilon,
    experience_status,
    fulfilment_bounds,
    mandatory_status,
)


def test_epsilon_policy():
    assert epsilon(0.02) == pytest.approx(0.01)
    assert epsilon(0.5) == pytest.approx(0.05)


def test_null_is_unresolved_not_zero():
    assert mandatory_status(None, 0.5) == "UNRESOLVED"
    assert mandatory_status(0.0, 0.5) == "FAILED"


def test_satisfied_at_threshold_and_borderline():
    assert mandatory_status(0.5, 0.5) == "SATISFIED"
    assert mandatory_status(0.46, 0.5) == "UNRESOLVED"  # within eps=0.05
    assert mandatory_status(0.44, 0.5) == "FAILED"


def test_bounds_all_known():
    l, u = fulfilment_bounds({"a": 0.5}, {"a": 1.0}, {"a": 1.0}, ["a"])
    assert l == pytest.approx(0.5) and u == pytest.approx(0.5)


def test_bounds_unknown_widens_interval():
    l, u = fulfilment_bounds({"a": None, "b": 1.0}, {"a": 0.5, "b": 0.5}, {"a": 1.0, "b": 1.0}, ["a", "b"])
    assert l == pytest.approx(0.5)  # b h=min(1,1/0.5)=1, weight 1 of total 2
    assert u == pytest.approx(1.0)


def test_bounds_capped_at_one_and_ordered():
    l, u = fulfilment_bounds({"a": 0.9}, {"a": 0.1}, {"a": 1.0}, ["a"])
    assert l == 1.0 and u == 1.0


def test_extra_experience_not_penalized():
    assert experience_status(10, 3, True) == 2


def test_unknown_experience_is_one():
    assert experience_status(None, 3, True) == 1


def test_below_minimum_is_zero():
    assert experience_status(1, 3, True) == 0


def test_zero_score_distinct_from_null_in_bounds():
    l0, _ = fulfilment_bounds({"a": 0.0}, {"a": 0.5}, {"a": 1.0}, ["a"])
    ln, un = fulfilment_bounds({"a": None}, {"a": 0.5}, {"a": 1.0}, ["a"])
    assert l0 == 0.0 and (ln, un) == (0.0, 1.0)
