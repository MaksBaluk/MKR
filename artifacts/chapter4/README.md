# Матеріали розділу 4: як відтворити (фази 1–3)

Фаза 1 охоплює етапи 1–4 і 8 специфікації (`.superpowers/sdd/ch4-spec.md`): знімок реалізації, аудит SeniorityEstimator і архітектури, контрольні сценарії S01–S12, перевірку математичного ядра, технічне тестування. Етапи 5–7, 9–12 (порівняння режимів, адаптивність, незалежна якість, тексти розділу) — наступні фази.

**Що це не є.** Жодного виклику реальної LLM, жодного реального кандидата, жодних експертних міток. Усі наскрізні інтерв'ю — детерміновані заглушки з міткою `SIMULATED`; рядки рівня оцінювача мають мітку `ESTIMATOR_LEVEL`. Ці дані показують коректність алгоритмів і потоку, а не якість оцінювання реальних людей. Походження вакансій наведено за приміткою власника про дані; технічні метадані імпорту збережені в репозиторії (поля import_version, retrieved_at, source_name).

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

Файли попереднього пакета, створені на старішому коді, у фазі 2 **видалено** (історія git, коміт `1278e33`): `math_validation.csv` (замінено `mathematical_validation.csv`), `evaluation_report/`, `raw/runs.*`, `adaptivity_scenarios.*` (замінено `adaptivity_evidence.*`), `chapter4_evidence_report.md` (новий звіт — фаза 3); скрипти `scripts/chapter4/experiments.py`, `report.py`. Перегенеровано на заморожених версіях: `experiment_runs.csv`, `criterion_results.csv`, `ranking_results.csv`, `evaluation_metrics.csv`, `dataset_summary.csv`, `environment.md`.

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


## Фаза 2 (етапи 5–7, протокол v2 `.superpowers/sdd/ch4-spec-addendum.md`)

Одна команда (з `app/`, на чистому продуктовому коді; інакше відмова, `--allow-dirty` — свідомий обхід):

```bash
uv run python -m scripts.chapter4.build_all            # ≈ 12–15 хв на 6 процесах; --with-sweep додає фазові перебори (≈ 12 хв)
uv run pytest -q tests/test_chapter4_modes.py
```

| Файл | Зміст | Генератор |
|---|---|---|
| `simulation_method.md` | генеративний алгоритм кандидатів/заглушок, режими, статистика (для 4.2) | вручну |
| `raw/modes_runs.jsonl.gz`, `raw/modes_meta.json` | усі прогони режимів з ходами й ревізіями оцінок; перевірка відтворюваності | `modes_experiment.py` |
| `experiment_runs.csv` | один рядок на прогін: питання, теми, follow-up, зміни складності, fallback/UNGRADED, покриття, невирішені критичні, рівень, ширина інтервалів, `config_ref` | `modes_analysis.py` |
| `interview_experiment_results.csv` (E2), `ranking_metrics.csv` (E3), `evaluator_metrics.csv` (E4), `seniority_experiment_results.csv`, `estimator_metrics.csv` (E5) | поля протоколу v2; з фази 3 P@5/NDCG/MAE/точність обчислено проти пілотних `ADJUDICATED`-міток (статус `COMPUTED_PILOT_LLM_ANNOTATOR`) | `chapter4_metrics.py` |
| `mode_comparison.csv` | парні різниці режимів, кластерний бутстреп-ДІ, знаковий тест, d_z | `modes_analysis.py` |
| `ablation_results.csv` | B / C / D без зміни складності / D, дві моделі кандидата | `modes_analysis.py` |
| `criterion_results.csv`, `ranking_results.csv` | критерії (бюджет 50, і режим A) і Top-10 кожного прогону | `modes_analysis.py` |
| `seniority_results.csv`, `interview_turns.jsonl` | рядки фази 1 + рядки з `suite` (у jsonl — ходи seed 0, бюджет 50 і stub_check; усі ходи в raw) | `seniority_scenarios_ch4.py` + `modes_analysis.py` |
| `adaptivity_evidence.md/.json` | етап 6: вибір теми, складність, followup_goal на збережених ходах | `adaptivity_evidence.py` |
| `evaluation_metrics.csv` | статуси NO_GROUND_TRUTH / SIMULATED_GROUND_TRUTH / NOT_APPLICABLE | `modes_analysis.py` |
| `figures_data/*.csv`, `figures/*.svg`, `tables/*` | джерела рисунків, SVG з українськими підписами; з фази 3 таблиці 4.1–4.7 — див. нижче | `modes_analysis.py`, `final_report.py` |
| `missing_evidence.md` | чого бракує для повних висновків | `final_report.py` |
| `data/` | `vacancies.csv`, `vacancy_requirements.jsonl`, `dataset_audit.md`, `candidates.csv`, `hidden/scenario_definitions.json` (приховано), `candidate_competency_reference.jsonl` (null), `response_bank.jsonl`, `annotations/*.csv` (з фази 3 — пілотна розмітка), `annotation_inputs/` (інструкція, шкала 0–3, пул вакансій) | `data_package.py` |

Ідентифікатори: `ch4-m-<кандидат>-<режим>-b<бюджет>-s<seed>` (режими A, B, C, D, Dfd; суфікси `-dsens` — чутлива модель кандидата, `-enstub` — документована заглушка для перевірки EB-3). Усі прогони — SIMULATED на commit `282f6fb` (продуктовий код) і `experiment_manifest.json` → `frozen_config`; список run_id — `experiment_manifest.json` → `runs`.


## Фаза 3 (етапи 7, 9, 10, 12: розмітка, метрики, гіпотези, звіт)

Одна команда (з `app/`; нових симуляцій не запускає, читає збережені прогони й розмітку; ≈ 15 с):

```bash
uv run python -m scripts.chapter4.build_all --phase3-only          # + --with-timing переміряє E6 (≈ 20 с)
uv run pytest -q tests/test_chapter4_annotation_merge.py tests/test_chapter4_final_report.py
```

Повна перебудова всього пакета (фази 2–3): `uv run python -m scripts.chapter4.build_all` (≈ 6–7 хв). Повторний запуск `--phase3-only` дає побайтово однаковий вміст `artifacts/chapter4/` (перевірено хешем дерева). Значення E6 змінюються між вимірами, тому `raw/timing_e6.json` переписується лише з `--with-timing`.

| Файл | Зміст | Генератор |
|---|---|---|
| `data/annotations/*.csv`, `agreement_report.md` | сирі проходи `LLM_ANNOTATOR_1/2/3` + остаточні `ADJUDICATED` (944 / 18 / 202); узгодженість до узгодження; третій прохід (86 релевантність, 1 рівень) | `annotation_merge.py` (джерело — `.superpowers/sdd/annot/`, за відсутності — збережені сирі рядки) |
| `ranking_metrics.csv` | P@5, NDCG@10 на фіксованому пулі `pool-v1` (ранжування прогону обмежено пулом; відсутні в ранжуванні вакансії пулу дописуються в кінець і рахуються — 0), стабільність між сідами, зміни рангу щодо A | `chapter4_metrics.py` |
| `hypothesis_comparisons.csv` | парні різниці режимів (покриття, P@5, NDCG@10, рівень, невирішені групи, Top-5, повторні питання) з бутстреп-ДІ та знаковим тестом | `final_report.py` |
| `hypotheses.csv` | H1–H4: статус, первинна метрика, підсумок, обмеження | `final_report.py` |
| `ranking_per_candidate_differences.csv`, `level_confusion_pilot.csv` | покращення/погіршення за кандидатом (D проти A/B/C); матриці рівнів проти пілоту | `final_report.py` |
| `tables/table_4_1 … 4_7` (+ `4_4b_ablation`) | таблиці 4.1–4.7 (md + csv), українські заголовки; відсутні дані — статус і причина | `final_report.py` |
| `figures/*.svg`, `figures_data/fig_*.csv` | покриття за бюджетом, B/C/D, P@5/NDCG@10, неоцінені/невирішені, матриця рівнів, тривалість (заглушки), питання, збіг рівня | `final_report.py` |
| `raw/timing_e6.json` | E6: медіана/p95 детермінованих компонентів (matching, ранжування, rank_items, оцінювач, ринок); затримка LLM NOT_RUN | `timing_e6.py` |
| `chapter4_evidence_report.md`, `chapter4_results_summary.md`, `missing_evidence.md` | звіт етапу 12 (A–G), підсумок чисел, відсутні докази | `final_report.py` + `report_text.py` |
| `self_audit.json` | незалежне перерахування 6 ключових чисел із сирих файлів (лише stdlib) | `self_audit.py` |
| `thesis_changes_1_3.md` | таблиця змін розділів 1–3 (DOCX відсутній) | вручну |

Мітки: розмітка — `LLM_ANNOTATOR_PILOT` (LLM, не експерти-люди; корельовані між собою й з LLM-оцінювачами); кандидати — SIMULATED; Evaluator — заглушка. Продуктовий код не змінювався (`282f6fb`).
