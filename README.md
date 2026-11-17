# CompetenceMatch

> Цей README частково застарів (тести, кількість вакансій, описи потоку). Актуальний стан і відкриті пункти: `docs/tasks/STATUS.md` і `docs/tasks/TODO.md`.

Candidate-centric, explainable job recommendation: the system ranks vacancies for the candidate automatically, then **one shared adaptive interview** refines the ranking over a frozen, system-selected cohort. Ukrainian React interface, FastAPI, PostgreSQL + pgvector, 90 synthetic curated vacancies, typed open-ended answers by default, and optional LLM question generation and rubric grading. No multi-agent SDLC required.

## Quick start (recommended)

**Requirements:** Docker Desktop with Docker Compose, internet for the first build. From the extracted project root:

```bash
cd app
docker compose up --build -d
docker compose ps
```

The first run starts PostgreSQL, creates the `vector` extension and a restricted `cm_app` database role, runs Alembic, loads fixtures and a demo user, then starts the API and the UI.

- **Web app:** http://localhost:8080
- **FastAPI documentation:** http://localhost:8000/docs
- **Health / readiness:** http://localhost:8000/healthz and http://localhost:8000/readyz
- **Demo account:** see `app/DEMO_CREDENTIALS.txt` (also set in `app/.env`).

If one service fails, inspect:

```bash
docker compose logs --tail=150 db migrate seed api web
```

Stop with `docker compose down`. **Destructive reset:** `docker compose down -v` removes local database data; the next `up` will re-seed it. Do not use included demo passwords in production. `app/.env` is prefilled for **local demo only** and intentionally contains no real LLM key.

Verified on this machine: `docker compose up --build -d` starts `db`, `migrate` (0002 applied on an existing database), `seed` (idempotent), `api` and `web`; the Playwright journey passes (see *Acceptance*).

## User workflow

1. Create a candidate account (or use the demo login, shown only in local development).
2. Fill in the profile: track, desired title, years of experience (optional) and self-reported skill levels 0–3. **Unknown stays unknown**, not zero.
3. The **Recommendations** screen ranks all active vacancies of the track automatically. No vacancy has to be selected. Optional filters (work mode, seniority, city, "respect experience") only narrow the list; missing experience never excludes a vacancy.
4. **Start the interview** over all eligible vacancies. The cohort is frozen before question 1 (`POST /api/v1/discovery/snapshots`, with a SHA-256 of the payload).
5. Answer in your own words. The default interview is free text and works without any LLM. An optional, clearly labelled multiple-choice check may appear for one repeat of a competency that needs verification.
6. Typed answers are saved as **pending evaluation**. With an LLM configured you can request a rubric proposal (levels 0–3, quoted evidence, uncertainty). A proposal changes the profile **only after you confirm it**.
7. After finishing, the **Results** screen shows the baseline ranking and the post-interview ranking over the same frozen cohort, with rank changes. If nothing was confirmed, it says so explicitly.

These are **invented, curated demonstration vacancies** with realistic details. They are not Djinni postings, even if some company names or job titles happen to sound real. Live scraping, external vacancy parsing and automatic ESCO normalization are *not implemented*. Competencies are pre-normalized within a local catalog.

## LLM question generation (optional)

Everything works without an API key using the 120-question curated bank. Adaptive *topic selection* and vacancy *ranking* remain deterministic whether LLM is enabled or not.

To enable Anthropic Claude, edit `app/.env`:

```dotenv
LLM_PROVIDER=anthropic
LLM_API_KEY=YOUR_API_KEY_HERE
LLM_MODEL=YOUR_AVAILABLE_CLAUDE_MODEL
LLM_QUESTION_GENERATION=true
LLM_QUESTION_STRATEGY=hybrid
```

Or use `LLM_PROVIDER=openai_compatible` with a compatible `LLM_BASE_URL`, model and key. Set `LLM_QUESTION_STRATEGY=dynamic` to request a fresh open question on every step. `hybrid` retains objective test questions when available and generates context-specific free-text questions for appropriate turns. The provider receives relevant vacancy requirements and a small window of recent interview turns. Failed or malformed provider responses fall back to the local question bank. Restart the services with `docker compose up -d --force-recreate api` after changing `.env`.

**Safety/accuracy limitation:** LLM-generated questions do not automatically certify a candidate's proficiency. Text answers are stored as `PENDING_REVIEW`; any LLM answer-analysis output is a non-authoritative review proposal. Adding the API key alone is *not* sufficient: configure a real provider/model; no provider was contacted in local tests.

## Development and tests

From `app/`:

```bash
uv sync                       # creates local .venv; downloads deps on first run
uv run pytest -q              # Python tests (68 passed on the last run)
uv run uvicorn backend.main:app --reload
```

The local API process requires the database URL from `app/.env`. For a fully local non-container workflow, start PostgreSQL and run migrations/seed first:

```bash
uv run alembic upgrade head
uv run python -m backend.seed
```

To develop the frontend outside Docker:

```bash
cd app/frontend
npm install
npm run dev                  # http://localhost:5173; proxies /api to localhost:8000
npm run build
```

Run the backend from `app/`. On a non-Docker local installation, update `DATABASE_URL` in `app/.env` to point to a local PostgreSQL instance. For repeatability, generate and commit `app/uv.lock` using `cd app && uv lock` when registry access is available; this environment could not resolve dependencies online or offline. Frontend also does not yet contain a `package-lock.json` because npm registry access was unavailable; generate one via `npm install --package-lock-only` and commit it after first successful online install.

## Data and implementation

- `app/fixtures/vacancies.json` — **90** invented, curated vacancies (30 Python, 30 marketing, 30 design), each with ~11 structured S/F/U requirement groups, descriptions, responsibilities, benefits, salaries and seniority.
- `app/fixtures/competencies.json` — **60** local canonical action-level competencies; this is a curated catalog, **not an ESCO import**.
- `app/fixtures/questions.json` — **120** curated interview questions.
- `app/backend/` — API, auth, candidate profiles, immutable vacancy snapshots, interviews, match explanations, optional LLM adapter.
- `app/backend/domain/` — pure deterministic matching and adaptive topic algorithms.
- `app/alembic/` — PostgreSQL schema migration; `competency_vectors` with pgvector `vector(384)` and HNSW index prepared for future embedding search, **not populated** by this demo.
- `app/scripts/generate_fixtures.py` — fixture generator; `app/backend/seed.py` — idempotent database seed.
- `app/frontend/` — React/Vite interface inspired by supplied visual references; screenshots were design reference, not executable UI assets.
- `app/tests/` — Python API, fixture, matching and LLM-adapter tests.

## Acceptance and limitations

Last verified run (this repository state):

- `cd app && uv run pytest -q` → **68 passed** (SQLite test database; includes matching semantics, discovery, free-text interview, profile versions P0/P1, rubric parsing, evidence policy with mocked provider output, adaptive conflicts, Alembic migration).
- `cd app/frontend && npm run typecheck && npm test && npm run build` → typecheck clean, **8 unit tests** passed, production build succeeded.
- `docker compose up --build -d` on PostgreSQL 16 + pgvector: migrations applied, seed idempotent, live API flow (cohort → interview → typed answer → finish → post-interview match) verified with curl.
- `cd app/frontend && npx playwright test` → **3 passed** against the Docker stack (re-run after review fixes) (register → automatic recommendations → typed interview → reload resume → finish → results; mobile 375px no horizontal scroll; settings and catalog provenance).

Not verified: a **live** LLM provider (no key in this environment; grading and question generation are tested with mocked responses only), dependency CVE scan, Firefox/Safari rendering, and expert ranking quality. No empirical ranking-quality claims are made without expert relevance labels.

Known limitations: fixture summaries contain some lowercase, mixed-language fragments (synthetic text, not rewritten); a candidate's own confirmation is a self-review, not an independent check; the cohort cap (30) matters only if the catalog grows beyond 30 per track.
