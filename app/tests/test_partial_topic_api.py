"""One assessed criterion of a multi-criterion rubric must not satisfy a requirement (MATH_SPEC §4, E_c)."""
from sqlalchemy import func, select

from backend.models import CohortSnapshot, CoreInterview, CriterionAssessment, Rubric, RubricCriterion
from tests.test_interview_flow import llm  # noqa: F401
from tests.test_profiles_api import API, finished  # noqa: F401


def _setup(db, finished, criterion_ids=None):
    with db() as s:
        rid, action = s.execute(select(RubricCriterion.rubric_id, Rubric.action_id).join(Rubric)
                                .where(Rubric.version == "v1", Rubric.source.in_(("CURATED", "CURATED_TEMPLATE", "REVIEWED")))
                                .group_by(RubricCriterion.rubric_id, Rubric.action_id)
                                .having(func.count() == 5).limit(1)).first()
        crit = s.scalars(select(RubricCriterion).where(RubricCriterion.rubric_id == rid)
                         .order_by(RubricCriterion.criterion_id)).all()
        iv = s.scalars(select(CoreInterview).where(CoreInterview.status == "FINISHED")).first()
        snap = s.get(CohortSnapshot, iv.cohort_id)
        vid = snap.vacancy_ids[0]
        alt = {"competency_id": action, "required_level": 2}
        if criterion_ids:
            alt["criterion_ids"] = [crit[0].criterion_id]
        revs = {k: dict(v) for k, v in snap.requirement_revisions.items()}
        revs[vid] = {**revs[vid], "groups": [{"id": "g1", "kind": "MANDATORY", "label": "x", "excerpt": "x",
                                              "alternatives": [alt]}]}
        snap.requirement_revisions = revs
        for r in s.scalars(select(CriterionAssessment).where(CriterionAssessment.session_id == iv.id)).all():
            s.delete(r)
        s.add(CriterionAssessment(user_id=iv.user_id, session_id=iv.id, action_id=action,
                                  criterion_id=crit[0].criterion_id, rubric_id=rid, score=0.95, reason="ok",
                                  evidence=[], revision=1, sufficient_evidence=True))
        s.commit()
        return action, vid


def _get(client, auth, pid):
    return client.get(f"{API}/profiles/{pid}/results", params={"page_size": 50, "fitting": "all"}, headers=auth).json()


def test_one_of_five_criteria_does_not_satisfy(client, auth, db, finished):
    action, vid = _setup(db, finished)
    r = _get(client, auth, finished["id"])
    comp = next(c for c in r["competencies"] if c["action_id"] == action)
    assert comp["coverage"] == 0.2 and comp["overall_level_allowed"] is False
    item = next(i for i in r["items"] if i["vacancy_id"] == vid)
    assert item["met_count"] == 0 and item["strengths"] == []


def test_criterion_subset_requirement_is_met(client, auth, db, finished):
    action, vid = _setup(db, finished, criterion_ids=True)
    item = next(i for i in _get(client, auth, finished["id"])["items"] if i["vacancy_id"] == vid)
    assert item["met_count"] == 1 and item["strengths"]


def test_detail_shows_score_and_state_for_seeded_rubric(client, auth, db, finished):
    action, vid = _setup(db, finished, criterion_ids=True)
    d = client.get(f"{API}/profiles/{finished['id']}/results/{vid}", headers=auth).json()
    alt = d["groups"][0]["alternatives"][0]
    assert alt["candidate_score"] == 0.95 and alt["state"] == "MET"


def test_detail_partial_topic_not_met(client, auth, db, finished):
    action, vid = _setup(db, finished)
    alt = client.get(f"{API}/profiles/{finished['id']}/results/{vid}", headers=auth).json()["groups"][0]["alternatives"][0]
    # 1 of 5 required criteria graded: M_c 0.95 is shown, but the state is not BORDERLINE ("майже достатньо").
    assert alt["candidate_score"] == 0.95 and alt["state"] == "UNKNOWN" and alt["coverage"] == 0.2


def test_recommendations_one_of_five_not_met(client, auth, db, finished):
    action, vid = _setup(db, finished)
    with db() as s:
        cid = s.scalars(select(CoreInterview)).first().cohort_id
    r = client.post(f"{API}/recommendations", json={"cohort_id": cid}, headers=auth).json()
    item = next(i for i in r["items"] if i["vacancy_id"] == vid)
    assert item["met_count"] == 0 and item["z"] != 2
