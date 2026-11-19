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
class CriterionPool:
    """Critical unit of a pooled policy (v2): criteria that evidence one professional capability across tools.
    Any member can confirm the pool; members of one pool never stand in for another pool (§3e)."""
    pool_id: str
    title: str  # Ukrainian, user-facing
    members: tuple[str, ...]


@dataclass(frozen=True)
class LevelRule:
    level: Level
    tau: float
    min_assessed_share: float
    min_confirmed_share: float
    min_competencies: int
    critical: tuple[str, ...]  # pooled rules: the union of pool members (policy order)
    pools: tuple[CriterionPool, ...] = ()  # empty: every critical id is its own unit (v1 code path)
    min_assessed: int | None = None  # pooled rules: count-based thresholds over pools
    min_confirmed: int | None = None


def pooled(level: Level, tau: float, min_assessed: int, min_confirmed: int, min_competencies: int,
           pools: tuple[CriterionPool, ...]) -> LevelRule:
    """Count-based rule over pools; share thresholds are neutral (0) so only the counts decide."""
    members = tuple(dict.fromkeys(c for p in pools for c in p.members))
    return LevelRule(level, tau, 0.0, 0.0, min_competencies, members, pools, min_assessed, min_confirmed)


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

_P = CriterionPool
PYTHON_BACKEND_V2 = SeniorityPolicy(
    policy_id="python-backend", version="v2", track="python", status="WORKING_ASSUMPTION",
    rules=(
        pooled(Level.JUNIOR, 0.50, 5, 5, 3, (
            _P("python-basics", "Базове володіння Python", ("python-core.idioms", "python-core.errors")),
            _P("data-queries", "Запити до реляційних даних", ("sql.joins", "sql.correctness", "sql.aggregation")),
            _P("api-contract", "Контракт і валідація API", ("rest-api.contract", "fastapi.validation")),
            _P("code-testing", "Перевірка коректності коду", ("python-core.testing", "pytest.structure")),
            _P("build-run", "Збирання й запуск сервісу",
               ("docker.images", "docker.compose", "ci-cd.pipeline", "git.branching")),
            _P("practice-independence", "Самостійність у виконанні задач", ("practice-backend.independence",)),
        )),
        pooled(Level.MIDDLE, 0.70, 10, 8, 5, (
            _P("typed-contracts", "Типізація та контракти коду", ("python-core.typing",)),
            _P("query-efficiency", "Ефективність запитів і доступу до даних",
               ("postgresql.indexes", "sql.performance", "sqlalchemy.loading", "django.orm")),
            _P("data-consistency", "Транзакції та узгодженість даних",
               ("postgresql.transactions", "sqlalchemy.session")),
            _P("schema-design", "Проєктування схеми даних", ("postgresql.schema", "sqlalchemy.models")),
            _P("service-design", "Структура сервісу та API",
               ("fastapi.dependencies", "rest-api.pagination", "django.architecture")),
            _P("async-io", "Асинхронна робота без блокувань",
               ("fastapi.async", "async-python.blocking", "async-python.eventloop")),
            _P("test-isolation", "Ізольовані тести сервісу",
               ("pytest.isolation", "fastapi.testing", "async-python.testing")),
            _P("deploy-config", "Конфігурація та розгортання",
               ("docker.runtime", "ci-cd.deploy", "aws.deploy", "kubernetes.workloads")),
            _P("async-processing", "Обробка подій і фонових задач",
               ("kafka.consumers", "celery.design", "celery.retries", "redis.caching")),
            _P("input-security", "Безпека вхідних даних і секретів",
               ("app-security.input", "app-security.secrets", "docker.security")),
            _P("practice-independence", "Самостійність у виконанні задач", ("practice-backend.independence",)),
            _P("practice-rationale", "Обґрунтування рішень", ("practice-backend.rationale",)),
            _P("practice-diagnosis", "Діагностика проблем", ("practice-backend.diagnosis",)),
        )),
        pooled(Level.SENIOR, 0.75, 10, 10, 4, (
            _P("db-operations", "Експлуатація й безпечні зміни бази даних",
               ("postgresql.operations", "postgresql.migrations", "django.migrations")),
            _P("concurrency", "Конкурентний доступ і паралельність",
               ("sqlalchemy.concurrency", "async-python.concurrency")),
            _P("delivery-reliability", "Надійна доставка повідомлень і задач",
               ("kafka.semantics", "kafka.errors", "celery.idempotency", "redis.reliability")),
            _P("release-safety", "Безпечні релізи та відкат", ("ci-cd.safety",)),
            _P("access-security", "Безпека доступу та авторизація",
               ("app-security.authz", "rest-api.security", "aws.iam", "django.permissions", "kubernetes.security")),
            _P("incident-diagnosis", "Розслідування інцидентів у продакшені",
               ("observability.incidents", "observability.tracing", "linux.diagnostics",
                "kubernetes.troubleshooting")),
            _P("architecture-tradeoffs", "Вибір інфраструктури з урахуванням вартості й надійності",
               ("aws.services", "aws.cost")),
            _P("contract-evolution", "Сумісність контрактів під час змін", ("rest-api.versioning", "kafka.schemas")),
            _P("practice-tradeoffs", "Аналіз компромісів", ("practice-backend.tradeoffs",)),
            _P("practice-ambiguity", "Робота з невизначеністю", ("practice-backend.ambiguity",)),
            _P("practice-ownership", "Відповідальність за результат", ("practice-backend.ownership",)),
            _P("practice-diagnosis", "Діагностика проблем", ("practice-backend.diagnosis",)),
            _P("practice-rationale", "Обґрунтування рішень", ("practice-backend.rationale",)),
        )),
    ))

# Every policy version ever used to store a level stays addressable, so stored rows keep their meaning.
POLICY_VERSIONS: dict[tuple[str, str], SeniorityPolicy] = {
    (p.policy_id, p.version): p for p in (PYTHON_BACKEND_V1, PYTHON_BACKEND_V2)}

# Current policy per track: new finalizations use it. Marketing and design have none (unreviewed rubrics).
POLICIES: dict[str, SeniorityPolicy | None] = {"python": PYTHON_BACKEND_V2, "marketing": None, "design": None}


def policy_for(track: str | None) -> SeniorityPolicy | None:
    return POLICIES.get(track) if track else None


def policy_by_version(policy_id: str | None, version: str | None) -> SeniorityPolicy | None:
    return POLICY_VERSIONS.get((policy_id, version)) if policy_id and version else None
