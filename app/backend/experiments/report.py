"""Evaluation report over exported experiment records: per-mode metrics, chart datasets and files.

Pure: no DB, no model, no network. Expert labels are evaluation ground truth only; they never reach ranking code.

Mode keys: INITIAL_PROFILE, STATIC_INTERVIEW, ADAPTIVE_INTERVIEW; an ADAPTIVE record with adaptive flags switched off
gets one suffix per disabled flag in the order topics, followup, difficulty (e.g. ADAPTIVE_INTERVIEW-followup,
ADAPTIVE_INTERVIEW-topics-difficulty). Records of one mode key must share one config; each candidate appears at most
once per mode key; candidates are matched across modes by candidate_id.

Ranking metrics (P@5, NDCG@10): labels restricted to the vacancies the record ranked. A candidate is included only
with >= min_labeled_vacancies labelled vacancies and a fully labelled top 10; otherwise excluded and counted
(n_excluded_lt_10_labeled, n_excluded_unlabeled_in_top with the unlabelled ids). Unlabelled vacancies are never given
a grade. All-zero labels: P@5 counted, NDCG undefined (None) and counted in n_ndcg_undefined. One inclusion rule covers
both P@5 and NDCG@10: a candidate with an unlabelled vacancy at ranks 6-10 is excluded from P@5 too (deliberate: both
metrics stay on one sample).
precision_at_5 / ndcg_at_10 per mode are UNPAIRED means over that mode's included candidates, which can differ between
modes. precision_at_5_paired / ndcg_at_10_paired / n_paired are means over the candidates included in EVERY mode of
the report; the ranking_by_mode chart and report.csv use the paired values.

Coverage: records with an empty relevant_criteria (also records exported before that field existed) are excluded from
criterion_coverage_mean, questions_to_coverage_mean and n_reached and counted in n_excluded_no_relevant_criteria.
An interview with no answers has coverage 0.0 (nothing is evidenced).

Labels: when any label in a set is ADJUDICATED only the adjudicated labels are used; the candidates whose
non-adjudicated labels were ignored are listed (labels.<kind>.candidates_labels_ignored) and stated, and a candidate left
with no relevance label at all is excluded as LABELS_NOT_ADJUDICATED (n_excluded_labels_not_adjudicated), not as too
few labels. Otherwise the given labels are used and the quality statement says they are not adjudicated (any
data_status). Each key may appear once in the set used. Criterion labels whose rubric_version differs from the run's
version of that action are dropped and counted (n_rubric_version_mismatch); a label for an action the run has no
rubric version for is kept.

report.csv has one row per mode with the columns REPORT_CSV_FIELDS:
mode, data_status, n_candidates, n_included, n_excluded_lt_10_labeled, n_excluded_unlabeled_in_top,
n_excluded_labels_not_adjudicated, n_ndcg_undefined, n_paired, precision_at_5_paired, ndcg_at_10_paired,
n_excluded_no_relevant_criteria, criterion_coverage_mean,
unresolved_requirements_rate_mean, questions_mean, questions_to_coverage_mean, n_reached, total_s_mean,
llm_wait_s_mean, excluding_llm_s_mean, llm_errors, ungraded_answers, fallback_questions, n_ungraded_runs, mae,
mae_n_compared, mae_n_evaluator_unknown, mae_n_expert_unknown, mae_n_missing_expert, mae_n_evaluator_missing,
mae_n_rubric_version_mismatch, answer_sources (";"-joined), config (JSON). Empty cell = None (not computed /
undefined), never 0.

Error counters per mode (sums over runs): llm_errors = llm_exceptions + evaluator_rejections (provider exceptions and
evaluator outputs rejected by validation). ungraded_answers and fallback_questions are reported apart: one provider
exception also produces an ungraded answer, and a run without a model (n_ungraded_runs: interview runs whose
model_info.provider is None) has every answer ungraded and every question from the bank without any LLM error.
Runs without a model say nothing about assessment quality.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from backend.experiments.expert_labels import (DataStatus, ExpertCriterionLabel, ExpertRelevanceLabel, LabelError,
                                               ReviewStatus, relevance_map, validate_label_set)
from backend.experiments.metrics import (MaeResult, MissingLabelsError, coverage_curve, evaluator_mae,
                                         interview_duration, ndcg_at_k, precision_at_k, questions_to_coverage,
                                         unresolved_requirements_rate)

if TYPE_CHECKING:
    from backend.experiments.store import ExperimentRecord

NO_EXPERT_LABELS = "NO_EXPERT_LABELS"
LLM_ERROR_KEYS = ("llm_exceptions", "evaluator_rejections")
SEPARATE_COUNTERS = ("ungraded_answers", "fallback_questions")
_ABLATIONS = (("adaptive_topics", "topics"), ("adaptive_followup", "followup"), ("adaptive_difficulty", "difficulty"))
_BASE_ORDER = ("INITIAL_PROFILE", "STATIC_INTERVIEW", "ADAPTIVE_INTERVIEW")
_MAE_FIELDS = ("mae", "n_compared", "n_evaluator_unknown", "n_expert_unknown", "n_missing_expert",
               "n_evaluator_missing")
REPORT_CSV_FIELDS = [
    "mode", "data_status", "n_candidates", "n_included", "n_excluded_lt_10_labeled", "n_excluded_unlabeled_in_top",
    "n_excluded_labels_not_adjudicated", "n_ndcg_undefined", "n_paired", "precision_at_5_paired", "ndcg_at_10_paired",
    "n_excluded_no_relevant_criteria", "criterion_coverage_mean",
    "unresolved_requirements_rate_mean", "questions_mean", "questions_to_coverage_mean", "n_reached",
    "total_s_mean", "llm_wait_s_mean", "excluding_llm_s_mean", "llm_errors", "ungraded_answers",
    "fallback_questions", "n_ungraded_runs", "mae", "mae_n_compared", "mae_n_evaluator_unknown",
    "mae_n_expert_unknown", "mae_n_missing_expert", "mae_n_evaluator_missing", "mae_n_rubric_version_mismatch",
    "answer_sources", "config"]
CHART_KEYS = ("ranking_by_mode", "coverage_vs_questions", "questions_static_vs_adaptive",
              "evaluator_quality_by_criterion")


@dataclass(frozen=True)
class ReportInputs:
    records: Sequence[ExperimentRecord]
    relevance: Sequence[ExpertRelevanceLabel] | None = None
    criteria: Sequence[ExpertCriterionLabel] | None = None
    coverage_threshold: float = 0.8
    min_labeled_vacancies: int = 10


def mode_key(record: ExperimentRecord) -> str:
    if record.mode != "ADAPTIVE_INTERVIEW":
        return record.mode
    off = [suffix for flag, suffix in _ABLATIONS if record.config.get(flag, True) is False]
    return "-".join([record.mode, *off])


def _order(key: str) -> tuple:
    base = key.split("-", 1)[0]
    return (_BASE_ORDER.index(base) if base in _BASE_ORDER else len(_BASE_ORDER), key != base, key)


def _mean(xs: Sequence[float | None]) -> float | None:
    vals = [x for x in xs if x is not None]
    return sum(vals) / len(vals) if vals else None


def _used_labels(labels: Sequence | None, kind: str) -> tuple[list, bool | None, list]:
    """(labels used, adjudicated?, ignored non-adjudicated labels). adjudicated is None without labels."""
    if not labels:
        return [], None, []
    validate_label_set(labels)
    adj = [lb for lb in labels if lb.review_status is ReviewStatus.ADJUDICATED]
    used = adj or list(labels)
    dup = sorted(k for k, n in Counter(lb.key() for lb in used).items() if n > 1)
    if dup:
        raise LabelError([f"{kind}: {len(dup)} key(s) labelled more than once in the set used, e.g. {dup[0]}; "
                          "pass one final (adjudicated) label per key"])
    return used, bool(adj), [lb for lb in labels if lb.review_status is not ReviewStatus.ADJUDICATED] if adj else []


def _ranking(rec: ExperimentRecord, labels: dict[str, int] | None, min_labeled: int, ignored_only: set[str]) -> dict:
    out: dict[str, Any] = {"precision_at_5": None, "ndcg_at_10": None, "n_labeled": None, "unlabeled_in_top": []}
    if labels is None:
        return {**out, "ranking_status": "NO_LABELS"}
    if not labels and rec.candidate_id in ignored_only:
        return {**out, "n_labeled": 0, "ranking_status": "LABELS_NOT_ADJUDICATED"}
    ranked = [i["vacancy_id"] for i in rec.ranking]
    in_cohort = set(ranked)
    own = {v: g for v, g in labels.items() if v in in_cohort}
    out["n_labeled"] = len(own)
    if len(own) < min_labeled:
        return {**out, "ranking_status": "LT_MIN_LABELED"}
    try:
        p5 = precision_at_k(ranked, own, k=5, unlabeled="error")
        ndcg = ndcg_at_k(ranked, own, k=10, unlabeled="error")
    except MissingLabelsError:
        return {**out, "ranking_status": "UNLABELED_IN_TOP",
                "unlabeled_in_top": sorted(v for v in ranked[:10] if v not in own)}
    return {**out, "ranking_status": "INCLUDED", "precision_at_5": p5, "ndcg_at_10": ndcg}


def _expert_map(rec: ExperimentRecord, crit: Sequence[ExpertCriterionLabel]) -> tuple[dict, int]:
    """Expert scores for this candidate; labels for another rubric version than the run used are dropped and counted."""
    expert, mismatch = {}, 0
    for lb in crit:
        if lb.candidate_id != rec.candidate_id:
            continue
        version = rec.rubric_versions.get(lb.action_id)
        if version is not None and version != lb.rubric_version:
            mismatch += 1
            continue
        expert[(lb.action_id, lb.criterion_id)] = lb.expert_score
    return expert, mismatch


def _pool(results: Sequence[MaeResult]) -> dict:
    n = sum(r.n_compared for r in results)
    total = sum(r.mae * r.n_compared for r in results if r.mae is not None)
    return {"mae": total / n if n else None, "n_compared": n,
            **{f: sum(getattr(r, f) for r in results) for f in _MAE_FIELDS[2:]}}


def _candidate(rec: ExperimentRecord, labels: dict | None, inp: ReportInputs, ignored_only: set[str]) -> dict:
    rel = list(rec.relevant_criteria or [])
    curve = coverage_curve(rec.qa, rel) if rel else None
    coverage = None if curve is None else (curve[-1] if curve else 0.0)
    dur = interview_duration(rec.timings)
    return {"candidate_id": rec.candidate_id, **_ranking(rec, labels, inp.min_labeled_vacancies, ignored_only),
            "criterion_coverage": coverage, "coverage_curve": curve,
            "questions_to_coverage": None if curve is None else questions_to_coverage(curve, inp.coverage_threshold),
            "n_questions": len(rec.qa), "unresolved_requirements_rate": unresolved_requirements_rate(rec.ranking),
            **dur, "llm_errors": sum(int(rec.errors.get(k) or 0) for k in LLM_ERROR_KEYS),
            **{k: int(rec.errors.get(k) or 0) for k in SEPARATE_COUNTERS},
            "ungraded_run": rec.mode != "INITIAL_PROFILE" and (rec.model_info or {}).get("provider") is None,
            "answer_source": rec.answer_source}


def _mode(recs: list[ExperimentRecord], rel: list | None, crit: list | None, inp: ReportInputs,
          ignored_only: set[str]) -> dict:
    rows = [_candidate(r, None if rel is None else relevance_map(rel, r.candidate_id), inp, ignored_only)
            for r in recs]
    included = [c for c in rows if c["ranking_status"] == "INCLUDED"]
    covered = [c for c in rows if c["criterion_coverage"] is not None]
    reached = [c["questions_to_coverage"] for c in covered if c["questions_to_coverage"] is not None]
    status = Counter(c["ranking_status"] for c in rows)
    mode = {
        "n_candidates": len(rows), "n_included": len(included),
        "n_excluded_lt_10_labeled": status["LT_MIN_LABELED"], "n_excluded_unlabeled_in_top": status["UNLABELED_IN_TOP"],
        "n_excluded_labels_not_adjudicated": status["LABELS_NOT_ADJUDICATED"],
        "n_ndcg_undefined": sum(1 for c in included if c["ndcg_at_10"] is None),
        "precision_at_5": _mean([c["precision_at_5"] for c in included]),
        "ndcg_at_10": _mean([c["ndcg_at_10"] for c in included]),
        "n_excluded_no_relevant_criteria": len(rows) - len(covered),
        "criterion_coverage_mean": _mean([c["criterion_coverage"] for c in covered]),
        "unresolved_requirements_rate_mean": _mean([c["unresolved_requirements_rate"] for c in rows]),
        "questions_mean": _mean([c["n_questions"] for c in rows]),
        "questions_to_coverage_mean": _mean(reached), "n_reached": len(reached),
        "duration": {f"{k}_mean": _mean([c[k] for c in rows]) for k in ("total_s", "llm_wait_s", "excluding_llm_s")},
        "llm_errors": sum(c["llm_errors"] for c in rows),
        **{k: sum(c[k] for c in rows) for k in SEPARATE_COUNTERS},
        "n_ungraded_runs": sum(c["ungraded_run"] for c in rows),
        "answer_sources": sorted({r.answer_source for r in recs}),
        "config": recs[0].config, "evaluator_mae": None, "evaluator_mae_by_criterion": None, "candidates": rows}
    if crit is not None:
        overall, per_crit, mismatch = [], defaultdict(list), 0
        for r in recs:
            expert, miss = _expert_map(r, crit)
            mismatch += miss
            overall.append(evaluator_mae(r.assessments, expert))
            for cid in sorted({a["criterion_id"] for a in r.assessments}):
                per_crit[cid].append(evaluator_mae([a for a in r.assessments if a["criterion_id"] == cid], expert))
        mode["evaluator_mae"] = {**_pool(overall), "n_rubric_version_mismatch": mismatch}
        mode["evaluator_mae_by_criterion"] = [{"criterion_id": c, "mae": p["mae"], "n_compared": p["n_compared"]}
                                              for c, p in ((c, _pool(rs)) for c, rs in sorted(per_crit.items()))]
    return mode


def _statement(status: str, adjudicated: dict, ignored: dict, sources: list[str], modes: dict) -> str:
    """ignored: kind -> list of ignored non-adjudicated labels."""
    parts = []
    if status == NO_EXPERT_LABELS:
        parts.append("No expert labels were supplied: ranking metrics and evaluator MAE are not computed, "
                     "so method quality is not established.")
    elif status == DataStatus.SYNTHETIC_TEST_DATA.value:
        parts.append("Labels are SYNTHETIC_TEST_DATA (test fixtures, not expert annotations): label-based metrics "
                     "only check the pipeline, so method quality is not established.")
    else:
        parts.append("Label-based metrics use EXPERT labels.")
    for kind, adj in adjudicated.items():
        if adj is False:
            parts.append(f"The {kind} labels are not adjudicated (single-annotator, PENDING/REVIEWED); "
                         f"{kind} results are preliminary.")
        if adj is None:
            parts.append(f"No {kind} labels were supplied; the corresponding metrics are not computed.")
        if ignored[kind]:
            cands = sorted({lb.candidate_id for lb in ignored[kind]})
            parts.append(f"{len(ignored[kind])} non-adjudicated {kind} label(s) for candidate(s) {', '.join(cands)} "
                         "were ignored because other labels are adjudicated.")
    parts.append(f"Answer sources: {', '.join(sources) or 'none'}.")
    if {"SCRIPTED", "SIMULATED"} & set(sources):
        parts.append("Scripted or simulated answers are pipeline checks, not evidence of real-candidate performance.")
    if "HUMAN" in sources:
        parts.append("LLM evaluator grades assess the supplied answers only, not verified employment history.")
    if "UNKNOWN" in sources:
        parts.append("Some runs have answer provenance unknown; not evidence of real-candidate performance.")
    ungraded = sum(m["n_ungraded_runs"] for m in modes.values())
    if ungraded:
        parts.append(f"{ungraded} interview run(s) had no model: their answers are ungraded, so their coverage "
                     "reflects no evaluation, not missed criteria, and they say nothing about assessment quality.")
    sums = Counter()
    for m in modes.values():
        for k in ("n_excluded_lt_10_labeled", "n_excluded_unlabeled_in_top", "n_excluded_labels_not_adjudicated",
                  "n_ndcg_undefined",
                  "n_excluded_no_relevant_criteria"):
            sums[k] += m[k]
    if sums["n_excluded_lt_10_labeled"] or sums["n_excluded_unlabeled_in_top"]:
        parts.append(f"Ranking metrics exclude {sums['n_excluded_lt_10_labeled']} candidate run(s) with too few "
                     f"labelled vacancies and {sums['n_excluded_unlabeled_in_top']} with unlabelled vacancies in the "
                     "top 10.")
    if sums["n_excluded_labels_not_adjudicated"]:
        parts.append(f"Ranking metrics exclude {sums['n_excluded_labels_not_adjudicated']} candidate run(s) whose "
                     "relevance labels are all non-adjudicated.")
    if adjudicated["relevance"] is not None and any(m["n_paired"] != m["n_included"] for m in modes.values()):
        parts.append("Per-mode means cover different candidate subsets; compare the paired values "
                     f"({next(iter(modes.values()))['n_paired']} candidate(s) included in every mode).")
    mismatch = sum((m["evaluator_mae"] or {}).get("n_rubric_version_mismatch", 0) for m in modes.values())
    if mismatch:
        parts.append(f"Evaluator MAE ignores {mismatch} expert criterion label(s) written for a different rubric "
                     "version than the run used.")
    if sums["n_ndcg_undefined"]:
        parts.append(f"NDCG@10 is undefined for {sums['n_ndcg_undefined']} run(s) whose labels are all zero "
                     "(P@5 still counted).")
    if sums["n_excluded_no_relevant_criteria"]:
        parts.append(f"Coverage metrics exclude {sums['n_excluded_no_relevant_criteria']} run(s) without "
                     "relevant_criteria (empty cohort or records exported before that field existed).")
    return " ".join(parts)


def _check_record(n: int, r: ExperimentRecord) -> None:
    """Structural check of the fields the report reads; malformed exported records raise ValueError."""
    problems = []
    if not isinstance(r.config, dict):
        problems.append("config must be an object")
    for name in ("qa", "assessments", "ranking", "relevant_criteria"):
        if not isinstance(getattr(r, name), list) or not all(
                isinstance(x, str if name == "relevant_criteria" else dict) for x in getattr(r, name)):
            problems.append(f"{name} must be a list of {'strings' if name == 'relevant_criteria' else 'objects'}")
    if isinstance(r.ranking, list) and not all(isinstance(i, dict) and isinstance(i.get("vacancy_id"), str)
                                               for i in r.ranking):
        problems.append("every ranking item needs a string vacancy_id")
    if not isinstance(r.timings, dict) or not isinstance(r.errors, dict):
        problems.append("timings and errors must be objects")
    if problems:
        raise ValueError(f"record {n} ({r.candidate_id!r}, {r.mode!r}): {'; '.join(problems)}")


def build_report(inp: ReportInputs) -> dict:
    if not 0 < inp.coverage_threshold <= 1:
        raise ValueError("coverage_threshold must be in (0, 1]")
    if inp.min_labeled_vacancies < 1:
        raise ValueError("min_labeled_vacancies must be >= 1")
    rel, rel_adj, rel_ign = _used_labels(inp.relevance, "relevance")
    crit, crit_adj, crit_ign = _used_labels(inp.criteria, "criterion")
    statuses = {lb.data_status for lb in [*rel, *crit]}
    if len(statuses) > 1:
        raise LabelError(["mixed data_status (SYNTHETIC_TEST_DATA and EXPERT) across label files in one report"])
    status = statuses.pop().value if statuses else NO_EXPERT_LABELS
    for n, r in enumerate(inp.records):
        _check_record(n, r)
    groups: dict[str, list] = defaultdict(list)
    for r in inp.records:
        groups[mode_key(r)].append(r)
    for key, recs in groups.items():
        dup = sorted(c for c, n in Counter(r.candidate_id for r in recs).items() if n > 1)
        if dup:
            raise ValueError(f"mode {key}: candidate(s) {dup} appear more than once")
        diff = sorted({f for r in recs for f in set(r.config) | set(recs[0].config)
                       if r.config.get(f) != recs[0].config.get(f)})
        if diff:
            raise ValueError(f"mode {key}: records with different configs cannot be averaged together "
                             f"(differing fields: {diff})")
    used_rel = {lb.candidate_id for lb in rel}
    ignored_only = {lb.candidate_id for lb in rel_ign} - used_rel
    modes = {k: _mode(groups[k], rel if inp.relevance else None, crit if inp.criteria else None, inp, ignored_only)
             for k in sorted(groups, key=_order)}
    paired = set.intersection(*({c["candidate_id"] for c in m["candidates"] if c["ranking_status"] == "INCLUDED"}
                                for m in modes.values())) if modes else set()
    for m in modes.values():
        rows = [c for c in m["candidates"] if c["candidate_id"] in paired]
        m.update({"n_paired": len(rows), "precision_at_5_paired": _mean([c["precision_at_5"] for c in rows]),
                  "ndcg_at_10_paired": _mean([c["ndcg_at_10"] for c in rows])})
    present = defaultdict(set)
    for k, recs in groups.items():
        for r in recs:
            present[r.candidate_id].add(k)
    excluded = {
        "labels_not_adjudicated": {k: [c["candidate_id"] for c in m["candidates"]
                                       if c["ranking_status"] == "LABELS_NOT_ADJUDICATED"] for k, m in modes.items()},
        "lt_min_labeled": {k: [c["candidate_id"] for c in m["candidates"] if c["ranking_status"] == "LT_MIN_LABELED"]
                           for k, m in modes.items()},
        "unlabeled_in_top": {k: {c["candidate_id"]: c["unlabeled_in_top"] for c in m["candidates"]
                                 if c["ranking_status"] == "UNLABELED_IN_TOP"} for k, m in modes.items()},
        "ndcg_undefined": {k: [c["candidate_id"] for c in m["candidates"]
                               if c["ranking_status"] == "INCLUDED" and c["ndcg_at_10"] is None]
                           for k, m in modes.items()},
        "no_relevant_criteria": {k: [c["candidate_id"] for c in m["candidates"] if c["criterion_coverage"] is None]
                                 for k, m in modes.items()},
        "missing_in_modes": {c: sorted(set(modes) - ks, key=_order) for c, ks in sorted(present.items())
                             if set(modes) - ks},
    }
    sources = sorted({r.answer_source for r in inp.records})
    return {"data_status": status,
            "quality_statement": _statement(status, {"relevance": rel_adj, "criterion": crit_adj},
                                            {"relevance": rel_ign, "criterion": crit_ign}, sources, modes),
            "answer_sources": sources, "experiment_ids": sorted({r.experiment_id for r in inp.records}),
            "coverage_threshold": inp.coverage_threshold, "min_labeled_vacancies": inp.min_labeled_vacancies,
            "labels": {kind: {"n_used": len(used), "adjudicated": adj, "n_ignored": len(ign),
                              "candidates_labels_ignored": sorted({lb.candidate_id for lb in ign})}
                       for kind, used, adj, ign in (("relevance", rel, rel_adj, rel_ign),
                                                    ("criterion", crit, crit_adj, crit_ign))},
            "modes": modes, "excluded_candidates": excluded}


def _coverage_points(cands: list[dict]) -> list[dict]:
    """Mean coverage after n questions; a finished interview keeps its final value; n = 0 is 0.0 by definition."""
    curves = [c["coverage_curve"] for c in cands if c["coverage_curve"] is not None]
    if not curves:
        return []
    length = max(len(c) for c in curves)
    return [{"n_questions": n, "n_candidates": len(curves),
             "coverage_mean": sum(c[min(n, len(c)) - 1] if n and c else 0.0 for c in curves) / len(curves)}
            for n in range(length + 1)]


def chart_data(report: dict) -> dict:
    """Four datasets, each {"data_status", "data"}. ranking_by_mode carries the PAIRED means (candidates included
    in every mode) under precision_at_5 / ndcg_at_10, with n_paired and n_included. questions_static_vs_adaptive
    pairs candidates present in both
    STATIC_INTERVIEW and ADAPTIVE_INTERVIEW: static/adaptive = questions to reach the coverage threshold (None if
    not reached or no relevant criteria), *_asked = questions shown."""
    st, modes = report["data_status"], report["modes"]
    by_cand = {k: {c["candidate_id"]: c for c in modes[k]["candidates"]} if k in modes else {}
               for k in ("STATIC_INTERVIEW", "ADAPTIVE_INTERVIEW")}
    s, a = by_cand["STATIC_INTERVIEW"], by_cand["ADAPTIVE_INTERVIEW"]
    data = {
        "ranking_by_mode": [{"mode": k, "precision_at_5": m["precision_at_5_paired"],
                             "ndcg_at_10": m["ndcg_at_10_paired"], "n_paired": m["n_paired"],
                             "n_included": m["n_included"]} for k, m in modes.items()],
        "coverage_vs_questions": {k: _coverage_points(m["candidates"]) for k, m in modes.items()},
        "questions_static_vs_adaptive": [
            {"candidate_id": c, "static": s[c]["questions_to_coverage"], "adaptive": a[c]["questions_to_coverage"],
             "static_asked": s[c]["n_questions"], "adaptive_asked": a[c]["n_questions"]} for c in sorted(set(s) & set(a))],
        "evaluator_quality_by_criterion": [{"mode": k, **row} for k, m in modes.items()
                                           for row in m["evaluator_mae_by_criterion"] or []],
    }
    return {k: {"data_status": st, "data": data[k]} for k in CHART_KEYS}


def _csv_row(key: str, m: dict, status: str) -> dict:
    mae = m["evaluator_mae"] or {}
    return {"mode": key, "data_status": status,
            **{f: m[f] for f in REPORT_CSV_FIELDS[2:REPORT_CSV_FIELDS.index("total_s_mean")]},
            **m["duration"], **{k: m[k] for k in ("llm_errors", *SEPARATE_COUNTERS, "n_ungraded_runs")},
            "mae": mae.get("mae"),
            **{f"mae_{f}": mae.get(f) for f in (*_MAE_FIELDS[1:], "n_rubric_version_mismatch")},
            "answer_sources": ";".join(m["answer_sources"]), "config": json.dumps(m["config"], sort_keys=True)}


def write_report(report: dict, charts: dict, out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, obj in (("report.json", report), ("charts.json", charts)):
        (out_dir / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(out_dir / "report.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(_csv_row(k, m, report["data_status"]) for k, m in report["modes"].items())

