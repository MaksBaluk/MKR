import backend.api.profiles as prof_api
from tests.test_interview_flow import llm  # noqa: F401
from tests.test_profiles_api import API, mk_profile, finished  # noqa: F401


def results(client, auth, pid, **params):
    r = client.get(f"{API}/profiles/{pid}/results", params=params, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def _all(client, auth, pid, **kw):
    return results(client, auth, pid, page_size=50, **kw)


def test_default_returns_only_fitting(client, auth, finished, monkeypatch):
    real = prof_api.rank_items

    def fake(*a, **k):  # one vacancy with confirmed share, one without
        items = real(*a, **k)
        items[0].update(z=1, confirmed_share=40)
        items[1].update(z=1, confirmed_share=0)
        return items
    monkeypatch.setattr(prof_api, "rank_items", fake)
    r = _all(client, auth, finished["id"])
    assert len(r["items"]) == min(50, r["total"]) and r["total"] == r["fitting_total"] >= 1 and all(i["fits"] for i in r["items"])
    assert r["total"] == r["fitting_total"] <= r["all_total"]


def test_all_and_nonfitting(client, auth, finished):
    pid = finished["id"]
    everything = _all(client, auth, pid, fitting="all")
    non = _all(client, auth, pid, fitting="nonfitting")
    assert everything["total"] == everything["all_total"] > 0 and len(everything["items"]) == min(50, everything["total"])
    assert non["items"] and all(not i["fits"] for i in non["items"])
    assert non["total"] == everything["all_total"] - everything["fitting_total"]


def test_zero_share_is_not_fitting(client, auth, finished, monkeypatch):
    real = prof_api.rank_items

    def fake(*a, **k):
        items = real(*a, **k)
        items[0].update(z=2, confirmed_share=0)
        return items
    monkeypatch.setattr(prof_api, "rank_items", fake)
    r = _all(client, auth, finished["id"], fitting="nonfitting")
    zero = [i for i in r["items"] if i["confirmed_share"] == 0]
    assert zero and all(i["fits"] is False for i in r["items"])


def test_reasons_non_empty_strengths_first(client, auth, finished):
    for i in _all(client, auth, finished["id"], fitting="all")["items"]:
        assert i["reasons"] and all(isinstance(x, str) and x for x in i["reasons"])
        if i["unknown_count"]:
            assert i["reasons"][-1] == f"Не оцінено: {i['unknown_count']} вимог"
        assert len(i["reasons"]) == len(i["strengths"]) + len(i["gaps"]) + (1 if i["unknown_count"] else 0)


def test_no_finished_attempt(client, auth):
    p = mk_profile(client, auth)
    r = results(client, auth, p["id"])
    assert r["has_results"] is False and r["fitting_total"] == 0 and r["all_total"] == 0


def test_bogus_fitting_422(client, auth, finished):
    assert client.get(f"{API}/profiles/{finished['id']}/results", params={"fitting": "bogus"},
                      headers=auth).status_code == 422
