from backend.domain.core_flow import tau_for
from tests.test_interview_flow import llm  # noqa: F401
from tests.test_profiles_api import API, finished, mk_profile  # noqa: F401


def first_vacancy_id(client, auth, pid):
    return client.get(f"{API}/profiles/{pid}/results", params={"fitting": "all", "page_size": 1},
                      headers=auth).json()["items"][0]["vacancy_id"]


def breakdown(client, auth, pid, vid):
    return client.get(f"{API}/profiles/{pid}/results/{vid}", headers=auth)


def test_breakdown_lists_every_requirement_with_level_score_and_state(client, auth, finished):  # noqa: F811
    pid = finished["id"]
    vid = first_vacancy_id(client, auth, pid)
    r = breakdown(client, auth, pid, vid)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["vacancy_id"] == vid and body["groups"] and "confirmed_share" in body and "fits" in body
    for g in body["groups"]:
        assert g["kind"] in ("MANDATORY", "DESIRED") and g["status"] in ("SATISFIED", "FAILED", "UNRESOLVED")
        assert g["alternatives"]
        for a in g["alternatives"]:
            assert a["required_level"] in (1, 2, 3) and a["threshold"] == tau_for(a["required_level"])
            score = a["candidate_score"]
            expected = "UNKNOWN" if score is None else "MET" if score >= a["threshold"] else "GAP"
            assert a["state"] == expected or (expected == "GAP" and a["state"] == "BORDERLINE")


def test_summary_counts_groups_by_status(client, auth, finished):  # noqa: F811
    pid = finished["id"]
    body = breakdown(client, auth, pid, first_vacancy_id(client, auth, pid)).json()
    counts = {s: sum(1 for g in body["groups"] if g["status"] == s) for s in ("SATISFIED", "FAILED", "UNRESOLVED")}
    assert body["summary"] == {"met": counts["SATISFIED"], "gap": counts["FAILED"], "unknown": counts["UNRESOLVED"]}


def test_unknown_vacancy_and_missing_results_are_404(client, auth, finished):  # noqa: F811
    assert breakdown(client, auth, finished["id"], "no-such-vacancy").status_code == 404
    fresh = mk_profile(client, auth, "python", "Без результатів")
    assert breakdown(client, auth, fresh["id"], "python-01").status_code == 404


def test_list_counts_match_the_detail_summary_and_are_not_capped(client, auth, finished):  # noqa: F811
    pid = finished["id"]
    items = client.get(f"{API}/profiles/{pid}/results", params={"fitting": "all", "page_size": 12}, headers=auth).json()["items"]
    assert items
    for item in items:
        detail = breakdown(client, auth, pid, item["vacancy_id"]).json()
        assert item["met_count"] == detail["summary"]["met"]
        assert item["gap_count"] == detail["summary"]["gap"]
        assert item["unknown_count"] == detail["summary"]["unknown"]
        assert item["met_count"] + item["gap_count"] + item["unknown_count"] == item["groups_total"]
