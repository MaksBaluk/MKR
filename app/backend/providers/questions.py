"""Curated question bank. FREE_TEXT is served first; MULTIPLE_CHOICE is an optional second check."""
import json
from functools import lru_cache
from pathlib import Path

BANK_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "questions.json"


@lru_cache(maxsize=1)
def question_bank() -> dict[str, list[dict]]:
    return json.loads(BANK_PATH.read_text(encoding="utf-8"))


def next_question(action: str, previously_asked: int) -> dict | None:
    options = sorted(question_bank().get(action, []), key=lambda q: q["kind"] != "FREE_TEXT")
    return dict(options[previously_asked]) if previously_asked < len(options) else None
