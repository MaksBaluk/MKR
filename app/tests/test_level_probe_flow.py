"""Level probing inside real interviews (Task 4): caps, budget, Q_t order and evidence rules stay untouched."""
import json
import re
from types import SimpleNamespace

import pytest
from sqlalchemy import select

import backend.api.core as core
from backend.agents.prompts import INTERVIEWER_SYSTEM
from backend.domain.interview_budget import MAX_SHOWN_QUESTIONS_PER_ACTION, MAX_TOPICS
from backend.domain.seniority import estimate
from backend.domain.seniority_policy import PRACTICE_ACTION, PYTHON_BACKEND_V1, PYTHON_BACKEND_V2
from backend.experiments.config import InterviewMode, config_for
from backend.experiments.providers import CandidateSpec, ScriptedProvider
from backend.experiments.runner import run_experiment
from backend.models import CoreTurn, CriterionAssessment
from tests.test_followup_flow import PolicyChat, _use

ADAPTIVE = InterviewMode.ADAPTIVE_INTERVIEW
PRACTICE_SCORED = "practice-backend.independence"


def cand(track="python"):
    return CandidateSpec(candidate_id="c1", desired_title="Python Developer", years_experience=3, target_level="middle",
                         track=track, location="Київ", work_mode="remote", self_ratings={})


GOOD = ScriptedProvider({"c1": {"default": "Налаштовував індекси та транзакції в PostgreSQL для сервісу замовлень."}})


class ProbeChat(PolicyChat):
    """PolicyChat that also grades one practice criterion when the Evaluator is asked for practice criteria."""

    def invoke(self, messages, *a, **k):
        resp = super().invoke(messages, *a, **k)
        human = messages[1].content
        if messages[0].content == INTERVIEWER_SYSTEM or "practice_criterion_ids: " not in human:
            return resp
        ids = json.loads(re.search(r"^practice_criterion_ids: (.*)$", human, re.M).group(1))
        turn_id = re.findall(r"turn_id=\"([^\"]+)\"", human)[-1]
        text = json.loads(re.findall(r">(\".*\")</candidate_answer>", human)[-1])
        out = json.loads(resp.content)
        out["practice"] = [{"criterion_id": c, "score": 0.8 if c == PRACTICE_SCORED else None, "reason": "з відповіді",
                            "evidence": [{"turn_id": turn_id, "exact_excerpt": text}] if c == PRACTICE_SCORED else []}
                           for c in ids]
        return SimpleNamespace(content=json.dumps(out))


def mixed(allowed, n):
    """First criterion of a topic strong, the rest weak: topics stay open, so follow-ups target the weak ones."""
    return {c: (0.95 if i == 0 else 0.4) for i, c in enumerate(allowed)}, []


@pytest.fixture()
def ask_log(monkeypatch):
    log: list[dict] = []
    real = core.run_ask

    def spy(state, model):
        log.append(state)
        return real(state, model)

    monkeypatch.setattr("backend.api.core.run_ask", spy)
    return log


def _run(client, db, monkeypatch, eid, policy=mixed, track="python", **over):
    _use(monkeypatch, ProbeChat(policy))
    with db() as s:
        return run_experiment(eid, config_for(ADAPTIVE, **over), cand(track), GOOD, client, s)


def _caps(rec):
    per: dict[str, int] = {}
    for q in rec.qa:
        per[q["action_id"]] = per.get(q["action_id"], 0) + 1
    return per


def test_interview_never_exceeds_caps_with_level_probing(client, db, monkeypatch, ask_log):
    rec = _run(client, db, monkeypatch, "probe-caps")
    per = _caps(rec)
    assert rec.qa and len(per) <= MAX_TOPICS and max(per.values()) <= MAX_SHOWN_QUESTIONS_PER_ACTION
    assert any(s.get("practice_gaps") for s in ask_log)  # probing was active on the python track
    assert all(len(s.get("practice_gaps") or []) <= 2 for s in ask_log)
    assert len(ask_log) == len(rec.qa)  # one Interviewer run per shown question, no extra calls
    budget = _run(client, db, monkeypatch, "probe-budget", total_budget=4)
    assert len(budget.qa) <= 4 and len(_caps(budget)) <= MAX_TOPICS


def test_no_question_targets_criterion_with_sufficient_evidence(client, db, monkeypatch, ask_log):
    rec = _run(client, db, monkeypatch, "probe-targets")
    with db() as s:
        turns = s.scalars(select(CoreTurn).where(CoreTurn.interview_id == rec.interview_id)
                          .order_by(CoreTurn.sequence)).all()
        rows = s.scalars(select(CriterionAssessment).where(CriterionAssessment.session_id == rec.interview_id)).all()
    strong = {r.criterion_id for r in rows if r.score is not None and r.score >= 0.9}
    assert strong
    confirmed: set[str] = set()
    practice_scored = False
    for t, state in zip(turns, ask_log):
        assert not (set(t.target_criteria or []) & confirmed), t.sequence  # an earlier answer confirmed it
        assert not (set(state["unmet_criteria"]) & confirmed)
        assert not any(c.startswith(f"{PRACTICE_ACTION}.") for c in state["unmet_criteria"])
        if practice_scored:
            assert PRACTICE_SCORED not in (state.get("practice_gaps") or [])
        confirmed |= {r.criterion_id for r in rows if r.action_id == t.action_id and r.criterion_id in strong
                      and r.score is not None and r.score >= 0.9}
        practice_scored = True  # the first evaluation already graded the practice criterion


def test_q_t_choice_identical_with_and_without_probing(client, db, monkeypatch, ask_log):
    probed = _run(client, db, monkeypatch, "probe-on")
    monkeypatch.setattr("backend.api.core.prioritize_unmet", lambda unmet, policy, result: list(unmet))
    monkeypatch.setattr("backend.api.core.practice_gaps", lambda *a, **k: [])
    plain = _run(client, db, monkeypatch, "probe-off")
    key = [(q["action_id"], q["ordinal_in_topic"], q["difficulty"]) for q in probed.qa]
    assert key == [(q["action_id"], q["ordinal_in_topic"], q["difficulty"]) for q in plain.qa]
    assert [sorted(q["target_criteria"] or []) for q in probed.qa] == [sorted(q["target_criteria"] or [])
                                                                       for q in plain.qa]
    assert [r["vacancy_id"] for r in probed.ranking] == [r["vacancy_id"] for r in plain.ranking]


def test_budget_exhausted_leaves_level_unknown_not_guessed(client, db, monkeypatch, ask_log):
    rec = _run(client, db, monkeypatch, "probe-short", policy=lambda allowed, n: ({c: 0.95 for c in allowed}, []),
               total_budget=2)
    assert len(rec.qa) <= 2
    with db() as s:
        rows = s.scalars(select(CriterionAssessment).where(CriterionAssessment.session_id == rec.interview_id)
                         .order_by(CriterionAssessment.created_at, CriterionAssessment.revision)).all()
        topics = {t.id: t.action_id for t in s.scalars(select(CoreTurn).where(CoreTurn.interview_id == rec.interview_id))}
    assert all(r.score != 0 for r in rows)  # unasked criteria are never stored as 0
    r = estimate(PYTHON_BACKEND_V1, core.seniority_evidence(rows, topics))
    assert (r.assessed_level, r.assessment_status) == ("UNKNOWN", "INSUFFICIENT_DATA")
    assert r.critical_gaps == () and r.unassessed_criteria
    v2 = estimate(PYTHON_BACKEND_V2, core.seniority_evidence(rows, topics))  # the current policy: same honest outcome
    assert (v2.assessed_level, v2.assessment_status) == ("UNKNOWN", "INSUFFICIENT_DATA")
    assert v2.critical_gaps == () and v2.unassessed_criteria


def test_track_without_policy_sends_no_practice_gaps(client, db, monkeypatch, ask_log):
    rec = _run(client, db, monkeypatch, "probe-marketing", track="marketing")
    assert rec.qa and ask_log
    assert all(not s.get("practice_gaps") for s in ask_log)


def test_followup_goal_wins_over_practice_gaps(client, db, monkeypatch, ask_log):
    def goal_on_weak(allowed, n):
        scores = {c: (0.95 if i == 0 else 0.4) for i, c in enumerate(allowed)}
        return scores, [allowed[-1]] if len(allowed) > 1 else []

    _use(monkeypatch, PolicyChat(goal_on_weak))  # practice never graded: practice gaps stay open all interview
    with db() as s:
        rec = run_experiment("probe-goal", config_for(ADAPTIVE), cand(), GOOD, client, s)
    with_goal = [s for s in ask_log if s.get("followup_goal")]
    assert rec.qa and with_goal and any(s.get("practice_gaps") for s in ask_log)
    assert all(not s.get("practice_gaps") for s in with_goal)  # the goal's criterion, not practice, drives the question
