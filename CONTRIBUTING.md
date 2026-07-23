# Contributing / Development notes

Small, focused pull requests using [Conventional Commits](https://www.conventionalcommits.org/). This is primarily a portfolio project, but the workflow below keeps it clean and reviewable.

## Local setup

```bash
cp .env.example .env      # USE_MOCKS=true by default — no real keys needed
docker compose up --build
docker compose exec backend python -m ingestion.run --dataset seed
```

App on :3000, API on :8000 (`/docs`), MLflow on :5000.

## Before you commit

The same gate CI enforces (see [Rules.md](./Rules.md) and [ImplementationPlan.md](./ImplementationPlan.md)):

```bash
make lint     # ruff, ruff format, mypy --strict, eslint, tsc
make test     # unit + integration (>=80% on domain/application)
make sec      # pip-audit, npm audit, bandit, semgrep, gitleaks
make eval     # agent golden-set execution accuracy (regression gate)
```

- Never commit secrets — only `.env.example` is tracked; `gitleaks` runs pre-commit.
- Keep changes within the clean-architecture boundaries ([Design §2](./Design.md)): `domain` imports nothing outward.
- If you change a contract or schema, update the relevant doc in the same commit.
- Name applied design patterns in docstrings so intent stays legible.

## Commit style

```
feat(llm): add groq adapter with retry+jitter decorator
test(guardrail): cover CTE-write and comment-evasion attempts
fix(sse): flush explanation deltas incrementally
docs(tracker): mark phase 5 done
```
