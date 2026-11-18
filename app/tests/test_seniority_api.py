"""Assessed level (Task 5): stored on finish, immutable per (attempt, policy version), owner-only API, results views."""
import dataclasses
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from backend.api.core import seniority_evidence
from backend.api.level import attempt_evidence, finalize_level
from backend.domain.seniority import estimate, result_to_json
from backend.domain.seniority_policy import PRACTICE_ACTION, PYTHON_BACKEND_V1
from backend.experiments.config import InterviewMode, config_for
from backend.experiments.runner import run_experiment
from backend.models import CoreInterview, CoreTurn, SeniorityAssessment
from tests.test_level_probe_flow import GOOD, ProbeChat, cand, mixed
from tests.test_followup_flow import _use
from tests.test_practice_criteria import API, PracticeChat, _answer, _attempt

V2 = dataclasses.replace(PYTHON_BACKEND_V1, version="v2", rules=tuple(
    dataclasses.replace(r, tau=0.99) for r in PYTHON_BACKEND_V1.rules))


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
        iv["id"], iv["profile_id"], "python-backend", "v1")
    assert row.created_at is not None and row.policy_status == "WORKING_ASSUMPTION" and row.track == "python"
    with db() as s:
        turns = s.scalars(select(CoreTurn).where(CoreTurn.interview_id == iv["id"])).all()
        expected = result_to_json(estimate(PYTHON_BACKEND_V1, attempt_evidence(s, iv["id"])))
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
    assert [r.policy_version for r in _rows(db, rec.interview_id)] == ["v1"]


def test_policy_version_change_does_not_rewrite_history(client, auth, db, chat, monkeypatch):
    iv = _finished(client, auth)
    [old] = _rows(db, iv["id"])
    monkeypatch.setattr("backend.api.level.policy_for", lambda track: V2)
    got = client.get(f"{API}/interviews/{iv['id']}/level", headers=auth).json()
    assert got["policy"]["version"] == "v1" and len(_rows(db, iv["id"])) == 1  # reading never re-assesses
    with db() as s:
        new = finalize_level(s, s.get(CoreInterview, iv["id"]), V2)
        again = finalize_level(s, s.get(CoreInterview, iv["id"]), V2)
        s.commit()
        assert again.id == new.id  # idempotent per (attempt, policy version)
    rows = _rows(db, iv["id"])
    assert [r.policy_version for r in rows] == ["v1", "v2"]
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
        assert _rows(db, iv["id"])[0].result == result_to_json(estimate(PYTHON_BACKEND_V1, evidence))
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
        recomputed = result_to_json(estimate(PYTHON_BACKEND_V1, attempt_evidence(s, iv["id"])))
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
    assert got["policy"] == {"id": "python-backend", "version": "v1", "status": "WORKING_ASSUMPTION"}
    assert got["note"] == "Потребує експертної валідації" and got["created_at"] and row.policy_version == "v1"
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


def test_lead_counts_as_senior_section(client, auth, db, chat):
    iv = _finished(client, auth)
    client.put(f"{API}/profiles/{iv['profile_id']}", headers=auth, json={
        "name": "Профіль python", "track": "python", "target_level": "lead", "years_experience": 3})
    items, _ = _all_items(client, auth, iv["profile_id"])
    assert all((i["section"] == "DESIRED_LEVEL") == ((i["seniority"] or "").upper() == "SENIOR") for i in items)


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
