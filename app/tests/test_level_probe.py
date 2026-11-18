"""Level probe (Task 4): reorders the chosen topic's open criteria and names practice gaps; never changes membership."""
from backend.agents.prompts import INTERVIEWER_SYSTEM, format_interviewer_input
from backend.domain.level_probe import practice_gaps, prioritize_unmet
from backend.domain.seniority import CriterionEvidence, estimate
from backend.domain.seniority_policy import PYTHON_BACKEND_V1

JUNIOR, MIDDLE, SENIOR = (r.critical for r in PYTHON_BACKEND_V1.rules)


def ev(scores: dict[str, float | None]) -> dict[str, CriterionEvidence]:
    return {c: CriterionEvidence(c, s, ("t1",) if s is not None else ()) for c, s in scores.items()}


def result(scores):
    return estimate(PYTHON_BACKEND_V1, ev(scores))


JUNIOR_OK = {c: 0.9 for c in JUNIOR}


def test_priority_puts_level_critical_first_and_keeps_membership():
    unmet = ["python-core.typing", "python-core.zzz", "python-core.idioms", "python-core.errors"]
    out = prioritize_unmet(unmet, PYTHON_BACKEND_V1, result({}))
    assert out == ["python-core.idioms", "python-core.errors", "python-core.typing", "python-core.zzz"]
    assert sorted(out) == sorted(unmet) and len(out) == len(unmet)
    assert prioritize_unmet([], PYTHON_BACKEND_V1, result({})) == []


def test_no_policy_returns_input_unchanged():
    unmet = ["b.x", "a.y", "python-core.idioms"]
    out = prioritize_unmet(unmet, None, None)
    assert out == unmet and out is not unmet
    assert prioritize_unmet(unmet, None, estimate(None, {})) == unmet
    assert prioritize_unmet(unmet, PYTHON_BACKEND_V1, None) == unmet
    assert practice_gaps(None, None) == [] and practice_gaps(None, estimate(None, {})) == []
    assert practice_gaps(PYTHON_BACKEND_V1, None) == []


def test_supported_level_criteria_not_reprioritized():
    r = result(JUNIOR_OK)
    assert r.coverage_by_level["JUNIOR"].status == "SUPPORTED"
    unmet = ["python-core.errors", "sql.joins", "python-core.typing", "postgresql.indexes"]
    # JUNIOR is supported: MIDDLE critical criteria lead; JUNIOR-only criteria keep their rubric order behind them
    assert prioritize_unmet(unmet, PYTHON_BACKEND_V1, r) == [
        "python-core.typing", "postgresql.indexes", "python-core.errors", "sql.joins"]
    every = result({c: 0.95 for c in JUNIOR + MIDDLE + SENIOR})
    assert all(c.status == "SUPPORTED" for c in every.coverage_by_level.values())
    assert prioritize_unmet(unmet, PYTHON_BACKEND_V1, every) == unmet
    assert practice_gaps(PYTHON_BACKEND_V1, every) == []


def test_practice_gaps_limited_and_only_unassessed():
    assert practice_gaps(PYTHON_BACKEND_V1, result({})) == ["practice-backend.independence"]
    r = result(JUNIOR_OK)  # independence confirmed; MIDDLE practice: rationale, diagnosis unassessed
    assert practice_gaps(PYTHON_BACKEND_V1, r) == ["practice-backend.rationale", "practice-backend.diagnosis"]
    assert practice_gaps(PYTHON_BACKEND_V1, r, limit=1) == ["practice-backend.rationale"]
    assert practice_gaps(PYTHON_BACKEND_V1, r, limit=0) == []
    graded = result({**JUNIOR_OK, "practice-backend.rationale": 0.3})  # assessed (a gap) is not "unassessed"
    assert practice_gaps(PYTHON_BACKEND_V1, graded) == ["practice-backend.diagnosis"]
    assert all(g.startswith("practice-backend.") for g in practice_gaps(PYTHON_BACKEND_V1, result({}), limit=9))


BASE = dict(action_name="A", topic_summary="T", unmet_criteria=["a.x"], previous_answers=["відповідь"],
            followup_goal=None, candidate_level="middle", years_experience=3, asked_questions=[], difficulty="BASIC")


def test_interviewer_input_byte_identical_without_practice_gaps():
    plain = format_interviewer_input(**BASE)
    assert format_interviewer_input(**BASE, practice_gaps=[]) == plain
    assert format_interviewer_input(**BASE, practice_gaps=None) == plain
    assert "practice_gaps" not in plain


def test_interviewer_input_lists_practice_gaps_as_ids_only():
    out = format_interviewer_input(**BASE, practice_gaps=["practice-backend.rationale", "<b>x</b>"])
    assert 'practice_gaps: ["practice-backend.rationale", "\\u003cb\\u003ex\\u003c/b\\u003e"]' in out
    assert "practice_gaps" in INTERVIEWER_SYSTEM
    rule = INTERVIEWER_SYSTEM[INTERVIEWER_SYSTEM.index("practice_gaps (optional"):]
    assert "never name them" in rule and "Stay on action_name" in INTERVIEWER_SYSTEM
    assert "priority order" in INTERVIEWER_SYSTEM


def test_evaluator_shape_mentions_optional_practice():
    from backend.agents.prompts import EVALUATOR_SYSTEM
    shape = next(line for line in EVALUATOR_SYSTEM.splitlines() if line.strip().startswith('{"action_id": "..."'))
    assert '"practice":' in shape
    assert "optional" in EVALUATOR_SYSTEM[EVALUATOR_SYSTEM.index(shape):EVALUATOR_SYSTEM.index(shape) + len(shape) + 200]
