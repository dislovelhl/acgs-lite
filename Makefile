.PHONY: help setup lock-sync lock-validate test test-quick test-lite test-bus test-gw lint format clean bench cov cov-html codex-doctor autoresearch-promote agent-commit

LOCK_PYTHON ?= 3.11
UV ?= uv
ROOT_DIR := $(CURDIR)
UV_CACHE_DIR ?= $(ROOT_DIR)/.uv-cache
VENV_PYTHON := $(ROOT_DIR)/.venv/bin/python
PYTHON ?= $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),python3)
PIP ?= $(PYTHON) -m pip
WORKSPACE_PYTHONPATH := $(ROOT_DIR)/packages:$(ROOT_DIR)/src:$(ROOT_DIR)
export PYTHONPATH := $(WORKSPACE_PYTHONPATH)$(if $(PYTHONPATH),:$(PYTHONPATH))
PYTEST_TARGETS ?=
PYTEST_ARGS ?=
UV_SYNC_ARGS ?= --frozen --all-packages --extra dev --extra test --python $(LOCK_PYTHON) --no-python-downloads

help:
	@echo "ACGS — Advanced Constitutional Governance System"
	@echo ""
	@echo "  Setup:"
	@echo "    make setup        Install deps + pre-commit"
	@echo "    make lock-sync    Rebuild the project .venv from uv.lock on Python $(LOCK_PYTHON)"
	@echo "    make lock-validate Verify the locked .venv and run environment smoke tests"
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
	@echo "    make bench        Run acgs-lite benchmark suite"

# === Setup ===
setup:
	$(PIP) install -e ".[dev,test]"
	$(PIP) install -e packages/acgs-lite[dev]
	$(PIP) install -e packages/enhanced_agent_bus[dev]
	$(PIP) install -e packages/acgs-deliberation[dev]
	pre-commit install
	cd packages/propriety-ai && npm install

lock-sync:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) sync $(UV_SYNC_ARGS)

lock-validate: lock-sync
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) sync $(UV_SYNC_ARGS) --check
	$(PYTHON) -c "import acgs_lite, sys; print(sys.executable); print(sys.version.split()[0]); print(acgs_lite.__file__)"
	$(PYTHON) -m pytest --import-mode=importlib -q \
		tests/test_testclient_compat.py \
		src/core/shared/tests/test_runtime_environment.py \
		src/core/services/api_gateway/tests/unit/test_lifespan.py::TestVerifyConstitutionalHashAtStartup::test_environment_only_production_still_requires_constitutional_hash

# === Testing ===
test:
	$(PYTHON) -m pytest --import-mode=importlib -v $(PYTEST_TARGETS) $(PYTEST_ARGS)
	cd packages/propriety-ai && npm run test

test-quick:
	$(PYTHON) -m pytest --import-mode=importlib -m "not slow" -x -v $(PYTEST_TARGETS) $(PYTEST_ARGS)
	cd packages/propriety-ai && npm run test:unit

test-lite:
	$(PYTHON) -m pytest $(or $(PYTEST_TARGETS),packages/acgs-lite/tests/) -v --import-mode=importlib $(PYTEST_ARGS)

test-bus:
	$(PYTHON) -m pytest $(or $(PYTEST_TARGETS),packages/enhanced_agent_bus/tests/) -v --import-mode=importlib $(PYTEST_ARGS)

test-gw:
	$(PYTHON) -m pytest $(or $(PYTEST_TARGETS),src/core/services/api_gateway/tests/) -v --import-mode=importlib $(PYTEST_ARGS)

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
	$(PYTHON) -m pytest packages/acgs-lite/tests/test_benchmark_engine.py -m benchmark -v --import-mode=importlib

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
