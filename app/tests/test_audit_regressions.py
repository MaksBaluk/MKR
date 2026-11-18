"""Audit regressions: evaluator validation (4) and assessment revisions (3). MATH_SPEC §3."""
import itertools

import pytest

from backend.domain.assessment import CriterionResult, EvaluatorOutput, EvidenceRef, validate_against_context
from backend.domain.topic_summary import topic_summary
from tests.test_interview_flow import llm  # noqa: F401
from tests.test_profiles_api import API, mk_profile, start

TURNS = {"t1": "Я використовував індекси та аналізував EXPLAIN."}
ALLOWED = {"a.x", "a.y", "a.z"}


def crit(cid, score, *excerpts, turn="t1"):
    return CriterionResult(criterion_id=cid, score=score, reason="r",
                           evidence=[EvidenceRef(turn_id=turn, exact_excerpt=e) for e in excerpts])


def out(*criteria):
    return EvaluatorOutput(action_id="a", rubric_version="v1", criteria=list(criteria))


# ---- 4. evaluator validation (unit)
def test_valid_output_passes():
    assert validate_against_context(out(crit("a.x", 0.8, "індекси"), crit("a.y", None)), ALLOWED, TURNS) == []


def test_score_without_evidence_rejected():
    assert any("without evidence" in e for e in validate_against_context(out(crit("a.x", 0.9)), ALLOWED, TURNS))


def test_blank_excerpt_rejected():
    errs = validate_against_context(out(crit("a.x", 0.9, "   ")), ALLOWED, TURNS)
    assert errs  # blank excerpt is neither evidence nor a valid quote


def test_duplicate_criterion_rejected():
    errs = validate_against_context(out(crit("a.x", 0.5, "індекси"), crit("a.x", 0.9, "EXPLAIN")), ALLOWED, TURNS)
    assert any("duplicate" in e for e in errs)


def test_unknown_criterion_unknown_turn_and_foreign_quote_rejected():
    assert any("unknown criterion" in e for e in validate_against_context(out(crit("z.q", 0.5, "індекси")), ALLOWED, TURNS))
    assert any("unknown turn" in e for e in validate_against_context(out(crit("a.x", 0.5, "x", turn="t9")), ALLOWED, TURNS))
    assert any("not in turn" in e for e in validate_against_context(out(crit("a.x", 0.5, "вигадана цитата")), ALLOWED, TURNS))


@pytest.mark.parametrize("bad", [1.2, -0.1, float("nan")])
def test_score_out_of_range_rejected(bad):
    assert validate_against_context(out(crit("a.x", bad, "індекси")), ALLOWED, TURNS)


def test_one_strong_criterion_does_not_make_topic_strong():
    rubric = [("a.x", 1.0), ("a.y", 1.0), ("a.z", 1.0), ("a.w", 1.0)]
    t = topic_summary(rubric, {"a.x": 1.0, "a.y": None, "a.z": None, "a.w": None})
    assert t.m == 1.0 and t.e == pytest.approx(0.25)  # score and coverage are separate numbers
    assert not t.overall_level_allowed and set(t.unknown) == {"a.y", "a.z", "a.w"}


# ---- 3. revisions (integration through the API)
_n = itertools.count(1)


def answer_next(client, auth, attempt_id, text):
    version = client.get(f"{API}/interviews/{attempt_id}", headers=auth).json()["version"]
    q = client.post(f"{API}/interviews/{attempt_id}/next-question", json={"version": version}, headers=auth).json()
    assert not q.get("done"), q
    r = client.post(f"{API}/interviews/{attempt_id}/answers", headers=auth, json={
        "turn_id": q["turn"]["id"], "text": text, "version": q["version"], "idempotency_key": f"audit-{next(_n):06d}"})
    assert r.status_code == 200, r.text
    return q["turn"]["action_id"]


def answer_same_action(client, auth, attempt_id, action, text, limit=10):
    """Keep answering until the planner returns to `action` (the min-two-questions rule makes it come back)."""
    for _ in range(limit):
        if answer_next(client, auth, attempt_id, text) == action:
            return
    raise AssertionError("planner never returned to the same action")


@pytest.fixture()
def attempt(client, auth, llm):  # noqa: F811
    p = mk_profile(client, auth)
    return start(client, auth, p["id"]).json()


def snapshot(db, attempt_id, action):
    from backend.api.core import attempt_scores
    from backend.models import CriterionAssessment
    s = db()
    rows = s.query(CriterionAssessment).filter_by(session_id=attempt_id, action_id=action).all()
    return attempt_scores(s, attempt_id), sorted({r.revision for r in rows}), rows


def test_off_topic_and_null_never_erase_confirmed_scores_and_history_is_kept(client, auth, llm, attempt, db):  # noqa: F811
    llm.score = 0.6
    action = answer_next(client, auth, attempt["id"], "Проєктував схеми з індексами й перевіряв EXPLAIN.")
    before, revs, _ = snapshot(db, attempt["id"], action)
    confirmed = {c for c, v in before.items() if v == 0.6}
    assert confirmed and revs == [1]

    llm.off_topic = True  # off-topic answer on the same topic
    answer_same_action(client, auth, attempt["id"], action, "Розкажіть краще анекдот про котів.")
    after, revs2, rows = snapshot(db, attempt["id"], action)
    assert {c: after[c] for c in confirmed} == {c: 0.6 for c in confirmed}  # nothing erased
    assert len(revs2) >= 2 and any(r.score is None and r.revision > 1 for r in rows)  # null revision recorded
    assert any(r.score == 0.6 and r.revision == 1 for r in rows)  # earlier revision still stored


def test_contradicting_answer_is_regraded_over_whole_series(client, auth, llm, attempt, db):  # noqa: F811
    llm.score = 0.6
    action = answer_next(client, auth, attempt["id"], "Профілював запити та будував індекси.")
    llm.score = 0.1  # evaluator re-grades the series after a contradicting answer
    llm.human_inputs.clear()
    answer_same_action(client, auth, attempt["id"], action, "Насправді я ніколи цього не робив.")
    evaluator_input = llm.human_inputs[-1]
    assert "Профілював запити" in evaluator_input and "ніколи цього не робив" in evaluator_input  # whole series
    scores, _, rows = snapshot(db, attempt["id"], action)
    assert all(v == 0.1 for v in scores.values() if v is not None)
    assert any(r.score == 0.6 for r in rows)  # superseded revision stays in history


def test_partial_null_in_new_revision_keeps_earlier_score(client, auth, llm, attempt, db):  # noqa: F811
    llm.score = 0.6
    action = answer_next(client, auth, attempt["id"], "Описав транзакції та ізоляцію.")
    llm.score = None  # new answer evidences nothing: every criterion null, no excerpts needed
    answer_same_action(client, auth, attempt["id"], action, "Ще додам кілька слів без деталей.")
    scores, _, _ = snapshot(db, attempt["id"], action)
    assert all(v == 0.6 for v in scores.values() if v is not None) and any(v == 0.6 for v in scores.values())
