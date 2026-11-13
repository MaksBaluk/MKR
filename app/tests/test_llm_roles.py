import pytest

from backend.domain.assessment import EvaluatorOutput
from backend.providers.roles import (
    LLMError,
    evaluator_assess,
    interviewer_question,
)

VALID = {
    "action_id": "postgres_query_design",
    "rubric_version": "1",
    "criteria": [{"criterion_id": "sql_design", "score": 0.6, "reason": "ok",
                  "evidence": [{"turn_id": "t1", "exact_excerpt": "Працював з PostgreSQL"}]}],
    "sufficient_evidence": True,
    "needs_followup": False,
    "followup_goal": None,
    "limitations": "",
}


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0
        self.systems = []

    def complete(self, system, user, *, timeout_s):
        self.calls += 1
        self.systems.append(system)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _assess(transport):
    return evaluator_assess(transport, action_id="postgres_query_design", rubric_version="1",
                            allowed_criteria={"sql_design"}, turns={"t1": "Працював з PostgreSQL та індексами."})


def test_valid_evaluator_json_parses():
    import json
    out = _assess(FakeTransport(json.dumps(VALID)))
    assert isinstance(out, EvaluatorOutput)
    assert out.criteria[0].score == 0.6


def test_incomplete_json_is_malformed_after_retry():
    t = FakeTransport("{not json", "{not json")
    with pytest.raises(LLMError) as err:
        _assess(t)
    assert err.value.kind == "MALFORMED"
    assert t.calls == 2


def test_timeout_retries_then_succeeds():
    import json
    t = FakeTransport(LLMError("TIMEOUT"), json.dumps(VALID))
    assert _assess(t).criteria[0].score == 0.6
    assert t.calls == 2


def test_rate_limit_exhausts_retries():
    t = FakeTransport(LLMError("RATE_LIMIT"), LLMError("RATE_LIMIT"), LLMError("RATE_LIMIT"))
    with pytest.raises(LLMError) as err:
        _assess(t)
    assert err.value.kind == "RATE_LIMIT"


def test_offline_raises_without_fabrication():
    t = FakeTransport(LLMError("OFFLINE"))
    with pytest.raises(LLMError) as err:
        _assess(t)
    assert err.value.kind == "OFFLINE"
    assert t.calls == 1


def test_evaluator_rejects_bad_evidence():
    import json
    bad = dict(VALID, criteria=[dict(VALID["criteria"][0], evidence=[{"turn_id": "t1", "exact_excerpt": "Docker"}])])
    with pytest.raises(LLMError) as err:
        _assess(FakeTransport(json.dumps(bad), json.dumps(bad)))
    assert err.value.kind == "MALFORMED"


def test_interviewer_forbids_topic_change():
    t = FakeTransport("Яким був ваш досвід з PostgreSQL?")
    q = interviewer_question(t, action_name="PostgreSQL", rubric_criteria=["sql_design"],
                             previous_turns=[], followup_goal=None)
    assert q.startswith("Яким")
    assert "не змінюй" in t.systems[0].lower() or "не змінювати" in t.systems[0].lower()
