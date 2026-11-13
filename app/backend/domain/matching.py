"""Approved deterministic S/F/U semantics; no LLM, similarity or secret weights."""
from __future__ import annotations


def effective_profile(self_reports: dict[str, int | None], passed_tasks: set[str] | None = None) -> dict:
    """Elementary MCQ pass only supports level-1 lower bound; never downgrades self report."""
    passed_tasks = passed_tasks or set()
    levels: dict[str, int | None] = dict(self_reports)
    provenance: dict[str, str] = {key: "SELF_REPORT" for key, value in levels.items() if value is not None}
    conflicts: list[str] = []
    for action in sorted(passed_tasks):
        previous = levels.get(action)
        if previous is None:
            levels[action] = 1
            provenance[action] = "DEMO_OBSERVED_LEVEL_1"
        elif previous == 0:
            conflicts.append(action)
            provenance[action] = "SELF_REPORT_CONFLICTED_WITH_DEMO_TASK"
        else:
            provenance[action] = "SELF_REPORT_WITH_DEMO_TASK"
    return {"levels": levels, "provenance": provenance, "conflicts": conflicts,
            "observed_actions": sorted(passed_tasks), "policy": "effective-profile-v1"}


def evaluate_group(group: dict, levels: dict[str, int | None]) -> dict:
    comparisons: list[bool | None] = []
    annotated: list[dict] = []
    for alt in group.get("alternatives", []):
        action = alt["competency_id"]
        status = alt.get("normalization_status", "ACCEPTED_CURATED")
        level = levels.get(action)
        known = level is not None and status in ("ACCEPTED", "ACCEPTED_CURATED")
        comparison = level >= alt["required_level"] if known else None
        comparisons.append(comparison)
        annotated.append({**alt, "candidate_level": level if known else None,
                          "comparison": "S" if comparison is True else ("F" if comparison is False else "U")})
    state = "S" if True in comparisons else ("F" if comparisons and all(x is False for x in comparisons) else "U")
    return {"id": group["id"], "kind": group["kind"], "label": group["label"],
            "excerpt": group.get("excerpt", ""), "state": state, "alternatives": annotated}


def evaluate_vacancy(vacancy: dict, levels: dict[str, int | None], years_experience: int | None = None) -> dict:
    groups = [evaluate_group(g, levels) for g in vacancy.get("groups", [])]
    s, f, u = (sum(group["state"] == value for group in groups) for value in ("S", "F", "U"))
    n = s + f + u
    mandatory = [g["state"] for g in groups if g["kind"] == "MANDATORY"]
    e = 0 if "F" in mandatory else (1 if "U" in mandatory else 2)
    years_match = None if years_experience is None else years_experience >= vacancy.get("years_min", 0)
    return {
        "vacancy": {key: value for key, value in vacancy.items() if key != "groups"},
        "vacancy_id": vacancy["id"], "s": s, "f": f, "u": u,
        "required_class": e, "evaluable": bool(n),
        "match": s / (s + f) if (s + f) else None,
        "coverage": (s + f) / n if n else None,
        "r_score": s / n if n else None,
        "groups": groups, "years_eligibility": years_match,
        "note": "No mandatory groups were declared" if not mandatory else "",
        "policy": "matcher-v1",
    }


def rank_snapshot(vacancies: list[dict], profile: dict, years_experience: int | None = None) -> list[dict]:
    levels = profile.get("levels", profile)
    results = [evaluate_vacancy(vacancy, levels, years_experience) for vacancy in vacancies]
    evaluable = [row for row in results if row["evaluable"]]
    unevaluable = [row for row in results if not row["evaluable"]]
    evaluable.sort(key=lambda row: (-row["required_class"], -row["r_score"],
                                    -row["coverage"], row["vacancy_id"]))
    unevaluable.sort(key=lambda row: row["vacancy_id"])
    for index, row in enumerate(evaluable, start=1):
        row["rank_position"] = index
    for row in unevaluable:
        row["rank_position"] = None
    return evaluable + unevaluable


def presentation_summary(row: dict) -> dict:
    """Presentation-only view of an evaluate_vacancy row; never changes S/F/U or the formulas."""
    s, f, u = row["s"], row["f"], row["u"]
    total = s + f + u
    known = s + f
    mandatory_status = {2: "COMPLETE", 1: "PENDING", 0: "FAILED"}[row["required_class"]]
    match_label = None if row["match"] is None else f"Серед оцінених вимог: {round(row['match'] * 100)}% ({s}/{known})"
    return {"headline_kind": "NOT_ENOUGH_EVIDENCE" if known == 0 else "EVALUATED_SHARE",
            "known_count": s, "assessed_count": known, "total_count": total, "unknown_count": u,
            "mandatory_status": mandatory_status, "match_label": match_label}
