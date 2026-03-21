# AGENTS.md - Enhanced Agent Bus

Scope: `packages/enhanced_agent_bus/` — largest Python package in the repository.

## Overview

This package is the main governance runtime. The FastAPI app lives under `api/`, MACI enforcement
and constitutional workflows live in dedicated subpackages, and `mcp_server/` contains the MCP
server implementation.

## Structure

- `api/`: FastAPI app factory, routers, tests.
- `agent_bus.py`, `message_processor.py`: core routing and orchestration.
- `maci/`: MACI role separation and enforcement.
- `constitutional/`: amendment workflows, storage, validation.
- `deliberation_layer/`: impact scoring, HITL, consensus workflows.
- `mcp/`: MCP client and routing.
- `mcp_server/`: server transports, tools, resources.
- `middlewares/`: canonical middleware stack.
- `context_memory/`: canonical context/memory subsystem.
- `persistence/`: persistence for workflow/runtime state.
- `saga_persistence/`: distributed saga state backends.
- `observability/`: logging, metrics, capacity instrumentation.
- `optimization_toolkit/`: profiling and optimization helpers.
- `tests/`: package-wide test suites.
- `rust/`: Rust kernels and benchmarks.

## Where to Look

- API handlers: `api/`, `routes/`
- Governance/validation: `constitutional/`, `validators.py`, `policy_client.py`
- MCP interface: `mcp/`, `mcp_server/`
- Performance/cache: `_ext_*.py`, `circuit_breaker/`, `optimization_toolkit/`
- Deliberation: `deliberation_layer/`
- Saga/state handling: `persistence/`, `saga_persistence/`
- Health/recovery: `agent_health/`, `observability/`, `verification/`

## Namespace Contracts

| Namespace | Status | Notes |
| --------- | ------ | ----- |
| `middlewares/` | Canonical | Use for all new middleware |
| `middleware/` | Deleted | Do not import |
| `context_memory/` | Canonical | Preferred for new code |
| `context/` | Legacy shim | Avoid for new code |
| `persistence/` | Canonical | Keep isolated from saga persistence |
| `saga_persistence/` | Canonical | Keep isolated from persistence |

### Import Rules

1. Never import from `enhanced_agent_bus.middleware`.
2. Prefer `context_memory/` over `context/`.
3. Do not add cross-domain imports between `persistence/` and `saga_persistence/`.
4. Keep new middleware under `middlewares/`.

## Conventions

- Use `structlog` in runtime code.
- Fail closed on auth, policy, and governance decisions.
- Prefer shared or explicit types over bare `object`, except in `_ext_*.py` fallback stubs.
- Keep constitutional hash handling aligned with service/runtime configuration.

## Commands

```bash
python -m pytest packages/enhanced_agent_bus/tests/ -v --import-mode=importlib
python -m pytest packages/enhanced_agent_bus/tests/ -m "not slow" -v --import-mode=importlib
```

If you run tests from inside the package directory, use the package-local `pyproject.toml`
settings and adjust paths accordingly.

## Optional Dependency Matrix

`_ext_*.py` modules wrap optional dependencies behind availability flags and typed fallbacks. When
adding a new extension module:

1. Wrap imports in `try/except ImportError`.
2. Export an availability flag.
3. Provide fallback names that keep import sites stable.
4. Re-export through package entrypoints only when the pattern already exists.

## Testing

- Package `pyproject.toml` sets `fail_under = 80`.
- `conftest.py` performs singleton and module canonicalization cleanup for tests.
- Use targeted suites first; full-package runs are expensive.
- If a change touches optional integrations, verify both present and fallback behavior when
  practical.

## Subdirectory AGENTS.md Index

| Path | Scope |
| ---- | ----- |
| [`maci/AGENTS.md`](maci/AGENTS.md) | MACI role separation |
| [`opa_client/AGENTS.md`](opa_client/AGENTS.md) | OPA policy evaluation client |
| [`middlewares/AGENTS.md`](middlewares/AGENTS.md) | Canonical middleware stack |
| [`context_memory/AGENTS.md`](context_memory/AGENTS.md) | Context memory subsystem |
| [`observability/AGENTS.md`](observability/AGENTS.md) | Metrics and logging |
| [`persistence/AGENTS.md`](persistence/AGENTS.md) | Workflow persistence |
| [`saga_persistence/AGENTS.md`](saga_persistence/AGENTS.md) | Saga persistence |
| [`constitutional/AGENTS.md`](constitutional/AGENTS.md) | Amendment engine |
| [`deliberation_layer/AGENTS.md`](deliberation_layer/AGENTS.md) | HITL and consensus |
| [`mcp/AGENTS.md`](mcp/AGENTS.md) | MCP client and routing |
| [`optimization_toolkit/AGENTS.md`](optimization_toolkit/AGENTS.md) | Profiling and optimization |
| [`rust/AGENTS.md`](rust/AGENTS.md) | Rust kernels |

## Anti-Patterns

- Do not edit generated artifacts or cached coverage outputs.
- Do not bypass policy enforcement or introduce fail-open branches.
- Do not use `eval()` or `exec()`.
- Do not introduce new imports from deleted or shim-only namespaces.
