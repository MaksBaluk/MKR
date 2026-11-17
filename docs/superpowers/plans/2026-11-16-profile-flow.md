# Профілі, співбесіда, результати, ринок: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline). Steps use checkbox syntax. Each task follows TDD: failing test, run, minimal code, run, no commit until the owner agrees.

**Goal:** Реалізувати погоджений флоу з `docs/superpowers/specs/2026-11-16-profile-flow-design.md`: стан застосунку залежить від активного профілю, сторінка профілю містить усе про профіль, результати і ринок змінені за описом.

**Architecture:** Профільні дані вже є в API (`/profiles`, `/profiles/{id}/attempts`, `/results`, `/self-ratings`). Фронтенд перестає читати legacy `useSession().interview` і бере стан співбесіди з активного профілю. Сортування результатів за відсотком робиться в ендпоінті результатів, математика в `backend/domain/ranking.py` не змінюється.

**Tech Stack:** FastAPI, SQLAlchemy, pytest; React, TypeScript, Vitest, recharts.

**Spec:** `docs/superpowers/specs/2026-11-16-profile-flow-design.md`, UI: `docs/superpowers/specs/2026-11-16-ux-ui-spec.md` (від UX/UI агента).

## Global Constraints

- Українські рядки, без транслітерації. Вакансії не підписуються як демо.
- Самооцінку змінює лише кандидат; оцінка LLM лише читання.
- Диплом (DOCX) не змінюється; розбіжність з розділом 2.3.5 фіксується в `docs/tasks/TODO.md`.
- Один профіль ≠ одна співбесіда: стан кроків, банер і замки рахуються по активному профілю.

## Review Focus

1. Профіль без спроб: кроки «Результати» і «Ринок» заблоковані, банера немає.
2. Нова спроба («Пройти ще раз») при наявних завершених: результати і ринок заблоковані до завершення.
3. Перемикання профілю під час відкритої співбесіди іншого профілю.
4. Нуль підтверджених вимог (збіг 0): вакансія в «Усіх», не в «Підходящих».
5. Вакансії з однаковим збігом: порядок детермінований (`z`, `x`, `vacancy_id`).

## Task 1: Профіль повертає стан спроб

**Files:** `app/backend/api/profiles.py` (`_profile_dict`), test `app/tests/test_profile_attempt_state.py`.

- [ ] Тест: профіль без спроб повертає `open_attempt=None` і `latest_finished_attempt=None`; після `start` повертає `open_attempt={id, cohort_id, status}`; після завершення спроби повертає `latest_finished_attempt={id, cohort_id}` і `open_attempt=None`.
- [ ] Запустити, переконатися, що падає (`KeyError`).
- [ ] Реалізувати поля в `_profile_dict`.
- [ ] `cd app && uv run pytest -q`.

## Task 2: Порядок і «підходить» за відсотком

**Files:** `app/backend/api/profiles.py` (`results`, `_with_fit`), test `app/tests/test_results_order_percent.py`; оновити `app/tests/test_results_fit.py`.

- [ ] Тест: `items` (fitting=all) впорядковані за `confirmed_share` спадаючи, при рівності за `z` спадаючи, `x` спадаючи, `vacancy_id`. `fits == (confirmed_share > 0)`.
- [ ] Запустити, переконатися, що падає.
- [ ] Реалізація: у `results` відсортувати `items` перед фільтрацією; `fits = item["confirmed_share"] > 0`. Позначка провалу обов'язкової вимоги лишається в `reasons`.
- [ ] Повний `pytest`.

## Task 3: Ендпоінт даних для графіків ринку

**Files:** `app/backend/api/market.py`, test `app/tests/test_market_overview.py`.

- [ ] Тест `GET /market/overview?track=python`: повертає `seniority` (кількість вакансій за рівнем), `work_mode`, `salary` (min, avg, max за рівнем, лише вакансії з зарплатою), `requirement_kinds` (для кожної дії: скільки вакансій мають її як обов'язкову і як бажану). Невідомий трек → 422. Порожній трек → порожні списки.
- [ ] Запустити, падає.
- [ ] Реалізація: групування одним запитом на показник.
- [ ] Повний `pytest`.

## Task 4: Стан співбесіди з активного профілю (фронтенд)

**Files:** `app/frontend/src/lib/profileInterview.ts`, test `profileInterview.test.ts`; `types.ts`; `routes.tsx`; `components/AppShell.tsx`; `screens/WelcomeScreen.tsx`.

- [ ] Тест `interviewFromProfile(p)`: `open_attempt` → `{id, cohort_id, status:'active'}`; інакше `latest_finished_attempt` → `finished`; інакше `null`.
- [ ] Реалізація; замінити `useSession().interview` в `routes.tsx` (ProfilePage, ResultsPage-обгортка, AppShell) і `WelcomeScreen` на значення з `useActiveProfile().active`.
- [ ] Перевірити `npm run typecheck && npm test`.

## Task 5: Сторінка профілю

**Files:** `app/frontend/src/screens/ProfileScreen.tsx` (переписати), `routes.tsx`, `screens/ProfilesScreen.tsx`.

- [ ] Тести helper-ів: `attemptRows(attempts)` (порядок, підписи статусів).
- [ ] Реалізація за `ux-ui-spec`: дані профілю (`PUT /profiles/{id}`), самооцінка з `profileId`, шкала LLM і порівняння (перенесено з результатів), історія спроб, кнопка старту/«Пройти ще раз» через `useStartAttempt`. Створення профілю веде на `/profile`.
- [ ] `typecheck`, `npm test`, `build`.

## Task 6: Результати

**Files:** `app/frontend/src/screens/ResultsScreen.tsx`.

- [ ] Блок «Ваші компетентності» справа, вакансії зліва, прибрати `ComparisonSection`. Картка: відсоток, позначка «Не підходить» з першими двома прогалинами.

## Task 7: Профіль ринку з графіками

**Files:** `app/frontend/src/components/MarketCharts.tsx` (нові), `lib/marketOverview.ts` + test, `screens/MarketScreen.tsx`.

- [ ] Тести helper-ів форматування даних для кожного графіка (порожній вхід, сума часток).
- [ ] Графіки: рівні, формат роботи, зарплатні вилки, обов'язкове проти бажаного, радар «ваш рівень проти ринку». Таблиці-альтернативи.

## Task 8: Налаштування (тема)

**Files:** `app/frontend/src/lib/theme.ts` + test, `screens/SettingsScreen.tsx`, `routes.tsx`, `lib/navigation.ts` (`settings` → `/settings`), токени темної теми в `tokens.css`.

- [ ] Тест: `resolveTheme(stored, systemDark)`; збереження в `localStorage` з `try/catch`.
- [ ] Реалізація перемикача світла / темна / системна.

## Task 9: Перевірка

- [ ] `cd app && uv run pytest -q`; `cd app/frontend && npm run typecheck && npm test && npm run build`; `docker compose -f compose.yaml up --build -d`; прохід у браузері: профіль → співбесіда → результати → ринок → налаштування, на 1366 і 375 px.
- [ ] Оновити `docs/tasks/TODO.md` і `STATUS.md`.
