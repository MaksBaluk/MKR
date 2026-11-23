"""E2-E5 result files of protocol v2 from the SIMULATED mode runs, reading annotation files when they exist.

E2 interview_experiment_results.csv; E3 ranking_metrics.csv (P@5 / NDCG@10 only against ADJUDICATED relevance labels,
else NO_GROUND_TRUTH; extra ranking metrics always); E4 evaluator_metrics.csv; E5 seniority_experiment_results.csv and
estimator_metrics.csv. Tables 4.1-4.7, figures, hypotheses and reports: scripts/chapter4/final_report.py.
P@5/NDCG@10 rank only the fixed annotated pool (see pool_ranking). Unit of analysis = candidate (seeds averaged).
Run from app/:  uv run python -m scripts.chapter4.chapter4_metrics
"""
from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

from backend.experiments.metrics import MissingLabelsError, ndcg_at_k, precision_at_k
from scripts.chapter4.common import OUT, write_csv
from scripts.chapter4.modes_analysis import A, B, C, D, DFD, _kendall, _overlap, derive
from scripts.chapter4.modes_experiment import load_runs

DATA, TAB, FIGS, FIGD = OUT / "data", OUT / "tables", OUT / "figures", OUT / "figures_data"
MODES = (A, B, C, D)
UA = {A: "A: початковий профіль", B: "B: статичне", C: "C: адаптивне без ринку", D: "D: CompetenceMatch",
      DFD: "D без зміни складності"}
ADJ = "ADJUDICATED"


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def annotations() -> dict:
    a = DATA / "annotations"
    rel, lvl, crit = (_read(a / n) for n in ("expert_vacancy_relevance.csv", "expert_seniority.csv",
                                            "expert_criterion_annotations.csv"))
    labels = defaultdict(dict)
    for r in rel:
        if r["annotator_id"] == ADJ and r["relevance"] != "":
            labels[r["candidate_id"]][r["vacancy_id"]] = int(r["relevance"])
    levels = {r["candidate_id"]: r["level"] for r in lvl if r["annotator_id"] == ADJ}
    scores = {(r["question_id"], r["criterion_id"]): (None if r["score"] == "" else float(r["score"]))
              for r in crit if r["annotator_id"] == ADJ}
    kinds = sorted({r["annotator_id"].split("_")[0] for r in rel + lvl + crit})
    gt = ("PILOT_LLM_ANNOTATOR" if kinds and all(k == "LLM" or k == ADJ for k in kinds) else
          "HUMAN_EXPERT" if kinds else None)
    return {"relevance": dict(labels), "levels": levels, "criterion": scores, "ground_truth_version": gt,
            "n_rows": {"relevance": len(rel), "seniority": len(lvl), "criterion": len(crit)}}


def e2(runs) -> list[dict]:
    out = []
    for r in runs:
        if r["suite"] != "modes":
            continue
        out.append({"run_id": r["run_id"], "candidate_id": r["profile_id"], "mode": r["mode_label"],
                    "budget": r["total_budget"] if r["total_budget"] else "", "seed": "" if r["seed"] is None else r["seed"],
                    "questions_used": r["n_questions"], "topics_used": r["n_topics"],
                    "relevant_coverage": r["relevant_coverage"],
                    "relevant_denominator": r["n_vacancy_relevant_criteria"],
                    "relevant_denominator_definition": "criteria named by D_vga of the candidate's cohort requirements",
                    "total_rubric_coverage": r["graded_share"], "total_rubric_denominator": r["n_relevant_criteria"],
                    "sufficient_topic_coverage": r["criterion_coverage"],
                    "critical_coverage": None if r["unresolved_critical_share"] is None else
                    round(1 - r["unresolved_critical_share"], 4), "critical_denominator": r["n_critical"],
                    "unknown_count": r["unknown_count"], "unresolved_mandatory_count": r["unresolved_mandatory_count"],
                    "mandatory_groups_total": r["mandatory_groups_total"], "followups": r["followups"],
                    "difficulty_changes": r["difficulty_changes_overall"], "fallback_questions": r["fallback_questions"],
                    "ungraded_share": r["ungraded_share"], "llm_calls": r["llm_calls_simulated"],
                    "duration_seconds": r["total_s"], "status": "SIMULATED"})
    return out


def pools() -> dict[str, list[str]]:
    """Fixed annotated vacancy pool per candidate (annotation_inputs/vacancy_pool.csv, file order)."""
    out: dict[str, list[str]] = defaultdict(list)
    for r in _read(DATA / "annotation_inputs" / "vacancy_pool.csv"):
        out[r["candidate_id"]].append(r["vacancy_id"])
    return dict(out)


def pool_ranking(ranking: list[str], pool_ids: list[str]) -> tuple[list[str], int]:
    """Rank only the fixed pool: the run's order restricted to pool vacancies. Pool vacancies absent from the run's
    ranking are not dropped: they are appended after the ranked ones in pool-file order (a fixed, system-independent
    order) and counted. With the full 90-vacancy rankings of the frozen runs this count is 0 for every run."""
    pool_set, rank_set = set(pool_ids), set(ranking)
    missing = [v for v in pool_ids if v not in rank_set]
    return [v for v in ranking if v in pool_set] + missing, len(missing)


def run_pool_metrics(r: dict, ann: dict, pool_map: dict) -> dict | None:
    """P@5 (relevant = grade >= 2) and NDCG@10 (linear gain) of one run against ADJUDICATED pool labels."""
    labels, pool_ids = ann["relevance"].get(r["profile_id"]), pool_map.get(r["profile_id"])
    if not labels or not pool_ids:
        return None
    lab = {v: labels[v] for v in pool_ids if v in labels}
    if len(lab) != len(pool_ids):
        raise MissingLabelsError(f"{r['profile_id']}: {len(pool_ids) - len(lab)} pool vacancies without ADJUDICATED label")
    ranked, missing = pool_ranking(r["ranking"], pool_ids)
    return {"p5": precision_at_k(ranked, lab, 5), "ndcg10": ndcg_at_k(ranked, lab, 10), "missing": missing,
            "pool_size": len(pool_ids), "pool_relevant": sum(g >= 2 for g in lab.values())}


def e3(runs, ann) -> list[dict]:
    groups = defaultdict(list)
    for r in runs:
        if r["suite"] == "modes":
            groups[(r["profile_id"], r["mode_label"], r["total_budget"])].append(r)
    a_rank = {pid: rs[0]["ranking"] for (pid, m, _), rs in groups.items() if m == A}
    pool_map = pools()
    out = []
    for (pid, mode, bud), rs in sorted(groups.items(), key=lambda kv: str(kv[0])):
        pm, status = [], "NO_GROUND_TRUTH"
        try:
            pm = [x for x in (run_pool_metrics(r, ann, pool_map) for r in rs) if x is not None]
            if pm:
                status = f"COMPUTED_{ann['ground_truth_version']}"
        except MissingLabelsError:
            pm, status = [], "INCOMPLETE_LABELS"
        p5 = [x["p5"] for x in pm]
        n10 = [x["ndcg10"] for x in pm if x["ndcg10"] is not None]
        top5s = [r["ranking"][:5] for r in rs]
        stab = [_overlap(x, y, 5) for i, x in enumerate(top5s) for y in top5s[i + 1:]]
        out.append({"candidate_id": pid, "mode": mode, "budget": bud or "", "n_runs": len(rs),
                    "precision_at_5": round(statistics.fmean(p5), 4) if p5 else "",
                    "ndcg_at_10": round(statistics.fmean(n10), 4) if n10 else "",
                    "precision_at_5_sd_seeds": round(statistics.pstdev(p5), 4) if len(p5) > 1 else "",
                    "ndcg_at_10_sd_seeds": round(statistics.pstdev(n10), 4) if len(n10) > 1 else "",
                    "evaluation_set": "fixed annotated pool (pool-v1); run ranking restricted to pool",
                    "pool_size": pm[0]["pool_size"] if pm else "", "pool_relevant_ge2": pm[0]["pool_relevant"] if pm else "",
                    "pool_missing_from_ranking": sum(x["missing"] for x in pm) if pm else "",
                    "ground_truth_version": ann["ground_truth_version"] or "", "status": status,
                    "share_top10_unresolved_mandatory": round(statistics.fmean(r["top10_share_unresolved_mandatory"] for r in rs), 4),
                    "share_top10_failed_mandatory": round(statistics.fmean(r["top10_share_failed_mandatory"] for r in rs), 4),
                    "top5_overlap_vs_A": round(statistics.fmean(_overlap(r["ranking"], a_rank[pid], 5) for r in rs), 4),
                    "kendall_tau_vs_A": round(statistics.fmean(_kendall(r["ranking"], a_rank[pid]) for r in rs), 4),
                    "top5_stability_across_seeds": round(statistics.fmean(stab), 4) if stab else ""})
    return out


def e4(runs, ann) -> list[dict]:
    inter = [r for r in runs if r["suite"] == "modes" and r["n_questions"]]
    turns = sum(r["n_questions"] for r in inter)
    rows = [{"section": "JSON/contract validation", "metric": "evaluator outputs rejected (MALFORMED/INVALID)",
             "value": sum(r["evaluator_rejections"] for r in inter), "n": turns, "status": "SIMULATED",
             "note": "product validation (criterion membership, verbatim quotes) applied to stub outputs"},
            {"section": "JSON/contract validation", "metric": "provider exceptions",
             "value": sum(r["llm_exceptions"] for r in inter), "n": turns, "status": "SIMULATED", "note": ""},
            {"section": "FakeChat/stub", "metric": "share of answers UNGRADED",
             "value": round(sum(r["ungraded_answers"] for r in inter) / turns, 4), "n": turns, "status": "SIMULATED",
             "note": "stub Evaluator; not evidence of LLM quality"}]
    bank = {}
    p = DATA / "response_bank.jsonl"
    if p.exists():
        bank = {b["response_id"]: b for b in map(json.loads, p.read_text(encoding="utf-8").splitlines())}
    by_run = {r["run_id"]: r for r in runs}
    pairs = []
    for (qid, cid), exp in ann["criterion"].items():
        b = bank.get(qid)
        r = by_run.get(b["first_run_id"]) if b else None
        if not r:
            continue
        t = next((t for t in r["turns"] if t["answer_text"] == b["response_text"]), None)
        sys = next((rv["score"] for rv in r["revisions"] if t and t["turn_id"] in rv["evidence_turns"]
                    and rv["criterion_id"] == cid), None)
        pairs.append((exp, sys))
    both = [(e, s) for e, s in pairs if e is not None and s is not None]
    gt = ann["ground_truth_version"]
    rows += [{"section": "FakeChat/stub", "metric": "MAE vs adjudicated criterion annotation",
              "value": round(statistics.fmean(abs(e - s) for e, s in both), 4) if both else "", "n": len(both),
              "status": f"COMPUTED_{gt}" if both else "NO_GROUND_TRUTH",
              "note": "template answers: measures stub noise vs annotators, not a real Evaluator"},
             {"section": "FakeChat/stub", "metric": "UNKNOWN detection (annotator NO_EVIDENCE and system null)",
              "value": (round(sum(e is None and s is None for e, s in pairs) / max(1, sum(e is None for e, _ in pairs)), 4)
                        if any(e is None for e, _ in pairs) else ""), "n": len(pairs),
              "status": f"COMPUTED_{gt}" if pairs else "NO_GROUND_TRUTH", "note": ""},
             {"section": "FakeChat/stub", "metric": "unjustified score > 0 (annotator NO_EVIDENCE, system > 0)",
              "value": sum(e is None and (s or 0) > 0 for e, s in pairs) if pairs else "", "n": len(pairs),
              "status": f"COMPUTED_{gt}" if pairs else "NO_GROUND_TRUTH", "note": ""},
             {"section": "FakeChat/stub", "metric": "repeat consistency", "value": "", "n": "",
              "status": "NOT_APPLICABLE", "note": "stub grades are deterministic per seed by construction"},
             {"section": "local LLM", "metric": "all E4 metrics", "value": "", "n": "", "status": "NOT_RUN",
              "note": "no local LLM available in this environment"},
             {"section": "production LLM", "metric": "all E4 metrics", "value": "", "n": "", "status": "NOT_RUN",
              "note": "no paid/real LLM calls allowed (EB-2)"}]
    return rows


RANK = {"UNKNOWN": 0, "JUNIOR": 1, "MIDDLE": 2, "SENIOR": 3}


def e5(runs, ann) -> tuple[list[dict], list[dict]]:
    rows = []
    for r in runs:
        if r["suite"] != "modes":
            continue
        cov = r.get("level_coverage_by_level") or {}
        assess = {a["criterion_id"]: a["score"] for a in r["assessments"]}
        from scripts.chapter4.candidate_model import CRITICAL
        gaps = sorted(c for c in CRITICAL if assess.get(c) is not None and assess[c] < 0.5)
        rows.append({"run_id": r["run_id"], "candidate_id": r["profile_id"], "mode": r["mode_label"],
                     "budget": r["total_budget"] or "", "seed": "" if r["seed"] is None else r["seed"],
                     "desired_level": r["desired_level"].upper(), "assessed_level": r["level_assessed_level"],
                     "highest_supported_level": r["level_highest_supported_level"],
                     "assessment_status": r["level_assessment_status"],
                     "coverage_junior": cov.get("JUNIOR", ""), "coverage_middle": cov.get("MIDDLE", ""),
                     "coverage_senior": cov.get("SENIOR", ""), "critical_gaps": " ".join(gaps),
                     "unknown_critical_count": r["n_critical"] - r["n_critical_graded"],
                     "simulated_truth_level": r["oracle_level"], "expert_level": ann["levels"].get(r["profile_id"], ""),
                     "status": "SIMULATED"})
    metrics = []
    for truth_name, truth_of in (("SIMULATED_GROUND_TRUTH", lambda x: x["simulated_truth_level"]),
                                 (ann["ground_truth_version"] or "EXPERT", lambda x: x["expert_level"] or None)):
        for mode in (A, B, C, D):
            for bud in sorted({x["budget"] for x in rows if x["mode"] == mode}, key=str):
                rs = [x for x in rows if x["mode"] == mode and x["budget"] == bud and truth_of(x)]
                if not rs:
                    metrics.append({"truth": truth_name, "mode": mode, "budget": bud, "n_runs": 0,
                                    "n_candidates": 0, "status": "NO_GROUND_TRUTH"})
                    continue
                by_c = defaultdict(list)
                for x in rs:
                    by_c[x["candidate_id"]].append(x)
                labs = ["UNKNOWN", "JUNIOR", "MIDDLE", "SENIOR"]

                def f1(lab):
                    tp = sum(x["assessed_level"] == lab and truth_of(x) == lab for x in rs)
                    fp = sum(x["assessed_level"] == lab and truth_of(x) != lab for x in rs)
                    fn = sum(x["assessed_level"] != lab and truth_of(x) == lab for x in rs)
                    return 0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn)
                cand_acc = [statistics.fmean(x["assessed_level"] == truth_of(x) for x in v) for v in by_c.values()]
                non = [x for x in rs if x["assessed_level"] != "UNKNOWN"]
                metrics.append({
                    "truth": truth_name, "mode": mode, "budget": bud, "n_runs": len(rs), "n_candidates": len(by_c),
                    "accuracy_candidate_mean": round(statistics.fmean(cand_acc), 4),
                    "macro_f1": round(statistics.fmean(f1(lab) for lab in labs), 4),
                    "abstention_rate": round(statistics.fmean(x["assessed_level"] == "UNKNOWN" and truth_of(x) != "UNKNOWN"
                                                              for x in rs), 4),
                    "selective_accuracy": round(statistics.fmean(x["assessed_level"] == truth_of(x) for x in non), 4)
                    if non else "",
                    "false_promotion_rate": round(statistics.fmean(RANK[x["assessed_level"]] > RANK[truth_of(x)]
                                                                   for x in rs), 4),
                    "unjustified_downgrade_rate": round(statistics.fmean(0 < RANK[x["assessed_level"]] < RANK[truth_of(x)]
                                                                         for x in rs), 4),
                    "senior_reached_runs": sum(x["assessed_level"] == "SENIOR" for x in rs),
                    "status": "SIMULATED_GROUND_TRUTH" if truth_name == "SIMULATED_GROUND_TRUTH" else f"COMPUTED_{truth_name}"})
    return rows, metrics


def _svg_lines(path: Path, title: str, xlab: str, ylab: str, series: dict[str, list[tuple[float, float]]],
               ymax: float = 1.0) -> None:
    w, h, l, b, t, r = 640, 400, 60, 50, 40, 190
    xs = sorted({x for s in series.values() for x, _ in s})
    if not xs:
        return
    fx = lambda x: l + (x - xs[0]) / ((xs[-1] - xs[0]) or 1) * (w - l - r)  # noqa: E731
    fy = lambda y: h - b - y / ymax * (h - b - t)  # noqa: E731
    colors = ["#1f5fa8", "#c2410c", "#15803d", "#7c3aed", "#6b7280"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" font-family="sans-serif" font-size="12">',
           f'<rect width="{w}" height="{h}" fill="white"/>', f'<text x="{l}" y="22" font-size="14">{title}</text>',
           f'<line x1="{l}" y1="{h - b}" x2="{w - r}" y2="{h - b}" stroke="black"/>',
           f'<line x1="{l}" y1="{t}" x2="{l}" y2="{h - b}" stroke="black"/>',
           f'<text x="{(l + w - r) / 2}" y="{h - 12}" text-anchor="middle">{xlab}</text>',
           f'<text x="14" y="{(t + h - b) / 2}" transform="rotate(-90 14 {(t + h - b) / 2})" text-anchor="middle">{ylab}</text>']
    for x in xs:
        out.append(f'<text x="{fx(x)}" y="{h - b + 16}" text-anchor="middle">{x:g}</text>')
    for i in range(6):
        y = ymax * i / 5
        out.append(f'<text x="{l - 6}" y="{fy(y) + 4}" text-anchor="end">{y:.2g}</text>')
        out.append(f'<line x1="{l}" y1="{fy(y)}" x2="{w - r}" y2="{fy(y)}" stroke="#e5e7eb"/>')
    for k, (name, pts) in enumerate(series.items()):
        c = colors[k % len(colors)]
        out.append(f'<polyline fill="none" stroke="{c}" stroke-width="2" points="'
                   + " ".join(f"{fx(x):.1f},{fy(y):.1f}" for x, y in sorted(pts)) + '"/>')
        out += [f'<circle cx="{fx(x):.1f}" cy="{fy(y):.1f}" r="3" fill="{c}"/>' for x, y in pts]
        out.append(f'<rect x="{w - r + 12}" y="{t + 18 * k}" width="12" height="3" fill="{c}"/>'
                   f'<text x="{w - r + 30}" y="{t + 18 * k + 5}">{name}</text>')
    out.append("</svg>")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _md_table(rows: list[dict], cols: list[str]) -> str:
    return "\n".join(["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)] +
                     ["| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in rows])


def build() -> dict:
    runs = [derive(r) for r in load_runs()]
    ann = annotations()
    e2rows = e2(runs)
    write_csv(OUT / "interview_experiment_results.csv", list(e2rows[0]), e2rows)
    e3rows = e3(runs, ann)
    write_csv(OUT / "ranking_metrics.csv", list(e3rows[0]), e3rows)
    e4rows = e4(runs, ann)
    write_csv(OUT / "evaluator_metrics.csv", list(e4rows[0]), e4rows)
    e5rows, e5m = e5(runs, ann)
    write_csv(OUT / "seniority_experiment_results.csv", list(e5rows[0]), e5rows)
    write_csv(OUT / "estimator_metrics.csv", list(dict.fromkeys(k for x in e5m for k in x)), e5m)
    return {"e2_rows": len(e2rows), "e3_rows": len(e3rows), "e5_rows": len(e5rows),
            "ground_truth_version": ann["ground_truth_version"], "annotation_rows": ann["n_rows"]}


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False))
