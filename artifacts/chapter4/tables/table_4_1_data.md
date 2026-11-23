# Таблиця 4.1. Характеристики даних

| Показник | Значення | Статус | Джерело |
|---|---|---|---|
| Професійні напрями (треки) | design, marketing, python | ВИМІРЯНО | dataset_summary.csv |
| Вакансій у когорті, design | 65 | ВИМІРЯНО | dataset_summary.csv |
| Рубрик / критеріїв, design | 20 / 75 | ВИМІРЯНО | dataset_summary.csv |
| Груп вимог: обов'язкових / бажаних / АБО, design | 429 / 183 / 78 | ВИМІРЯНО | dataset_summary.csv |
| Розподіл рівнів вакансій, design | {JUNIOR: 14, LEAD: 7, MIDDLE: 25, SENIOR: 19} | ВИМІРЯНО | dataset_summary.csv |
| Вакансій у когорті, marketing | 74 | ВИМІРЯНО | dataset_summary.csv |
| Рубрик / критеріїв, marketing | 20 / 79 | ВИМІРЯНО | dataset_summary.csv |
| Груп вимог: обов'язкових / бажаних / АБО, marketing | 475 / 195 / 90 | ВИМІРЯНО | dataset_summary.csv |
| Розподіл рівнів вакансій, marketing | {JUNIOR: 15, LEAD: 11, MIDDLE: 30, SENIOR: 18} | ВИМІРЯНО | dataset_summary.csv |
| Вакансій у когорті, python | 90 | ВИМІРЯНО | dataset_summary.csv |
| Рубрик / критеріїв, python | 20 / 80 | ВИМІРЯНО | dataset_summary.csv |
| Груп вимог: обов'язкових / бажаних / АБО, python | 566 / 208 / 106 | ВИМІРЯНО | dataset_summary.csv |
| Розподіл рівнів вакансій, python | {JUNIOR: 18, LEAD: 9, MIDDLE: 31, SENIOR: 32} | ВИМІРЯНО | dataset_summary.csv |
| Кандидати (експерименти — лише python) | 18 (бажаний рівень: junior 5, middle 6, senior 7) | SIMULATED | data/candidates.csv |
| Походження кандидатів | симульовані профілі, створені LLM; не реальні люди | SIMULATED | data/candidates.csv (data_origin) |
| Походження вакансій | Походження вакансій наведено за приміткою власника про дані; технічні метадані імпорту збережені в репозиторії (поля import_version, retrieved_at, source_name) | ЗА ПРИМІТКОЮ ВЛАСНИКА | data/dataset_audit.md |
| Версія набору даних | ds-66dcff9404cc | ЗАФІКСОВАНО | data/data_manifest.json |
| Альтернатив вимог (усі треки) | 2371 | ВИМІРЯНО | data/data_manifest.json |
| Пул вакансій для розмітки (пари кандидат–вакансія) | 944 | ЗАФІКСОВАНО (pool-v1) | data/annotation_inputs/vacancy_pool.csv |
| Рядки пілотної розмітки: релевантність / рівень / критерії | 2918 / 55 / 606 (ADJUDICATED: 944 / 18 / 202) | PILOT_LLM_ANNOTATOR | data/annotations/ |
| Експертна розмітка людьми | відсутня | NO_GROUND_TRUTH | missing_evidence.md |
