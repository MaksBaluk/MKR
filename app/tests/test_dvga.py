"""D_vga (criterion subset per requirement) and tau status. MATH_SPEC §3d, thesis (2.11)-(2.13)."""
import json

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from backend.config import get_settings
from backend.domain.core_flow import TAU_SOURCE_LEVEL_MAP, alt_criteria, alt_tau, eval_alternative, rank_vacancy
from backend.domain.vacancy_criteria import CRITERIA_SOURCE, derive_required_criteria
from backend.seed import read_fixture
from tests.test_interview_flow import cohort, llm  # noqa: F401

RUBRIC = {"c": [("c.a", 1.0), ("c.b", 1.0), ("c.c", 1.0), ("c.d", 1.0)]}


def alt(**kw):
    return {"competency_id": "c", "required_level": 2, **kw}


# ---- matching semantics
def test_requirement_needing_two_criteria_is_satisfied_by_those_two_only():
    scores = {"c.a": 0.8, "c.b": 0.8, "c.c": None, "c.d": 0.0}  # c.d is a failing criterion NOT required here
    assert eval_alternative(alt(criterion_ids=["c.a", "c.b"]), scores, RUBRIC).status == "SATISFIED"
    assert eval_alternative(alt(), scores, RUBRIC).status == "FAILED"  # legacy whole-rubric row sees the failing c.d


def test_required_criterion_unknown_stays_unresolved_and_failed_is_failed():
    ids = ["c.a", "c.b"]
    assert eval_alternative(alt(criterion_ids=ids), {"c.a": 0.8}, RUBRIC).status == "UNRESOLVED"  # c.b never assessed
    assert eval_alternative(alt(criterion_ids=ids), {"c.a": 0.8, "c.b": 0.1}, RUBRIC).status == "FAILED"


def test_criterion_ids_are_authoritative_and_never_widened():
    assert alt_criteria(alt(criterion_ids=["c.b", "c.a"]), RUBRIC) == [("c.a", 1.0), ("c.b", 1.0)]  # rubric order
    assert alt_criteria(alt(criterion_ids=["x.unknown"]), RUBRIC) == []
    ev = eval_alternative(alt(criterion_ids=["x.unknown"]), {"c.a": 1.0, "c.b": 1.0, "c.c": 1.0, "c.d": 1.0}, RUBRIC)
    assert (ev.status, ev.lower, ev.upper) == ("UNRESOLVED", 0.0, 1.0)  # no resolvable D_vga: unknown, never SATISFIED


def test_tau_explicit_overrides_level_map_and_unknown_level_is_not_evaluable():
    assert alt_tau(alt(required_level=1)) == 0.5 and alt_tau(alt(required_level=3)) == 0.9
    assert alt_tau(alt(required_level=1, tau=0.8)) == 0.8
    assert alt_tau(alt(required_level=7)) is None
    ev = eval_alternative(alt(required_level=7, criterion_ids=["c.a"]), {"c.a": 1.0}, RUBRIC)
    assert ev.status == "UNRESOLVED"  # no silent 0.75 default
    scores = {"c.a": 0.6}
    assert eval_alternative(alt(required_level=1, criterion_ids=["c.a"]), scores, RUBRIC).status == "SATISFIED"
    assert eval_alternative(alt(required_level=1, tau=0.8, criterion_ids=["c.a"]), scores, RUBRIC).status == "FAILED"


def test_vacancy_z_uses_the_subset():
    vac = {"id": "v", "years_min": 0, "groups": [{"id": "g", "kind": "MANDATORY",
                                                  "alternatives": [alt(criterion_ids=["c.a", "c.b"])]}]}
    r = rank_vacancy(vac, {"c.a": 0.9, "c.b": 0.9}, RUBRIC, 3)
    assert r.z == 2 and r.label == "RANKED"
    assert rank_vacancy(vac, {}, RUBRIC, 3).z == 1  # nothing assessed: UNKNOWN, not confirmed


# ---- derivation rule and fixtures
def test_derivation_is_deterministic_subset_by_level():
    crit = ["k.1", "k.2", "k.3", "k.4"]
    a = derive_required_criteria("v1", "k", 1, crit)
    assert a == derive_required_criteria("v1", "k", 1, crit) and len(a) == 2 and set(a) <= set(crit)
    assert [len(derive_required_criteria("v1", "k", lv, crit)) for lv in (1, 2, 3)] == [2, 3, 4]
    assert derive_required_criteria("v1", "k", 2, crit) == [c for c in crit if c in derive_required_criteria("v1", "k", 2, crit)]
    assert any(derive_required_criteria(f"v{i}", "k", 1, crit) != a for i in range(2, 12))  # varies across vacancies
    assert derive_required_criteria("v1", "k", 1, []) == []


def test_fixture_mapping_covers_every_alternative_inside_its_rubric():
    rubrics = {r["action_id"]: [c["criterion_id"] for c in r["criteria"]] for r in read_fixture("rubrics.json")["rubrics"]}
    doc = read_fixture("vacancy_criteria.json")
    assert doc["criteria_source"] == CRITERIA_SOURCE and "SYNTHETIC" in doc["_note"]
    strict = total = 0
    try:
        imported = read_fixture("vacancies_real.json")
    except FileNotFoundError:
        imported = []
    for v in read_fixture("vacancies.json") + imported:
        for g in v["groups"]:
            for i, a in enumerate(g["alternatives"]):
                ids = doc["requirements"][f"{g['id']}-a{i + 1}"]
                full = rubrics[a["competency_id"]]
                assert ids and set(ids) <= set(full)
                total += 1
                strict += len(ids) < len(full)
    assert total == len(doc["requirements"]) and strict > total * 0.5  # not "all criteria" by default


# ---- persistence and snapshots
def test_seeded_alternatives_carry_criteria_and_tau_source(db):
    from backend.models import RequirementAlternative
    rows = db().query(RequirementAlternative).all()
    assert rows and all(r.criterion_ids and r.criteria_source == CRITERIA_SOURCE for r in rows)
    assert all(r.tau is not None and r.tau_source == TAU_SOURCE_LEVEL_MAP for r in rows)


def test_snapshot_freezes_criteria_and_tau(client, auth, cohort, db):  # noqa: F811
    from backend.models import CohortSnapshot
    snap = db().get(CohortSnapshot, cohort)
    alts = [a for rev in snap.requirement_revisions.values() for g in rev["groups"] for a in g["alternatives"]]
    assert alts and all(a["criterion_ids"] and a["tau"] is not None and a["tau_source"] for a in alts)


def test_seed_backfills_legacy_rows_without_overwriting(db):
    from backend.models import RequirementAlternative
    from backend.seed import seed_database
    s = db()
    legacy, kept = s.query(RequirementAlternative).limit(2).all()
    legacy.criterion_ids = legacy.criteria_source = legacy.tau = legacy.tau_source = None
    kept.criterion_ids = ["custom.keep"]
    s.commit()
    seed_database(s)
    s.refresh(legacy), s.refresh(kept)
    assert legacy.criterion_ids and legacy.tau is not None and legacy.tau_source == TAU_SOURCE_LEVEL_MAP
    assert kept.criterion_ids == ["custom.keep"]


def test_breakdown_exposes_required_criteria_and_threshold_source(client, auth, llm):  # noqa: F811
    from tests.test_profiles_api import API, mk_profile, run_attempt, start
    p = mk_profile(client, auth)
    run_attempt(client, auth, start(client, auth, p["id"]).json(), answers=3)
    top = client.get(f"{API}/profiles/{p['id']}/results", params={"fitting": "all"}, headers=auth).json()["items"][0]
    d = client.get(f"{API}/profiles/{p['id']}/results/{top['vacancy_id']}", headers=auth)
    assert d.status_code == 200, d.text
    alts = [a for g in d.json()["groups"] for a in g["alternatives"]]
    assert all(a["required_criteria"] and a["threshold_source"] == TAU_SOURCE_LEVEL_MAP for a in alts)


def test_0013_adds_columns_and_keeps_rows(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm13.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    new = {"criterion_ids", "criteria_source", "tau", "tau_source"}
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "0012_experiment_run_fields")
        eng = create_engine(url)
        with eng.begin() as c:  # 0001 builds from current metadata: strip to emulate a pre-0013 database
            for name in new:
                c.execute(sa.text(f"ALTER TABLE requirement_alternatives DROP COLUMN {name}"))
        command.upgrade(cfg, "head")
        assert new <= {c["name"] for c in sa.inspect(eng).get_columns("requirement_alternatives")}
        command.downgrade(cfg, "0012_experiment_run_fields")
        assert not new & {c["name"] for c in sa.inspect(eng).get_columns("requirement_alternatives")}
        command.upgrade(cfg, "head")  # idempotent re-upgrade
    finally:
        get_settings.cache_clear()
