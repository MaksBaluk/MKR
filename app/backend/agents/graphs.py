"""LangGraph ask/answer graphs for the Interviewer and Evaluator. Python keeps topic choice, budgets and ranking.

Models are invoked for plain text and parsed here (free OpenRouter models are unreliable with tool modes).
Failures are logged by kind only: never prompts, answers or keys.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from backend.agents.prompts import (EVALUATOR_SYSTEM, INTERVIEWER_SYSTEM, format_evaluator_input,
                                    format_interviewer_input)
from backend.domain.assessment import EvaluatorOutput, validate_against_context
from backend.providers.questions import next_question as bank_question

log = logging.getLogger("competencematch.llm")

ALLOWLIST = ("FastAPI", "Django", "PostgreSQL", "Docker", "AWS", "CI/CD", "Kafka", "Redis", "Celery", "pytest", "SQL",
             "REST", "API", "Git", "Linux", "Kubernetes", "SQLAlchemy", "Python", "Figma", "SEO", "SMM", "UX", "UI",
             "GA4", "CRM")
_ALLOW_RE = re.compile("|".join(re.escape(w) for w in sorted(ALLOWLIST, key=len, reverse=True)), re.I)
_SCORE_RE = re.compile(r"\d\s*[.,]\s*\d|%|рубрик|критері|(?:оцінк|бал|рівен|рівня|рівні)\w*\s*:?\s*\d", re.I)


class AskState(TypedDict, total=False):
    action_id: str
    action_name: str
    summary: str
    unmet_criteria: list[str]
    previous_answers: list[str]
    followup_goal: str | None
    off_topic_detected: bool
    question: str | None
    source: str


class AnswerState(TypedDict, total=False):
    action_id: str
    rubric_version: str
    allowed_criterion_ids: list[str]
    turns: dict[str, str]
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
    sentences = [s for s in re.split(r"(?<=[.!?…])\s+", text.strip()) if s.strip()]
    if len(sentences) > (3 if off_topic else 2):
        return "TOO_LONG"
    letters = [c for c in _ALLOW_RE.sub("", text) if c.isalpha()]
    if not letters or sum("Ѐ" <= c <= "ӿ" for c in letters) / len(letters) < 0.7:
        return "NOT_UKRAINIAN"
    if _SCORE_RE.search(text):
        return "LEAKS_SCORING"
    return None


def _bank_text(action_id: str, label: str) -> str:
    banked = bank_question(action_id, 0)
    if banked is None or banked.get("kind") != "FREE_TEXT":
        banked = next((q for q in (bank_question(action_id, i) for i in range(6))
                       if q and q.get("kind") == "FREE_TEXT"), None)
    return banked["text"] if banked else f"Розкажіть про ваш практичний досвід: {label}. Наведіть конкретний приклад."


def _build_ask(model):
    def write_question(s: AskState) -> dict:
        if model is None:
            return {"question": None}
        try:
            user = format_interviewer_input(
                action_name=s["action_name"], topic_summary=s.get("summary", ""),
                unmet_criteria=s.get("unmet_criteria", []), previous_answers=s.get("previous_answers", [])[-3:],
                followup_goal=s.get("followup_goal"), off_topic_detected=s.get("off_topic_detected", False))
            resp = model.invoke([SystemMessage(INTERVIEWER_SYSTEM), HumanMessage(user)])
            return {"question": _text(resp).strip().strip('"«»').strip()}
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
        return {"question": _bank_text(s["action_id"], s["action_name"]), "source": "FALLBACK_UNGRADED"}

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
                                      allowed_criterion_ids=s["allowed_criterion_ids"], bands=None, turns=s["turns"])
        try:
            raw = _text(model.invoke([SystemMessage(EVALUATOR_SYSTEM), HumanMessage(user)]))
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
        errors = validate_against_context(out, set(s["allowed_criterion_ids"]), s["turns"])
        if not out.criteria and not out.off_topic:
            errors.append("no criteria")
        if errors:
            log.warning("evaluator output invalid action=%s count=%d", s["action_id"], len(errors))
            return {"output": None, "status": "UNGRADED", "reason": "INVALID", "retryable": True}
        if out.off_topic:  # nothing from an off-topic answer may reach ranking
            out = out.model_copy(update={"criteria": [c.model_copy(update={"score": None, "evidence": []})
                                                     for c in out.criteria]})
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
