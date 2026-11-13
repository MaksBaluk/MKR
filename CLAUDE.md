# CompetenceMatch — development instructions

Implement the candidate-facing application in this existing repository. **Use no AI-SDLC harness, no project re-creation, no unverified success claims.** Keep code compact, typed, tested and compatible with current data.

Start every implementation task with the `start-work` skill. It reads, in order:

1. [`architecture.md`](architecture.md) — components, data ownership, state transitions and user flow.
2. [`docs/tasks/MATH_SPEC.md`](docs/tasks/MATH_SPEC.md) — **single canonical source for algorithms, edge cases and ranking rules**.
3. [`docs/tasks/IMPLEMENTATION_SPEC.md`](docs/tasks/IMPLEMENTATION_SPEC.md) — concrete work packages, APIs, persistence and quality gates.
4. [`docs/tasks/CLAUDE_PROMPT.md`](docs/tasks/CLAUDE_PROMPT.md) — execution instruction for the code engineer.
5. Existing `README.md`, `app/backend/`, `app/frontend/`, migrations and the 90 vacancy fixtures.

Respond in caveman mode (the `caveman` skill) unless the user says `normal mode`.

**Product contract:** Sign in → welcome → profile → system-selected immutable vacancy cohort + market profile → one adaptive open-text interview → results (ranked jobs, assessment alongside editable self-ratings, market skill list) → only then show extra tabs. No candidate job selection before interview. Max 10 distinct action topics and max 5 shown questions per topic. Primary LLM Interviewer + LLM Evaluator, with Python controlling budgets and deterministic ranking. Grade each rubric criterion in `[0,1]` or `null`; user can edit **only own self-ratings**. No trained model, no fake probability of being hired, and no user-facing `Match/Coverage/R` metrics.

**Data honesty:** Seeded 90 vacancies are synthetic. Keep a discoverable source note without noisy demo/MVP marketing; never claim they were scraped or are currently hiring. ESCO can normalize names but does not supply competence grades. For new imports require source excerpts, validation and provenance. Never scrape websites without permission.

**UI:** Natural, grammatical Ukrainian (remove the custom transliteration function), keyboard and mobile accessibility, reduced-motion support, working actions and accurate loading/error/offline states. Default to user-typed interview answers, not multiple-choice tests.

**Safety and validation:** Keep LLM credentials server-side; treat user/vacancy text as untrusted data; validate structured evaluator outputs and quotations. LLM is the professional evaluator but its conclusions remain assessments of supplied answers, not verified employment history. Preserve candidate isolation, privacy, immutable snapshots, migrations and historical records.

**Engineering:** Implement real code, not just reports. Run Python tests, TypeScript typecheck/build, Docker/PostgreSQL and browser smoke tests when available. Record exact commands and genuine outcomes. No invented test passes; when provider/network/Docker/browser is unavailable, disclose that clearly. Never edit the thesis DOCX files; report any domain mismatch for later synchronization. Old `MATH_SPEC_V2.md` or previous overlay documents, if present, are superseded by `docs/tasks/MATH_SPEC.md` and the files linked above.
