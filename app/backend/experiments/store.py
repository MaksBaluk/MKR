"""Experiment run records: persistence in experiment_runs and JSON/CSV export."""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from backend.models import ExperimentRun

# experiment_runs has no own column for it: stored inside the config JSON and popped by load_record.
# ExperimentConfig.from_json ignores this key, so a raw row's config can still be parsed directly.
_SOURCE_KEY = "answer_source"


@dataclass
class ExperimentRecord:
    experiment_id: str
    candidate_id: str
    mode: str
    config: dict
    cohort_id: str  # "" when the cohort is empty
    cohort_sha256: str
    profile_snapshot: dict
    rubric_versions: dict
    prompt_version: str
    model_info: dict
    algorithm_version: str
    qa: list[dict]
    assessments: list[dict]
    ranking: list[dict]
    timings: dict
    errors: dict
    answer_source: str  # "SCRIPTED" | "HUMAN" | "SIMULATED" | "NONE"
    interview_id: str | None = None


def save_record(db: Session, record: ExperimentRecord) -> str:
    data = asdict(record)
    data["config"] = {**record.config, _SOURCE_KEY: data.pop(_SOURCE_KEY)}
    row = ExperimentRun(**data)
    db.add(row)
    db.commit()
    return row.id


def load_record(db: Session, run_id: str) -> ExperimentRecord:
    row = db.get(ExperimentRun, run_id)
    if row is None:
        raise KeyError(run_id)
    config = dict(row.config)
    source = config.pop(_SOURCE_KEY, "UNKNOWN")
    return ExperimentRecord(experiment_id=row.experiment_id, candidate_id=row.candidate_id, mode=row.mode,
                            config=config, cohort_id=row.cohort_id, cohort_sha256=row.cohort_sha256,
                            profile_snapshot=row.profile_snapshot, rubric_versions=row.rubric_versions,
                            prompt_version=row.prompt_version, model_info=row.model_info,
                            algorithm_version=row.algorithm_version, qa=row.qa, assessments=row.assessments,
                            ranking=row.ranking, timings=row.timings, errors=row.errors, answer_source=source,
                            interview_id=row.interview_id)


_FLAGS = ("adaptive_topics", "adaptive_followup", "adaptive_difficulty", "max_topics", "max_per_topic",
          "total_budget", "static_questions_per_topic")
_ERRORS = ("ungraded_answers", "fallback_questions", "llm_exceptions", "empty_cohort")
CSV_FIELDS = ["experiment_id", "candidate_id", "mode", *_FLAGS, "answer_source", "interview_id", "cohort_id",
              "cohort_sha256", "n_vacancies", "n_questions", "n_assessed_criteria", *_ERRORS,
              "total_s", "llm_wait_s", "llm_calls"]


def _csv_row(r: ExperimentRecord) -> dict:
    return {"experiment_id": r.experiment_id, "candidate_id": r.candidate_id, "mode": r.mode,
            **{k: r.config.get(k) for k in _FLAGS}, "answer_source": r.answer_source,
            "interview_id": r.interview_id or "", "cohort_id": r.cohort_id, "cohort_sha256": r.cohort_sha256,
            "n_vacancies": len(r.ranking), "n_questions": len(r.qa),
            "n_assessed_criteria": sum(1 for a in r.assessments if a["score"] is not None),
            **{k: r.errors.get(k) for k in _ERRORS}, "total_s": r.timings.get("total_s"),
            "llm_wait_s": r.timings.get("llm_wait_s"), "llm_calls": r.timings.get("calls")}


def export_records(records: Sequence[ExperimentRecord], out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "runs.json").write_text(json.dumps([asdict(r) for r in records], ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    with open(out_dir / "runs.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(_csv_row(r) for r in records)
