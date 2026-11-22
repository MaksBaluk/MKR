# Механізми адаптивності (етап 6) — SIMULATED

Джерело: збережені ходи прогонів `raw/modes_runs.jsonl.gz` (набір `modes` і `ablation_sensitive`), створені `scripts/chapter4/modes_experiment.py`; файл згенеровано `scripts/chapter4/adaptivity_evidence.py`. Інтерв'юер, оцінювач і кандидат — детерміновані заглушки (див. `simulation_method.md`); рішення про тему, складність і уточнення — код продукту без змін. Це перевірка поведінки механізмів, а не якості на реальних кандидатах.

## 6.1 Вибір теми після позитивних і негативних відповідей

| Бюджет | Пар B/D | Порядок тем D відрізняється від статичного плану B | Множина тем D і B відрізняється |
|---|---|---|---|
| 10 | 54 | 15 | 54 |
| 20 | 54 | 54 | 54 |
| 30 | 54 | 54 | 39 |
| 50 | 54 | 54 | 34 |

Різних статичних планів на треку python: 1; різних порядків тем режиму D (бюджет 50): 14. Повні послідовності: `figures_data/topic_sequences_static_vs_adaptive.csv`.

Контраст за однакової когорти, бюджету 50 і seed 0 (режим D, адаптивне інтерв'ю продукту; колонка `no_market_topics` у CSV — режим C):

| Профіль | run_id | Питань | Питань на тему | Причини уточнень (followup_reason) |
|---|---|---|---|---|
| C13 | `ch4-m-C13-D-b50-s0` | 23 | `{"python-core": 2, "kafka": 2, "fastapi": 2, "ci-cd": 2, "aws": 2, "sql": 2, "docker": 5, "postgresql": 2, "rest-api": 2, "git": 2}` | OPEN_CRITERIA: 19, Є прогалина.: 4 |
| C07 | `ch4-m-C07-D-b50-s0` | 40 | `{"python-core": 4, "kafka": 5, "fastapi": 5, "ci-cd": 2, "aws": 2, "sql": 5, "docker": 5, "postgresql": 5, "git": 5, "pytest": 2}` | Є прогалина.: 22, OPEN_CRITERIA: 18 |
| C01 | `ch4-m-C01-D-b50-s0` | 44 | `{"python-core": 5, "kafka": 5, "fastapi": 5, "sql": 2, "django": 5, "ci-cd": 5, "aws": 5, "postgresql": 5, "docker": 5, "redis": 2}` | Є прогалина.: 33, OPEN_CRITERIA: 11 |
| C06 | `ch4-m-C06-D-b50-s0` | 22 | `{"python-core": 4, "kafka": 2, "fastapi": 2, "sql": 2, "django": 2, "ci-cd": 2, "aws": 2, "postgresql": 2, "docker": 2, "redis": 2}` | OPEN_CRITERIA: 19, Є прогалина.: 3 |

## 6.2 Адаптація складності (difficulty/v2)

Кількість подій (набір | модель кандидата):

- `DOWN_AFTER_WEAK_ADVANCED_TARGETS_WEAK|ablation_sensitive|sensitive`: 109
- `DOWN_AFTER_WEAK_ADVANCED_TARGETS_WEAK|modes|insensitive`: 91
- `DOWN_AFTER_WEAK_ADVANCED|ablation_sensitive|sensitive`: 111
- `DOWN_AFTER_WEAK_ADVANCED|modes|insensitive`: 91
- `UP_AFTER_STRONG|ablation_sensitive|sensitive`: 159
- `UP_AFTER_STRONG|modes|insensitive`: 244

**Сильна відповідь → складніше питання.**

- `ch4-m-C14-D-b10-s0` хід 1 (python-core, BASIC, причина `LEVEL:junior`), цілі `['python-core.idioms', 'python-core.errors']`, оцінки з цієї відповіді `{"practice-backend.independence": 0.81, "python-core.errors": 0.91, "python-core.idioms": 0.92}`
- `ch4-m-C14-D-b10-s0` наступний хід 2 (python-core, INTERMEDIATE, причина `STRONG`), цілі `['python-core.testing', 'python-core.typing']`, оцінки з цієї відповіді `{"practice-backend.diagnosis": 0.98, "practice-backend.rationale": 0.98, "python-core.testing": 0.86, "python-core.typing": 0.85}`

**Слабка відповідь на ADVANCED → діагностичне уточнення нижчого рівня.**

- `ch4-m-C11-D-b20-s0-dsens` хід 6 (kafka, ADVANCED, причина `STRONG`), цілі `['kafka.schemas', 'kafka.semantics']`, оцінки з цієї відповіді `{"practice-backend.ambiguity": 0.27, "practice-backend.diagnosis": 0.83, "practice-backend.ownership": 0.24, "practice-backend.rationale": 0.55, "practice-backend.tradeoffs": 0.23, "kafka.schemas": 0.33, "kafka.semantics": 0.51}`
- `ch4-m-C11-D-b20-s0-dsens` наступний хід 7 (kafka, INTERMEDIATE, причина `WEAK`), цілі `['kafka.schemas', 'kafka.semantics']`, оцінки з цієї відповіді `{"practice-backend.diagnosis": 0.72, "practice-backend.rationale": 0.72, "kafka.schemas": 0.59, "kafka.semantics": 0.52}`

**Висока оцінка в одній темі не піднімає складність усіх тем** (профіль C02: сильний Python, слабкий PostgreSQL; бюджет 50, seed 0; формат `рівень:причина` для кожного питання теми):

- `ch4-m-C02-D-b50-s0` (modes|insensitive), рівень: JUNIOR
  - python-core: B:LEVEL:junior, I:STRONG
  - kafka: I:CARRY:NO_OPEN_CRITERIA, B:WEAK, B:WEAK, B:WEAK, B:WEAK
  - fastapi: B:CARRY:QUESTION_CAP, B:PARTIAL, B:WEAK, B:WEAK, B:WEAK
  - ci-cd: B:CARRY:QUESTION_CAP, B:WEAK, B:PARTIAL, B:WEAK, B:WEAK
  - aws: B:CARRY:QUESTION_CAP, B:WEAK, B:WEAK, B:WEAK, B:WEAK
  - django: B:CARRY:QUESTION_CAP, B:WEAK, B:WEAK, B:WEAK, B:WEAK
  - sql: B:CARRY:QUESTION_CAP, B:PARTIAL
  - docker: I:CARRY:STRONG+ENOUGH, B:WEAK, B:WEAK, B:WEAK, B:WEAK
  - redis: B:CARRY:QUESTION_CAP, B:WEAK, B:WEAK, B:WEAK, B:WEAK
  - postgresql: B:CARRY:QUESTION_CAP, B:WEAK
- `ch4-m-C02-D-b50-s0-enstub` (stub_check|insensitive), рівень: JUNIOR
  - python-core: B:LEVEL:junior, I:STRONG
  - kafka: I:CARRY:NO_OPEN_CRITERIA, B:WEAK, B:WEAK, B:WEAK, B:WEAK
  - fastapi: B:CARRY:QUESTION_CAP, B:PARTIAL, B:WEAK, B:WEAK, B:WEAK
  - ci-cd: B:CARRY:QUESTION_CAP, B:WEAK, B:PARTIAL, B:WEAK, B:WEAK
  - aws: B:CARRY:QUESTION_CAP, B:WEAK, B:WEAK, B:WEAK, B:WEAK
  - django: B:CARRY:QUESTION_CAP, B:WEAK, B:WEAK, B:WEAK, B:WEAK
  - sql: B:CARRY:QUESTION_CAP, B:PARTIAL
  - docker: I:CARRY:STRONG+ENOUGH, B:WEAK, B:WEAK, B:WEAK, B:WEAK
  - redis: B:CARRY:QUESTION_CAP, B:WEAK, B:WEAK, B:WEAK, B:WEAK
  - postgresql: B:CARRY:QUESTION_CAP, B:WEAK
- `ch4-m-C02-D-b50-s0-dsens` (ablation_sensitive|sensitive), рівень: JUNIOR
  - python-core: B:LEVEL:junior, I:STRONG
  - kafka: I:CARRY:NO_OPEN_CRITERIA, B:WEAK, B:WEAK, B:WEAK, B:WEAK
  - fastapi: B:CARRY:QUESTION_CAP, B:PARTIAL, B:WEAK, B:WEAK, B:WEAK
  - ci-cd: B:CARRY:QUESTION_CAP, B:WEAK, B:PARTIAL, B:WEAK, B:WEAK
  - aws: B:CARRY:QUESTION_CAP, B:WEAK, B:WEAK, B:WEAK, B:WEAK
  - django: B:CARRY:QUESTION_CAP, B:WEAK, B:WEAK, B:WEAK, B:WEAK
  - sql: B:CARRY:QUESTION_CAP, B:PARTIAL
  - docker: I:CARRY:STRONG+ENOUGH, B:WEAK, B:WEAK, B:WEAK, B:WEAK
  - redis: B:CARRY:QUESTION_CAP, B:WEAK, B:WEAK, B:WEAK, B:WEAK
  - postgresql: B:CARRY:QUESTION_CAP, B:WEAK

**Бажаний рівень Junior не обмежує глибину** (C14: латентний Senior, бажаний junior):

| Набір / модель / режим | Прогонів | Дійшли до ADVANCED | Рівні |
|---|---|---|---|
| ablation_sensitive|sensitive|B_STATIC | 6 | 0 | JUNIOR: 6 |
| ablation_sensitive|sensitive|D_FIXED_DIFFICULTY | 6 | 0 | JUNIOR: 1, MIDDLE: 2, SENIOR: 3 |
| ablation_sensitive|sensitive|D_FULL_COMPETENCEMATCH | 6 | 6 | MIDDLE: 1, SENIOR: 5 |
| modes|insensitive|B_STATIC | 12 | 0 | JUNIOR: 12 |
| modes|insensitive|D_FIXED_DIFFICULTY | 12 | 0 | SENIOR: 9, UNKNOWN: 3 |
| modes|insensitive|D_FULL_COMPETENCEMATCH | 12 | 12 | SENIOR: 9, UNKNOWN: 3 |

## 6.3 followup_goal визначає наступне питання

Подій «один критерій питання підтверджено (≥ 0.75), інший слабкий (< 0.5) або без оцінки → наступне питання тієї ж теми спрямоване на відкритий критерій»: 246; з них підтверджена оцінка збереглася до кінця спроби: 246; відкритий критерій був без оцінки (не приписаний): 147. Причини наступного питання: `{"Є прогалина.": 110, "OPEN_CRITERIA": 136}`. Випадків PostgreSQL (transactions підтверджено, indexes відкритий): 0.

Подій «слабка оцінка postgresql.indexes → наступне питання теми про indexes»: 44.

**Приклад PostgreSQL (transactions підтверджено, indexes відкритий).**

Не спостерігалося (NOT_OBSERVED).

**Приклад PostgreSQL (indexes слабкий → уточнення про indexes).**

- `ch4-m-C12-D-b30-s0` хід 29: питання «Розкажіть про PostgreSQL (базовий рівень): «Індекси та плани виконання» та «Транзакції та ізоляція», питання 29?»; цілі `['postgresql.indexes', 'postgresql.transactions']`; followup_reason `OPEN_CRITERIA`; оцінки з відповіді `{"practice-backend.ambiguity": 0.61, "practice-backend.tradeoffs": 0.67, "postgresql.indexes": 0.3}`; ціль оцінювача після відповіді `["postgresql.indexes"]`
- `ch4-m-C12-D-b30-s0` наступний хід 30: питання «Розкажіть про PostgreSQL (базовий рівень): «Індекси та плани виконання», питання 30?»; цілі `['postgresql.indexes']`; followup_reason `Є прогалина.`; оцінки з відповіді `{"postgresql.indexes": 0.32}`; ціль оцінювача після відповіді `["postgresql.indexes"]`
- Підсумкові оцінки спроби: `{"postgresql.indexes": 0.32, "postgresql.transactions": null}`; підтверджене збережено: n/a; питань теми з indexes першою ціллю: 2.

**Приклад, де відкритий критерій лишився без оцінки.**

- `ch4-m-C03-D-b50-s1` хід 43: питання «Розкажіть про Git (базовий рівень): «Гілки та злиття» та «Командна робота з репозиторієм», питання 43?»; цілі `['git.branching', 'git.collaboration']`; followup_reason `OPEN_CRITERIA`; оцінки з відповіді `{"git.branching": 0.79}`; ціль оцінювача після відповіді `["git.collaboration"]`
- `ch4-m-C03-D-b50-s1` наступний хід 44: питання «Розкажіть про Git (середній рівень): «Командна робота з репозиторієм», питання 44?»; цілі `['git.collaboration']`; followup_reason `Є прогалина.`; оцінки з відповіді `{"practice-backend.diagnosis": 0.25, "practice-backend.rationale": 0.3, "git.collaboration": 0.38}`; ціль оцінювача після відповіді `["git.collaboration"]`
- Підсумкові оцінки спроби: `{"git.branching": 0.79, "git.collaboration": 0.38}`; підтверджене збережено: True; питань теми з indexes першою ціллю: n/a.

## 6.4 Абляція

Див. `ablation_results.csv` і `tables/table_4_6_ablation.md`.
