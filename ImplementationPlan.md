# ImplementationPlan — DataChat

> **Build plan for Claude Code.** Execute **top to bottom, phase by phase, autonomously.**
> **Read [Rules.md](./Rules.md) first** (the constitution), then [PRD](./PRD.md) · [TechSpec](./TechSpec.md) · [AppFlow](./AppFlow.md) · [Design](./Design.md) · [Schema](./Schema.md). Update [Tracker.md](./Tracker.md) after every completed task.

---

## How to run this plan

1. **Autonomous by default.** Do not wait for the user between phases. Start at Phase 0 and continue to the end.
2. **Every phase ends with the same gate** (below). Only when it is fully green do you make a small conventional commit, tick the tasks in `Tracker.md`, and continue.
3. **Defer anything needing the user's accounts.** Build against `.env.example` with mocks/stubs/fixtures. Never block on a missing key, account, or deploy — write the code + tests with mocks and append the real step to `GOLIVE.md`.
4. **Stop only for a genuine blocker:** a truly ambiguous requirement, or a destructive/irreversible action. Otherwise keep going.
5. **Checkpointed mode** (opt-in): if the user set `BUILD_MODE=checkpointed` in `Rules.md`, pause for approval at each phase boundary instead of continuing.

## The per-phase gate (Definition of Done for a phase)

A phase is **done** only when all of the following pass. This is the "test + security gate on every phase," not just at the end.

- [ ] **Lint/format/type:** `ruff`, `ruff format`, `mypy --strict` (backend); `eslint`, `tsc --noEmit` (frontend) — clean.
- [ ] **Tests:** new unit + integration tests written and passing; coverage ≥ 80% on `domain/` + `application/`; agent-eval/golden cases pass where relevant.
- [ ] **Dependency audit:** `pip-audit` and `npm audit` (if FE touched) — no unresolved high/critical.
- [ ] **SAST:** `bandit` and `semgrep` — no unresolved high severity.
- [ ] **Secret scan:** `gitleaks` (or `trufflehog`) — **zero** findings; nothing sensitive staged.
- [ ] **LLM/agent security cases** relevant to this phase pass (grow the suite each phase; full matrix in Phase 11).
- [ ] **$0 check:** no paid service/dependency introduced.
- [ ] **Docs + Tracker:** contracts/docs updated if changed; `Tracker.md` rows moved to Done with date + notes.
- [ ] **Commit:** one small conventional commit (e.g. `feat(llm): add gemini adapter with retry decorator`). Never a giant dump.

CI (Phase 12) runs the same checks; locally they must pass before the commit.

---

## Phase 0 — Scaffolding & tooling
**Goal:** an empty but reputable repo that builds, lints, tests, and runs in Docker.
**Files/tasks**
- [ ] Monorepo layout per [Design §2](./Design.md); `backend/` (uv) + `frontend/` (pnpm).
- [ ] `pyproject.toml` with pinned deps (re-verify latest patch, record in Tracker); `ruff`, `mypy`, `pytest`, `pytest-asyncio`, `bandit`, `pip-audit` configured.
- [ ] `frontend/` Next.js 16.2 App Router + TS strict + Tailwind + eslint.
- [ ] `docker-compose.yml`: postgres (pgvector image), redis, backend, frontend, mlflow.
- [ ] `.env.example` (every var, safe placeholders), `.gitignore`, `LICENSE` (MIT), `CONTRIBUTING.md`, `README.md` skeleton.
- [ ] `Makefile`/task runner: `make up|test|lint|sec|eval`.
- [ ] Pre-commit hooks: ruff, gitleaks.
**Acceptance:** `docker compose up` boots all services; `make test` and `make lint` pass on a hello-world health test. **Gate → commit.**

## Phase 1 — Domain core (ports, entities, config)
**Goal:** the framework-free core.
- [ ] `domain/entities.py`, `value_objects.py`, `results.py` (typed errors / Result).
- [ ] `domain/ports/*` per [Design §3](./Design.md): `LLMProvider`, `EmbeddingProvider`, `SchemaCatalog`, `SqlValidator`, `QueryExecutor`, repositories, `Cache`, `Tracer`.
- [ ] `config.py` (Pydantic Settings) reads env only.
- [ ] Fakes/mocks for every port (in `tests/fakes/`).
**Acceptance:** domain has **no** outward imports (enforced by an import-linter rule); ports fully typed; fakes usable in tests. **Gate → commit.**

## Phase 2 — Persistence & schema
**Goal:** Postgres, migrations, repositories, and the security roles.
- [ ] SQLAlchemy async models for the `app` schema ([Schema §3](./Schema.md)).
- [ ] Alembic async env; autogenerate app schema; **hand-written** migrations for `CREATE EXTENSION vector`, the `analytics` schema, and the **roles/grants** ([Schema §5](./Schema.md)).
- [ ] Repository adapters implementing domain ports.
- [ ] CI check: `upgrade head` then `downgrade -1` on scratch DB.
**Acceptance:** migrations apply + reverse; `analytics_ro`/`datachat_exec` exist with SELECT-only, `statement_timeout=5s`, `read_only=on`; repositories pass integration tests. **Security case:** a write attempted as `datachat_exec` is rejected by the DB. **Gate → commit.**

## Phase 3 — LLM provider gateway
**Goal:** resilient, swappable LLM access ([Design §5](./Design.md)).
- [ ] `Adapter` per vendor (Gemini, Groq, OpenRouter) behind `LLMProvider`; httpx with timeouts.
- [ ] `ResilientProvider` Decorator (trace → cache → circuit-breaker → retry w/ backoff+jitter).
- [ ] `CircuitBreaker` (CLOSED/OPEN/HALF_OPEN) with shared state in Redis.
- [ ] `ProviderRouter` (Strategy): task- + health-aware selection, fallback order Gemini→Groq→(OpenRouter off by default).
- [ ] `EmbeddingProvider` (Gemini primary; local BGE offline path).
- [ ] Mock providers for tests (no real keys).
**Acceptance:** unit tests for breaker transitions, retry, fallback; integration test proves failover Gemini→Groq using mocks; adding a provider needs no core edits (OCP test). **Security:** timeouts + capped retries verified (LLM10). **Gate → commit.**

## Phase 4 — Semantic layer, ingestion & retrieval
**Goal:** grounded RAG-to-SQL context ([TechSpec §7](./TechSpec.md), [AppFlow §5,§9](./AppFlow.md)).
- [ ] Ingestion pipeline (Chain of Responsibility): fetch → validate+checksum → normalize → load `analytics` → build semantic layer → embed → version. Idempotent.
- [ ] `DatasetConnector` Adapters: World Bank WDI, OWID CO₂.
- [ ] `SchemaCatalog` (pgvector) retrieval of top-k tables/columns + few-shot examples.
- [ ] Seed fixtures for local/dev + golden set inputs.
**Acceptance:** `python -m ingestion.run --dataset wdi` is idempotent (re-run = no dupes); retrieval returns relevant tables for sample questions; embeddings dim = config. **Security:** ingestion validates/authenticates sources, checksums data (LLM04/ASI06). **Gate → commit.**

## Phase 5 — SQL guardrail & read-only executor
**Goal:** nothing unsafe can run ([Design §6](./Design.md), [Schema §5](./Schema.md)).
- [ ] `SqlValidatorChain` (sqlglot AST): SingleStatement, ReadOnly, TableAllowlist, NoSystemCatalog, MandatoryLimit rules.
- [ ] `QueryExecutor` on a **separate engine/pool** as `datachat_exec` (Bulkhead), row cap + timeout.
- [ ] Redis result cache decorator around the executor.
**Acceptance:** guardrail unit tests cover INSERT/UPDATE/DELETE/DDL/multi-statement/`pg_*`/comment-evasion/CTE-write attempts — all blocked; valid SELECT passes; executor enforces timeout + row cap. **Security (LLM05/LLM06/ASI02):** injection corpus (see Phase 11) fully blocked. **Gate → commit.**

## Phase 6 — Agent graph (MVP happy path)
**Goal:** the first end-to-end answer.
- [ ] `state.py`, `BaseNode` (Template Method: span → run → validate-output → checkpoint).
- [ ] Nodes: understand → retrieve_context → plan → generate_sql → guardrail_validate → execute → explain → respond.
- [ ] `GraphBuilder` (Builder) wires the `StateGraph` + `PostgresSaver` checkpointer.
- [ ] `NodeFactory` + `container.py` composition root (DI/Factory).
**Acceptance:** given a seeded DB + mock LLM, a question returns a correct table + grounded prose; run is fully traced; state is checkpointed each step. Maps FR-4…FR-8, FR-11. **Gate → commit.**

## Phase 7 — HITL, self-repair, verification, streaming, charts
**Goal:** the real agent (v1).
- [ ] `hitl_approve` + `clarify` via `interrupt()`; `/chat/{run_id}/resume` path; durable resume ([AppFlow §3,§4](./AppFlow.md)).
- [ ] `verify` node + bounded `repair` loop (`MAX_REPAIR_ATTEMPTS`) feeding DB errors back ([AppFlow §7](./AppFlow.md)).
- [ ] `visualize` node → Vega-Lite chart spec (validated JSON, not code).
- [ ] SSE event stream + event types ([TechSpec §4](./TechSpec.md)).
**Acceptance:** HITL pauses durably and resumes after simulated restart; repair fixes a deliberately broken query within budget then stops; chart spec validates against a schema; SSE emits the documented events. Maps FR-9,10,12,13,14. **Security (ASI08/ASI09):** loop caps enforced; approval cannot be bypassed server-side. **Gate → commit.**

## Phase 8 — BFF / API edge
**Goal:** the public contract, safely.
- [ ] Routers: `/chat` (SSE), `/chat/{id}/resume`, `/conversations/{id}`, `/datasets`, `/health`, `/ready`.
- [ ] Middleware: request-id, structured logging, input validation (Pydantic), rate limiting (Redis), idempotency keys, CORS.
- [ ] Error mapping → safe messages + code + trace_id.
**Acceptance:** contract tests for every endpoint; rate limit returns 429 with `Retry-After`; idempotent `POST /chat` de-dupes; no stack traces leak. Maps FR-21,22,24. **Gate → commit.**

## Phase 9 — Frontend (Next.js)
**Goal:** a clean, streaming chat UI (kept intentionally thin).
- [ ] Chat view: question input, streamed stages, SQL disclosure, results table, **Vega-Lite renderer** (`vega-embed`), HITL approve/edit/clarify UI.
- [ ] Typed API client + SSE handling; dataset picker; "waking up" cold-start state.
- [ ] Loading/empty/error states; accessible + responsive; a couple of Playwright smoke tests.
**Acceptance:** against the mock backend, the full journey works (ask → stream → chart), HITL approve/edit works, cold-start UX shows. Maps US1–US6, FR-12. **Gate → commit.**

## Phase 10 — MLflow: tracing, prompt registry, eval harness
**Goal:** the LLMOps proof.
- [ ] Tracing spans on graph + every node/LLM/tool call (autolog + manual) — 100% coverage.
- [ ] Prompt registry: register + version SQL-gen/repair/explain/verify/clarify; record version per run.
- [ ] Eval harness: golden set; scorers `execution_accuracy`, `sql_valid`, `explanation_faithfulness` (LLM-judge), latency/cost; baseline saved; `pytest -m eval`.
**Acceptance:** a trace appears per run with tokens/latency/provider/prompt-version; `pytest -m eval` produces metrics + writes `eval_runs`; regression beyond threshold fails. Maps FR-18,19,20, success metrics. **Gate → commit.**

## Phase 11 — Security hardening & OWASP suite
**Goal:** make the security story real and tested. Implement mitigations + tests for the matrix below.

**OWASP LLM Top 10 (2025) → mitigation → test**

| Risk | Mitigation in DataChat | Test |
|---|---|---|
| LLM01 Prompt Injection | Untrusted user input + data cells; guardrail before execute; system-prompt hardening; retrieved data never treated as instructions | Injection corpus tries to make it write/exfiltrate → all refused |
| LLM02 Sensitive Info Disclosure | Public non-PII data only; secrets never in prompts/logs; log minimization | Log scan test; no secrets in outputs |
| LLM03 Supply Chain | Pinned deps + lockfiles; pip-audit/npm audit in CI | CI audit job |
| LLM04 Data & Model Poisoning | Curated sources; ingestion validation + checksums | Tampered-fixture rejected |
| LLM05 Improper Output Handling | Every LLM output validated; SQL guardrailed; chart is validated JSON not code; no unsanitized HTML | Output-validation unit tests |
| LLM06 Excessive Agency | Read-only role; fixed least-privilege tools; no dynamic tools; HITL before execute | Tool-scope + write-attempt tests |
| LLM07 System Prompt Leakage | No secrets in system prompt; assume leakable | Prompt-dump attempt reveals nothing sensitive |
| LLM08 Vector/Embedding Weakness | Only curated docs embedded; retrieval read-only | Poisoned-example rejected at ingest |
| LLM09 Misinformation | Grounding + verify node + citations to rows + eval faithfulness | Faithfulness scorer threshold |
| LLM10 Unbounded Consumption | Rate limits, quotas, capped loops/retries, timeouts, circuit breaker | Load/abuse test hits limits gracefully |

**OWASP Agentic Top 10 (2026) → mitigation → test**

| Risk | Mitigation | Test |
|---|---|---|
| ASI01 Agent Goal Hijack | Scoped system role; retrieved content is data not instructions; refuse out-of-scope | Goal-hijack prompts don't change behavior |
| ASI02 Tool Misuse & Exploitation | Fixed tool set; read-only executor; arg validation | Malicious tool-arg tests |
| ASI03 Identity & Privilege Abuse | Separate `datachat_exec` RO role (Bulkhead); no app-schema access | Cross-schema read blocked |
| ASI04 Agentic Supply Chain | Pinned deps; scanners; verified model/provider endpoints | CI supply-chain job |
| ASI05 Unexpected Code Execution | No `eval`/dynamic code; SQL only via guardrail+RO role; chart = declarative JSON | Static check: no dynamic exec |
| ASI06 Memory & Context Poisoning | Checkpoint integrity; curated few-shots; windowed history; retrieved data sandboxed | Poisoned-history test |
| ASI07 Insecure Inter-Agent Comms | **Out of scope by design** (single-process subgraphs, no external agents) | N/A documented |
| ASI08 Cascading Agent Failures | Hard caps on repair/retries; circuit breakers; timeouts | Loop-cap + breaker tests |
| ASI09 Human-Agent Trust Exploitation | Server-side, non-bypassable HITL for approval; transparent SQL shown | Client-bypass attempt fails |
| ASI10 Rogue Agents | Bounded action space (read-only, fixed tools); full audit trail (`agent_actions`) | Audit completeness test |

**Acceptance:** every row has a passing test in `tests/security/`; `bandit`/`semgrep`/`gitleaks` clean; injection corpus 100% blocked; **0 unsafe SQL executed**. **Gate → commit.**

## Phase 12 — CI/CD & observability
- [ ] GitHub Actions: lint → type → unit/integration → security suite → `pytest -m eval` → build images. Cache deps.
- [ ] Coverage + eval metrics as CI artifacts; PR fails on regression or security finding.
- [ ] Minimal metrics endpoint + a small observability dashboard (requests, breaker state, provider failures, cache hit-rate, eval trend).
**Acceptance:** CI green end-to-end on a PR; a deliberately regressed eval fails the build. **Gate → commit.**

## Phase 13 — Deployment prep & hand-back
- [ ] Dockerfiles production-ready; `/ready` wired for keep-warm; `scripts/keep_warm.py` + cron instructions.
- [ ] Vercel/Render/Neon/Upstash/MLflow config documented against `.env.example` (no secrets committed).
- [ ] **Produce the hand-back:**
  1. **Final summary** — what was built, how to run locally, current test + security status.
  2. **`GOLIVE.md`** — the single ordered **YOUR ACTION ITEMS** checklist: create free accounts (Gemini, Groq, Neon, Upstash, Vercel, Render, Hugging Face, GitHub), exactly which key → which `.env` var, and the exact deploy clicks. Each step copy-pasteable.
  3. **Final security report** — run a full pass (and `/security-review` if available); summarize findings against the OWASP matrices; confirm `gitleaks` shows no secrets in history.
  4. **Confirmation** that `Tracker.md` matches reality and git history is small, incremental, conventional.
**Acceptance:** a new user can go from clone → local run with mocks in minutes, and from `GOLIVE.md` → live in one sitting. **Final gate → commit + tag `v1.0.0`.**

---

## Milestone → PRD scope mapping

| Milestone | Phases | PRD scope |
|---|---|---|
| MVP | 0–6 | retrieve → generate → guardrail → execute → answer + tracing |
| v1 | 7–10 | full agent, HITL, streaming, charts, fallback, eval |
| v2 | 11–13 | security suite, CI, observability, live $0 deploy |

## Teaching checkpoints (authenticity)
At the end of Phases 3, 6, 10, and 11, Claude Code MUST pause its narration to **quiz the user** with 2–3 "explain it in an interview" questions on what was just built (e.g., "why a circuit breaker over the free LLM APIs?", "why execution-accuracy over string match?", "why is the RO role needed if the guardrail already blocks writes?"). This is a required part of the milestone, per [Rules.md](./Rules.md).
