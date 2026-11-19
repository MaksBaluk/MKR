# Матеріали розділу 4: як відтворити (фаза 1)

Фаза 1 охоплює етапи 1–4 і 8 специфікації (`.superpowers/sdd/ch4-spec.md`): знімок реалізації, аудит SeniorityEstimator і архітектури, контрольні сценарії S01–S12, перевірку математичного ядра, технічне тестування. Етапи 5–7, 9–12 (порівняння режимів, адаптивність, незалежна якість, тексти розділу) — наступні фази.

**Що це не є.** Жодного виклику реальної LLM, жодного реального кандидата, жодних експертних міток. Усі наскрізні інтерв'ю — детерміновані заглушки з міткою `SIMULATED`; рядки рівня оцінювача мають мітку `ESTIMATOR_LEVEL`. Ці дані показують коректність алгоритмів і потоку, а не якість оцінювання реальних людей. 180 вакансій-фікстур — вигадані/адаптовані приклади, 49 — знімок Djinni.

## Файли фази 1

| Файл | Що містить | Як створено |
|---|---|---|
| `implementation_snapshot.md` | версії, БД, міграції, дані, LLM, версії правил, перевірка критичних виправлень, EXPERIMENT_BLOCKER | вручну за результатами команд |
| `experiment_manifest.json` | `frozen_config` (commit, хеші датасету й когорт, рубрики, політика v4 + sha256, `difficulty/v2`, `prompt_version`, ліміти, LLM без секретів), `phase1_evidence`, `runs` (порожній, для фази 2) | `scripts/chapter4/freeze_config.py` |
| `architecture_audit.md`, `seniority_audit.md` | аудит етапу 2, дефекти P0/P1/P2 з `файл:рядок` | вручну |
| `seniority_results.csv` | S01–S12 (+S09a) на рівні оцінювача і 6 наскрізних прогонів через API | `scripts/chapter4/seniority_scenarios_ch4.py` |
| `interview_turns.jsonl` | усі ходи наскрізних прогонів S*-E2E (питання, цілі, складність, відповідь, ревізії оцінок) з `run_id` | те саме |
| `mathematical_validation.csv` | 65 контрольних прикладів + 22 property-перевірки (сідовані цикли) | `scripts/chapter4/math_validation_ch4.py` |
| `raw/seniority_sweep_runs.csv`, `raw/seniority_sweep_summary.json` | 96 детермінованих + 224 шумових інтерв'ю, частоти за політиками v1–v4, причини пропуску Senior | `scripts/chapter4/seniority_sweep_ch4.py` |
| `raw/seniority_sweep_ua_stub_*` | той самий шумовий перебір зі зміненою заглушкою (варіант стенду `UaModel`) | `seniority_sweep_ch4.py --stub-ua` |
| `test_results.md` | точні команди, середовище, кількості, тривалість, збої | вручну за результатами команд |
| `failure_cases.md` | проблемні сценарії й обмеження (оновлено) | вручну |

Файли попереднього пакета (`experiment_runs.csv`, `criterion_results.csv`, `ranking_results.csv`, `evaluation_*`, `adaptivity_scenarios.*`, `math_validation.csv`, `environment.md`, `chapter4_evidence_report.md`, `raw/runs.*`) створено на **старішому коді** (інший `prompt_version`, до політики v4 і WP-B). Вони не є результатами фази 1 і мають бути перегенеровані у фазі 2. `interview_turns.jsonl` перезаписано: тепер він містить лише ходи фази 1 (старі рядки є в історії git, коміт `1278e33`).

## Команди (з каталогу `app/`)

```bash
# Етап 1: заморозити конфігурацію (масив runs не чіпається)
uv run python -m scripts.chapter4.freeze_config

# Етап 3: S01–S12 + наскрізні прогони (≈10 с)
uv run python -m scripts.chapter4.seniority_scenarios_ch4
uv run pytest -q tests/test_chapter4_seniority_scenarios.py

# Етап 4: математичне ядро (≈2 с)
uv run python -m scripts.chapter4.math_validation_ch4
uv run pytest -q tests/test_chapter4_math_properties.py

# Етап 2: досяжність рівнів через API (≈7 хв, 320 інтерв'ю; варіант стенду ≈5 хв)
uv run python -m scripts.chapter4.seniority_sweep_ch4
uv run python -m scripts.chapter4.seniority_sweep_ch4 --stub-ua
uv run python -m scripts.seniority_realistic --noisy        # оригінальний скрипт; має дати ті самі v4-частоти

# Етап 8
uv run pytest -q                                            # SQLite
docker run -d --rm --name ch4-pg -e POSTGRES_PASSWORD=ch4 -e POSTGRES_DB=ch4 -p 127.0.0.1:55432:5432 pgvector/pgvector:pg16
CH4_PG_URL=postgresql+psycopg://postgres:ch4@127.0.0.1:55432/ch4 uv run pytest -q tests/test_chapter4_postgres.py
docker stop ch4-pg
cd frontend && npm run typecheck && npm test && npm run build && cd ..
docker compose up -d --build api web && (cd frontend && npx playwright test)
```

`tests/test_chapter4_postgres.py` без змінної `CH4_PG_URL` пропускається; він **скидає схему** бази, тому вказувати лише одноразову БД, ніколи проєктну. Playwright створює тестових користувачів `e2e-*@example.test` у БД Docker-стека.

## Ідентифікатори прогонів

- `ch4-sweep-det-NNN`, `ch4-sweep-noi-NNN` (і `…-ua` для варіанта стенду) — рядки `raw/seniority_sweep_runs.csv`, кожен із `interview_id`.
- `ch4-sNN-est` — рядки оцінювача в `seniority_results.csv`; `ch4-sNN-e2e*` — наскрізні прогони, їхні ходи в `interview_turns.jsonl`.
- `ch4-pg-*` — прогони на одноразовому PostgreSQL (`test_chapter4_postgres.py`).
Усі прогони фази 1 виконано на commit `282f6fb` і конфігурації `experiment_manifest.json` → `frozen_config`.
