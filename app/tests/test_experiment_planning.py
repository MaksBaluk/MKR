import pytest

from backend.experiments.config import ExperimentConfig, InterviewMode, config_for
from backend.experiments.planning import plan_topics, slot_targets, static_plan_json


def _alt(c): return {"competency_id": c, "required_level": 2}


def _g(kind, *cs): return {"kind": kind, "alternatives": [_alt(c) for c in cs]}


# v1: [A] [B]; v2: [A] [C]; v3: [A|D]. Weights 1/6,1/6,1/6,1/6,1/3.
REVS = [
    {"id": "v1", "years_min": 0, "groups": [_g("MANDATORY", "A"), _g("PREFERRED", "B")]},
    {"id": "v2", "years_min": 0, "groups": [_g("MANDATORY", "A"), _g("PREFERRED", "C")]},
    {"id": "v3", "years_min": 0, "groups": [_g("MANDATORY", "A", "D")]},
]


def test_config_rejects_caps_above_product_limits():
    for kw in ({"max_topics": 11}, {"max_per_topic": 6}, {"static_questions_per_topic": 6}, {"total_budget": 0}):
        with pytest.raises(ValueError):
            ExperimentConfig(InterviewMode.ADAPTIVE_INTERVIEW, **kw)


def test_static_forces_flags_off():
    c = config_for(InterviewMode.STATIC_INTERVIEW)
    assert not (c.adaptive_topics or c.adaptive_followup or c.adaptive_difficulty)


def test_static_rejects_flag_overrides():
    with pytest.raises(ValueError):
        config_for(InterviewMode.STATIC_INTERVIEW, adaptive_topics=True)


def test_adaptive_ablation_flags():
    c = config_for(InterviewMode.ADAPTIVE_INTERVIEW, adaptive_difficulty=False)
    assert (c.adaptive_topics, c.adaptive_followup, c.adaptive_difficulty) == (True, True, False)
    assert config_for(InterviewMode.ADAPTIVE_INTERVIEW).adaptive_difficulty is True


def test_json_roundtrip():
    c = config_for(InterviewMode.ADAPTIVE_INTERVIEW, total_budget=12, adaptive_followup=False)
    d = c.to_json()
    assert d["mode"] == "ADAPTIVE_INTERVIEW"
    assert ExperimentConfig.from_json(d) == c


def test_plan_topics_deterministic_and_greedy():
    mass = {"C": 0.9, "B": 0.1}
    # A covers 3 groups (gain 2/3) -> first. Then B,C tie on gain 1/6; mass picks C. D covered by A.
    out = plan_topics(REVS, {}, mass, 10)
    assert out == ["A", "C", "B"]
    assert plan_topics(REVS, {}, mass, 10) == out


def test_plan_topics_respects_max_topics_and_stops_at_zero_gain():
    assert plan_topics(REVS, {}, {}, 2)[0] == "A" and len(plan_topics(REVS, {}, {}, 2)) == 2
    assert len(plan_topics(REVS, {}, {}, 10)) == 3  # no more gain after 3 topics


def test_plan_topics_empty_cohort_returns_empty():
    assert plan_topics([], {}, {}, 10) == []


def test_slot_targets_partition():
    cs = ["c0", "c1", "c2", "c3", "c4"]
    a, b = slot_targets(cs, 2, 0), slot_targets(cs, 2, 1)
    assert a == ("c0", "c2", "c4") and b == ("c1", "c3")
    assert sorted(a + b) == cs
    with pytest.raises(ValueError):
        slot_targets(cs, 2, 2)


def test_static_plan_json():
    c = config_for(InterviewMode.STATIC_INTERVIEW, total_budget=8)
    assert static_plan_json(["A"], c) == {"topics": ["A"], "questions_per_topic": 2, "total_budget": 8}
