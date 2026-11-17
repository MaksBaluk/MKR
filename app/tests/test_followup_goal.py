import json

from backend.agents.graphs import run_answer
from backend.agents.prompts import EVALUATOR_SYSTEM, format_evaluator_input
from backend.domain.assessment import EvaluatorOutput, FollowupGoal, sanitize_goal
from test_graphs import ACTION, FakeModel


def _g(*ids):
    return FollowupGoal(criterion_ids=list(ids), reason="немає прикладу", expected_evidence="інструмент")


def _raw(goal, needs=True):
    return json.dumps({"action_id": ACTION, "rubric_version": "v1", "needs_followup": needs, "followup_goal": goal,
                       "criteria": [{"criterion_id": "a", "score": 0.6, "reason": "ок",
                                     "evidence": [{"turn_id": "t1", "exact_excerpt": "PostgreSQL"}]}]})


def _run(goal, open_ids=None, needs=True):
    st = {"action_id": ACTION, "rubric_version": "v1", "allowed_criterion_ids": ["a", "b"],
          "turns": {"t1": "Працював з PostgreSQL."}}
    if open_ids is not None:
        st["open_criterion_ids"] = open_ids
    return run_answer(st, FakeModel(_raw(goal, needs)))


def test_goal_dropped_when_criterion_unknown():
    assert sanitize_goal(_g("zzz"), {"a"}, ["a"]) is None
    r = _run({"criterion_ids": ["zzz"], "reason": "x"})
    assert r.output.followup_goal is None and r.status == "ACCEPTED"


def test_goal_dropped_when_criterion_confirmed():
    assert sanitize_goal(_g("a"), {"a", "b"}, ["b"]) is None
    assert _run({"criterion_ids": ["a"], "reason": "x"}, open_ids=["b"]).output.followup_goal is None


def test_goal_kept_for_open_criterion():
    g = sanitize_goal(_g("a", "b", "zzz"), {"a", "b"}, ["b"])
    assert g.criterion_ids == ["b"]
    assert _run({"criterion_ids": ["b"], "reason": "x"}, open_ids=["b"]).output.followup_goal.criterion_ids == ["b"]


def test_legacy_string_goal_becomes_none():
    for v in ("уточнити", ["a"], {"reason": "x"}):
        assert EvaluatorOutput.model_validate({"action_id": "a", "rubric_version": "v", "criteria": [],
                                               "followup_goal": v}).followup_goal is None


def test_needs_followup_without_goal_is_allowed():
    r = _run(None)
    assert r.status == "ACCEPTED" and r.output.needs_followup and r.output.followup_goal is None


def test_evaluator_input_lists_open_and_goal_shape():
    u = format_evaluator_input(action_id="a", rubric_version="v", allowed_criterion_ids=["a", "b"], bands=None,
                               turns={}, open_criterion_ids=["b"])
    assert 'open_criterion_ids: ["b"]' in u
    assert '"criterion_ids"' in EVALUATOR_SYSTEM and '"expected_evidence"' in EVALUATOR_SYSTEM
