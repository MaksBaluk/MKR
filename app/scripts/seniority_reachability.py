"""Reachability of the level policies on the full python cohort (SIMULATED, reproducible). Run from app/:
    uv run python scripts/seniority_reachability.py

1. Topic frequency: 17 answer patterns x 3 desired levels = 51 adaptive interviews through the real API with the
   SIMULATED TruthEvaluator of scripts/seniority_scenarios.py (Q_t, caps and budgets unchanged; in-memory SQLite).
2. Upper bound: every criterion of the first k topics Q_t picked (k = 6, 8, 10) plus all practice graded 0.9.
3. Partial grading: the first n criteria (rubric order) of each of the k most frequent topics (frequency order), with
   1, 3 or 6 practice criteria confirmed.
4. Named cases: a run with no data-layer topic (M-1 disclosure) and the 8 always-picked topics.
5. Minimal number of fully graded topics (measured sequences) for Middle and Senior, per policy and practice count.
6. REALISTIC evaluator (scripts/seniority_realistic.py, audit D-8): 8 hidden-truth profiles x 3 desired levels x
   1-2 criteria per question x follow-up goal GAP_ONLY/OPEN = 96 interviews through the real API; outcome per policy
   (the current one is what the API stores; older versions re-estimate the same evidence).
Policies v1, v2, v3 and the current v4 are reported side by side. Sections 2-5 grade every chosen criterion (and, for
v4, every practice criterion in two topics) at 0.9: an upper bound, not a realistic estimate.
Numbers say what the thresholds imply for given evidence; they do not validate the policy or the evaluator.
"""
from __future__ import annotations

import hashlib
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.seniority_scenarios as S  # noqa: E402  (sets the throwaway DB and disabled provider first)
from backend.domain.seniority import CriterionEvidence, estimate  # noqa: E402
from backend.domain.seniority_policy import (PRACTICE_CRITERIA, PYTHON_BACKEND_V1,  # noqa: E402
                                             PYTHON_BACKEND_V2, PYTHON_BACKEND_V3, PYTHON_BACKEND_V4)
from backend.seed import read_fixture  # noqa: E402
from scripts.chapter4.scenarios import Env  # noqa: E402

RUBRIC = {r["action_id"]: [c["criterion_id"] for c in r["criteria"]] for r in read_fixture("rubrics.json")["rubrics"]}
POLICIES = (PYTHON_BACKEND_V1, PYTHON_BACKEND_V2, PYTHON_BACKEND_V3, PYTHON_BACKEND_V4)
POOLED = (PYTHON_BACKEND_V2, PYTHON_BACKEND_V3, PYTHON_BACKEND_V4)


def _u(seed: object, cid: str) -> float:
    return int(hashlib.sha256(f"{seed}:{cid}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def patterns() -> dict:
    out = {f"all{v}": (lambda v: lambda c: v)(v) for v in (0.9, 0.75, 0.6, 0.4, 0.2)}
    for s in range(8):
        out[f"rand{s}"] = (lambda s: lambda c: round(0.3 + 0.7 * _u(s, c), 2))(s)
    for s in range(4):
        out[f"randnull{s}"] = (lambda s: lambda c: None if _u(s + 100, c) < 0.25 else round(0.3 + 0.7 * _u(s, c), 2))(s)
    return out


def measure_topics() -> list[tuple[str, str, list[str]]]:
    runs = []
    with Env() as env:
        for level in ("junior", "middle", "senior"):
            for name, truth in patterns().items():
                r = S.run(env, S.Scenario(name, name, level, truth, ("-", "-")))
                runs.append((level, name, r["topics"]))
    return runs


def ev(ids) -> dict[str, CriterionEvidence]:
    """Every id at 0.9 with an evidence turn; practice graded in two source topics (v4 reads the per-topic spread)."""
    return {c: CriterionEvidence(c, 0.9, ("t",), topic_scores=(0.9, 0.9) if c in PRACTICE_CRITERIA else ())
            for c in ids}


def line(policy, ids) -> str:
    r = estimate(policy, ev(ids))
    cov = " ".join(f"{k[0]}:{c.status[:4]} a{c.assessed}/{c.critical_total} k{c.confirmed} comp{c.competencies_confirmed}"
                   for k, c in r.coverage_by_level.items())
    return f"{policy.version} {r.assessed_level:8} {cov}"


def topic_ids(topics, per: int | None = None) -> list[str]:
    return [c for t in topics for c in RUBRIC[t][:per]]


def main() -> None:
    print(S.LABEL)
    runs = measure_topics()
    freq = Counter(t for _, _, topics in runs for t in topics)
    print(f"\n1. topic frequency over {len(runs)} interviews (full system cohort):")
    for t, n in freq.most_common():
        print(f"  {t:14} {n}/{len(runs)}")
    never = sorted(set(RUBRIC) & {c.split('.')[0] for r in PYTHON_BACKEND_V2.rules for c in r.critical} - set(freq))
    print("  policy topics never picked:", ", ".join(never))
    by_level = {lvl: [tuple(t) for l2, _, t in runs if l2 == lvl] for lvl in ("junior", "middle", "senior")}
    print("  desired level changes topic sequences:", len({tuple(v) for v in by_level.values()}) > 1)

    sequences = list(dict.fromkeys(tuple(t) for _, _, t in runs))
    print(f"\n2. upper bound: all criteria of the first k picked topics + all practice at 0.9 ({len(sequences)} sequences)")
    for k in (5, 6, 7, 8, 10):
        outcomes = {p.version: Counter() for p in POLICIES}
        for seq in sequences:
            for p in POLICIES:
                outcomes[p.version][estimate(p, ev(topic_ids(seq[:k]) + list(PRACTICE_CRITERIA))).assessed_level] += 1
        print(f"  k={k:2}: " + "; ".join(f"{v}: {dict(c)}" for v, c in outcomes.items()))

    base = list(freq)[:10]  # the ten most frequent topics, in frequency order
    print(f"\n3. partial grading over the {len(base)} most frequent topics {base} (v2 | v3 | v4)")
    for k in (5, 6, 7, 8, 10):
        for per in (2, 3, 4):
            row = []
            for prac in (1, 3, 6):
                got = [estimate(p, ev(topic_ids(base[:k], per) + list(PRACTICE_CRITERIA[:prac]))).assessed_level
                       for p in POOLED]
                row.append(f"practice{prac}={'|'.join(got)}")
            print(f"  topics={k:2} criteria/topic={per}: " + " ".join(row))

    print("\n4. named cases")
    always = [t for t, n in freq.items() if n == len(runs)]
    no_data = [t for t in base if t not in ("sql", "postgresql", "django", "sqlalchemy")][:6]
    sql_only = [t for t in base if t not in ("postgresql", "django", "sqlalchemy")][:8]
    for title, topics in ((f"always-picked {always}", always), (f"no data-layer topic {no_data}", no_data),
                          (f"sql but no postgresql/django {sql_only}", sql_only)):
        for prac in (0, 6):
            for p in POOLED:
                print(f"  {title} practice={prac}: " + line(p, topic_ids(topics) + list(PRACTICE_CRITERIA[:prac])))

    print(f"\n5. minimal k (all criteria of the first k picked topics) over {len(sequences)} sequences: min/max")
    for p in POOLED:
        for prac in (0, 3, 6):
            mins = {"MIDDLE": [], "SENIOR": []}
            for seq in sequences:
                for target in mins:
                    k = next((k for k in range(1, len(seq) + 1) if rank_of(estimate(
                        p, ev(topic_ids(seq[:k]) + list(PRACTICE_CRITERIA[:prac]))).assessed_level) >= rank_of(target)),
                        None)
                    mins[target].append(k)
            print(f"  {p.version} practice={prac}: " + "; ".join(
                f"{t} k={fmt(v)}" for t, v in mins.items()))


def rank_of(level: str) -> int:
    return {"UNKNOWN": -1, "JUNIOR": 0, "MIDDLE": 1, "SENIOR": 2}[level]


def fmt(values: list[int | None]) -> str:
    reached = [v for v in values if v is not None]
    never = len(values) - len(reached)
    if not reached:
        return "never"
    return f"{min(reached)}..{max(reached)}" + (f" (never in {never})" if never else "")


def realistic() -> None:
    import scripts.seniority_realistic as R
    from collections import defaultdict
    print(f"\n6. {R.LABEL}")
    runs = R.grid()
    current = runs[0]["policy"]
    table: dict[tuple, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for r in runs:
        key = (r["profile"], r["per_q"], r["goal"])
        for name, level in r["same_evidence"].items():
            table[key][name.split("/")[1]][level] += 1
    versions = sorted({v for t in table.values() for v in t})
    print(f"  {len(runs)} interviews; API stored policy {current}; outcome counts over desired junior/middle/senior")
    print("  questions per interview: " + fmt_range([r["questions"] for r in runs]))
    for key in sorted(table):
        print(f"  {key[0]:16} per_q={key[1]} {key[2]:8} " + " | ".join(
            f"{v}: " + ", ".join(f"{lvl} {n}" for lvl, n in sorted(table[key][v].items())) for v in versions))


def fmt_range(values: list[int]) -> str:
    return f"{min(values)}..{max(values)}"


if __name__ == "__main__":
    main()
    realistic()
