from tests.test_interview_flow import llm  # noqa: F401
from tests.test_profiles_api import API, mk_profile, run_attempt, start  # noqa: F401


def profile(client, auth, pid):
    r = client.get(f"{API}/profiles/{pid}", headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def test_profile_without_attempts_has_no_attempt_state(client, auth):
    p = profile(client, auth, mk_profile(client, auth)["id"])
    assert p["open_attempt"] is None and p["latest_finished_attempt"] is None


def test_open_attempt_is_reported(client, auth, llm):  # noqa: F811
    p = mk_profile(client, auth)
    a = start(client, auth, p["id"]).json()
    got = profile(client, auth, p["id"])
    assert got["open_attempt"]["id"] == a["id"] and got["open_attempt"]["cohort_id"] == a["cohort_id"]
    assert got["open_attempt"]["status"] == "ACTIVE" and got["latest_finished_attempt"] is None


def test_finished_attempt_replaces_open_one(client, auth, llm):  # noqa: F811
    p = mk_profile(client, auth)
    a = start(client, auth, p["id"]).json()
    run_attempt(client, auth, a, answers=1)
    got = profile(client, auth, p["id"])
    assert got["open_attempt"] is None
    assert got["latest_finished_attempt"] == {"id": a["id"], "cohort_id": a["cohort_id"]}
