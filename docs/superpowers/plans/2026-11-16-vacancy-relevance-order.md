# Порядок вакансій за релевантністю: перевірка і фіксація Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Гарантувати, що вакансії в результатах відсортовані за лексикографічним ключем релевантності (найбільш релевантні зверху), а відсоток є лише підписом, і закріпити це тестами.

**Architecture:** Сортування вже виконує `order(ranked)` у `backend/api/recommendations.py:43` за ключем `sort_key` з `backend/domain/ranking.py`. Фронтенд порядок не змінює. План перевіряє цей ланцюг від домену до UI, додає тести на порядок і прибирає ризики, що порядок зміниться після фільтрації.

**Tech Stack:** Python 3.12, FastAPI, pytest; React + TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-11-14-results-redesign-design.md`, `docs/tasks/MATH_SPEC.md` §5, `docs/superpowers/specs/2026-11-13-ranking-tiebreak-design.md`.

## Global Constraints

- Ключ сортування: `(-Z, -X, -L^M, -L^P, W^M, W^P, vacancy_id)`, як у `backend/domain/ranking.py` `sort_key`.
- Відсоток збігу (`confirmed_share`) не є ключем сортування і не є ймовірністю працевлаштування.
- Жодних `Match/Coverage/R` метрик у UI (`CLAUDE.md`).
- Фільтр `fitting` не змінює відносний порядок вакансій, які лишилися.

## Review Focus

1. Однакові ключі у двох вакансій: порядок визначає `vacancy_id` (стабільно, детерміновано).
2. Вакансія без жодної валідної вимоги (`NOT_EVALUABLE`): не потрапляє в список рейтингу, не отримує місця.
3. `LOW_INFORMATION` з високим відсотком не піднімається над `RANKED` з нижчим Z (Z має вищий пріоритет).
4. Фільтр `fitting=fitting` або `min_share` видаляє вакансії, але не переставляє решту.
5. Порожній список результатів (`total = 0`) не падає і повертає порожній `items`.

## Task 1: Закріпити порядок на бекенді

**Files:**
- Modify: `app/backend/api/recommendations.py` (тільки якщо тест покаже відхилення)
- Test: `app/tests/test_ranking_order.py` (новий)

**Interfaces:**
- Consumes: `rank_items(db, years_experience, snap, scores)` з `backend/api/recommendations.py:25`; `sort_key(r: VacancyRanking) -> tuple` з `backend/domain/ranking.py`.
- Produces: тести, що фіксують порядок `items` у відповіді `GET /api/v1/profiles/{id}/results?fitting=all`.

- [ ] **Step 1: Написати тест порядку.** Для фіксованого профілю з готовими результатами взяти `items` з `fitting=all` і перевірити, що `[(i["z"], i["x"], i["l_mandatory"], i["l_preferred"], -i["w_mandatory"], -i["w_preferred"]) ...]` не зростає за лексикографічним порівнянням з урахуванням правила напрямку (Z, X, L спадають; W зростають). Другий тест: порядок не змінюється після `fitting=fitting` для спільних вакансій.
- [ ] **Step 2: Запустити тест.** `cd app && uv run pytest tests/test_ranking_order.py -q`. Очікування: PASS, якщо порядок уже правильний. Якщо FAIL, перейти до Step 3.
- [ ] **Step 3: Виправити лише якщо тест упав.** Причину шукати в `rank_items` або `order`. Не змінювати `sort_key`.
- [ ] **Step 4: Повний прогін.** `cd app && uv run pytest -q`. Очікування: усі тести PASS.
- [ ] **Step 5: Коміт** (після схвалення користувача): `git add app/tests/test_ranking_order.py && git commit -m "test(api): pin lexicographic relevance order of results"`.

## Task 2: Фронтенд не змінює порядок

**Files:**
- Test: `app/frontend/src/lib/results.test.ts` (розширити)
- Read-only check: `app/frontend/src/screens/ResultsScreen.tsx` (рядки з `data.items.map`)

**Interfaces:**
- Consumes: `ProfileResults.items` з `app/frontend/src/types.ts`.
- Produces: тест-доказ, що UI рендерить `items` у тому самому порядку (жодного `sort` у компонентах результатів).

- [ ] **Step 1: Перевірити відсутність сортування.** `grep -n "\.sort(" app/frontend/src/screens/ResultsScreen.tsx app/frontend/src/components/*.tsx` має повернути лише сортування `competencies` у `CompetencySection` (не вакансії). Якщо знайдено сортування вакансій, видалити його.
- [ ] **Step 2: Додати тест**, що `ResultsScreen` не містить сортування вакансій: читання файлу і перевірка відсутності `items.sort` / `.sort(` поряд зі `items`. Очікування: PASS після Step 1.
- [ ] **Step 3: Запустити** `cd app/frontend && npm test`. Очікування: усі тести PASS.
- [ ] **Step 4: Коміт** (після схвалення): `git commit -m "test(frontend): results keep server relevance order"`.

## Task 3: Відсоток лише як підпис

**Files:**
- Read-only: `app/frontend/src/screens/ResultsScreen.tsx` (`FitBlock`, `fitLabel`)

- [ ] **Step 1: Перевірити**, що відсоток показано в `FitBlock` з підписом «Збіг профілю» і поясненням `FIT_EXPLANATION`, а заголовка сортування «за відсотком» немає. `grep -rn "за відсотком\|sort.*confirmed_share" app/frontend/src app/backend` має бути порожнім.
- [ ] **Step 2:** Якщо знайдено, видалити. Інакше зафіксувати в описі коміту, що перевірку пройдено без змін.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-11-16-vacancy-relevance-order.md`. Please review the plan. Which execution approach would you prefer?

- **Subagent-driven**: окремий виконавець і рев'ювер на кожну задачу. Найсуворіше, дорожче.
- **Native**: я виконую сам у цій сесії, потім один рев'ювер на всю гілку. Дешевше і швидше.

Рекомендую **Native**: задачі короткі і майже не залежать одна від одної, а найгірший наслідок помилки — неправильний порядок, який видно в тестах.
