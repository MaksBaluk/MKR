# Звіт: оцінений професійний рівень (SeniorityEstimator)

Гілка `feat/criterion-core`, коміти від `1e8c250` до фінального коміту задачі 7 (2026-11-18). Дизайн: `docs/superpowers/specs/2026-11-18-seniority-estimator-design.md`. План: `docs/superpowers/plans/2026-11-18-seniority-estimator.md`. Правила: `docs/tasks/MATH_SPEC.md` §3e.

## Оновлення 2026-11-19: політика `python-backend/v2` (§v2)

Поточна політика напряму python тепер `python-backend/v2`. Політика v1 лишається доступною за версією. Збережені рядки v1 не переписуються. Правила описано в `docs/tasks/MATH_SPEC.md` §3e (пункти «Policy v2», «v2 thresholds», «Versions and rows»). Q_t, вибір тем, бюджети, ранжування (2.15) та оцінки `E_c` не змінювалися.

### Вимірювання: які теми вибирає Q_t

Вибір тем виміряно на повній системній добірці (90 засіяних вакансій python) через реальний API з симульованим Evaluator. Було 17 шаблонів відповідей:
- рівні оцінки 0.9, 0.75, 0.6, 0.4 і 0.2;
- 8 псевдовипадкових наборів оцінок у діапазоні 0.3–1.0;
- 4 такі самі набори, де частина оцінок дорівнює null.

Кожен шаблон запускався з бажаним рівнем junior, middle і senior, тобто всього 51 співбесіда. Скрипт лежить поза репозиторієм, бо це разове вимірювання. Сценарії нижче відтворюють його ключові випадки.

| Тема | Частка співбесід, де тему вибрано |
|---|---|
| python-core, kafka, fastapi, ci-cd, sql, aws, docker, postgresql | 51/51 |
| django | 42/51 |
| git | 24/51 |
| redis | 24/51 |
| rest-api | 12/51 (лише за сильних відповідей) |
| sqlalchemy, celery, pytest, async-python, observability, app-security, kubernetes, linux | 0/51 |

- Бажаний рівень на вибір тем не вплинув: послідовності для junior, middle і senior збігаються.
- Порядок тем за ринковою вагою (`GET /cohorts/{id}/market`) такий: python-core, fastapi, kafka, django, docker, redis, aws, pytest, sql, postgresql, ci-cd, celery, rest-api, git, sqlalchemy, observability, async-python, app-security, kubernetes, linux.
- pytest стоїть восьмим за ринком, але Q_t його не вибирає. Q_t максимізує приріст покриття груп вимог, а групи з pytest уже закриті іншими альтернативами.
- Наслідок для v1: критичні множини Middle і Senior лежать переважно в темах, які Q_t не вибирає. Обмеження I-1 підтверджено.

### Пули v2

Критична одиниця рівня — це пул еквівалентних критеріїв, тобто одна професійна здатність, яку можна показати різними інструментами. Пул підтверджено, якщо його підтверджує будь-який член. Компенсації між пулами немає. Точні правила наведено в MATH_SPEC §3e.

Усі id існують у `fixtures/rubrics.json` або `fixtures/practice_rubrics.json`; це перевіряє тест `test_v2_pools_use_existing_ids_titles_and_hierarchy`. Нових критеріїв немає: усі взято з наявних рубрик.

- Повторно використано всі 34 критичні id v1. Лише `ci-cd.pipeline` змінив рівень: з Middle він перейшов на Junior, у пул «Збирання й запуск сервісу».
- У політику рівнів додано 37 id, які у v1 не були критичними:
  - app-security.secrets;
  - async-python.eventloop, .testing;
  - aws.cost, .deploy, .iam, .services;
  - celery.design, .retries;
  - ci-cd.deploy;
  - django.architecture, .migrations, .orm, .permissions;
  - docker.compose, .images, .runtime, .security;
  - fastapi.async, .dependencies, .testing, .validation;
  - kafka.consumers, .errors, .schemas, .semantics;
  - kubernetes.security, .troubleshooting, .workloads;
  - linux.diagnostics;
  - observability.tracing;
  - redis.caching;
  - rest-api.versioning;
  - sql.aggregation, .performance;
  - sqlalchemy.loading, .models.

| Рівень (τ, мінімум оцінених / підтверджених пулів / компетентностей) | Пули (назва: члени) |
|---|---|
| Junior (0.50; 5 / 5 / 3 з 6) | Базове володіння Python: python-core.idioms, .errors · Запити до реляційних даних: sql.joins, .correctness, .aggregation · Контракт і валідація API: rest-api.contract, fastapi.validation · Перевірка коректності коду: python-core.testing, pytest.structure · Збирання й запуск сервісу: docker.images, docker.compose, ci-cd.pipeline, git.branching · Самостійність (практика) |
| Middle (0.70; 10 / 8 / 5 з 13) | Типізація та контракти коду: python-core.typing · Ефективність запитів: postgresql.indexes, sql.performance, sqlalchemy.loading, django.orm · Транзакції та узгодженість: postgresql.transactions, sqlalchemy.session · Проєктування схеми: postgresql.schema, sqlalchemy.models · Структура сервісу та API: fastapi.dependencies, rest-api.pagination, django.architecture · Асинхронна робота без блокувань: fastapi.async, async-python.blocking, .eventloop · Ізольовані тести: pytest.isolation, fastapi.testing, async-python.testing · Конфігурація та розгортання: docker.runtime, ci-cd.deploy, aws.deploy, kubernetes.workloads · Обробка подій і фонових задач: kafka.consumers, celery.design, celery.retries, redis.caching · Безпека вхідних даних і секретів: app-security.input, .secrets, docker.security · практика: самостійність, обґрунтування, діагностика |
| Senior (0.75; 10 / 10 / 4 з 13) | Експлуатація й безпечні зміни БД: postgresql.operations, .migrations, django.migrations · Конкурентний доступ і паралельність: sqlalchemy.concurrency, async-python.concurrency · Надійна доставка повідомлень і задач: kafka.semantics, kafka.errors, celery.idempotency, redis.reliability · Безпечні релізи та відкат: ci-cd.safety · Безпека доступу та авторизація: app-security.authz, rest-api.security, aws.iam, django.permissions, kubernetes.security · Розслідування інцидентів: observability.incidents, .tracing, linux.diagnostics, kubernetes.troubleshooting · Вибір інфраструктури з урахуванням вартості й надійності: aws.services, aws.cost · Сумісність контрактів під час змін: rest-api.versioning, kafka.schemas · практика: компроміси, невизначеність, відповідальність, діагностика, обґрунтування |

**Як обрано пороги.** Кожен поріг дорівнює `⌈частка × кількість пулів⌉`. Частки Junior узято з v1 (0.75 / 0.75). Частки Middle (0.70 / 0.60) і Senior (0.75 / 0.70) знижено, як пропонував варіант 2 рев'ю. Мінімум компетентностей Senior знижено з 6 до 4: серед тем, які Q_t вибирає завжди, пули Senior мають лише postgresql, kafka, ci-cd і aws.

Вимірювання верхньої межі: сильні оцінки 0.9 мають усі критерії перших k вибраних тем і вся практика. Результати таблиці отримано скриптом поза репозиторієм; тест `test_v2_middle_reachable_with_market_topics_only` перевіряє випадок «8 тем».

| Покриття | v1 | v2 |
|---|---|---|
| перші 6 тем, усі критерії | UNKNOWN (Junior 6/9 < 0.75) | MIDDLE |
| перші 8 тем, усі критерії | UNKNOWN | SENIOR. Виняток — набір без postgresql і django (там rest-api): MIDDLE, бо пул «Експлуатація й безпечні зміни БД» не оцінено |
| 10 тем, усі критерії | UNKNOWN або JUNIOR | SENIOR |

Реальний Evaluator не оцінює всі критерії теми з однієї відповіді. Тому окремо перевірено часткове покриття: перші 10 тем із S2-product (з django і redis), оцінено 1–4 перші критерії кожної теми.
- Middle з усіма 4 критеріями на тему потребує 5 тем, якщо підтверджено всі 6 критеріїв практики, і 7 тем за 3 критеріїв практики.
- Middle з 3 критеріями на тему потребує 8 тем.
- Із 2 критеріями на тему навіть 10 тем дають лише JUNIOR.
- Senior потребує ≥8 тем із 4 критеріями і всієї практики Senior, або 10 тем із 3 критеріями і всієї практики.

Отже, Middle досяжний за 7–8 релевантних тем із реалістичним частковим оцінюванням, але не тривіально. Нижня межа в 5 тем вимагає підтвердити всю практику. Senior досяжний лише з майже повним покриттям і сильною практикою.

### Сценарії v2 (SIMULATED, реальні прогони)

Команда: `cd app && uv run python scripts/seniority_scenarios.py`. Усі сценарії використовують повну системну добірку: 90 вакансій, без `SCENARIO_SUB_COHORT`. Evaluator-заглушка оцінює кожен критерій теми з прихованої «істини» і цитує відповідь. Тому P1 і P2 показують верхню межу, а не якість оцінювання.

| Сценарій | Відповіді | Питань / тем | Теми (порядок Q_t) | Отримано |
|---|---|---|---|---|
| P1 | усе 0.9 | 10 / 10 | python-core, kafka, fastapi, ci-cd, sql, aws, docker, rest-api, postgresql, git | SENIOR, ASSESSED: Junior 6/6, Middle 13/13, Senior 11/13 оцінено й підтверджено; не перевірено: «Конкурентний доступ і паралельність», «Розслідування інцидентів у продакшені» |
| P2 | Junior і Middle 0.9, критерії лише Senior 0.72, практика Senior без доказів; бажаний Senior | 10 / 10 | python-core, kafka, fastapi, ci-cd, aws, sql, docker, git, redis, postgresql | MIDDLE, ASSESSED: Senior UNVERIFIED (8/13 оцінено, 2 підтверджено, 6 UNRESOLVED), прогалин 0 |
| P3 (контроль) | усе 0.3 | 20 / 10 | python-core, kafka, fastapi, django, sql, aws, ci-cd, postgresql, docker, redis | UNKNOWN, GAPS_AT_JUNIOR: усі 6 пулів Junior мають статус GAP |
| P4 | критерії Junior і перших 5 пулів Middle 0.9, решта без доказів | 27 / 10 | python-core, kafka, fastapi, ci-cd, aws, django, sql, docker, redis, git | JUNIOR, ASSESSED: Middle UNVERIFIED (4/13 оцінено, прогалин 0) |
| S3 | усе 0.95, бюджет 3 питання | 3 / 3 | python-core, kafka, fastapi | UNKNOWN, INSUFFICIENT_DATA: Junior 4/6 |

- Пояснення P2: «Підтверджено Middle за перевіреними критеріями. Для висновку про Senior недостатньо даних.»
- Пояснення P4: «Підтверджено Junior за перевіреними критеріями. Для висновку про Middle недостатньо даних.»
- S3 показує, як працює поріг. Із 3 тем Middle має 8 підтверджених пулів, тобто мінімум `K^min` виконано. Але Middle блокують «оцінено 8 < 10» і «компетентностей 3 < 5», а Junior має лише 4/6.

Сценарії S1, S2 і S2-product на `SCENARIO_SUB_COHORT` прибрано. Вони показували досяжність рівнів для v1 лише на звуженій добірці. Із v2 звужена добірка не потрібна. Їхні результати для v1 збережено в таблиці «Три сценарії» нижче як історичні.

### Перевірки (2026-11-19, реальні команди)

| Команда | Результат |
|---|---|
| `cd app && uv run pytest -q` | `687 passed, 65 warnings in 139.60s` |
| `cd app && uv run pytest -q tests/test_seniority_policy_v2.py` | `15 passed` (зокрема золотий тест v1: 91 випадок, JSON байт у байт) |
| `cd app && uv run pytest -q tests/test_seniority_scenarios.py` | `11 passed in 2.66s` |
| `cd app/frontend && npm run typecheck` | код 0 |
| `cd app/frontend && npm test` | `Test Files 20 passed (20)`, `Tests 163 passed (163)` |
| `cd app/frontend && npm run build` | `✓ built in 1.86s` |
| `cd app && docker compose up -d --build api web` | api `Healthy`, web запущено |
| `cd app/frontend && npx playwright test` | `8 passed (3.9s)`; `level.spec.ts` перевіряє v2 і назву непокритої здатності українською |
| PostgreSQL у Docker | рядки v1 (3) залишились, новий рядок v2 (1); `level_for_attempt` віддає для рядків v1 версію v1, для v2 — v2; міграція `0016`, схема не змінювалась |

Мутаційна перевірка:
- правило «пул підтверджено, лише коли немає прогалин» дало `2 failed`;
- правило «прогалина навіть за наявності нерозв'язаного члена» дало `1 failed`;
- після відновлення коду: `15 passed`.

Не запускалось:
- реальна LLM: оцінки рівня v2, практику та часткове оцінювання реальною моделлю не перевірено;
- експертна валідація пулів і порогів;
- Firefox і Safari.

### Обмеження v2

- Пули, пороги й мінімуми компетентностей є робочим припущенням автора (WORKING_ASSUMPTION). Експертної валідації немає. Рубрики є шаблонами CURATED_TEMPLATE.
- Рівень Senior сильно залежить від практики: це 5 з 13 пулів Senior. Серед тем, які Q_t вибирає, непрактичних пулів Senior може бути оцінено щонайбільше 6, тож мінімум 10 потребує ≥4 підтверджених пулів практики. Практику реальна модель не оцінювала. Крім того, практика агрегується максимумом між темами, тобто з оптимістичним зміщенням.
- Два пули Senior на повній добірці python ніколи не оцінюються, бо Q_t не вибирає sqlalchemy, async-python, observability, linux і kubernetes.
- Еквівалентність членів пулу — це судження автора. Наприклад, сильна відповідь про `aws.deploy` підтверджує «Конфігурацію та розгортання» так само, як `docker.runtime`.
- Сценарії P1 і P2 є верхньою межею: заглушка оцінює всі критерії теми з однієї відповіді.

## Що змінено

- **Домен:**
  - `app/backend/domain/seniority_policy.py` — політика `python-backend/v1`, WORKING_ASSUMPTION.
  - `app/backend/domain/seniority.py` — чистий детермінований оцінювач.
  - `app/backend/domain/level_probe.py` — переставляє непокриті критерії поточної теми й додає прогалини практики.
  - `app/backend/domain/assessment.py` — поле `practice` і його валідація.
- **Агенти:** `app/backend/agents/prompts.py` і `graphs.py`.
  - Evaluator оцінює практику.
  - Interviewer отримує `practice_gaps`; ціль follow-up завжди має пріоритет.
  - Питання, що повторює id критерію, відхиляється.
- **API:**
  - `app/backend/api/level.py` — `finalize_level`, ледаче обчислення, `GET /interviews/{id}/level`, `GET /profiles/{id}/level`.
  - `core.py` — `seniority_evidence`, збереження практики, хук на завершення.
  - `profiles.py` — блок `level` і поле `section` у результатах.
  - `recommendations.py` і `experiments/runner.py` — критерії практики відфільтровано.
- **Дані:**
  - `app/fixtures/practice_rubrics.json` — 6 критеріїв, шаблон CURATED_TEMPLATE.
  - Міграція `app/alembic/versions/0016_seniority_assessments.py` — таблиця, унікальність (спроба, версія), частковий унікальний індекс для рядків без політики.
- **Інтерфейс:**
  - `LevelSummary.tsx` і `lib/levelView.ts`.
  - Розділи вакансій у `ResultsScreen.tsx`.
  - Під заголовком списку додано пояснення: номер — це місце в загальному списку за відсотком, а розділи лише групують.
- **Задача 7:**
  - `app/scripts/seniority_scenarios.py` і `app/tests/test_seniority_scenarios.py`.
  - Тести `test_middle_confirmed_even_if_desired_junior_or_senior`, `test_self_rating_and_years_do_not_raise_level` і `test_level_independent_of_partial_topic_coverage`.
  - У попередження про збій збереження рівня додано traceback (`exc_info=True`, перевірка через caplog).

## Перевірки (реальні команди й виводи, 2026-11-18)

| Команда | Результат |
|---|---|
| `cd app && uv run pytest -q` | `667 passed, 65 warnings in 123.61s`. Перший прогін дав `1 failed, 666 passed`: alembic `fileConfig` у тестах міграцій вимикає логер, і caplog нічого не отримував. Тест тепер вмикає логер явно |
| `cd app && uv run pytest -q tests/test_seniority_scenarios.py` | `9 passed in 1.36s` |
| `cd app/frontend && npm run typecheck` | код 0 |
| `cd app/frontend && npm test` | `Test Files 20 passed (20)`, `Tests 161 passed (161)` |
| `cd app/frontend && npm run build` | `✓ built in 1.61s` |
| `cd app && docker compose up -d --build` | код 0; migrate і seed завершились, api `healthy`, web запущено |
| `cd app/frontend && npx playwright test` (Docker-стек) | `8 passed (2.8s)`, включно з `e2e/level.spec.ts` |
| `docker compose exec -T db psql ... -c "select version_num from alembic_version"` | `0016_seniority_assessments` |

Мутаційна перевірка сценарних тестів. Ланцюг рівнів тимчасово змінено: замість «SUPPORTED» достатньо «не GAP». Результат: `4 failed, 5 passed`. Після відновлення коду: `9 passed`.

Тест логування спершу був червоним без `exc_info` (`1 failed`), після виправлення став зеленим.

Нові тести властивостей 4, 7 і «часткове покриття» пройшли одразу, бо ці властивості вже виконувались. Це регресійні тести.

Не запускалось:
- реальна LLM: усі оцінки походять від заглушок;
- ручна браузерна перевірка поза Playwright;
- Firefox і Safari.

## Три сценарії (SIMULATED, політика v1, історичні результати 2026-11-18)

Команда: `cd app && uv run python scripts/seniority_scenarios.py`.

Код продукту працює без змін:
- профіль, добірка, адаптивна співбесіда;
- валідація виходу Evaluator, агрегація практики, хук завершення;
- `GET /level` і `GET /results`.

Замінено лише чат-модель. Interviewer-заглушка питає про непокриті критерії за їхніми назвами. Evaluator-заглушка ставить оцінку з прихованої «істини» й дослівно цитує відповідь. Отже, сценарії показують, як оцінювач і API обробляють задані докази. Якість оцінювання вони не вимірюють.

| Сценарій | Добірка | Питань / тем | Очікувано | Отримано |
|---|---|---|---|---|
| S1: бажаний Senior. Критерії Junior і Middle 0.9; критерії лише Senior 0.72 (смуга `[τ−ε, τ)`); практика Senior без доказів | сценарна, 10 вакансій | 10 / 10 | MIDDLE, ASSESSED | MIDDLE, ASSESSED: Junior 9/9, Middle 12/13 SUPPORTED; Senior 8/15 оцінено, 2 підтверджено, UNVERIFIED; прогалин 0 |
| S2: усі критерії 0.9 | сценарна, 10 вакансій | 10 / 10 | SENIOR, ASSESSED | SENIOR, ASSESSED: Junior 8/9, Middle 11/13, Senior 12/15, 6 компетентностей |
| S3: усі критерії 0.95, бюджет 3 питання (`total_budget`, як у раннері експериментів) | системна, 90 вакансій | 3 / 3 | UNKNOWN, INSUFFICIENT_DATA | UNKNOWN, INSUFFICIENT_DATA: Junior 4/9, 1 компетентність |
| S2-product (контроль): відповіді S2 на повній добірці | системна, 90 вакансій | 10 / 10 | — | JUNIOR, ASSESSED: Middle 9/13 і Senior 9/15, UNVERIFIED |

- Пояснення S1: «Підтверджено Middle за перевіреними критеріями. Для висновку про Senior недостатньо даних.»
- Пояснення S3: «Рівень не визначено: для висновку про Junior недостатньо даних.»
- Скрипт друкує для кожного сценарію:
  - оцінки й кількість доказових відповідей на критерій;
  - покриття за рівнями з кодами причин;
  - пояснення та неоцінені критерії;
  - топ-5 вакансій із розділом.

**Сценарна добірка** відхиляється від продуктового контракту, і це позначено у виводі як `SCENARIO_SUB_COHORT`. Вона містить ті самі 10 засіяних вакансій без змін вимог: кожна має ≥5 тем політики і ≤2 інших теми. Без такої добірки Middle і Senior через API показати неможливо (див. наступний розділ).

## Відповідність 12 обов'язкових вимог тестам

Нумерація відповідає розподілу з плану (задача 7, крок 1). Назви тестів перевірено через `grep` у `app/tests/`. Файли: `est` = `test_seniority_estimator.py`, `api` = `test_seniority_api.py`, `flow` = `test_level_probe_flow.py`, `scn` = `test_seniority_scenarios.py`.

| # | Вимога | Тести (файл::назва) | Сценарій |
|---|---|---|---|
| 1 | Зміна бажаного рівня не змінює оцінений рівень | `api::test_desired_level_change_does_not_change_result`, `est::test_estimator_has_no_desired_level_years_or_self_rating_parameter` | S1 (бажаний Senior → MIDDLE): `scn::test_s1_desired_senior_confirms_middle_senior_unverified` |
| 2 | Один сильний критерій нічого не підтверджує; Junior не призначається за замовчуванням | `est::test_one_of_five_criteria_confirms_nothing`, `est::test_junior_requires_minimum_coverage_never_default`, `est::test_min_competencies_blocks_single_competency_proof` | S3: `scn::test_s3_strong_answers_without_coverage_stay_unknown` |
| 3 | Невідомий критерій не є прогалиною; встановлена прогалина ≠ відсутність доказів | `est::test_unknown_is_not_a_gap`, `est::test_established_gap_differs_from_missing_evidence`, `est::test_low_score_without_evidence_turn_is_unresolved_not_gap` | S1 (прогалин 0 при неперевіреному Senior) |
| 4 | Middle підтверджується незалежно від бажаного Junior чи Senior | `est::test_middle_confirmed_even_if_desired_junior_or_senior`, `est::test_middle_confirmed_senior_unverified_sentence` | S1 |
| 5 | Відсутня компенсація: сильні базові чи другорядні оцінки не закривають критичне Senior; Senior потребує всіх нижчих рівнів | `est::test_high_basics_do_not_compensate_unverified_critical_senior`, `est::test_secondary_high_scores_do_not_offset_a_critical_gap`, `est::test_senior_requires_all_hierarchical_levels` | S2: `scn::test_s2_senior_needs_every_level_supported` |
| 6 | Поріг `τ` і смуга `ε`; підтвердження потребує доказової відповіді | `est::test_tau_epsilon_borderline_is_unresolved_not_gap`, `est::test_score_without_evidence_turn_is_not_counted_confirmed` | S1 (критерії Senior 0.72 у смузі) |
| 7 | Самооцінки й роки досвіду не підвищують рівень | `api::test_self_rating_and_years_do_not_raise_level` | — |
| 8 | Нова версія політики не переписує історію; рядок містить версію політики й спробу | `api::test_policy_version_change_does_not_rewrite_history`, `api::test_level_stored_on_finish_with_policy_version_and_attempt` | — |
| 9 | Спроби не змішуються; докази практики не залежать від порядку тем | `api::test_attempts_are_not_mixed`, `api::test_practice_evidence_is_topic_order_independent` | — |
| 10 | Рівень не змінює ранжування; розділи лише групують ті самі вакансії | `api::test_level_does_not_change_ranking_key`, `api::test_sections_partition_same_items` | топ-5 вакансій у виводі S1–S3 |
| 11 | Доступ лише власника; маркетинг і дизайн → UNKNOWN / POLICY_UNAVAILABLE | `api::test_owner_isolation_level_endpoint`, `api::test_unauthenticated_level_401`, `api::test_results_level_block_for_marketing_is_unknown_policy_unavailable`, `est::test_no_policy_marketing` | — |
| 12 | Співбесіда з пріоритетом рівня не порушує лімітів, Q_t і бюджету; вичерпаний бюджет дає UNKNOWN, а не здогад | `flow::test_interview_never_exceeds_caps_with_level_probing`, `flow::test_no_question_targets_criterion_with_sufficient_evidence`, `flow::test_q_t_choice_identical_with_and_without_probing`, `flow::test_budget_exhausted_leaves_level_unknown_not_guessed` | S3 (бюджет 3) |
| + | Рівень не залежить від `E_c` і `MIN_COVERAGE_FOR_OVERALL` | `api::test_level_independent_of_partial_topic_coverage` | — |

Усі чотири сценарії перевіряє `scn::test_scenario_level_and_status`.

## Відомі обмеження (коротко)

- Практика агрегується максимумом між темами. Одна тема, що підтверджує критерій, переважує іншу тему, що показує прогалину. Це зміщення вгору: оптимістична асиметрія порівняно з правилом «остання ненульова оцінка» для критеріїв тем.
- З політикою v1 Middle (і тим більше Senior) структурно недосяжний на повній добірці python. Подробиці — у пункті 1 наступного розділу. З 2026-11-19 поточною є v2, де це обмеження знято (розділ «Оновлення 2026-11-19»).

## Головний результат і обмеження

1. **(v1; розв'язано політикою v2, див. «Оновлення 2026-11-19».) На повній добірці python Middle і Senior за v1 практично недосяжні.**
   - Q_t вибирає теми за ринковою цінністю. Серед 10 тем є fastapi, kafka, aws і docker, яких немає в політиці.
   - Тому навіть рівномірно сильні відповіді дають лише JUNIOR (контроль S2-product).
   - Варіанти, перевірені під час розробки, теж не дали вищого рівня. Це оцінки 0 або 0.3 для тем поза політикою і бажаний рівень junior: результат UNKNOWN або JUNIOR.
   - Критичні множини v1 охоплюють 13 тем. Щоб за 10 тем досягти Senior, майже всі вибрані теми мають бути темами політики, як у S2 на сценарній добірці. Q_t на ринковій добірці так не вибирає, а змінювати Q_t план забороняє.
   - Рішення потребує власника. Можливі варіанти: політика під ринкові теми, рівневий вибір тем або більший бюджет. Тест `test_full_system_cohort_caps_level_known_limit` фіксує цей стан.
2. **Політика є робочим припущенням.** Пороги, частки, критичні множини й мінімум компетентностей обрав автор. Експертної валідації немає. Рубрики практики є шаблоном CURATED_TEMPLATE.
3. **Валідації немає.** Не було ні експертної перевірки, ні реальних кандидатів, ні реальної LLM. Тексти практики реальна модель не оцінювала: не перевірено, чи вона не оцінює впевненість замість дій.
4. **Малий бюджет дає UNKNOWN.** Короткий бюджет (S3) і навіть повні 10 тем на ринковій добірці дають UNKNOWN або Junior. Це очікуваний чесний результат, а не помилка.
5. **Маркетинг і дизайн не підтримуються.** Для них політики немає: результат UNKNOWN і POLICY_UNAVAILABLE.
6. **Технічні рішення, які треба знати:**
   - межа звітних списків дорівнює `max(ланцюг+1, найвищий зачеплений рівень)`;
   - `evidence_turns` — це об'єднання відповідей усіх ненульових ревізій;
   - підтвердження вимагає доказової відповіді;
   - оцінка без відповіді не є прогалиною;
   - практика агрегується за темою джерела незалежно від порядку: максимум між темами;
   - оцінку практики зараховано темі першої цитованої відповіді;
   - один недійсний пункт практики відкидає й оцінки теми: після повтору відповідь отримує статус UNGRADED;
   - `prompt_version` змінився для всіх напрямів, тож запуски до і після змін не порівнюються за промптами.
7. **Відкладені дрібниці:**
   - назви критеріїв беруться лише з рубрик `v1`; для інших версій показується сирий id;
   - запит останньої завершеної спроби дублюється в `level.py` і `profiles.py`;
   - `GET /assessments` віддає рядки практики з `action_name = practice-backend`;
   - розділи групують лише поточну сторінку;
   - фраза в рядку політики залежить від тексту бекенду (`levelView.ts`).
8. **Диплом.** DOCX не редагувався. Потрібні зміни описано в `docs/tasks/THESIS_SYNC_SENIORITY.md`.
