from sqlalchemy import select

from backend.models import ProfileVersion


def _start(client, auth):
    cohort = client.post("/api/v1/discovery/snapshots", headers=auth, json={}).json()
    iv = client.post("/api/v1/interviews", headers=auth, json={"snapshot_id": cohort["id"]}).json()
    return iv


def _next(client, auth, iv):
    r = client.post(f"/api/v1/interviews/{iv['id']}/next-question", headers=auth,
                    json={"state_version": iv["state_version"]})
    assert r.status_code == 200, r.text
    return r.json()


def test_free_text_is_default_without_llm(client, auth):
    iv = _start(client, auth)
    body = _next(client, auth, iv)
    q = body["current_question"]
    assert q["question_kind"] == "FREE_TEXT"
    assert q["question_format"] == "OPEN"
    assert q["question_source"] == "CURATED_BANK"
    assert q["question_options"] == []


def test_mcq_is_only_second_optional_check_for_each_competency():
    from backend.providers.questions import next_question, question_bank
    for action in list(question_bank())[:5]:
        assert next_question(action, 0)["kind"] == "FREE_TEXT"
        assert next_question(action, 1)["kind"] == "MULTIPLE_CHOICE"


def test_typed_answer_saved_as_pending_review_without_options(client, auth):
    iv = _start(client, auth)
    body = _next(client, auth, iv)
    turn = body["current_question"]
    r = client.post(f"/api/v1/interviews/{iv['id']}/answers", headers=auth, json={
        "turn_id": turn["id"], "answer_text": "Аналізую метрики та логи", "idempotency_key": "key-typed-0001",
        "state_version": body["state_version"]})
    assert r.status_code == 200, r.text
    stored = r.json()["turns"][0]
    assert stored["assessment_status"] == "PENDING_REVIEW"
    assert stored["answer_text"] == "Аналізую метрики та логи"


def test_whitespace_answer_rejected(client, auth):
    iv = _start(client, auth)
    body = _next(client, auth, iv)
    r = client.post(f"/api/v1/interviews/{iv['id']}/answers", headers=auth, json={
        "turn_id": body["current_question"]["id"], "answer_text": "   ", "idempotency_key": "key-space-0001",
        "state_version": body["state_version"]})
    assert r.status_code == 422


def test_answer_idempotent_replay_and_stale_version(client, auth):
    iv = _start(client, auth)
    body = _next(client, auth, iv)
    turn_id = body["current_question"]["id"]
    payload = {"turn_id": turn_id, "answer_text": "Перша відповідь", "idempotency_key": "key-replay-01",
               "state_version": body["state_version"]}
    first = client.post(f"/api/v1/interviews/{iv['id']}/answers", headers=auth, json=payload)
    second = client.post(f"/api/v1/interviews/{iv['id']}/answers", headers=auth, json=payload)
    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["idempotent_replay"] is True
    assert len(second.json()["turns"]) == 1
    stale = client.post(f"/api/v1/interviews/{iv['id']}/answers", headers=auth, json={
        **payload, "idempotency_key": "key-other-0002", "answer_text": "Інша"})
    assert stale.status_code == 409


def test_resume_returns_same_outstanding_question(client, auth):
    iv = _start(client, auth)
    body = _next(client, auth, iv)
    question_id = body["current_question"]["id"]
    paused = client.post(f"/api/v1/interviews/{iv['id']}/pause", headers=auth,
                         json={"state_version": body["state_version"]}).json()
    resumed = client.post(f"/api/v1/interviews/{iv['id']}/resume", headers=auth,
                          json={"state_version": paused["state_version"]}).json()
    assert resumed["current_question"]["id"] == question_id


def test_interview_rejected_after_track_change(client, auth):
    cohort = client.post("/api/v1/discovery/snapshots", headers=auth, json={}).json()
    profile = client.get("/api/v1/profile", headers=auth).json()
    client.put("/api/v1/profile", headers=auth, json={**profile, "track": "marketing"})
    r = client.post("/api/v1/interviews", headers=auth, json={"snapshot_id": cohort["id"]})
    assert r.status_code == 422
