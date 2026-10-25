.PHONY: help dev test lint mypy migrate build up down clean install-hooks

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies (including dev)
	uv sync

install-hooks: ## Install pre-commit hooks
	uv run pre-commit install

dev: ## Run development server with auto-reload
	uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

test: ## Run all tests
	uv run pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage report
	uv run pytest tests/ -v --cov=backend --cov-report=term-missing --cov-report=html

lint: ## Run ruff linter and auto-fix
	uv run ruff check backend/ tests/ --fix
	uv run ruff format backend/ tests/

lint-check: ## Run ruff in check-only mode (no auto-fix)
	uv run ruff check backend/ tests/
	uv run ruff format --check backend/ tests/

mypy: ## Run mypy type checker
	uv run mypy backend/

migrate-init: ## Create initial Alembic migration
	uv run alembic revision --autogenerate -m "initial"

migrate: ## Generate migration from model changes
	uv run alembic revision --autogenerate -m "$(msg)"

migrate-up: ## Apply all pending migrations
	uv run alembic upgrade head

migrate-down: ## Rollback last migration
	uv run alembic downgrade -1

migrate-status: ## Show current migration status
	uv run alembic current

build: ## Build Docker image
	docker build -t crosstax-ai:latest .

up: ## Start all services via docker-compose
	docker compose up -d

down: ## Stop all services
	docker compose down

clean: ## Remove build artifacts and caches
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

check: lint-check mypy test ## Run all checks (lint + mypy + test)
