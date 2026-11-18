# Mathematical specification: market-guided assessment and vacancy ranking

**Canonical domain contract for the implementation.** The three thesis chapters and this document describe one intended system. The formulas are design decisions to be implemented and evaluated; mathematical invariants can be tested, but the accuracy of LLM judgments and relevance of job recommendations require independent expert data. Do **not** present rubric scores as probabilities of employability or as certified qualifications.

## 0. Terms and invariants

- `V`: validated available vacancies; `p`: candidate metadata and editable self-ratings. `H(v,p)` is a deterministic filter of **genuinely hard** constraints (occupation, geographical/work-mode exclusions and other expressly non-negotiable preferences). Missing values are *unknown*, not false. Minimum experience is a lower bound; more years do not cause a penalty. Record whether the minimum is a hard condition or a ranking criterion.
- `V_p = {v∈V : H(v,p)=1}`, `N=|V_p|`. Handle `N=0` explicitly. Freeze all selected vacancy IDs, full requirement versions, selection policy and content digest **before the first interview question**. No manual selection by candidate.
- Each vacancy `v` contains nonempty requirement groups `G_v`. Each group `g` has `kind∈{MANDATORY,PREFERRED}`, at least one distinct alternative action in `A_vg`, and explicit source excerpts. **AND** across groups; **OR** across alternatives. An alternative may refer to several rubric criteria. Unvalidated or missing requirement targets must never be silently treated as achieved.
- A *professional action* is more granular than a technology name. `Python` may contain actions such as designing async APIs and diagnosing concurrency issues, with separate rubrics. Display a parent skill name by stable aggregation, without inheriting evidence across distinct actions.
- The user edits **self-rating for a professional action** (`self_c∈[0,1]∪{null}`) and basic metadata. The user cannot edit LLM interview evaluation (`s_cd`). No field presents old `Match/Coverage/R` metrics or percent job fit. `null` and `0` are different states.
- One shared interview: maximum **10 distinct action topics**, maximum **5 questions per action**, normally 1–2; terminate earlier if enough evidence. Interviewer and Evaluator are separate LLM *roles*; a Python controller owns budgets and ranking.

## 1. Market profile: prevalence vs normalized question-planning weight

Let `C_v` be the **set** of unique normalized actions present in the vacancy (regardless of repeated mentions). The occurrence frequency, for `N>0`, is

`F(c) = (1/N) · Σ_{v∈V_p} 1[c∈C_v]`.

This preserves the natural interpretation: Python in every suitable vacancy has `F(Python)=1`. It is only prevalence in the selected catalog, not a measured national demand rate. **The final market-skills UI sorts by descending F(c), then by I(c), then stable ID**. It shows ordered names and optional assessment states, not the fractions or vacancy counts. For parent concepts, compute prevalence on *distinct vacancies containing at least one mapped action*, not the sum of their action prevalences.

For question-selection weight, distribute an equal mass among the requirement groups of each vacancy:

`w_vg = 1 / (N · |G_v|)`;

`I(c) = Σ_{v∈V_p} Σ_{g∈G_v} [w_vg · 1[c∈A_vg] / |A_vg|]`.

Assume nonempty groups, deduplicated distinct alternatives and `N>0`. Then `I(c)≥0` and `Σ_c I(c)=1` across atomic actions. This prevents a verbose vacancy from dominating and prevents one OR group from counting twice. **Market weights guide interview planning only; never multiply them again into vacancy-specific fit.**

## 2. Dynamic greedy weighted coverage

At time `t`, a group is `open` if additional evidence could change its required-action status. `A_open(t,v,g)` contains those alternatives that may still influence it, and `u_t(v,g)∈{0,1}` identifies open groups. An OR group decisively satisfied by one alternative is closed; a failed alternative with another unknown one remains open. **Self-rating alone never closes a group as verified.**

For an eligible set `T` of as-yet-unassessed action topics, define a fixed-state coverage function

`Q_t(T) = Σ_{v∈V_p} Σ_{g∈G_v} w_vg · u_t(v,g) · 1[T ∩ A_open(t,v,g) ≠ ∅]`.

At each topic boundary choose the available action maximizing marginal coverage at the current state, equivalently with `T=∅` when selecting one next action:

`c*_t = argmax_{c∈C_available} (Q_t({c}) - Q_t(∅))`.

Ties: largest number of open mandatory groups influenced, then a self-rating that needs verification/has contradictory evidence, then `I(c)`, then stable action ID. Cap at 10 distinct selected topics; no forcing of 10 if marginal gain is zero or no evaluable question can be formed. Recompute `u_t`, `A_open`, and `Q_t` **after each topic series**, and optionally after evidence-changing follow-ups within a series, without introducing a new topic.

For fixed `t` and nonnegative weights, `Q_t` is a monotone submodular coverage function. The classical `(1−1/e)` static greedy guarantee applies to selecting up to `k` elements against a **fixed** Q; it does **not** prove global optimality of the adaptive LLM-conditioned process or accuracy of job rankings. No ILP solver or trained model is required in production. Source: Nemhauser, Wolsey & Fisher (1978), DOI 10.1007/BF01588971.

## 3. Two LLM roles and the criterion rubric

- **Interviewer** receives the selected action and rubric ID/version, unmet criteria, situational context, previous topic turns and evaluator follow-up goal. It generates an open, professional Ukrainian question. It does **not** choose another topic, change the question budget or author the job rank.
- **Evaluator** receives the full series of questions/answers for **the one current action**, anchored rubric, exact turn IDs and current evidence. It returns a structured, holistic assessment *revised after each new answer*, not an unweighted average of earlier per-question scores.
- Allowed criterion value: `s_cd∈[0,1]∪{⊥}`, where `⊥` serializes to JSON `null`. `0` indicates assessment after meaningful targeted evidence of incorrect/non-fulfilment; `null` indicates insufficient evidence. Rubric bands: `[0,.25)` materially incorrect, `[.25,.50)` weak, `[.50,.75)` partial, `[.75,.90)` good with shortcomings, `[.90,1]` near-complete. Those are **policy anchors**, not statistical calibration or precise person-level probabilities. Scores like 0.78 and 0.81 need not be interpreted as meaningfully different.
- Every result must contain `criterion_id`, `score | null`, `reason`, exact `turn_id` + evidence excerpt, `needs_followup`, `sufficient_evidence`, source model/prompt/rubric versions and status. Backend validates criterion IDs, score range, citation presence and scope, then writes immutable assessment and profile revisions. Validation proves structural traceability, not epistemic certainty. A human review of every answer is **not** required for normal operation; independent expert review is required for evaluation of accuracy.
- Maximum 5 **persisted questions shown** per action, including follow-ups. When budget ends without evidence, preserve nulls, never invent a concluding grade. Provider failure may retry safely, pause or use a **clearly ungraded** open-text fallback.

A descriptive action score among assessed rubric criteria `K_c={d∈D_c:s_cd≠⊥}` with predefined positive weights `β_cd` (default 1):

`M_c = (Σ_{d∈K_c} β_cd·s_cd) / (Σ_{d∈K_c} β_cd)`, `M_c=null` for `K_c=∅`.

`E_c = (Σ_{d∈K_c} β_cd) / (Σ_{d∈D_c} β_cd)`, given a nonempty rubric.

`M_c` is an illustrative action summary and `E_c` is evidence coverage. **Neither replaces the individual criterion scores in vacancy matching.** Baseline self-rating remains independently editable and versioned, never overwriting an accepted LLM assessment.

## 3a. Topic coverage vs score, criterion states, follow-up goal contract

Implemented in `app/backend/domain/topic_summary.py`, `assessment.py`, `core_flow.py`.

- **Score and coverage are separate.** `M_c` (score among assessed criteria) is never read alone: it is shown with `E_c` (weight share of assessed criteria). A topic with `E_c < MIN_COVERAGE_FOR_OVERALL` (0.6) has `overall_level_allowed=false`; the UI must show criterion-level evidence, not one overall level. The API returns `coverage` and `overall_level_allowed` on result competency items.
- **Criterion states** (per criterion, from latest assessment): `UNKNOWN` (score `null`); `CONFIRMED` (`s>=CONFIRMED_SCORE`=0.75); `DECLINED` (`s<=DECLINED_SCORE`=0.05 **and** `sufficient_evidence`, i.e. the candidate said they lack the experience, a closed observation, not a gap to probe); `WEAK` (any other known score). **Open criteria** = `UNKNOWN` or `WEAK`, in rubric order. Only open criteria are targeted by follow-ups.
- **Follow-up goal.** Evaluator may return `followup_goal = {criterion_ids: [str, ...] (min 1), reason: str (min 1), expected_evidence: str}`. Backend sanitization (`sanitize_goal`) keeps only ids that exist in the action rubric **and** are still open; if none remain the goal is dropped (no goal). The sanitized goal is persisted as `eval_goal` on the answered `core_turns` row (migration 0009; also `followup_reason`). Goal `reason`/`expected_evidence` are truncated to 200 characters (never rejected) and are given to the Interviewer only as delimited untrusted context. The next question targets the goal criteria, or else all open criteria; the stored goal is re-sanitized against criteria open at that moment, and a malformed stored goal counts as no goal. If no criterion is open the topic closes early (no forced second question). While criteria are open the minimum of two questions per topic applies; after the second question a started topic is asked again only if its latest `M_c` is null or its last answered turn has a sanitized goal (goal-driven follow-up; the just-answered topic continues first). Without a goal the planner moves on. Caps stay: 5 shown questions per topic, 10 topics. If any criterion score is null (and the answer is not off-topic), Python sets `sufficient_evidence=false` whatever the Evaluator returned.
- The LLM goal is a proposal. Python owns budgets, validation and the decision to continue.

## 3b. Policy constants (policy, not calibration)

| Constant | Value | Role |
|---|---|---|
| `CONFIRMED_SCORE` | 0.75 | lower edge of band "good"; criterion `CONFIRMED` |
| `DECLINED_SCORE` | 0.05 | with sufficient evidence: criterion `DECLINED` |
| `EARLY_CLOSE_SCORE` | 0.75 | strong sufficient answer may close topic early |
| `MIN_COVERAGE_FOR_OVERALL` | 0.6 | below it no overall topic level is shown |
| `SELF_CLAIM_THRESHOLD` | 0.7 | self-rating at/above it counts as a claim worth verifying |
| `SELF_GAP` | 0.25 | claim minus `M_c` at/above it sets planner `needs_verification` |
| `ε(τ)` | `min(0.05, τ/2)` | borderline margin (§4) |

These are author's policy values, not statistically calibrated; they need expert review.

**`D_vga` and `τ` (superseded: see §3d).** Requirement criteria are explicit per alternative since migration 0013.

## 3c. Difficulty controller

Implemented in `app/backend/domain/difficulty.py` (pure, no DB/API), wired in `app/backend/api/core.py` `next_question`.

**Extension of the thesis model.** The thesis (chapter 2) has no question-difficulty controller. This section is an extension that needs a chapter-2 paragraph (DOCX not edited; for later synchronization).

**Principle.** Difficulty only chooses how hard the next question is. It never sets or caps a criterion score, never changes any target `τ`, and never changes ranking. Scores come from the Evaluator's grading of the supplied answers. Caps are unchanged: 5 shown questions per topic, 10 topics, min two shown questions while criteria stay open (§3a).

**Levels** (`Difficulty`): `BASIC` = basic concepts and typical operations; `INTERMEDIATE` = practical application, diagnosis, choosing a solution; `ADVANCED` = designing complex systems, trade-offs, scaling, non-standard situations. The Interviewer prompt gives these definitions and only follows `difficulty` (candidate level sets the setting, not the depth). The rule that difficulty never changes grading lives in the Evaluator prompt; the Evaluator gets only each turn's `target_criteria` (`turn_meta`), not its difficulty.

**Initial hypothesis** (`initial_difficulty`, start of each topic): candidate level `junior`->`BASIC`, `middle`->`INTERMEDIATE`, `senior`->`ADVANCED` (reason `LEVEL:<level>`). Only if the level is unknown, the market level from the median of known `years_min` of the cohort (`<2` junior, `<5` middle, else senior; reason `MARKET:<level>`). Otherwise `INTERMEDIATE` (`DEFAULT`). Seniority is only a starting guess; evidence moves the level.

**`next_step` rules** (first match wins; `targeted` = criteria the last question aimed at; `known` = their non-null scores):

1. No open criteria: `CLOSE`, reason `NO_OPEN_CRITERIA`.
2. Question cap reached (`can_ask_question` false): `CLOSE`, `QUESTION_CAP`.
3. `enough` = min-two not owed (`needs_min_followup`), topic score known, and no still-open validated follow-up goal.
4. No known targeted score (bank or untargeted question, all null): level unchanged; `CLOSE` with `NO_EVIDENCE+ENOUGH` if `enough`, else `FOLLOWUP` with `NO_EVIDENCE`.
5. `STRONG`: evidence `sufficient`, known share `>= min_known_share`, mean known `>= up_score`: level +1 (max `ADVANCED`).
6. `WEAK`: all targeted known (share 1.0) and mean `< down_score`: level -1, not below `diagnostic_floor`.
   Otherwise `PARTIAL`: level unchanged.
7. If `enough`: `CLOSE` with reason + `+ENOUGH` (e.g. `STRONG+ENOUGH`). Else `CONTINUE` if the level changed, `FOLLOWUP` if not.

Level moves at most one step per answer. Targets of the next question are the criterion ids of the validated follow-up goal when one exists, else the open criteria. `DifficultyDecision.target_criteria` (the open criteria) is informational; `next_question` sets `target_criteria` itself.

**`DifficultyConfig` defaults** (policy, not calibration; need expert review):

| Field | Default | Role |
|---|---|---|
| `up_score` | 0.75 | mean targeted score for `STRONG` (equals `CONFIRMED_SCORE`) |
| `down_score` | 0.50 | mean below it gives `WEAK` |
| `min_known_share` | 0.5 | share of targeted criteria with known score needed for `STRONG` |
| `diagnostic_floor` | `BASIC` | lowest level a weak run can reach |

**Persistence.** Each `core_turns` row stores `difficulty`, `difficulty_reason`, `controller_before`, `controller_after` (migration 0010). Bank-fallback questions advance the state with reason `FALLBACK:<reason>`. A legacy topic whose last turn has NULL difficulty restarts at the initial level (`LEGACY_RESTART`).

**Accepted behaviour (recorded, not a bug).**
(a) A strong sufficient first answer while a validated follow-up goal is still open gets a second question: the min-two rule and the open goal keep the topic open (bounded by caps). Cost if wrong: one extra question in a rare case.
(b) `next_level` on a `CLOSE` decision is informational only: the next topic starts from the initial difficulty, not from the closed topic's level.

## 3d. D_vga, τ status, assessment revisions, evaluator validation (audit fixes, 2026-11-18)

- **D_vga.** Each requirement alternative stores `criterion_ids` (the rubric criteria it needs), `criteria_source`, `tau` and `tau_source` (`requirement_alternatives`, migration 0013) and the cohort snapshot freezes all four. `alt_criteria` treats an explicit `criterion_ids` as authoritative: ids missing from the rubric are dropped, and an empty result is never widened to the whole rubric. The alternative is then `UNRESOLVED` with interval `[0,1]` (unknown stays unknown). Only a legacy row with `criterion_ids = NULL` (created before 0013 and not yet backfilled) uses the whole rubric. The seed backfills such rows once and never overwrites a stored value.
- **Fixture D_vga is synthetic.** `fixtures/vacancy_criteria.json` (generated by `scripts/derive_vacancy_criteria.py`, rule `SYNTHETIC_RULE_V1`, `backend/domain/vacancy_criteria.py`) gives each requirement `ceil(n·share)` of its competency's `n` rubric criteria, share `{1: 0.5, 2: 0.75, 3: 1.0}`, chosen by a stable hash of (vacancy, competency, criterion). It is a documented working assumption, not employer data. `vacancies.json` is unchanged (the original 90 are hash-guarded). A real import must supply `criterion_ids` with a source excerpt.
- **τ.** `tau_source = WORKING_ASSUMPTION_LEVEL_MAP`: `{1: .50, 2: .75, 3: .90}` applied to `required_level` is a working assumption, never an employer statement. An explicit `tau` overrides the map. A level outside the map with no explicit `tau` has no reliable threshold: the alternative is `UNRESOLVED` (no silent `.75`). `GET /profiles/{id}/results/{vacancy_id}` returns `required_criteria` and `threshold_source` per alternative.
- **Results order (owner decision, deviation from (2.15)).** `GET /profiles/{id}/results` shows `confirmed_share` (mean interval lower bound, rounded percent) first, ties broken by the (2.15) key + `T_v`/`J_v` + id (§5). `POST /recommendations` keeps the pure (2.15) key. The audit asked to remove the percent sort; the owner re-confirmed it on 2026-11-18 for readability. Consequence: a `Z=0` vacancy with a high percent can precede a `Z=2` one.
- **Revisions.** Every evaluation appends a revision per criterion; nothing is deleted. The current value of a criterion is the latest revision **with a score** (`effective_rows`). A later `null` revision (off-topic answer, or an answer that does not evidence the criterion) is stored for history but never erases an earlier score. An off-topic revision inherits the previous `sufficient_evidence`. When a later answer contradicts an earlier one the Evaluator receives the whole series of answers on the topic and re-grades every criterion over it; the new, usually lower, score becomes current and the superseded revision stays in history.
- **Evaluator validation** (`validate_against_context`; a violation rejects the output, one retry, then `UNGRADED`): unknown criterion id; duplicate criterion id; score outside [0,1] or non-finite; a numeric score without at least one non-blank evidence excerpt; blank excerpt; unknown turn id; excerpt that is not a verbatim substring of that turn. Missing criteria are allowed (they stay unknown). Score and coverage stay separate (§3a): one strong criterion raises `E_c` by its weight only and never makes the topic confirmed (`overall_level_allowed` needs `E_c ≥ MIN_COVERAGE_FOR_OVERALL`).

## 3e. Assessed professional level (SeniorityEstimator, policy `python-backend/v1`, 2026-11-18)

Three quantities stay separate: `desired_level` (the profile's `target_level`; it seeds only the first question's difficulty and labels a results section), `assessed_level` (this section) and vacancy fit (§4–§5, unchanged). The estimator (`backend/domain/seniority.py`) is pure and deterministic: its only inputs are the level policy and per-criterion evidence `{c: (s_c, T_c)}` from **one** attempt, where `s_c ∈ [0,1] ∪ {null}` and `T_c` is a set of evidence turn ids. Desired level, years, title, self-ratings, vacancy data, ranking and `E_c` are not parameters. A non-finite or out-of-range score raises an error (never guessed).

- **Policy.** `backend/domain/seniority_policy.py`, versioned, never in prompts. For each level `L ∈ {JUNIOR, MIDDLE, SENIOR}`: critical set `C_L`, threshold `τ_L` (.50/.70/.75), `min_assessed_share` (.75/.80/.80), `min_confirmed_share` (.75/.70/.80), `min_competencies` (4/5/6). Exact table: `docs/superpowers/plans/2026-11-18-seniority-estimator.md`. `C_L` mixes existing rubric criteria and six practice criteria `practice-backend.<slug>` (independence, rationale, tradeoffs, diagnosis, ambiguity, ownership); a practice criterion may be critical at two levels and is classified at each level with that level's `τ_L`. Status `WORKING_ASSUMPTION`: the table is the author's assumption and needs expert validation; the API returns the note «Потребує експертної валідації». Marketing and design have no policy (`None`, their rubrics are unreviewed templates): result `UNKNOWN` + `POLICY_UNAVAILABLE`.
- **Per-criterion classes at level L** (`ε(τ) = min(0.05, τ/2)`, as in §4): assessed `A_L = {c ∈ C_L : s_c ≠ null}`; confirmed `K_L = {c ∈ A_L : s_c ≥ τ_L ∧ T_c ≠ ∅}` (a confirmation needs at least one evidence turn); established gap `G_L = {c ∈ A_L : s_c < τ_L − ε(τ_L) ∧ T_c ≠ ∅}`. A score in `[τ_L − ε, τ_L)`, and any score without an evidence turn, is assessed but unresolved: neither confirmed nor a gap. `null` is never 0 and never a gap.
- **Level status.** `GAP` iff `G_L ≠ ∅` (zero tolerance, no compensation: high secondary scores never offset a critical gap). Otherwise `SUPPORTED` iff `|A_L|/|C_L| ≥ min_assessed_share ∧ |K_L|/|C_L| ≥ min_confirmed_share ∧ comp(K_L) ≥ min_competencies` (`comp` = distinct competency prefixes of `K_L`, practice excluded); else `UNVERIFIED`. Reason codes: `CRITICAL_GAP`, `ASSESSED_SHARE_BELOW_MIN`, `CONFIRMED_SHARE_BELOW_MIN`, `TOO_FEW_COMPETENCIES`.
- **Hierarchy.** `assessed_level` = top of the unbroken `SUPPORTED` chain from JUNIOR (`S_SENIOR` requires `S_MIDDLE` and `S_JUNIOR`). If JUNIOR is not supported the result is `UNKNOWN` with `GAPS_AT_JUNIOR` (JUNIOR is `GAP`) or `INSUFFICIENT_DATA`; JUNIOR is never a default. `highest_supported_level` reports a supported level above a broken chain, which is explained but not assigned.
- **Report scope.** Lists (`confirmed_strengths`, `critical_gaps`, `unassessed_criteria`, `evidence_references`) cover levels up to `max(chain + 1, highest level with any assessed critical criterion)`. A criterion that is a gap at any level in scope is listed as a gap, not as a strength. Practice evidence usually touches every level, so in practice the scope is all levels.
- **Evidence from stored revisions** (`core.seniority_evidence`, one attempt only). Topic criteria: the current score is the latest non-null revision (`effective_rows`, §3d); `T_c` is the union of turn ids quoted by **all** non-null revisions of `c`, so a current score can be confirmed by turns cited only by an earlier revision. Practice criteria are re-graded in every topic call from that topic's answers, so they are aggregated order-independently: each revision is credited to the topic of its first quoted turn; within a topic the latest non-null score wins; across topics the maximum is taken (a gap only if no topic confirms); `T_c` is the union. A practice score that quotes no turn is used only when no traced score exists (then `T_c = ∅`, unresolved).
- **Immutability.** On every transition to FINISHED one `seniority_assessments` row is stored per (attempt, policy version) (migration 0016; partial unique index for rows without a policy). It is never updated; a new policy version adds a row. A finished attempt without a row is assessed lazily on first read. A failure while storing never blocks finishing (logged with traceback).
- **Interview integration.** Only the order of the current topic's unmet criteria changes (critical criteria of the lowest non-supported level first) and up to two unassessed practice criteria are passed to the Interviewer (a validated follow-up goal always wins). Q_t, caps, `total_budget` and difficulty are unchanged, so topic choice is market-driven, not level-driven (consequence in `docs/tasks/SENIORITY_REPORT.md`).
- **Not affected.** Ranking (2.15), the results percent order, `/recommendations`, D_vga, the planner and `E_c`/`MIN_COVERAGE_FOR_OVERALL` ignore the level and practice criteria; results sections are labels over the unchanged order.
- **Validation side effects.** Practice items use the same evaluator validation as topic criteria (§3d); one invalid practice item rejects the whole output, so after the retry the topic answer is `UNGRADED`. The Evaluator and Interviewer system prompts changed for **all** tracks, so `prompt_version` changed: experiment runs before and after this change are not comparable on prompts.

## 4. Requirement thresholds and interval fulfilment

Each alternative `(v,g,a)` lists required **criterion IDs** `D_vga` and a documented target `τ_vgad∈(0,1]` per criterion. ESCO URI does not determine targets. If the vacancy states no level, apply an explicitly named **policy-derived rubric threshold** or mark the target unavailable; never report such a value as an employer statement. For existing integer requirements, a documented migration may convert `1→.50`, `2→.75`, `3→.90`, tagged `POLICY_DERIVED_LEGACY`; never silently reinterpret stored values. Rubrics/target versions must be compatible or the item is `NOT_EVALUABLE`.

For `s_ad≠null`, the *defined monotone fulfilment utility* is

`h_vgad = min(1, s_ad/τ_vgad)`.

This is an author's piecewise-linear utility, **not** psychometrically validated interval arithmetic or a probability. For an unknown criterion, possible `h∈[0,1]`. Let `K_vga` be the assessed criteria among `D_vga`, all `β_d>0` and `D_vga` nonempty. Then

`L_vga = [Σ_{d∈K_vga} β_d h_vgad] / [Σ_{d∈D_vga} β_d]`;

`U_vga = L_vga + [Σ_{d∈D_vga\K_vga} β_d] / [Σ_{d∈D_vga} β_d]`.

An OR group's possible utility bounds are `L_vg=max_a L_vga`, `U_vg=max_a U_vga`; this is NOT a sum. For valid inputs, `0≤L≤U≤1`. More evidence narrows or preserves the interval; it does **not** necessarily raise L (an observed negative result can close the interval at a low value).

Mandatory decision is **separate** from fulfilment utility. For a known criterion score and target τ, accept `SATISFIED` if `s≥τ`; classify `FAILED` only when `s<τ−ε(τ)`; otherwise `BORDERLINE` and `UNRESOLVED`, with

`ε(τ)=min(0.05, τ/2)`.

This margin is an explicit, revisable policy, not statistically calibrated. `null→UNRESOLVED`. An alternative is satisfied only if all its required criteria satisfy; failed if any definitely fails; otherwise unresolved. An OR group is satisfied if **any** alternative satisfies, failed only if **all** fail, otherwise unresolved. For vacancy `Z_v=0` if any mandatory group fails; `Z_v=1` if none fails but at least one unresolved, or no explicit mandatory groups; `Z_v=2` only when one or more mandatory groups exist and **all** satisfy. Add `NO_MANDATORY_SPECIFIED` label to distinguish missing mandatory groups from unresolved ones. Store experience status independently: `X_v=2` if declared years meet a stated minimum, `X_v=0` if below, `X_v=1` if unknown/not given. When years are non-negotiable, filter with `H` instead of ranking.

## 5. Explainable lexicographic ranking

For mandatory group set `G_v^M`, preferred group set `G_v^P`, compute arithmetic means of `L_vg` and `U_vg` within each **nonempty** class. Denote `L_v^M`, `L_v^P`, `U_v^M`, `U_v^P`, and widths `W_v^M=U_v^M−L_v^M`, `W_v^P=U_v^P−L_v^P`. For an **absent** group class, use neutral zeros `L=U=W=0` in the technical key, plus a `has_mandatory/has_preferred` flag; absence is not evidence of suitability. If a vacancy has **no valid evaluable requirement group**, set `NOT_EVALUABLE` instead of ranking using fabricated zeros.

Sort descending by the tuple

`K(v)=(Z_v, X_v, L_v^M, L_v^P, -W_v^M, -W_v^P)`;

on an exact tie sort **stable vacancy ID ascending as a string** (UUID-compatible). This is an ordered multi-criteria rule; it is not a calibrated 'fit score'. Explanations include mandatory status, known fulfilled/failed/unassessed actions, rubric evidence, experience mismatch, criteria and target provenance and low-information conditions. For all-unassessed profiles the rank is **not** presented as confident evidence of match; clearly show `LOW_INFORMATION`.

**Self-rating tie-break `T_v`, `J_v`.** After the six-part key and before the vacancy id, sort by `T_v` desc then `J_v` desc. For group `g` let `b_vg` = the **maximum known** self-rating among its alternatives' actions (groups with none known contribute nothing to the sum). `T_v = Σ_g b_vg / |G_v|` over all groups of the vacancy; `J_v = |{g: b_vg known}| / |G_v|` (share of groups with any self-rating). Full key: `(Z, X, L^M, L^P, -W^M, -W^P, T_v, J_v)`, then id ascending. Self-ratings only break exact ties of the interview-based key; they never raise `L`, never change `Z`/`X`, and are not evidence. Never shown as classes or percents. `POST /recommendations` order is exactly this key.

**Results display ordering (owner decision, deviation).** `GET /profiles/{id}/results` orders by `(-confirmed_share, -Z, -X, -L^M, -L^P, W^M, W^P, -T_v, -J_v, id)`; filters keep this relative order. This deviates from thesis (2.15), where the percent is not a ranking key; describe it in chapter 2. A `Z=0` vacancy with a high share can appear above a `Z=2` one; the default `fitting` filter hides only `confirmed_share=0`. `confirmed_share` is not a probability of being hired.

**Planner flag.** `needs_verification(self_rating, summary)` is true when `self_rating>=SELF_CLAIM_THRESHOLD` (0.7) and either the topic has `E_c<MIN_COVERAGE_FOR_OVERALL` or `self_rating-M_c>=SELF_GAP` (0.25). It prioritizes asking, not scoring.

Potential trade-off: conservative sorting favors observed evidence; another set of rank policies may reorder uncertain jobs. Validate expert relevance before claiming this policy is optimal. Do not show a large percentage, even if an internal bounded number happens to reach 1.

## 6. Research comparability, source data and validation

Research conditions: (A) initial self-report, (B) fixed question selection, (C) adaptive topic selection. **Identical** candidate set, immutable vacancy set, target/rubric versions, scoring policy and ranking implementation; B and C have equal question/topic caps. If A is scored from self-report, use a declared **provisional projection** from action self-rating to rubric criteria with `SELF_REPORT_UNVERIFIED` provenance; do not equate it with interviewed evidence and do not use it silently in final live recommendations. Report both assessment agreement with independent experts and NDCG@10 / Precision@5 only with independently labeled vacancy relevance. The synthetic fixture corpus alone cannot demonstrate deployment quality.

Must test: `N=0`, duplicated text and whole-vacancy duplicates, AND/OR groups, unknown vs zero, all-unknown, no mandatory groups, borderlines, `τ→0`, mixed UUID IDs, nonempty rubric weights, topic cap 10 and per-topic cap 5, idempotency, historical cohort immutability, monotonic interval narrowing and fixed-t submodularity. Run a separate expert assessment to determine whether the rubric bands/thresholds and ranking are empirically useful.

## 6a. Experiment modes (implemented in Phase 3)

Existing formulas are unchanged. Modes only switch which planner/controller steps run; all modes share the same candidate profile, immutable cohort snapshot, rubrics, evaluator, scoring (§3a), ranking (§5) and the 10-topic / 5-question-per-topic caps.

**Modes** (`backend/experiments/config.py`, `ExperimentConfig`):

- **A `INITIAL_PROFILE`**: no interview. Ranking uses the same key (2.15) with every criterion unknown (scores `{}`); self-ratings act only through the `T_v`/`J_v` tie-break (§5). No projection of self-ratings to criteria scores is made.
- **B `STATIC_INTERVIEW`**: the three adaptive flags are fixed off (`config_for` rejects overrides). The topic list is fixed once before the first answer by `plan_topics` (greedy coverage over the cohort with no scores, a chosen topic closes every group it appears in) and stored as `core_interviews.static_plan`; it is never rebuilt. Each topic gets exactly `static_questions_per_topic` (default 2) questions, slot `i` of `k` targets the round-robin share `criteria[i::k]` of the rubric (all criteria if the share is empty). No goal-driven follow-up, no early close, no difficulty controller: difficulty stays at the initial hypothesis (`reason = FIXED:<initial reason>`).
- **C `ADAPTIVE_INTERVIEW`**: the product behaviour. Ablation flags, each defaulting to true: `adaptive_topics` (planner `choose_next` vs fixed list), `adaptive_followup` (goal/open-criteria follow-up, early close vs fixed slots), `adaptive_difficulty` (controller §3c vs fixed initial level). Turning a flag off applies the static behaviour of that dimension only.
- `total_budget` (optional): max shown questions per interview; when spent the interview finishes like plan exhaustion and unasked criteria stay null. `max_topics`/`max_per_topic` may only lower the product caps (10 / 5).
- B can end below `total_budget` when the static plan runs out of topics (no remaining topic has positive coverage gain); `n_questions` in `runs.csv` shows it. The CLI requires an explicit `--total-budget` whenever B and C run together.

**Equal-conditions rules.** Per candidate, every mode uses the same profile (set once, never edited during the run), the same auto-selected cohort (id + sha256 recorded), the same rubrics, evaluator prompts and ranking code. B and C use the same `max_topics`, `max_per_topic` and `total_budget` when given. The experiment config is written server-side on the interview row by the runner; it is not a public API field.

**Run record** (`experiment_runs`, migration 0011): experiment id, candidate id, mode, config JSON (plus `answer_source`), cohort id and sha256, profile snapshot, rubric versions, prompt version, model info, algorithm version, question/answer sequence (action, ordinal, text, source, difficulty, target criteria, assessment status), latest criterion assessments, ranking, timings (total, LLM wait, calls), error counters (`ungraded_answers`, `fallback_questions`, `llm_exceptions`, `evaluator_rejections` = evaluator results rejected by validation without a provider exception, `empty_cohort`), `interview_id`. `prompt_version` is the sha256 of the whole `backend/agents/prompts.py` source (system prompts, input formatters, default bands). `model_info` lists the configured provider, model, temperature, max tokens, timeout and the model names the provider reported (`served_models`); an injected test model is recorded as `provider: "injected"` with its class only.
`qa` and `assessments` keep only the latest score per criterion (plus per-question status); the full revision history (reasons, evidence, every evaluator revision per question) stays in the experiment database and is reached through `interview_id`. `answer_source` is `SCRIPTED` for scripted answers, `NONE` for mode A and `UNKNOWN` for a provider without a declared source.

**Rerank.** `rerank(record, db)` recomputes the ranking from the stored assessments, profile snapshot and cohort snapshot with no model call; it fails if the cohort snapshot is missing or its sha256 differs, or if the seeded rubric versions of the cohort's actions differ from the recorded `rubric_versions`. Same stored scores give the same ranking.

**Honesty.**
- Scripted answers are fixtures, not evidence of real-candidate performance; a run with them only checks the pipeline.
- The synthetic fixture corpus cannot demonstrate deployment quality.
- Claims about which mode is better need independent expert labels of vacancy relevance (Phase 4: NDCG@10, Precision@5); none exist yet and no such comparison is reported.
- LLM calls (interviewer, evaluator) are not deterministic. Only the ranking recomputation from stored scores is reproducible; two runs of the same mode may differ.
- Interview modes need an explicit `--llm configured` (the configured provider receives questions, answers, vacancy and rubric text) or `--llm none --allow-ungraded` (no model: answers are stored ungraded and questions come from the bank); ungraded runs say nothing about assessment quality.


## 6b. Metrics and expert reference data (implemented in Phase 4)

Existing formulas are unchanged. Code: `backend/experiments/{expert_labels,metrics,report}.py`. These modules are evaluation-only: no other module under `backend/` may reference them in any form (imports, package attribute access, dotted names in text; test `test_no_expert_labels_import_in_engine`), so expert labels never reach ranking, planning or scoring.

**Ranking metrics.** Expert relevance grade `g ∈ {0,1,2,3}` per (candidate, vacancy); relevant means `g ≥ 2`. Let `r_1..r_n` be the vacancies in the run's ranking.
- `P@5 = |{i ≤ 5 : g(r_i) ≥ 2}| / 5`. The denominator is always 5.
- `NDCG@10 = DCG@10 / IDCG@10`, `DCG@k = Σ_{i=1..k} gain(g(r_i)) / log2(i+1)`. Default gain is linear, `gain = g`; option `exp`, `gain = 2^g − 1`. The thesis must state which gain is used (the code default is linear). IDCG is the DCG of the ideal ordering of **all labelled vacancies of that candidate** (labels restricted to the vacancies the run ranked), top 10. IDCG = 0 (all labels zero) gives `None`, never 1 or 0; P@5 of that candidate is still computed.
- Inclusion rule: a candidate counts only with at least 10 labelled vacancies (`min_labeled_vacancies`, default 10) **and** every vacancy in the top 10 labelled. Otherwise the candidate is excluded and counted (`n_excluded_lt_10_labeled`, `n_excluded_unlabeled_in_top`, ids listed under `excluded_candidates`). One rule covers P@5 and NDCG@10, so both use one sample. Unlabelled vacancies are never given a grade. A `skip` mode exists in `metrics.py` (unlabelled ids dropped before taking top k) but it is pooling-biased and the report does not use it.
- Unpaired mean (`precision_at_5`, `ndcg_at_10` in `report.json`): mean over the candidates included in that mode; the sets can differ between modes. Paired mean (`precision_at_5_paired`, `ndcg_at_10_paired`, `n_paired`): mean over the candidates included in **every** mode of the report. Compare modes only through the paired values; the `ranking_by_mode` chart and `report.csv` carry them. The paired intersection spans all modes of the report including ablations.

**Criterion coverage.** `coverage = |sufficient ∩ relevant| / |relevant|` where `relevant` is the set of rubric criteria of the actions in the cohort (`relevant_criteria` of the run) and `sufficient` is `qa[i]["sufficient_criteria_after"]`, the criteria sufficient by §3a after question `i`. Empty `relevant` gives `None`; such runs (and records exported before the field existed) are excluded from `criterion_coverage_mean`, `questions_to_coverage_mean` and `n_reached` and counted in `n_excluded_no_relevant_criteria`. An interview with no answers has coverage 0.0. **Questions to coverage** is the 1-based index of the first question whose coverage reaches the threshold (default 0.8, `--coverage-threshold`); `None` if never reached.

**Unresolved requirements rate** = `Σ unknown_count / Σ groups_total` over the ranked vacancies with `groups_total > 0` (§4–§5 counts); `None` if no vacancy has groups.

**Duration.** `total_s`, `llm_wait_s` and `excluding_llm_s = max(total_s − llm_wait_s, 0)`; missing keys count 0, negative or non-finite values are rejected.

**Error counters.** Per mode, summed over runs: `llm_errors = llm_exceptions + evaluator_rejections` (provider exceptions and evaluator outputs rejected by validation without an exception). `ungraded_answers` and `fallback_questions` are reported apart, never added to `llm_errors`: one provider exception also yields an ungraded answer, and a run without a model has every answer ungraded and every question from the bank with no LLM error at all. `n_ungraded_runs` counts interview runs without a model (`model_info.provider` is `null`); such runs say nothing about assessment quality, and their coverage reflects no evaluation, not missed criteria.

**Evaluator MAE.** MAE of `|evaluator score − expert score|` over (action, criterion) pairs where both are non-null. Counted separately and never treated as 0: `n_evaluator_unknown` (evaluator `null`, checked first), `n_expert_unknown` (expert `null`), `n_missing_expert` (no expert row), `n_evaluator_missing` (expert-labelled criterion with no evaluator row), `n_compared`, and `n_rubric_version_mismatch` (expert labels written for another rubric version than the run used; dropped). MAE is `None` when `n_compared = 0`. Pooled MAE weights by `n_compared`.

**None policy.** `None` means "not computed or undefined" and is written as an empty CSV cell; it is never replaced by 0 in means, counters or charts.

**Expert data protocol.** (1) Two annotators label the same keys independently (relevance: 0..3 with rationale; criterion: score in [0,1] or empty, with `evidence_reference` when set). Agreement is computed before adjudication (exact agreement and quadratic weighted kappa). (2) An adjudicator **distinct from both annotators** produces the final labels; annotator and final sets must share one `data_status`, one `label_version` and, for criterion labels, one `rubric_version` per action (so adjudication cannot turn synthetic labels into expert ones) (`review_status = ADJUDICATED`, adjudicator as `annotator_id`) for exactly the shared keys. (3) The report uses final labels. If some labels are `ADJUDICATED`, only those are used, the candidates whose other labels were ignored are listed, and a candidate left without any relevance label is excluded as `LABELS_NOT_ADJUDICATED`. If none is adjudicated, labels are used and flagged preliminary. Each key may appear once in the set used. (4) `data_status` is `EXPERT` for real annotation and `SYNTHETIC_TEST_DATA` for fixtures; the two cannot mix in one report. Synthetic labels are refused by the CLI without `--allow-synthetic-labels`, and every output (`report.json`, `report.csv` column `data_status`, each chart dataset) carries the status. Without labels `data_status` is `NO_EXPERT_LABELS` and the statement says that method quality is not established. No label is invented, generated or defaulted; the repository ships only header-only templates.

**What each metric can and cannot show.**
- P@5, NDCG@10: agreement of the ranking with expert relevance for the labelled candidates; valid only with real adjudicated labels. They do not show employment outcomes or hiring probability. Different modes use different interview data, so a difference shows ranking quality under that mode, not a causal effect on its own.
- Coverage, questions to coverage: how much of the rubric the interview evidenced (by LLM-graded sufficiency) and how fast; not whether the grades are right.
- Unresolved rate: how many requirement groups stay unknown; low is not "good" unless grades are correct.
- Duration: machine time only; it ignores candidate typing time and LLM latency differences between providers.
- Evaluator MAE: distance of LLM grades from expert grades on commonly graded criteria; it hides disagreements about what is unknown (separate counters).
- With scripted or simulated answers every metric is a pipeline check, not evidence about real candidates. The 90 synthetic vacancies cannot show deployment quality.
