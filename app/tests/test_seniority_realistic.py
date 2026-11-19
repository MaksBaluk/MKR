"""Audit regression scenarios through the real API with the REALISTIC simulated evaluator (scripts/seniority_realistic.py:
1-2 criteria per question, only addressed criteria graded). SIMULATED: not a real LLM, not a real candidate.

Each case also re-estimates the same stored evidence under v3, to show the audit defect it fixes."""
import pytest

from scripts.chapter4.scenarios import Env
from scripts.seniority_realistic import LABEL, profiles, run

CASES = {  # id: (profile, desired, criteria per question, follow-up goal policy)
    "no-kafka-2": ("senior-no-kafka", "senior", 2, "GAP_ONLY"),
    "no-kafka-1": ("senior-no-kafka", "senior", 1, "GAP_ONLY"),
    "no-aws-2": ("senior-no-aws", "senior", 2, "GAP_ONLY"),
    "weak-git-2": ("senior-weak-git", "senior", 2, "GAP_ONLY"),
    "weak-senior-2": ("weak-senior", "senior", 2, "OPEN"),
    "weak-senior-1": ("weak-senior", "senior", 1, "OPEN"),
    "middle-2": ("middle", "middle", 2, "GAP_ONLY"),
    "junior-2": ("junior", "junior", 2, "GAP_ONLY"),
    "weak-2": ("weak", "senior", 2, "OPEN"),
}


@pytest.fixture(scope="module")
def results():
    truths = profiles()
    with Env() as env:
        return {k: run(env, p, truths[p], d, pq, g) for k, (p, d, pq, g) in CASES.items()}


def test_label_is_simulated():
    assert LABEL.startswith("SIMULATED")


def test_all_runs_store_v4_and_respect_budgets(results):
    for r in results.values():
        assert r["policy"] == "v4" and len(r["topics"]) <= 10 and r["questions"] <= 50


def test_ur1_senior_without_kafka_does_not_collapse_to_junior(results):
    two, one = results["no-kafka-2"], results["no-kafka-1"]
    assert two["assessed"] == "SENIOR" and two["same_evidence"]["python-backend/v3"] == "JUNIOR"
    assert {p["id"] for p in two["level"]["no_experience_pools"]} >= {"event-consumers", "failure-handling"}
    assert one["assessed"] != "JUNIOR"


def test_ur2_senior_without_aws_is_not_dropped_to_middle(results):
    r = results["no-aws-2"]
    assert r["assessed"] == "SENIOR" and r["same_evidence"]["python-backend/v3"] == "MIDDLE"


def test_ur4_one_weak_git_answer_does_not_force_unknown(results):
    r = results["weak-git-2"]
    assert r["assessed"] == "SENIOR" and r["same_evidence"]["python-backend/v3"] == "UNKNOWN"
    assert "git.branching" in {c["id"] for c in r["level"]["coverage_by_level"]["JUNIOR"]["tolerated_gaps"]}


def test_ws1_weak_evidence_senior_never_gets_senior(results):
    for key in ("weak-senior-2", "weak-senior-1"):
        assert results[key]["assessed"] == "MIDDLE"


def test_controls_keep_their_level(results):
    assert results["middle-2"]["assessed"] == "MIDDLE"
    assert results["junior-2"]["assessed"] == "JUNIOR"
    assert (results["weak-2"]["assessed"], results["weak-2"]["status"]) == ("UNKNOWN", "GAPS_AT_JUNIOR")
