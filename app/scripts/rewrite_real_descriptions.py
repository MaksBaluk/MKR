"""Rebuild summary/description of fixtures/vacancies_real.json from the stored fields (offline, idempotent).
Run from app/: uv run python scripts/rewrite_real_descriptions.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.domain.vacancy_import import compose_texts  # noqa: E402

FX = Path(__file__).resolve().parents[1] / "fixtures"
names = {c["id"]: c["label_uk"] for c in json.loads((FX / "competencies.json").read_text("utf-8"))}
path = FX / "vacancies_real.json"
rows = json.loads(path.read_text("utf-8"))
for r in rows:
    r["summary"], r["description"] = compose_texts(r, names)
path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", "utf-8")
print("rewrote", len(rows))
