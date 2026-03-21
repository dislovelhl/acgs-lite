# ACGS-2 Developer Guide

> Advanced Constitutional Governance System — constitutional governance infrastructure for AI agents.
> This guide is for engineers onboarding to the project.

Constitutional hash: `cdd01ef066bc6cf2` — this value is embedded in all validation paths and must
never be changed without a full refoundation protocol.

---

## 1. Getting Started

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Runtime for all packages |
| uv | latest | Workspace dependency manager |
| Node.js | 18+ | PM2 process manager |
| PM2 | latest | Service orchestration (`npm install -g pm2`) |
| Rust + Cargo | stable | Optional: PyO3 extension for 100-1000x validation speedup |
| maturin | latest | Optional: Build Rust/PyO3 extension (`pip install maturin`) |

### First-time setup

```bash
# 1. Clone and enter the repo
git clone <repo-url> acgs-clean
cd acgs-clean

# 2. Install all Python dependencies and pre-commit hooks
make setup

# This is equivalent to:
#   pip install -e ".[dev,test]"
#   pip install -e packages/acgs-lite[dev]
#   pip install -e packages/enhanced_agent_bus[dev]
#   pre-commit install
```

### Verify the setup

```bash
# Run the fast test suite — should pass entirely
make test-quick

# Run the linter — should produce no errors
make lint
```

If both pass, your environment is working.

### Optional: Rust extension

The Rust/PyO3 extension drops validation latency from microseconds to 560ns P50. It is not
required to run tests or services, but is strongly recommended for benchmarks and production.

```bash
cd packages/acgs-lite/rust
maturin develop --release
```

---

## 2. Project Layout

```
acgs-clean/
├── packages/
│   ├── acgs-lite/                  # Standalone governance library
│   │   ├── src/acgs_lite/
│   │   │   ├── constitution/       # Rule, Constitution, analytics, metrics, versioning
│   │   │   ├── engine/             # Validation engine (Python + optional Rust backend)
│   │   │   ├── maci.py             # MACI role enforcement
│   │   │   ├── compliance/         # Compliance mapping, regulatory alignment
│   │   │   └── eu_ai_act/          # EU AI Act risk classification
│   │   ├── rust/src/               # PyO3 native extension (6 modules)
│   │   │   ├── validator.rs        # Core rule validation
│   │   │   ├── severity.rs         # Severity enum + ordering
│   │   │   ├── verbs.rs            # Action verb parsing
│   │   │   ├── result.rs           # Validation result types
│   │   │   ├── context.rs          # Governance context
│   │   │   └── hash.rs             # Constitutional hash computation
│   │   └── tests/
│   └── enhanced_agent_bus/         # Platform engine with 80+ subsystems
│       ├── agent_bus.py            # Core bus entry point
│       ├── api/app.py              # FastAPI application (port 8000)
│       ├── maci/enforcer.py        # MACI role enforcement
│       ├── middlewares/            # Use this path (plural) — NOT middleware/
│       │   └── batch/governance.py # MACI enforcement lives here
│       ├── context_memory/         # Canonical path
│       ├── persistence/            # Canonical path
│       ├── _ext_*.py               # 15 optional extension modules (try/except fallback)
│       └── tests/
├── src/core/
│   ├── services/
│   │   └── api_gateway/            # FastAPI on port 8080
│   └── shared/                     # Shared types, auth, config, structured logging
│       └── constants.py            # CONSTITUTIONAL_HASH defined here
├── tests/                          # Root-level integration tests
├── autoresearch/                   # Governance-quality experiment loop
├── scripts/
│   └── agent-commit.sh             # MACI-attributed commit helper
├── .github/workflows/ci.yml        # CI: lint + test-quick on PR, test-full on main
├── docker-compose.yml              # Local infrastructure: Redis, OPA
├── ecosystem.config.cjs            # PM2 service configuration for checked-in local services
├── pyproject.toml                  # Root workspace, uv, ruff, mypy, pytest config
├── Makefile                        # All development commands
├── conftest.py                     # Root pytest config: sys.path, env defaults
└── .pre-commit-config.yaml         # trailing-whitespace, ruff, detect-secrets
```

### Import paths — the two rules

1. Import `enhanced_agent_bus` directly. Never use `src.core.enhanced_agent_bus.*`:

   ```python
   # Correct
   from enhanced_agent_bus.models import Priority
   from enhanced_agent_bus.agent_bus import EnhancedAgentBus
   from enhanced_agent_bus.maci.enforcer import MACIRole

   # Wrong — Phase 3 extraction removed this path
   from src.core.enhanced_agent_bus.models import Priority
   ```

2. Use the canonical plural module paths in `enhanced_agent_bus`:

   ```python
   # Correct
   from enhanced_agent_bus.middlewares.batch.governance import ...
   from enhanced_agent_bus.context_memory import ...
   from enhanced_agent_bus.persistence import ...

   # Wrong — deprecated shims exist but must not be used in new code
   from enhanced_agent_bus.middleware.batch.governance import ...
   ```

---

## 3. Development Workflow

### Branch strategy

| Branch pattern | Purpose |
|---------------|---------|
| `main` | Protected. Requires passing CI. Full test suite runs on merge. |
| `feat/<name>` | New features |
| `fix/<name>` | Bug fixes |
| `refactor/<name>` | Refactoring without behavior change |

CI triggers `lint` + `test-quick` on all branches. The full suite (`test`) runs only on `main`.

### Commit conventions

```
<type>: <short description>

<optional body>
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`

### Agent-attributed commits

When committing as an agent with a MACI role, use the commit helper instead of `git commit`:

```bash
make agent-commit MSG="feat: add governance rule" AGENT=claude-code ROLE=proposer
make agent-commit MSG="fix: correct validation path" AGENT=codex ROLE=validator
```

This stamps `ACGS_AGENT_ID` and `ACGS_MACI_ROLE` in the commit metadata via
`scripts/agent-commit.sh`.

### PR process

1. Create a branch from `main`.
2. Run `make test-quick && make lint` locally before pushing.
3. Open a PR against `main`. CI runs `lint` and `test-quick` automatically.
4. For governance-critical changes, request an independent reviewer pass before merging.

---

## 4. Testing Reference

### Make targets

| Target | Command run | When to use |
|--------|------------|-------------|
| `make test` | `pytest --import-mode=importlib -v` | Full gate before merging to main; runs ~3,820 tests |
| `make test-quick` | `pytest --import-mode=importlib -m "not slow" -x -v` | Default during development; fast feedback loop |
| `make test-lite` | `pytest packages/acgs-lite/tests/ ...` | When working only in the acgs-lite package |
| `make test-bus` | `pytest packages/enhanced_agent_bus/tests/ ...` | When working only in the agent bus (3,534 tests) |
| `make test-gw` | `pytest src/core/services/api_gateway/tests/ ...` | When working only in the API gateway |
| `make cov` | `pytest --cov --cov-report=term-missing -m "not slow" -x` | Check coverage in the terminal |
| `make cov-html` | `pytest --cov --cov-report=html -m "not slow"` | Generate HTML coverage at `htmlcov/index.html` |
| `make bench` | `pytest packages/acgs-lite/tests/ -m benchmark ...` | Run performance benchmarks (acgs-lite) |

### The required flag: `--import-mode=importlib`

Every pytest invocation in this project requires `--import-mode=importlib`. This is configured as
a default in `pyproject.toml` (`addopts = "--import-mode=importlib"`), so `make test*` targets
include it automatically.

If you run pytest directly, always include it:

```bash
python -m pytest packages/acgs-lite/tests/test_engine.py -v --import-mode=importlib
```

Omitting it causes incorrect module resolution across the workspace.

### Pytest markers

Use `-m` to filter test runs. Multiple markers can be combined with `and`/`not`/`or`.

| Marker | What it covers | Typical run time |
|--------|---------------|-----------------|
| `unit` | Single functions and classes in isolation | Fast |
| `integration` | API endpoints, database operations, cross-module flows | Medium |
| `slow` | Tests that take several seconds each | Slow — skipped by `test-quick` |
| `constitutional` | Constitutional policy validation, rule evaluation | Fast–medium |
| `benchmark` | Performance benchmarks with `pytest-benchmark` | Medium |
| `governance` | Critical governance path tests | Medium |
| `security` | Auth, secret handling, permission validation | Fast |
| `maci` | MACI role enforcement, proposer/validator/executor separation | Fast |
| `chaos` | Chaos engineering — fault injection, resilience | Slow |
| `pqc` | Post-quantum cryptography tests (requires `liboqs-python`) | Medium |
| `e2e` | End-to-end flows spanning multiple services | Slow |
| `compliance` | Regulatory compliance verification | Medium |

Examples:

```bash
# Only unit tests
python -m pytest -m unit -v --import-mode=importlib

# Skip slow and chaos tests
python -m pytest -m "not slow and not chaos" -v --import-mode=importlib

# Only MACI and governance tests
python -m pytest -m "maci or governance" -v --import-mode=importlib
```

### Writing new tests

**File locations:**

| Code location | Test location |
|--------------|--------------|
| `packages/acgs-lite/src/` | `packages/acgs-lite/tests/` |
| `packages/enhanced_agent_bus/` | `packages/enhanced_agent_bus/tests/` |
| `src/core/services/api_gateway/` | `src/core/services/api_gateway/tests/` |
| `src/core/shared/` | `src/core/shared/tests/` |

**Naming:** Files must be `test_*.py`, classes `Test*`, functions `test_*`.

**Async tests:** All async tests work without decoration because `asyncio_mode = "auto"` is set
globally in `pyproject.toml`.

**Minimum pattern for a new test module:**

```python
import pytest


@pytest.mark.unit
def test_basic_behavior() -> None:
    # Arrange
    ...
    # Act
    result = function_under_test(input)
    # Assert
    assert result == expected


@pytest.mark.unit
async def test_async_behavior() -> None:
    result = await async_function()
    assert result is not None
```

**fakeredis for Redis-dependent tests:**

```python
import fakeredis.aioredis
import pytest


@pytest.fixture
async def redis_client():
    return fakeredis.aioredis.FakeRedis()
```

### Coverage thresholds

The `[tool.coverage.report]` in `pyproject.toml` sets `fail_under = 70`. CI runs `make test`
on `main`, which will fail if overall coverage drops below 70%. The project memory notes a prior
target of 40% that was raised; do not lower the threshold.

Coverage sources are:
- `src/`
- `packages/enhanced_agent_bus/`
- `packages/acgs-lite/src/`

---

## 5. Code Quality

### Linting with ruff

```bash
make lint       # Check only
make format     # Auto-fix and format
```

`make lint` runs `ruff check` followed by a targeted `mypy` invocation. `make format` runs
`ruff check --fix` then `ruff format`.

Key ruff settings (`pyproject.toml`):

| Setting | Value |
|---------|-------|
| Line length | 100 |
| Target Python | 3.11 |
| Rule sets | E, F, W, I (isort), B (bugbear), UP (pyupgrade), BLE, S (security), RUF, C90 |
| Ignored | E501 (line length — handled by formatter), B008, S101, E402, C901 |
| Max complexity | 15 (McCabe) |

Test files relax security rules S105/S106/S108 (hardcoded passwords) and a few others — this is
intentional and expected for test fixtures.

### Type checking with mypy

mypy is in strict mode for `src/` only. The `enhanced_agent_bus` package is excluded from mypy
checking (too many dynamic patterns). The `make lint` target runs mypy against a specific list of
files rather than entire directories — see `Makefile` for the current list.

If you add new modules to `src/core/shared/` or `src/core/services/`, add them to the mypy
invocation in `Makefile`.

### Pre-commit hooks

Hooks run automatically on `git commit`. To run them manually:

```bash
pre-commit run --all-files
```

Active hooks:

| Hook | What it checks |
|------|---------------|
| `trailing-whitespace` | No trailing whitespace |
| `end-of-file-fixer` | Files end with a newline |
| `check-yaml` | YAML syntax |
| `check-toml` | TOML syntax |
| `check-added-large-files` | No files over 500KB |
| `ruff` | Lint + auto-fix (exits non-zero if it fixes anything — re-stage and commit again) |
| `ruff-format` | Code formatting |
| `detect-secrets` | No hardcoded secrets (baseline: `.secrets.baseline`) |

If `ruff` auto-fixes something during a commit, the commit will be aborted. Stage the fixes and
commit again.

---

## 6. Local Service Stack

### Infrastructure (docker-compose)

Start the infrastructure dependencies before running services locally:

```bash
docker compose up -d redis opa
```

| Service | Port | Purpose |
|---------|------|---------|
| `redis` | 6379 | Message queues, caching, saga state |
| `opa` | 8181 | Open Policy Agent — policy decision point |

Both have health checks. `agent-bus` in docker-compose depends on Redis being healthy before
starting.

### Application services (PM2)

```bash
pm2 start ecosystem.config.cjs          # Start checked-in local services
pm2 start ecosystem.config.cjs --only agent-bus-8000   # Start one service
pm2 stop all
pm2 restart all
pm2 logs                                 # Tail all logs
pm2 logs agent-bus-8000                  # Tail one service
pm2 monit                                # Live dashboard
pm2 status                               # Service status table
```

| PM2 name | Port | Purpose |
|----------|------|---------|
| `agent-bus-8000` | 8000 | Enhanced Agent Bus — core messaging, MACI enforcement |
| `api-gateway-8080` | 8080 | Unified ingress, auth, rate limiting |

Historical docs and old PM2 logs may still mention `arch-fitness`, `analytics-api`, `x402-api`,
`eu-ai-act`, and `mistral`. Those are not part of the current checked-in `ecosystem.config.cjs`.

### Minimal local stack for development

For most feature work, you only need:

```bash
docker compose up -d redis opa
pm2 start ecosystem.config.cjs --only agent-bus-8000
pm2 start ecosystem.config.cjs --only api-gateway-8080
```

---

## 7. Environment Variables

### Required for running services

| Variable | Example value | Required by |
|----------|--------------|-------------|
| `CONSTITUTIONAL_HASH` | `cdd01ef066bc6cf2` | All services — must match exactly |
| `MACI_STRICT_MODE` | `true` | `agent-bus` |
| `REDIS_URL` | `redis://localhost:6379/0` | `agent-bus` |
| `OPA_URL` | `http://localhost:8181` | `agent-bus` |
| `JWT_SECRET` | (generate a secret) | `api-gateway` |
| `AGENT_BUS_URL` | `http://localhost:8000` | `api-gateway` |
| `ACGS2_SERVICE_SECRET` | (32+ character string) | All services — inter-service auth |
| `SERVICE_JWT_ALGORITHM` | `HS256` | All services |

### Auto-set in tests

The root `conftest.py` sets these defaults so you do not need them in `.env` when running tests:

```
ACGS2_SERVICE_SECRET = "test-service-secret-key-that-is-at-least-32-characters-long"
SERVICE_JWT_ALGORITHM = "HS256"
```

### PYTHONPATH for services

PM2 sets `PYTHONPATH` to both the project root and `src/`. When running services outside PM2,
set it manually:

```bash
export PYTHONPATH="/path/to/acgs-clean:/path/to/acgs-clean/src"
```

---

## 8. Codex Delegation

### When to use Claude Code vs Codex

| Task | Use |
|------|-----|
| Architecture decisions | Claude Code |
| MACI/constitutional invariants | Claude Code |
| Security sign-off | Claude Code |
| Final merge approval | Claude Code |
| Scoped implementation (a single file, a specific function) | Codex |
| Mechanical refactors across many files | Codex |
| Test fixes with explicit acceptance criteria | Codex |
| Running build validation in CI-like conditions | Codex |

This follows MACI separation of duties: Claude Code acts as the proposer and validator for
architecture; Codex acts as the proposer for implementation chunks; Claude Code validates
Codex output before merge.

### Codex invocation

```bash
# Interactive session — ask for approval before each action
codex -C /home/martin/Documents/acgs-clean --sandbox workspace-write --ask-for-approval on-request

# Non-interactive scoped task
codex exec -C /home/martin/Documents/acgs-clean --sandbox workspace-write --full-auto \
  "Fix failing imports in enhanced_agent_bus and run make test-quick"

# JSON output for pipelines
codex exec -C /home/martin/Documents/acgs-clean --json \
  "Run make lint and summarize errors with file:line references"
```

Always invoke Codex from the project root (`-C /path/to/acgs-clean`). Never use
`--dangerously-bypass-approvals-and-sandbox`.

### Handoff template from Claude to Codex

```text
Scope: <one bounded change — single file, single module>
Constraints: Python 3.11+, ruff line-length 100, use middlewares/ (plural), no src.core.enhanced_agent_bus.* imports
Required checks: make lint && make test-quick --import-mode=importlib
Deliverable: unified diff + brief risk note
```

For governance-critical changes, run an independent reviewer pass (`codex review` or a separate
Claude session) before merging.

---

## 9. MACI Invariants

MACI (Multi-Agent Constitutional Invariants) enforces that **agents never validate their own
output**. These rules are enforced at the middleware level and must not be bypassed.

### The three roles

| Role | Responsibility |
|------|---------------|
| **Proposer** | Submits content or a change for consideration |
| **Validator** | Independently evaluates the proposal — must be a different agent than the proposer |
| **Executor** | Acts on validated decisions |

### Where enforcement lives

Enforcement is in `packages/enhanced_agent_bus/middlewares/batch/governance.py`. There is no
`maci_metrics.py` — it was deleted. Do not recreate it.

### What you must never break

1. An agent must not appear as both Proposer and Validator for the same decision.
2. The `middlewares/` (plural) path is canonical. New code must not import from `middleware/` (singular).
3. The constitutional hash `cdd01ef066bc6cf2` must be present and unchanged in all validation
   paths. It is embedded in `conftest.py`, `docker-compose.yml`, `ecosystem.config.cjs`, and
   `src/core/shared/constants.py`.
4. MACI enforcement must remain at the middleware layer, not in individual agent logic.

### Constitutional hash in tests

The hash is imported and verified in the root `conftest.py`:

```python
from src.core.shared.constants import CONSTITUTIONAL_HASH
```

If `src/core/shared/constants.py` is missing or the hash differs, the entire test suite will fail
to import.

---

## 10. Common Pitfalls

### Import errors on first run

**Symptom:** `ModuleNotFoundError: No module named 'enhanced_agent_bus'`

**Fix:** Run `make setup` from the project root. All three packages must be installed as editable
installs (`-e`).

### pytest fails without `--import-mode=importlib`

**Symptom:** Tests that import across packages fail with `ImportError` or import the wrong module.

**Fix:** Always use `--import-mode=importlib`. It is set as a default in `pyproject.toml`, but if
you invoke pytest with a custom command that overrides `addopts`, you must add it manually.

### `src.core.enhanced_agent_bus` import fails

**Symptom:** `ModuleNotFoundError: No module named 'src.core.enhanced_agent_bus'`

**Fix:** Use `enhanced_agent_bus.*` directly. Phase 3 extraction moved the package out of `src/`.

### `MessagePriority` not found

**Symptom:** `ImportError: cannot import name 'MessagePriority'`

**Fix:** Use `Priority` from `enhanced_agent_bus.models`. `MessagePriority` is deprecated and
removed.

### Constitutional hash mismatch

**Symptom:** Services refuse to start or validation always fails.

**Fix:** All services and tests expect `CONSTITUTIONAL_HASH=cdd01ef066bc6cf2`. Check
`ecosystem.config.cjs`, `docker-compose.yml`, and your local environment. Never change this
value without a full refoundation protocol.

### ruff commit hook aborts the commit

**Symptom:** `git commit` fails with ruff auto-fixing files.

**Fix:** ruff made fixes. Stage them with `git add <files>` and run `git commit` again. This is
expected behavior — the hook uses `--exit-non-zero-on-fix`.

### ACGS2_SERVICE_SECRET too short

**Symptom:** Auth middleware raises a validation error during startup or tests.

**Fix:** The secret must be at least 32 characters. The test default in `conftest.py` satisfies
this. For local service runs outside of tests, set a 32+ character value.

### Rust extension not found (acgs-lite)

**Symptom:** acgs-lite validation runs but is slower than expected; no error, just pure Python.

**Explanation:** The Rust extension is optional. The Python fallback activates automatically.
To enable the Rust backend, run `cd packages/acgs-lite/rust && maturin develop --release`.

### mypy errors in enhanced_agent_bus

**Explanation:** The `enhanced_agent_bus` package is excluded from mypy (too many dynamic
patterns). If mypy reports errors in that package, check whether the file was accidentally added
to the mypy invocation in `Makefile`. It should not be there.

### cargo audit failures

**Explanation:** Four CVEs are intentionally ignored in CI for the acgs-lite Rust crate:
`RUSTSEC-2025-0123`, `RUSTSEC-2024-0387`, `RUSTSEC-2024-0436`, `RUSTSEC-2025-0134`. If `cargo
audit` fails on one of these, it is a known and accepted risk. Any other CVE should be
investigated immediately.
