# Звіт: оцінений професійний рівень (SeniorityEstimator)

Гілка `feat/criterion-core`, коміти від `1e8c250` до фінального коміту задачі 7 (2026-11-18). Дизайн: `docs/superpowers/specs/2026-11-18-seniority-estimator-design.md`. План: `docs/superpowers/plans/2026-11-18-seniority-estimator.md`. Правила: `docs/tasks/MATH_SPEC.md` §3e.

## Оновлення 2026-11-19 (друге): політика `python-backend/v3` (§v3)

Поточна політика напряму python тепер `python-backend/v3`. Це рішення власника: знизити поріг Senior. Політики v1 і v2 лишаються доступними за версією, а збережені рядки v1 і v2 не переписуються й показуються за власними порогами. Правила описано в `docs/tasks/MATH_SPEC.md` §3e, пункт «Policy v3».

**Що змінено.** Лише правило Senior. Пули, τ, правила Junior і Middle, код оцінювача, Q_t, бюджети й ранжування (2.15) не змінювалися. Міграції немає.

| Senior | v2 | v3 |
|---|---|---|
| частка оцінених пулів | .75 → 11 з 14 | .60 → 9 з 14 |
| частка підтверджених пулів | .70 → 10 з 14 | .50 → 7 з 14 |
| мінімум компетентностей `m_L` | 4 | 3 |

- Кількості дорівнюють `⌈частка × 14⌉`. Частки .60/.50 є обраним робочим припущенням, а не виміряними чи каліброваними величинами. Статус лишається WORKING_ASSUMPTION; потрібна експертна валідація.
- **Що означає зниження.** Для Senior тепер потрібно менше доказів. Senior за v3 — слабше твердження, ніж Senior за v2. Рівні різних версій не можна порівнювати як одну шкалу.
- **Чому `m_L` = 3.** Із `m_L` = 4 і нижчими кількостями Senior потребує 7–8 повністю оцінених тем з усією практикою на 14 виміряних послідовностях (v2: 7–9). Ціль власника — близько 6 тем, а це потребує `m_L` = 3. Це вибір поза заявленими частками; він чекає явного підтвердження власника. Альтернатива — `m_L` = 4 і 7–8 тем.
- **Що `m_L` = 3 не гарантує.** `comp` рахує різні інструменти серед підтвердних критеріїв, а не пули. Одна тема або два інструменти покриття Senior не дають (тест: kafka + aws + уся практика — 9/9 пулів, але 2 інструменти). Проте два інструменти в одному пулі рахуються двічі, тому це **не** гарантія ширини: Senior за v3 може спиратися лише на **2 технічні здатності Senior** (наприклад, «Безпечні релізи та відкат» через `ci-cd.safety` і «Безпека доступу та авторизація» через `aws.iam` і `rest-api.security`) плюс 5 пулів практики. Решту до `A^min` = 9 можуть заповнити нерозв'язані пули (межова оцінка або оцінка без ходу з доказом), бо вони рахуються як оцінені. Вимір рецензента: такі докази дають SENIOR за v3 і MIDDLE за v2. У v2 поріг 10 підтверджених пулів вимагав щонайменше 5 технічних.
- **Збережені запобіжники (тести).** Ієрархія: Senior потребує підтвердженого ланцюга Junior і Middle. Компенсації між пулами немає. Підтвердження потребує ходу з доказом. Слабка практика рівня Senior дає GAP. Без жодної теми даних — UNKNOWN. Прогалину однієї навички не ховає сусідня навичка того самого інструмента.

### Досяжність v2 і v3 (вивід `scripts/seniority_reachability.py`, SIMULATED, реальний прогін)

Частота тем не змінилася (51 співбесіда, ті самі 14 послідовностей тем).

**Верхня межа** (усі критерії перших k тем і вся практика, 14 послідовностей):

| k | v2 | v3 |
|---|---|---|
| 5 | MIDDLE 13, UNKNOWN 1 | MIDDLE 13, UNKNOWN 1 |
| 6 | MIDDLE 14 | SENIOR 14 |
| 7 | SENIOR 11, MIDDLE 3 | SENIOR 14 |
| 8 | SENIOR 13, MIDDLE 1 | SENIOR 14 |
| 10 | SENIOR 14 | SENIOR 14 |

**Мінімальне k** (усі критерії перших k тем, min..max за 14 послідовностями):

| Практика | v2 Middle | v2 Senior | v3 Middle | v3 Senior |
|---|---|---|---|---|
| немає | 7–9 | ніколи | 7–9 | ніколи |
| перші 3 критерії | 5–6 | ніколи | 5–6 | 7–9 |
| усі 6 | 5–6 | 7–9 | 5–6 | 6 |

**Часткове оцінювання з усією практикою.** v3 дає SENIOR за 6–8 тем по 4 критерії або 8–10 тем по 3 критерії. v2 давав SENIOR лише за 10 тем по 4 критерії. З 1 або 3 критеріями практики результат v3 такий самий, як у v2 (MIDDLE або нижче). З 2 критеріями на тему — UNKNOWN за обох версій.

**Окремі випадки:**
- 8 тем, які Q_t вибирає завжди: без практики MIDDLE за обох версій; з усією практикою SENIOR за обох версій.
- Без жодної теми даних з усією практикою: UNKNOWN за обох версій. Покриття Senior саме по собі за v3 має статус SUPPORTED, але ланцюг обривається на Junior.
- **Новий ефект v3:** sql без postgresql і django (8 тем) з усією практикою дає SENIOR (v2: MIDDLE). Транзакції, схема даних, експлуатація БД і міграції при цьому не перевірені.

### Сценарії v3 (SIMULATED, реальні прогони)

Команда: `cd app && uv run python scripts/seniority_scenarios.py`. Для кожного сценарію ті самі збережені докази також оцінено за v2 (лише для порівняння).

| Сценарій | Питань / тем | v3 (збережено) | v2 на тих самих доказах |
|---|---|---|---|
| P1, усе 0.9 | 10 / 10 | SENIOR (Senior 12/14, 5 компетентностей) | SENIOR |
| P2, Senior-критерії 0.72, без практики Senior | 10 / 10 | MIDDLE (Senior 9/14 оцінено, 2 підтверджено) | MIDDLE |
| P3, усе 0.3 | 20 / 10 | UNKNOWN, GAPS_AT_JUNIOR | UNKNOWN |
| P4, Junior і частина Middle | 28 / 10 | JUNIOR | JUNIOR |
| S3, бюджет 3 | 3 / 3 | UNKNOWN, INSUFFICIENT_DATA | UNKNOWN |
| P5 (новий), усе 0.9, бюджет 6 | 6 / 6 | SENIOR (Senior 10/14, рівно 3 компетентності) | MIDDLE |

### Обмеження v3

- Пороги — робоче припущення власника, не калібрування. Експертної валідації немає.
- Senior за v3 потребує менше доказів: 7 підтверджених пулів, з них до 5 — практика. Реальна модель практику не оцінювала; агрегування максимумом між темами має оптимістичне зміщення.
- P5 досягає Senior із рівно 3 компетентностями, тобто на межі `m_L`.
- Поза системною добіркою (будь-які теми рубрик, повне оцінювання й уся практика) найменший набір для Senior має 5 тем за v3 (наприклад, async-python, celery, python-core, rest-api, sql) і 6 за v2. Q_t зараз таких наборів не вибирає.
- Співбесіда, розпочата за v2 і завершена після переходу на v3, оцінюється за v3: проба рівня й завершення беруть поточну політику (`api/core.py`, `api/level.finalize_level`). Збережені рядки завжди мають власну версію.
- Senior можна призначити без доказів про транзакції, схему даних і міграції, якщо оцінено sql (див. окремі випадки).
- Обмеження v2 (нижче) лишаються чинними.

## Оновлення 2026-11-19: політика `python-backend/v2` (§v2)

Станом на це оновлення поточною була `python-backend/v2` (з другого оновлення поточна v3). Політика v1 лишається доступною за версією, а збережені рядки v1 не переписуються. Правила описано в `docs/tasks/MATH_SPEC.md` §3e: пункти «Policy v2», «v2 thresholds», «Disclosed weaknesses», «Versions and rows». Q_t, вибір тем, бюджети, ранжування (2.15) й `E_c` не змінювалися.

**Виправлення після рев'ю (I-1).** Перша редакція v2 об'єднувала в один пул «будь-який із» різні навички одного інструмента, наприклад `sql.joins | sql.correctness` чи `python-core.idioms | errors`. Через це сильна навичка ховала встановлену прогалину сусідньої: `errors=0.1` і `sql.correctness=0.1` давали JUNIOR без прогалин.
- Тепер пул містить лише альтернативи з різних інструментів, і тест це перевіряє. Кожна навичка одного інструмента стала окремим пулом.
- Регресійний тест `test_same_tool_gap_is_never_hidden_by_a_sibling_skill` перевіряє цей випадок: результат GAPS_AT_JUNIOR, обидві прогалини у `critical_gaps`, як і у v1.
- Нижче наведено виміри після виправлення.

### Вимірювання: які теми вибирає Q_t

Команда (відтворювана, SIMULATED): `cd app && uv run python scripts/seniority_reachability.py`. Прогін триває близько 30 с.

Співбесіди йшли через реальний API на повній системній добірці (90 засіяних вакансій python) із симульованим Evaluator. Шаблонів відповідей 17:
- рівні оцінки 0.9, 0.75, 0.6, 0.4 і 0.2;
- 8 псевдовипадкових наборів у діапазоні 0.3–1.0;
- 4 такі самі набори, де частина оцінок дорівнює null.

Кожен шаблон запускався з бажаним рівнем junior, middle і senior: усього 51 співбесіда.

| Тема | Частка співбесід, де тему вибрано |
|---|---|
| python-core, kafka, fastapi, ci-cd, sql, aws, docker, postgresql | 51/51 |
| django | 42/51 |
| git | 24/51 |
| redis | 24/51 |
| rest-api | 12/51 |
| app-security, async-python, celery, kubernetes, linux, observability, pytest, sqlalchemy | 0/51 |

- Бажаний рівень на послідовність тем не вплинув.
- Порядок тем за ринковою вагою (`GET /cohorts/{id}/market`): python-core, fastapi, kafka, django, docker, redis, aws, pytest, sql, postgresql, ci-cd, celery, rest-api, git, sqlalchemy, observability, async-python, app-security, kubernetes, linux.
- pytest стоїть восьмим за ринком, але Q_t його не вибирає. Q_t максимізує приріст покриття груп, а групи з pytest уже закриті іншими альтернативами.

### Пули v2

Пул — це одна професійна здатність, яку можна показати різними інструментами. Члени пулу завжди мають різні префікси компетентностей. Пул підтверджено, якщо його підтверджує будь-який член. Компенсації між пулами немає.

Усі id існують у фікстурах; це перевіряє тест `test_v2_pools_use_existing_ids_titles_and_hierarchy`. Нових критеріїв рубрик немає.

- Із 34 критичних id v1 повторно використано 33.
- `ci-cd.pipeline` змінив рівень: з Middle перейшов на Junior, у пул «Збирання сервісу».
- `app-security.input` не увійшов до v2. Серед вибираних тем він не має альтернативи з іншого інструмента. Окремим пулом він був би завжди неоціненою одиницею, бо Q_t не вибирає app-security.
- Додано 31 id, які у v1 не були критичними:
  - app-security.secrets;
  - async-python.testing;
  - aws.cost, .deploy, .iam;
  - celery.design, .retries;
  - ci-cd.deploy;
  - django.architecture, .migrations, .orm, .permissions;
  - docker.images, .runtime, .security;
  - fastapi.async, .dependencies, .testing, .validation;
  - kafka.consumers, .errors, .schemas, .semantics;
  - kubernetes.security, .troubleshooting, .workloads;
  - linux.diagnostics;
  - rest-api.versioning;
  - sql.performance;
  - sqlalchemy.loading, .models.

| Рівень (τ; мін. оцінених / підтверджених пулів / компетентностей) | Пули (назва: члени) |
|---|---|
| Junior (0.50; 7 / 7 / 3 з 9) | Ідіоматичний код Python: python-core.idioms · Обробка помилок у Python: python-core.errors · З'єднання таблиць у запитах: sql.joins · Коректність результатів запитів: sql.correctness · Контракт і валідація API: rest-api.contract, fastapi.validation · Перевірка коректності коду: python-core.testing, pytest.structure · Збирання сервісу: docker.images, ci-cd.pipeline · Робота з гілками в Git: git.branching · Самостійність (практика) |
| Middle (0.70; 10 / 9 / 5 з 14) | Типізація та контракти коду: python-core.typing · Ефективність запитів і доступу до даних: postgresql.indexes, sql.performance, sqlalchemy.loading, django.orm · Транзакції та узгодженість: postgresql.transactions, sqlalchemy.session · Проєктування схеми: postgresql.schema, sqlalchemy.models · Структура сервісу та API: fastapi.dependencies, rest-api.pagination, django.architecture · Асинхронна робота без блокувань: fastapi.async, async-python.blocking · Ізольовані тести: pytest.isolation, fastapi.testing, async-python.testing · Конфігурація та розгортання: docker.runtime, ci-cd.deploy, aws.deploy, kubernetes.workloads · Споживачі подій і фонові задачі: kafka.consumers, celery.design · Обробка збоїв і повторні спроби: kafka.errors, celery.retries · Безпека контейнерів і секретів: docker.security, app-security.secrets · практика: самостійність, обґрунтування, діагностика |
| Senior (0.75; 11 / 10 / 4 з 14) | Експлуатація бази даних: postgresql.operations · Безпечні зміни схеми: postgresql.migrations, django.migrations · Конкурентний доступ і паралельність: sqlalchemy.concurrency, async-python.concurrency · Гарантії доставки: kafka.semantics, celery.idempotency, redis.reliability · Безпечні релізи та відкат: ci-cd.safety · Безпека доступу та авторизація: app-security.authz, rest-api.security, aws.iam, django.permissions, kubernetes.security · Розслідування інцидентів: observability.incidents, linux.diagnostics, kubernetes.troubleshooting · Вартість і надійність інфраструктури: aws.cost · Сумісність контрактів: rest-api.versioning, kafka.schemas · практика: компроміси, невизначеність, відповідальність, діагностика, обґрунтування |

**Пороги не виміряно й не калібровано.** Кожен поріг дорівнює `⌈частка × кількість пулів⌉`. Частки обрано:
- Junior: 0.75 / 0.75, як у v1;
- Middle: 0.70 / 0.60, знижено з 0.80 / 0.70 за варіантом 2 рев'ю;
- Senior: 0.75 / 0.70, знижено з 0.80 / 0.80.

Мінімум компетентностей Senior знижено з 6 до 4. Після розщеплення пулів частки не змінювалися: перераховано лише кількості. Вимірювання нижче показує наслідки цих порогів, а не обґрунтовує їх. У дипломі їх не можна називати виміряними.

### Досяжність (вивід `scripts/seniority_reachability.py`, SIMULATED)

**Верхня межа.** Оцінку 0.9 мають усі критерії перших k вибраних тем і вся практика. Наборів тем 14:

| k | v1 | v2 |
|---|---|---|
| 6 | UNKNOWN 14 | MIDDLE 14 |
| 8 | UNKNOWN 14 | SENIOR 13, MIDDLE 1 |
| 10 | UNKNOWN 12, JUNIOR 2 | SENIOR 14 |

**Часткове оцінювання.** Оцінено перші n критеріїв кожної з k найчастіших тем: python-core, kafka, fastapi, ci-cd, sql, aws, docker, rest-api, postgresql, git. Підтверджено 1, 3 або 6 критеріїв практики. Результат v2:
- 2 критерії на тему: UNKNOWN за будь-якої кількості тем.
- 3 критерії на тему:
  - 5–6 тем: JUNIOR;
  - 7–8 тем: JUNIOR, а MIDDLE лише з усією практикою;
  - 10 тем: MIDDLE.
- 4 критерії на тему:
  - 5–6 тем: MIDDLE за ≥3 критеріїв практики, інакше JUNIOR;
  - 7–8 тем: MIDDLE;
  - 10 тем: MIDDLE, а SENIOR лише з усією практикою.

**Окремі випадки:**
- 8 тем, які Q_t вибирає завжди, усі критерії, без практики: MIDDLE. З усією практикою: SENIOR (12/14 пулів; рівно 4 компетентності).
- Без жодної теми даних (python-core, kafka, fastapi, ci-cd, aws, docker) навіть з усією практикою: UNKNOWN. Покриття Middle саме по собі має статус SUPPORTED, але пули SQL рівня Junior не оцінено, тому ланцюг рівнів обривається. Див. M-1 у MATH_SPEC §3e.
- sql без postgresql і django (8 тем) з усією практикою: MIDDLE, хоча транзакції та схему даних не перевірено.

**Висновок.**
- Middle досяжний на системній добірці, якщо кожна тема має 3–4 оцінені критерії. Знадобиться від 5 до 10 тем, залежно від кількості критеріїв на тему й підтвердженої практики.
- Senior досяжний лише з майже повним покриттям 8–10 тем і щонайменше 3 підтвердженими пулами практики.
- Два пули Senior на системній добірці недосяжні.

### Сценарії v2 (SIMULATED, реальні прогони)

Команда: `cd app && uv run python scripts/seniority_scenarios.py`. Усі сценарії використовують повну системну добірку (90 вакансій). Заглушка Evaluator оцінює всі критерії теми з прихованої «істини», тому P1 і P2 показують верхню межу.

| Сценарій | Відповіді | Питань / тем | Отримано |
|---|---|---|---|
| P1 | усе 0.9 | 10 / 10 | SENIOR: Junior 9/9, Middle 14/14, Senior 12/14; не перевірено: «Конкурентний доступ і паралельність», «Розслідування інцидентів у продакшені» |
| P2 | Junior і Middle 0.9, критерії лише Senior 0.72, практика Senior без доказів; бажаний Senior | 10 / 10 | MIDDLE; Senior UNVERIFIED (9/14 оцінено, 2 підтверджено), прогалин 0 |
| P3 (контроль) | усе 0.3 | 20 / 10 | UNKNOWN, GAPS_AT_JUNIOR: 8 з 8 оцінених пулів Junior мають статус GAP (git не вибрано) |
| P4 | Junior і перші 5 пулів Middle 0.9, решта без доказів | 28 / 10 | JUNIOR; Middle UNVERIFIED (6/14 оцінено, прогалин 0) |
| S3 | усе 0.95, бюджет 3 | 3 / 3 | UNKNOWN, INSUFFICIENT_DATA: Junior 5/9 |

Сценарії S1, S2 і S2-product на `SCENARIO_SUB_COHORT` прибрано: із v2 звужена добірка не потрібна. Їхні історичні результати для v1 наведено нижче.

### Перевірки

Реальні команди після виправлення, 2026-11-19, наведено в `.superpowers/sdd/2026-11-18-seniority-estimator/policy-v2-report.md` (розділ «Fix round 1»). Підсумок:
- `cd app && uv run pytest -q`: усі тести пройшли;
- фронтенд: typecheck, vitest і build пройшли;
- Docker і Playwright: 8 passed.

Не запускалось:
- реальна LLM;
- експертна валідація;
- Firefox і Safari.

### Обмеження v2

- Пули, частки, пороги й мінімуми компетентностей є робочим припущенням (WORKING_ASSUMPTION). Експертної валідації немає. Рубрики є шаблонами CURATED_TEMPLATE.
- Senior сильно залежить від практики: потрібно ≥4 оцінені й ≥3 підтверджені пули практики. Реальна модель практику не оцінювала. Практика агрегується максимумом між темами, тобто з оптимістичним зміщенням.
- Одна тема може підтвердити кілька пулів одного рівня, бо це різні навички (M-2):
  - postgresql — 3 пули Middle;
  - fastapi — 3 пули Middle;
  - aws і kafka — по 2 пули Senior.
  Ширину забезпечує лише `m_L`.
- Middle можна призначити без доказів про транзакції та схему даних, якщо оцінено sql (M-1).
- Еквівалентність міжінструментних альтернатив — судження автора. Наприклад, `aws.deploy` і `docker.runtime` вважаються рівноцінними для «Конфігурація та розгортання».
- Два пули Senior на повній добірці python ніколи не оцінюються.

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
- З політикою v1 Middle (і тим більше Senior) структурно недосяжний на повній добірці python. Подробиці — у пункті 1 наступного розділу. З 2026-11-19 це обмеження знято політикою v2 (розділ «Оновлення 2026-11-19»); з другого оновлення того ж дня поточною є v3.

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
