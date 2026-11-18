import itertools

import pytest

from tests.test_interview_flow import llm, no_llm  # noqa: F401

API = "/api/v1"
_keys = itertools.count(1)


def mk_profile(client, auth, track="python", name="Профіль тест", **extra):
    body = {"name": name, "track": track, "target_level": "middle", "years_experience": 3, **extra}
    r = client.post(f"{API}/profiles", json=body, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


def start(client, auth, pid):
    return client.post(f"{API}/profiles/{pid}/attempts", headers=auth)


def run_attempt(client, auth, attempt, answers=3, finish=True):
    version = attempt["version"]
    for _ in range(answers):
        q = client.post(f"{API}/interviews/{attempt['id']}/next-question", json={"version": version}, headers=auth).json()
        if q.get("done"):
            break
        a = client.post(f"{API}/interviews/{attempt['id']}/answers", headers=auth, json={
            "turn_id": q["turn"]["id"], "text": "Працював із цим на проєкті.", "version": q["version"],
            "idempotency_key": f"key-{next(_keys):08d}"}).json()
        version = a["version"]
    if finish:
        r = client.post(f"{API}/interviews/{attempt['id']}/finish", json={"version": version}, headers=auth)
        assert r.status_code == 200, r.text
    return version


def results(client, auth, pid, **params):
    params.setdefault("fitting", "all")  # endpoint default is the fitting subset; these tests cover the whole cohort
    r = client.get(f"{API}/profiles/{pid}/results", params=params, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def other(client):
    r = client.post(f"{API}/auth/register", json={
        "email": "other-user@example.test", "display_name": "Other User", "password": "another-pass-456"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_register_creates_default_profile(client, other):
    items = client.get(f"{API}/profiles", headers=other).json()["items"]
    assert len(items) == 1 and items[0]["name"] == "Основний профіль"


def test_profile_crud_and_validation(client, auth):
    p = mk_profile(client, auth, years_experience=3, location="Київ")
    assert p["attempts_count"] == 0 and p["latest_finished_attempt_id"] is None and p["archived"] is False
    assert client.get(f"{API}/profiles/{p['id']}", headers=auth).json()["location"] == "Київ"
    r = client.put(f"{API}/profiles/{p['id']}", headers=auth,
                   json={"name": "Нова назва", "track": "python", "years_experience": 5})
    assert r.json()["name"] == "Нова назва" and r.json()["years_experience"] == 5
    bad = client.post(f"{API}/profiles", json={"name": "x", "track": "python"}, headers=auth)
    assert bad.status_code == 422
    assert client.post(f"{API}/profiles", json={"name": "Ok name", "track": "law"}, headers=auth).status_code == 422
    assert client.post(f"{API}/profiles", headers=auth,
                       json={"name": "Ok name", "track": "python", "years_experience": 99}).status_code == 422


def test_owner_isolation(client, auth, other, llm):
    p = mk_profile(client, auth)
    for path in ("", "/attempts", "/results", "/self-ratings"):
        assert client.get(f"{API}/profiles/{p['id']}{path}", headers=other).status_code == 404
    assert client.post(f"{API}/profiles/{p['id']}/attempts", headers=other).status_code == 404
    assert client.delete(f"{API}/profiles/{p['id']}", headers=other).status_code == 404
    assert all(i["id"] != p["id"] for i in client.get(f"{API}/profiles", headers=other).json()["items"])


def test_self_ratings_do_not_leak_between_profiles(client, auth):
    py = mk_profile(client, auth, "python", "Python")
    mk = mk_profile(client, auth, "marketing", "Marketing")
    assert client.get(f"{API}/profiles/{py['id']}/self-ratings", headers=auth).json()["items"] == []
    ids = _action_ids(client, auth)
    r = client.put(f"{API}/profiles/{py['id']}/self-ratings/{ids['python']}", json={"value": 0.4}, headers=auth)
    assert r.status_code == 200
    client.put(f"{API}/profiles/{py['id']}/self-ratings/{ids['python']}", json={"value": 0.7}, headers=auth)
    got = client.get(f"{API}/profiles/{py['id']}/self-ratings", headers=auth).json()["items"]
    assert [(g["action_id"], g["value"]) for g in got] == [(ids["python"], 0.7)]
    assert client.get(f"{API}/profiles/{mk['id']}/self-ratings", headers=auth).json()["items"] == []
    wrong = client.put(f"{API}/profiles/{mk['id']}/self-ratings/{ids['python']}", json={"value": 0.5}, headers=auth)
    assert wrong.status_code == 422
    assert client.put(f"{API}/profiles/{mk['id']}/self-ratings/nope", json={"value": 0.5}, headers=auth).status_code == 404
    assert client.put(f"{API}/profiles/{mk['id']}/self-ratings/{ids['marketing']}", json={"value": 2}, headers=auth).status_code == 422
    client.put(f"{API}/profiles/{mk['id']}/self-ratings/{ids['marketing']}", json={"value": None}, headers=auth)
    assert client.get(f"{API}/profiles/{mk['id']}/self-ratings", headers=auth).json()["items"][0]["value"] is None
    assert len(client.get(f"{API}/profiles/{py['id']}/self-ratings", headers=auth).json()["items"]) == 1


def _action_ids(client, auth):
    from backend.models import Competency
    from sqlalchemy import select
    from backend.db import get_db
    from backend.main import app
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    out = {}
    for c in db.scalars(select(Competency).order_by(Competency.id)).all():
        out.setdefault(c.track, c.id)
    return out


def test_attempt_numbering_and_single_unfinished(client, auth, llm):
    p = mk_profile(client, auth)
    a1 = start(client, auth, p["id"])
    assert a1.status_code == 201 and a1.json()["attempt_no"] == 1 and a1.json()["cohort_id"]
    again = start(client, auth, p["id"])
    assert again.status_code == 200 and again.json()["id"] == a1.json()["id"]
    run_attempt(client, auth, a1.json(), answers=1)
    a2 = start(client, auth, p["id"]).json()
    assert a2["attempt_no"] == 2 and a2["id"] != a1.json()["id"]
    run_attempt(client, auth, a2, answers=0)
    assert start(client, auth, p["id"]).json()["attempt_no"] == 3
    items = client.get(f"{API}/profiles/{p['id']}/attempts", headers=auth).json()["items"]
    assert [i["attempt_no"] for i in items] == [3, 2, 1]
    assert items[2]["answers_count"] == 1 and items[2]["topics_used"] == 1 and items[2]["status"] == "FINISHED"
    assert client.get(f"{API}/profiles/{p['id']}", headers=auth).json()["attempts_count"] == 3


def test_second_attempt_does_not_change_results_until_finished(client, auth, llm):
    p = mk_profile(client, auth)
    a1 = start(client, auth, p["id"]).json()
    llm.score = 0.9
    run_attempt(client, auth, a1, answers=4)
    r1 = results(client, auth, p["id"], page_size=50)
    assert r1["has_results"] and r1["attempt_id"] == a1["id"]
    assert any(c["score"] == 0.9 for c in r1["competencies"])
    a2 = start(client, auth, p["id"]).json()
    llm.score = 0.1
    v = run_attempt(client, auth, a2, answers=4, finish=False)
    assert results(client, auth, p["id"], page_size=50) == r1
    client.post(f"{API}/interviews/{a2['id']}/finish", json={"version": v}, headers=auth)
    r2 = results(client, auth, p["id"], page_size=50)
    assert r2["attempt_id"] == a2["id"] and r2 != r1
    assert any(c["score"] == 0.1 for c in r2["competencies"]) and all(c["score"] != 0.9 for c in r2["competencies"])
    assert client.get(f"{API}/profiles/{p['id']}", headers=auth).json()["latest_finished_attempt_id"] == a2["id"]


def test_attempt_planner_ignores_other_attempt_scores(client, auth, llm):
    p = mk_profile(client, auth)
    a1 = start(client, auth, p["id"]).json()
    run_attempt(client, auth, a1, answers=2)
    a2 = start(client, auth, p["id"]).json()
    first_topics = {t["action_id"] for t in client.get(f"{API}/interviews/{a1['id']}", headers=auth).json()["turns"]}
    q = client.post(f"{API}/interviews/{a2['id']}/next-question", json={"version": a2["version"]}, headers=auth).json()
    # fresh attempt starts from zero knowledge: same first topic as attempt 1 started with
    assert q["turn"]["action_id"] in first_topics


def test_archive_hides_blocks_attempts_keeps_history(client, auth, llm):
    p = mk_profile(client, auth)
    a1 = start(client, auth, p["id"]).json()
    run_attempt(client, auth, a1, answers=1)
    assert client.delete(f"{API}/profiles/{p['id']}", headers=auth).status_code == 204
    assert all(i["id"] != p["id"] for i in client.get(f"{API}/profiles", headers=auth).json()["items"])
    assert start(client, auth, p["id"]).status_code == 409
    assert len(client.get(f"{API}/profiles/{p['id']}/attempts", headers=auth).json()["items"]) == 1
    assert results(client, auth, p["id"])["has_results"] is True


def test_results_without_finished_attempt(client, auth):
    p = mk_profile(client, auth)
    r = results(client, auth, p["id"])
    assert r["has_results"] is False and r["items"] == [] and r["competencies"] == [] and r["market"] == []
    assert r["total"] == 0
    start(client, auth, p["id"])
    assert results(client, auth, p["id"])["has_results"] is False


@pytest.fixture()
def finished(client, auth, llm):
    p = mk_profile(client, auth)
    a = start(client, auth, p["id"]).json()
    run_attempt(client, auth, a, answers=3)
    return p


def test_results_pagination(client, auth, finished):
    pid = finished["id"]
    p1 = results(client, auth, pid, page_size=5)
    p2 = results(client, auth, pid, page_size=5, page=2)
    assert p1["total"] > 5 and len(p1["items"]) == 5 and p1["total"] == p2["total"]
    assert [i["vacancy_id"] for i in p1["items"]] != [i["vacancy_id"] for i in p2["items"]]
    assert not {i["vacancy_id"] for i in p1["items"]} & {i["vacancy_id"] for i in p2["items"]}
    far = results(client, auth, pid, page_size=5, page=999)
    assert far["items"] == [] and far["total"] == p1["total"]
    allp = results(client, auth, pid, page_size=50)
    assert [i["vacancy_id"] for i in allp["items"][:5]] == [i["vacancy_id"] for i in p1["items"]]
    for bad in (0, 51):
        assert client.get(f"{API}/profiles/{pid}/results", params={"page_size": bad}, headers=auth).status_code == 422
    assert client.get(f"{API}/profiles/{pid}/results", params={"page": 0}, headers=auth).status_code == 422
    item = p1["items"][0]
    for k in ("title", "company", "location", "work_mode", "seniority", "years_min", "tags", "strengths", "gaps",
              "unknown_count", "confirmed_share", "label", "z", "x"):
        assert k in item


def test_results_filters(client, auth, finished):
    pid = finished["id"]
    allr = results(client, auth, pid, page_size=50)
    total, items = allr["total"], allr["items"]
    mode = items[0]["work_mode"]
    r = results(client, auth, pid, page_size=50, work_mode=mode.upper())
    assert 0 < r["total"] <= total and all(i["work_mode"] == mode for i in r["items"])
    sen = next(i["seniority"] for i in items if i["seniority"])
    r = results(client, auth, pid, page_size=50, seniority=sen.upper())
    assert 0 < r["total"] <= total and all(i["seniority"] == sen for i in r["items"])
    word = items[0]["title"].split()[0].lower()
    r = results(client, auth, pid, page_size=50, q=word)
    assert 0 < r["total"] <= total
    assert all(word in (i["title"] + i["company"]).lower() for i in r["items"])
    r = results(client, auth, pid, page_size=50, min_share=100)
    assert all(i["confirmed_share"] >= 100 for i in r["items"]) and r["total"] <= total
    assert any(results(client, auth, pid, page_size=50, **f)["total"] < total
               for f in ({"work_mode": mode}, {"seniority": sen}, {"q": word}, {"min_share": 100}))
    assert results(client, auth, pid, work_mode="no-such-mode")["total"] == 0
    assert results(client, auth, pid, q="zzzzqqqq")["items"] == []
    assert client.get(f"{API}/profiles/{pid}/results", params={"min_share": 101}, headers=auth).status_code == 422


def test_market_is_names_only(client, auth, finished):
    r = results(client, auth, finished["id"])
    assert r["market"] and all(set(m) == {"order", "action_id", "name"} for m in r["market"])
    assert [m["order"] for m in r["market"]] == list(range(1, len(r["market"]) + 1))
    text = str(r["market"]).lower()
    for word in ("prevalence", "mass", "count", "%"):
        assert word not in text
    comp = r["competencies"][0]
    assert {"action_id", "action_name", "score", "reason", "evidence"} <= set(comp) and comp["score"] == 0.6


def test_every_interview_has_profile_and_attempt_no(client, auth, no_llm):
    cohort = client.post(f"{API}/cohorts/auto", headers=auth).json()["cohort_id"]
    iv = client.post(f"{API}/interviews", json={"cohort_id": cohort}, headers=auth).json()
    from backend.models import CoreInterview
    from backend.db import get_db
    from backend.main import app
    db = next(app.dependency_overrides[get_db]())
    row = db.get(CoreInterview, iv["id"])
    assert row.profile_id and row.attempt_no == 1


def test_auto_cohort_unchanged_and_accepts_profile(client, auth):
    base = client.post(f"{API}/cohorts/auto", headers=auth).json()
    p = mk_profile(client, auth, "marketing")
    mkt = client.post(f"{API}/cohorts/auto", params={"profile_id": p["id"]}, headers=auth).json()
    assert base["vacancy_count"] > 0 and mkt["cohort_id"] != base["cohort_id"]
    assert client.post(f"{API}/cohorts/auto", params={"profile_id": "nope"}, headers=auth).status_code == 404


def _open_count(client, auth, pid):
    items = client.get(f"{API}/profiles/{pid}/attempts", headers=auth).json()["items"]
    return len([i for i in items if i["status"] != "FINISHED"])


def test_start_attempt_race_loser_gets_existing(client, auth, monkeypatch):
    import backend.api.profiles as prof_api
    p = mk_profile(client, auth)
    winner = start(client, auth, p["id"]).json()
    real = prof_api._open_attempt
    calls = []
    # loser's existence check ran before the winner committed: it sees nothing, then collides on insert
    monkeypatch.setattr(prof_api, "_open_attempt", lambda db, pid: None if not calls and not calls.append(1) else real(db, pid))
    import backend.api.common as common
    monkeypatch.setattr(common, "next_attempt_no", lambda db, pid: 1)  # loser computed max+1 before winner committed
    r = start(client, auth, p["id"])
    assert r.status_code == 200 and r.json()["id"] == winner["id"]
    assert _open_count(client, auth, p["id"]) == 1


def test_legacy_interview_race_returns_existing(client, auth, no_llm, monkeypatch):
    import backend.api.common as common
    cohort = client.post(f"{API}/cohorts/auto", headers=auth).json()["cohort_id"]
    first = client.post(f"{API}/interviews", json={"cohort_id": cohort}, headers=auth).json()
    monkeypatch.setattr(common, "next_attempt_no", lambda db, pid: 1)  # stale number, as a racer would compute
    second = client.post(f"{API}/interviews", json={"cohort_id": cohort}, headers=auth)
    assert second.status_code == 201 and second.json()["id"] == first["id"]
    pid = client.get(f"{API}/profiles", headers=auth).json()["items"][0]["id"]
    assert _open_count(client, auth, pid) == 1


def test_race_with_no_open_attempt_is_409_not_500(client, auth, monkeypatch):
    import backend.api.common as common
    p = mk_profile(client, auth)
    a = start(client, auth, p["id"]).json()
    client.post(f"{API}/interviews/{a['id']}/finish", json={"version": a["version"]}, headers=auth)
    monkeypatch.setattr(common, "next_attempt_no", lambda db, pid: 1)
    assert start(client, auth, p["id"]).status_code == 409


def test_results_items_have_source_and_group_counts(client, auth, finished, db):
    from backend.models import Vacancy
    items = results(client, auth, finished["id"], page_size=50)["items"]
    with db() as s:
        kinds = {v.id: v.source_type for v in s.query(Vacancy).all()}
    assert items
    for i in items:
        assert i["source_label"] == ("Djinni" if kinds[i["vacancy_id"]] == "REAL_IMPORTED" else "Приклад")
        assert isinstance(i["groups_total"], int) and isinstance(i["groups_assessed"], int)
        assert i["groups_total"] >= i["groups_assessed"] >= 0 and i["groups_total"] > 0
    assert {i["source_label"] for i in items} <= {"Djinni", "Приклад"}
    assert any(i["groups_assessed"] > 0 for i in items)


def test_explain_vacancy_counts_assessed_groups():
    from backend.domain.core_flow import explain_vacancy
    vac = {"groups": [
        {"kind": "MANDATORY", "alternatives": [{"competency_id": "a", "required_level": 0.5},
                                               {"competency_id": "b", "required_level": 0.5}]},
        {"kind": "MANDATORY", "alternatives": [{"competency_id": "c", "required_level": 0.5}]},
        {"kind": "DESIRED", "alternatives": [{"competency_id": "d", "required_level": 0.5}]}]}
    out = explain_vacancy(vac, {"a": None, "b": 0.0, "c": None}, {}, {})
    assert out["groups_total"] == 3 and out["groups_assessed"] == 1


def test_legacy_recommendations_have_source_and_group_counts(client, auth, finished):
    cohort = client.post(f"{API}/cohorts/auto", headers=auth).json()["cohort_id"]
    r = client.post(f"{API}/recommendations", json={"cohort_id": cohort}, headers=auth)
    assert r.status_code == 200, r.text
    for i in r.json()["items"]:
        assert i["source_label"] in ("Djinni", "Приклад")
        assert i["groups_total"] >= i["groups_assessed"] >= 0
