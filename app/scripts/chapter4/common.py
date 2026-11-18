"""Shared paths for the chapter-4 evidence scripts. Output goes to <repo>/artifacts/chapter4/."""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[2]
REPO = APP.parent
OUT = REPO / "artifacts" / "chapter4"
sys.path.insert(0, str(APP))


def sh(*cmd: str, cwd: Path = REPO) -> str:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception as exc:  # noqa: BLE001 - evidence script: record the failure instead of crashing
        return f"UNAVAILABLE ({type(exc).__name__})"


def write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
