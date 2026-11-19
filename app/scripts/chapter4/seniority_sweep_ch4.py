"""Chapter-4 Phase 1, Stage 2: end-to-end level reachability through the standard API (SIMULATED realistic stub).

Two grids, both through the real API on throwaway in-memory SQLite (90+ seeded vacancies, Q_t, caps, validation, finish
hook, GET /level):
  * deterministic grid: 8 profiles x 3 desired levels x 1-2 criteria/question x GAP_ONLY/OPEN goals = 96 interviews;
  * noisy sweep: seeds 0-6 (desired level cycles with the seed) x 8 profiles x 1-2 x GAP_ONLY/OPEN = 224 interviews,
    noise as in scripts/seniority_realistic.Noise (jitter .10, miss .08, over/under .05), keyed on answer position.
Outputs (artifacts/chapter4/): raw/seniority_sweep_runs.csv (one row per interview), raw/seniority_sweep_summary.json
(rates per policy over the same stored evidence, budget use, Senior-miss causes). Not a real LLM, not real candidates.

Run from app/:  uv run python -m scripts.chapter4.seniority_sweep_ch4 [--quick] [--stub-ua]
--stub-ua: harness variant (realistic_runs.UaModel, noisy grid only) -> raw/seniority_sweep_ua_stub_*.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter

from scripts.chapter4.common import OUT, sh, write_csv, write_json
from scripts.chapter4.realistic_runs import UaModel, run_detailed, senior_diagnosis
from scripts.seniority_realistic import Model
from scripts.chapter4.scenarios import Env
from scripts.seniority_realistic import TRUE_LEVEL, Noise, profiles, rates, usage
from backend.domain.seniority_policy import POLICY_VERSIONS, policy_for

HEADER = ["run_id", "grid", "label", "seed", "profile", "true_level", "desired", "per_q", "goal", "questions", "topics",
          "n_topics", "max_per_topic", "fallback_questions", "advanced_questions", "assessed_level_api", "policy_api",
          "v1", "v2", "v3", "v4", "senior_status", "senior_reasons", "senior_technical_confirmed",
          "senior_practice_confirmed", "db_operations", "schema_migrations", "postgresql_visited",
          "replicated_single_confirmation", "senior_members_never_targeted", "causes", "interview_id", "duration_s"]


def _row(grid: str, r: dict) -> dict:
    d = senior_diagnosis(r)
    return {"run_id": r["run_id"], "grid": grid, "label": "SIMULATED", "seed": r["seed"], "profile": r["profile"],
            "true_level": TRUE_LEVEL[r["profile"]], "desired": r["desired"], "per_q": r["per_q"], "goal": r["goal"],
            "questions": r["questions"], "topics": " ".join(r["topics"]), "n_topics": len(r["topics"]),
            "max_per_topic": r["max_per_topic"], "fallback_questions": r["fallback_questions"],
            "advanced_questions": r["difficulty"].get("ADVANCED", 0), "assessed_level_api": r["assessed"],
            "policy_api": r["policy"], **{k.split("/")[1]: v for k, v in r["same_evidence"].items()},
            "senior_status": d["senior_status"], "senior_reasons": " ".join(d["senior_reasons"]),
            "senior_technical_confirmed": d["senior_technical_confirmed"],
            "senior_practice_confirmed": d["senior_practice_confirmed"],
            "db_operations": d["senior_data_pools"]["db-operations"],
            "schema_migrations": d["senior_data_pools"]["schema-migrations"],
            "postgresql_visited": d["postgresql_visited"],
            "replicated_single_confirmation": " ".join(d["replicated_single_confirmation"]),
            "senior_members_never_targeted": " ".join(d["senior_members_never_targeted_in_visited_topics"]),
            "causes": " ".join(d["causes"]), "interview_id": r["interview_id"], "duration_s": r["duration_s"]}


def _grid_params(quick: bool):
    names = list(profiles())
    det = [(n, d, pq, g, None) for n in names for d in ("junior", "middle", "senior") for pq in (1, 2)
           for g in ("GAP_ONLY", "OPEN")]
    noisy = [(n, ("junior", "middle", "senior")[s % 3], pq, g, Noise(s)) for s in range(7) for n in names
             for pq in (1, 2) for g in ("GAP_ONLY", "OPEN")]
    if quick:
        det, noisy = det[:4], noisy[:4]
    return det, noisy


def miss_causes(rows: list[dict]) -> dict:
    """Missed SENIOR (true Senior profile, v4 level below SENIOR) by cause, per criteria/question."""
    missed = [r for r in rows if r["true_level"] == "SENIOR" and r["v4"] != "SENIOR"]
    out = {"n_missed": len(missed), "by_assessed": dict(Counter(r["v4"] for r in missed)),
           "by_profile_per_q": dict(Counter(f"{r['profile']}|per_q={r['per_q']}" for r in missed)),
           "by_cause": dict(Counter(c for r in missed for c in r["causes"].split())),
           "postgresql_not_visited": sum(r["postgresql_visited"] is False for r in missed),
           "with_fallback_questions": sum(r["fallback_questions"] > 0 for r in missed),
           "avg_fallback_questions_missed": round(sum(r["fallback_questions"] for r in missed) / max(len(missed), 1), 2),
           "avg_fallback_questions_reached": round(
               sum(r["fallback_questions"] for r in rows if r["true_level"] == "SENIOR" and r["v4"] == "SENIOR")
               / max(sum(r["true_level"] == "SENIOR" and r["v4"] == "SENIOR" for r in rows), 1), 2),
           "never_targeted_senior_members": dict(Counter(
               c for r in missed for c in r["senior_members_never_targeted"].split()).most_common(12))}
    return out


def main(argv: list[str]) -> int:
    quick = "--quick" in argv
    variant = "--stub-ua" in argv  # harness variant (UaModel): noisy grid only, separate output files
    det, noisy = _grid_params(quick)
    if variant:
        det = []
    model_cls = UaModel if variant else Model
    t0 = time.time()
    rows: list[dict] = []
    raw: dict[str, list[dict]] = {"deterministic": [], "noisy": []}
    truths = profiles()
    with Env() as env:
        for grid, params in (("deterministic", det), ("noisy", noisy)):
            for i, (name, desired, pq, goal, noise) in enumerate(params):
                run_id = f"ch4-sweep-{grid[:3]}-{i:03d}"
                r = run_detailed(env, name, truths[name], desired, pq, goal, noise,
                                 run_id + ("-ua" if variant else ""), model_cls=model_cls)
                rows.append(_row(grid, r))
                raw[grid].append({k: v for k, v in r.items() if k not in ("level", "turns")})
    summary = {"label": "SIMULATED (realistic stub, not a real LLM)", "commit": sh("git", "rev-parse", "HEAD"),
               "current_policy": f"{policy_for('python').policy_id}/{policy_for('python').version}",
               "duration_s": round(time.time() - t0, 1)}
    summary["stub"] = "UaModel (harness variant: Ukrainian difficulty word)" if variant else "seniority_realistic.Model"
    for grid in (("noisy",) if variant else ("deterministic", "noisy")):
        sel = [r for r in rows if r["grid"] == grid]
        summary[grid] = {
            "runs": len(sel),
            "rates": {f"{p}/{v}": rates(raw[grid], pol) for (p, v), pol in POLICY_VERSIONS.items()},
            "usage": usage(raw[grid]),
            "distribution_v4": {f"{n}|per_q={pq}": dict(Counter(r["v4"] for r in sel
                                                                 if r["profile"] == n and r["per_q"] == pq))
                                for n in truths for pq in (1, 2)},
            "missed_senior": miss_causes(sel),
            "api_equals_recomputed_v4": all(r["assessed_level_api"] == r["v4"] for r in sel),
        }
    if not quick:  # --quick is a smoke run: it never overwrites the evidence files
        stem = "seniority_sweep_ua_stub" if variant else "seniority_sweep"
        write_csv(OUT / "raw" / f"{stem}_runs.csv", HEADER, rows)
        write_json(OUT / "raw" / f"{stem}_summary.json", summary)
    print(json.dumps({g: {"runs": summary[g]["runs"], "v4": summary[g]["rates"]["python-backend/v4"]}
                      for g in summary if isinstance(summary[g], dict)}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
