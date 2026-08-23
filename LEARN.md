# LEARN — change log with reasoning

A running record of non-obvious changes: what moved, **why**, what else was
considered, and how to defend it out loud. Most recent date first; within a date,
in the order the work happened.

For *how the system works* rather than why it changed, see [FLOW.md](./FLOW.md).

---

## 2026-08-23 — System design interview pack (HLD, LLD, the questions that follow), and a live incident found while measuring it

The full design docs already exist — [TechSpec](./TechSpec.md), [Design](./Design.md),
[Schema](./Schema.md), [AppFlow](./AppFlow.md), [FLOW.md](./FLOW.md). This section is
different on purpose: it's the **five-minute verbal version** of those docs, shaped
the way a system-design interview actually runs — HLD first, LLD on request, then
the follow-up questions an interviewer reaches for on a project like this one.
Researched against current (2026) system-design and GenAI-interview guidance, not
guessed.

### High-level design — the whiteboard version

**Problem in one line:** turn a plain-English question into a *safe, grounded,
verified* SQL analysis over curated open data — an agent (plan → generate →
guardrail → execute → verify → repair → explain), not a single prompt.

**Requirements, stated the way an interviewer wants them stated:**
- Functional: NL → SQL → executed rows → grounded prose + chart, streamed; HITL
  approve/edit and clarify; conversation memory.
- Non-functional, with numbers, not adjectives: first token ≤ ~2s warm, p95 ≤ ~8s;
  cold-start recovery ≤ ~60s with no state loss; $0/month (see [TechSpec §11](./TechSpec.md)
  for the full free-tier budget); ≥80% unit coverage on domain/application; 100%
  of runs traced.
- **Explicitly out of scope, stated up front** — see the [scope section](#scope--what-a-strong-candidate-declares-and-why)
  below; this is the part candidates under-invest in and it is scored.

**Component diagram (condensed from [TechSpec §2](./TechSpec.md#2-architecture)):**

```
Next.js UI (Vercel) --HTTPS/SSE--> FastAPI BFF (Render, one process)
                                      |
                          rate-limit + idempotency (Redis)
                                      |
                              LangGraph orchestrator
                         /            |              \
              Semantic layer    SQL guardrail    LLM provider gateway
              (pgvector RAG)    + RO executor     (Adapter+Strategy+
                    |                 |             Decorator+Breaker)
                    +--------> Postgres (Neon) <----------+
                    (app schema rw / analytics schema ro)      Groq/Gemini (httpx)
```

**Why a modular monolith, not microservices** — the question every interviewer
asks: the free tier cannot run eight always-on services, and networking a young
system into services you don't yet need is the *distributed monolith*
anti-pattern — all the ops cost, none of the payoff. So: **one deployable
process**, internal modules with **microservice-grade boundaries** (clean
architecture, ports, dependency inversion) so any module — the LLM gateway, the
guardrail, the semantic layer — could be extracted to its own service later
**without touching the domain code**. Say it exactly like that; it's the
"microservice-ready, not microservice-burdened" line from [TechSpec §2](./TechSpec.md#2-architecture).

**The one flow worth walking end to end** (pick this if asked for depth — it's
the one with the interesting decisions in it): ask → retrieve schema context
(RAG) → plan → generate SQL → **guardrail** (parse the AST, reject writes /
multi-statement / non-allow-listed tables / missing `LIMIT`) → execute against a
**separate read-only DB role**, not just an app-level check → verify the shape →
on failure, **bounded repair** (≤2 attempts) using the DB error as feedback → explain
→ chart → stream. Full sequence diagram: [AppFlow §2](./AppFlow.md#2-happy-path--ask--streamed-answer).

### Low-level design — the "now go deeper" version

Pull this out only if asked; it's [Design.md](./Design.md) condensed to the parts
that come up.

- **Dependency rule:** `interface → application → domain ← infrastructure`. Domain
  imports nothing outward — no FastAPI, no SQLAlchemy, no LangGraph. Adapters
  implement domain **ports** (`LLMProvider`, `SchemaCatalog`, `SqlValidator`,
  `QueryExecutor`, `Cache`). This is what makes "what if Groq disappears" a
  one-adapter change instead of a rewrite — see the incident below, where that's
  exactly what happened.
- **LLM Provider Gateway** = Adapter (one class per vendor) + Strategy
  (`ProviderRouter` picks one) + Decorator (retry → cache → trace → circuit-breaker
  wraps each adapter) + Circuit Breaker (opens after `breaker_fail_threshold=5`
  consecutive failures, half-opens to probe). Adding a vendor is a new adapter
  class + one config line — **OCP**, not a router rewrite.
- **SQL guardrail** = Chain of Responsibility. Each rule (`SingleStatementRule`,
  `ReadOnlyRule`, `TableAllowlistRule`, `NoSystemCatalogRule`, `MandatoryLimitRule`)
  parses the `sqlglot` AST independently and the chain short-circuits on first
  failure. This is layer 1 of 2 — layer 2 is the DB role itself (§ below) —
  **defence in depth**, either alone would suffice.
- **Agent nodes** = Template Method (`BaseNode.__call__` fixes: open trace span →
  `_run` → validate output as untrusted (LLM05) → checkpoint; subclasses fill only
  `_run`, so no node can skip tracing or validation) built by a Factory.
- **Data isolation, the security spine:** two schemas, two roles. `app` (rw,
  conversations/runs/semantic layer/eval) and `analytics` (the open datasets). The
  executor connects as `datachat_exec`, a **separate login role** with
  `default_transaction_read_only=on`, `search_path=analytics`, and a 5s
  `statement_timeout` — bulkhead pattern. Even a fully bypassed guardrail chain
  hits a database that physically cannot write or cross schemas. See
  [Schema §5](./Schema.md#5-read-only-role--execution-safety-the-security-spine).
- **State & durability:** LangGraph's `PostgresSaver` checkpoints after every node,
  so a HITL interrupt or a cold start resumes from exactly where it left off — no
  in-memory state anywhere on the request path (**NFR-10**, stateless BFF).

### The questions that follow a design like this

Researched against 2026 GenAI/agentic system-design interview guides (PracHub,
System Design Handbook, KDnuggets, DesignGurus, and the Agentic AI interview
literature) — these are the categories interviewers reach for once the HLD is on
the board, mapped to how *this* project actually answers them, gaps included.
Sources at the bottom.

#### "How would you limit token usage?"

Answer with what's actually built, then name the gap — that's the senior-signal
move, not reciting a generic list:

- **Retrieval-limited context** (already built): the prompt gets top-*k*
  pgvector-retrieved schema/examples, not the whole semantic layer — this is the
  project's actual RAG component and it's a token-budget decision as much as a
  quality one ([TechSpec §7](./TechSpec.md#7-semantic-layer--retrieval-rag-to-sql)).
- **Exact-match answer cache** (already built): `cache:answer:{sha256(question)}`
  in Redis, 1h TTL — a cache hit burns **zero** tokens and answers in ~80ms
  instead of running the graph at all ([Schema §7](./Schema.md#7-redis-upstash-key-patterns--ttls)).
- **Bounded loops** (already built): `max_repair_attempts=2` caps the
  generate→guardrail→repair cycle, so a stubborn bad query can't silently burn an
  unbounded number of calls ([config.py](../backend/app/config.py)).
- **Global + per-session quotas** (already built): `global_daily_quota=1000`,
  `rate_limit_per_min=20`, enforced in Redis before the graph ever runs — this is
  the layer research calls "gateway-level budget enforcement," here implemented
  with token-bucket counters rather than a managed API gateway product.
- **Circuit breaker** (already built): stops calling a provider that's already
  failing rather than retrying into a wall.
- **The honest gap:** `LLMRequest.max_tokens` exists in the domain model
  ([entities.py](../backend/app/domain/entities.py)) but **no node ever sets it** —
  every call is provider-default length, uncapped. That's a real, one-line fix
  (`max_tokens=200` on `explain`, tighter on `classify`/`verify`) that was never
  prioritized because free-tier daily *request* caps were the binding constraint,
  not per-call *token* cost. Naming this unprompted is exactly the "propose what
  you'd add, and why it wasn't done yet" move the interview guides call out as a
  staff-level signal, not a weakness to hide.
- **Not built, and worth naming as "next":** semantic caching (today's cache is
  exact-match only — a paraphrase misses), and cost/complexity-based model
  routing (provider order is fixed by quota headroom, not per-request routed by
  question difficulty).

#### "How would this scale to a million users?"

Bottleneck framing an interviewer wants to hear: it isn't CPU or memory, it's
**LLM inference throughput and per-provider rate limits** — a server at 20% CPU
can still be maxed out because every request is blocked on a 30s provider call
capped at N requests/day. Given that:

- The backend is **stateless by design** (all state in Postgres/Redis via the
  checkpointer), so horizontally scaling the process is "in principle, not yet
  needed" — true today, and defensible because it wasn't retrofitted.
- The real ceiling isn't the app, it's the **free-tier LLM/DB quotas** ([TechSpec §11](./TechSpec.md#11-0-cost-table-proof)).
  At real scale the fix isn't "add servers," it's **provider tiers with paid
  throughput + prompt caching on the shared system prompt** (the research is
  explicit that a 5k-token system prompt resent on every call is the usual hidden
  cost driver) + **model routing by complexity** (small/cheap model for
  `classify`/`verify`, large model reserved for `generate_sql`/`explain`).
- Neon and Upstash both scale-to-zero on the free tier; at real traffic that
  setting is the first thing to turn off, not a code change.

#### "What happens when a provider goes down?"

The designed answer: circuit breaker opens after `breaker_fail_threshold`
consecutive failures, `ProviderRouter` fails over to the next configured
provider, retries respect `Retry-After`. **The honest answer, proven true this
session:** see the incident below — production currently has exactly **one**
provider registered, so "failover" has never actually been exercised in prod. A
good interviewer will ask "have you *tested* the failover path in production, or
only in code?" — the honest answer here is "no," and that's a stronger answer
than pretending otherwise.

#### Security — "this looks like SQL injection, why isn't it solved the same way?"

A favorite probe, and this project has a real answer: SQL injection was solved
architecturally — parameterized queries put a hard boundary between code and
data that the database itself enforces. **No equivalent exists for prompts** —
the model has to interpret natural language to work at all, so you cannot
parameterize your way out of it. That's why this system leans on **layers the
model can't talk its way around**: an AST guardrail that never trusts the model's
claim that its own SQL is safe, and underneath that, a **database role that
physically cannot write**, independent of anything the LLM believes about itself.
Prompt injection specifically is scoped down, not solved: the web fallback treats
every search snippet as untrusted, parses the model's extraction back into a
strict schema, and drops any row that cites a source index the model wasn't
actually shown — the parser is the control, the prompt is just a request (see
`web_table@v1`, above, 2026-08-11 entry).

#### Evaluation — "how do you know the answer is even right?"

Two-tier, because "the eval passed" and "the model is good" are different claims
that must never share one number:

- **Tier 1 (`pytest -m eval`, CI, every push):** the real graph, real pgvector,
  real read-only executor — but a *scripted* LLM that returns the gold SQL. Model
  quality is pinned at perfect on purpose, so this number moves only when the
  **pipeline** breaks, and it's calibrated to fail (verified by mutation, see
  2026-08-11 entry).
- **Tier 2 (`pytest -m eval_real`, opt-in):** the same 26-case golden set (21
  answerable + 5 refusal) against the real deployed provider, scored on four axes
  that are deliberately never blended into one number: `execution_accuracy`
  (BIRD-style result-set equality — different SQL, same rows, still correct),
  `refusal_accuracy` (did it decline the 5 out-of-scope cases instead of
  hallucinating an answer — the failure mode that actually hurts a user),
  `sql_valid_rate` (parses + passes the guardrail), and **`faithfulness`**
  (LLM-as-judge, 0–1, grading whether the prose explanation is *supported by the
  returned rows* — not whether it's fluent).
- The tolerance (0.05) is sized by set granularity, not model jitter — at 21
  answerable cases, one flipped case moves the score by 1/21 ≈ 0.048, so a
  tighter gate fires on noise.

#### Scope — what a strong candidate declares, and why

Research consensus (System Design Handbook, Exponent, staff-level interview
guides) is blunt about this: **stating exclusions explicitly, early, with a
reason, is scored** — "out of scope" left implicit is where solid engineers
quietly lose points, and naming a tradeoff you *chose against* signals more
seniority than naming the one you built. This project already has a ready-made
answer — [PRD §3](./PRD.md#3-goals--non-goals), verbatim, because it was written
before any code, not rationalized after:

> No write/DDL, ever. No user-uploaded datasets in v1. No multi-tenant SaaS or
> billing. No model fine-tuning — grounding is retrieval, not weights. Not a
> general chatbot — out-of-scope questions are refused, not guessed at. No
> multi-agent mesh across network boundaries — sub-steps are LangGraph subgraphs
> in one process, which structurally removes an entire OWASP Agentic category
> (ASI07, insecure inter-agent comms) rather than mitigating it.

The template worth reusing out loud, straight from the research: **declare it**
("write/DDL is out of scope for this design"), **justify it** ("a read-only agent
has a fundamentally smaller blast radius, and that's the property this whole
design optimizes for"), **leave the door open** ("if we have time, I can sketch
how a write-capable version would add an approval workflow on top of the same
guardrail chain"). Don't just name the technology you excluded — name what
building it would have cost and what it would have put at risk instead.

### A live incident, found while writing this section

Measuring the faithfulness number below required a real run against the deployed
provider — and it failed immediately, not with a rate limit but with `client
error 404`. Groq's model catalog no longer contains **any** Llama model,
including `llama-3.3-70b-versatile`, the one this codebase had hardcoded as the
`GroqAdapter` default since the project began. Direct request to
`api.groq.com/openai/v1/chat/completions` confirmed it: `"model_not_found"`.

**This meant the live public demo was down for every request**, not just the
eval — confirmed by curling the deployed endpoint directly and getting back
`event: error / providers_unavailable` instead of an answer. And it surfaced the
gap named above under "what happens when a provider goes down": `Container.llm()`
([container.py](../backend/app/container.py)) only registers a provider whose key
is present, and `render.yaml` deliberately declares **only** `DATACHAT_GROQ_API_KEY`
in production (Gemini is documented as "add in the dashboard when you actually
want it" — never done). So the circuit-breaker/fallback machinery that's real and
tested in code had **nothing to fall back to** in production. One dead model name
was a full outage, not a degraded mode — exactly the single-point-of-failure this
design is supposed to route around, undone by a deploy-time config choice the
design docs never flagged as a risk.

**Fix:** swapped the `GroqAdapter` default to `openai/gpt-oss-120b` — the closest
available flagship model on Groq's current lineup (131k context, comparable
class to the retired 70B Llama) — verified against Groq's live `/models` list
rather than guessed. Re-measured against the golden set (below) before
committing, per this repo's own rule: "swapping providers is a deliberate act
that needs its own measurement, not a silent pass or fail" (`eval_baseline.json`).

**Still open, not fixed here — a product/ops decision, not a code fix:** add a
second provider key (Gemini, per the original TechSpec design) to production so
failover is actually exercised, not just implemented. Logged rather than done
silently, matching this repo's habit of naming gaps instead of hiding them
(see `Tracker.md` → Known open items).

### Settled: faithfulness on the golden set

Measured via `DATACHAT_EVAL_REAL=1 uv run pytest -m eval_real -s`, temperature
0.0, the full 26-case golden set (21 answerable + 5 refusal), against the
**currently deployed** provider — real graph, real pgvector catalog, real
read-only executor, real network calls, no mocks.

| Provider | execution_accuracy | refusal_accuracy | sql_valid_rate | **faithfulness** |
|---|---:|---:|---:|---:|
| **`groq/openai/gpt-oss-120b`** *(deployed now)* | 0.5238 | 1.0000 | 0.6667 | **0.6190** |
| `groq/llama-3.3-70b-versatile` *(retired by Groq, historical)* | 0.8095 | 1.0000 | 0.9524 | 0.9048 |
| `groq/qwen/qwen3.6-27b` *(rejected)* | 0.0476 | 1.0000 | 0.0476 | 0.0476 |

**Settled number: faithfulness = 0.62** (21 answerable cases, `openai/gpt-oss-120b`,
`temperature=0`, measured 2026-08-23 — full run in `eval_baseline.json`).

Reported plainly, not softened: this is a **real drop** from the 0.90 the retired
model measured, not a pipeline issue — Tier 1 (the scripted-LLM pipeline gate)
still scores a clean 1.0, so the graph, retrieval, guardrail, and scoring
machinery are all intact. The drop is the model. `qwen/qwen3.6-27b` was tried
first and rejected outright — it emits `<think>...</think>` reasoning blocks by
default, which the SQL-extraction step doesn't strip, so `sql_valid_rate`
collapsed to 0.0476 (one lucky case out of 21). `gpt-oss-120b` was the better of
the two available replacements, not a good one in absolute terms — worth a
prompt-tuning pass or a different provider entirely, logged as a follow-up
rather than fixed here.

`faithfulness` is the LLM-as-judge score from `FaithfulnessJudge`
([eval_service.py](../backend/app/application/services/eval_service.py)):
graded 0–1 per answerable case on whether every claim in the generated prose
explanation is supported by the actual returned rows (not whether it's
fluent, not whether the SQL was right — a query can be wrong *and* the
resulting sentence can still be faithful to the wrong rows it saw), then
averaged over the 21 answerable cases.

**Sources consulted for this section:** [PracHub GenAI & LLM System Design
Interview Guide](https://prachub.com/resources/genai-llm-system-design-interview-guide-2026) ·
[System Design Handbook — Generative AI System Design Interview](https://www.systemdesignhandbook.com/guides/generative-ai-system-design-interview/) ·
[System Design Handbook — LLM System Design](https://www.systemdesignhandbook.com/guides/llm-system-design/) ·
[System Design Handbook — Scale AI System Design Interview](https://www.systemdesignhandbook.com/guides/scale-ai-system-design-interview/) ·
[Redis — LLM Token Optimization](https://redis.io/blog/llm-token-optimization-speed-up-apps/) ·
[Trident Ventures — LLM Cost Control at Scale](https://tridentventures.org/blog/llm-cost-control-scale) ·
[NeuralTrust — AI Token Optimization Guide](https://neuraltrust.ai/blog/ai-token-optimization-guide) ·
[NVIDIA — Scaling LangGraph Agents in Production](https://developer.nvidia.com/blog/how-to-scale-your-langgraph-agents-in-production-from-a-single-user-to-1000-coworkers/) ·
[Cisco — Prompt Injection is the New SQL Injection](https://blogs.cisco.com/ai/prompt-injection-is-the-new-sql-injection-and-guardrails-arent-enough) ·
[The Architect's Notebook — How to Think Out Loud in a System Design Interview](https://thearchitectsnotebook.substack.com/p/system-design-insight-how-to-think) ·
[DesignGurus — LLD vs System Design Interview Questions](https://www.designgurus.io/answers/detail/difference-between-low-level-design-and-system-design-interview-questions).

---

## 2026-08-14 - CI was never green, and two production bugs

Sixteen commits. The theme: gates that reported success without checking
anything, and two defects only a real deployment could expose.

### CI had been red since the first push - and worse, silently skipping

Nobody noticed because the repo had not been pushed since 25 July. Five failures,
each hidden behind the one before it. The pipeline got further each time:
32s -> 4m18s.

**1. `uv sync` died on `readme = "../README.md"`** (`f5c0d85`). hatchling refuses a
readme outside the project directory. This is the worst kind of CI failure: it
died at dependency install, so lint, types, tests, the eval gate, bandit and
pip-audit were all *skipped* rather than passing. A pipeline that runs nothing
looks exactly like one that passes everything until you read it. Key removed - the
package is never published, so the metadata bought nothing and cost the lot.

**2. import-linter refused to start** (`11be0d4`). The "Domain is framework-free"
contract forbids *external* packages, which requires `include_external_packages`.
Without it the tool errors instead of evaluating, so the architecture contracts
were never checked at all. They pass: 3 kept, 146 files, 540 dependencies.

**3. Eleven `mypy --strict` errors** (`d4445aa`), all from code written in the
previous two days. Invisible locally because mypy is blocked on this dev box by
Windows Application Control - the reason `scripts/typecheck.sh` exists. One was a
real gap rather than a lint nit: `WebTableEvent` was never added to the
`AgentEvent` union, which is the contract the SSE layer formats against. Another
was a `# type: ignore` hiding a genuine signature error (`_rate` typed `int` while
faithfulness sums floats) - the ignore is gone and the type is right.

*Verifying this needs care:* `.dockerignore` excludes `tests/`, so running mypy in
the image checks 116 files and silently skips every test file. The tests have to be
mounted in to get the real 174.

**4. Twelve dependency advisories** (`1379d3b`). Upgraded gitpython, h2 and
langgraph-checkpoint-postgres. Three cryptography advisories are transitively
unfixable - mlflow pins `cryptography<47` - so they are ignored **by ID with the
constraint written next to them**, not by softening the step to `|| true`. An audit
that always passes tells you nothing; three named exceptions start failing again
the moment mlflow relaxes its cap.

**5. A dict row factory** (`ea3329d`), caught by the type check after the pool
change below.

### The datachat_exec password bug - and a correction I owed

Seven integration tests failed with `InvalidPasswordError` for the read-only role.
I had told Sahil this was host-specific and that CI was the reference environment.
**Both were wrong**: CI failed identically; it had just been dying at dependency
install before ever reaching those tests.

The migration was never at fault. Two separate bugs (`40caa8e`):

1. The test built its DSN with `str(url)`. **SQLAlchemy's `URL.__str__` masks the
   password as `***`**, so the tests authenticated with three literal asterisks.
   The error says "password authentication failed", which reads as a broken role or
   a broken migration - I spent real time in `0003_roles_grants` because of it. The
   sibling helper in `tests/agent_eval` passed the URL *object* and never
   stringified it, which is why the eval gate worked while these did not.

2. `ReadOnlyQueryExecutor` let a native asyncpg error escape. On the streaming path
   a driver error can surface while rows are buffered, *after* SQLAlchemy's wrapper
   has run, arriving as `asyncpg.PostgresError` rather than `DBAPIError`. The
   read-only role rejecting a `DELETE` is exactly that case - **the last line of
   defence was raising instead of returning `Err`**, so a correctly blocked write
   became an unhandled exception.

### Refusal accuracy 0.80 -> 1.00 (`da67ccf`)

One in five out-of-scope questions was answered rather than declined, which on a
public demo is a hallucination risk.

The cause was not a careless model - four of five refusal cases already declined
correctly. *"What will global CO2 per capita be in 2030?"* produced
`SUM(co2)/SUM(pop) WHERE year = 2030`, and **an aggregate over zero matching rows
returns one row containing NULL**. `row_count == 1`, so every emptiness check
concluded there was data.

Two fixes, in the order they should apply - certain and free first, probabilistic
second:

- A `scope_check` node between `retrieve` and `plan`. A country or year named in
  the question is checked against the loaded slice **before any model call**. A
  named year outside the range is a fact we hold, not a judgement to delegate. It
  also removes ~5 LLM calls and the entire repair budget from every out-of-scope
  question, which previously burned all of it to reach a wrong answer.
- `ExecutionResult.is_empty()` now treats a single all-NULL row as no data, so the
  aggregate case is caught even where the gate cannot see it. The answer cache uses
  the same check, so a non-answer can no longer be pinned and replayed.

**Deliberately conservative.** It refuses only on something positively identified
as outside the slice. Indicators are *not* checked - that vocabulary is open, and a
keyword list would refuse phrasings we do support.

**A false positive caught in testing:** the first gazetteer split a text blob on
whitespace, which shredded "united states" into "united" and "states". "states"
then matched a question about a country we *do* load and refused it. Multi-word
names now survive intact and matching is whole-word, longest-first.

Measured on the same set and model: refusal 0.80 -> 1.00, **execution accuracy
unchanged at 0.8095**. That second number is the one that matters - the gate caught
the miss without refusing anything answerable.

### Two bugs only production could show

**`stream_failed` logged nothing** (`6b2cbaf`). The handler recorded an event name
and a trace id and threw the exception away. The client is deliberately told only
"Something went wrong", so the server log is the one place the cause can live - and
it was discarding it. A production failure was undiagnosable until this was fixed,
and fixing it is what found the next one.

**The checkpointer used a single connection** (`f9b45ae`).
`AsyncPostgresSaver.from_conn_string` opens exactly one psycopg connection, and
psycopg forbids overlapping commands on one connection:

```
OperationalError: sending prepared query failed: another command is already in progress
```

The graph checkpoints after every node, so once two operations overlap the whole
SSE stream fails. **Latent before today** - adding the scope node put another
checkpoint write in each turn and widened the window enough to surface it. It would
have broken the first time two people opened the demo together, which for a public
link is a matter of when, not if. Now a pool.

*This class of bug is invisible to the local suite:* `MemorySaver` has no
connection at all, and psycopg's async path cannot run on Windows ("cannot use the
'ProactorEventLoop'"), so the Postgres checkpointer is only ever exercised in the
deployed container.

### Presentation, and honesty about the numbers

**Six verified example chips and a scope line** on the landing view. An empty text
box over a narrow corpus invites a question we cannot answer, so a first-time
visitor's first impression is a refusal. Every example was verified end to end
against the deployed backend before shipping. One is a *deliberate refusal* -
watching the system decline and say exactly why is a better signal than a sixth
question that works.

**README restructured** for a ten-second skim: demo link, GIF slot, scope-and-cost
line and the numbers table all above the first paragraph of prose, with sample size
and model named inline rather than in a footnote.

**A limitations section written from measured runs.** The part worth reading: of
the 4 answerable cases Groq misses, **3 are one scoring artifact** - the model
returns country *names* where the gold SQL used ISO codes. Strict result-set
equality marks that wrong despite being right, and arguably more readable. A
lenient scorer would report ~0.95. The strict number is published anyway, because
loosening a metric to flatter yourself is how an eval stops being worth running.

**Both provider baselines measured** (`3ae6db6`). Groq 0.810 vs self-hosted qwen2.5
7B 0.667 - the cost of self-hosting, measured rather than guessed. The gate itself
had to be fixed first: it drove a *raw* adapter, and 26 cases is ~130 back-to-back
calls, which a free tier answers with 429. It now wraps the adapter in the same
`build_resilient` stack production uses, which also makes the measurement describe
the system rather than an adapter nobody runs in isolation.

### Audit findings

- **Data attribution was missing.** `DATA-SOURCES.md` now separates the MIT code
  licence from the ~90 World Bank and Our World in Data values this public repo
  redistributes, with links to each publisher's terms and an accuracy caveat.
- **The refusal message read badly.** "15 countries, 2021, 2022" is a count and a
  range rendered as a three-item list, and the measures ran together on one line.
  Now "covering 2021-2022" with measures on separate lines.
- **Stale repo artifacts removed**: a git worktree and two merged branches, one a
  tool-generated name. Nothing lost - the worktree sat at a commit already in
  master's history with no uncommitted changes.
- Confirmed clean: no secrets in any tracked file, only `.env.example` tracked, and
  `backend/.env` and the real `deploy/Caddyfile` (tunnel token) both ignored.

### Still open

- `docs/hero.gif` and the two "YOUR WORDS" README sections - both need a human.
- Commit `6b2cbaf` is mislabeled: it contains the UI examples but its message
  describes only the logging fix, because of a `git add -A`.
- One commit message names a deleted tool-generated branch, which is a trace this
  repo is meant not to carry. Both need a history rewrite to fix.

---

## 2026-08-13 — Live

**https://data-chat-seven.vercel.app/** → **https://datachat-api-wmpd.onrender.com**

Groq on the free tier, Neon Postgres + pgvector, Upstash Redis, Vercel frontend,
keep-warm every 12 minutes. Verified in the browser: *"Which 3 countries had the
lowest life expectancy in 2022?"* → Nigeria 53.6, South Africa 62.3, India 67.7,
with the executed SQL, a Vega-Lite chart and a grounded explanation.

### Four failures, and what each really was

None of them said what it meant, which is the whole lesson.

**1. `render.yaml not found`.** The file had never been pushed. Ten commits —
including the one that created it — had been sitting local since 25 July. The
GitHub repo a recruiter would have seen was missing the web fallback, the
downloadable reports and the answer cache too.

**2. `Exited with status 127`.** Render runs `dockerCommand` through a shell, so
an inline `sh -c "a && b && c"` had its quotes passed through literally and the
shell went looking for one command named `a && b && c`. Moved to
`backend/start.sh` — no quoting ambiguity, and readable locally. Took `exec
uvicorn` and `set -e` with it, so the server gets SIGTERM directly and a failed
migration stops the container rather than serving against a half-migrated DB.

**3. `error parsing value for field "cors_origins"`.** pydantic-settings
JSON-decodes collection-typed fields at the *source*, before validators run, so a
plain `http://localhost:3000` is a JSON syntax error. Decoding off + a validator
that takes plain, comma-separated, or JSON.

**4. UI live, every request blocked.** `CORS_ORIGINS` was
`https://data-chat-seven.vercel.app/` — the trailing slash you get by copying a
URL out of a dashboard. A browser `Origin` is scheme + host + port and never has a
path, and Starlette compares exactly. The failure is one-sided and vicious: the
API still answers 200 to curl while the browser blocks it, so it reads as "the
frontend is broken" and sends you into the wrong codebase.

why fix 3 and 4 in code rather than in the runbook: both arrive by default — the
slash from copy-paste, the JSON from a type annotation nobody sees — and neither
symptom points at its cause. A note in GOLIVE.md would have been a note about a
trap rather than the removal of one.

### Earned its keep

The MLflow startup bound shipped two days earlier fired in production on the first
successful boot: `prompt_register_timed_out` after 5.0s. Without it, startup
blocks ~90s on an unreachable tracking server and Render's health check fails the
deploy. It was written for exactly this and never tested against it until now.

The `no_llm_provider_configured` guard also paid off — its *absence* from the logs
was how I confirmed the Groq key had landed, rather than discovering it later
through identical wrong answers.

### Deliberately not deployed

Ollama. A public URL must answer when the author's PC is off, and
`cloudflared tunnel --url` issues a new hostname on every restart, so every reboot
would mean editing the Render env and redeploying. It stays one env flag away for
a live demo — which is a better interview moment than a link that happens to work.

---

## 2026-08-11 — Making the evaluation honest

### The problem, stated plainly

Three things in this repo were false or misleading. All three were public.

**1. The CI "regression gate" could not fail.**
`tests/agent_eval/test_golden_eval.py` asserted:

```python
assert 0.0 <= report.execution_accuracy <= 1.0
```

That is a tautology. Worse, the job it guarded ran `MockLLMProvider`, which
returns *one hardcoded CO₂ query for every question* regardless of what was asked
(`app/infrastructure/llm/mock.py`). Measured: the CI eval scored
**execution_accuracy = 0.0** and passed. Meanwhile `EvalReport.regressed()`
existed and was never called outside unit tests.

The README said the golden set "gates every change in CI." It gated nothing.

**2. Two metric names, one number.**
`guardrail_pass_rate` and `sql_valid_rate` were computed from the identical
expression. The README printed both as 1.00, which reads as two independent
confirmations of safety. It was one measurement counted twice.

**3. Train/test leakage in the golden set.**
`golden_set.py` claimed "questions are distinct from the few-shot examples to
avoid train/test leakage." One of its five questions — *"What was Germany's CO2
per capita in 2022?"* — was a **verbatim** few-shot example from
`ingestion/definitions.py`. The retriever puts that example straight into the
prompt for that question, so the model copies the answer. It passed, and inflated
the published score.

### What changed

| Area | Before | After |
|---|---|---|
| CI gate | `assert 0.0 <= acc <= 1.0` | Scripted-LLM pipeline gate, must score exactly 1.00 |
| Quality gate | none | `make eval-real` vs committed `eval_baseline.json`, tolerance 0.05 |
| Golden set | 5 cases, 1 leaked | 26 cases (21 answerable + 5 refusal), leakage blocked by a test |
| Refusals | not represented | Scored separately as `refusal_accuracy` |
| `guardrail_pass_rate` | duplicate of `sql_valid_rate` | deleted |
| Published accuracy | 0.80 | 0.667 — measured, harder set, no leakage |

### Decision 1 — two tiers, not one gate

The published quality number and the per-PR gate cannot come from the same run.
One needs a real model (GPU or paid keys, minutes per run, mild nondeterminism);
the other must be free and deterministic on every pull request. Forcing them
together is what produced the fake gate in the first place.

- **Tier 1, `pytest -m eval`** — real graph, real pgvector catalog, real read-only
  executor, but a `GoldScriptedLLM` that returns the gold SQL for each question.
  Model quality is pinned at perfect, so the score moves only when the *pipeline*
  moves. Must be exactly 1.00. Free, runs in CI.
- **Tier 2, `pytest -m eval_real`** — same set, real provider, compared against a
  committed baseline. Opt-in via `DATACHAT_EVAL_REAL=1`.

**Alternatives considered.** Gate CI on a real model — needs paid keys and
tolerates flakiness, and CI has no GPU. Publish the mock number — meaningless, as
demonstrated. Keep one blended gate — that is the status quo that failed.

**Defence in two sentences:** the CI gate holds model quality constant so it
measures the pipeline, and it is calibrated to fail — I verified that by mutating
the scripted SQL and watching it drop off 1.00. The model-quality number comes
from a separate, opt-in run against a committed baseline, so neither number
pretends to be the other.

### Decision 2 — refusals scored separately, not blended in

Five cases have no correct answer in the governed data. Result-set equality
against a null gold is meaningless, so they are scored on whether the agent
*declined*: `refusal_accuracy`, over the refusal cases only. Execution accuracy is
computed over answerable cases only.

**Why it matters:** an agent that confidently answers an unanswerable question is
the failure mode that actually hurts a user, and blending refusals into one
average makes a perfect refusal and a wrong answer indistinguishable.

**Alternative considered:** score refusals as `execution_accuracy = 0`. Simpler,
but it destroys exactly the signal the negative cases exist to produce.

A refusal is detected as: an error/guardrail dead-end, a clarify interrupt (the
run pauses with no execution), or a query that ran and matched nothing.

### Decision 3 — regression tolerance of 0.05

A golden set is granular. With 21 answerable cases, one case flipping moves the
score by **1/21 = 0.048**. So:

- tolerance **< 0.048** → any single flaky case fails the build. That is noise, not regression.
- tolerance **0.05** → absorbs exactly one case, blocks two (0.095).
- tolerance **> 0.095** → stops catching real slides.

Sampling variance is not the driver — `temperature` is 0.0 — so the tolerance is
sized by set granularity, not by model jitter. If the set grows, revisit it: at 50
answerable cases one case is 0.02 and the tolerance should tighten.

### Decision 4 — deleted `guardrail_pass_rate` rather than inventing a difference

It measured the same thing as `sql_valid_rate`. The options were to fabricate a
distinction or to delete one name. Since nothing unsafe can execute by
construction (AST guardrail *and* a read-only role), there is no second number to
report; a genuinely different metric would need a fault-injection setup that does
not exist. Deleted. The `eval_runs.guardrail_pass_rate` DB column is retained and
now receives `sql_valid_rate` — renaming it needs a migration and buys nothing.

### The number went down. That is the point.

0.80 → 0.667. Nothing regressed. The old figure came from five easy cases, one of
which the model could copy out of its own prompt. The new figure comes from 26
cases spanning lookups, aggregations, rankings, joins, group-by, two-year
time-series and out-of-scope refusals, with leakage blocked by a test.

A number that only moves up is not a measurement.

### Unplanned fix found along the way

`OpenAICompatibleAdapter` sent `Authorization: Bearer {key}` unconditionally. With
no key configured — the default (`ollama_api_key = ""`) — httpx rejects the bare
`"Bearer "` as an illegal header value, and the failure surfaced as
`transport error: Illegal header value b'Bearer '` rather than a config problem.
This blocks a keyless local Ollama, which is the documented go-live path in
`GOLIVE.md`. The header is now omitted when there is no key; the tunnel still
enforces auth in production.

### Verification performed

- 228 unit/security tests pass (was 219; 9 added).
- Tier-1 gate passes against live Postgres, and **fails when mutated** — the
  scripted SQL was deliberately corrupted, the gate reported
  `pipeline regression: [...]` and exited 1. Reverted after.
- Real-model measurement run twice: 5-case set reproduced the old 0.80 exactly
  (confirming the previous figure was honest, just easy), 26-case set produced the
  new baseline.
- 7 integration tests fail locally on `datachat_exec` password auth. Confirmed
  pre-existing by stashing all changes and re-running on a clean tree: **same 7
  failures**. Environmental (throwaway Postgres volume), not caused by this work.

---

## 2026-08-11 — Container verified end to end (C1)

Both images build clean. The full five-service stack (`postgres`, `redis`,
`backend`, `frontend`, `mlflow`) comes up from a wiped volume, auto-migrates and
auto-seeds on boot, and `/ready` returns 200.

**SSE verified against the real model, not mocks.** The container ran with
`USE_MOCKS=false`, Ollama enabled, `qwen2.5:7b-instruct`. `POST /api/v1/chat`
returns `content-type: text/event-stream` and streams
`status → plan → sql → rows → explanation_delta → done` — 15 frames for a cold
answer, 6–7 for a cache replay. Answers were correct against the seed slice
(top-5 CO₂ per capita: Qatar, Saudi Arabia, Australia, US, Canada; highest-average
region: Middle East & North Africa at 28.15).

Live confirmation of a known scoring artifact: the agent returned country *names*
where the golden gold SQL uses ISO codes — substantively right, scored as a miss.
That is exactly the case flagged in the `notes` field of that golden case.

Note the route prefix is `/api/v1/chat`, not `/chat`.

### Cache figure restored, corrected

The old "~20–40 s → ~70 ms" had no artifact behind it and was cut. It is now
measured and back: **987–1569 ms cold → 77–87 ms cached** across five distinct
questions, roughly 15–20×. The old *cached* number (~70 ms) was accurate; the old
*cold* number was not reproducible on a warm local model — it likely came from a
cold-start context that includes model load. The README now states the conditions
so the ratio can't be mistaken for a cold-boot claim.

### Still open

- **7 integration tests fail on this host** (`test_readonly_role.py`,
  `test_executor.py`), all on `InvalidPasswordError` for `datachat_exec`. Proven
  pre-existing: stashing every change and re-running on a clean tree reproduces the
  same 7. Also fails in isolation, so it is not test-ordering, and it survives a
  wiped volume. The role *is* created with a real SCRAM verifier — checked
  `pg_authid`, so this is **not** an empty-password hole — but the verifier does
  not match what the host-side test connects with. Suspect the
  `set_config('datachat.exec_pw', ...)` → `current_setting(...)` handoff in
  `0003_roles_grants` does not resolve as intended when alembic is driven from the
  host. CI (Linux, container-run migrations) is the reference environment. Worth
  its own session; untouched here.
- Backend image is 3.16GB; ~1.13GB is a duplicated venv layer caused by
  `chown -R` after `COPY`, ~470MB is MLflow's scientific stack, and dev tools
  (`pytest`, `mypy`, `ruff`, `bandit`) ship to production because `uv sync` lacks
  `--no-dev`. Matters for a Render free-tier cold start.

---

## 2026-08-11 — Structured answers from the web fallback

### The problem

"Not in the available datasets" is a dead end. The fallback existed but returned a
paragraph, and most of these questions ("which countries have X", "what is Y in
Z") are inherently tabular — a paragraph reads badly and cannot be exported.

### What changed

`web_fallback` now makes a second versioned LLM call (`web_table@v1`) that
extracts a small table from the search snippets, rendered with per-row provenance
and downloadable as a report or CSV.

### Decision 1 — a separate type, not a flag

`WebTable` is its own domain entity. It is *not* an `ExecutionResult` with
`is_web=True`.

Governed rows are verified by a read-only role and an AST guardrail. Web rows are
a language model's reading of untrusted snippets. Give them one type and they
become substitutable in the UI, the report, the cache and the chart — and one
missed flag check silently launders a scrape as verified data. The separation is
carried all the way out: a distinct `web_table` SSE event, a distinct report
document, a `source_url` column in the CSV.

**Alternative considered:** one type plus a provenance flag. Fewer types, but the
failure mode is invisible and permanent, and the credibility of this whole project
rests on that distinction holding.

**Defence in two sentences:** governed data and web scrapings are different types
end to end, so the UI cannot render one through the other's path by accident. The
web path has exactly one outgoing edge in the graph — to `respond` — so web
content structurally cannot re-enter SQL generation.

### Decision 2 — the parser enforces attribution, not the prompt

Once extraction is structured, the obvious injection payload changes. A hostile
page no longer just skews a sentence; it tries to inject a *row* that renders in a
data table and a downloadable report, with a fabricated citation to look sourced.

So `parse_web_table` re-validates everything the model returns and drops any row
that is misshapen, all-null, or cites a source index outside the results actually
shown to it. Columns and rows are capped. Nulls render as an em dash, never the
string `"None"`, so a gap cannot be misread as data.

Prompt instructions are a request. The parser is the control. There is a test for
the fabricated-citation case specifically.

### Decision 3 — downloadable, but never replayed

Web answers are written to `report:{run_id}` so the user can download the answer
they just got, but deliberately **not** to the question-keyed answer cache. The
web moves; serving a month-old scrape as a fresh answer is worse than a cache
miss. This preserved the existing "don't cache web answers" decision while fixing
the fact that reports were silently unavailable for every web answer.

### Verified

End to end in the container against live DuckDuckGo and `qwen2.5:7b-instruct`.
"What is the adult literacy rate in Kenya?" produced a cited table (82%, 2020,
attributed to Africa Check), a report with the provenance banner, and a CSV
carrying `source_url`. 240 unit tests pass; the tier-1 eval gate still passes.

### Honest limits

Snippet fidelity is the ceiling, and it is low. Typical output is one row and one
or two columns, one of which is often just "Year" — the Kenya CO₂ answer was a
single cell. This was a deliberate choice against adding a page fetcher, which
would give real tables at the cost of a new dependency, SSRF and injection
surface, latency, and robots/ToS obligations on a public demo.

### Consequence to handle before enabling in production

The feature is off by default (`DATACHAT_WEB_SEARCH_ENABLED=false`) and the eval
graph is built without the fallback, so `refusal_accuracy = 0.80` still holds.

**The moment it is enabled, three of the five refusal cases become wrong** —
Kenya's CO₂, India's literacy rate and Germany's unemployment would escalate to
the web rather than refuse, which is now the *desired* behaviour. The golden set
needs splitting into "must refuse" (genuinely ambiguous) and "must escalate"
(out-of-corpus but answerable), with a separate `escalation_accuracy`. Not done.

### Also found

- The repair loop burns the full budget — three SQL generations — on questions
  that can never be answered, before falling through to the web. Real latency and
  cost per out-of-corpus question.
- Backend startup blocks on MLflow. With the tracking server down, boot took ~90s
  instead of seconds: the tracer is best-effort at *runtime* but not at *startup*.
  That will hurt on a free-tier cold start.
