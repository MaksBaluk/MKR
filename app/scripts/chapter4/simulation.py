"""Deterministic simulation used by the chapter-4 experiments: SIMULATED, not a real LLM and not a real candidate.

SimulatedModel plays both LLM roles through the real ask/answer graphs (prompts, validation, retries are the product's):
- Interviewer: asks about the targeted criteria (followup goal if given, else the first two unmet criteria).
- Evaluator: grades a criterion only from sentences about it in the candidate's answers and quotes that sentence.
SimulatedCandidate answers a question from a hidden per-criterion truth and the question's difficulty.
Because the grade is a function of the hidden truth, evaluator MAE against it would be 0 by construction: never report it
as quality. The simulation exercises the planner, controller, follow-up targeting and ranking, nothing else."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

from backend.agents.prompts import INTERVIEWER_SYSTEM
from backend.seed import read_fixture

PHRASE = {"STRONG": "це моя щоденна практика, можу пояснити механізм і наслідки на прикладі",
          "PARTIAL": "розумію загальну ідею, але без конкретних деталей",
          "WEAK": "лише чув про це і не застосовував",
          "NONE": "не знаю цього і не працював"}
SCORE = {"STRONG": 0.85, "PARTIAL": 0.6, "WEAK": 0.3, "NONE": 0.0}
THRESHOLD = {"BASIC": 0.3, "INTERMEDIATE": 0.6, "ADVANCED": 0.8}
CRIT_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\.[a-z0-9_]+")
SENT_RE = re.compile(r"Щодо (" + CRIT_RE.pattern + r"): (" + "|".join(re.escape(p) for p in PHRASE.values()) + r")\.")
PHRASE_TO_LEVEL = {v: k for k, v in PHRASE.items()}


LEVEL_WORDS = {"BASIC": "на базовому рівні", "INTERMEDIATE": "на середньому рівні", "ADVANCED": "на просунутому рівні"}
TITLES = {c["criterion_id"]: c["title"] for r in read_fixture("rubrics.json")["rubrics"] for c in r["criteria"]}
QUESTIONS: dict[str, tuple[str, list[str]]] = {}  # question text -> (difficulty, targeted criterion ids), set by the stub


def _line(human: str, key: str) -> str:
    m = re.search(rf"^{key}: (.*)$", human, re.M)
    return m.group(1) if m else ""


class SimulatedModel:
    """Chat-model stand-in (invoke only). Counts nothing itself: the runner's timing proxy counts calls."""

    temperature = None
    max_tokens = None
    # "ALL_GRADED" (default, matches the product prompt: sufficient only when every criterion could be graded) or
    # "ASKED_STRONG" (permissive variant for a labelled sensitivity run: >=2 criteria graded, all graded ones >= 0.75).
    sufficiency = "ALL_GRADED"

    def invoke(self, messages, *a, **k):
        system, human = messages[0].content, messages[1].content
        return SimpleNamespace(content=self._question(human) if system == INTERVIEWER_SYSTEM else self._evaluate(human),
                               response_metadata={"model_name": "SIMULATED_STUB"})

    def _sufficient(self, criteria) -> bool:
        graded = [c["score"] for c in criteria if c["score"] is not None]
        if self.sufficiency == "ASKED_STRONG":
            return len(graded) >= 2 and all(x >= 0.75 for x in graded)
        return len(graded) == len(criteria)

    @staticmethod
    def _question(human: str) -> str:
        unmet = json.loads(_line(human, "unmet_criteria") or "[]")
        goal = re.search(r"<followup_goal>(.*?)</followup_goal>", human, re.S)
        targets = (json.loads(goal.group(1)).get("criterion_ids") if goal else None) or unmet[:2]
        diff = _line(human, "difficulty")
        name = json.loads(_line(human, "action_name") or '""')
        titles = " та ".join(f"«{TITLES.get(t, t)}»" for t in targets)
        text = f"Розкажіть {LEVEL_WORDS.get(diff, 'на середньому рівні')} про {name}: {titles}?"
        QUESTIONS[text] = (diff, list(targets))
        return text

    def _evaluate(self, human: str) -> str:
        allowed = json.loads(_line(human, "allowed_criterion_ids"))
        open_ids = json.loads(_line(human, "open_criterion_ids") or "null")
        action = json.loads(_line(human, "action_id"))
        version = json.loads(_line(human, "rubric_version"))
        latest: dict[str, tuple[str, str, str]] = {}  # criterion -> (turn_id, level, excerpt); later answers override
        for tid, body in re.findall(r'<candidate_answer turn_id="([^"]+)">(".*")</candidate_answer>', human):
            text = json.loads(body)
            for cid, phrase in SENT_RE.findall(text):
                if cid in allowed:
                    latest[cid] = (tid, PHRASE_TO_LEVEL[phrase], f"Щодо {cid}: {phrase}.")
        criteria = [{"criterion_id": c, "score": SCORE[latest[c][1]] if c in latest else None,
                     "reason": "оцінено за відповіддю" if c in latest else "у відповідях немає свідчень",
                     "evidence": [{"turn_id": latest[c][0], "exact_excerpt": latest[c][2]}] if c in latest else []}
                    for c in allowed]
        pool = open_ids if open_ids is not None else allowed
        gaps = [c for c in pool if c not in latest or SCORE[latest[c][1]] < 0.75]
        goal = ({"criterion_ids": gaps[:2], "reason": "Критерій не підтверджено або слабкий.",
                 "expected_evidence": "Конкретний приклад із практики."} if gaps else None)
        return json.dumps({"action_id": action, "rubric_version": version, "off_topic": False, "criteria": criteria,
                           "sufficient_evidence": self._sufficient(criteria),
                           "needs_followup": bool(goal), "followup_goal": goal}, ensure_ascii=False)


class SimulatedCandidate:
    """AnswerProvider: SIMULATED answers from hidden truth {candidate_id: {"base": {action_id: x}, "default": x}}."""

    source = "SIMULATED"

    def __init__(self, truth: Mapping[str, Mapping[str, Any]]):
        self.truth = truth

    def level_of(self, candidate_id: str, criterion_id: str, difficulty: str) -> str:
        t = self.truth[candidate_id]
        action = criterion_id.split(".")[0]
        base = t.get("criteria", {}).get(criterion_id, t.get("base", {}).get(action, t["default"]))
        jitter = (int(hashlib.sha256(f"{candidate_id}|{criterion_id}".encode()).hexdigest(), 16) % 3 - 1) * 0.1
        x = min(1.0, max(0.0, base + jitter))
        thr = THRESHOLD.get(difficulty, 0.6)
        return "STRONG" if x >= thr + 0.15 else "PARTIAL" if x >= thr else "WEAK" if x >= 0.15 else "NONE"

    def answer(self, candidate, turn) -> str:
        diff, ids = QUESTIONS.get(turn["question_text"], ("INTERMEDIATE", []))  # bank fallback question: unknown targets
        return " ".join(f"Щодо {c}: {PHRASE[self.level_of(candidate.candidate_id, c, diff)]}." for c in ids) or "Не знаю."


def model_factory():
    return SimulatedModel()
