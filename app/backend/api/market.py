"""Per-track share of active vacancies that require each professional action (public catalog data)."""
from collections import Counter
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.core import _names
from backend.db import get_db
from backend.models import RequirementAlternative, RequirementGroup, Vacancy

router = APIRouter(prefix="/market", tags=["market"])

LEVEL_NAMES = {1: "low", 2: "mid", 3: "high"}


def _highest_levels(rows) -> dict[tuple[str, str], int]:
    """(vacancy, action) -> highest required level (1..3) the vacancy asks for that action; each pair counts once."""
    best: dict[tuple[str, str], int] = {}
    for vacancy_id, action_id, level in rows:
        key = (vacancy_id, action_id)
        best[key] = max(best.get(key, 1), min(3, max(1, level)))
    return best


@router.get("/distribution")
def distribution(track: Literal["python", "marketing", "design"], db: Session = Depends(get_db)):
    active = (Vacancy.track == track, Vacancy.is_active.is_(True))
    total = db.scalar(select(func.count()).select_from(Vacancy).where(*active)) or 0
    # distinct (vacancy, action) pairs: each vacancy counts once per action, even across OR alternatives
    rows_all = db.execute(
        select(RequirementGroup.vacancy_id, RequirementAlternative.competency_id, RequirementAlternative.required_level)
        .join(RequirementAlternative, RequirementAlternative.group_id == RequirementGroup.id)
        .join(Vacancy, Vacancy.id == RequirementGroup.vacancy_id)
        .where(*active)).all()
    best = _highest_levels(rows_all)  # (vacancy, action) -> highest required level in that vacancy
    counts = Counter(action_id for _, action_id in best)
    levels: dict[str, dict[str, int]] = {a: {"low": 0, "mid": 0, "high": 0} for a in counts}
    for (_, action_id), level in best.items():
        levels[action_id][LEVEL_NAMES[level]] += 1
    names = _names(db)
    rows = sorted(counts.items(), key=lambda kv: (-round(100 * kv[1] / total), kv[0])) if total else []
    items = [{"action_id": action_id, "name": names.get(action_id, action_id),
              "share_percent": round(100 * n / total), "levels": levels[action_id]} for action_id, n in rows]
    return {"track": track, "vacancies_total": total, "items": items}


@router.get("/overview")
def overview(track: Literal["python", "marketing", "design"], db: Session = Depends(get_db)):
    """Data for the market page charts: seniority and work-mode mix, salary ranges, mandatory vs desired actions."""
    vacancies = db.scalars(select(Vacancy).where(Vacancy.track == track, Vacancy.is_active.is_(True))).all()
    seniority = Counter(v.seniority for v in vacancies)
    work_mode = Counter(v.work_mode for v in vacancies)
    salary = []
    for level in seniority:
        priced = [v for v in vacancies if v.seniority == level and v.salary_min is not None and v.salary_max is not None]
        if priced:
            mids = [(v.salary_min + v.salary_max) / 2 for v in priced]
            salary.append({"seniority": level, "count": len(priced), "min": min(v.salary_min for v in priced),
                           "avg": round(sum(mids) / len(mids)), "max": max(v.salary_max for v in priced),
                           "currency": priced[0].currency})
    mandatory: Counter = Counter()
    desired: Counter = Counter()
    level_sum: Counter = Counter()
    level_n: Counter = Counter()
    for v in vacancies:
        top: dict[str, int] = {}
        for g in v.groups:
            for a in g.alternatives:
                top[a.competency_id] = max(top.get(a.competency_id, 1), min(3, max(1, a.required_level)))
        for action_id, level in top.items():
            level_sum[action_id] += level
            level_n[action_id] += 1
        mand_ids = {a.competency_id for g in v.groups if g.kind == "MANDATORY" for a in g.alternatives}
        des_ids = {a.competency_id for g in v.groups if g.kind != "MANDATORY" for a in g.alternatives}
        mandatory.update(mand_ids)
        desired.update(des_ids)
    names = _names(db)
    kinds = [{"action_id": a, "name": names.get(a, a), "mandatory": mandatory.get(a, 0), "desired": desired.get(a, 0),
              "avg_required_level": round(level_sum[a] / level_n[a], 2) if level_n[a] else 1.0}
             for a in sorted(set(mandatory) | set(desired),
                             key=lambda a: (-(mandatory.get(a, 0) + desired.get(a, 0)), a))]
    return {"track": track, "vacancies_total": len(vacancies), "seniority": dict(seniority),
            "work_mode": dict(work_mode), "salary": sorted(salary, key=lambda r: r["seniority"]),
            "requirement_kinds": kinds}
