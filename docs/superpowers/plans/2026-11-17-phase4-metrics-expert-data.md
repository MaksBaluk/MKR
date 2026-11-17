# Phase 4 — Metrics, expert reference data and evaluation report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute Precision@5, NDCG@10, criterion coverage, unresolved-requirements rate, question efficiency, duration and Evaluator MAE against independently labelled data, with validated expert-label schemas, a JSON/CSV report per mode and chart-ready datasets — without ever inventing expert labels.

**Architecture:** Pure metric functions (`app/backend/experiments/metrics.py`) take rankings/labels as arguments; label schemas, loaders, validators, double-annotation agreement and adjudication live in `expert_labels.py`; `report.py` aggregates stored `ExperimentRecord`s + labels into per-mode results and chart datasets; CLI `app/scripts/evaluate_experiments.py` reads exported `runs.json` and label CSV/JSON files. Records get two additive fields (relevant criteria, per-answer evidence state) so coverage and efficiency are computable from the record alone. Engine code (`backend.domain`, `backend.api`) never imports label/metric modules.

**Tech Stack:** Python, pydantic, SQLAlchemy/Alembic (one small migration), pytest (`cd app && uv run pytest -q`).

**Spec:** `docs/superpowers/plans/2026-11-17-adaptive-assessment-roadmap.md` (Phase 4), original request §6–§7, `docs/tasks/MATH_SPEC.md` §6/§6a.

## Global Constraints

- **No invented expert data.** Real results only from independent labels. Synthetic examples live only in tests/templates and carry `data_status="SYNTHETIC_TEST_DATA"`; a report built from synthetic or missing labels says so and states that method quality is not established.
- Expert grades: relevance integer 0–3 (relevant ≥ 2); criterion score float in [0,1] or `null`; two independent annotators + adjudicated final; annotator ids required.
- `precision_at_k(k=5)` = relevant_in_top_k / k (relevant = grade ≥ 2); `ndcg_at_k(k=10)` with graded relevance 0–3, standard DCG, normalised by the ideal ranking of the same labelled vacancies; ideal DCG 0 ⇒ `None` (documented); perfect ranking ⇒ 1; reversed ⇒ lower; duplicate vacancy ids ⇒ `ValueError`; unlabelled vacancies are never given a fake grade (default `unlabeled="error"`, explicit `"skip"` documented as pooling bias).
- Ranking metrics are averaged only over candidates with ≥ 10 labelled vacancies; the count of included/excluded candidates is reported.
- Evaluator MAE only over pairs where BOTH evaluator and expert scores are non-null; coverage (compared / evaluator-unknown / expert-unknown) reported separately; `null` is never `0`.
- Engine isolation: nothing under `backend/domain` or `backend/api` imports `expert_labels`, `metrics`, `report`; ground-truth labels never reach recommendation/ranking code (extend the AST scan test).
- No user-facing UI change; no scraping/ESCO/trained model; do not edit thesis DOCX.
- Real runs with scripted answers are pipeline checks, not evidence of real-candidate quality.

## Review Focus

- Candidate with fewer than 10 labelled vacancies is excluded from P@5/NDCG means, with the exclusion counted (Task 3, 4).
- Top-5 containing an unlabelled vacancy ⇒ error by default, never silently treated as non-relevant (Task 3).
- All-zero relevance labels ⇒ NDCG `None` and P@5 0.0, with a clear note in the report (Task 3, 4).
- Label files with out-of-range grades, NaN scores, missing annotator, duplicate keys, same annotator twice, or mixed synthetic+real rows are rejected with row-numbered errors (Task 2).
- Records produced before this phase (no `relevant_criteria`) ⇒ coverage metrics `None`, report notes it, no crash (Task 1, 4).
- Report with zero labels still produces the non-label metrics and an explicit "quality not established" status (Task 4).

---

### Task 1: Record fields for coverage and efficiency (+ migration 0012)

**Files:**
- Modify: `app/backend/experiments/runner.py`, `app/backend/experiments/store.py`, `app/backend/models.py` (`ExperimentRun`)
- Create: `app/alembic/versions/0012_experiment_run_fields.py`
- Test: extend `app/tests/test_experiment_runner.py`; create `app/tests/test_migration_0012.py` (pattern `test_migration_0011.py`)

**Interfaces:**
- Consumes: Phase 3 `ExperimentRecord`, `run_experiment`, `rubric_map`, `cohort_actions`, `_revisions`.
- Produces: `ExperimentRecord.relevant_criteria: list[str]` = sorted criterion ids of every rubric criterion of every action appearing in the cohort groups (`rubric_map(db, cohort_actions(revisions), {})` values; actions without a seeded rubric contribute `[action_id]`); every `qa[i]` gets `"sufficient_criteria_after": list[str]` = criterion ids with a non-null latest score AND `sufficient_evidence=True` after that answer (empty list for INITIAL_PROFILE/ungraded); new nullable `experiment_runs` columns `relevant_criteria` JSON and `answer_source` String(16) (migration 0012, idempotent in the 0009/0010/0011 style, revision id ≤ 32 chars, `down_revision="0011_experiments"`); `save_record/load_record` use the real columns (stop storing `answer_source` inside `config`; `load_record` still accepts old rows that have it in `config`). Also fix the Phase 3 deferred minor: `errors["evaluator_rejections"]` counts only `reason in {"MALFORMED","INVALID"}` (not `NO_MODEL`).

- [ ] **Step 1: Failing tests:** (a) interview run record has non-empty `relevant_criteria` equal to the cohort's rubric criteria, and each `qa[i]["sufficient_criteria_after"]` is a subset of it, monotone-or-reset-aware (assert the final entry equals the ids of the final assessments with non-null score and sufficient flag); (b) INITIAL_PROFILE has `[]` per answer and non-empty `relevant_criteria`; (c) `--llm none --allow-ungraded`-style run has `evaluator_rejections == 0` while `ungraded_answers > 0`; (d) save/load round trip keeps both new fields and `answer_source` via the new columns; an old-style row (answer_source in config, no relevant_criteria) still loads with `relevant_criteria == []`; (e) migration 0012 upgrade adds both columns, downgrade removes them keeping rows, re-upgrade idempotent.
- [ ] **Step 2:** Run `cd app && uv run pytest tests/test_migration_0012.py tests/test_experiment_runner.py -q` — expect FAIL.
- [ ] **Step 3: Implement** fields, columns, migration, store changes.
- [ ] **Step 4:** Run the two files then the full suite — PASS.
- [ ] **Step 5: Commit** `feat(experiments): record relevant criteria and per-answer evidence state`.

### Task 2: Expert label schemas, loaders, validators, adjudication

**Files:**
- Create: `app/backend/experiments/expert_labels.py`, `app/experiments/templates/relevance_labels.csv`, `app/experiments/templates/criterion_labels.csv`, `app/experiments/templates/README.md`
- Test: `app/tests/test_expert_labels.py`

**Interfaces:**
- Produces:
```python
class DataStatus(str, Enum): SYNTHETIC_TEST_DATA; EXPERT
class ReviewStatus(str, Enum): PENDING; REVIEWED; ADJUDICATED
class ExpertRelevanceLabel(BaseModel): candidate_id: str; vacancy_id: str; grade: int  # 0..3
    rationale: str  # min length 10; annotator_id: str; label_version: str; data_status: DataStatus; review_status: ReviewStatus = PENDING
class ExpertCriterionLabel(BaseModel): candidate_id: str; action_id: str; criterion_id: str; rubric_version: str
    expert_score: float | None  # [0,1] finite or None; evidence_reference: str  # required (min 3 chars) when expert_score is not None
    annotator_id: str; label_version: str; data_status: DataStatus; review_status: ReviewStatus = PENDING
class LabelError(ValueError): pass   # carries list[str] of "row N: reason"
def load_relevance_labels(path: Path) -> list[ExpertRelevanceLabel]   # CSV or JSON by suffix; collects ALL row errors then raises LabelError
def load_criterion_labels(path: Path) -> list[ExpertCriterionLabel]
def validate_label_set(labels: Sequence[...]) -> None   # duplicate (annotator, key) => error; mixed data_status => error; two labels of one annotator for the same key => error
def split_by_annotator(labels) -> dict[str, list]
def adjudicate(a: Sequence, b: Sequence, final: Sequence, adjudicator_id: str) -> list   # final must cover exactly the keys both annotators labelled; annotators distinct; returns final with review_status ADJUDICATED
def agreement_report(a: Sequence[ExpertRelevanceLabel], b: Sequence[ExpertRelevanceLabel]) -> dict   # n_pairs, exact_agreement, quadratic_weighted_kappa (None if undefined), per-grade confusion
def relevance_map(final: Sequence[ExpertRelevanceLabel], candidate_id: str) -> dict[str, int]
def require_expert_data(labels) -> None   # raises SyntheticDataError if any label is SYNTHETIC_TEST_DATA
```
CSV headers = the field names; `expert_score` empty ⇒ `None`. Templates contain only the header row plus ONE commented/example row clearly marked `SYNTHETIC_TEST_DATA` (or header only — preferred; README explains each field and the annotation protocol).

- [ ] **Step 1: Failing tests** (`test_expert_labels.py`): valid relevance and criterion labels load; rejected with row-numbered messages: grade 4 / -1 / 1.5, score 1.2 / NaN, missing annotator_id, rationale shorter than 10, score without evidence_reference, duplicate (annotator, candidate, vacancy), mixed SYNTHETIC+EXPERT in one set; `adjudicate` rejects equal annotator ids and a final that misses/extends keys; `agreement_report` hand-computed: pairs `(3,3),(2,2),(0,1),(3,2)` ⇒ `exact_agreement == 0.5` and a hand-computed quadratic-weighted kappa; `require_expert_data` raises on synthetic; `relevance_map` returns `{vacancy_id: grade}` for one candidate; template files exist and load as empty sets (header-only) without error.
- [ ] **Step 2:** Run `cd app && uv run pytest tests/test_expert_labels.py -q` — FAIL.
- [ ] **Step 3: Implement** (pydantic validators; kappa via the standard formula; no numpy/scipy requirement).
- [ ] **Step 4:** Run the file, then the full suite — PASS.
- [ ] **Step 5: Commit** `feat(experiments): expert label schemas, validators and adjudication`.

### Task 3: Pure metrics

**Files:**
- Create: `app/backend/experiments/metrics.py`
- Test: `app/tests/test_metrics.py`

**Interfaces:**
- Produces:
```python
class MissingLabelsError(ValueError): ...
def precision_at_k(ranked_ids: Sequence[str], labels: Mapping[str, int], k: int = 5, rel_min: int = 2, unlabeled: Literal["error","skip"] = "error") -> float
def ndcg_at_k(ranked_ids: Sequence[str], labels: Mapping[str, int], k: int = 10, gain: Literal["linear","exp"] = "linear", unlabeled: Literal["error","skip"] = "error") -> float | None
def criterion_coverage(sufficient_ids: Iterable[str], relevant_criteria: Sequence[str]) -> float | None   # |sufficient ∩ relevant| / |relevant|; None if relevant empty
def unresolved_requirements_rate(ranking_items: Sequence[Mapping]) -> float | None   # Σ unknown_count / Σ groups_total over items with groups_total>0; None if none
def coverage_curve(qa: Sequence[Mapping], relevant_criteria: Sequence[str]) -> list[float]   # coverage after each answered question, from qa[i]["sufficient_criteria_after"]
def questions_to_coverage(curve: Sequence[float], threshold: float) -> int | None   # 1-based index of first curve value >= threshold; None if never
def interview_duration(timings: Mapping[str, float]) -> dict   # {"total_s","llm_wait_s","excluding_llm_s"=max(total-llm_wait,0)}
@dataclass(frozen=True) class MaeResult: mae: float | None; n_compared: int; n_evaluator_unknown: int; n_expert_unknown: int; n_missing_expert: int   # n_missing_expert = evaluator criteria with no expert row at all
def evaluator_mae(assessments: Sequence[Mapping], expert: Mapping[tuple[str, str], float | None]) -> MaeResult   # assessments: dicts with action_id, criterion_id, score; expert keyed by (action_id, criterion_id); MAE over pairs where both non-null
```
`ndcg_at_k`: DCG = Σ_{i=1..k} gain(rel_i)/log2(i+1), gain linear = rel, exp = 2^rel−1; ideal = labels sorted desc (all labelled vacancies of the candidate, top k); `unlabeled="skip"` drops ids missing from `labels` before taking the top k (document: pooling bias). Duplicate ids in `ranked_ids` ⇒ `ValueError`; grades outside 0..3 ⇒ `ValueError`. `precision_at_k`: with `unlabeled="error"` any top-k id missing from labels ⇒ `MissingLabelsError` naming the ids; denominator always `k` (fewer than k ranked ids ⇒ the missing slots count as non-relevant, documented).

- [ ] **Step 1: Failing tests** (`test_metrics.py`) with HAND-COMPUTED values in comments: (a) P@5 `ranked=[v1..v6]`, labels `{v1:3,v2:1,v3:2,v4:0,v5:2,v6:3}` ⇒ relevant in top 5 = v1,v3,v5 ⇒ `0.6`; (b) NDCG@10 hand example: ranked `[a,b,c]` labels `{a:3,b:0,c:2,d:3}` (linear) ⇒ DCG = 3/1 + 0/log2(3) + 2/2 = 4.0, ideal = 3/1 + 3/log2(3) + 2/2 ⇒ ndcg = 4/(4+3/log2(3)... compute exactly in the test with `math.log2`); (c) perfect ranking ⇒ `1.0`; reversed ⇒ `< 1.0`; (d) all-zero labels ⇒ NDCG `None`, P@5 `0.0`; (e) unlabeled in top-5 with default ⇒ `MissingLabelsError`, with `"skip"` ⇒ computed on labelled ones; (f) duplicate ids ⇒ ValueError; grade 4 ⇒ ValueError; (g) `exp` gain differs from linear on the hand example; (h) `criterion_coverage`: 3 sufficient of 5 relevant ⇒ 0.6; extra non-relevant sufficient ids ignored; empty relevant ⇒ None; (i) `coverage_curve`/`questions_to_coverage` on a hand qa list; threshold never reached ⇒ None; (j) `unresolved_requirements_rate` hand example, items with `groups_total == 0` skipped, none ⇒ None; (k) `evaluator_mae`: pairs `(0.8 vs 0.6), (0.5 vs 0.5), (None vs 0.4), (0.3 vs None)` ⇒ `mae == 0.1`, `n_compared == 2`, `n_evaluator_unknown == 1`, `n_expert_unknown == 1`; an evaluator `0.0` vs expert `None` is NOT compared; (l) `interview_duration` excluding LLM never negative.
- [ ] **Step 2:** Run `cd app && uv run pytest tests/test_metrics.py -q` — FAIL.
- [ ] **Step 3: Implement** (pure stdlib; no I/O).
- [ ] **Step 4:** Run the file, then the full suite — PASS.
- [ ] **Step 5: Commit** `feat(experiments): ranking, coverage and evaluator-error metrics`.

### Task 4: Report builder, chart data and CLI

**Files:**
- Create: `app/backend/experiments/report.py`, `app/scripts/evaluate_experiments.py`
- Test: `app/tests/test_experiment_report.py`

**Interfaces:**
- Consumes: Tasks 1–3, `ExperimentRecord`, `store.export_records` JSON format (add `store.load_exported_records(path) -> list[ExperimentRecord]` if missing).
- Produces:
```python
@dataclass(frozen=True) class ReportInputs: records: Sequence[ExperimentRecord]; relevance: Sequence[ExpertRelevanceLabel] | None; criteria: Sequence[ExpertCriterionLabel] | None; coverage_threshold: float = 0.8; min_labeled_vacancies: int = 10
def build_report(inp: ReportInputs) -> dict
def chart_data(report: dict) -> dict            # keys: "ranking_by_mode", "coverage_vs_questions", "questions_static_vs_adaptive", "evaluator_quality_by_criterion"
def write_report(report: dict, charts: dict, out_dir: Path) -> None   # report.json, report.csv (one row per mode), charts.json
```
`report` = `{"data_status": "NO_EXPERT_LABELS"|"SYNTHETIC_TEST_DATA"|"EXPERT", "quality_statement": str, "answer_sources": [...], "modes": {mode_key: {...}}, "excluded_candidates": {...}}` where `mode_key` = `INITIAL_PROFILE`, `STATIC_INTERVIEW`, `ADAPTIVE_INTERVIEW` and `ADAPTIVE_INTERVIEW[-topics|-followup|-difficulty]` for ablations (derive from config flags). Per mode: `n_candidates`, `precision_at_5`, `ndcg_at_10` (means over included candidates, or `None` without labels), `n_included`, `n_excluded_lt_10_labeled`, `criterion_coverage_mean`, `unresolved_requirements_rate_mean`, `questions_mean`, `questions_to_coverage_mean` (`None` if never reached; also `n_reached`), `duration` (mean total / excluding-LLM), `llm_errors` (sum of ungraded_answers + fallback_questions + llm_exceptions + evaluator_rejections), `config` echo, `evaluator_mae` (`MaeResult` fields; only with criterion labels). Candidates are matched across modes by `candidate_id`; relevance labels use the ADJUDICATED final set (`review_status == ADJUDICATED`); if only single-annotated labels are given the report says so in `quality_statement`. `quality_statement` is mandatory: for no labels or synthetic labels it must say that method quality is not established. CLI: `--runs runs.json --relevance FILE --criteria FILE --out DIR [--coverage-threshold 0.8]`, labels optional, `--allow-synthetic-labels` required to use `SYNTHETIC_TEST_DATA` (otherwise exit 2 with `error:`), prints the output directory; never touches a DB.

- [ ] **Step 1: Failing tests** (`test_experiment_report.py`, build `ExperimentRecord`s by hand and also one small end-to-end set from the Phase 3 runner with the fake model): (a) no labels ⇒ `data_status == "NO_EXPERT_LABELS"`, ranking metrics `None`, non-label metrics present, statement contains "not established"; (b) synthetic labels without the flag ⇒ CLI rc 2; with the flag ⇒ report `data_status == "SYNTHETIC_TEST_DATA"` and the statement says so; (c) hand-built two-candidate example with known P@5/NDCG@10 per mode ⇒ means equal the hand values; a candidate with 9 labelled vacancies is excluded and counted; (d) ablation records get distinct `mode_key`s; (e) chart datasets have the four keys and shapes (`ranking_by_mode`: list of `{mode, precision_at_5, ndcg_at_10}`; `coverage_vs_questions`: per mode list of `{n_questions, coverage_mean}`; `questions_static_vs_adaptive`: per candidate `{candidate_id, static, adaptive}`; `evaluator_quality_by_criterion`: list of `{criterion_id, mae, n_compared}`); (f) `write_report` writes `report.json`, `report.csv` (header = documented columns) and `charts.json` and they reload equal; (g) old-style records without `relevant_criteria` ⇒ coverage `None`, no crash; (h) CLI end-to-end on a temp dir with a runs.json exported by `store.export_records` and synthetic label files with the flag; (i) EXPERT-status adjudicated labels give `data_status == "EXPERT"` (use hand-made labels marked EXPERT ONLY inside the test to exercise the path; the test docstring states they are test fixtures, not real annotations).
- [ ] **Step 2:** Run the file — FAIL.
- [ ] **Step 3: Implement** modules and CLI.
- [ ] **Step 4:** Run the file, then the full suite — PASS.
- [ ] **Step 5: Commit** `feat(experiments): evaluation report, chart data and CLI`.

### Task 5: Leakage guard, honesty tests and docs

**Files:**
- Modify: `app/tests/test_experiment_comparability.py` (extend scenario 8 scan to forbid imports of `expert_labels`, `metrics`, `report` from `backend.domain`, `backend.api`, `backend.experiments.{planning,runner}`), `docs/tasks/MATH_SPEC.md` (§6b "Metrics and expert reference data": exact definitions, gain choice, ideal ranking, ≥10 labelled rule, MAE coverage reporting, `None` policies, double annotation + adjudication protocol, synthetic-data rule, what each metric can and cannot show), `architecture.md`, `README.md` ("Evaluation" section with exact CLI commands and the label file formats), `docs/tasks/STATUS.md`, roadmap (mark Phase 4 done; final E-category table: what is confirmed by automated tests / measurable after expert data / needs real participants)
- Create: `app/tests/test_evaluation_honesty.py`

- [ ] **Step 1: Write tests:** the extended AST scan (non-vacuous, same helper); `test_report_never_claims_quality_without_expert_labels`; `test_synthetic_labels_are_flagged_everywhere` (report JSON, CSV `data_status` column, chart data carries `data_status`); `test_label_templates_contain_no_labels` (header-only); `test_no_label_fixture_marked_expert_outside_tests` (scan `app/experiments/` and `app/fixtures/` for `"data_status": "EXPERT"` / `EXPERT` rows ⇒ none).
- [ ] **Step 2:** Run them — PASS (a FAIL is a defect in Tasks 1–4: send it back).
- [ ] **Step 3:** Update the docs from the real code; run `cd app && uv run pytest -q`; run `scripts/evaluate_experiments.py` once on a scratch directory with runs exported from a scripted INITIAL_PROFILE run and NO labels, paste the real command and output summary into STATUS; state what was not run (Docker/PostgreSQL, browser, real LLM, any real expert data).
- [ ] **Step 4: Commit** `docs+test: evaluation metrics, expert data protocol and honesty guards`.

## Self-review

- Spec coverage (request §6–§7): P@5 (T3), NDCG@10 (T3), coverage / unresolved / efficiency / duration / MAE (T1, T3), per-mode report with config, questions, duration, LLM errors (T4), chart datasets 1–4 (T4), JSON/CSV (T4), expert criterion and relevance schemas with annotator ids/status/versions, two annotators + adjudication (T2), synthetic status and refusal to present as real (T2, T4, T5), no leakage (T5), honest "quality not established" (T4, T5).
- Types consistent: `ExperimentRecord.relevant_criteria`/`qa[i]["sufficient_criteria_after"]` (T1) feed `coverage_curve`/`criterion_coverage` (T3) and the report (T4); label models (T2) feed `relevance_map`/MAE inputs (T4).
- Risk: relevance labelling is done by people outside this repo; until then only the non-label metrics and the pipeline are verified. The chosen gain (`linear`) is a convention to confirm in the thesis.
