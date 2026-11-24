# Results page UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline; the change is small and frontend-only).

**Goal:** Flat percent-ordered vacancy list with section badges, and one right-column summary (level + competencies) with a calm caveat.

**Architecture:** `ResultsScreen` renders `data.items` in server order; `levelView.ts` gains short section labels; `LevelSummary` becomes a compact card used in the aside, with details collapsed.

**Tech Stack:** React, TypeScript, Tailwind, vitest.

**Spec:** `docs/superpowers/specs/2026-11-23-results-page-ux-design.md`

## Global Constraints

- No API or server change; ranking, percent and level policy untouched.
- The level-policy caveat stays visible as text (project data-honesty rule); no amber badge.
- Natural Ukrainian copy; keyboard order, mobile layout and reduced motion keep working.
- Do not edit thesis DOCX files.

## Review Focus

- Page 2 numbering continues (offset + index), never restarts at 1.
- An item with a missing or unknown `section` still renders, with the "є прогалини" badge.
- `level` is `null` or `undefined`: the summary card still renders with the fallback text.
- Level `UNKNOWN`: the hint with counts is shown; counts are never shown as a score.
- Mobile width: the summary stacks above the list and stays collapsed.

### Task 1: Section badge labels

**Files:** Modify `app/frontend/src/lib/levelView.ts`, `app/frontend/src/lib/levelView.test.ts`.

**Interfaces:** Produces `sectionBadge(s: ResultSection | undefined): string` returning `"бажаний рівень"` (DESIRED_LEVEL), `"інші, що підходять"` (OTHER_FITTING), `"є прогалини"` (UNRESOLVED_OR_GAPS and any missing/unknown value).

- [ ] Write the failing test for the three values plus `undefined`.
- [ ] Run `cd app/frontend && npx vitest run src/lib/levelView.test.ts`; expect FAIL.
- [ ] Implement `sectionBadge`; keep `sectionTitle`, drop `groupBySection`, `SECTIONS` and their tests only when Task 2 leaves them unused.
- [ ] Run the test; expect PASS.

### Task 2: Flat list in `ResultsScreen`

**Files:** Modify `app/frontend/src/screens/ResultsScreen.tsx`.

**Interfaces:** `VacancyCard({ item, rank })` shows `sectionBadge(item.section)` as a small outline badge beside the title; list is one `<ol>` over `data.items` with `rank = offset + index + 1`; helper text becomes "Номер — місце в списку за відсотком збігу."

- [ ] Replace the `SECTIONS.map` block by one `<ol aria-label="Вакансії за відсотком збігу">`.
- [ ] Remove the section-regroup comment and unused imports; delete `groupBySection`/`SECTIONS` if unused.
- [ ] Run `npm run typecheck`; expect clean.

### Task 3: Summary card in the aside

**Files:** Modify `app/frontend/src/components/LevelSummary.tsx`, `app/frontend/src/screens/ResultsScreen.tsx`.

**Interfaces:** `LevelSummary` renders as a card titled "Ваш рівень" placed first in `<aside>`, above `CompetencySection`; level pair is a two-cell grid; the confirmed/gaps/unchecked/borderline lists sit in one `<details><summary>Деталі рівня</summary>`; caveat is one muted line `Правила рівнів — робоче припущення, ще не перевірені експертами.` with `level.note` kept inside the details; for `UNKNOWN` show `Підтверджено {n} із {m} вимог. Відповідайте розгорнутіше, щоб рівень можна було визначити.` using the lists' lengths.

- [ ] Move `<LevelSummary>` into the aside; remove it from the top of the page.
- [ ] Implement the compact card as described; keep `role="alert"` for the "blocked" notice.
- [ ] Run `npm run typecheck && npm test`; expect all pass.

### Task 4: Test account and profiles

Create a new account through `POST /api/v1/auth/register` on localhost and four profiles via `POST /api/v1/profiles` (senior Python, senior designer, middle marketing, junior Python). Append the credentials to `app/DEMO_CREDENTIALS.txt` (git-ignored).

### Task 5: Verify

- [ ] `cd app/frontend && npm run typecheck && npm test`
- [ ] `docker compose up -d --build web`, then check `/results` on desktop and 375 px width in the browser pane.
