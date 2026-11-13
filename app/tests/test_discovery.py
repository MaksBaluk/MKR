import ast
from pathlib import Path

from backend.domain import discovery


def _register(client, email: str) -> dict:
    r = client.post("/api/v1/auth/register", json={"email": email, "display_name": "Тест Кандидат",
                                                    "password": "long-password-123"})
    assert r.status_code in (200, 201), r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_recommendations_need_no_selection(client, auth):
    r = client.get("/api/v1/discovery/recommendations", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 30
    assert all(item["vacancy"]["track"] == "python" for item in body["items"])
    assert body["profile_source"] == "SELF_REPORT_BASELINE"


def test_discovery_snapshot_is_full_track_cohort_with_policy(client, auth):
    r = client.post("/api/v1/discovery/snapshots", headers=auth, json={"name": "Авто"})
    assert r.status_code == 201, r.text
    snap = r.json()
    assert snap["vacancy_count"] == 30
    assert snap["cohort_policy"]["policy"] == "TRACK_ALL_ELIGIBLE_V1"
    assert snap["cohort_policy"]["cap"] == 30
    assert snap["cohort_policy"]["dropped_count"] == 0
    assert len(snap["sha256"]) == 64
    assert snap["baseline_match_id"]


def test_identical_inputs_give_identical_hash(client, auth):
    a = client.post("/api/v1/discovery/snapshots", headers=auth, json={}).json()["sha256"]
    b = client.post("/api/v1/discovery/snapshots", headers=auth, json={}).json()["sha256"]
    assert a == b


def test_unknown_experience_is_not_a_rejection(client, auth):
    profile = client.get("/api/v1/profile", headers=auth).json()
    client.put("/api/v1/profile", headers=auth, json={**profile, "years_experience": None})
    r = client.get("/api/v1/discovery/recommendations", headers=auth)
    assert r.json()["total"] == 30
    assert all(item["years_eligibility"] is None for item in r.json()["items"])


def test_empty_cohort_is_422(client, auth):
    r = client.post("/api/v1/discovery/snapshots", headers=auth, json={"seniority": "NO_SUCH_LEVEL"})
    assert r.status_code == 422


def test_cross_user_snapshot_is_404(client, auth):
    cohort = client.post("/api/v1/discovery/snapshots", headers=auth, json={}).json()
    other = _register(client, "other.candidate@example.com")
    assert client.get(f"/api/v1/snapshots/{cohort['id']}", headers=other).status_code == 404


def test_legacy_manual_snapshot_still_accepted(client, auth):
    ids = [v["id"] for v in client.get("/api/v1/vacancies?track=python", headers=auth).json()["items"][:3]]
    r = client.post("/api/v1/snapshots", headers=auth, json={"vacancy_ids": ids})
    assert r.status_code == 201, r.text


def test_discovery_module_does_not_use_llm():
    source = Path(discovery.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not any("providers" in (m or "") for m in imported)
