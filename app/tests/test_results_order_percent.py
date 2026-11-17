from tests.test_interview_flow import llm  # noqa: F401
from tests.test_profiles_api import API, finished  # noqa: F401


def items(client, auth, pid, **params):
    r = client.get(f"{API}/profiles/{pid}/results", params={"page_size": 50, "fitting": "all", **params}, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_results_sorted_by_percent_then_z_x_id(client, auth, finished):  # noqa: F811
    rows = items(client, auth, finished["id"])
    keys = [(-i["confirmed_share"], -i["z"], -i["x"], i["vacancy_id"]) for i in rows]
    assert len(rows) > 5 and keys == sorted(keys)


def test_fits_means_some_confirmed_share(client, auth, finished):  # noqa: F811
    for i in items(client, auth, finished["id"]):
        assert i["fits"] == (i["confirmed_share"] > 0)


def test_fitting_filter_keeps_percent_order(client, auth, finished):  # noqa: F811
    every = [i["vacancy_id"] for i in items(client, auth, finished["id"]) if i["fits"]]
    only = [i["vacancy_id"] for i in items(client, auth, finished["id"], fitting="fitting")]
    assert only == every
