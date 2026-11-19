"""Level probe (§3e): within the topic Q_t already chose, put criteria that are critical for the lowest level not yet
SUPPORTED first, and name that level's unassessed practice criteria as a hint for the Interviewer. For a pooled policy
(v2-v4) "critical" means the members of that level's pools that are not CONFIRMED yet.

Pure. It only reorders and annotates: membership of `unmet`, topic choice, budgets, caps and difficulty are untouched.
Without a level policy (or without an estimate) the input comes back unchanged and there are no practice gaps.
"""
from __future__ import annotations

from collections.abc import Sequence

from backend.domain.seniority import SeniorityResult
from backend.domain.seniority_policy import PRACTICE_ACTION, LevelRule, SeniorityPolicy, rank


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


def practice_gaps(policy: SeniorityPolicy | None, result: SeniorityResult | None, limit: int = 2) -> list[str]:
    """Practice criteria of the target level with no score yet (policy order), at most `limit`."""
    rule = _target(policy, result)
    if rule is None or limit <= 0:
        return []
    cov = result.coverage_by_level.get(rule.level.value)  # type: ignore[union-attr]
    if cov is None:
        return []
    unassessed = set(cov.unassessed_ids)  # pooled rule: members of wholly unassessed pools

    return [c for c in rule.critical if c.startswith(f"{PRACTICE_ACTION}.") and c in unassessed][:limit]
