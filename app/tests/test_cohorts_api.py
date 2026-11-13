import pytest


@pytest.fixture()
def cohort(client, auth):
    r = client.post("/api/v1/cohorts/auto", headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


def test_auto_cohort_is_server_selected(cohort):
    assert cohort["empty"] is False
    assert cohort["vacancy_count"] > 0
    assert len(cohort["sha256"]) == 64


def test_post_is_idempotent(client, auth, cohort):
    again = client.post("/api/v1/cohorts/auto", headers=auth).json()
    assert again["cohort_id"] == cohort["cohort_id"]


def test_client_vacancy_ids_are_ignored(client, auth):
    r = client.post("/api/v1/cohorts/auto", headers=auth, json={"vacancy_ids": ["forged"]})
    assert r.status_code == 201
    assert r.json()["vacancy_count"] > 0


def test_market_has_no_counts_or_percentages(client, auth, cohort):
    body = client.get(f"/api/v1/cohorts/{cohort['cohort_id']}/market", headers=auth).json()
    assert body["skills"]
    text = str(body)
    assert "%" not in text and "prevalence" not in text and "mass" not in text


def test_cohort_scoped_to_owner(client, auth, cohort):
    reg = client.post("/api/v1/auth/register", json={
        "email": "other-owner@example.test", "display_name": "Other Owner", "password": "another-pass-123"})
    assert reg.status_code == 201, reg.text
    token = reg.json()["token"]
    r = client.get(f"/api/v1/cohorts/{cohort['cohort_id']}/market",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404
