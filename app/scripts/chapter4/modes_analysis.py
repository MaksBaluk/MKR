"""Stage 5/6.4/7 analysis of raw/modes_runs.jsonl.gz (SIMULATED runs of scripts.chapter4.modes_experiment).

Writes experiment_runs.csv, criterion_results.csv, ranking_results.csv, ablation_results.csv, mode_comparison.csv,
evaluation_metrics.csv, figures_data/*.csv; appends the run rows to seniority_results.csv and the turns of selected runs
to interview_turns.jsonl (Phase-1 rows are kept; a `suite` field tells them apart) and the run ids to
experiment_manifest.json -> runs. Statistics: cluster bootstrap over profiles (pairs from one profile are not
independent), exact two-sided sign test on per-profile mean differences, Cohen's d_z. Simulated profiles are a designed
set, not a sample of candidates: CIs describe variation over this set and its noise seeds only.

Run from app/:  uv run python -m scripts.chapter4.modes_analysis
"""
from __future__ import annotations

import csv
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from scripts.chapter4.candidate_model import BY_ID, CRITICAL, truth_table
from scripts.chapter4.common import OUT, write_csv, write_json
from scripts.chapter4.modes_experiment import load_runs
from scripts.seniority_realistic import quant

FIG = OUT / "figures_data"
CONFIG_REF = "experiment_manifest.json#/runs (suite modes) + #/frozen_config"
RANK = {"UNKNOWN": 0, "JUNIOR": 1, "MIDDLE": 2, "SENIOR": 3}
BOOT = 5000
RNG_SEED = 20261119
A, B, C, D, DFD = ("A_INITIAL_PROFILE", "B_STATIC", "C_ADAPTIVE_NO_MARKET", "D_FULL_COMPETENCEMATCH",
                   "D_FIXED_DIFFICULTY")
# addendum comparisons: B vs C (adaptivity), C vs D (market planning), B vs D (total), A vs D; ablation D vs D_fixed
PAIRS = ((C, B), (D, C), (D, B), (D, A), (B, A), (C, A), (D, DFD))
METRICS = ("n_questions", "n_topics", "graded_share", "criterion_coverage", "unresolved_critical_share",
           "mean_w_mandatory_top10", "mean_w_mandatory_all", "followups", "level_correct", "graded_per_question",
           "fallback_questions", "ungraded_share", "llm_calls_simulated", "relevant_coverage", "unknown_count",
           "unresolved_mandatory_count", "top10_share_unresolved_mandatory", "top10_share_failed_mandatory")


# ---------- statistics ----------
def boot_ci(clusters: dict[str, list[float]], reps: int = BOOT, seed: int = RNG_SEED) -> tuple[float, float] | None:
    keys = sorted(k for k, v in clusters.items() if v)
    if not keys:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(reps):
        vals = [x for k in (rng.choice(keys) for _ in keys) for x in clusters[k]]
        means.append(statistics.fmean(vals))
    means.sort()
    return means[int(0.025 * reps)], means[int(0.975 * reps) - 1]


def sign_test(diffs: list[float]) -> tuple[int, int, int, float | None]:
    pos, neg = sum(d > 1e-12 for d in diffs), sum(d < -1e-12 for d in diffs)
    ties, n = len(diffs) - pos - neg, pos + neg
    if n == 0:
        return pos, neg, ties, None
    k = min(pos, neg)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
    return pos, neg, ties, p


def cohen_dz(diffs: list[float]) -> float | None:
    if len(diffs) < 2:
        return None
    sd = statistics.stdev(diffs)
    return None if sd == 0 else statistics.fmean(diffs) / sd


def _r(x, n=4):
    return "" if x is None else round(x, n)


# ---------- derived per-run values ----------
def derive(r: dict) -> dict:
    r = dict(r)
    oracle, got = r["oracle_level"], r["level_assessed_level"]
    applicable = oracle not in ("NOT_APPLICABLE", None) and got is not None
    r["level_correct"] = (1.0 if got == oracle else 0.0) if applicable else None
    r["level_abstained"] = (1.0 if got == "UNKNOWN" and oracle != "UNKNOWN" else 0.0) if applicable else None
    r["level_false_promotion"] = (1.0 if RANK[got] > RANK[oracle] else 0.0) if applicable else None
    r["level_downgrade"] = (1.0 if 0 < RANK[got] < RANK[oracle] else 0.0) if applicable else None
    r["graded_per_question"] = (r["n_graded_criteria"] / r["n_questions"]) if r["n_questions"] else None
    return r


def flat(r: dict) -> dict:
    keys = ("run_id", "suite", "label", "stub", "candidate_model", "profile_id", "track", "desired_level", "years",
            "intended_level", "oracle_level", "pattern", "mode_label", "mode", "adaptive_topics", "adaptive_followup",
            "adaptive_difficulty", "total_budget", "seed", "per_q", "n_questions", "n_topics", "followups",
            "goal_followups", "difficulty_changes_within_topic", "difficulty_changes_overall", "fallback_questions",
            "ungraded_answers", "ungraded_share", "llm_calls_simulated", "llm_exceptions", "evaluator_rejections",
            "total_s", "n_relevant_criteria", "n_graded_criteria", "graded_share", "criterion_coverage", "n_critical",
            "n_critical_graded", "unresolved_critical_share", "level_assessed_level", "level_highest_supported_level",
            "level_assessment_status", "level_policy", "level_correct", "level_abstained", "level_false_promotion",
            "level_downgrade", "mean_w_mandatory_top10", "mean_w_mandatory_all", "n_vacancy_relevant_criteria",
            "relevant_coverage", "unknown_count", "unresolved_mandatory_count", "mandatory_groups_total",
            "failed_mandatory_count", "top10_share_unresolved_mandatory", "top10_share_failed_mandatory",
            "research_planner", "interview_id")
    out = {k: r.get(k) for k in keys}
    out["topic_sequence"] = " > ".join(r["topic_sequence"])
    out["difficulty_sequence"] = " ".join(d[0] for d in r["difficulty_sequence"])
    out["questions_per_topic"] = json.dumps(r["questions_per_topic"], ensure_ascii=False)
    out["coverage_by_level"] = json.dumps(r.get("level_coverage_by_level") or {}, ensure_ascii=False)
    out["top5"] = " ".join(r["top5"])
    out["cohort_sha256"] = r["equal_conditions"]["cohort_sha256"][:16]
    out["prompt_version"] = r["equal_conditions"]["prompt_version"]
    out["config_ref"] = CONFIG_REF
    return out


# ---------- comparisons ----------
def paired(runs: list[dict], metric: str, a: str, b: str, budget, suite="modes", cand="insensitive",
           equal_used: bool = False) -> dict | None:
    """a - b for runs with the same (profile, seed, budget); mode A has no seed/budget and pairs with every one."""
    idx = {(r["profile_id"], r["mode_label"], r["total_budget"], r["seed"]): r for r in runs
           if r["suite"] == suite and r["candidate_model"] == cand}
    clusters: dict[str, list[float]] = defaultdict(list)
    for (pid, mode, bud, seed), ra in idx.items():
        if mode != a or (a != "A_INITIAL_PROFILE" and bud != budget):
            continue
        for s in ([seed] if seed is not None else sorted({k[3] for k in idx if k[1] == b and k[0] == pid and k[2] == budget})):
            rb = idx.get((pid, b, None if b == "A_INITIAL_PROFILE" else budget, None if b == "A_INITIAL_PROFILE" else s))
            if a == "A_INITIAL_PROFILE":
                ra2 = ra
            else:
                ra2 = ra
            if rb is None or ra2.get(metric) is None or rb.get(metric) is None:
                continue
            if equal_used and not (ra2["n_questions"] == rb["n_questions"]):
                continue
            clusters[pid].append(ra2[metric] - rb[metric])
    clusters = {k: v for k, v in clusters.items() if v}
    if not clusters:
        return None
    per_profile = [statistics.fmean(v) for v in clusters.values()]
    all_d = [x for v in clusters.values() for x in v]
    ci = boot_ci(clusters)
    pos, neg, ties, p = sign_test(per_profile)
    return {"metric": metric, "a": a, "b": b, "budget": budget, "equal_used_budget_only": equal_used,
            "suite": suite, "candidate_model": cand, "n_pairs": len(all_d), "n_profiles": len(clusters),
            "mean_a_minus_b": _r(statistics.fmean(all_d)), "ci95_low": _r(ci[0]) if ci else "",
            "ci95_high": _r(ci[1]) if ci else "", "profiles_a_gt_b": pos, "profiles_a_lt_b": neg, "profiles_tie": ties,
            "sign_test_p_two_sided": _r(p, 5), "cohen_dz_profile_means": _r(cohen_dz(per_profile)),
            "ci_method": f"cluster bootstrap over profiles, {BOOT} reps, rng seed {RNG_SEED}"}


def mode_means(runs, metric, mode, budget, suite="modes", cand="insensitive") -> dict:
    clusters: dict[str, list[float]] = defaultdict(list)
    for r in runs:
        if r["suite"] == suite and r["candidate_model"] == cand and r["mode_label"] == mode and \
                (mode == "A_INITIAL_PROFILE" or r["total_budget"] == budget) and r.get(metric) is not None:
            clusters[r["profile_id"]].append(r[metric])
    vals = [x for v in clusters.values() for x in v]
    ci = boot_ci(clusters) if vals else None
    return {"n": len(vals), "mean": _r(statistics.fmean(vals)) if vals else "", "ci95_low": _r(ci[0]) if ci else "",
            "ci95_high": _r(ci[1]) if ci else ""}


# ---------- writers ----------
def _merge_csv(path: Path, rows: list[dict], suites: set[str]) -> None:
    """Keep rows of other suites (Phase-1 rows get suite=phase1-scenarios), replace rows of `suites`."""
    old = []
    if path.exists():
        with open(path, encoding="utf-8", newline="") as f:
            old = [dict(x, suite=x.get("suite") or "phase1-scenarios") for x in csv.DictReader(f)]
    keep = [x for x in old if x["suite"] not in suites]
    header = list(dict.fromkeys([*(list(keep[0]) if keep else []), *(list(rows[0]) if rows else []), "suite"]))
    write_csv(path, header, [{k: x.get(k, "") for k in header} for x in keep + rows])


def _merge_jsonl(path: Path, rows: list[dict], suites: set[str]) -> None:
    old = []
    if path.exists():
        old = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    keep = [x for x in old if x.get("suite", "phase1-scenarios") not in suites]
    with open(path, "w", encoding="utf-8") as f:
        for x in keep + rows:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")


def seniority_rows(runs) -> list[dict]:
    out = []
    for r in runs:
        if r["track"] != "python" or r["suite"] == "stub_check":
            continue
        verdict = ("MATCH" if r["level_correct"] == 1.0 else "ABSTAINED" if r["level_abstained"] == 1.0 else
                   "FALSE_PROMOTION" if r["level_false_promotion"] == 1.0 else "DOWNGRADE")
        out.append({"scenario_id": r["profile_id"], "title": r["pattern"], "label": "SIMULATED", "run_id": r["run_id"],
                    "input": f"mode={r['mode_label']} budget={r['total_budget']} seed={r['seed']} "
                             f"candidate_model={r['candidate_model']} desired={r['desired_level']} years={r['years']}",
                    "expected": f"{r['oracle_level']} (SIMULATED_GROUND_TRUTH: estimator on perfect-observation evidence)",
                    "actual": f"{r['level_assessed_level']} ({r['level_assessment_status']})",
                    "criteria": r["n_graded_criteria"], "scores": "",
                    "coverage": json.dumps(r.get("level_coverage_by_level") or {}),
                    "evidence_refs": f"raw/modes_runs.jsonl.gz#{r['run_id']}", "result": verdict,
                    "verdict": verdict, "test_path": "app/tests/test_chapter4_modes.py", "policy": r["level_policy"] or "",
                    "note": "generator-vs-estimator check, not real candidates", "suite": r["suite"]})
    return out


def criterion_rows(runs) -> list[dict]:
    out = []
    for r in runs:
        if r["suite"] != "modes" or r["total_budget"] not in (50, None):
            continue
        prof = BY_ID[r["profile_id"]]
        graded = {a["criterion_id"]: a for a in r["assessments"]}
        truth = truth_table(prof)
        for cid in sorted(set(graded) | (CRITICAL if prof.track == "python" else set())):
            a = graded.get(cid)
            t = truth.get(cid)
            out.append({"run_id": r["run_id"], "suite": r["suite"], "label": "SIMULATED", "profile_id": r["profile_id"],
                        "mode_label": r["mode_label"], "total_budget": r["total_budget"], "seed": r["seed"],
                        "action_id": cid.split(".")[0], "criterion_id": cid, "level_critical": cid in CRITICAL,
                        "score": "" if not a or a["score"] is None else a["score"],
                        "state": "UNASSESSED" if not a or a["score"] is None else "GRADED",
                        "sufficient_evidence": bool(a and a["sufficient_evidence"]),
                        "revision": a["revision"] if a else "", "latent_truth": "" if t is None else t,
                        "answer_anchor": "" if t is None else quant(t)})
    return out


def ranking_rows(runs) -> list[dict]:
    out = []
    for r in runs:
        if r["suite"] != "modes":
            continue
        for i, x in enumerate(r["top10"], 1):
            out.append({"run_id": r["run_id"], "suite": r["suite"], "label": "SIMULATED", "profile_id": r["profile_id"],
                        "mode_label": r["mode_label"], "total_budget": r["total_budget"], "seed": r["seed"],
                        "rank_215": i, **{k: x[k] for k in ("vacancy_id", "title", "seniority", "z", "x", "label",
                                                            "confirmed_share")},
                        **{k: round(x[k], 4) for k in ("l_mandatory", "l_preferred", "w_mandatory", "w_preferred")}})
    return out


def _overlap(a: list[str], b: list[str], k: int) -> float:
    return len(set(a[:k]) & set(b[:k])) / k


def _kendall(a: list[str], b: list[str]) -> float | None:
    pos = {v: i for i, v in enumerate(b)}
    xs = [pos[v] for v in a if v in pos]
    n = len(xs)
    if n < 2:
        return None
    conc = sum((xs[i] < xs[j]) - (xs[i] > xs[j]) for i in range(n) for j in range(i + 1, n))
    return conc / (n * (n - 1) / 2)


def ranking_diffs(runs) -> list[dict]:
    idx = {(r["profile_id"], r["mode_label"], r["total_budget"], r["seed"]): r for r in runs if r["suite"] == "modes"}
    out = []
    for (pid, mode, bud, seed), r in sorted(idx.items(), key=lambda kv: str(kv[0])):
        if mode == "A_INITIAL_PROFILE":
            continue
        a = idx[(pid, "A_INITIAL_PROFILE", None, None)]
        others = {"vs_A": a["ranking"]}
        if mode != B:
            others["vs_B"] = idx[(pid, B, bud, seed)]["ranking"]
        if mode == D:
            others["vs_C"] = idx[(pid, C, bud, seed)]["ranking"]
        for name, other in others.items():
            out.append({"run_id": r["run_id"], "profile_id": pid, "mode_label": mode, "total_budget": bud,
                        "seed": seed, "comparison": name, "top1_same": r["ranking"][0] == other[0],
                        "top5_overlap": _overlap(r["ranking"], other, 5), "top10_overlap": _overlap(r["ranking"], other, 10),
                        "kendall_tau_full": _r(_kendall(r["ranking"], other))})
    return out


def level_outcomes(runs) -> tuple[list[dict], list[dict]]:
    dist, conf = [], []
    groups = defaultdict(list)
    for r in runs:
        if r["track"] == "python" and r["suite"] in ("modes", "ablation_sensitive"):
            groups[(r["suite"], r["candidate_model"], r["mode_label"], r["total_budget"])].append(r)
    for (suite, cand, mode, bud), rs in sorted(groups.items(), key=lambda kv: str(kv[0])):
        c = Counter(r["level_assessed_level"] for r in rs)
        labels = ["UNKNOWN", "JUNIOR", "MIDDLE", "SENIOR"]
        f1 = []
        for lab in labels:
            tp = sum(r["level_assessed_level"] == lab and r["oracle_level"] == lab for r in rs)
            fp = sum(r["level_assessed_level"] == lab and r["oracle_level"] != lab for r in rs)
            fn = sum(r["level_assessed_level"] != lab and r["oracle_level"] == lab for r in rs)
            f1.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
        nonunk = [r for r in rs if r["level_assessed_level"] != "UNKNOWN"]
        dist.append({"suite": suite, "candidate_model": cand, "mode_label": mode, "total_budget": bud, "n_runs": len(rs),
                     **{f"assessed_{lab}": c.get(lab, 0) for lab in labels},
                     "accuracy_vs_simulated_truth": _r(statistics.fmean(r["level_correct"] for r in rs)),
                     "macro_f1_vs_simulated_truth": _r(statistics.fmean(f1)),
                     "abstention_rate": _r(statistics.fmean(r["level_abstained"] for r in rs)),
                     "false_promotion_rate": _r(statistics.fmean(r["level_false_promotion"] for r in rs)),
                     "unjustified_downgrade_rate": _r(statistics.fmean(r["level_downgrade"] for r in rs)),
                     "selective_accuracy": _r(statistics.fmean(r["level_correct"] for r in nonunk)) if nonunk else "",
                     "n_non_unknown": len(nonunk), "label": "SIMULATED_GROUND_TRUTH"})
        for o in labels:
            for p in labels:
                conf.append({"suite": suite, "candidate_model": cand, "mode_label": mode, "total_budget": bud,
                             "simulated_truth": o, "assessed": p,
                             "count": sum(r["oracle_level"] == o and r["level_assessed_level"] == p for r in rs)})
    return dist, conf


def curves(runs) -> list[dict]:
    out = []
    budgets = sorted({r["total_budget"] for r in runs if r["total_budget"]})
    for mode in (A, B, C, D, DFD):
        for b in budgets:
            row = {"mode_label": mode, "total_budget": b, "label": "SIMULATED"}
            for m in ("graded_share", "criterion_coverage", "n_questions", "n_topics", "unresolved_critical_share",
                      "mean_w_mandatory_top10", "mean_w_mandatory_all", "level_correct", "fallback_questions",
                      "relevant_coverage", "unknown_count", "unresolved_mandatory_count"):
                mm = mode_means(runs, m, mode, b)
                row.update({f"{m}_mean": mm["mean"], f"{m}_ci95_low": mm["ci95_low"], f"{m}_ci95_high": mm["ci95_high"],
                            f"{m}_n": mm["n"]})
            out.append(row)
    return out


def ablation(runs) -> list[dict]:
    out = []
    for cand, suite in (("insensitive", "modes"), ("sensitive", "ablation_sensitive")):
        budgets = sorted({r["total_budget"] for r in runs if r["suite"] == suite and r["total_budget"]})
        for b in budgets:
            for mode in (B, C, DFD, D):
                rs = [r for r in runs if r["suite"] == suite and r["mode_label"] == mode and r["total_budget"] == b]
                row = {"candidate_model": cand, "suite": suite, "total_budget": b, "mode_label": mode,
                       "adaptive_difficulty": mode in (C, D), "n_runs": len(rs), "label": "SIMULATED"}
                for m in ("n_questions", "graded_share", "criterion_coverage", "unresolved_critical_share",
                          "difficulty_changes_overall", "level_correct", "level_false_promotion", "level_abstained"):
                    mm = mode_means(runs, m, mode, b, suite, cand)
                    row.update({m: mm["mean"], f"{m}_ci95": f"[{mm['ci95_low']}, {mm['ci95_high']}]"})
                d = Counter(x for r in rs for x in r["difficulty_sequence"])
                row["difficulty_mix"] = json.dumps(dict(sorted(d.items())))
                out.append(row)
            for metric in ("graded_share", "criterion_coverage", "level_correct", "unresolved_critical_share"):
                p = paired(runs, metric, D, DFD, b, suite, cand)
                if p:
                    out.append({"candidate_model": cand, "suite": suite, "total_budget": b,
                                "mode_label": f"DIFF {D} - {DFD} ({metric})",
                                "n_runs": p["n_pairs"], metric: p["mean_a_minus_b"],
                                f"{metric}_ci95": f"[{p['ci95_low']}, {p['ci95_high']}]",
                                "difficulty_mix": f"sign test p={p['sign_test_p_two_sided']} "
                                                  f"(+{p['profiles_a_gt_b']}/-{p['profiles_a_lt_b']}/={p['profiles_tie']})",
                                "label": "SIMULATED"})
    return out


def equal_conditions(runs) -> dict:
    groups = defaultdict(list)
    for r in runs:
        if r["suite"] == "modes":
            groups[r["profile_id"]].append(r)
    bad = []
    for pid, rs in groups.items():
        ec = [r["equal_conditions"] for r in rs]
        for key in ("cohort_sha256", "prompt_version", "algorithm_version", "profile_snapshot_sha", "rubric_versions_sha"):
            if len({e[key] for e in ec}) != 1:
                bad.append((pid, key))
        inter = [e for e in ec if e["config"]["mode"] != "INITIAL_PROFILE"]
        if len({e["model_class"] for e in inter}) != 1:
            bad.append((pid, "model_class"))
        for e in inter:
            c = e["config"]
            if (c["max_topics"], c["max_per_topic"], c["static_questions_per_topic"]) != (10, 5, 2):
                bad.append((pid, "caps"))
    budget_ok = all(r["n_questions"] <= (r["total_budget"] or 50) and r["n_topics"] <= 10 and
                    max(r["questions_per_topic"].values(), default=0) <= 5 for r in runs)
    return {"profiles_checked": len(groups), "violations": bad, "all_equal": not bad,
            "budgets_never_exceeded": budget_ok,
            "checked_keys": ["cohort_sha256", "prompt_version", "algorithm_version", "profile_snapshot_sha",
                             "rubric_versions_sha (seeded rubric versions of the cohort)", "model_class (interview modes)",
                             "caps 10/5/2"]}


def fallback_summary(runs) -> list[dict]:
    out = []
    groups = defaultdict(list)
    for r in runs:
        if r["mode_label"] != "A_INITIAL_PROFILE":
            groups[(r["suite"], r["stub"], r["candidate_model"], r["mode_label"])].append(r)
    for (suite, stub, cand, mode), rs in sorted(groups.items()):
        q = sum(r["n_questions"] for r in rs)
        out.append({"suite": suite, "stub": stub, "candidate_model": cand, "mode_label": mode, "n_runs": len(rs),
                    "questions": q, "fallback_questions": sum(r["fallback_questions"] for r in rs),
                    "ungraded_answers": sum(r["ungraded_answers"] for r in rs),
                    "fallback_share": _r(sum(r["fallback_questions"] for r in rs) / q if q else None),
                    "runs_with_fallback": sum(r["fallback_questions"] > 0 for r in rs)})
    return out


def evaluation_metrics(dist: list[dict]) -> list[dict]:
    nogt = "No independent expert labels exist (EXPERIMENT_BLOCKER EB-1); see expert_annotation_templates/."
    rows = [{"metric": m, "component": comp, "status": "NO_GROUND_TRUTH", "value": "", "n": "", "ci95": "",
             "scope": "independent labels for candidates and candidate x vacancy pairs", "note": nogt}
            for m, comp in (("MAE (criterion score vs expert)", "Evaluator"), ("Precision@5", "Ranking"),
                            ("NDCG@10", "Ranking"), ("Accuracy vs expert level", "SeniorityEstimator"),
                            ("Macro-F1 vs expert level", "SeniorityEstimator"),
                            ("Confusion matrix vs expert level", "SeniorityEstimator"),
                            ("Abstention rate vs expert 'cannot determine'", "SeniorityEstimator"),
                            ("Selective accuracy vs expert level", "SeniorityEstimator"),
                            ("False-promotion risk vs expert level", "SeniorityEstimator"),
                            ("Unjustified-downgrade risk vs expert level", "SeniorityEstimator"),
                            ("Inter-expert agreement (Cohen/Fleiss kappa)", "Annotation"))]
    rows.append({"metric": "Evaluator MAE vs simulated truth", "component": "Evaluator", "status": "NOT_APPLICABLE",
                 "value": "", "n": "", "ci95": "", "scope": "SIMULATED",
                 "note": "the stub Evaluator grades the generator's own anchors plus designed noise; an error against "
                         "them measures the noise parameters, not evaluator quality"})
    rows.append({"metric": "Ranking P@5/NDCG@10 vs simulated relevance", "component": "Ranking",
                 "status": "NOT_APPLICABLE", "value": "", "n": "", "ci95": "", "scope": "SIMULATED",
                 "note": "no relevance definition independent of the system's own requirement model exists; "
                         "comparing the ranking to itself is forbidden by the spec"})
    for d in dist:
        if d["suite"] != "modes" or d["mode_label"] == "A_INITIAL_PROFILE" and d["total_budget"] is not None:
            continue
        scope = f"SIMULATED python profiles x seeds; mode {d['mode_label']}, budget {d['total_budget']}"
        for key, name in (("accuracy_vs_simulated_truth", "Estimator accuracy vs simulated truth"),
                          ("macro_f1_vs_simulated_truth", "Estimator macro-F1 vs simulated truth"),
                          ("abstention_rate", "Abstention (UNKNOWN while truth known)"),
                          ("false_promotion_rate", "False promotion vs simulated truth"),
                          ("unjustified_downgrade_rate", "Unjustified downgrade vs simulated truth"),
                          ("selective_accuracy", "Selective accuracy (non-UNKNOWN outputs)")):
            rows.append({"metric": name, "component": "SeniorityEstimator (end-to-end through simulated interview)",
                         "status": "SIMULATED_GROUND_TRUTH", "value": d[key], "n": d["n_runs"], "ci95": "",
                         "scope": scope,
                         "note": "truth = estimator on perfect-observation evidence of the generator; tests information "
                                 "loss of interview+noise, not agreement with experts or real candidates"})
    return rows


def build() -> dict:
    raw = load_runs()
    runs = [derive(r) for r in raw]
    meta = json.loads((OUT / "raw" / "modes_meta.json").read_text(encoding="utf-8"))
    FIG.mkdir(parents=True, exist_ok=True)
    write_csv(OUT / "experiment_runs.csv", list(flat(runs[0])), [flat(r) for r in runs])
    crit = criterion_rows(runs)
    write_csv(OUT / "criterion_results.csv", list(crit[0]), crit)
    rank = ranking_rows(runs)
    write_csv(OUT / "ranking_results.csv", list(rank[0]), rank)
    _merge_csv(OUT / "seniority_results.csv", seniority_rows(runs), {"modes", "ablation_sensitive"})
    # turns (size bound): seed 0 at budget 50 for every mode and the stub check; all turns are in raw/modes_runs.jsonl.gz
    sel = [r for r in runs if r["seed"] == 0 and r["total_budget"] == 50 and r["suite"] in ("modes", "stub_check")]
    turns = [{"run_id": r["run_id"], "suite": r["suite"], "label": "SIMULATED", "profile_id": r["profile_id"],
              "mode_label": r["mode_label"], "total_budget": r["total_budget"], "seed": r["seed"],
              "interview_id": r["interview_id"],
              **{k: v for k, v in t.items() if k not in ("controller_before", "controller_after")}}
             for r in sel for t in r["turns"]]
    _merge_jsonl(OUT / "interview_turns.jsonl", turns, {"modes", "ablation_sensitive", "stub_check"})
    comp = []
    budgets = sorted({r["total_budget"] for r in runs if r["suite"] == "modes" and r["total_budget"]})
    for b in budgets:
        for a, bb in PAIRS:
            for m in METRICS:
                p = paired(runs, m, a, bb, b)
                if p:
                    comp.append(p)
            if (a, bb) in ((C, B), (D, C), (D, B)):
                for m in ("graded_share", "criterion_coverage", "unresolved_critical_share", "level_correct"):
                    p = paired(runs, m, a, bb, b, equal_used=True)
                    if p:
                        comp.append(p)
    write_csv(OUT / "mode_comparison.csv", list(comp[0]), comp)
    dist, conf = level_outcomes(runs)
    write_csv(FIG / "level_outcomes.csv", list(dist[0]), dist)
    write_csv(FIG / "level_confusion_vs_simulated_truth.csv", list(conf[0]), conf)
    cur = curves(runs)
    write_csv(FIG / "coverage_vs_budget.csv", list(cur[0]), cur)
    write_csv(FIG / "questions_by_mode.csv", ["mode_label", "total_budget", "n_questions_mean", "n_questions_ci95_low",
                                              "n_questions_ci95_high", "n_topics_mean", "n_questions_n"],
              [{k: c[k] for k in ("mode_label", "total_budget", "n_questions_mean", "n_questions_ci95_low",
                                  "n_questions_ci95_high", "n_topics_mean", "n_questions_n")} for c in cur])
    write_csv(FIG / "uncertainty_width_vs_budget.csv",
              ["mode_label", "total_budget", "mean_w_mandatory_top10_mean", "mean_w_mandatory_top10_ci95_low",
               "mean_w_mandatory_top10_ci95_high", "mean_w_mandatory_all_mean", "mean_w_mandatory_all_ci95_low",
               "mean_w_mandatory_all_ci95_high"], [{k: c[k] for k in (
                   "mode_label", "total_budget", "mean_w_mandatory_top10_mean", "mean_w_mandatory_top10_ci95_low",
                   "mean_w_mandatory_top10_ci95_high", "mean_w_mandatory_all_mean", "mean_w_mandatory_all_ci95_low",
                   "mean_w_mandatory_all_ci95_high")} for c in cur])
    rd = ranking_diffs(runs)
    write_csv(FIG / "ranking_differences.csv", list(rd[0]), rd)
    fb = fallback_summary(runs)
    write_csv(FIG / "fallback_by_mode.csv", list(fb[0]), fb)
    abl = ablation(runs)
    header = list(dict.fromkeys(k for row in abl for k in row))
    write_csv(OUT / "ablation_results.csv", header, abl)
    write_csv(OUT / "evaluation_metrics.csv", ["metric", "component", "status", "value", "n", "ci95", "scope", "note"],
              evaluation_metrics(dist))
    eq = equal_conditions(runs)
    # manifest: append the run ids of this suite (Phase-1 entries and frozen_config untouched)
    man_path = OUT / "experiment_manifest.json"
    man = json.loads(man_path.read_text(encoding="utf-8"))
    ds = man.get("frozen_config", {}).get("dataset_snapshot", {})
    if "note" in ds:  # owner decision: one neutral provenance sentence (values/hashes unchanged)
        ds["note"] = ("Походження вакансій наведено за приміткою власника про дані; технічні метадані імпорту збережені "
                      "в репозиторії (поля import_version, retrieved_at, source_name). tau WORKING_ASSUMPTION_LEVEL_MAP")
    man["runs"] = [x for x in man.get("runs", []) if x.get("suite") not in {"modes", "ablation_sensitive", "stub_check"}]
    for suite in ("modes", "ablation_sensitive", "stub_check"):
        ids = [r["run_id"] for r in runs if r["suite"] == suite]
        man["runs"].append({
            "suite": suite, "label": "SIMULATED", "n_runs": len(ids), "run_ids": ids,
            "config": "experiment_manifest.json#/frozen_config (commit 282f6fb); mode configs below",
            "mode_configs": meta["modes"], "budgets": sorted({r["total_budget"] for r in runs if r["suite"] == suite
                                                              and r["total_budget"]}),
            "seeds": sorted({r["seed"] for r in runs if r["suite"] == suite and r["seed"] is not None}),
            "profiles": sorted({r["profile_id"] for r in runs if r["suite"] == suite}),
            "stub": meta["stub"] if suite != "stub_check" else "scripts.seniority_realistic.Model (documented stub)",
            "candidate_model": "insensitive" if suite != "ablation_sensitive" else "sensitive",
            "command": "cd app && uv run python -m scripts.chapter4.modes_experiment && "
                       "uv run python -m scripts.chapter4.modes_analysis",
            "files": ["raw/modes_runs.jsonl.gz", "raw/modes_meta.json", "experiment_runs.csv"],
            "reproducibility": meta["reproducibility"] if suite == "modes" else None,
            "equal_conditions_check": eq if suite == "modes" else None, "wall_s_all_suites": meta["wall_s"]})
    write_json(man_path, man)
    summary = {"n_runs": len(runs), "equal_conditions": eq, "reproducibility": meta["reproducibility"]}
    write_json(FIG / "summary.json", summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False)[:2000])
