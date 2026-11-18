"""Write fixtures/vacancy_sources.json: the display source of every non-imported (example) vacancy.

The assignment is a project-owner statement at catalog level, NOT a per-posting provenance: it is deterministic (sha256 of
the vacancy id) and recorded as such in the file. Run from app/: uv run python scripts/assign_vacancy_sources.py"""
import hashlib
import json
from pathlib import Path

FX = Path(__file__).resolve().parents[1] / "fixtures"
SOURCES = {"python": ["robota.ua", "work.ua", "DOU"], "marketing": ["robota.ua", "work.ua"], "design": ["robota.ua", "work.ua"]}


def pick(vacancy_id: str, track: str) -> str:
    options = SOURCES[track]
    return options[int(hashlib.sha256(vacancy_id.encode()).hexdigest(), 16) % len(options)]


def main() -> int:
    rows = json.loads((FX / "vacancies.json").read_text("utf-8"))
    doc = {"_note": "Display source of example vacancies. Assignment: project-owner statement at catalog level (data adapted for "
                    "illustration), deterministic by vacancy id; not the provenance of an individual posting. The thesis note describes this.",
           "assignment": "OWNER_STATEMENT_CATALOG_LEVEL", "by_vacancy": {r["id"]: pick(r["id"], r["track"]) for r in rows}}
    (FX / "vacancy_sources.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print("assigned", len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
