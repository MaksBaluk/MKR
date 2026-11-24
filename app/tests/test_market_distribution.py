from sqlalchemy import select

from backend.models import Vacancy
from tests.test_profiles_api import API  # noqa: F401


def distribution(client, track):
    return client.get(f"{API}/market/distribution", params={"track": track})


def expected(db, track):
    with db() as s:
        vacancies = s.scalars(select(Vacancy).where(Vacancy.track == track, Vacancy.is_active.is_(True))).all()
        total = len(vacancies)
        counts: dict[str, int] = {}
        for v in vacancies:
            ids = {a.competency_id for g in v.groups for a in g.alternatives}
            for cid in ids:
                counts[cid] = counts.get(cid, 0) + 1
    rows = [(cid, round(100 * n / total)) for cid, n in counts.items()]
    rows.sort(key=lambda x: (-x[1], x[0]))
    return total, rows


def test_shares_match_unique_vacancy_counts(client, db):
    r = distribution(client, "python")
    assert r.status_code == 200, r.text
    body = r.json()
    total, rows = expected(db, "python")
    assert body["track"] == "python" and body["vacancies_total"] == total > 0
    assert [(i["action_id"], i["share_percent"]) for i in body["items"]] == rows


def test_sorted_by_share_then_id(client):
    items = distribution(client, "marketing").json()["items"]
    keys = [(-i["share_percent"], i["action_id"]) for i in items]
    assert keys == sorted(keys) and all(0 <= i["share_percent"] <= 100 for i in items)
    assert all(set(i) == {"action_id", "name", "share_percent", "levels"} for i in items)


def test_unknown_track_422(client):
    assert distribution(client, "devops").status_code == 422


def test_inactive_vacancies_excluded(client, db):
    with db() as s:
        target = s.scalars(select(Vacancy).where(Vacancy.track == "design", Vacancy.is_active.is_(True))).first()
        target.is_active = False
        s.commit()
    body = distribution(client, "design").json()
    total, rows = expected(db, "design")
    assert body["vacancies_total"] == total and [(i["action_id"], i["share_percent"]) for i in body["items"]] == rows


def test_empty_track_returns_empty_list(client, db):
    with db() as s:
        for v in s.scalars(select(Vacancy).where(Vacancy.track == "design")).all():
            v.is_active = False
        s.commit()
    body = distribution(client, "design").json()
    assert body["vacancies_total"] == 0 and body["items"] == []


def required_levels(db, track):
    """Per action: how many vacancies need it at the low / mid / high level (the highest level in the vacancy counts)."""
    from collections import defaultdict
    names = {1: "low", 2: "mid", 3: "high"}
    out: dict[str, dict[str, int]] = defaultdict(lambda: {"low": 0, "mid": 0, "high": 0})
    with db() as s:
        for v in s.scalars(select(Vacancy).where(Vacancy.track == track, Vacancy.is_active.is_(True))).all():
            best: dict[str, int] = {}
            for g in v.groups:
                for a in g.alternatives:
                    best[a.competency_id] = max(best.get(a.competency_id, 0), a.required_level)
            for action, level in best.items():
                out[action][names[min(3, max(1, level))]] += 1
    return out


def test_levels_split_vacancies_by_required_level(client, db):
    body = distribution(client, "python").json()
    expected = required_levels(db, "python")
    assert body["items"]
    for item in body["items"]:
        assert item["levels"] == expected[item["action_id"]]
        assert sum(item["levels"].values()) >= 1


def test_seniority_filter_counts_only_that_level_and_totals_cover_all(client, db):
    whole = distribution(client, "python").json()
    totals = whole["seniority_totals"]
    assert sum(totals.values()) == whole["vacancies_total"] and whole["seniority"] is None
    for level in ("junior", "senior"):
        r = client.get(f"{API}/market/distribution", params={"track": "python", "seniority": level}).json()
        assert r["seniority"] == level and r["vacancies_total"] == totals.get(level, 0)
        assert all(0 <= i["share_percent"] <= 100 for i in r["items"])
        assert r["seniority_totals"] == totals
    assert client.get(f"{API}/market/distribution", params={"track": "python", "seniority": "guru"}).status_code == 422
