# PRD — DataChat

> **Product Requirements Document**
> Project: **DataChat** — an agentic natural-language analytics platform over open datasets.
> *(Working name; rename freely — see README.)*
> Status: Approved for build · Owner: Sahil Chakraborty · Last updated: 2026-07-23
> Sibling docs: [TechSpec](./TechSpec.md) · [AppFlow](./AppFlow.md) · [Design](./Design.md) · [Schema](./Schema.md) · [ImplementationPlan](./ImplementationPlan.md) · [Rules](./Rules.md)

---

## 1. Problem statement

Public open datasets (World Bank development indicators, Our World in Data, data.gov) are rich but locked behind SQL and BI tooling. Non-technical people cannot ask them questions, and even technical users lose time hand-writing exploratory queries. Meanwhile, most "text-to-SQL" demos are single-shot prompt wrappers: they hallucinate columns, run unvalidated (sometimes destructive) SQL, have no evaluation, and no observability.

**DataChat** turns a plain-English question into a **safe, grounded, verified** SQL analysis over curated open data. It is built as a real **agent** (plan → generate → guardrail → execute → verify → repair → explain), not a single prompt, with an evaluation harness, tracing, and least-privilege security throughout. The point is to demonstrate production agentic engineering, not a toy.

## 2. Target users & personas

| Persona | Who | Needs | What DataChat gives them |
|---|---|---|---|
| **Jamie (Journalist)** | Non-technical, data-curious | Answers + a chart to embed, fast | NL question → chart + plain-English explanation with numbers tied to real rows |
| **Ana (Analyst)** | Technical, "trust but verify" | Quick exploration; wants to see and tweak the SQL | Streamed reasoning, the executed SQL shown, HITL approve/edit before run |
| **Sam (Student)** | Learning data + SQL | To learn *how* the answer was derived | Transparent plan + SQL + explanation as a teaching artifact |
| **Riley (Recruiter / Hiring manager)** — meta-persona | Evaluating Sahil | Evidence of production skill in <10 min | A live demo, clean repo, eval + security rigor, and an architecture story |

The Riley persona is deliberate: this is a portfolio piece, so "legible to a hiring manager in ten minutes" is a first-class requirement, not an afterthought.

## 3. Goals & non-goals

**Goals**
- G1. Convert NL questions into correct, **read-only** SQL over curated open datasets and return a grounded answer + chart.
- G2. Be an *agent*: multi-step planning, tool use, self-repair, verification, and human-in-the-loop.
- G3. Be **evaluated**: an execution-accuracy golden set gates every change in CI.
- G4. Be **safe**: no unsafe SQL can ever execute; OWASP LLM + Agentic mitigations applied.
- G5. Be **observable**: every run and model call traced in MLflow.
- G6. Run **entirely on $0 free tiers** with an honest cold-start UX, deployable to a live URL.

**Non-goals (v1)** — scope discipline is itself a design signal.
- NG1. **No write/DDL** ever. DataChat is read-only analytics; it will never mutate data.
- NG2. **No user-uploaded datasets** in v1 (curated open datasets only). User uploads = future.
- NG3. **No multi-tenant SaaS / billing.** Public demo with rate limiting; auth is optional/lightweight.
- NG4. **No model fine-tuning.** Grounding is via semantic layer + retrieval + few-shot prompting.
- NG5. **Not a general chatbot.** Out-of-scope questions are refused with a helpful message.
- NG6. **No multi-agent mesh across networks.** Sub-steps are LangGraph subgraphs in one process (keeps ASI07 *Insecure Inter-Agent Communication* out of scope by design).

## 4. User stories

- US1. *As Jamie,* I ask "Which 10 countries had the highest CO₂ per capita in 2022?" and get a ranked bar chart plus a one-paragraph explanation.
- US2. *As Ana,* I ask a question, see the generated SQL, edit one clause, approve it, and get results — without leaving the chat.
- US3. *As Ana,* when my question is ambiguous ("richest countries" — by GDP? per capita?), the agent asks me which metric I mean before running.
- US4. *As Sam,* I can expand each step (plan, retrieved schema, SQL, verification) to learn how the answer was built.
- US5. *As any user,* if a provider is down or rate-limited, I still get an answer via automatic fallback, or a clear "try again shortly" message — never a crash.
- US6. *As any user,* my previous questions in this conversation inform follow-ups ("now show it per capita").
- US7. *As Sahil (operator),* I can open MLflow and see the full trace, prompt version, latency, and token cost of any run.
- US8. *As Riley,* I can open the live URL, ask one question, and immediately see it work — even after the app has been idle.

## 5. Functional requirements

Numbered and testable. Each maps to acceptance criteria in [ImplementationPlan](./ImplementationPlan.md) and status in [Tracker](./Tracker.md).

**Data & semantic layer**
- **FR-1** An offline ingestion pipeline loads curated open datasets (v1: World Bank WDI + Our World in Data subset) into a dedicated **read-only `analytics` schema** in Postgres.
- **FR-2** The system maintains a **semantic layer** per dataset: table/column descriptions, units, synonyms, allowed join keys, and curated few-shot NL→SQL examples.
- **FR-3** Ingestion is **idempotent** and **versioned** (re-running does not duplicate; each load records a dataset version + checksum).

**Ask → answer**
- **FR-4** A user submits an NL question through the chat UI.
- **FR-5** The agent retrieves the **relevant schema subset + few-shot examples** for the question (RAG over the semantic layer via pgvector) to ground generation.
- **FR-6** The agent **plans** the analysis and generates **one** read-only SQL statement grounded in retrieved schema (no invented tables/columns).
- **FR-7** Generated SQL must pass a **guardrail pipeline** (read-only only; single statement; allow-listed `analytics` tables only; mandatory `LIMIT`; no system catalogs/functions) **before** execution. Failing SQL is repaired or refused — **never executed**.
- **FR-8** Validated SQL executes against a **read-only least-privilege role** with a **statement timeout** and **row cap**.
- **FR-9** On DB error / empty / timeout, the agent runs a **bounded self-repair loop** (≤ `MAX_REPAIR_ATTEMPTS`, default 2) using the DB error as feedback.
- **FR-10** The agent **verifies** results (shape/plausibility) before answering.
- **FR-11** The response includes: (a) a prose explanation grounded in the returned rows, (b) the **executed SQL** (transparency), (c) a **declarative chart spec** (Vega-Lite JSON) when a chart is appropriate.
- **FR-12** Responses **stream** to the UI step-wise via SSE, surfacing agent progress (planning → generating → executing → explaining).
- **FR-13** **HITL — approve SQL:** when enabled (config or risk flag), the agent **interrupts** and presents the SQL for approve/edit before execution; run state is **durable** across the interrupt (resumes after reload/cold start).
- **FR-14** **HITL — clarify:** when the question is ambiguous, the agent asks a clarifying question instead of guessing.
- **FR-15** Conversations and turns are **persisted**; follow-up questions use prior turn context.

**Resilience**
- **FR-16** All LLM calls go through a **provider abstraction** with ≥2 providers (Gemini primary, Groq fallback) and automatic failover.
- **FR-17** A **circuit breaker** opens per provider on repeated failures/429s and routes to the next provider; it half-opens to recover.

**Observability & evaluation**
- **FR-18** Every agent run and LLM/tool call is **traced in MLflow** (spans, I/O, latency, tokens, provider, prompt version).
- **FR-19** Prompts live in a **versioned registry**; each run records the exact version used.
- **FR-20** An **evaluation harness** scores a curated golden NL→SQL set by **execution accuracy** (+ guardrail pass rate + explanation faithfulness) and runs in **CI as a regression gate**.

**Security & abuse**
- **FR-21** Per-IP/session **rate limiting** and a global daily **quota** protect the free LLM tiers.
- **FR-22** All user input and **all LLM output are validated at every service boundary**; LLM output is treated as untrusted.
- **FR-23** **No write/DDL** path exists from the agent to any database (enforced at both DB-role and guardrail levels — defence in depth).

**Ops**
- **FR-24** `/health` (liveness) and `/ready` (readiness) endpoints; a **keep-warm** mechanism mitigates free-tier cold starts.
- **FR-25** The whole app runs locally via `docker compose up` using `.env.example` with **mocked external services** and seed data (no real keys required to develop).

## 6. Non-functional requirements

- **NFR-1 — Cost:** **$0/month**, permanent free tiers / OSS only. Introducing any paid dependency is a build failure (see [Rules](./Rules.md)).
- **NFR-2 — Performance (warm):** first streamed token ≤ ~2s; p95 end-to-end ≤ ~8s for a typical single-table query. Latency is dominated by free-tier LLMs; the design must stream to hide it.
- **NFR-3 — Availability:** best-effort under free-tier scale-to-zero. Cold-start recovery ≤ ~60s with an explicit "waking up" UX; **no state loss** across sleeps (durable Postgres checkpointer).
- **NFR-4 — Security:** OWASP **LLM Top 10 (2025)** + **Agentic Top 10 (2026)** mitigations (see [TechSpec §12]); no secrets in code; least privilege everywhere.
- **NFR-5 — Privacy:** only public, **non-PII** open data. User questions are logged with minimization and a defined retention window (see [Schema §7]).
- **NFR-6 — Reliability:** provider failover, bounded retries with backoff, and graceful, human-readable degradation — never a raw stack trace to the user.
- **NFR-7 — Maintainability:** clean architecture; ≥80% unit coverage on domain + application layers; fully typed (`mypy --strict` backend, `tsc` strict frontend).
- **NFR-8 — Portability:** DB, vendors, and the agent framework sit behind ports; local topology mirrors prod so "works on my machine" == "works deployed."
- **NFR-9 — Observability:** 100% of agent runs traced; structured JSON logs with a correlation ID propagated end-to-end.
- **NFR-10 — Scalability posture:** backend is **stateless** (all state in Postgres/Redis) so it *could* scale horizontally, even though the free tier runs a single instance.

## 7. Success metrics

| Metric | Target (v2) | How measured |
|---|---|---|
| **Execution accuracy** on golden set | **≥ 70%** | `execution_accuracy` scorer (BIRD baseline ~73%, so this is honest, not inflated) |
| **Unsafe SQL executed** | **0** (hard gate) | Guardrail + security test suite |
| **Guardrail pass rate** (safe queries not wrongly blocked) | ≥ 95% | Eval harness |
| **Explanation faithfulness** | ≥ 90% | LLM-as-judge scorer against returned rows |
| **Provider-failover success** | Answer served despite primary down | Chaos/integration test |
| **Cold-start recovery** | ≤ 60s to first token | Timed probe after idle |
| **Secrets in repo** | 0 | gitleaks in CI |
| **Trace coverage** | 100% of runs | MLflow |
| **Live demo** | Reachable + returns a correct answer | Manual + uptime ping |

## 8. Scope: MVP → v1 → v2

Layered so the app is **runnable and demoable at every stage** (mitigates the marathon's main risk: loss of momentum).

- **MVP (weeks 1–4):** one dataset; retrieve schema → generate SQL → guardrail → read-only execute → return table + prose; MLflow tracing on; runs via `docker compose`. *Demoable.*
- **v1 (weeks 5–8):** full agent graph (plan → generate → guardrail → execute → verify → repair → explain → visualize); HITL approve/clarify; SSE streaming + chart specs; provider fallback + circuit breaker; prompt registry.
- **v2 (weeks 9–12):** multi-dataset semantic layer + connector abstraction; execution-accuracy eval harness in CI; observability dashboards; full OWASP security test suite; live $0 deployment + keep-warm.

## 9. Assumptions & constraints

- **A1.** Free tiers as verified 2026-07-23 (see [TechSpec §11]); limits change — Claude Code re-verifies at build time.
- **A2.** Vercel Hobby is **non-commercial** — fine for a portfolio demo; if monetized later, hosting must change.
- **A3.** Neon free scales to zero after 5 min and caps at 0.5 GB / 100 compute-hours per month → the curated corpus must stay **small and bounded** (a design constraint, not an accident).
- **A4.** Free LLM latency and daily caps are real → stream everything, cache aggressively, and rate-limit users.
- **A5.** Text-to-SQL has a known "performance cliff" on complex/multi-join questions → the semantic layer intentionally **narrows** the surface and the eval set is scoped to what the loaded datasets support.

## 10. Open questions (tracked)

| # | Question | Default if unresolved |
|---|---|---|
| OQ-1 | Add lightweight auth (Supabase/JWT) or leave the demo open behind rate limits? | Open + rate-limited for v1; auth deferred to `GOLIVE`/future |
| OQ-2 | Second dataset for v2 — data.gov slice vs a second OWID domain? | OWID second domain (simpler, cleaner schema) |
| OQ-3 | Host MLflow UI publicly or keep tracking-only? | Tracking-only for $0 stability; public UI is a stretch |

*Resolve or accept defaults before the relevant build phase.*
