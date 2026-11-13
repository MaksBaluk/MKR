"""A legacy holistic row (criterion_id == action_id, rubric auto-1) is ignored
once seeded `<action>.<slug>` criterion rows exist for the same action."""
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.api.core import _action_scores
from backend.models import CriterionAssessment, Rubric
from tests.test_interview_flow import llm  # noqa: F401
from tests.test_profiles_api import finished, mk_profile, results  # noqa: F401


def _row(action, criterion, score):
    return SimpleNamespace(action_id=action, criterion_id=criterion, score=score)


def test_legacy_row_dropped_when_dotted_criteria_exist():
    rows = [_row("fastapi", "fastapi", 0.2), _row("fastapi", "fastapi.validation", 0.8),
            _row("fastapi", "fastapi.testing", 0.6)]
    assert _action_scores(rows)["fastapi"] == pytest.approx(0.7)


def test_legacy_only_and_dotted_only_unchanged():
    assert _action_scores([_row("django", "django", 0.4)]) == {"django": pytest.approx(0.4)}
    dotted = [_row("sql", "sql.joins", 0.5), _row("sql", "sql.performance", 0.9)]
    assert _action_scores(dotted) == {"sql": pytest.approx(0.7)}
    assert _action_scores([_row("sql", "sql", None)]) == {"sql": None}


def test_profile_results_ignore_legacy_row(client, auth, db, finished):  # noqa: F811
    before = results(client, auth, finished["id"], page_size=50)
    comp = next(c for c in before["competencies"] if c["score"] is not None)
    with db() as s:
        rub = s.scalar(select(Rubric).where(Rubric.action_id == comp["action_id"]))
        mine = s.scalars(select(CriterionAssessment).where(CriterionAssessment.session_id == before["attempt_id"],
                                                           CriterionAssessment.action_id == comp["action_id"])).first()
        s.add(CriterionAssessment(user_id=mine.user_id, session_id=mine.session_id, action_id=comp["action_id"],
                                  criterion_id=comp["action_id"], rubric_id=rub.id, score=0.0, reason="legacy",
                                  evidence=[], revision=mine.revision))
        s.commit()
    after = results(client, auth, finished["id"], page_size=50)
    assert {c["action_id"]: c["score"] for c in after["competencies"]} == \
        {c["action_id"]: c["score"] for c in before["competencies"]}
    assert "legacy" not in next(c for c in after["competencies"] if c["action_id"] == comp["action_id"])["reason"]
    assert [i["vacancy_id"] for i in after["items"]] == [i["vacancy_id"] for i in before["items"]]
