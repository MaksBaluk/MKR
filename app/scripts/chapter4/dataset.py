"""dataset_summary.csv: structure of the vacancy catalog per track, from fixtures only (no database)."""
from __future__ import annotations

import collections
import json

from scripts.chapter4.common import APP, OUT, write_csv

HEADER = ["track", "vacancies", "unique_competencies", "mandatory_groups",
          "desired_groups", "or_groups", "alternatives_total", "level_1", "level_2", "level_3", "seniority_distribution",
          "rubrics_used", "criteria_in_used_rubrics", "mean_criteria_per_requirement", "min_criteria_per_requirement",
          "max_criteria_per_requirement", "requirements_with_subset_of_rubric"]


def build() -> list[dict]:
    fx = APP / "fixtures"
    vacancies = json.loads((fx / "vacancies.json").read_text(encoding="utf-8"))
    if (fx / "vacancies_real.json").exists():
        vacancies += json.loads((fx / "vacancies_real.json").read_text(encoding="utf-8"))
    rubrics = {r["action_id"]: r for r in json.loads((fx / "rubrics.json").read_text(encoding="utf-8"))["rubrics"]}
    dvga = json.loads((fx / "vacancy_criteria.json").read_text(encoding="utf-8"))["requirements"]
    groups = collections.defaultdict(list)
    for v in vacancies:
        groups[v["track"]].append(v)  # per profession only (owner decision: no provenance classes)
    rows = []
    for track, vs in sorted(groups.items()):
        comps, lv, sen = set(), collections.Counter(), collections.Counter(v["seniority"] for v in vs)
        mand = des = orr = alts = subset = 0
        sizes = []
        for v in vs:
            for g in v["groups"]:
                mand += g["kind"] == "MANDATORY"
                des += g["kind"] != "MANDATORY"
                orr += len(g["alternatives"]) > 1
                for i, a in enumerate(g["alternatives"]):
                    alts += 1
                    comps.add(a["competency_id"])
                    lv[a["required_level"]] += 1
                    ids = dvga[f"{g['id']}-a{i + 1}"]
                    sizes.append(len(ids))
                    subset += len(ids) < len(rubrics[a["competency_id"]]["criteria"])
        rows.append({
            "track": track, "vacancies": len(vs),
            "unique_competencies": len(comps), "mandatory_groups": mand, "desired_groups": des, "or_groups": orr,
            "alternatives_total": alts, "level_1": lv[1], "level_2": lv[2], "level_3": lv[3],
            "seniority_distribution": json.dumps(dict(sorted(sen.items())), ensure_ascii=False),
            "rubrics_used": len(comps), "criteria_in_used_rubrics": sum(len(rubrics[c]["criteria"]) for c in comps),
            "mean_criteria_per_requirement": round(sum(sizes) / len(sizes), 3), "min_criteria_per_requirement": min(sizes),
            "max_criteria_per_requirement": max(sizes), "requirements_with_subset_of_rubric": subset})
    write_csv(OUT / "dataset_summary.csv", HEADER, rows)
    return rows


if __name__ == "__main__":
    for r in build():
        print(r["track"], r["vacancies"], r["unique_competencies"], r["mandatory_groups"], r["desired_groups"], r["or_groups"])
