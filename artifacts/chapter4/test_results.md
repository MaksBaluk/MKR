# Результати автоматизованих перевірок

Усі команди виконано 2026-11-18 на робочому дереві з незакомічними змінами (див. `environment.md`). Нижче лише те, що реально запускалось.

| # | Команда (каталог) | Час запуску | Результат | Обмеження |
|---|---|---|---|---|
| 1 | `uv run pytest -q` (`app/`) | 18:01 | **578 passed**, 59 warnings, 100 с | SQLite in-memory; **не PostgreSQL**; LLM підміняється заглушками тестів |
| 2 | `npm run typecheck` (`app/frontend/`) | 17:17 | без помилок (`tsc -b`) | — |
| 3 | `npm test` (`app/frontend/`) | 17:17 | **19 файлів, 155 тестів passed** (vitest) | unit-тести бібліотек UI, не браузер |
| 4 | `npm run build` (`app/frontend/`) | 17:17 | збірка успішна (`built in 1.64s`) | — |
| 5 | `npx playwright test` (`app/frontend/`) | 2026-11-18 18:22 | **7 passed** (Chromium, 1.5 с): реєстрація через форму й збереження сесії, помилка входу, відновлення інтерв'ю після перезавантаження, ізоляція користувачів, провенанс у каталозі, 375px без горизонтального скролу | йдуть проти Docker-стека `http://127.0.0.1:8080`; Evaluator недоступний, тож відповідь зберігається як `UNGRADED`; створюють акаунти `e2e-*@example.test` у dev-БД; тільки Chromium |
| 6 | 26 надійнісних тестів поіменно (`raw/reliability_tests.txt`) | 17:17 | **26 passed** | SQLite; перелік нижче |
| 7 | `uv run python -m scripts.chapter4.pg_smoke` (`app/`) | 17:20 | **8/8 PASS** (`raw/pg_smoke.json`) | жива PostgreSQL у Docker; створено 2 тестові акаунти `*@example.test` у dev-БД; Evaluator був недоступний (LLM-сервер вимкнено), тому відповідь збережена як `UNGRADED` |
| 8 | `alembic_version` у PostgreSQL | 2026-11-18 | `0014_vacancy_provenance` (`raw/postgres_migrations.txt`); у БД 229 вакансій (49 `REAL_IMPORTED`), 2371 з 2371 вимог мають D_vga/τ | міграції застосовано контейнером `migrate` |
| 9 | `uv run python -m scripts.chapter4.math_validation` (`app/`) | 2026-11-18 | **65/65 PASS** (`math_validation.csv`) | перевірка коду на ручних прикладах, не емпірична якість |
| 10 | `uv run python -m scripts.chapter4.build_all` (`app/`) | 2026-11-18 | 18 прогонів, відтворюваність `identical=true`, `rerank` без LLM збігається зі збереженим порядком | **SIMULATED**, див. `experiment_manifest.json` |

## Що саме покривають надійнісні тести (рядок 6)

| Вимога | Тест | Статус |
|---|---|---|
| Відновлення інтерв'ю | `test_interview_flow.py::test_resume_returns_open_interview_without_browser_storage` | PASSED |
| Повторний запит (ідемпотентність) | `test_interview_flow.py::test_answer_replay_same_key_returns_same_turn`, `test_cohorts_api.py::test_post_is_idempotent` | PASSED |
| Застарілий version → 409 | `test_interview_flow.py::test_stale_version_rejected` | PASSED |
| Паралельні `next-question` | `test_interview_completion.py::test_parallel_next_question_returns_the_winner_not_a_500` | PASSED |
| Тайм-аут LLM не повторюється | `test_graphs.py::test_timeout_not_retried` | PASSED |
| Rate limit: повтор після паузи / остаточна відмова | `test_graphs.py::test_rate_limited_calls_are_retried_after_a_wait`, `::test_rate_limit_that_never_clears_ends_as_a_provider_failure` | PASSED |
| Відсутня модель → відповідь збережена `UNGRADED` | `test_graphs.py::test_no_model_ungraded`, `test_interview_flow.py::test_ungraded_answer_moves_to_next_topic` | PASSED |
| Збій провайдера → без оцінок і цілей | `test_followup_flow.py::test_provider_failure_is_ungraded_without_goal`, `test_experiment_runner.py::test_llm_failure_creates_no_grades` | PASSED |
| Збереження попередніх оцінок (`null`/off-topic) | `test_audit_regressions.py` (3 інтеграційні тести) | PASSED |
| Ізоляція користувачів | `test_profiles_api.py::test_owner_isolation` | PASSED |

Не проведено: тести на PostgreSQL (весь набір SQLite), навантажувальні тести, реальні відмови провайдера в мережі, Firefox/Safari.

## Тести, додані в рамках підготовки матеріалів

- `tests/test_vacancy_import.py` (16): парсер, валідація, походження, міграція 0014.
- `tests/test_audit_regressions.py` (12), `tests/test_dvga.py` (12): виправлення аудиту (валідація Evaluator, ревізії, D_vga/τ, міграція 0013).
- `tests/test_expert_labels.py` +2: `criterion_agreement` (узгодженість двох розмітників за критеріальними оцінками).
