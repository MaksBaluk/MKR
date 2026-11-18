"""LangGraph ask/answer graphs for the Interviewer and Evaluator. Python keeps topic choice, budgets and ranking.

Models are invoked for plain text and parsed here (free OpenRouter models are unreliable with tool modes).
Failures are logged by kind only: never prompts, answers or keys.
"""
from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from backend.agents.prompts import (EVALUATOR_SYSTEM, INTERVIEWER_SYSTEM, format_evaluator_input,
                                    format_interviewer_input)
from backend.domain.assessment import EvaluatorOutput, sanitize_goal, validate_against_context
from backend.providers.questions import next_question as bank_question

log = logging.getLogger("competencematch.llm")

# Slow providers (free OpenRouter models) are waited for: no wall-clock limit by default. Set a number of seconds to make
# a late call count as a provider failure (a stalled stream would otherwise hold the request).
HARD_DEADLINE_SECONDS: float | None = None
_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="llm")


# Free provider tiers answer 429 under load: wait and try again instead of losing the answer (seconds per retry).
RATE_LIMIT_WAITS: tuple[float, ...] = (15.0, 30.0, 60.0)


def _invoke(model, messages):
    for wait in (*RATE_LIMIT_WAITS, None):
        future = _POOL.submit(model.invoke, messages)
        try:
            return future.result(timeout=HARD_DEADLINE_SECONDS)
        except FutureTimeout as exc:
            future.cancel()
            raise TimeoutError("LLM call exceeded the hard deadline") from exc
        except Exception as exc:  # noqa: BLE001 - only the provider's rate limit is retried, the rest is re-raised
            if wait is None or "RateLimit" not in type(exc).__name__:
                raise
            log.warning("llm rate limited, retrying in %ss", wait)
            time.sleep(wait)

ALLOWLIST = ("FastAPI", "Django", "PostgreSQL", "Docker Compose", "Docker", "AWS", "CI/CD", "Kafka", "Redis", "Celery",
             "pytest", "SQL", "REST", "API", "Git", "Linux", "Kubernetes", "SQLAlchemy", "Python", "Figma", "SEO",
             "SMM", "UX", "UI", "GA4", "CRM", "Terraform", "Ansible", "Excel", "Jira", "React", "Google Analytics",
             "Notion", "Slack", "GitHub", "GitLab", "Nginx", "Grafana", "Prometheus", "Elasticsearch", "RabbitMQ",
             "Flask", "Pydantic", "Alembic", "TypeScript", "JavaScript", "HTML", "CSS", "JSON", "HTTP", "gRPC",
             "GraphQL", "SaaS", "B2B", "KPI", "ROI", "CTR", "CPA", "A/B", "Adobe", "Photoshop", "Illustrator",
             "Sketch", "WCAG")
_ALLOW_RE = re.compile("|".join(re.escape(w) for w in sorted(ALLOWLIST, key=len, reverse=True)), re.I)
# Real leaks only: a 0.x decimal (not a version like 3.11), score words followed by a number, "рівень:", rubric.
_SCORE_RE = re.compile(r"(?<![\d.])0[.,]\d+(?!\d)|\b(?:оцінк\w*|балів|бали|бал)\s*:?\s*\d|\bрівен[ья]\s*:|\bрубрик", re.I)
_PERCENT_SCORE_RE = re.compile(r"\b(?:оцінк|рівен|рівн|бал(?:и|ів)?\b|рубрик|відсот)", re.I)
_ABBREV_RE = re.compile(r"\b(напр|тощо|т\.\s?д|т\.\s?п|ін|див|пор|тис|грн)\.", re.I)
REFUSAL = "Я можу обговорювати лише професійну тему цієї розмови."


class AskState(TypedDict, total=False):
    action_id: str
    action_name: str
    summary: str
    unmet_criteria: list[str]
    previous_answers: list[str]
    asked_questions: list[str]  # question texts already shown for this action (the fallback never repeats them)
    followup_goal: dict | None  # validated FollowupGoal.model_dump(): criterion_ids, reason, expected_evidence
    off_topic_detected: bool
    candidate_level: str | None
    years_experience: int | None
    difficulty: str | None  # BASIC | INTERMEDIATE | ADVANCED from the DifficultyController
    question: str | None
    source: str


class AnswerState(TypedDict, total=False):
    action_id: str
    rubric_version: str
    allowed_criterion_ids: list[str]
    bands: dict[str, str] | None  # per-criterion anchored bands of a seeded rubric
    turns: dict[str, str]
    open_criterion_ids: list[str] | None  # None/absent: every allowed criterion is open
    turn_meta: dict[str, dict] | None  # turn_id -> {target_criteria}; context, never a score
    allowed_practice_ids: list[str]  # professional-practice criteria to grade from the same answers; empty: none
    practice_bands: dict[str, str] | None
    attempt: int
    output: EvaluatorOutput | None
    status: str
    reason: str | None
    retryable: bool


@dataclass(frozen=True)
class AskResult:
    question_text: str
    source: Literal["LLM_INTERVIEWER", "FALLBACK_UNGRADED"]


@dataclass(frozen=True)
class AnswerResult:
    output: EvaluatorOutput | None
    status: Literal["ACCEPTED", "UNGRADED"]
    reason: str | None
    off_topic: bool


def _text(resp) -> str:
    content = getattr(resp, "content", resp)
    if isinstance(content, list):
        content = "".join(p if isinstance(p, str) else str(p.get("text", "")) for p in content)
    return content if isinstance(content, str) else ""


# ---- ask graph
def validate_question(text: str, off_topic: bool) -> str | None:
    """Return a rejection reason, or None when the question is acceptable."""
    if not text.strip():
        return "EMPTY"
    flat = _ABBREV_RE.sub(lambda m: m.group(0).replace(".", "").replace(" ", ""), text.strip())
    sentences = [s for s in re.split(r"(?<=[.!?…])\s+", flat) if s.strip()]
    if len(sentences) > (3 if off_topic else 2) or len(flat.split()) > (50 if off_topic else 35):
        return "TOO_LONG"
    if flat.count("?") > 1:
        return "MULTI_PART"
    letters = [c for c in _ALLOW_RE.sub("", text) if c.isalpha()]
    if not letters or sum("Ѐ" <= c <= "ӿ" for c in letters) / len(letters) < 0.7:
        return "NOT_UKRAINIAN"
    if _SCORE_RE.search(text) or ("%" in text and _PERCENT_SCORE_RE.search(text)):
        return "LEAKS_SCORING"
    return None


def _bank_text(action_id: str, label: str, asked: list[str] | None = None) -> str:
    """First free-text bank question not shown yet; a generic ask only when the bank is exhausted."""
    asked = asked or []
    for i in range(12):
        q = bank_question(action_id, i)
        if q is None:
            break
        if q.get("kind") == "FREE_TEXT" and q["text"] not in asked:
            return q["text"]
    return f"Розкажіть про ваш практичний досвід: {label}. Наведіть конкретний приклад."


def _build_ask(model):
    def write_question(s: AskState) -> dict:
        if model is None:
            return {"question": None}
        try:
            user = format_interviewer_input(
                action_name=s["action_name"], topic_summary=s.get("summary", ""),
                unmet_criteria=s.get("unmet_criteria", []), previous_answers=s.get("previous_answers", [])[-3:],
                followup_goal=s.get("followup_goal"), off_topic_detected=s.get("off_topic_detected", False),
                candidate_level=s.get("candidate_level"), years_experience=s.get("years_experience"),
                asked_questions=s.get("asked_questions", []), difficulty=s.get("difficulty"))
            resp = _invoke(model, [SystemMessage(INTERVIEWER_SYSTEM), HumanMessage(user)])
            question = _text(resp).strip().strip('"«»').strip()
            if validate_question(question, s.get("off_topic_detected", False)) in ("TOO_LONG", "MULTI_PART"):
                # one more try with the reason, before the bank is used
                retry = user + "\n\nПопередня версія задовга або з кількома питаннями. Дай ОДНЕ питання до 25 слів."
                resp = _invoke(model, [SystemMessage(INTERVIEWER_SYSTEM), HumanMessage(retry)])
                question = _text(resp).strip().strip('"«»').strip()
            return {"question": question}
        except Exception as exc:  # noqa: BLE001 - any provider failure means bank fallback
            log.warning("interviewer failed action=%s kind=%s", s.get("action_id"), type(exc).__name__)
            return {"question": None}

    def validate(s: AskState) -> dict:
        q = s.get("question")
        if q is None:
            return {}
        reason = validate_question(q, s.get("off_topic_detected", False))
        if reason:
            log.warning("interviewer question rejected action=%s kind=%s", s.get("action_id"), reason)
            return {"question": None}
        return {"source": "LLM_INTERVIEWER"}

    def fallback(s: AskState) -> dict:
        text = _bank_text(s["action_id"], s["action_name"], s.get("asked_questions"))
        if s.get("off_topic_detected"):
            text = f"{REFUSAL} {text}"
        return {"question": text, "source": "FALLBACK_UNGRADED"}

    g = StateGraph(AskState)
    g.add_node("write_question", write_question)
    g.add_node("validate_question", validate)
    g.add_node("fallback_bank", fallback)
    g.add_edge(START, "write_question")
    g.add_edge("write_question", "validate_question")
    g.add_conditional_edges("validate_question", lambda s: "done" if s.get("question") else "fallback_bank",
                            {"done": END, "fallback_bank": "fallback_bank"})
    g.add_edge("fallback_bank", END)
    return g.compile()


def run_ask(state: AskState, model) -> AskResult:
    out = _build_ask(model).invoke(state)
    return AskResult(out["question"], out["source"])


# ---- answer graph
def _parse(raw: str) -> EvaluatorOutput:
    text = re.sub(r"```(?:json)?", "", raw)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no json object")
    return EvaluatorOutput.model_validate_json(text[start:end + 1])


def _build_answer(model):
    def evaluate(s: AnswerState) -> dict:
        if model is None:
            return {"status": "UNGRADED", "reason": "NO_MODEL", "retryable": False, "output": None}
        user = format_evaluator_input(action_id=s["action_id"], rubric_version=s["rubric_version"],
                                      allowed_criterion_ids=s["allowed_criterion_ids"], bands=s.get("bands"),
                                      turns=s["turns"], open_criterion_ids=s.get("open_criterion_ids"),
                                      turn_meta=s.get("turn_meta"),
                                      practice_criterion_ids=s.get("allowed_practice_ids") or None,
                                      practice_bands=s.get("practice_bands"))
        try:
            raw = _text(_invoke(model, [SystemMessage(EVALUATOR_SYSTEM), HumanMessage(user)]))
        except Exception as exc:  # noqa: BLE001 - timeouts/connection errors are not retried
            kind = type(exc).__name__
            log.warning("evaluator failed action=%s kind=%s", s["action_id"], kind)
            return {"status": "UNGRADED", "reason": f"ERROR:{kind}", "retryable": False, "output": None}
        try:
            return {"output": _parse(raw), "status": "PENDING", "reason": None, "retryable": True}
        except (ValueError, ValidationError):
            log.warning("evaluator output malformed action=%s", s["action_id"])
            return {"output": None, "status": "UNGRADED", "reason": "MALFORMED", "retryable": True}

    def validate_output(s: AnswerState) -> dict:
        out = s.get("output")
        if out is None:
            return {}
        errors = validate_against_context(out, set(s["allowed_criterion_ids"]), s["turns"],
                                          frozenset(s.get("allowed_practice_ids") or ()))
        if not out.criteria and not out.off_topic:
            errors.append("no criteria")
        if errors:
            log.warning("evaluator output invalid action=%s count=%d", s["action_id"], len(errors))
            return {"output": None, "status": "UNGRADED", "reason": "INVALID", "retryable": True}
        allowed = set(s["allowed_criterion_ids"])
        open_ids = s.get("open_criterion_ids")
        goal = sanitize_goal(out.followup_goal, allowed, allowed if open_ids is None else open_ids)
        out = out.model_copy(update={"followup_goal": goal})
        if not out.off_topic and any(c.score is None for c in out.criteria):
            out = out.model_copy(update={"sufficient_evidence": False})  # a null criterion is never sufficient evidence
        if out.off_topic:  # nothing from an off-topic answer may reach ranking
            out = out.model_copy(update={k: [c.model_copy(update={"score": None, "evidence": []})
                                                for c in getattr(out, k)] for k in ("criteria", "practice")})
        return {"output": out, "status": "ACCEPTED", "reason": None}

    def retry_once(s: AnswerState) -> dict:
        return {"attempt": s.get("attempt", 1) + 1}

    def route(s: AnswerState) -> str:
        return "retry_once" if s.get("status") != "ACCEPTED" and s.get("retryable") and s.get("attempt", 1) < 2 else "done"

    g = StateGraph(AnswerState)
    g.add_node("evaluate", evaluate)
    g.add_node("validate_output", validate_output)
    g.add_node("retry_once", retry_once)
    g.add_edge(START, "evaluate")
    g.add_edge("evaluate", "validate_output")
    g.add_conditional_edges("validate_output", route, {"retry_once": "retry_once", "done": END})
    g.add_edge("retry_once", "evaluate")
    return g.compile()


def run_answer(state: AnswerState, model) -> AnswerResult:
    out = _build_answer(model).invoke({**state, "attempt": 1})
    if out.get("status") == "ACCEPTED":
        o = out["output"]
        return AnswerResult(o, "ACCEPTED", None, o.off_topic)
    return AnswerResult(None, "UNGRADED", out.get("reason"), False)
