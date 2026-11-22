# Аудит набору вакансій (data/)

Версія: `ds-66dcff9404cc` (sha256 фікстур: `vacancies.json` 9bc11fcde8b1, `vacancies_real.json` 1a15d456f080, `vacancy_criteria.json` 9aa9e1fdefb7, `vacancy_sources.json` 30841da50c9c, `rubrics.json` a728ea45b247, `competencies.json` a98106cd3ebc).
Згенеровано `app/scripts/chapter4/data_package.py` з фікстур репозиторію (ті самі файли засіває `backend/seed.py`).

## Склад

| Професія | Тип джерела | Вакансій |
|---|---|---|
| design | CURATED | 30 |
| design | REAL | 5 |
| design | SYNTHETIC | 30 |
| marketing | CURATED | 30 |
| marketing | REAL | 14 |
| marketing | SYNTHETIC | 30 |
| python | CURATED | 30 |
| python | REAL | 30 |
| python | SYNTHETIC | 30 |

Усього вакансій: 229; груп вимог: 2056 (обов'язкових 1470, бажаних 586); OR-груп: 274; альтернатив: 2371.

## Перевірки

| Перевірка | Результат |
|---|---|
| Унікальність vacancy_id | PASS |
| Однакові тексти опису | 0 вакансій у 0 групах дублікатів |
| Однакові (назва, компанія) | 1 пар |
| Група без альтернатив | 0 |
| Вакансія без обов'язкових груп | 0 |
| competency_id відсутній у competencies.json | немає |
| competency_id без засіяної рубрики | немає |
| criterion_ids (D_vga) поза рубрикою своєї компетентності | 0 |
| Альтернатив без D_vga | 0 |
| Логіка | групи між собою — AND; альтернативи в групі — OR (`eval_group`: SATISFIED, якщо задовольняє будь-яка; FAILED, лише якщо провалено всі) |

## Походження і застереження

- `REAL` (49): короткі описи, складені з публічних оголошень Djinni (`djinni-import-v1`, `retrieved_at` у vacancies.csv). Рівень вакансії для них визначено правилом `SENIORITY_RULE_V1`, а не роботодавцем.
- `CURATED` і `SYNTHETIC` (180): вигадані/адаптовані приклади репозиторію; зовнішнього джерела немає, тому `source_reference` = фікстура.
- **Знахідка аудиту (DATASET-1).** Поле відображення `source_name` (fixtures/vacancy_sources.json, assignment `OWNER_STATEMENT_CATALOG_LEVEL`) присвоює 180 не-реальним вакансіям назви сайтів: DOU: 21, robota.ua: 83, work.ua: 76. За приміткою файлу це «заява власника проєкту на рівні каталогу (дані адаптовано для ілюстрації)», а не походження конкретного оголошення. Ці вакансії не можна описувати як отримані з robota.ua/work.ua/DOU; у vacancies.csv вони мають `source_type` CURATED/SYNTHETIC, мітку збережено в `repo_display_source_name` і позначено `provenance_flag`. Потрібна синхронізація UI/тексту диплома.
- **D_vga.** Усі 2371 альтернатив мають criterion_ids з правилом `SYNTHETIC_RULE_V1`, зокрема 332 альтернатив REAL-вакансій: критерії рубрик визначено правилом репозиторію, а не текстом роботодавця.
- **Пороги τ.** Значення з карти рівнів {1: 0.5, 2: 0.75, 3: 0.9} (`WORKING_ASSUMPTION_LEVEL_MAP`): у вакансіях немає порогів роботодавця, тому `threshold_status` = робоче припущення.
- ESCO не використовується для оцінок; скрапінгу в цьому кроці немає.

