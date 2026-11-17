"""Experiment runner: drives the real HTTP API (TestClient) for one candidate in one mode and records the run.

Experiment config reaches the interview only through the DB row (server-side), never through a public request field.
The candidate profile is set once before the run and never edited between questions."""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import backend.agents.model as agent_model
import backend.agents.prompts as prompts
import backend.api.core as core
from backend.api.core import _revisions, _seeded_rubric, cohort_actions, current_criteria_rows, static_plan_for
from backend.api.recommendations import rank_items
from backend.config import get_settings
from backend.experiments.config import ExperimentConfig, InterviewMode
from backend.experiments.providers import DEFAULT_ANSWER, AnswerProvider, CandidateSpec
from backend.experiments.store import ExperimentRecord
from backend.models import CohortSnapshot, CoreInterview, CoreTurn, CriterionAssessment, Rubric

ALGORITHM_VERSION = "rank-2.15+tv-jv/v1"
API = "/api/v1"
MAX_ANSWER_CHARS = 4000


PROMPTS_FILE = Path(prompts.__file__)


def prompt_version(path: Path = PROMPTS_FILE) -> str:
    """sha256 of the whole prompts module source: system prompts, input formatters and default bands."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass
class _LlmStats:
    calls: int = 0
    wait_s: float = 0.0
    exceptions: int = 0
    rejections: int = 0  # evaluator runs that returned without a provider exception but were not ACCEPTED
    served: set[str] = field(default_factory=set)  # model names reported in response metadata
    lock: threading.Lock = field(default_factory=threading.Lock)


class _TimedModel:
    """Proxy around a chat model: counts calls, provider exceptions and wall time spent waiting in invoke()."""

    def __init__(self, inner, stats: _LlmStats):
        self._inner, self._stats = inner, stats

    def invoke(self, *args, **kwargs):
        start, failed = time.perf_counter(), False
        try:
            result = self._inner.invoke(*args, **kwargs)
            meta = getattr(result, "response_metadata", None) or {}
            served = meta.get("model_name") or meta.get("model") if isinstance(meta, dict) else None
            if served:
                with self._stats.lock:
                    self._stats.served.add(str(served))
            return result
        except Exception:
            failed = True
            raise
        finally:
            with self._stats.lock:
                self._stats.calls += 1
                self._stats.wait_s += time.perf_counter() - start
                self._stats.exceptions += failed

    def __getattr__(self, name):
        return getattr(self._inner, name)


@contextmanager
def _timed_model(stats: _LlmStats):
    """Wrap backend.api.core.get_chat_model (timing) and run_answer (evaluator rejections) for the run;
    yields the unwrapped model factory."""
    original, original_answer = core.get_chat_model, core.run_answer

    def wrapped():
        model = original()
        return None if model is None else _TimedModel(model, stats)

    def counted_answer(state, model):
        before = stats.exceptions
        result = original_answer(state, model)
        if result.status != "ACCEPTED" and stats.exceptions == before:
            with stats.lock:
                stats.rejections += 1
        return result

    # module-global patch: not safe for concurrent runs in one process
    core.get_chat_model, core.run_answer = wrapped, counted_answer
    try:
        yield original
    finally:
        core.get_chat_model, core.run_answer = original, original_answer


def _number(model, *names):
    for n in names:
        v = getattr(model, n, None)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return v
    return None


def _model_info(model, factory) -> dict:
    """Configured provider only when the product factory is in use; an injected factory never reports settings."""
    if model is None:
        return {"provider": None}
    if factory is not agent_model.get_chat_model:
        return {"provider": "injected", "client_class": type(model).__name__, "served_models": []}
    s = get_settings()
    return {"provider": s.llm_provider, "model": s.llm_model,
            "temperature": _number(model, "temperature", "_temperature"),
            "max_tokens": _number(model, "max_tokens", "_max_tokens"), "timeout": s.llm_timeout_seconds,
            "client_class": type(model).__name__, "served_models": []}


def _ok(response, status: int) -> dict:
    if response.status_code != status:
        raise RuntimeError(f"{response.request.method} {response.request.url.path} -> "
                           f"{response.status_code}: {response.text[:300]}")
    return response.json() if response.content else {}


def _register(client: TestClient) -> dict:
    token = uuid.uuid4().hex
    body = _ok(client.post(f"{API}/auth/register", json={
        "email": f"exp-{token}@experiments.local", "display_name": "Experiment candidate",
        "password": uuid.uuid4().hex}), 201)
    return {"Authorization": f"Bearer {body['token']}"}


def _setup_profile(client: TestClient, h: dict, c: CandidateSpec) -> dict:
    """Fill the throwaway user's default profile and self-ratings once; returns the frozen profile snapshot."""
    pid = _ok(client.get(f"{API}/profiles", headers=h), 200)["items"][0]["id"]
    prof = _ok(client.put(f"{API}/profiles/{pid}", headers=h, json={
        "name": f"Experiment {c.candidate_id}"[:120], "track": c.track, "desired_title": c.desired_title,
        "target_level": c.target_level, "work_mode": c.work_mode, "years_experience": c.years_experience,
        "location": c.location}), 200)
    for action_id, value in sorted(c.self_ratings.items()):
        _ok(client.put(f"{API}/profiles/{pid}/self-ratings/{action_id}", headers=h, json={"value": value}), 200)
    ratings = _ok(client.get(f"{API}/profiles/{pid}/self-ratings", headers=h), 200)["items"]
    return {"profile_id": pid, **{k: prof[k] for k in ("track", "desired_title", "target_level", "work_mode",
                                                       "years_experience", "location")},
            "self_ratings": {r["action_id"]: r["value"] for r in ratings}}


def _json(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


def _rank(db: Session, snap: CohortSnapshot, profile: dict, scores: dict) -> list[dict]:
    return _json(rank_items(db, profile["years_experience"], snap, scores, profile["self_ratings"]))


def _scores(assessments: list[dict]) -> dict[str, float | None]:
    return {a["criterion_id"]: a["score"] for a in assessments}


def _latest_assessments(db: Session, interview_id: str) -> list[dict]:
    """Latest revision per criterion (same rows and order as attempt_scores)."""
    rows = db.scalars(select(CriterionAssessment).where(CriterionAssessment.session_id == interview_id)
                      .order_by(CriterionAssessment.created_at, CriterionAssessment.revision)).all()
    out: dict[str, dict] = {}
    for r in current_criteria_rows(rows):
        out[r.criterion_id] = {"action_id": r.action_id, "criterion_id": r.criterion_id, "score": r.score,
                               "sufficient_evidence": bool(r.sufficient_evidence), "revision": r.revision}
    return list(out.values())


def _seeded_versions(db: Session, snap: CohortSnapshot) -> dict[str, str]:
    out = {}
    for a in sorted(cohort_actions(_revisions(snap))):
        rubric = _seeded_rubric(db, a)
        if rubric is not None:
            out[a] = rubric.version
    return out


def _rubric_versions(db: Session, snap: CohortSnapshot, interview_id: str | None) -> dict[str, str]:
    out = _seeded_versions(db, snap)
    if interview_id:
        for r in db.scalars(select(CriterionAssessment).where(CriterionAssessment.session_id == interview_id)):
            rubric = db.get(Rubric, r.rubric_id)
            if rubric is not None:
                out[r.action_id] = rubric.version
    return dict(sorted(out.items()))


def _interview(client: TestClient, h: dict, db: Session, snap: CohortSnapshot, cfg: ExperimentConfig,
               candidate: CandidateSpec, provider: AnswerProvider) -> tuple[str, list[dict]]:
    created = _ok(client.post(f"{API}/interviews", headers=h, json={"cohort_id": snap.id}), 201)
    iv_id, version = created["id"], created["version"]
    db.expire_all()
    row = db.get(CoreInterview, iv_id)
    row.mode_config = cfg.to_json()  # server-side only: never a public request field
    row.static_plan = None if cfg.adaptive_topics else static_plan_for(db, _revisions(snap), cfg)
    db.commit()
    qa: list[dict] = []
    shown: dict[str, int] = {}
    for _ in range(cfg.max_topics * cfg.max_per_topic + 1):
        nxt = _ok(client.post(f"{API}/interviews/{iv_id}/next-question", headers=h, json={"version": version}), 200)
        version = nxt["version"]
        if nxt.get("done"):
            return iv_id, qa
        turn = nxt["turn"]
        shown[turn["action_id"]] = shown.get(turn["action_id"], 0) + 1
        text = provider.answer(candidate, {"action_id": turn["action_id"], "question_text": turn["question_text"],
                                           "ordinal_in_topic": shown[turn["action_id"]],
                                           "sequence": turn["sequence"]})
        text = (text or "").strip()[:MAX_ANSWER_CHARS] or DEFAULT_ANSWER
        ans = _ok(client.post(f"{API}/interviews/{iv_id}/answers", headers=h, json={
            "turn_id": turn["id"], "text": text, "version": version,
            "idempotency_key": f"exp-{uuid.uuid4().hex}"}), 200)
        version = ans["version"]
        db.expire_all()
        t = db.get(CoreTurn, turn["id"])  # experiment record: stored difficulty/targets are read from the row
        qa.append({"sequence": t.sequence, "action_id": t.action_id, "ordinal_in_topic": shown[t.action_id],
                   "question_text": t.question_text, "answer_text": t.answer_text,
                   "question_source": t.question_source, "difficulty": t.difficulty,
                   "target_criteria": t.target_criteria, "assessment_status": ans.get("assessment_status")})
    raise RuntimeError(f"interview {iv_id} did not finish within the product caps")


def run_experiment(experiment_id: str, cfg: ExperimentConfig, candidate: CandidateSpec,
                   provider: AnswerProvider | None, client: TestClient, db: Session) -> ExperimentRecord:
    interviewing = cfg.mode is not InterviewMode.INITIAL_PROFILE
    if interviewing and provider is None:
        raise ValueError("interview modes need an answer provider")
    started = time.perf_counter()
    stats = _LlmStats()
    h = _register(client)
    profile = _setup_profile(client, h, candidate)
    cohort = _ok(client.post(f"{API}/cohorts/auto", headers=h, params={"profile_id": profile["profile_id"]}), 201)
    qa: list[dict] = []
    assessments: list[dict] = []
    ranking: list[dict] = []
    rubric_versions: dict = {}
    model_info: dict = {"provider": None}
    interview_id = None
    if not cohort["empty"]:
        db.expire_all()
        snap = db.get(CohortSnapshot, cohort["cohort_id"])
        if interviewing:
            with _timed_model(stats) as factory:
                model_info = _model_info(factory(), factory)
                interview_id, qa = _interview(client, h, db, snap, cfg, candidate, provider)
            if "served_models" in model_info:
                model_info["served_models"] = sorted(stats.served)
            db.expire_all()
            assessments = _latest_assessments(db, interview_id)
        # Mode A: scores={} (every criterion unknown); self-ratings act only through the T_v/J_v tie-break.
        ranking = _rank(db, snap, profile, _scores(assessments))
        rubric_versions = _rubric_versions(db, snap, interview_id)
    errors = {"ungraded_answers": sum(1 for q in qa if q["assessment_status"] != "ACCEPTED"),
              "fallback_questions": sum(1 for q in qa if q["question_source"] != "LLM_INTERVIEWER"),
              "llm_exceptions": stats.exceptions, "evaluator_rejections": stats.rejections,
              "empty_cohort": bool(cohort["empty"])}
    return ExperimentRecord(
        experiment_id=experiment_id, candidate_id=candidate.candidate_id, mode=cfg.mode.value, config=cfg.to_json(),
        cohort_id=cohort["cohort_id"] or "", cohort_sha256=cohort["sha256"] or "", profile_snapshot=profile,
        rubric_versions=rubric_versions, prompt_version=prompt_version(), model_info=model_info,
        algorithm_version=ALGORITHM_VERSION, qa=qa, assessments=assessments, ranking=ranking,
        timings={"total_s": round(time.perf_counter() - started, 6), "llm_wait_s": round(stats.wait_s, 6),
                 "calls": stats.calls},
        errors=errors, answer_source=getattr(provider, "source", "UNKNOWN") if interviewing else "NONE",
        interview_id=interview_id)


def rerank(record: ExperimentRecord, db: Session) -> list[dict]:
    """Ranking recomputed from the stored assessments, profile snapshot and cohort snapshot; no model call.
    Raises ValueError when the cohort snapshot or the seeded rubric versions differ from the recorded ones."""
    if not record.cohort_id:
        return []
    snap = db.get(CohortSnapshot, record.cohort_id)
    if snap is None or snap.sha256 != record.cohort_sha256:
        raise ValueError(f"cohort snapshot {record.cohort_id} missing or changed (sha256 mismatch)")
    current = _seeded_versions(db, snap)
    # auto-1 rubrics (LLM-proposed for actions without a seeded rubric) never enter rubric_map, so ranking ignores them
    expected = {**{a: v for a, v in record.rubric_versions.items() if v == "auto-1" and a not in current}, **current}
    if dict(sorted(expected.items())) != dict(sorted(record.rubric_versions.items())):
        diff = sorted(a for a in set(expected) | set(record.rubric_versions)
                      if expected.get(a) != record.rubric_versions.get(a))
        raise ValueError(f"rubric versions changed since the run for actions {diff[:10]}")
    return _rank(db, snap, record.profile_snapshot, _scores(record.assessments))
