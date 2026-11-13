# Results redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Results show only fitting vacancies by default with reasons, an «Усі вакансії» toggle shows the rest, post-interview scores sit beside self-ratings, vacancies become a top-level section outside the stepper, and the market page shows per-track competency distribution.

**Architecture:** Backend adds a fit flag and reasons to profile results, a post-interview comparison field on competencies, and one market distribution endpoint. Frontend reworks the results screen, nav, and market page. Ranking order is unchanged.

**Tech Stack:** FastAPI, SQLAlchemy, pytest; React 19, Tailwind v4, react-router, recharts (already lazy-loaded), vitest.

**Spec:** `docs/superpowers/specs/2026-11-14-results-redesign-design.md`.

## Global Constraints
- Fit threshold: `FIT_THRESHOLD_PERCENT = 40` (owner may change it; one constant).
- Fitting = `z != 0` AND `confirmed_share >= FIT_THRESHOLD_PERCENT`.
- Label «Збіг профілю N%» and the honesty tooltip stay. Never «ймовірність працевлаштування» or Match/Coverage/R.
- Market distribution shows shares labelled «частка вакансій у добірці»; no raw counts in the UI.
- Ukrainian UI strings. No new heavy dependencies.
- Do not change migrations, fixtures, prompts, or graphs.

## Review Focus
1. Profile with no finished attempt: results return `has_results: false`, no fitting list, no crash.
2. Zero active vacancies in a track: distribution endpoint returns an empty list, not a division-by-zero error.
3. Competency with interview score but no self-rating (and the reverse): both sides render, no fake value.
4. Toggle «Усі вакансії» with zero non-fitting vacancies: explicit empty message, not a blank list.
5. Vacancies page reachable without any interview: no redirect, no locked state.

---

### Task 1: Backend fit flag and reasons on profile results
**Files:**
- Modify: `app/backend/api/profiles.py` (results endpoint, item builder)
- Test: `app/tests/test_results_fit.py`

**Interfaces:**
- Consumes: `rank_items` in `app/backend/api/recommendations.py`, `explain_vacancy` in `app/backend/domain/core_flow.py`.
- Produces: `FIT_THRESHOLD_PERCENT: int = 40` (module constant in `profiles.py`); each result item gains `fits: bool` and `reasons: list[str]`; `GET /profiles/{id}/results` accepts `fitting: str = "fitting"` with values `fitting | all | nonfitting` (422 otherwise). `total` counts the filtered set; `fitting_total` and `all_total` are returned alongside.

- [ ] **Step 1: Write the failing tests** in `app/tests/test_results_fit.py`:
  - `fitting` default returns only items with `fits=True` and `confirmed_share >= 40`.
  - `fitting=all` returns every cohort vacancy; `fitting=nonfitting` returns only `fits=False`.
  - `fits` is False when `z == 0` even if share is ≥ 40.
  - `reasons` is a non-empty list for every item (strengths first, then gaps, then «Не оцінено: N вимог»).
  - A profile with no finished attempt returns `has_results: false` with `fitting_total == 0` and `all_total == 0`.
  - `fitting=bogus` returns 422.
- [ ] **Step 2: Run** `cd app && uv run pytest tests/test_results_fit.py -q` and confirm failures.
- [ ] **Step 3: Implement.** Add `FIT_THRESHOLD_PERCENT`. Compute `fits` per item in the results builder after `rank_items`. Build `reasons` from `strengths`, `gaps`, and `unknown_count`. Apply the `fitting` filter before pagination. Keep ranking order.
- [ ] **Step 4: Run** the same command; expect pass. Then `cd app && uv run pytest -q` (full suite, all pass).
- [ ] **Step 5: Commit** `git add app/backend/api/profiles.py app/tests/test_results_fit.py && git commit -m "feat(api): fit flag, reasons and fitting filter on profile results" -m "Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>"`

### Task 2: Backend post-interview competency comparison
**Files:**
- Modify: `app/backend/api/profiles.py` (`_competencies` and results response)
- Test: `app/tests/test_results_competencies.py`

**Interfaces:**
- Consumes: `_competencies(db, iv)` and self-ratings of the profile (`latest_self_ratings` helper in `profiles.py` or equivalent).
- Produces: each entry of `competencies` gains `interview_score: float | None` (LLM, read-only) and `self_rating: float | None` (editable, latest for this profile), keeping the existing `score` field as an alias of `interview_score`.

- [ ] **Step 1: Write failing tests** in `app/tests/test_results_competencies.py`:
  - An action with an interview score and a self-rating returns both values.
  - An action with only a self-rating returns `interview_score: None`.
  - An action with only an interview score returns `self_rating: None`.
  - Self-rating from another profile of the same user does not appear.
- [ ] **Step 2: Run** `cd app && uv run pytest tests/test_results_competencies.py -q`; confirm failures.
- [ ] **Step 3: Implement** the two fields as specified. Keep `score` as the same value as `interview_score`.
- [ ] **Step 4: Run** the focused file, then `cd app && uv run pytest -q`; all pass.
- [ ] **Step 5: Commit** `git commit -m "feat(api): interview score beside self-rating on competencies" -m "Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>"`

### Task 3: Backend market distribution endpoint
**Files:**
- Create: `app/backend/api/market.py`
- Modify: `app/backend/main.py` (mount router under `/api/v1`)
- Test: `app/tests/test_market_distribution.py`

**Interfaces:**
- Consumes: `Vacancy`, `RequirementGroup`, `RequirementAlternative`, `Competency` models; `compute_market` (domain) is NOT used here because it returns internal F/I values, not shares for display.
- Produces: `GET /api/v1/market/distribution?track=python|marketing|design` returning `{track, vacancies_total, items: [{action_id, name, share_percent: int}]}`, where `share_percent = round(100 * vacancies_containing / vacancies_total)`, items sorted by `share_percent` desc then `action_id` asc. Empty track returns `vacancies_total: 0, items: []`. No auth required (public catalog, like `/vacancies`).

- [ ] **Step 1: Write failing tests** in `app/tests/test_market_distribution.py`:
  - Share of an action equals the rounded percentage of active vacancies of the track that contain it (any alternative counts as contained only if it is in some group of the vacancy; count each vacancy once).
  - Sorting: desc share then id asc.
  - Unknown track → 422; track with no vacancies → empty items, no error.
  - Inactive vacancies excluded.
- [ ] **Step 2: Run** `cd app && uv run pytest tests/test_market_distribution.py -q`; confirm failures.
- [ ] **Step 3: Implement** the router and mount it. Use one grouped query, not per-vacancy loops.
- [ ] **Step 4: Run** the focused file, then `cd app && uv run pytest -q`; all pass.
- [ ] **Step 5: Commit** `git add app/backend/api/market.py app/backend/main.py app/tests/test_market_distribution.py && git commit -m "feat(api): per-track competency distribution for the market page" -m "Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>"`

### Task 4: Frontend results screen: fitting default, all-vacancies toggle, comparison
**Files:**
- Modify: `app/frontend/src/screens/ResultsScreen.tsx` (or the current results page component after Task 10/11 changes)
- Modify: `app/frontend/src/lib/results.ts` (URL state gains `fitting`)
- Modify: `app/frontend/src/types.ts` (new fields `fits`, `reasons`, `interview_score`, `self_rating`, `fitting_total`, `all_total`)
- Test: `app/frontend/src/lib/results.test.ts` (extend)

**Interfaces:**
- Consumes: Task 1 query param `fitting`, Task 2 fields.
- Produces: pure helper `fittingParam(value: string | null): 'fitting' | 'all' | 'nonfitting'` (invalid → `'fitting'`), and `comparisonRows(competencies)` returning `{name, interview: number | null, self: number | null}[]` in server order.

- [ ] **Step 1: Write failing vitest tests** in `results.test.ts`: `fittingParam` defaults and invalid values; `comparisonRows` keeps order and passes nulls through without inventing values.
- [ ] **Step 2: Run** `cd app/frontend && npm test`; confirm failures.
- [ ] **Step 3: Implement.** Results page: default list is fitting only; a segmented control «Підходящі (N)» / «Усі вакансії (M)» switches `fitting` in the URL (`replace`, not push). Non-fitting cards show «Не підходить» and their first two gaps. Each card lists `reasons`. Add a «Порівняння: співбесіда і самооцінка» section (LLM score read-only, self-rating shown separately with its own label, never merged). Empty toggle state shows an explicit message.
- [ ] **Step 4: Run** `cd app/frontend && npm run typecheck && npm test && npm run build`; all pass.
- [ ] **Step 5: Commit** `git commit -m "feat(frontend): fitting-by-default results with all-vacancies toggle and comparison" -m "Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>"`

### Task 5: Frontend navigation: stepper without Vacancies, Vacancies as a top-level section
**Files:**
- Modify: `app/frontend/src/lib/navigation.ts`, `app/frontend/src/lib/navigation.test.ts`
- Modify: `app/frontend/src/components/AppShell.tsx` (sidebar: stepper above, «Вакансії» and «Налаштування» below a divider)

**Interfaces:**
- Consumes: existing route names from `routes.tsx`.
- Produces: stepper steps = `[Вітання /, Профіль /profile, Інтерв'ю, Результати /results, Профіль ринку /market]`, numbered 1–5 (Профіль ринку stays a step because it is a result view). `Вакансії /vacancies` and `Налаштування /settings` are side items, not steps. «Вакансії» is never locked.

- [ ] **Step 1: Write failing tests** in `navigation.test.ts`: four-plus-one stepper ordering; Вакансії absent from steps and never `locked`; «Налаштування» present as a side item.
- [ ] **Step 2: Run** `cd app/frontend && npm test -- navigation`; confirm failures.
- [ ] **Step 3: Implement** the new step list and side items; update the stepper header «Крок N із M» to use the step count.
- [ ] **Step 4: Run** `cd app/frontend && npm run typecheck && npm test && npm run build`; all pass.
- [ ] **Step 5: Commit** `git commit -m "feat(frontend): vacancies outside the interview flow in navigation" -m "Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>"`

### Task 6: Frontend market page: per-track distribution chart
**Files:**
- Modify: `app/frontend/src/screens/MarketScreen.tsx`
- Create: `app/frontend/src/components/MarketDistributionChart.tsx` (recharts horizontal bars, lazy-loaded through the existing `LazyMarketChart` pattern)
- Modify: `app/frontend/src/lib/marketChart.ts` (add `distributionRows(items)` pure helper)
- Test: `app/frontend/src/lib/marketChart.test.ts` (extend)

**Interfaces:**
- Consumes: Task 3 `GET /api/v1/market/distribution?track=`.
- Produces: `distributionRows(items: {action_id, name, share_percent}[]): {id, name, share: number}[]` (top 15, server order, share clamped 0..100); chart shows bars labelled «частка вакансій у добірці» with `share_percent` as the axis value; accessible table alternative with the same numbers.

- [ ] **Step 1: Write failing tests** in `marketChart.test.ts`: `distributionRows` keeps order, clamps out-of-range shares, returns `[]` for empty input.
- [ ] **Step 2: Run** `cd app/frontend && npm test -- marketChart`; confirm failures.
- [ ] **Step 3: Implement** the helper, the lazy chart component, and the page section per track (track selector Python / Маркетинг / Дизайн, default = active profile's track). Keep the existing personal-level chart on the same page, below.
- [ ] **Step 4: Run** `cd app/frontend && npm run typecheck && npm test && npm run build`; all pass. Confirm the recharts chunk is still separate.
- [ ] **Step 5: Commit** `git commit -m "feat(frontend): per-track competency distribution on the market page" -m "Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>"`

### Task 7: Verification
- [ ] **Step 1:** `cd app && uv run pytest -q` (all pass; report count).
- [ ] **Step 2:** `cd app/frontend && npm run typecheck && npm test && npm run build` (all pass; report counts and main chunk size).
- [ ] **Step 3:** `cd app && docker compose up --build -d --no-deps api web`, then check `GET /api/v1/market/distribution?track=python` and `GET /api/v1/profiles/{id}/results` for a profile with a finished attempt.
- [ ] **Step 4:** If browser tools are available, check results at 1366px and 375px (default fitting view, toggle, comparison), vacancies outside the stepper, and the market page distribution chart. Report exactly what was and was not checked.

## Open items
- Task 11 (vacancies and profiles pages) is in progress with uncommitted changes in `navigation.ts`, `AppShell.tsx` and `App.tsx`. Tasks 4–6 must start after Task 11 is committed, or they conflict with its edits.
- DevOps and AI-engineer tracks are out of scope (separate project).
