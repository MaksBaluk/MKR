"""Automatic candidate cohort: deterministic eligibility filters and a capped, ranked selection.

No LLM import here by design: ranking and eligibility are decided by the approved matcher.
"""
from __future__ import annotations
from .matching import rank_snapshot

POLICY = "TRACK_ALL_ELIGIBLE_V1"
MAX_COHORT = 30  # Ruling: current corpus has 30 per track, so the cap never fires; above it, keep the best baseline ranks.


def eligible(vacancies: list[dict], *, work_mode: str | None, seniority: str | None,
             location_contains: str | None, respect_experience: bool,
             years_experience: int | None) -> list[dict]:
    """Optional filters only. Unknown years_experience never excludes a vacancy."""
    result = []
    for vacancy in vacancies:
        if work_mode and vacancy["work_mode"].upper() != work_mode.upper():
            continue
        if seniority and vacancy["seniority"] != seniority.upper():
            continue
        if location_contains and location_contains.strip().lower() not in vacancy["location"].lower():
            continue
        if respect_experience and years_experience is not None and vacancy["years_min"] > years_experience:
            continue
        result.append(vacancy)
    return result


def select_cohort(vacancies: list[dict], *, levels: dict, years_experience: int | None,
                  work_mode: str | None = None, seniority: str | None = None,
                  location_contains: str | None = None, respect_experience: bool = False) -> tuple[list[dict], dict]:
    """Return (cohort sorted by vacancy id, cohort_policy). Raises ValueError when empty."""
    filters = {"work_mode": work_mode, "seniority": seniority,
               "location_contains": location_contains, "respect_experience": respect_experience}
    pool = eligible(vacancies, work_mode=work_mode, seniority=seniority, location_contains=location_contains,
                    respect_experience=respect_experience, years_experience=years_experience)
    if not pool:
        raise ValueError("Немає вакансій за цими умовами")
    by_id = {v["id"]: v for v in pool}
    ranked_ids = [row["vacancy_id"] for row in rank_snapshot(pool, {"levels": levels}, years_experience)]
    kept_ids = ranked_ids[:MAX_COHORT]
    dropped_ids = ranked_ids[MAX_COHORT:]
    cohort = [by_id[vid] for vid in sorted(kept_ids)]
    policy = {"policy": POLICY, "cap": MAX_COHORT, "filters": filters,
              "eligible_count": len(pool), "dropped_count": len(dropped_ids), "dropped_ids": dropped_ids,
              "years_experience_known": years_experience is not None}
    return cohort, policy
