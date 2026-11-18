"""Controlled runs of modes A/B/C and ablations with SIMULATED candidates and a SIMULATED evaluator (no real LLM).

Everything goes through the real HTTP API of the product (TestClient), the real ask/answer graphs, the real planner,
difficulty controller and ranking. Only the two LLM roles and the candidate answers are simulated."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.api.core as core
import backend.models  # noqa: F401
from backend.db import Base, get_db
from backend.domain.topic_summary import criterion_state, topic_summary
from backend.experiments.config import InterviewMode, config_for
from backend.experiments.metrics import criterion_coverage, unresolved_requirements_rate
from backend.experiments.providers import CandidateSpec
from backend.experiments.report import mode_key
from backend.experiments.runner import ALGORITHM_VERSION, rerank, run_experiment
from backend.experiments.store import export_records, save_record
from backend.main import app
from backend.models import CoreTurn
from backend.seed import read_fixture, seed_database
from scripts.chapter4.common import OUT, write_csv, write_json
from scripts.chapter4.simulation import SimulatedCandidate, model_factory

TOTAL_BUDGET = 12
CANDIDATES = [
    CandidateSpec("sim-junior", "Junior Python Developer", 1, "junior", "python", "Київ", "remote",
                  {"python-core": 0.6, "git": 0.5, "pytest": 0.4, "kafka": 0.8}),
    CandidateSpec("sim-middle", "Python Backend Developer", 4, "middle", "python", "Київ", "remote",
                  {"python-core": 0.8, "fastapi": 0.8, "postgresql": 0.8, "redis": 0.7}),
    CandidateSpec("sim-senior", "Senior Python Engineer", 8, "senior", "python", "Київ", "remote",
                  {"python-core": 0.9, "postgresql": 0.9, "kubernetes": 0.9, "kafka": 0.9}),
]
# Hidden truth per simulated candidate: base level per competency (0..1) with a fixed +-0.1 per-criterion jitter.
TRUTH = {
    "sim-junior": {"default": 0.45, "base": {"python-core": 0.7, "git": 0.7, "rest-api": 0.65, "pytest": 0.6, "sql": 0.6,
                                              "kafka": 0.1, "kubernetes": 0.05, "redis": 0.15, "aws": 0.1, "ci-cd": 0.2}},
    "sim-middle": {"default": 0.65, "base": {"fastapi": 0.9, "django": 0.85, "postgresql": 0.9, "sql": 0.9, "python-core": 0.9,
                                              "kafka": 0.2, "kubernetes": 0.3}},
    "sim-senior": {"default": 0.85, "base": {"kafka": 0.2, "kubernetes": 0.25, "redis": 0.5}},
}
CONFIGS = [  # (label, mode, overrides)
    ("A", InterviewMode.INITIAL_PROFILE, {}),
    ("B", InterviewMode.STATIC_INTERVIEW, {"total_budget": TOTAL_BUDGET}),
    ("C", InterviewMode.ADAPTIVE_INTERVIEW, {"total_budget": TOTAL_BUDGET}),
    ("C-difficulty", InterviewMode.ADAPTIVE_INTERVIEW, {"total_budget": TOTAL_BUDGET, "adaptive_difficulty": False}),
    ("C-followup", InterviewMode.ADAPTIVE_INTERVIEW, {"total_budget": TOTAL_BUDGET, "adaptive_followup": False}),
    ("C-topics", InterviewMode.ADAPTIVE_INTERVIEW, {"total_budget": TOTAL_BUDGET, "adaptive_topics": False}),
]


def run_batch(experiment_id: str):
    """Returns (records, turn_rows). Fresh in-memory SQLite database per batch; never the product database."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as s:
        seed_database(s, demo_mode=False)

    def override():
        with Session() as session:
            yield session

    original, saved = core.get_chat_model, dict(app.dependency_overrides)
    core.get_chat_model = model_factory
    app.dependency_overrides[get_db] = override
    provider = SimulatedCandidate(TRUTH)
    records, turns = [], []
    try:
        with TestClient(app) as client, Session() as db:
            for cand in CANDIDATES:
                for label, mode, over in CONFIGS:
                    rec = run_experiment(experiment_id, config_for(mode, **over), cand, provider, client, db)
                    save_record(db, rec)
                    records.append((label, rec))
                    if rec.interview_id:
                        for t in db.scalars(select(CoreTurn).where(CoreTurn.interview_id == rec.interview_id)
                                            .order_by(CoreTurn.sequence)).all():
                            turns.append({"config": label, "candidate_id": cand.candidate_id, "run_no": 1,
                                          "answer_source": rec.answer_source, "interview_id": rec.interview_id,
                                          "sequence": t.sequence, "action_id": t.action_id,
                                          "question_source": t.question_source, "question_text": t.question_text,
                                          "answer_text": t.answer_text, "difficulty": t.difficulty,
                                          "difficulty_reason": t.difficulty_reason, "followup_reason": t.followup_reason,
                                          "target_criteria": t.target_criteria, "eval_goal": t.eval_goal,
                                          "controller_before": t.controller_before, "controller_after": t.controller_after,
                                          "off_topic": t.off_topic})
        # rerank without any model call must reproduce the stored order (reproducibility of the ranking stage)
        with Session() as db:
            from backend.experiments.store import load_record
            for label, rec in records:
                again = rerank(rec, db)
                assert [x["vacancy_id"] for x in again] == [x["vacancy_id"] for x in rec.ranking], (label, rec.candidate_id)
    finally:
        core.get_chat_model = original
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)
        engine.dispose()
    return records, turns


def normalized(records, turns) -> str:
    """Run content without ids and timings: equal across batches iff the runs are reproducible."""
    def run(label, r):
        return {"c": label, "cand": r.candidate_id, "qa": [(q["action_id"], q["difficulty"], q["target_criteria"], q["answer_text"]) for q in r.qa],
                "ass": sorted((a["criterion_id"], a["score"]) for a in r.assessments),
                "rank": [(x["vacancy_id"], x["confirmed_share"], x["z"]) for x in r.ranking]}
    return hashlib.sha256(json.dumps([run(l, r) for l, r in records], sort_keys=True, default=str).encode()).hexdigest()


def write_outputs(records, turns, repro: dict) -> dict:
    rubrics = {r["action_id"]: [(c["criterion_id"], float(c.get("weight", 1))) for c in r["criteria"]]
               for r in read_fixture("rubrics.json")["rubrics"]}
    cands = {c.candidate_id: c for c in CANDIDATES}
    run_rows, crit_rows, rank_rows = [], [], []
    for label, r in records:
        c = cands[r.candidate_id]
        cov = criterion_coverage(r.qa[-1]["sufficient_criteria_after"] if r.qa else [], r.relevant_criteria)
        unresolved = unresolved_requirements_rate(r.ranking)
        topics = list(dict.fromkeys(q["action_id"] for q in r.qa))
        key = f"{r.candidate_id}|{label}"
        run_rows.append({
            "config": label, "mode_key": mode_key(r), "mode": r.mode, "adaptive_topics": r.config["adaptive_topics"],
            "adaptive_followup": r.config["adaptive_followup"], "adaptive_difficulty": r.config["adaptive_difficulty"],
            "candidate_id": r.candidate_id, "candidate_level": c.target_level, "years_experience": c.years_experience,
            "run_no": 1, "answer_source": r.answer_source, "evaluator": "SIMULATED_STUB" if r.qa else "none",
            "total_budget": r.config["total_budget"], "n_questions": len(r.qa), "n_topics": len(topics),
            "topic_sequence": " > ".join(q["action_id"] for q in r.qa), "difficulty_sequence": " > ".join(q["difficulty"] for q in r.qa),
            "questions_per_topic": json.dumps({t: sum(1 for q in r.qa if q["action_id"] == t) for t in topics}, ensure_ascii=False),
            "n_assessed_criteria": sum(1 for a in r.assessments if a["score"] is not None),
            "n_relevant_criteria": len(r.relevant_criteria), "criterion_coverage": "" if cov is None else round(cov, 4),
            "unresolved_requirements_rate": "" if unresolved is None else round(unresolved, 4),
            "top5_vacancies": " ".join(x["vacancy_id"] for x in r.ranking[:5]),
            "llm_calls": r.timings.get("calls"), "llm_wait_s": r.timings.get("llm_wait_s"), "total_s": r.timings.get("total_s"),
            "ungraded_answers": r.errors["ungraded_answers"], "fallback_questions": r.errors["fallback_questions"],
            "llm_exceptions": r.errors["llm_exceptions"], "evaluator_rejections": r.errors["evaluator_rejections"],
            "cohort_sha256": r.cohort_sha256[:16], "interview_id": r.interview_id or ""})
        by_action = {}
        for a in r.assessments:
            by_action.setdefault(a["action_id"], {})[a["criterion_id"]] = a
        for action in topics:
            scores = {cid: (by_action.get(action, {}).get(cid) or {}).get("score") for cid, _ in rubrics.get(action, [])}
            ts = topic_summary(rubrics[action], scores)
            for cid, _ in rubrics[action]:
                a = by_action.get(action, {}).get(cid)
                suff = bool(a and a.get("sufficient_evidence"))
                crit_rows.append({"config": label, "candidate_id": r.candidate_id, "run_no": 1, "answer_source": r.answer_source,
                                  "action_id": action, "criterion_id": cid, "score": "" if not a or a["score"] is None else a["score"],
                                  "state": criterion_state(None if not a else a["score"], suff),
                                  "sufficient_evidence": suff, "action_coverage_E": round(ts.e, 4),
                                  "action_score_M": "" if ts.m is None else round(ts.m, 4),
                                  "overall_level_allowed": ts.overall_level_allowed})
        screen = sorted(range(len(r.ranking)), key=lambda i: (-r.ranking[i]["confirmed_share"], i))  # percent-first, stable
        screen_pos = {i: p + 1 for p, i in enumerate(screen)}
        for i, x in enumerate(r.ranking):
            rank_rows.append({"config": label, "candidate_id": r.candidate_id, "run_no": 1, "answer_source": r.answer_source,
                              "rank_215": i + 1, "rank_results_screen": screen_pos[i], "vacancy_id": x["vacancy_id"],
                              "title": x["title"], "seniority": x["seniority"], "z": x["z"], "x": x["x"], "label": x["label"],
                              "confirmed_share_pct": x["confirmed_share"], "l_mandatory": round(x["l_mandatory"], 4),
                              "l_preferred": round(x["l_preferred"], 4), "w_mandatory": round(x["w_mandatory"], 4),
                              "w_preferred": round(x["w_preferred"], 4), "met": x.get("met_count", ""), "gaps": x.get("gap_count", ""),
                              "unknown": x.get("unknown_count", "")})
    h = list(run_rows[0])
    write_csv(OUT / "experiment_runs.csv", h, run_rows)
    write_csv(OUT / "criterion_results.csv", list(crit_rows[0]), crit_rows)
    write_csv(OUT / "ranking_results.csv", list(rank_rows[0]), rank_rows)
    with open(OUT / "interview_turns.jsonl", "w", encoding="utf-8") as f:
        for t in turns:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    # equal conditions for B and C (and A): per candidate the cohort, rubric versions, budget and model are identical
    equal = {}
    for cid in cands:
        rs = [r for _, r in records if r.candidate_id == cid]
        interview = [r for r in rs if r.mode != "INITIAL_PROFILE"]
        equal[cid] = {"same_cohort_sha256_all_modes": len({r.cohort_sha256 for r in rs}) == 1,
                      "same_rubric_versions_interview_modes": len({json.dumps(r.rubric_versions, sort_keys=True) for r in interview}) == 1,
                      "same_total_budget_interview_modes": len({r.config["total_budget"] for r in interview}) == 1,
                      "same_model_info_interview_modes": len({json.dumps(r.model_info, sort_keys=True) for r in interview}) == 1,
                      "same_algorithm_version": len({r.algorithm_version for r in rs}) == 1,
                      "same_profile_all_modes_except_generated_id": len({json.dumps({k: v for k, v in r.profile_snapshot.items() if k != "profile_id"}, sort_keys=True) for r in rs}) == 1}
    manifest = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "kind": "SIMULATED_CONTROLLED_RUNS",
        "answer_source": "SIMULATED", "evaluator": "SIMULATED_STUB (deterministic, not an LLM)", "real_llm_calls": 0,
        "claim_scope": "pipeline behaviour of planner, difficulty controller, follow-up targeting and ranking only; "
                       "no statement about real candidates, real evaluator quality or real vacancies",
        "algorithm_version": ALGORITHM_VERSION, "total_budget": TOTAL_BUDGET, "max_topics": 10, "max_per_topic": 5,
        "static_questions_per_topic": 2, "database": "SQLite in-memory per batch (product database never used)",
        "configs": [{"label": l, "mode": m.value, **o} for l, m, o in CONFIGS],
        "candidates": [asdict(c) | {"hidden_truth": TRUTH[c.candidate_id]} for c in CANDIDATES],
        "run_count": len(records), "runs_per_candidate_config": 1,
        "reproducibility": repro, "equal_conditions_check": equal,
        "rubric_versions": sorted({v for _, r in records for v in r.rubric_versions.values()}),
        "prompt_version": records[0][1].prompt_version, "cohort_sha256": sorted({r.cohort_sha256 for _, r in records if r.cohort_sha256}),
        "command": "cd app && uv run python -m scripts.chapter4.build_all"}
    write_json(OUT / "experiment_manifest.json", manifest)
    return manifest


def build() -> dict:
    t0 = time.time()
    rec1, turns1 = run_batch("ch4-sim-1")
    rec2, turns2 = run_batch("ch4-sim-2")
    h1, h2 = normalized(rec1, turns1), normalized(rec2, turns2)
    repro = {"batches": 2, "normalized_sha256_batch1": h1[:16], "normalized_sha256_batch2": h2[:16], "identical": h1 == h2,
             "rerank_without_llm_matches_stored_order": True, "wall_s": round(time.time() - t0, 1)}
    export_records([r for _, r in rec1], OUT / "raw")  # runs.json / runs.csv in the product export format
    return write_outputs(rec1, turns1, repro)


if __name__ == "__main__":
    m = build()
    print(json.dumps({k: m[k] for k in ("run_count", "reproducibility", "equal_conditions_check")}, indent=1, ensure_ascii=False))
