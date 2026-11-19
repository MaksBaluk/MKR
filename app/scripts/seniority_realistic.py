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

import hashlib
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
    noise: "Noise | None" = None  # noisy grading (audit fix I-5); None = exact anchors

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
        position: dict[str, str] = {}  # turn id -> "<action>#<answer index>": noise must not depend on random UUIDs
        for i, (tid, body) in enumerate(re.findall(r'<candidate_answer turn_id="([^"]+)">(".*")</candidate_answer>', h)):
            position[tid] = f"{_line(h, 'action_id')}#{i}"
            for cid, ph in _SENT.findall(json.loads(body)):
                latest[cid] = (tid, _P2S[ph], f"Щодо {cid}: {ph}.")

        def item(c: str) -> dict:
            if c in latest and self.noise is not None and latest[c][1] > 0.0:
                tid, s0, ex = latest[c]
                s = self.noise.grade(c, position[tid], s0)
                if s is None:  # the grader missed the sentence: no evidence for this criterion
                    return {"criterion_id": c, "score": None, "reason": "немає свідчень", "evidence": []}
                latest[c] = (tid, s, ex)
            if c in latest:
                tid, s, ex = latest[c]
                out = {"criterion_id": c, "score": s, "reason": "оцінено",
                       "evidence": [{"turn_id": tid, "exact_excerpt": ex}]}
                if s == 0.0 and not c.startswith("practice"):  # the "не працював" phrase: a validated declaration
                    out["no_experience"] = True
                return out
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


@dataclass(frozen=True)
class Noise:
    """Deterministic grading noise per (seed, criterion, answer position in its topic): the same answer always gets the
    same grade, and a rerun with the same seed gives the same sweep (before WP-B the key was the random turn UUID, so
    sweeps were not reproducible).
    jitter: uniform +-jitter around the anchor (0.78 +- .1 covers .68-.88, 0.6 covers .50-.70); p_miss: the criterion
    is not graded at all; p_over / p_under: an extra +-.15 (over-/under-grading)."""
    seed: int
    jitter: float = 0.10
    p_miss: float = 0.08
    p_over: float = 0.05
    p_under: float = 0.05

    def grade(self, cid: str, turn: str, anchor: float) -> float | None:
        u = [int(hashlib.sha256(f"{self.seed}:{cid}:{turn}:{k}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
             for k in range(3)]
        if u[0] < self.p_miss:
            return None
        s = anchor + (2 * u[1] - 1) * self.jitter
        s += 0.15 if u[2] < self.p_over else -0.15 if u[2] > 1 - self.p_under else 0.0
        return round(min(1.0, max(0.0, s)), 2)


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


def run(env, name: str, truth: Callable[[str], float], desired: str, per_q: int = 1, goal: str = "GAP_ONLY",
        noise: Noise | None = None) -> dict:
    original = core.get_chat_model
    core.get_chat_model = lambda: Model(per_q, goal, MODEL_QUESTIONS, noise)
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
            "evidence": evidence,
            "max_per_topic": max(Counter(t.action_id for t in turns).values(), default=0),
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


TRUE_LEVEL = {"senior": "SENIOR", "senior-no-kafka": "SENIOR", "senior-no-aws": "SENIOR", "senior-weak-git": "SENIOR",
              "middle": "MIDDLE", "weak-senior": "MIDDLE", "junior": "JUNIOR", "weak": "UNKNOWN"}
_RANK = {"UNKNOWN": -1, "JUNIOR": 0, "MIDDLE": 1, "SENIOR": 2}


def noisy_sweep(seeds=range(7), policies=None) -> dict:
    """>= 200 noisy interviews (8 profiles x 1-2 criteria/question x GAP_ONLY/OPEN x seeds; desired level cycles with
    the seed). Rates per policy over the same stored evidence (the API stores the current policy)."""
    from scripts.chapter4.scenarios import Env
    truths, runs = profiles(), []
    with Env() as env:
        for seed in seeds:
            desired = ("junior", "middle", "senior")[seed % 3]
            for name in truths:
                for pq in (1, 2):
                    for g in ("GAP_ONLY", "OPEN"):
                        r = run(env, name, truths[name], desired, pq, g, Noise(seed))
                        runs.append({k: v for k, v in r.items() if k != "level"})
    policies = policies or {f"{p}/{v}": POLICY_VERSIONS[(p, v)] for p, v in POLICY_VERSIONS}
    return {"runs": len(runs), "rates": {name: rates(runs, pol) for name, pol in policies.items()},
            "usage": usage(runs), "rows": runs}


def usage(runs: list[dict]) -> dict:
    """Budget use of a sweep: averages and maxima of questions / topics / questions per topic, difficulty totals,
    and how many interviews of a true Senior with desired junior reached at least one ADVANCED question."""
    n = len(runs) or 1
    diff = Counter()
    for r in runs:
        diff.update(r["difficulty"])
    sj = [r for r in runs if TRUE_LEVEL[r["profile"]] == "SENIOR" and r["desired"] == "junior"]
    return {"avg_questions": round(sum(r["questions"] for r in runs) / n, 2),
            "avg_topics": round(sum(len(r["topics"]) for r in runs) / n, 2),
            "max_questions": max(r["questions"] for r in runs), "max_topics": max(len(r["topics"]) for r in runs),
            "max_per_topic": max(r["max_per_topic"] for r in runs), "difficulty": dict(diff),
            "senior_desired_junior_advanced": f"{sum(bool(r['difficulty'].get('ADVANCED')) for r in sj)}/{len(sj)}"}


def rates(runs: list[dict], policy) -> dict:
    got = [(TRUE_LEVEL[r["profile"]], estimate(policy, r["evidence"]).assessed_level, r["per_q"]) for r in runs]
    def share(pred, cond):
        sel = [x for x in got if cond(x)]
        return f"{sum(pred(x) for x in sel)}/{len(sel)}"
    return {
        "false_senior": share(lambda x: x[1] == "SENIOR", lambda x: x[0] != "SENIOR"),
        "false_middle_or_higher": share(lambda x: _RANK[x[1]] >= 1, lambda x: _RANK[x[0]] <= 0),
        "missed_senior": share(lambda x: x[1] != "SENIOR", lambda x: x[0] == "SENIOR"),
        "false_middle": share(lambda x: x[1] == "MIDDLE", lambda x: _RANK[x[0]] < 1),
        "missed_senior_per_q1": share(lambda x: x[1] != "SENIOR", lambda x: x[0] == "SENIOR" and x[2] == 1),
        "missed_senior_per_q2": share(lambda x: x[1] != "SENIOR", lambda x: x[0] == "SENIOR" and x[2] == 2),
        "missed_middle": share(lambda x: _RANK[x[1]] < 1, lambda x: x[0] == "MIDDLE"),
        "missed_middle_per_q1": share(lambda x: _RANK[x[1]] < 1, lambda x: x[0] == "MIDDLE" and x[2] == 1),
        "overrated_any": share(lambda x: _RANK[x[1]] > _RANK[x[0]], lambda x: True),
    }


if __name__ == "__main__":
    if "--noisy" in sys.argv:
        print(LABEL + "; NOISY grading (Noise: jitter .10, miss .08, over/under .05)")
        out = noisy_sweep()
        print(f"{out['runs']} interviews")
        for name, r in out["rates"].items():
            print(f"  {name:20} " + "  ".join(f"{k}={v}" for k, v in r.items()))
        print("  usage " + "  ".join(f"{k}={v}" for k, v in out["usage"].items()))
        cur = policy_for("python")
        for (name, pq), n in sorted(Counter((r["profile"], r["per_q"]) for r in out["rows"]).items()):
            sel = [r for r in out["rows"] if (r["profile"], r["per_q"]) == (name, pq)]
            got = Counter(estimate(cur, r["evidence"]).assessed_level for r in sel)
            print(f"  {name:16} per_q={pq} n={n} {dict(sorted(got.items()))} "
                  f"avg_q={sum(r['questions'] for r in sel) / len(sel):.1f}")
        raise SystemExit(0)
    print(LABEL)
    for r in grid():
        print(f"{r['profile']:16} desired={r['desired']:6} per_q={r['per_q']} {r['goal']:8} q={r['questions']:2} "
              f"-> {r['assessed']:7} ({r['status']}) hi={r['highest']} same evidence: {r['same_evidence']}")
