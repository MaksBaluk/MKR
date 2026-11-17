"""Expert label schemas, loaders, validators and adjudication. Pure: no DB, no engine imports.

Labels are ground truth for evaluation only; nothing in recommendation/ranking code may use them."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError, field_validator, model_validator


class DataStatus(str, Enum):
    SYNTHETIC_TEST_DATA = "SYNTHETIC_TEST_DATA"
    EXPERT = "EXPERT"


class ReviewStatus(str, Enum):
    PENDING = "PENDING"
    REVIEWED = "REVIEWED"
    ADJUDICATED = "ADJUDICATED"


class LabelError(ValueError):
    """Invalid label data. `errors` holds every "row N: reason" message (header = row 1)."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


class SyntheticDataError(ValueError):
    """Raised when SYNTHETIC_TEST_DATA labels are used where expert data is required."""


class _Label(BaseModel):
    annotator_id: str
    label_version: str
    data_status: DataStatus
    review_status: ReviewStatus = ReviewStatus.PENDING

    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, v: Any, info) -> Any:
        if info.field_name in ("expert_score", "grade", "evidence_reference"):
            return v
        if isinstance(v, str):
            v = v.strip()
            if not v and info.field_name != "review_status":
                raise ValueError("must not be empty")
        return v

    def key(self) -> tuple[str, ...]:
        raise NotImplementedError


class ExpertRelevanceLabel(_Label):
    candidate_id: str
    vacancy_id: str
    grade: int
    rationale: str

    @field_validator("grade", mode="before")
    @classmethod
    def _grade(cls, v: Any) -> int:
        if isinstance(v, bool):
            raise ValueError("grade must be an integer 0..3")
        if isinstance(v, str):
            try:
                v = float(v.strip())
            except ValueError:
                raise ValueError("grade must be an integer 0..3") from None
        if not isinstance(v, (int, float)) or not math.isfinite(v) or v != int(v):
            raise ValueError("grade must be an integer 0..3")
        v = int(v)
        if not 0 <= v <= 3:
            raise ValueError("grade must be in 0..3")
        return v

    @field_validator("rationale")
    @classmethod
    def _rationale(cls, v: str) -> str:
        if len(v) < 10:
            raise ValueError("rationale must be at least 10 characters")
        return v

    def key(self) -> tuple[str, ...]:
        return (self.candidate_id, self.vacancy_id)


class ExpertCriterionLabel(_Label):
    candidate_id: str
    action_id: str
    criterion_id: str
    rubric_version: str
    expert_score: float | None
    evidence_reference: str = ""

    @field_validator("expert_score", mode="before")
    @classmethod
    def _score(cls, v: Any) -> float | None:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        if isinstance(v, bool):
            raise ValueError("expert_score must be a number in [0,1] or empty")
        try:
            f = float(v)
        except (TypeError, ValueError):
            raise ValueError("expert_score must be a number in [0,1] or empty") from None
        if not math.isfinite(f) or not 0.0 <= f <= 1.0:
            raise ValueError("expert_score must be finite and in [0,1]")
        return f

    @model_validator(mode="after")
    def _evidence(self) -> "ExpertCriterionLabel":
        if self.expert_score is not None and len(self.evidence_reference.strip()) < 3:
            raise ValueError("evidence_reference (min 3 chars) required when expert_score is set")
        return self

    def key(self) -> tuple[str, ...]:
        return (self.candidate_id, self.action_id, self.criterion_id)


def _fmt(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'row'}: {e['msg']}" for e in exc.errors())


def _read_rows(path: Path) -> list[dict]:
    path = Path(path)
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
            raise LabelError(["row 1: JSON must be a list of objects"])
        return data
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _load(path: Path, model: type[_Label]) -> list:
    out, errors = [], []
    for n, row in enumerate(_read_rows(path), start=2):  # header = row 1
        try:
            out.append(model.model_validate(row))
        except ValidationError as exc:
            errors.append(f"row {n}: {_fmt(exc)}")
    if errors:
        raise LabelError(errors)
    return out


def load_relevance_labels(path: Path) -> list[ExpertRelevanceLabel]:
    return _load(path, ExpertRelevanceLabel)


def load_criterion_labels(path: Path) -> list[ExpertCriterionLabel]:
    return _load(path, ExpertCriterionLabel)


def validate_label_set(labels: Sequence[_Label]) -> None:
    errors: list[str] = []
    if len({lb.data_status for lb in labels}) > 1:
        errors.append("mixed data_status (SYNTHETIC_TEST_DATA and EXPERT) in one label set")
    seen: dict[tuple, int] = {}
    for n, lb in enumerate(labels, start=2):
        k = (lb.annotator_id, *lb.key())
        if k in seen:
            errors.append(
                f"row {n}: duplicate label by annotator {lb.annotator_id!r} for {lb.key()} (first at row {seen[k]})"
            )
        else:
            seen[k] = n
    if errors:
        raise LabelError(errors)


def split_by_annotator(labels: Sequence[_Label]) -> dict[str, list]:
    out: dict[str, list] = defaultdict(list)
    for lb in labels:
        out[lb.annotator_id].append(lb)
    return dict(out)


def _keyset(labels: Sequence[_Label]) -> set[tuple]:
    return {lb.key() for lb in labels}


def adjudicate(a: Sequence, b: Sequence, final: Sequence, adjudicator_id: str) -> list:
    errors: list[str] = []
    ids_a, ids_b = {lb.annotator_id for lb in a}, {lb.annotator_id for lb in b}
    if len(ids_a) != 1 or len(ids_b) != 1:
        errors.append("each annotator set must come from exactly one annotator")
    elif ids_a == ids_b:
        errors.append(f"annotators must be distinct, both are {next(iter(ids_a))!r}")
    elif adjudicator_id in ids_a | ids_b:
        errors.append("adjudicator must differ from both annotators")
    ka, kb, kf = _keyset(a), _keyset(b), _keyset(final)
    if ka != kb:
        errors.append(f"annotators labelled different keys: {len(ka ^ kb)} differ")
    if kf != (ka & kb):
        errors.append(
            f"final must cover exactly the shared keys: missing {len((ka & kb) - kf)}, extra {len(kf - (ka & kb))}"
        )
    if len(kf) != len(final):
        errors.append("final contains duplicate keys")
    bad = [lb.key() for lb in final if lb.annotator_id != adjudicator_id]
    if bad:
        errors.append(f"final labels must carry adjudicator_id {adjudicator_id!r}: {len(bad)} do not")
    if errors:
        raise LabelError(errors)
    return [lb.model_copy(update={"review_status": ReviewStatus.ADJUDICATED}) for lb in final]


def agreement_report(a: Sequence[ExpertRelevanceLabel], b: Sequence[ExpertRelevanceLabel]) -> dict:
    gb = {lb.key(): lb.grade for lb in b}
    pairs = [(lb.grade, gb[lb.key()]) for lb in a if lb.key() in gb]
    n = len(pairs)
    confusion = {i: {j: 0 for j in range(4)} for i in range(4)}
    for x, y in pairs:
        confusion[x][y] += 1
    kappa = None
    if n:
        obs = sum((x - y) ** 2 for x, y in pairs) / (9 * n)
        ca, cb = Counter(x for x, _ in pairs), Counter(y for _, y in pairs)
        exp = sum(ca[i] * cb[j] * (i - j) ** 2 for i in range(4) for j in range(4)) / (9 * n * n)
        kappa = None if exp == 0 else 1 - obs / exp
    return {
        "n_pairs": n,
        "exact_agreement": sum(x == y for x, y in pairs) / n if n else None,
        "quadratic_weighted_kappa": kappa,
        "confusion": confusion,
    }


def relevance_map(final: Sequence[ExpertRelevanceLabel], candidate_id: str) -> dict[str, int]:
    return {lb.vacancy_id: lb.grade for lb in final if lb.candidate_id == candidate_id}


def require_expert_data(labels: Sequence[_Label]) -> None:
    n = sum(lb.data_status is DataStatus.SYNTHETIC_TEST_DATA for lb in labels)
    if n:
        raise SyntheticDataError(f"{n} label(s) are SYNTHETIC_TEST_DATA; expert data required")
