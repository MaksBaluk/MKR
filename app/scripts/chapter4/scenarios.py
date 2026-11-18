"""Six adaptivity scenarios (+ ablation table) on the real product code with SIMULATED answers and evaluator.

Each scenario prints the actual inputs (candidate truth / scripted answer), the controller transitions stored on the
interview turns, and the resulting criterion states. Expectations are checked mechanically; a scenario that does not
behave as expected is reported as NOT_CONFIRMED, never adjusted away."""
from __future__ import annotations

import json
from dataclasses import dataclass

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.api.core as core
import backend.models  # noqa: F401
from backend.api.cohorts import _vacancy_revisions
from backend.api.core import rubric_map
from backend.db import Base, get_db
from backend.domain.core_flow import planner_state
from backend.domain.planner import coverage
from backend.domain.topic_summary import criterion_state
from backend.experiments.config import InterviewMode, config_for
from backend.experiments.providers import CandidateSpec
from backend.experiments.runner import run_experiment
from backend.main import app
from backend.models import CoreTurn, CriterionAssessment
from backend.seed import read_fixture, seed_database
from scripts.chapter4.common import OUT, write_json
from scripts.chapter4.simulation import (PHRASE, QUESTIONS, SimulatedCandidate, SimulatedModel, model_factory)

RUBRIC = {r["action_id"]: [c["criterion_id"] for c in r["criteria"]] for r in read_fixture("rubrics.json")["rubrics"]}


class RecordingModel(SimulatedModel):
    """Keeps the exact Interviewer/Evaluator inputs (the product prompts) for the scenario evidence."""

    log: list[dict] = []

    def invoke(self, messages, *a, **k):
        res = super().invoke(messages, *a, **k)
        kind = "INTERVIEWER" if "INTERVIEWER" in str(messages[0].content)[:200].upper() or "інтерв" in str(messages[0].content)[:300].lower() else "EVALUATOR"
        RecordingModel.log.append({"role": kind, "input": messages[1].content, "output": res.content})
        return res


@dataclass
class Result:
    turns: list[dict]
    assessments: list[dict]
    log: list[dict]
    record: object


class Env:
    def __enter__(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.Session() as s:
            seed_database(s, demo_mode=False)

        def override():
            with self.Session() as session:
                yield session

        self.original, self.saved = core.get_chat_model, dict(app.dependency_overrides)
        app.dependency_overrides[get_db] = override
        self.client = TestClient(app).__enter__()
        self.db = self.Session()
        return self

    def __exit__(self, *exc):
        core.get_chat_model = self.original
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self.saved)
        self.db.close()
        self.client.__exit__(*exc)
        self.engine.dispose()

    def drive(self, cand: CandidateSpec, provider, budget: int = 12, **over) -> Result:
        RecordingModel.log = []
        core.get_chat_model = lambda: RecordingModel()
        rec = run_experiment("ch4-scn", config_for(InterviewMode.ADAPTIVE_INTERVIEW, total_budget=budget, **over), cand,
                             provider, self.client, self.db)
        turns = []
        for t in self.db.scalars(select(CoreTurn).where(CoreTurn.interview_id == rec.interview_id).order_by(CoreTurn.sequence)).all():
            turns.append({"seq": t.sequence, "action": t.action_id, "difficulty": t.difficulty, "reason": t.difficulty_reason,
                          "followup_reason": t.followup_reason, "targets": t.target_criteria, "eval_goal": t.eval_goal,
                          "controller_after": t.controller_after, "question": t.question_text, "answer": t.answer_text})
        return Result(turns, rec.assessments, list(RecordingModel.log), rec)


class FixedTruth(SimulatedCandidate):
    def __init__(self, cid, default, base=None, criteria=None):
        super().__init__({cid: {"default": default, "base": base or {}, "criteria": criteria or {}}})


def cand(cid, level, years, title="Python Developer"):
    return CandidateSpec(cid, title, years, level, "python", "Київ", "remote", {})


def states(assessments, action):
    return {a["criterion_id"]: {"score": a["score"], "state": criterion_state(a["score"], bool(a.get("sufficient_evidence")))}
            for a in assessments if a["action_id"] == action}


def topic_rows(turns, action):
    return [{k: t[k] for k in ("seq", "difficulty", "reason", "followup_reason", "targets", "eval_goal")} | {"level_after": (t["controller_after"] or {}).get("level")}
            for t in turns if t["action"] == action]


def build() -> dict:
    out = {"label": "SIMULATED (deterministic stub evaluator and candidate); not a real LLM, not a real candidate", "scenarios": []}
    with Env() as env:
        # S1 junior answers basics correctly -> difficulty rises
        class JuniorBasics(SimulatedCandidate):
            """First answer grades every criterion of the topic (all but the last STRONG, the last PARTIAL): the product
            forces sufficient_evidence=false while any criterion is null, so a level rise needs a fully graded answer."""
            def answer(self, candidate, turn):
                ids = RUBRIC[turn["action_id"]]
                if turn["ordinal_in_topic"] == 1:
                    return " ".join(f"Щодо {c}: {PHRASE['STRONG' if c != ids[-1] else 'PARTIAL']}." for c in ids)
                return super().answer(candidate, turn)
        r = env.drive(cand("s1-junior", "junior", 1), JuniorBasics({"s1-junior": {"default": 0.5}}))
        first = r.turns[0]["action"]
        rows = topic_rows(r.turns, first)
        out["scenarios"].append({"id": "S1", "title": "Junior відповідає правильно на базові питання", "input": "junior, 1 year; first answer: all criteria of the topic graded, the last one PARTIAL, the rest STRONG",
                                 "expected": "start BASIC; a STRONG decision (sufficient_evidence=true, mean >= 0.75) raises the level one step while the goal stays open",
                                 "topic_trace": rows, "difficulty_sequence": [t["difficulty"] for t in r.turns],
                                 "note": "BASIC->INTERMEDIATE->ADVANCED over several consecutive STRONG decisions is covered by tests/test_difficulty*.py, not by this run",
                                 "confirmed": rows[0]["difficulty"] == "BASIC" and len(rows) > 1 and rows[1]["difficulty"] == "INTERMEDIATE" and rows[1]["reason"] == "STRONG"})
        # S2 senior does not demonstrate an advanced criterion -> diagnostic step down
        class WeakFirstTopic(SimulatedCandidate):
            """Strong everywhere except the topic asked first (the planner picks it): the senior cannot show its criteria."""
            first = None

            def answer(self, candidate, turn):
                self.first = self.first or turn["action_id"]
                ids = RUBRIC[turn["action_id"]]
                tag = "WEAK" if turn["action_id"] == self.first else "STRONG"
                return " ".join(f"Щодо {c}: {PHRASE[tag]}." for c in ids if c in QUESTIONS.get(turn["question_text"], ("", []))[1])
        r = env.drive(cand("s2-senior", "senior", 8, "Senior Python Engineer"), WeakFirstTopic({"s2-senior": {"default": 0.9}}))
        topic = r.turns[0]["action"]
        rows = topic_rows(r.turns, topic)
        out["scenarios"].append({"id": "S2", "title": "Senior не демонструє складного критерію", "input": "senior, 8 years; every criterion of the first topic answered WEAK, all other topics STRONG",
                                 "expected": "ADVANCED start; WEAK evidence lowers the level toward BASIC (diagnostic question)", "topic": topic,
                                 "topic_trace": rows, "confirmed": rows[0]["difficulty"] == "ADVANCED" and any(x["reason"].startswith("WEAK") for x in rows[1:]) and rows[-1]["difficulty"] != "ADVANCED"})
        # S3 strong answer about PostgreSQL transactions does not confirm indexes
        class PgTransactionsOnly(SimulatedCandidate):
            def answer(self, candidate, turn):
                if turn["action_id"] == "postgresql" and turn["ordinal_in_topic"] == 1:
                    return f"Щодо postgresql.transactions: {PHRASE['STRONG']}."
                return " ".join(f"Щодо {c}: {PHRASE['STRONG']}." for c in RUBRIC[turn["action_id"]])  # other topics close fast
        r = env.drive(cand("s3-mid", "middle", 4), PgTransactionsOnly({"s3-mid": {"default": 0.6}}), budget=30)
        r_rows = topic_rows(r.turns, "postgresql")
        first_rev = {a.criterion_id: a.score for a in env.db.scalars(select(CriterionAssessment).where(
            CriterionAssessment.session_id == r.record.interview_id, CriterionAssessment.action_id == "postgresql",
            CriterionAssessment.revision == 1)).all()}
        pg = states(r.assessments, "postgresql")
        pg_turns = topic_rows(r.turns, "postgresql")
        out["scenarios"].append({"id": "S3", "title": "Сильна відповідь про транзакції не підтверджує індекси", "input": "first postgresql answer: only 'postgresql.transactions' STRONG",
                                 "expected": "after that answer transactions=0.85 and indexes stay unknown (null, UNKNOWN); the next question targets indexes; later evidence may confirm them",
                                 "scores_after_first_answer_revision_1": first_rev,
                                 "criterion_states_final_after_follow_ups": pg, "topic_trace": pg_turns,
                                 "confirmed": bool(pg_turns) and first_rev.get("postgresql.transactions") == 0.85 and first_rev.get("postgresql.indexes") is None and
                                              "postgresql.indexes" in (pg_turns[1]["targets"] if len(pg_turns) > 1 else [])})
        # S4 evaluator finds an unknown criterion -> Interviewer receives a concrete target
        r = env.drive(cand("s4-mid", "middle", 4), FixedTruth("s4-mid", 0.9))
        t0 = r.turns[0]
        with_goal = next((t for t in r.turns if t["eval_goal"]), None)
        nxt = next((t for t in r.turns if with_goal and t["seq"] == with_goal["seq"] + 1), None)
        interviewer_in = next((e["input"] for e in r.log if e["role"] == "INTERVIEWER" and with_goal and "followup_goal: none" not in e["input"]), None)
        out["scenarios"].append({"id": "S4", "title": "Evaluator знаходить невідомий критерій → цільове уточнення", "input": "truth 0.9; first question covers 2 of 4 criteria",
                                 "expected": "stored eval_goal names the unknown criteria; next question's target_criteria == goal ids; Interviewer input contains the goal",
                                 "answered_turn_goal": with_goal["eval_goal"] if with_goal else None, "next_turn_targets": nxt["targets"] if nxt else None,
                                 "next_turn_followup_reason": nxt["followup_reason"] if nxt else None,
                                 "interviewer_input_with_goal": (interviewer_in or "")[:900],
                                 "confirmed": bool(with_goal and nxt and nxt["action"] == with_goal["action"] and nxt["targets"] == with_goal["eval_goal"]["criterion_ids"] and interviewer_in)})
        # S6 sufficient evidence closes the topic early
        class AllCriteriaStrong(SimulatedCandidate):
            def answer(self, candidate, turn):
                return " ".join(f"Щодо {c}: {PHRASE['STRONG']}." for c in RUBRIC[turn["action_id"]])
        r = env.drive(cand("s6-mid", "middle", 4), AllCriteriaStrong({"s6-mid": {"default": 0.9}}), budget=6)
        per_topic = {}
        for t in r.turns:
            per_topic[t["action"]] = per_topic.get(t["action"], 0) + 1
        out["scenarios"].append({"id": "S6", "title": "Достатні докази завершують тему раніше ліміту", "input": "first answer evidences every criterion of the topic as STRONG",
                                 "expected": "each topic closes after 1 question (< 5 cap, < min-two rule because sufficient and >= 0.75)",
                                 "questions_per_topic": per_topic, "first_topic_trace": topic_rows(r.turns, r.turns[0]["action"]),
                                 "confirmed": all(v == 1 for v in per_topic.values()) and len(per_topic) >= 2})
        # S5 OR alternative: confirming one alternative closes the group (planner level, real cohort)
        revs = _vacancy_revisions(env.db, "python")
        v = next(x for x in revs if x["id"] == "python-01")
        gi, g = next((i, g) for i, g in enumerate(v["groups"]) if len(g["alternatives"]) > 1)
        alts = [a["competency_id"] for a in g["alternatives"]]
        rub = rubric_map(env.db, {a for x in revs for gr in x["groups"] for al in gr["alternatives"] for a in [al["competency_id"]]}, {})
        first_alt = g["alternatives"][0]
        conf = {c: 0.9 for c in first_alt["criterion_ids"]}
        s0, w = planner_state(revs, {}, rub)
        s1, _ = planner_state(revs, conf, rub)
        key = (v["id"], gi)
        other = alts[1]
        out["scenarios"].append({"id": "S5", "title": "Підтверджена OR-альтернатива не витрачає питання на іншу", "input": f"group {key} requires {alts} (OR); all required criteria of {alts[0]} scored 0.9",
                                 "expected": "the group is open before and closed after; the second alternative gains nothing from this group",
                                 "group_open_before": key in s0.open_groups, "group_open_after": key in s1.open_groups,
                                 "open_alternatives_before": sorted(s0.open_alternatives.get(key, [])), "open_alternatives_after": sorted(s1.open_alternatives.get(key, [])),
                                 "coverage_gain_of_second_alternative_before": round(coverage(s0, w, frozenset({other})), 6),
                                 "coverage_gain_of_second_alternative_after": round(coverage(s1, w, frozenset({other})), 6),
                                 "note": "gain after can stay > 0 only through other vacancies that still need the second competency",
                                 "confirmed": key in s0.open_groups and key not in s1.open_groups and not (set(s1.open_alternatives.get(key, [])) & {other})})
    out["scenarios"].sort(key=lambda s: s["id"])
    out["summary"] = {s["id"]: ("CONFIRMED" if s["confirmed"] else "NOT_CONFIRMED") for s in out["scenarios"]}
    write_json(OUT / "adaptivity_scenarios.json", out)
    (OUT / "adaptivity_scenarios.md").write_text(to_md(out), encoding="utf-8")
    return out


def to_md(out: dict) -> str:
    lines = ["# Сценарії адаптивності (SIMULATED)", "", out["label"], "",
             "Усі сценарії проходять через реальні ask/answer-графи, планувальник, контролер складності та ранжування продукту; "
             "імітовані лише відповіді кандидата й оцінювач. Дані з `adaptivity_scenarios.json` (генерується `scripts/chapter4/scenarios.py`).", "",
             "| Сценарій | Результат |", "|---|---|"]
    lines += [f"| {s['id']} {s['title']} | **{out['summary'][s['id']]}** |" for s in out["scenarios"]]
    for s in out["scenarios"]:
        lines += ["", f"## {s['id']}. {s['title']} — {out['summary'][s['id']]}", "", f"- Вхід: {s['input']}", f"- Очікування: {s['expected']}"]
        rest = {k: v for k, v in s.items() if k not in ("id", "title", "input", "expected", "confirmed")}
        lines += ["- Фактичні дані:", "", "```json", json.dumps(rest, ensure_ascii=False, indent=1), "```"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    o = build()
    print(json.dumps(o["summary"]))
    for s in o["scenarios"]:
        print(s["id"], s["confirmed"])
