"""Deterministic priority tuple (mandatory open, all open, verify, distinct-vacancy prevalence)."""
from collections import Counter, defaultdict
from .matching import effective_profile


def priorities(vacancies: list[dict], baseline: dict[str, int | None],
               successful_tasks: set[str] | None = None, asked_counts: dict[str, int] | None = None,
               needs_verification: set[str] | None = None) -> list[dict]:
    successful_tasks = successful_tasks or set()
    asked_counts = asked_counts or {}
    needs_verification = needs_verification or set()
    distinct_vacancies: dict[str, set[str]] = defaultdict(set)
    mandatory_groups: dict[str, set[str]] = defaultdict(set)
    all_groups: dict[str, set[str]] = defaultdict(set)
    n = len({v["id"] for v in vacancies})
    for vacancy in vacancies:
        for group in vacancy.get("groups", []):
            # A valid level-1 demo task only settles groups with a <=1 threshold.
            # Failed MCQ tasks do not establish inability or settle a group.
            # Ruling: an elementary objective pass settles a group only when no alternative is still under verification.
            if any(alt["competency_id"] in successful_tasks and alt["required_level"] <= 1
                   for alt in group.get("alternatives", [])) and not any(
                       alt["competency_id"] in needs_verification for alt in group.get("alternatives", [])):
                continue
            for alt in group.get("alternatives", []):
                action = alt["competency_id"]
                # Ruling: default interview asks each competency once (FREE_TEXT). A single verification
                # repeat is allowed and is served as the optional objective check (bank index 1).
                asked = asked_counts.get(action, 0)
                if asked >= 2 or (asked == 1 and action not in needs_verification):
                    continue
                distinct_vacancies[action].add(vacancy["id"])
                all_groups[action].add(group["id"])
                if group["kind"] == "MANDATORY":
                    mandatory_groups[action].add(group["id"])
    result = []
    for action, vacancy_set in distinct_vacancies.items():
        priority = [len(mandatory_groups[action]), len(all_groups[action]),
                    int(action in needs_verification or (action in baseline and baseline[action] is not None
                                                         and action not in successful_tasks)),
                    len(vacancy_set) / n if n else 0]
        if any(priority):
            result.append({"competency_id": action, "priority": priority,
                           "mode": "VERIFY" if priority[2] else "DISCOVER",
                           "vacancy_count": len(vacancy_set)})
    result.sort(key=lambda row: (-row["priority"][0], -row["priority"][1], -row["priority"][2],
                                 -row["priority"][3], row["competency_id"]))
    return result


def choose_topic(vacancies: list[dict], baseline: dict, successful_tasks: set[str],
                 asked_counts: dict[str, int], static_plan: list[str] | None = None,
                 needs_verification: set[str] | None = None) -> dict | None:
    if static_plan is not None:
        for action in static_plan:
            if asked_counts.get(action, 0) == 0:
                return {"competency_id": action, "priority": [0, 0, 0, 0], "mode": "STATIC"}
        return None
    choices = priorities(vacancies, baseline, successful_tasks, asked_counts, needs_verification)
    return choices[0] if choices else None


def observed_successes(turns) -> set[str]:
    return {t.competency_id for t in turns if t.assessment_status == "DEMO_OBSERVED_LEVEL_1"}


def asked_by_action(turns) -> dict[str, int]:
    return dict(Counter(t.competency_id for t in turns))
