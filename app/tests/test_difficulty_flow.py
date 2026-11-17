"""DifficultyController wired into next_question: difficulty chosen, persisted with its reason and state, and passed
to the Interviewer and Evaluator as context only. The candidate-facing turn never shows it."""
import json
from types import SimpleNamespace

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
    assert t.difficulty == "BASIC" and t.difficulty_reason == "PARTIAL"
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


class LongInterviewer(PolicyChat):
    """Interviewer output is always rejected (two questions), so every question comes from the bank."""

    def invoke(self, messages, *a, **k):
        if messages[0].content == INTERVIEWER_SYSTEM:
            return SimpleNamespace(content="Що ви робили? Чому саме так?")
        return super().invoke(messages, *a, **k)


def test_strong_sufficient_bank_answer_closes_topic_early(client, auth, db, monkeypatch):
    # every criterion graded (no null keeps sufficient_evidence), topic m >= 0.75, the last one stays WEAK (open)
    _use(monkeypatch, LongInterviewer(lambda allowed, n: ({c: 0.95 for c in allowed[:-1]} | {allowed[-1]: 0.6}, []),
                                      sufficient=True))
    iv = _start(client, auth)
    q1 = _next(client, auth, iv, 0)
    assert q1["turn"]["question_source"] == "FALLBACK_UNGRADED"
    assert _turn(db, q1["turn"]["id"]).target_criteria is None
    a1 = _answer(client, auth, iv, q1, "difficulty-key-0031")
    assert a1["assessment_status"] == "ACCEPTED"
    q2 = _next(client, auth, iv, a1["version"])
    assert q2.get("done") or q2["turn"]["action_id"] != q1["turn"]["action_id"]  # a new topic, not a 2nd question


# ---- Integration scenarios: real endpoints, scripted Evaluator --------------------------------------------------------

def _script(rows, *, sufficient=True):
    """PolicyChat whose n-th evaluation is rows[min(n, len) - 1] = (scores by criterion position, goal position or None).
    Criteria not listed score null."""
    def policy(allowed, n):
        scores, goal = rows[min(n, len(rows)) - 1]
        return ({allowed[i]: s for i, s in scores.items() if i < len(allowed)},
                [allowed[goal]] if goal is not None and goal < len(allowed) else [])
    return PolicyChat(policy, sufficient=sufficient)


def _uniform(score, k=40):
    return {i: score for i in range(k)}


def _play(client, auth, iv, n, prefix):
    """Answer up to n questions in a row; returns the shown turn dicts."""
    out, version = [], iv["version"]
    for i in range(n):
        q = _next(client, auth, iv, version)
        if q.get("done"):
            break
        out.append(q["turn"])
        version = _answer(client, auth, iv, q, f"{prefix}-{i:04d}")["version"]
    return out


def _stored(db, shown):
    return [_turn(db, t["id"]) for t in shown]


def test_junior_strong_answers_progress_basic_to_advanced(client, auth, db, monkeypatch):
    # every criterion graded each time (so evidence stays sufficient); row(n, goal): the first n criteria score strong,
    # the rest stay weak/open; `goal` is the open criterion the next follow-up targets
    def row(strong_n, goal):
        return {i: 0.95 if i < strong_n else 0.7 for i in range(40)}, goal
    strong = row(1, 1), row(2, 2), row(3, 3)
    _use(monkeypatch, _script(list(strong)))
    iv = _start(client, auth)
    _set_level(db, "junior")
    turns = _stored(db, _play(client, auth, iv, 3, "adv"))
    assert len({t.action_id for t in turns}) == 1
    assert [t.difficulty for t in turns] == ["BASIC", "INTERMEDIATE", "ADVANCED"]
    assert [t.difficulty_reason for t in turns][1:] == ["STRONG", "STRONG"]
    crit = turns[0].target_criteria  # q1 targets all, each later turn the one criterion the previous answer left open
    assert [t.target_criteria for t in turns[1:]] == [[crit[1]], [crit[2]]]
    assert turns[0].target_criteria == crit and len(crit) >= 4


def test_senior_weak_answer_gets_diagnostic_question(client, auth, db, monkeypatch):
    _use(monkeypatch, _script([(_uniform(0.2), 0)]))
    iv = _start(client, auth)
    _set_level(db, "senior")
    turns = _stored(db, _play(client, auth, iv, 4, "dia"))
    assert [t.difficulty for t in turns] == ["ADVANCED", "INTERMEDIATE", "BASIC", "BASIC"]
    assert [t.difficulty_reason for t in turns][1:] == ["WEAK", "WEAK", "WEAK"]
    assert all(t.difficulty != "ADVANCED" for t in turns[1:])  # never below BASIC, never back up


def test_incomplete_answer_follows_up_same_level_on_open_criterion(client, auth, db, monkeypatch):
    _use(monkeypatch, _script([({0: 0.1}, 1)]))  # first criterion graded (weak), the rest null
    iv = _start(client, auth)
    _set_level(db, "middle")
    q1, q2 = _stored(db, _play(client, auth, iv, 2, "inc"))
    assert q1.action_id == q2.action_id
    assert q2.difficulty == q1.difficulty == "INTERMEDIATE" and q2.difficulty_reason == "PARTIAL"
    assert q2.followup_reason and q2.target_criteria == [q1.target_criteria[1]]  # a null criterion, not the graded one
    assert q1.target_criteria[0] not in q2.target_criteria


def test_uncertain_answer_no_level_change(client, auth, db, monkeypatch):
    _use(monkeypatch, _script([({}, None)]))
    iv = _start(client, auth)
    _set_level(db, "middle")
    q1, q2 = _stored(db, _play(client, auth, iv, 2, "unc"))
    assert q2.action_id == q1.action_id
    assert q2.difficulty == q1.difficulty == "INTERMEDIATE" and q2.difficulty_reason == "NO_EVIDENCE"
    assert q2.controller_before["level"] == "INTERMEDIATE"


def test_good_candidate_does_not_spend_five_questions(client, auth, db, monkeypatch):
    _use(monkeypatch, _script([(_uniform(0.95), None)]))
    iv = _start(client, auth)
    shown = _play(client, auth, iv, 6, "good")
    per_topic: dict[str, int] = {}
    for t in shown:
        per_topic[t["action_id"]] = per_topic.get(t["action_id"], 0) + 1
    assert shown and per_topic[shown[0]["action_id"]] < 5
    assert len(per_topic) > 1  # moved on to other topics instead of repeating the first


def test_caps_hold_with_controller(client, auth, db, monkeypatch):
    # endless partial answers with a goal on an open criterion: the controller keeps following up, the caps stop it
    _use(monkeypatch, _script([({0: 0.6, 1: 0.6}, 0)]))
    iv = _start(client, auth)
    shown = _play(client, auth, iv, 80, "caps")
    assert len(shown) < 80, "interview never finished"
    per_topic: dict[str, int] = {}
    for t in shown:
        per_topic[t["action_id"]] = per_topic.get(t["action_id"], 0) + 1
    assert max(per_topic.values()) == 5 and len(per_topic) == 10  # both caps are actually reached, never exceeded


def test_tau_not_changed_by_level(client, auth, db, monkeypatch):
    from backend.api.core import attempt_scores
    from backend.api.recommendations import rank_items
    from backend.models import CohortSnapshot, CoreInterview

    results = {}
    for score in (0.8, 0.6):  # two score levels: thresholds stay fixed across a range of scores
        for level in ("junior", "senior"):
            _use(monkeypatch, _script([(_uniform(score), None)]))
            iv = _start(client, auth)
            _set_level(db, level)
            _play(client, auth, iv, 3, f"tau-{level}-{score}")
            with db() as s:
                snap = s.get(CohortSnapshot, s.get(CoreInterview, iv["id"]).cohort_id)
                scores = attempt_scores(s, iv["id"])
                items = rank_items(s, 3, snap, scores)
            results[score, level] = (scores, [(i["vacancy_id"], i["z"], i["x"], i["l_mandatory"], i["l_preferred"])
                                              for i in items])
    for score in (0.8, 0.6):
        jr, sr = results[score, "junior"], results[score, "senior"]
        assert jr[0] and jr[0] == sr[0]  # same assessments in
        assert jr[1] and jr[1] == sr[1]  # same Z/X/L out
        assert any(row[3] > 0 or row[4] > 0 for row in jr[1])  # not trivially zero
    assert results[0.8, "junior"][1] != results[0.6, "junior"][1]  # the scores do move the values
