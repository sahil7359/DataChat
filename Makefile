# DataChat task runner. Thin wrappers over uv/pnpm so the same commands work
# locally and in CI. See ImplementationPlan.md for the per-phase gate.

BACKEND := backend
FRONTEND := frontend

.DEFAULT_GOAL := help
.PHONY: help up down install lint fmt type test test-cov sec eval ingest fe-install fe-lint fe-build

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

up: ## Boot the full stack (postgres+pgvector, redis, backend, frontend, mlflow)
	docker compose up --build

down: ## Stop the stack
	docker compose down -v

install: ## Install backend deps (incl. dev group)
	cd $(BACKEND) && uv sync --all-extras

lint: ## ruff + import-linter (backend); eslint (frontend)
	cd $(BACKEND) && uv run python -m ruff check . && uv run python -m ruff format --check .
	# `|| true` because grimp's native ext is WDAC-blocked on the Windows dev
	# box; CI (Linux) runs `lint-imports` for real and must not be softened.
	# Note `python -m importlinter.cli` silently no-ops on 2.13 — if you want a
	# local check, run `lint-imports` inside the container.
	cd $(BACKEND) && uv run python -m importlinter.cli lint || true

fmt: ## Auto-format
	cd $(BACKEND) && uv run python -m ruff format . && uv run python -m ruff check --fix .

type: ## mypy --strict (backend)
	bash $(BACKEND)/scripts/typecheck.sh

test: ## Unit tests (no live services)
	cd $(BACKEND) && uv run python -m pytest -m "not integration and not eval and not eval_real"

test-cov: ## Unit + integration with coverage gate on domain/application
	cd $(BACKEND) && uv run python -m pytest --cov --cov-report=term-missing

sec: ## Security scanners: bandit, pip-audit, gitleaks (semgrep runs in CI)
	cd $(BACKEND) && uv run python -m bandit -q -r app ingestion -c pyproject.toml
	cd $(BACKEND) && uv run python -m pip_audit || true
	gitleaks dir --no-banner --redact -c .gitleaks.toml .

eval: ## Deterministic golden-set pipeline gate (scripted LLM, free, runs in CI)
	cd $(BACKEND) && uv run python -m pytest -m eval

eval-real: ## Quality gate vs eval_baseline.json using a real provider (needs Ollama or keys)
	cd $(BACKEND) && DATACHAT_EVAL_REAL=1 uv run python -m pytest -m eval_real -s

ingest: ## Load the seed open-data slice locally
	cd $(BACKEND) && uv run python -m ingestion.run --dataset seed

fe-install: ## Install frontend deps
	cd $(FRONTEND) && pnpm install

fe-lint: ## Lint + typecheck frontend
	cd $(FRONTEND) && pnpm run lint && pnpm run typecheck

fe-build: ## Production build of the frontend
	cd $(FRONTEND) && pnpm run build
