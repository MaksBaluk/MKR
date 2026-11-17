from collections import Counter

from sqlalchemy import select

from backend.models import Vacancy
from tests.test_profiles_api import API  # noqa: F401


def overview(client, track):
    return client.get(f"{API}/market/overview", params={"track": track})


def active(db, track):
    with db() as s:
        rows = s.scalars(select(Vacancy).where(Vacancy.track == track, Vacancy.is_active.is_(True))).all()
        return [(v.seniority, v.work_mode, v.salary_min, v.salary_max, v.currency,
                 {a.competency_id for g in v.groups if g.kind == "MANDATORY" for a in g.alternatives},
                 {a.competency_id for g in v.groups if g.kind != "MANDATORY" for a in g.alternatives}) for v in rows]


def test_counts_match_catalog(client, db):
    r = overview(client, "python")
    assert r.status_code == 200, r.text
    body = r.json()
    rows = active(db, "python")
    assert body["track"] == "python" and body["vacancies_total"] == len(rows) > 0
    assert body["seniority"] == dict(Counter(v[0] for v in rows))
    assert body["work_mode"] == dict(Counter(v[1] for v in rows))


def test_salary_by_seniority_only_for_priced_vacancies(client, db):
    body = overview(client, "python").json()
    for row in body["salary"]:
        assert row["min"] <= row["avg"] <= row["max"] and row["count"] > 0 and row["seniority"] in body["seniority"]


def test_requirement_kinds_count_vacancies_once(client, db):
    body = overview(client, "python").json()
    rows = active(db, "python")
    mand = Counter(c for v in rows for c in v[5])
    des = Counter(c for v in rows for c in v[6])
    assert body["requirement_kinds"]
    for item in body["requirement_kinds"]:
        assert item["mandatory"] == mand.get(item["action_id"], 0) and item["desired"] == des.get(item["action_id"], 0)
        assert set(item) == {"action_id", "name", "mandatory", "desired", "avg_required_level"}


def test_unknown_track_422(client):
    assert overview(client, "devops").status_code == 422


def test_empty_track_returns_empty_lists(client, db):
    with db() as s:
        for v in s.scalars(select(Vacancy).where(Vacancy.track == "design")).all():
            v.is_active = False
        s.commit()
    body = overview(client, "design").json()
    assert body["vacancies_total"] == 0 and body["seniority"] == {} and body["work_mode"] == {}
    assert body["salary"] == [] and body["requirement_kinds"] == []


def test_requirement_kinds_carry_average_required_level(client, db):
    body = overview(client, "python").json()
    assert body["requirement_kinds"]
    for item in body["requirement_kinds"]:
        assert 1.0 <= item["avg_required_level"] <= 3.0
