"""Policy python-backend/v3 (§3e): v2 pools with lower Senior thresholds; v1 and v2 stay byte-identical and addressable."""
import hashlib
import json
import math
from pathlib import Path

import pytest

from backend.domain.level_probe import practice_gaps, prioritize_unmet
from backend.domain.seniority import CriterionEvidence, estimate, result_to_json
from backend.domain.seniority_policy import (
    PRACTICE_CRITERIA, POLICY_VERSIONS, PYTHON_BACKEND_V1, PYTHON_BACKEND_V2, PYTHON_BACKEND_V3, policy_by_version,
    policy_for)
from backend.seed import read_fixture
from tests.seniority_v1_cases import V2_IDS, cases

V2, V3 = PYTHON_BACKEND_V2, PYTHON_BACKEND_V3
RUBRIC = {r["action_id"]: [c["criterion_id"] for c in r["criteria"]] for r in read_fixture("rubrics.json")["rubrics"]}
# The topics Q_t picks on the full python cohort, in the order of a measured interview (scripts/seniority_reachability.py).
MARKET = ("python-core", "kafka", "fastapi", "ci-cd", "sql", "aws", "docker", "postgresql")
PRACTICE = {c: 0.9 for c in PRACTICE_CRITERIA}


def ev(scores: dict[str, float]) -> dict[str, CriterionEvidence]:
    return {c: CriterionEvidence(c, s, ("t1",)) for c, s in scores.items()}


def topics(names, score=0.9) -> dict[str, float]:
    return {c: score for t in names for c in RUBRIC[t]}


# --- registry ------------------------------------------------------------------------------------------------------

def test_registry_current_is_v3_and_older_versions_stay_addressable():
    assert policy_for("python") is V3 and (V3.policy_id, V3.version, V3.track, V3.status) == (
        "python-backend", "v3", "python", "WORKING_ASSUMPTION")
    assert policy_by_version("python-backend", "v1") is PYTHON_BACKEND_V1
    assert policy_by_version("python-backend", "v2") is V2
    assert policy_by_version("python-backend", "v3") is V3
    assert set(POLICY_VERSIONS) == {("python-backend", v) for v in ("v1", "v2", "v3")}
    assert policy_for("marketing") is None and policy_for("design") is None


def test_v3_is_v2_with_lower_senior_counts_only():
    j2, m2, s2 = V2.rules
    j3, m3, s3 = V3.rules
    assert (j3, m3) == (j2, m2)  # Junior and Middle rules identical to v2
    assert (s3.level, s3.tau, s3.pools, s3.critical) == (s2.level, s2.tau, s2.pools, s2.critical)
    assert (s3.min_assessed_share, s3.min_confirmed_share) == (0.0, 0.0)  # pooled rules: the counts decide
    n = len(s3.pools)
    assert n == 14 and (s3.min_assessed, s3.min_confirmed) == (math.ceil(0.60 * n), math.ceil(0.50 * n)) == (9, 7)
    assert (s2.min_assessed, s2.min_confirmed, s2.min_competencies) == (11, 10, 4)  # v2 untouched
    assert s3.min_competencies == 3
    # A single topic confirms at most two Senior pools, so min_competencies 3 always needs three different tools.
    per_topic = {t: sum(any(m.split(".", 1)[0] == t for m in p.members) for p in s3.pools) for t in RUBRIC}
    assert max(per_topic.values()) == 2


# --- v1 and v2 stay byte-identical -----------------------------------------------------------------------------------

def test_v2_results_byte_identical_to_golden():
    golden = json.loads((Path(__file__).parent / "data" / "seniority_v2_golden.json").read_text())
    got = []
    for e in cases(ids=V2_IDS):
        r = estimate(V2, e)
        got.append({"result": result_to_json(r), "prioritized": prioritize_unmet(V2_IDS, V2, r),
                    "practice_gaps": practice_gaps(V2, r, limit=9)})
    assert len(got) == golden["cases"] == 91
    assert [[g["result"]["assessed_level"], g["result"]["assessment_status"]] for g in got] == golden["levels"]
    blob = json.dumps(got, ensure_ascii=False, sort_keys=True).encode()
    assert hashlib.sha256(blob).hexdigest() == golden["sha256"]


# --- Senior reachability (measured on the market topics) -------------------------------------------------------------

@pytest.mark.parametrize("k", [6, 7, 8])
def test_v3_senior_with_six_market_topics_and_practice(k):
    r = estimate(V3, ev(topics(MARKET[:k]) | PRACTICE))
    assert (r.assessed_level, r.assessment_status) == ("SENIOR", "ASSESSED")


def test_v3_five_topics_stay_middle_and_v2_needs_more():
    five = estimate(V3, ev(topics(MARKET[:5]) | PRACTICE))
    assert five.assessed_level == "MIDDLE"
    assert five.coverage_by_level["SENIOR"].reasons[0] == "ASSESSED_COUNT_BELOW_MIN"
    six_v2 = estimate(V2, ev(topics(MARKET[:6]) | PRACTICE))
    assert six_v2.assessed_level == "MIDDLE"  # the same evidence under v2: Senior needs 8 topics
    assert estimate(V2, ev(topics(MARKET[:8]) | PRACTICE)).assessed_level == "SENIOR"


def test_v3_market_topics_without_practice_are_never_senior():
    """Q_t never picks the concurrency/incident tools on the system cohort, so at most 7 non-practice Senior pools are
    assessable there and 9 assessed pools need practice evidence."""
    for k in range(1, len(MARKET) + 1):
        assert estimate(V3, ev(topics(MARKET[:k]))).assessed_level != "SENIOR"
    all_market = estimate(V3, ev(topics(MARKET + ("django", "git", "redis", "rest-api"))))
    assert all_market.coverage_by_level["SENIOR"].assessed == 7 and all_market.assessed_level != "SENIOR"


def test_v3_weak_senior_practice_is_a_gap_not_senior():
    weak = {c: 0.3 for c in ("practice-backend.tradeoffs", "practice-backend.ambiguity", "practice-backend.ownership")}
    r = estimate(V3, ev(topics(MARKET) | PRACTICE | weak))
    assert r.assessed_level == "MIDDLE" and r.coverage_by_level["SENIOR"].status == "GAP"
    assert set(weak) <= set(r.coverage_by_level["SENIOR"].gap_ids)


def test_v3_two_tools_never_make_senior_coverage():
    """kafka + aws + all practice: 9 assessed, 9 confirmed Senior pools, but only 2 tools (min_competencies 3)."""
    r = estimate(V3, ev(topics(("kafka", "aws")) | PRACTICE))
    s = r.coverage_by_level["SENIOR"]
    assert (s.assessed, s.confirmed, s.competencies_confirmed) == (9, 9, 2)
    assert s.status != "SUPPORTED" and "TOO_FEW_COMPETENCIES" in s.reasons
    assert estimate(V3, ev(topics(("postgresql",)) | PRACTICE)).coverage_by_level["SENIOR"].status != "SUPPORTED"


def test_v3_senior_still_needs_the_middle_chain():
    """Senior coverage alone (no Junior/Middle evidence) never yields SENIOR: hierarchy unchanged."""
    r = estimate(V3, ev(topics(("kafka", "aws", "ci-cd")) | PRACTICE))
    assert r.coverage_by_level["SENIOR"].status == "SUPPORTED"
    assert r.assessed_level != "SENIOR" and r.coverage_by_level["MIDDLE"].status != "SUPPORTED"


def test_v3_no_data_layer_evidence_is_unknown():
    r = estimate(V3, ev(topics(("python-core", "kafka", "fastapi", "ci-cd", "aws", "docker")) | PRACTICE))
    assert r.assessed_level == "UNKNOWN" and r.coverage_by_level["JUNIOR"].status == "UNVERIFIED"


def test_v3_same_tool_gap_is_never_hidden():
    strong = {c: 0.9 for rule in V3.rules for c in rule.critical}
    r = estimate(V3, ev({**strong, "python-core.errors": 0.1, "sql.correctness": 0.1}))
    assert (r.assessed_level, r.assessment_status) == ("UNKNOWN", "GAPS_AT_JUNIOR")


def test_v3_weak_answers_stay_gaps_at_junior():
    r = estimate(V3, ev(topics(MARKET, 0.3) | {c: 0.3 for c in PRACTICE_CRITERIA}))
    assert (r.assessed_level, r.assessment_status) == ("UNKNOWN", "GAPS_AT_JUNIOR")


def test_v3_estimate_is_deterministic():
    e = cases(ids=V2_IDS)[7]
    assert result_to_json(estimate(V3, e)) == result_to_json(estimate(V3, e))
