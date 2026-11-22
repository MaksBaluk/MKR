# Аудит набору вакансій (data/)

Версія: `ds-66dcff9404cc` (sha256 фікстур: `vacancies.json` 9bc11fcde8b1, `vacancies_real.json` 1a15d456f080, `vacancy_criteria.json` 9aa9e1fdefb7, `vacancy_sources.json` 30841da50c9c, `rubrics.json` a728ea45b247, `competencies.json` a98106cd3ebc).
Згенеровано `app/scripts/chapter4/data_package.py` з фікстур репозиторію (ті самі файли засіває `backend/seed.py`).

Походження вакансій наведено за приміткою власника про дані; технічні метадані імпорту збережені в репозиторії (поля import_version, retrieved_at, source_name).

## Склад

| Професія | Рівень вакансії | Вакансій |
|---|---|---|
| design | JUNIOR | 14 |
| design | LEAD | 7 |
| design | MIDDLE | 25 |
| design | SENIOR | 19 |
| marketing | JUNIOR | 15 |
| marketing | LEAD | 11 |
| marketing | MIDDLE | 30 |
| marketing | SENIOR | 18 |
| python | JUNIOR | 18 |
| python | LEAD | 9 |
| python | MIDDLE | 31 |
| python | SENIOR | 32 |

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

## Вимоги й пороги

- D_vga (`criterion_ids`) зберігаються разом із полем джерела правила (значення в репозиторії: `SYNTHETIC_RULE_V1`).
- Пороги τ: карта рівнів {1: 0.5, 2: 0.75, 3: 0.9} (`WORKING_ASSUMPTION_LEVEL_MAP`), `threshold_status` у vacancy_requirements.jsonl; порогів у тексті вакансій немає.
- ESCO не використовується для оцінок; скрапінгу в цьому кроці немає.

