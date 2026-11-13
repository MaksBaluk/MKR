# UI redesign, chat polish, planner fix, OpenRouter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox syntax.

**Goal:** Mockup-style UI, chatbot-feel interview, autosaving self-ratings, non-repeating planner, bank-backed fallback questions, OpenRouter free model, top-5 results with a labelled confirmed-share percentage.

**Architecture:** Backend changes stay in `api/core.py`, `api/recommendations.py`, `domain/core_flow.py`, `domain/ranking.py`. Frontend stays React + Tailwind v4; screens rewritten against the existing API plus new fields.

**Tech Stack:** FastAPI, pytest, React 19, Tailwind v4, lucide-react.

**Spec:** `docs/superpowers/specs/2026-11-13-ranking-tiebreak-design.md`, `docs/tasks/MATH_SPEC.md`.

## Global Constraints
- Ukrainian UI strings. No `Match`/`Coverage`/`R` labels. The percentage is shown only as "Підтверджено відповідями", derived from the lower bound `L`, never as hiring probability. **Deviates from CLAUDE.md/MATH_SPEC §5; user requested it — ruling.**
- At most 5 recommendations shown; ranking key unchanged.
- `prefers-reduced-motion` respected. API key only in git-ignored `app/.env`.

## Review Focus
1. Ungraded answers must not re-ask the same action (planner test).
2. Fallback question comes from the bank, FREE_TEXT only.
3. Self-rating 0 vs unknown still distinct after autosave.

### Task 1: Planner re-asks only on insufficient evidence
- Files: `app/backend/api/core.py`, `app/tests/test_interview_flow.py`
- [ ] Test: two consecutive `next-question` calls after an ungraded answer return different `action_id`.
- [ ] Implement: an action with ≥1 shown question is available again only if its latest assessment in this interview exists and has `score is None`.
### Task 2: Bank fallback + action names in API
- Files: `app/backend/api/core.py`
- [ ] Fallback uses `providers.questions.next_question` (FREE_TEXT only), else template. `_turn_dict` and `/assessments` return `action_name`.
### Task 3: OpenRouter config
- Files: `app/.env`, `app/.env.example`
- [ ] `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL=https://openrouter.ai/api/v1`, `LLM_MODEL=openrouter/free`; key only in `.env`.
### Task 4: Top-5 recommendations with confirmed share
- Files: `domain/ranking.py`, `domain/core_flow.py`, `api/recommendations.py`, tests
- [ ] `VacancyRanking.confirmed_share` = mean group `L`; response returns top 5 + `total`, `strengths`, `gaps`, `unknown_count`, `tags`.
### Task 5: Frontend redesign
- Files: `frontend/src/screens/*`, `components/SelfRatingList.tsx`, `style.css`
- [ ] Autosave sliders, chat with typing indicator + typewriter, side panel, top-5 cards, stat tiles. Verify: typecheck, build, browser.
