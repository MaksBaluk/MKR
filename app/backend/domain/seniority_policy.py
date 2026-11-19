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
    # Capability rules (v4) only; None/empty keeps the v1-v3 semantics exactly (see seniority._capability_coverage).
    gap_below: float | None = None  # established gap: s < gap_below; [gap_below, tau) is borderline (unresolved)
    min_technical: int = 0  # CONFIRMED non-practice pools
    min_practice: int = 0  # CONFIRMED practice pools
    max_soft_gaps: int = 0  # GAP pools tolerated outside hard_pools (still reported as gaps)
    hard_pools: tuple[str, ...] = ()  # a GAP in one of these always makes the level GAP
    required_any: tuple[str, ...] = ()  # at least one of these pools must be CONFIRMED

    @property
    def capability(self) -> bool:
        return self.gap_below is not None


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
    # Capability policies (v4): distinct GAP pools tolerated over a level and all lower levels together. None: v1-v3.
    max_chain_soft_gaps: int | None = None


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
# Any-of only across different tools: the members of one pool always have distinct competency prefixes, so two skills of
# one tool (e.g. sql.joins and sql.correctness) are never alternatives and a gap in one is never hidden by the other.
# Counts are ceil(share * pools) with the owner-chosen shares Junior .75/.75, Middle .70/.60, Senior .75/.70
# (lowered from v1; not calibrated).
PYTHON_BACKEND_V2 = SeniorityPolicy(
    policy_id="python-backend", version="v2", track="python", status="WORKING_ASSUMPTION",
    rules=(
        pooled(Level.JUNIOR, 0.50, 7, 7, 3, (
            _P("python-idioms", "Ідіоматичний код Python", ("python-core.idioms",)),
            _P("python-errors", "Обробка помилок у Python", ("python-core.errors",)),
            _P("sql-joins", "З'єднання таблиць у запитах", ("sql.joins",)),
            _P("sql-correctness", "Коректність результатів запитів", ("sql.correctness",)),
            _P("api-contract", "Контракт і валідація API", ("rest-api.contract", "fastapi.validation")),
            _P("code-testing", "Перевірка коректності коду", ("python-core.testing", "pytest.structure")),
            _P("build-pipeline", "Збирання сервісу", ("docker.images", "ci-cd.pipeline")),
            _P("version-control", "Робота з гілками в Git", ("git.branching",)),
            _P("practice-independence", "Самостійність у виконанні задач", ("practice-backend.independence",)),
        )),
        pooled(Level.MIDDLE, 0.70, 10, 9, 5, (
            _P("typed-contracts", "Типізація та контракти коду", ("python-core.typing",)),
            _P("query-efficiency", "Ефективність запитів і доступу до даних",
               ("postgresql.indexes", "sql.performance", "sqlalchemy.loading", "django.orm")),
            _P("data-consistency", "Транзакції та узгодженість даних",
               ("postgresql.transactions", "sqlalchemy.session")),
            _P("schema-design", "Проєктування схеми даних", ("postgresql.schema", "sqlalchemy.models")),
            _P("service-design", "Структура сервісу та API",
               ("fastapi.dependencies", "rest-api.pagination", "django.architecture")),
            _P("async-io", "Асинхронна робота без блокувань", ("fastapi.async", "async-python.blocking")),
            _P("test-isolation", "Ізольовані тести сервісу",
               ("pytest.isolation", "fastapi.testing", "async-python.testing")),
            _P("deploy-config", "Конфігурація та розгортання",
               ("docker.runtime", "ci-cd.deploy", "aws.deploy", "kubernetes.workloads")),
            _P("event-consumers", "Споживачі подій і фонові задачі", ("kafka.consumers", "celery.design")),
            _P("failure-handling", "Обробка збоїв і повторні спроби", ("kafka.errors", "celery.retries")),
            _P("secure-config", "Безпека контейнерів і секретів", ("docker.security", "app-security.secrets")),
            _P("practice-independence", "Самостійність у виконанні задач", ("practice-backend.independence",)),
            _P("practice-rationale", "Обґрунтування рішень", ("practice-backend.rationale",)),
            _P("practice-diagnosis", "Діагностика проблем", ("practice-backend.diagnosis",)),
        )),
        pooled(Level.SENIOR, 0.75, 11, 10, 4, (
            _P("db-operations", "Експлуатація бази даних", ("postgresql.operations",)),
            _P("schema-migrations", "Безпечні зміни схеми", ("postgresql.migrations", "django.migrations")),
            _P("concurrency", "Конкурентний доступ і паралельність",
               ("sqlalchemy.concurrency", "async-python.concurrency")),
            _P("delivery-guarantees", "Гарантії доставки повідомлень і задач",
               ("kafka.semantics", "celery.idempotency", "redis.reliability")),
            _P("release-safety", "Безпечні релізи та відкат", ("ci-cd.safety",)),
            _P("access-security", "Безпека доступу та авторизація",
               ("app-security.authz", "rest-api.security", "aws.iam", "django.permissions", "kubernetes.security")),
            _P("incident-diagnosis", "Розслідування інцидентів у продакшені",
               ("observability.incidents", "linux.diagnostics", "kubernetes.troubleshooting")),
            _P("cost-reliability", "Вартість і надійність інфраструктури", ("aws.cost",)),
            _P("contract-evolution", "Сумісність контрактів під час змін", ("rest-api.versioning", "kafka.schemas")),
            _P("practice-tradeoffs", "Аналіз компромісів", ("practice-backend.tradeoffs",)),
            _P("practice-ambiguity", "Робота з невизначеністю", ("practice-backend.ambiguity",)),
            _P("practice-ownership", "Відповідальність за результат", ("practice-backend.ownership",)),
            _P("practice-diagnosis", "Діагностика проблем", ("practice-backend.diagnosis",)),
            _P("practice-rationale", "Обґрунтування рішень", ("practice-backend.rationale",)),
        )),
    ))

# v3 = v2 pools with a lower Senior bar (owner decision: Senior was out of reach on the topics Q_t picks). Junior and
# Middle rules are the v2 objects. Senior counts are ceil(share * 14 pools) with the chosen shares .60/.50 -> 9/7, and
# min_competencies 4 -> 3 (owner target ~6 topics; with 4 the measured minimum is 7-8). It counts distinct tools of the
# confirming member ids, not pools: two tools confirming one pool count twice, so Senior can rest on 2 technical Senior
# capabilities plus 5 practice pools. It is not a breadth guarantee (MATH_SPEC §3e, v3).
# Lowering means Senior needs less evidence; the numbers are a working assumption, not measured or calibrated.
_J2, _M2, _S2 = PYTHON_BACKEND_V2.rules
PYTHON_BACKEND_V3 = SeniorityPolicy(
    policy_id="python-backend", version="v3", track="python", status="WORKING_ASSUMPTION",
    rules=(_J2, _M2, pooled(Level.SENIOR, _S2.tau, 9, 7, 3, _S2.pools)))


def capability(level: Level, tau: float, gap_below: float, min_confirmed: int, min_technical: int, min_practice: int,
               min_competencies: int, pools: tuple[CriterionPool, ...], *, max_soft_gaps: int = 1,
               hard_pools: tuple[str, ...] = (), required_any: tuple[str, ...] = ()) -> LevelRule:
    """Capability rule (v4): gaps are decided per capability, not per tool (MATH_SPEC §3e v4). Only CONFIRMED and GAP
    pools are decided evidence; UNRESOLVED (borderline/untraced), DECLINED and UNASSESSED never fill a minimum."""
    members = tuple(dict.fromkeys(c for p in pools for c in p.members))
    return LevelRule(level, tau, 0.0, 0.0, min_competencies, members, pools, None, min_confirmed, gap_below,
                     min_technical, min_practice, max_soft_gaps, hard_pools, required_any)


# v4 = v3 pools with capability-level gaps, anchor-aligned thresholds and counts over confirmed pools (audit 2026-11-19,
# D-1, D-4, D-10, UR-7). Confirm at >= .50 (Junior), >= .70 (Middle, measured under noise) or >= .75 (Senior, band edge
# "good"); a gap is a traced score below .50 ("weak"/"incorrect"). [.50, tau) is borderline: never a gap nor a pass.
# Counts are chosen from the realistic-evaluator measurement (scripts/seniority_reachability.py §6) and remain a
# WORKING_ASSUMPTION: not calibrated, expert validation required.
_V4_SENIOR_POOLS = tuple(
    _P("cost-reliability", "Вартість і надійність інфраструктури", ("aws.cost", "kubernetes.resources"))
    if p.pool_id == "cost-reliability" else p for p in _S2.pools)  # UR-2: no single-tool Senior capability via aws only
PYTHON_BACKEND_V4 = SeniorityPolicy(
    policy_id="python-backend", version="v4", track="python", status="WORKING_ASSUMPTION",
    rules=(
        # Every level needs one confirmed data-layer capability of its own (no backend level without data evidence).
        # Hard pools come from topics Q_t picks in every measured interview (python-core, sql, postgresql): a weak try
        # there always blocks the level. One soft gap is tolerated per chain (max_chain_soft_gaps), not per level.
        # Junior: 6 of 9 capabilities confirmed (5 technical).
        capability(Level.JUNIOR, 0.50, 0.50, 6, 5, 0, 3, _J2.pools,
                   hard_pools=("python-idioms", "python-errors", "sql-correctness"),
                   required_any=("sql-joins", "sql-correctness")),
        # Middle: half of 14 confirmed, >= 5 of 11 technical and >= 2 of 3 practice (justified decisions, diagnosis).
        # Middle tau .70 (fix round 1, I-5): under noisy grading (scripts/seniority_realistic.py --noisy, 224 runs) .75
        # missed 17/56 true Middles versus 9/56 at .70, with identical false-Senior/false-Middle counts. [.50, .70) stays
        # borderline (UNRESOLVED), never a gap: the anchors do not separate scores inside the "partial" band (UR-7).
        capability(Level.MIDDLE, 0.70, 0.50, 7, 5, 2, 4, _M2.pools, hard_pools=("data-consistency",),
                   required_any=("query-efficiency", "data-consistency", "schema-design")),
        # Senior: >= 4 of 9 technical Senior capabilities, >= 3 of 5 practice, one of them on the data layer (WS-3).
        capability(Level.SENIOR, 0.75, 0.50, 7, 4, 3, 3, _V4_SENIOR_POOLS,
                   hard_pools=("db-operations", "schema-migrations"),
                   required_any=("db-operations", "schema-migrations")),
    ),
    max_chain_soft_gaps=1)

# Every policy version ever used to store a level stays addressable, so stored rows keep their meaning.
POLICY_VERSIONS: dict[tuple[str, str], SeniorityPolicy] = {
    (p.policy_id, p.version): p
    for p in (PYTHON_BACKEND_V1, PYTHON_BACKEND_V2, PYTHON_BACKEND_V3, PYTHON_BACKEND_V4)}

# Current policy per track: new finalizations use it. Marketing and design have none (unreviewed rubrics).
POLICIES: dict[str, SeniorityPolicy | None] = {"python": PYTHON_BACKEND_V4, "marketing": None, "design": None}


def policy_for(track: str | None) -> SeniorityPolicy | None:
    return POLICIES.get(track) if track else None


def policy_by_version(policy_id: str | None, version: str | None) -> SeniorityPolicy | None:
    return POLICY_VERSIONS.get((policy_id, version)) if policy_id and version else None
