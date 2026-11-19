"""Chapter-4 harness: one interview through the standard API with the REALISTIC simulated stub, with full turn logging.

SIMULATED: Interviewer, Evaluator and candidate are the deterministic stubs of scripts/seniority_realistic.py (1-2 criteria
per question, grades only addressed criteria, optional deterministic noise). Not a real LLM, not a real candidate.
Unlike seniority_realistic.run, every turn is returned (question, targets, difficulty, controller reason, answer, the
criterion revisions written by that answer), plus the interview id, the stored level payload and a diagnosis of why the
Senior level was or was not supported. Shared by the Phase-1 sweep, the S01-S12 end-to-end scenario and later phases.
"""
from __future__ import annotations

import time
import uuid
from collections import Counter
from collections.abc import Callable

from sqlalchemy import select

import backend.api.core as core
from backend.api.level import attempt_evidence
from backend.domain.seniority import _confirming_turns, estimate
from backend.domain.seniority_policy import MIN_CONFIRMING_TURNS, POLICY_VERSIONS, Level, policy_for
from backend.models import CoreTurn, CriterionAssessment
from scripts.seniority_realistic import MODEL_QUESTIONS, Candidate, Model, Noise

API = "/api/v1"
SIM_LABEL = "SIMULATED"


def _rows(env, iv: str) -> list[CriterionAssessment]:
    env.db.expire_all()
    return list(env.db.scalars(select(CriterionAssessment).where(CriterionAssessment.session_id == iv)
                               .order_by(CriterionAssessment.created_at, CriterionAssessment.revision)))


def run_detailed(env, name: str, truth: Callable[[str], float], desired: str, per_q: int = 1, goal: str = "GAP_ONLY",
                 noise: Noise | None = None, run_id: str | None = None, years: int = 6,
                 model_cls: type[Model] = Model) -> dict:
    """Run one interview to the end through the HTTP API and return everything needed for evidence files.
    `model_cls` selects the stub (default: the documented realistic stub; UaModel: harness variant, see below)."""
    original = core.get_chat_model
    model = model_cls(per_q, goal, MODEL_QUESTIONS, noise)
    core.get_chat_model = lambda: model
    t0 = time.perf_counter()
    try:
        return _run(env, model, Candidate(name, truth), desired, per_q, goal, noise, run_id or uuid.uuid4().hex[:12],
                    years, t0)
    finally:
        core.get_chat_model = original
        MODEL_QUESTIONS.clear()


def _run(env, model: Model, cand: Candidate, desired: str, per_q: int, goal: str, noise, run_id: str, years: int,
         t0: float) -> dict:
    c = env.client
    tok = c.post(f"{API}/auth/register", json={"email": f"ch4-{uuid.uuid4().hex}@sim.local", "display_name": "Simulated",
                                               "password": uuid.uuid4().hex}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    pid = c.get(f"{API}/profiles", headers=h).json()["items"][0]["id"]
    c.put(f"{API}/profiles/{pid}", headers=h, json={"name": cand.name, "track": "python",
                                                    "desired_title": "Python Developer", "target_level": desired,
                                                    "years_experience": years, "location": "Київ",
                                                    "work_mode": "remote"}).raise_for_status()
    cohort = c.post(f"{API}/cohorts/auto", headers=h, params={"profile_id": pid}).json()["cohort_id"]
    r = c.post(f"{API}/interviews", headers=h, json={"cohort_id": cohort})
    r.raise_for_status()
    iv, ver = r.json()["id"], r.json()["version"]
    seen: set[str] = set()
    log: list[dict] = []
    for _ in range(80):
        nx = c.post(f"{API}/interviews/{iv}/next-question", headers=h, json={"version": ver}).json()
        ver = nx["version"]
        if nx.get("done"):
            break
        turn = nx["turn"]
        answer = cand.answer(model.questions.get(turn["question_text"]))
        a = c.post(f"{API}/interviews/{iv}/answers", headers=h, json={
            "turn_id": turn["id"], "text": answer, "version": ver, "idempotency_key": f"k-{uuid.uuid4().hex}"}).json()
        ver = a["version"]
        new = [x for x in _rows(env, iv) if x.id not in seen]
        seen.update(x.id for x in new)
        log.append({"turn_id": turn["id"], "answer": answer, "assessment_status": a.get("assessment_status"),
                    "revisions": [{"criterion_id": x.criterion_id, "score": x.score, "revision": x.revision,
                                   "evidence_turns": [e.get("turn_id") for e in (x.evidence or [])
                                                      if isinstance(e, dict)],
                                   "no_experience": x.no_experience} for x in new]})
    level = c.get(f"{API}/interviews/{iv}/level", headers=h).json()
    env.db.expire_all()
    evidence = attempt_evidence(env.db, iv)
    turns = env.db.scalars(select(CoreTurn).where(CoreTurn.interview_id == iv).order_by(CoreTurn.sequence)).all()
    by_id = {x["turn_id"]: x for x in log}
    turn_rows = [{"sequence": t.sequence, "turn_id": t.id, "action_id": t.action_id, "question_source": t.question_source,
                  "question_text": t.question_text, "target_criteria": t.target_criteria or [],
                  "difficulty": t.difficulty, "difficulty_reason": t.difficulty_reason,
                  "followup_reason": t.followup_reason, "eval_goal": t.eval_goal, "off_topic": t.off_topic,
                  "answer_text": t.answer_text, "assessment_status": by_id.get(t.id, {}).get("assessment_status"),
                  "revisions": by_id.get(t.id, {}).get("revisions", [])} for t in turns]
    return {"run_id": run_id, "label": SIM_LABEL, "profile": cand.name, "desired": desired, "per_q": per_q,
            "goal": goal, "seed": getattr(noise, "seed", None), "interview_id": iv, "cohort_id": cohort,
            "questions": len(turns), "topics": list(dict.fromkeys(t.action_id for t in turns)),
            "max_per_topic": max(Counter(t.action_id for t in turns).values(), default=0),
            "fallback_questions": sum(t.question_source != "LLM_INTERVIEWER" for t in turns),
            "difficulty": dict(Counter(t.difficulty for t in turns)), "level": level,
            "assessed": level.get("assessed_level"), "policy": (level.get("policy") or {}).get("version"),
            "same_evidence": {f"{p}/{v}": estimate(POLICY_VERSIONS[(p, v)], evidence).assessed_level
                              for p, v in POLICY_VERSIONS},
            "evidence": evidence, "turns": turn_rows, "duration_s": round(time.perf_counter() - t0, 3)}


_UA_DIFFICULTY = {"BASIC": "базовий рівень", "INTERMEDIATE": "середній рівень", "ADVANCED": "поглиблений рівень"}


class UaModel(Model):
    """HARNESS VARIANT (not the documented stub): the question names the difficulty in Ukrainian. The documented stub
    writes it in English ("(advanced)"); with one criterion title per question and a Latin tool name (Apache Kafka,
    CI/CD) the share of Cyrillic letters falls below the product's 0.7 rule (graphs.validate_question NOT_UKRAINIAN), the
    question is replaced by an UNGRADED bank question and the topic's criteria are never graded. A real Interviewer
    writes Ukrainian, so this variant isolates a stub artifact. Product code is unchanged."""

    def _ask(self, h: str) -> str:
        import re as _re
        q = super()._ask(h)
        diff = _re.search(r"^difficulty: (\w+)", h, _re.M).group(1)
        meta = self.questions.pop(q)
        q2 = q.replace(f"({diff.lower()})", f"({_UA_DIFFICULTY.get(diff, diff)})")
        self.questions[q2] = meta
        return q2


SENIOR_DATA_POOLS = ("db-operations", "schema-migrations")


def senior_diagnosis(run: dict, policy=None) -> dict:
    """Why the current policy did or did not support SENIOR on this run's stored evidence (deterministic, no LLM)."""
    pol = policy or policy_for("python")
    res = estimate(pol, run["evidence"])
    cov = res.coverage_by_level
    sen = cov["SENIOR"]
    rule = next(r for r in pol.rules if r.level == Level.SENIOR)
    targeted = {c for t in run["turns"] for c in t["target_criteria"]}
    tech_members = {c for p in rule.pools for c in p.members if not c.startswith("practice")}
    visited = set(run["topics"])
    never_targeted = sorted(c for c in tech_members if c.split(".")[0] in visited and c not in targeted)
    single_confirmation = []
    for p in rule.pools:
        if p.pool_id in rule.replicated_pools:
            for m in p.members:
                ev = run["evidence"].get(m)
                if ev and ev.score is not None and ev.score >= rule.tau and \
                        len(_confirming_turns(ev, rule.tau)) < MIN_CONFIRMING_TURNS:
                    single_confirmation.append(m)
    pools = {p.pool_id: p.status for p in sen.pools}
    causes = []
    if cov["JUNIOR"].status != "SUPPORTED":
        causes.append(f"JUNIOR_{cov['JUNIOR'].status}")
    if cov["MIDDLE"].status != "SUPPORTED":
        causes.append(f"MIDDLE_{cov['MIDDLE'].status}")
    causes += [f"SENIOR:{x}" for x in sen.reasons]
    if "REQUIRED_CAPABILITY_UNCONFIRMED" in sen.reasons:
        causes.append("DATA_LAYER:" + ("NO_POSTGRESQL_TOPIC" if "postgresql" not in visited else
                                       "SINGLE_CONFIRMATION" if single_confirmation else
                                       "MEMBER_NEVER_TARGETED" if {"postgresql.operations", "postgresql.migrations"}
                                       & set(never_targeted) else "NOT_CONFIRMED"))
    return {"assessed": res.assessed_level, "senior_status": sen.status, "senior_reasons": list(sen.reasons),
            "senior_technical_confirmed": sen.technical_confirmed, "senior_practice_confirmed": sen.practice_confirmed,
            "senior_data_pools": {k: pools.get(k) for k in SENIOR_DATA_POOLS},
            "senior_pool_status": pools, "senior_members_never_targeted_in_visited_topics": never_targeted,
            "replicated_single_confirmation": single_confirmation, "postgresql_visited": "postgresql" in visited,
            "causes": causes}
