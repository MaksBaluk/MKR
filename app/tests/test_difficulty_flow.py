"""DifficultyController wired into next_question: difficulty chosen, persisted with its reason and state, and passed
to the Interviewer and Evaluator as context only. The candidate-facing turn never shows it."""
import json

import pytest

from backend.agents.prompts import EVALUATOR_SYSTEM, INTERVIEWER_SYSTEM
from backend.models import CandidateProfile, CoreTurn
from tests.test_followup_flow import PolicyChat, _answer, _next, _start, _turn, _use


class SpyChat(PolicyChat):
    """PolicyChat that also records the raw Interviewer and Evaluator inputs."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.interviewer_humans: list[str] = []
        self.evaluator_humans: list[str] = []

    def invoke(self, messages, *a, **k):
        system, human = messages[0].content, messages[1].content
        (self.interviewer_humans if system == INTERVIEWER_SYSTEM else self.evaluator_humans).append(human)
        return super().invoke(messages, *a, **k)


def _set_level(db, level):
    with db() as s:
        for p in s.query(CandidateProfile).all():
            p.target_level = level
        s.commit()


@pytest.fixture()
def spy(monkeypatch):
    return _use(monkeypatch, SpyChat(lambda allowed, n: ({allowed[0]: 0.6}, [])))


@pytest.mark.parametrize("level, expected", [("junior", "BASIC"), ("senior", "ADVANCED")])
def test_first_question_difficulty_from_level(client, auth, db, spy, level, expected):
    iv = _start(client, auth)
    _set_level(db, level)
    q1 = _next(client, auth, iv, 0)
    t = _turn(db, q1["turn"]["id"])
    assert t.difficulty == expected and t.difficulty_reason == f"LEVEL:{level}"
    assert t.controller_before == {"level": expected, "shown": 0, "history": []}
    assert t.controller_after == {"level": expected, "shown": 1, "history": [expected]}
    assert f"difficulty: {expected}" in spy.interviewer_humans[-1]


def test_interviewer_prompt_defines_levels():
    p = INTERVIEWER_SYSTEM
    for name in ("BASIC", "INTERMEDIATE", "ADVANCED"):
        assert f"- {name}:" in p
    assert "follow `difficulty`, never mention it" in p


def test_evaluator_gets_turn_meta_and_no_score_rule(client, auth, db, spy):
    iv = _start(client, auth)
    _set_level(db, "junior")
    q1 = _next(client, auth, iv, 0)
    _answer(client, auth, iv, q1, "difficulty-key-0001")
    t = _turn(db, q1["turn"]["id"])
    line = next(x for x in spy.evaluator_humans[-1].splitlines() if x.startswith("turn_meta"))
    meta = json.loads(line.split(": ", 1)[1])
    assert meta == {t.id: {"difficulty": "BASIC", "target_criteria": t.target_criteria}}
    assert "question difficulty must not raise or lower a score" in EVALUATOR_SYSTEM


def test_second_question_replays_controller_state(client, auth, db, spy):
    iv = _start(client, auth)
    _set_level(db, "junior")
    q1 = _next(client, auth, iv, 0)
    a1 = _answer(client, auth, iv, q1, "difficulty-key-0011")
    q2 = _next(client, auth, iv, a1["version"])
    assert q2["turn"]["action_id"] == q1["turn"]["action_id"]  # min-two rule: 0.6 is not an early close
    t = _turn(db, q2["turn"]["id"])
    assert t.controller_before == {"level": "BASIC", "shown": 1, "history": ["BASIC"]}
    assert t.difficulty == "BASIC" and t.difficulty_reason in ("PARTIAL", "NO_EVIDENCE")
    assert t.controller_after["shown"] == 2 and t.controller_after["history"] == ["BASIC", "BASIC"]


def test_legacy_null_difficulty_restarts(client, auth, db, spy):
    iv = _start(client, auth)
    _set_level(db, "senior")
    q1 = _next(client, auth, iv, 0)
    a1 = _answer(client, auth, iv, q1, "difficulty-key-0021")
    with db() as s:  # pre-phase-2 turn: no recorded difficulty or controller state
        legacy = s.get(CoreTurn, q1["turn"]["id"])
        legacy.difficulty = legacy.difficulty_reason = legacy.controller_before = legacy.controller_after = None
        s.commit()
    q2 = _next(client, auth, iv, a1["version"])
    assert q2["turn"]["action_id"] == q1["turn"]["action_id"]
    t = _turn(db, q2["turn"]["id"])
    assert t.difficulty == "ADVANCED" and t.difficulty_reason == "LEGACY_RESTART"
    assert t.controller_before == {"level": "ADVANCED", "shown": 1, "history": []}


def test_bank_fallback_still_gets_difficulty(client, auth, db, monkeypatch):
    _use(monkeypatch, PolicyChat(fail=True))
    iv = _start(client, auth)
    _set_level(db, "junior")
    q1 = _next(client, auth, iv, 0)
    t = _turn(db, q1["turn"]["id"])
    assert q1["turn"]["question_source"] == "FALLBACK_UNGRADED"
    assert t.difficulty == "BASIC" and t.difficulty_reason == "FALLBACK:LEVEL:junior"
    assert t.controller_after["shown"] == 1


def test_turn_dict_hides_difficulty_while_db_stores_it(client, auth, db, spy):
    iv = _start(client, auth)
    q1 = _next(client, auth, iv, 0)
    assert not [k for k in q1["turn"] if k.startswith(("difficulty", "controller_"))]
    t = _turn(db, q1["turn"]["id"])
    assert t.difficulty in ("BASIC", "INTERMEDIATE", "ADVANCED") and t.difficulty_reason
    assert t.controller_before is not None and t.controller_after is not None
    got = client.get(f"/api/v1/interviews/{iv['id']}", headers=auth).json()
    assert "difficulty" not in json.dumps(got) and "controller_" not in json.dumps(got)
