# drive-sync Makefile
# Usage: make [target]

.PHONY: help test test-verbose test-coverage build run

# Default target
help:
	@echo "drive-sync - Makefile commands"
	@echo ""
	@echo "Testing (Docker):"
	@echo "  make test              Run tests in Docker"
	@echo "  make test-verbose      Run tests with verbose output"
	@echo "  make test-coverage     Run tests with coverage report"
	@echo ""
	@echo "Docker:"
	@echo "  make build             Build Docker image"
	@echo "  make run               Run sync via Docker"

# ===== Testing =====

test:
	@echo "Running tests in Docker..."
	docker compose run --rm drive-sync python -m pytest tests/ -v

test-verbose:
	docker compose run --rm drive-sync python -m pytest tests/ -v --tb=long

test-coverage:
	docker compose run --rm drive-sync python -m pytest tests/ -v --cov=src/drive_sync --cov-report=term-missing

# ===== Docker =====

build:
	docker compose build

run:
	docker compose up
