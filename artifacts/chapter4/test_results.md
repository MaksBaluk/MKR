# Технічне тестування (етап 8), фаза 1

Дата: 2026-11-19. Продуктовий код: commit `282f6fb`. Машина: macOS 27.2.1, Apple M3 Pro (12 ядер); Python 3.12.13 (uv 0.12.3), Node 25.9.0, Docker 29.3.1. Реальна LLM не викликалась (налаштована кінцева точка недоступна, `ConnectionRefusedError`). Попередні значення цього файлу (старий код) замінено.

## 1. Запуски

| # | Команда (каталог) | Середовище / БД | Результат | Тривалість |
|---|---|---|---|---|
| 1 | `uv run pytest -q -p no:cacheprovider` (`app/`), до змін фази 1 | SQLite in-memory (`conftest.py`) | **781 passed**, 0 failed, 81 warnings (DeprecationWarning sqlite datetime adapter) | 154.75 с |
| 2 | те саме після додавання тестів фази 1 | SQLite | **885 passed, 4 skipped** (4 = `test_chapter4_postgres.py` без `CH4_PG_URL`), 0 failed | 169.15 с |
| 3 | `uv run pytest -q tests/test_chapter4_seniority_scenarios.py` | SQLite + API-потік із заглушкою | 17 passed | 8.2 с |
| 4 | `uv run pytest -q tests/test_chapter4_math_properties.py` | чисті функції | 87 passed (22 property + 65 контрольних прикладів) | 1.9 с |
| 5 | `CH4_PG_URL=postgresql+psycopg://postgres:***@127.0.0.1:55432/ch4 uv run pytest -q tests/test_chapter4_postgres.py` | **PostgreSQL 16 (pgvector/pgvector:pg16), одноразовий контейнер `ch4-pg`, схема Alembic `upgrade head`** | **4 passed** | 6.3 с |
| 6 | `npm run typecheck` (`app/frontend`) | TypeScript 5.9.2 | exit 0 | 2.1 с |
| 7 | `npm test` | Vitest 3.2.4 | **167 passed** (20 файлів) | 1.5 с |
| 8 | `npm run build` | Vite 7.1.7 | exit 0 (`built in 1.57s`) | 3.6 с |
| 9 | `docker compose up -d --build api web` (`app/`) | стек `competencematch` (db PostgreSQL 16.15, api, web; сервіси `migrate`, `seed` ідемпотентні) | exit 0; `GET /healthz` 200; `alembic_version` лишився `0018_assessment_no_experience` | — |
| 10 | `npx playwright test --reporter=line` (`app/frontend`) | Chromium 1187 проти nginx `127.0.0.1:8080` (Docker, PostgreSQL) | **8 passed** | 3.9 с |
| 11 | `uv run python -m scripts.seniority_realistic --noisy` | SQLite + API, `SIMULATED` | exit 0, 224 інтерв'ю | 4 хв 55 с |
| 12 | `uv run python -m scripts.chapter4.seniority_sweep_ch4` / `--stub-ua` | SQLite + API, `SIMULATED` | exit 0, 320 / 224 інтерв'ю | 7 хв 16 с / 4 хв 38 с |

Повний набір pytest на PostgreSQL **NOT_RUN**: `tests/conftest.py` жорстко задає SQLite, режиму PostgreSQL немає. На PostgreSQL виконано лише 4 інтеграційні тести (рядок 5) і Playwright проти Docker-стека (рядок 10). SQLite-результати не подаються як доказ PostgreSQL. Старий `scripts/chapter4/pg_smoke.py` не запускався: він створює користувачів у проєктній БД; ті самі перевірки виконано на одноразовій БД (рядок 5).

Побічні ефекти: Playwright створює користувачів `e2e-*@example.test` у БД Docker-стека (зараз їх 108, накопичено багатьма прогонами). Контейнер `ch4-pg` зупинено й видалено (`--rm`).

## 2. Окремі перевірки

| Перевірка | Тести (усі PASS, команда: `uv run pytest -q <id>`; 36 тестів, 12.3 с) | БД |
|---|---|---|
| Повторні HTTP-запити (ідемпотентність) | `test_interview_flow.py::test_answer_replay_same_key_returns_same_turn`, `test_cohorts_api.py::test_post_is_idempotent`, `test_interview_flow.py::test_pending_question_not_regenerated`; `test_chapter4_postgres.py::test_idempotent_replay_stale_version_and_isolation_on_postgres` (повтор відповіді з тим самим ключем, 409 на застарілу версію) | SQLite; **PostgreSQL** |
| Відновлення інтерв'ю | `test_interview_flow.py::test_resume_returns_open_interview_without_browser_storage`, `test_difficulty_flow.py::test_second_question_replays_controller_state`; Playwright `interview.spec.ts:5` (відповідь збережено, відновлення після перезавантаження); PG-тест (pending_turn із сервера) | SQLite; PostgreSQL |
| Помилки LLM, тайм-аути | `test_graphs.py::{test_unknown_id_retried_once_then_ungraded, test_timeout_not_retried, test_llm_exception_falls_back_to_bank, test_a_stalled_provider_hits_a_hard_deadline_in_ask_and_answer, test_rate_limit_that_never_clears_ends_as_a_provider_failure}`, `test_followup_flow.py::test_provider_failure_is_ungraded_without_goal` | SQLite (провайдер — фейк) |
| Збереження балів | `test_audit_regressions.py::{test_off_topic_and_null_never_erase_confirmed_scores_and_history_is_kept, test_partial_null_in_new_revision_keeps_earlier_score}`, `test_practice_criteria.py::test_null_practice_revision_does_not_erase_score`, `test_seniority_api.py::test_competency_evidence_keeps_effective_rows_and_all_turns`; сценарій S11 | SQLite |
| Цілісність історичних результатів | `test_profiles_api.py::{test_second_attempt_does_not_change_results_until_finished, test_archive_hides_blocks_attempts_keeps_history}`, `test_seniority_api.py::{test_v1_row_of_old_attempt_is_kept_and_rendered, test_v2_row_of_old_attempt_is_kept_and_rendered_with_its_own_pools}`, `test_dvga.py::test_snapshot_freezes_criteria_and_tau`; PG: рядок рівня один і незмінний після повторного читання | SQLite; PostgreSQL |
| Ізоляція користувачів | `test_profiles_api.py::test_owner_isolation`, `test_seniority_api.py::test_owner_isolation_level_endpoint`; Playwright `interview.spec.ts:33`; PG-тест (403/404 для чужого інтерв'ю й результатів) | SQLite; PostgreSQL |
| Ізоляція спроб | `test_seniority_api.py::test_attempts_are_not_mixed`, `test_profiles_api.py::test_attempt_planner_ignores_other_attempt_scores`. Виняток у коді: `POST /recommendations` змішує спроби (`architecture_audit.md` A-2; тесту на це немає, UI і раннер його не використовують) | SQLite |
| Версіонування SeniorityPolicy | `test_seniority_api.py::{test_policy_version_change_does_not_rewrite_history, test_attempt_started_under_older_policy_is_finalized_under_it, test_desired_level_is_captured_at_attempt_start}`; PG: `finalize_level(v3)` додає рядок v3, рядок v4 не змінюється | SQLite; PostgreSQL |
| Зміна рубрики | `test_experiment_runner.py::test_rerank_refuses_changed_rubric_versions`, `test_experiment_report.py::test_rubric_version_mismatch_sentence_and_missing_version_kept` | SQLite |
| Відсутність хибного підвищення | `test_seniority_ws1.py` (7 тестів), сценарії S01, S05, S08, S09a; шумовий перебір: хибний Senior 0/112, хибний Middle+ 0/56 (обидва варіанти стенду) | SQLite; `SIMULATED` |
| Міграції на PostgreSQL | `test_chapter4_postgres.py::test_alembic_head_on_postgres_and_one_step_reversible` (head = 0018, `downgrade -1` і `upgrade head`) | PostgreSQL |

Нових тестів для прогалин написано: `test_chapter4_postgres.py` (4; PostgreSQL), `test_chapter4_seniority_scenarios.py` (17), `test_chapter4_math_properties.py` (87).

## 3. Збої

Збоїв у жодному запуску немає. Попередження: 81 `DeprecationWarning` (sqlite datetime adapter, Python 3.12), 3 `DeprecationWarning` Alembic (`path_separator`). Під час інтерв'ю зі заглушкою в журналі є рядки `interviewer question rejected … kind=NOT_UKRAINIAN` — це очікувана поведінка продукту на артефакт заглушки (див. `seniority_audit.md` §4), а не збій тесту.

## Фаза 2 (2026-11-23)

| Команда | Середовище | Результат | Тривалість |
|---|---|---|---|
| `cd app && uv run pytest -q` | чистий git worktree на commit `414404e` (продуктовий код = `282f6fb`), SQLite, локальний `app/.env` | 892 passed, 4 skipped | 169 с |
| `uv run pytest -q tests/test_chapter4_modes.py` | те саме | 7 passed (детермінованість seed, однакові умови режимів, бюджети, сітка, статистика, дослідницький планувальник) | ≈ 4 с |
| `uv run python -m scripts.chapter4.build_all --workers 6` | чистий worktree, усі виходи фази 2 попередньо видалено | 0 помилок; 1350 SIMULATED прогонів; хеш вмісту `eca6a8386e6af0ac` = закоміченому | 6 хв 23 с |

Основне робоче дерево на момент фази 2 містило незакомічені зміни продуктового коду з іншої сесії (`agents/graphs.py`, frontend); вони не входять у заморожену конфігурацію, тому тести й експерименти запускалися в окремому чистому worktree.
