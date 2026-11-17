from tests.test_interview_flow import llm  # noqa: F401
from tests.test_profiles_api import API, other, start  # noqa: F401


def create(client, auth, **body):
    return client.post(f"{API}/profiles", json={"name": "Профіль", **body}, headers=auth)


def test_profile_keeps_target_level_and_work_mode(client, auth):
    r = create(client, auth, track="marketing", target_level="senior", work_mode="remote", years_experience=6)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["target_level"] == "senior" and p["work_mode"] == "remote"
    assert client.get(f"{API}/profiles/{p['id']}", headers=auth).json()["target_level"] == "senior"


def test_invalid_level_or_work_mode_is_rejected(client, auth):
    assert create(client, auth, track="python", target_level="wizard").status_code == 422
    assert create(client, auth, track="python", work_mode="moon").status_code == 422


def test_profile_can_be_saved_without_track_yet(client, auth):
    r = create(client, auth)
    assert r.status_code == 201 and r.json()["track"] is None
    upd = client.put(f"{API}/profiles/{r.json()['id']}", json={"name": "Профіль", "track": "design"}, headers=auth)
    assert upd.status_code == 200 and upd.json()["track"] == "design"


def test_new_account_profile_has_no_preselected_track(client, other):
    items = client.get(f"{API}/profiles", headers=other).json()["items"]
    assert items[0]["track"] is None and items[0]["target_level"] is None


def test_start_requires_track_level_and_years(client, auth, llm):  # noqa: F811
    incomplete = [
        {},
        {"track": "python"},
        {"track": "python", "target_level": "middle"},
        {"track": "python", "years_experience": 3},
    ]
    for body in incomplete:
        p = create(client, auth, **body).json()
        r = start(client, auth, p["id"])
        assert r.status_code == 422, (body, r.text)
    ok = create(client, auth, track="python", target_level="middle", years_experience=3).json()
    assert start(client, auth, ok["id"]).status_code == 201
