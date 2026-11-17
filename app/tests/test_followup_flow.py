"""Follow-ups target concrete open criteria: goal persisted on core_turns, Interviewer sees only open criteria."""
import json
import re
from types import SimpleNamespace

import pytest
from sqlalchemy import select

import backend.api.core as core
from backend.agents.prompts import INTERVIEWER_SYSTEM
from backend.models import CoreTurn, CriterionAssessment

GOAL_REASON = "Немає прикладу керування транзакціями."


class PolicyChat:
    """Evaluator grades by criterion position via `policy(allowed) -> (scores, goal_ids)`; `fail` raises for every call."""

    def __init__(self, policy=None, fail=False, sufficient=False):
        self.policy, self.fail, self.sufficient = policy, fail, sufficient
        self.evaluator_inputs: list[dict] = []
        self.asked = 0

    def invoke(self, messages, *a, **k):
        if self.fail:
            raise ConnectionError("provider down")
        system, human = messages[0].content, messages[1].content
        if system == INTERVIEWER_SYSTEM:
            self.asked += 1
            return SimpleNamespace(content=f"Опишіть випадок номер {'один' if self.asked == 1 else 'інший'} з вашої практики?")
        data = {k: json.loads(v) for k, v in (line.split(": ", 1) for line in human.splitlines()
                                              if re.match(r"(action_id|allowed_criterion_ids|open_criterion_ids): ", line))}
        self.evaluator_inputs.append(data)
        allowed = data["allowed_criterion_ids"]
        turn_id = re.findall(r"turn_id=\"([^\"]+)\"", human)[-1]
        text = json.loads(re.findall(r">(\".*\")</candidate_answer>", human)[-1])
        scores, goal_ids = self.policy(allowed)
        crit = [{"criterion_id": c, "score": scores.get(c), "reason": "з відповіді",
                 "evidence": [{"turn_id": turn_id, "exact_excerpt": text}] if scores.get(c) is not None else []}
                for c in allowed]
        goal = {"criterion_ids": goal_ids, "reason": GOAL_REASON, "expected_evidence": "Конкретний приклад."} if goal_ids else None
        return SimpleNamespace(content=json.dumps({"action_id": data["action_id"], "rubric_version": "v1",
                                                   "criteria": crit, "sufficient_evidence": self.sufficient,
                                                   "needs_followup": bool(goal), "followup_goal": goal}))


@pytest.fixture()
def ask_log(monkeypatch):
    log: list[dict] = []
    real = core.run_ask

    def spy(state, model):
        log.append(state)
        return real(state, model)

    monkeypatch.setattr("backend.api.core.run_ask", spy)
    return log


def _use(monkeypatch, fake):
    monkeypatch.setattr("backend.api.core.get_chat_model", lambda: fake)
    return fake


def _start(client, auth):
    cohort = client.post("/api/v1/cohorts/auto", headers=auth).json()["cohort_id"]
    return client.post("/api/v1/interviews", json={"cohort_id": cohort}, headers=auth).json()


def _next(client, auth, iv, version):
    r = client.post(f"/api/v1/interviews/{iv['id']}/next-question", json={"version": version}, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def _answer(client, auth, iv, q, key):
    r = client.post(f"/api/v1/interviews/{iv['id']}/answers", headers=auth, json={
        "turn_id": q["turn"]["id"], "text": "Створював індекси для повільних запитів.", "version": q["version"],
        "idempotency_key": key})
    assert r.status_code == 200, r.text
    return r.json()


def _turn(db, turn_id) -> CoreTurn:
    with db() as s:
        return s.get(CoreTurn, turn_id)


def test_goal_targets_open_criterion_and_is_persisted(client, auth, db, monkeypatch, ask_log):
    fake = _use(monkeypatch, PolicyChat(lambda allowed: ({allowed[0]: 0.9}, [allowed[1]])))
    iv = _start(client, auth)
    q1 = _next(client, auth, iv, 0)
    assert len(ask_log[0]["unmet_criteria"]) >= 2 and ask_log[0]["followup_goal"] is None
    allowed = ask_log[0]["unmet_criteria"]
    first = _turn(db, q1["turn"]["id"])
    assert first.target_criteria == allowed and first.followup_reason == "OPEN_CRITERIA"
    a1 = _answer(client, auth, iv, q1, "followup-key-0001")
    assert a1["assessment_status"] == "ACCEPTED"
    assert fake.evaluator_inputs[0]["open_criterion_ids"] == allowed
    answered = _turn(db, q1["turn"]["id"])
    assert answered.eval_goal == {"criterion_ids": [allowed[1]], "reason": GOAL_REASON,
                                  "expected_evidence": "Конкретний приклад."}

    q2 = _next(client, auth, iv, a1["version"])
    assert q2["turn"]["action_id"] == q1["turn"]["action_id"]
    state = ask_log[-1]
    assert state["unmet_criteria"] == allowed[1:] and allowed[0] not in state["unmet_criteria"]
    assert state["followup_goal"]["criterion_ids"] == [allowed[1]]
    new = _turn(db, q2["turn"]["id"])
    assert new.target_criteria == [allowed[1]] and new.followup_reason == GOAL_REASON
    _answer(client, auth, iv, q2, "followup-key-0002")
    assert fake.evaluator_inputs[1]["open_criterion_ids"] == allowed[1:]


def test_goal_on_just_confirmed_criterion_is_dropped(client, auth, db, monkeypatch, ask_log):
    _use(monkeypatch, PolicyChat(lambda allowed: ({allowed[0]: 0.9}, [allowed[0]])))
    iv = _start(client, auth)
    q1 = _next(client, auth, iv, 0)
    allowed = ask_log[0]["unmet_criteria"]
    a1 = _answer(client, auth, iv, q1, "followup-key-0011")
    q2 = _next(client, auth, iv, a1["version"])
    assert q2["turn"]["action_id"] == q1["turn"]["action_id"]
    assert ask_log[-1]["followup_goal"] is None
    new = _turn(db, q2["turn"]["id"])
    assert new.target_criteria == allowed[1:] and new.followup_reason == "OPEN_CRITERIA"


def test_all_confirmed_closes_topic_early(client, auth, db, monkeypatch, ask_log):
    # sufficient_evidence false: the old min-two rule would have asked again; no open criterion now closes the topic.
    _use(monkeypatch, PolicyChat(lambda allowed: ({c: 0.9 for c in allowed}, [])))
    iv = _start(client, auth)
    q1 = _next(client, auth, iv, 0)
    first_action = q1["turn"]["action_id"]
    a = _answer(client, auth, iv, q1, "followup-key-0021")
    assert _turn(db, q1["turn"]["id"]).eval_goal is None
    version = a["version"]
    for i in range(3):
        q = _next(client, auth, iv, version)
        if q.get("done"):
            break
        assert q["turn"]["action_id"] != first_action
        version = _answer(client, auth, iv, q, f"followup-key-003{i}")["version"]


def test_provider_failure_is_ungraded_without_goal(client, auth, db, monkeypatch, ask_log):
    _use(monkeypatch, PolicyChat(fail=True))
    iv = _start(client, auth)
    q1 = _next(client, auth, iv, 0)
    assert q1["turn"]["question_source"] == "FALLBACK_UNGRADED"
    first = _turn(db, q1["turn"]["id"])
    assert first.target_criteria is None and first.followup_reason is None
    a1 = _answer(client, auth, iv, q1, "followup-key-0041")
    assert a1["assessment_status"] == "UNGRADED"
    t = _turn(db, q1["turn"]["id"])
    assert t.eval_goal is None
    with db() as s:
        assert s.scalars(select(CriterionAssessment).where(CriterionAssessment.session_id == iv["id"])).all() == []
    q2 = _next(client, auth, iv, a1["version"])
    assert q2["turn"]["question_source"] == "FALLBACK_UNGRADED" and ask_log[-1]["followup_goal"] is None
