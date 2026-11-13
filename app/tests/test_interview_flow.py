import json
import re
from types import SimpleNamespace

import pytest

from backend.agents.prompts import INTERVIEWER_SYSTEM


class FakeChat:
    """Fake chat model patched at backend.api.core.get_chat_model: interviewer or evaluator by system prompt."""

    def __init__(self, score=0.6, off_topic=False, sufficient=False):
        self.score, self.off_topic, self.sufficient = score, off_topic, sufficient
        self.human_inputs = []

    def invoke(self, messages, *a, **k):
        system, human = messages[0].content, messages[1].content
        self.human_inputs.append(human)
        if system == INTERVIEWER_SYSTEM:
            return SimpleNamespace(content="Опишіть, як ви проєктували схему бази даних?")
        data = dict(line.split(": ", 1) for line in human.splitlines() if re.match(r"\w+: ", line))
        action = json.loads(data["action_id"])
        allowed = json.loads(data["allowed_criterion_ids"])
        turn_id = re.search(r"turn_id=\"([^\"]+)\"", human).group(1)
        text = json.loads(re.search(r">(\".*\")</candidate_answer>", human).group(1))
        crit = [{"criterion_id": c, "score": None if self.off_topic else self.score, "reason": "з відповіді",
                 "evidence": [] if self.off_topic else [{"turn_id": turn_id, "exact_excerpt": text}]} for c in allowed]
        return SimpleNamespace(content=json.dumps({"action_id": action, "rubric_version": "auto-1",
                                                   "off_topic": self.off_topic, "criteria": crit,
                                                   "sufficient_evidence": self.sufficient}))


@pytest.fixture()
def llm(monkeypatch):
    fake = FakeChat()
    monkeypatch.setattr("backend.api.core.get_chat_model", lambda: fake)
    return fake


@pytest.fixture()
def no_llm(monkeypatch):
    monkeypatch.setattr("backend.api.core.get_chat_model", lambda: None)


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


def test_resume_returns_open_interview_without_browser_storage(client, auth, interview):
    r = client.get("/api/v1/interviews/active", headers=auth).json()
    assert r["interview"]["id"] == interview["id"]
    assert r["interview"]["status"] == "ACTIVE"


def test_finished_interview_not_active(client, auth, interview):
    client.post(f"/api/v1/interviews/{interview['id']}/finish", json={"version": 0}, headers=auth)
    assert client.get("/api/v1/interviews/active", headers=auth).json()["interview"] is None
    done = client.get("/api/v1/interviews/latest-finished", headers=auth).json()["interview"]
    assert done["id"] == interview["id"]


def test_ungraded_answer_moves_to_next_topic(client, auth, interview):
    q1 = _next(client, auth, interview, 0).json()
    ans = client.post(f"/api/v1/interviews/{interview['id']}/answers", headers=auth, json={
        "turn_id": q1["turn"]["id"], "text": "Робив сервіс.", "version": q1["version"],
        "idempotency_key": "answer-key-0010"}).json()
    q2 = _next(client, auth, interview, ans["version"]).json()
    assert q2["turn"]["action_id"] != q1["turn"]["action_id"]


def test_fallback_question_comes_from_bank_and_has_action_name(client, auth, interview):
    turn = _next(client, auth, interview, 0).json()["turn"]
    assert turn["action_name"] and "Розкажіть про ваш практичний досвід" not in turn["question_text"]


def test_recommendations_top_five_with_explanations(client, auth, cohort, no_llm):
    body = client.post("/api/v1/recommendations", json={"cohort_id": cohort}, headers=auth).json()
    assert len(body["items"]) == 5 and body["total"] > 5
    first = body["items"][0]
    assert 0 <= first["confirmed_share"] <= 100
    assert first["tags"] and "strengths" in first and "gaps" in first and "unknown_count" in first


def test_off_topic_answer_not_ranked_and_same_action_reasked(client, auth, cohort, llm):
    iv = client.post("/api/v1/interviews", json={"cohort_id": cohort}, headers=auth).json()
    q1 = _next(client, auth, iv, 0).json()
    llm.off_topic = True
    ans = client.post(f"/api/v1/interviews/{iv['id']}/answers", headers=auth, json={
        "turn_id": q1["turn"]["id"], "text": "як приготувати борщ", "version": q1["version"],
        "idempotency_key": "answer-key-0020"}).json()
    assert ans["assessment_status"] == "ACCEPTED"
    items = client.get("/api/v1/assessments", headers=auth).json()["items"]
    assert items and all(i["score"] is None for i in items)
    ranked = client.post("/api/v1/recommendations", json={"cohort_id": cohort}, headers=auth).json()["items"]
    assert all(i["label"] != "RANKED" for i in ranked)
    llm.off_topic = False
    q2 = _next(client, auth, iv, ans["version"]).json()
    assert q2["turn"]["action_id"] == q1["turn"]["action_id"]
    assert "off_topic_detected: true" in llm.human_inputs[-1]


def _answer(client, auth, iv, q, text, key):
    return client.post(f"/api/v1/interviews/{iv['id']}/answers", headers=auth, json={
        "turn_id": q["turn"]["id"], "text": text, "version": q["version"], "idempotency_key": key}).json()


def test_weak_first_answer_gets_second_question_on_same_topic(client, auth, cohort, llm):
    iv = client.post("/api/v1/interviews", json={"cohort_id": cohort}, headers=auth).json()
    q1 = _next(client, auth, iv, 0).json()
    llm.score = 0.2
    ans = _answer(client, auth, iv, q1, "Трохи знаю.", "answer-key-0101")
    q2 = _next(client, auth, iv, ans["version"]).json()
    assert q2["turn"]["action_id"] == q1["turn"]["action_id"]
    ans2 = _answer(client, auth, iv, q2, "Більше не знаю.", "answer-key-0102")
    q3 = _next(client, auth, iv, ans2["version"]).json()
    assert q3["turn"]["action_id"] != q1["turn"]["action_id"]


def test_strong_sufficient_first_answer_closes_topic(client, auth, cohort, llm):
    iv = client.post("/api/v1/interviews", json={"cohort_id": cohort}, headers=auth).json()
    q1 = _next(client, auth, iv, 0).json()
    llm.score, llm.sufficient = 0.9, True
    ans = _answer(client, auth, iv, q1, "Детально проєктував схему з індексами.", "answer-key-0111")
    q2 = _next(client, auth, iv, ans["version"]).json()
    assert q2["turn"]["action_id"] != q1["turn"]["action_id"]


def test_five_question_cap_per_topic_still_enforced(client, auth, cohort, llm):
    iv = client.post("/api/v1/interviews", json={"cohort_id": cohort}, headers=auth).json()
    llm.off_topic = True  # null scores: the topic stays open for re-asks
    q = _next(client, auth, iv, 0).json()
    first = q["turn"]["action_id"]
    seen = []
    for i in range(6):
        seen.append(q["turn"]["action_id"])
        ans = _answer(client, auth, iv, q, "як приготувати борщ", f"answer-key-02{i:02d}")
        q = _next(client, auth, iv, ans["version"]).json()
    assert seen.count(first) == 5 and seen[5] != first


def test_interviewer_gets_candidate_level_from_profile(client, auth, cohort, llm, db):
    from backend.models import CandidateProfile
    iv = client.post("/api/v1/interviews", json={"cohort_id": cohort}, headers=auth).json()
    with db() as s:  # the attempt's profile exists now; make it an early-career one
        for p in s.query(CandidateProfile).all():
            p.desired_title, p.years_experience = "Python Developer", 1
        s.commit()
    _next(client, auth, iv, 0)
    assert 'candidate_level: "junior"' in llm.human_inputs[-1] and "years_experience: 1" in llm.human_inputs[-1]
