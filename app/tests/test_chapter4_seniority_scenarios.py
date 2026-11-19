"""Chapter-4 control scenarios S01-S12 (policy python-backend/v4). Source of truth for the rows of
artifacts/chapter4/seniority_results.csv (scripts/chapter4/seniority_scenarios_ch4.py).

Expectations come from the owner specification and are not adjusted to the result. S09 (literal reading: strong
technical answers and strong other practice, practice-independence never assessed) is a recorded contradiction with
policy v4: the test pins the actual behaviour so that a policy change forces a re-review of the finding."""
import pytest

from backend.domain.seniority import estimate
from scripts.chapter4.seniority_scenarios_ch4 import (ALL_TECH, POLICY, PR, e2e_scenarios, estimator_scenarios, ev)

ROWS = {r["scenario_id"]: r for r in estimator_scenarios()}
PASSING = [s for s in ROWS if s != "S09"]


@pytest.mark.parametrize("sid", PASSING)
def test_estimator_scenario_meets_the_specified_expectation(sid):
    assert ROWS[sid]["verdict"] == "PASS", (sid, ROWS[sid]["actual"], ROWS[sid]["coverage"])


def test_s09_contradiction_is_pinned_independence_is_not_required_for_senior():
    row = ROWS["S09"]
    assert row["verdict"] == "FAIL" and row["_result"].assessed_level == "SENIOR"
    senior_pools = {c for r in POLICY.rules if r.level.value == "SENIOR" for p in r.pools for c in p.members}
    assert PR["independence"] not in senior_pools


def test_s10_and_s12_are_distinguishable_in_the_result():
    s10, s12 = ROWS["S10"]["_result"], ROWS["S12"]["_result"]
    assert s10.assessed_level == s12.assessed_level == "MIDDLE"
    assert (s10.coverage_by_level["SENIOR"].status, s12.coverage_by_level["SENIOR"].status) == ("UNVERIFIED", "GAP")
    assert not s10.critical_gaps and "postgresql.operations" in s12.critical_gaps
    assert s10.explanation[0] != s12.explanation[0]


def test_desired_level_years_and_self_rating_are_not_estimator_inputs():
    import inspect
    assert list(inspect.signature(estimate).parameters) == ["policy", "evidence"]


def test_unknown_is_not_zero_for_the_level():
    weak = estimate(POLICY, ev({c: 0.0 for c in ALL_TECH}))
    unknown = estimate(POLICY, ev({c: None for c in ALL_TECH}))
    assert weak.assessment_status == "GAPS_AT_JUNIOR" and unknown.assessment_status == "INSUFFICIENT_DATA"


def test_end_to_end_senior_and_the_documented_narrow_question_miss():
    rows, turns = e2e_scenarios()
    by = {r["scenario_id"]: r for r in rows}
    assert all(r["label"] == "SIMULATED_E2E" for r in rows)
    for sid in ("S04-E2E", "S07-E2E", "S01-E2E", "S08-E2E", "S10-E2E"):
        assert by[sid]["verdict"] == "PASS", (sid, by[sid]["actual"], by[sid]["note"])
    # 1 criterion per question: the true Senior stays MIDDLE (Q_t picks no postgresql topic in this run)
    assert by["S04-E2E-narrow"]["actual"].startswith("MIDDLE") and "NO_POSTGRESQL_TOPIC" in by["S04-E2E-narrow"]["note"]
    assert {t["run_id"] for t in turns} == {r["run_id"] for r in rows}
    per_topic = {}
    for t in turns:
        per_topic[(t["run_id"], t["action_id"])] = per_topic.get((t["run_id"], t["action_id"]), 0) + 1
    assert max(per_topic.values()) <= 5
    assert all(len({a for (rid, a) in per_topic if rid == r["run_id"]}) <= 10 for r in rows)
