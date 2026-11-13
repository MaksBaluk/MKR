import pytest
from pydantic import ValidationError

from backend.domain.assessment import (
    CriterionResult,
    EvaluatorOutput,
    EvidenceRef,
    validate_against_context,
)

TURNS = {"t1": "Працював з PostgreSQL та індексами."}


def _out(score, excerpt="Працював з PostgreSQL", criterion="sql_design", turn="t1"):
    return EvaluatorOutput(
        action_id="postgres_query_design",
        rubric_version="1",
        criteria=[
            CriterionResult(
                criterion_id=criterion,
                score=score,
                reason="пояснення",
                evidence=[EvidenceRef(turn_id=turn, exact_excerpt=excerpt)],
            )
        ],
        sufficient_evidence=True,
        needs_followup=False,
        followup_goal=None,
        limitations="",
    )


def test_zero_is_valid_and_distinct_from_null():
    assert validate_against_context(_out(0.0), {"sql_design"}, TURNS) == []
    assert validate_against_context(_out(None), {"sql_design"}, TURNS) == []


def test_score_out_of_range_rejected():
    assert validate_against_context(_out(1.2), {"sql_design"}, TURNS)
    assert validate_against_context(_out(-0.1), {"sql_design"}, TURNS)


def test_nan_rejected():
    assert validate_against_context(_out(float("nan")), {"sql_design"}, TURNS)


def test_quote_not_in_turn_rejected():
    assert validate_against_context(_out(0.5, excerpt="Docker"), {"sql_design"}, TURNS)


def test_unknown_criterion_rejected():
    assert validate_against_context(_out(0.5), {"other"}, TURNS)


def test_malformed_payload_raises():
    with pytest.raises(ValidationError):
        EvaluatorOutput.model_validate({"action_id": "x"})


@pytest.mark.parametrize("limitations", [None, ["a", "b"], "текст"])
def test_limitations_variants_from_models_are_accepted(limitations):
    out = EvaluatorOutput.model_validate({
        "action_id": "x", "rubric_version": "1", "criteria": [], "sufficient_evidence": True,
        "needs_followup": False, "followup_goal": None, "limitations": limitations})
    assert isinstance(out.limitations, str)
