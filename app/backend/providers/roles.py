"""Interviewer and Evaluator LLM roles behind a mockable transport. CLAUDE_PROMPT §3.

Roles are separate prompts; the Python controller owns topic selection, budgets and ranking.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Literal, Protocol

from pydantic import ValidationError

from backend.domain.assessment import EvaluatorOutput, validate_against_context

ErrorKind = Literal["TIMEOUT", "RATE_LIMIT", "MALFORMED", "OFFLINE"]
RETRYABLE: dict[str, int] = {"TIMEOUT": 2, "RATE_LIMIT": 2, "MALFORMED": 1}
INTERVIEWER_TIMEOUT_S = 25.0   # fail fast: the bank question is an acceptable fallback
EVALUATOR_TIMEOUT_S = 50.0
INTERVIEWER_RETRIES: dict[str, int] = {"TIMEOUT": 0, "RATE_LIMIT": 0, "MALFORMED": 1}
EVALUATOR_RETRIES: dict[str, int] = {"TIMEOUT": 0, "RATE_LIMIT": 1, "MALFORMED": 1}


class LLMError(Exception):
    def __init__(self, kind: ErrorKind):
        super().__init__(kind)
        self.kind = kind


class LLMTransport(Protocol):
    def complete(self, system: str, user: str, *, timeout_s: float) -> str: ...


INTERVIEWER_SYSTEM = (
    "Ти інтерв'юер. Постав одне відкрите ситуаційне питання українською про вказану професійну дію. "
    "Не змінюй обрану дію, не вибирай іншу тему, не змінюй ліміти та не оцінюй кандидата. "
    "Відповідь — лише текст питання."
)

EVALUATOR_SYSTEM = (
    "Ти оцінювач. Оціни ВСІ наведені відповіді для однієї дії за рубрикою. "
    "Поверни лише JSON за схемою: action_id, rubric_version, criteria[criterion_id, score (0..1 або null), "
    "reason, evidence[turn_id, exact_excerpt]], sufficient_evidence, needs_followup, followup_goal, limitations. "
    "Використовуй ЛИШЕ criterion_id зі списку allowed_criterion_ids, по одному елементу на кожен ID, нічого не вигадуй. "
    "Шкала score: [0,0.25) суттєво хибно, [0.25,0.5) слабко, [0.5,0.75) частково, [0.75,0.9) добре з недоліками, "
    "[0.9,1] майже повністю. Цитати мають бути дослівними фрагментами відповіді. Без доказів став score = null. "
    "Поле reason пиши українською. Загальне твердження про досвід без технічних деталей і прикладів не заслуговує "
    "оцінки вище 0.5: не виводь високий рівень лише з гладкого тексту."
)


def _with_retries(call, kinds_retry: Mapping[str, int] = RETRYABLE):
    attempts: dict[str, int] = {}
    while True:
        try:
            return call()
        except LLMError as exc:
            attempts[exc.kind] = attempts.get(exc.kind, 0) + 1
            limit = kinds_retry.get(exc.kind, 0)
            if attempts[exc.kind] > limit:
                raise


def interviewer_question(
    transport: LLMTransport,
    *,
    action_name: str,
    rubric_criteria: Sequence[str],
    previous_turns: Sequence[str],
    followup_goal: str | None,
) -> str:
    user = json.dumps({
        "action": action_name,
        "unmet_criteria": list(rubric_criteria),
        "previous_answers": list(previous_turns)[-3:],
        "followup_goal": followup_goal,
    }, ensure_ascii=False)

    def call() -> str:
        text = transport.complete(INTERVIEWER_SYSTEM, user, timeout_s=INTERVIEWER_TIMEOUT_S).strip()
        if not text:
            raise LLMError("MALFORMED")
        return text

    return _with_retries(call, INTERVIEWER_RETRIES)


def evaluator_assess(
    transport: LLMTransport,
    *,
    action_id: str,
    rubric_version: str,
    allowed_criteria: set[str],
    turns: Mapping[str, str],
) -> EvaluatorOutput:
    user = json.dumps({"action_id": action_id, "rubric_version": rubric_version,
                       "allowed_criterion_ids": sorted(allowed_criteria), "turns": turns}, ensure_ascii=False)

    def call() -> EvaluatorOutput:
        raw = transport.complete(EVALUATOR_SYSTEM, user, timeout_s=EVALUATOR_TIMEOUT_S)
        try:
            out = EvaluatorOutput.model_validate(json.loads(raw))
        except (ValueError, ValidationError) as exc:
            raise LLMError("MALFORMED") from exc
        if validate_against_context(out, allowed_criteria, turns):
            raise LLMError("MALFORMED")
        return out

    return _with_retries(call, EVALUATOR_RETRIES)
