"""Experiment modes in the interview engine: STATIC plan/slots, ablation flags, total budget, caps.

mode_config/static_plan are server-side: set directly on the attempt row, never through the public API."""
import pytest
from sqlalchemy import select

from backend.api.core import criteria_for
from backend.domain.interview_budget import MAX_SHOWN_QUESTIONS_PER_ACTION, MAX_TOPICS
from backend.experiments.config import InterviewMode, config_for
from backend.experiments.planning import slot_targets
from backend.models import CoreInterview, CoreTurn, CriterionAssessment
from tests.test_followup_flow import PolicyChat, _answer, _next, _start, _use

ADAPTIVE = InterviewMode.ADAPTIVE_INTERVIEW
STATIC = InterviewMode.STATIC_INTERVIEW


def strong(allowed, n):
    return {c: 0.95 for c in allowed}, []


def weak(allowed, n):
    return {c: 0.1 for c in allowed}, []


def _configure(db, iv, cfg=None, static_plan=None):
    with db() as s:
        row = s.get(CoreInterview, iv["id"])
        row.mode_config = cfg.to_json() if cfg else None
        row.static_plan = static_plan
        s.commit()


def _row(db, iv) -> CoreInterview:
    with db() as s:
        return s.get(CoreInterview, iv["id"])


def _turns(db, iv) -> list[CoreTurn]:
    with db() as s:
        return list(s.scalars(select(CoreTurn).where(CoreTurn.interview_id == iv["id"]).order_by(CoreTurn.sequence)))


def _run(client, auth, db, monkeypatch, policy, cfg=None, sufficient=True, limit=60, on_first=None):
    """Start an attempt, apply cfg, answer until done; returns (iv, shown turns, last response)."""
    _use(monkeypatch, PolicyChat(policy, sufficient=sufficient))
    iv = _start(client, auth)
    _configure(db, iv, cfg)
    version, last = iv["version"], None
    for i in range(limit):
        last = _next(client, auth, iv, version)
        if i == 0 and on_first is not None:
            on_first(iv)
        if last.get("done"):
            break
        version = _answer(client, auth, iv, last, f"modes-{iv['id'][:8]}-{i:04d}")["version"]
    assert last.get("done"), "interview did not finish within the limit"
    return iv, _turns(db, iv), last


def _topics(turns) -> list[str]:
    return list(dict.fromkeys(t.action_id for t in turns))


def _per_topic(turns) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in turns:
        out[t.action_id] = out.get(t.action_id, 0) + 1
    return out


def test_no_config_behaves_as_before(client, auth, db, monkeypatch):
    _use(monkeypatch, PolicyChat(strong, sufficient=True))
    a = _start(client, auth)
    first_none = _next(client, auth, a, 0)["turn"]
    assert _row(db, a).mode_config is None and _row(db, a).static_plan is None
    b = _start(client, auth)
    _configure(db, b, config_for(ADAPTIVE))
    first_adaptive = _next(client, auth, b, 0)["turn"]
    assert first_adaptive["action_id"] == first_none["action_id"]
    ta, tb = _turns(db, a)[0], _turns(db, b)[0]
    assert (ta.target_criteria, ta.followup_reason, ta.difficulty, ta.difficulty_reason) == \
        (tb.target_criteria, tb.followup_reason, tb.difficulty, tb.difficulty_reason)
    assert _row(db, b).static_plan is None  # adaptive topics never build a static plan


@pytest.mark.parametrize("policy", [strong, weak], ids=["strong", "weak"])
def test_static_plan_fixed_before_first_question(client, auth, db, monkeypatch, policy):
    stored = {}

    def capture(iv):
        stored["plan"] = _row(db, iv).static_plan
        assert _turns(db, iv)[0].answer_text is None  # stored before any answer exists

    iv, turns, _ = _run(client, auth, db, monkeypatch, policy, config_for(STATIC), on_first=capture)
    plan = stored["plan"]
    assert plan and plan["topics"] and plan["questions_per_topic"] == 2
    assert _row(db, iv).static_plan == plan  # never rewritten after answers
    assert _topics(turns) == plan["topics"]  # the sequence of topics follows the plan, whatever the answers


def test_static_schedule_independent_of_answers(client, auth, db, monkeypatch):
    _, strong_turns, _ = _run(client, auth, db, monkeypatch, strong, config_for(STATIC))
    _, weak_turns, _ = _run(client, auth, db, monkeypatch, weak, config_for(STATIC))
    assert [(t.action_id, t.target_criteria, t.difficulty) for t in strong_turns] == \
        [(t.action_id, t.target_criteria, t.difficulty) for t in weak_turns]


def test_adaptive_plan_can_differ_after_answers(client, auth, db, monkeypatch):
    s_iv, static_turns, _ = _run(client, auth, db, monkeypatch, strong, config_for(STATIC))
    plan = _row(db, s_iv).static_plan["topics"]
    _, adaptive_turns, _ = _run(client, auth, db, monkeypatch, weak, config_for(ADAPTIVE))
    assert _topics(static_turns) == plan
    assert _topics(adaptive_turns) != plan  # failed groups change what the planner opens next


def test_static_asks_fixed_slots_without_goal(client, auth, db, monkeypatch, request):
    log: list[dict] = []
    import backend.api.core as core
    real = core.run_ask
    monkeypatch.setattr("backend.api.core.run_ask", lambda state, model: (log.append(state), real(state, model))[1])
    # strong, sufficient first answer plus an Evaluator goal: adaptive would close or follow the goal; static does neither
    iv, turns, _ = _run(client, auth, db, monkeypatch, lambda allowed, n: ({c: 0.95 for c in allowed}, [allowed[-1]]),
                        config_for(STATIC, static_questions_per_topic=3))
    k = 3
    with db() as s:
        for a, n in _per_topic(turns).items():
            assert n == k
            crit = criteria_for(s, a)
            mine = [t for t in turns if t.action_id == a]
            for i, t in enumerate(mine):
                assert tuple(t.target_criteria) == (slot_targets(crit, k, i) or tuple(crit))
                assert t.followup_reason == "STATIC_SLOT"
                assert t.difficulty_reason.startswith("FIXED:")
    assert log and all(state["followup_goal"] is None for state in log)
    assert len({t.difficulty for t in turns}) == 1  # no controller step on strong answers


def _fingerprint(turns):
    return {"topics": _topics(turns), "targets": [t.target_criteria for t in turns],
            "reasons": [t.followup_reason for t in turns], "difficulty": [t.difficulty_reason for t in turns]}


@pytest.mark.parametrize("flag", ["adaptive_topics", "adaptive_followup", "adaptive_difficulty"])
def test_ablation_flags_are_independent(client, auth, db, monkeypatch, flag):
    # weak answers: adaptive difficulty steps down, the planner sees failed groups, follow-ups are owed
    base_iv, base_turns, _ = _run(client, auth, db, monkeypatch, weak, config_for(ADAPTIVE))
    iv, turns, _ = _run(client, auth, db, monkeypatch, weak, config_for(ADAPTIVE, **{flag: False}))
    base, got = _fingerprint(base_turns), _fingerprint(turns)
    plan = _row(db, iv).static_plan
    if flag == "adaptive_topics":
        assert plan is not None and got["topics"] == plan["topics"][:len(got["topics"])]
        assert "STATIC_SLOT" not in got["reasons"] and not any(r.startswith("FIXED:") for r in got["difficulty"])
    else:
        assert plan is None
    if flag == "adaptive_followup":
        assert set(got["reasons"]) == {"STATIC_SLOT"}
        assert set(_per_topic(turns).values()) == {2}
        assert not any(r.startswith("FIXED:") for r in got["difficulty"])
    else:
        assert "STATIC_SLOT" not in got["reasons"]
    if flag == "adaptive_difficulty":
        assert all(r.startswith("FIXED:") for r in got["difficulty"])
        assert len({t.difficulty for t in turns}) == 1
        # only difficulty changed: topics, targets and follow-up reasons equal the full adaptive run
        assert (got["topics"], got["targets"], got["reasons"]) == (base["topics"], base["targets"], base["reasons"])
    else:
        assert not any(r.startswith("FIXED:") for r in got["difficulty"])
        assert len({t.difficulty for t in base_turns}) > 1  # the adaptive baseline does step on weak answers


@pytest.mark.parametrize("mode", [STATIC, ADAPTIVE])
def test_total_budget_finishes_interview_and_keeps_nulls(client, auth, db, monkeypatch, mode):
    iv, turns, last = _run(client, auth, db, monkeypatch, lambda allowed, n: ({allowed[0]: 0.8}, []),
                           config_for(mode, total_budget=3))
    assert len(turns) == 3 and last["done"] is True and last["status"] == "FINISHED"
    assert _row(db, iv).status == "FINISHED"
    asked = {t.action_id for t in turns}
    with db() as s:
        rows = s.scalars(select(CriterionAssessment).where(CriterionAssessment.session_id == iv["id"])).all()
        assert rows and {r.action_id for r in rows} <= asked  # never-asked topics get no rows at all
        for r in rows:
            assert r.score is None or r.criterion_id == criteria_for(s, r.action_id)[0]  # no fabricated 0
            assert r.score != 0


@pytest.mark.parametrize("cfg", [config_for(STATIC, static_questions_per_topic=5),
                                 config_for(ADAPTIVE), config_for(STATIC, max_topics=3, max_per_topic=2,
                                                                  static_questions_per_topic=2),
                                 config_for(ADAPTIVE, max_topics=3, max_per_topic=2)],
                         ids=["static-k5", "adaptive", "static-small", "adaptive-small"])
def test_caps_hold_in_static_and_adaptive(client, auth, db, monkeypatch, cfg):
    # goal on the last criterion every time: adaptive would keep asking up to the per-topic cap
    _, turns, _ = _run(client, auth, db, monkeypatch, lambda allowed, n: ({allowed[0]: 0.9}, [allowed[-1]]), cfg,
                       sufficient=False, limit=80)
    per = _per_topic(turns)
    assert len(per) <= min(cfg.max_topics, MAX_TOPICS)
    assert max(per.values()) <= min(cfg.max_per_topic, MAX_SHOWN_QUESTIONS_PER_ACTION)
