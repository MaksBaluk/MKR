# Adaptive assessment, modes and metrics — master roadmap

Source request: thesis chapters 2.3.2–2.3.5 and 3 (`Балук_Диплом.docx`), formulas (2.4)–(2.15). Canonical math: `docs/tasks/MATH_SPEC.md`. Four sub-projects, each its own plan, built in order (each depends on the previous one). Only Phase 1 is detailed now.

| # | Phase | Plan file | Status |
|---|---|---|---|
| 1 | Criterion-level core: `D_vga`, coverage vs score, structured `followup_goal`, `T_v`/`J_v`, self-rating tie-break | `2026-11-17-phase1-criterion-core.md` | detailed, ready |
| 2 | `DifficultyController` (BASIC/INTERMEDIATE/ADVANCED) | this file, below | outline |
| 3 | Modes A/B/C, ablation flags, reproducible runner | this file, below | outline |
| 4 | Metrics, expert dataset, report export | this file, below | outline |

## Decisions already made (owner)

- **D_vga source = option (a): derived from rubric.** Required criteria of an alternative are all criteria of the competency's rubric; `required_level` only picks τ (`TAU_BY_LEVEL`). The revision format also accepts an optional `criterion_ids` list per alternative (used when present), so per-vacancy subsets (option b) can be added later without code change. Consequence to disclose in thesis: vacancies with the same competency and level currently require the same criteria; "this vacancy needs only transactions" is supported by the code but not yet present in the 90 fixtures.
- Mode A uses the same key (2.15) with all criteria unknown (docx line 523); `T_v`/`J_v` only break ties. No self-rating→criterion projection.
- No scraping, ESCO, trained model, or UI mode switch.
- Never edit thesis DOCX; report math extensions (difficulty controller) for later sync.

## Cross-phase constants (documented in `MATH_SPEC.md` §3a, §7 as policy, not calibration)

`CONFIRMED_SCORE=0.75`, `DECLINED_SCORE=0.05` (already in `interview_budget.py`), `MIN_COVERAGE_FOR_OVERALL=0.6`, `SELF_CLAIM_THRESHOLD=0.7`, `SELF_GAP=0.25`.

## Phase 2 — DifficultyController (outline)

Files: create `app/backend/domain/difficulty.py`, `app/tests/test_difficulty.py`, `app/tests/test_difficulty_flow.py`; modify `models.py` + migration `0010` (core_turns: `difficulty`, `difficulty_reason`, `controller_before`, `controller_after` JSON), `agents/prompts.py` (Interviewer gets difficulty + definition of each level), `api/core.py`.

Interfaces:
```python
class Difficulty(str, Enum): BASIC; INTERMEDIATE; ADVANCED
@dataclass(frozen=True) class DifficultyConfig: up_score=0.75; down_score=0.50; min_evidence_turns=1; diagnostic_floor=BASIC
@dataclass(frozen=True) class ControllerState: level: Difficulty; shown: int; history: tuple[Difficulty,...]
@dataclass(frozen=True) class DifficultyDecision: next_level: Difficulty; reason: str; action: Literal["CONTINUE","FOLLOWUP","CLOSE"]; target_criteria: tuple[str,...]
def initial_difficulty(level: str|None, years: int|None, vacancy_seniority_mode: str|None) -> Difficulty
def next_step(state, cfg, *, scores: Mapping[str,float|None], sufficient: bool, open_criteria: Sequence[str], targeted: Sequence[str]) -> DifficultyDecision
```
Rules (tests): junior strong BASIC→INTERMEDIATE→ADVANCED; senior weak ADVANCED→INTERMEDIATE→BASIC (diagnostic); incomplete answer with open targeted criterion ⇒ FOLLOWUP, level unchanged; all-null ⇒ no level change; score of a BASIC question confirms only its `targeted` criteria; τ never changed by seniority; 5-question and 10-topic caps hold. Reuses `open_criteria` from Phase 1.

## Phase 3 — Modes and runner (outline)

Files: create `app/backend/experiments/{__init__,config,modes,runner,store}.py`, `app/scripts/run_experiment.py`, migration `0011` (`experiment_runs`), tests `test_modes.py`, `test_experiment_runner.py`.

Interfaces:
```python
class InterviewMode(str, Enum): INITIAL_PROFILE; STATIC_INTERVIEW; ADAPTIVE_INTERVIEW
@dataclass(frozen=True) class ExperimentConfig: mode; adaptive_topics: bool; adaptive_followup: bool; adaptive_difficulty: bool; max_topics=10; max_per_topic=5; total_budget: int
def static_plan(cohort_revisions, profile, cfg) -> list[PlannedTurn]   # fixed before first answer; uses initial difficulty
def run_experiment(cfg, candidate, cohort, model) -> ExperimentRecord   # records everything in spec §8
def rerank(record: ExperimentRecord) -> list[VacancyRanking]           # no LLM call
```
Same `ask`/`answer` graphs, rubrics, evaluator, matching for all modes; ablation flags switch planner (`choose_next` vs static order), follow-up targeting, controller. `experiment_runs` stores: experiment_id, profile version, cohort id + sha256, mode, config JSON, rubric/prompt/model versions, generation params, QA sequence, evaluator output, ranking, timings (LLM wait vs total), errors/fallbacks. Test: same stored scores ⇒ identical ranking; static plan unchanged after answers; adaptive may change.

## Phase 4 — Metrics and expert data (outline)

Files: create `app/backend/experiments/{metrics,dataset,report}.py`, `app/experiments/templates/*.csv`, tests `test_metrics.py`, `test_dataset.py`, `test_leakage.py`.

Interfaces:
```python
def precision_at_k(ranked_ids: Sequence[str], labels: Mapping[str,int], k=5, rel_min=2) -> float
def ndcg_at_k(ranked_ids, labels, k=10) -> float|None   # None when ideal DCG = 0 (documented); dup ids ⇒ ValueError; unlabeled ids not imputed
def criterion_coverage(...); unresolved_rate(...); question_efficiency(...); evaluator_mae(...)  # MAE skips null, coverage reported separately
class ExpertCriterionLabel / ExpertRelevanceLabel (pydantic; status: SYNTHETIC_TEST_DATA | ANNOTATED | ADJUDICATED; two annotators + final)
def build_report(records, labels) -> dict ; def write_report(report, dir) -> json+csv ; def chart_data(report) -> 4 datasets
```
Tests: hand-computed P@5 and NDCG@10; perfect=1, reversed<1; invalid labels rejected; synthetic data flagged and refused as real results; labels never imported by `backend/domain` or `api` (import-graph test). No invented expert labels; templates only.

## Final report (after Phase 4)

Sections A–F from the request, filled only with real command outputs.
