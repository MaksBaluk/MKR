"""Idempotent fixture loader. No live external ingestion and no fabricated source URLs."""
import json
from pathlib import Path
from sqlalchemy.orm import Session
from .db import SessionLocal
from .config import get_settings
from .security import hash_password
from .models import (Competency, Vacancy, RequirementGroup, RequirementAlternative, User)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def read_fixture(filename: str):
    return json.loads((FIXTURES / filename).read_text(encoding="utf-8"))


def seed_database(db: Session, *, demo_mode: bool | None = None, demo_password: str | None = None) -> dict:
    settings = get_settings()
    demo_mode = settings.demo_mode if demo_mode is None else demo_mode
    demo_password = settings.demo_password if demo_password is None else demo_password
    if demo_mode and (not demo_password or len(demo_password) < 10):
        raise ValueError("DEMO_PASSWORD must have at least 10 characters in DEMO_MODE")
    counts = {"competencies_added": 0, "vacancies_added": 0, "demo_user_added": 0}
    for record in read_fixture("competencies.json"):
        if db.get(Competency, record["id"]) is None:
            db.add(Competency(**record))
            counts["competencies_added"] += 1
    db.flush()
    for record in read_fixture("vacancies.json"):
        if db.get(Vacancy, record["id"]) is not None:
            continue
        vacancy_data = {k: v for k, v in record.items() if k != "groups"}
        vacancy = Vacancy(**vacancy_data)
        for sort_order, group in enumerate(record["groups"]):
            group_model = RequirementGroup(id=group["id"], kind=group["kind"], label=group["label"],
                                           excerpt=group["excerpt"], sort_order=sort_order)
            for index, alt in enumerate(group["alternatives"]):
                group_model.alternatives.append(RequirementAlternative(
                    id=f"{group['id']}-a{index+1}", competency_id=alt["competency_id"],
                    required_level=alt["required_level"], normalization_status=alt["normalization_status"]
                ))
            vacancy.groups.append(group_model)
        db.add(vacancy)
        counts["vacancies_added"] += 1
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


def main():
    with SessionLocal() as db:
        stats = seed_database(db)
        print("Fixture seed complete:", stats)


if __name__ == "__main__":
    main()
