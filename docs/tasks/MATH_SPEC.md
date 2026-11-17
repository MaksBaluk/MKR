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

**`D_vga` limitation.** By default `D_vga` is **all** rubric criteria of the alternative's action, with target `τ` derived by requirement level (policy-derived, not an employer statement). An optional per-alternative `criterion_ids` subset is supported **in the domain layer only** (`alt_criteria`): there is no persistence or snapshot path yet (cohort snapshot builders emit only `competency_id`/`required_level`, no model column), so vacancy-specific criteria are not available through the API; **the 90 fixtures do not contain it**, so every fixture alternative uses the whole rubric. Fixture requirements are therefore harder to satisfy than a vacancy-specific criterion list would be. An invalid `criterion_ids` currently falls back silently to the whole rubric.

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

**Results display ordering (owner decision, deviation).** `GET /profiles/{id}/results` shows a display ordering: `confirmed_share` (mean interval lower bound, displayed rounded percent) descending first, ties broken by the full key above, then id: `(-confirmed_share, -Z, -X, -L^M, -L^P, W^M, W^P, -T_v, -J_v, id)`. Filters keep this relative order. This deviates from thesis (2.15), where the percent is not a ranking key; it must be described in chapter 2 later. Consequence: a `Z=0` vacancy with a high share can appear above a `Z=2` one; the default `fitting` filter mitigates this only partly, because it hides just vacancies with `confirmed_share=0`. `confirmed_share` is still not a probability of being hired.

**Planner flag.** `needs_verification(self_rating, summary)` is true when `self_rating>=SELF_CLAIM_THRESHOLD` (0.7) and either the topic has `E_c<MIN_COVERAGE_FOR_OVERALL` or `self_rating-M_c>=SELF_GAP` (0.25). It prioritizes asking, not scoring.

Potential trade-off: conservative sorting favors observed evidence; another set of rank policies may reorder uncertain jobs. Validate expert relevance before claiming this policy is optimal. Do not show a large percentage, even if an internal bounded number happens to reach 1.

## 6. Research comparability, source data and validation

Research conditions: (A) initial self-report, (B) fixed question selection, (C) adaptive topic selection. **Identical** candidate set, immutable vacancy set, target/rubric versions, scoring policy and ranking implementation; B and C have equal question/topic caps. If A is scored from self-report, use a declared **provisional projection** from action self-rating to rubric criteria with `SELF_REPORT_UNVERIFIED` provenance; do not equate it with interviewed evidence and do not use it silently in final live recommendations. Report both assessment agreement with independent experts and NDCG@10 / Precision@5 only with independently labeled vacancy relevance. The synthetic fixture corpus alone cannot demonstrate deployment quality.

Must test: `N=0`, duplicated text and whole-vacancy duplicates, AND/OR groups, unknown vs zero, all-unknown, no mandatory groups, borderlines, `τ→0`, mixed UUID IDs, nonempty rubric weights, topic cap 10 and per-topic cap 5, idempotency, historical cohort immutability, monotonic interval narrowing and fixed-t submodularity. Run a separate expert assessment to determine whether the rubric bands/thresholds and ranking are empirically useful.
