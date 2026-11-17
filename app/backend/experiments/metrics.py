"""Ranking, coverage and evaluator-error metrics. Pure stdlib: no I/O, no DB."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal


class MissingLabelsError(ValueError):
    """Top-k contains vacancy ids without an expert label."""


def _check_labels(labels: Mapping[str, int]) -> None:
    for vid, g in labels.items():
        if isinstance(g, bool) or not isinstance(g, int) or not 0 <= g <= 3:
            raise ValueError(f"label grade for {vid!r} must be int 0..3, got {g!r}")


def _top_k(ranked_ids: Sequence[str], labels: Mapping[str, int], k: int, unlabeled: str) -> list[str]:
    if k < 1:
        raise ValueError("k must be >= 1")
    if unlabeled not in ("error", "skip"):
        raise ValueError("unlabeled must be 'error' or 'skip'")
    if len(set(ranked_ids)) != len(ranked_ids):
        raise ValueError("duplicate vacancy ids in ranked_ids")
    _check_labels(labels)
    if unlabeled == "skip":  # pooling bias: unlabelled vacancies silently dropped before top k
        return [v for v in ranked_ids if v in labels][:k]
    top = list(ranked_ids[:k])
    missing = sorted(v for v in top if v not in labels)
    if missing:
        raise MissingLabelsError(f"unlabeled vacancies in top {k}: {missing}")
    return top


def precision_at_k(
    ranked_ids: Sequence[str],
    labels: Mapping[str, int],
    k: int = 5,
    rel_min: int = 2,
    unlabeled: Literal["error", "skip"] = "error",
) -> float:
    """Relevant (grade >= rel_min) in top k / k.

    Denominator is always k: fewer than k ranked ids means missing slots count
    as non-relevant. Unlabelled top-k id: MissingLabelsError ("error") or dropped
    before taking top k ("skip", pooling bias). Duplicates / bad grades: ValueError.
    """
    top = _top_k(ranked_ids, labels, k, unlabeled)
    return sum(1 for v in top if labels[v] >= rel_min) / k


def ndcg_at_k(
    ranked_ids: Sequence[str],
    labels: Mapping[str, int],
    k: int = 10,
    gain: Literal["linear", "exp"] = "linear",
    unlabeled: Literal["error", "skip"] = "error",
) -> float | None:
    """DCG@k / ideal DCG@k. gain linear = rel, exp = 2^rel - 1.

    Ideal ranking = all labelled vacancies of the candidate sorted desc, top k.
    Ideal DCG 0 (all-zero labels) -> None. Unlabelled handling as in precision_at_k.
    """
    if gain not in ("linear", "exp"):
        raise ValueError("gain must be 'linear' or 'exp'")
    top = _top_k(ranked_ids, labels, k, unlabeled)
    g = (lambda r: r) if gain == "linear" else (lambda r: 2**r - 1)

    def dcg(rels: Iterable[int]) -> float:
        return sum(g(r) / math.log2(i + 2) for i, r in enumerate(rels))

    ideal = dcg(sorted(labels.values(), reverse=True)[:k])
    if ideal == 0:
        return None
    return dcg(labels[v] for v in top) / ideal


def criterion_coverage(sufficient_ids: Iterable[str], relevant_criteria: Sequence[str]) -> float | None:
    """|sufficient ∩ relevant| / |relevant|; ids outside relevant ignored; None if relevant empty."""
    relevant = set(relevant_criteria)
    if not relevant:
        return None
    return len(relevant & set(sufficient_ids)) / len(relevant)


def unresolved_requirements_rate(ranking_items: Sequence[Mapping[str, Any]]) -> float | None:
    """Sum unknown_count / sum groups_total over items with groups_total > 0; None if no such item.

    Counts must be non-negative ints with unknown_count <= groups_total, else ValueError.
    """
    for i in ranking_items:
        u, t = i.get("unknown_count"), i.get("groups_total")
        if any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in (u, t)) or u > t:
            raise ValueError(f"invalid unknown_count/groups_total: {u!r}/{t!r}")
    items = [i for i in ranking_items if i["groups_total"] > 0]
    if not items:
        return None
    return sum(i["unknown_count"] for i in items) / sum(i["groups_total"] for i in items)


def coverage_curve(qa: Sequence[Mapping[str, Any]], relevant_criteria: Sequence[str]) -> list[float]:
    """Coverage after each qa entry, in order, from qa[i]["sufficient_criteria_after"].

    Empty relevant set -> [] (coverage undefined, never 0). Callers must exclude candidates
    whose criterion_coverage is None from coverage means and n_reached, and report the count.
    """
    if not relevant_criteria:
        return []
    return [criterion_coverage(q.get("sufficient_criteria_after", []), relevant_criteria) for q in qa]


def questions_to_coverage(curve: Sequence[float], threshold: float) -> int | None:
    """1-based index of first curve value >= threshold; None if never reached."""
    for i, c in enumerate(curve, 1):
        if c >= threshold:
            return i
    return None


def interview_duration(timings: Mapping[str, float]) -> dict[str, float]:
    """{"total_s","llm_wait_s","excluding_llm_s"}; missing keys count 0; excluding clamped at 0.

    Negative, non-finite or non-numeric timings raise ValueError.
    """
    total, llm = (_unit(timings.get(k, 0.0), "timing", 0.0, math.inf) for k in ("total_s", "llm_wait_s"))
    return {"total_s": total, "llm_wait_s": llm, "excluding_llm_s": max(total - llm, 0.0)}


def _unit(x: Any, what: str, lo: float = 0.0, hi: float = 1.0) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not lo <= x <= hi:
        raise ValueError(f"{what} must be a finite number in [{lo}, {hi}], got {x!r}")
    return float(x)


@dataclass(frozen=True)
class MaeResult:
    mae: float | None
    n_compared: int
    n_evaluator_unknown: int
    n_expert_unknown: int
    n_missing_expert: int  # evaluator criteria with no expert row at all
    n_evaluator_missing: int = 0  # expert-labelled (action, criterion) keys with no evaluator row at all


def evaluator_mae(
    assessments: Sequence[Mapping[str, Any]],
    expert: Mapping[tuple[str, str], float | None],
) -> MaeResult:
    """MAE over (action_id, criterion_id) pairs where evaluator and expert are both non-null.

    Evaluator score None -> n_evaluator_unknown (checked first). Otherwise no expert key ->
    n_missing_expert; expert None -> n_expert_unknown. None is never treated as 0.
    Expert keys matched by no assessment row -> n_evaluator_missing.
    mae is None when no pair is compared. Scores must be finite floats in [0,1]
    (bool/NaN/out-of-range, evaluator or expert) -> ValueError.
    """
    errs: list[float] = []
    ev_unk = ex_unk = missing = 0
    seen = {(a["action_id"], a["criterion_id"]) for a in assessments}
    for a in assessments:
        score = a.get("score")
        if score is not None:
            score = _unit(score, "evaluator score")
        if score is None:
            ev_unk += 1
            continue
        key = (a["action_id"], a["criterion_id"])
        if expert.get(key) is not None:
            _unit(expert[key], "expert score")
        if key not in expert:
            missing += 1
        elif expert[key] is None:
            ex_unk += 1
        else:
            errs.append(abs(score - expert[key]))
    mae = sum(errs) / len(errs) if errs else None
    return MaeResult(mae, len(errs), ev_unk, ex_unk, missing, sum(1 for k in expert if k not in seen))
