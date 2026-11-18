"""Professional-practice criteria graded in the same Evaluator call (Task 3): validation, storage, isolation."""
import itertools
import json
import re
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.agents.graphs import run_answer
from backend.agents.prompts import EVALUATOR_SYSTEM, INTERVIEWER_SYSTEM, format_evaluator_input
from backend.api.core import (_revisions, action_summary, attempt_scores, cohort_actions, practice_criteria_for,
                              rubric_map)
from backend.api.recommendations import rank_items
from backend.domain.core_flow import planner_state
from backend.domain.seniority_policy import PRACTICE_ACTION, PRACTICE_CRITERIA
from backend.models import CohortSnapshot, CriterionAssessment, Rubric

API = "/api/v1"
_keys = itertools.count(1)
ANSWER = "Я обрав індекс, бо запит сканував усю таблицю, і перевірив план через EXPLAIN."


class PracticeChat:
    """Interviewer/Evaluator stub: grades every allowed topic criterion and every requested practice criterion."""

    def __init__(self, score=0.6, practice=0.8):
        self.score, self.practice = score, practice
        self.human_inputs: list[str] = []

    def invoke(self, messages, *a, **k):
        system, human = messages[0].content, messages[1].content
        self.human_inputs.append(human)
        if system == INTERVIEWER_SYSTEM:
            return SimpleNamespace(content="Опишіть, як ви проєктували схему бази даних?")
        data = dict(line.split(": ", 1) for line in human.splitlines() if re.match(r"\w+: ", line))
        turn_id = re.findall(r"turn_id=\"([^\"]+)\"", human)[-1]
        text = json.loads(re.findall(r">(\".*\")</candidate_answer>", human)[-1])

        def item(c, score):
            ev = [] if score is None else [{"turn_id": turn_id, "exact_excerpt": text}]
            return {"criterion_id": c, "score": score, "reason": "з відповіді", "evidence": ev}

        practice = json.loads(data["practice_criterion_ids"]) if "practice_criterion_ids" in data else []
        return SimpleNamespace(content=json.dumps({
            "action_id": json.loads(data["action_id"]), "rubric_version": "v1", "off_topic": False,
            "criteria": [item(c, self.score) for c in json.loads(data["allowed_criterion_ids"])],
            "practice": [item(c, self.practice) for c in practice]}))


@pytest.fixture()
def chat(monkeypatch):
    fake = PracticeChat()
    monkeypatch.setattr("backend.api.core.get_chat_model", lambda: fake)
    return fake


def _profile(client, auth, track):
    r = client.post(f"{API}/profiles", json={"name": f"Профіль {track}", "track": track, "target_level": "middle",
                                             "years_experience": 3}, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _attempt(client, auth, track):
    pid = _profile(client, auth, track)
    r = client.post(f"{API}/profiles/{pid}/attempts", headers=auth)
    assert r.status_code in (200, 201), r.text
    return {**r.json(), "profile_id": pid}


def _answer(client, auth, iv, version, text=ANSWER):
    q = client.post(f"{API}/interviews/{iv['id']}/next-question", json={"version": version}, headers=auth).json()
    a = client.post(f"{API}/interviews/{iv['id']}/answers", headers=auth, json={
        "turn_id": q["turn"]["id"], "text": text, "version": q["version"],
        "idempotency_key": f"practice-{next(_keys):08d}"}).json()
    assert a["assessment_status"] == "ACCEPTED", a
    return q["turn"]["action_id"], a["version"]


def _rows(db, iv_id, practice: bool):
    with db() as s:
        rows = s.scalars(select(CriterionAssessment).where(CriterionAssessment.session_id == iv_id)
                         .order_by(CriterionAssessment.created_at, CriterionAssessment.revision)).all()
    return [r for r in rows if (r.action_id == PRACTICE_ACTION) == practice]


# ---- graph-level validation
def _output(practice, off_topic=False):
    crit = [{"criterion_id": "a.x", "score": 0.6, "reason": "р", "evidence": [{"turn_id": "t1", "exact_excerpt": "індекс"}]}]
    return json.dumps({"action_id": "a", "rubric_version": "v1", "off_topic": off_topic, "criteria": crit,
                       "practice": practice})


class _Model:
    def __init__(self, raw):
        self.raw, self.calls = raw, 0

    def invoke(self, messages, *a, **k):
        self.calls += 1
        return SimpleNamespace(content=self.raw)


def _state():
    return {"action_id": "a", "rubric_version": "v1", "allowed_criterion_ids": ["a.x"], "bands": None,
            "turns": {"t1": ANSWER}, "allowed_practice_ids": list(PRACTICE_CRITERIA), "practice_bands": None}


def _p(cid, score=0.7, excerpt="індекс", turn="t1"):
    return {"criterion_id": cid, "score": score, "reason": "р",
            "evidence": [] if excerpt is None else [{"turn_id": turn, "exact_excerpt": excerpt}]}


@pytest.mark.parametrize("practice", [
    [_p("practice-backend.unknown")],
    [_p("practice-backend.rationale"), _p("practice-backend.rationale")],
    [_p("practice-backend.rationale", excerpt=None)],
    [_p("practice-backend.rationale", excerpt="цього немає у відповіді")],
    [_p("practice-backend.rationale", score=1.5)],
], ids=["unknown", "duplicate", "no-quote", "invented-quote", "out-of-range"])
def test_practice_scores_require_evidence_and_known_ids(practice):
    model = _Model(_output(practice))
    result = run_answer(_state(), model)
    assert result.status == "UNGRADED" and result.reason == "INVALID" and model.calls == 2


def test_practice_rejected_when_not_requested():
    model = _Model(_output([_p("practice-backend.rationale")]))
    state = {**_state(), "allowed_practice_ids": []}
    assert run_answer(state, model).status == "UNGRADED"


def test_valid_practice_accepted_and_optional():
    ok = run_answer(_state(), _Model(_output([_p("practice-backend.rationale"), _p("practice-backend.diagnosis", None, None)])))
    assert ok.status == "ACCEPTED" and [c.score for c in ok.output.practice] == [0.7, None]
    assert ok.output.criteria[0].score == 0.6  # practice never changes a topic criterion
    legacy = json.loads(_output([]))
    legacy.pop("practice")
    assert run_answer(_state(), _Model(json.dumps(legacy))).output.practice == []


def test_off_topic_nulls_practice():
    result = run_answer(_state(), _Model(_output([_p("practice-backend.rationale")], off_topic=True)))
    assert result.status == "ACCEPTED" and result.off_topic
    assert all(c.score is None and c.evidence == [] for c in result.output.practice + result.output.criteria)


def test_evaluator_prompt_carries_practice_only_when_requested():
    base = dict(action_id="a", rubric_version="v1", allowed_criterion_ids=["a.x"], bands=None, turns={"t1": "x"})
    assert "practice_criterion_ids" not in format_evaluator_input(**base)
    text = format_evaluator_input(**base, practice_criterion_ids=["practice-backend.rationale"],
                                  practice_bands={"practice-backend.rationale": "Обґрунтування"})
    assert 'practice_criterion_ids: ["practice-backend.rationale"]' in text and "practice_bands: " in text
    assert "practice" in EVALUATOR_SYSTEM and "never" in EVALUATOR_SYSTEM.split("practice", 1)[1]


# ---- API storage and isolation
def test_practice_rows_stored_under_practice_action(client, auth, db, chat):
    iv = _attempt(client, auth, "python")
    action, _ = _answer(client, auth, iv, iv["version"])
    practice, topic = _rows(db, iv["id"], True), _rows(db, iv["id"], False)
    assert sorted(r.criterion_id for r in practice) == sorted(PRACTICE_CRITERIA)
    assert {r.revision for r in practice} == {1} and all(r.score == 0.8 and r.evidence for r in practice)
    with db() as s:
        rubric = s.scalar(select(Rubric).where(Rubric.action_id == PRACTICE_ACTION, Rubric.version == "v1"))
    assert {r.rubric_id for r in practice} == {rubric.id}
    assert topic and {r.action_id for r in topic} == {action} and all(r.score == 0.6 for r in topic)
    assert 'practice_criterion_ids: ' in chat.human_inputs[-1]


def test_practice_not_requested_for_marketing_track(client, auth, db, chat):
    iv = _attempt(client, auth, "marketing")
    _answer(client, auth, iv, iv["version"])
    evaluator_inputs = [h for h in chat.human_inputs if "allowed_criterion_ids" in h]
    assert evaluator_inputs and all("practice_criterion_ids" not in h for h in evaluator_inputs)
    assert _rows(db, iv["id"], True) == []


def test_practice_criteria_for_tracks(db):
    with db() as s:
        assert practice_criteria_for(s, "python") == sorted(PRACTICE_CRITERIA)
        assert practice_criteria_for(s, "marketing") == [] and practice_criteria_for(s, "design") == []
        assert practice_criteria_for(s, None) == []


def test_null_practice_revision_does_not_erase_score(client, auth, db, chat):
    iv = _attempt(client, auth, "python")
    _, v = _answer(client, auth, iv, iv["version"])
    chat.practice = None
    _answer(client, auth, iv, v)
    practice = _rows(db, iv["id"], True)
    assert {r.revision for r in practice} == {1, 2}
    with db() as s:
        scores = attempt_scores(s, iv["id"])
    assert all(scores[c] == 0.8 for c in PRACTICE_CRITERIA)


def test_practice_never_enters_planner_or_ranking_inputs(client, auth, db, chat):
    iv = _attempt(client, auth, "python")
    _answer(client, auth, iv, iv["version"])
    with db() as s:
        scores = attempt_scores(s, iv["id"])
        assert all(scores[c] == 0.8 for c in PRACTICE_CRITERIA)  # attempt_scores keeps topic + practice criteria
        topic_only = {k: v for k, v in scores.items() if not k.startswith(f"{PRACTICE_ACTION}.")}
        snap = s.get(CohortSnapshot, iv["cohort_id"])
        revisions = _revisions(snap)
        assert PRACTICE_ACTION not in cohort_actions(revisions)

        def ranking(sc):
            return [(i["vacancy_id"], i["label"], i["z"], i["confirmed_share"]) for i in rank_items(s, 3, snap, sc)]

        assert ranking(scores) == ranking(topic_only)
        plan = lambda sc: planner_state(revisions, sc, rubric_map(s, cohort_actions(revisions), sc))  # noqa: E731
        assert plan(scores) == plan(topic_only)
        rows = _rows(db, iv["id"], True) + _rows(db, iv["id"], False)
        assert PRACTICE_ACTION not in action_summary(rows, rubric_map(s, {r.action_id for r in rows}, scores))
    rec = client.post(f"{API}/recommendations", json={"cohort_id": iv["cohort_id"]}, headers=auth).json()
    assert rec["assessed_actions"] == sum(1 for v in topic_only.values() if v is not None)
    state = client.get(f"{API}/interviews/{iv['id']}", headers=auth).json()
    r = client.post(f"{API}/interviews/{iv['id']}/finish", json={"version": state["version"]}, headers=auth)
    assert r.status_code == 200, r.text
    res = client.get(f"{API}/profiles/{iv['profile_id']}/results", params={"fitting": "all"}, headers=auth).json()
    assert res["competencies"] and all(c["action_id"] != PRACTICE_ACTION for c in res["competencies"])
