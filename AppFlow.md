# AppFlow — DataChat

> **Application Flow** — end-to-end journeys and lifecycles as sequence diagrams.
> Reads alongside [TechSpec](./TechSpec.md) (§4 API, §5 agent) and [Design](./Design.md) (classes).

---

## 1. Journeys at a glance

1. **Ask → grounded answer** (happy path, streaming).
2. **HITL — approve/edit SQL** before execution.
3. **HITL — clarify** an ambiguous question.
4. **RAG retrieval** (schema + few-shot grounding).
5. **Resilience** — retry → circuit breaker → provider fallback.
6. **Self-repair loop** on a bad query.
7. **Cold-start / keep-warm** (free-tier reality).
8. **Ingestion** (offline).
9. **Evaluation** (CI gate).

Legend: **FE** Next.js · **BFF** API gateway · **ORCH** LangGraph orchestrator · **SEM** semantic layer · **LLM** provider gateway · **GUARD** SQL guardrail+executor · **PG** Postgres · **CP** checkpointer · **MLF** MLflow.

## 2. Happy path — ask → streamed answer

```mermaid
sequenceDiagram
  autonumber
  actor U as User
  participant FE
  participant BFF
  participant ORCH
  participant SEM
  participant LLM
  participant GUARD
  participant PG as Postgres (RO)
  participant MLF

  U->>FE: type question
  FE->>BFF: POST /api/v1/chat (SSE open)
  BFF->>BFF: validate input, rate-limit, X-Request-ID
  BFF->>ORCH: run(question, conversation_id)
  ORCH->>MLF: start trace
  ORCH->>SEM: retrieve_context(question)
  SEM->>PG: pgvector top-k (schema + examples)
  SEM-->>ORCH: RetrievedContext
  ORCH-->>FE: event: status {stage:"planning"}
  ORCH->>LLM: plan + generate_sql (grounded prompt)
  LLM-->>ORCH: candidate_sql
  ORCH-->>FE: event: sql {sql}
  ORCH->>GUARD: validate(sql)
  GUARD-->>ORCH: ValidationResult(ok)
  ORCH->>GUARD: execute(sql)  %% read-only role, timeout, row cap
  GUARD->>PG: SELECT ...
  PG-->>GUARD: rows
  GUARD-->>ORCH: ExecutionResult(rows)
  ORCH-->>FE: event: rows {columns, rows}
  ORCH->>ORCH: verify(results)
  ORCH->>LLM: explain(rows) [stream]
  LLM-->>ORCH: explanation tokens
  ORCH-->>FE: event: explanation_delta (streamed)
  ORCH->>ORCH: visualize -> chart_spec
  ORCH-->>FE: event: chart_spec {vega-lite}
  ORCH->>CP: checkpoint each step
  ORCH->>MLF: end trace (latency, tokens, prompt versions)
  ORCH-->>FE: event: done {trace_id}
  FE-->>U: render prose + table + chart
```

## 3. HITL — approve / edit SQL

Interrupt happens **after** the guardrail passes but **before** execution, so a human sees exactly what will run.

```mermaid
sequenceDiagram
  autonumber
  actor U as User
  participant FE
  participant BFF
  participant ORCH
  participant CP as Checkpointer
  participant GUARD

  ORCH->>GUARD: validate(sql) -> ok
  ORCH->>CP: checkpoint (state before execute)
  ORCH-->>FE: event: awaiting_approval {run_id, sql}
  Note over ORCH: interrupt() — graph pauses, state durable
  U->>FE: Approve / Edit / Reject
  FE->>BFF: POST /chat/{run_id}/resume {decision, edited_sql?}
  BFF->>ORCH: resume(run_id, decision)
  ORCH->>CP: load checkpoint
  alt approve
    ORCH->>GUARD: execute(sql)
  else edit
    ORCH->>ORCH: candidate_sql = edited_sql -> re-validate
  else reject
    ORCH-->>FE: event: done {cancelled}
  end
```

*Why this matters:* the pause is server-side and durable — a user can close the tab, the host can sleep, and the run resumes from the checkpoint. The approval cannot be bypassed by the client (mitigates ASI09 *Human-Agent Trust Exploitation*).

## 4. HITL — clarify ambiguous question

```mermaid
sequenceDiagram
  autonumber
  actor U as User
  participant FE
  participant ORCH
  participant LLM
  ORCH->>LLM: understand(question, history)
  LLM-->>ORCH: ambiguity {options:["GDP total","GDP per capita"]}
  ORCH-->>FE: event: awaiting_approval {type:"clarify", options}
  U->>FE: pick "GDP per capita"
  FE->>ORCH: resume(run_id, {clarification})
  ORCH->>ORCH: continue -> retrieve_context ...
```

## 5. RAG retrieval (grounding)

```mermaid
sequenceDiagram
  autonumber
  participant ORCH
  participant SEM
  participant EMB as EmbeddingProvider
  participant PG as pgvector
  ORCH->>SEM: retrieve_context(question)
  SEM->>EMB: embed(question)
  EMB-->>SEM: vector[768]
  SEM->>PG: ORDER BY embedding <=> :q LIMIT k  (tables)
  SEM->>PG: ORDER BY embedding <=> :q LIMIT k  (few-shot examples)
  PG-->>SEM: top-k table docs + examples
  SEM-->>ORCH: RetrievedContext(schema_subset, examples)
```

Only the retrieved subset enters the SQL-gen prompt — small context, narrower surface, fewer hallucinations.

## 6. Resilience — retry → circuit breaker → fallback

```mermaid
sequenceDiagram
  autonumber
  participant ORCH
  participant GW as LLM Gateway
  participant CB as CircuitBreaker
  participant G as Gemini
  participant Q as Groq
  participant MLF

  ORCH->>GW: complete(request)
  GW->>CB: state(Gemini)?
  alt breaker CLOSED
    GW->>G: call (timeout)
    alt 200
      G-->>GW: completion
    else 429 / 5xx
      G-->>GW: error
      GW->>GW: retry w/ backoff (capped)
      GW->>CB: record failure
      CB->>CB: threshold -> OPEN(Gemini)
    end
  end
  alt Gemini unavailable / breaker OPEN
    GW->>CB: state(Groq)?
    GW->>Q: call
    Q-->>GW: completion (fallback)
  end
  GW->>MLF: log provider_used, attempts, breaker events
  GW-->>ORCH: completion  (or safe error if all down)
```

If **all** providers are exhausted, the user gets `event: error {code:"providers_unavailable", message:"Busy right now — try again shortly."}` — never a stack trace.

## 7. Self-repair loop

```mermaid
sequenceDiagram
  autonumber
  participant ORCH
  participant GUARD
  participant PG
  participant LLM
  ORCH->>GUARD: execute(sql)
  GUARD->>PG: SELECT ...
  PG-->>GUARD: error "column x does not exist"
  GUARD-->>ORCH: ExecutionResult(error)
  ORCH->>ORCH: verify -> repair? (attempts < MAX)
  ORCH->>LLM: generate_sql(question, schema, error_feedback)
  LLM-->>ORCH: repaired_sql
  ORCH->>GUARD: validate -> execute (retry)
  Note over ORCH: repair_attempts++ ; hard cap prevents infinite loops (ASI08)
```

## 8. Cold-start / keep-warm

```mermaid
sequenceDiagram
  autonumber
  participant PING as cron-job.org
  participant BFF
  participant PG as Neon
  actor U as User
  participant FE
  loop every ~12 min
    PING->>BFF: GET /ready
    BFF->>PG: SELECT 1 (resume compute)
    BFF-->>PING: 200
  end
  U->>FE: ask (after idle)
  FE->>BFF: POST /chat
  alt backend was asleep
    BFF-->>FE: event: status {stage:"waking"}
    FE-->>U: "Waking the server (free tier)…"
  end
  BFF->>PG: resume (sub-second)
  BFF-->>FE: normal stream continues
```

## 9. Ingestion (offline)

```mermaid
flowchart LR
  A[Fetch dataset<br/>World Bank / OWID API] --> B[Validate schema + checksum]
  B --> C[Normalize -> analytics tables]
  C --> D[Load into Postgres analytics schema]
  D --> E[Build semantic layer<br/>descriptions, synonyms, units]
  E --> F[Embed docs + few-shot -> pgvector]
  F --> G[Record dataset_version + checksum]
  G --> H{Idempotent?}
  H -- re-run --> B
```

Chain-of-Responsibility pipeline; each step is a link with a uniform `process(context)` contract (see [Design](./Design.md)).

## 10. Evaluation (CI gate)

```mermaid
sequenceDiagram
  autonumber
  participant CI as GitHub Actions
  participant EVAL
  participant ORCH
  participant PG
  participant MLF
  CI->>EVAL: pytest -m eval (on PR)
  loop each golden case
    EVAL->>ORCH: run(question)
    ORCH->>PG: execute predicted SQL
    EVAL->>PG: execute gold SQL
    EVAL->>EVAL: compare result sets -> execution_accuracy
    EVAL->>EVAL: faithfulness (LLM-judge), guardrail pass
  end
  EVAL->>MLF: log run + metrics
  EVAL-->>CI: pass/fail vs baseline threshold
  CI->>CI: block merge if regression
```
