# Таблиця 4.2. Умови експерименту

| Умова | Значення | Статус |
|---|---|---|
| Продуктовий код (commit) | 282f6fb2a286 | ЗАФІКСОВАНО |
| Режими | A INITIAL_PROFILE; B STATIC_INTERVIEW; C ADAPTIVE_NO_MARKET (дослідницький планувальник, не продукт); D FULL_COMPETENCEMATCH; Dfd — D без зміни складності (абляція) | ЗАФІКСОВАНО |
| Бюджети питань | 10, 20, 30, 50 | ЗАФІКСОВАНО |
| Сіди | 0, 1, 2 | ЗАФІКСОВАНО |
| Кандидати | 18 симульованих (python) | SIMULATED |
| Прогонів (suite modes) | 882 | SIMULATED |
| Interviewer / Evaluator | детерміновані заглушки (scripts.chapter4.realistic_runs.UaModel (Ukrainian difficulty word) over scripts.seniority_realistic.Model; noise scripts.seniority_realistic.Noise(seed)); реальна LLM не викликалась | SIMULATED |
| Модель кандидата | insensitive | SIMULATED |
| Політика рівнів | python-backend/v4 (WORKING_ASSUMPTION), min_confirming_turns=2 | ЗАФІКСОВАНО |
| Контролер складності | difficulty/v2 | ЗАФІКСОВАНО |
| Ранжування в експериментах | pure (2.15)+T_v/J_v+id | ЗАФІКСОВАНО |
| Ранжування на екрані результатів | confirmed_share first (owner decision, deviation from (2.15)) | ВІДХИЛЕННЯ ВІД (2.15); не впливає на експерименти |
| Версія промптів | 4a377e2a7eb4 | ЗАФІКСОВАНО |
| Ліміти інтерв'ю | тем ≤ 10, питань на тему ≤ 5, мінімум 2 | ЗАФІКСОВАНО |
| Перевірка однакових умов | {"profiles_checked": 18, "violations": [], "all_equal": true, "budgets_never_exceeded": true, "checked_keys": ["cohort_sha256", "prompt_version", "algorithm_version", "profile_snapshot_sha", "rubric_versions_sha (seeded rubric versions of the cohort)", "model_class (interview modes)", "caps 10/5/2"] | ПЕРЕВІРЕНО |
| Відтворюваність | {"probe_runs": 10, "hash_first": "eca6a8386e6af0ac", "hash_second": "eca6a8386e6af0ac", "identical": true} | ПЕРЕВІРЕНО |
| Налаштована LLM (не використовувалась) | openai_compatible / lmstudio-community/Qwen2.5-7B-Instruct-1M-GGUF, t=0.3 | NOT_RUN |
| Еталон для P@5/NDCG/рівня | пілотні мітки LLM-розмітників (LLM_ANNOTATOR_PILOT, ADJUDICATED), не експерти-люди | PILOT_LLM_ANNOTATOR |
