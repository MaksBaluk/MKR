# Phase 1 — Criterion-level core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Matching, planning and follow-ups work on individual rubric criteria (`D_vga`) instead of a per-competency mean; Evaluator returns a structured gap goal; self-ratings act only as tie-breakers (`T_v`, `J_v`, planner verify flag).

**Architecture:** Pure domain functions (`app/backend/domain/`) take criterion-keyed scores plus a rubric map `{action_id: [(criterion_id, weight)]}`. API layer builds both from `CriterionAssessment` rows and `Rubric` tables and passes them in. Follow-up goal is validated in Python against deterministic "open criteria", stored on `core_turns`, and fed to the Interviewer.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Alembic, pydantic, LangGraph, pytest (`cd app && uv run pytest -q`).

**Spec:** `docs/superpowers/plans/2026-11-17-adaptive-assessment-roadmap.md`, `docs/tasks/MATH_SPEC.md` §2–5, thesis (2.4)–(2.15), docx lines 450–524.

## Global Constraints

- Criterion score `∈[0,1]` or `null`; `null` is never `0`, never defaulted.
- Max 10 distinct topics, max 5 shown questions per action; min-two rule in `interview_budget.py` stays.
- Self-rating never closes a group, never becomes an assessment, never touches Z/X/L/W; only tie-break after (2.15) key.
- Ranking key `(Z,X,L^M,L^P,-W^M,-W^P)` then `T_v`, `J_v`, then vacancy id ASC (docx line 524).
- No `Match/Coverage/R` metrics in user UI. LLM credentials server-side. Ukrainian user text. Do not edit thesis DOCX.
- `D_vga` default = all criteria of the competency's rubric, τ from `TAU_BY_LEVEL`; optional per-alternative `criterion_ids` in the revision overrides.
- Constants: `CONFIRMED_SCORE=0.75`, `DECLINED_SCORE=0.05`, `MIN_COVERAGE_FOR_OVERALL=0.6`, `SELF_CLAIM_THRESHOLD=0.7`, `SELF_GAP=0.25`.
- Legacy holistic rows (`criterion_id == action_id`) stay supported: an action without seeded rubric has rubric `[(action_id, 1.0)]`.

## Review Focus

- Action with 1 of 5 criteria assessed at 0.95 → alternative `UNRESOLVED`, `overall_level_allowed=False` (Task 1, 2).
- Vacancy with `criterion_ids=["postgresql.transactions"]` and only that criterion assessed ≥ τ → `SATISFIED` (Task 2).
- Evaluator `followup_goal` naming a criterion not in rubric, or already `CONFIRMED` → goal dropped, no crash (Task 4).
- Provider failure / UNGRADED → no scores, no fabricated goal; question comes from bank (Task 5).
- Self-rating 0.95, no evidence: vacancy stays `Z=1`, only ordering among exact ties changes (Task 6).
- Legacy snapshot revisions without `criterion_ids` and legacy holistic assessment rows still rank (Task 2, 3).

---

### Task 1: Criterion states and topic summary

**Files:**
- Create: `app/backend/domain/topic_summary.py`
- Test: `app/tests/test_topic_summary.py`

**Interfaces:**
- Produces:
```python
RubricCriteria = Sequence[tuple[str, float]]          # (criterion_id, weight β>0)
CONFIRMED_SCORE = 0.75; DECLINED_SCORE = 0.05; MIN_COVERAGE_FOR_OVERALL = 0.6
CriterionState = Literal["UNKNOWN","WEAK","CONFIRMED","DECLINED"]
def criterion_state(score: float | None, sufficient: bool) -> CriterionState
def open_criteria(rubric: RubricCriteria, scores: Mapping[str, float|None], sufficient: bool) -> list[str]  # rubric order; UNKNOWN or WEAK
@dataclass(frozen=True) class TopicSummary: m: float|None; e: float; assessed: tuple[str,...]; unknown: tuple[str,...]; overall_level_allowed: bool
def topic_summary(rubric: RubricCriteria, scores: Mapping[str, float|None]) -> TopicSummary   # (2.8) M_c, (2.9) E_c
```

- [ ] **Step 1: Write failing tests** in `test_topic_summary.py`:
  - `test_one_of_five_high_is_not_overall`: rubric 5×w1, scores `{c1:0.95}` ⇒ `m==0.95`, `e==0.2`, `overall_level_allowed is False`.
  - `test_all_null`: `m is None`, `e==0.0`.
  - `test_weights`: rubric `[(a,1),(b,3)]`, scores `{a:1.0,b:0.5}` ⇒ `m==0.625`, `e==1.0`, allowed True.
  - `test_state`: `criterion_state(None,False)=="UNKNOWN"`, `(0.5,True)=="WEAK"`, `(0.75,False)=="CONFIRMED"`, `(0.0,True)=="DECLINED"`, `(0.0,False)=="WEAK"`.
  - `test_open_criteria_skips_confirmed_and_declined`.
- [ ] **Step 2:** Run `cd app && uv run pytest tests/test_topic_summary.py -q` — expect FAIL (module missing).
- [ ] **Step 3: Implement** in `topic_summary.py`; `criterion_state`: `None→UNKNOWN`; `≥CONFIRMED→CONFIRMED`; `≤DECLINED and sufficient→DECLINED`; else `WEAK`. `overall_level_allowed = e >= MIN_COVERAGE_FOR_OVERALL`.
- [ ] **Step 4:** Run the file — expect PASS.
- [ ] **Step 5: Commit** `feat(domain): criterion states and topic coverage summary`.

### Task 2: Criterion-level group evaluation

**Files:**
- Modify: `app/backend/domain/core_flow.py` (`eval_group`, `planner_state`, `rank_vacancy`, `explain_vacancy`; lines 25–123)
- Test: `app/tests/test_criterion_eval.py`; update `app/tests/test_core_flow.py`, `test_results_fit.py` for new signatures.

**Interfaces:**
- Consumes: `RubricCriteria` (Task 1), `fulfilment_bounds`, `mandatory_status` (`criteria.py`).
- Produces:
```python
RubricMap = Mapping[str, RubricCriteria]   # action_id -> criteria; missing action => [(action_id, 1.0)]
def alt_criteria(alt: Mapping, rubrics: RubricMap) -> list[tuple[str, float]]   # alt.get("criterion_ids") filtered from rubric, else whole rubric
def eval_alternative(alt, scores: Mapping[str,float|None], rubrics: RubricMap) -> GroupEval
def eval_group(alts, scores, rubrics) -> GroupEval        # OR over alternatives
def planner_state(revisions, scores, rubrics, self_flags: frozenset[str] = frozenset()) -> tuple[OpenState, dict]
def rank_vacancy(vacancy, scores, rubrics, user_years, self_ratings=None) -> VacancyRanking   # self_ratings used in Task 6
def explain_vacancy(vacancy, scores, rubrics, names, limit=3) -> dict
```
`scores` is now **criterion-keyed**. Alternative status per MATH_SPEC §4: `SATISFIED` iff every required criterion satisfies its τ; `FAILED` iff any definitely fails; else `UNRESOLVED`. `L/U` via `fulfilment_bounds` over `alt_criteria` with weights β. `open_alternatives` keeps an alternative open while it is not FAILED.

- [ ] **Step 1: Write failing tests** in `test_criterion_eval.py` (rubric `{"pg": [("pg.tx",1),("pg.idx",1),("pg.opt",1),("pg.conc",1),("pg.repl",1)]}`, alt `{"competency_id":"pg","required_level":3}`):
  - `test_one_of_five_unresolved`: scores `{pg.tx:0.95}` ⇒ status `UNRESOLVED`, `lower==0.2`, `upper==1.0` (τ=0.9 ⇒ h=1).
  - `test_all_five_satisfied`: all 0.95 ⇒ `SATISFIED`, `lower==1.0`.
  - `test_one_definite_fail`: `{pg.tx:0.95, pg.idx:0.2}` ⇒ `FAILED`.
  - `test_vacancy_specific_subset`: alt with `"criterion_ids":["pg.tx"]`, scores `{pg.tx:0.95}` ⇒ `SATISFIED`.
  - `test_or_group_max_not_sum`: two alternatives, bounds are `max`.
  - `test_legacy_action_without_rubric`: `rubrics={}`, scores `{"pg":0.8}` level 2 ⇒ `SATISFIED`.
  - `test_null_is_not_zero`: all-null ⇒ `lower==0`, `upper==1`, `UNRESOLVED`, never `FAILED`.
  - `test_planner_state_keeps_group_open_until_all_criteria`: group stays in `open_groups` with 1/5 criteria.
- [ ] **Step 2:** Run `uv run pytest tests/test_criterion_eval.py -q` — expect FAIL.
- [ ] **Step 3: Implement** the signatures above; keep `tau_for`, `TAU_BY_LEVEL`, `GroupEval` unchanged. `explain_vacancy` `groups_assessed` counts groups with any criterion score.
- [ ] **Step 4:** Update call sites in existing tests; run `uv run pytest tests/test_criterion_eval.py tests/test_core_flow.py tests/test_ranking.py -q` — PASS (callers in `api/` are fixed in Task 3; run only these files here).
- [ ] **Step 5: Commit** `feat(domain): criterion-level group evaluation (D_vga)`.

### Task 3: Wire criterion scores and rubric map through the API

**Files:**
- Modify: `app/backend/api/core.py` (`_action_scores` 54–78, `next_question` ~196–222), `app/backend/api/recommendations.py`, `app/backend/api/profiles.py` (214, 252, 292–297)
- Test: `app/tests/test_results_competencies.py`, `test_results_fit.py`, `test_results_order_percent.py` (update), new `app/tests/test_partial_topic_api.py`

**Interfaces:**
- Consumes: Task 2 signatures.
- Produces in `api/core.py`:
```python
def criterion_scores(rows) -> dict[str, float | None]            # latest revision per criterion_id; legacy-row rule via current_criteria_rows
def rubric_map(db: Session, action_ids: Iterable[str]) -> RubricMap  # from _seeded_criteria (id, weight)
def action_summary(rows, rubrics) -> dict[str, TopicSummary]
```
`_action_scores` stays for display only (mean M_c); it must now use `topic_summary` so `M_c` is weighted by β. `attempt_scores` and `latest_scores` return **criterion** scores; callers needing action M_c use `action_summary`.

- [ ] **Step 1: Write failing API test** `test_partial_topic_api.py`: seed an interview with one assessed criterion of a 5-criterion rubric at 0.95; `GET` results/recommendations for that attempt returns vacancies requiring that competency with `Z==1` semantics (not in "fitting" top as confirmed) and the competency row has `coverage==0.2`, `overall_level_allowed False`. Add the test with a vacancy-level criterion subset (via cohort revision `criterion_ids`) ⇒ requirement counts as met. Reuse fixtures from `test_results_fit.py`.
- [ ] **Step 2:** Run it — FAIL.
- [ ] **Step 3: Implement** helpers; pass `rubric_map(db, actions in cohort)` and criterion scores into `planner_state`, `rank_vacancy`, `explain_vacancy`, `eval_group` in all call sites listed (grep `eval_group|rank_vacancy|explain_vacancy|planner_state|attempt_scores|latest_scores`). Expose `coverage` (E_c) and `overall_level_allowed` on result competency items without adding a user-facing percent label.
- [ ] **Step 4:** Run `uv run pytest -q` — all existing + new pass; fix regressions caused by the mean→criterion change.
- [ ] **Step 5: Commit** `feat(api): rank and plan on criterion scores with rubric map`.

### Task 4: Structured `followup_goal` and Evaluator prompt

**Files:**
- Modify: `app/backend/domain/assessment.py` (lines 14–66), `app/backend/agents/prompts.py` (Evaluator system + `format_evaluator_input`), `app/backend/agents/graphs.py` (`validate_output`)
- Test: `app/tests/test_followup_goal.py`, update `test_prompts.py`, `test_graphs.py`

**Interfaces:**
- Produces:
```python
class FollowupGoal(BaseModel): criterion_ids: list[str] = Field(min_length=1); reason: str = Field(min_length=1); expected_evidence: str = ""
EvaluatorOutput.followup_goal: FollowupGoal | None   # legacy str/list coerced to None (no concrete gap => no goal)
def sanitize_goal(goal: FollowupGoal | None, allowed: set[str], open_ids: Sequence[str]) -> FollowupGoal | None
```
`sanitize_goal` keeps only `criterion_ids ∈ allowed ∩ open_ids`; empty remainder ⇒ `None`. `validate_against_context` stays strict on criterion ids of `criteria`; goal ids are filtered, not an error (a bad goal must not discard an otherwise valid assessment). Evaluator prompt asks for `followup_goal` as the JSON object above, only for a concrete gap; the evaluator input includes per-criterion `open` flags computed by Python.

- [ ] **Step 1: Failing tests:** `test_goal_dropped_when_criterion_unknown`; `test_goal_dropped_when_criterion_confirmed`; `test_goal_kept_for_open_criterion`; `test_legacy_string_goal_becomes_none`; `test_needs_followup_without_goal_is_allowed` (no goal created); prompt test: Evaluator input mentions open criteria ids and the JSON shape of `followup_goal`.
- [ ] **Step 2:** Run `uv run pytest tests/test_followup_goal.py -q` — FAIL.
- [ ] **Step 3: Implement.** Pydantic `field_validator("followup_goal", mode="before")` returns `None` for str/list, dict otherwise. Apply `sanitize_goal` in `validate_output` of the answer graph (needs `open_ids` in `AnswerState`; add key `open_criterion_ids: list[str]`).
- [ ] **Step 4:** `uv run pytest tests/test_followup_goal.py tests/test_prompts.py tests/test_graphs.py -q` — PASS.
- [ ] **Step 5: Commit** `feat(evaluator): structured followup_goal tied to rubric criteria`.

### Task 5: Persist goal and target criteria; targeted Interviewer questions

**Files:**
- Modify: `app/backend/models.py` (`CoreTurn`), `app/backend/api/core.py` (`_assess_action`, `next_question`), `app/backend/agents/graphs.py` (`AskState`), `app/backend/agents/prompts.py` (`format_interviewer_input`)
- Create: `app/alembic/versions/0009_turn_followup_targets.py`
- Test: `app/tests/test_followup_flow.py`, update `test_migration*.py` style test for 0009

**Interfaces:**
- Consumes: `open_criteria` (Task 1), `FollowupGoal` (Task 4), `criterion_scores`, `rubric_map` (Task 3).
- Produces: `core_turns` new nullable columns `target_criteria` JSON (criteria the question is meant to test), `followup_reason` Text, `eval_goal` JSON (goal the Evaluator emitted after this turn's answer). `AskState.followup_goal: dict | None`, `AskState.unmet_criteria` now = open criteria only. `format_interviewer_input(..., followup_goal: dict | None, ...)` renders `criterion_ids`, `reason`, `expected_evidence`; prompt rule "do not repeat confirmed criteria".

- [ ] **Step 1: Failing tests** (`test_followup_flow.py`, fake model like in `test_graphs.py`/`test_interview_flow.py`):
  - Evaluator confirms `pg.idx` (0.9), leaves `pg.tx` null with goal on `pg.tx` ⇒ next question's `AskState` has `unmet_criteria==["pg.tx", …open]` without `pg.idx`, `followup_goal.criterion_ids==["pg.tx"]`, new turn row has `target_criteria==["pg.tx"]` and `followup_reason` set.
  - All criteria confirmed after answer 1 ⇒ topic not re-asked (early close), next question belongs to another action.
  - UNGRADED answer ⇒ no scores written, `eval_goal` is `None`, fallback bank used.
  - 5-question cap and 10-topic cap still enforced (existing tests pass).
  - Migration upgrade/downgrade for 0009 on SQLite.
- [ ] **Step 2:** Run — FAIL.
- [ ] **Step 3: Implement.** In `_assess_action`: compute `open_ids` before calling `run_answer`, store `turn.eval_goal = goal.model_dump()` after acceptance. In `next_question`: for the chosen action compute open criteria from latest criterion scores + `sufficient`; if none are open and the topic already has ≥1 graded answer, treat topic as closed (extend `eligible`/`needs_second`: min-two rule applies only while open criteria remain); pass `followup_goal` from the last answered turn's `eval_goal`; write `target_criteria` = goal ids or open criteria; `followup_reason` = goal.reason or `"OPEN_CRITERIA"`.
- [ ] **Step 4:** `uv run pytest -q` — PASS.
- [ ] **Step 5: Commit** `feat(interview): follow-up targets concrete criterion gaps`.

### Task 6: Self-rating tie-break (`T_v`, `J_v`) and planner verify flag

**Files:**
- Modify: `app/backend/domain/ranking.py`, `app/backend/domain/core_flow.py`, `app/backend/domain/topic_summary.py`, `app/backend/api/core.py` + `app/backend/api/profiles.py` (pass self-ratings; `latest_self_ratings` in `api/profile.py`)
- Test: `app/tests/test_self_rating_tiebreak.py`, update `test_ranking.py`

**Interfaces:**
- Produces:
```python
VacancyRanking += t_v: float = 0.0; j_v: float = 0.0
sort_key -> (-z, -x, -l_m, -l_p, w_m, w_p, -t_v, -j_v, vacancy_id)
def self_claim_metrics(groups, self_ratings: Mapping[str, float|None]) -> tuple[float, float]  # (T_v, J_v) per docx line 524; b_vg = max known r_a over group alternatives
def needs_verification(self_rating: float|None, summary: TopicSummary|None) -> bool  # r>=SELF_CLAIM_THRESHOLD and (summary is None or summary.e<MIN_COVERAGE or (summary.m is not None and r - summary.m >= SELF_GAP))
```
`planner_state(..., self_flags)` sets `OpenState.self_rating_needs_verification` from `needs_verification` over open-alternative actions. Self-ratings are never copied into scores.

- [ ] **Step 1: Failing tests:**
  - `test_tv_jv_hand_example`: groups g1 alts{a:0.8,b:0.4}, g2 alts{c: unrated}, g3 alt{d:0.6} ⇒ `b_g1=0.8`, `T=(0.8+0.6)/3`, `J=2/3`.
  - `test_tie_break_only_on_exact_key_tie`: two vacancies, equal (2.15) key, higher `T_v` first; unequal `L^M` ⇒ self-rating ignored.
  - `test_self_rating_cannot_satisfy_mandatory`: rating 0.95 ⇒ `Z` stays 1, group `UNRESOLVED`, `l_m==0`.
  - `test_missing_self_rating_not_penalised`: unrated vacancy ties equal to rated-null one (`T=J=0` both).
  - `test_planner_prefers_self_claimed_action_on_tie`: two actions with equal gain/mandatory/`I(c)`, flagged one chosen even if id sorts later.
  - `test_needs_verification` cases: r=0.95,no evidence ⇒ True; r=0.95,m=0.9,e=1.0 ⇒ False; r=0.95,m=0.5,e=1.0 ⇒ True; r=0.3 ⇒ False.
  - API: real endpoint order equals formula (2.15) + `T_v/J_v` for a seeded cohort (extend `test_results_order_percent.py`).
- [ ] **Step 2:** Run — FAIL.
- [ ] **Step 3: Implement.** Round nothing; `T_v` normalizes by total group count `|G_v|` (0 groups ⇒ 0.0).
- [ ] **Step 4:** `uv run pytest -q` — PASS.
- [ ] **Step 5: Commit** `feat(ranking): self-rating tie-breakers T_v/J_v and planner verify flag`.

### Task 7: Docs and full verification

**Files:**
- Modify: `docs/tasks/MATH_SPEC.md` (add §3a topic coverage vs score + criterion states + goal contract; §5 `T_v/J_v` tie-break; constants table), `docs/tasks/STATUS.md`, `architecture.md` (follow-up flow)

- [ ] **Step 1:** Update the three docs (policy constants listed in Global Constraints; note option (a) `D_vga` limitation).
- [ ] **Step 2:** Run `cd app && uv run pytest -q`; record counts. Run `cd app/frontend && npm run typecheck && npm test && npm run build` (frontend types: add optional `coverage`, `overall_level_allowed` to result competency type in `src/types.ts` if the API now returns them).
- [ ] **Step 3:** Record genuine outcomes in `STATUS.md`; state Docker/browser/provider checks not run unless run.
- [ ] **Step 4: Commit** `docs: criterion core spec and status`.

## Self-review

- Spec coverage: points 1 (Tasks 4–5), 3 (Task 6), pasted completeness rules 1–7 (Tasks 1–3, 5), tests 1,2,6,7,8,9 (Tasks 2–6). Points 2, 4–10 belong to Phases 2–4 in the roadmap.
- Types consistent: `RubricMap`/`RubricCriteria` defined in Tasks 1–2 and reused in 3–6; `FollowupGoal` in 4 used in 5.
- Risk: replacing the action mean with criterion-level checks makes vacancies harder to satisfy; existing percent/"fitting" tests will need updates and the 40% threshold in `fitting` may need owner review (flagged in `TODO.md` §5).
