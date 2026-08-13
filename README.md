<div align="center">

# DataChat

**Ask open data in plain English. Get safe, verified SQL, a grounded answer, and a chart.**
An agentic natural-language analytics platform over public datasets — built as a real LangGraph agent, evaluated, observable, and secured, running entirely on free tiers.

<!-- Rename freely — "DataChat" is a working title. -->

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-1.2-1C3C3C)
![MLflow](https://img.shields.io/badge/MLflow-3.14-0194E2?logo=mlflow&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-16.2-000000?logo=nextdotjs&logoColor=white)
![Postgres](https://img.shields.io/badge/Postgres-pgvector-4169E1?logo=postgresql&logoColor=white)
![Cost](https://img.shields.io/badge/cost-%240%2Fmonth-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)

[**▶ Live demo**](https://data-chat-seven.vercel.app/) · [API](https://datachat-api-wmpd.onrender.com/health) · [API docs](https://datachat-api-wmpd.onrender.com/docs) · [Architecture](#architecture) · [Flow](./FLOW.md) · [Design](./Design.md)

> **First load after idle takes ~50s.** The backend runs on a free tier that sleeps
> after 15 minutes and the database scales to zero. A keep-warm ping every 12
> minutes mitigates it. This is a documented trade-off of a genuinely $0 deploy,
> not a bug — see [Live deployment](#live-deployment).

Or hit the API directly, no setup:

```bash
curl -N -X POST https://datachat-api-wmpd.onrender.com/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"Which 5 countries had the highest CO2 per capita in 2022?"}'
```

</div>

---

<!-- ┌──────────────────────────────────────────────────────────────────────────┐
     │  HERO GIF — drop the file at docs/hero.gif and delete this comment block │
     │  and the placeholder line below. Recording steps: docs/README.md         │
     └──────────────────────────────────────────────────────────────────────────┘ -->

<!-- Once docs/hero.gif exists, uncomment the next line: -->
<!-- ![DataChat in action](docs/hero.gif) -->

> **[ Hero GIF goes here ]** — a 15–20s loop: question typed → plan streams → SQL
> appears → table fills → chart renders. Recording instructions in
> [docs/README.md](docs/README.md).

## The problem & why it matters

<!-- 👉 YOUR WORDS (2–4 sentences). A strong start: "Public datasets like the World Bank's are a goldmine, but you need SQL to use them. I wanted anyone to be able to just ask — safely, and with an answer they can trust." Make it yours. -->

Public open datasets are rich but locked behind SQL and BI tools. Most "text-to-SQL" demos are single-shot prompts that hallucinate columns, run unvalidated queries, and are never evaluated. **DataChat** treats the problem as it actually is in production: a multi-step agent that plans, grounds itself in a semantic layer, generates SQL, **guardrails and verifies it before execution**, repairs its own mistakes, and explains the result — with tracing and an evaluation harness proving it works.

## Key features

- **Real agent, not a prompt** — LangGraph graph: plan → retrieve → generate SQL → guardrail → (human approve) → execute → verify → self-repair → explain → visualize.
- **Safe by construction** — generated SQL passes an AST guardrail chain *and* runs on a read-only, least-privilege DB role with timeouts. No write path exists.
- **Grounded (RAG-to-SQL)** — a semantic layer (schema docs, synonyms, few-shot examples) is retrieved via pgvector so the model doesn't invent columns.
- **Human-in-the-loop** — approve or edit the SQL before it runs; durable state means the pause survives reloads and cold starts.
- **Your GPU is the AI** — a self-hosted **Ollama** model (behind a token-guarded tunnel) is the primary provider, with **Gemini→Groq** as automatic circuit-breaker fallback. Private, free, and swappable.
- **Instant on repeats** — a normalised whole-answer cache replays a prior answer for the same question, skipping the whole LLM chain, with zero false-positive risk (exact-match, never fuzzy). Measured **~1.0–1.6 s → ~80 ms** (see [Evaluation](#evaluation) for conditions).
- **Downloadable reports & data** — every answer can be exported as a Markdown report (question, summary, SQL, table, and links to the source datasets) or a CSV of the result set.
- **Honest out-of-scope answers** — when the governed data has no answer, an optional, injection-hardened web fallback returns a **structured table with a citation on every row**, plus a summary and a downloadable report. Web data is a separate type end to end — its own SSE event, its own report layout, `source_url` in the CSV — so a scrape can never be rendered as verified data, and it never re-enters the SQL path.
- **Evaluated** — a 26-case golden set (21 answerable + 5 that *should* be refused) scored by result-set equality, BIRD-style. A deterministic pipeline gate runs on every PR; the model-quality number is measured separately against a committed baseline. See [Evaluation](#evaluation).
- **Observable** — every run and model call traced in MLflow, with a versioned prompt registry.
- **Streaming UI** — watch the agent think; results render as a chart from a backend-emitted Vega-Lite spec.
- **$0/month** — every component runs on a permanent free tier or your own hardware.

## Architecture

A **modular monolith with microservice-grade boundaries** — clean architecture + dependency inversion keep vendors, the DB, and even LangGraph as swappable details. It's microservice-*ready* without paying the ops cost prematurely.

```mermaid
flowchart LR
  UI["Next.js UI<br/>(Vercel)"] -->|SSE| BFF["FastAPI BFF<br/>rate-limit · stream"]
  BFF --> AGENT["LangGraph agent<br/>plan→SQL→guardrail→verify→explain→(web fallback)"]
  AGENT --> SEM["Semantic layer<br/>(pgvector RAG)"]
  AGENT --> GUARD["SQL guardrail +<br/>read-only executor"]
  AGENT --> LLM["Provider gateway<br/>Ollama (your GPU) → Gemini/Groq"]
  LLM -.->|token-guarded tunnel| OLL["Ollama on your PC<br/>(Cloudflare + Caddy auth)"]
  GUARD -->|read-only role| PG[("Postgres + pgvector<br/>Neon")]
  SEM --> PG
  BFF --> REDIS[("Redis · Upstash<br/>rate-limit · answer cache")]
  AGENT -. traces .-> MLF["MLflow"]
```

The differentiators — the **agentic LangGraph core**, the **guardrail + read-only-role defence in depth**, the **provider circuit breaker**, and the **eval harness** — are documented in depth in **[Design.md](./Design.md)** and **[TechSpec.md](./TechSpec.md)**. Named patterns (Strategy, Adapter, Decorator, Chain of Responsibility, Circuit Breaker, Template Method, Repository, Builder…) are mapped to SOLID in Design §4.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Agent | LangGraph 1.2 | Durable state, checkpoints, HITL interrupts, subgraphs |
| Backend | FastAPI + Pydantic v2 + SQLAlchemy 2 (async) | Typed, async, boundary validation as a control |
| LLMs | Ollama (self-hosted, primary) + Gemini/Groq fallback, pluggable | Provider abstraction + circuit breaker; private GPU, strictly free |
| Data / vectors | Postgres + pgvector (Neon) | One system for relational data *and* embeddings |
| Cache / limits | Redis (Upstash) | Result cache, rate limiting, breaker state |
| LLMOps | MLflow 3.14 | Tracing, prompt registry, evaluation, CI gate |
| Frontend | Next.js 16 + React 19 + Tailwind | Streaming chat; thin Vega-Lite renderer |
| CI/CD | GitHub Actions | Lint, type, test, security, eval on every PR |
| **Cost** | **Free tiers only** | **Runs entirely on $0 — by design, not by luck** |

## Getting started (local, no API keys needed)

Local dev runs against mocks + seed data, so you can try it before creating any accounts.

**Prerequisites:** Docker + Docker Compose, and (for non-container dev) `uv` and `pnpm`.

```bash
git clone https://github.com/<you>/datachat.git
cd datachat
cp .env.example .env          # defaults use USE_MOCKS=true — no real keys required
docker compose up --build     # postgres+pgvector, redis, backend, frontend, mlflow

# seed the sample open-data slice + few-shot examples
docker compose exec backend python -m ingestion.run --dataset seed
```

- App: http://localhost:3000  ·  API docs: http://localhost:8000/docs  ·  MLflow: http://localhost:5000
- Run the checks: `make test` · `make lint` · `make sec` · `make eval`

To use real models later, set `USE_MOCKS=false` and add keys — see **[GOLIVE.md](./GOLIVE.md)** (generated at the end of the build).

## Live deployment

| Component | Host | URL |
|---|---|---|
| Frontend | Vercel (Hobby) | <https://data-chat-seven.vercel.app> |
| Backend | Render (free) | <https://datachat-api-wmpd.onrender.com> |
| Database | Neon (Postgres 16 + pgvector) | — |
| Cache / rate limit | Upstash Redis | — |
| Model | Groq `llama-3.3-70b-versatile` | — |

**Total cost: $0/month.** Every component is a permanent free tier.

- **Provider choice.** Groq serves the demo rather than the self-hosted Ollama, on
  purpose: a public URL has to answer when my PC is off, and a quick Cloudflare
  tunnel changes hostname on every restart. Ollama is the same port behind the
  same router and is one env flag away — see [GOLIVE.md](./GOLIVE.md).
- **Cold-start caveat.** The backend sleeps after ~15 min idle and Neon scales to
  zero, so the first request after idle takes ~50s and the UI shows a "waking"
  state. A keep-warm ping every 12 minutes mitigates it. Durable LangGraph
  checkpoints mean an in-flight human-approval step survives the sleep. This is a
  documented trade-off of a genuinely $0 deploy, not a defect.

## What I learned / engineering highlights

<!-- 👉 YOUR WORDS. Pick the 2–3 hardest things and say what you learned. Prompts: -->
<!--   • Circuit breaker + fallback over flaky free LLM APIs — what surprised you? -->
<!--   • Why execution-accuracy eval beats string-matching SQL. -->
<!--   • LangGraph durable state + HITL surviving cold starts. -->
<!--   • Defence in depth: guardrail AST *and* a read-only DB role. -->

- **Resilience over free APIs:** a per-provider circuit breaker with Gemini→Groq fallback turns flaky free tiers into a dependable service.
- **Safety as architecture:** an AST guardrail chain plus a read-only least-privilege role means no unsafe SQL can execute even if a layer is bypassed.
- **Evaluation you can trust:** execution-accuracy scoring (result-set equality) gates regressions in CI.
- **Durable agent state:** LangGraph checkpoints let a human-in-the-loop pause survive reloads and cold starts.

## What data it answers from

Three datasets ship, selectable at ingestion (`--dataset seed|wdi|owid`). The live
demo runs `seed`.

| Dataset | Source | Contents |
|---|---|---|
| `seed` | bundled fixture | The union of the two below — keyless local dev and the deployed demo |
| `wdi` | [World Bank API](https://api.worldbank.org/v2) (live fetch) | 15 countries × GDP per capita, population, life expectancy × 2022 |
| `owid` | [Our World in Data](https://github.com/owid/co2-data) | Same 15 countries × CO₂ total / per capita / global share × 2021–2022 |

Four tables: `countries`, `wdi_indicators`, `wdi_values`, `owid_co2`.

**The slice is small on purpose.** Neon's free tier is 0.5 GB, and the point of
the project is retrieval quality and evaluation, not corpus size. It is real data
from real sources — not synthetic — and everything the agent claims is traceable
to a row you can download as CSV.

**Scaling it is a config change, not a rewrite.** The World Bank API exposes on the
order of a thousand indicators for ~200 countries; widening means adding entries
to `_INDICATORS` and a matching semantic definition. Any new source is a
`DatasetConnector` — `name` plus `async fetch() -> RawDataset` — alongside
`world_bank.py` and `owid.py`, with no change to the agent, the guardrail or the API.

## Where the RAG is

Retrieval does **not** fetch answers. It fetches the *schema* the model needs to
write correct SQL, which is what keeps the LLM from inventing column names.

```
question ──embed──> pgvector cosine top-k ──> only the relevant slice of:
                                                • table + column descriptions
                                                • units, synonyms
                                                • few-shot Q→SQL examples
                                              ──> SQL-generation prompt
```

- **Indexed:** each semantic table, each column, and each few-shot example, embedded
  at ingestion time (`ingestion/steps.py`)
- **Retrieved:** cosine top-k over `<=>` with an HNSW index (`catalog/pgvector.py`)
- **Used by:** the `retrieve` node, before `plan` and `generate_sql`

**Why this reduces LLM usage rather than adding to it:** the model never receives
the whole schema, only the top-k slice, so prompts stay small and the surface for
hallucinated columns shrinks. On top of that, an exact-match answer cache replays
repeat questions in ~80 ms with **zero** model calls, and embeddings are computed
once at ingestion — a query costs exactly one embedding call.

The curated part matters: indicator *names, units and descriptions* are written by
hand in `ingestion/definitions.py` rather than fetched, so an upstream label change
cannot alter the grounding surface. That is a supply-chain path straight into the
prompt, closed deliberately.

## Evaluation

### What produced these numbers

Golden set: **26 cases — 21 answerable + 5 that should be refused** (out-of-scope
country, indicators we don't carry, an ambiguous question, a year beyond the data).
No golden question duplicates a few-shot example; a test enforces that, because a
duplicated question measures copying, not reasoning.

Measured at `temperature=0` against the `seed` dataset. Reproduce with
`make eval-real`. Baselines are committed per provider in
[`backend/eval_baseline.json`](backend/eval_baseline.json) — execution accuracy is
as much a property of the model as of the pipeline, so one blended number across
providers would mean nothing.

| Metric | **Groq `llama-3.3-70b-versatile`** *(deployed)* | Ollama `qwen2.5:7b-instruct` *(self-hosted)* | n |
|---|---:|---:|---:|
| Execution accuracy | **0.810** | 0.667 | 21 |
| Refusal accuracy | **0.80** | 0.80 | 5 |
| SQL valid rate | **0.952** | 0.952 | 21 |
| Explanation faithfulness | **0.881** | 0.857 | 21 |

<sub>The left column is what the live demo runs. The right is the same set against
a self-hosted 7B, kept so the Ollama path stays gated too — the 14-point gap is
the cost of running on your own GPU, measured rather than guessed.
An earlier README showed 0.80 for a 5-case set, one of whose questions was a
verbatim few-shot example; both problems are fixed and the set is now 26 cases
with a test that fails the build if leakage returns.
Known scoring artifact: result-set equality is strict, so an answer returning
country *names* where the gold used ISO codes counts as a miss despite being
substantively right — that is 1 of the 4 Groq misses.</sub>

### How it is gated

Two tiers, because the published number and the per-PR gate cannot come from the
same run — one needs a real model, the other has to be free and deterministic.

| Tier | Command | Runs in CI | Gates |
|---|---|---|---|
| Pipeline | `make eval` | yes, every PR | Graph, retrieval, guardrail, execution and the scorers, with a scripted LLM holding model quality constant. Must score exactly 1.00. |
| Quality | `make eval-real` | no (needs a GPU or keys) | Real-model execution accuracy against `backend/eval_baseline.json`, tolerance **0.05** |

Tolerance rationale: one answerable case is worth 1/21 = 0.048, so 0.05 absorbs a
single case flipping and blocks two. Baselines are measured and committed, never
hand-written.

### Answer-cache latency

End-to-end through the containerised stack (`docker compose up`), real model, five
distinct questions asked cold then repeated:

| Path | Latency | SSE frames |
|---|---:|---:|
| Cold (full agent chain) | 987–1569 ms | 15–16 |
| Cached (exact-match replay) | 77–87 ms | 6–7 |

<sub>Conditions: local Ollama with `qwen2.5:7b-instruct` already resident in VRAM,
Postgres and Redis on the same host. A cold model load or a free-tier cold start
adds tens of seconds to the first number and does not affect the second — so treat
this as the steady-state ratio (~15–20×), not a cold-boot claim.</sub>

## Testing, observability & security

- **Testing** — unit + integration (≥80% on core), agent-eval golden set, Playwright smoke; full matrix in CI. See [ImplementationPlan.md](./ImplementationPlan.md).
- **Observability (MLflow)** — 100% of runs traced (spans, tokens, latency, provider, prompt version) + a versioned prompt registry. See [TechSpec §8](./TechSpec.md).
- **Security (OWASP)** — mapped and **tested** against the **LLM Top 10 (2025)** and **Agentic Top 10 (2026)**: prompt-injection corpus, least-privilege tools, read-only execution, rate limits, bounded loops. See [ImplementationPlan §11](./ImplementationPlan.md).

## Documentation

**Start here:** [**FLOW.md**](./FLOW.md) — how a question becomes an answer, end to end, with the trust boundaries marked. · [LEARN.md](./LEARN.md) — what changed and why, with the alternatives that were rejected.

[PRD](./PRD.md) · [TechSpec](./TechSpec.md) · [AppFlow](./AppFlow.md) · [Design](./Design.md) · [Schema](./Schema.md) · [ImplementationPlan](./ImplementationPlan.md) · [Tracker](./Tracker.md) · [Rules](./Rules.md) · [Security (OWASP matrix)](./SECURITY.md) · [Go-live checklist](./GOLIVE.md) · [Deploy walkthrough](./DEPLOY.md)

## License

MIT — see [LICENSE](./LICENSE).
