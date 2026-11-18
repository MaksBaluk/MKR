"""Fixture v2: synthetic vacancies, curated-template rubrics and the extended free-text bank."""
import hashlib
import json
import re
from collections import Counter

from sqlalchemy import func, select

from backend.api.core import criteria_for
from backend.models import Rubric, RubricCriterion, Vacancy
from backend.seed import read_fixture, seed_database

# sha256(json.dumps(first 90 records of HEAD~ vacancies.json, ensure_ascii=False, sort_keys=True))
# Updated after owner-approved title fixes (15 level mismatches), see docs/tasks/TODO.md
ORIGINAL_90_SHA256 = "e4ad83c72c71b2ac9703675eea0a26f8b954d6e323e290a43e966c2b23e8fe67"
TRACKS = ("python", "marketing", "design")
BANDS = ("0-0.25", "0.25-0.5", "0.5-0.75", "0.75-0.9", "0.9-1")


def _cyrillic_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    return sum("а" <= c.lower() <= "я" or c.lower() in "іїєґ" for c in letters) / max(1, len(letters))


def _new_rows():
    return [v for v in read_fixture("vacancies.json") if v.get("fixture_version") == "fixtures-v2"]


def test_original_90_vacancies_unchanged():
    rows = read_fixture("vacancies.json")
    first = rows[:90]
    assert [v["id"] for v in first] == [f"{t}-{i:02d}" for t in TRACKS for i in range(1, 31)]
    digest = hashlib.sha256(json.dumps(first, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    assert digest == ORIGINAL_90_SHA256


def test_at_least_30_new_vacancies_per_track():
    rows = read_fixture("vacancies.json")
    new = _new_rows()
    assert len(rows) >= 180 and len(rows) == 90 + len(new)
    counts = Counter(v["track"] for v in new)
    assert all(counts[t] >= 30 for t in TRACKS), counts
    for t in TRACKS:
        ids = [v["id"] for v in new if v["track"] == t]
        assert all(re.fullmatch(rf"{t}-\d{{2,3}}", i) and int(i.rsplit("-", 1)[1]) > 30 for i in ids)


def test_new_vacancies_structurally_valid():
    rows = read_fixture("vacancies.json")
    skills = {c["id"]: c["track"] for c in read_fixture("competencies.json")}
    new = _new_rows()
    assert len({v["id"] for v in rows}) == len(rows)
    assert len({(v["company"], v["title"]) for v in rows}) == len(rows)
    assert len({v["description"] for v in rows}) == len(rows)
    keys = set(rows[0])
    for v in new:
        assert set(v) == keys, v["id"]
        assert v["source_type"] == "SYNTHETIC_GENERATED" and v["source_url"] is None
        assert "djinni" not in json.dumps(v, ensure_ascii=False).lower()
        assert v["seniority"] in {"JUNIOR", "MIDDLE", "SENIOR", "LEAD"}
        assert v["work_mode"] in {"REMOTE", "HYBRID", "OFFICE"} and v["currency"] in {"USD", "EUR"}
        assert 0 < v["salary_min"] <= v["salary_max"]
        assert v["years_max"] is None or v["years_min"] <= v["years_max"]
        assert v["responsibilities"] and v["benefits"] and v["stack"] and len(v["description"]) > 1300
        assert _cyrillic_ratio(" ".join(v["responsibilities"])) > 0.7
        groups = v["groups"]
        assert 8 <= len(groups) <= 12, v["id"]
        assert sum(g["kind"] == "MANDATORY" for g in groups) >= 3
        assert sum(g["kind"] == "DESIRED" for g in groups) >= 2
        assert any(len(g["alternatives"]) > 1 for g in groups)
        assert len({g["id"] for g in groups}) == len(groups)
        used = [a["competency_id"] for g in groups for a in g["alternatives"]]
        assert len(used) == len(set(used)), v["id"]
        for g in groups:
            alts = [a["competency_id"] for a in g["alternatives"]]
            assert 1 <= len(alts) <= 3 and len(set(alts)) == len(alts)
            assert g["excerpt"] and g["excerpt"] in v["description"]
            for a in g["alternatives"]:
                assert skills.get(a["competency_id"]) == v["track"]
                assert a["required_level"] in (1, 2, 3)


def test_rubrics_cover_every_action():
    data = read_fixture("rubrics.json")
    assert "_note" in data and "review" in data["_note"].lower()
    ids = {c["id"] for c in read_fixture("competencies.json")}
    rubrics = {r["action_id"]: r for r in data["rubrics"]}
    assert set(rubrics) == ids and len(data["rubrics"]) == 60
    seen = set()
    for action, r in rubrics.items():
        assert r["version"] == "v1" and r["source"] == "CURATED_TEMPLATE"
        assert 3 <= len(r["criteria"]) <= 5, action
        titles = [c["title"] for c in r["criteria"]]
        assert len(set(titles)) == len(titles)
        for c in r["criteria"]:
            assert c["criterion_id"].startswith(f"{action}.") and c["criterion_id"] not in seen
            seen.add(c["criterion_id"])
            assert c["weight"] == 1
            assert tuple(c["anchors"]) == BANDS
            texts = list(c["anchors"].values())
            assert len(set(texts)) == 5
            for text in [c["title"], *texts]:
                assert text.strip() and _cyrillic_ratio(text) > 0.45, text


def test_every_action_has_five_distinct_free_text_questions():
    bank = read_fixture("questions.json")
    for action, questions in bank.items():
        free = [q for q in questions if q["kind"] == "FREE_TEXT"]
        assert len(free) >= 5, action
        assert len({q["text"] for q in free}) == len(free)
        assert len({q["id"] for q in questions}) == len(questions)
        for q in free:
            assert _cyrillic_ratio(q["text"]) > 0.45 and q["text"].rstrip().endswith(("?", "."))
            assert not re.search(r"\bбал(и|ів|ам|ами|ах)?\b|\bрів(ень|ня|нем)\b|\d\s*%", q["text"].lower()), q["text"]
        for q in free[1:]:
            assert q["id"].endswith("-v2") and q["rubric_version"] == "v1" and q["options"] == []


def real_fixture():
    try:
        return read_fixture("vacancies_real.json")
    except FileNotFoundError:
        return []


def test_seed_is_idempotent_with_rubrics(db):
    with db() as s:
        before = (s.scalar(select(func.count(Vacancy.id))), s.scalar(select(func.count(Rubric.id))),
                  s.scalar(select(func.count(RubricCriterion.id))))
        assert before[0] == len(read_fixture("vacancies.json")) + len(real_fixture()) and before[1] == 60
        again = seed_database(s, demo_mode=False)
        assert all(value == 0 for key, value in again.items() if key.endswith("_added")), again
        after = (s.scalar(select(func.count(Vacancy.id))), s.scalar(select(func.count(Rubric.id))),
                 s.scalar(select(func.count(RubricCriterion.id))))
        assert after == before


def test_criteria_for_uses_seeded_curated_template_rubric(db):
    data = {r["action_id"]: r for r in read_fixture("rubrics.json")["rubrics"]}
    with db() as s:
        rubric = s.scalar(select(Rubric).where(Rubric.action_id == "fastapi"))
        assert rubric.version == "v1" and rubric.source == "CURATED_TEMPLATE"
        expected = sorted(c["criterion_id"] for c in data["fastapi"]["criteria"])
        assert criteria_for(s, "fastapi") == expected
        assert criteria_for(s, "unknown-action") == ["unknown-action"]


class _EchoEvaluator:
    """Interviewer/Evaluator stub: grades every allowed criterion id with 0.7 and quotes the answer."""

    def __init__(self):
        self.inputs = []

    def invoke(self, messages, *a, **k):
        from types import SimpleNamespace
        from backend.agents.prompts import INTERVIEWER_SYSTEM
        system, human = messages[0].content, messages[1].content
        self.inputs.append(human)
        if system == INTERVIEWER_SYSTEM:
            return SimpleNamespace(content="Як ви перевіряєте вхідні дані у своєму сервісі?")
        data = dict(line.split(": ", 1) for line in human.splitlines() if re.match(r"\w+: ", line))
        turn_id = re.search(r'turn_id="([^"]+)"', human).group(1)
        text = json.loads(re.search(r'>(".*")</candidate_answer>', human).group(1))
        crit = [{"criterion_id": c, "score": 0.7, "reason": "з відповіді",
                 "evidence": [{"turn_id": turn_id, "exact_excerpt": text}]}
                for c in json.loads(data["allowed_criterion_ids"])]
        return SimpleNamespace(content=json.dumps({"action_id": json.loads(data["action_id"]), "rubric_version": "v1",
                                                   "off_topic": False, "criteria": crit}))


def _answer_once(client, auth, monkeypatch):
    fake = _EchoEvaluator()
    monkeypatch.setattr("backend.api.core.get_chat_model", lambda: fake)
    cohort = client.post("/api/v1/cohorts/auto", headers=auth).json()["cohort_id"]
    iv = client.post("/api/v1/interviews", json={"cohort_id": cohort}, headers=auth).json()
    q = client.post(f"/api/v1/interviews/{iv['id']}/next-question", json={"version": 0}, headers=auth).json()
    body = {"turn_id": q["turn"]["id"], "text": "Перевіряю схему запиту та повертаю 422.", "version": q["version"],
            "idempotency_key": "fixture-v2-key-1"}
    ans = client.post(f"/api/v1/interviews/{iv['id']}/answers", json=body, headers=auth).json()
    assert ans["assessment_status"] == "ACCEPTED", ans
    return fake, q["turn"]["action_id"], iv["id"]


def test_assessments_stored_per_seeded_criterion(client, auth, db, monkeypatch):
    from backend.models import CriterionAssessment
    fake, action, iv_id = _answer_once(client, auth, monkeypatch)
    rubric = {r["action_id"]: r for r in read_fixture("rubrics.json")["rubrics"]}[action]
    expected = sorted(c["criterion_id"] for c in rubric["criteria"])
    evaluator_input = fake.inputs[-1]
    assert json.dumps(expected, ensure_ascii=False) in evaluator_input
    first = rubric["criteria"][0]
    assert first["title"] in evaluator_input and first["anchors"]["0.9-1"] in evaluator_input
    with db() as s:
        seeded = s.scalar(select(Rubric).where(Rubric.action_id == action, Rubric.version == "v1"))
        rows = s.scalars(select(CriterionAssessment).where(CriterionAssessment.session_id == iv_id)).all()
        assert sorted(r.criterion_id for r in rows) == expected
        assert {r.rubric_id for r in rows} == {seeded.id}


def test_without_seeded_rubric_single_action_criterion(client, auth, db, monkeypatch):
    from backend.models import CriterionAssessment
    with db() as s:
        for r in s.scalars(select(Rubric)).all():
            s.delete(r)
        s.commit()
    fake, action, iv_id = _answer_once(client, auth, monkeypatch)
    with db() as s:
        rows = s.scalars(select(CriterionAssessment).where(CriterionAssessment.session_id == iv_id)).all()
        assert [r.criterion_id for r in rows] == [action]
        assert s.get(Rubric, rows[0].rubric_id).source == "LLM_PROPOSED"
