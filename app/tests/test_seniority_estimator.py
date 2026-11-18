import json
from inspect import signature

import pytest

import backend.domain.seniority as seniority
from backend.domain.criteria import epsilon
from backend.domain.seniority import CriterionEvidence, estimate, result_to_json
from backend.domain.seniority_policy import (
    PYTHON_BACKEND_V1, Level, LevelRule, SeniorityPolicy, policy_for)

JUNIOR, MIDDLE, SENIOR = (r.critical for r in PYTHON_BACKEND_V1.rules)


def ev(scores: dict[str, float | None], turns: tuple[str, ...] = ("t1",)) -> dict[str, CriterionEvidence]:
    return {cid: CriterionEvidence(cid, s, turns if s is not None else ()) for cid, s in scores.items()}


def all_of(ids, score):
    return {cid: score for cid in ids}


def test_one_of_five_criteria_confirms_nothing():
    r = estimate(PYTHON_BACKEND_V1, ev({"postgresql.transactions": 0.95}))
    assert (r.assessed_level, r.assessment_status, r.highest_supported_level) == ("UNKNOWN", "INSUFFICIENT_DATA", "UNKNOWN")
    assert "postgresql.indexes" in r.unassessed_criteria and "postgresql.indexes" not in r.critical_gaps
    assert r.coverage_by_level["MIDDLE"].status == "UNVERIFIED"
    assert r.coverage_by_level["MIDDLE"].confirmed == 1 and r.critical_gaps == ()


def test_unknown_is_not_a_gap():
    r = estimate(PYTHON_BACKEND_V1, ev(all_of(JUNIOR, None)))
    j = r.coverage_by_level["JUNIOR"]
    assert (j.status, j.assessed, j.gaps, j.gap_ids) == ("UNVERIFIED", 0, 0, ())
    assert r.critical_gaps == () and set(JUNIOR) <= set(r.unassessed_criteria)
    assert r.assessment_status == "INSUFFICIENT_DATA"


def test_established_gap_differs_from_missing_evidence():
    base = all_of(JUNIOR + MIDDLE, 0.8)
    gap = estimate(PYTHON_BACKEND_V1, ev({**base, "redis.reliability": 0.2}))
    s = gap.coverage_by_level["SENIOR"]
    assert (s.status, s.gap_ids) == ("GAP", ("redis.reliability",))
    assert gap.assessed_level == "MIDDLE" and gap.critical_gaps == ("redis.reliability",)
    assert any("Для Senior виявлено критичні прогалини: redis.reliability" in line for line in gap.explanation)
    unknown = estimate(PYTHON_BACKEND_V1, ev({**base, "redis.reliability": None}))
    assert unknown.coverage_by_level["SENIOR"].status == "UNVERIFIED"
    assert "redis.reliability" in unknown.unassessed_criteria and unknown.critical_gaps == ()


def test_junior_requires_minimum_coverage_never_default():
    empty = estimate(PYTHON_BACKEND_V1, {})
    assert (empty.assessed_level, empty.assessment_status) == ("UNKNOWN", "INSUFFICIENT_DATA")
    partial = estimate(PYTHON_BACKEND_V1, ev(all_of(JUNIOR[:6], 0.9)))  # 6/9 < 0.75
    assert partial.assessed_level == "UNKNOWN"
    assert "ASSESSED_SHARE_BELOW_MIN" in partial.coverage_by_level["JUNIOR"].reasons


def test_middle_confirmed_senior_unverified_sentence():
    r = estimate(PYTHON_BACKEND_V1, ev(all_of(JUNIOR + MIDDLE, 0.8)))
    assert (r.assessed_level, r.assessment_status) == ("MIDDLE", "ASSESSED")
    assert r.coverage_by_level["SENIOR"].status == "UNVERIFIED"
    assert any("Підтверджено Middle за перевіреними критеріями. Для висновку про Senior недостатньо даних" in line
               for line in r.explanation)
    assert "postgresql.operations" in r.unassessed_criteria


def test_high_basics_do_not_compensate_unverified_critical_senior():
    senior_part = [c for c in SENIOR if c not in MIDDLE][:9]  # + diagnosis, rationale = 11/15 < 0.8
    r = estimate(PYTHON_BACKEND_V1, ev({**all_of(JUNIOR + MIDDLE, 1.0), **all_of(senior_part, 1.0)}))
    s = r.coverage_by_level["SENIOR"]
    assert (s.assessed, s.status) == (11, "UNVERIFIED")
    assert r.assessed_level == "MIDDLE" and r.highest_supported_level == "MIDDLE"


def test_senior_requires_all_hierarchical_levels():
    r = estimate(PYTHON_BACKEND_V1, ev(all_of(SENIOR, 0.95)))
    assert r.coverage_by_level["SENIOR"].status == "SUPPORTED"
    assert r.coverage_by_level["JUNIOR"].status == "UNVERIFIED"
    assert (r.assessed_level, r.highest_supported_level) == ("UNKNOWN", "SENIOR")
    assert r.assessment_status == "INSUFFICIENT_DATA"


def test_full_chain_yields_senior():
    r = estimate(PYTHON_BACKEND_V1, ev(all_of(JUNIOR + MIDDLE + SENIOR, 0.9)))
    assert (r.assessed_level, r.assessment_status) == ("SENIOR", "ASSESSED")
    assert any("Підтверджено Senior за перевіреними критеріями" in line for line in r.explanation)
    assert r.unassessed_criteria == () and r.critical_gaps == ()


def test_secondary_high_scores_do_not_offset_a_critical_gap():
    scores = {**all_of(JUNIOR, 0.9), "sql.joins": 0.3, "python-core.generators": 0.99, "docker.images": 0.99}
    r = estimate(PYTHON_BACKEND_V1, ev(scores))
    j = r.coverage_by_level["JUNIOR"]
    assert (j.status, j.gap_ids, j.confirmed) == ("GAP", ("sql.joins",), 8)
    assert (r.assessed_level, r.assessment_status) == ("UNKNOWN", "GAPS_AT_JUNIOR")
    assert "sql.joins" in r.critical_gaps and "python-core.generators" not in r.confirmed_strengths


def test_tau_epsilon_borderline_is_unresolved_not_gap():
    tau = PYTHON_BACKEND_V1.rules[0].tau
    border = estimate(PYTHON_BACKEND_V1, ev({**all_of(JUNIOR, 0.9), "sql.joins": tau - epsilon(tau)}))
    j = border.coverage_by_level["JUNIOR"]
    assert (j.assessed, j.confirmed, j.gaps, j.status) == (9, 8, 0, "SUPPORTED")
    assert "sql.joins" not in border.critical_gaps + border.confirmed_strengths + border.unassessed_criteria
    below = estimate(PYTHON_BACKEND_V1, ev({**all_of(JUNIOR, 0.9), "sql.joins": tau - epsilon(tau) - 0.001}))
    assert below.coverage_by_level["JUNIOR"].status == "GAP" and "sql.joins" in below.critical_gaps


def test_score_without_evidence_turn_is_not_counted_confirmed():
    evidence = ev(all_of(JUNIOR, 0.9))
    for cid in JUNIOR[:3]:
        evidence[cid] = CriterionEvidence(cid, 0.9, ())
    r = estimate(PYTHON_BACKEND_V1, evidence)
    j = r.coverage_by_level["JUNIOR"]
    assert (j.assessed, j.confirmed, j.status) == (9, 6, "UNVERIFIED")
    assert JUNIOR[0] not in r.confirmed_strengths and JUNIOR[0] not in r.evidence_references
    assert r.evidence_references[JUNIOR[5]] == ("t1",)


def test_min_competencies_blocks_single_competency_proof():
    rule = LevelRule(Level.JUNIOR, 0.5, 0.75, 0.75, 4, ("a.x", "a.y", "b.x", "practice-backend.independence"))
    policy = SeniorityPolicy("toy", "v0", "python", "WORKING_ASSUMPTION", (rule,))
    r = estimate(policy, ev(all_of(rule.critical, 0.9)))
    j = r.coverage_by_level["JUNIOR"]
    assert (j.confirmed, j.competencies_confirmed, j.status) == (4, 2, "UNVERIFIED")
    assert "TOO_FEW_COMPETENCIES" in j.reasons and r.assessed_level == "UNKNOWN"
    real = {**all_of(JUNIOR, 0.9), "rest-api.contract": None, "git.branching": None}  # 7/9, 3 competencies
    jr = estimate(PYTHON_BACKEND_V1, ev(real)).coverage_by_level["JUNIOR"]
    assert (jr.competencies_confirmed, jr.status) == (3, "UNVERIFIED")


def test_estimator_has_no_desired_level_years_or_self_rating_parameter():
    assert set(signature(estimate).parameters) == {"policy", "evidence"}


def test_deterministic_and_json_safe():
    scores = {**all_of(JUNIOR + MIDDLE, 0.8), "redis.reliability": 0.2, "celery.idempotency": 0.9}
    a = result_to_json(estimate(PYTHON_BACKEND_V1, ev(scores)))
    b = result_to_json(estimate(PYTHON_BACKEND_V1, ev(dict(reversed(list(scores.items()))))))
    assert a == b and json.dumps(a) == json.dumps(b)
    assert a["assessed_level"] == "MIDDLE" and type(a["coverage_by_level"]["SENIOR"]["level"]) is str


def test_independent_of_vacancy_and_ranking_inputs():
    base = all_of(JUNIOR + MIDDLE, 0.8)
    extra = {**base, "docker.images": 0.0, "kubernetes.pods": 1.0}  # non-policy criteria (vacancy-side E_c)
    assert result_to_json(estimate(PYTHON_BACKEND_V1, ev(base))) == result_to_json(estimate(PYTHON_BACKEND_V1, ev(extra)))
    imported = {getattr(v, "__name__", "") for v in vars(seniority).values()}
    assert not any(n.startswith(("backend.domain.ranking", "backend.domain.market", "sqlalchemy")) for n in imported)


def test_no_policy_marketing():
    r = estimate(policy_for("marketing"), ev({"seo.audit": 0.9}))
    assert (r.assessed_level, r.highest_supported_level, r.assessment_status) == ("UNKNOWN", "UNKNOWN", "POLICY_UNAVAILABLE")
    assert r.explanation == ("Для цього напряму рівень не визначається: потрібна експертна валідація рубрик",)
    assert (r.policy_id, r.policy_version, r.coverage_by_level) == (None, None, {})
    assert estimate(policy_for("unknown-track"), {}).assessment_status == "POLICY_UNAVAILABLE"


@pytest.mark.parametrize("bad", [1.2, -0.1, float("nan")])
def test_out_of_range_score_rejected(bad):
    with pytest.raises(ValueError):
        estimate(PYTHON_BACKEND_V1, ev({"sql.joins": bad}))


def test_low_score_without_evidence_turn_is_unresolved_not_gap():
    evidence = ev(all_of(JUNIOR, 0.9))
    evidence[JUNIOR[0]] = CriterionEvidence(JUNIOR[0], 0.1, ())  # a number nobody can trace to an answer
    r = estimate(PYTHON_BACKEND_V1, evidence)
    j = r.coverage_by_level["JUNIOR"]
    assert (j.assessed, j.confirmed, j.gaps) == (9, 8, 0) and j.status != "GAP"
    assert JUNIOR[0] not in r.critical_gaps + r.confirmed_strengths + r.unassessed_criteria
    traced = dict(evidence, **{JUNIOR[0]: CriterionEvidence(JUNIOR[0], 0.1, ("t9",))})
    assert JUNIOR[0] in estimate(PYTHON_BACKEND_V1, traced).critical_gaps


@pytest.mark.parametrize("desired", ["junior", "senior"])
def test_middle_confirmed_even_if_desired_junior_or_senior(desired):
    """The desired level is not an estimator input: the same evidence gives MIDDLE whatever the candidate wanted."""
    evidence = ev(all_of(JUNIOR + MIDDLE, 0.8))
    assert "desired" not in " ".join(signature(estimate).parameters)
    r = estimate(PYTHON_BACKEND_V1, evidence)
    assert (r.assessed_level, r.assessment_status) == ("MIDDLE", "ASSESSED")
    assert r.coverage_by_level["MIDDLE"].status == "SUPPORTED" and r.coverage_by_level["SENIOR"].status == "UNVERIFIED"
    assert r.explanation[0] == "Підтверджено Middle за перевіреними критеріями. Для висновку про Senior недостатньо даних."
