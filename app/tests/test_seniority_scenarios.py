"""End-to-end level scenarios (SIMULATED evaluator) through the real API: profile, cohort, interview, finish, /level."""
import pytest

from scripts.seniority_scenarios import LABEL, build


@pytest.fixture(scope="module")
def results():
    return {r["id"]: r for r in build()}


def _got(r):
    return r["level"]["assessed_level"], r["level"]["assessment_status"]


def test_scenarios_are_labelled_simulated():
    assert LABEL.startswith("SIMULATED")


@pytest.mark.parametrize("sid", ["S1", "S2", "S3", "S2-product"])
def test_scenario_level_and_status(results, sid):
    r = results[sid]
    assert r["status"] == "FINISHED"
    assert _got(r) == tuple(r["expected"])


def test_s1_desired_senior_confirms_middle_senior_unverified(results):
    lv = results["S1"]["level"]
    assert lv["desired_level"] == "senior"
    assert {k: c["status"] for k, c in lv["coverage_by_level"].items()} == {
        "JUNIOR": "SUPPORTED", "MIDDLE": "SUPPORTED", "SENIOR": "UNVERIFIED"}
    assert lv["critical_gaps"] == []  # borderline 0.72 and missing evidence are not gaps
    assert lv["explanation"][0] == "Підтверджено Middle за перевіреними критеріями. Для висновку про Senior недостатньо даних."
    unassessed = {c["id"] for c in lv["unassessed_criteria"]}
    assert {"practice-backend.ownership", "practice-backend.tradeoffs"} <= unassessed


def test_s2_senior_needs_every_level_supported(results):
    cov = results["S2"]["level"]["coverage_by_level"]
    assert all(c["status"] == "SUPPORTED" for c in cov.values())
    assert results["S2"]["level"]["note"] == "Потребує експертної валідації"


def test_s3_strong_answers_without_coverage_stay_unknown(results):
    r = results["S3"]
    assert r["questions"] == 3 and r["level"]["critical_gaps"] == []
    assert all(e["score"] >= 0.95 for e in r["evidence"].values() if e["score"] is not None)
    assert all(c["status"] == "UNVERIFIED" for c in r["level"]["coverage_by_level"].values())


def test_full_system_cohort_caps_level_known_limit(results):
    """Documented limit: on the full system cohort Q_t spends topics on non-policy skills, so even uniformly strong
    answers stop at JUNIOR. If Q_t or the policy change, revisit SENIORITY_REPORT.md instead of editing this away."""
    r = results["S2-product"]
    assert r["cohort"] == "SYSTEM_COHORT" and len(r["topics"]) == 10
    assert {"kafka", "fastapi"} <= set(r["topics"])

