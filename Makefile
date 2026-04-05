.PHONY: help setup lock-sync lock-validate test test-quick test-lite test-bus test-gw build-root-package publish-root-dry-run publish-root-package build-acgs-lite publish-acgs-lite-dry-run publish-acgs-lite build-acgs publish-dry-run publish-acgs health-manifest health-overview health-lite health-bus health-bus-governance health-bus-wrappers health-bus-wrappers-batch1-ready health-gw health-constitutional-swarm health-frontend health-worker lint format clean bench cov cov-html codex-doctor autoresearch-promote agent-commit dashboard-install dashboard-dev dashboard-build dashboard-backend

LOCK_PYTHON ?= 3.11
UV ?= uv
ROOT_DIR := $(CURDIR)
UV_CACHE_DIR ?= $(ROOT_DIR)/.uv-cache
VENV_PYTHON := $(ROOT_DIR)/.venv/bin/python
PYTHON ?= $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),python3)
PIP ?= $(PYTHON) -m pip
WORKSPACE_PYTHONPATH := $(ROOT_DIR)/packages/enhanced_agent_bus:$(ROOT_DIR)/packages/acgs-core/src:$(ROOT_DIR)/packages/acgs-lite/src:$(ROOT_DIR)/packages/acgs-deliberation/src:$(ROOT_DIR)/packages/constitutional_swarm/src:$(ROOT_DIR)/packages/mhc/src:$(ROOT_DIR)/src:$(ROOT_DIR)
export PYTHONPATH := $(WORKSPACE_PYTHONPATH)$(if $(PYTHONPATH),:$(PYTHONPATH))
PYTEST_TARGETS ?=
PYTEST_ARGS ?=
UV_SYNC_ARGS ?= --frozen --all-packages --extra dev --extra test --extra postgres --extra ml --extra messaging --extra all --python $(LOCK_PYTHON) --no-python-downloads

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
	@echo "  Release:"
	@echo "    make build-root-package    Build the root package artifacts"
	@echo "    make publish-root-dry-run  Build and dry-run the root package publish"
	@echo "    make publish-root-package  Build and publish the root package (requires UV_PUBLISH_TOKEN)"
	@echo "    make build-acgs-lite       Build the public acgs-lite package artifacts"
	@echo "    make publish-acgs-lite-dry-run Build and dry-run the public acgs-lite publish"
	@echo "    make publish-acgs-lite     Build and publish the public acgs-lite package"
	@echo "    make build-acgs            Legacy alias for make build-root-package"
	@echo "    make publish-dry-run       Legacy alias for make publish-root-dry-run"
	@echo "    make publish-acgs          Legacy alias for make publish-root-package"
	@echo ""
	@echo "  Package Health:"
	@echo "    make health-manifest Validate package health metadata"
	@echo "    make health-overview Show per-package owners, namespaces, and verification commands"
	@echo "    make health-lite    First-class acgs-lite health gate"
	@echo "    make health-bus     First-class enhanced-agent-bus health gate"
	@echo "    make health-bus-governance Governance-core slice for enhanced-agent-bus"
	@echo "    make health-bus-wrappers MessageProcessor wrapper-audit gate"
	@echo "    make health-bus-wrappers-batch1-ready Fail until Batch 1 wrappers are delete-ready"
	@echo "    make health-gw      First-class API Gateway health gate"
	@echo "    make health-constitutional-swarm First-class constitutional-swarm health gate"
	@echo "    make health-frontend First-class propriety-ai health gate"
	@echo "    make health-worker  First-class governance-proxy worker health gate"
	@echo ""
	@echo "  Code Quality:"
	@echo "    make lint         Ruff + MyPy"
	@echo "    make format       Auto-fix formatting"
	@echo "    make clean        Remove cache files"
	@echo ""
	@echo "  Dashboard:"
	@echo "    make dashboard-dev     Start dashboard dev server (port 3100)"
	@echo "    make dashboard-backend Start acgs-lite backend (port 8100)"
	@echo "    make dashboard-build   Production build"
	@echo ""
	@echo "  Benchmarks:"
	@echo "    make bench        Run acgs-lite benchmark suite"

# === Setup ===
setup: lock-sync
	@if [ "$${CI:-}" = "true" ]; then \
		echo "Skipping pre-commit install in CI"; \
	elif git config --get core.hooksPath >/dev/null 2>&1; then \
		echo "Skipping pre-commit install because git core.hooksPath is set"; \
	else \
		pre-commit install; \
	fi
	cd packages/propriety-ai && if [ "$${CI:-}" = "true" ]; then npm ci; else npm install; fi

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
	cd packages/propriety-ai && npm run test:unit || echo "WARN: propriety-ai unit tests failed (WebGL not available in headless CI)"

test-lite:
	$(PYTHON) -m pytest $(or $(PYTEST_TARGETS),packages/acgs-lite/tests/) -v --import-mode=importlib $(PYTEST_ARGS)

test-bus:
	$(PYTHON) -m pytest $(or $(PYTEST_TARGETS),packages/enhanced_agent_bus/tests/) -v --import-mode=importlib $(PYTEST_ARGS)

test-gw:
	$(PYTHON) -m pytest $(or $(PYTEST_TARGETS),src/core/services/api_gateway/tests/) -v --import-mode=importlib $(PYTEST_ARGS)

build-root-package:
	bash scripts/publish-acgs.sh --build-only

publish-root-dry-run:
	bash scripts/publish-acgs.sh --dry-run

publish-root-package:
	bash scripts/publish-acgs.sh

build-acgs-lite:
	PACKAGE_DIR=packages/acgs-lite bash scripts/publish-acgs.sh --build-only

publish-acgs-lite-dry-run:
	PACKAGE_DIR=packages/acgs-lite bash scripts/publish-acgs.sh --dry-run

publish-acgs-lite:
	PACKAGE_DIR=packages/acgs-lite bash scripts/publish-acgs.sh

build-acgs: build-root-package

publish-dry-run: publish-root-dry-run

publish-acgs: publish-root-package

health-manifest:
	$(PYTHON) scripts/package_health.py validate

health-overview: health-manifest
	$(PYTHON) scripts/package_health.py list

health-lite: test-lite

health-bus: test-bus

health-bus-governance:
	ruff check \
		packages/enhanced_agent_bus/governance_core.py \
		packages/enhanced_agent_bus/message_processor.py \
		packages/enhanced_agent_bus/verification_orchestrator.py \
		packages/enhanced_agent_bus/config.py \
		packages/enhanced_agent_bus/tests/test_governance_core.py \
		packages/enhanced_agent_bus/tests/test_config.py
	python3 -m pytest --import-mode=importlib -q \
		packages/enhanced_agent_bus/tests/test_governance_core.py \
		packages/enhanced_agent_bus/tests/test_config.py \
		packages/enhanced_agent_bus/tests/test_message_processor_coverage.py \
		packages/enhanced_agent_bus/tests/test_processor_redesign.py::TestMessageProcessorBackwardCompat \
		packages/enhanced_agent_bus/tests/test_environment_check.py \
		packages/enhanced_agent_bus/tests/test_security_defaults.py \
		packages/enhanced_agent_bus/tests/test_message_processor_independent_validator_gate.py

health-bus-wrappers:
	$(PYTHON) packages/enhanced_agent_bus/tools/message_processor_wrapper_audit.py --check
	$(PYTHON) -m ruff check \
		packages/enhanced_agent_bus/tools/message_processor_wrapper_audit.py \
		packages/enhanced_agent_bus/docs/MESSAGE_PROCESSOR_ARCHITECTURE.md \
		packages/enhanced_agent_bus/docs/MESSAGE_PROCESSOR_FINAL_ARCHITECTURE_AUDIT.md \
		packages/enhanced_agent_bus/docs/MESSAGE_PROCESSOR_COVERAGE_REGEN_CLEANUP_PLAN.md

health-bus-wrappers-batch1-ready:
	$(PYTHON) packages/enhanced_agent_bus/tools/message_processor_wrapper_audit.py --ready-batch batch1

health-gw: test-gw

health-constitutional-swarm:
	$(PYTHON) -m ruff check packages/constitutional_swarm
	$(PYTHON) -c "import constitutional_swarm"
	$(PYTHON) -m pytest --import-mode=importlib packages/constitutional_swarm/tests -v

health-frontend:
	cd packages/propriety-ai && npm run test

health-worker:
	cd workers/governance-proxy && npm run test

# === Code Quality ===
lint:
	$(PYTHON) -m ruff check --extend-exclude .codex-home .
	$(PYTHON) -m mypy \
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
		packages/acgs-lite/src/acgs_lite/compliance/__init__.py \
		packages/acgs-lite/src/acgs_lite/compliance/base.py \
		packages/acgs-lite/src/acgs_lite/compliance/multi_framework.py \
		packages/acgs-lite/src/acgs_lite/compliance/evidence.py \
		packages/acgs-lite/src/acgs_lite/compliance/report_exporter.py \
		packages/acgs-lite/src/acgs_lite/compliance/__main__.py \
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

# === Per-Rule Eval Harness ===
eval-rules:
	$(PYTHON) autoresearch/eval_rules.py --output-dir eval_results

eval-rules-generate:
	$(PYTHON) autoresearch/eval_rules.py --generate

# === ACGS Core ===
test-core:
	$(PYTHON) -m pytest packages/acgs-core/tests/ -v --import-mode=importlib

# === Dashboard ===
dashboard-install:
	cd packages/acgs-dashboard && npm install

dashboard-dev:
	cd packages/acgs-dashboard && npm run dev

dashboard-build:
	cd packages/acgs-dashboard && npm run build

dashboard-backend:
	$(PYTHON) packages/acgs-dashboard/scripts/start-backend.py

# === Codex Bootstrap ===
codex-doctor:
	bash ./scripts/codex-doctor.sh

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
