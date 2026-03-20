# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

ACGS (Advanced Constitutional Governance System) — constitutional governance infrastructure for AI agents. Three domains:

- **acgs-lite** (`packages/acgs-lite/`) — Standalone governance library. The public API: `Constitution.from_yaml()` + `GovernedAgent()`. Python + optional Rust/PyO3 backend (560ns P50 validation).
- **enhanced-agent-bus** (`packages/enhanced_agent_bus/`) — Platform engine with 80+ subsystems: MACI enforcement, constitutional amendments, deliberation, MCP server, OPA integration, circuit breakers, saga persistence.
- **Shared services** (`src/core/`) — API gateway (port 8080), shared types, auth, config, structured logging.

Constitutional hash: `cdd01ef066bc6cf2` — embedded in all validation paths.

Primary languages: Python (primary), TypeScript (secondary), Markdown (docs), Rust (occasional). Default to Python unless otherwise specified.

### When to Use Rust

Use Rust (via PyO3) whenever the implementation would meaningfully benefit from it — performance-critical paths, CPU-bound computation, memory-sensitive data structures, or where Rust's type system prevents classes of bugs. The existing extension lives in `packages/acgs-lite/rust/`. Every Rust function must have a pure-Python fallback so the extension remains optional.

## Commands

```bash
# Setup
make setup                    # Install all deps + pre-commit hooks

# Testing (--import-mode=importlib is REQUIRED for all pytest)
make test                     # Full suite (~3,820 tests)
make test-quick               # Skip slow tests (-m "not slow" -x)
make test-lite                # acgs-lite only (286 tests)
make test-bus                 # enhanced-agent-bus only (3,534 tests)
make test-gw                  # API gateway only

# Single test file
python -m pytest packages/acgs-lite/tests/test_engine.py -v --import-mode=importlib

# Single test
python -m pytest packages/acgs-lite/tests/test_engine.py::test_name -v --import-mode=importlib

# Code quality
make lint                     # ruff check + mypy
make format                   # ruff fix + ruff format

# Benchmarks
make bench                    # acgs-lite benchmark suite

# Rust extension (optional, 100-1000x speedup)
cd packages/acgs-lite/rust && maturin develop --release
```

## Codex CLI

Use Codex for bounded, high-throughput implementation and validation tasks from project root:

```bash
# Interactive Codex session in this repo
codex -C /home/martin/Documents/acgs-clean --sandbox workspace-write --ask-for-approval on-request

# Non-interactive execution for scoped tasks
codex exec -C /home/martin/Documents/acgs-clean --sandbox workspace-write --full-auto \
  "Fix failing imports in enhanced_agent_bus and run make test-quick"

# JSON output mode for automation/pipelines
codex exec -C /home/martin/Documents/acgs-clean --json \
  "Run make lint and summarize errors with file:line references"
```

Preferred Codex defaults for this project:
- `--sandbox workspace-write` (safe default with editable workspace)
- `--ask-for-approval on-request` for interactive sessions
- `--full-auto` only for scoped non-destructive tasks
- `--model gpt-5.4` for governance/security-critical work
- `--model gpt-5.3-codex` for mechanical refactors, test fixes, and codebase-wide edits

Avoid for normal workflows:
- `--dangerously-bypass-approvals-and-sandbox`
- Running Codex from a directory other than repo root (`-C /home/martin/Documents/acgs-clean`)

### Claude Code ↔ Codex Delegation Pattern

Use MACI-style separation of duties: proposer and validator should be different agents.

- Claude Code owns architecture, constitutional/MACI invariants, security sign-off, and final merge.
- Codex owns scoped implementation chunks with explicit acceptance criteria and commands.
- Claude validates Codex output with targeted checks (`make lint`, `make test-quick`, package-level tests).
- For governance-critical paths, run an independent reviewer pass (`codex review` or Claude review) before merge.

Recommended handoff template from Claude to Codex:

```text
Scope: <one bounded change>
Constraints: Python 3.11+, ruff line-length 100, no middleware/ singular imports
Required checks: <exact commands, include --import-mode=importlib for pytest>
Deliverable: unified diff + brief risk note
```

## Architecture

### Package Relationships

```
pyproject.toml (root workspace, uv)
├── packages/acgs-lite/          → import acgs_lite
├── packages/enhanced_agent_bus/ → import enhanced_agent_bus
└── src/core/
    ├── services/api_gateway/    → FastAPI on port 8080
    └── shared/                  → import src.core.shared
```

Never import as `src.core.enhanced_agent_bus.*` — use `enhanced_agent_bus.*` directly (Phase 3 extraction complete).

### MACI Separation of Powers

Agents NEVER validate their own output. Three roles enforced at middleware level:
- **Proposer** — submits content
- **Validator** — independent evaluation
- **Executor** — acts on validated decisions

Enforcement lives in `middlewares/batch/governance.py`, not in any `maci_metrics.py` (deleted).

### Key Entry Points

| Service | Entry Point | Port |
|---------|------------|------|
| Agent Bus | `enhanced_agent_bus.api.app:app` | 8000 |
| API Gateway | `src/core/services/api_gateway/main.py` | 8080 |
| PM2 config | `ecosystem.config.cjs` | 7 services |

### Canonical Module Paths (enhanced-agent-bus)

Use `middlewares/` (plural), `context_memory/`, `persistence/`. Deprecated singular paths have shims but should not be used in new code.

### Extension Modules

15 `_ext_*.py` modules provide optional features (cache warming, chaos, circuit breaker, MCP, PQC, etc.) via try/except fallback patterns.

## Conventions

- **Python 3.11+**, union syntax `X | Y`, explicit types everywhere
- **Line length**: 100 (ruff)
- **Async**: `async def` for all I/O operations
- **Logging**: `structlog` only, never `print()` in production
- **Validation**: Pydantic models at API boundaries
- **Imports**: `from enhanced_agent_bus.models import Priority` (not `MessagePriority`, deprecated)
- **mypy**: strict mode for `src/`, excluded for `enhanced_agent_bus` package

## Testing

When running tests, always verify the correct import paths and module invocation before running coverage or test suites. Use `python -m pytest <path>` format to avoid import shadowing issues.

## Test Markers

`unit`, `integration`, `slow`, `constitutional`, `benchmark`, `governance`, `security`, `maci`, `chaos`, `pqc`, `e2e`, `compliance`

## Workflow / Commit Guidelines

After making code changes, run the full test suite ONCE and fix all failures before committing. Do not commit with known test failures unless explicitly asked.

## Code Quality

When using linters (mypy, ruff, eslint), scope checks to changed files first before expanding. Add `# noqa` or `# type: ignore` comments for re-exports that linters incorrectly flag as unused.

## Git Workflow

When cherry-picking or rebasing multiple commits, always use a one-at-a-time approach with conflict resolution rather than batch --no-commit mode.

## Environment

Tests auto-set `ACGS2_SERVICE_SECRET` via root `conftest.py`. For running services, see `ecosystem.config.cjs` for required env vars (`CONSTITUTIONAL_HASH`, `MACI_STRICT_MODE`, `OPA_URL`, `REDIS_URL`).

## Sub-Package Instructions

See `packages/acgs-lite/CLAUDE.md` and `packages/enhanced_agent_bus/CLAUDE.md` for package-specific details.
