# LEARN — change log with reasoning

A running record of non-obvious changes: what moved, **why**, what else was
considered, and how to defend it out loud. Newest first.

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

### Still open

- Cache speedup figure pulled from the README — the hit path is not instrumented,
  so the old "~20–40s → ~70ms" had no artifact behind it. Re-publish only with a
  measurement.
- Backend image is 3.16GB; ~1.13GB is a duplicated venv layer caused by
  `chown -R` after `COPY`, ~470MB is MLflow's scientific stack, and dev tools
  (`pytest`, `mypy`, `ruff`, `bandit`) ship to production because `uv sync` lacks
  `--no-dev`. Matters for a Render free-tier cold start.
