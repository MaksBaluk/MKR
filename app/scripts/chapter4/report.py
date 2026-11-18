"""Compose chapter4_evidence_report.md from the generated artifacts so every number matches the files."""
from __future__ import annotations

import collections
import csv
import json
import statistics as st

from scripts.chapter4.common import APP, OUT


def rows(name):
    return list(csv.DictReader(open(OUT / name, encoding="utf-8")))


def build() -> str:
    runs, ds, math, ranks = rows("experiment_runs.csv"), rows("dataset_summary.csv"), rows("math_validation.csv"), rows("ranking_results.csv")
    man = json.load(open(OUT / "experiment_manifest.json"))
    sc = json.load(open(OUT / "adaptivity_scenarios.json"))["summary"]
    imp = json.load(open(APP / "fixtures" / "vacancies_real_import_report.json"))
    env_sha = next(l for l in open(OUT / "environment.md", encoding="utf-8") if "Commit SHA" in l).strip()[2:]
    by = collections.defaultdict(list)
    for r in runs:
        by[r["config"]].append(r)
    mean = lambda v, c: st.mean(float(x[c]) for x in v if x[c] != "")
    names = {"A": "A — INITIAL_PROFILE", "B": "B — STATIC_INTERVIEW", "C": "C — ADAPTIVE (повний)", "C-difficulty": "C без адаптації складності",
             "C-followup": "C без цільових уточнень", "C-topics": "C без адаптивного вибору тем"}
    cfg = [f"| {names[k]} | {len(by[k])} | {mean(by[k], 'n_questions'):.1f} | {mean(by[k], 'n_topics'):.1f} | {mean(by[k], 'n_assessed_criteria'):.1f} | "
           f"{mean(by[k], 'criterion_coverage'):.3f} | {mean(by[k], 'unresolved_requirements_rate'):.3f} | {mean(by[k], 'llm_calls'):.0f} |" for k in names]
    ds_rows = [f"| {r['track']} | {r['source_type'] if r['source_type'] != 'ALL' else 'усі'} | {r['vacancies']} | {r['unique_competencies']} | {r['mandatory_groups']} | "
               f"{r['desired_groups']} | {r['or_groups']} | {r['level_1']}/{r['level_2']}/{r['level_3']} | {r['mean_criteria_per_requirement']} |" for r in ds]
    total = sum(int(r["vacancies"]) for r in ds if r["source_type"] == "ALL")
    real = sum(int(r["vacancies"]) for r in ds if r["source_type"] == "REAL_IMPORTED")
    per_run = collections.defaultdict(list)
    for r in ranks:
        per_run[(r["config"], r["candidate_id"])].append(r)
    inter = [v for k, v in per_run.items() if k[0] != "A"]
    inversions = sum(any(int(a["z"]) < int(b["z"]) for i, a in enumerate(sorted(v, key=lambda r: int(r["rank_results_screen"]))) for b in sorted(v, key=lambda r: int(r["rank_results_screen"]))[i + 1:]) for v in inter)
    z2 = sum(1 for r in ranks if r["z"] == "2")
    imp_lines = "\n".join(f"| {i['track']} | {i['listed']} | {i['fetched']} | {i['accepted']} | {sum(i['rejected'].values()) and i['fetched'] - i['accepted']} |" for i in imp)
    ok = sum(r["status"] == "PASS" for r in math)
    return f'''# Підсумковий звіт доказів для розділу 4 (CompetenceMatch)

Це не текст розділу 4, а перелік перевірених фактів, команд і файлів-доказів. Дата: 2026-11-18. {env_sha}
Робоче дерево **не чисте** (виправлення аудиту, імпорт вакансій та цей пакет не закомічені), тому SHA `HEAD` не ідентифікує код повністю: використовуйте хеш diff з `environment.md`. Усі файли, крім рукописних (`test_results.md`, `failure_cases.md`, `expert_annotation_templates/annotation_protocol.md`), генеруються командою `cd app && uv run python -m scripts.chapter4.build_all` (без мережі й без реальної LLM).

## Стан виправлень аудиту (перевірено)

| Пункт аудиту | Стан | Доказ |
|---|---|---|
| `D_vga` (критерії вимоги) | виправлено: явні `criterion_ids` на альтернативі, у знімку когорти, не «вся рубрика» | `tests/test_dvga.py`, `math_validation.csv` (C07, C08, U04), міграція 0013 в PostgreSQL |
| `τ` | робоче припущення з явним джерелом `WORKING_ASSUMPTION_LEVEL_MAP`; невідомий рівень без τ → `UNRESOLVED` | `math_validation.csv` (T50, T75, T90, U05) |
| `null`/off-topic не стирають оцінки | виправлено, історія ревізій зберігається | `tests/test_audit_regressions.py`, `math_validation.csv` V01, V02 |
| Валідація Evaluator (цитати, дублікати, оцінка без доказу) | виправлено | `math_validation.csv` E01–E06 |
| Лексикографічне сортування (2.15) | **частково**: доменне ранжування й `/recommendations` — чистий (2.15); **екран результатів сортує за відсотком** (рішення власника, відхилення від диплома) | `ranking_results.csv` (`rank_215` проти `rank_results_screen`), `failure_cases.md` п. 6 |

## ПІДТВЕРДЖЕНО (реальні запуски коду, з командами й файлами)

1. **Середовище й версії** — `environment.md`.
2. **Структура датасету** — `dataset_summary.csv`. Каталог містить {total} вакансій: **{real} реальних** (`REAL_IMPORTED`, публічні оголошення Djinni, отримано 2026-11-18, із `source_url`) і по 90 вигаданих (`DEMO_CURATED`, `SYNTHETIC_GENERATED`). Вигадані вакансії не є реальними оголошеннями Djinni; в інтерфейсі вони підписані «Приклад» (підказка пояснює, що це вигадана вакансія), а «Djinni» отримують лише імпортовані.

| Напрям | Джерело | Вакансій | Унік. компетентностей | Обов'язкових груп | Бажаних груп | OR-груп | Вимог рівня 1/2/3 | Сер. критеріїв на вимогу (D_vga) |
|---|---|---|---|---|---|---|---|---|
{chr(10).join(ds_rows)}

   Рубрик 60 (20 на напрям), по 3–5 критеріїв (`CURATED_TEMPLATE`, без експертної перевірки). Вигадані вакансії: детермінований скрипт із фіксованим seed (`scripts/generate_fixtures*.py`), без скрейпінгу. Реальні: `scripts/import_djinni.py` (власник підтвердив дозвіл Djinni; перевірено `robots.txt`; 1 запит на 2 с; зберігаються структуровані поля, URL, дата й дослівні фрагменти вимог, не повний текст і не контакти). Результат імпорту:

| Напрям | У списках | Завантажено | Прийнято | Відхилено валідацією |
|---|---|---|---|---|
{imp_lines}

   Відхилення — оголошення, де після зіставлення з 20 curated-компетентностями напряму лишилось < 3 груп вимог, < 2 обов'язкових або < 3 різних компетентностей. Пороги не знижувались, щоб збільшити вибірку; тому для marketing і design реальних вакансій мало (реальні оголошення рідко називають ці компетентності так, як каталог). **Обмеження репрезентативності:** каталог не випадкова вибірка ринку (перші сторінки публічного списку Djinni за ключовим словом на одну дату); зіставлення вимог з компетентностями — таблиця аліасів `djinni-import-v1`, а не експертна нормалізація; рівні вимог (`SENIORITY_RULE_V1`), D_vga (`SYNTHETIC_RULE_V1`) і τ — правила та припущення, а не дані роботодавця; `work_mode=OFFICE` для будь-якого не-remote оголошення (HYBRID не розрізняється).
3. **Математична коректність формул розділу 2 на контрольних прикладах**: {ok} із {len(math)} PASS (`math_validation.csv`). Це перевірка реалізації формул, а не якості системи.
4. **Відтворюваність**: два незалежні батчі дають однаковий нормалізований хеш `{man['reproducibility']['normalized_sha256_batch1']}`; перерахунок рейтингу без LLM (`rerank`) збігається зі збереженим порядком для всіх {man['run_count']} запусків (`experiment_manifest.json`).
5. **Рівні умови режимів** (одна когорта sha256, одні версії рубрик, однаковий бюджет {man['total_budget']}, однакова «модель», версія алгоритму, профіль) — `experiment_manifest.json` → `equal_conditions_check`: усе `true` для трьох кандидатів. Когорта python: {next(int(r['vacancies']) for r in ds if r['track']=='python' and r['source_type']=='ALL')} вакансій (з них {next(int(r['vacancies']) for r in ds if r['track']=='python' and r['source_type']=='REAL_IMPORTED')} реальних).
6. **Інженерна надійність** — `test_results.md`: 575 backend-тестів, 155 frontend-тестів, typecheck, build, 7 E2E-тестів Playwright (Chromium, Docker-стек), 26 цільових надійнісних тестів, 8 перевірок на живій PostgreSQL, міграції до 0014.
7. **Шаблони експертної розмітки й формули узгодженості** (`expert_annotation_templates/`, `criterion_agreement` + `agreement_report` з тестами на ручних прикладах).

## ОБМЕЖЕНО (симуляції, заглушки, неповні прогони)

Усі результати нижче мають `answer_source=SIMULATED`, `evaluator=SIMULATED_STUB`, **реальних LLM-викликів 0**. Вони перевіряють поведінку планувальника, контролера складності, цільових уточнень і ранжування, але **не** професійну точність, не якість Evaluator і не поведінку реальних кандидатів. Когорта містить і реальні, і вигадані вакансії; результати за джерелами не розділялись.

1. **Порівняння режимів A/B/C та абляцій** (3 імітовані кандидати; по 1 запуску; бюджет {man['total_budget']} питань; `experiment_runs.csv`, `criterion_results.csv`, `ranking_results.csv`, `interview_turns.jsonl`, `evaluation_metrics.csv`). Середнє за кандидатами:

| Конфігурація | Запусків | Питань | Тем | Оцінено критеріїв | Criterion Coverage | Unresolved Rate | Викликів LLM-ролей |
|---|---|---|---|---|---|---|---|
{chr(10).join(cfg)}

   Coverage = частка достатньо підтверджених критеріїв серед 80 релевантних критеріїв когорти; Unresolved Rate = частка нерозв'язаних вимог у рейтингу. У цій симуляції режими з уточненнями покривають менше тем при рівному бюджеті; це наслідок імітованого оцінювача, а не доказ переваги чи недоліку методу.
2. **Сценарії адаптивності** (`adaptivity_scenarios.md/.json`): {', '.join(f'{k} {v}' for k, v in sc.items())}. S1 вдалось продемонструвати лише з відповіддю, що оцінює всі критерії теми (`failure_cases.md` п. 9). Послідовність BASIC→INTERMEDIATE→ADVANCED усередині теми покрита юніт-тестом `tests/test_difficulty_flow.py::test_junior_strong_answers_progress_basic_to_advanced`.
3. **Метрики без еталонів** (`evaluation_metrics.csv`): обчислено лише безеталонні (coverage, unresolved rate, кількість питань, тривалість, помилки). `data_status=NO_EXPERT_LABELS`. Precision@5, NDCG@10 і MAE **не обчислено**. Формули метрик перевірено на синтетичних контрольних прикладах у `tests/test_metrics.py` (окремо від емпіричної якості).
4. **Порядок на екрані результатів проти (2.15)**: у {inversions} із {len(inter)} інтерв'ю-запусків хоча б одна вакансія з нижчим `Z` стоїть на екрані вище за вакансію з вищим `Z`; `Z=2` досягнуто в {z2} рядках рейтингів (12 питань).
5. **Тривалість і кількість викликів**: у імітації кожне питання = 2 виклики (Interviewer + Evaluator), у режимі A викликів 0 (`llm_calls`, `llm_wait_s`, `total_s`). Час імітованих викликів майже нульовий і не відображає реальну LLM.

## НЕ ДОСЛІДЖЕНО (потрібні експерти, жива LLM, додаткові дані)

| Що | Чого бракує |
|---|---|
| Precision@5, NDCG@10 для режимів | незалежні мітки релевантності ≥10 вакансій на кандидата, 2 розмітники + арбітр (`expert_annotation_templates/annotation_protocol.md`). Код не може «виправити» це: потрібні живі експерти |
| Evaluator MAE, міжекспертна узгодженість критеріїв | незалежні критеріальні оцінки експертів на реальних відповідях |
| Якість адаптивності для реальних людей | реальні кандидати (≥ 20) зі згодою; живі відповіді |
| Поведінка реальної LLM: відхилення валідації, тайм-аути, вартість, тривалість | запуск на реальному провайдері; потрібне ваше погодження вартості (нижче) |
| Повний набір тестів на PostgreSQL | лише smoke-перевірка та міграції |
| Реальний каталог достатнього розміру для marketing і design | лише 14 і 5 реальних вакансій; потрібне розширення таблиці аліасів або інші джерела з дозволом |

## Оцінка вартості реальних LLM-запусків (без запуску; потребує погодження)

Виміряно за промптами продукту на симульованому інтерв'ю з 12 питань: вхід Interviewer ≈ 6.2 тис. символів (системний промпт 5.2 + дані 1.0), вхід Evaluator ≈ 10.0 тис. (5.4 + 4.6), вивід заглушки Evaluator ≈ 1.2 тис.; реальна відповідь довша. Токени ≈ символи / 3 (груба оцінка):

| Показник | Оцінка |
|---|---|
| На 1 питання (Interviewer + Evaluator) | ≈ 5.4 тис. токенів входу + ≈ 0.85 тис. виходу (нижня межа для моделі без reasoning) |
| На 1 інтерв'ю (12 питань, 24 виклики) | ≈ 65 тис. входу + ≈ 10 тис. виходу |
| Мінімальне порівняння B проти C, 20 кандидатів (40 інтерв'ю) | ≈ 2.6 млн входу + ≈ 0.4 млн виходу |
| Повний дизайн з абляціями (5 конфігурацій × 20 кандидатів = 100 інтерв'ю) | ≈ 6.5 млн входу + ≈ 1.0 млн виходу |

Вартість у грошах = токени × тариф провайдера; тарифу в конфігурації немає, тому суму не наводжу. Для reasoning-моделей вихід може бути в 5–10 разів більшим. Локальна модель не коштує грошей, але потребує ≥ 8–10 ГБ пам'яті (`failure_cases.md` п. 13). **Жодного платного або реального LLM-виклику не зроблено; для запуску потрібне ваше погодження провайдера, моделі й бюджету.**

## Що вже можна обґрунтовано написати в розділі 4, а що ні

| Елемент розділу 4 | Можна зараз? | На чому ґрунтується |
|---|---|---|
| Опис експериментального середовища й конфігурації | **Так** (з приміткою про незакомічені зміни) | `environment.md` |
| Таблиця структури каталогу (реальні й синтетичні окремо) | **Так** | `dataset_summary.csv`, `vacancies_real_import_report.json` |
| Опис методу імпорту реальних вакансій і його обмежень | **Так** | `scripts/import_djinni.py`, `backend/domain/vacancy_import.py`, `tests/test_vacancy_import.py` |
| Таблиця контрольних математичних перевірок реалізації | **Так** | `math_validation.csv`, `tests/` |
| Опис відтворюваності, рівних умов режимів | **Так** | `experiment_manifest.json` |
| Опис інженерної надійності | **Так** (SQLite, smoke PostgreSQL, 7 E2E у Chromium) | `test_results.md` |
| Демонстрація механізмів адаптивності (шість сценаріїв) | **Так, як ілюстрація на імітації**, із застереженням щодо S1 | `adaptivity_scenarios.md` |
| Рисунок/таблиця порівняння режимів A/B/C | **Лише як перевірка конвеєра на імітації**, без висновків про якість | `evaluation_metrics.csv`, `experiment_runs.csv` |
| Рисунок «абляція: внесок механізмів» | **Лише як поведінка конвеєра на імітації** | те саме |
| Висновок «адаптивний режим кращий за статичний» | **Ні** | немає незалежних міток і реальних кандидатів |
| Precision@5 / NDCG@10 порівняння режимів | **Ні** | немає експертної релевантності |
| MAE Evaluator, узгодженість експертів | **Ні** (лише шаблони й формули) | немає експертних оцінок |
| Висновки про професійну точність | **Ні** | імітовані відповіді |
| Висновки про реальний ринок | **Ні** | 49 реальних вакансій на одну дату, шаблонне зіставлення |
| Висновки про поведінку реальної LLM | **Ні** | реальних запусків не було |

## Що потребує вашого рішення

1. Відхилення екрана результатів від (2.15) потрібно описати в розділі 2 або повернути чистий ключ (`failure_cases.md` п. 6).
2. Закомітити виправлення аудиту, імпорт і пакет, щоб SHA однозначно ідентифікував код.
3. Погодити провайдера, модель і бюджет, якщо потрібні реальні LLM-прогони.
4. Експертна розмітка (потрібні розмітники й реальні кандидати) для Precision@5, NDCG@10 і MAE.
'''


if __name__ == "__main__":
    (OUT / "chapter4_evidence_report.md").write_text(build(), encoding="utf-8")
    print("report written")
