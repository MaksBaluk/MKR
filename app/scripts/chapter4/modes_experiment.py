"""Stage 5/6.4: INITIAL_PROFILE vs STATIC_INTERVIEW vs ADAPTIVE_INTERVIEW (+ ablation without difficulty change).

SIMULATED: Interviewer/Evaluator = scripts.chapter4.realistic_runs.UaModel (Ukrainian-only question text, so the product
never rejects a stub question as NOT_UKRAINIAN), candidate = scripts.chapter4.candidate_model (latent truth per
criterion). Product code runs unchanged through backend.experiments.runner.run_experiment (real HTTP API, planner,
static plan, difficulty/v2, level probe, estimator, ranking 2.15). One fresh in-memory SQLite database per worker.

Run from app/:  uv run python -m scripts.chapter4.modes_experiment [--quick] [--workers N]
Writes raw/modes_runs.jsonl.gz (one record per run, incl. turns) and raw/modes_meta.json; modes_analysis.py builds the
CSV/figure files from them.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import statistics
import time
from collections import Counter
from contextlib import nullcontext
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite://")
os.environ.setdefault("LLM_PROVIDER", "disabled")

from sqlalchemy import select  # noqa: E402

import backend.api.core as core  # noqa: E402
from backend.api.level import attempt_evidence, level_for_attempt  # noqa: E402
from backend.domain.seniority import estimate  # noqa: E402
from backend.domain.seniority_policy import policy_for  # noqa: E402
from backend.experiments.config import InterviewMode, config_for  # noqa: E402
from backend.experiments.metrics import criterion_coverage  # noqa: E402
from backend.experiments.runner import ALGORITHM_VERSION, run_experiment  # noqa: E402
from backend.api.core import _revisions as _cohort_revisions, cohort_actions, rubric_map  # noqa: E402
from backend.domain.core_flow import eval_group  # noqa: E402
from backend.models import CohortSnapshot, CoreInterview, CoreTurn, CriterionAssessment  # noqa: E402
from scripts.chapter4.candidate_model import BY_ID, CRITICAL, PROFILES, TruthProvider, oracle_level  # noqa: E402
from scripts.chapter4.common import OUT  # noqa: E402
from scripts.chapter4.realistic_runs import UaModel  # noqa: E402
from scripts.chapter4.research_planner import VERSION as RESEARCH_VERSION, no_market_planner  # noqa: E402
from scripts.chapter4.scenarios import Env  # noqa: E402
from scripts.seniority_realistic import Model, Noise  # noqa: E402

RAW = OUT / "raw"
SUITE = "modes"
# label -> (mode, overrides). STATIC fixes all three adaptive flags off (config_for enforces it).
MODES = {
    "A_INITIAL_PROFILE": (InterviewMode.INITIAL_PROFILE, {}),
    "B_STATIC": (InterviewMode.STATIC_INTERVIEW, {}),
    # research planner (scripts.chapter4.research_planner): product adaptive flow, next topic without market priority
    "C_ADAPTIVE_NO_MARKET": (InterviewMode.ADAPTIVE_INTERVIEW, {}),
    "D_FULL_COMPETENCEMATCH": (InterviewMode.ADAPTIVE_INTERVIEW, {}),  # the product's adaptive interview
    "D_FIXED_DIFFICULTY": (InterviewMode.ADAPTIVE_INTERVIEW, {"adaptive_difficulty": False}),  # ablation 6.4
}
RESEARCH_NO_MARKET = {"C_ADAPTIVE_NO_MARKET"}
INTERVIEW_MODES = [m for m in MODES if m != "A_INITIAL_PROFILE"]
BUDGETS = (10, 20, 30, 50)  # total question budget; 50 = product caps (10 topics x 5 questions)
SEEDS = (0, 1, 2)
ABLATION_BUDGETS = (20, 50)
PER_Q = 2  # criteria named per Interviewer question (same in every mode)
GOAL = "GAP_ONLY"
GENERIC_REASONS = {"OPEN_CRITERIA", "STATIC_SLOT", "BANK_FALLBACK"}
QUICK = {"profiles": ("C01", "C07", "C13"), "seeds": (0,), "budgets": (10, 50)}


@dataclass(frozen=True)
class Job:
    profile_id: str
    mode: str
    budget: int | None
    seed: int | None
    stub: str = "ua"  # "ua" = UaModel (all experiment runs); "en" = documented stub, only for the EB-3 fallback check
    cand_model: str = "insensitive"  # "sensitive" = DifficultySensitiveCandidate (ablation sensitivity grid only)

    @property
    def run_id(self) -> str:
        b = "na" if self.budget is None else f"b{self.budget:02d}"
        s = "na" if self.seed is None else f"s{self.seed}"
        m = {"A_INITIAL_PROFILE": "A", "B_STATIC": "B", "C_ADAPTIVE_NO_MARKET": "C", "D_FULL_COMPETENCEMATCH": "D",
             "D_FIXED_DIFFICULTY": "Dfd"}[self.mode]
        return f"ch4-m-{self.profile_id.split('-')[0]}-{m}-{b}-{s}" + ("" if self.stub == "ua" else "-enstub") \
            + ("" if self.cand_model == "insensitive" else "-dsens")


def grid(profiles=None, seeds=SEEDS, budgets=BUDGETS, modes=tuple(MODES)) -> list[Job]:
    jobs = []
    for p in (profiles or [p.profile_id for p in PROFILES]):
        if "A_INITIAL_PROFILE" in modes:
            jobs.append(Job(p, "A_INITIAL_PROFILE", None, None))  # no interview: budget and noise do not apply
        for m in modes:
            if m == "A_INITIAL_PROFILE":
                continue
            jobs += [Job(p, m, b, s) for b in budgets for s in seeds]
    return jobs


def _turns(env, interview_id: str) -> list[dict]:
    env.db.expire_all()
    rows = env.db.scalars(select(CoreTurn).where(CoreTurn.interview_id == interview_id).order_by(CoreTurn.sequence))
    return [{"sequence": t.sequence, "turn_id": t.id, "action_id": t.action_id, "question_source": t.question_source,
             "question_text": t.question_text, "target_criteria": t.target_criteria or [], "difficulty": t.difficulty,
             "difficulty_reason": t.difficulty_reason, "followup_reason": t.followup_reason, "eval_goal": t.eval_goal,
             "controller_before": t.controller_before, "controller_after": t.controller_after,
             "answer_text": t.answer_text, "off_topic": t.off_topic} for t in rows]


def _revisions(env, interview_id: str) -> list[dict]:
    """Every stored criterion revision of the attempt in write order (topic and practice criteria)."""
    env.db.expire_all()
    rows = env.db.scalars(select(CriterionAssessment).where(CriterionAssessment.session_id == interview_id)
                          .order_by(CriterionAssessment.created_at, CriterionAssessment.revision))
    return [{"action_id": r.action_id, "criterion_id": r.criterion_id, "revision": r.revision, "score": r.score,
             "sufficient_evidence": bool(r.sufficient_evidence), "no_experience": r.no_experience,
             "evidence_turns": [e.get("turn_id") for e in (r.evidence or []) if isinstance(e, dict)]} for r in rows]


def _requirement_block(env, rec) -> dict:
    """Coverage over D_vga (criteria the cohort's requirements name) and mandatory-group states per vacancy, from the
    frozen cohort snapshot and the attempt's final scores (same eval_group as the ranking)."""
    if not rec.cohort_id:
        return {}
    env.db.expire_all()
    revs = _cohort_revisions(env.db.get(CohortSnapshot, rec.cohort_id))
    scores = {a["criterion_id"]: a["score"] for a in rec.assessments}
    rubrics = rubric_map(env.db, cohort_actions(revs), scores)
    dvga = {c for v in revs for g in v["groups"] for a in g["alternatives"]
            for c in (a.get("criterion_ids") or [x for x, _ in rubrics.get(a["competency_id"], [])])}
    per_vac = {}
    for v in revs:
        st = [eval_group(g["alternatives"], scores, rubrics).status for g in v["groups"] if g["kind"] == "MANDATORY"]
        per_vac[v["id"]] = (sum(x == "FAILED" for x in st), sum(x not in ("SATISFIED", "FAILED") for x in st), len(st))
    top10 = [x["vacancy_id"] for x in rec.ranking[:10]]
    graded = {c for c, x in scores.items() if x is not None}
    return {"n_vacancy_relevant_criteria": len(dvga), "n_vacancy_relevant_graded": len(graded & dvga),
            "relevant_coverage": round(len(graded & dvga) / len(dvga), 4) if dvga else None,
            "unknown_count": len(dvga - graded),
            "unresolved_mandatory_count": sum(u for _, u, _ in per_vac.values()),
            "mandatory_groups_total": sum(n for _, _, n in per_vac.values()),
            "failed_mandatory_count": sum(f for f, _, _ in per_vac.values()),
            "top10_share_unresolved_mandatory": round(sum(per_vac[v][1] > 0 for v in top10) / len(top10), 4)
            if top10 else None,
            "top10_share_failed_mandatory": round(sum(per_vac[v][0] > 0 for v in top10) / len(top10), 4)
            if top10 else None}


def _difficulty_changes(turns: list[dict]) -> tuple[int, int]:
    """(changes inside a topic, changes between consecutive questions overall)."""
    within = overall = 0
    for a, b in zip(turns, turns[1:]):
        if a["difficulty"] != b["difficulty"]:
            overall += 1
            within += a["action_id"] == b["action_id"]
    return within, overall


def _level_block(env, rec, profile) -> dict:
    pol = policy_for(profile.track)
    if rec.interview_id is None:  # mode A: the estimator sees no interview evidence
        res = estimate(pol, {})
        return {"assessed_level": res.assessed_level, "highest_supported_level": res.highest_supported_level,
                "assessment_status": res.assessment_status, "policy": f"{res.policy_id}/{res.policy_version}"
                if res.policy_id else None, "coverage_by_level": {k: v.status for k, v in res.coverage_by_level.items()}}
    env.db.expire_all()
    payload = level_for_attempt(env.db, env.db.get(CoreInterview, rec.interview_id)) or {}
    res = estimate(pol, attempt_evidence(env.db, rec.interview_id)) if pol else None
    return {"assessed_level": payload.get("assessed_level"),
            "highest_supported_level": payload.get("highest_supported_level"),
            "assessment_status": payload.get("assessment_status"),
            "policy": f"{(payload.get('policy') or {}).get('policy_id')}/{(payload.get('policy') or {}).get('version')}"
            if payload.get("policy") else None,
            "coverage_by_level": {k: v.status for k, v in res.coverage_by_level.items()} if res else {},
            "recomputed_matches_stored": (res.assessed_level == payload.get("assessed_level")) if res else None}


def run_job(env, job: Job) -> dict:
    profile = BY_ID[job.profile_id]
    mode, over = MODES[job.mode]
    cfg = config_for(mode, **({**over, "total_budget": job.budget} if job.budget else over))
    model = (UaModel if job.stub == "ua" else Model)(PER_Q, GOAL, {}, Noise(job.seed) if job.seed is not None else None)
    original = core.get_chat_model
    core.get_chat_model = lambda: model
    t0 = time.perf_counter()
    planner = no_market_planner(job.seed or 0) if job.mode in RESEARCH_NO_MARKET else nullcontext()
    try:
        with planner:
            rec = run_experiment("ch4-modes", cfg, profile.spec(), TruthProvider(model, profile.candidate(job.cand_model)),
                                 env.client, env.db)
    finally:
        core.get_chat_model = original
    turns = _turns(env, rec.interview_id) if rec.interview_id else []
    graded = {a["criterion_id"]: a["score"] for a in rec.assessments if a["score"] is not None}
    relevant = set(rec.relevant_criteria)
    critical = sorted(CRITICAL & relevant) if profile.track == "python" else []
    sufficient = rec.qa[-1]["sufficient_criteria_after"] if rec.qa else []
    within, overall = _difficulty_changes(turns)
    shown: Counter = Counter()
    followups = goal_followups = 0
    for t in turns:
        shown[t["action_id"]] += 1
        followups += shown[t["action_id"]] > 1
        goal_followups += (t["followup_reason"] or "") not in GENERIC_REASONS
    top10 = rec.ranking[:10]
    level = _level_block(env, rec, profile)
    return {
        "run_id": job.run_id, "suite": SUITE if job.stub == "ua" and job.cand_model == "insensitive" else
        "stub_check" if job.stub != "ua" else "ablation_sensitive", "stub": job.stub, "candidate_model": job.cand_model, "label": "SIMULATED", "profile_id": profile.profile_id,
        "track": profile.track, "desired_level": profile.desired, "years": profile.years,
        "intended_level": profile.intended, "oracle_level": oracle_level(profile), "pattern": profile.pattern,
        "mode_label": job.mode, "mode": rec.mode, "adaptive_topics": rec.config["adaptive_topics"],
        "adaptive_followup": rec.config["adaptive_followup"], "adaptive_difficulty": rec.config["adaptive_difficulty"],
        "total_budget": job.budget, "seed": job.seed, "per_q": PER_Q if rec.interview_id else None,
        "n_questions": len(turns), "n_topics": len(shown), "topic_sequence": [t["action_id"] for t in turns],
        "difficulty_sequence": [t["difficulty"] for t in turns], "static_plan": None,
        "questions_per_topic": dict(shown), "followups": followups, "goal_followups": goal_followups,
        "difficulty_changes_within_topic": within, "difficulty_changes_overall": overall,
        "fallback_questions": rec.errors["fallback_questions"], "ungraded_answers": rec.errors["ungraded_answers"],
        "ungraded_share": round(rec.errors["ungraded_answers"] / len(turns), 4) if turns else None,
        "llm_calls_simulated": rec.timings["calls"], "llm_exceptions": rec.errors["llm_exceptions"],
        "evaluator_rejections": rec.errors["evaluator_rejections"], "total_s": rec.timings["total_s"],
        "wall_s": round(time.perf_counter() - t0, 3),
        "n_relevant_criteria": len(relevant), "n_graded_criteria": len(set(graded) & relevant),
        "graded_share": round(len(set(graded) & relevant) / len(relevant), 4) if relevant else None,
        "criterion_coverage": None if not relevant else round(criterion_coverage(sufficient, rec.relevant_criteria) or 0.0, 4),
        "n_critical": len(critical), "n_critical_graded": sum(c in graded for c in critical),
        "unresolved_critical_share": round(sum(c not in graded for c in critical) / len(critical), 4) if critical else None,
        **{f"level_{k}": v for k, v in level.items()}, **_requirement_block(env, rec),
        "research_planner": RESEARCH_VERSION if job.mode in RESEARCH_NO_MARKET else None,
        "top5": [x["vacancy_id"] for x in rec.ranking[:5]], "ranking": [x["vacancy_id"] for x in rec.ranking],
        "top10": [{k: x[k] for k in ("vacancy_id", "title", "seniority", "z", "x", "label", "confirmed_share",
                                     "l_mandatory", "l_preferred", "w_mandatory", "w_preferred")} for x in top10],
        "mean_w_mandatory_top10": round(statistics.fmean(x["w_mandatory"] for x in top10), 4) if top10 else None,
        "mean_w_mandatory_all": round(statistics.fmean(x["w_mandatory"] for x in rec.ranking), 4) if rec.ranking else None,
        "assessments": rec.assessments, "turns": turns,
        "revisions": _revisions(env, rec.interview_id) if rec.interview_id else [],
        "equal_conditions": {"cohort_sha256": rec.cohort_sha256, "rubric_versions_sha": hashlib.sha256(json.dumps(
            rec.rubric_versions, sort_keys=True).encode()).hexdigest()[:16], "prompt_version": rec.prompt_version[:16],
            "algorithm_version": ALGORITHM_VERSION, "model_class": rec.model_info.get("client_class"),
            "profile_snapshot_sha": hashlib.sha256(json.dumps({k: v for k, v in rec.profile_snapshot.items()
                                                                if k != "profile_id"}, sort_keys=True).encode()).hexdigest()[:16],
            "config": rec.config},
        "interview_id": rec.interview_id, "cohort_id": rec.cohort_id,
    }


def _worker(jobs: list[Job]) -> list[dict]:
    out = []
    with Env() as env:
        for j in jobs:
            r = run_job(env, j)
            if r["interview_id"] and not r["adaptive_topics"]:
                env.db.expire_all()
                r["static_plan"] = env.db.get(CoreInterview, r["interview_id"]).static_plan
            out.append(r)
    return out


def run_grid(jobs: list[Job], workers: int = 1) -> list[dict]:
    chunks = [jobs[i::workers] for i in range(workers)]
    if workers == 1:
        res = _worker(jobs)
    else:
        with ProcessPoolExecutor(workers) as ex:
            res = [r for part in ex.map(_worker, chunks) for r in part]
    order = {j.run_id: i for i, j in enumerate(jobs)}
    return sorted(res, key=lambda r: order[r["run_id"]])


def content_hash(records: list[dict]) -> str:
    """Run content without ids/timings: equal across two executions iff the simulation is reproducible."""
    keep = [{"r": r["run_id"], "q": [(t["action_id"], t["difficulty"], t["target_criteria"], t["answer_text"])
                                      for t in r["turns"]],
             "a": sorted((a["criterion_id"], a["score"]) for a in r["assessments"]), "lvl": r["level_assessed_level"],
             "rank": r["ranking"]} for r in records]
    return hashlib.sha256(json.dumps(keep, sort_keys=True, default=str).encode()).hexdigest()


def load_runs(path=None) -> list[dict]:
    with gzip.open(path or RAW / "modes_runs.jsonl.gz", "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="3 profiles x 1 seed x 2 budgets (smoke)")
    ap.add_argument("--workers", type=int, default=max(1, min(6, (os.cpu_count() or 2) - 1)))
    args = ap.parse_args(argv)
    jobs = grid(QUICK["profiles"], QUICK["seeds"], QUICK["budgets"]) if args.quick else grid()
    t0 = time.time()
    records = run_grid(jobs, args.workers)
    wall = round(time.time() - t0, 1)
    # reproducibility: a second execution of a fixed subset must give identical content
    probe = [j for j in jobs if j.profile_id in ("C07", "C13") and j.budget in (None, 20)
             and j.seed in (None, 0)]
    again = run_grid(probe, 1)
    first = [r for r in records if r["run_id"] in {j.run_id for j in probe}]
    # EB-3 check: the documented stub (English difficulty word) on the same profiles, budget 50, seed 0, modes B/C
    en_jobs = [Job(p, m, 50, 0, "en") for p in (QUICK["profiles"] if args.quick else [p.profile_id for p in PROFILES])
               for m in ("B_STATIC", "D_FULL_COMPETENCEMATCH")]
    records += run_grid(en_jobs, args.workers)
    # 6.4 sensitivity: difficulty-sensitive candidate, python profiles, interview modes, budgets 20 and 50
    py = [p.profile_id for p in PROFILES if p.track == "python"]
    sens = [Job(p, m, b, s, "ua", "sensitive") for p in (QUICK["profiles"] if args.quick else py)
            for m in INTERVIEW_MODES for b in ABLATION_BUDGETS for s in (QUICK["seeds"] if args.quick else SEEDS)]
    records += run_grid(sens, args.workers)
    RAW.mkdir(parents=True, exist_ok=True)
    with gzip.open(RAW / "modes_runs.jsonl.gz", "wt", encoding="utf-8", compresslevel=9) as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    meta = {"suite": SUITE, "label": "SIMULATED", "quick": args.quick, "workers": args.workers, "wall_s": wall,
            "n_runs": len(records), "modes": {k: {"mode": m.value, **o} for k, (m, o) in MODES.items()},
            "budgets": list(QUICK["budgets"] if args.quick else BUDGETS),
            "seeds": list(QUICK["seeds"] if args.quick else SEEDS), "per_q": PER_Q, "goal_policy": GOAL,
            "profiles": [p.profile_id for p in PROFILES] if not args.quick else list(QUICK["profiles"]),
            "stub": "scripts.chapter4.realistic_runs.UaModel (Ukrainian difficulty word) over "
                    "scripts.seniority_realistic.Model; noise scripts.seniority_realistic.Noise(seed)",
            "reproducibility": {"probe_runs": len(probe), "hash_first": content_hash(first)[:16],
                                "hash_second": content_hash(again)[:16],
                                "identical": content_hash(first) == content_hash(again)}}
    (RAW / "modes_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("n_runs", "wall_s", "reproducibility")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["Job", "grid", "run_grid", "run_job", "MODES", "BUDGETS", "SEEDS", "Model"]
