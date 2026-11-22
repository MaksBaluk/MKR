"""Chapter-4 stage-5 harness: seeds are deterministic, modes run under equal conditions, budgets are never exceeded.
SIMULATED stubs only (no LLM, no network); throwaway in-memory SQLite."""
from __future__ import annotations

import pytest

from scripts.chapter4.candidate_model import PROFILES, oracle_level, sensitive_truth
from scripts.chapter4.modes_analysis import boot_ci, sign_test
from scripts.chapter4.modes_experiment import Job, content_hash, grid, run_job
from scripts.chapter4.scenarios import Env


@pytest.fixture(scope="module")
def env():
    with Env() as e:
        yield e


def test_profiles_reach_their_designed_level_on_perfect_evidence():
    assert {p.profile_id: oracle_level(p) for p in PROFILES} == \
        {p.profile_id: p.intended for p in PROFILES}


def test_same_seed_same_run_content(env):
    job = Job("C12", "D_FULL_COMPETENCEMATCH", 8, 1)
    first, second = run_job(env, job), run_job(env, job)
    assert content_hash([first]) == content_hash([second])
    assert first["interview_id"] != second["interview_id"]  # two independent attempts, identical content


def test_modes_share_conditions_and_respect_budget(env):
    runs = {m: run_job(env, Job("C07", m, None if m == "A_INITIAL_PROFILE" else 6, None if m ==
                                "A_INITIAL_PROFILE" else 0))
            for m in ("A_INITIAL_PROFILE", "B_STATIC", "C_ADAPTIVE_NO_MARKET", "D_FULL_COMPETENCEMATCH", "D_FIXED_DIFFICULTY")}
    ec = [r["equal_conditions"] for r in runs.values()]
    for key in ("cohort_sha256", "prompt_version", "algorithm_version", "profile_snapshot_sha", "rubric_versions_sha"):
        assert len({e[key] for e in ec}) == 1, key
    flags = {m: (r["adaptive_topics"], r["adaptive_followup"], r["adaptive_difficulty"]) for m, r in runs.items()}
    assert flags["B_STATIC"] == (False, False, False)
    assert flags["C_ADAPTIVE_NO_MARKET"] == flags["D_FULL_COMPETENCEMATCH"] == (True, True, True)
    assert flags["D_FIXED_DIFFICULTY"] == (True, True, False)
    assert runs["C_ADAPTIVE_NO_MARKET"]["research_planner"] and not runs["D_FULL_COMPETENCEMATCH"]["research_planner"]
    assert runs["A_INITIAL_PROFILE"]["n_questions"] == 0
    for m in ("B_STATIC", "C_ADAPTIVE_NO_MARKET", "D_FULL_COMPETENCEMATCH", "D_FIXED_DIFFICULTY"):
        r = runs[m]
        assert 0 < r["n_questions"] <= 6 and r["n_topics"] <= 10
        assert max(r["questions_per_topic"].values()) <= 5
        assert r["fallback_questions"] == 0  # UaModel: no NOT_UKRAINIAN bank fallback (EB-3)
    assert {d for d in runs["D_FIXED_DIFFICULTY"]["difficulty_sequence"]} == \
        {runs["D_FIXED_DIFFICULTY"]["difficulty_sequence"][0]}


def test_grid_pairs_every_interview_mode_on_the_same_budgets_and_seeds():
    jobs = grid(["C01"], (0, 1), (5, 10))
    keys = {m: {(j.budget, j.seed) for j in jobs if j.mode == m} for m in
            ("B_STATIC", "C_ADAPTIVE_NO_MARKET", "D_FULL_COMPETENCEMATCH", "D_FIXED_DIFFICULTY")}
    assert keys["B_STATIC"] == keys["C_ADAPTIVE_NO_MARKET"] == keys["D_FULL_COMPETENCEMATCH"] == \
        keys["D_FIXED_DIFFICULTY"] == \
        {(5, 0), (5, 1), (10, 0), (10, 1)}
    assert len({j.run_id for j in jobs}) == len(jobs)


def test_statistics_helpers():
    assert sign_test([1, 1, 1, 1, 1]) == (5, 0, 0, 0.0625)
    assert sign_test([0, 0]) == (0, 0, 2, None)
    lo, hi = boot_ci({"a": [1.0, 2.0], "b": [3.0]})
    assert 1.0 <= lo <= hi <= 3.0 and boot_ci({"a": [1.0, 2.0], "b": [3.0]}) == (lo, hi)


def test_sensitive_candidate_assumptions():
    assert sensitive_truth(0.9, "BASIC") == 0.8
    assert sensitive_truth(0.6, "ADVANCED") == pytest.approx(0.45)
    assert sensitive_truth(0.9, "ADVANCED") == 0.9
    assert sensitive_truth(0.4, "INTERMEDIATE") == pytest.approx(0.25)


def test_research_planner_ignores_market_and_restores_product_planner():
    import backend.api.core as core
    from backend.domain.planner import OpenState
    from scripts.chapter4.research_planner import no_market_choice, no_market_planner
    st = OpenState(frozenset({"g1", "g2"}), {"g1": frozenset({"a", "b"}), "g2": frozenset({"c"})}, frozenset({"g1"}),
                   frozenset())
    pick = no_market_choice(3)
    heavy = {"a": 100.0, "b": 0.0, "c": 0.0}
    assert pick(st, {}, ["a", "b", "c"], heavy) == pick(st, {"x": 9.0}, ["a", "b", "c"], {})  # weights/mass unused
    assert pick(st, {}, ["z"], {}) is None  # no open group: plan exhausted, like the product
    original = core.choose_next
    with no_market_planner(1):
        assert core.choose_next is not original
    assert core.choose_next is original
