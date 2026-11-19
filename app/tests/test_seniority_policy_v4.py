"""Policy python-backend/v4 (§3e, audit 2026-11-19): capability-level gaps, DECLINED tools, anchor-aligned thresholds,
counts over confirmed technical/practice pools, proportional gaps, median practice. Regression tests for each audit
scenario fixed here (D-1, D-4, D-5, D-9, D-10, UR-1..UR-4, UR-7, WS-1..WS-4). v1-v3 goldens live in their own files."""
import json
import math

import pytest

from backend.domain.seniority import CriterionEvidence, estimate, is_declined, result_to_json
from backend.domain.seniority_policy import (
    POLICY_VERSIONS, PRACTICE_CRITERIA, PYTHON_BACKEND_V3, PYTHON_BACKEND_V4, Level, policy_by_version, policy_for)
from backend.seed import read_fixture

V3, V4 = PYTHON_BACKEND_V3, PYTHON_BACKEND_V4
J, M, S = V4.rules
RUBRIC = {r["action_id"]: [c["criterion_id"] for c in r["criteria"]] for r in read_fixture("rubrics.json")["rubrics"]}
PR = {c.split(".", 1)[1]: c for c in PRACTICE_CRITERIA}
DECLINE = "Не знаю цього і не працював з цим інструментом."


def ev(scores: dict[str, float | None], declined=(), topics=2) -> dict[str, CriterionEvidence]:
    """Traced evidence; practice is graded in `topics` source topics with the same score; `declined` ids carry a
    "never worked with it" statement (as seniority_evidence derives it)."""
    out = {}
    for c, s in scores.items():
        if s is None:
            out[c] = CriterionEvidence(c, None)
        elif c in PRACTICE_CRITERIA:
            out[c] = CriterionEvidence(c, s, ("t1",), topic_scores=(s,) * topics)
        else:
            out[c] = CriterionEvidence(c, s, ("t1",), declined=c in declined)
    return out


def members(rule) -> list[str]:
    return [c for p in rule.pools for c in p.members]


FULL = {c: 0.9 for r in V4.rules for c in members(r)}  # every capability of every level confirmed


def pools(r, level="SENIOR") -> dict[str, str]:
    return {p.pool_id: p.status for p in r.coverage_by_level[level].pools}


# --- registry and structure ----------------------------------------------------------------------------------------

def test_v4_is_current_and_every_older_version_stays_addressable():
    assert policy_for("python") is V4 and (V4.policy_id, V4.version, V4.status) == (
        "python-backend", "v4", "WORKING_ASSUMPTION")
    assert set(POLICY_VERSIONS) == {("python-backend", v) for v in ("v1", "v2", "v3", "v4")}
    assert policy_by_version("python-backend", "v3") is V3
    assert policy_for("marketing") is None and policy_for("design") is None


def test_v4_thresholds_sit_on_rubric_band_edges_and_counts_are_over_confirmed_pools():
    bands = {0.25, 0.5, 0.75, 0.9}
    for rule in V4.rules:
        assert rule.capability and rule.tau in bands and rule.gap_below in bands
        assert rule.min_assessed is None and rule.min_assessed_share == rule.min_confirmed_share == 0.0
        assert rule.min_technical + rule.min_practice <= rule.min_confirmed <= len(rule.pools)
    assert [(r.tau, r.gap_below) for r in V4.rules] == [(0.50, 0.50), (0.75, 0.50), (0.75, 0.50)]
    assert [(r.min_confirmed, r.min_technical, r.min_practice) for r in V4.rules] == [(6, 5, 0), (7, 5, 2), (7, 4, 3)]
    assert (J.hard_pools, J.max_soft_gaps, M.max_soft_gaps, S.max_soft_gaps) == (
        ("python-idioms", "python-errors"), 1, 1, 1)
    assert S.required_any == ("db-operations", "schema-migrations")
    assert J.required_any == ("sql-joins", "sql-correctness")
    assert M.required_any == ("query-efficiency", "data-consistency", "schema-design")


def test_no_data_layer_evidence_gives_no_level_even_with_all_practice():
    """M-1 guard kept under the lower v4 counts: six market topics without sql/postgresql plus all practice."""
    no_data = {**{c: 0.9 for t in ("python-core", "kafka", "fastapi", "ci-cd", "aws", "docker") for c in RUBRIC[t]},
               **{c: 0.9 for c in PRACTICE_CRITERIA}}
    r = estimate(V4, ev(no_data))
    assert r.assessed_level == "UNKNOWN" and "REQUIRED_CAPABILITY_UNCONFIRMED" in r.coverage_by_level["JUNIOR"].reasons


def test_v4_pools_are_v3_pools_except_the_broadened_single_tool_cost_pool():
    v3 = {r.level: {p.pool_id: p for p in r.pools} for r in V3.rules}
    for rule in V4.rules:
        for p in rule.pools:
            assert len({m.split(".", 1)[0] for m in p.members}) == len(p.members)  # distinct tools only
            if p.pool_id == "cost-reliability":
                assert p.members == ("aws.cost", "kubernetes.resources")  # UR-2
            else:
                assert p == v3[rule.level][p.pool_id]
    assert {"aws.cost", "kubernetes.resources"} <= {c for ids in RUBRIC.values() for c in ids}


# --- D-1 / UR-1..UR-3: gaps at capability level ---------------------------------------------------------------------

def test_ur1_senior_who_never_worked_with_kafka_is_not_collapsed():
    kafka = {c: 0.0 for c in RUBRIC["kafka"]}
    evidence = {**FULL, **kafka}
    for c in ("celery.design", "celery.retries", "celery.idempotency"):
        evidence.pop(c, None)  # the alternative tool was never asked (Q_t picks kafka, not celery)
    r4 = estimate(V4, ev(evidence, declined=kafka))
    assert pools(r4, "MIDDLE")["event-consumers"] == pools(r4, "MIDDLE")["failure-handling"] == "DECLINED"
    assert r4.assessed_level == "SENIOR" and r4.critical_gaps == ()
    assert set(r4.coverage_by_level["MIDDLE"].declined_ids) == {"kafka.consumers", "kafka.errors"}
    assert any("не працював" in line for line in r4.explanation)
    # the same answers under v3 were two Middle gaps: JUNIOR
    assert estimate(V3, ev(evidence)).assessed_level == "JUNIOR"


def test_declined_tool_is_a_gap_when_two_alternatives_were_offered_or_the_pool_has_one_tool():
    evidence = {**FULL, "kafka.consumers": 0.0, "celery.design": 0.0}
    r = estimate(V4, ev(evidence, declined={"kafka.consumers", "celery.design"}))
    assert pools(r, "MIDDLE")["event-consumers"] == "GAP"
    single = estimate(V4, ev({**FULL, "git.branching": 0.0}, declined={"git.branching"}))
    assert pools(single, "JUNIOR")["version-control"] == "GAP"  # no alternative tool exists


def test_weak_answer_on_a_tool_the_candidate_uses_stays_a_gap():
    evidence = {k: v for k, v in FULL.items() if k != "celery.retries"}
    r = estimate(V4, ev({**evidence, "kafka.errors": 0.3}))  # substantive but weak: genuinely weak knowledge
    assert pools(r, "MIDDLE")["failure-handling"] == "GAP" and "kafka.errors" in r.critical_gaps
    assert r.coverage_by_level["MIDDLE"].status == "SUPPORTED"  # one gap of 14 is tolerated, still reported
    assert r.coverage_by_level["MIDDLE"].tolerated_gap_ids == ("kafka.errors",)


def test_two_weak_capabilities_block_the_level_no_compensation():
    r = estimate(V4, ev({**FULL, "kafka.errors": 0.3, "celery.retries": 0.3, "python-core.typing": 0.2}))
    # failure-handling: both offered tools weak; typed-contracts: weak. Two GAP pools > max_soft_gaps (1).
    m = r.coverage_by_level["MIDDLE"]
    assert (m.status, m.gaps) == ("GAP", 2) and "CRITICAL_GAP" in m.reasons
    assert r.assessed_level == "JUNIOR" and r.highest_supported_level == "SENIOR"


def test_ur2_senior_without_aws_does_not_drop_to_middle():
    aws = {c: 0.0 for c in RUBRIC["aws"]}
    evidence = {k: v for k, v in {**FULL, **aws}.items() if not k.startswith("kubernetes.")}
    r = estimate(V4, ev(evidence, declined=aws))
    assert pools(r)["cost-reliability"] == "DECLINED" and r.assessed_level == "SENIOR"
    assert estimate(V3, ev(evidence)).assessed_level == "MIDDLE"


def test_ur3_ur7_partial_answer_is_borderline_not_a_gap():
    evidence = {k: v for k, v in FULL.items() if k != "celery.retries"}
    for score in (0.5, 0.6, 0.7, 0.74):
        r = estimate(V4, ev({**evidence, "kafka.errors": score}))
        assert pools(r, "MIDDLE")["failure-handling"] == "UNRESOLVED" and r.assessed_level == "SENIOR"
    assert pools(estimate(V4, ev({**evidence, "kafka.errors": 0.75})), "MIDDLE")["failure-handling"] == "CONFIRMED"
    assert pools(estimate(V4, ev({**evidence, "kafka.errors": 0.49})), "MIDDLE")["failure-handling"] == "GAP"
    assert estimate(V3, ev({**evidence, "kafka.errors": 0.6})).assessed_level == "JUNIOR"  # D1b under v3


# --- D-10 / UR-4: proportional gaps ---------------------------------------------------------------------------------

def test_ur4_one_weak_git_answer_does_not_force_unknown():
    r = estimate(V4, ev({**FULL, "git.branching": 0.4}))
    assert r.coverage_by_level["JUNIOR"].status == "SUPPORTED" and r.assessed_level == "SENIOR"
    assert "git.branching" in r.critical_gaps and "git.branching" not in r.confirmed_strengths
    assert any("не блокують" in line and "git.branching" in line for line in r.explanation)
    assert estimate(V3, ev({**FULL, "git.branching": 0.4})).assessed_level == "UNKNOWN"


def test_hard_pool_gap_and_two_junior_gaps_still_block():
    hard = estimate(V4, ev({**FULL, "python-core.errors": 0.3}))
    assert (hard.assessed_level, hard.assessment_status) == ("UNKNOWN", "GAPS_AT_JUNIOR")
    two = estimate(V4, ev({**FULL, "git.branching": 0.3, "sql.joins": 0.3}))
    assert (two.assessed_level, two.assessment_status) == ("UNKNOWN", "GAPS_AT_JUNIOR")


# --- D-4 / WS-1..WS-4: weak-evidence Senior -------------------------------------------------------------------------

BASE_MID = {c: 0.8 for r in (J, M) for c in members(r)}


def test_ws1_two_technical_senior_capabilities_are_not_senior():
    weak = {**BASE_MID, "app-security.authz": 0.8, "rest-api.security": 0.8, "aws.iam": 0.8, "ci-cd.safety": 0.8,
            "postgresql.operations": 0.72, "postgresql.migrations": 0.72, **{c: 0.8 for c in PRACTICE_CRITERIA}}
    r = estimate(V4, ev(weak))
    s = r.coverage_by_level["SENIOR"]
    assert r.assessed_level == "MIDDLE" and s.technical_confirmed == 2 and "TECHNICAL_POOLS_BELOW_MIN" in s.reasons
    assert estimate(V3, ev(weak)).assessed_level == "SENIOR"


def test_ws2_senior_without_confirmed_practice_is_not_senior():
    market = {c: 0.9 for t in ("python-core", "kafka", "fastapi", "ci-cd", "sql", "aws", "docker", "rest-api",
                               "postgresql", "git") for c in RUBRIC[t]}
    evidence = {**market, PR["tradeoffs"]: 0.72, PR["ambiguity"]: 0.72}
    r = estimate(V4, ev(evidence))
    s = r.coverage_by_level["SENIOR"]
    assert r.assessed_level != "SENIOR" and s.practice_confirmed == 0 and "PRACTICE_POOLS_BELOW_MIN" in s.reasons
    assert estimate(V3, ev(evidence)).assessed_level == "SENIOR"


def test_ws3_senior_without_data_layer_senior_capability_is_not_senior():
    sql_only = {**{c: 0.9 for t in ("python-core", "sql", "rest-api", "git", "pytest", "docker", "fastapi", "ci-cd",
                                     "async-python", "aws") for c in RUBRIC[t]}, **{c: 0.9 for c in PRACTICE_CRITERIA}}
    r = estimate(V4, ev(sql_only))
    assert r.assessed_level == "MIDDLE"
    assert r.coverage_by_level["SENIOR"].reasons == ("REQUIRED_CAPABILITY_UNCONFIRMED",)
    assert estimate(V3, ev(sql_only)).assessed_level == "SENIOR"


def test_unresolved_pools_never_fill_a_minimum():
    """v3 counted borderline/untraced pools as assessed (369 of 434 random SENIOR results relied on it)."""
    borderline = {**FULL, **{c: 0.72 for p in S.pools for c in p.members if not c.startswith("practice")}}
    r = estimate(V4, ev(borderline))
    s = r.coverage_by_level["SENIOR"]
    assert s.technical_confirmed == 0 and s.assessed == s.confirmed == 5 and r.assessed_level == "MIDDLE"
    untraced = {c: CriterionEvidence(c, 0.9) for c in FULL}  # scores without evidence turns
    assert estimate(V4, untraced).assessment_status == "INSUFFICIENT_DATA"


def test_senior_minimum_is_four_technical_and_three_practice_pools():
    techs = ("postgresql.migrations", "kafka.semantics", "ci-cd.safety", "aws.iam")
    senior = {**BASE_MID, **{c: 0.9 for c in techs}}
    three = estimate(V4, ev({**senior, **{PR[k]: 0.9 for k in ("tradeoffs", "ambiguity", "ownership")}}))
    assert three.assessed_level == "SENIOR"
    s = three.coverage_by_level["SENIOR"]
    assert (s.technical_confirmed, s.practice_confirmed) == (4, 5)  # BASE_MID confirms rationale and diagnosis too
    fewer = estimate(V4, ev({**senior, "aws.iam": None}))
    assert fewer.assessed_level == "MIDDLE" and "TECHNICAL_POOLS_BELOW_MIN" in fewer.coverage_by_level["SENIOR"].reasons


def test_d9_practice_free_senior_is_impossible_under_v4():
    r = estimate(V4, ev({c: s for c, s in FULL.items() if c not in PRACTICE_CRITERIA}))
    assert r.assessed_level != "SENIOR"
    assert "PRACTICE_POOLS_BELOW_MIN" in r.coverage_by_level["SENIOR"].reasons


# --- D-5: practice by median of per-topic scores ---------------------------------------------------------------------

def test_d5_one_strong_topic_no_longer_outweighs_weak_ones():
    cid = PR["ownership"]
    mixed = {**FULL, cid: 0.9}
    e = ev(mixed)
    e[cid] = CriterionEvidence(cid, 0.9, ("a", "b", "c", "d"), topic_scores=(0.9, 0.3, 0.3, 0.3))
    assert pools(estimate(V4, e))["practice-ownership"] == "GAP"  # median 0.3
    e[cid] = CriterionEvidence(cid, 0.9, ("a", "b"), topic_scores=(0.9, 0.3))
    assert pools(estimate(V4, e))["practice-ownership"] == "UNRESOLVED"  # median 0.6: conflicting topics
    e[cid] = CriterionEvidence(cid, 0.9, ("a",), topic_scores=(0.9,))
    assert pools(estimate(V4, e))["practice-ownership"] == "CONFIRMED"
    e[cid] = CriterionEvidence(cid, 0.9, ())  # no traced topic: never decided
    assert pools(estimate(V4, e))["practice-ownership"] == "UNRESOLVED"


# --- invariants kept ---------------------------------------------------------------------------------------------------

def test_unknown_is_never_a_gap_and_no_evidence_is_not_junior():
    r = estimate(V4, {})
    assert (r.assessed_level, r.assessment_status) == ("UNKNOWN", "INSUFFICIENT_DATA") and r.critical_gaps == ()
    nulls = estimate(V4, ev({c: None for c in FULL}))
    assert nulls.critical_gaps == () and nulls.assessment_status == "INSUFFICIENT_DATA"


def test_hierarchy_unchanged_senior_needs_the_chain():
    only_senior = estimate(V4, ev({c: 0.9 for c in members(S)}))
    assert only_senior.coverage_by_level["SENIOR"].status == "SUPPORTED" and only_senior.assessed_level == "UNKNOWN"


def test_v4_json_carries_capability_fields_and_is_deterministic():
    r = estimate(V4, ev({**FULL, "git.branching": 0.4}))
    data = result_to_json(r)
    assert json.loads(json.dumps(data)) == data and data == result_to_json(estimate(V4, ev({**FULL, "git.branching": 0.4})))
    j = data["coverage_by_level"]["JUNIOR"]
    assert j["tolerated_gap_ids"] == ["git.branching"] and j["technical_confirmed"] == 7 and "declined_ids" in j
    assert all("declined_ids" in p for p in j["pools"])
    v3 = result_to_json(estimate(V3, ev(FULL)))["coverage_by_level"]["SENIOR"]
    assert not {"technical_confirmed", "tolerated_gap_ids", "declined_ids"} & set(v3)


@pytest.mark.parametrize("text,declined", [
    ("Не знаю цього і не працював.", True), ("Я не працювала з Kafka", True), ("Немає досвіду з AWS", True),
    ("I have never used it", True), ("Не знаю, як працює ISR", False), ("Працював, але погано пам'ятаю", False)])
def test_decline_detection_matches_only_no_experience_statements(text, declined):
    assert is_declined(0.0, [text]) is declined
    assert is_declined(0.5, [text]) is False and is_declined(0.0, []) is False
    assert is_declined(0.0, [text, "Використовую partition key для порядку"]) is False


def test_counts_are_not_shares_of_v3():
    assert math.ceil(0.5 * len(S.pools)) == S.min_confirmed == 7 and Level.SENIOR == S.level
