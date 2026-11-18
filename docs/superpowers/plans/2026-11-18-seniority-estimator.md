# Seniority Estimator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deterministic, evidence-based `assessed_level` (JUNIOR/MIDDLE/SENIOR/UNKNOWN) separate from `desired_level` and from vacancy fit, with persisted explanation, API and results UI.

**Architecture:** A pure domain `SeniorityEstimator` (no LLM) evaluates a versioned, hierarchical level policy over existing criterion assessments plus six professional-practice criteria that the existing Evaluator grades from the same answers. The interview only reorders the open criteria of the *current* topic. Results are persisted immutably per attempt and policy version.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/Alembic (next migration `0016`), LangGraph graphs, pytest (`cd app && uv run pytest -q`), React/TypeScript/vitest/Playwright (`app/frontend`).

**Spec:** `docs/superpowers/specs/2026-11-18-seniority-estimator-design.md`. Canonical math: `docs/tasks/MATH_SPEC.md` (add §3e in Task 7). Baseline: 578 backend tests, 155 frontend tests, 7 E2E.

## Global Constraints

- No new agents, ML models, microservices, scraping, ESCO. Never edit the thesis DOCX; describe needed thesis changes in `docs/tasks/THESIS_SYNC_SENIORITY.md`.
- Do not change ranking (2.15), `choose_next`/`coverage` (Q_t), difficulty rules, caps `MAX_TOPICS=10`, `MAX_SHOWN_QUESTIONS_PER_ACTION=5`, experiment `total_budget`.
- `desired_level` (`profile.target_level`), years of experience, job title and self-ratings are never inputs of the estimator. Estimator signature has no such parameter.
- Unknown criterion ≠ failed criterion: `score is None` is never turned into 0 anywhere.
- Level policy lives in code under `backend/domain/seniority_policy.py` (versioned), never in prompts. Policy status for `python-backend/v1` is `WORKING_ASSUMPTION` ("потребує експертної валідації"); marketing and design have no policy (`None`) and return `UNKNOWN` + `POLICY_UNAVAILABLE`.
- Stored results are immutable: changing a policy version never rewrites existing rows; attempts are never mixed.
- All user-facing text Ukrainian. Keep LLM credentials server-side; treat answers as untrusted data (existing validation applies to practice criteria too).
- Use the `start-work` skill, then caveman voice in chat; record real command outputs.

## Review Focus

- A single strong criterion (0.95 on PostgreSQL transactions, 4 of 5 unchecked) must not yield Middle/Senior anywhere.
- Unverified Senior criteria must stay `unassessed`, never 0, and must not block a *confirmed* Middle result.
- `desired_level`, years, self-ratings changing must not change the result; evidence changing must.
- Practice criteria rows (`action_id="practice-backend"`) must never reach the planner, D_vga, `/recommendations` or the vacancy ranking inputs as competencies.
- Null/off-topic revisions must not erase practice scores (same `effective_rows` rule).
- Budget: the interview with level probing never exceeds caps or `total_budget` and never asks about a criterion that already has sufficient evidence.

## Policy `python-backend/v1` (exact content; WORKING_ASSUMPTION)

Criterion ids are existing rubric criteria (`<competency>.<slug>`) plus practice criteria `practice-backend.<slug>`.

| Level | tau | min_assessed_share | min_confirmed_share | min_competencies | critical criteria |
|---|---|---|---|---|---|
| JUNIOR | 0.50 | 0.75 | 0.75 | 4 | python-core.idioms, python-core.errors, python-core.testing, sql.joins, sql.correctness, rest-api.contract, git.branching, pytest.structure, practice-backend.independence |
| MIDDLE | 0.70 | 0.80 | 0.70 | 5 | python-core.typing, postgresql.indexes, postgresql.transactions, postgresql.schema, sqlalchemy.session, rest-api.pagination, pytest.isolation, app-security.input, async-python.blocking, ci-cd.pipeline, practice-backend.independence, practice-backend.rationale, practice-backend.diagnosis |
| SENIOR | 0.75 | 0.80 | 0.80 | 6 | postgresql.operations, postgresql.migrations, sqlalchemy.concurrency, celery.idempotency, redis.reliability, observability.incidents, app-security.authz, ci-cd.safety, async-python.concurrency, rest-api.security, practice-backend.tradeoffs, practice-backend.ambiguity, practice-backend.ownership, practice-backend.diagnosis, practice-backend.rationale |

Rules per level `L` (shares are over `len(critical)`): criterion *assessed* = score not None; *confirmed* = score ≥ tau; *gap* = score < tau − `epsilon(tau)` (existing `backend/domain/criteria.py::epsilon`); the band `[tau−ε, tau)` is assessed-but-unresolved. `competencies_confirmed` = distinct competency prefixes (text before `.`, excluding `practice-backend`) with ≥1 confirmed critical criterion. L is `SUPPORTED` iff assessed_share ≥ min_assessed_share ∧ confirmed_share ≥ min_confirmed_share ∧ gaps = 0 ∧ competencies_confirmed ≥ min_competencies ∧ every confirmed criterion has ≥1 evidence turn id. `GAP` iff gaps > 0. Otherwise `UNVERIFIED`. Practice criteria `practice-backend.independence|rationale|tradeoffs|diagnosis|ambiguity|ownership`.

### Task 1: Practice rubric fixture, seed and policy registry

**Files:**
- Create: `app/fixtures/practice_rubrics.json`, `app/backend/domain/seniority_policy.py`, `app/tests/test_seniority_policy.py`
- Modify: `app/backend/seed.py` (new `seed_practice_rubrics`, called from `seed_database`)

**Interfaces:**
- Produces (`seniority_policy.py`):
```python
class Level(str, Enum): JUNIOR="JUNIOR"; MIDDLE="MIDDLE"; SENIOR="SENIOR"   # + def rank(l) -> int 0..2
@dataclass(frozen=True) class LevelRule: level: Level; tau: float; min_assessed_share: float; min_confirmed_share: float; min_competencies: int; critical: tuple[str, ...]
@dataclass(frozen=True) class SeniorityPolicy: policy_id: str; version: str; track: str; status: Literal["WORKING_ASSUMPTION","VALIDATED"]; rules: tuple[LevelRule, ...]
PRACTICE_ACTION = "practice-backend"; PRACTICE_CRITERIA: tuple[str, ...]  # six ids above, in that order
PYTHON_BACKEND_V1: SeniorityPolicy; POLICIES: dict[str, SeniorityPolicy | None]  # python -> V1, marketing/design -> None
def policy_for(track: str | None) -> SeniorityPolicy | None
```
- Produces (fixture): rubric `{"action_id": "practice-backend", "version": "v1", "source": "CURATED_TEMPLATE", "criteria": [{criterion_id, title, weight: 1, anchors: {"0-0.25","0.25-0.5","0.5-0.75","0.75-0.9","0.9-1"}}]}` for the six practice criteria (Ukrainian titles/anchors, same band keys as `fixtures/rubrics.json`). Each anchor describes *observable actions in the answer* (what the candidate did, justified, diagnosed), never confidence, eloquence or term count.

- [ ] **Step 1: Write failing tests** in `test_seniority_policy.py`: `test_policy_levels_are_hierarchical_and_ids_exist` (every non-practice critical id exists in `fixtures/rubrics.json`; every practice id exists in `practice_rubrics.json`; rule ranks ascending; each higher level's `min_competencies >= lower`), `test_policy_is_versioned_and_flagged` (`policy_id=="python-backend"`, `version=="v1"`, `status=="WORKING_ASSUMPTION"`), `test_marketing_design_have_no_policy` (`policy_for("marketing") is None`, `policy_for("design") is None`, `policy_for(None) is None`), `test_practice_rubric_seeded_and_planner_blind` (after `seed_database`, 6 criteria rows for `practice-backend`; `"practice-backend" not in` any `Competency.id`, and `cohort_actions` of a python cohort excludes it), `test_seed_practice_idempotent`.
- [ ] **Step 2:** Run `cd app && uv run pytest tests/test_seniority_policy.py -q` → FAIL (module missing).
- [ ] **Step 3:** Implement the module with the exact table above, write the fixture (Ukrainian anchors), add `seed_practice_rubrics(db, counts)` mirroring `seed_rubrics` (never modifies an existing `(action_id, version)`).
- [ ] **Step 4:** Run the file → PASS; run `uv run pytest -q` → all green (existing rubric-count tests must still see 60 rubrics: practice rubric lives in its own file/seed function, so adjust only tests that count `Rubric` rows to expect 61 where they count all rows).
- [ ] **Step 5: Commit** `feat(seniority): level policy python-backend/v1 and practice rubric`.

### Task 2: Pure `SeniorityEstimator`

**Files:**
- Create: `app/backend/domain/seniority.py`, `app/tests/test_seniority_estimator.py`

**Interfaces:**
- Consumes: `SeniorityPolicy`, `Level`, `epsilon` (`backend/domain/criteria.py`).
- Produces:
```python
@dataclass(frozen=True) class CriterionEvidence: criterion_id: str; score: float | None; evidence_turns: tuple[str, ...] = ()
@dataclass(frozen=True) class LevelCoverage: level: Level; critical_total: int; assessed: int; confirmed: int; gaps: int; assessed_share: float; confirmed_share: float; competencies_confirmed: int; status: Literal["SUPPORTED","GAP","UNVERIFIED"]; confirmed_ids: tuple[str, ...]; gap_ids: tuple[str, ...]; unassessed_ids: tuple[str, ...]; reasons: tuple[str, ...]
@dataclass(frozen=True) class SeniorityResult: assessed_level: Literal["JUNIOR","MIDDLE","SENIOR","UNKNOWN"]; highest_supported_level: Literal["JUNIOR","MIDDLE","SENIOR","UNKNOWN"]; assessment_status: Literal["ASSESSED","INSUFFICIENT_DATA","GAPS_AT_JUNIOR","POLICY_UNAVAILABLE"]; coverage_by_level: dict[str, LevelCoverage]; confirmed_strengths: tuple[str, ...]; critical_gaps: tuple[str, ...]; unassessed_criteria: tuple[str, ...]; evidence_references: dict[str, tuple[str, ...]]; policy_id: str | None; policy_version: str | None; explanation: tuple[str, ...]
def estimate(policy: SeniorityPolicy | None, evidence: Mapping[str, CriterionEvidence]) -> SeniorityResult
def result_to_json(r: SeniorityResult) -> dict   # JSON-safe (levels as strings)
```
`highest_supported_level` = highest level whose own rule is SUPPORTED (informational); `assessed_level` = highest level of the unbroken SUPPORTED chain from JUNIOR; Junior not SUPPORTED → `UNKNOWN` with status `GAPS_AT_JUNIOR` (Junior status GAP) or `INSUFFICIENT_DATA`; `policy is None` → `UNKNOWN`/`POLICY_UNAVAILABLE`, explanation «Для цього напряму рівень не визначається: потрібна експертна валідація рубрик». `critical_gaps`/`unassessed_criteria`/`confirmed_strengths` are over the criteria of the *first level above the assessed one* plus all lower levels' (strengths = confirmed across levels ≤ assessed+1). Explanation lines (Ukrainian) include the exact sentence «Підтверджено Middle за перевіреними критеріями. Для висновку про Senior недостатньо даних» when Middle is the assessed level and Senior is UNVERIFIED, and «… Для Senior виявлено критичні прогалини: <ids>» when Senior is GAP.

- [ ] **Step 1: Write failing tests** (hand-computed, using small helper `ev(**scores)` and the real `PYTHON_BACKEND_V1`): `test_one_of_five_criteria_confirms_nothing` (only `postgresql.transactions=0.95` → `UNKNOWN`, `INSUFFICIENT_DATA`, `postgresql.indexes` in `unassessed_criteria` not in `critical_gaps`), `test_unknown_is_not_a_gap`, `test_established_gap_differs_from_missing_evidence` (score 0.2 on a Senior critical → Senior `GAP`; None → `UNVERIFIED`), `test_junior_requires_minimum_coverage_never_default` (no evidence → `UNKNOWN`), `test_middle_confirmed_senior_unverified_sentence` (all Junior+Middle critical at 0.8, Senior nothing → `MIDDLE`, exact sentence present), `test_high_basics_do_not_compensate_unverified_critical_senior`, `test_senior_requires_all_hierarchical_levels` (Senior criteria strong but Junior unverified → `assessed_level=="UNKNOWN"`, `highest_supported_level=="SENIOR"`), `test_secondary_high_scores_do_not_offset_a_critical_gap` (extra non-critical 0.99 + one critical gap → level not supported), `test_tau_epsilon_borderline_is_unresolved_not_gap` (score `tau−ε` → assessed, not confirmed, not gap; `tau−ε−0.001` → gap), `test_score_without_evidence_turn_is_not_counted_confirmed`, `test_min_competencies_blocks_single_competency_proof` (all confirmed from 2 competencies → UNVERIFIED), `test_estimator_has_no_desired_level_years_or_self_rating_parameter` (inspect `signature(estimate).parameters == {"policy","evidence"}`), `test_deterministic_and_json_safe` (same input twice equal; `json.dumps(result_to_json(r))` works), `test_no_policy_marketing`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5: Commit** `feat(seniority): deterministic SeniorityEstimator`.

### Task 3: Practice criteria in Evaluator output, validation and storage

**Files:**
- Modify: `app/backend/domain/assessment.py` (`EvaluatorOutput.practice: list[CriterionResult] = []`, `validate_against_context(..., allowed_practice: set[str] = frozenset())`), `app/backend/agents/prompts.py` (Evaluator rules + `format_evaluator_input(..., practice_criterion_ids, practice_bands)`), `app/backend/agents/graphs.py` (`AnswerState` fields `allowed_practice_ids`, `practice_bands`; `validate_output` passes them, an off-topic answer nulls `practice` too), `app/backend/api/core.py` (`_assess_action` passes practice ids for tracks with a policy and persists `output.practice` as `CriterionAssessment` rows with `action_id=PRACTICE_ACTION`, rubric = the seeded practice rubric, same `revision` per call)
- Test: `app/tests/test_practice_criteria.py`

**Interfaces:**
- Consumes: `PRACTICE_ACTION`, `PRACTICE_CRITERIA`, `policy_for` (Task 1).
- Produces: `practice_criteria_for(db: Session, track: str | None) -> list[str]` in `core.py` (empty for marketing/design); `attempt_practice(db, interview_id) -> dict[str, CriterionEvidence]` is added in Task 5.
- Prompt rules (exact intent): practice criteria are graded only from concrete *actions the candidate describes* (what they decided, why, which trade-off they named, how they diagnosed, how they handled missing requirements, who owned the outcome); null with empty evidence otherwise; never from confidence, fluency, length or number of terms; same evidence rules (verbatim quote) as topic criteria; a practice score never changes a topic criterion score.

- [ ] **Step 1: Write failing tests** with the `FakeChat` pattern of `tests/test_interview_flow.py`: `test_practice_scores_require_evidence_and_known_ids` (unknown practice id, duplicate, score without quote → output rejected → UNGRADED after retry), `test_practice_rows_stored_under_practice_action` (after an accepted answer `CriterionAssessment` rows with `action_id=="practice-backend"` exist, topic rows unchanged), `test_practice_not_requested_for_marketing_track` (marketing profile: evaluator input has no `practice_criterion_ids`), `test_null_practice_revision_does_not_erase_score` (second answer with practice null keeps the earlier practice score via `effective_rows`), `test_practice_never_enters_planner_or_ranking_inputs` (`rubric_map`/`cohort_actions`/`attempt_scores` consumers: `attempt_scores` is topic+practice rows keyed by criterion id, but `planner_state`/`rank_items` ignore ids outside the cohort rubrics — assert ranking order identical with and without practice rows), `test_off_topic_nulls_practice`.
- [ ] **Step 2–4:** red → implement → green; `uv run pytest -q` stays green (existing FakeChat outputs have no `practice`, default `[]` must keep them valid). **Step 5: Commit** `feat(seniority): grade professional-practice criteria in the Evaluator`.

### Task 4: Interviewer integration (priority of level-critical criteria, budget safe)

**Files:**
- Create: `app/backend/domain/level_probe.py`, `app/tests/test_level_probe.py`, `app/tests/test_level_probe_flow.py`
- Modify: `app/backend/api/core.py` (`next_question`: reorder `unmet`, pass `practice_gaps`), `app/backend/agents/prompts.py` + `graphs.py` (`AskState.practice_gaps: list[str]`; Interviewer rule: prefer a situational question that also reveals the listed practice gaps; keep ≤2 sentences / existing validation)

**Interfaces:**
- Produces:
```python
def prioritize_unmet(unmet: Sequence[str], policy: SeniorityPolicy | None, result: SeniorityResult | None) -> list[str]
# stable: unmet criteria that are critical for the lowest level whose status is not SUPPORTED come first (rubric order inside each group); criteria with sufficient evidence never appear (input already excludes them); unmet unchanged when policy is None
def practice_gaps(policy: SeniorityPolicy | None, result: SeniorityResult | None, limit: int = 2) -> list[str]
# practice criteria of the lowest non-SUPPORTED level that are unassessed
```
Only reorders and annotates; `unmet` membership, goals, controller decisions, `choose_next`, caps and `total_budget` are untouched.

- [ ] **Step 1: Write failing tests:** unit (`test_priority_puts_level_critical_first_and_keeps_membership`, `test_no_policy_returns_input_unchanged`, `test_supported_level_criteria_not_reprioritized`, `test_practice_gaps_limited_and_only_unassessed`); flow with `FakeChat` (`test_interview_never_exceeds_caps_with_level_probing` — run an attempt to completion: ≤10 topics, ≤5 per topic, and with an experiment `total_budget` config ≤ budget; `test_no_question_targets_criterion_with_sufficient_evidence`; `test_q_t_choice_identical_with_and_without_probing` — same topic sequence for the same scores (monkeypatch `prioritize_unmet` to identity and compare `action_id` sequences); `test_budget_exhausted_leaves_level_unknown_not_guessed`).
- [ ] **Step 2–4:** red → implement → green. **Step 5: Commit** `feat(seniority): prioritize level-critical criteria within the current topic`.

### Task 5: Persistence, finalize-on-finish, API

**Files:**
- Create: `app/alembic/versions/0016_seniority_assessments.py`, `app/backend/api/level.py`, `app/tests/test_seniority_api.py`, `app/tests/test_migration_0016.py`
- Modify: `app/backend/models.py` (`SeniorityAssessment`), `app/backend/api/core.py` (call `finalize_level` where `iv.status = "FINISHED"` is set, both auto-finish and lifecycle finish), `app/backend/main.py` (include router), `app/backend/api/profiles.py` (`results` adds `level` block and per-item `section`)

**Interfaces:**
- Model `SeniorityAssessment` (table `seniority_assessments`): `id`, `user_id` FK, `profile_id` FK nullable, `interview_id` FK (unique with `policy_version`), `track`, `policy_id`, `policy_version`, `policy_status`, `assessed_level`, `highest_supported_level`, `assessment_status`, `result` JSON (`result_to_json`), `rubric_versions` JSON (`{action_id: version}` of rubrics used), `desired_level` (copied for display only), `created_at`. Immutable: no update path.
- `attempt_evidence(db, interview_id) -> dict[str, CriterionEvidence]` (effective rows via `effective_rows`; `evidence_turns` = distinct `turn_id`s of **all non-null revisions** of that criterion) and `finalize_level(db, iv, policy=None) -> SeniorityAssessment` (idempotent per `(interview_id, policy_version)`; never overwrites).
- API: `GET /api/v1/interviews/{id}/level` (owner only; finished attempts; returns stored row or computes+stores lazily for legacy attempts), `GET /api/v1/profiles/{id}/level` (latest finished attempt of that profile only). Payload: `desired_level`, `assessed_level`, `highest_supported_level`, `assessment_status`, `policy {id, version, status}`, `coverage_by_level`, `confirmed_strengths`, `critical_gaps`, `unassessed_criteria`, `evidence_references`, `explanation`, `interview_id`, `created_at`, `note` («Потребує експертної валідації» for WORKING_ASSUMPTION). `results` adds `level` (same payload, no extra request) and per item `section ∈ {"DESIRED_LEVEL","OTHER_FITTING","UNRESOLVED_OR_GAPS"}` where `DESIRED_LEVEL` = `seniority == desired_level.upper()` (`lead` counts as SENIOR), `OTHER_FITTING` = not desired and `fits` and `z != 0`, else `UNRESOLVED_OR_GAPS`; item order, filters, pagination and the ranking are unchanged (sections are labels).

- [ ] **Step 1: Write failing tests:** `test_level_stored_on_finish_with_policy_version_and_attempt` (row has `interview_id`, `policy_version=="v1"`, `created_at`, rubric versions), `test_policy_version_change_does_not_rewrite_history` (monkeypatch a `v2` policy: old row unchanged, a new row only when explicitly finalized with it), `test_attempts_are_not_mixed` (two attempts of one profile with different evidence → each level uses only its own rows; `/profiles/{id}/level` = latest finished attempt), `test_desired_level_change_does_not_change_result` (PUT profile `target_level` then recompute from same evidence → identical `assessed_level` and `result`), `test_level_does_not_change_ranking_key` (`/recommendations` and `/results` item order, `z`, `x`, `l_*` identical with level present vs rows deleted), `test_owner_isolation_level_endpoint`, `test_unauthenticated_level_401`, `test_sections_partition_same_items` (union of sections == all items, no vacancy dropped, no duplicates), `test_results_level_block_for_marketing_is_unknown_policy_unavailable`; migration test as `test_migration_0014/0015` pattern (add/remove, idempotent).
- [ ] **Step 2–4:** red → implement → green. **Step 5: Commit** `feat(seniority): persist and expose assessed level`.

### Task 6: Frontend results

**Files:**
- Create: `app/frontend/src/components/LevelSummary.tsx`, `app/frontend/src/lib/levelView.ts`, `app/frontend/src/lib/levelView.test.ts`, `app/frontend/e2e/level.spec.ts`
- Modify: `app/frontend/src/screens/ResultsScreen.tsx`, `app/frontend/src/types.ts`

**Interfaces:** `levelView.ts`: `levelLabel(l: 'JUNIOR'|'MIDDLE'|'SENIOR'|'UNKNOWN'): string` («Junior», «Middle», «Senior», «Недостатньо даних»), `desiredLabel(v: string|null): string`, `groupBySection(items): Record<Section, Item[]>` (stable order, never drops an item), `sectionTitle(s): string` («Вакансії бажаного рівня», «Інші вакансії, що підходять за підтвердженими вимогами», «Вакансії з невирішеними або невиконаними критичними вимогами»). `LevelSummary` shows «Бажаний рівень: X», «Підтверджений рівень: Y», explanation lines, collapsible lists «Підтверджено», «Прогалини», «Не перевірено» (criterion names via the existing competency names where available, else id), the policy note, and no probability/percent of employment. The vacancy list renders the three sections from `groupBySection`; the existing cards/percent/filters stay.

- [ ] **Step 1: Failing vitest tests:** `levelLabel` for all four values, `groupBySection` keeps total count and order, empty sections omitted, `sectionTitle` strings.
- [ ] **Step 2–4:** implement; `npm run typecheck && npm test && npm run build`; Playwright `level.spec.ts`: register via API, finished attempt with stubbed level via API fixtures is not possible without LLM, so the spec asserts the page shows «Бажаний рівень» and «Недостатньо даних» for an attempt finished without evaluator (UNKNOWN) and that the three section headings never remove vacancies (`count` of cards = API total). **Step 5: Commit** `feat(seniority): results show desired vs assessed level`.

### Task 7: Scenarios, docs, report, full verification

**Files:**
- Create: `app/scripts/seniority_scenarios.py`, `app/tests/test_seniority_scenarios.py`, `docs/tasks/SENIORITY_REPORT.md`, `docs/tasks/THESIS_SYNC_SENIORITY.md`
- Modify: `docs/tasks/MATH_SPEC.md` (§3e), `docs/tasks/STATUS.md`, `architecture.md`, `README.md`

**Interfaces:** `seniority_scenarios.py` builds the three end-to-end scenarios through the real API with the simulated evaluator pattern of `scripts/chapter4/simulation.py` (label SIMULATED): (1) desired Senior, confirmed Middle; (2) sufficient Senior evidence; (3) strong separate answers but insufficient coverage → `UNKNOWN`. Each prints criteria/evidence, estimator result, reasons, unassessed criteria and the top vacancies; `test_seniority_scenarios.py` asserts the three expected levels and statuses.

- [ ] **Step 1:** Write the scenario script and its test (red → green). Cover the remaining mandatory tests not already placed: 12-scenario checklist mapping in the report (1 → `test_desired_level_change…`+scenario 1; 2,3,5,6 → estimator tests; 4 → add `test_middle_confirmed_even_if_desired_junior_or_senior` in `test_seniority_estimator.py`; 7 → `test_self_rating_and_years_do_not_raise_level` in `test_seniority_api.py` (set years/self-ratings, evidence unchanged → identical result); 8 → Task 5; 9 → Task 5; 10 → Task 5; 11 → Task 5; 12 → Task 4), plus `test_level_independent_of_partial_topic_coverage` (assessed level equals the result computed from criterion evidence even when `E_c` of every topic is < 0.6, and changing `MIN_COVERAGE_FOR_OVERALL` leaves it unchanged).
- [ ] **Step 2:** Docs: MATH_SPEC §3e (definitions of statuses, tau/ε use, hierarchy, no compensation, UNKNOWN rule, policy version immutability, WORKING_ASSUMPTION flag); THESIS_SYNC_SENIORITY.md lists chapter 1 (definition of professional level vs desired level), chapter 2 (formalization: `C_L`, `A_L`, `K_L`, `G_L`, `S_L ⇔ …`, hierarchy, practice criteria), chapter 3 (architecture/data model, API, UI) changes; SENIORITY_REPORT.md: changed files, migrations, test results (real outputs), three scenarios, unresolved issues and scientific-validity limits (working-assumption policy, template rubrics, no expert validation, small interview budget → frequent UNKNOWN, simulated evaluator in scenarios, marketing/design unsupported).
- [ ] **Step 3:** Verify with real commands: `cd app && uv run pytest -q`; `cd app/frontend && npm run typecheck && npm test && npm run build`; `docker compose up -d --build` then `npx playwright test`; migration 0016 applied in PostgreSQL (`select version_num from alembic_version`). Record outputs; disclose anything not run.
- [ ] **Step 4: Commit** `docs+test(seniority): scenarios, report, thesis sync notes`.
