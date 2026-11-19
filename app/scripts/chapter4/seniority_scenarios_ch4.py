"""Chapter-4 Phase 1, Stage 3: control scenarios S01-S12 for the SeniorityEstimator (policy python-backend/v4).

Two kinds of rows, never mixed:
  * ESTIMATOR_LEVEL: deterministic evidence built by hand and passed to backend.domain.seniority.estimate (S11 goes
    through core.seniority_evidence on stored-row stand-ins). Proves the rule, not real candidates.
  * SIMULATED_E2E: a whole interview through the standard API with the realistic simulated stub
    (scripts/chapter4/realistic_runs.py): Q_t, caps, difficulty, validation, finish hook, GET /level. Not a real LLM.
Expectations come from the owner specification (S01-S12). They are never adjusted to the result: when policy v4 does
not support the literal expectation the row is FAIL with the reason in `note`.

Run from app/:  uv run python -m scripts.chapter4.seniority_scenarios_ch4
Writes artifacts/chapter4/seniority_results.csv and artifacts/chapter4/interview_turns.jsonl (SIMULATED_E2E turns).
"""
from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

from backend.api.core import seniority_evidence
from backend.domain.seniority import CriterionEvidence, estimate
from backend.domain.seniority_policy import PRACTICE_CRITERIA, PYTHON_BACKEND_V4, Level

POLICY = PYTHON_BACKEND_V4
TEST_PATH = "app/tests/test_chapter4_seniority_scenarios.py"
PR = {c.split(".", 1)[1]: c for c in PRACTICE_CRITERIA}
RULE = {r.level: r for r in POLICY.rules}


def members(level: Level, practice: bool | None = None) -> list[str]:
    """Pool members of a level; practice=None both, True practice only, False technical only."""
    out = [c for p in RULE[level].pools for c in p.members]
    if practice is not None:
        out = [c for c in out if c.startswith("practice-backend.") == practice]
    return list(dict.fromkeys(out))


def ev(scores: dict[str, float | None], declined: tuple[str, ...] = ()) -> dict[str, CriterionEvidence]:
    """Traced evidence: every topic criterion quoted by two distinct answers (replicated Senior pools need two), every
    practice criterion graded in two source topics with the same score. None stays unknown (never 0)."""
    out = {}
    for c, s in scores.items():
        if s is None:
            out[c] = CriterionEvidence(c, None)
        elif c in PRACTICE_CRITERIA:
            out[c] = CriterionEvidence(c, s, (f"t-{c}",), topic_scores=(s, s))
        else:
            out[c] = CriterionEvidence(c, s, (f"t1-{c}", f"t2-{c}"), declined=c in declined)
    return out


J_TECH, M_TECH = members(Level.JUNIOR, False), members(Level.MIDDLE, False)
S_TECH = [c for c in members(Level.SENIOR, False) if c not in J_TECH + M_TECH]
ALL_TECH = list(dict.fromkeys(J_TECH + M_TECH + S_TECH))


def coverage_text(res) -> str:
    parts = []
    for lvl in ("JUNIOR", "MIDDLE", "SENIOR"):
        c = res.coverage_by_level[lvl]
        parts.append(f"{lvl[0]}:{c.status} k={c.confirmed}/{c.critical_total} tech={c.technical_confirmed} "
                     f"prac={c.practice_confirmed} gaps={c.gaps}" + (f" [{' '.join(c.reasons)}]" if c.reasons else ""))
    return "; ".join(parts)


def _row(sid: str, title: str, input_text: str, expected: str, evidence: dict, verdict_fn, note: str = "") -> dict:
    res = estimate(POLICY, evidence)
    ok = bool(verdict_fn(res))
    known = {c: e.score for c, e in evidence.items() if e.score is not None}
    return {"scenario_id": sid, "title": title, "label": "ESTIMATOR_LEVEL", "run_id": f"ch4-{sid.lower()}-est",
            "input": input_text, "expected": expected,
            "actual": f"{res.assessed_level} ({res.assessment_status}); Senior {res.coverage_by_level['SENIOR'].status}",
            "criteria": len(evidence), "scores": json.dumps({"known": len(known), "min": min(known.values(), default=None),
                                                              "max": max(known.values(), default=None)}),
            "coverage": coverage_text(res),
            "evidence_refs": sum(len(v) for v in res.evidence_references.values()),
            "result": " | ".join(res.explanation[:2]), "verdict": "PASS" if ok else "FAIL",
            "test_path": TEST_PATH, "policy": f"{POLICY.policy_id}/{POLICY.version}", "note": note,
            "_result": res}


def estimator_scenarios() -> list[dict]:
    full = {c: 0.9 for c in ALL_TECH} | {p: 0.9 for p in PRACTICE_CRITERIA}
    middle = ({c: 0.8 for c in J_TECH + M_TECH} | {PR["independence"]: 0.8, PR["rationale"]: 0.8, PR["diagnosis"]: 0.8})
    rows = [
        _row("S01", "desired Senior, only basics confirmed",
             "every Junior technical criterion 0.9 + practice-independence 0.9; nothing else assessed; desired=senior "
             "(the estimator has no desired-level input)", "not SENIOR (JUNIOR)",
             ev({c: 0.9 for c in J_TECH} | {PR["independence"]: 0.9}),
             lambda r: r.assessed_level == "JUNIOR"),
        _row("S02", "full Junior", "every Junior technical criterion 0.6 (>= tau_J .50, < tau_M .70) + independence 0.6",
             "JUNIOR", ev({c: 0.6 for c in J_TECH} | {PR["independence"]: 0.6}),
             lambda r: r.assessed_level == "JUNIOR"),
        _row("S03", "full Middle", "Junior + Middle technical 0.8, practice independence/rationale/diagnosis 0.8; "
             "Senior-only criteria unassessed", "MIDDLE", ev(middle), lambda r: r.assessed_level == "MIDDLE"),
        _row("S04", "full Senior", "all technical criteria of all levels 0.9 + all 6 practice 0.9, two answers each",
             "SENIOR", ev(full), lambda r: r.assessed_level == "SENIOR"),
        _row("S05", "high scores on 1-2 criteria, low coverage",
             "postgresql.operations 1.0, postgresql.migrations 1.0, all practice 0.95; nothing else",
             "no SENIOR (UNKNOWN: Junior not supported)",
             ev({"postgresql.operations": 1.0, "postgresql.migrations": 1.0} | {p: 0.95 for p in PRACTICE_CRITERIA}),
             lambda r: r.assessed_level == "UNKNOWN" and r.highest_supported_level != "SENIOR"),
        _row("S06", "insufficient data even for basics", "python-core.idioms 0.9, sql.joins 0.9; nothing else",
             "UNKNOWN / INSUFFICIENT_DATA", ev({"python-core.idioms": 0.9, "sql.joins": 0.9}),
             lambda r: (r.assessed_level, r.assessment_status) == ("UNKNOWN", "INSUFFICIENT_DATA")),
        _row("S07", "desired Junior, full Senior evidence",
             "evidence of S04; desired=junior is not an estimator parameter (signature checked)", "SENIOR", ev(full),
             lambda r: r.assessed_level == "SENIOR" and "desired" not in str(inspect.signature(estimate))),
        _row("S08", "large experience, weak evidence",
             "every technical criterion and practice 0.3 (weak band); years=15 is not an estimator parameter",
             "no automatic raise: not above the evidence (UNKNOWN, gaps at Junior)",
             ev({c: 0.3 for c in ALL_TECH} | {p: 0.3 for p in PRACTICE_CRITERIA}),
             lambda r: r.assessed_level == "UNKNOWN" and r.assessment_status == "GAPS_AT_JUNIOR"
             and "years" not in str(inspect.signature(estimate))),
        _row("S09", "strong technical answers without independence evidence",
             "all technical 0.9; practice tradeoffs/ambiguity/ownership/diagnosis/rationale 0.9; "
             "practice-independence never assessed", "Senior not confirmed automatically",
             ev({c: 0.9 for c in ALL_TECH} | {p: 0.9 for p in PRACTICE_CRITERIA if p != PR["independence"]}),
             lambda r: r.assessed_level != "SENIOR",
             note="CONTRADICTION with policy v4: practice-independence is not a Senior pool and not required at "
                  "Junior (P_min=0) or Middle (2 of independence/rationale/diagnosis); Senior is assigned with "
                  "independence unassessed. Not a threshold issue; needs an owner decision (S09a: no practice -> JUNIOR)."),
        _row("S09a", "strong technical answers without any professional-practice evidence",
             "all technical 0.9; no practice criterion assessed", "not SENIOR (Middle needs 2 practice pools)",
             ev({c: 0.9 for c in ALL_TECH}), lambda r: r.assessed_level == "JUNIOR"),
        _row("S10", "Middle confirmed, Senior criteria not checked",
             "S03 evidence; every Senior-only criterion unassessed", "MIDDLE; Senior UNVERIFIED (not GAP), "
             "explanation says data are insufficient for Senior, no Senior gap listed", ev(middle),
             lambda r: r.assessed_level == "MIDDLE" and r.coverage_by_level["SENIOR"].status == "UNVERIFIED"
             and not r.coverage_by_level["SENIOR"].gap_ids and any("недостатньо даних" in x for x in r.explanation)),
    ]
    # S11 goes through core.seniority_evidence on stored-row stand-ins: strong answers, then an off-topic (null) revision
    # of every criterion. Expected: the earlier scores and their evidence turns stay effective.
    rows.append(s11())
    rows.append(_row("S12", "evidenced critical Senior gap",
                     "S03 evidence + Senior-only technical 0.9 + Senior practice 0.9, but postgresql.operations 0.3 "
                     "(hard Senior pool db-operations) and postgresql.migrations 0.3 / django.migrations unasked",
                     "MIDDLE; Senior GAP (CRITICAL_GAP, hard gap listed) - distinct from S10 UNVERIFIED",
                     ev(middle | {c: 0.9 for c in S_TECH} | {p: 0.9 for p in PRACTICE_CRITERIA}
                        | {"postgresql.operations": 0.3, "postgresql.migrations": 0.3, "django.migrations": None}),
                     lambda r: r.assessed_level == "MIDDLE" and r.coverage_by_level["SENIOR"].status == "GAP"
                     and "postgresql.operations" in (r.coverage_by_level["SENIOR"].hard_gap_ids or ())
                     and any("критичні прогалини" in x for x in r.explanation),
                     note="v4 has no state named FAILED: level status GAP = established failure, UNVERIFIED = not "
                          "enough decided evidence (UNKNOWN). Both keep assessed_level MIDDLE; payload and UI differ "
                          "by coverage_by_level.SENIOR.status, reasons, critical_gaps and the explanation line."))
    return rows


def s11() -> dict:
    full = {c: 0.9 for c in ALL_TECH} | {p: 0.9 for p in PRACTICE_CRITERIA}
    rows, turn_topics = [], {}
    for i, (cid, s) in enumerate(sorted(full.items())):
        action = cid.split(".", 1)[0]
        for k in (1, 2):  # two strong answers per criterion
            tid = f"t{k}-{cid}"
            turn_topics[tid] = action if action != "practice-backend" else f"topic{k}"
            rows.append(SimpleNamespace(action_id=action, criterion_id=cid, score=s, no_experience=None,
                                        evidence=[{"turn_id": tid, "exact_excerpt": "x"}]))
    for cid in sorted(full):  # then an off-topic answer: a null revision of every criterion, no quote
        rows.append(SimpleNamespace(action_id=cid.split(".", 1)[0], criterion_id=cid, score=None, no_experience=None,
                                    evidence=[]))
    evidence = seniority_evidence(rows, turn_topics)
    row = _row("S11", "strong answers, then off-topic",
               "two strong (0.9) revisions per criterion with quotes, then a null off-topic revision of every "
               "criterion; evidence built by core.seniority_evidence", "earlier scores preserved; SENIOR unchanged",
               evidence, lambda r: r.assessed_level == "SENIOR" and all(
                   evidence[c].score == 0.9 and len(evidence[c].evidence_turns) >= 1 for c in full))
    return row


def e2e_scenarios(env=None) -> tuple[list[dict], list[dict]]:
    """Whole interviews through the standard API (SIMULATED realistic stub, exact anchors, no noise)."""
    from scripts.chapter4.realistic_runs import run_detailed, senior_diagnosis
    from scripts.chapter4.scenarios import Env
    from scripts.seniority_realistic import profiles
    truths = profiles()
    cases = [  # (id, profile, desired, per_q, goal, years, expected, check)
        ("S04-E2E", "senior", "senior", 2, "OPEN", 6, "SENIOR", lambda lv: lv["assessed_level"] == "SENIOR"),
        ("S07-E2E", "senior", "junior", 2, "OPEN", 2, "SENIOR (desired junior does not cap depth)",
         lambda lv: lv["assessed_level"] == "SENIOR"),
        ("S01-E2E", "junior", "senior", 2, "OPEN", 6, "not SENIOR (JUNIOR)", lambda lv: lv["assessed_level"] == "JUNIOR"),
        ("S08-E2E", "weak", "senior", 2, "OPEN", 15, "no raise from 15 years (UNKNOWN)",
         lambda lv: lv["assessed_level"] == "UNKNOWN"),
        ("S10-E2E", "middle", "senior", 2, "OPEN", 6, "MIDDLE; Senior UNVERIFIED, not GAP",
         lambda lv: lv["assessed_level"] == "MIDDLE" and lv["coverage_by_level"]["SENIOR"]["status"] == "UNVERIFIED"),
        ("S04-E2E-narrow", "senior", "senior", 1, "OPEN", 6, "SENIOR (1 criterion per question)",
         lambda lv: lv["assessed_level"] == "SENIOR"),
    ]
    rows, turns = [], []
    own = env is None
    ctx = Env() if own else None
    env = ctx.__enter__() if own else env
    try:
        for sid, name, desired, pq, goal, years, expected, check in cases:
            run_id = f"ch4-{sid.lower()}"
            r = run_detailed(env, name, truths[name], desired, pq, goal, None, run_id, years)
            lv = r["level"]
            d = senior_diagnosis(r)
            sen = lv["coverage_by_level"]["SENIOR"]
            rows.append({
                "scenario_id": sid, "title": f"true profile '{name}', desired {desired}, {pq} criteria/question, "
                                             f"{goal} goals, years {years}",
                "label": "SIMULATED_E2E", "run_id": run_id,
                "input": f"realistic stub; questions={r['questions']} topics={len(r['topics'])} "
                         f"max/topic={r['max_per_topic']} fallback={r['fallback_questions']} difficulty={r['difficulty']}",
                "expected": expected,
                "actual": f"{lv['assessed_level']} ({lv['assessment_status']}); Senior {sen['status']}",
                "criteria": len([e for e in r["evidence"].values() if e.score is not None]),
                "scores": json.dumps({"known": len([e for e in r["evidence"].values() if e.score is not None])}),
                "coverage": "; ".join(f"{k[0]}:{v['status']} k={v['confirmed_count']}/{v['critical_total']} "
                                      f"tech={v.get('technical_confirmed_count')} prac={v.get('practice_confirmed_count')}"
                                      + (f" [{' '.join(v['reasons'])}]" if v["reasons"] else "")
                                      for k, v in lv["coverage_by_level"].items()),
                "evidence_refs": sum(len(x["turn_ids"]) for x in lv["evidence_references"]),
                "result": " | ".join(lv["explanation"][:2]), "verdict": "PASS" if check(lv) else "FAIL",
                "test_path": TEST_PATH, "policy": f"{lv['policy']['id']}/{lv['policy']['version']}",
                "note": f"interview_id={r['interview_id']}; causes={' '.join(d['causes']) or '-'}"})
            for t in r["turns"]:
                turns.append({"run_id": run_id, "scenario_id": sid, "label": "SIMULATED", "interview_id": r["interview_id"],
                              "policy": "python-backend/v4", **t})
    finally:
        if own:
            ctx.__exit__(None, None, None)
    return rows, turns


HEADER = ["scenario_id", "title", "label", "run_id", "input", "expected", "actual", "criteria", "scores", "coverage",
          "evidence_refs", "result", "verdict", "test_path", "policy", "note"]


def main() -> int:
    from scripts.chapter4.common import OUT, write_csv
    est = estimator_scenarios()
    e2e, turns = e2e_scenarios()
    rows = [{k: v for k, v in r.items() if k in HEADER} for r in est + e2e]
    write_csv(OUT / "seniority_results.csv", HEADER, rows)
    with open(OUT / "interview_turns.jsonl", "w", encoding="utf-8") as f:
        for t in turns:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    for r in rows:
        print(f"{r['scenario_id']:15} {r['label']:15} {r['verdict']:4} {r['actual']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
