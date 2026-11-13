# Design: results redesign, vacancies outside the flow, market charts

Status: DRAFT, awaiting owner approval. Size: project (several parts, each shippable).

## Intent

After an interview the candidate should see which vacancies fit them and why, and how the interview scored each competency next to their own self-rating. Vacancies become their own section, reachable at any time, not a step in the flow.

## Approach (chosen by owner)

**A. Threshold with an all-vacancies toggle.** Default view shows only fitting vacancies. A switch shows every vacancy, with non-fitting ones marked and their reasons visible.

## Behaviour

1. **Fitting** (default): all mandatory requirements are satisfied or still unresolved, and fit share ≥ 40% (owner may change the value; my call, not validated).
2. **Все вакансії** toggle: same list plus the rest, each non-fitting card shows «Не підходить» and the main gaps.
3. Each card shows: fit share with label «Збіг профілю N%», «оцінено X із Y вимог», strengths, gaps, unknowns, the mandatory-status sentence. Tooltip keeps the honesty text (not a hiring probability).
4. Results page sections after an interview: competencies with the interview score (LLM, read-only) beside the candidate's self-rating (editable, separate value), level words, and the Evaluator reason.
5. **Вакансії** is a top-level section with its own list and filters. It is not in the stepper flow. Stepper: Вітання → Профіль → Інтерв'ю → Результати. Вакансії and Налаштування sit outside it.
6. **Профіль ринку** per track: a distribution chart of how many vacancies in the track require each competency (share, labelled «частка вакансій у добірці»). Owner accepted this exception to the earlier no-market-numbers rule.

## Non-goals

- No new hiring probability or job-match claims.
- DevOps and AI-engineer tracks are NOT part of this design. They need new competencies and rubrics, so they are a separate project.

## Constraints

- Backend changes limited to: a fitting filter parameter on results, a non-fitting reason field, and a market-distribution endpoint. No change to ranking order.
- Snapshot note: a cohort is frozen at creation. Old attempts keep their cohort and do not see new fixture vacancies. Cohorts frozen before the seniority field existed are excluded from seniority filters. Both are kept on purpose and documented.

## Builder questions (answered)

- Threshold 40% is my proposal; owner may override.
- Market chart values are shares, not counts, and are labelled as a selection share.

## Next step

Owner approves this doc. Then the plan is written with superpowers:writing-plans.
