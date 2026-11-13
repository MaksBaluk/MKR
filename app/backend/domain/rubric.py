"""Competency rubric 0-3 and strict validation of LLM grading output.

Ruling: one shared observable rubric for all competencies (not per-competency text) — the lean MVP
has no per-competency rubric authoring; this version is recorded on every evidence row.
"""
import json
import re

RUBRIC_VERSION = "rubric-v1"
RUBRIC = {
    0: "Немає ознак: відповідь не містить релевантних дій або містить помилкові уявлення.",
    1: "Базово: згадує окремі дії чи інструменти без пояснення рішень або результатів.",
    2: "Впевнено: описує конкретний приклад, обґрунтовує вибір і спосіб перевірки результату.",
    3: "Просунуто: пояснює компроміси, діагностику складних випадків і вплив на результат.",
}
_FIELDS = {"level", "evidence_quote", "confidence", "uncertainty", "followup"}
_CONFIDENCE = {"LOW", "MEDIUM", "HIGH"}


def parse_grade(raw: str, answer: str = "") -> dict:
    """Validate provider JSON strictly. Any schema break raises ValueError; prose is never a level."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?|```$", "", text).strip()
    data = json.loads(text)
    if not isinstance(data, dict) or not _FIELDS <= set(data):
        raise ValueError("Grading JSON is missing required fields")
    level = data["level"]
    if level is not None and (isinstance(level, bool) or not isinstance(level, int) or not 0 <= level <= 3):
        raise ValueError("Level must be an integer 0-3 or null")
    if data["confidence"] not in _CONFIDENCE:
        raise ValueError("Confidence must be LOW, MEDIUM or HIGH")
    quote, uncertainty, followup = data["evidence_quote"], data["uncertainty"], data["followup"]
    if not isinstance(quote, str) or not isinstance(uncertainty, str) or not (followup is None or isinstance(followup, str)):
        raise ValueError("Grading text fields have invalid types")
    if level is not None and (not quote.strip() or quote.strip() not in answer):
        level, uncertainty = None, "NO_SUPPORTING_QUOTE"
    return {"level": level, "evidence_quote": quote[:300], "confidence": data["confidence"],
            "uncertainty": uncertainty[:300], "followup": (followup or None)}
