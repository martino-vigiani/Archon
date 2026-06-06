# Archon - Build and Test Commands
# ================================
#
# Usage:
#   make test          - Run all tests
#   make test-quick    - Run quick smoke tests
#   make coverage      - Run tests with coverage
#   make lint          - Run linting checks
#   make format        - Format code with black
#   make quality       - Run all quality gates
#   make build         - Verify build
#   make clean         - Clean generated files

.PHONY: all test test-backend test-frontend test-all test-quick test-unit test-integration test-critical coverage coverage-report coverage-html coverage-frontend lint lint-fix format types quality quality-quick quality-strict build build-check clean clean-all ci ci-quick monitor verify help install dev-install

# Default target
all: quality

# Tooling
PYTHON ?= .venv/bin/python
ifeq ($(wildcard $(PYTHON)),)
PYTHON := python
endif
NPM ?= npm

# =============================================================================
# Installation
# =============================================================================

install:
	$(PYTHON) -m pip install -r requirements.txt

dev-install:
	$(PYTHON) -m pip install -r requirements-dev.txt
	$(NPM) install

# =============================================================================
# Testing
# =============================================================================

test: test-backend

test-backend:
	$(PYTHON) -m pytest tests/ -v --tb=short

test-frontend:
	$(NPM) run test:frontend

test-all: test-backend test-frontend

test-quick:
	$(PYTHON) -m pytest tests/ -v --tb=line -x -m "smoke or not slow" -q

test-unit:
	$(PYTHON) -m pytest tests/ -v --tb=short -m "unit or not integration"

test-integration:
	$(PYTHON) -m pytest tests/ -v --tb=short -m "integration"

test-critical:
	$(PYTHON) -m pytest tests/ -v --tb=short -m "critical"

# =============================================================================
# Coverage
# =============================================================================

coverage:
	$(PYTHON) -m pytest tests/ \
		--cov=orchestrator \
		--cov-report=term-missing \
		--cov-report=html:.orchestra/qa/coverage/html \
		--cov-report=json:.orchestra/qa/coverage/coverage.json \
		--cov-fail-under=80

coverage-report:
	$(PYTHON) -m pytest tests/ \
		--cov=orchestrator \
		--cov-report=term-missing

coverage-html:
	$(PYTHON) -m pytest tests/ \
		--cov=orchestrator \
		--cov-report=html:.orchestra/qa/coverage/html
	@echo "Coverage report: .orchestra/qa/coverage/html/index.html"

coverage-frontend:
	$(NPM) run coverage:frontend

# =============================================================================
# Linting and Formatting
# =============================================================================

lint:
	$(PYTHON) -m ruff check orchestrator/ tests/
	$(PYTHON) -m black --check orchestrator/ tests/

lint-fix:
	$(PYTHON) -m ruff check --fix orchestrator/ tests/

format:
	$(PYTHON) -m black orchestrator/ tests/

types:
	$(PYTHON) -m mypy orchestrator/ --ignore-missing-imports

# =============================================================================
# Quality Gates
# =============================================================================

quality:
	$(PYTHON) scripts/quality_gates.py

quality-quick:
	$(PYTHON) scripts/quality_gates.py --quick

quality-strict:
	$(PYTHON) scripts/quality_gates.py --threshold 80

# =============================================================================
# Build Verification
# =============================================================================

build:
	@echo "Verifying build..."
	@$(PYTHON) -c "from orchestrator import config, task_queue, terminal" && echo "Build OK"

build-check:
	@echo "Running syntax check..."
	@$(PYTHON) -m py_compile orchestrator/__init__.py
	@$(PYTHON) -m py_compile orchestrator/config.py
	@$(PYTHON) -m py_compile orchestrator/task_queue.py
	@$(PYTHON) -m py_compile orchestrator/terminal.py
	@$(PYTHON) -m py_compile orchestrator/orchestrator.py
	@$(PYTHON) -m py_compile orchestrator/planner.py
	@echo "Syntax check passed"

# =============================================================================
# Cleanup
# =============================================================================

clean:
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf __pycache__
	rm -rf orchestrator/__pycache__
	rm -rf tests/__pycache__
	rm -rf .coverage
	rm -rf htmlcov
	rm -rf .orchestra/qa/coverage
	rm -rf .orchestra/qa/tests
	rm -rf .orchestra/qa/reports
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete

clean-all: clean
	rm -rf .venv
	rm -rf *.egg-info

# =============================================================================
# CI/CD Targets
# =============================================================================

ci: lint types test-backend coverage test-frontend

ci-quick: lint-fix test-quick test-frontend

# =============================================================================
# Continuous Monitoring (T5 Skeptic)
# =============================================================================

monitor:
	@echo "Starting continuous build monitoring..."
	@while true; do \
		echo "\n[$(date)] Running build check..."; \
		make build-check; \
		echo "[$(date)] Running quick tests..."; \
		make test-quick || echo "TESTS FAILED"; \
		echo "[$(date)] Waiting 120 seconds..."; \
		sleep 120; \
	done

verify:
	@echo "=== BUILD VERIFICATION ==="
	@make build-check
	@echo ""
	@echo "=== QUICK TESTS ==="
	@make test-quick
	@echo ""
	@echo "=== LINT CHECK ==="
	@make lint || true
	@echo ""
	@echo "=== VERIFICATION COMPLETE ==="

# =============================================================================
# Help
# =============================================================================

help:
	@echo "Archon Build Commands"
	@echo "===================="
	@echo ""
	@echo "Testing:"
	@echo "  make test           - Run backend tests"
	@echo "  make test-backend   - Run backend tests (pytest)"
	@echo "  make test-frontend  - Run frontend tests (vitest)"
	@echo "  make test-all       - Run backend + frontend tests"
	@echo "  make test-quick     - Run quick smoke tests"
	@echo "  make test-unit      - Run unit tests only"
	@echo "  make test-integration - Run integration tests"
	@echo "  make test-critical  - Run critical tests only"
	@echo ""
	@echo "Coverage:"
	@echo "  make coverage       - Run tests with coverage (fail under 80%)"
	@echo "  make coverage-report - Show coverage in terminal"
	@echo "  make coverage-html  - Generate HTML coverage report"
	@echo "  make coverage-frontend - Frontend coverage with Vitest"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint           - Run linting checks"
	@echo "  make lint-fix       - Auto-fix linting issues"
	@echo "  make format         - Format code with black"
	@echo "  make types          - Run type checking"
	@echo ""
	@echo "Quality Gates:"
	@echo "  make quality        - Run all quality gates"
	@echo "  make quality-quick  - Quick quality check"
	@echo "  make quality-strict - Strict quality (80% coverage)"
	@echo ""
	@echo "Build:"
	@echo "  make build          - Verify imports work"
	@echo "  make build-check    - Verify syntax"
	@echo "  make verify         - Full verification"
	@echo ""
	@echo "Monitoring (T5):"
	@echo "  make monitor        - Continuous build monitoring"
	@echo ""
	@echo "Maintenance:"
	@echo "  make install        - Install dependencies"
	@echo "  make dev-install    - Install backend+frontend dev dependencies"
	@echo "  make clean          - Clean generated files"
	@echo "  make ci             - Full CI pipeline"
