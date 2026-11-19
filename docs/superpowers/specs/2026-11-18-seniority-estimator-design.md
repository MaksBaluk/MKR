# Seniority estimation — design (approved by the owner: "сам придумай критерії")

## Intent
Show the candidate an evidence-based professional level, kept strictly separate from the level they *want* and from how well a vacancy fits.
`desired_level` (user's choice, only seeds the first question difficulty), `assessed_level` (JUNIOR|MIDDLE|SENIOR|UNKNOWN from interview evidence), `vacancy_fit` (existing matching, untouched).

## Goals / non-goals / anti-goals
- Goals: deterministic `SeniorityEstimator` (no LLM) over existing criterion assessments; versioned level policy outside prompts; professional-practice criteria graded from the *same* answers; persistence + API + results UI; honest `UNKNOWN`.
- Non-goals: new agents, ML models, scraping, ESCO, a psychological test, changing ranking (2.15) or the planner coverage Q_t.
- Anti-goals: `avg > 0.8 → SENIOR`; years/title/self-rating/desired level as evidence; Junior as a default when nothing is confirmed; hiding a vacancy because its level differs.

## Approaches considered
A (chosen): level policy over existing rubric criteria + a small `practice-backend` rubric graded in the existing Evaluator call.
B: only existing criteria tagged by level — cannot express trade-offs, diagnosis, ownership (requirement 3).
C: new level-tagged criteria inside all 60 rubrics (rubrics v2) — large, needs experts, changes D_vga everywhere.

## Design decisions (my calls, flagged WORKING_ASSUMPTION — need expert validation)
- Policy `python-backend/v1`: per level a tuple of critical criterion ids (existing rubric criteria + practice criteria), `tau`, `min_assessed_share`, `min_confirmed_share`, `min_competencies`, zero tolerance for an established critical gap (`score < tau − ε(tau)`). Levels are hierarchical (Middle needs Junior supported, Senior needs Middle).
- Level status per level: SUPPORTED | GAP (an established critical gap) | UNVERIFIED (not enough evidence). Unknown ≠ gap.
- `assessed_level` = highest level of the unbroken SUPPORTED chain from Junior; Junior not SUPPORTED → UNKNOWN (never default Junior).
- Marketing and design: policy registry entries are `None` (rubrics are unreviewed templates) → UNKNOWN with `POLICY_UNAVAILABLE` and a note "потрібна експертна валідація рубрик".
- Practice criteria are graded together with the topic answer (no extra questions); stored as `criterion_assessments` rows of the pseudo-action `practice-backend` (not a vacancy competency, so the planner and D_vga ignore it).
- Interview integration only reorders the *unmet criteria of the current topic* so level-critical ones come first and adds practice gaps to the Interviewer context; Q_t, caps (10 topics, 5 per topic, total budget) and difficulty rules are unchanged.
- Persistence: immutable `seniority_assessments` row per (attempt, policy version), written on finish; policy edits never rewrite stored rows; attempts are never mixed.
- Results: same ranking, three *views* of it (desired-level, other fitting, unresolved/gaps) — no new algorithm.

## Consequence to state honestly
~12 questions rarely cover enough critical criteria: `UNKNOWN`/"Middle confirmed, Senior unverified" will be the common outcome.

## Update 2026-11-19 (policy v2)
The consequence above held for v1 and was worse than predicted (Junior/UNKNOWN on the full cohort). Policy `python-backend/v2` replaces per-criterion critical sets with capability pools and count thresholds; see `docs/tasks/MATH_SPEC.md` §3e and `docs/tasks/SENIORITY_REPORT.md`.
