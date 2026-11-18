"""Deterministic SeniorityEstimator (§3e). Pure: no DB, no LLM, no IO, no clock, no randomness.

Inputs are only the level policy and per-criterion evidence. Desired level, years, title, self-ratings and
vacancy fit are deliberately not parameters. Unknown (score None) is never treated as 0 or as a gap.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Literal

from backend.domain.criteria import epsilon
from backend.domain.seniority_policy import PRACTICE_ACTION, Level, LevelRule, SeniorityPolicy, rank

LevelName = Literal["JUNIOR", "MIDDLE", "SENIOR", "UNKNOWN"]
LevelStatus = Literal["SUPPORTED", "GAP", "UNVERIFIED"]
AssessmentStatus = Literal["ASSESSED", "INSUFFICIENT_DATA", "GAPS_AT_JUNIOR", "POLICY_UNAVAILABLE"]

NO_POLICY_TEXT = "Для цього напряму рівень не визначається: потрібна експертна валідація рубрик"
_TITLE = {"JUNIOR": "Junior", "MIDDLE": "Middle", "SENIOR": "Senior"}


@dataclass(frozen=True)
class CriterionEvidence:
    criterion_id: str
    score: float | None
    evidence_turns: tuple[str, ...] = ()


@dataclass(frozen=True)
class LevelCoverage:
    level: Level
    critical_total: int
    assessed: int
    confirmed: int
    gaps: int
    assessed_share: float
    confirmed_share: float
    competencies_confirmed: int
    status: LevelStatus
    confirmed_ids: tuple[str, ...]
    gap_ids: tuple[str, ...]
    unassessed_ids: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class SeniorityResult:
    assessed_level: LevelName
    highest_supported_level: LevelName
    assessment_status: AssessmentStatus
    coverage_by_level: dict[str, LevelCoverage]
    confirmed_strengths: tuple[str, ...]
    critical_gaps: tuple[str, ...]
    unassessed_criteria: tuple[str, ...]
    evidence_references: dict[str, tuple[str, ...]]
    policy_id: str | None
    policy_version: str | None
    explanation: tuple[str, ...]


def _score(evidence: Mapping[str, CriterionEvidence], cid: str) -> CriterionEvidence | None:
    item = evidence.get(cid)
    if item is None or item.score is None:
        return None
    if not math.isfinite(item.score) or not 0.0 <= item.score <= 1.0:
        raise ValueError(f"score for {cid} must be in [0,1], got {item.score!r}")
    return item


def _coverage(rule: LevelRule, evidence: Mapping[str, CriterionEvidence]) -> LevelCoverage:
    confirmed: list[str] = []
    gaps: list[str] = []
    unassessed: list[str] = []
    assessed = 0
    for cid in rule.critical:
        item = _score(evidence, cid)
        if item is None:
            unassessed.append(cid)
            continue
        assessed += 1
        if item.score >= rule.tau and item.evidence_turns:  # a confirmation must cite at least one answer
            confirmed.append(cid)
        elif item.score < rule.tau - epsilon(rule.tau):
            gaps.append(cid)
    total = len(rule.critical)
    a_share, c_share = assessed / total, len(confirmed) / total
    comps = len({c.split(".", 1)[0] for c in confirmed} - {PRACTICE_ACTION})
    reasons = tuple(code for code, failed in (
        ("CRITICAL_GAP", bool(gaps)),
        ("ASSESSED_SHARE_BELOW_MIN", a_share < rule.min_assessed_share),
        ("CONFIRMED_SHARE_BELOW_MIN", c_share < rule.min_confirmed_share),
        ("TOO_FEW_COMPETENCIES", comps < rule.min_competencies)) if failed)
    status: LevelStatus = "GAP" if gaps else ("UNVERIFIED" if reasons else "SUPPORTED")
    return LevelCoverage(rule.level, total, assessed, len(confirmed), len(gaps), a_share, c_share, comps,
                         status, tuple(confirmed), tuple(gaps), tuple(unassessed), reasons)


def _unique(ids: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(ids))


def estimate(policy: SeniorityPolicy | None, evidence: Mapping[str, CriterionEvidence]) -> SeniorityResult:
    if policy is None:
        return SeniorityResult("UNKNOWN", "UNKNOWN", "POLICY_UNAVAILABLE", {}, (), (), (), {}, None, None,
                               (NO_POLICY_TEXT,))
    rules = sorted(policy.rules, key=lambda r: rank(r.level))
    cov = [_coverage(r, evidence) for r in rules]

    chain = -1  # index of the highest level in the unbroken SUPPORTED chain from the lowest level
    while chain + 1 < len(cov) and cov[chain + 1].status == "SUPPORTED":
        chain += 1
    supported = [i for i, c in enumerate(cov) if c.status == "SUPPORTED"]
    assessed: LevelName = cov[chain].level.value if chain >= 0 else "UNKNOWN"  # type: ignore[assignment]
    highest: LevelName = cov[supported[-1]].level.value if supported else "UNKNOWN"  # type: ignore[assignment]
    status: AssessmentStatus = ("ASSESSED" if chain >= 0 else
                                "GAPS_AT_JUNIOR" if cov[0].status == "GAP" else "INSUFFICIENT_DATA")

    # Report over levels up to the first one above the assessed level, widened to any level with evidence.
    touched = [i for i, c in enumerate(cov) if c.assessed]
    top = min(len(cov) - 1, max([chain + 1, *touched]))
    scope = cov[:top + 1]
    gaps = _unique([g for c in scope for g in c.gap_ids])
    strengths = tuple(s for s in _unique([s for c in scope for s in c.confirmed_ids]) if s not in gaps)
    unassessed = _unique([u for c in scope for u in c.unassessed_ids])
    refs = {cid: evidence[cid].evidence_turns for cid in _unique([cid for r in rules[:top + 1] for cid in r.critical])
            if cid not in unassessed and evidence[cid].evidence_turns}

    return SeniorityResult(assessed, highest, status, {c.level.value: c for c in cov}, strengths, gaps, unassessed, refs,
                           policy.policy_id, policy.version, _explain(policy, cov, chain, highest))


def _explain(policy: SeniorityPolicy, cov: list[LevelCoverage], chain: int, highest: LevelName) -> tuple[str, ...]:
    lines: list[str] = []
    if chain < 0:
        first = cov[0]
        lines.append(f"Рівень не визначено: для {_TITLE[first.level.value]} виявлено критичні прогалини: "
                     f"{', '.join(first.gap_ids)}." if first.status == "GAP" else
                     f"Рівень не визначено: для висновку про {_TITLE[first.level.value]} недостатньо даних.")
    else:
        line = f"Підтверджено {_TITLE[cov[chain].level.value]} за перевіреними критеріями."
        if chain + 1 < len(cov):
            nxt = cov[chain + 1]
            line += (f" Для {_TITLE[nxt.level.value]} виявлено критичні прогалини: {', '.join(nxt.gap_ids)}."
                     if nxt.status == "GAP" else f" Для висновку про {_TITLE[nxt.level.value]} недостатньо даних.")
        lines.append(line)
    if highest != "UNKNOWN" and (chain < 0 or rank(Level(highest)) > rank(cov[chain].level)):
        lines.append(f"Критерії {_TITLE[highest]} підтверджено, але нижчі рівні не підтверджені, "
                     "тому цей рівень не присвоюється.")
    if policy.status == "WORKING_ASSUMPTION":
        lines.append(f"Політика рівнів {policy.policy_id}/{policy.version} є робочим припущенням "
                     "і потребує експертної валідації.")
    return tuple(lines)


def result_to_json(r: SeniorityResult) -> dict:
    data = asdict(r)
    for key in ("confirmed_strengths", "critical_gaps", "unassessed_criteria", "explanation"):
        data[key] = list(data[key])
    data["evidence_references"] = {k: list(v) for k, v in r.evidence_references.items()}
    data["coverage_by_level"] = {k: {f: v.value if isinstance(v, Level) else list(v) if isinstance(v, tuple) else v
                                     for f, v in c.items()}
                                 for k, c in data["coverage_by_level"].items()}
    return data
