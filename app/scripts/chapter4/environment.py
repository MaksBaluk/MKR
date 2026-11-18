"""environment.md: the environment the evidence was produced in. Facts come from commands run now, never from memory."""
from __future__ import annotations

import hashlib
import platform
import re
import sys
import time

from scripts.chapter4.common import APP, OUT, REPO, sh
from backend.agents import prompts
from backend.domain.difficulty import DEFAULT_CONFIG
from backend.domain.interview_budget import MAX_SHOWN_QUESTIONS_PER_ACTION, MAX_TOPICS
from backend.domain.core_flow import TAU_BY_LEVEL, TAU_SOURCE_LEVEL_MAP
from backend.experiments.runner import ALGORITHM_VERSION, prompt_version
from backend.api.cohorts import POLICY_ID


def sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def pkg_versions() -> dict[str, str]:
    out = sh("uv", "pip", "list", cwd=APP)
    want = {"fastapi", "sqlalchemy", "alembic", "pydantic", "langgraph", "langchain-core", "langchain-openai", "httpx",
            "uvicorn", "psycopg", "pytest"}
    found = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].lower() in want:
            found[parts[0]] = parts[1]
    return dict(sorted(found.items()))


def env_settings() -> dict[str, str]:
    """LLM settings from app/.env without secrets: key and base URL are never copied."""
    keep = {"LLM_PROVIDER", "LLM_MODEL", "LLM_TIMEOUT_SECONDS", "LLM_QUESTION_GENERATION", "LLM_QUESTION_STRATEGY",
            "LLM_QUESTION_REPHRASING", "DEMO_MODE"}
    out = {}
    p = APP / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^([A-Z_]+)=(.*)$", line)
            if m and m.group(1) in keep:
                out[m.group(1)] = m.group(2)
    return out


def build() -> str:
    dirty = sh("git", "status", "--porcelain")
    tracked = sh("git", "diff", "HEAD", "--stat").splitlines()
    diff_hash = hashlib.sha256(sh("git", "diff", "HEAD").encode()).hexdigest()[:16]
    untracked = [l[3:] for l in dirty.splitlines() if l.startswith("??")]
    fe = sh("node", "-v"), sh("npm", "-v")
    pkg = (REPO / "app/frontend/package.json").read_text(encoding="utf-8")
    import json
    fpkg = json.loads(pkg)
    deps = {**fpkg.get("dependencies", {}), **fpkg.get("devDependencies", {})}
    fe_ver = {k: deps[k] for k in ("react", "react-dom", "vite", "typescript", "vitest", "@playwright/test", "tailwindcss") if k in deps}
    pg = sh("docker", "compose", "exec", "-T", "db", "postgres", "--version", cwd=APP)
    alembic_head = sh("uv", "run", "alembic", "heads", cwd=APP).splitlines()
    s = env_settings()
    lines = [
        "# Експериментальне середовище (CompetenceMatch, розділ 4)", "",
        f"Згенеровано: `{time.strftime('%Y-%m-%d %H:%M:%S %z')}` скриптом `app/scripts/chapter4/environment.py`.", "",
        "## Версія коду", "",
        f"- Commit SHA: `{sh('git', 'rev-parse', 'HEAD')}` (гілка `{sh('git', 'branch', '--show-current')}`).",
        f"- Робоче дерево: **{'НЕ чисте' if dirty else 'чисте'}**. Змінені відстежувані файли: {len(tracked) - 1 if tracked else 0}; "
        f"невідстежувані: {len(untracked)}. SHA-256 (перші 16 символів) `git diff HEAD`: `{diff_hash}`.",
        "- Невідстежувані файли (частина доказів і виправлень аудиту ще не закомічена):",
        *[f"  - `{u}`" for u in untracked], "",
        "Результати нижче відповідають коду `HEAD` **плюс** незакомічені зміни, ідентифіковані хешем diff. "
        "Для відтворюваності закомітьте зміни й повторіть `python -m scripts.chapter4.build_all`.", "",
        "## Платформа", "",
        f"- ОС: `{platform.platform()}`; архітектура `{platform.machine()}`.",
        f"- Процесор: `{sh('sysctl', '-n', 'machdep.cpu.brand_string')}`; ядер: `{sh('sysctl', '-n', 'hw.ncpu')}`; "
        f"RAM: `{round(int(sh('sysctl', '-n', 'hw.memsize') or 0) / 1073741824, 1)}` ГБ.",
        f"- Python: `{sys.version.split()[0]}` (`{sh('uv', '--version', cwd=APP)}`).",
        f"- Node: `{fe[0]}`, npm: `{fe[1]}`.", "",
        "## Залежності", "",
        "Backend (`uv pip list`):", *[f"- {k} {v}" for k, v in pkg_versions().items()], "",
        "Frontend (`app/frontend/package.json`, задані діапазони версій):", *[f"- {k} {v}" for k, v in fe_ver.items()], "",
        "## Бази даних", "",
        "| Контекст | Що фактично використано |", "|---|---|",
        "| Автотести backend | SQLite (in-memory, `StaticPool`), схема з `Base.metadata.create_all` |",
        f"| Продуктовий стек (Docker Compose) | PostgreSQL: `{pg}`; міграції Alembic до голови `{' '.join(alembic_head)}` |",
        "| Експериментальні прогони цього пакета | окрема SQLite-БД у тимчасовому каталозі (ніколи не продуктова) |",
        "| pgvector / HNSW | схема підготовлена, **не заповнена і не використовується** в експериментах |", "",
        "## LLM", "",
        "**Фактично в експериментах цього пакета: детермінована імітація (`SIMULATED_STUB`), реальна LLM не викликалась.** "
        "Нижче — те, що налаштовано в `app/.env` і підтримується кодом, але в цих прогонах НЕ використовувалось.", "",
        f"- Налаштований провайдер: `{s.get('LLM_PROVIDER', 'не задано')}`, модель: `{s.get('LLM_MODEL', 'не задано')}` "
        "(локальний OpenAI-сумісний сервер; адреса й ключ у звіт не копіюються).",
        "- Параметри клієнта (`backend/agents/model.py`): temperature=0.3, max_retries=0, "
        f"timeout={s.get('LLM_TIMEOUT_SECONDS', '?')} с, ліміт вихідних токенів не задано (використовується стандарт сервера).",
        f"- `LLM_QUESTION_GENERATION={s.get('LLM_QUESTION_GENERATION')}`, `LLM_QUESTION_STRATEGY={s.get('LLM_QUESTION_STRATEGY')}`, "
        f"`LLM_QUESTION_REPHRASING={s.get('LLM_QUESTION_REPHRASING')}`.",
        "- Підтримувані провайдери в коді: `anthropic`, `openai_compatible`, `disabled`.", "",
        "## Версії правил", "",
        f"- Промпти: SHA-256 вмісту `backend/agents/prompts.py` = `{prompt_version()}`.",
        f"- Рубрики: `fixtures/rubrics.json` sha256[:16] = `{sha(APP / 'fixtures/rubrics.json')}`, версія рубрик `v1`, джерело `CURATED_TEMPLATE`.",
        f"- Вакансії: `fixtures/vacancies.json` sha256[:16] = `{sha(APP / 'fixtures/vacancies.json')}`; "
        f"D_vga: `fixtures/vacancy_criteria.json` sha256[:16] = `{sha(APP / 'fixtures/vacancy_criteria.json')}` (правило `SYNTHETIC_RULE_V1`).",
        f"- Ранжування: `ALGORITHM_VERSION = {ALGORITHM_VERSION}` (ключ (2.15) + T_v, J_v + id); політика когорти `{POLICY_ID}`.",
        f"- Пороги τ: `{TAU_BY_LEVEL}`, джерело `{TAU_SOURCE_LEVEL_MAP}` (робоче припущення, не вимога вакансії).",
        f"- Контролер складності: `{DEFAULT_CONFIG}`.", "",
        "## Бюджет інтерв'ю", "",
        f"- Максимум тем: {MAX_TOPICS}; максимум показаних питань на тему: {MAX_SHOWN_QUESTIONS_PER_ACTION}.",
        "- Загальний бюджет питань (`total_budget`) задається в експерименті окремо й однаковий для режимів B і C; "
        "значення вказано в `experiment_manifest.json`.", "",
        "## Відмінність «запущено» і «підтримується кодом»", "",
        "| Можливість | Статус у цих експериментах |", "|---|---|",
        "| Реальна LLM (Interviewer + Evaluator) | підтримується, **не запускалась** (потрібне погодження вартості/доступу) |",
        "| Імітований Interviewer/Evaluator (`SIMULATED_STUB`) | **запущено** (див. `experiment_manifest.json`) |",
        "| Експертні мітки | відсутні; шаблони підготовлено |",
        "| PostgreSQL | Docker-стек працює; експерименти йдуть на SQLite |",
        "| Парсинг вакансій, ESCO | не реалізовано (поза межами) |",
    ]
    text = "\n".join(lines) + "\n"
    (OUT / "environment.md").write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    print(build()[:1500])
