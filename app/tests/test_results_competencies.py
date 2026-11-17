from tests.test_interview_flow import llm  # noqa: F401
from tests.test_profiles_api import API, finished, mk_profile  # noqa: F401


def results(client, auth, pid):
    r = client.get(f"{API}/profiles/{pid}/results", params={"page_size": 50, "fitting": "all"}, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def by_action(payload):
    return {c["action_id"]: c for c in payload["competencies"]}


def test_competency_has_interview_score_and_self_rating(client, auth, finished):
    pid = finished["id"]
    target = results(client, auth, pid)["competencies"][0]["action_id"]
    assert client.put(f"{API}/profiles/{pid}/self-ratings/{target}", json={"value": 0.2}, headers=auth).status_code == 200
    c = by_action(results(client, auth, pid))[target]
    assert c["self_rating"] == 0.2
    assert c["interview_score"] is not None
    assert c["score"] == c["interview_score"]


def test_unrated_competency_has_null_self_rating(client, auth, finished):
    comps = results(client, auth, finished["id"])["competencies"]
    assert comps and all(c["self_rating"] is None and c["interview_score"] is not None for c in comps)


def test_self_rating_of_other_profile_not_shown(client, auth, finished):
    pid = finished["id"]
    target = results(client, auth, pid)["competencies"][0]["action_id"]
    other = mk_profile(client, auth, "python", "Другий профіль")
    assert client.put(f"{API}/profiles/{other['id']}/self-ratings/{target}", json={"value": 0.9},
                      headers=auth).status_code == 200
    assert by_action(results(client, auth, pid))[target]["self_rating"] is None


def test_short_reason_drops_near_duplicates_and_keeps_two():
    from backend.api.profiles import _short_reason
    reasons = [
        "Кандидат прямо зазначив, що не вміє працювати з цією темою, тому немає відомостей про ставки.",
        "Кандидат прямо зазначив, що не вміє працювати з цією темою, тому немає відомостей про CPA.",
        "Кандидат прямо зазначив, що не вміє працювати з цією темою, тому структура кампаній не описана.",
        "Відповідь не містить прикладів.",
        "Третє пояснення, яке вже зайве.",
    ]
    out = _short_reason(reasons)
    assert out.count("Кандидат прямо зазначив") == 1
    assert out.endswith("Відповідь не містить прикладів.") and "зайве" not in out


def test_short_reason_handles_empty_input():
    from backend.api.profiles import _short_reason
    assert _short_reason([]) == ""


def test_competency_reports_whether_evidence_was_sufficient(client, auth, llm):  # noqa: F811
    from tests.test_profiles_api import run_attempt, start
    llm.sufficient = True
    p = mk_profile(client, auth)
    a = start(client, auth, p["id"]).json()
    run_attempt(client, auth, a, answers=1)
    comps = results(client, auth, p["id"])["competencies"]
    assert comps and all(c["sufficient_evidence"] is True for c in comps)
