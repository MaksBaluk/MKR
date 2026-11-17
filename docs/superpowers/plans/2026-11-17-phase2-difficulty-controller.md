# Phase 2 — DifficultyController Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A deterministic, configurable, tested `DifficultyController` chooses each question's difficulty (BASIC / INTERMEDIATE / ADVANCED) and the topic decision (continue / follow up / close) from demonstrated evidence; every choice is persisted with its reason and controller state.

**Architecture:** Pure module `app/backend/domain/difficulty.py` (no DB). `api/core.py::next_question` replays each topic's state from stored turns, calls `next_step`, and stores the result on the new `CoreTurn`. The Interviewer prompt gets the difficulty and its definition; the Evaluator input gets per-turn difficulty and target criteria but difficulty never changes a score automatically. The existing min-two/early-close rule (`needs_min_followup`) is reused by the controller, not duplicated.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Alembic, pydantic, LangGraph, pytest (`cd app && uv run pytest -q`).

**Spec:** `docs/superpowers/plans/2026-11-17-adaptive-assessment-roadmap.md` (Phase 2 section), `docs/tasks/MATH_SPEC.md` §2–3a, thesis 2.3.2–2.3.5. This phase is an **extension of the thesis model** (the thesis has no difficulty controller): MATH_SPEC must say so and the thesis chapter 2 needs a later paragraph.

## Global Constraints

- Seniority (junior/middle/senior) is only the **initial hypothesis** for difficulty, never a final judgment; not determined by years alone; never changes thresholds `τ` or the vacancy matching.
- Question difficulty **never automatically sets or caps a criterion score**; the Evaluator grades only what the answers evidence. A BASIC answer can confirm a basic criterion but not a criterion the question did not test.
- Max 10 distinct topics, max 5 shown questions per topic (`interview_budget.py`), min-two rule via `needs_min_followup`. The controller must not raise either cap.
- `null` is never `0`. A fully-unknown answer (all targeted criteria `null`) never changes the level.
- Thresholds are fields of a frozen `DifficultyConfig` with documented defaults (not scattered constants); defaults: `up_score=0.75`, `down_score=0.50`, `min_known_share=0.5`, `diagnostic_floor=BASIC`.
- Persist per question: difficulty, reason, target criteria (already `target_criteria`), controller state before and after. New columns nullable; historical rows keep working.
- No user-facing difficulty/score labels; Interviewer never reveals level or criteria. Ukrainian user text. LLM output untrusted. Do not edit thesis DOCX.

## Review Focus

- Junior with strong answers reaches ADVANCED only after two strong sufficient answers, never in one jump (Task 1, 5).
- Senior with a weak, fully-evidenced answer drops one level at a time to BASIC for diagnostics, then holds at the floor (Task 1, 5).
- Incomplete answer (some targeted criteria `null`, known ones weak) does NOT lower difficulty; same level follow-up (Task 1).
- Evaluator returns `null` for everything or provider fails (UNGRADED) → level unchanged, bank fallback, no fabricated state (Task 3, 5).
- Legacy turns with NULL difficulty (pre-phase-2 attempts) must still produce questions; the topic restarts from the initial difficulty (Task 3).
- Caps: ≤5 questions per topic and ≤10 topics hold when the controller keeps asking follow-ups (Task 5).

---

### Task 1: Pure difficulty controller

**Files:**
- Create: `app/backend/domain/difficulty.py`
- Test: `app/tests/test_difficulty.py`

**Interfaces:**
- Consumes: `needs_min_followup`, `can_ask_question`, `EARLY_CLOSE_SCORE`, `DECLINED_SCORE` from `backend/domain/interview_budget.py`.
- Produces:
```python
class Difficulty(str, Enum): BASIC="BASIC"; INTERMEDIATE="INTERMEDIATE"; ADVANCED="ADVANCED"   # ordered by rank()
def rank(d: Difficulty) -> int                                # 0,1,2
@dataclass(frozen=True) class DifficultyConfig: up_score: float = 0.75; down_score: float = 0.50; min_known_share: float = 0.5; diagnostic_floor: Difficulty = Difficulty.BASIC
@dataclass(frozen=True) class ControllerState: level: Difficulty; shown: int; history: tuple[Difficulty, ...]   # history = levels of questions already shown in this topic
Action = Literal["CONTINUE", "FOLLOWUP", "CLOSE"]
@dataclass(frozen=True) class DifficultyDecision: next_level: Difficulty; reason: str; action: Action; target_criteria: tuple[str, ...]
def market_level(years_min: Sequence[float | None]) -> Literal["junior","middle","senior"] | None   # median of known values: <2 junior, 2–4.99 middle, >=5 senior; None if none known
def initial_difficulty(candidate_level: str | None, market: str | None) -> tuple[Difficulty, str]    # junior->BASIC, middle->INTERMEDIATE, senior->ADVANCED; None -> market level; both None -> INTERMEDIATE; reason string names the source ("LEVEL:junior", "MARKET:senior", "DEFAULT")
def next_step(state: ControllerState, cfg: DifficultyConfig, *, targeted: Sequence[str], scores: Mapping[str, float | None], topic_score: float | None, sufficient: bool, open_criteria: Sequence[str], goal_open: bool = False) -> DifficultyDecision
```

Rules of `next_step` (evaluated in this order; `evidence` = scores of `targeted` criteria):
1. `CLOSE` (`reason="NO_OPEN_CRITERIA"`) when `open_criteria` is empty; `CLOSE` (`"QUESTION_CAP"`) when `not can_ask_question(state.shown)`. Level unchanged.
2. `known = [scores[c] for c in targeted if scores.get(c) is not None]`; if `known` is empty → `FOLLOWUP`, level unchanged, `reason="NO_EVIDENCE"`, targets = `open_criteria`.
3. `known_share = len(known)/len(targeted)`, `mean = sum(known)/len(known)`.
4. Strong: `sufficient and known_share >= cfg.min_known_share and mean >= cfg.up_score` → level up by one (cap ADVANCED), `reason="STRONG"`.
5. Weak: `known_share == 1.0 and mean < cfg.down_score` → level down by one but not below `diagnostic_floor`, `reason="WEAK"`.
6. Otherwise level unchanged, `reason="PARTIAL"` (incomplete or middling evidence).
7. Action for rules 3–6 (same as today's topic-continuation rule, now in one place): `CLOSE` with `reason` kept plus suffix `+ENOUGH` only when NOT (`needs_min_followup(state.shown, graded=True, score=topic_score, sufficient=sufficient)` or `topic_score is None` or `goal_open`) — i.e. min-two not owed, evidence not null, no validated goal on an open criterion. Else `CONTINUE` if the level changed, `FOLLOWUP` if it did not.
`target_criteria` = `open_criteria` (all returned decisions; the caller narrows by the Evaluator goal).

- [ ] **Step 1: Write failing tests** in `test_difficulty.py`:
  - `test_initial`: `("junior",None)->BASIC`, `("senior",None)->ADVANCED`, `(None,"middle")->INTERMEDIATE`, `(None,None)->INTERMEDIATE`, level wins over market.
  - `test_market_level`: `[1,2,6]->"middle"`, `[None,None]->None`, `[0,1]->"junior"`.
  - `test_junior_strong_steps_up_one_at_a_time`: BASIC + `scores {c1:0.9,c2:0.8}`, sufficient, open `["c3"]` ⇒ INTERMEDIATE; again ⇒ ADVANCED; third strong at ADVANCED stays ADVANCED.
  - `test_senior_weak_steps_down_to_floor`: ADVANCED, all targeted known `{c1:0.2}` ⇒ INTERMEDIATE; then BASIC; then stays BASIC.
  - `test_incomplete_weak_answer_does_not_lower`: targeted `[c1,c2]`, `{c1:0.1,c2:None}` ⇒ level unchanged, `reason=="PARTIAL"`, action FOLLOWUP.
  - `test_all_null_no_change`: `{c1:None}` ⇒ unchanged, `reason=="NO_EVIDENCE"`.
  - `test_strong_but_not_sufficient_no_raise`.
  - `test_close_when_no_open_criteria`, `test_close_at_question_cap` (`shown=5`), `test_close_when_min_two_met_and_no_goal` (shown=2, topic_score non-null, goal_open False ⇒ CLOSE) and `test_continue_when_goal_open` (same but goal_open True ⇒ not CLOSE).
  - `test_difficulty_does_not_change_scores`: `next_step` is a pure function of its inputs (same inputs, ADVANCED vs BASIC `state.level` only change `next_level`); asserts no score parameter is returned/mutated.
  - `test_config_thresholds_respected`: custom `DifficultyConfig(up_score=0.9)` blocks the step-up for mean 0.85.
- [ ] **Step 2:** Run `cd app && uv run pytest tests/test_difficulty.py -q` — expect FAIL (module missing).
- [ ] **Step 3: Implement** `difficulty.py` per the rules above; keep it dependency-free except `interview_budget`.
- [ ] **Step 4:** Run the file — expect PASS.
- [ ] **Step 5: Commit** `feat(domain): deterministic DifficultyController`.

### Task 2: Persist difficulty and controller state

**Files:**
- Modify: `app/backend/models.py` (`CoreTurn`)
- Create: `app/alembic/versions/0010_turn_difficulty.py`
- Test: `app/tests/test_migration_0010.py` (pattern: `test_migration_0009.py`)

**Interfaces:**
- Produces: nullable `core_turns` columns `difficulty` (`String(16)`), `difficulty_reason` (`String(64)`), `controller_before` JSON, `controller_after` JSON. JSON shape: `{"level": "BASIC", "shown": 1, "history": ["BASIC"]}`. `_turn_dict` in `api/core.py` must NOT expose them to the candidate-facing response.

- [ ] **Step 1: Failing test** `test_migration_0010.py`: upgrade adds the four columns, downgrade removes them keeping rows, second upgrade is idempotent; historical rows read NULL.
- [ ] **Step 2:** Run it — FAIL.
- [ ] **Step 3: Implement** columns + migration `0010` (revision id ≤ 32 chars, `down_revision` = 0009's id; follow 0009's idempotent add/drop style).
- [ ] **Step 4:** Run `tests/test_migration_0010.py tests/test_migration_0009.py` — PASS.
- [ ] **Step 5: Commit** `feat(db): store question difficulty and controller state`.

### Task 3: Wire the controller into next_question and the prompts

**Files:**
- Modify: `app/backend/api/core.py` (`next_question`, `_assess_action` untouched), `app/backend/agents/prompts.py` (`format_interviewer_input`, Interviewer system prompt, `format_evaluator_input`), `app/backend/agents/graphs.py` (`AskState`, `AnswerState`)
- Test: `app/tests/test_difficulty_flow.py` (created here, extended in Task 5), update `test_prompts.py`

**Interfaces:**
- Consumes: Task 1 API; Task 2 columns; `open_ids`, `goal_for`, `latest_in_session`, `sufficient` helpers already inside `next_question`.
- Produces: `AskState.difficulty: str | None`; `format_interviewer_input(..., difficulty: str | None)` renders `difficulty: BASIC|INTERMEDIATE|ADVANCED` and the system prompt defines each level (BASIC = basic concepts and typical operations; INTERMEDIATE = practical application, diagnosis, choosing a solution; ADVANCED = designing complex systems, trade-offs, scaling, non-standard situations) with the rule "the candidate level is context; follow `difficulty`, never mention it". `format_evaluator_input(..., turn_meta: dict[str, dict] | None)` where `turn_meta[turn_id] = {"difficulty": str|None, "target_criteria": list[str]|None}`; Evaluator system prompt adds: "grade a criterion only from answers that actually evidence it; question difficulty must not raise or lower a score".

Behaviour in `next_question` for the topic being continued or opened:
- No previous turn for the action ⇒ `level, reason = initial_difficulty(candidate_level, market_level(years_min of cohort revisions))`; `state = ControllerState(level, shown=0, history=())`; decision is not computed; store `difficulty_reason=reason`.
- Previous turn exists ⇒ replay: `level = last_turn.difficulty` (NULL ⇒ treat as no previous turn for the level, i.e. initial difficulty, reason `"LEGACY_RESTART"`), `history` = difficulties of the topic's turns; call `next_step(state, DEFAULT_CONFIG, targeted=last_turn.target_criteria or [], scores=cscores, topic_score=latest_in_session.get(a), sufficient=sufficient.get(a, False), open_criteria=open_ids(a), goal_open=goal_for(a) is not None)`.
- Decision `CLOSE` closes the topic exactly like today's `closed(a)` / `needs_min_followup` (replace the inline `closed`/`needs_second` logic by the decision so the rule exists once; keep `needs_min_followup` as the function the controller calls).
- Persist on the new turn: `difficulty=decision.next_level.value`, `difficulty_reason=decision.reason`, `controller_before`/`controller_after` JSON. Bank-fallback questions still get a difficulty (the controller state advances) with `difficulty_reason` prefixed `FALLBACK:`.
- `DEFAULT_CONFIG` is a module constant in `difficulty.py`; `next_question` does not read env/DB for it.

- [ ] **Step 1: Failing tests** (`test_difficulty_flow.py`, reuse fake-model patterns of `tests/test_followup_flow.py`):
  - first question of a junior profile has `difficulty=="BASIC"` and `difficulty_reason=="LEVEL:junior"`; of a senior profile `ADVANCED`.
  - the Interviewer input contains `difficulty: BASIC` (spy on the model input).
  - Evaluator input contains `turn_meta` with the turn's difficulty and `target_criteria`; prompt text contains the "difficulty must not raise or lower a score" rule.
  - legacy turn with NULL difficulty ⇒ next question still produced, `difficulty_reason=="LEGACY_RESTART"`.
  - `_turn_dict` response has no `difficulty*`/`controller_*` keys.
- [ ] **Step 2:** Run `uv run pytest tests/test_difficulty_flow.py -q` — FAIL.
- [ ] **Step 3: Implement** as specified; remove the now-duplicated inline closing logic in favour of the decision, keeping all existing tests green.
- [ ] **Step 4:** Run `uv run pytest -q` — all PASS (baseline after Phase 1: 309 passed plus Task 1–2 tests).
- [ ] **Step 5: Commit** `feat(interview): choose question difficulty with the controller`.

### Task 4: Integration scenarios (API level, fake LLM)

**Files:**
- Modify: `app/tests/test_difficulty_flow.py`
- (no production code unless a scenario exposes a defect; report it instead of patching around it)

**Interfaces:** consumes Task 3 behaviour; produces regression coverage for the thesis scenarios.

- [ ] **Step 1: Write scenario tests** (each runs the real endpoints with a scripted fake Evaluator):
  1. `test_junior_strong_answers_progress_basic_to_advanced`: scripted strong sufficient answers on targeted criteria ⇒ stored difficulties `[BASIC, INTERMEDIATE, ADVANCED]` for the topic's questions, each with a reason `STRONG` after the first.
  2. `test_senior_weak_answer_gets_diagnostic_question`: senior, first answer fully known and weak ⇒ next question `INTERMEDIATE`, then `BASIC`, never below.
  3. `test_incomplete_answer_follows_up_same_level_on_open_criterion`: some targeted criteria `null` ⇒ same difficulty, `followup_reason` set, target is the null criterion.
  4. `test_uncertain_answer_no_level_change`: all `null` ⇒ difficulty unchanged, reason `NO_EVIDENCE`.
  5. `test_good_candidate_does_not_spend_five_questions`: strong sufficient answers closing all criteria ⇒ topic ends with < 5 shown questions.
  6. `test_caps_hold_with_controller`: endless weak/partial answers ⇒ per-topic shown ≤ 5 and distinct topics ≤ 10 (reuse the cap-test pattern of `tests/test_interview_completion.py`).
  7. `test_tau_not_changed_by_level`: same assessments for a junior and a senior profile give the same vacancy Z/X/L values (`rank_items` equal) — difficulty/level never move thresholds.
- [ ] **Step 2:** Run the file — expect PASS (FAIL means a Task 3 defect: send it back, do not edit tests to pass).
- [ ] **Step 3:** Run `cd app && uv run pytest -q` — PASS.
- [ ] **Step 4: Commit** `test(interview): difficulty adaptation scenarios`.

### Task 5: Docs and verification

**Files:**
- Modify: `docs/tasks/MATH_SPEC.md` (new §3c Difficulty controller: levels, rules 1–6, `DifficultyConfig` table of defaults marked policy-not-calibration, explicit "extension of the thesis model, needs a chapter-2 paragraph"), `architecture.md` (flow), `docs/tasks/STATUS.md` (what changed, exact commands and outcomes, not run: Docker/PostgreSQL, browser, real LLM provider), `docs/superpowers/plans/2026-11-17-adaptive-assessment-roadmap.md` (mark Phase 2 done)

- [ ] **Step 1:** Update the docs from the real code (do not rewrite existing formulas).
- [ ] **Step 2:** Run `cd app && uv run pytest -q`; if frontend files changed also `cd app/frontend && npm run typecheck && npm test && npm run build`; paste exact summary lines into STATUS.
- [ ] **Step 3: Commit** `docs: difficulty controller spec and status`.

## Self-review

- Spec coverage (request §2): seniority vs difficulty separated (Task 1), initial hypothesis (T1), deterministic controller with listed inputs/outputs (T1), junior/senior/incomplete/good-candidate behaviours (T4), configurable documented thresholds (T1, T5), difficulty never scores (T3 prompt, T4 #7, T1 purity test), stored difficulty/targets/reason/state (T2, T3), τ untouched (T4 #7), caps (T4 #6).
- Types consistent: `ControllerState`/`DifficultyDecision`/`DEFAULT_CONFIG` defined in Task 1 and used in Tasks 3–4; column names in Task 2 match Task 3.
- Open risk: replacing the inline `closed/needs_second` logic is the one refactor; existing `test_interview_budget.py`, `test_followup_flow.py`, `test_interview_completion.py` are the safety net and must stay green unchanged.
