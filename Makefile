.PHONY: help setup test test-quick test-lite test-bus test-gw lint format clean bench cov cov-html codex-doctor autoresearch-promote agent-commit

PYTHON ?= python3
PIP ?= $(PYTHON) -m pip

help:
	@echo "ACGS — Advanced Constitutional Governance System"
	@echo ""
	@echo "  Setup:"
	@echo "    make setup        Install deps + pre-commit"
	@echo "    make codex-doctor  Run repo-local Codex readiness checks"
	@echo ""
	@echo "  Testing:"
	@echo "    make test         Full test suite"
	@echo "    make test-quick   Skip slow tests"
	@echo "    make test-lite    acgs-lite tests only"
	@echo "    make test-bus     Enhanced Agent Bus tests only"
	@echo "    make test-gw      API Gateway tests only"
	@echo ""
	@echo "  Code Quality:"
	@echo "    make lint         Ruff + MyPy"
	@echo "    make format       Auto-fix formatting"
	@echo "    make clean        Remove cache files"
	@echo ""
	@echo "  Benchmarks:"
	@echo "    make bench        Run autoresearch benchmark"

# === Setup ===
setup:
	$(PIP) install -e ".[dev,test]"
	$(PIP) install -e packages/acgs-lite[dev]
	$(PIP) install -e packages/enhanced_agent_bus[dev]
	pre-commit install
	cd packages/propriety-ai && npm install

# === Testing ===
test:
	$(PYTHON) -m pytest --import-mode=importlib -v
	cd packages/propriety-ai && npm run test

test-quick:
	$(PYTHON) -m pytest --import-mode=importlib -m "not slow" -x -v
	cd packages/propriety-ai && npm run test:unit

test-lite:
	$(PYTHON) -m pytest packages/acgs-lite/tests/ -v --import-mode=importlib

test-bus:
	$(PYTHON) -m pytest packages/enhanced_agent_bus/tests/ -v --import-mode=importlib

test-gw:
	$(PYTHON) -m pytest src/core/services/api_gateway/tests/ -v --import-mode=importlib

# === Code Quality ===
lint:
	ruff check --extend-exclude .codex-home .
	mypy \
		conftest.py \
		src/core/shared/cache/models.py \
		src/core/shared/acgs_logging/agent_workflow_events.py \
		src/core/shared/agent_workflow_metrics.py \
		src/core/shared/errors/logging.py \
		src/core/shared/utilities/tenant_normalizer.py \
		src/core/shared/security/auth_dependency.py \
		src/core/services/api_gateway/workos_event_ingestion.py \
		packages/enhanced_agent_bus/__init__.py \
		packages/enhanced_agent_bus/acl_adapters/__init__.py \
		packages/enhanced_agent_bus/agent_health/__init__.py \
		packages/enhanced_agent_bus/mcp/__init__.py \
		packages/enhanced_agent_bus/multi_tenancy/__init__.py \
		--ignore-missing-imports \
		--follow-imports skip
	cd packages/propriety-ai && npm run check && npm run lint

format:
	ruff check --fix .
	ruff format .
	cd packages/propriety-ai && npm run format

# === Coverage ===
cov:
	$(PYTHON) -m pytest --import-mode=importlib --cov --cov-report=term-missing -m "not slow" -x

cov-html:
	$(PYTHON) -m pytest --import-mode=importlib --cov --cov-report=html -m "not slow"
	@echo "Coverage report: htmlcov/index.html"

# === Benchmarks ===
bench:
	cd packages/acgs-lite && $(PYTHON) -m pytest tests/ -m benchmark -v --import-mode=importlib

# === Codex Bootstrap ===
codex-doctor:
	bash ./.agents/skills/acgs-codex-bootstrap/scripts/codex-doctor.sh

# === Autoresearch ===
autoresearch-promote:
	@if [ -z "$(COMMIT)" ]; then \
	  echo "Usage: make autoresearch-promote COMMIT=<sha>"; \
	  echo "  Cherry-picks a winning autoresearch commit onto the current branch."; \
	  exit 1; \
	fi
	git cherry-pick $(COMMIT)
	@echo ""
	@echo "Cherry-picked $(COMMIT). Verify before pushing:"
	@echo "  make test-quick && make lint"

# === Agent Identity ===
agent-commit:
	@if [ -z "$(MSG)" ]; then echo "Usage: make agent-commit MSG='feat: ...' AGENT=claude-code ROLE=validator"; exit 1; fi
	ACGS_AGENT_ID="$(or $(AGENT),unknown)" ACGS_MACI_ROLE="$(or $(ROLE),unknown)" \
	  bash scripts/agent-commit.sh -m "$(MSG)"

# === Cleanup ===
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".coverage" -delete 2>/dev/null || true
