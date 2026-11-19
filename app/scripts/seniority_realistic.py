"""REALISTIC simulated evaluator for level reachability (SIMULATED: stub Interviewer/Evaluator/candidate, NOT a real
LLM, NOT a real candidate). Used by scripts/seniority_reachability.py §6 and by the regression tests of the audit
scenarios. Ported from the independent audit harness (docs/audit/seniority-independent-audit.md §0, §2B).

Unlike scripts/seniority_scenarios.TruthEvaluator (every answer grades the whole topic and all practice), here:
  * the Interviewer asks about the follow-up goal criteria, else the first `per_q` (1 or 2) criteria of unmet_criteria,
    named by title (as the real prompt requires: one narrow question);
  * the candidate answers only those criteria (and practice only when the question invites it: hinted practice_gaps,
    plus rationale/diagnosis at INTERMEDIATE and five practice aspects at ADVANCED);
  * the Evaluator grades only criteria that an answer sentence addresses and quotes it verbatim; sufficient_evidence
    only when every topic criterion is graded; follow-up goal GAP_ONLY (literal prompt: only a graded weak criterion)
    or OPEN (any open criterion, generous);
  * a truth below 0.15 is answered "не знаю цього і не працював" (score 0: a declined tool).
The real API runs unchanged: profile, system cohort (90 seeded vacancies), Q_t, caps (≤10 topics, ≤5 questions per
topic), validation, practice storage, finish hook, GET /level. Throwaway in-memory SQLite.
"""
from __future__ import annotations

import json
import os
import re
import sys
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite://")
os.environ.setdefault("LLM_PROVIDER", "disabled")
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

import backend.api.core as core  # noqa: E402
from backend.agents.prompts import INTERVIEWER_SYSTEM  # noqa: E402
from backend.api.level import attempt_evidence  # noqa: E402
from backend.domain.seniority import estimate  # noqa: E402
from backend.domain.seniority_policy import POLICY_VERSIONS, PRACTICE_CRITERIA, Level, policy_for  # noqa: E402
from backend.models import CoreTurn  # noqa: E402
from backend.seed import read_fixture  # noqa: E402

API = "/api/v1"
LABEL = "SIMULATED (realistic stub: 1-2 criteria per question, grades only addressed criteria); not a real LLM"
TITLES = {c["criterion_id"]: c["title"] for r in read_fixture("rubrics.json")["rubrics"] for c in r["criteria"]}
PHRASES = {0.9: "робив це сам у продакшені й пояснюю механізм на конкретному прикладі",
           0.78: "застосовував на практиці, знаю основні підводні камені",
           0.6: "розумію загальну ідею, але без деталей",
           0.3: "лише чув про це",
           0.0: "не знаю цього і не працював"}
_P2S = {v: k for k, v in PHRASES.items()}
_SENT = re.compile(r"Щодо ([a-z0-9-]+\.[a-z0-9_]+): (" + "|".join(map(re.escape, PHRASES.values())) + r")\.")
NATURAL = {"BASIC": (), "INTERMEDIATE": ("rationale", "diagnosis"),
           "ADVANCED": ("rationale", "tradeoffs", "ambiguity", "ownership", "diagnosis")}


def quant(x: float) -> float:
    return 0.9 if x >= 0.88 else 0.78 if x >= 0.75 else 0.6 if x >= 0.5 else 0.3 if x >= 0.15 else 0.0


def _line(h: str, k: str):
    m = re.search(rf"^{k}: (.*)$", h, re.M)
    return json.loads(m.group(1)) if m else None


def _members(level: Level, policy=None) -> set[str]:
    rule = next(r for r in (policy or policy_for("python")).rules if r.level == level)
    return {c for p in rule.pools for c in p.members if not c.startswith("practice")}


@dataclass
class Model:
    """Interviewer + Evaluator stub. `questions` maps question text -> what it targeted (the candidate reads it)."""
    per_q: int = 1
    goal_policy: str = "GAP_ONLY"  # or OPEN
    questions: dict = field(default_factory=dict)

    def invoke(self, messages, *a, **k):
        system, human = messages[0].content, messages[1].content
        out = self._ask(human) if system == INTERVIEWER_SYSTEM else self._eval(human)
        return SimpleNamespace(content=out, response_metadata={"model_name": "SIMULATED_STUB"})

    def _ask(self, h: str) -> str:
        unmet = _line(h, "unmet_criteria") or []
        g = re.search(r"<followup_goal>(.*?)</followup_goal>", h, re.S)
        goal = json.loads(g.group(1)) if g else None
        targets = ((goal or {}).get("criterion_ids") or unmet)[:self.per_q]
        diff = re.search(r"^difficulty: (\w+)", h, re.M).group(1)
        q = (f"Розкажіть про {_line(h, 'action_name')} ({diff.lower()}): "
             f"{' та '.join('«' + TITLES.get(t, t) + '»' for t in targets)}, питання {len(self.questions) + 1}?")
        self.questions[q] = {"targets": list(targets), "difficulty": diff, "gaps": _line(h, "practice_gaps") or []}
        return q

    def _eval(self, h: str) -> str:
        allowed, open_ids = _line(h, "allowed_criterion_ids"), _line(h, "open_criterion_ids")
        practice = _line(h, "practice_criterion_ids") or []
        latest: dict[str, tuple[str, float, str]] = {}
        for tid, body in re.findall(r'<candidate_answer turn_id="([^"]+)">(".*")</candidate_answer>', h):
            for cid, ph in _SENT.findall(json.loads(body)):
                latest[cid] = (tid, _P2S[ph], f"Щодо {cid}: {ph}.")

        def item(c: str) -> dict:
            if c in latest:
                tid, s, ex = latest[c]
                return {"criterion_id": c, "score": s, "reason": "оцінено", "evidence": [{"turn_id": tid, "exact_excerpt": ex}]}
            return {"criterion_id": c, "score": None, "reason": "немає свідчень", "evidence": []}

        crit = [item(c) for c in allowed]
        pool = open_ids if open_ids is not None else allowed
        if self.goal_policy == "OPEN":
            gaps = [c for c in pool if c not in latest or latest[c][1] < 0.75]
        else:  # literal prompt: a goal only for a graded, weak (not declined) criterion
            gaps = [c for c in pool if c in latest and 0.05 < latest[c][1] < 0.75]
        goal = {"criterion_ids": gaps[:2], "reason": "Є прогалина.", "expected_evidence": "Приклад."} if gaps else None
        out = {"action_id": _line(h, "action_id"), "rubric_version": _line(h, "rubric_version"), "off_topic": False,
               "criteria": crit, "sufficient_evidence": all(c["score"] is not None for c in crit),
               "needs_followup": bool(goal), "followup_goal": goal}
        if practice:
            out["practice"] = [item(c) for c in practice]
        return json.dumps(out, ensure_ascii=False)


@dataclass
class Candidate:
    """Hidden truth per criterion (default for the rest). Shows practice only when the question invites it."""
    name: str
    truth: Callable[[str], float]

    def answer(self, meta: dict | None) -> str:
        if meta is None:  # bank fallback question: generic answer, nothing evidenced
            return "Працював із цим у кількох проєктах."
        parts = [f"Щодо {c}: {PHRASES[quant(self.truth(c))]}." for c in meta["targets"]]
        shown = {g.split(".", 1)[1] for g in meta["gaps"]} | set(NATURAL[meta["difficulty"]])
        parts += [f"Щодо practice-backend.{p}: {PHRASES[quant(self.truth(f'practice-backend.{p}'))]}."
                  for p in sorted(shown)]
        return " ".join(parts)


def profiles() -> dict[str, Callable[[str], float]]:
    """Hidden truths. 'senior' knows everything; the audit's underrating and weak-Senior cases are variants."""
    v3 = POLICY_VERSIONS[("python-backend", "v3")]
    jm = _members(Level.JUNIOR, v3) | _members(Level.MIDDLE, v3)
    s_only = _members(Level.SENIOR, v3) - jm
    mid_practice = {"practice-backend.independence": .85, "practice-backend.rationale": .8,
                    "practice-backend.diagnosis": .8}
    senior_two = {"app-security.authz", "rest-api.security", "aws.iam", "ci-cd.safety"}  # WS-1: 2 Senior capabilities

    def middle(c: str) -> float:
        return 0.82 if c in jm else mid_practice.get(c, 0.55 if c.startswith("practice") or c in s_only else 0.8)

    return {
        "senior": lambda c: 0.9,
        "senior-no-kafka": lambda c: 0.0 if c.startswith("kafka.") else 0.9,  # UR-1
        "senior-no-aws": lambda c: 0.0 if c.startswith("aws.") else 0.9,  # UR-2
        "senior-weak-git": lambda c: 0.4 if c == "git.branching" else 0.9,  # UR-4 / D-10
        "middle": middle,
        "weak-senior": lambda c: 0.85 if c in senior_two or c.startswith("practice") else 0.72 if c in s_only
        else middle(c),  # WS-1: 2 Senior capabilities + strong practice + borderline rest
        "junior": lambda c: 0.7 if c in _members(Level.JUNIOR, v3) or c == "practice-backend.independence" else 0.35,
        "weak": lambda c: 0.3,
    }


def run(env, name: str, truth: Callable[[str], float], desired: str, per_q: int = 1, goal: str = "GAP_ONLY") -> dict:
    original = core.get_chat_model
    core.get_chat_model = lambda: Model(per_q, goal, MODEL_QUESTIONS)
    try:
        return _run(env, name, truth, desired, per_q, goal)
    finally:
        core.get_chat_model = original
        MODEL_QUESTIONS.clear()


MODEL_QUESTIONS: dict = {}


def _run(env, name: str, truth: Callable[[str], float], desired: str, per_q: int, goal: str) -> dict:
    model, cand = core.get_chat_model(), Candidate(name, truth)
    c = env.client
    tok = c.post(f"{API}/auth/register", json={"email": f"real-{uuid.uuid4().hex}@sim.local",
                                               "display_name": "Simulated", "password": uuid.uuid4().hex}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    pid = c.get(f"{API}/profiles", headers=h).json()["items"][0]["id"]
    c.put(f"{API}/profiles/{pid}", headers=h, json={"name": name, "track": "python", "desired_title": "Python Developer",
                                                    "target_level": desired, "years_experience": 6,
                                                    "location": "Київ", "work_mode": "remote"}).raise_for_status()
    cohort = c.post(f"{API}/cohorts/auto", headers=h, params={"profile_id": pid}).json()["cohort_id"]
    r = c.post(f"{API}/interviews", headers=h, json={"cohort_id": cohort})
    r.raise_for_status()
    iv, ver = r.json()["id"], r.json()["version"]
    for _ in range(80):
        nx = c.post(f"{API}/interviews/{iv}/next-question", headers=h, json={"version": ver}).json()
        ver = nx["version"]
        if nx.get("done"):
            break
        a = c.post(f"{API}/interviews/{iv}/answers", headers=h, json={
            "turn_id": nx["turn"]["id"], "text": cand.answer(model.questions.get(nx["turn"]["question_text"])),
            "version": ver, "idempotency_key": f"k-{uuid.uuid4().hex}"}).json()
        ver = a["version"]
    lv = c.get(f"{API}/interviews/{iv}/level", headers=h).json()
    env.db.expire_all()
    evidence = attempt_evidence(env.db, iv)
    turns = env.db.scalars(select(CoreTurn).where(CoreTurn.interview_id == iv).order_by(CoreTurn.sequence)).all()
    return {"profile": name, "desired": desired, "per_q": per_q, "goal": goal, "questions": len(turns),
            "topics": list(dict.fromkeys(t.action_id for t in turns)), "level": lv,
            "assessed": lv["assessed_level"], "status": lv["assessment_status"],
            "highest": lv["highest_supported_level"], "policy": lv["policy"]["version"],
            "same_evidence": {f"{p}/{v}": estimate(POLICY_VERSIONS[(p, v)], evidence).assessed_level
                              for p, v in POLICY_VERSIONS},
            "difficulty": dict(Counter(t.difficulty for t in turns))}


def grid(names=None, desired=("junior", "middle", "senior"), per_qs=(1, 2), goals=("GAP_ONLY", "OPEN")):
    from scripts.chapter4.scenarios import Env
    truths = profiles()
    out = []
    with Env() as env:
        for name in names or truths:
            for d in desired:
                for pq in per_qs:
                    for g in goals:
                        out.append(run(env, name, truths[name], d, pq, g))
    return out


if __name__ == "__main__":
    print(LABEL)
    for r in grid():
        print(f"{r['profile']:16} desired={r['desired']:6} per_q={r['per_q']} {r['goal']:8} q={r['questions']:2} "
              f"-> {r['assessed']:7} ({r['status']}) hi={r['highest']} same evidence: {r['same_evidence']}")
