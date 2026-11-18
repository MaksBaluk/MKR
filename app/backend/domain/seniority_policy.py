"""Versioned level policy (§3e). Lives in code, never in prompts. Status WORKING_ASSUMPTION: needs expert validation."""
from dataclasses import dataclass
from enum import Enum
from typing import Literal


class Level(str, Enum):
    JUNIOR = "JUNIOR"
    MIDDLE = "MIDDLE"
    SENIOR = "SENIOR"


def rank(level: Level) -> int:
    return {Level.JUNIOR: 0, Level.MIDDLE: 1, Level.SENIOR: 2}[level]


@dataclass(frozen=True)
class LevelRule:
    level: Level
    tau: float
    min_assessed_share: float
    min_confirmed_share: float
    min_competencies: int
    critical: tuple[str, ...]


@dataclass(frozen=True)
class SeniorityPolicy:
    policy_id: str
    version: str
    track: str
    status: Literal["WORKING_ASSUMPTION", "VALIDATED"]
    rules: tuple[LevelRule, ...]


PRACTICE_ACTION = "practice-backend"
PRACTICE_CRITERIA: tuple[str, ...] = tuple(
    f"{PRACTICE_ACTION}.{s}" for s in ("independence", "rationale", "tradeoffs", "diagnosis", "ambiguity", "ownership"))

PYTHON_BACKEND_V1 = SeniorityPolicy(
    policy_id="python-backend", version="v1", track="python", status="WORKING_ASSUMPTION",
    rules=(
        LevelRule(Level.JUNIOR, 0.50, 0.75, 0.75, 4, (
            "python-core.idioms", "python-core.errors", "python-core.testing", "sql.joins", "sql.correctness",
            "rest-api.contract", "git.branching", "pytest.structure", "practice-backend.independence")),
        LevelRule(Level.MIDDLE, 0.70, 0.80, 0.70, 5, (
            "python-core.typing", "postgresql.indexes", "postgresql.transactions", "postgresql.schema",
            "sqlalchemy.session", "rest-api.pagination", "pytest.isolation", "app-security.input",
            "async-python.blocking", "ci-cd.pipeline", "practice-backend.independence",
            "practice-backend.rationale", "practice-backend.diagnosis")),
        LevelRule(Level.SENIOR, 0.75, 0.80, 0.80, 6, (
            "postgresql.operations", "postgresql.migrations", "sqlalchemy.concurrency", "celery.idempotency",
            "redis.reliability", "observability.incidents", "app-security.authz", "ci-cd.safety",
            "async-python.concurrency", "rest-api.security", "practice-backend.tradeoffs",
            "practice-backend.ambiguity", "practice-backend.ownership", "practice-backend.diagnosis",
            "practice-backend.rationale")),
    ))

POLICIES: dict[str, SeniorityPolicy | None] = {"python": PYTHON_BACKEND_V1, "marketing": None, "design": None}


def policy_for(track: str | None) -> SeniorityPolicy | None:
    return POLICIES.get(track) if track else None
