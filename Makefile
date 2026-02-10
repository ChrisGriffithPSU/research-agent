.PHONY: help migrate migrate-create migrate-autogen seed db-shell db-logs clean-db \
	infra infra-down infra-logs infra-restart services services-down services-logs \
	worker-kimi scheduler fetch-once health-check \
	test test-unit test-integration test-e2e test-cov test-watch test-repo \
	dev-setup lint lint-fix format format-check type-check deps deps-upgrade clean clean-all quickstart

help:  ## Show this help message
	@echo ''
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} ; { printf "  %-15s %s\n", $$1, $$2 } /^([a-zA-Z_-]+):.*?## / { $$1 = $$1 }' $(MAKEFILE_LIST)
	@echo ''

# Database targets
migrate:  ## Run database migrations to create/update schema
	uv run alembic -c src/shared/db/migrations/alembic.ini upgrade head

migrate-create:  ## Create a new migration (use MSG="description")
	@echo "Creating new migration..."
	uv run alembic -c src/shared/db/migrations/alembic.ini revision -m "$(MSG)"

migrate-autogen:  ## Auto-generate migration from model changes
	@echo "Auto-generating migration from model changes..."
	uv run alembic -c src/shared/db/migrations/alembic.ini revision --autogenerate -m "Auto-generated"

seed:  ## Seed database with initial data
	@echo "Seeding database..."
	uv run python -m src.shared.db.seed

db-shell:  ## Open PostgreSQL shell (psql)
	docker exec -it researcher-postgres psql -U postgres -d researcher_agent

db-logs:  ## Show PostgreSQL logs
	docker logs researcher-postgres

clean-db:  ## Reset database (WARNING: deletes all data)
	@echo "Stopping PostgreSQL..."
	docker compose -f infra/docker/docker-compose.yml down postgres
	@echo "Removing volume..."
	docker volume rm researcher-agent_postgres-data
	@echo "Starting PostgreSQL..."
	docker compose -f infra/docker/docker-compose.yml up -d postgres
	@sleep 10
	@echo "Running migrations..."
	$(MAKE) migrate
	@echo "Seeding database..."
	$(MAKE) seed
	@echo "Database reset complete!"

# Infrastructure targets
infra:  ## Start infrastructure (PostgreSQL + RabbitMQ)
	@echo "Starting infrastructure..."
	docker compose -f infra/docker/docker-compose.yml up -d postgres rabbitmq

infra-down:  ## Stop infrastructure
	@echo "Stopping infrastructure..."
	docker compose -f infra/docker/docker-compose.yml down

infra-logs:  ## Show infrastructure logs
	docker compose -f infra/docker/docker-compose.yml logs -f

infra-restart:  ## Restart infrastructure
	@echo "Restarting infrastructure..."
	$(MAKE) infra-down
	$(MAKE) infra

services:  ## Start all worker services from docker compose
	@echo "Starting worker services..."
	docker compose -f infra/docker/docker-compose.yml up -d arxiv-fetcher paper-triage pdf-parser concept-generator experiment-exploder notifier

services-down:  ## Stop worker services
	@echo "Stopping worker services..."
	docker compose -f infra/docker/docker-compose.yml stop arxiv-fetcher paper-triage pdf-parser concept-generator experiment-exploder notifier

services-logs:  ## Follow logs for worker services
	@echo "Streaming worker service logs..."
	docker compose -f infra/docker/docker-compose.yml logs -f arxiv-fetcher paper-triage pdf-parser concept-generator experiment-exploder notifier

worker-kimi:  ## Run Kimi worker in queue mode locally
	@echo "Starting local Kimi queue worker..."
	uv run python -m src.main worker kimi

scheduler:  ## Run scheduler locally
	@echo "Starting scheduler..."
	uv run python -m src.main scheduler

fetch-once:  ## Trigger one scheduler fetch cycle locally
	@echo "Running one fetch cycle..."
	uv run python -m src.main fetch-once

health-check:  ## Run app health checks locally
	@echo "Running health checks..."
	uv run python -m src.main health-check

# Testing targets
test:  ## Run all tests
	@echo "Running tests..."
	uv run pytest

test-unit:  ## Run unit tests only
	@echo "Running unit tests..."
	uv run pytest tests/unit

test-integration:  ## Run integration tests only
	@echo "Running integration tests..."
	uv run pytest tests/integration

test-e2e:  ## Run end-to-end tests only
	@echo "Running end-to-end tests..."
	uv run pytest tests/e2e

test-cov:  ## Run tests with coverage report
	@echo "Running tests with coverage..."
	uv run pytest --cov=src/shared --cov-report=html --cov-report=term

test-watch:  ## Run tests in watch mode
	@echo "Running tests in watch mode..."
	uv run pytest -f

test-repo:  ## Run repository tests
	@echo "Running repository tests..."
	uv run pytest tests/unit/shared/repositories

# Development targets
dev-setup:  ## Setup development environment
	@echo "Setting up development environment..."
	uv sync
	$(MAKE) migrate
	$(MAKE) seed
	@echo "Development setup complete!"

lint:  ## Run linter (ruff)
	@echo "Running linter..."
	uv run ruff check src workers tests

lint-fix:  ## Auto-fix linter issues
	@echo "Fixing linter issues..."
	uv run ruff check --fix src workers tests

format:  ## Format code (black)
	@echo "Formatting code..."
	uv run black src workers tests

format-check:  ## Check code formatting
	@echo "Checking code formatting..."
	uv run black --check src workers tests

type-check:  ## Run type checker (mypy)
	@echo "Running type checker..."
	uv run mypy src workers

# Utility targets
deps:  ## Install dependencies
	@echo "Installing dependencies..."
	uv sync

deps-upgrade:  ## Upgrade dependencies
	@echo "Upgrading dependencies..."
	uv sync --upgrade

clean:  ## Clean build artifacts
	@echo "Cleaning build artifacts..."
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

clean-all:  ## Clean everything including database volumes
	@echo "Cleaning everything..."
	$(MAKE) clean
	@echo "Stopping containers..."
	docker compose -f infra/docker/docker-compose.yml down -v
	@echo "Clean complete!"

# Quick start workflow
quickstart:  ## Quick start: setup infra + migrate + seed
	@echo "Quick start setup..."
	@echo "1. Starting infrastructure..."
	$(MAKE) infra
	@sleep 5
	@echo "2. Running migrations..."
	$(MAKE) migrate
	@echo "3. Seeding database..."
	$(MAKE) seed
	@echo "4. Running tests..."
	$(MAKE) test-unit
	@echo ""
	@echo "✅ Quick start complete!"
	@echo ""
	@echo "Next steps:"
	@echo "  - Start services: make services"
	@echo "  - Check database: make db-shell"
	@echo "  - View logs: make infra-logs"
