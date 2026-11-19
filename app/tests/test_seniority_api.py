"""Assessed level (Task 5): stored on finish, immutable per (attempt, policy version), owner-only API, results views."""
import dataclasses
import json
import logging
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from backend.api.core import seniority_evidence
from backend.api.level import attempt_evidence, finalize_level
from backend.domain.seniority import estimate, result_to_json
from backend.domain.seniority_policy import PRACTICE_ACTION, PYTHON_BACKEND_V1, PYTHON_BACKEND_V2, policy_for
from backend.experiments.config import InterviewMode, config_for
from backend.experiments.runner import run_experiment
from backend.models import CoreInterview, CoreTurn, SeniorityAssessment
from tests.test_level_probe_flow import GOOD, ProbeChat, cand, mixed
from tests.test_followup_flow import _use
from tests.test_practice_criteria import API, PracticeChat, _answer, _attempt

CURRENT = PYTHON_BACKEND_V2  # the python track's current policy: new finalizations use it
V3 = dataclasses.replace(PYTHON_BACKEND_V2, version="v3", rules=tuple(
    dataclasses.replace(r, tau=0.99) for r in PYTHON_BACKEND_V2.rules))


@pytest.fixture()
def chat(monkeypatch):
    fake = PracticeChat()
    monkeypatch.setattr("backend.api.core.get_chat_model", lambda: fake)
    return fake


@pytest.fixture()
def other(client):
    r = client.post(f"{API}/auth/register", json={
        "email": "level-other@example.test", "display_name": "Other User", "password": "another-pass-456"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _finish(client, auth, iv_id):
    state = client.get(f"{API}/interviews/{iv_id}", headers=auth).json()
    r = client.post(f"{API}/interviews/{iv_id}/finish", json={"version": state["version"]}, headers=auth)
    assert r.status_code == 200, r.text


def _finished(client, auth, track="python", answers=1):
    iv = _attempt(client, auth, track)
    v = iv["version"]
    for _ in range(answers):
        _, v = _answer(client, auth, iv, v)
    _finish(client, auth, iv["id"])
    return iv


def _rows(db, iv_id):
    with db() as s:
        return s.scalars(select(SeniorityAssessment).where(SeniorityAssessment.interview_id == iv_id)
                         .order_by(SeniorityAssessment.created_at)).all()


def test_level_stored_on_finish_with_policy_version_and_attempt(client, auth, db, chat):
    iv = _finished(client, auth)
    [row] = _rows(db, iv["id"])
    assert (row.interview_id, row.profile_id, row.policy_id, row.policy_version) == (
        iv["id"], iv["profile_id"], "python-backend", "v2")
    assert row.created_at is not None and row.policy_status == "WORKING_ASSUMPTION" and row.track == "python"
    with db() as s:
        turns = s.scalars(select(CoreTurn).where(CoreTurn.interview_id == iv["id"])).all()
        expected = result_to_json(estimate(CURRENT, attempt_evidence(s, iv["id"])))
    assert row.rubric_versions == {turns[0].action_id: "v1", PRACTICE_ACTION: "v1"}
    assert row.result == expected and row.assessed_level == expected["assessed_level"]
    assert row.desired_level == "middle"


def test_auto_finish_also_stores_level(client, db, monkeypatch):
    _use(monkeypatch, ProbeChat(mixed))
    with db() as s:
        rec = run_experiment("level-auto", config_for(InterviewMode.ADAPTIVE_INTERVIEW, total_budget=2), cand(), GOOD,
                             client, s)
    with db() as s:
        assert s.get(CoreInterview, rec.interview_id).status == "FINISHED"
    assert [r.policy_version for r in _rows(db, rec.interview_id)] == ["v2"]


def test_policy_version_change_does_not_rewrite_history(client, auth, db, chat, monkeypatch):
    iv = _finished(client, auth)
    [old] = _rows(db, iv["id"])
    monkeypatch.setattr("backend.api.level.policy_for", lambda track: V3)
    got = client.get(f"{API}/interviews/{iv['id']}/level", headers=auth).json()
    assert got["policy"]["version"] == "v2" and len(_rows(db, iv["id"])) == 1  # reading never re-assesses
    with db() as s:
        new = finalize_level(s, s.get(CoreInterview, iv["id"]), V3)
        again = finalize_level(s, s.get(CoreInterview, iv["id"]), V3)
        s.commit()
        assert again.id == new.id  # idempotent per (attempt, policy version)
    rows = _rows(db, iv["id"])
    assert [r.policy_version for r in rows] == ["v2", "v3"]
    assert (rows[0].id, rows[0].result, rows[0].created_at) == (old.id, old.result, old.created_at)


def test_attempts_are_not_mixed(client, auth, db, chat):
    first = _finished(client, auth)
    chat.score, chat.practice = 0.1, 0.3
    r = client.post(f"{API}/profiles/{first['profile_id']}/attempts", headers=auth)
    second = {**r.json(), "profile_id": first["profile_id"]}
    _, _ = _answer(client, auth, second, second["version"])
    _finish(client, auth, second["id"])
    levels = {}
    for iv in (first, second):
        levels[iv["id"]] = client.get(f"{API}/interviews/{iv['id']}/level", headers=auth).json()
        with db() as s:
            own_turns = {t.id for t in s.scalars(select(CoreTurn).where(CoreTurn.interview_id == iv["id"])).all()}
            evidence = attempt_evidence(s, iv["id"])
        assert evidence and all(set(e.evidence_turns) <= own_turns for e in evidence.values())
        refs = {t for item in levels[iv["id"]]["evidence_references"] for t in item["turn_ids"]}
        assert refs and refs <= own_turns
        assert _rows(db, iv["id"])[0].result == result_to_json(estimate(CURRENT, evidence))
    with db() as s:
        a, b = attempt_evidence(s, first["id"]), attempt_evidence(s, second["id"])
    assert {k: v.score for k, v in a.items()} != {k: v.score for k, v in b.items()}
    latest = client.get(f"{API}/profiles/{first['profile_id']}/level", headers=auth).json()
    assert latest["interview_id"] == second["id"] and latest == levels[second["id"]]


def test_desired_level_change_does_not_change_result(client, auth, db, chat):
    iv = _finished(client, auth)
    before = client.get(f"{API}/interviews/{iv['id']}/level", headers=auth).json()
    r = client.put(f"{API}/profiles/{iv['profile_id']}", headers=auth, json={
        "name": "Профіль python", "track": "python", "target_level": "senior", "years_experience": 12})
    assert r.status_code == 200, r.text
    with db() as s:
        recomputed = result_to_json(estimate(CURRENT, attempt_evidence(s, iv["id"])))
    [row] = _rows(db, iv["id"])
    assert recomputed == row.result and recomputed["assessed_level"] == before["assessed_level"]
    after = client.get(f"{API}/interviews/{iv['id']}/level", headers=auth).json()
    assert after == before  # desired level is a display copy taken at finish, never an input


def _ranking_key(items):
    return [(i["vacancy_id"], i["z"], i["x"], i["label"], i["l_mandatory"], i["l_preferred"]) for i in items]


def test_level_does_not_change_ranking_key(client, auth, db, chat, monkeypatch):
    iv = _finished(client, auth)
    params = {"fitting": "all", "page_size": 50}

    def snapshot():
        res = client.get(f"{API}/profiles/{iv['profile_id']}/results", params=params, headers=auth).json()
        rec = client.post(f"{API}/recommendations", json={"cohort_id": iv["cohort_id"]}, headers=auth).json()
        return res, _ranking_key(res["items"]), _ranking_key(rec["items"])

    with_level, res_key, rec_key = snapshot()
    assert with_level["level"] is not None
    with db() as s:
        s.execute(delete(SeniorityAssessment))
        s.commit()
    monkeypatch.setattr("backend.api.profiles.level_for_attempt", lambda db, iv: None)
    without, res_key2, rec_key2 = snapshot()
    assert without["level"] is None and _rows(db, iv["id"]) == []
    assert (res_key, rec_key) == (res_key2, rec_key2)


def test_owner_isolation_level_endpoint(client, auth, db, chat, other):
    iv = _finished(client, auth)
    assert client.get(f"{API}/interviews/{iv['id']}/level", headers=other).status_code == 404
    assert client.get(f"{API}/profiles/{iv['profile_id']}/level", headers=other).status_code == 404
    assert client.get(f"{API}/interviews/{iv['id']}/level", headers=auth).status_code == 200


def test_unauthenticated_level_401(client, auth, db, chat):
    iv = _finished(client, auth)
    assert client.get(f"{API}/interviews/{iv['id']}/level").status_code == 401
    assert client.get(f"{API}/profiles/{iv['profile_id']}/level").status_code == 401


def test_unfinished_attempt_has_no_level(client, auth, db, chat):
    iv = _attempt(client, auth, "python")
    _answer(client, auth, iv, iv["version"])
    assert client.get(f"{API}/interviews/{iv['id']}/level", headers=auth).status_code == 409
    assert client.get(f"{API}/profiles/{iv['profile_id']}/level", headers=auth).status_code == 404
    assert _rows(db, iv["id"]) == []


def test_legacy_finished_attempt_gets_level_lazily(client, auth, db, chat):
    iv = _finished(client, auth)
    with db() as s:
        s.execute(delete(SeniorityAssessment))
        s.commit()
    got = client.get(f"{API}/interviews/{iv['id']}/level", headers=auth).json()
    [row] = _rows(db, iv["id"])
    assert got["policy"] == {"id": "python-backend", "version": "v2", "status": "WORKING_ASSUMPTION"}
    assert got["note"] == "Потребує експертної валідації" and got["created_at"] and row.policy_version == "v2"
    assert client.get(f"{API}/interviews/{iv['id']}/level", headers=auth).json() == got


def _all_items(client, auth, pid):
    items, page = [], 1
    while True:
        res = client.get(f"{API}/profiles/{pid}/results", headers=auth,
                         params={"fitting": "all", "page_size": 5, "page": page}).json()
        items += res["items"]
        if page * 5 >= res["total"]:
            return items, res
        page += 1


def test_sections_partition_same_items(client, auth, db, chat):
    iv = _finished(client, auth)
    items, res = _all_items(client, auth, iv["profile_id"])
    ids = [i["vacancy_id"] for i in items]
    assert len(ids) == len(set(ids)) == res["all_total"] > 0
    sections = {"DESIRED_LEVEL", "OTHER_FITTING", "UNRESOLVED_OR_GAPS"}
    assert {i["section"] for i in items} <= sections
    for i in items:
        desired = (i["seniority"] or "").upper() == "MIDDLE"
        expected = ("DESIRED_LEVEL" if desired else "OTHER_FITTING" if i["fits"] and i["z"] != 0
                    else "UNRESOLVED_OR_GAPS")
        assert i["section"] == expected, i["vacancy_id"]
    plain = client.get(f"{API}/profiles/{iv['profile_id']}/results", params={"fitting": "all", "page_size": 50},
                       headers=auth).json()
    assert [i["vacancy_id"] for i in plain["items"]] == ids[:50]  # sections are labels: order unchanged


def _profile_with_level(client, auth, target):
    iv = _attempt(client, auth, "python")
    r = client.put(f"{API}/profiles/{iv['profile_id']}", headers=auth, json={
        "name": "Профіль python", "track": "python", "target_level": target, "years_experience": 3})
    assert r.status_code == 200, r.text
    _answer(client, auth, iv, iv["version"])
    _finish(client, auth, iv["id"])
    return iv


@pytest.mark.parametrize("target", ["lead", "senior"])
def test_lead_vacancies_count_as_senior_for_desired_section(client, auth, db, chat, target):
    iv = _profile_with_level(client, auth, target)
    items, _ = _all_items(client, auth, iv["profile_id"])
    levels = {(i["seniority"] or "").upper() for i in items}
    assert {"SENIOR", "LEAD"} <= levels  # the fixture cohort has both
    assert all((i["section"] == "DESIRED_LEVEL") == ((i["seniority"] or "").upper() in ("SENIOR", "LEAD"))
               for i in items)


def test_sections_use_stored_desired_level_like_level_block(client, auth, db, chat):
    iv = _finished(client, auth)  # finished with target_level middle
    client.put(f"{API}/profiles/{iv['profile_id']}", headers=auth, json={
        "name": "Профіль python", "track": "python", "target_level": "senior", "years_experience": 3})
    items, res = _all_items(client, auth, iv["profile_id"])
    assert res["level"]["desired_level"] == "middle"
    assert all((i["section"] == "DESIRED_LEVEL") == ((i["seniority"] or "").upper() == "MIDDLE") for i in items)


def test_level_failure_never_blocks_finish_or_results(client, auth, db, chat, monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("unexpected")

    iv = _attempt(client, auth, "python")
    _answer(client, auth, iv, iv["version"])
    monkeypatch.setattr("backend.api.level.estimate", boom)
    # alembic's fileConfig (migration tests) disables existing loggers; re-enable this one for the assertion
    monkeypatch.setattr(logging.getLogger("competencematch.level"), "disabled", False)
    with caplog.at_level("WARNING", logger="competencematch.level"):
        _finish(client, auth, iv["id"])
    [record] = [r for r in caplog.records if r.name == "competencematch.level"]
    assert record.exc_info and record.exc_info[0] is RuntimeError  # the traceback is logged, not only the class
    with db() as s:
        assert s.get(CoreInterview, iv["id"]).status == "FINISHED"
    assert _rows(db, iv["id"]) == []
    res = client.get(f"{API}/profiles/{iv['profile_id']}/results", params={"fitting": "all"}, headers=auth)
    assert res.status_code == 200 and res.json()["level"] is None and res.json()["items"]
    assert all(i["section"] for i in res.json()["items"])
    monkeypatch.undo()
    monkeypatch.setattr("backend.api.core.get_chat_model", lambda: chat)
    got = client.get(f"{API}/interviews/{iv['id']}/level", headers=auth)  # lazy compute once the fault is gone
    assert got.status_code == 200 and len(_rows(db, iv["id"])) == 1


def test_no_policy_row_is_unique_per_attempt_in_db(client, auth, db, chat):
    iv = _finished(client, auth, track="marketing")
    [row] = _rows(db, iv["id"])
    assert row.policy_version is None
    with db() as s:
        assert finalize_level(s, s.get(CoreInterview, iv["id"])).id == row.id
        s.add(SeniorityAssessment(user_id=row.user_id, profile_id=row.profile_id, interview_id=row.interview_id,
                                  track="marketing", assessed_level="UNKNOWN", highest_supported_level="UNKNOWN",
                                  assessment_status="POLICY_UNAVAILABLE", result=row.result, rubric_versions={}))
        with pytest.raises(IntegrityError):
            s.commit()
    assert len(_rows(db, iv["id"])) == 1


def test_results_level_block_for_marketing_is_unknown_policy_unavailable(client, auth, db, chat):
    iv = _finished(client, auth, track="marketing")
    res = client.get(f"{API}/profiles/{iv['profile_id']}/results", params={"fitting": "all"}, headers=auth).json()
    level = res["level"]
    assert (level["assessed_level"], level["assessment_status"]) == ("UNKNOWN", "POLICY_UNAVAILABLE")
    assert level["policy"] == {"id": None, "version": None, "status": None} and level["note"] is None
    assert level["explanation"] and level["interview_id"] == iv["id"]
    assert client.get(f"{API}/interviews/{iv['id']}/level", headers=auth).json() == level
    assert len(_rows(db, iv["id"])) == 1


def test_results_level_block_matches_endpoint_and_labels_practice(client, auth, db, chat):
    iv = _finished(client, auth)
    res = client.get(f"{API}/profiles/{iv['profile_id']}/results", headers=auth).json()
    level = client.get(f"{API}/interviews/{iv['id']}/level", headers=auth).json()
    assert res["level"] == level and level["desired_level"] == "middle"
    listed = level["confirmed_strengths"] + level["critical_gaps"] + level["unassessed_criteria"]
    practice = [c for c in listed if c["id"].startswith(f"{PRACTICE_ACTION}.")]
    assert practice and all(c["title"] and c["title"] != c["id"] and c["kind"] == "PRACTICE" for c in practice)
    assert all(PRACTICE_ACTION not in line for line in level["explanation"])
    for cov in level["coverage_by_level"].values():
        assert all("title" in c for key in ("confirmed", "gaps", "unassessed") for c in cov[key])


def _row(action, cid, score, turn, created):
    ev = [{"turn_id": turn, "exact_excerpt": "x"}] if turn else []
    return SimpleNamespace(action_id=action, criterion_id=cid, score=score, evidence=ev, created_at=created)


def test_practice_evidence_is_topic_order_independent():
    cid = "practice-backend.rationale"
    topics = {"a1": "postgresql", "b1": "fastapi"}
    strong_then_weak = [_row(PRACTICE_ACTION, cid, 0.9, "a1", 1), _row(PRACTICE_ACTION, cid, 0.3, "b1", 2)]
    weak_then_strong = [_row(PRACTICE_ACTION, cid, 0.3, "b1", 1), _row(PRACTICE_ACTION, cid, 0.9, "a1", 2)]
    one, two = seniority_evidence(strong_then_weak, topics), seniority_evidence(weak_then_strong, topics)
    assert one == two and one[cid].score == 0.9 and set(one[cid].evidence_turns) == {"a1", "b1"}
    assert estimate(PYTHON_BACKEND_V1, one) == estimate(PYTHON_BACKEND_V1, two)
    # within one topic the later re-grade of the whole series still wins; a null never erases a score
    same_topic = [_row(PRACTICE_ACTION, cid, 0.9, "a1", 1), _row(PRACTICE_ACTION, cid, 0.3, "a1", 2),
                  _row(PRACTICE_ACTION, cid, None, None, 3)]
    assert seniority_evidence(same_topic, topics)[cid].score == 0.3
    # a gap only when no topic confirms
    both_weak = [_row(PRACTICE_ACTION, cid, 0.2, "a1", 1), _row(PRACTICE_ACTION, cid, 0.3, "b1", 2)]
    assert seniority_evidence(both_weak, topics)[cid].score == 0.3


def test_competency_evidence_keeps_effective_rows_and_all_turns():
    rows = [_row("postgresql", "postgresql.indexes", 0.9, "a1", 1),
            _row("postgresql", "postgresql.indexes", 0.4, "a2", 2),
            _row("postgresql", "postgresql.indexes", None, None, 3)]
    ev = seniority_evidence(rows, {"a1": "postgresql", "a2": "postgresql"})["postgresql.indexes"]
    assert ev.score == 0.4 and set(ev.evidence_turns) == {"a1", "a2"}
    untraced = seniority_evidence([_row(PRACTICE_ACTION, "practice-backend.ownership", 0.1, None, 1)], {})
    assert untraced["practice-backend.ownership"].evidence_turns == ()  # unresolved, never an established gap


def _level_without_timestamp(payload):
    return {k: v for k, v in payload.items() if k != "created_at"}


def test_self_rating_and_years_do_not_raise_level(client, auth, db, chat):
    iv = _finished(client, auth)
    before = client.get(f"{API}/interviews/{iv['id']}/level", headers=auth).json()
    pid = iv["profile_id"]
    r = client.put(f"{API}/profiles/{pid}", headers=auth, json={
        "name": "Профіль python", "track": "python", "target_level": "middle", "years_experience": 15})
    assert r.status_code == 200, r.text
    for action in ("python-core", "postgresql", "sqlalchemy", "redis", "celery", "observability"):
        r = client.put(f"{API}/profiles/{pid}/self-ratings/{action}", headers=auth, json={"value": 1.0})
        assert r.status_code == 200, r.text
    with db() as s:  # force the lazy recomputation after the profile change: evidence is the only input
        s.execute(delete(SeniorityAssessment))
        s.commit()
    after = client.get(f"{API}/interviews/{iv['id']}/level", headers=auth).json()
    assert _level_without_timestamp(after) == _level_without_timestamp(before)
    assert after["assessed_level"] != "SENIOR"


class PartialChat:
    """PracticeChat that grades only the first allowed criterion of a topic (every E_c < 0.6), practice as usual."""

    def __init__(self):
        self.inner = PracticeChat(score=0.9, practice=0.9)

    def invoke(self, messages, *a, **k):
        resp = self.inner.invoke(messages, *a, **k)
        try:
            out = json.loads(resp.content)
        except ValueError:
            return resp  # Interviewer question
        out["criteria"] = [c if i == 0 else {**c, "score": None, "evidence": []} for i, c in enumerate(out["criteria"])]
        return SimpleNamespace(content=json.dumps(out))


def test_level_independent_of_partial_topic_coverage(client, auth, db, monkeypatch):
    from backend.domain import topic_summary as ts
    from backend.models import CriterionAssessment, Rubric, RubricCriterion

    monkeypatch.setattr("backend.api.core.get_chat_model", lambda: PartialChat())
    iv = _attempt(client, auth, "python")
    v = iv["version"]
    for _ in range(3):
        _, v = _answer(client, auth, iv, v)
    _finish(client, auth, iv["id"])
    level = client.get(f"{API}/interviews/{iv['id']}/level", headers=auth).json()
    with db() as s:
        rows = s.scalars(select(CriterionAssessment).where(CriterionAssessment.session_id == iv["id"],
                                                           CriterionAssessment.action_id != PRACTICE_ACTION)).all()
        topics = {r.action_id for r in rows}
        for action in topics:
            rubric = [(c.criterion_id, c.weight) for c in s.scalars(select(RubricCriterion).join(
                Rubric, Rubric.id == RubricCriterion.rubric_id).where(Rubric.action_id == action,
                                                                      Rubric.version == "v1"))]
            scores = {r.criterion_id: r.score for r in rows if r.action_id == action and r.score is not None}
            assert ts.topic_summary(rubric, scores).e < ts.MIN_COVERAGE_FOR_OVERALL, action
        expected = result_to_json(estimate(CURRENT, attempt_evidence(s, iv["id"])))
    assert topics and _rows(db, iv["id"])[0].result == expected
    assert expected["coverage_by_level"]["JUNIOR"]["assessed"] > 0  # partial topic evidence still counts
    monkeypatch.setattr("backend.domain.topic_summary.MIN_COVERAGE_FOR_OVERALL", 0.0)
    with db() as s:
        s.execute(delete(SeniorityAssessment))
        s.commit()
    again = client.get(f"{API}/interviews/{iv['id']}/level", headers=auth).json()
    assert _level_without_timestamp(again) == _level_without_timestamp(level)


# --- policy v2 is current; v1 rows stay as stored --------------------------------------------------------------------

def test_new_attempt_stores_v2_and_payload_names_pools_in_ukrainian(client, auth, db, chat):
    assert policy_for("python") is CURRENT
    iv = _finished(client, auth)
    [row] = _rows(db, iv["id"])
    assert row.policy_version == "v2"
    level = client.get(f"{API}/interviews/{iv['id']}/level", headers=auth).json()
    for cov in level["coverage_by_level"].values():
        assert cov["pools"] and all(p["title"] and "." not in p["title"] for p in cov["pools"])
        assert all(c["title"] != c["id"] for p in cov["pools"] for c in p["criteria"])
    assert level["unassessed_pools"] and all(set(p) == {"id", "title"} for p in level["unassessed_pools"])
    titles = {p["title"] for cov in level["coverage_by_level"].values() for p in cov["pools"]}
    assert {p["title"] for p in level["unassessed_pools"]} <= titles


def test_v1_row_of_old_attempt_is_kept_and_rendered(client, auth, db, chat):
    iv = _finished(client, auth)
    with db() as s:  # simulate an attempt finished before v2: only a v1 row exists
        s.execute(delete(SeniorityAssessment))
        v1 = finalize_level(s, s.get(CoreInterview, iv["id"]), PYTHON_BACKEND_V1)
        s.commit()
        v1_id, v1_result = v1.id, v1.result
    got = client.get(f"{API}/interviews/{iv['id']}/level", headers=auth).json()
    assert got["policy"]["version"] == "v1" and got["unassessed_pools"] == []
    assert all("pools" not in c for c in got["coverage_by_level"].values())
    assert [(r.id, r.policy_version, r.result) for r in _rows(db, iv["id"])] == [(v1_id, "v1", v1_result)]
    with db() as s:  # an explicit v2 finalization adds a row; the v1 row is untouched and the current one is shown
        finalize_level(s, s.get(CoreInterview, iv["id"]))
        s.commit()
    rows = _rows(db, iv["id"])
    assert [r.policy_version for r in rows] == ["v1", "v2"] and (rows[0].id, rows[0].result) == (v1_id, v1_result)
    assert client.get(f"{API}/interviews/{iv['id']}/level", headers=auth).json()["policy"]["version"] == "v2"


def test_current_policy_row_wins_regardless_of_creation_order(client, auth, db, chat):
    iv = _finished(client, auth)  # v2 row first
    with db() as s:
        finalize_level(s, s.get(CoreInterview, iv["id"]), PYTHON_BACKEND_V1)  # v1 row stored later
        s.commit()
    assert [r.policy_version for r in _rows(db, iv["id"])] == ["v2", "v1"]
    assert client.get(f"{API}/interviews/{iv['id']}/level", headers=auth).json()["policy"]["version"] == "v2"
