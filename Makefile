# drive-sync Makefile
# Usage: make [target]

.PHONY: help test test-verbose test-coverage test-local build run

# Default target
help:
	@echo "drive-sync - Makefile commands"
	@echo ""
	@echo "Testing (Docker):"
	@echo "  make test              Run tests in Docker"
	@echo "  make test-verbose      Run tests with verbose output"
	@echo "  make test-coverage     Run tests with coverage report"
	@echo "  make test-local        Run tests locally (no Docker)"
	@echo ""
	@echo "Docker:"
	@echo "  make build             Build Docker image"
	@echo "  make run               Run sync via Docker"

# ===== Testing =====

test:
	@echo "Running tests in Docker..."
	docker run --rm drive-sync-drive-sync python -m pytest tests/ -v

test-verbose:
	docker run --rm drive-sync-drive-sync python -m pytest tests/ -v --tb=long

test-coverage:
	docker run --rm drive-sync-drive-sync python -m pytest tests/ -v --cov=src/drive_sync --cov-report=term-missing

test-local:
	@echo "Running tests locally (requires Python dependencies)..."
	python -m pytest tests/ -v

# ===== Docker =====

build:
	docker compose build

run:
	docker compose up
