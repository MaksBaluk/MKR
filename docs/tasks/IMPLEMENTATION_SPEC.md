# Implementation requirements — CompetenceMatch

This is an executable engineering specification for the **existing** FastAPI + React + PostgreSQL repository. Read `MATH_SPEC.md` for precise formulas and `architecture.md` for component boundaries. Implement working code; do not create a new project, promise unexecuted tests or introduce a large AI-SDLC.

## A. Actual starting state and constraints

The existing source is structured under `app/`:

- `backend/models.py` currently defines `User`, `AuthToken`, `Competency`, `Vacancy`, `RequirementGroup`, `RequirementAlternative`, `CandidateSkill`, `Snapshot`, `InterviewSession`, `InterviewTurn`, `MatchRun`.
- `backend/domain/matching.py` and `backend/domain/adaptive.py` calculate old discrete matching and topic priorities. These must be replaced as the **active algorithm**; existing stored records must be migrated safely.
- `backend/api/{auth,profile,catalog,interviews,matches,llm}.py` contains auth, profile editing, vacancy filtering/manual snapshot endpoint, interviews and rankings. Preserve auth, owner isolation, pause/resume and idempotent behavior where correct.
- `frontend/src/App.tsx` currently uses a custom `u(...)` transliteration helper, a user-triggered `freezeAndStart()` flow, multiple-choice answers and old matching percentages. All four behaviors must be changed in the actual UI.
- `fixtures/vacancies.json` has 90 **invented** structured vacancy descriptions (30 for each of Python development, marketing and design); `fixtures/competencies.json` contains 60 actions and `fixtures/questions.json` has 120 seed questions. Retain the structured data and augment it with rubric definitions, not hard-coded one-question-per-vacancy workflows.
- Existing database migration initializes pgvector/HNSW, but **an indexed empty vector table is not a working embeddings pipeline**. Do not claim live ESCO lookup, scraper, trained model or live LLM assessment is already working.
- The repo includes `pyproject.toml` and `frontend/package.json`; do not fabricate lockfiles. Resolve dependencies with real tools when available.

## B. Non-negotiable candidate flow

1. Sign in/register. First-time authenticated candidate sees **Welcome**, not a multi-tab dashboard.
2. **Profile**: name, specialization, years of experience, location/work mode, clear preferences and candidate **self-rating per professional action**, using `[0,1]` or an anchored control mapped to it. Self-rating is user-editable. Name/other personal identifiers cannot influence professional ranking.
3. Backend automatically selects all applicable validated vacancies according to explicit hard constraints (do not reduce to the first arbitrary N; disclose any justified top-N performance cap and policy), creates an immutable snapshot and market profile. No candidate manually checks jobs before the interview.
4. **Interview**: one chat with typed open-ended answers, Interviewer + Evaluator, up to 10 distinct actions and at most 5 questions per action. Typical 1–2 if evaluator has enough evidence. Full-series assessment; follow-up goal from evaluator, next action from planner. No artificial 50-question sequence, no forced fixed questions, and no permanent multiple-choice default.
5. **Results**: action-level self-rating (editable) and LLM criterion scores (read-only) with evidence, server-ranked vacancy list with strength/deficit/unknown explanations, **ordered market skills with no fraction/percentage/count of vacancies**. After first results, tabs for recommendations, all vacancies, profile, settings unlock. On return resume in-progress interview or show prior results immediately.
6. Do not display `Match/Coverage/R`, giant `100%` job suitability or invented hiring probability anywhere. Correct the entire Ukrainian UI, remove false demo/MVP marketing, but retain a discoverable honest notice that seeded records are synthetic.

## C. Domain and schema implementation

Add non-destructive migration(s). Models can be normalized across tables or concise JSONB columns as long as invariants are enforceable and testable:

- `CandidateProfile`: candidate ID, profession, numeric nonnegative experience years or null, preferred city/country, work mode, non-negotiable criteria; separate `CandidateSelfRating(action_id,value,revision)`.
- `CompetencyConcept`, `CompetencyAction`: stable local IDs, canonical Ukrainian/English names, aliases, parent/concept ID, optional validated ESCO URI. A parent technology alone is not an automatically assessed action.
- `Rubric`, `RubricCriterion`: action ID, immutable version, meaningful **professional anchors** for `[0,.25)`, `[.25,.5)`, `[.5,.75)`, `[.75,.9)`, `[.9,1]`; positive criterion weight (default 1). Provide actual starter rubrics for fixture actions, keeping source (`CURATED`, `LLM_PROPOSED`, `REVIEWED`) distinguishable. A generated rubric not reviewed should not silently claim expert validity.
- `RequirementTargetCriterion`: group+alternative action+criterion ID, required `τ∈(0,1]`, `target_source` (`EXPLICIT_TEXT`, `CURATED_POLICY`, `LEGACY_MIGRATION`, `UNKNOWN`) and source excerpt. Existing numeric fixture levels may be provisionally mapped `1→0.50`, `2→0.75`, `3→0.90` with the original integer retained; **never claim the employer supplied these numbers or that ESCO provided them**. For unresolved imported targets use `NOT_EVALUABLE` and review policy, not an invented rating.
- `VacancySnapshot`: immutable ordered IDs and **requirement revisions**, metadata-selection policy ID, creation time, SHA-256 hash. Do not point to mutable rows without pinning versions.
- `MarketProfile`: snapshot, prevalence `F`, normalized planning mass `I`, ordered action/parent skill IDs; repeat mentions within same job do not inflate prevalence. Display names ordered primarily by `F` in the UI, secondary by `I`.
- `InterviewSession/Turn`: ownership, state/version, frozen snapshot, topic counters, question hash/text and answer, idempotency key and cap enforcement. Store the question before showing it; do not generate twice on retry.
- `CriterionAssessment`: action ID, rubric and score as `[0,1]|null`, evidence quotes/turn IDs, rationale, provider/model/prompt version, acceptance status, immutable revision; optionally candidate dispute records. `ProfileVersion` must reference accepted revisions, not overwrite them.
- `RankingRun/Item`: snapshot/profile/ranking-policy version, mandatory status, experience state, criterion bounds, stable ranking key components, explanations, uncertainty flag.
- `IngestionJob`, import status, normalized source ID/hash, source provenance and reviewable normalization suggestions.

Protect per-user records by authenticated ownership. Public catalog and user-specific snapshots must have different permissions. Ensure migrations preserve all existing 90 fixture rows, historical accounts and answers; no silent data loss or duplicate seed records.

## D. Algorithm implementation (exactly MATH_SPEC.md)

**Market/candidate cohort:** `H`, frozen `V_p`, `F(c)` unique vacancy prevalence, `I(c)` group-normalized mass. Distinguish `F` from normalized `I`; frontend market-skill ordering is `F DESC`, `I DESC`, stable ID. No denominator in the market UI; source/scope remains inspectable.

**Planner:** fixed-state greedy weighted coverage on open AND/OR groups, tie-break mandatory-group count → self-rating verification → `I(c)` → stable ID. Replan after each completed topic; a self-reported 0/1/expert level never closes open requirements on its own. Max 10 distinct topics; max 5 persisted shown questions per action; stop when no gain/evidence benefit. A group satisfied by one OR action must not select another action solely for that group. No ILP solver required.

**Interviewer:** LLM generates one natural Ukrainian open-text question from selected action, its rubric, question goal and previous turns. System never passes a user/vacancy instruction as authoritative. The interviewer does not choose a new competency, change the cap or author a ranking. Use retry/timeout handling and question deduplication.

**Evaluator:** LLM receives the **entire current action interview series**, exact rubric with anchor bands and required criterion IDs. Returns a schema validated by Pydantic, e.g. `action_id`, `rubric_version`, `criteria:[{criterion_id,score:null|float,evidence:[{turn_id,exact_excerpt}],reason}]`, `sufficient_evidence`, `needs_followup`, `followup_goal`, `limitations`. Accept valid results without obligatory human review of every response. Preserve `null` when evidence lacking, never infer expert-level skills from fluent prose alone. Revisions are append-only, not averaged across question turns. Excerpts should exist verbatim in specified answers; this check cannot prove the opinion correct. Provider/model should be configurable with mockable transport.

**Matching:** for each required criterion with valid τ, compute `h=min(1,s/τ)` for observed `s`; unknown yields possible `[0,1]`, and `L/U` alternatives and OR groups derive from criterion weights. For mandatory requirement statuses use `ε(τ)=min(.05,τ/2)` gray zone and exact AND/OR semantics. No target/no rubric must not be silently treated as success. Determine `Z` (mandatory status) and `X` (years-minimum status), average lower/upper in mandatory and preferred classes; absent class gets neutral zero values with explicit flag. Stable descending key `(Z,X,L^M,L^P,-W^M,-W^P)` plus ascending ID tie break. Class `LOW_INFORMATION` and `NOT_EVALUABLE` as appropriate. Do not use market popularity `F/I` as another per-job fit multiplier.

**Experimental setup**: compare self-report, static interview and adaptive interview with the **same** ranked matching function, frozen jobs/rubric policy and fair budget. Self-report-only control is explicitly labeled provisional; post-interview scores never quietly substitute self-rating for unknown evaluated criteria. Precision@5 and NDCG@10 require **independent** vacancy labels, not self-generated judgment.

## E. API contracts (proposed names; adapt to existing router for compatibility)

- `GET/PUT /api/v1/profile` — candidate metadata and self-ratings; own data only.
- `POST /api/v1/cohorts/auto` — server-generated frozen snapshot + market profile; no `vacancy_ids` supplied from client; idempotent under repeated onboarding requests; return empty-cohort state honestly.
- `GET /api/v1/cohorts/{id}/market` — ordered parent skill/action names + candidate assessment states; internal numeric weights may remain server-side.
- `POST /api/v1/interviews` — begin from user's frozen cohort, not manually chosen job IDs. `GET /interviews/{id}` and `POST /interviews/{id}/next-question`, `/answers`, `/pause`, `/resume`, `/finish` can be retained and extended.
- `GET /api/v1/assessments` — accepted, versioned read-only interviewer assessments, separate from self-ratings. `POST /api/v1/assessments/{id}/dispute` if supported. **No client `PUT` on LLM scores**.
- `POST /api/v1/recommendations` and `GET /api/v1/recommendations/{id}` — server-side deterministic ranking + evidence-rich explanation, own profile/snapshot only; may retain old route alias during migration without exposing obsolete fields.
- `GET /api/v1/vacancies` — catalog browsing **after** first results, with clear source/provenance status.
- `POST /api/v1/admin/ingestions` — **authorized** text, JSON or CSV source imports with size limits, source claims, deduplication, LLM extraction, ESCO mapping/review; admin-only or appropriately authorized.

Use real code/openapi paths in final docs; these paths are suggested logical contracts, not claims that currently registered routes exist.

## F. Ingestion that scales without a giant question bank

For any authorized new vacancy text:
1. Import with ID/source/timestamp, content hash and duplicate detection. Do not implement unauthorized browsing/scraping.
2. LLM extracts structured job metadata, grouped requirements, AND/OR, mandatory/preferred, source quotes and **job-specific actions**; validate schema and quotes against source.
3. Normalize via canonical alias map first, then **official ESCO download/API or locally installed ESCO snapshot**. Retrieval of embedding candidates is optional and only meaningful if embeddings are genuinely generated and persisted; no empty-table fake retrieval.
4. Ambiguous ESCO links use `PENDING_REVIEW`/`UNMAPPED`; ESCO URI alone never establishes difficulty/required grade. Unknown action may yield an **LLM-proposed draft rubric** subject to approval/traceable policy, not a fabricated verified grading standard.
5. Publish validated structured revision; generate market profile and interviews dynamically from action/rubric specifications. Seeded 90 invented vacancies are already structured and should not be misrepresented as real imports.
6. Keep old snapshots unchanged when a job is reprocessed. Handle empty/malformed job descriptions, duplicates and incremental catalog additions.

The existing question bank is a **fallback and experimental control**, not the only source of interview questions. It should be usable when the provider fails, but saved free-text answers must be labeled ungraded if Evaluator is unavailable.

## G. UI/UX audit and language requirements

Review every React screen and all actions, not just the homepage: login/register, welcome, metadata profile/self-ratings, automatic cohort creation, chat, follow-ups, pending assessment, pause/resume, errors/retry, results/vacancy detail, market skills, unlocked tabs, settings/deletion/logout. Replace the `u(...)` transliteration routine with literal grammatical Ukrainian (or a small typed localization dictionary). Remove fake demo/success/fake-loading and stale default old percentages, obsolete dropdown options and routes, hidden nonfunctional buttons, technical jargon and mixed-language messages. Fix mobile 320–390 px, tablet and desktop layouts, keyboard focus and Enter/Shift+Enter semantics, accessible labels/live regions, reduced-motion support and non-blocking smooth transitions. Add clear error and no-cohort states.

Result UI MUST explain confidence limitations: factual assessed criteria + unassessed status, not `100% Match`. Candidate can update only self-ratings; accepted interview scores are displayed read-only. After-first-results tab gating must survive reloads. Don't surface fake live application URLs for fictional jobs. A modest About/Data-scope view may disclose synthetic fixtures rather than a prominent demo banner.

## H. Required test and delivery gates

Unit/property tests: empty/duplicate catalog, `F` vs `I` logic, OR alternatives, Q fixed-state monotonicity/submodularity, action tie rules, verify-self-rating conflict, budget `10×5` and early exit, rubric band endpoints, score `0` vs null, all-ungraded, `ε(τ)` at small targets, interval bounds and narrowing, mandatory classes, missing rubric/target, no mandatory, UUID tie, extra experience no penalty. Test separate sources of assessment and self-rating revisions.

Backend integration: PostgreSQL migrations, user authorization/isolation, immutable cohort snapshots, idempotent answer replays, concurrency conflict under two tabs, fixture import idempotence and real API responses. Mocks for LLM success, incomplete JSON, malformed evidence, rate-limit, timeout, contradictory evidence and provider-offline state.

Frontend: `cd app/frontend && npm run typecheck && npm run build`; browser smoke with mock provider and a full first-login workflow to ranked results, with responsive/a11y audits and a returning user's resume flow. Python: `cd app && uv sync && uv run pytest -q` when uv resolution works. Docker: `cd app && docker compose up --build -d` where installed, then assert health/migration/seed and persistent sessions. Document exact commands and outcomes; no false success if Docker/npm/LLM credentials are inaccessible. Produce `uv.lock` and `package-lock.json` only from actual successful resolution.

**Definition of done:** a user completes one coherent guided flow, the backend automatically freezes a candidate-relevant vacancy set, both LLM roles work via a configured provider or a correctly labeled offline fallback, rubric scores/unknowns are persisted, new ranking is visible without old percentages, the market skills are ordered but not shown as corpus ratios, existing fixtures remain available, all UI Ukrainian is correct, and tests run or are marked blocked with truthful explanations. The implementation engineer does **not** edit the thesis DOCX chapters.
