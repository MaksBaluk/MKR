# Таблиця 4.7. Технічне тестування (з test_results.md) і E6

| Розділ test_results.md | Команда | Середовище | Результат | Тривалість |
|---|---|---|---|---|
| 1. Запуски | `uv run pytest -q -p no:cacheprovider` (`app/`), до змін фази 1 | SQLite in-memory (`conftest.py`) | **781 passed**, 0 failed, 81 warnings (DeprecationWarning sqlite datetime adapter) | 154.75 с |
| 1. Запуски | те саме після додавання тестів фази 1 | SQLite | **885 passed, 4 skipped** (4 = `test_chapter4_postgres.py` без `CH4_PG_URL`), 0 failed | 169.15 с |
| 1. Запуски | `uv run pytest -q tests/test_chapter4_seniority_scenarios.py` | SQLite + API-потік із заглушкою | 17 passed | 8.2 с |
| 1. Запуски | `uv run pytest -q tests/test_chapter4_math_properties.py` | чисті функції | 87 passed (22 property + 65 контрольних прикладів) | 1.9 с |
| 1. Запуски | `CH4_PG_URL=postgresql+psycopg://postgres:***@127.0.0.1:55432/ch4 uv run pytest -q tests/test_chapter4_postgres.py` | **PostgreSQL 16 (pgvector/pgvector:pg16), одноразовий контейнер `ch4-pg`, схема Alembic `upgrade head`** | **4 passed** | 6.3 с |
| 1. Запуски | `npm run typecheck` (`app/frontend`) | TypeScript 5.9.2 | exit 0 | 2.1 с |
| 1. Запуски | `npm test` | Vitest 3.2.4 | **167 passed** (20 файлів) | 1.5 с |
| 1. Запуски | `npm run build` | Vite 7.1.7 | exit 0 (`built in 1.57s`) | 3.6 с |
| 1. Запуски | `docker compose up -d --build api web` (`app/`) | стек `competencematch` (db PostgreSQL 16.15, api, web; сервіси `migrate`, `seed` ідемпотентні) | exit 0; `GET /healthz` 200; `alembic_version` лишився `0018_assessment_no_experience` | — |
| 1. Запуски | `npx playwright test --reporter=line` (`app/frontend`) | Chromium 1187 проти nginx `127.0.0.1:8080` (Docker, PostgreSQL) | **8 passed** | 3.9 с |
| 1. Запуски | `uv run python -m scripts.seniority_realistic --noisy` | SQLite + API, `SIMULATED` | exit 0, 224 інтерв'ю | 4 хв 55 с |
| 1. Запуски | `uv run python -m scripts.chapter4.seniority_sweep_ch4` / `--stub-ua` | SQLite + API, `SIMULATED` | exit 0, 320 / 224 інтерв'ю | 7 хв 16 с / 4 хв 38 с |
| Фаза 2 (2026-11-23) | `cd app && uv run pytest -q` | чистий git worktree на commit `414404e` (продуктовий код = `282f6fb`), SQLite, локальний `app/.env` | 892 passed, 4 skipped | 169 с |
| Фаза 2 (2026-11-23) | `uv run pytest -q tests/test_chapter4_modes.py` | те саме | 7 passed (детермінованість seed, однакові умови режимів, бюджети, сітка, статистика, дослідницький планувальник) | ≈ 4 с |
| Фаза 2 (2026-11-23) | `uv run python -m scripts.chapter4.build_all --workers 6` | чистий worktree, усі виходи фази 2 попередньо видалено | 0 помилок; 1350 SIMULATED прогонів; хеш вмісту `eca6a8386e6af0ac` = закоміченому | 6 хв 23 с |
| Фаза 3 (2026-11-23) | `cd app && uv run pytest -q -p no:cacheprovider` | чистий git worktree на commit `a6c9398` + незакомічені файли фази 3 лише в `app/scripts/chapter4`, `app/tests/test_chapter4_*`, `artifacts/chapter4` (продуктовий код = `282f6fb`), SQLite, локальний `app/.env` | 899 passed, 4 skipped (4 = `test_chapter4_postgres.py` без `CH4_PG_URL`), 0 failed, 81 warnings | 162.69 с |
| Фаза 3 (2026-11-23) | `uv run pytest -q tests/test_chapter4_annotation_merge.py tests/test_chapter4_final_report.py` | те саме | 7 passed | 1.0 с |
| Фаза 3 (2026-11-23) | `uv run python -m scripts.chapter4.timing_e6` | те саме, Apple M3 Pro | E6 записано в `raw/timing_e6.json` (200 вимірів × 3 кандидати на компонент) | ≈ 19 с |
| Фаза 3 (2026-11-23) | `uv run python -m scripts.chapter4.build_all --phase3-only` (двічі) | те саме | 0 помилок; SHA-256 дерева `artifacts/chapter4` однаковий після двох запусків | ≈ 13–15 с |
| — | повний pytest на PostgreSQL | — | NOT_RUN: tests/conftest.py задає SQLite | — |
| — | реальна LLM (локальна / продакшн) | — | NOT_RUN: локальна кінцева точка недоступна; платні виклики не дозволено | — |
| E6 (raw/timing_e6.json) | scripts.chapter4.timing_e6: matching | Apple M3 Pro, Python 3.12.13, SQLite in-memory | медіана 3.716 мс, p95 3.860 мс (N=600) | — |
| E6 (raw/timing_e6.json) | scripts.chapter4.timing_e6: ranking | Apple M3 Pro, Python 3.12.13, SQLite in-memory | медіана 0.014 мс, p95 0.015 мс (N=600) | — |
| E6 (raw/timing_e6.json) | scripts.chapter4.timing_e6: results | Apple M3 Pro, Python 3.12.13, SQLite in-memory | медіана 12.836 мс, p95 13.733 мс (N=600) | — |
| E6 (raw/timing_e6.json) | scripts.chapter4.timing_e6: estimator | Apple M3 Pro, Python 3.12.13, SQLite in-memory | медіана 0.119 мс, p95 0.125 мс (N=600) | — |
| E6 (raw/timing_e6.json) | scripts.chapter4.timing_e6: estimator_with_db | Apple M3 Pro, Python 3.12.13, SQLite in-memory | медіана 3.155 мс, p95 3.398 мс (N=600) | — |
| E6 (raw/timing_e6.json) | scripts.chapter4.timing_e6: market | Apple M3 Pro, Python 3.12.13, SQLite in-memory | медіана 0.209 мс, p95 0.220 мс (N=600) | — |

Тривалості pytest не є вимірами продуктивності. E6 — окремі повторні виміри детермінованих компонентів.
