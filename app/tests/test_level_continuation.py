"""WP-B (audit D-2, D-6): Python-owned topic continuation for unresolved level-critical criteria, probe order and practice
hints of the next level. Pure: policy v4 + per-criterion evidence, no LLM."""
from backend.domain.level_probe import MAX_ASKS_PER_CRITERION, continuation_targets, practice_gaps, probe_order
from backend.domain.seniority import CriterionEvidence, estimate
from backend.domain.seniority_policy import (PRACTICE_CRITERIA, PYTHON_BACKEND_V1, PYTHON_BACKEND_V3,
                                             PYTHON_BACKEND_V4)

V4 = PYTHON_BACKEND_V4
PG = ["postgresql.indexes", "postgresql.transactions", "postgresql.schema", "postgresql.operations",
      "postgresql.migrations"]
JUNIOR_TECH = {"python-core.idioms": .9, "python-core.errors": .9, "sql.joins": .9, "sql.correctness": .9,
               "rest-api.contract": .9, "docker.images": .9}


def ev(scores: dict[str, float]) -> dict[str, CriterionEvidence]:
    return {c: CriterionEvidence(c, s, ("t1",), False, (s,) if c.startswith("practice") else ())
            for c, s in scores.items()}


def targets(scores, topic=PG, asked=None, policy=V4):
    return continuation_targets(policy, estimate(policy, ev(scores)), topic, scores, asked or {})


def test_lowest_open_level_and_the_next_one_are_probed():
    # nothing known: Junior is the target, so Junior + Middle pools; Senior-only postgresql criteria wait
    assert targets({}) == ["postgresql.indexes", "postgresql.transactions", "postgresql.schema"]
    junior = {**JUNIOR_TECH, "git.branching": .9}
    r = estimate(V4, ev(junior))
    assert r.coverage_by_level["JUNIOR"].status == "SUPPORTED"
    # Junior supported: Middle + Senior pools, so db-operations and schema-migrations are asked too
    assert targets(junior) == PG
    # WS-1 fix: a replicated Senior pool confirmed by one answer only gets its second answer first
    one = {**junior, "postgresql.operations": .9}
    assert targets(one, asked={"postgresql.operations": 1})[0] == "postgresql.operations"


def test_confirmed_weak_and_twice_asked_criteria_do_not_keep_a_topic_open():
    base = {**JUNIOR_TECH, "git.branching": .9}
    assert "postgresql.indexes" not in targets({**base, "postgresql.indexes": .8})  # pool confirmed
    assert "postgresql.transactions" not in targets({**base, "postgresql.transactions": .3})  # weak: not unresolved
    assert "postgresql.schema" in targets({**base, "postgresql.schema": .6})  # borderline gets a follow-up
    assert "postgresql.schema" not in targets({**base, "postgresql.schema": .6},
                                              asked={"postgresql.schema": MAX_ASKS_PER_CRITERION})
    assert "postgresql.schema" in targets(base, asked={"postgresql.schema": MAX_ASKS_PER_CRITERION - 1})


def test_weak_lowest_level_gives_no_escalation():
    weak = {"python-core.idioms": .2, "python-core.errors": .2, "sql.correctness": .2}  # hard Junior gaps
    r = estimate(V4, ev(weak))
    assert r.coverage_by_level["JUNIOR"].status == "GAP"
    assert targets(weak) == []


def test_older_policies_and_no_policy_keep_the_previous_flow():
    assert targets({}, policy=PYTHON_BACKEND_V3) == [] and targets({}, policy=PYTHON_BACKEND_V1) == []
    assert continuation_targets(None, None, PG, {}, {}) == []
    assert continuation_targets(None, estimate(None, {}), PG, {}, {}) == []


def test_probe_order_puts_targets_first_and_keeps_membership():
    unmet = ["postgresql.indexes", "postgresql.migrations", "postgresql.operations", "postgresql.schema"]
    r = estimate(V4, ev({}))
    out = probe_order(unmet, V4, r, ["postgresql.operations", "x.not-open"])
    assert out[0] == "postgresql.operations" and sorted(out) == sorted(unmet)
    assert probe_order(unmet, None, None, []) == unmet


def test_next_level_practice_is_hinted_once_lower_technical_minimum_is_met():
    r = estimate(V4, ev({}))
    assert practice_gaps(V4, r, limit=9) == ["practice-backend.independence"]  # Junior only
    five = {c: s for c, s in JUNIOR_TECH.items() if c != "docker.images"}
    tech = estimate(V4, ev(five))  # 5 Junior technical pools = T^min, but K^min 6 not met: Junior not yet SUPPORTED
    cov = tech.coverage_by_level["JUNIOR"]
    assert cov.status != "SUPPORTED" and cov.technical_confirmed >= V4.rules[0].min_technical
    assert practice_gaps(V4, tech, limit=9) == ["practice-backend.independence", "practice-backend.rationale",
                                                "practice-backend.diagnosis"]
    assert len(practice_gaps(V4, tech)) == 2  # default limit unchanged


def test_senior_practice_including_ownership_and_ambiguity_is_reachable():
    middle = {**JUNIOR_TECH, "git.branching": .9, "practice-backend.independence": .9, "python-core.typing": .9,
              "postgresql.indexes": .9, "postgresql.transactions": .9, "postgresql.schema": .9, "fastapi.async": .9,
              "practice-backend.rationale": .9, "practice-backend.diagnosis": .9}
    r = estimate(V4, ev(middle))
    assert r.coverage_by_level["MIDDLE"].status != "SUPPORTED"  # target level is Middle
    gaps = practice_gaps(V4, r, limit=9)
    assert {"practice-backend.ambiguity", "practice-backend.ownership", "practice-backend.tradeoffs"} <= set(gaps)


def test_borderline_practice_is_hinted_again():
    r = estimate(V4, ev({"practice-backend.independence": .4}))  # .4 < .50: a decided gap, not re-hinted
    assert "practice-backend.independence" not in practice_gaps(V4, r, limit=9)
    tech = {**JUNIOR_TECH, "git.branching": .9, "practice-backend.independence": .9,
            "practice-backend.rationale": .6}  # Middle tau .70: .6 is borderline (UNRESOLVED)
    r = estimate(V4, ev(tech))
    gaps = practice_gaps(V4, r, limit=9)
    assert "practice-backend.rationale" in gaps and gaps.index("practice-backend.rationale") > gaps.index(
        "practice-backend.diagnosis")  # unassessed aspects first
    assert set(gaps) <= set(PRACTICE_CRITERIA)
