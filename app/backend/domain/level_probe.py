"""Level probe (§3e): within the topic Q_t already chose, put criteria that are critical for the lowest level not yet
SUPPORTED first, and name that level's unassessed practice criteria as a hint for the Interviewer. For a pooled policy
(v2-v4) "critical" means the members of that level's pools that are not CONFIRMED yet.

Pure. It reorders and annotates: membership of `unmet`, topic choice, budgets, caps and difficulty are untouched.
Without a level policy (or without an estimate) the input comes back unchanged and there are no practice gaps.

WP-B (audit D-2, D-6): `continuation_targets` names the topic criteria for which Python (not the LLM) keeps the
current topic open, within the unchanged caps; `probe_order` puts them first; `practice_gaps` also covers the next
level up once the lower level's technical minimum is met, and re-hints borderline practice.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from backend.domain.seniority import SeniorityResult
from backend.domain.seniority_policy import PRACTICE_ACTION, LevelRule, SeniorityPolicy, rank

MAX_ASKS_PER_CRITERION = 2  # a criterion stops keeping its topic open after it was in focus of two questions


def _target(policy: SeniorityPolicy | None, result: SeniorityResult | None) -> LevelRule | None:
    """Rule of the lowest level whose status is not SUPPORTED; None when there is nothing to probe."""
    if policy is None or result is None or not result.coverage_by_level:
        return None
    for rule in sorted(policy.rules, key=lambda r: rank(r.level)):
        cov = result.coverage_by_level.get(rule.level.value)
        if cov is None or cov.status != "SUPPORTED":
            return rule
    return None


def prioritize_unmet(unmet: Sequence[str], policy: SeniorityPolicy | None,
                     result: SeniorityResult | None) -> list[str]:
    """Stable partition: target-level critical criteria first, then the rest, each group in input (rubric) order."""
    rule = _target(policy, result)
    if rule is None:
        return list(unmet)
    critical = set(rule.critical) if not rule.pools else _open_members(rule, result)
    return [c for c in unmet if c in critical] + [c for c in unmet if c not in critical]


def _open_members(rule: LevelRule, result: SeniorityResult | None) -> set[str]:
    """Pooled rule: members of the target level's pools that are not CONFIRMED yet (a confirmed pool needs nothing)."""
    cov = result.coverage_by_level.get(rule.level.value) if result else None
    done = {p.pool_id for p in cov.pools if p.status == "CONFIRMED"} if cov else set()
    return {c for p in rule.pools if p.pool_id not in done for c in p.members}


def _probe_rules(policy: SeniorityPolicy | None, result: SeniorityResult | None) -> list[LevelRule]:
    """Capability rules (v4) probed now: the lowest non-SUPPORTED level L and the next level up. None when L is GAP
    (answers at L are weak: no escalation) or without a capability policy / estimate (v1-v3 attempts and tracks without
    a policy keep the previous flow)."""
    rule = _target(policy, result)
    if rule is None or not rule.capability:
        return []
    cov = result.coverage_by_level.get(rule.level.value)  # type: ignore[union-attr]
    if cov is not None and cov.status == "GAP":
        return []
    ordered = sorted(policy.rules, key=lambda r: rank(r.level))  # type: ignore[union-attr]
    i = ordered.index(rule)
    return ordered[i:i + 2]


def _unresolved(rule: LevelRule, score: float | None) -> bool:
    """Not asked yet (null) or borderline: [gap bound, tau) of the capability rule."""
    return score is None or rule.gap_below <= score < rule.tau  # type: ignore[operator]


def continuation_targets(policy: SeniorityPolicy | None, result: SeniorityResult | None, topic_criteria: Sequence[str],
                         scores: Mapping[str, float | None], asked: Mapping[str, int],
                         max_asks: int = MAX_ASKS_PER_CRITERION) -> list[str]:
    """Topic criteria that keep the topic open (D-2): members of not-yet-decided pools (not CONFIRMED, not GAP, not
    NO_EXPERIENCE) of the probed levels (lowest non-SUPPORTED level first, then the next level up) whose score is null or
    borderline (or, in a replicated pool, confirmed by one answer only: it needs a second confirming answer) and that
    were in focus of fewer than `max_asks` questions of this topic. Pending second confirmations of replicated pools come
    first (they decide the level boundary), then the rest in level and pool order. Practice criteria never qualify
    (they are not topic criteria). Deterministic from stored scores and the policy; the LLM goal is not consulted."""
    topic = set(topic_criteria)
    decisive: dict[str, None] = {}  # second answers for replicated pools (Senior data layer): asked first
    out: dict[str, None] = {}
    for rule in _probe_rules(policy, result):
        cov = result.coverage_by_level.get(rule.level.value)  # type: ignore[union-attr]
        status = {p.pool_id: p.status for p in cov.pools} if cov else {}
        for pool in rule.pools:
            if status.get(pool.pool_id) in ("CONFIRMED", "GAP", "NO_EXPERIENCE"):
                continue
            replicated = pool.pool_id in rule.replicated_pools
            for c in pool.members:
                s = scores.get(c)
                # a replicated pool that is not CONFIRMED needs a second, independent confirming answer (WS-1 fix)
                second = replicated and s is not None and s >= rule.tau
                if c in topic and asked.get(c, 0) < max_asks and (_unresolved(rule, s) or second):
                    (decisive if second else out)[c] = None
    return list(decisive) + [c for c in out if c not in decisive]


def replicated_members(policy: SeniorityPolicy | None) -> frozenset[str]:
    """Members of the replicated pools of a capability policy (empty otherwise)."""
    return frozenset(c for r in (policy.rules if policy else ()) if r.capability for p in r.pools
                     if p.pool_id in r.replicated_pools for c in p.members)


def probe_order(unmet: Sequence[str], policy: SeniorityPolicy | None, result: SeniorityResult | None,
                first: Sequence[str]) -> list[str]:
    """Stable order of the topic's open criteria: `first` (continuation targets, their order) leads, then
    prioritize_unmet. Membership is unchanged; without targets it equals prioritize_unmet."""
    lead = [c for c in first if c in set(unmet)]
    rest = prioritize_unmet([c for c in unmet if c not in set(lead)], policy, result)
    return lead + rest


def practice_gaps(policy: SeniorityPolicy | None, result: SeniorityResult | None, limit: int = 2) -> list[str]:
    """Practice hints (policy order), at most `limit`. Pooled rules (D-6): the lowest non-SUPPORTED level's wholly
    unassessed practice, then — once that level's technical minimum is met — the next level's, then borderline
    (UNRESOLVED) practice of the same levels, so a borderline aspect gets another chance in a later topic. Capability
    rules (v4) only; v1-v3: the target level's unassessed practice criteria, as before."""
    rule = _target(policy, result)
    if rule is None or limit <= 0:
        return []
    cov = result.coverage_by_level.get(rule.level.value)  # type: ignore[union-attr]
    if cov is None:
        return []
    if not rule.capability:  # v1-v3: unchanged (golden digests): the target level's wholly unassessed practice
        unassessed = set(cov.unassessed_ids)
        return [c for c in rule.critical if c.startswith(f"{PRACTICE_ACTION}.") and c in unassessed][:limit]
    rules = [rule]
    nxt = [r for r in policy.rules if rank(r.level) == rank(rule.level) + 1]  # type: ignore[union-attr]
    if nxt and cov.technical_confirmed is not None and cov.technical_confirmed >= rule.min_technical:
        rules.append(nxt[0])
    fresh: dict[str, None] = {}
    border: dict[str, None] = {}
    for r in rules:
        c2 = result.coverage_by_level.get(r.level.value)  # type: ignore[union-attr]
        for p in (c2.pools if c2 else ()):
            for c in p.members:
                if c.startswith(f"{PRACTICE_ACTION}."):
                    (fresh if p.status == "UNASSESSED" else border if p.status == "UNRESOLVED" else {})[c] = None
    return list(dict.fromkeys([*fresh, *border]))[:limit]
