"""Idempotent fixture loader. No live external ingestion and no fabricated source URLs."""
import json
from pathlib import Path
from sqlalchemy.orm import Session
from .db import SessionLocal
from .config import get_settings
from .security import hash_password
from .domain.core_flow import TAU_BY_LEVEL, TAU_SOURCE_LEVEL_MAP
from .models import (Competency, Vacancy, RequirementGroup, RequirementAlternative, Rubric, RubricCriterion, User)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def read_fixture(filename: str):
    return json.loads((FIXTURES / filename).read_text(encoding="utf-8"))


def seed_database(db: Session, *, demo_mode: bool | None = None, demo_password: str | None = None) -> dict:
    settings = get_settings()
    demo_mode = settings.demo_mode if demo_mode is None else demo_mode
    demo_password = settings.demo_password if demo_password is None else demo_password
    if demo_mode and (not demo_password or len(demo_password) < 10):
        raise ValueError("DEMO_PASSWORD must have at least 10 characters in DEMO_MODE")
    counts = {"competencies_added": 0, "vacancies_added": 0, "rubrics_added": 0, "rubric_criteria_added": 0,
              "demo_user_added": 0}
    for record in read_fixture("competencies.json"):
        if db.get(Competency, record["id"]) is None:
            db.add(Competency(**record))
            counts["competencies_added"] += 1
    db.flush()
    criteria = read_fixture("vacancy_criteria.json")
    columns = {c.name for c in Vacancy.__table__.columns}
    for record in read_fixture("vacancies.json") + (read_fixture("vacancies_real.json") if (FIXTURES / "vacancies_real.json").exists() else []):
        existing = db.get(Vacancy, record["id"])
        if existing is not None:
            # Keep existing rows (and their snapshots); only sync the display title from the fixture.
            existing.title = record["title"]
            if record.get("source_type") == "REAL_IMPORTED":  # texts composed from stored fields may be regenerated
                existing.summary, existing.description = record["summary"], record["description"]
            _backfill_requirements(db, record, criteria)
            continue
        vacancy_data = {k: v for k, v in record.items() if k in columns}  # extra provenance keys outside the table are dropped
        vacancy = Vacancy(**vacancy_data)
        for sort_order, group in enumerate(record["groups"]):
            group_model = RequirementGroup(id=group["id"], kind=group["kind"], label=group["label"],
                                           excerpt=group["excerpt"], sort_order=sort_order)
            for index, alt in enumerate(group["alternatives"]):
                group_model.alternatives.append(RequirementAlternative(
                    id=f"{group['id']}-a{index+1}", competency_id=alt["competency_id"],
                    required_level=alt["required_level"], normalization_status=alt["normalization_status"],
                    **_requirement_fields(f"{group['id']}-a{index+1}", alt["required_level"], criteria)))
            vacancy.groups.append(group_model)
        db.add(vacancy)
        counts["vacancies_added"] += 1
    seed_rubrics(db, counts)
    if demo_mode:
        email = settings.demo_email.lower()
        from sqlalchemy import select
        existing = db.scalar(select(User).where(User.email == email))
        if existing is None:
            db.add(User(email=email, display_name="Демо кандидат", track="python",
                        desired_title="Python Backend Developer", years_experience=2,
                        location="Remote", password_hash=hash_password(demo_password)))
            counts["demo_user_added"] = 1
    db.commit()
    return counts


def _requirement_fields(alt_id: str, level: int, criteria: dict) -> dict:
    """D_vga from fixtures/vacancy_criteria.json and tau from the level map, stored explicitly with their sources
    (tau is a working assumption: fixture vacancies carry no employer-stated threshold)."""
    ids = criteria["requirements"].get(alt_id)
    return {"criterion_ids": ids, "criteria_source": criteria["criteria_source"] if ids is not None else None,
            "tau": TAU_BY_LEVEL.get(level), "tau_source": TAU_SOURCE_LEVEL_MAP if level in TAU_BY_LEVEL else None}


def _backfill_requirements(db: Session, record: dict, criteria: dict) -> None:
    """Existing vacancy rows created before migration 0013: fill D_vga/tau once (never overwrite a stored value).
    Cohort snapshots already taken keep their own copy of the requirements and are not touched."""
    for group in record["groups"]:
        for index, alt in enumerate(group["alternatives"]):
            alt_id = f"{group['id']}-a{index+1}"
            row = db.get(RequirementAlternative, alt_id)
            if row is None or row.criterion_ids is not None:
                continue
            for key, value in _requirement_fields(alt_id, alt["required_level"], criteria).items():
                if getattr(row, key) is None:
                    setattr(row, key, value)


def seed_rubrics(db: Session, counts: dict) -> None:
    """Curated-template starter rubrics; an existing (action_id, version) rubric is never modified."""
    from sqlalchemy import select
    existing = {(r.action_id, r.version) for r in db.scalars(select(Rubric)).all()}
    for record in read_fixture("rubrics.json")["rubrics"]:
        if (record["action_id"], record["version"]) in existing:
            continue
        rubric = Rubric(action_id=record["action_id"], version=record["version"], source=record["source"])
        db.add(rubric)
        db.flush()
        for c in record["criteria"]:
            db.add(RubricCriterion(rubric_id=rubric.id, criterion_id=c["criterion_id"], weight=float(c["weight"]),
                                   anchors={"title": c["title"], "bands": c["anchors"]}))
            counts["rubric_criteria_added"] += 1
        counts["rubrics_added"] += 1


def main():
    with SessionLocal() as db:
        stats = seed_database(db)
        print("Fixture seed complete:", stats)


if __name__ == "__main__":
    main()
