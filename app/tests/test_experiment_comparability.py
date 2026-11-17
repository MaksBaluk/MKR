"""Mode comparability and reproducibility: A/B/C share inputs and budget; STATIC plan ignores answers; ranking is replayable."""
import ast
import random
from pathlib import Path

import pytest

import backend
from backend.experiments.config import InterviewMode, config_for
from backend.experiments.providers import CandidateSpec, ScriptedProvider
from backend.experiments.runner import rerank, run_experiment
from backend.models import CoreInterview
from tests.test_followup_flow import PolicyChat, _use

INITIAL = InterviewMode.INITIAL_PROFILE
STATIC = InterviewMode.STATIC_INTERVIEW
ADAPTIVE = InterviewMode.ADAPTIVE_INTERVIEW
BUDGET = 8
CAND = CandidateSpec(candidate_id="c1", desired_title="Python Developer", years_experience=3, target_level="middle",
                     track="python", location="Київ", work_mode="remote", self_ratings={})
GOOD = ScriptedProvider({"c1": {"default": "Налаштовував індекси та транзакції в PostgreSQL для сервісу замовлень."}})
POOR = ScriptedProvider({"c1": {"default": "Не працював з цим."}})


def strong(allowed, n):
    return {c: 0.95 for c in allowed}, []


def weak(allowed, n):
    return {c: 0.1 for c in allowed}, []


def _run(client, db, monkeypatch, mode, policy=strong, provider=GOOD, eid="cmp", **over):
    _use(monkeypatch, PolicyChat(policy, sufficient=True))
    over = {"total_budget": BUDGET, **over} if mode is not INITIAL else {}
    with db() as s:
        return run_experiment(eid, config_for(mode, **over), CAND, None if mode is INITIAL else provider, client, s)


def _schedule(rec, with_difficulty=False):
    return [(q["action_id"], q["ordinal_in_topic"]) + ((q["difficulty"],) if with_difficulty else ()) for q in rec.qa]


@pytest.fixture()
def abc(client, db, monkeypatch):
    return {m: _run(client, db, monkeypatch, m) for m in (INITIAL, STATIC, ADAPTIVE)}


def test_same_initial_data_for_all_modes(abc):
    recs = list(abc.values())
    assert len({r.cohort_sha256 for r in recs}) == 1 and recs[0].cohort_sha256 and len(recs[0].cohort_sha256) == 64
    assert all(r.profile_snapshot["track"] == "python" and r.profile_snapshot["years_experience"] == 3 for r in recs)
    profiles = [{k: v for k, v in r.profile_snapshot.items() if k != "profile_id"} for r in recs]
    assert profiles[0] == profiles[1] == profiles[2]
    assert recs[1].rubric_versions and recs[1].rubric_versions == recs[2].rubric_versions
    assert {v for r in recs for v in r.rubric_versions.values()} <= {"v1", "auto-1"}
    assert recs[1].prompt_version == recs[2].prompt_version and recs[1].algorithm_version == recs[2].algorithm_version
    assert {i["vacancy_id"] for i in recs[0].ranking} == {i["vacancy_id"] for i in recs[1].ranking} \
        == {i["vacancy_id"] for i in recs[2].ranking}


def test_static_and_adaptive_share_budget_and_caps(abc, db):
    s, a = abc[STATIC], abc[ADAPTIVE]
    assert s.config["total_budget"] == a.config["total_budget"] == BUDGET
    assert s.config["max_topics"] == a.config["max_topics"] <= 10
    assert s.config["max_per_topic"] == a.config["max_per_topic"] <= 5
    for r in (s, a):
        per: dict[str, int] = {}
        for q in r.qa:
            per[q["action_id"]] = per.get(q["action_id"], 0) + 1
        assert 0 < len(r.qa) <= BUDGET and len(per) <= 10 and max(per.values()) <= 5
        assert all(1 <= q["ordinal_in_topic"] <= 5 for q in r.qa)
    with db() as sess:
        assert sess.get(CoreInterview, s.interview_id).static_plan is not None
        assert sess.get(CoreInterview, a.interview_id).static_plan is None


def test_static_plan_identical_for_different_answer_scripts(client, db, monkeypatch):
    s1 = _run(client, db, monkeypatch, STATIC, strong, GOOD)
    s2 = _run(client, db, monkeypatch, STATIC, weak, POOR)
    assert s1.qa and _schedule(s1) == _schedule(s2)
    assert s1.qa[0]["answer_text"] != s2.qa[0]["answer_text"]  # the scripts really differed
    assert [q["answer_text"] for q in s1.qa] != [q["answer_text"] for q in s2.qa]
    with db() as sess:
        plans = [sess.get(CoreInterview, r.interview_id).static_plan for r in (s1, s2)]
    assert plans[0] == plans[1]
    # sensitivity: the same two scripts DO change the adaptive schedule, so the equality above is not vacuous
    a1 = _run(client, db, monkeypatch, ADAPTIVE, strong, GOOD)
    a2 = _run(client, db, monkeypatch, ADAPTIVE, weak, POOR)
    assert _schedule(a1) != _schedule(a2)


def test_adaptive_schedule_depends_on_answers(client, db, monkeypatch):
    hi = _run(client, db, monkeypatch, ADAPTIVE, strong, GOOD)
    lo = _run(client, db, monkeypatch, ADAPTIVE, weak, POOR)
    assert hi.qa and lo.qa
    assert _schedule(hi, True) != _schedule(lo, True)
    assert [q["difficulty"] for q in hi.qa] != [q["difficulty"] for q in lo.qa] or _schedule(hi) != _schedule(lo)


@pytest.mark.parametrize("flag", ["adaptive_topics", "adaptive_followup", "adaptive_difficulty"])
def test_ablation_runs_complete_for_each_flag(client, db, monkeypatch, flag):
    rec = _run(client, db, monkeypatch, ADAPTIVE, strong, GOOD, **{flag: False})
    assert rec.config[flag] is False
    assert all(rec.config[f] is True for f in ("adaptive_topics", "adaptive_followup", "adaptive_difficulty") if f != flag)
    assert 0 < len(rec.qa) <= BUDGET and rec.assessments
    assert rec.errors["ungraded_answers"] == 0 and rec.interview_id
    with db() as s:
        row = s.get(CoreInterview, rec.interview_id)
        assert row.status == "FINISHED" and row.mode_config == rec.config
        assert (row.static_plan is not None) == (flag == "adaptive_topics")


def test_rerank_equals_ranking_for_every_mode(abc, db, monkeypatch):
    def boom():
        raise AssertionError("rerank must not call the model")

    monkeypatch.setattr("backend.api.core.get_chat_model", boom)
    with db() as s:
        for mode, rec in abc.items():
            assert rec.ranking, mode
            assert rerank(rec, s) == rec.ranking, mode
    assert any(i["label"] == "RANKED" for i in abc[STATIC].ranking)
    assert abc[INITIAL].ranking != abc[STATIC].ranking  # different inputs do give different rankings


def test_ranking_deterministic_same_snapshot(abc, db, monkeypatch):
    monkeypatch.setattr("backend.api.core.get_chat_model", lambda: pytest.fail("no LLM in ranking"))
    rec = abc[ADAPTIVE]
    assert len(rec.assessments) > 1
    shuffled = list(rec.assessments)
    random.Random(7).shuffle(shuffled)
    assert shuffled != rec.assessments
    from dataclasses import replace
    with db() as s:
        first, second = rerank(rec, s), rerank(rec, s)
        reordered = rerank(replace(rec, assessments=shuffled), s)
    assert first == second == reordered == rec.ranking
    assert [i["vacancy_id"] for i in first] == [i["vacancy_id"] for i in rec.ranking]


BACKEND = Path(backend.__file__).parent
SCANNED = [*sorted((BACKEND / "domain").rglob("*.py")), *sorted((BACKEND / "api").rglob("*.py")),
           BACKEND / "experiments" / "planning.py", BACKEND / "experiments" / "runner.py"]
FORBIDDEN = ("expert", "labels")


def forbidden_imports(source: str) -> list[str]:
    """Imported module names (and `from x import name` names) containing expert/labels, case-insensitive."""
    bad = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or "", *(f"{node.module or ''}.{a.name}" for a in node.names)]
        else:
            continue
        bad += [n for n in names if any(f in n.lower() for f in FORBIDDEN)]
    return bad


def test_no_expert_labels_import_in_engine():
    assert len(SCANNED) >= 15 and all(p.is_file() for p in SCANNED)
    assert {p.name for p in SCANNED} >= {"planner.py", "core.py", "planning.py", "runner.py"}
    # the helper is not vacuous: it flags each import form
    assert forbidden_imports("import backend.expert_labels") == ["backend.expert_labels"]
    assert forbidden_imports("from backend.labels import x")
    assert forbidden_imports("from backend import expert_scores")
    assert forbidden_imports("import os\nfrom backend.domain import ranking") == []
    offenders = {str(p.relative_to(BACKEND)): forbidden_imports(p.read_text(encoding="utf-8")) for p in SCANNED}
    assert {k: v for k, v in offenders.items() if v} == {}
