import uuid

from tests.test_interview_flow import llm  # noqa: F401
from tests.test_profiles_api import API, mk_profile, start  # noqa: F401


def _answer_until_done(client, auth, attempt, limit=80):
    version = attempt["version"]
    for _ in range(limit):
        q = client.post(f"{API}/interviews/{attempt['id']}/next-question", json={"version": version},
                        headers=auth).json()
        if q.get("done"):
            return q
        a = client.post(f"{API}/interviews/{attempt['id']}/answers", headers=auth, json={
            "turn_id": q["turn"]["id"], "text": "Працював із цим на проєкті.", "version": q["version"],
            "idempotency_key": str(uuid.uuid4())})
        assert a.status_code == 200, a.text
        version = a.json()["version"]
    raise AssertionError("interview did not finish within the limit")


def test_interview_finishes_itself_when_plan_is_exhausted(client, auth, llm):  # noqa: F811
    p = mk_profile(client, auth)
    a = start(client, auth, p["id"]).json()
    done = _answer_until_done(client, auth, a)
    assert done["done"] is True and done["turn"] is None
    iv = client.get(f"{API}/interviews/{a['id']}", headers=auth).json()
    assert iv["status"] == "FINISHED"
    late = client.post(f"{API}/interviews/{a['id']}/answers", headers=auth, json={
        "turn_id": "x", "text": "ще відповідь", "version": done["version"], "idempotency_key": str(uuid.uuid4())})
    assert late.status_code == 409


def test_done_interview_reports_finished_status(client, auth, llm):  # noqa: F811
    p = mk_profile(client, auth)
    a = start(client, auth, p["id"]).json()
    _answer_until_done(client, auth, a)
    again = client.post(f"{API}/interviews/{a['id']}/next-question", json={"version": 10**6}, headers=auth)
    assert again.status_code in (409, 422)


def test_parallel_next_question_returns_the_winner_not_a_500(client, auth, db, llm, monkeypatch):  # noqa: F811
    """Two parallel next-question calls: the loser hits the unique (interview, sequence) key and must not get a 500."""
    import backend.api.core as core
    from backend.models import CoreTurn

    p = mk_profile(client, auth)
    a = start(client, auth, p["id"]).json()
    real = core.run_ask

    def racing(*args, **kwargs):  # the other request inserts sequence 1 while this one is still generating
        with db() as s:
            s.add(CoreTurn(interview_id=a["id"], sequence=1, action_id="fastapi", question_text="Питання-переможець",
                           question_source="LLM_INTERVIEWER"))
            s.commit()
        return real(*args, **kwargs)

    monkeypatch.setattr(core, "run_ask", racing)
    r = client.post(f"{API}/interviews/{a['id']}/next-question", json={"version": a["version"]}, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["turn"]["question_text"] == "Питання-переможець" and r.json()["done"] is False
