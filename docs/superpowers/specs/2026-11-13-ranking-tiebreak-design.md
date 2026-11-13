# Design: self-rating tie-break, BORDERLINE state, deferred A/B/C harness

Status: DRAFT — awaiting user approval. Size: small change.

## Intent

Bring the active ranking and threshold code in line with the 2026-11 clarification of MATH_SPEC §2–§3. The A/B/C research harness is explicitly out of scope and deferred until this core is verified.

## Goals

1. Ranking key `K(v)` uses `(mandatory_class, experience_status, mandatory_lower, preferred_lower, -mandatory_width, -preferred_width)`.
2. Exact ties on `K` break by a self-rating signal `T(v)` desc, then `J(v)` desc, then `vacancy_id` ascending as string.
3. Threshold classification exposes `BORDERLINE` distinctly from `UNRESOLVED`; `null` maps to `UNKNOWN` (which is `UNRESOLVED`).
4. Parameterized tests on `tau`, `tau−eps`, `tau−eps±delta`, and `null`.

## Non-goals

- No A/B/C harness, no experiment logging, no expert labels.
- No change to LLM assessment, interview flow, or frontend.
- No change to general formulas beyond the clarified key and tie-break.

## Anti-goals

- Self-rating must never become a criterion score, change mandatory status, or be presented as verified evidence.

## Decisions (my calls, to confirm)

- **`mandatory_class` = existing `Z`** (0 failed, 1 unresolved, 2 all satisfied). The clarification's name is the same concept; no new field.
- **`experience_status` = existing `X`.**
- **`T(v)` and `J(v)`** computed exactly as the clarification states. Groups with no alternative having a self-rating are excluded from the numerator and count as undefined `b`. `J(v) = defined_groups / all_groups`.
- **`NOT_EVALUABLE` vacancies** get no `T,J` and sort last (already excluded by `rank()`).
- **`BORDERLINE`** is returned by `mandatory_status` as a distinct value, and treated as unresolved everywhere it matters (group/alt/Z). Existing callers that compare to `"UNRESOLVED"` must be updated.
- Self-rating input comes from `CandidateSelfRating` latest revision per action; no other source.

## Approaches considered

1. **Chosen:** change `ranking.py` sort key + add `T,J` computation in `core_flow.py`; extend `mandatory_status` with `BORDERLINE`. Smallest diff, reuses existing seams.
2. Rejected: new `RankingPolicy` table with versioned weights now. Adds persistence the spec does not yet require.
3. Rejected: compute `T,J` inside SQL. Harder to test; ranking is pure Python.

## Builder check (what a builder could ask)

- Does `K` replace the current sort, or sit beside it? → Replaces it; `Z` is the first component.
- Is `T` capped? → No cap; it is a bounded average in [0,1].
- What if no self-ratings at all? → `T=0`, `J=0` for every vacancy; ties fall to ID. Expected and documented.

## Open for user

None blocking. Confirm the two calls above (`mandatory_class = Z`, `BORDERLINE` as distinct value).
