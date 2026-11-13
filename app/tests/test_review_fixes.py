from sqlalchemy import select

from backend.models import ProfileVersion
from backend.config import Settings
import backend.providers.llm as llm


def _start(client, auth):
    cohort = client.post("/api/v1/discovery/snapshots", headers=auth, json={}).json()
    iv = client.post("/api/v1/interviews", headers=auth, json={"snapshot_id": cohort["id"]}).json()
    return cohort, iv


def test_last_answer_stays_gradable_and_interview_not_auto_completed(client, auth, monkeypatch):
    monkeypatch.setattr(Settings, "llm_ready", property(lambda self: True))
    monkeypatch.setattr(llm, "_text", lambda prompt, max_tokens=0: '{"level": 1, "evidence_quote": "логи", "confidence": "LOW", "uncertainty": "", "followup": null}')
    cohort, iv = _start(client, auth)
    state = iv["state_version"]
    turn_id = None
    for index in range(iv["question_budget"]):
        body = client.post(f"/api/v1/interviews/{iv['id']}/next-question", headers=auth,
                           json={"state_version": state}).json()
        if body["current_question"] is None:
            break
        state = body["state_version"]
        turn_id = body["current_question"]["id"]
        ans = client.post(f"/api/v1/interviews/{iv['id']}/answers", headers=auth, json={
            "turn_id": turn_id, "answer_text": f"логи {index}", "idempotency_key": f"key-last-{index:04d}",
            "state_version": state}).json()
        state = ans["state_version"]
    assert ans["status"] != "COMPLETED"
    r = client.post(f"/api/v1/interviews/{iv['id']}/turns/{turn_id}/grade", headers=auth)
    assert r.status_code == 200, r.text


def test_track_change_blocks_running_interview_and_match(client, auth):
    cohort, iv = _start(client, auth)
    first = client.post(f"/api/v1/interviews/{iv['id']}/next-question", headers=auth,
                        json={"state_version": iv["state_version"]}).json()
    profile = client.get("/api/v1/profile", headers=auth).json()
    client.put("/api/v1/profile", headers=auth, json={**profile, "track": "marketing"})
    r = client.post(f"/api/v1/interviews/{iv['id']}/next-question", headers=auth,
                    json={"state_version": first["state_version"]})
    assert r.status_code == 409
    m = client.post("/api/v1/matches", headers=auth, json={"snapshot_id": cohort["id"], "interview_id": iv["id"]})
    assert m.status_code == 409


def test_evidence_quality_counts_only_current_track_competencies(client, auth):
    profile = client.get("/api/v1/profile", headers=auth).json()
    client.put("/api/v1/profile", headers=auth, json={**profile, "track": "marketing"})
    body = client.get("/api/v1/discovery/recommendations", headers=auth).json()
    assessed = body["evidence_quality"]["assessed_competencies"]
    total = body["evidence_quality"]["total_competencies"]
    assert assessed <= total
