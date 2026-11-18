"""Djinni import: pure parser, validation, provenance of imported fixtures, migration 0014. No network."""
import json
import re
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from backend.config import get_settings
from backend.domain.vacancy_import import (ALIAS, SOURCE_TYPE, build_groups, build_record, level_for, match, sections,
                                           seniority_of, validate_record)
from backend.seed import read_fixture

PY = [c["id"] for c in read_fixture("competencies.json") if c["track"] == "python"]
POSTING = {
    "url": "https://djinni.co/jobs/1-junior-python-engineer/", "identifier": "1", "title": "Junior Python Engineer",
    "hiringOrganization": {"name": "Acme"}, "datePosted": "2026-11-17T10:00:00", "jobLocationType": "TELECOMMUTE",
    "experienceRequirements": {"monthsOfExperience": 12.0},
    "baseSalary": {"currency": "USD", "value": {"minValue": 500, "maxValue": 800}},
    "description": ("We build tools for ML teams. Python is our passion.\n\nRequirements:\n"
                    "1+ years of practical experience with Python.\nWeb frameworks like Flask, Django, or FastAPI.\n"
                    "Docker, Celery and Redis.\nGit and unit tests.\n\nNice to have:\nKubernetes basics.\n\n"
                    "Responsibilities:\nWrite Python services with Django.\n\nWe offer:\nGym and Docker licences.\n"),
}


def test_every_competency_has_a_compilable_alias_and_tracks_are_covered():
    comps = [c["id"] for c in read_fixture("competencies.json")]
    assert set(ALIAS) == set(comps) and len(comps) == 60


def test_alias_matching_examples():
    assert match("Experience with PostgreSQL and SQLAlchemy", PY) == ["postgresql", "sqlalchemy"]
    assert match("CI/CD pipelines", PY) == ["ci-cd"]
    assert match("We value teamwork", PY) == []


def test_sections_company_intro_and_responsibilities_are_not_requirements():
    modes = {line: m for m, line, _ in sections(POSTING["description"])}
    assert modes["We build tools for ML teams. Python is our passion."] == "IGNORE"
    assert modes["Write Python services with Django."] == "IGNORE"
    assert modes["Gym and Docker licences."] == "IGNORE"
    assert modes["Git and unit tests."] == "REQ"


def test_groups_or_and_mandatory_desired_and_excerpt():
    gs = build_groups(POSTING["description"], PY, "JUNIOR")
    by = {tuple(a["competency_id"] for a in g["alternatives"]): g for g in gs}
    assert ("django", "fastapi") in by or ("fastapi", "django") in by  # one OR group, not two AND groups
    for solo in (("docker",), ("celery",), ("redis",), ("git",), ("pytest",)):
        assert by[solo]["kind"] == "MANDATORY"
    assert by[("kubernetes",)]["kind"] == "DESIRED"
    assert by[("python-core",)]["excerpt"] == "1+ years of practical experience with Python."
    assert not any("licences" in g["excerpt"] or "Write Python" in g["excerpt"] for g in gs)
    assert all(g["excerpt"] for g in gs)


def test_levels_and_seniority_rules():
    assert [seniority_of(t, None) for t in ("Senior Python Dev", "Python Lead", "Junior Dev", "Middle Dev", "Python Dev")] == \
        ["SENIOR", "LEAD", "JUNIOR", "MIDDLE", "JUNIOR"]
    assert seniority_of("Python Developer", 60) == "SENIOR"
    assert [level_for("JUNIOR", False), level_for("MIDDLE", False), level_for("SENIOR", False), level_for("SENIOR", True),
            level_for("JUNIOR", True)] == [1, 2, 3, 2, 1]


def test_build_record_provenance_and_determinism():
    rec = build_record(POSTING, "python", PY, "2026-11-18")
    assert rec == build_record(POSTING, "python", PY, "2026-11-18")
    assert (rec["source_type"], rec["source_url"], rec["retrieved_at"], rec["date_posted"]) == (
        SOURCE_TYPE, POSTING["url"], "2026-11-18", "2026-11-17")
    assert (rec["seniority"], rec["years_min"], rec["work_mode"], rec["salary_min"], rec["salary_max"]) == ("JUNIOR", 1, "REMOTE", 500, 800)
    assert len(rec["summary"]) <= 280 and "Витяг" in rec["description"] and rec["id"] == "djinni-python-1"
    assert validate_record(rec, PY) == []


@pytest.mark.parametrize("patch", [{"url": "https://example.com/jobs/1"}, {"title": ""}, {"description": ""},
                                   {"hiringOrganization": {}}])
def test_unusable_postings_return_none(patch):
    assert build_record({**POSTING, **patch}, "python", PY, "2026-11-18") is None


def test_malformed_input_never_raises():
    assert build_record({}, "python", PY, "d") is None
    assert build_record({"url": 5}, "python", PY, "d") is None


def test_validation_rejections():
    rec = build_record(POSTING, "python", PY, "2026-11-18")
    thin = {**rec, "groups": rec["groups"][:2]}
    assert "fewer than 3 requirement groups" in validate_record(thin, PY)
    assert "competency outside the track" in validate_record(rec, ["python-core"])
    assert "missing retrieved_at" in validate_record({**rec, "retrieved_at": ""}, PY)
    no_excerpt = {**rec, "groups": [{**g, "excerpt": ""} for g in rec["groups"]]}
    assert "group without source excerpt" in validate_record(no_excerpt, PY)


# ---- the imported fixture file (absent until an import was run)
REAL = Path(__file__).resolve().parent.parent / "fixtures" / "vacancies_real.json"
needs_real = pytest.mark.skipif(not REAL.exists(), reason="no import has been run")


@needs_real
def test_imported_fixture_has_provenance_and_valid_structure():
    rows = json.loads(REAL.read_text(encoding="utf-8"))
    ids = [r["id"] for r in rows]
    assert rows and len(ids) == len(set(ids))
    comps = {t: [c["id"] for c in read_fixture("competencies.json") if c["track"] == t] for t in ("python", "marketing", "design")}
    for r in rows:
        assert r["source_type"] == SOURCE_TYPE and re.fullmatch(r"https://djinni\.co/jobs/\d+[^\s]*", r["source_url"])
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["retrieved_at"]) and r["import_version"] and r["level_source"]
        assert validate_record(r, comps[r["track"]]) == [], r["id"]
        assert len(r["description"]) < 4000 and len(r["summary"]) <= 280  # excerpts only, never the full posting


@needs_real
def test_imported_vacancies_are_seeded_with_provenance_and_djinni_label(db):
    from backend.api.common import source_label
    from backend.models import Vacancy
    s = db()
    real = s.query(Vacancy).filter_by(source_type=SOURCE_TYPE).all()
    assert real and all(v.retrieved_at and v.source_url and v.import_version for v in real)
    assert {source_label(v) for v in real} == {"Djinni"}


def test_0014_adds_columns_and_is_reversible(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm14.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    new = {"retrieved_at", "date_posted", "import_version"}
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "0013_requirement_criteria_tau")
        eng = create_engine(url)
        with eng.begin() as c:
            for name in new:
                c.execute(sa.text(f"ALTER TABLE vacancies DROP COLUMN {name}"))
        command.upgrade(cfg, "head")
        assert new <= {c["name"] for c in sa.inspect(eng).get_columns("vacancies")}
        command.downgrade(cfg, "0013_requirement_criteria_tau")
        assert not new & {c["name"] for c in sa.inspect(eng).get_columns("vacancies")}
        command.upgrade(cfg, "head")
    finally:
        get_settings.cache_clear()


def test_headers_without_keywords_and_arrow_bullets():
    text = "Intro paragraph about us.\nWhat matters to us:\n↳ Confident use of Figma and Photoshop\nNice to have:\n↳ Experience with Illustrator\nWhat you’ll do:\n↳ Collaborate with developers\n"
    design = [c["id"] for c in read_fixture("competencies.json") if c["track"] == "design"]
    got = {(g["kind"], g["alternatives"][0]["competency_id"]) for g in build_groups(text, design, "JUNIOR")}
    assert got == {("MANDATORY", "figma"), ("MANDATORY", "photoshop"), ("DESIRED", "illustrator")}
