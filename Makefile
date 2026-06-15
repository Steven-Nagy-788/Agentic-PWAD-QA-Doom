.PHONY: help dev dev-venv test lint clean docker-up docker-down docker-build install

help:
	@echo "Agentic PWAD QA for Doom"
	@echo ""
	@echo "Local development (venv):"
	@echo "  make install          Install all services into venvs + npm/bun install"
	@echo "  make dev-venv         Start all services locally (postgres, mcp-doom, backend, frontend)"
	@echo "  make test             Run all test suites"
	@echo "  make lint             Run linters across all services"
	@echo ""
	@echo "Docker development:"
	@echo "  make docker-up        Build and start the full Docker Compose stack"
	@echo "  make docker-down      Stop and remove the Docker Compose stack"
	@echo "  make docker-build     Build all Docker images without starting"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean            Remove caches, build artifacts, and __pycache__"

# ---------------------------------------------------------------------------
# Local venv development
# ---------------------------------------------------------------------------

install:
	@echo "==> Installing backend..."
	cd Backend && python3 -m venv .venv && .venv/bin/pip install --upgrade pip -q && .venv/bin/pip install -r requirements.txt -q
	@echo "==> Installing mcp-doom..."
	cd mcp-doom && python3 -m venv .venv && .venv/bin/pip install --upgrade pip -q && .venv/bin/pip install -e ".[dev]" -q
	@echo "==> Installing frontend..."
	cd frontend && (command -v bun >/dev/null 2>&1 && bun install --frozen-lockfile || npm ci)
	@echo "==> Done. Copy Backend/.env.example to Backend/.env and configure it."

dev-venv: install
	@echo "Starting all services locally..."
	@echo "  PostgreSQL must be running on localhost:5432"
	@echo "  Run 'make -C Backend db-init && make -C Backend db-upgrade' if first time"
	@echo ""
	@make -C Backend run &
	@cd mcp-doom && .venv/bin/fastmcp run src/doom_mcp/server.py --transport sse --host 127.0.0.1 --port 8001 --path /sse &
	@cd frontend && (command -v bun >/dev/null 2>&1 && bun dev || npm run dev) &
	@wait

# ---------------------------------------------------------------------------
# Docker development
# ---------------------------------------------------------------------------

docker-up:
	POSTGRES_PASSWORD=$${POSTGRES_PASSWORD:-doom_dev} docker compose up -d --build

docker-down:
	docker compose down -v

docker-build:
	docker compose build

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

test:
	@echo "==> Backend tests..."
	cd Backend && .venv/bin/python -m pytest -q
	@echo "==> MCP-Doom unit tests..."
	cd mcp-doom && .venv/bin/python -m pytest -q -m "not integration"
	@echo "==> Frontend tests..."
	cd frontend && (command -v bun >/dev/null 2>&1 && bun run test || npm test -- --run)
	@echo "==> All tests passed."

# ---------------------------------------------------------------------------
# Linting
# ---------------------------------------------------------------------------

lint:
	@echo "==> Frontend lint..."
	cd frontend && (command -v bun >/dev/null 2>&1 && bun run lint || npm run lint)
	@echo "==> All lints passed."

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

clean:
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	find . -type d -name '.pytest_cache' -prune -exec rm -rf {} +
	find . -type d -name 'node_modules' -prune -exec rm -rf {} +
	rm -rf frontend/.next backend/.venv mcp-doom/.venv
