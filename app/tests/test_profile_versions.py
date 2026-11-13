from sqlalchemy import select

from backend.models import ProfileVersion, MatchRun


def _versions(db, interview_id):
    with db() as session:
        rows = session.scalars(select(ProfileVersion).where(ProfileVersion.interview_id == interview_id)).all()
        return {row.kind: {"id": row.id, "levels": row.levels} for row in rows}


def _complete_free_text(client, auth):
    cohort = client.post("/api/v1/discovery/snapshots", headers=auth, json={}).json()
    iv = client.post("/api/v1/interviews", headers=auth, json={"snapshot_id": cohort["id"]}).json()
    state = iv["state_version"]
    for index in range(iv["question_budget"]):
        body = client.post(f"/api/v1/interviews/{iv['id']}/next-question", headers=auth,
                           json={"state_version": state}).json()
        if body["current_question"] is None:
            break
        state = body["state_version"]
        ans = client.post(f"/api/v1/interviews/{iv['id']}/answers", headers=auth, json={
            "turn_id": body["current_question"]["id"], "answer_text": f"Відповідь {index}",
            "idempotency_key": f"key-complete-{index:03d}", "state_version": state}).json()
        assert "state_version" in ans, ans
        state = ans["state_version"]
        if ans["status"] == "COMPLETED":
            break
    # Completion happens only through finish (P1 is written there).
    client.post(f"/api/v1/interviews/{iv['id']}/finish", headers=auth,
                json={"state_version": client.get(f"/api/v1/interviews/{iv['id']}", headers=auth).json()["state_version"]})
    return iv["id"]


def test_p0_created_on_interview_start(client, auth, db):
    cohort = client.post("/api/v1/discovery/snapshots", headers=auth, json={}).json()
    iv = client.post("/api/v1/interviews", headers=auth, json={"snapshot_id": cohort["id"]}).json()
    versions = _versions(db, iv["id"])
    assert "P0" in versions
    assert versions["P0"]["levels"] == iv["baseline_profile"]


def test_p1_on_finish_and_match_uses_it(client, auth, db):
    iv_id = _complete_free_text(client, auth)
    client.post(f"/api/v1/interviews/{iv_id}/finish", headers=auth,
                json={"state_version": client.get(f"/api/v1/interviews/{iv_id}", headers=auth).json()["state_version"]})
    versions = _versions(db, iv_id)
    assert "P1" in versions
    snap_id = client.get(f"/api/v1/interviews/{iv_id}", headers=auth).json()["snapshot_id"]
    run = client.post("/api/v1/matches", headers=auth, json={"snapshot_id": snap_id, "interview_id": iv_id}).json()
    assert run["profile"]["source"] == "POST_INTERVIEW"
    assert run["profile_version_id"] == versions["P1"]["id"]


def test_no_accepted_evidence_means_unchanged_results(client, auth, db):
    iv_id = _complete_free_text(client, auth)
    snap_id = client.get(f"/api/v1/interviews/{iv_id}", headers=auth).json()["snapshot_id"]
    run = client.post("/api/v1/matches", headers=auth, json={"snapshot_id": snap_id, "interview_id": iv_id}).json()
    assert run["unchanged_reason"] == "NO_ACCEPTED_EVIDENCE"
    versions = _versions(db, iv_id)
    assert versions["P1"]["levels"] == versions["P0"]["levels"]
