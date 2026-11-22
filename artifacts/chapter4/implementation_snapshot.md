# Знімок реалізації CompetenceMatch для розділу 4 (етап 1)

Дата знімка: 2026-11-19. Усі значення нижче отримано командами в цьому прогоні (фаза 1), а не з пам'яті чи старих звітів. Заморожена конфігурація в машинному вигляді: `experiment_manifest.json` → `frozen_config`.

## 1. Версія коду

| Параметр | Значення | Команда |
|---|---|---|
| Гілка | `feat/criterion-core` | `git branch --show-current` |
| Commit продуктового коду | `282f6fb2a286bdc0291bf42c4b87cf89b63d9e92` | `git rev-parse HEAD` |
| Робоче дерево на старті | чисте (0 змінених файлів) | `git status --porcelain \| wc -l` → `0` |
| Продуктовий код у фазі 1 | **не змінювався**; додано лише скрипти `app/scripts/chapter4/*`, тести `app/tests/test_chapter4_*` і артефакти | `git diff --stat 282f6fb -- app/backend app/frontend/src app/fixtures app/alembic` (порожній) |

Коміт фази 1 містить лише артефакти, скрипти й тести (див. `README.md`). Числа експериментів фази 1 відповідають продуктовому коду `282f6fb`.

## 2. Середовище

| Компонент | Версія (фактично) |
|---|---|
| ОС / CPU | macOS 27.2.1, Apple M3 Pro, 12 ядер |
| Python (локально / контейнер `api`) | 3.12.13 (uv 0.12.3) / 3.12.16 |
| FastAPI (локально / контейнер) | 0.162.5 / 0.162.6 |
| SQLAlchemy | 2.1.8 (обидва) |
| Alembic, Pydantic, psycopg | 1.20.1, 2.14.3, 3.3.9 |
| LangGraph, langchain-core, langchain-openai | 1.2.21, 1.8.0, 1.7.4 |
| pytest | 9.2.0; `hypothesis` **не** є залежністю (property-перевірки зроблено сідованими циклами) |
| Node / npm | 25.9.0 / 11.12.1 |
| React, TypeScript, Vite, Vitest, Playwright | 19.1.1, 5.9.2, 7.1.7, 3.2.4, 1.55.0 (Chromium 1187) |
| Docker | 29.3.1; стек `competencematch-{db,api,web}`; образ БД `pgvector/pgvector:pg16` |
| PostgreSQL (проєктна БД) | 16.15 (Debian 16.15-1.pgdg12+2) |

Розбіжність FastAPI 0.162.5 (локально) і 0.162.6 (образ `api`) зафіксовано; впливу на результати не виявлено, але це не одне оточення.

## 3. Бази даних і міграції

| Контекст | БД | Стан |
|---|---|---|
| `uv run pytest` | SQLite in-memory, схема `Base.metadata.create_all` (`tests/conftest.py` примусово ставить SQLite) | не є доказом PostgreSQL |
| Скрипти фази 1 (сценарії, перебори) | SQLite in-memory на кожен запуск | проєктна БД не використовується |
| PostgreSQL-інтеграція фази 1 | одноразовий контейнер `ch4-pg` (`pgvector/pgvector:pg16`, порт 55432), схема через Alembic `upgrade head` | 4 тести, див. `test_results.md` |
| Проєктна БД (Docker) | PostgreSQL 16.15, `alembic_version = 0018_assessment_no_experience` (голова; 18 файлів міграцій) | лише читання (`psql`); `docker compose up` запускає сервіси `migrate` і `seed` (ідемпотентні, версія лишилась 0018) |

Проєктна БД (читання, 2026-11-19): 229 вакансій, 63 рубрики (61 `v1` + `fastapi`/`django` `auto-1` `LLM_PROPOSED`), 2371 альтернатива вимог (усі `criteria_source = SYNTHETIC_RULE_V1`, `tau_source = WORKING_ASSUMPTION_LEVEL_MAP`, `criterion_ids` ніде не NULL і не порожній, явний `tau` у всіх 2371), 72 інтерв'ю (49 `ACTIVE`, 23 `FINISHED`), 11 рядків `seniority_assessments` (v1: 3, v2: 2, v3: 1, v4: 5). У БД є 108 тестових користувачів `e2e-*@example.test` (накопичені прогони Playwright, включно з цим).

## 4. Дані

| Набір | Кількість | Походження |
|---|---|---|
| `fixtures/vacancies.json` | 180 (по 60 на python/marketing/design) | Походження вакансій наведено за приміткою власника про дані; технічні метадані імпорту збережені в репозиторії (поля import_version, retrieved_at, source_name). |
| `fixtures/vacancies_real.json` | 49 (python 30, marketing 14, design 5; `import_version`, `retrieved_at`) | технічні метадані імпорту збережено |
| Когорта python (свіжий seed) | 90 вакансій, 904 альтернативи, sha256 `bee5974491cd5599…` | однаковий хеш із попереднім пакетом (дані не змінювались) |
| Рубрики | 61 рубрика у фікстурах (60 тематичних + `practice-backend`), 240 критеріїв, усі `v1`, `CURATED_TEMPLATE` | шаблонні, без експертної перевірки |
| Хеш знімка датасету | `f8b085258bc6de3b…` (sha256 від sha256 восьми файлів фікстур) | `experiment_manifest.json` |

**Провенанс вакансій.** Походження вакансій наведено за приміткою власника про дані; технічні метадані імпорту збережені в репозиторії (поля import_version, retrieved_at, source_name). `RequirementGroup.excerpt` дорівнює `label` у 2052 з 2056 груп (шаблон, не цитата джерела).

## 5. LLM

| Параметр | Значення |
|---|---|
| Налаштований провайдер / модель (`app/.env`, без ключа й адреси) | `openai_compatible` / `lmstudio-community/Qwen2.5-7B-Instruct-1M-GGUF` |
| Доступність кінцевої точки | недоступна (`ConnectionRefusedError`) під час фази 1 |
| Клієнт (`backend/agents/model.py:24-26`) | temperature 0.3, `max_retries=0`, timeout `LLM_TIMEOUT_SECONDS=300` |
| Anthropic-клієнт | max_tokens 1500, temperature 0.3 (не налаштований) |
| Повтор Evaluator при невалідному виході | 1 повтор, далі `UNGRADED` (`test_graphs.py::test_unknown_id_retried_once_then_ungraded`) |
| Генерація питань | `LLM_QUESTION_GENERATION=true`, `LLM_QUESTION_STRATEGY=hybrid`, `LLM_QUESTION_REPHRASING=false` |
| **Використано у фазі 1** | **жодного виклику LLM**; усі інтерв'ю — детерміновані заглушки (`SIMULATED`) |

## 6. Версії правил

| Об'єкт | Версія / значення |
|---|---|
| Промпти | `prompt_version` = sha256 `backend/agents/prompts.py` = `4a377e2a7eb4af46c43479c4adf4b8fcb07e5d11ece9101290adfc6a1f90a21e` (попередній пакет: `d1aec7a4…`, тобто **не порівнюваний** за промптами) |
| Рубрики | усі `v1` (`CURATED_TEMPLATE`); `practice-backend` `v1` |
| Політика рівня (python) | `python-backend/v4`, `WORKING_ASSUMPTION`, sha256 `25b4b16b93494df6…`; адресовані v1–v4; `MIN_CONFIRMING_TURNS = 2` для реплікованих пулів Senior (`db-operations`, `schema-migrations`); marketing/design: політики немає (`None`) |
| Контролер складності | `difficulty/v2` (`up_score .75`, `down_score .50`, `min_known_share .5`, `focus 2`, `diagnostic_floor BASIC`) |
| Оцінювання | `CONFIRMED_SCORE .75`, `MIN_COVERAGE_FOR_OVERALL .6`, τ-карта `{1: .50, 2: .75, 3: .90}` (`WORKING_ASSUMPTION_LEVEL_MAP`), ε(τ)=min(.05, τ/2) |
| Ранжування | `ALGORITHM_VERSION = rank-2.15+tv-jv/v1`; когорта `TRACK_ALL_VALID_V2` |
| Ліміти інтерв'ю | ≤10 тем, ≤5 показаних питань на тему, мінімум 2 питання на відкриту тему; `total_budget` задається в експерименті |

## 7. Наявні експериментальні модулі

`backend/experiments/{config,providers,runner,metrics,report,expert_labels}.py` (режими A/B/C, абляційні прапорці, `rerank` без LLM, метрики P@5/NDCG@10/MAE лише з експертними мітками); скрипти `scripts/{run_experiment,evaluate_experiments,seniority_reachability,seniority_realistic,seniority_scenarios}.py`; пакет `scripts/chapter4/*` (старий білд + нові модулі фази 1: `realistic_runs`, `seniority_sweep_ch4`, `seniority_scenarios_ch4`, `math_checks`, `math_validation_ch4`, `freeze_config`).

## 8. Перевірка критичних виправлень

| # | Виправлення | Стан | Доказ |
|---|---|---|---|
| 1 | Ранжування (2.15) | **Відхилення за рішенням власника, задокументоване.** `GET /profiles/{id}/results` сортує спершу за `confirmed_share` (`backend/api/profiles.py:272`, стабільне сортування поверх ключа (2.15)+T/J+id). `POST /recommendations` і експериментальний раннер (`runner._rank` → `recommendations.rank_items` → `ranking.rank`) лишаються чистим (2.15). | `mathematical_validation.csv` K01 (PASS, 800 вибірок), R01 (`DEVIATION`); `test_results_order_percent.py` (5 тестів) |
| 1a | Чи впливає на експерименти | Ні для метрик ранжування з раннера (чистий ключ). Так для всього, що зчитує порядок з екрана результатів (знімки екрана, розділ 4.5): там вакансія `Z=0` може стояти вище за `Z=2`. Окремо: `POST /recommendations` бере оцінки **усіх спроб користувача** (`latest_scores`, `recommendations.py:53`), а не однієї спроби — UI і раннер його не використовують. | код, розділ 2.2 `architecture_audit.md` |
| 2 | D_vga і τ у вимогах | Виконано: явні `criterion_ids` авторитетні, порожній набір не розширюється до всієї рубрики (`core_flow.py` `alt_criteria`), τ без мапи → `UNRESOLVED`; знімок когорти заморожує `criterion_ids/criteria_source/tau/tau_source` (`cohorts.py:36-39`). У проєктній БД усі 2371 альтернативи мають `criterion_ids` і `tau`. Обмеження: D_vga задано правилом репозиторію, τ — робоче припущення. | `test_dvga.py::test_snapshot_freezes_criteria_and_tau` PASS |
| 3 | null / off_topic не стирає прийняті бали | Виконано: `core.effective_rows` (`core.py:67-77`) бере останню ревізію з балом; історія зберігається. | `test_audit_regressions.py` (2 тести), `test_practice_criteria.py::test_null_practice_revision_does_not_erase_score`, сценарій S11 (через `core.seniority_evidence`) — PASS |
| 4 | Evaluator: належність критерію і обґрунтовані цитати | Виконано структурно (`assessment.validate_against_context`, `assessment.py:93-120`): невідомий/дубльований id, бал поза [0,1], бал без цитати, порожня цитата, невідомий turn, цитата не є дослівним підрядком відповіді; `no_experience` лише для тематичних критеріїв, бал <.25 і цитата. Обмеження: семантичну відповідність цитати критерію не перевірено (лише дослівність). | `test_audit_regressions.py::test_unknown_criterion_unknown_turn_and_foreign_quote_rejected`, `test_graphs.py::test_unknown_id_retried_once_then_ungraded` PASS |
| 5 | Версіонування рубрик | Рубрика = (action_id, version, source); `rerank` відмовляє при зміні версій рубрик (`runner.py:321-324`); рівень зберігає `rubric_versions`. | `test_experiment_runner.py::test_rerank_refuses_changed_rubric_versions` PASS |
| 6 | Ізоляція спроб | Рівень і результати профілю — з однієї спроби (`attempt_scores`, `attempt_evidence`); старт-знімок `start_desired_level/start_policy_*` (міграція 0017). Виняток: `POST /recommendations` (п. 1a). | `test_seniority_api.py::test_attempts_are_not_mixed`, `test_profiles_api.py::test_attempt_planner_ignores_other_attempt_scores` PASS |
| 7 | Провенанс вакансій | Походження вакансій наведено за приміткою власника про дані; технічні метадані імпорту збережені в репозиторії (поля import_version, retrieved_at, source_name). | код, БД |

## 9. EXPERIMENT_BLOCKER

| ID | Що | Наслідок | Статус |
|---|---|---|---|
| EB-1 | Немає незалежних експертних міток (критерії, релевантність, рівень) | P@5, NDCG@10, MAE Evaluator, accuracy/F1 рівня не обчислюються | BLOCKED (NO_GROUND_TRUTH) для етапу 7 |
| EB-2 | Жива LLM недоступна/не погоджена | Усі наскрізні числа — `SIMULATED`; якість реального Evaluator/Interviewer не виміряно | BLOCKED для real-LLM частини етапів 5–7 |
| EB-3 | Заглушка `seniority_realistic.Model` пише складність англійською («(advanced)»); з однією назвою критерію і латинською назвою інструмента частка кирилиці < 0.7 → продукт відхиляє питання (`NOT_UKRAINIAN`, `graphs.py:150`) → банкове питання без оцінки. Це артефакт стенду, не продукту. | Завищує пропуск Senior за вузьких питань; для фази 2 потрібно використовувати варіант `UaModel` або явно підписувати вплив | Не блокує фазу 1 (виміряно, див. `seniority_audit.md` §4); для порівняння режимів у фазі 2 — **блокер, якщо не врахувати** |

Продуктового блокера, який можна було б усунути крихітною безпечною зміною, не виявлено; продуктовий код не змінювався.

## 10. Заморожена конфігурація

`experiment_manifest.json` → `frozen_config`: commit `282f6fb`, датасет `f8b085258bc6de3b…`, когорти за треками, версії рубрик, `python-backend/v4` + sha256, `difficulty/v2`, `prompt_version 4a377e2a…`, ліміти, параметри LLM без секретів. Відтворення: `cd app && uv run python -m scripts.chapter4.freeze_config` (масив `runs` не перезаписується). Старий маніфест (старий код, інший `prompt_version`) збережено лише як підсумок у `superseded_previous_package`.
