import pytest
from sqlalchemy import select

from backend.config import Settings
from backend.models import EvidenceItem, ProfileVersion
import backend.providers.llm as llm

ANSWER = "Перевіряю логи та метрики після кожного релізу"
VALID = ('{"level": 2, "evidence_quote": "логи", "confidence": "MEDIUM", '
         '"uncertainty": "", "followup": null}')


@pytest.fixture()
def llm_on(monkeypatch):
    monkeypatch.setattr(Settings, "llm_ready", property(lambda self: True))
    state = {"raw": VALID}
    monkeypatch.setattr(llm, "_text", lambda prompt, max_tokens=0: state["raw"])
    return state


def _answered(client, auth):
    cohort = client.post("/api/v1/discovery/snapshots", headers=auth, json={}).json()
    iv = client.post("/api/v1/interviews", headers=auth, json={"snapshot_id": cohort["id"]}).json()
    body = client.post(f"/api/v1/interviews/{iv['id']}/next-question", headers=auth,
                       json={"state_version": iv["state_version"]}).json()
    turn = body["current_question"]
    ans = client.post(f"/api/v1/interviews/{iv['id']}/answers", headers=auth, json={
        "turn_id": turn["id"], "answer_text": ANSWER, "idempotency_key": "key-evidence-01",
        "state_version": body["state_version"]}).json()
    return iv["id"], turn["id"], ans


def test_grading_disabled_without_provider_is_503(client, auth):
    iv_id, turn_id, _ = _answered(client, auth)
    r = client.post(f"/api/v1/interviews/{iv_id}/turns/{turn_id}/grade", headers=auth)
    assert r.status_code == 503


def test_llm_proposal_is_not_confirmed_and_does_not_change_profile(client, auth, llm_on, db):
    iv_id, turn_id, _ = _answered(client, auth)
    r = client.post(f"/api/v1/interviews/{iv_id}/turns/{turn_id}/grade", headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "PROPOSED" and r.json()["provenance"] == "LLM_PROPOSAL"
    client.post(f"/api/v1/interviews/{iv_id}/finish", headers=auth,
                json={"state_version": client.get(f"/api/v1/interviews/{iv_id}", headers=auth).json()["state_version"]})
    with db() as s:
        p1 = s.scalar(select(ProfileVersion).where(ProfileVersion.interview_id == iv_id, ProfileVersion.kind == "P1"))
        assert p1.provenance.get("competency") is None
        assert all(v != "HUMAN_REVIEW" for v in p1.provenance.values())


def test_human_accept_confirms_and_enters_profile(client, auth, llm_on, db):
    iv_id, turn_id, _ = _answered(client, auth)
    proposal = client.post(f"/api/v1/interviews/{iv_id}/turns/{turn_id}/grade", headers=auth).json()
    r = client.post(f"/api/v1/evidence/{proposal['id']}/review", headers=auth, json={"decision": "ACCEPT"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "CONFIRMED" and r.json()["provenance"] == "HUMAN_REVIEW"
    client.post(f"/api/v1/interviews/{iv_id}/finish", headers=auth,
                json={"state_version": client.get(f"/api/v1/interviews/{iv_id}", headers=auth).json()["state_version"]})
    with db() as s:
        p1 = s.scalar(select(ProfileVersion).where(ProfileVersion.interview_id == iv_id, ProfileVersion.kind == "P1"))
        assert p1.levels[proposal["competency_id"]] == 2
        assert p1.provenance[proposal["competency_id"]] == "HUMAN_REVIEW"


def test_other_user_cannot_review_or_read_evidence(client, auth, llm_on):
    iv_id, turn_id, _ = _answered(client, auth)
    proposal = client.post(f"/api/v1/interviews/{iv_id}/turns/{turn_id}/grade", headers=auth).json()
    other = client.post("/api/v1/auth/register", json={"email": "eve@example.com", "display_name": "Ева Тест",
                                                       "password": "long-password-456"}).json()
    other_h = {"Authorization": f"Bearer {other['token']}"}
    assert client.post(f"/api/v1/evidence/{proposal['id']}/review", headers=other_h,
                       json={"decision": "ACCEPT"}).status_code == 404
    assert client.get(f"/api/v1/interviews/{iv_id}/evidence", headers=other_h).status_code == 404


def test_adversarial_answer_cannot_confirm_a_level(client, auth, llm_on, monkeypatch):
    llm_on["raw"] = ('{"level": 3, "evidence_quote": "логи", "confidence": "HIGH", '
                     '"uncertainty": "", "followup": null}')
    iv_id, turn_id, _ = _answered(client, auth)
    proposal = client.post(f"/api/v1/interviews/{iv_id}/turns/{turn_id}/grade", headers=auth).json()
    assert proposal["status"] == "PROPOSED"  # injected-looking output is still only a proposal


def test_invalid_provider_output_is_rejected_and_stays_pending(client, auth, llm_on):
    llm_on["raw"] = "Відповідь чудова, рівень 3."
    iv_id, turn_id, _ = _answered(client, auth)
    r = client.post(f"/api/v1/interviews/{iv_id}/turns/{turn_id}/grade", headers=auth)
    assert r.status_code == 503
    turns = client.get(f"/api/v1/interviews/{iv_id}", headers=auth).json()["turns"]
    assert turns[0]["assessment_status"] == "PENDING_REVIEW"
