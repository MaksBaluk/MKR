from sqlalchemy import select, func

from backend.domain.seniority_policy import (PRACTICE_ACTION, PRACTICE_CRITERIA, PYTHON_BACKEND_V1, policy_for, rank)
from backend.models import Competency, Rubric, RubricCriterion, RequirementAlternative
from backend.seed import read_fixture, seed_database


def _ids(fixture):
    return {c["criterion_id"] for r in read_fixture(fixture)["rubrics"] for c in r["criteria"]}


def test_policy_levels_are_hierarchical_and_ids_exist():
    base, practice = _ids("rubrics.json"), _ids("practice_rubrics.json")
    assert set(PRACTICE_CRITERIA) == practice and len(PRACTICE_CRITERIA) == 6
    rules = PYTHON_BACKEND_V1.rules
    for rule in rules:
        for cid in rule.critical:
            assert cid in (practice if cid.startswith(PRACTICE_ACTION + ".") else base), cid
    assert [rank(r.level) for r in rules] == [0, 1, 2]
    assert [r.min_competencies for r in rules] == sorted(r.min_competencies for r in rules)
    assert [r.tau for r in rules] == sorted(r.tau for r in rules)


def test_policy_is_versioned_and_flagged():
    p = PYTHON_BACKEND_V1
    assert (p.policy_id, p.version, p.status) == ("python-backend", "v1", "WORKING_ASSUMPTION")
    assert policy_for("python") is p


def test_marketing_design_have_no_policy():
    assert policy_for("marketing") is None and policy_for("design") is None and policy_for(None) is None


def test_practice_rubric_seeded_and_planner_blind(db):
    from backend.api.core import cohort_actions
    with db() as s:
        rubric = s.scalar(select(Rubric).where(Rubric.action_id == PRACTICE_ACTION))
        rows = s.scalars(select(RubricCriterion).where(RubricCriterion.rubric_id == rubric.id)).all()
        assert sorted(r.criterion_id for r in rows) == sorted(PRACTICE_CRITERIA)
        assert s.get(Competency, PRACTICE_ACTION) is None
        alts = s.scalars(select(RequirementAlternative)).all()
        revisions = [{"groups": [{"alternatives": [{"competency_id": a.competency_id} for a in alts]}]}]
        assert PRACTICE_ACTION not in cohort_actions(revisions)


def test_seed_practice_idempotent(db):
    with db() as s:
        count = lambda: (s.scalar(select(func.count(Rubric.id))), s.scalar(select(func.count(RubricCriterion.id))))
        before = count()
        again = seed_database(s, demo_mode=False)
        assert again["rubrics_added"] == 0 and count() == before
