import json

import pytest

from backend.providers import roles
from backend.providers.roles import EVALUATOR_SYSTEM, INTERVIEWER_SYSTEM


class FakeLLM:
    def __init__(self, score=0.6):
        self.score = score

    def complete(self, system, user, *, timeout_s):
        if system == INTERVIEWER_SYSTEM:
            return "Опишіть, як ви проєктували схему бази даних?"
        data = json.loads(user)
        turn_id, text = next(iter(data["turns"].items()))
        action = data["action_id"]
        return json.dumps({
            "action_id": action, "rubric_version": "auto-1",
            "criteria": [{"criterion_id": action, "score": self.score, "reason": "з відповіді",
                          "evidence": [{"turn_id": turn_id, "exact_excerpt": text}]}],
            "sufficient_evidence": True, "needs_followup": False, "followup_goal": None, "limitations": ""})


@pytest.fixture()
def llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr("backend.api.core.get_transport", lambda: fake)
    return fake


@pytest.fixture()
def no_llm(monkeypatch):
    monkeypatch.setattr("backend.api.core.get_transport", lambda: None)


@pytest.fixture()
def cohort(client, auth):
    return client.post("/api/v1/cohorts/auto", headers=auth).json()["cohort_id"]


@pytest.fixture()
def interview(client, auth, cohort, no_llm):
    return client.post("/api/v1/interviews", json={"cohort_id": cohort}, headers=auth).json()


def _next(client, auth, iv, version):
    return client.post(f"/api/v1/interviews/{iv['id']}/next-question", json={"version": version}, headers=auth)


def test_question_persisted_and_fallback_is_ungraded(client, auth, interview):
    r = _next(client, auth, interview, 0)
    assert r.status_code == 200, r.text
    turn = r.json()["turn"]
    assert turn["question_source"] == "FALLBACK_UNGRADED" and turn["graded"] is False


def test_pending_question_not_regenerated(client, auth, interview):
    first = _next(client, auth, interview, 0).json()
    replay = _next(client, auth, interview, first["version"] - 1)
    # version moved on; stale version is rejected, pending question still served via GET
    assert replay.status_code == 409
    state = client.get(f"/api/v1/interviews/{interview['id']}", headers=auth).json()
    assert state["pending_turn"]["id"] == first["turn"]["id"]


def test_stale_version_rejected(client, auth, interview):
    assert _next(client, auth, interview, 7).status_code == 409


def test_answer_replay_same_key_returns_same_turn(client, auth, interview):
    q = _next(client, auth, interview, 0).json()
    body = {"turn_id": q["turn"]["id"], "text": "Проєктував схему з індексами.", "version": q["version"],
            "idempotency_key": "answer-key-0001"}
    first = client.post(f"/api/v1/interviews/{interview['id']}/answers", json=body, headers=auth).json()
    again = client.post(f"/api/v1/interviews/{interview['id']}/answers", json=body, headers=auth).json()
    assert first["replayed"] is False and again["replayed"] is True
    assert again["turn"]["id"] == first["turn"]["id"]


def test_graded_answer_creates_read_only_assessment(client, auth, cohort, llm):
    iv = client.post("/api/v1/interviews", json={"cohort_id": cohort}, headers=auth).json()
    q = _next(client, auth, iv, 0).json()
    assert q["turn"]["question_source"] == "LLM_INTERVIEWER"
    body = {"turn_id": q["turn"]["id"], "text": "Проєктував схему з індексами.", "version": q["version"],
            "idempotency_key": "answer-key-0002"}
    ans = client.post(f"/api/v1/interviews/{iv['id']}/answers", json=body, headers=auth).json()
    assert ans["assessment_status"] == "ACCEPTED"
    items = client.get("/api/v1/assessments", headers=auth).json()["items"]
    assert items and items[0]["editable"] is False and items[0]["score"] == 0.6


def test_assessments_have_no_write_endpoints(client, auth):
    assert client.put("/api/v1/assessments/x", json={"score": 1}, headers=auth).status_code in (404, 405)
    assert client.post("/api/v1/assessments", json={"score": 1}, headers=auth).status_code in (404, 405)


def test_interview_scoped_to_owner(client, auth, interview):
    reg = client.post("/api/v1/auth/register", json={
        "email": "iso-owner@example.test", "display_name": "Iso Owner", "password": "another-pass-456"})
    token = reg.json()["token"]
    r = client.get(f"/api/v1/interviews/{interview['id']}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404


def test_recommendations_low_information_without_scores(client, auth, cohort, no_llm):
    r = client.post("/api/v1/recommendations", json={"cohort_id": cohort}, headers=auth)
    assert r.status_code == 200
    items = r.json()["items"]
    assert items and all(i["label"] in ("LOW_INFORMATION", "NOT_EVALUABLE") for i in items)


def test_recommendations_ranked_after_scores(client, auth, cohort, llm):
    iv = client.post("/api/v1/interviews", json={"cohort_id": cohort}, headers=auth).json()
    q = _next(client, auth, iv, 0).json()
    client.post(f"/api/v1/interviews/{iv['id']}/answers", headers=auth, json={
        "turn_id": q["turn"]["id"], "text": "Проєктував схему з індексами.", "version": q["version"],
        "idempotency_key": "answer-key-0003"})
    items = client.post("/api/v1/recommendations", json={"cohort_id": cohort}, headers=auth).json()["items"]
    assert any(i["label"] == "RANKED" for i in items)
    assert "ймовірність працевлаштування" in client.post("/api/v1/recommendations", json={"cohort_id": cohort},
                                    headers=auth).json()["note"]


def test_self_rating_zero_is_stored_and_null_is_unknown(client, auth):
    action = _track_action(client, auth)
    r = client.put(f"/api/v1/profile/self-ratings/{action}", json={"value": 0.0}, headers=auth)
    assert r.status_code == 200 and r.json()["value"] == 0.0
    listed = {x["action_id"]: x["value"] for x in client.get("/api/v1/profile", headers=auth).json()["self_ratings"]}
    assert listed[action] == 0.0
    r2 = client.put(f"/api/v1/profile/self-ratings/{action}", json={"value": None}, headers=auth)
    assert r2.json()["value"] is None


def _track_action(client, auth):
    cohort = client.post("/api/v1/cohorts/auto", headers=auth).json()["cohort_id"]
    market = client.get(f"/api/v1/cohorts/{cohort}/market", headers=auth).json()["skills"]
    return market[0]["action_id"]
