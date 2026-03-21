# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## What This Is

ACGS is a multi-package governance codebase:

- **acgs-lite** (`packages/acgs-lite/`) — standalone governance library with optional Rust
  acceleration and integration adapters.
- **enhanced_agent_bus** (`packages/enhanced_agent_bus/`) — platform runtime with MACI,
  constitutional workflows, MCP, persistence, observability, and service integrations.
- **Shared services** (`src/core/`) — API gateway plus shared auth, config, logging, and
  security code.
- **Frontend and edge** (`packages/propriety-ai/`, `workers/governance-proxy/`) — SvelteKit UI
  and a Cloudflare Worker proxy.

Constitutional hash: `cdd01ef066bc6cf2`.

Primary languages: Python first, TypeScript second, Rust for hot paths, Markdown for operating
docs.

### When to Use Rust

Use Rust when the change is clearly CPU-bound, latency-sensitive, or benefits from stronger type
and memory guarantees. `packages/acgs-lite/rust/` is the main Rust workspace. Keep a Python
fallback when the Rust path is optional.

## Commands

```bash
# Setup
make setup

# Testing (--import-mode=importlib is required for repository pytest runs)
make test
make test-quick
make test-lite
make test-bus
make test-gw

# Coverage
make cov
make cov-html

# Targeted pytest
python -m pytest packages/acgs-lite/tests/ -v --import-mode=importlib
python -m pytest packages/enhanced_agent_bus/tests/ -v --import-mode=importlib
python -m pytest src/core/services/api_gateway/tests/ -v --import-mode=importlib

# Code quality
make lint
make format
make clean

# Benchmarks
make bench

# acgs-lite Rust build
cd packages/acgs-lite/rust && maturin develop --release
```

Notes:
- `make test` and `make test-quick` also run `packages/propriety-ai` npm test scripts.
- `make lint` runs Ruff across the repo, scoped MyPy checks, and the frontend type/lint checks.

## Codex CLI

Use Codex from the repository root:

```bash
codex -C /home/martin/Documents/acgs-clean --sandbox workspace-write --ask-for-approval on-request

codex exec -C /home/martin/Documents/acgs-clean --sandbox workspace-write --full-auto \
  "Fix failing imports in enhanced_agent_bus and run make test-quick"

codex exec -C /home/martin/Documents/acgs-clean --json \
  "Run make lint and summarize errors with file:line references"
```

Preferred defaults:
- `--sandbox workspace-write`
- `--ask-for-approval on-request`
- `--full-auto` only for bounded, non-destructive tasks
- `--model gpt-5.4` for governance/security-critical changes
- `--model gpt-5.3-codex` for broad refactors and mechanical fixes

Avoid:
- `--dangerously-bypass-approvals-and-sandbox`
- Running Codex outside repo root

## Architecture

### Package Relationships

```
pyproject.toml (root workspace, uv)
├── packages/acgs-lite/            -> import acgs_lite
├── packages/enhanced_agent_bus/   -> import enhanced_agent_bus
├── packages/propriety-ai/         -> SvelteKit frontend
├── workers/governance-proxy/      -> Cloudflare Worker
└── src/core/
    ├── services/api_gateway/      -> FastAPI service
    └── shared/                    -> import src.core.shared
```

Use `enhanced_agent_bus.*` directly. Do not invent `src.core.enhanced_agent_bus.*` import paths.

### MACI Separation of Powers

Agents never validate their own output.

- **Proposer** submits actions or amendments.
- **Validator** independently evaluates constitutional compliance.
- **Executor** performs approved actions.

Core enforcement lives in the enhanced agent bus and its middleware/governance paths.

### Key Entry Points

| Service | Entry Point | Port |
| ------- | ----------- | ---- |
| Agent Bus | `start_agent_bus.py` | 8000 |
| Enhanced Agent Bus package entry | `packages/enhanced_agent_bus/api/__main__.py` | 8000 |
| API Gateway | `src/core/services/api_gateway/main.py` | 8080 |
| Governance Proxy | `workers/governance-proxy/src/index.ts` | Worker |

`ecosystem.config.cjs` is present, but some referenced service launchers are not checked in. Treat
it as deployment intent, not guaranteed runtime truth.

### Canonical Module Paths (enhanced-agent-bus)

Prefer `middlewares/`, `context_memory/`, `persistence/`, and `saga_persistence/`.
Legacy paths such as `middleware/` and `context/` still appear in compatibility scenarios and
should not be used for new code.

### Extension Modules

`packages/enhanced_agent_bus/_ext_*.py` files wrap optional dependencies behind lazy imports and
availability flags. Follow the existing fallback pattern when adding new optional integrations.

## Conventions

- Python 3.11+ at the repo level; `acgs-lite` itself supports Python 3.10+.
- Use `X | Y` unions and explicit type annotations.
- Use `async def` for I/O code.
- Use `structlog`, not `print()`, in production paths.
- Use Pydantic models at API boundaries.
- Import `Priority` from `enhanced_agent_bus.models`; avoid deprecated or compatibility aliases in
  new code.
- `make lint` uses a scoped MyPy invocation; package-level MyPy settings still exist in individual
  `pyproject.toml` files.

## Testing

Use `python -m pytest ... --import-mode=importlib` for repository-level runs.

Root pytest markers:
`unit`, `integration`, `slow`, `constitutional`, `benchmark`, `governance`, `security`, `maci`,
`chaos`, `pqc`

Package-level `pyproject.toml` files define additional markers where needed.

## Workflow

- After code changes, run the narrowest meaningful verification first, then expand if the change
  touches shared or critical paths.
- Scope lint/test commands to changed areas before paying for a full repo run.
- Do not commit known failures unless the user explicitly asks for a partial checkpoint.

## Environment

- Root `conftest.py` sets default test env values including `ACGS2_SERVICE_SECRET`.
- PM2 service env is defined in `ecosystem.config.cjs`.
- Root coverage threshold is `fail_under = 70`.
- `packages/enhanced_agent_bus/pyproject.toml` raises coverage threshold to `80` for that package.

## Pre-commit Hooks

`make setup` installs pre-commit hooks and frontend dependencies. Expect formatting and secret
checks to run on commit.

## Sub-Package Instructions

See `packages/acgs-lite/CLAUDE.md` and `packages/enhanced_agent_bus/CLAUDE.md` for package-level
guidance.
