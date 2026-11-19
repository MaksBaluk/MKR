"""Policy python-backend/v2 (§3e): pooled critical units, count thresholds; v1 stays byte-identical and addressable."""
import json
from pathlib import Path

import pytest

from backend.domain.level_probe import practice_gaps, prioritize_unmet
from backend.domain.seniority import CriterionEvidence, estimate, result_to_json
from backend.domain.seniority_policy import (
    PRACTICE_ACTION, PRACTICE_CRITERIA, POLICY_VERSIONS, PYTHON_BACKEND_V1, PYTHON_BACKEND_V2, CriterionPool, Level,
    SeniorityPolicy, policy_by_version, policy_for, pooled, rank)
from backend.seed import read_fixture
from tests.seniority_v1_cases import V1_IDS, cases

V2 = PYTHON_BACKEND_V2
J, M, S = V2.rules


def ev(scores: dict[str, float | None], turns=("t1",)) -> dict[str, CriterionEvidence]:
    return {c: CriterionEvidence(c, s, turns if s is not None else ()) for c, s in scores.items()}


def first_members(rule, score):
    return {p.members[0]: score for p in rule.pools}


# --- v1 regression -------------------------------------------------------------------------------------------------

def test_v1_results_byte_identical_to_golden():
    golden = json.loads((Path(__file__).parent / "data" / "seniority_v1_golden.json").read_text())
    got = []
    for e in cases():
        r = estimate(PYTHON_BACKEND_V1, e)
        got.append({"result": result_to_json(r), "prioritized": prioritize_unmet(V1_IDS, PYTHON_BACKEND_V1, r),
                    "practice_gaps": practice_gaps(PYTHON_BACKEND_V1, r, limit=9)})
    assert len(got) == len(golden) == 91
    assert json.dumps(got, ensure_ascii=False, sort_keys=True) == json.dumps(golden, ensure_ascii=False, sort_keys=True)
    assert all("pools" not in c for g in got for c in g["result"]["coverage_by_level"].values())


# --- registry ------------------------------------------------------------------------------------------------------

def test_registry_current_is_v2_and_v1_stays_addressable():
    assert policy_for("python") is V2 and (V2.policy_id, V2.version, V2.status) == (
        "python-backend", "v2", "WORKING_ASSUMPTION")
    assert policy_by_version("python-backend", "v1") is PYTHON_BACKEND_V1
    assert policy_by_version("python-backend", "v2") is V2
    assert policy_by_version("python-backend", "v9") is None and policy_by_version(None, None) is None
    assert set(POLICY_VERSIONS) == {("python-backend", "v1"), ("python-backend", "v2")}
    assert PYTHON_BACKEND_V1.version == "v1" and all(not r.pools for r in PYTHON_BACKEND_V1.rules)


def test_v2_pools_use_existing_ids_titles_and_hierarchy():
    base = {c["criterion_id"] for r in read_fixture("rubrics.json")["rubrics"] for c in r["criteria"]}
    for rule in V2.rules:
        assert rule.pools and rule.min_assessed and rule.min_confirmed
        assert rule.min_confirmed <= rule.min_assessed <= len(rule.pools)
        assert rule.critical == tuple(dict.fromkeys(c for p in rule.pools for c in p.members))
        ids = [p.pool_id for p in rule.pools]
        assert len(ids) == len(set(ids))
        members = [c for p in rule.pools for c in p.members]
        assert len(members) == len(set(members)), "a criterion belongs to at most one pool per level"
        for p in rule.pools:
            assert p.members and p.title and not any(ch in p.title for ch in "._")  # human Ukrainian title
            for c in p.members:
                assert c in (set(PRACTICE_CRITERIA) if c.startswith(PRACTICE_ACTION + ".") else base), c
    assert [rank(r.level) for r in V2.rules] == [0, 1, 2]
    assert [r.tau for r in V2.rules] == sorted(r.tau for r in V2.rules)
    # one pool id has one meaning across levels
    seen: dict[str, tuple] = {}
    for rule in V2.rules:
        for p in rule.pools:
            assert seen.setdefault(p.pool_id, (p.title, p.members)) == (p.title, p.members)


# --- pool semantics ------------------------------------------------------------------------------------------------

TINY = SeniorityPolicy("tiny", "t1", "python", "WORKING_ASSUMPTION", (
    pooled(Level.JUNIOR, 0.5, 2, 2, 1, (
        CriterionPool("a", "Пул А", ("x.a1", "y.a2", "z.a3")),
        CriterionPool("b", "Пул Б", ("x.b1",)))),
    pooled(Level.MIDDLE, 0.7, 1, 1, 1, (CriterionPool("c", "Пул В", ("x.c1", "y.c2")),)),
))


def pool(result, level, pid):
    return next(p for p in result.coverage_by_level[level].pools if p.pool_id == pid)


def test_any_member_confirms_pool():
    r = estimate(TINY, ev({"y.a2": 0.6, "x.a1": 0.2, "x.b1": 0.9}))
    a = pool(r, "JUNIOR", "a")
    assert (a.status, a.confirmed_ids, a.gap_ids) == ("CONFIRMED", ("y.a2",), ())
    assert r.coverage_by_level["JUNIOR"].status == "SUPPORTED" and r.assessed_level == "JUNIOR"
    assert "x.a1" not in r.critical_gaps  # a failed alternative inside a confirmed pool is not a level gap


def test_no_compensation_across_pools():
    r = estimate(TINY, ev({"x.a1": 1.0, "y.a2": 1.0, "z.a3": 1.0, "x.b1": 0.1}))
    cov = r.coverage_by_level["JUNIOR"]
    assert (cov.status, cov.gap_ids, cov.reasons[0]) == ("GAP", ("x.b1",), "CRITICAL_GAP")
    assert (r.assessed_level, r.assessment_status) == ("UNKNOWN", "GAPS_AT_JUNIOR")


def test_gap_rule_exact():
    eps_band = 0.5 - 0.04  # inside [tau - eps, tau): unresolved
    cases_ = {
        "GAP": {"x.a1": 0.2},  # one established gap, other members unscored
        "UNRESOLVED": {"x.a1": 0.2, "y.a2": eps_band},  # a borderline member blocks the gap
        "UNASSESSED": {},
        "CONFIRMED": {"x.a1": 0.2, "z.a3": 0.5},
    }
    for status, scores in cases_.items():
        assert pool(estimate(TINY, ev(scores)), "JUNIOR", "a").status == status, status
    untraced = estimate(TINY, {"x.a1": CriterionEvidence("x.a1", 0.1, ())})
    assert pool(untraced, "JUNIOR", "a").status == "UNRESOLVED"  # a score without an answer is never a gap
    no_turn_high = estimate(TINY, {"x.a1": CriterionEvidence("x.a1", 0.9, ())})
    assert pool(no_turn_high, "JUNIOR", "a").status == "UNRESOLVED"  # nor a confirmation
    assert pool(estimate(TINY, ev({"x.a1": 0.2, "y.a2": 0.1})), "JUNIOR", "a").gap_ids == ("x.a1", "y.a2")


def test_unknown_reasons_and_counts():
    r = estimate(TINY, ev({"x.a1": 0.9}))
    j = r.coverage_by_level["JUNIOR"]
    assert (j.critical_total, j.assessed, j.confirmed, j.gaps) == (2, 1, 1, 0)
    assert j.reasons == ("ASSESSED_COUNT_BELOW_MIN", "CONFIRMED_COUNT_BELOW_MIN")
    assert (r.assessed_level, r.assessment_status) == ("UNKNOWN", "INSUFFICIENT_DATA")
    assert r.unassessed_criteria == ("x.b1",)  # members of wholly unassessed pools only; scope stops at Junior
    assert r.coverage_by_level["MIDDLE"].unassessed_ids == ("x.c1", "y.c2")
    assert estimate(TINY, {}).assessed_level == "UNKNOWN"  # never a Junior default


def test_hierarchy_middle_needs_junior():
    only_middle = estimate(TINY, ev({"y.c2": 0.9}))
    assert only_middle.coverage_by_level["MIDDLE"].status == "SUPPORTED"
    assert (only_middle.assessed_level, only_middle.highest_supported_level) == ("UNKNOWN", "MIDDLE")
    both = estimate(TINY, ev({"x.a1": 0.9, "x.b1": 0.9, "y.c2": 0.9}))
    assert both.assessed_level == "MIDDLE"


def test_competencies_counted_over_confirming_members_without_practice():
    p = SeniorityPolicy("t", "t", "python", "WORKING_ASSUMPTION", (pooled(Level.JUNIOR, 0.5, 2, 2, 2, (
        CriterionPool("a", "А", ("x.a1", "y.a2")), CriterionPool("p", "П", ("practice-backend.independence",)))),))
    one = estimate(p, ev({"x.a1": 0.9, "practice-backend.independence": 0.9}))
    assert one.coverage_by_level["JUNIOR"].competencies_confirmed == 1
    assert one.coverage_by_level["JUNIOR"].reasons == ("TOO_FEW_COMPETENCIES",)
    two = estimate(p, ev({"x.a1": 0.9, "y.a2": 0.9, "practice-backend.independence": 0.9}))
    assert two.assessed_level == "JUNIOR"


def test_pooled_result_json_has_pools_with_titles():
    data = result_to_json(estimate(TINY, ev({"x.a1": 0.9})))
    pools = data["coverage_by_level"]["JUNIOR"]["pools"]
    assert pools[0] == {"pool_id": "a", "title": "Пул А", "status": "CONFIRMED", "members": ["x.a1", "y.a2", "z.a3"],
                        "confirmed_ids": ["x.a1"], "gap_ids": [], "unassessed_ids": []}
    assert json.loads(json.dumps(data)) == data


def test_v2_middle_reachable_with_market_topics_only():
    """The topics Q_t picks on the full cohort (measured): no sqlalchemy/celery/pytest/async/observability."""
    topics = ("python-core", "kafka", "fastapi", "ci-cd", "sql", "aws", "docker", "postgresql")
    rubric = {r["action_id"]: [c["criterion_id"] for c in r["criteria"]] for r in read_fixture("rubrics.json")["rubrics"]}
    strong = {c: 0.9 for t in topics for c in rubric[t]} | {c: 0.9 for c in PRACTICE_CRITERIA}
    r = estimate(V2, ev(strong))
    assert r.coverage_by_level["MIDDLE"].status == "SUPPORTED" and r.assessed_level in ("MIDDLE", "SENIOR")
    weak = estimate(V2, ev({c: 0.3 for c in strong}))
    assert weak.assessed_level == "UNKNOWN" and weak.assessment_status == "GAPS_AT_JUNIOR"


def test_v2_one_topic_or_single_pool_per_level_does_not_reach_middle():
    r = estimate(V2, ev({c: 0.95 for c in ("postgresql.indexes", "postgresql.transactions", "postgresql.schema",
                                            "postgresql.operations", "postgresql.migrations")}))
    assert r.assessed_level == "UNKNOWN"
    junior_only = estimate(V2, ev(first_members(J, 0.9) | {"sql.correctness": 0.9}))
    assert junior_only.assessed_level == "JUNIOR"
    assert junior_only.coverage_by_level["MIDDLE"].status == "UNVERIFIED"


def test_probe_targets_unmet_pools_only():
    junior_ok = ev(first_members(J, 0.9) | {"pytest.structure": 0.9, "sql.correctness": 0.9})
    r = estimate(V2, junior_ok | ev({"postgresql.indexes": 0.9}))
    assert r.coverage_by_level["JUNIOR"].status == "SUPPORTED"
    # query-efficiency (Middle) is confirmed by postgresql.indexes: its other members are not prioritized
    unmet = ["sql.performance", "sql.aggregation", "postgresql.transactions", "postgresql.schema"]
    assert prioritize_unmet(unmet, V2, r) == ["postgresql.transactions", "postgresql.schema",
                                              "sql.performance", "sql.aggregation"]
    assert sorted(prioritize_unmet(unmet, V2, r)) == sorted(unmet)
    assert practice_gaps(V2, r) == ["practice-backend.rationale", "practice-backend.diagnosis"]
    assert practice_gaps(V2, estimate(V2, {})) == ["practice-backend.independence"]


@pytest.mark.parametrize("policy", [PYTHON_BACKEND_V1, PYTHON_BACKEND_V2])
def test_estimate_is_deterministic(policy):
    e = cases()[5]
    assert result_to_json(estimate(policy, e)) == result_to_json(estimate(policy, e))
