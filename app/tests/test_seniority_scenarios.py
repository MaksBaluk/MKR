"""End-to-end level scenarios (SIMULATED evaluator) through the real API: profile, cohort, interview, finish, /level.

All scenarios run on the full system-selected python cohort under the current policy python-backend/v3."""
import pytest

from scripts.seniority_scenarios import LABEL, SCENARIOS, build


@pytest.fixture(scope="module")
def results():
    return {r["id"]: r for r in build()}


def _got(r):
    return r["level"]["assessed_level"], r["level"]["assessment_status"]


def _statuses(r):
    return {k: c["status"] for k, c in r["level"]["coverage_by_level"].items()}


def test_scenarios_are_labelled_simulated():
    assert LABEL.startswith("SIMULATED")


@pytest.mark.parametrize("sc", SCENARIOS, ids=[s.sid for s in SCENARIOS])
def test_scenario_level_and_status(results, sc):
    r = results[sc.sid]
    assert r["status"] == "FINISHED" and r["cohort"] == "SYSTEM_COHORT" and r["vacancies"] == 90
    assert r["level"]["policy"]["version"] == "v3"
    assert _got(r) == tuple(r["expected"])
    assert {k: v for k, v in _statuses(r).items() if k in sc.expected_levels} == sc.expected_levels


def test_p1_product_cohort_reaches_senior_with_market_topics(results):
    """Q_t is unchanged and still spends the budget on market topics (kafka, fastapi, aws, docker, ...); v2 pools let
    that evidence count. Two Senior capabilities stay unassessed because Q_t never picks their topics."""
    r = results["P1"]
    assert len(r["topics"]) == 10 and {"kafka", "fastapi", "aws", "docker"} <= set(r["topics"])
    assert not {"sqlalchemy", "celery", "pytest", "async-python", "observability"} & set(r["topics"])
    titles = {p["title"] for p in r["level"]["unassessed_pools"]}
    assert titles == {"Конкурентний доступ і паралельність", "Розслідування інцидентів у продакшені"}
    assert r["level"]["critical_gaps"] == []


def test_p2_desired_senior_confirms_middle_senior_unverified(results):
    lv = results["P2"]["level"]
    assert lv["desired_level"] == "senior" and lv["critical_gaps"] == []  # borderline 0.72 is not a gap
    assert lv["explanation"][0] == "Підтверджено Middle за перевіреними критеріями. Для висновку про Senior недостатньо даних."
    senior = {p["title"]: p["status"] for p in lv["coverage_by_level"]["SENIOR"]["pools"]}
    assert senior["Аналіз компромісів"] == "UNASSESSED" and "UNRESOLVED" in senior.values()


def test_p3_weak_answers_never_reach_a_level(results):
    lv = results["P3"]["level"]
    junior = lv["coverage_by_level"]["JUNIOR"]
    assert junior["gap_count"] == junior["assessed_count"] >= 7 and lv["critical_gaps"]


def test_p4_partial_middle_is_unverified_not_gap(results):
    lv = results["P4"]["level"]
    middle = lv["coverage_by_level"]["MIDDLE"]
    assert middle["gap_count"] == 0 and "ASSESSED_COUNT_BELOW_MIN" in middle["reasons"]
    assert lv["explanation"][0] == "Підтверджено Junior за перевіреними критеріями. Для висновку про Middle недостатньо даних."


def test_s3_strong_answers_without_coverage_stay_unknown(results):
    r = results["S3"]
    assert r["questions"] == 3 and r["level"]["critical_gaps"] == []
    assert all(e["score"] >= 0.95 for e in r["evidence"].values() if e["score"] is not None)
    assert all(c["status"] == "UNVERIFIED" for c in r["level"]["coverage_by_level"].values())


# The same stored evidence re-estimated under the previous policy v2 (comparison only; v3 is what the API stores).
V2_LEVELS = {"P1": "SENIOR", "P2": "MIDDLE", "P3": "UNKNOWN", "P4": "JUNIOR", "S3": "UNKNOWN", "P5": "MIDDLE"}


def test_v2_comparison_differs_only_where_the_senior_bar_moved(results):
    assert {sid: r["v2_level"] for sid, r in results.items()} == V2_LEVELS


def test_p5_six_strong_topics_reach_senior_under_v3_only(results):
    r = results["P5"]
    assert r["questions"] == 6 and len(r["topics"]) == 6 and r["v2_level"] == "MIDDLE"
    senior = r["level"]["coverage_by_level"]["SENIOR"]
    assert (senior["assessed_count"], senior["confirmed_count"], senior["competencies_confirmed"]) == (10, 10, 3)
