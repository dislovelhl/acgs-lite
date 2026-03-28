# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Language & Style

Primary languages: Python (primary), TypeScript (secondary), Rust (permissive — don't be overly
restrictive), Markdown (docs). Always use type hints in Python and run mypy only on files known
to pass.

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

Constitutional hash: `608508a9bd224290` — the SHA-256 of the default constitutional rule set,
used as both `Constitution.default().hash` and the platform constant in
`src/core/shared/constants.py`.

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
python -m pytest src/core/shared/security/tests/ -v --import-mode=importlib

# Code quality
make lint
make format
make clean

# Benchmarks
make bench

# acgs-lite Rust build
cd packages/acgs-lite/rust && maturin develop --release
# Note: rust/ is a Cargo workspace; maturin reads its config from the parent
# packages/acgs-lite/pyproject.toml, not from within rust/.
```

Notes:
- `make test` and `make test-quick` also run `packages/propriety-ai` npm test scripts.
- `make lint` runs Ruff across the repo, scoped MyPy checks, and the frontend type/lint checks.


## Evals

Eval definitions live in `.claude/evals/`. Dashboard: `.claude/evals/DASHBOARD.md`.
Four suites: MCP server, GitLab pipeline, Cloud Run, demo project.
Run evals with the bash snippets in each eval `.md` file from repo root.

## Architecture

### Package Relationships

```
pyproject.toml (root workspace, uv)
├── packages/acgs-lite/            -> import acgs_lite
├── packages/acgs-deliberation/    -> deliberation layer
├── packages/constitutional_swarm/ -> constitutional swarm
├── packages/enhanced_agent_bus/   -> import enhanced_agent_bus
├── packages/mhc/                  -> MHC package
├── packages/propriety-ai/         -> SvelteKit frontend
├── workers/governance-proxy/      -> Cloudflare Worker
└── src/core/
    ├── cli/                       -> CLI utilities
    ├── cognitive/                 -> Cognitive modules
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

See `.claude/rules/code-style.md` for always-on style rules (loaded automatically).

Additional notes not covered by rules:
- `make lint` uses a scoped MyPy invocation; package-level MyPy settings still exist in individual
  `pyproject.toml` files.
- Token revocation state lives in both `auth.py` and `auth_dependency.py` —
  `configure_revocation_service()` and `shutdown_revocation_service()` must sync both modules'
  `_revocation_service` caches.

## Testing

See `.claude/rules/testing.md` for always-on testing rules (loaded automatically).

At session start, establish a test baseline before making changes so pre-existing failures
are visible. Package-level `pyproject.toml` files define additional markers where needed.

## Refactoring Guidelines

When refactoring or renaming packages, verify all import paths across the entire codebase using
grep before committing. Check for duplicate code left by template extraction.

### Incremental Refactoring (Hard Rule)

When narrowing exceptions, changing error handling, or refactoring cross-cutting patterns:
make changes **one module at a time** and run tests after each module. Never bulk-change 60+
files in one pass. If more than 5 tests fail after a module change, revert that module and
retry with a more conservative approach.

### Sub-Agent Scope Limits

When using sub-agents for parallel work, scope each agent to **<10 files**. Each agent must run
tests for its scoped module before returning. Revert the entire agent's work if failures exceed
5 tests. Never let multiple agents touch the same files.

## Git Workflow

See `.claude/rules/git-workflow.md` for always-on git rules (loaded automatically).

When making git commits, check `git status` and `git log --oneline -5` first to see if
sub-agents have already committed changes. Do not stage/unstage repeatedly — verify state
once, then commit. Only one process should manage git state at a time.

## Iteration & Optimization

When iterating on improvements (skill evolution, code optimization), stop after 3 consecutive
iterations with <0.3 score improvement. Declare ceiling reached rather than regressing by
removing load-bearing content.

## Workflow

- After code changes, run the narrowest meaningful verification first, then expand if the change
  touches shared or critical paths.
- Scope lint/test commands to changed areas before paying for a full repo run.
- Do not commit known failures unless the user explicitly asks for a partial checkpoint.

## Environment

- PM2 service env is defined in `ecosystem.config.cjs`.

## Sub-Package Instructions

See `packages/acgs-lite/CLAUDE.md` and `packages/enhanced_agent_bus/CLAUDE.md` for package-level
guidance.

## gstack

gstack is vendored as a git submodule at `.claude/skills/gstack/`. Use `/browse` for all web
browsing — never use `mcp__claude-in-chrome__*` tools directly. Run `cd .claude/skills/gstack
&& ./setup` after clone or if skills stop working. See `.claude/skills/gstack/CLAUDE.md` for
the full skill list.
