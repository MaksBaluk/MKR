"""artifacts/chapter4/mathematical_validation.csv: the hand-worked control examples of math_validation.py (re-run on the
current code) plus the seeded property checks of math_checks.py. Unit-level evidence of algorithm correctness only;
it says nothing about the empirical quality of grades or rankings. The thesis DOCX is not in the repository: formulas
are compared with docs/tasks/MATH_SPEC.md.

Run from app/:  uv run python -m scripts.chapter4.math_validation_ch4
"""
from __future__ import annotations

from collections import Counter

from scripts.chapter4 import math_validation
from scripts.chapter4.common import OUT, sh, write_csv
from scripts.chapter4.math_checks import SEED, run_all

HEADER = ["id", "kind", "quantity", "math_spec_ref", "property", "method", "cases", "input", "expected", "actual",
          "status", "detail", "commit"]


def build() -> list[dict]:
    commit = sh("git", "rev-parse", "HEAD")
    rows = [{"id": f"CE-{r['id']}", "kind": "CONTROL_EXAMPLE", "quantity": r["area"], "math_spec_ref": "",
             "property": r["formula"], "method": "hand-worked example", "cases": 1, "input": r["input"],
             "expected": r["expected"], "actual": r["actual"], "status": r["status"], "detail": r["why"],
             "commit": commit} for r in math_validation.ROWS]
    rows += [{**r, "kind": "PROPERTY", "input": f"seed {SEED}:{r['id']}", "expected": "", "actual": "",
              "commit": commit} for r in run_all()]
    write_csv(OUT / "mathematical_validation.csv", HEADER, rows)
    return rows


if __name__ == "__main__":
    rows = build()
    print(len(rows), "rows", dict(Counter(r["status"] for r in rows)))
    for r in rows:
        if r["status"] not in ("PASS",):
            print(r["id"], r["status"], r["detail"][:160])
