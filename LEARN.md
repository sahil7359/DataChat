# LEARN — change log with reasoning

A running record of non-obvious changes: what moved, **why**, what else was
considered, and how to defend it out loud. Most recent date first; within a date,
in the order the work happened.

For *how the system works* rather than why it changed, see [FLOW.md](./FLOW.md).

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
