"""Independent re-derivation of five headline numbers from raw files (stdlib only; imports nothing from backend/ or the
other chapter-4 scripts) and comparison with the values published in tables/*.csv.

Raw inputs: raw/modes_runs.jsonl.gz, data/annotations/*.csv (ADJUDICATED rows), data/annotation_inputs/vacancy_pool.csv.
Writes artifacts/chapter4/self_audit.json. Run from app/:  uv run python -m scripts.chapter4.self_audit
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parents[3] / "artifacts" / "chapter4"
TOL = 0.0006  # published values are rounded to 3 decimals


def _rows(p: Path) -> list[dict]:
    with p.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _runs() -> list[dict]:
    with gzip.open(OUT / "raw" / "modes_runs.jsonl.gz", "rt", encoding="utf-8") as fh:
        return [r for r in map(json.loads, fh) if r["suite"] == "modes"]


def _cand_mean(vals: dict[str, list[float]]) -> float:
    return sum(sum(v) / len(v) for v in vals.values()) / len(vals)


def derive() -> dict:
    runs = _runs()
    rel = defaultdict(dict)
    for r in _rows(OUT / "data/annotations/expert_vacancy_relevance.csv"):
        if r["annotator_id"] == "ADJUDICATED":
            rel[r["candidate_id"]][r["vacancy_id"]] = int(r["relevance"])
    lvl = {r["candidate_id"]: r["level"] for r in _rows(OUT / "data/annotations/expert_seniority.csv")
           if r["annotator_id"] == "ADJUDICATED"}
    pool = defaultdict(list)
    for r in _rows(OUT / "data/annotation_inputs/vacancy_pool.csv"):
        pool[r["candidate_id"]].append(r["vacancy_id"])

    def restricted(run):
        ps = set(pool[run["profile_id"]])
        order = [v for v in run["ranking"] if v in ps]
        return order + [v for v in pool[run["profile_id"]] if v not in set(order)]

    def p5(run):
        g = rel[run["profile_id"]]
        return sum(g[v] >= 2 for v in restricted(run)[:5]) / 5

    def ndcg10(run):
        g = rel[run["profile_id"]]
        dcg = sum(g[v] / math.log2(i + 2) for i, v in enumerate(restricted(run)[:10]))
        ideal = sum(x / math.log2(i + 2) for i, x in enumerate(sorted((g[v] for v in pool[run["profile_id"]]), reverse=True)[:10]))
        return dcg / ideal

    def sel(mode, budget=None):
        return [r for r in runs if r["mode_label"] == mode and (budget is None or r["total_budget"] == budget)]

    out = {}
    v = defaultdict(list)
    for r in sel("D_FULL_COMPETENCEMATCH", 50):
        v[r["profile_id"]].append(p5(r))
    out["P@5 D b50"] = _cand_mean(v)
    v = defaultdict(list)
    for r in sel("A_INITIAL_PROFILE"):
        v[r["profile_id"]].append(ndcg10(r))
    out["NDCG@10 A"] = _cand_mean(v)
    v = defaultdict(list)
    for r in sel("B_STATIC", 20):
        crit = {a["criterion_id"] for a in r["assessments"] if a["score"] is not None}
        v[r["profile_id"]].append(r["n_vacancy_relevant_graded"] / r["n_vacancy_relevant_criteria"])
        assert len(crit) >= r["n_vacancy_relevant_graded"]
    out["relevant coverage B b20"] = _cand_mean(v)
    v = defaultdict(list)
    for r in sel("D_FULL_COMPETENCEMATCH", 50):
        v[r["profile_id"]].append(float(r["level_assessed_level"] == lvl[r["profile_id"]]))
    out["level accuracy (pilot) D b50"] = _cand_mean(v)
    rs = sel("D_FULL_COMPETENCEMATCH", 10)
    out["abstention (pilot) D b10"] = sum(r["level_assessed_level"] == "UNKNOWN" and lvl[r["profile_id"]] != "UNKNOWN"
                                          for r in rs) / len(rs)
    out["ADJUDICATED relevance rows"] = sum(len(x) for x in rel.values())
    return out


def _num(cell: str) -> float:
    return float(cell.split(" ")[0])


def published() -> dict:
    t44 = _rows(OUT / "tables/table_4_4_interview.csv")
    t45 = _rows(OUT / "tables/table_4_5_recommendations.csv")
    t46 = _rows(OUT / "tables/table_4_6_estimator.csv")
    t41 = _rows(OUT / "tables/table_4_1_data.csv")

    def row(t, mode_prefix, budget):
        return next(r for r in t if r["Режим"].startswith(mode_prefix) and r["Бюджет"] == budget)
    adj = next(r for r in t41 if r["Показник"].startswith("Рядки пілотної розмітки"))["Значення"]
    return {"P@5 D b50": _num(row(t45, "D: ", "50")["P@5 [95% ДІ]"]),
            "NDCG@10 A": _num(row(t45, "A: ", "—")["NDCG@10 [95% ДІ]"]),
            "relevant coverage B b20": _num(row(t44, "B: ", "20")["Покриття релевантних критеріїв [95% ДІ]"]),
            "level accuracy (pilot) D b50": _num(row(t46, "D: ", "50")["Точність (пілот)"]),
            "abstention (pilot) D b10": _num(row(t46, "D: ", "10")["Частка утримань (UNKNOWN при визначеному рівні)"]),
            "ADJUDICATED relevance rows": float(adj.split("ADJUDICATED: ")[1].split(" ")[0])}


def run() -> dict:
    d, p = derive(), published()
    items = [{"quantity": k, "independent": round(d[k], 4), "published": p[k],
              "agree": abs(d[k] - p[k]) <= TOL} for k in d]
    res = {"method": "separate stdlib re-implementation (pool restriction, P@5, NDCG@10 linear gain, coverage, level "
                     "accuracy, abstention) vs published tables; tolerance 0.0006 (3-decimal rounding)",
           "items": items, "summary": f"{sum(i['agree'] for i in items)}/{len(items)} agree",
           "discrepancies": [i for i in items if not i["agree"]]}
    (OUT / "self_audit.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return res


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=1))
