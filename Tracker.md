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
| HITL approve/clarify (interrupt + resume) | 7 | To Do | | |
| Verify + bounded repair loop | 7 | To Do | | |
| Visualize node (Vega-Lite spec) | 7 | To Do | | |
| SSE streaming + event types | 7 | To Do | | |
| BFF routers + middleware (rate-limit, idempotency) | 8 | To Do | | |
| Safe error mapping | 8 | To Do | | |
| Frontend chat UI + SSE + chart renderer | 9 | To Do | | |
| HITL UI + cold-start UX + smoke tests | 9 | To Do | | |
| MLflow tracing (100% coverage) | 10 | To Do | | |
| Prompt registry + versioning | 10 | To Do | | |
| Eval harness + scorers + golden set | 10 | To Do | | |
| OWASP LLM Top 10 mitigations + tests | 11 | To Do | | |
| OWASP Agentic Top 10 mitigations + tests | 11 | To Do | | |
| Injection corpus + security suite green | 11 | To Do | | |
| GitHub Actions CI (all gates) | 12 | To Do | | |
| Observability dashboard | 12 | To Do | | |
| Deployment prep + keep-warm | 13 | To Do | | |
| GOLIVE.md + final security report + handback | 13 | To Do | | |

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

## Deferred to GOLIVE.md (needs user accounts)

| Item | Why deferred |
|---|---|
| Gemini/Groq API keys | User account required |
| Neon / Upstash connection strings | User account required |
| Vercel / Render / HF deploys | User account + clicks required |
| Public MLflow host (optional) | User account required |
