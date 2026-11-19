"""WS-1 fix (owner-approved): a member of a replicated pool (Senior data layer: db-operations, schema-migrations,
hard + required_any) confirms only with two distinct confirming answers; a re-asked borderline answer that is
over-graded once stays borderline. Policy v4 only; v1-v3 goldens live in their own files."""
import random

from backend.api.core import seniority_evidence
from backend.domain.level_probe import continuation_targets
from backend.domain.seniority import CriterionEvidence, estimate
from backend.domain.seniority_policy import PRACTICE_CRITERIA, PYTHON_BACKEND_V4
from tests.test_seniority_policy_v4 import FULL, _GRID, _RANK, ev

V4 = PYTHON_BACKEND_V4
S = V4.rules[2]
OPS, MIG = "postgresql.operations", "postgresql.migrations"


def senior_pools(e):
    return {p.pool_id: p.status for p in estimate(V4, e).coverage_by_level["SENIOR"].pools}


def with_ops(revs):
    """FULL evidence; the Senior data layer only via postgresql.operations with the given (score, turns) revisions."""
    e = ev({**FULL, MIG: None, "django.migrations": None})
    score = next((s for s, _ in reversed(revs)), None)
    turns = tuple(sorted({t for _, ts in revs for t in ts}))
    e[OPS] = CriterionEvidence(OPS, score, turns, scored_turns=tuple(sorted(revs)))
    return e


def test_policy_marks_only_the_senior_data_layer_as_replicated():
    assert S.replicated_pools == ("db-operations", "schema-migrations") == S.hard_pools == S.required_any
    assert all(not r.replicated_pools for r in V4.rules[:2])


def test_one_confirming_answer_is_borderline_two_distinct_answers_confirm():
    assert senior_pools(with_ops([(0.9, ("t1",))]))["db-operations"] == "UNRESOLVED"
    assert senior_pools(with_ops([(0.9, ("t1",)), (0.9, ("t2",))]))["db-operations"] == "CONFIRMED"
    # the same answer re-graded by several revisions is still one answer
    assert senior_pools(with_ops([(0.9, ("t1",)), (0.85, ("t1",))]))["db-operations"] == "UNRESOLVED"
    assert estimate(V4, with_ops([(0.9, ("t1",))])).assessed_level == "MIDDLE"  # required data pool unconfirmed
    assert estimate(V4, with_ops([(0.9, ("t1",)), (0.9, ("t2",))])).assessed_level == "SENIOR"


def test_ws1_borderline_then_lucky_over_grade_is_not_a_confirmation():
    """Re-audit case: 0.57 on the first answer, 0.8 on the re-asked one (latest wins) -> stays UNRESOLVED, not GAP."""
    e = with_ops([(0.57, ("t1",)), (0.8, ("t2",)), (0.8, ("t2",))])
    assert e[OPS].score == 0.8 and senior_pools(e)["db-operations"] == "UNRESOLVED"
    # a turn graded weak by one revision never confirms, even if a later revision quotes it again with a high score
    e = with_ops([(0.57, ("t1",)), (0.8, ("t1", "t2"))])
    assert senior_pools(e)["db-operations"] == "UNRESOLVED"
    e = with_ops([(0.57, ("t1",)), (0.8, ("t2",)), (0.9, ("t3",))])
    assert senior_pools(e)["db-operations"] == "CONFIRMED"


def test_non_replicated_pools_and_lower_levels_still_confirm_from_one_answer():
    one = ev(FULL, turns=("t1",))
    r = estimate(V4, one)
    assert r.coverage_by_level["MIDDLE"].status == "SUPPORTED"
    senior = {p.pool_id: p.status for p in r.coverage_by_level["SENIOR"].pools}
    assert {k for k, v in senior.items() if v != "CONFIRMED"} == {"db-operations", "schema-migrations"}


def test_seniority_evidence_collects_scored_turns_order_independently():
    class Row:
        def __init__(self, cid, score, turn, rev):
            self.action_id, self.criterion_id, self.score, self.revision = "postgresql", cid, score, rev
            self.evidence = [{"turn_id": turn}] if turn else []
            self.no_experience = None

    rows = [Row(OPS, 0.57, "t1", 1), Row(OPS, 0.8, "t2", 2), Row(OPS, None, None, 3)]
    a = seniority_evidence(rows, {"t1": "postgresql", "t2": "postgresql"})[OPS]
    b = seniority_evidence(list(reversed(rows[:2])) + rows[2:], {"t1": "postgresql", "t2": "postgresql"})[OPS]
    assert a.scored_turns == b.scored_turns == ((0.57, ("t1",)), (0.8, ("t2",)))


def _vector(rng):
    out = {}
    for c in FULL:
        if rng.random() < 0.3:
            continue
        if c in PRACTICE_CRITERIA:
            ts = tuple(sorted((rng.choice(_GRID) for _ in range(rng.randint(1, 4))), reverse=True))
            out[c] = CriterionEvidence(c, ts[0], ("t",), topic_scores=ts)
        else:
            revs = tuple(sorted((rng.choice(_GRID), (f"t{rng.randint(1, 3)}",)) for _ in range(rng.randint(1, 3))))
            turns = tuple(sorted({t for _, ts in revs for t in ts}))
            out[c] = CriterionEvidence(c, revs[-1][0], turns, scored_turns=revs)
    return out


def test_property_raising_a_revision_never_lowers_and_order_never_matters():
    rng = random.Random(20261120)
    checks = 0
    for _ in range(3000):
        e = _vector(rng)
        before = _RANK[estimate(V4, e).assessed_level]
        topic = [c for c in e if c not in PRACTICE_CRITERIA]
        c = rng.choice(topic)
        revs = list(e[c].scored_turns)
        i = rng.randrange(len(revs))
        up = [g for g in _GRID if g > revs[i][0]]
        # permutation of the revision order (input order of rows) changes nothing
        shuffled = {**e, c: CriterionEvidence(c, e[c].score, e[c].evidence_turns,
                                              scored_turns=tuple(rng.sample(revs, len(revs))))}
        assert _RANK[estimate(V4, shuffled).assessed_level] == before
        if up:
            revs[i] = (rng.choice(up), revs[i][1])
            score = max(e[c].score, revs[i][0]) if len(revs) > 1 else revs[i][0]
            raised = {**e, c: CriterionEvidence(c, score, e[c].evidence_turns, scored_turns=tuple(sorted(revs)))}
            assert _RANK[estimate(V4, raised).assessed_level] >= before, c
            checks += 1
        extra = {**e, c: CriterionEvidence(c, e[c].score, tuple(sorted({*e[c].evidence_turns, "t9"})),
                                           scored_turns=tuple(sorted([*e[c].scored_turns, (0.9, ("t9",))])))}
        if e[c].score >= 0.75:  # one more confirming answer on a confirmed criterion never lowers the level
            assert _RANK[estimate(V4, extra).assessed_level] >= before, c
    assert checks > 2000


def test_flow_asks_a_second_confirming_question_within_the_caps():
    r = estimate(V4, with_ops([(0.9, ("t1",))]))
    topic = ["postgresql.indexes", "postgresql.transactions", "postgresql.schema", OPS, MIG]
    scores = {c: 0.9 for c in topic} | {MIG: None}
    got = continuation_targets(V4, r, topic, scores, {OPS: 1})
    assert got[:2] == [OPS, MIG]  # the pending second confirmation first, then the unasked member
    assert OPS not in continuation_targets(V4, r, topic, scores, {OPS: 2})  # at most two leading questions
    done = estimate(V4, with_ops([(0.9, ("t1",)), (0.9, ("t2",))]))
    assert OPS not in continuation_targets(V4, done, topic, scores, {OPS: 1})
