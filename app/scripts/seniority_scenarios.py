"""SeniorityEstimator scenarios through the real API with a SIMULATED evaluator (not a real LLM, not a real
candidate). Run from app/:  uv run python scripts/seniority_scenarios.py

The product code runs unchanged: profile, system-selected cohort, adaptive interview (Q_t, caps, validation of the
Evaluator output, practice aggregation, finish hook), GET /interviews/{id}/level and GET /profiles/{id}/results.
Only the chat model is replaced: the Interviewer stub asks about the unmet criteria by title, the Evaluator stub grades
from a hidden per-criterion truth and quotes the candidate's answer verbatim. Because the grades are the hidden truth,
the scenarios show how the estimator and the API treat given evidence; they say nothing about evaluator quality.
The database is a throwaway in-memory SQLite seeded like the tests; the product database is never used.
"""
from __future__ import annotations

import json
import os
import re
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "sqlite+pysqlite://"  # never the configured product database
os.environ["LLM_PROVIDER"] = "disabled"  # the chat model is the SIMULATED stub below
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

import backend.api.core as core  # noqa: E402
from backend.api.level import attempt_evidence  # noqa: E402
from backend.domain.seniority import estimate  # noqa: E402
from backend.domain.seniority_policy import (PRACTICE_CRITERIA, PYTHON_BACKEND_V2, PYTHON_BACKEND_V3, Level,  # noqa: E402
                                             policy_for)
from backend.experiments.config import InterviewMode, config_for  # noqa: E402
from backend.models import CohortSnapshot, CoreInterview, CoreTurn  # noqa: E402
from scripts.chapter4.scenarios import Env  # noqa: E402
from scripts.chapter4.simulation import SimulatedModel  # noqa: E402

API = "/api/v1"
LABEL = "SIMULATED: deterministic stub Interviewer/Evaluator, scripted answers; not a real LLM and not a real candidate"
POLICY = policy_for("python")  # the current python policy (python-backend/v4): what new attempts are assessed with
# NOTE (audit D-8): TruthEvaluator grades the whole topic and all practice from every answer. It is an UPPER BOUND of
# evaluator generosity, not a realistic reachability estimate; see scripts/seniority_realistic.py for that.
CRITICAL = {r.level: r.critical for r in POLICY.rules}
ANSWER = ("У сервісі замовлень я сам обрав складений індекс, бо запит сканував усю таблицю; порівняв план через "
          "EXPLAIN до і після, а міграцію виконав без блокування таблиці.")


def _line(human: str, key: str):
    m = re.search(rf"^{key}: (.*)$", human, re.M)
    return json.loads(m.group(1)) if m else None


class TruthEvaluator(SimulatedModel):
    """SIMULATED Evaluator: score = truth(criterion id) (None = no evidence in the answer), quoting the latest answer."""

    def __init__(self, truth: Callable[[str], float | None]):
        self.truth = truth

    def _evaluate(self, human: str) -> str:
        turn_id = re.findall(r'turn_id="([^"]+)"', human)[-1]
        text = json.loads(re.findall(r'>(".*")</candidate_answer>', human)[-1])

        def item(cid: str) -> dict:
            score = self.truth(cid)
            return {"criterion_id": cid, "score": score, "reason": "SIMULATED: оцінка з прихованої істини",
                    "evidence": [] if score is None else [{"turn_id": turn_id, "exact_excerpt": text}]}

        criteria = [item(c) for c in _line(human, "allowed_criterion_ids")]
        out = {"action_id": _line(human, "action_id"), "rubric_version": _line(human, "rubric_version"),
               "off_topic": False, "criteria": criteria,
               "sufficient_evidence": all(c["score"] is not None for c in criteria)}
        practice = _line(human, "practice_criterion_ids")
        if practice:
            out["practice"] = [item(c) for c in practice]
        return json.dumps(out, ensure_ascii=False)

    def invoke(self, messages, *a, **k):
        res = super().invoke(messages, *a, **k)
        return SimpleNamespace(content=res.content, response_metadata={"model_name": "SIMULATED_STUB"})


def members(*names: Level) -> set[str]:
    return {c for n in names for c in CRITICAL[n]}


@dataclass
class Scenario:
    sid: str
    title: str
    target_level: str
    truth: Callable[[str], float | None]
    expected: tuple[str, str]  # (assessed_level, assessment_status)
    total_budget: int | None = None  # server-side experiment budget; None = product behaviour
    expected_levels: dict[str, str] = field(default_factory=dict)  # level -> coverage status


J_M = members(Level.JUNIOR, Level.MIDDLE)
SENIOR_ONLY = members(Level.SENIOR) - J_M  # P2: borderline 0.72 (inside [tau-eps, tau) of Senior), practice: none
MIDDLE_POOLS = [p for r in POLICY.rules if r.level == Level.MIDDLE for p in r.pools]
HALF_MIDDLE = {c for p in MIDDLE_POOLS[:5] for c in p.members}  # P4: 5 of 13 Middle pools have evidence


def _partial(c: str) -> float | None:
    if c in members(Level.JUNIOR) or c in HALF_MIDDLE:
        return 0.9
    return None  # nothing said about the other capabilities (and no other practice evidence)


# Every scenario runs on the full system-selected python cohort (90 seeded vacancies): no scenario-only cohort.
SCENARIOS = (
    Scenario("P1", "Сильні відповіді з усіх тем, які обрав планувальник", "senior", lambda c: 0.9,
             ("SENIOR", "ASSESSED"), expected_levels={"JUNIOR": "SUPPORTED", "MIDDLE": "SUPPORTED",
                                                      "SENIOR": "SUPPORTED"}),
    Scenario("P2", "Бажаний Senior; підтверджено Middle, Senior не перевірено", "senior",
             lambda c: 0.9 if c in J_M or c not in SENIOR_ONLY else None if c in PRACTICE_CRITERIA else 0.72,
             ("MIDDLE", "ASSESSED"), expected_levels={"JUNIOR": "SUPPORTED", "MIDDLE": "SUPPORTED",
                                                      "SENIOR": "UNVERIFIED"}),
    Scenario("P3", "Слабкі відповіді (контроль)", "middle", lambda c: 0.3, ("UNKNOWN", "GAPS_AT_JUNIOR"),
             expected_levels={"JUNIOR": "GAP"}),
    Scenario("P4", "Junior підтверджено, Middle покрито частково", "middle", _partial, ("JUNIOR", "ASSESSED"),
             expected_levels={"JUNIOR": "SUPPORTED", "MIDDLE": "UNVERIFIED", "SENIOR": "UNVERIFIED"}),
    Scenario("S3", "Сильні окремі відповіді, але замало покриття (бюджет 3 питання)", "senior", lambda c: 0.95,
             ("UNKNOWN", "INSUFFICIENT_DATA"), total_budget=3),
    Scenario("P5", "Сильні відповіді, бюджет 6 питань (WS-4: Senior у v3, у v4 бракує шару даних Senior)", "senior",
             lambda c: 0.9, ("MIDDLE", "ASSESSED"), total_budget=6,
             expected_levels={"JUNIOR": "SUPPORTED", "MIDDLE": "SUPPORTED", "SENIOR": "UNVERIFIED"}),
)


def run(env: Env, sc: Scenario) -> dict:
    core.get_chat_model = lambda: TruthEvaluator(sc.truth)
    c = env.client
    token = c.post(f"{API}/auth/register", json={"email": f"seniority-{uuid.uuid4().hex}@scenarios.local",
                                                 "display_name": "Scenario candidate",
                                                 "password": uuid.uuid4().hex}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    pid = c.get(f"{API}/profiles", headers=h).json()["items"][0]["id"]
    c.put(f"{API}/profiles/{pid}", headers=h, json={
        "name": f"Scenario {sc.sid}", "track": "python", "desired_title": "Python Backend Developer",
        "target_level": sc.target_level, "years_experience": 6, "location": "Київ", "work_mode": "remote"}
    ).raise_for_status()
    cohort = c.post(f"{API}/cohorts/auto", headers=h, params={"profile_id": pid}).json()["cohort_id"]
    iv = c.post(f"{API}/interviews", headers=h, json={"cohort_id": cohort})
    iv.raise_for_status()
    iv_id, version = iv.json()["id"], iv.json()["version"]
    if sc.total_budget is not None:  # server-side only, as in the experiment runner
        env.db.expire_all()
        env.db.get(CoreInterview, iv_id).mode_config = config_for(InterviewMode.ADAPTIVE_INTERVIEW,
                                                                  total_budget=sc.total_budget).to_json()
        env.db.commit()
    for _ in range(60):
        nxt = c.post(f"{API}/interviews/{iv_id}/next-question", headers=h, json={"version": version}).json()
        version = nxt["version"]
        if nxt.get("done"):
            break
        ans = c.post(f"{API}/interviews/{iv_id}/answers", headers=h, json={
            "turn_id": nxt["turn"]["id"], "text": ANSWER, "version": version,
            "idempotency_key": f"scn-{uuid.uuid4().hex}"}).json()
        version = ans["version"]
    level = c.get(f"{API}/interviews/{iv_id}/level", headers=h)
    level.raise_for_status()
    res = c.get(f"{API}/profiles/{pid}/results", headers=h, params={"fitting": "all", "page_size": 5}).json()
    env.db.expire_all()
    evidence = attempt_evidence(env.db, iv_id)
    topics = [t.action_id for t in env.db.scalars(select(CoreTurn).where(CoreTurn.interview_id == iv_id)
                                                  .order_by(CoreTurn.sequence))]
    status = env.db.get(CoreInterview, iv_id).status
    return {"id": sc.sid, "title": sc.title, "target_level": sc.target_level, "status": status,
            "expected": sc.expected, "cohort": "SYSTEM_COHORT",
            "vacancies": len(env.db.get(CohortSnapshot, cohort).vacancy_ids), "budget": sc.total_budget,
            "questions": len(topics), "topics": list(dict.fromkeys(topics)),
            "evidence": {k: {"score": v.score, "turns": len(v.evidence_turns)} for k, v in sorted(evidence.items())},
            "v2_level": estimate(PYTHON_BACKEND_V2, evidence).assessed_level,  # same evidence, older policies
            "v3_level": estimate(PYTHON_BACKEND_V3, evidence).assessed_level,
            "level": level.json(), "top": [(i["title"], i["seniority"], i.get("section")) for i in res["items"]]}


def show(r: dict) -> None:
    lv = r["level"]
    print(f"\n=== {r['id']} {r['title']}  [{LABEL.split(':')[0]}]")
    print(f"cohort {r['cohort']} ({r['vacancies']} seeded vacancies), budget {r['budget'] or 'product'}, expected {r['expected']}")
    print(f"interview {r['status']}, questions {r['questions']}, topics {len(r['topics'])}: {', '.join(r['topics'])}")
    print("criterion evidence (score, evidence turns):")
    for cid, e in r["evidence"].items():
        print(f"  {cid:36} {e['score']!s:5} turns={e['turns']}")
    print(f"desired {lv['desired_level']} -> assessed {lv['assessed_level']} ({lv['assessment_status']}), "
          f"highest supported {lv['highest_supported_level']}, policy {lv['policy']}; same evidence under v2: "
          f"{r['v2_level']}")
    for name, cov in lv["coverage_by_level"].items():
        print(f"  {name:7} {cov['status']:10} pools assessed {cov['assessed_count']}/{cov['critical_total']} "
              f"confirmed {cov['confirmed_count']} gaps {cov['gap_count']} competencies {cov['competencies_confirmed']}"
              f" reasons {cov['reasons']}")
        for p in cov.get("pools", ()):
            print(f"      {p['status']:10} {p['title']}")
    print("explanation:", " | ".join(lv["explanation"]))
    print("unassessed capabilities:", ", ".join(p["title"] for p in lv["unassessed_pools"]) or "-")
    print("critical gaps:", ", ".join(c["id"] for c in lv["critical_gaps"]) or "-")
    got = (lv["assessed_level"], lv["assessment_status"])
    print(f"expected {tuple(r['expected'])}, got {got}: {'CONFIRMED' if got == tuple(r['expected']) else 'NOT_CONFIRMED'}")
    print("top vacancies (title, seniority, section):")
    for t in r["top"]:
        print("  ", t)


def build() -> list[dict]:
    with Env() as env:
        return [run(env, sc) for sc in SCENARIOS]


if __name__ == "__main__":
    print(LABEL)
    for result in build():
        show(result)
