from tests.test_interview_flow import llm  # noqa: F401
from tests.test_profiles_api import API, finished  # noqa: F401


def items(client, auth, pid, **params):
    r = client.get(f"{API}/profiles/{pid}/results", params={"page_size": 50, "fitting": "all", **params}, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_results_sorted_by_percent_then_215_key_then_tv_jv(client, auth, finished, db):  # noqa: F811
    from backend.api.core import _revisions
    from backend.domain.core_flow import self_claim_metrics
    from backend.models import CohortSnapshot, CoreInterview
    pid = finished["id"]
    ratings = {c["action_id"]: 0.3 + 0.07 * (n % 9) for n, c in enumerate(
        client.get(f"{API}/profiles/{pid}/results", headers=auth).json()["competencies"])}
    for a, v in ratings.items():
        assert client.put(f"{API}/profiles/{pid}/self-ratings/{a}", json={"value": v}, headers=auth).status_code == 200
    rows = items(client, auth, pid)
    s = db()
    iv = s.query(CoreInterview).filter_by(profile_id=pid).one()
    revs = {r["id"]: r for r in _revisions(s.get(CohortSnapshot, iv.cohort_id))}
    keys = []
    for i in rows:
        t, j = self_claim_metrics(revs[i["vacancy_id"]]["groups"], ratings)
        keys.append((-i["confirmed_share"], -i["z"], -i["x"], -i["l_mandatory"], -i["l_preferred"], i["w_mandatory"],
                     i["w_preferred"], -t, -j, i["vacancy_id"]))
    assert len(rows) > 5 and keys == sorted(keys)
    assert any(a[0] == b[0] for a, b in zip(keys, keys[1:]))  # equal percents exist, so the (2.15)+T/J tie-break is exercised


def test_fits_means_some_confirmed_share(client, auth, finished):  # noqa: F811
    for i in items(client, auth, finished["id"]):
        assert i["fits"] == (i["confirmed_share"] > 0)


def test_fitting_filter_keeps_relative_order(client, auth, finished):  # noqa: F811
    every = [i["vacancy_id"] for i in items(client, auth, finished["id"]) if i["fits"]]
    only = [i["vacancy_id"] for i in items(client, auth, finished["id"], fitting="fitting")]
    assert every
    assert only[:len(every)] == every  # 'all' is page-capped at 50; filter keeps relative order


def test_other_profile_ratings_do_not_change_order(client, auth, finished):  # noqa: F811
    from tests.test_profiles_api import mk_profile, run_attempt, start
    b = mk_profile(client, auth, name="Профіль B")
    run_attempt(client, auth, start(client, auth, b["id"]).json(), answers=3)
    before = [i["vacancy_id"] for i in items(client, auth, b["id"])]
    for c in client.get(f"{API}/profiles/{finished['id']}/results", headers=auth).json()["competencies"]:
        client.put(f"{API}/profiles/{finished['id']}/self-ratings/{c['action_id']}", json={"value": 0.95}, headers=auth)
    assert [i["vacancy_id"] for i in items(client, auth, b["id"])] == before
    assert client.get(f"{API}/profiles/{b['id']}/self-ratings", headers=auth).json()["items"] == []
