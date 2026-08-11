# Tracker — DataChat (Living Progress Board)

> **Claude Code MUST update this file after every completed task** — move the row's status and add the date + a one-line note. This is the single source of truth for build progress and mirrors [ImplementationPlan.md](./ImplementationPlan.md).
> Status legend: `To Do` · `In Progress` · `Done` · `Blocked` (add reason).

## Board

| Task | Phase | Status | Notes | Date |
|---|---|---|---|---|
| Repo scaffold, docker-compose, tooling, hygiene files | 0 | Done | uv backend + Next.js FE + compose + Makefile + pre-commit; full local gate green (ruff, mypy --strict, pytest, bandit, gitleaks, pip-audit 0 vulns) | 2026-07-23 |
| Domain entities, value objects, results | 1 | Done | frozen dataclasses; Result/Either + error taxonomy; 99% cov | 2026-07-23 |
| Domain ports (interfaces) + fakes | 1 | Done | 6 role-specific Protocols; fakes for every port; conformance test | 2026-07-23 |
| Config (Pydantic Settings) | 1 | Done | env-only, mock-first, SecretStr keys, $0 defaults | 2026-07-23 |
| SQLAlchemy models (app schema) | 2 | Done | app + analytics ORM (11+4 tables), pgvector(768), CHECK/FK/index; metadata test | 2026-07-23 |
| Alembic migrations (schema + pgvector + roles) | 2 | Done | async env; 0001 app+pgvector+HNSW, 0002 analytics, 0003 roles/grants; chain+security static tests | 2026-07-23 |
| Repository adapters | 2 | Done | Sql* repos implement domain ports; row<->entity mappers; integration round-trips (CI) | 2026-07-23 |
| Read-only role + execution safety verified | 2 | Done | analytics_ro SELECT-only + datachat_exec timeout/read-only; write-rejection + cross-schema tests (CI) | 2026-07-23 |
| LLM Adapters (Gemini/Groq/OpenRouter) | 3 | Done | httpx adapters + MockTransport tests; retryable-error mapping; OpenAI-compat base | 2026-07-23 |
| ResilientProvider decorator stack | 3 | Done | Trace->Cache->Breaker->Retry, explicit order; backoff+jitter, retry_after, capped | 2026-07-23 |
| CircuitBreaker + Redis shared state | 3 | Done | CLOSED/OPEN/HALF_OPEN via Cache port; injected clock; per-provider; transition tests | 2026-07-23 |
| ProviderRouter (Strategy) + fallback | 3 | Done | task+health-aware order; Gemini->Groq failover test; OCP add-provider test | 2026-07-23 |
| EmbeddingProvider | 3 | Done | Gemini embed adapter + deterministic local-hash offline path | 2026-07-23 |
| Ingestion pipeline (CoR) + connectors | 4 | Done | CoR steps (fetch->validate+checksum->load->embed->version), idempotent; seed/WDI/OWID connectors | 2026-07-24 |
| SchemaCatalog pgvector retrieval | 4 | Done | pgvector catalog (cosine top-k) + offline in-memory catalog; retrieval tests green | 2026-07-24 |
| Seed fixtures + golden inputs | 4 | Done | curated 15-country seed + few-shot + eval examples in definitions; loads via --dataset seed | 2026-07-24 |
| SQL guardrail chain (sqlglot) | 5 | Done | AST CoR: SingleStatement/ReadOnly(incl CTE-write)/TableAllowlist/NoSystemCatalog/MandatoryLimit; injection corpus 100% blocked | 2026-07-24 |
| Read-only QueryExecutor (Bulkhead) + cache | 5 | Done | streamed row cap + timeout on datachat_exec engine; redis result-cache decorator; executor integration tests (CI) | 2026-07-24 |
| Agent state + BaseNode (Template Method) | 6 | Done | AgentState TypedDict; BaseNode span->run->validate-output; untrusted LLM output checked in-node | 2026-07-24 |
| MVP nodes + GraphBuilder + checkpointer | 6 | Done | understand..respond; StateGraph + guardrail/execute branches; MemorySaver in tests, PostgresSaver in prod | 2026-07-24 |
| NodeFactory + composition root (DI) | 6 | Done | NodeFactory by name; container.py wires mock/real adapters; end-to-end test with fakes (no DB/keys) | 2026-07-24 |
| HITL approve/clarify (interrupt + resume) | 7 | Done | langgraph interrupt() before execute + in understand; durable resume via Command; edit=approval; server-side non-bypassable (ASI09) | 2026-07-24 |
| Verify + bounded repair loop | 7 | Done | verify plausibility; repair feeds DB error back to generate; hard-capped at MAX_REPAIR (ASI08) | 2026-07-24 |
| Visualize node (Vega-Lite spec) | 7 | Done | declarative Vega-Lite built from rows + structural validation; never code (LLM05/ASI05) | 2026-07-24 |
| SSE streaming + event types | 7 | Done | QueryService.stream/resume over graph.astream; status/plan/sql/rows/explanation_delta/chart_spec/awaiting_approval/error/done | 2026-07-24 |
| BFF routers + middleware (rate-limit, idempotency) | 8 | Done | /chat SSE, /resume, /conversations, /datasets, /health, /ready; request-id + structlog; per-IP+global rate limit; idempotency-key dedupe; CORS | 2026-07-24 |
| Safe error mapping | 8 | Done | exception handlers -> code+message+trace_id; in-stream errors -> safe error event; no stack traces leak; contract tests green | 2026-07-24 |
| Frontend chat UI + SSE + chart renderer | 9 | Done | Next.js client: typed API + SSE parser, streamed stages, SQL disclosure, results table, vega-embed chart; tsc+eslint+build clean; pnpm audit 0 | 2026-07-24 |
| HITL UI + cold-start UX + smoke tests | 9 | Done | approve/edit/reject + clarify panels; waking banner; loading/empty/error states; playwright smoke specs (CI) | 2026-07-24 |
| MLflow tracing (100% coverage) | 10 | Done | MLflowTracer behind Tracer port; every node (BaseNode) + LLM call (decorator) span-wrapped; best-effort, degrades to no-op offline | 2026-07-24 |
| Prompt registry + versioning | 10 | Done | PROMPT_VERSIONS catalog (sql_generation/explanation/clarify/faithfulness); versions recorded per run in state+trace | 2026-07-24 |
| Eval harness + scorers + golden set | 10 | Done | execution_accuracy (result-set equality) + sql_valid + faithfulness (LLM-judge); regression gate; golden set; pytest -m eval writes eval_runs | 2026-07-24 |
| OWASP LLM Top 10 mitigations + tests | 11 | Done | LLM01-10 mapped to mitigations + tests; compromised-model-output-can't-write; secret hygiene; bounded consumption | 2026-07-24 |
| OWASP Agentic Top 10 mitigations + tests | 11 | Done | ASI01-10 mapped; audit outbox (ASI10); non-bypassable HITL (ASI09); no dynamic exec (ASI05); inter-agent out-of-scope (ASI07) | 2026-07-24 |
| Injection corpus + security suite green | 11 | Done | ~30-entry injection corpus 100% blocked; full security suite green; bandit/gitleaks clean; SECURITY.md matrix | 2026-07-24 |
| GitHub Actions CI (all gates) | 12 | Done | ci.yml: backend(lint/type/import-linter/test+cov/eval/bandit/pip-audit w/ pg+redis) + frontend(lint/tsc/build/pnpm audit) + gitleaks/semgrep + docker image build | 2026-07-24 |
| Observability dashboard | 12 | Done | in-process Metrics + /metrics (prometheus) + /api/v1/metrics (json); request+cache-hit counters, live breaker states; frontend /dashboard page | 2026-07-24 |
| Deployment prep + keep-warm | 13 | Done | prod Dockerfiles (non-root) + .dockerignore; scripts/keep_warm.py + purge_old_turns.py; keep-warm cron workflow; /ready wired | 2026-07-24 |
| GOLIVE.md + final security report + handback | 13 | Done | GOLIVE.md ordered action items; SECURITY.md OWASP matrix; final scans clean (pip-audit/pnpm audit 0, gitleaks history clean, bandit 0); tagged v1.0.0 | 2026-07-24 |

## Verified versions (Claude Code fills at build time)

| Dependency | Planned (2026-07-23) | Pinned at build | Date |
|---|---|---|---|
| langgraph | 1.2.x (1.2.9) | 1.2.9 | 2026-07-23 |
| langgraph-checkpoint-postgres | latest | 3.1.0 | 2026-07-23 |
| mlflow | 3.14.x | 3.14.0 | 2026-07-23 |
| fastapi | 0.136.x | 0.139.2 | 2026-07-23 |
| pydantic | 2.10.x | 2.13.4 | 2026-07-23 |
| sqlalchemy | 2.0.x | 2.0.51 | 2026-07-23 |
| alembic | 1.14.x | 1.14.1 | 2026-07-23 |
| sqlglot | 26.x | 26.33.0 | 2026-07-23 |
| starlette (transitive) | — | 1.3.1 (CVE-fixed) | 2026-07-23 |
| pgvector (ext) | 0.8.x | pgvector/pgvector:pg16 | 2026-07-23 |
| next | 16.2.x | 15.1.3 | 2026-07-23 |
| react | 19.x | 19.x | 2026-07-23 |

## Blockers / decisions log

| Date | Item | Resolution |
|---|---|---|
| 2026-07-23 | Next.js 16.2 not available in index | Pinned Next.js 15.1.3 (latest resolvable) + React 19; App Router unchanged. Revisit at go-live. |
| 2026-07-23 | mlflow 2.x / pyarrow / starlette 0.46 carried known CVEs | Bumped to mlflow 3.14.0, pyarrow 24, starlette 1.3.1, pytest 9.1.1; pip-audit now clean. |
| 2026-07-23 | Dev box blocks mypy/_ctypes/exe-shims via Windows Application Control (WDAC) | Run pure-python mypy from a signed-interpreter tool venv (`scripts/typecheck.sh`); invoke pytest/ruff/bandit/pip-audit as `python -m ...`. CI (Linux) uses the standard invocations. |
| 2026-07-23 | semgrep has poor Windows support | Wired into CI (Linux) in Phase 12; local SAST covered by bandit + ruff's flake8-bandit (S) rules. |
| 2026-07-23 | import-linter's grimp (`_rustgrimp`) also WDAC-blocked locally | Contracts run in CI; locally the dependency rule is enforced by an ast-based fitness test (`tests/unit/test_architecture.py`). |

## Post-Phase-13 work

| Item | Status | Note | Date |
|---|---|---|---|
| Eval gate made real | Done | CI assert was `0.0 <= acc <= 1.0` and the job scored 0.0 while passing. Split into a deterministic pipeline gate (`make eval`, CI) and an opt-in quality gate vs committed `eval_baseline.json` (`make eval-real`, tolerance 0.05). Verified failing by mutation. | 2026-08-11 |
| Golden set 5 → 26 | Done | 21 answerable + 5 refusal, covering lookups, aggregations, rankings, joins, group-by, time series. Refusals scored separately as `refusal_accuracy`. | 2026-08-11 |
| Train/test leakage fixed | Done | One golden question was a verbatim few-shot example; `test_golden_set.py` now fails the build on any duplicate. | 2026-08-11 |
| `guardrail_pass_rate` removed | Done | Same expression as `sql_valid_rate` — two names for one number. DB column retained, now stores `sql_valid_rate`. | 2026-08-11 |
| Published numbers corrected | Done | 0.667 exec / 0.80 refusal / 0.952 valid / 0.857 faithfulness on qwen2.5:7b-instruct, `temperature=0`, n stated per metric. Old 0.80 came from 5 easy cases with a leak. | 2026-08-11 |
| Cache latency measured | Done | 987–1569 ms cold → 77–87 ms cached. Replaces the unreproducible "20–40s → 70ms". | 2026-08-11 |
| Ollama keyless auth fix | Done | `Bearer {empty}` is an illegal httpx header; header now omitted when no key. Unblocks the documented local Ollama path. | 2026-08-11 |
| Container verified end to end | Done | Five services from a wiped volume, auto-migrate + seed, `/ready` 200, SSE streaming with `USE_MOCKS=false` against qwen2.5:7b-instruct. | 2026-08-11 |
| Web fallback returns a table | Done | `web_table@v1` extraction with per-row citations, distinct `WebTable` type + `web_table` SSE event + web report layout + `source_url` in CSV. Parser enforces attribution. Off by default. | 2026-08-11 |
| FLOW.md | Done | Single-file architecture walkthrough with trust boundaries; linked as the entry point from the README. | 2026-08-11 |

## Known open items

| Item | Why it matters |
|---|---|
| Frontend does not render `web_table` | The API returns it; `ResultsTable.tsx` / `useChat.ts` do not consume it yet, so the browser UI shows only the prose. |
| Refusal cases conflict with web fallback | Enabling `DATACHAT_WEB_SEARCH_ENABLED` makes 3 of 5 refusal cases wrong — they should *escalate*, not refuse. Needs a refuse/escalate split and an `escalation_accuracy` metric before going live with it. |
| 7 integration tests fail on the Windows host | `datachat_exec` password auth; pre-existing, reproduces on clean `master`, fails in isolation, survives a wiped volume. Not an empty-password hole (`pg_authid` shows a real SCRAM verifier). CI is the reference environment. |
| Backend image is 3.16GB | ~1.13GB duplicated venv layer (`chown -R` after `COPY`), ~470MB MLflow scientific stack, dev tools shipped (no `--no-dev`). Hurts a Render free-tier cold pull. |
| Startup blocks on MLflow | With the tracking server down, boot took ~90s. Tracing is best-effort at runtime but not at startup. |
| Repair budget spent on unanswerable questions | Three SQL generations before falling through to the web fallback. |

## Deferred to GOLIVE.md (needs user accounts)

| Item | Why deferred |
|---|---|
| Gemini/Groq API keys | User account required |
| Neon / Upstash connection strings | User account required |
| Vercel / Render / HF deploys | User account + clicks required |
| Public MLflow host (optional) | User account required |
