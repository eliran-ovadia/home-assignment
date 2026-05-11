.PHONY: help install lint format typecheck check test test-unit test-integration dev dev-db migrate migration clean

help:  ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install all dependencies and set up pre-commit hooks
	pip install -e ".[dev]"
	pre-commit install

lint:  ## Run ruff linter
	ruff check .

format:  ## Run ruff formatter
	ruff format .

typecheck:  ## Run ty static type checking
	ty check src/

check: lint typecheck  ## Run all static checks (lint + types)

test:  ## Run full test suite with coverage (enforces ≥80%)
	pytest --cov-fail-under=80

test-unit:  ## Run only unit tests (no database required)
	pytest tests/unit/

test-integration:  ## Run integration tests (requires running database)
	pytest tests/integration/

dev:  ## Start the full local environment via Docker Compose
	docker compose up --build

dev-db:  ## Start only the database service in the background
	docker compose up db -d

migrate:  ## Apply all pending Alembic migrations
	alembic upgrade head

migration:  ## Generate a new migration (usage: make migration name="describe_the_change")
	@test -n "$(name)" || (echo "ERROR: provide a name — e.g. make migration name='add_users_table'" && exit 1)
	alembic revision --autogenerate -m "$(name)"

clean:  ## Remove all build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -name "*.pyc" -delete
