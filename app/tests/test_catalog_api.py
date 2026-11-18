import math

from backend.models import Vacancy

URL = "/api/v1/vacancies"


def get(client, **params):
    r = client.get(URL, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def all_items(client, **params):
    out, page = [], 1
    while True:
        body = get(client, page=page, page_size=50, **params)
        out += body["items"]
        if len(out) >= body["total"]:
            return out
        page += 1


def test_list_shape_and_defaults(client):
    body = get(client)
    assert body["page"] == 1 and body["page_size"] == 12
    assert 0 < len(body["items"]) <= 12 <= body["total"] or body["total"] <= 12
    item = body["items"][0]
    for key in ["id", "track", "title", "company", "seniority", "location", "work_mode", "employment",
                "salary_min", "salary_max", "currency", "summary", "stack", "years_min", "years_max",
                "source_label", "requirements_count"]:
        assert key in item
    assert "description" not in item and "groups" not in item
    assert set(body["facets"]) == {"track", "work_mode", "seniority"}
    titles = [i["title"] for i in body["items"]]
    assert titles == sorted(titles)


def test_each_filter_narrows_and_matches(client):
    total = get(client)["total"]
    for param, field, value in [("track", "track", "python"), ("work_mode", "work_mode", "REMOTE"),
                                ("seniority", "seniority", "JUNIOR")]:
        items = all_items(client, **{param: value})
        assert 0 < len(items) < total
        assert all(i[field] == value for i in items)
        low = all_items(client, **{param: value.lower()}) if param != "track" else items
        assert {i["id"] for i in low} == {i["id"] for i in items}
    loc = all_items(client, location="remote")
    assert loc and all("remote" in i["location"].lower() for i in loc)
    assert {i["id"] for i in all_items(client, location="REMOTE")} == {i["id"] for i in loc}


def test_combined_filters(client):
    both = all_items(client, track="python", work_mode="remote", seniority="junior")
    assert all(i["track"] == "python" and i["work_mode"] == "REMOTE" and i["seniority"] == "JUNIOR" for i in both)
    assert len(both) <= len(all_items(client, track="python", work_mode="remote"))
    assert len(both) <= len(all_items(client, track="python", seniority="junior"))


def test_text_search_title_company_stack(client):
    first = client.get(f"{URL}/python-01").json()
    for needle in [first["title"].split()[1].upper(), first["company"].lower(), first["stack"][0].lower()]:
        ids = {i["id"] for i in all_items(client, q=needle)}
        assert "python-01" in ids
    title_hits = all_items(client, q="python backend")
    assert all("python backend" in i["title"].lower() or "python backend" in i["company"].lower()
               or any("python backend" in s.lower() for s in i["stack"]) for i in title_hits)


def test_salary_min_semantics(client, db):
    with db() as s:
        s.add(Vacancy(id="nosal-1", track="python", title="Zzz No Salary", company="Acme", seniority="JUNIOR",
                      years_min=0, location="Київ", work_mode="OFFICE", summary="s", description="d",
                      salary_min=None, salary_max=None, source_type="SYNTHETIC_GENERATED"))
        s.commit()
    items = all_items(client, salary_min=2500)
    assert any(i["id"] == "nosal-1" for i in items)
    assert all(i["salary_max"] is None or i["salary_max"] >= 2500 for i in items)
    assert len(items) < get(client)["total"]
    huge = all_items(client, salary_min=10**9)
    assert "nosal-1" in [i["id"] for i in huge]
    assert all(i["salary_max"] is None for i in huge)  # unknown salary passes; imported postings without salary too


def test_sorts_are_ordered(client):
    by_title = all_items(client, sort="title")
    assert [i["title"] for i in by_title] == sorted(i["title"] for i in by_title)
    newest = [i["id"] for i in all_items(client, sort="newest")]
    assert newest == sorted(newest, reverse=True)
    desc = [i["salary_max"] for i in all_items(client, sort="salary_desc") if i["salary_max"] is not None]
    asc = [i["salary_max"] for i in all_items(client, sort="salary_asc") if i["salary_max"] is not None]
    assert desc == sorted(desc, reverse=True) and asc == sorted(asc)
    assert len(set(desc)) > 1
    assert client.get(URL, params={"sort": "bogus"}).status_code == 422


def test_pagination_math(client):
    p1 = get(client, page_size=10)
    total = p1["total"]
    pages = math.ceil(total / 10)
    assert len(p1["items"]) == min(10, total)
    p2 = get(client, page_size=10, page=2)
    assert p2["total"] == total and p2["page"] == 2
    assert {i["id"] for i in p1["items"]}.isdisjoint(i["id"] for i in p2["items"])
    last = get(client, page_size=10, page=pages)
    assert len(last["items"]) == total - 10 * (pages - 1)
    past = get(client, page_size=10, page=pages + 1)
    assert past["items"] == [] and past["total"] == total
    seen = []
    for p in range(1, pages + 1):
        seen += [i["id"] for i in get(client, page_size=10, page=p)["items"]]
    assert len(seen) == len(set(seen)) == total


def test_bad_paging_params(client):
    for params in [{"page_size": 0}, {"page_size": 51}, {"page": 0}]:
        assert client.get(URL, params=params).status_code == 422
    assert client.get(URL, params={"page_size": 50}).status_code == 200
    assert client.get(URL, params={"track": "nope"}).status_code == 422


def test_empty_result(client):
    body = get(client, q="no-such-vacancy-xyz")
    assert body["total"] == 0 and body["items"] == []
    assert sum(body["facets"]["track"].values()) == 0


def test_facets_standard_faceting(client):
    unfiltered = get(client)["facets"]
    assert sum(unfiltered["track"].values()) == get(client)["total"]
    body = get(client, track="python", work_mode="REMOTE")
    f = body["facets"]
    # work_mode facet ignores its own filter: sums to the python-only total
    assert sum(f["work_mode"].values()) == get(client, track="python")["total"]
    # track facet ignores track filter: sums to the remote-only total
    assert sum(f["track"].values()) == get(client, work_mode="REMOTE")["total"]
    # seniority facet respects both filters
    assert sum(f["seniority"].values()) == body["total"]


def test_detail_shape(client):
    d = client.get(f"{URL}/python-01").json()
    for key in ["description", "responsibilities", "benefits", "stack", "summary", "source_type",
                "source_label", "source_url", "fixture_version", "requirements_count", "requirements"]:
        assert key in d
    assert d["source_label"] in ("robota.ua", "work.ua", "DOU") and d["source_example"] is True  # python-01 is an adapted example
    assert d["requirements_count"] == len(d["requirements"]) > 0
    kinds = {r["kind"] for r in d["requirements"]}
    assert kinds == {"MANDATORY", "DESIRED"}
    for r in d["requirements"]:
        assert r["id"] and r["label"] and "excerpt" in r and r["alternatives"]
        for a in r["alternatives"]:
            assert a["competency_id"] and a["name"] and isinstance(a["required_level"], int)


def test_detail_404(client, db):
    r = client.get(f"{URL}/nope-999")
    assert r.status_code == 404 and r.json()["detail"]
    with db() as s:
        s.get(Vacancy, "python-02").is_active = False
        s.commit()
    assert client.get(f"{URL}/python-02").status_code == 404
    assert "python-02" not in {i["id"] for i in all_items(client)}


def test_source_label(client, db):
    assert client.get(f"{URL}/python-01").json()["source_label"] in ("robota.ua", "work.ua", "DOU")
    assert client.get(f"{URL}/python-31").json()["source_label"] in ("robota.ua", "work.ua", "DOU")
    with db() as s:
        s.add(Vacancy(id="synth-1", track="python", title="Synthetic", company="Fake", seniority="JUNIOR",
                      years_min=0, location="Київ", work_mode="OFFICE", summary="s", description="d",
                      source_type="SYNTHETIC_GENERATED"))
        s.commit()
    assert client.get(f"{URL}/synth-1").json()["source_label"] == "Приклад"
    item = next(i for i in all_items(client, q="Synthetic") if i["id"] == "synth-1")
    assert item["source_label"] == "Приклад"


def test_competencies_unchanged(client):
    assert isinstance(client.get("/api/v1/competencies").json(), list)
