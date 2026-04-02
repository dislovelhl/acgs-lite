# ACGS Agent Guide

ACGS is a multi-package governance codebase with Python services, a Svelte frontend, and a
Cloudflare worker. Keep repo guidance short, local, and operational.

## Repo Layout

- `packages/acgs-lite/`
  Standalone governance library plus optional Rust acceleration.
- `packages/enhanced_agent_bus/`
  Main platform runtime: MACI, constitutional workflows, MCP, persistence, observability.
- `packages/propriety-ai/`
  SvelteKit frontend.
- `src/core/services/api_gateway/`
  FastAPI gateway service.
- `src/core/shared/`
  Shared config, auth, logging, security, and types.
- `workers/governance-proxy/`
  Cloudflare Worker governance proxy.
- `autoresearch/`
  Benchmark and evaluation harness.

Read the nearest scoped `AGENTS.md` before changing a subsystem with local rules.

## Core Commands

```bash
make setup
make test
make test-quick
make test-lite
make test-bus
make test-gw
make lint
make format
make bench
make cov
make codex-doctor
```

Repository pytest runs must include:

```bash
--import-mode=importlib
```

Prefer the narrowest meaningful package or health command before a full repo sweep.

## Coding Rules

- Use explicit type annotations and `X | Y` union syntax.
- Use `async def` for I/O paths.
- Use `structlog` in production code. Do not use `print()`.
- Use Pydantic models at API boundaries.
- Prefer canonical enhanced-agent-bus namespaces:
  - `middlewares/`, not `middleware/`
  - `context_memory/`, not new imports from `context/`
  - avoid cross-imports between `persistence/` and `saga_persistence/`
- Treat constitutional and policy logic as fail-closed.

## Do Not

- use `eval()` or `exec()`
- let agents validate their own work; respect MACI separation of powers
- hardcode secrets or ship placeholder production secrets
- use `allow_origins=["*"]` together with credentials
- make OPA, auth, or governance checks fail open
- rely on `ecosystem.config.cjs` as runtime truth without checking the referenced entrypoints

## Definition Of Done

A task is done when:
- the changed area is formatted and linted as needed
- the narrowest relevant tests or health gates pass
- broader verification is run when shared or critical paths changed
- docs or agent guidance are updated if the workflow changed
- known pre-existing failures or follow-up risks are called out explicitly

## Review Expectations

- findings first, ordered by severity, with file references when reviewing code
- note whether failures are pre-existing or introduced by the current change
- include the exact verification commands you ran, or say what you could not run

## Repo-Local Codex Setup

- active repo-local skills live in `.agents/skills/`
- repo-local Codex defaults live in `.codex/config.toml`
- `make codex-doctor` validates the checked-in Codex workspace

Constitutional hash: `608508a9bd224290`
