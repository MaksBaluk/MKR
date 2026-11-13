# CompetenceMatch core loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Working candidate flow: auth → welcome → profile → automatic frozen cohort → open-text interview (LLM Interviewer + Evaluator, budget 10×5) → rubric assessments → deterministic ranking → results UI. No ingestion.

**Architecture:** Pure deterministic domain modules (`market`, `planner`, `criteria`, `ranking`) replace the old `matching.py` and `adaptive.py` as the active algorithm. FastAPI routes call them; LLM roles sit behind a mockable transport in `backend/providers/llm.py`. React UI migrates incrementally to Tailwind v4 + shadcn/ui with lucide icons, screen by screen.

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy + Alembic + Pydantic, PostgreSQL 16 (+pgvector, unused here), pytest; React 19 + Vite 7 + TypeScript 5.9, Tailwind CSS v4, shadcn/ui (Radix), lucide-react 0.468.0, Vitest, Playwright.

**Spec:** `docs/tasks/MATH_SPEC.md` (canonical math), `architecture.md`, `docs/tasks/IMPLEMENTATION_SPEC.md`, `docs/tasks/CLAUDE_PROMPT.md`. Brainstorm decision: core loop first, incremental UI migration (option A), no ingestion.

## Global Constraints

- Ukrainian copy written as real grammatical Ukrainian strings. No `u(...)` transliteration helper.
- Never show `Match`, `Coverage`, `R`, percent job fit, hiring probability, or `n of N` vacancy counts. Market table shows order and names only.
- Market order: `F DESC`, then `I DESC`, then stable ID ASC.
- Interview caps: max 10 distinct action topics; max 5 persisted shown questions per action; normally 1–2.
- Evaluator scores: `s ∈ [0,1] ∪ {null}`; bands `[0,.25)`, `[.25,.50)`, `[.50,.75)`, `[.75,.90)`, `[.90,1]`. `0` ≠ `null`.
- Mandatory epsilon: `ε(τ) = min(0.05, τ/2)`. `s ≥ τ` satisfied; `s < τ − ε` failed; else unresolved/borderline.
- Ranking key: `(Z DESC, X DESC, L^M DESC, L^P DESC, W^M ASC, W^P ASC, stable vacancy ID ASC)`.
- Users edit only their own self-ratings. No client PUT on LLM assessments.
- Keep the 90 fixture vacancies (30 Python / 30 marketing / 30 design) and existing accounts. Migrations are non-destructive.
- Never edit `.docx` files.
- No ingestion endpoint, ESCO fetch, or scraper in this plan.
- Do not claim live LLM verification; provider tests use mocks unless a real key is supplied.

## Review Focus

1. Candidate with zero matching vacancies → explicit empty-cohort state, no crash, no silent fallback to all vacancies.
2. Self-rating `0` vs unknown → kept distinct end to end (API, DB, UI).
3. LLM returns malformed JSON / score outside `[0,1]` / quote not present in the cited turn → rejected, nothing persisted, retry or unassessed state shown.
4. Two concurrent answer submissions with same idempotency key → one stored turn, replay returns same result.
5. Browser refresh mid-interview → resumes the exact pending question without regenerating it.

Each line is pinned by a test in the owning task below.

---

## File Structure

| File | Responsibility |
|---|---|
| `app/backend/domain/market.py` (new) | `F(c)`, `I(c)`, market ordering |
| `app/backend/domain/planner.py` (new) | open groups, `Q_t`, greedy topic choice with ties |
| `app/backend/domain/criteria.py` (new) | `h`, `L/U`, `ε`, mandatory status `Z`, experience `X` |
| `app/backend/domain/ranking.py` (new) | group aggregation, sort key, `LOW_INFORMATION`, `NOT_EVALUABLE` |
| `app/backend/domain/interview_budget.py` (new) | 10 topics × 5 shown questions, idempotency rules |
| `app/backend/domain/assessment.py` (new) | Pydantic schema for Evaluator output + acceptance validation |
| `app/backend/domain/matching.py`, `adaptive.py` | Delete after callers switch (Task 9) |
| `app/alembic/versions/0003_core_loop.py` (new) | additive tables/columns |
| `app/backend/api/cohorts.py` (new) | `POST /api/v1/cohorts/auto`, `GET /api/v1/cohorts/{id}/market` |
| `app/backend/api/interviews.py` (rewrite) | next / answers / pause / resume / finish |
| `app/backend/api/assessments.py` (new) | `GET /api/v1/assessments` |
| `app/backend/api/recommendations.py` (new) | `POST` / `GET /api/v1/recommendations` |
| `app/backend/providers/llm.py` | Interviewer and Evaluator prompts, transport interface |
| `app/frontend/` | Tailwind v4, shadcn/ui, lucide, screens migrated |

---

### Task 1: Market profile (pure domain)

**Files:**
- Create: `app/backend/domain/market.py`
- Test: `app/tests/test_market.py`

**Interfaces:**
- Consumes: none
- Produces:
  ```python
  @dataclass(frozen=True)
  class RequirementGroupInput:
      kind: Literal["MANDATORY", "PREFERRED"]
      alternatives: frozenset[str]          # distinct atomic action IDs per alternative
  @dataclass(frozen=True)
  class VacancyInput:
      vacancy_id: str
      groups: tuple[tuple[str, ...], ...]   # each group = alternative actions (OR within group)
  @dataclass(frozen=True)
  class MarketEntry:
      action_id: str
      prevalence: float      # F(c)
      mass: float            # I(c)
  def compute_market(vacancies: Sequence[VacancyInput]) -> list[MarketEntry]: ...
  ```
  Returns sorted by `F DESC, I DESC, action_id ASC`. Empty input returns `[]`.

- [ ] **Step 1: Write failing tests**

```python
def test_repeated_mention_counts_once():
    vs = [VacancyInput("v1", (("py",), ("py", "sql"))), VacancyInput("v2", (("sql",),))]
    m = {e.action_id: e for e in compute_market(vs)}
    assert m["py"].prevalence == 0.5
    assert m["sql"].prevalence == 1.0

def test_mass_sums_to_one():
    vs = [VacancyInput("v1", (("a",), ("b", "c"))), VacancyInput("v2", (("a",),))]
    assert abs(sum(e.mass for e in compute_market(vs)) - 1.0) < 1e-12

def test_or_alternatives_split_group_mass():
    vs = [VacancyInput("v1", (("a", "b"),))]
    m = {e.action_id: e.mass for e in compute_market(vs)}
    assert m["a"] == 0.5 and m["b"] == 0.5

def test_empty_catalog_returns_empty():
    assert compute_market([]) == []

def test_ordering_F_then_I_then_id():
    # equal F, different I → higher I first; equal both → lexicographic id
    ...
```

- [ ] **Step 2: Run tests, expect FAIL**

Run: `cd app && uv run pytest tests/test_market.py -v`
Expected: FAIL (module missing)

- [ ] **Step 3: Implement `compute_market` per MATH_SPEC §1**

`F(c) = |{v : c ∈ C_v}| / N`, `w_vg = 1/(N·|G_v|)`, `I(c) = Σ w_vg·1[c∈A_vg]/|A_vg|`. Deduplicate actions per vacancy before counting. Skip vacancies with no groups (they cannot contribute mass; document this in the docstring).

- [ ] **Step 4: Run tests, expect PASS**

Run: `cd app && uv run pytest tests/test_market.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/backend/domain/market.py app/tests/test_market.py
git commit -m "feat: add market profile domain"
```

---

### Task 2: Planner (fixed-state greedy coverage)

**Files:**
- Create: `app/backend/domain/planner.py`
- Test: `app/tests/test_planner.py`

**Interfaces:**
- Consumes: `VacancyInput` from Task 1 (groups of alternatives), `MarketEntry` from Task 1
- Produces:
  ```python
  @dataclass(frozen=True)
  class OpenState:                       # snapshot of u_t and A_open
      open_groups: frozenset[tuple[str, int]]         # (vacancy_id, group_index) still open
      open_alternatives: dict[tuple[str, int], frozenset[str]]
      mandatory_groups: frozenset[tuple[str, int]]
      self_rating_needs_verification: frozenset[str]  # action IDs
  def coverage(state: OpenState, weights: dict[tuple[str,int], float], topic: frozenset[str]) -> float: ...
  def choose_next(state, weights, available: Sequence[str], market: dict[str, float], stable_ids...) -> str | None: ...
  ```
  `weights[(v,g)] = w_vg`. `choose_next` returns `None` when no positive marginal gain.

- [ ] **Step 1: Failing tests**

```python
def test_coverage_is_monotone_for_fixed_state(): ...
def test_coverage_submodular_diminishing_returns(): ...
def test_or_group_satisfied_by_one_alt_is_closed(): ...
def test_self_rating_alone_does_not_close_group(): ...
def test_tie_prefers_more_open_mandatory_groups(): ...
def test_returns_none_when_zero_gain(): ...
```

- [ ] **Step 2: Run, expect FAIL**

Run: `cd app && uv run pytest tests/test_planner.py -v`

- [ ] **Step 3: Implement**

Greedy argmax of `Q_t({c}) − Q_t(∅)` over `available`. Tie order: more open mandatory groups influenced → `needs_verification` membership → higher `I(c)` → stable action ID ASC.

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add app/backend/domain/planner.py app/tests/test_planner.py
git commit -m "feat: add greedy weighted coverage planner"
```

---

### Task 3: Criterion fulfilment, mandatory status, experience, ranking key

**Files:**
- Create: `app/backend/domain/criteria.py`
- Create: `app/backend/domain/ranking.py`
- Test: `app/tests/test_criteria.py`, `app/tests/test_ranking.py`

**Interfaces:**
- Consumes: criterion scores `dict[str, float | None]`, targets `dict[str, float]` (τ ∈ (0,1]), weights `dict[str, float]` (β > 0)
- Produces:
  ```python
  def fulfilment_bounds(scores, targets, weights, required_ids) -> tuple[float, float]  # (L, U)
  def mandatory_status(score, tau) -> Literal["SATISFIED","FAILED","UNRESOLVED"]
  def epsilon(tau) -> float   # min(0.05, tau/2)
  def experience_status(declared_years, minimum_years, is_hard: bool) -> Literal[2,1,0]  # X
  @dataclass(frozen=True)
  class VacancyRanking:
      vacancy_id: str
      z: Literal[0,1,2]
      x: Literal[0,1,2]
      l_m: float; l_p: float; w_m: float; w_p: float
      has_mandatory: bool; has_preferred: bool
      label: Literal["RANKED","LOW_INFORMATION","NOT_EVALUABLE"]
  def sort_key(r: VacancyRanking) -> tuple: ...   # tuple used with sorted(...)
  def rank(rankings: Sequence[VacancyRanking]) -> list[VacancyRanking]: ...
  ```

- [ ] **Step 1: Failing tests (exact values from spec)**

```python
def test_epsilon_small_tau():
    assert epsilon(0.02) == 0.01        # τ/2 wins below 0.1
    assert epsilon(0.5) == 0.05

def test_null_is_unresolved_not_zero():
    assert mandatory_status(None, 0.5) == "UNRESOLVED"
    assert mandatory_status(0.0, 0.5) == "FAILED"

def test_bounds_monotone_narrowing():
    # adding evidence never widens U−L
    ...

def test_or_takes_max_not_sum(): ...

def test_extra_experience_not_penalized():
    assert experience_status(10, 3, True) == 2

def test_absent_preferred_class_is_zero_with_flag(): ...

def test_uuid_tie_break_string_ascending(): ...

def test_no_evaluable_groups_is_not_evaluable(): ...
```

- [ ] **Step 2: Run, expect FAIL**

Run: `cd app && uv run pytest tests/test_criteria.py tests/test_ranking.py -v`

- [ ] **Step 3: Implement** per MATH_SPEC §4–5.

`L = Σ_{d∈K} β_d·min(1, s_d/τ_d) / Σ_{d∈D} β_d`; `U = L + Σ_{d∈D\K} β_d / Σ_{d∈D} β_d`. OR group: `max` over alternatives for both `L` and `U`. `Z=2` only if all mandatory groups satisfy; `Z=0` if any mandatory group fails; otherwise `Z=1`. `X=1` when declared years unknown.

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add app/backend/domain/criteria.py app/backend/domain/ranking.py app/tests/test_criteria.py app/tests/test_ranking.py
git commit -m "feat: add criterion fulfilment and ranking key"
```

---

### Task 4: Interview budget and Evaluator output validation

**Files:**
- Create: `app/backend/domain/interview_budget.py`
- Create: `app/backend/domain/assessment.py`
- Test: `app/tests/test_interview_budget.py`, `app/tests/test_assessment.py`

**Interfaces:**
- Consumes: none (pure)
- Produces:
  ```python
  MAX_TOPICS = 10
  MAX_SHOWN_QUESTIONS_PER_ACTION = 5
  def can_start_topic(distinct_topics_so_far: int) -> bool
  def can_ask_question(shown_for_action: int) -> bool

  class CriterionResult(BaseModel):
      criterion_id: str
      score: float | None          # 0..1 inclusive, None = null
      reason: str
      evidence: list[EvidenceRef]  # turn_id + exact_excerpt
  class EvidenceRef(BaseModel):
      turn_id: str
      exact_excerpt: str
  class EvaluatorOutput(BaseModel):
      action_id: str
      rubric_version: str
      criteria: list[CriterionResult]
      sufficient_evidence: bool
      needs_followup: bool
      followup_goal: str | None
      limitations: str

  def validate_against_context(out: EvaluatorOutput, allowed_criteria: set[str],
                               turn_texts: dict[str, str]) -> list[str]: ...  # returns errors, empty = ok
  ```

- [ ] **Step 1: Failing tests**

```python
def test_topic_cap_10(): ...
def test_question_cap_5_per_action(): ...
def test_score_zero_is_valid_and_distinct_from_null():
    ok = EvaluatorOutput(... criteria=[CriterionResult(criterion_id="a", score=0.0, ...)])
    assert validate_against_context(ok, {"a"}, {"t1": "..."}) == []
def test_score_out_of_range_rejected(): ...
def test_quote_not_in_turn_rejected(): ...
def test_unknown_criterion_rejected(): ...
def test_malformed_json_raises(): ...
```

- [ ] **Step 2: Run, expect FAIL**

Run: `cd app && uv run pytest tests/test_interview_budget.py tests/test_assessment.py -v`

- [ ] **Step 3: Implement**

`validate_against_context` checks: criterion IDs ⊆ `allowed_criteria`; `score` null or `0 ≤ s ≤ 1` and finite; each `evidence.turn_id ∈ turn_texts`; `exact_excerpt` substring of that turn's text.

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add app/backend/domain/interview_budget.py app/backend/domain/assessment.py app/tests/test_interview_budget.py app/tests/test_assessment.py
git commit -m "feat: add interview budget and evaluator validation"
```

---

### Task 5: Alembic migration 0003 (additive)

**Files:**
- Create: `app/alembic/versions/0003_core_loop.py`
- Modify: `app/backend/models.py` (add ORM classes; do not remove existing ones yet)
- Test: `app/tests/test_migration_0003.py`

**Interfaces:**
- Consumes: revision `0002` (`0002_discovery_evidence_profiles`)
- Produces (table names exact):
  - `candidate_self_ratings(user_id, action_id, value numeric null check value between 0 and 1 or null, revision int, PK(user_id, action_id, revision))`
  - `rubrics(id, action_id, version, source check in ('CURATED','LLM_PROPOSED','REVIEWED'), UNIQUE(action_id, version))`
  - `rubric_criteria(id, rubric_id, criterion_id, weight numeric > 0, anchors jsonb, UNIQUE(rubric_id, criterion_id))`
  - `interview_sessions` add column `snapshot_id`, `version int default 1`, `topics_used int default 0`
  - `interview_turns` add `idempotency_key text`, `action_id text`, `question_hash text`, unique (`session_id`, `idempotency_key`)
  - `criterion_assessments(id, session_id, action_id, criterion_id, rubric_id, score numeric null, reason text, evidence jsonb, revision int, status, created_at, UNIQUE(session_id, action_id, criterion_id, revision))`
  - `cohort_snapshots(id, user_id, vacancy_ids jsonb, requirement_revisions jsonb, policy_id text, sha256 text, created_at)`

- [ ] **Step 1: Failing test**

```python
def test_0003_preserves_fixture_vacancies(migrated_db):
    # count vacancies before (0002) and after (0003) → equal and = 90
    ...
def test_downgrade_removes_only_new_tables(...): ...
```

- [ ] **Step 2: Run, expect FAIL**

Run: `cd app && uv run pytest tests/test_migration_0003.py -v`

- [ ] **Step 3: Write migration**

Additive `op.create_table` and `op.add_column` only. No `DROP` of existing tables in upgrade. Downgrade drops only the new tables and added columns.

- [ ] **Step 4: Run, expect PASS**

Run: `cd app && uv run alembic upgrade head && uv run pytest tests/test_migration_0003.py tests/test_migration.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/alembic/versions/0003_core_loop.py app/backend/models.py app/tests/test_migration_0003.py
git commit -m "feat: add core loop migration"
```

---

### Task 6: Cohort and market endpoints

**Files:**
- Create: `app/backend/api/cohorts.py`
- Modify: `app/backend/main.py` (register router)
- Test: `app/tests/test_cohorts_api.py`

**Interfaces:**
- Consumes: `compute_market` (Task 1), `VacancyInput`
- Produces:
  - `POST /api/v1/cohorts/auto` → `{cohort_id, vacancy_count, sha256, empty: bool}`. Idempotent per user per profile version. No client-supplied vacancy IDs. If `vacancy_count == 0`, `empty: true`, no snapshot.
  - `GET /api/v1/cohorts/{cohort_id}/market` → `{skills: [{action_id, name, order}]}`. No counts or percentages in the response.

- [ ] **Step 1: Failing tests**

```python
def test_cohort_is_owner_scoped(client, user_a, user_b): ...  # user B gets 404 on A's cohort
def test_post_is_idempotent(client, user): ...
def test_response_has_no_percentage_or_count_fields(client, user):
    body = client.get(f"/api/v1/cohorts/{cid}/market").json()
    assert "count" not in str(body) and "%" not in str(body)
def test_empty_cohort_state(client, user_with_no_match): ...
def test_client_vacancy_ids_ignored(client, user):
    r = client.post("/api/v1/cohorts/auto", json={"vacancy_ids": ["x"]})
    assert r.status_code in (200, 422) and ... # server ignores field
```

- [ ] **Step 2: Run, expect FAIL**

Run: `cd app && uv run pytest tests/test_cohorts_api.py -v`

- [ ] **Step 3: Implement**

Hard filter `H` on occupation (profession track) and work-mode / location exclusions only. Unknown experience never excludes. Persist snapshot with SHA-256 over canonical JSON of IDs + requirement revisions.

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add app/backend/api/cohorts.py app/backend/main.py app/tests/test_cohorts_api.py
git commit -m "feat: add automatic cohort and market endpoints"
```

---

### Task 7: LLM Interviewer and Evaluator roles

**Files:**
- Modify: `app/backend/providers/llm.py`
- Create: `app/backend/providers/prompts.py` (Ukrainian system prompts, role separation)
- Test: `app/tests/test_llm_roles.py`

**Interfaces:**
- Consumes: `EvaluatorOutput` (Task 4), `validate_against_context` (Task 4)
- Produces:
  ```python
  class LLMTransport(Protocol):
      def complete(self, system: str, user: str, *, timeout_s: float) -> str: ...
  def interviewer_question(transport, action, rubric, unmet_criteria, previous_turns, followup_goal) -> str
  def evaluator_assess(transport, action, rubric, turns) -> EvaluatorOutput   # raises LLMError on invalid
  class LLMError(Exception): kind: Literal["TIMEOUT","RATE_LIMIT","MALFORMED","OFFLINE"]
  ```
  Retry: up to 2 retries on `TIMEOUT`/`RATE_LIMIT` with backoff; `MALFORMED` retries once.

- [ ] **Step 1: Failing tests (mock transport)**

```python
def test_valid_evaluator_json_parses(): ...
def test_incomplete_json_raises_malformed(): ...
def test_timeout_retries_then_raises(): ...
def test_rate_limit_retries(): ...
def test_offline_raises_without_fabrication(): ...
def test_interviewer_prompt_forbids_topic_change(): ...   # system text contains constraint
```

- [ ] **Step 2: Run, expect FAIL**

Run: `cd app && uv run pytest tests/test_llm_roles.py -v`

- [ ] **Step 3: Implement** with a transport interface. Real Anthropic/OpenAI adapters stay behind `LLMTransport`. Do not call a provider in tests.

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add app/backend/providers/llm.py app/backend/providers/prompts.py app/tests/test_llm_roles.py
git commit -m "feat: add interviewer and evaluator roles"
```

---

### Task 8: Interview flow API (next / answers / pause / resume / finish) and assessments

**Files:**
- Rewrite: `app/backend/api/interviews.py`
- Create: `app/backend/api/assessments.py`
- Create: `app/backend/api/recommendations.py`
- Modify: `app/backend/main.py`
- Test: `app/tests/test_interview_flow.py`, `app/tests/test_assessments_api.py`, `app/tests/test_recommendations_api.py`

**Interfaces:**
- Consumes: planner (Task 2), budget (Task 4), LLM roles (Task 7), ranking (Task 3), snapshot (Task 6)
- Produces:
  - `POST /api/v1/interviews` `{cohort_id}` → session. `version=1`.
  - `POST /api/v1/interviews/{id}/next-question` → stores question before returning. Retry returns the same stored question (no regeneration).
  - `POST /api/v1/interviews/{id}/answers` `{turn_id, text, idempotency_key, expected_version}` → 409 if version mismatch. Replay of same key returns the same turn.
  - `POST /api/v1/interviews/{id}/pause`, `/resume`, `/finish`.
  - `GET /api/v1/assessments?session_id=` → read-only accepted assessments. No `PUT`/`PATCH`/`POST` for LLM scores.
  - `POST /api/v1/recommendations` → RankingRun. `GET /api/v1/recommendations/{id}`.

- [ ] **Step 1: Failing tests**

```python
def test_question_stored_before_return(client, interview): ...
def test_retry_next_question_returns_same_question(client, interview): ...
def test_answer_replay_same_idempotency_key(client, interview): ...
def test_concurrent_answers_one_stored(client, interview): ...   # two threads, same key
def test_stale_version_returns_409(client, interview): ...
def test_cannot_put_llm_assessment(client, user): ...          # 405
def test_resume_after_refresh_returns_pending_question(client, interview): ...
def test_provider_offline_saves_answer_as_ungraded(client, interview, offline_llm): ...
def test_recommendations_scoped_to_owner(client, user_a, user_b): ...
```

- [ ] **Step 2: Run, expect FAIL**

Run: `cd app && uv run pytest tests/test_interview_flow.py tests/test_assessments_api.py tests/test_recommendations_api.py -v`

- [ ] **Step 3: Implement**

Each answer triggers Evaluator on the **whole current action series**. Accepted output appended as a new `criterion_assessments` revision with `revision = prev + 1`. Validation failure → nothing written, state `EVAL_PENDING` shown. Planner recomputed after each completed action series. `finish` runs ranking and writes `RankingRun`.

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add app/backend/api/interviews.py app/backend/api/assessments.py app/backend/api/recommendations.py app/backend/main.py app/tests/test_interview_flow.py app/tests/test_assessments_api.py app/tests/test_recommendations_api.py
git commit -m "feat: add interview flow, assessments and recommendations API"
```

---

### Task 9: Remove superseded algorithms and old tests

**Files:**
- Delete: `app/backend/domain/matching.py`, `app/backend/domain/adaptive.py`
- Delete or rewrite: `app/tests/test_matching.py`, `app/tests/test_matching_semantics.py`, `app/tests/test_adaptive_conflicts.py`
- Modify: any remaining caller found by `grep -rn "domain.matching\|domain.adaptive" app/backend app/tests`

**Interfaces:**
- Consumes: Tasks 1–8 callers
- Produces: none (deletion)

- [ ] **Step 1: Confirm no callers**

Run: `cd app && grep -rn "domain.matching\|domain.adaptive" backend tests`
Expected: no output after the callers from Task 8 were switched.

- [ ] **Step 2: Delete the files listed above**

- [ ] **Step 3: Run full Python suite**

Run: `cd app && uv run pytest -q`
Expected: all tests pass; record the exact count.

- [ ] **Step 4: Commit**

```bash
git add -A app/backend app/tests
git commit -m "refactor: remove superseded matching and adaptive algorithms"
```

---

### Task 10: Frontend Tailwind v4 + shadcn/ui + lucide setup

**Files:**
- Modify: `app/frontend/package.json` (add `tailwindcss`, `@tailwindcss/vite`, `class-variance-authority`, `clsx`, `tailwind-merge`, `@radix-ui/*` used by shadcn components)
- Modify: `app/frontend/vite.config.ts` (add `@tailwindcss/vite`, alias `@` → `src`)
- Modify: `app/frontend/tsconfig.json` (`paths`: `@/*`)
- Create: `app/frontend/components.json` (shadcn config)
- Create: `app/frontend/src/lib/utils.ts` (`cn`)
- Create: `app/frontend/src/components/ui/` (shadcn: button, input, label, card, badge, alert, progress)
- Modify: `app/frontend/src/style.css` (keep token variables; move colors into `@theme` mapping)
- Test: `app/frontend/src/lib/utils.test.ts`

**Interfaces:**
- Consumes: none
- Produces: `cn(...inputs: ClassValue[]): string` from `@/lib/utils`. shadcn components export named React components.

- [ ] **Step 1: Failing test**

```ts
import { cn } from "@/lib/utils";
import { expect, test } from "vitest";
test("cn merges tailwind classes", () => {
  expect(cn("p-2", "p-4")).toBe("p-4");
});
```

- [ ] **Step 2: Run, expect FAIL**

Run: `cd app/frontend && npm test`

- [ ] **Step 3: Install and configure**

Run: `cd app/frontend && npm install tailwindcss @tailwindcss/vite class-variance-authority clsx tailwind-merge`
Then: `npx shadcn@latest init` (Tailwind v4, base color neutral, alias `@/components`, `@/lib`).
Then: `npx shadcn@latest add button input label card badge alert progress`

Commit the generated `package-lock.json` only after this succeeds.

- [ ] **Step 4: Run, expect PASS**

Run: `cd app/frontend && npm test && npm run typecheck && npm run build`

- [ ] **Step 5: Commit**

```bash
git add app/frontend/package.json app/frontend/package-lock.json app/frontend/vite.config.ts app/frontend/tsconfig.json app/frontend/components.json app/frontend/src/lib app/frontend/src/components/ui app/frontend/src/style.css
git commit -m "feat: add tailwind v4 and shadcn/ui setup"
```

---

### Task 11: Migrate screens to Tailwind + shadcn + lucide (one at a time)

**Files (per screen, in order):**
- `app/frontend/src/screens/AuthScreen.tsx`
- `app/frontend/src/screens/ProfileScreen.tsx`
- `app/frontend/src/screens/InterviewScreen.tsx`
- `app/frontend/src/screens/ResultsScreen.tsx`
- `app/frontend/src/screens/RecommendationsScreen.tsx`
- `app/frontend/src/screens/CatalogScreen.tsx`
- `app/frontend/src/screens/SettingsScreen.tsx`
- Modify: `app/frontend/src/App.tsx` (remove `freezeAndStart()`, route to welcome → profile → interview → results)
- Remove: `app/frontend/src/components/MatchMetrics.tsx`; delete the `u(...)` helper from `app/frontend/src/i18n/uk.ts` or the file that defines it.
- Test: `app/frontend/e2e/journey.spec.ts` (Playwright)

**Interfaces:**
- Consumes: Tasks 6–8 API responses; `cn` and shadcn components from Task 10
- Produces: lucide icons imported per name, e.g. `import { CheckCircle2, AlertTriangle, ArrowRight } from "lucide-react"`

- [ ] **Step 1: Update the Playwright journey to the new flow (failing)**

Scenario: register → welcome → profile (self-ratings edit) → automatic cohort → typed answer → assessment shown read-only → results with ranked list and market table (no `%`, no `count`).

- [ ] **Step 2: Run against the dev server, expect FAIL**

Run: `cd app/frontend && npx playwright test`

- [ ] **Step 3: Migrate each screen**

Replace `style.css` class usage with Tailwind utilities + shadcn primitives. Replace emoji/unicode icons with lucide. Every label is literal Ukrainian. Include loading, error, empty, retry states. Respect `prefers-reduced-motion` with `motion-safe:` / `motion-reduce:` classes.

- [ ] **Step 4: Run Playwright, expect PASS**

Run: `cd app/frontend && npm run typecheck && npm run build && npx playwright test`

- [ ] **Step 5: Commit per screen**

```bash
git add app/frontend/src/screens/AuthScreen.tsx app/frontend/src/App.tsx
git commit -m "feat(ui): migrate auth screen to tailwind and shadcn"
```

Repeat per screen.

---

### Task 12: Vacancy logos (Djinni) — BLOCKED pending confirmation

**Status:** Not started. Requires explicit user decision before any work.

**Why blocked:** Seeded vacancies are invented (see `architecture.md` §7). Showing Djinni's logo on them implies Djinni listings and affiliation, which the spec forbids (no impersonation via third-party branding; no claim these are real postings). Logo use also needs Djinni's permission or a licensed asset.

**Options to choose from:**
1. Neutral generated monogram per vacancy (lucide icon + company initials). No third-party brand.
2. Djinni logo only with written permission, shown with an explicit "тестові дані" label.

- [ ] **Step 1:** Ask the user to pick option 1 or 2 and confirm rights for option 2.
- [ ] **Step 2:** Implement chosen option in a separate task after the answer.

---

### Task 13: Final verification

**Files:** none modified.

- [ ] **Step 1: Python**

Run: `cd app && uv sync && uv run pytest -q`
Record exact pass count.

- [ ] **Step 2: Frontend**

Run: `cd app/frontend && npm install && npm run typecheck && npm test && npm run build`

- [ ] **Step 3: Stack**

Run: `cd app && docker compose up --build -d && docker compose ps` (if Docker is available; otherwise record "not run: Docker unavailable").

- [ ] **Step 4: Browser**

Run: `cd app/frontend && npx playwright test` against the running stack.

- [ ] **Step 5: Report**

Report exact commands and outcomes. Do not claim live LLM verification unless a real provider key was used.

---

## Open items for the user

1. **Djinni logos (Task 12):** choose option 1 (neutral monogram) or option 2 (Djinni logo with permission and "тестові дані" label).
2. **Real LLM key:** not available here. Provider tests use mocks. Confirm whether a key will be supplied for a live check.
