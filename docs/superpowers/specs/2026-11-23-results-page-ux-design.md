# Results page UX: flat ranked list, level in the side column

Status: approved by the owner in chat (2026-11-23). Short design for a small frontend change.

## Intent

On `/results` the candidate sees three confusing things: card numbers that start at 3 and jump, a large "Рівень за співбесідою" block above the list that looks like an error ("Недостатньо даних", an amber "Потребує експертної валідації" badge), and competencies in a separate place from the level. The page should read as one result: a ranked list on the left, "who I am by this interview" on the right.

## Goals

- Card numbers run 1…N in the order of the percent-first list, with no jumps.
- One summary block in the right column (level + competencies), instead of a block above the list.
- The policy caveat stays discoverable but stops looking like a failure.
- When the level cannot be set, say what would help rather than only "Недостатньо даних".

## Non-goals / anti-goals

- No change to ranking, percent, sections or level policy on the server; no API change.
- Do not hide that the level rules are a working assumption (project data-honesty rule).
- No new metrics for the user (`Match/Coverage/R` stay hidden).

## Approaches considered

1. Keep the section groups and renumber inside each group. Keeps the grouping but contradicts the owner's "sort by percent" decision, because the visible order would no longer be the percent order.
2. Flat list by percent, section shown as a badge on each card (chosen). Matches the owner's ordering decision; the section information is kept.
3. Tabs per section. Hides most results behind clicks; rejected.

## Design

- `ResultsScreen`: render `data.items` in server order as one list. Number = position on the page offset by the page start (the server already paginates the percent-first list). The section is a small badge from `sectionTitle`, short labels: "бажаний рівень", "інші, що підходять", "є прогалини".
- `LevelSummary` moves into the right column, above the competencies card, as one sticky container "Ваш рівень і компетентності". Desired and confirmed level on top. The three lists (confirmed / gaps / unchecked) and borderline answers go inside a collapsed "Деталі рівня".
- Caveat: one muted line with an info marker under the level ("Правила рівнів — робоче припущення, ще не перевірені експертами"), keeping the full note in the details. No amber badge.
- Empty level state: show the counts ("Підтверджено 0 із N вимог") and one hint to answer in more detail or to continue the interview. Copy is natural Ukrainian; no new claims about the candidate.
- Mobile: the right column stacks above the list; the details stay collapsed; keyboard order unchanged; reduced-motion respected.

## Left to the builder

Exact class names and spacing; small refactor of `levelView.ts` (`groupBySection` may stay for the badge helper or be removed if unused, with its test updated).

## Test and data

Unit tests for the numbering and the badge label. Browser check of desktop and mobile layout. Test account with several profiles (designer, marketer, python senior, junior, empty) is created through the API; its credentials go to `app/DEMO_CREDENTIALS.txt`.
