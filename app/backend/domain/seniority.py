"""Deterministic SeniorityEstimator (§3e). Pure: no DB, no LLM, no IO, no clock, no randomness.

Inputs are only the level policy and per-criterion evidence. Desired level, years, title, self-ratings and
vacancy fit are deliberately not parameters. Unknown (score None) is never treated as 0 or as a gap.
"""
from __future__ import annotations

import math
import dataclasses
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from statistics import median
from typing import Literal

from backend.domain.criteria import epsilon
from backend.domain.seniority_policy import (PRACTICE_ACTION, CriterionPool, Level, LevelRule, SeniorityPolicy,
                                             rank)

LevelName = Literal["JUNIOR", "MIDDLE", "SENIOR", "UNKNOWN"]
LevelStatus = Literal["SUPPORTED", "GAP", "UNVERIFIED"]
# NO_EXPERIENCE: capability rules (v4) only; decided like UNRESOLVED (no credit, no gap), shown separately.
PoolStatus = Literal["CONFIRMED", "GAP", "UNRESOLVED", "UNASSESSED", "NO_EXPERIENCE"]
AssessmentStatus = Literal["ASSESSED", "INSUFFICIENT_DATA", "GAPS_AT_JUNIOR", "POLICY_UNAVAILABLE"]

NO_POLICY_TEXT = "Для цього напряму рівень не визначається: потрібна експертна валідація рубрик"
_TITLE = {"JUNIOR": "Junior", "MIDDLE": "Middle", "SENIOR": "Senior"}


@dataclass(frozen=True)
class CriterionEvidence:
    criterion_id: str
    score: float | None
    evidence_turns: tuple[str, ...] = ()
    declined: bool = False  # topic criterion: validated Evaluator flag no_experience on the effective revision
    topic_scores: tuple[float, ...] = ()  # practice criterion: traced score per source topic, descending (v4 uses it)


@dataclass(frozen=True)
class PoolCoverage:
    pool_id: str
    title: str
    status: PoolStatus
    members: tuple[str, ...]
    confirmed_ids: tuple[str, ...]
    gap_ids: tuple[str, ...]
    unassessed_ids: tuple[str, ...]
    no_experience_ids: tuple[str, ...] | None = None  # capability rules only (None: not part of v2/v3 JSON)


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
    pools: tuple[PoolCoverage, ...] = ()  # pooled policies only; counts above are then over pools
    # Capability rules (v4) only; None keeps v1-v3 JSON byte-identical.
    technical_confirmed: int | None = None
    practice_confirmed: int | None = None
    tolerated_gap_ids: tuple[str, ...] | None = None  # gaps of GAP pools that do not block the level
    no_experience_ids: tuple[str, ...] | None = None
    hard_gap_ids: tuple[str, ...] | None = None  # gaps of GAP pools listed in the rule's hard_pools


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
    if rule.capability:
        return _capability_coverage(rule, evidence)
    if rule.pools:
        return _pooled_coverage(rule, evidence)
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
        elif item.score < rule.tau - epsilon(rule.tau) and item.evidence_turns:  # untraceable low score: unresolved
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


def _pool(pool: CriterionPool, tau: float, evidence: Mapping[str, CriterionEvidence]) -> PoolCoverage:
    """CONFIRMED: some member s >= tau with an evidence turn. GAP: none confirms, at least one member is an established
    gap (s < tau - eps with a turn) and no member is assessed-but-unresolved (borderline or untraced). UNRESOLVED:
    assessed otherwise. UNASSESSED: no member scored. Unscored members never block a gap nor count as one."""
    confirmed, gaps, unresolved, unassessed = [], [], [], []
    for cid in pool.members:
        item = _score(evidence, cid)
        if item is None:
            unassessed.append(cid)
        elif item.score >= tau and item.evidence_turns:
            confirmed.append(cid)
        elif item.score < tau - epsilon(tau) and item.evidence_turns:
            gaps.append(cid)
        else:
            unresolved.append(cid)
    status: PoolStatus = ("CONFIRMED" if confirmed else "GAP" if gaps and not unresolved else
                          "UNRESOLVED" if gaps or unresolved else "UNASSESSED")
    return PoolCoverage(pool.pool_id, pool.title, status, pool.members, tuple(confirmed),
                        tuple(gaps) if status == "GAP" else (), tuple(unassessed) if status == "UNASSESSED" else ())


def _pooled_coverage(rule: LevelRule, evidence: Mapping[str, CriterionEvidence]) -> LevelCoverage:
    """Counts over pools (no compensation across pools). `unassessed_ids` lists members of wholly unassessed pools only:
    an unscored alternative inside an assessed pool is not missing evidence for the level."""
    pools = tuple(_pool(p, rule.tau, evidence) for p in rule.pools)
    total = len(pools)
    assessed = sum(p.status != "UNASSESSED" for p in pools)
    confirmed = sum(p.status == "CONFIRMED" for p in pools)
    gaps = sum(p.status == "GAP" for p in pools)
    confirmed_ids = _unique([c for p in pools for c in p.confirmed_ids])
    comps = len({c.split(".", 1)[0] for c in confirmed_ids} - {PRACTICE_ACTION})
    reasons = tuple(code for code, failed in (
        ("CRITICAL_GAP", bool(gaps)),
        ("ASSESSED_COUNT_BELOW_MIN", assessed < (rule.min_assessed or 0)),
        ("CONFIRMED_COUNT_BELOW_MIN", confirmed < (rule.min_confirmed or 0)),
        ("TOO_FEW_COMPETENCIES", comps < rule.min_competencies)) if failed)
    status: LevelStatus = "GAP" if gaps else ("UNVERIFIED" if reasons else "SUPPORTED")
    return LevelCoverage(rule.level, total, assessed, confirmed, gaps, assessed / total, confirmed / total, comps,
                         status, confirmed_ids, _unique([c for p in pools for c in p.gap_ids]),
                         _unique([c for p in pools for c in p.unassessed_ids]), reasons, pools)


def _is_practice(cid: str) -> bool:
    return cid.startswith(f"{PRACTICE_ACTION}.")


def _member(rule: LevelRule, cid: str, evidence: Mapping[str, CriterionEvidence]) -> str:
    """State of one pool member under a capability rule: CONF, WEAK, NOEXP, BORDER or NONE (no score).
    Practice is classified by the median of its per-source-topic scores (D-5: one strong topic no longer outweighs
    weaker ones, as the v1-v3 maximum did); an even count takes the mean of the middle two; a practice score with no
    traced topic is borderline."""
    item = _score(evidence, cid)
    if item is None:
        return "NONE"
    tau, low = rule.tau, rule.gap_below
    if _is_practice(cid):
        if not item.topic_scores:
            return "BORDER"
        s = median(item.topic_scores)
        return "CONF" if s >= tau else "WEAK" if s < low else "BORDER"
    if not item.evidence_turns:
        return "BORDER"  # a score without an evidence turn is never a confirmation nor a gap
    return ("CONF" if item.score >= tau else "NOEXP" if item.declined else "WEAK" if item.score < low
            else "BORDER")


def _capability_pool(rule: LevelRule, pool: CriterionPool, evidence: Mapping[str, CriterionEvidence]) -> PoolCoverage:
    """CONFIRMED: a member confirms. UNRESOLVED: otherwise any borderline/untraced member. GAP: only when every
    alternative of the pool was asked (or the pool has a single member) and each is weak or a no-experience
    declaration. While an alternative is still unasked, a weak try and a declaration are treated alike (audit fix I-1:
    a declaration must never beat trying): NO_EXPERIENCE if every scored member is a declaration, else UNRESOLVED.
    Neither gives credit or a gap. A hard pool (rule.hard_pools) needs no alternative: a weak try or a declaration is a
    GAP at once. UNASSESSED: no member scored."""
    st = {cid: _member(rule, cid, evidence) for cid in pool.members}
    by = {k: tuple(c for c, v in st.items() if v == k) for k in ("CONF", "WEAK", "NOEXP", "BORDER", "NONE")}
    # A hard-critical capability must be shown in the tool that was asked: no waiting for an alternative there.
    all_asked = not by["NONE"] or pool.pool_id in rule.hard_pools
    status: PoolStatus = (
        "CONFIRMED" if by["CONF"] else "UNRESOLVED" if by["BORDER"] else
        ("GAP" if all_asked else "UNRESOLVED" if by["WEAK"] else "NO_EXPERIENCE") if by["WEAK"] or by["NOEXP"] else
        "UNASSESSED")
    return PoolCoverage(pool.pool_id, pool.title, status, pool.members, by["CONF"],
                        by["WEAK"] + by["NOEXP"] if status == "GAP" else (),
                        pool.members if status == "UNASSESSED" else (),
                        by["NOEXP"] if status == "NO_EXPERIENCE" else ())


def _capability_coverage(rule: LevelRule, evidence: Mapping[str, CriterionEvidence]) -> LevelCoverage:
    """Counts over decided pools (CONFIRMED or GAP); no compensation across pools: a pool is confirmed only by its own
    members. A level is GAP when a hard pool is GAP or more than `max_soft_gaps` pools are GAP (the chain-wide budget
    is applied in estimate)."""
    pools = tuple(_capability_pool(rule, p, evidence) for p in rule.pools)
    practice = {p.pool_id for p in rule.pools if all(_is_practice(c) for c in p.members)}
    conf = [p for p in pools if p.status == "CONFIRMED"]
    gap = [p for p in pools if p.status == "GAP"]
    tech = sum(p.pool_id not in practice for p in conf)
    prac = len(conf) - tech
    confirmed_ids = _unique([c for p in conf for c in p.confirmed_ids])
    comps = len({c.split(".", 1)[0] for c in confirmed_ids} - {PRACTICE_ACTION})
    hard = _unique([c for p in gap if p.pool_id in rule.hard_pools for c in p.gap_ids])
    blocking = bool(hard) or len(gap) > rule.max_soft_gaps
    required_ok = not rule.required_any or any(p.pool_id in rule.required_any for p in conf)
    reasons = tuple(code for code, failed in (
        ("CRITICAL_GAP", blocking),
        ("CONFIRMED_COUNT_BELOW_MIN", len(conf) < (rule.min_confirmed or 0)),
        ("TECHNICAL_POOLS_BELOW_MIN", tech < rule.min_technical),
        ("PRACTICE_POOLS_BELOW_MIN", prac < rule.min_practice),
        ("TOO_FEW_COMPETENCIES", comps < rule.min_competencies),
        ("REQUIRED_CAPABILITY_UNCONFIRMED", not required_ok)) if failed)
    status: LevelStatus = "GAP" if blocking else ("UNVERIFIED" if reasons else "SUPPORTED")
    total, decided = len(pools), len(conf) + len(gap)
    gap_ids = _unique([c for p in gap for c in p.gap_ids])
    return LevelCoverage(rule.level, total, decided, len(conf), len(gap), decided / total, len(conf) / total, comps,
                         status, confirmed_ids, gap_ids, _unique([c for p in pools for c in p.unassessed_ids]), reasons,
                         pools, tech, prac, () if blocking else gap_ids,
                         _unique([c for p in pools for c in (p.no_experience_ids or ())]), hard)


def _chain_budget(policy: SeniorityPolicy, cov: list[LevelCoverage]) -> list[LevelCoverage]:
    """Chain-wide soft-gap budget (audit fix I-2): a level is GAP when the distinct GAP pools of it and every lower
    level exceed `policy.max_chain_soft_gaps`, so tolerated gaps never accumulate along Junior -> Middle -> Senior."""
    cap = policy.max_chain_soft_gaps
    if cap is None:
        return cov
    seen: dict[str, None] = {}
    out = []
    for c in cov:
        seen.update(dict.fromkeys(p.pool_id for p in c.pools if p.status == "GAP"))
        if len(seen) > cap and c.status != "GAP":
            c = dataclasses.replace(c, status="GAP", reasons=("CUMULATIVE_GAPS", *c.reasons), tolerated_gap_ids=())
        out.append(c)
    return out


def _unique(ids: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(ids))


def estimate(policy: SeniorityPolicy | None, evidence: Mapping[str, CriterionEvidence]) -> SeniorityResult:
    if policy is None:
        return SeniorityResult("UNKNOWN", "UNKNOWN", "POLICY_UNAVAILABLE", {}, (), (), (), {}, None, None,
                               (NO_POLICY_TEXT,))
    rules = sorted(policy.rules, key=lambda r: rank(r.level))
    cov = _chain_budget(policy, [_coverage(r, evidence) for r in rules])

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
            if cid in evidence and evidence[cid].score is not None and evidence[cid].evidence_turns}

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
    tolerated = _unique([g for c in cov for g in (c.tolerated_gap_ids or ())])
    if tolerated:
        lines.append(f"Окремі прогалини не блокують рівень, але їх варто підтягнути: {', '.join(tolerated)}.")
    no_exp = _unique([d for c in cov for d in (c.no_experience_ids or ())])
    if no_exp:
        lines.append(f"У відповідях зазначено, що досвіду з частиною інструментів немає ({', '.join(no_exp)}); "
                     "альтернативні інструменти не перевірялися, тому ці навички не враховано ні як підтвердження, "
                     "ні як прогалину.")
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
    data["coverage_by_level"] = {k: _coverage_json(c) for k, c in data["coverage_by_level"].items()}
    return data


def _coverage_json(c: dict) -> dict:
    """Per-criterion policies (v1) store exactly the fields they always stored: no `pools` key."""
    out = {f: v.value if isinstance(v, Level) else list(v) if isinstance(v, tuple) else v
           for f, v in c.items() if f != "pools" and not (f in _V4_ONLY and v is None)}
    if c["pools"]:
        out["pools"] = [{f: list(v) if isinstance(v, tuple) else v for f, v in p.items()
                         if not (f in _V4_ONLY and v is None)} for p in c["pools"]]
    return out


# Keys that exist only for capability rules (v4): absent (not null) in v1-v3 JSON, so stored rows stay byte-identical.
_V4_ONLY = frozenset({"technical_confirmed", "practice_confirmed", "tolerated_gap_ids", "no_experience_ids",
                      "hard_gap_ids"})
