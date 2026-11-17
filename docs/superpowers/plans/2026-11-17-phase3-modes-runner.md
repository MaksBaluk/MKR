# Phase 3 — Interview modes A/B/C and reproducible runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the same candidates, cohort snapshot, rubrics, Evaluator and ranking under INITIAL_PROFILE, STATIC_INTERVIEW and ADAPTIVE_INTERVIEW (with per-feature ablation flags), record everything needed to reproduce the run, and re-rank from stored scores without calling the LLM.

**Architecture:** One interview engine (`api/core.py::next_question`) reads an optional `ExperimentConfig` stored on `core_interviews.mode_config`; with no config it behaves exactly as today (= fully adaptive, product behaviour). The three flags (`adaptive_topics`, `adaptive_followup`, `adaptive_difficulty`) switch the planner, the follow-up targeting/early-close and the DifficultyController independently; STATIC = all three off, with the topic list fixed in `core_interviews.static_plan` before the first question. A runner under `app/backend/experiments/` drives the real HTTP API through FastAPI `TestClient` with an `AnswerProvider`, stores one `experiment_runs` row per run, and `rerank()` recomputes the ranking from stored data.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Alembic, pydantic, pytest (`cd app && uv run pytest -q`).

**Spec:** `docs/superpowers/plans/2026-11-17-adaptive-assessment-roadmap.md` (Phase 3), `docs/tasks/MATH_SPEC.md` §2, §6, §3a, §3c; thesis docx lines 523–524 (mode A ranking uses the same key, self-ratings only break ties).

## Global Constraints

- Equal conditions for B and C: same max topics (≤10), same max questions per topic (≤5), same `total_budget`, same rubrics, Evaluator/prompt versions, matching/ranking code, cohort snapshot.
- Mode A: no LLM, no interview; ranking = same key (2.15) with all criteria unknown; self-ratings only through `T_v`/`J_v` tie-break; never converted to criterion scores.
- STATIC: topic list and per-topic question count fixed before the first answer, stored on the interview, never rebuilt; per-slot target criteria and difficulty fixed; no goal targeting, no early close, no controller; the Evaluator, scoring and ranking are identical to ADAPTIVE.
- ADAPTIVE = today's behaviour. Ablation flags change only their own component.
- Product caps unchanged: `max_topics ≤ 10`, `max_per_topic ≤ 5` (config validation rejects larger). No user-facing mode switch; experiment config is set server-side (runner writes the interview row), never accepted from the public API.
- An LLM failure must never produce a fabricated grade (existing UNGRADED path); failures are recorded in the run (`errors`, fallback counts).
- `null` is never `0`. Ground-truth/expert labels must never be read by `backend/domain` or `backend/api` (Phase 4 enforces by test).
- Same snapshot + same deterministic code ⇒ same ranking; LLM calls are not promised to be deterministic.
- Do not edit thesis DOCX. No scraping, ESCO, trained model, UI changes.

## Review Focus

- STATIC plan must not change after answers; ADAPTIVE may (Task 3, 5).
- Total budget exhausted mid-topic ⇒ interview finishes, unevaluated criteria stay `null` (Task 3).
- Mode A with a profile that has self-ratings but no interview: no criterion score appears anywhere in the output (Task 4).
- Provider failure during a run ⇒ ungraded turns counted in `errors`, no scores invented, run still stored (Task 4, 5).
- Legacy/product interviews with `mode_config IS NULL` behave exactly as before (Task 2, 3).
- A candidate with fewer cohort topics than `max_topics` (small plan) or an empty cohort (N=0): runner reports it, no crash (Task 1, 4).

---

### Task 1: Experiment config and deterministic static plan (pure)

**Files:**
- Create: `app/backend/experiments/__init__.py`, `app/backend/experiments/config.py`, `app/backend/experiments/planning.py`
- Test: `app/tests/test_experiment_planning.py`

**Interfaces:**
- Consumes: `choose_next`, `OpenState` (`domain/planner.py`), `planner_state`, `RubricMap` (`domain/core_flow.py`), `MAX_TOPICS`, `MAX_SHOWN_QUESTIONS_PER_ACTION` (`domain/interview_budget.py`).
- Produces:
```python
class InterviewMode(str, Enum): INITIAL_PROFILE="INITIAL_PROFILE"; STATIC_INTERVIEW="STATIC_INTERVIEW"; ADAPTIVE_INTERVIEW="ADAPTIVE_INTERVIEW"
@dataclass(frozen=True) class ExperimentConfig:
    mode: InterviewMode
    adaptive_topics: bool = True; adaptive_followup: bool = True; adaptive_difficulty: bool = True
    max_topics: int = 10; max_per_topic: int = 5; total_budget: int | None = None
    static_questions_per_topic: int = 2
    # __post_init__ raises ValueError if max_topics>10, max_per_topic>5, static_questions_per_topic>max_per_topic, total_budget<1
    def to_json(self) -> dict; @classmethod def from_json(cls, d: dict) -> "ExperimentConfig"
def config_for(mode: InterviewMode, **overrides) -> ExperimentConfig   # STATIC => the three flags forced False (overrides of them rejected); ADAPTIVE => flags from overrides (default True); INITIAL => flags irrelevant
def plan_topics(revisions: Sequence[Mapping], rubrics: RubricMap, mass: Mapping[str, float], max_topics: int) -> list[str]
def slot_targets(criteria: Sequence[str], k: int, slot: int) -> tuple[str, ...]   # round-robin partition: criteria[slot::k]; k>=1, 0<=slot<k
def static_plan_json(topics: Sequence[str], cfg: ExperimentConfig) -> dict   # {"topics":[...],"questions_per_topic":k,"total_budget":cfg.total_budget}
```
`plan_topics` = static greedy coverage with NO answers: start from `planner_state(revisions, {}, rubrics)`, repeatedly `choose_next` over all actions in `open_alternatives`, then close every group containing the chosen action (assumed covered) and repeat until `max_topics` or zero marginal gain. Deterministic (ties as in `choose_next`).

- [ ] **Step 1: Failing tests** in `test_experiment_planning.py`:
  - `test_config_rejects_caps_above_product_limits` (`max_topics=11`, `max_per_topic=6`, `static_questions_per_topic=6`, `total_budget=0` ⇒ ValueError).
  - `test_static_forces_flags_off` / `test_static_rejects_flag_overrides` / `test_adaptive_ablation_flags`.
  - `test_json_roundtrip`.
  - `test_plan_topics_deterministic_and_greedy` on a hand-built 3-vacancy revision set (hand-computed order and that a topic covering more groups comes first), same input twice ⇒ same list.
  - `test_plan_topics_respects_max_topics_and_stops_at_zero_gain`.
  - `test_plan_topics_empty_cohort_returns_empty`.
  - `test_slot_targets_partition`: 5 criteria, k=2 ⇒ `(c0,c2,c4)` and `(c1,c3)`; union equals all, no overlap.
- [ ] **Step 2:** Run `cd app && uv run pytest tests/test_experiment_planning.py -q` — expect FAIL (module missing).
- [ ] **Step 3: Implement** the signatures above (pure, no DB).
- [ ] **Step 4:** Run the file — expect PASS.
- [ ] **Step 5: Commit** `feat(experiments): config and deterministic static topic plan`.

### Task 2: Persistence — interview mode config, static plan, experiment runs

**Files:**
- Modify: `app/backend/models.py` (`CoreInterview`, new `ExperimentRun`)
- Create: `app/alembic/versions/0011_experiments.py`
- Test: `app/tests/test_migration_0011.py` (pattern: `test_migration_0010.py`)

**Interfaces:**
- Produces: nullable `core_interviews.mode_config` JSON and `core_interviews.static_plan` JSON. New table `experiment_runs`: `id` (uid), `experiment_id` String(64) index, `candidate_id` String(120), `mode` String(24), `config` JSON, `cohort_id` String(36), `cohort_sha256` String(64), `profile_snapshot` JSON, `rubric_versions` JSON, `prompt_version` String(64), `model_info` JSON, `algorithm_version` String(64), `interview_id` String(36) nullable, `qa` JSON, `assessments` JSON, `ranking` JSON, `timings` JSON, `errors` JSON, `created_at`. No foreign keys to interviews/cohorts (records must survive cleanup); upgrade/downgrade idempotent like 0009/0010; revision id ≤ 32 chars, `down_revision="0010_turn_difficulty"`.

- [ ] **Step 1: Failing test:** upgrade adds the two columns and the table; downgrade removes them keeping existing interview rows; re-upgrade idempotent; NULL for legacy interviews.
- [ ] **Step 2:** Run it — FAIL.
- [ ] **Step 3: Implement** model + migration.
- [ ] **Step 4:** Run `tests/test_migration_0011.py tests/test_migration_0010.py` — PASS.
- [ ] **Step 5: Commit** `feat(db): interview mode config and experiment runs`.

### Task 3: Interview engine honours the experiment config

**Files:**
- Modify: `app/backend/api/core.py` (`next_question`; interview creation helper `create_attempt` is in `api/common.py` — only add what the runner needs), `app/backend/domain/difficulty.py` only if a small pure helper is needed
- Test: `app/tests/test_modes_flow.py`

**Interfaces:**
- Consumes: Task 1 (`ExperimentConfig`, `plan_topics`, `slot_targets`), Task 2 columns, existing helpers in `next_question` (`open_ids`, `goal_for`, `initial_difficulty`, controller).
- Produces: `next_question` reads `iv.mode_config` (`None` ⇒ default adaptive config, behaviour byte-identical to today). Per flag:
  - `adaptive_topics=False`: topic order = `iv.static_plan["topics"]` (the next topic whose shown count < its quota); the planner (`choose_next`) is not called; if `static_plan` is NULL it is computed once on first call via `plan_topics` and stored.
  - `adaptive_followup=False`: every started topic gets exactly `cfg.static_questions_per_topic` questions (bounded by `max_per_topic`), the question for slot *i* targets `slot_targets(criteria_for(topic), k, i)`, `followup_goal` is not passed, no early close and no min-two logic; `followup_reason="STATIC_SLOT"`.
  - `adaptive_difficulty=False`: `initial_difficulty` for every question of the topic, `difficulty_reason="FIXED:<reason>"`, no controller step.
  - `total_budget`: when the number of shown questions in the interview reaches it, mark the interview `FINISHED` (same completion response as plan exhaustion).
  - `max_topics`/`max_per_topic` from the config replace the module constants in the eligibility checks (never above product limits).
- Evaluation (`_assess_action`) and ranking code are NOT changed: all modes use the same Evaluator and scoring.

- [ ] **Step 1: Failing tests** (`test_modes_flow.py`, reuse `PolicyChat`, `_start/_next/_answer/_use` from `tests/test_followup_flow.py`; set `mode_config`/`static_plan` directly on the `CoreInterview` row via the `db` fixture before the first next-question):
  - `test_no_config_behaves_as_before` (the existing suites already cover; add one check that `mode_config is None` interview asks the same first question action as an explicit `ADAPTIVE` config).
  - `test_static_plan_fixed_before_first_question`: `static_plan` stored at the first call; after scripted strong/weak answers the stored plan and the sequence of topics are unchanged.
  - `test_adaptive_plan_can_differ_after_answers`: same candidate/cohort, scripted answers that close a vacancy group ⇒ adaptive topic sequence differs from the static plan.
  - `test_static_asks_fixed_slots_without_goal`: each topic has exactly `k` questions with `target_criteria == slot_targets(...)`, `followup_reason == "STATIC_SLOT"`, no early close even after a strong sufficient first answer.
  - `test_ablation_flags_are_independent` (parametrize the 3 flags off one at a time: only the matching behaviour changes — topic order / slot targeting / FIXED difficulty).
  - `test_total_budget_finishes_interview_and_keeps_nulls`: `total_budget=3` ⇒ exactly 3 shown questions then `done`; criteria never asked stay `null` in assessments (no rows with fabricated 0).
  - `test_caps_hold_in_static_and_adaptive` (≤5 per topic, ≤10 topics) for both modes.
- [ ] **Step 2:** Run `uv run pytest tests/test_modes_flow.py -q` — FAIL.
- [ ] **Step 3: Implement** as specified; keep the default path untouched (all existing tests must pass unchanged: `test_interview_budget`, `test_followup_flow`, `test_difficulty_flow`, `test_interview_completion`, `test_interview_flow`).
- [ ] **Step 4:** Run `cd app && uv run pytest -q` — PASS.
- [ ] **Step 5: Commit** `feat(interview): experiment modes and ablation flags in the engine`.

### Task 4: Runner, answer providers, stored runs, re-ranking, CLI

**Files:**
- Create: `app/backend/experiments/providers.py`, `app/backend/experiments/runner.py`, `app/backend/experiments/store.py`, `app/scripts/run_experiment.py`
- Test: `app/tests/test_experiment_runner.py`

**Interfaces:**
- Consumes: Tasks 1–3; real API through `fastapi.testclient.TestClient(backend.main.app)`; `rank_items` (`api/recommendations.py`), `rank_vacancy`, `rubric_map`, `criterion_scores` (`api/core.py`).
- Produces:
```python
@dataclass(frozen=True) class CandidateSpec: candidate_id: str; desired_title: str; years_experience: int | None; target_level: str | None; track: str | None; location: str; work_mode: str | None; self_ratings: dict[str, float]   # action_id -> 0..1; absent = unknown
class AnswerProvider(Protocol): def answer(self, candidate: CandidateSpec, turn: Mapping[str, Any]) -> str   # turn has action_id, question_text, ordinal_in_topic
class ScriptedProvider:  # JSON file {"<candidate_id>": {"<action_id>": ["answer1","answer2",...], "default": "Не знаю."}}; missing ⇒ default; marks results SCRIPTED
@dataclass class ExperimentRecord: experiment_id: str; candidate_id: str; mode: str; config: dict; cohort_id: str; cohort_sha256: str; profile_snapshot: dict; rubric_versions: dict; prompt_version: str; model_info: dict; algorithm_version: str; qa: list[dict]; assessments: list[dict]; ranking: list[dict]; timings: dict; errors: dict; answer_source: str   # "SCRIPTED"|"HUMAN"|"SIMULATED"
def run_experiment(experiment_id: str, cfg: ExperimentConfig, candidate: CandidateSpec, provider: AnswerProvider | None, client: TestClient, db: Session) -> ExperimentRecord
def rerank(record: ExperimentRecord, db: Session) -> list[dict]   # recompute from stored assessments + profile snapshot + the stored cohort snapshot; NO model call
def save_record(db: Session, record: ExperimentRecord) -> str; def load_record(db: Session, run_id: str) -> ExperimentRecord
def export_records(records: Sequence[ExperimentRecord], out_dir: Path) -> None   # runs.json + runs.csv (one row per run: ids, mode, config flags, n_questions, n_assessed_criteria, errors, durations)
```
`run_experiment`: registers a throwaway user, creates the profile and self-ratings through the API, builds the cohort (`POST /cohorts/auto`), then:
- `INITIAL_PROFILE`: no interview, no LLM; ranking = `rank_items(..., scores={}, self_ratings=...)`; `qa=[]`, `assessments=[]`.
- `STATIC_INTERVIEW` / `ADAPTIVE_INTERVIEW`: creates the attempt via `create_attempt`, sets `mode_config` (and `static_plan` for static) on the row, loops next-question → `provider.answer` → answers until `done`; records `qa`, per-turn `assessment_status`, the latest criterion assessments, then ranks. LLM wait time is measured by wrapping `backend.api.core.get_chat_model`'s model in a timing proxy during the run (`timings = {"total_s", "llm_wait_s", "calls"}`); `errors = {"ungraded_answers": n, "fallback_questions": n, "llm_exceptions": n}`. `prompt_version` = sha256 of the Interviewer+Evaluator system prompts; `model_info` from `get_settings()` (provider, model, temperature) or `{"provider": None}` when no model; `algorithm_version` = constant `"rank-2.15+tv-jv/v1"`; `rubric_versions` from the rubrics used.
- The CLI `run_experiment.py`: `--db sqlite:///...` (required; creates schema and seeds like the tests' conftest, never defaults to the product DB), `--candidates candidates.json`, `--answers answers.json`, `--modes`, `--flags` for ablations, `--total-budget`, `--out dir`; refuses to run an interview mode when no LLM is configured unless `--allow-ungraded` is given (records then show ungraded). Prints the output directory and run ids.

- [ ] **Step 1: Failing tests** (`test_experiment_runner.py`, fake chat via the same `_use` helper; client/db fixtures from conftest):
  - `test_mode_a_has_no_scores_and_uses_self_ratings_only_as_tiebreak`: candidate with self-ratings 0.95, run INITIAL ⇒ `assessments == []`, `qa == []`, every ranking item has `z != 2`-or-low-info label `LOW_INFORMATION`, `l_m == 0`; two vacancies tied on the key are ordered by `T_v` (self-rating) not by id.
  - `test_run_static_and_adaptive_record_everything`: fields of `ExperimentRecord` populated (cohort sha256 equals the cohort's, prompt_version 64 hex chars, qa length = shown questions, timings keys, algorithm_version).
  - `test_rerank_reproduces_ranking_without_llm`: monkeypatch `get_chat_model` to raise if called during `rerank`; result equals `record.ranking`.
  - `test_save_load_roundtrip_and_export`: record saved to `experiment_runs`, loaded equal, `export_records` writes `runs.json` and `runs.csv` with the expected header.
  - `test_llm_failure_creates_no_grades`: failing model ⇒ `errors["fallback_questions"] > 0`, `assessments == []`, ranking labelled `LOW_INFORMATION`, run still saved.
  - `test_scripted_provider_defaults`.
  - `test_empty_cohort_is_reported_not_crash` (track/filters that yield N=0 ⇒ record with empty ranking and `errors["empty_cohort"]=True`).
- [ ] **Step 2:** Run the file — FAIL.
- [ ] **Step 3: Implement** modules and CLI (CLI smoke covered by one test invoking `main()` with a temp sqlite DB, scripted answers and a fake model injected through an env-free hook argument; no network).
- [ ] **Step 4:** Run `cd app && uv run pytest -q` — PASS.
- [ ] **Step 5: Commit** `feat(experiments): runner, stored runs, rerank and CLI`.

### Task 5: Comparability and reproducibility scenarios

**Files:**
- Test: `app/tests/test_experiment_comparability.py` (no production code unless a defect is exposed — report it instead of patching around it)

- [ ] **Step 1: Write scenario tests** (A/B/C on the same `CandidateSpec`, cohort and scripted answers):
  1. `test_same_initial_data_for_all_modes`: cohort sha256, profile snapshot and rubric versions equal across the three records.
  2. `test_static_and_adaptive_share_budget_and_caps`: same `total_budget`, per-topic ≤ 5, topics ≤ 10 in both.
  3. `test_static_plan_identical_for_different_answer_scripts`: two runs of STATIC with different answer scripts have the same ordered `(action_id, ordinal)` question schedule.
  4. `test_adaptive_schedule_depends_on_answers`: two ADAPTIVE runs with strong vs weak scripts differ in schedule or difficulty.
  5. `test_ablation_runs_complete_for_each_flag`: three ablation configs run to completion, `config` recorded.
  6. `test_rerank_equals_ranking_for_every_mode`.
  7. `test_ranking_deterministic_same_snapshot`: same stored assessments ⇒ identical ranking twice.
  8. `test_no_expert_labels_import_in_engine`: `backend.domain`, `backend.api` and `backend.experiments.{planning,runner}` do not import any module named `expert*`/`labels*` (static import scan; Phase 4 extends it).
- [ ] **Step 2:** Run the file — PASS (a FAIL is a Task 1–4 defect: send it back).
- [ ] **Step 3:** Run `cd app && uv run pytest -q` — PASS.
- [ ] **Step 4: Commit** `test(experiments): mode comparability and reproducibility`.

### Task 6: Docs and verification

**Files:**
- Modify: `docs/tasks/MATH_SPEC.md` (new §6a "Experiment modes": mode definitions, ablation flags, equal-conditions rules, what is recorded, honesty: scripted/simulated answers are not evidence of real-candidate performance; results need independent expert labels), `architecture.md` (experiment engine flow), `docs/tasks/STATUS.md`, roadmap (mark Phase 3 done), `README.md` (a short "Experiments" section: exact CLI command and a minimal candidates/answers example, flagged as scripted)
- [ ] **Step 1:** Update docs from the real code.
- [ ] **Step 2:** Run `cd app && uv run pytest -q`; run the CLI once on a temp SQLite DB with the scripted fixture and a fake/no model (`--allow-ungraded`), paste the real command and output summary into STATUS; state what was not run (Docker/PostgreSQL, browser, real LLM).
- [ ] **Step 3: Commit** `docs: experiment modes and runner`.

## Self-review

- Spec coverage (request §5, §8): three modes (T1, T3, T4), same candidates/vacancies/rubrics/evaluator/ranking (T4, T5.1–2), ablation flags (T1, T3, T5.5), static plan fixed (T3, T5.3), adaptive changes (T5.4), run record fields (T2, T4), rerank without LLM (T4, T5.6), CLI (T4), honest disclosure (T6). Metrics/expert data = Phase 4.
- Types consistent: `ExperimentConfig`/`plan_topics`/`slot_targets` (T1) used in T3–T4; columns (T2) used in T3–T4.
- Open risk: T3 touches the busiest function in the codebase; the default path must stay byte-identical (existing suites are the net). Answers for real candidates need a human or a simulated candidate; Phase 3 ships the scripted provider only, and every record carries `answer_source`.
