.PHONY: help setup test test-quick test-lite test-bus test-gw lint format clean bench codex-doctor autoresearch-promote agent-commit

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

# === Testing ===
test:
	$(PYTHON) -m pytest --import-mode=importlib -v

test-quick:
	$(PYTHON) -m pytest --import-mode=importlib -m "not slow" -x -v

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
		src/core/cognitive/graphrag/factory.py \
		src/core/shared/cache/__init__.py \
		src/core/shared/cache/l1.py \
		src/core/shared/cache/manager.py \
		src/core/shared/cache/metrics.py \
		src/core/shared/cache/models.py \
		src/core/shared/cache/warming.py \
		src/core/shared/cache/workflow_state.py \
		src/core/shared/acgs_logging/__init__.py \
		src/core/shared/acgs_logging/agent_workflow_events.py \
		src/core/shared/acgs_logging/audit_logger.py \
		src/core/shared/agent_workflow_metrics.py \
		src/core/shared/audit_client.py \
		src/core/shared/fastapi_base.py \
		src/core/shared/json_utils.py \
		src/core/shared/metrics/_registry.py \
		src/core/shared/errors/logging.py \
		src/core/shared/auth/certs/generate_certs.py \
		src/core/shared/utilities/config_merger.py \
		src/core/shared/utilities/dependency_registry.py \
		src/core/shared/utilities/tenant_normalizer.py \
		src/core/shared/schema_registry.py \
		src/core/shared/security/auth.py \
		src/core/shared/security/auth_dependency.py \
		src/core/shared/security/cors_config.py \
		src/core/shared/security/rate_limiter.py \
		src/core/shared/security/tenant_context.py \
		src/core/shared/security/token_revocation.py \
		src/core/shared/security/deserialization.py \
		src/core/shared/security/execution_time_limit.py \
		src/core/shared/types/protocol_types.py \
		src/core/services/api_gateway/main.py \
		src/core/services/api_gateway/health.py \
		src/core/services/api_gateway/arcjet_protection.py \
		src/core/services/api_gateway/metrics.py \
		src/core/services/api_gateway/redis_backend.py \
		src/core/services/api_gateway/workos_event_ingestion.py \
		packages/enhanced_agent_bus/__init__.py \
		packages/enhanced_agent_bus/agent_bus.py \
		packages/enhanced_agent_bus/ab_testing.py \
		packages/enhanced_agent_bus/acl_adapters/__init__.py \
		packages/enhanced_agent_bus/adapters/__init__.py \
		packages/enhanced_agent_bus/adaptive_governance/__init__.py \
		packages/enhanced_agent_bus/agent_health/__init__.py \
		packages/enhanced_agent_bus/constitutional/__init__.py \
		packages/enhanced_agent_bus/mcp/__init__.py \
		packages/enhanced_agent_bus/multi_tenancy/__init__.py \
		--ignore-missing-imports \
		--follow-imports skip

format:
	ruff check --fix .
	ruff format .

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
