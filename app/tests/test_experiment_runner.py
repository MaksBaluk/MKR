"""Experiment runner: modes A/B/C through the real API, stored runs, deterministic re-ranking and the CLI."""
import csv
import hashlib
import json
import re
from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import select

import backend.api.core as core
from backend.api.core import _revisions
from backend.domain.core_flow import self_claim_metrics
from backend.experiments.config import ExperimentConfig, InterviewMode, config_for
from backend.experiments.providers import CandidateSpec, ScriptedProvider
from backend.agents.prompts import INTERVIEWER_SYSTEM
from backend.experiments.runner import ALGORITHM_VERSION, PROMPTS_FILE, prompt_version, rerank, run_experiment
from backend.experiments.store import CSV_FIELDS, export_records, load_record, save_record
from backend.models import CohortSnapshot, CoreInterview, CoreTurn, ExperimentRun, Rubric, Vacancy
from tests.test_followup_flow import PolicyChat, _use

INITIAL = InterviewMode.INITIAL_PROFILE
STATIC = InterviewMode.STATIC_INTERVIEW
ADAPTIVE = InterviewMode.ADAPTIVE_INTERVIEW
KEY = ("z", "x", "l_mandatory", "l_preferred", "w_mandatory", "w_preferred")


def strong(allowed, n):
    return {c: 0.95 for c in allowed}, []


def cand(cid="c1", track="python", ratings=None):
    return CandidateSpec(candidate_id=cid, desired_title="Python Developer", years_experience=3, target_level="middle",
                         track=track, location="Київ", work_mode="remote", self_ratings=ratings or {})


SCRIPT = ScriptedProvider({"c1": {"default": "Налаштовував індекси та транзакції в PostgreSQL для сервісу замовлень."}})


def test_mode_a_has_no_scores_and_uses_self_ratings_only_as_tiebreak(client, db, monkeypatch):
    monkeypatch.setattr("backend.api.core.get_chat_model", lambda: pytest.fail("mode A must not touch the LLM"))
    with db() as s:
        base = run_experiment("exp-a", config_for(INITIAL), cand("plain"), None, client, s)
        assert base.qa == [] and base.assessments == [] and base.interview_id is None
        assert base.answer_source == "NONE" and base.model_info == {"provider": None}
        assert base.ranking and all(i["label"] == "LOW_INFORMATION" and i["l_mandatory"] == 0 for i in base.ranking)
        revs = {r["id"]: r for r in _revisions(s.get(CohortSnapshot, base.cohort_id))}
    # a tied pair (equal ranking key) ordered by id; a self-rating on an action that favours the later id flips it
    pick = None
    for i, a in enumerate(base.ranking):
        for b in base.ranking[i + 1:]:
            if tuple(a[k] for k in KEY) != tuple(b[k] for k in KEY):
                break
            for x in sorted({alt["competency_id"] for g in revs[b["vacancy_id"]]["groups"] for alt in g["alternatives"]}):
                tb = self_claim_metrics(revs[b["vacancy_id"]]["groups"], {x: 0.95})[0]
                ta = self_claim_metrics(revs[a["vacancy_id"]]["groups"], {x: 0.95})[0]
                if tb > ta:
                    pick = (a["vacancy_id"], b["vacancy_id"], x)
                    break
            if pick:
                break
        if pick:
            break
    assert pick, "fixture cohort has no tied pair"
    first, second, action = pick
    assert first < second
    with db() as s:
        rec = run_experiment("exp-a", config_for(INITIAL), cand("rated", ratings={action: 0.95}), None, client, s)
    assert rec.assessments == [] and rec.qa == [] and rec.profile_snapshot["self_ratings"] == {action: 0.95}
    order = [i["vacancy_id"] for i in rec.ranking]
    assert order.index(second) < order.index(first)  # T_v breaks the tie, not the id
    assert all(i["label"] == "LOW_INFORMATION" and i["l_mandatory"] == 0 for i in rec.ranking)
    keys = {i["vacancy_id"]: tuple(i[k] for k in KEY) for i in rec.ranking}
    assert keys == {i["vacancy_id"]: tuple(i[k] for k in KEY) for i in base.ranking}  # never a criterion score
    assert all(not i["strengths"] and not i["gaps"] for i in rec.ranking)


@pytest.mark.parametrize("mode", [STATIC, ADAPTIVE])
def test_run_static_and_adaptive_record_everything(client, db, monkeypatch, mode):
    _use(monkeypatch, PolicyChat(strong, sufficient=True))
    cfg = config_for(mode, total_budget=6)
    with db() as s:
        rec = run_experiment("exp-bc", cfg, cand(), SCRIPT, client, s)
        snap = s.get(CohortSnapshot, rec.cohort_id)
        row = s.get(CoreInterview, rec.interview_id)
        turns = list(s.scalars(select(CoreTurn).where(CoreTurn.interview_id == row.id).order_by(CoreTurn.sequence)))
    assert rec.mode == mode.value and rec.config == cfg.to_json() and row.mode_config == cfg.to_json()
    assert (row.static_plan is not None) == (mode is STATIC) and row.status == "FINISHED"
    assert rec.cohort_sha256 == snap.sha256 and re.fullmatch(r"[0-9a-f]{64}", rec.prompt_version)
    assert rec.algorithm_version == ALGORITHM_VERSION == "rank-2.15+tv-jv/v1" and rec.answer_source == "SCRIPTED"
    assert 0 < len(rec.qa) == len(turns) <= 6
    for q, t in zip(rec.qa, turns):
        assert (q["sequence"], q["action_id"], q["question_text"], q["answer_text"], q["question_source"],
                q["difficulty"], q["target_criteria"]) == (t.sequence, t.action_id, t.question_text, t.answer_text,
                                                          t.question_source, t.difficulty, t.target_criteria)
        assert q["assessment_status"] == "ACCEPTED" and q["ordinal_in_topic"] >= 1
    assert rec.assessments and all({"criterion_id", "score", "sufficient_evidence", "revision"} <= set(a)
                                   for a in rec.assessments)
    assert set(rec.timings) == {"total_s", "llm_wait_s", "calls"} and rec.timings["calls"] > 0
    assert 0 <= rec.timings["llm_wait_s"] <= rec.timings["total_s"]
    assert rec.errors == {"ungraded_answers": 0, "fallback_questions": 0, "llm_exceptions": 0,
                          "evaluator_rejections": 0, "empty_cohort": False}
    # injected factory: never the configured provider/model; PolicyChat sends no response metadata
    assert rec.model_info == {"provider": "injected", "client_class": "PolicyChat", "served_models": []}
    assert rec.rubric_versions and set(rec.rubric_versions.values()) <= {"v1", "auto-1"}
    assert rec.ranking and any(i["label"] == "RANKED" for i in rec.ranking)
    assert rec.profile_snapshot["years_experience"] == 3 and rec.profile_snapshot["track"] == "python"


def test_rerank_reproduces_ranking_without_llm(client, db, monkeypatch):
    _use(monkeypatch, PolicyChat(strong, sufficient=True))
    with db() as s:
        rec = run_experiment("exp-rr", config_for(ADAPTIVE, total_budget=5), cand(), SCRIPT, client, s)

    def boom():
        raise AssertionError("rerank must not call the model")

    monkeypatch.setattr("backend.api.core.get_chat_model", boom)
    assert any(i["label"] == "RANKED" for i in rec.ranking)
    with db() as s:
        assert rerank(rec, s) == rec.ranking
        assert rerank(load_record(s, save_record(s, rec)), s) == rec.ranking
        with pytest.raises(ValueError):
            rerank(replace(rec, cohort_sha256="0" * 64), s)
        # recomputed, not echoed: without assessments every vacancy falls back to LOW_INFORMATION
        blank = rerank(replace(rec, assessments=[]), s)
        assert blank != rec.ranking and all(i["label"] == "LOW_INFORMATION" for i in blank)
        # one stored criterion score lowered 0.95 -> 0.0 changes the l_* values of the vacancies needing it
        target = next(a for a in rec.assessments if a["score"] is not None)
        changed = [{**a, "score": 0.0} if a is target else a for a in rec.assessments]
        moved = {i["vacancy_id"]: (i["l_mandatory"], i["l_preferred"]) for i in rerank(replace(rec, assessments=changed), s)}
        before = {i["vacancy_id"]: (i["l_mandatory"], i["l_preferred"]) for i in rec.ranking}
        assert any(moved[v] != before[v] for v in before)


def test_save_load_roundtrip_and_export(client, db, monkeypatch, tmp_path):
    _use(monkeypatch, PolicyChat(strong, sufficient=True))
    with db() as s:
        recs = [run_experiment("exp-io", config_for(m, total_budget=4), cand(), SCRIPT, client, s)
                for m in (INITIAL, STATIC)]
        ids = [save_record(s, r) for r in recs]
        assert [load_record(s, i) for i in ids] == recs
        rows = s.scalars(select(ExperimentRun).where(ExperimentRun.experiment_id == "exp-io")).all()
        assert len(rows) == 2 and {r.interview_id for r in rows} == {None, recs[1].interview_id}
        for r in rows:  # answer_source rides in the raw config JSON; from_json still parses it
            assert "answer_source" in r.config and ExperimentConfig.from_json(r.config).to_json() == {
                k: v for k, v in r.config.items() if k != "answer_source"}
    export_records(recs, tmp_path / "out")
    data = json.loads((tmp_path / "out" / "runs.json").read_text(encoding="utf-8"))
    assert [d["mode"] for d in data] == ["INITIAL_PROFILE", "STATIC_INTERVIEW"]
    with open(tmp_path / "out" / "runs.csv", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == CSV_FIELDS
        rows = list(reader)
    assert rows[0]["n_questions"] == "0" and int(rows[1]["n_questions"]) == len(recs[1].qa)
    assert rows[1]["adaptive_topics"] == "False" and rows[1]["empty_cohort"] == "False"


def test_llm_failure_creates_no_grades(client, db, monkeypatch):
    _use(monkeypatch, PolicyChat(fail=True))
    with db() as s:
        rec = run_experiment("exp-fail", config_for(ADAPTIVE), cand(), SCRIPT, client, s)
        run_id = save_record(s, rec)
        assert load_record(s, run_id) == rec
    assert rec.qa and rec.errors["fallback_questions"] == len(rec.qa) > 0
    assert rec.errors["ungraded_answers"] == len(rec.qa) and rec.errors["llm_exceptions"] > 0
    assert all(q["assessment_status"] == "UNGRADED" for q in rec.qa)
    assert rec.assessments == [] and all(i["label"] == "LOW_INFORMATION" for i in rec.ranking)


def test_scripted_provider_defaults(tmp_path):
    data = {"c1": {"a1": ["перша", "друга"], "default": "Не працював з цим."}}
    path = tmp_path / "answers.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    for p in (ScriptedProvider(data), ScriptedProvider.from_file(path)):
        turn = lambda a, n: {"action_id": a, "question_text": "?", "ordinal_in_topic": n}  # noqa: E731
        assert p.source == "SCRIPTED"
        assert [p.answer(cand("c1"), turn("a1", n)) for n in (1, 2, 3)] == ["перша", "друга", "Не працював з цим."]
        assert p.answer(cand("c1"), turn("other", 1)) == "Не працював з цим."
        assert p.answer(cand("nobody"), turn("a1", 1)) == "Не знаю."


@pytest.mark.parametrize("mode", [INITIAL, ADAPTIVE])
def test_empty_cohort_is_reported_not_crash(client, db, monkeypatch, mode):
    monkeypatch.setattr("backend.api.core.get_chat_model", lambda: pytest.fail("no question without a cohort"))
    with db() as s:
        for v in s.scalars(select(Vacancy).where(Vacancy.track == "design")):
            v.is_active = False
        s.commit()
        rec = run_experiment("exp-empty", config_for(mode), cand(track="design"), SCRIPT, client, s)
        assert load_record(s, save_record(s, rec)) == rec
        assert rerank(rec, s) == []
    assert rec.ranking == [] and rec.qa == [] and rec.assessments == [] and rec.errors["empty_cohort"] is True
    assert rec.cohort_id == "" and rec.interview_id is None


def _cli_inputs(tmp_path):
    (tmp_path / "candidates.json").write_text(json.dumps([{
        "candidate_id": "c1", "desired_title": "Python Developer", "years_experience": 3, "target_level": "middle",
        "track": "python", "location": "Київ", "work_mode": "remote", "self_ratings": {}}]), encoding="utf-8")
    (tmp_path / "answers.json").write_text(json.dumps({"c1": {"default": "Писав API на FastAPI з тестами."}},
                                                      ensure_ascii=False), encoding="utf-8")
    return ["--db", f"sqlite:///{tmp_path / 'exp.db'}", "--candidates", str(tmp_path / "candidates.json"),
            "--answers", str(tmp_path / "answers.json"), "--out", str(tmp_path / "out")]


class _Spy:
    """Model factory that records calls; returns the wrapped fake (or None)."""

    def __init__(self, fake=None):
        self.fake, self.calls = fake, 0

    def __call__(self):
        self.calls += 1
        return self.fake


def test_cli_runs_modes_with_injected_model(tmp_path, capsys):
    from scripts.run_experiment import main
    spy = _Spy(PolicyChat(strong, sufficient=True))
    args = _cli_inputs(tmp_path) + ["--modes", "INITIAL_PROFILE", "STATIC_INTERVIEW", "ADAPTIVE_INTERVIEW",
                                    "--flags", "no_adaptive_difficulty", "--total-budget", "3",
                                    "--llm", "configured", "--experiment-id", "cli-1"]
    assert main(args, model_factory=spy) == 0 and spy.calls > 0
    assert core.get_chat_model is not None and core.get_chat_model.__module__ == "backend.agents.model"
    data = json.loads((tmp_path / "out" / "runs.json").read_text(encoding="utf-8"))
    assert [d["mode"] for d in data] == ["INITIAL_PROFILE", "STATIC_INTERVIEW", "ADAPTIVE_INTERVIEW"]
    assert all(len(d["qa"]) <= 3 for d in data) and data[2]["config"]["adaptive_difficulty"] is False
    assert data[2]["config"]["adaptive_topics"] is True and data[1]["config"]["adaptive_topics"] is False
    assert data[0]["assessments"] == [] and all(d["assessments"] and d["timings"]["calls"] > 0 for d in data[1:])
    assert all(d["model_info"]["client_class"] == "PolicyChat" for d in data[1:])  # the injected model graded
    out = capsys.readouterr().out
    assert "llm: provider=injected model=PolicyChat" in out
    assert str(tmp_path / "out") in out and len(re.findall(r"run [0-9a-f-]{36}", out)) == 3


def test_cli_default_mode_is_initial_and_calls_no_model(tmp_path):
    from scripts.run_experiment import main
    spy = _Spy(PolicyChat(strong))
    assert main(_cli_inputs(tmp_path), model_factory=spy) == 0 and spy.calls == 0
    data = json.loads((tmp_path / "out" / "runs.json").read_text(encoding="utf-8"))
    assert [d["mode"] for d in data] == ["INITIAL_PROFILE"]


@pytest.mark.parametrize("extra", [[], ["--allow-ungraded"]], ids=["plain", "allow-ungraded"])
def test_cli_interview_without_llm_flag_is_refused(tmp_path, capsys, extra):
    from scripts.run_experiment import main
    spy = _Spy(PolicyChat(strong))
    args = _cli_inputs(tmp_path) + ["--modes", "STATIC_INTERVIEW", "--total-budget", "2", *extra]
    assert main(args, model_factory=spy) == 2 and spy.calls == 0 and not (tmp_path / "out").exists()
    assert "error: interview modes need --llm" in capsys.readouterr().err


def test_cli_llm_none_needs_allow_ungraded_and_never_calls_a_model(tmp_path, capsys):
    from scripts.run_experiment import main
    spy = _Spy(PolicyChat(strong))
    args = _cli_inputs(tmp_path) + ["--modes", "STATIC_INTERVIEW", "--total-budget", "2", "--llm", "none"]
    assert main(args, model_factory=spy) == 2 and not (tmp_path / "out").exists()
    assert main(args + ["--allow-ungraded"], model_factory=spy) == 0 and spy.calls == 0
    data = json.loads((tmp_path / "out" / "runs.json").read_text(encoding="utf-8"))
    assert data[0]["errors"]["ungraded_answers"] == len(data[0]["qa"]) > 0 and data[0]["assessments"] == []
    assert data[0]["model_info"] == {"provider": None} and data[0]["timings"]["calls"] == 0
    assert "llm: none" in capsys.readouterr().out


def test_cli_llm_configured_prints_provider_without_secrets(tmp_path, capsys, monkeypatch):
    """Product factory path (no injection): provider/model printed and recorded; key and base URL never printed."""
    from types import SimpleNamespace
    from scripts.run_experiment import main
    fake = PolicyChat(strong, sufficient=True)
    settings = SimpleNamespace(database_url="sqlite+pysqlite://", llm_provider="openai_compatible",
                               llm_model="vendor/model-x", llm_api_key="sk-SECRET-123",
                               llm_base_url="https://secret-base.example/v1", llm_timeout_seconds=18.0)
    monkeypatch.setattr("scripts.run_experiment.get_settings", lambda: settings)
    monkeypatch.setattr("backend.experiments.runner.get_settings", lambda: settings)
    factory = lambda: fake  # noqa: E731
    monkeypatch.setattr("backend.agents.model.get_chat_model", factory)  # stands in for the configured provider
    monkeypatch.setattr("backend.api.core.get_chat_model", factory)
    args = _cli_inputs(tmp_path) + ["--modes", "ADAPTIVE_INTERVIEW", "--total-budget", "2", "--llm", "configured"]
    assert main(args) == 0
    captured = capsys.readouterr()
    assert "llm: provider=openai_compatible model=vendor/model-x" in captured.out
    assert "SECRET" not in captured.out + captured.err and "secret-base" not in captured.out + captured.err
    data = json.loads((tmp_path / "out" / "runs.json").read_text(encoding="utf-8"))
    info = data[0]["model_info"]
    assert info["provider"] == "openai_compatible" and info["model"] == "vendor/model-x" and info["timeout"] == 18.0
    assert set(info) == {"provider", "model", "temperature", "max_tokens", "timeout", "client_class", "served_models"}
    assert data[0]["assessments"] and "SECRET" not in json.dumps(data)


@pytest.mark.parametrize("extra,needle", [
    (["--modes", "STATIC_INTERVIEW", "ADAPTIVE_INTERVIEW", "--llm", "none", "--allow-ungraded"], "--total-budget"),
    (["--modes", "INITIAL_PROFILE", "--flags", "no_adaptive_topics"], "--flags"),
    (["--modes", "STATIC_INTERVIEW", "--flags", "no_adaptive_topics", "--llm", "none", "--allow-ungraded",
      "--total-budget", "2"], "--flags"),
    (["--total-budget", "0"], "--total-budget"),
    (["--total-budget", "-3"], "--total-budget"),
    (["--total-budget", "two"], "--total-budget"),
    (["--modes", "BOGUS"], "--modes"),
])
def test_cli_bad_arguments_exit_2_with_error(tmp_path, capsys, extra, needle):
    from scripts.run_experiment import main
    spy = _Spy(PolicyChat(strong))
    assert main(_cli_inputs(tmp_path) + extra, model_factory=spy) == 2 and spy.calls == 0
    err = capsys.readouterr().err
    assert "error:" in err and needle in err and "Traceback" not in err
    assert not (tmp_path / "out").exists()


def test_cli_config_validation_error_exit_2(tmp_path, capsys, monkeypatch):
    from scripts.run_experiment import main

    def bad(*a, **k):
        raise ValueError("max_topics must be in 1..10")

    monkeypatch.setattr("scripts.run_experiment.config_for", bad)
    assert main(_cli_inputs(tmp_path)) == 2
    assert "error: invalid experiment config: max_topics" in capsys.readouterr().err


def test_cli_requires_sqlite_db(tmp_path, capsys):
    from scripts.run_experiment import main
    assert main(["--candidates", "x.json", "--answers", "y.json", "--out", str(tmp_path)]) == 2  # --db is required
    assert "--db" in capsys.readouterr().err
    assert main(["--db", "postgresql://x/y"] + _cli_inputs(tmp_path)[2:]) == 2


def _settings_url(monkeypatch, url):
    from types import SimpleNamespace
    monkeypatch.setattr("scripts.run_experiment.get_settings", lambda: SimpleNamespace(database_url=url))


@pytest.mark.parametrize("spelling", ["sqlite+pysqlite:///./prod.db", "sqlite:///prod.db", "sqlite:///./prod.db",
                                      "sqlite:///{abs}", "sqlite+pysqlite:///{abs}", "sqlite:///sub/../prod.db"])
def test_cli_refuses_product_db_under_any_spelling(tmp_path, monkeypatch, spelling):
    from scripts.run_experiment import main
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sub").mkdir()
    _settings_url(monkeypatch, "sqlite+pysqlite:///./prod.db")  # the product default URL shape
    args = _cli_inputs(tmp_path)[2:] + ["--modes", "INITIAL_PROFILE"]
    assert main(["--db", spelling.format(abs=tmp_path / "prod.db")] + args) == 2
    assert not (tmp_path / "prod.db").exists() and not (tmp_path / "out").exists()


def test_cli_refuses_in_memory_when_product_is_in_memory(tmp_path, monkeypatch):
    from scripts.run_experiment import main
    _settings_url(monkeypatch, "sqlite+pysqlite://")
    args = _cli_inputs(tmp_path)[2:] + ["--modes", "INITIAL_PROFILE"]
    assert main(["--db", "sqlite://"] + args) == 2 and main(["--db", "sqlite:///:memory:"] + args) == 2
    _settings_url(monkeypatch, "sqlite+pysqlite:///./prod.db")
    assert main(["--db", "sqlite://"] + args) == 0  # a separate in-memory DB is fine when the product is a file


def test_cli_failing_run_keeps_batch_and_exits_nonzero(tmp_path, capsys):
    from scripts.run_experiment import main
    args = _cli_inputs(tmp_path)
    bad = {"candidate_id": "bad", "desired_title": "X", "years_experience": 1, "target_level": "junior",
           "track": "astronomy", "location": "", "work_mode": None, "self_ratings": {}}  # profile PUT -> 422
    good = json.loads((tmp_path / "candidates.json").read_text(encoding="utf-8"))
    (tmp_path / "candidates.json").write_text(json.dumps([bad] + good), encoding="utf-8")
    assert main(args + ["--modes", "INITIAL_PROFILE"]) == 1
    data = json.loads((tmp_path / "out" / "runs.json").read_text(encoding="utf-8"))
    assert [d["candidate_id"] for d in data] == ["c1"]
    out = capsys.readouterr().out
    assert "FAILED bad INITIAL_PROFILE: RuntimeError" in out and "422" in out


class _Garbled(PolicyChat):
    """Interviewer works; the Evaluator answers with text that never validates (no provider exception)."""

    def invoke(self, messages, *a, **k):
        out = super().invoke(messages, *a, **k)
        return out if messages[0].content == INTERVIEWER_SYSTEM else SimpleNamespace(content="не JSON")


class _Served(PolicyChat):
    def invoke(self, messages, *a, **k):
        out = super().invoke(messages, *a, **k)
        name = "vendor/interviewer-1" if messages[0].content == INTERVIEWER_SYSTEM else "vendor/evaluator-2"
        return SimpleNamespace(content=out.content, response_metadata={"model_name": name})


def test_evaluator_rejections_counted_apart_from_exceptions(client, db, monkeypatch):
    _use(monkeypatch, _Garbled(strong, sufficient=True))
    with db() as s:
        rec = run_experiment("exp-rej", config_for(ADAPTIVE, total_budget=3), cand(), SCRIPT, client, s)
    assert rec.qa and rec.errors["llm_exceptions"] == 0 and rec.errors["fallback_questions"] == 0
    assert rec.errors["evaluator_rejections"] == rec.errors["ungraded_answers"] == len(rec.qa)
    assert rec.assessments == []


def test_served_models_from_response_metadata(client, db, monkeypatch):
    _use(monkeypatch, _Served(strong, sufficient=True))
    with db() as s:
        rec = run_experiment("exp-served", config_for(ADAPTIVE, total_budget=2), cand(), SCRIPT, client, s)
    assert rec.model_info["served_models"] == ["vendor/evaluator-2", "vendor/interviewer-1"]
    assert rec.model_info["provider"] == "injected" and "model" not in rec.model_info


def test_prompt_version_tracks_the_whole_prompts_module(tmp_path):
    src = PROMPTS_FILE.read_text(encoding="utf-8")
    assert prompt_version() == hashlib.sha256(PROMPTS_FILE.read_bytes()).hexdigest()
    same, changed = tmp_path / "same.py", tmp_path / "changed.py"
    same.write_text(src, encoding="utf-8")
    # change only formatter code (not a system prompt): the version must still change
    start = src.index("def format_evaluator_input")
    assert src.count("def format_evaluator_input") == 1
    changed.write_text(src[:start] + "# formatter edit\n" + src[start:], encoding="utf-8")
    assert prompt_version(same) == prompt_version()
    assert prompt_version(changed) != prompt_version()


def test_rerank_refuses_changed_rubric_versions(client, db, monkeypatch):
    _use(monkeypatch, PolicyChat(strong, sufficient=True))
    with db() as s:
        rec = run_experiment("exp-rv", config_for(ADAPTIVE, total_budget=2), cand(), SCRIPT, client, s)
        action = next(a for a, v in rec.rubric_versions.items() if v == "v1")
        assert rerank(rec, s) == rec.ranking
        with pytest.raises(ValueError, match="rubric versions"):
            rerank(replace(rec, rubric_versions={**rec.rubric_versions, action: "v0"}), s)
        with pytest.raises(ValueError, match="rubric versions"):
            rerank(replace(rec, rubric_versions={k: v for k, v in rec.rubric_versions.items() if k != action}), s)
        rubric = s.scalar(select(Rubric).where(Rubric.action_id == action, Rubric.version == "v1"))
        rubric.version = "v2"  # the seeded rubric row changed after the run
        s.commit()
        with pytest.raises(ValueError, match=action):
            rerank(rec, s)
