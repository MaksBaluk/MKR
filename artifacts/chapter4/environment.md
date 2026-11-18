# Експериментальне середовище (CompetenceMatch, розділ 4)

Згенеровано: `2026-11-18 18:32:52 +0100` скриптом `app/scripts/chapter4/environment.py`.

## Версія коду

- Commit SHA: `1ed85b6dea5a4bd532182d630e06ef23e4d84955` (гілка `feat/criterion-core`).
- Робоче дерево: **НЕ чисте**. Змінені відстежувані файли: 28; невідстежувані: 17. SHA-256 (перші 16 символів) `git diff HEAD`: `37d7e64d7263cc39`.
- Невідстежувані файли (частина доказів і виправлень аудиту ще не закомічена):
  - `app/alembic/versions/0013_requirement_criteria_tau.py`
  - `app/alembic/versions/0014_vacancy_provenance.py`
  - `app/backend/domain/vacancy_criteria.py`
  - `app/backend/domain/vacancy_import.py`
  - `app/fixtures/vacancies_real.json`
  - `app/fixtures/vacancies_real_import_report.json`
  - `app/fixtures/vacancy_criteria.json`
  - `app/frontend/e2e/`
  - `app/scripts/chapter4/`
  - `app/scripts/derive_vacancy_criteria.py`
  - `app/scripts/import_djinni.py`
  - `app/scripts/rewrite_real_descriptions.py`
  - `app/tests/test_audit_regressions.py`
  - `app/tests/test_dvga.py`
  - `app/tests/test_vacancy_import.py`
  - `artifacts/`
  - `docs/audit/2026-11-17-independent-audit.md`

Результати нижче відповідають коду `HEAD` **плюс** незакомічені зміни, ідентифіковані хешем diff. Для відтворюваності закомітьте зміни й повторіть `python -m scripts.chapter4.build_all`.

## Платформа

- ОС: `macOS-27.2.1-arm64-arm-64bit`; архітектура `arm64`.
- Процесор: `Apple M3 Pro`; ядер: `12`; RAM: `18.0` ГБ.
- Python: `3.12.13` (`uv 0.12.3 (Homebrew 2026-08-07 aarch64-apple-darwin)`).
- Node: `v25.9.0`, npm: `11.12.1`.

## Залежності

Backend (`uv pip list`):
- alembic 1.20.1
- fastapi 0.162.5
- httpx 0.28.1
- langchain-core 1.8.0
- langchain-openai 1.7.4
- langgraph 1.2.21
- psycopg 3.3.9
- pydantic 2.14.3
- pytest 9.2.0
- sqlalchemy 2.1.8
- uvicorn 0.54.0

Frontend (`app/frontend/package.json`, задані діапазони версій):
- react 19.1.1
- react-dom 19.1.1
- vite 7.1.7
- typescript 5.9.2
- vitest ^3.2.4
- @playwright/test ^1.55.0
- tailwindcss ^4.3.5

## Бази даних

| Контекст | Що фактично використано |
|---|---|
| Автотести backend | SQLite (in-memory, `StaticPool`), схема з `Base.metadata.create_all` |
| Продуктовий стек (Docker Compose) | PostgreSQL: `postgres (PostgreSQL) 16.15 (Debian 16.15-1.pgdg12+2)`; міграції Alembic до голови `0014_vacancy_provenance (head)` |
| Експериментальні прогони цього пакета | окрема SQLite-БД у тимчасовому каталозі (ніколи не продуктова) |
| pgvector / HNSW | схема підготовлена, **не заповнена і не використовується** в експериментах |

## LLM

**Фактично в експериментах цього пакета: детермінована імітація (`SIMULATED_STUB`), реальна LLM не викликалась.** Нижче — те, що налаштовано в `app/.env` і підтримується кодом, але в цих прогонах НЕ використовувалось.

- Налаштований провайдер: `openai_compatible`, модель: `google/gemma-4-12b-qat` (локальний OpenAI-сумісний сервер; адреса й ключ у звіт не копіюються).
- Параметри клієнта (`backend/agents/model.py`): temperature=0.3, max_retries=0, timeout=300 с, ліміт вихідних токенів не задано (використовується стандарт сервера).
- `LLM_QUESTION_GENERATION=true`, `LLM_QUESTION_STRATEGY=hybrid`, `LLM_QUESTION_REPHRASING=false`.
- Підтримувані провайдери в коді: `anthropic`, `openai_compatible`, `disabled`.

## Версії правил

- Промпти: SHA-256 вмісту `backend/agents/prompts.py` = `d1aec7a48cbcd16133dd55a1ee0f34e10021cc3b0e106e569d8c577971be3870`.
- Рубрики: `fixtures/rubrics.json` sha256[:16] = `a728ea45b2475704`, версія рубрик `v1`, джерело `CURATED_TEMPLATE`.
- Вакансії: `fixtures/vacancies.json` sha256[:16] = `9bc11fcde8b1d857`; D_vga: `fixtures/vacancy_criteria.json` sha256[:16] = `9aa9e1fdefb70d92` (правило `SYNTHETIC_RULE_V1`).
- Ранжування: `ALGORITHM_VERSION = rank-2.15+tv-jv/v1` (ключ (2.15) + T_v, J_v + id); політика когорти `TRACK_ALL_VALID_V2`.
- Пороги τ: `{1: 0.5, 2: 0.75, 3: 0.9}`, джерело `WORKING_ASSUMPTION_LEVEL_MAP` (робоче припущення, не вимога вакансії).
- Контролер складності: `DifficultyConfig(up_score=0.75, down_score=0.5, min_known_share=0.5, diagnostic_floor=<Difficulty.BASIC: 'BASIC'>)`.

## Бюджет інтерв'ю

- Максимум тем: 10; максимум показаних питань на тему: 5.
- Загальний бюджет питань (`total_budget`) задається в експерименті окремо й однаковий для режимів B і C; значення вказано в `experiment_manifest.json`.

## Відмінність «запущено» і «підтримується кодом»

| Можливість | Статус у цих експериментах |
|---|---|
| Реальна LLM (Interviewer + Evaluator) | підтримується, **не запускалась** (потрібне погодження вартості/доступу) |
| Імітований Interviewer/Evaluator (`SIMULATED_STUB`) | **запущено** (див. `experiment_manifest.json`) |
| Експертні мітки | відсутні; шаблони підготовлено |
| PostgreSQL | Docker-стек працює; експерименти йдуть на SQLite |
| Парсинг вакансій, ESCO | не реалізовано (поза межами) |
