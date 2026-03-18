.PHONY: help setup test test-quick test-lite test-bus test-gw lint format clean bench codex-doctor

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
	ruff check --exclude .codex-home .
	mypy src/ packages/ --ignore-missing-imports

format:
	ruff check --fix .
	ruff format .

# === Benchmarks ===
bench:
	cd packages/acgs-lite && $(PYTHON) -m pytest tests/ -m benchmark -v --import-mode=importlib

# === Codex Bootstrap ===
codex-doctor:
	bash ./.agents/skills/acgs-codex-bootstrap/scripts/codex-doctor.sh

# === Cleanup ===
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".coverage" -delete 2>/dev/null || true
