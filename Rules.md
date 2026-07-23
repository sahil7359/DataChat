# Rules — DataChat (Engineering Constitution)

> **Read this first, in full, before writing any code.** It governs every other doc. If any instruction elsewhere conflicts with Rules.md, Rules.md wins. These rules exist so the finished project is genuinely the owner's work — understood, defensible, and human-authored.

---

## 0. Prime directives

1. **$0 forever.** No paid service or dependency, ever. If a task seems to need one, stop and find the free/OSS path or defer to `GOLIVE.md`.
2. **Security is not optional.** Treat all user input and **all LLM output as untrusted**. Least privilege everywhere. No secrets in code or git.
3. **It must be defensible.** Every non-trivial decision is explained so the owner can re-explain it in an interview. Name the pattern/principle in code.
4. **Human-authored feel.** Idiomatic, conventional code and an incremental git history. No AI tells (see §8).
5. **Autonomous execution.** Follow [ImplementationPlan.md](./ImplementationPlan.md) top to bottom without waiting, stopping only for a true blocker (§9).

## 1. Read order & build behavior

- Read: **Rules.md** → PRD → TechSpec → AppFlow → Design → Schema → ImplementationPlan → Tracker.
- Execute ImplementationPlan **phase by phase, autonomously**. After each phase: run the **per-phase gate** (tests + security + $0 + lint/type), fix all red, make **one small conventional commit**, tick tasks in **Tracker.md**, then continue.
- **Defer, don't block:** anything needing the user's accounts/keys/deploys is built against `.env.example` with mocks/stubs/fixtures; the real step goes to `GOLIVE.md`.
- **Stop only** for (a) a genuinely ambiguous requirement, or (b) a destructive/irreversible action. Otherwise keep going to the end.
- **`BUILD_MODE` toggle:** default `autonomous`. If set to `checkpointed`, pause for approval at each phase boundary. (Set here: `BUILD_MODE=autonomous`.)

## 2. Coding standards & style

**Python**
- Python 3.12+, **fully type-annotated**, `mypy --strict` clean. `ruff` + `ruff format` (line length 100).
- Async I/O throughout (FastAPI, asyncpg, httpx). No blocking calls on the request path.
- Prefer pure functions in `domain`; side effects live in `infrastructure`.
- Small functions, early returns, no deep nesting. Explicit over clever.
- Errors: typed errors / `Result` where failure is expected; exceptions only for the exceptional. Never `except: pass`.
- Docstrings only where they earn their place (public interfaces, non-obvious logic). Where a class realises a pattern, name it: `"""Adapter for the Groq chat API (see Design.md §5)."""`

**TypeScript / React**
- `strict` TS, no `any` (use `unknown` + narrowing). `eslint` (incl. security rules) clean.
- Server Components by default; Client Components only where interactivity requires. Keep the FE thin — rendering, not intelligence.
- Small components; typed API client; no secrets in the browser bundle.

**General**
- Comments explain **why**, never restate the obvious **what**.
- No dead code, no commented-out blocks, no leftover `TODO`/placeholder in committed code (open a Tracker row instead).
- Consistent style across the repo — it must read as one author.

## 3. Folder structure & naming

- Layout is fixed by [Design §2](./Design.md). Respect the clean-architecture boundaries: **`domain` imports nothing outward**; `infrastructure` implements `domain` ports; `interface` wires them. Enforce with an import-linter rule in CI.
- Python: `snake_case` modules/functions, `PascalCase` classes, `UPPER_SNAKE` constants. Ports are `PascalCase` protocols ending in the role (`SqlValidator`, `QueryExecutor`).
- TS: `camelCase` vars/functions, `PascalCase` components/types. Files: components `PascalCase.tsx`, utils `camelCase.ts`.
- Tests mirror source paths under `tests/`.

## 4. Testing requirements

- **Unit + integration for all new code**; ≥80% coverage on `domain/` + `application/`.
- **Agent/LLM behavior:** golden-set eval (`pytest -m eval`) with `execution_accuracy`, `sql_valid`, `explanation_faithfulness` scorers; MLflow-logged.
- **Security tests** (`tests/security/`) for every OWASP row in [ImplementationPlan §11](./ImplementationPlan.md).
- Use the **mock providers + seed fixtures** so the whole suite runs with **no real keys**.
- Deterministic tests: mock time/network; seed randomness. Flaky tests are bugs.
- CI (Phase 12) runs the full matrix; locally the per-phase gate must pass before committing.

## 5. Security rules (non-negotiable)

- **No secrets in code or git.** Only `.env` (git-ignored). `.env.example` documents every var with placeholders. `gitleaks` runs pre-commit and in CI — **zero** findings.
- **Validate every boundary.** Pydantic on all inputs; validate/schema-check **all LLM output** before use (SQL → guardrail; chart → JSON-schema).
- **Least privilege.** SQL runs only via the read-only `datachat_exec` role with timeout + row cap. The agent's tool set is **fixed and read-only**; no dynamic tool loading; no code execution (`eval`/`exec` banned — semgrep-enforced).
- **The guardrail pipeline is mandatory** before any execution and cannot be skipped by any node.
- **Defence in depth:** guardrail AST checks **and** the DB role both prevent writes; both must exist.
- **Bounded consumption:** rate limits, global quota, capped repair/retry loops, request timeouts, circuit breakers.
- **HITL is server-side** and non-bypassable by the client.
- **Dependencies:** pinned + lockfiles; `pip-audit`/`npm audit` in CI; add a dep only with a clear reason.
- Map every control to its OWASP LLM (2025) / Agentic (2026) item in the code/test and the matrix.

## 6. The $0 rule

- Every dependency and service must sit on a **permanent free tier or be OSS self-hosted**.
- Before adding any external service, confirm a free tier and record its limit + mitigation in [TechSpec §11](./TechSpec.md).
- If something is impossible at $0, **stop and flag it** with the cheapest honest alternative — do not silently add cost.

## 7. LLD expectations

- Apply the patterns in [Design §4](./Design.md) where they fit — and **name them in docstrings** so intent is legible.
- Do **not** cargo-cult: if a pattern doesn't earn its place, don't add it (the rejected list in Design §4 is part of the design).
- Keep vendors/DB/framework behind ports so they stay swappable (DIP). New provider/rule/dataset = new class + config, **no core edits** (OCP).

## 8. Authenticity rules (this is the owner's project)

- **Human-style code.** Idiomatic and conventional. **No AI tells:** no over-commenting the obvious, no "As an AI…"/"Here's the implementation" narration in code or comments, no emoji-stuffed comments, no giant verbose docstrings on trivial functions, no inconsistent styles stitched together, no placeholder `TODO`s left behind.
- **Incremental git history.** Small, focused commits using **Conventional Commits**; the log should read like a person built this over days/weeks (scaffold → feature → tests → refactor). **Never** one giant "initial commit" dump. Examples:
  - `chore: scaffold backend with uv, ruff, mypy`
  - `feat(llm): add circuit breaker with redis-backed state`
  - `test(guardrail): cover comment-evasion and CTE-write attempts`
  - `refactor(agent): extract BaseNode template method`
  - `fix(sse): flush explanation deltas incrementally`
  - `docs(tracker): mark phase 5 done`
- **Teach as you go.** For each non-trivial decision, briefly explain the why + the trade-off in the build narration (not in code noise). The owner must be able to defend it.
- **The owner writes the "why".** In README, leave the flagged spots (motivation, what I learned, a design decision I'm proud of) as clearly-marked placeholders for the owner's own words — do not fill them with generic prose.
- **Quiz at milestones.** At the end of Phases 3, 6, 10, 11, ask the owner **2–3 "explain it in an interview" questions** on what was just built. If they can't answer, re-teach before continuing. This is a required deliverable of the milestone, not a delay.

## 9. Stop / continue policy

| Situation | Action |
|---|---|
| Missing API key / account / deploy step | Build with mock/stub; add to `GOLIVE.md`; **continue** |
| Ambiguous requirement | **Stop**, ask one crisp question |
| Destructive/irreversible action (drop data, force-push, spend money) | **Stop**, ask |
| Test/security red | Fix; do not commit or advance until green |
| Everything green | Commit, update Tracker, **continue** to next phase |

## 10. Definition of done (whole project)

- All ImplementationPlan phases complete; Tracker matches reality.
- CI green: lint, type, unit/integration, agent-eval, security suite; coverage met.
- **0 secrets** in the repo/history; **0 unsafe SQL** executable; OWASP matrices satisfied with tests.
- Runs locally via `docker compose up` against `.env.example` with mocks (no real keys).
- `GOLIVE.md`, final summary, and final security report produced; git history clean + incremental; `v1.0.0` tagged.

## 11. Keep docs in sync

If a contract, schema, or decision changes during the build, update the relevant doc (PRD/TechSpec/AppFlow/Design/Schema) **in the same commit**, and note it in the Tracker decisions log. The docs and the code must never drift.
