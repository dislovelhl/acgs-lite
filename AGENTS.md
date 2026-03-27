# ACGS Agent Guide

> **Reviewed**: 2026-03-20 | **Commit**: `1d769ab` | **Branch**: `main`
> **Constitutional Hash**: `608508a9bd224290` | **Python**: 3.11+ | **Line Length**: 100

Constitutional governance infrastructure for AI agents. The repository contains a standalone
governance library, a large platform runtime, shared services, a Svelte frontend, and supporting
worker/tooling packages.

Brand and naming rules live in [`docs/brand-architecture.md`](docs/brand-architecture.md).

## Structure

```
acgs/
├── packages/
│   ├── acgs-lite/                  # Standalone governance library (PyPI: acgs)
│   │   ├── src/acgs_lite/          # Engine, constitution, MACI, audit, integrations
│   │   ├── src/eu_ai_act_tool/     # EU AI Act self-assessment app
│   │   ├── rust/                   # Optional Rust acceleration workspace
│   │   ├── tests/                  # Package test suite
│   │   └── examples/               # Quickstarts and examples
│   ├── enhanced_agent_bus/         # Platform runtime and governance engine
│   │   ├── api/                    # FastAPI app factory and routes
│   │   ├── constitutional/         # Amendment engine and storage
│   │   ├── deliberation_layer/     # HITL, voting, impact scoring
│   │   ├── maci/                   # Role separation and enforcement
│   │   ├── mcp/                    # MCP client and routing
│   │   ├── mcp_server/             # MCP server transports, tools, resources
│   │   ├── middlewares/            # Canonical middleware stack
│   │   ├── context_memory/         # Canonical context/memory subsystem
│   │   ├── persistence/            # PostgreSQL-oriented persistence
│   │   ├── saga_persistence/       # Redis + PostgreSQL saga persistence
│   │   ├── observability/          # Metrics and structured logging
│   │   ├── optimization_toolkit/   # Profiling and cost/context optimization
│   │   ├── rust/                   # Rust kernels and benches
│   │   └── tests/                  # Package test suite
│   └── propriety-ai/               # SvelteKit frontend
├── src/core/
│   ├── services/api_gateway/       # API Gateway service
│   └── shared/                     # Shared types, config, auth, logging, security
├── workers/governance-proxy/       # Cloudflare Worker governance proxy
├── sdk/                            # Client SDK artifacts
├── autoresearch/                   # Benchmark optimization harness
└── ecosystem.config.cjs            # PM2 service definitions
```

## Commands

```bash
make setup           # Install Python deps, package deps, pre-commit, propriety-ai npm deps
make test            # Full Python test suite + propriety-ai test suite
make test-quick      # Skip slow Python tests + propriety-ai unit tests
make test-lite       # acgs-lite tests only
make test-bus        # enhanced_agent_bus tests only
make test-gw         # API Gateway tests only
make lint            # Ruff + targeted MyPy + propriety-ai check/lint
make format          # Ruff fix/format + propriety-ai format
make bench           # acgs-lite benchmark-marked tests
make cov             # Root coverage run
make clean           # Remove caches and local coverage files

# PM2 services
pm2 start ecosystem.config.cjs
pm2 start ecosystem.config.cjs --only agent-bus-8000
```

All repository pytest invocations should include `--import-mode=importlib`.

## Codex Bootstrap

- Repo-local Codex entry: `.agents/skills/acgs-codex-bootstrap/`.
- Use `make codex-doctor` for the quick local readiness check.
- The target runs `scripts/codex-doctor.sh`.
- For OpenAI product/API questions, prefer the configured `openaiDeveloperDocs` MCP server.
- The stable Codex CLI in this workspace does not expose a repo hook manager; use tracked scripts
  and Make targets instead.

## Where to Look

| Task | Location |
| ---- | -------- |
| Governance library API | `packages/acgs-lite/src/acgs_lite/__init__.py` |
| Message routing | `packages/enhanced_agent_bus/message_processor.py` |
| MACI enforcement | `packages/enhanced_agent_bus/maci/` |
| Policy evaluation | `packages/enhanced_agent_bus/opa_client/` |
| Constitutional amendments | `packages/enhanced_agent_bus/constitutional/` |
| Deliberation / HITL | `packages/enhanced_agent_bus/deliberation_layer/` |
| MCP integration | `packages/enhanced_agent_bus/mcp/` |
| MCP server | `packages/enhanced_agent_bus/mcp_server/` |
| Optional deps (`_ext_*.py`) | `packages/enhanced_agent_bus/_ext_*.py` |
| API Gateway | `src/core/services/api_gateway/main.py` |
| Auth / CORS / rate limiting | `src/core/shared/security/` |
| Frontend app | `packages/propriety-ai/src/` |
| Worker proxy | `workers/governance-proxy/src/` |
| Benchmark optimization | `autoresearch/program.md` |

## Runtime Entry Points

| Component | Port | Checked-in Entry Point |
| --------- | ---- | ---------------------- |
| Agent Bus | 8000 | `start_agent_bus.py` |
| Enhanced Agent Bus API package | 8000 | `packages/enhanced_agent_bus/api/__main__.py` |
| API Gateway | 8080 | `src/core/services/api_gateway/main.py` |
| Governance Proxy | Worker | `workers/governance-proxy/src/index.ts` |
| Frontend app | Vite/SvelteKit | `packages/propriety-ai/package.json` scripts |

`ecosystem.config.cjs` exists, but parts of it currently point at missing checked-in entrypoints
such as `scripts/pm2/start.cjs`, `src/core/services/arch_fitness/start.py`, and
`services/mistral/start.sh`. Verify those before relying on the PM2 map as operational truth.

## Conventions

- Explicit types everywhere. Use `X | Y` union syntax.
- `async def` for I/O operations.
- Structured logging via `structlog`. Never `print()` in production code.
- Pydantic models for API boundaries.
- Ruff line length is 100, target is `py311`, max complexity is 15.
- Root MyPy is strict, but the `make lint` target intentionally scopes checks to selected files.
- Constitutional hash `608508a9bd224290` is part of validation and service configuration paths.

## MACI (Separation of Powers)

| Role | Can | Cannot |
| ---- | --- | ------ |
| **Proposer** | Suggest governance actions | Approve or validate |
| **Validator** | Verify constitutional compliance | Propose |
| **Executor** | Execute approved actions | Validate own work |

**Golden Rule**: agents never validate their own output.

## Namespace Contracts (Enhanced Agent Bus)

| Namespace | Status | Use Instead |
| --------- | ------ | ----------- |
| `middlewares/` | **Canonical** | — |
| `middleware/` | **Deleted** | `middlewares/` |
| `context_memory/` | **Canonical** | — |
| `context/` | **Legacy (shimmed)** | `context_memory/` |
| `persistence/` | **Canonical** | — |
| `saga_persistence/` | **Canonical** | — |

Never import from `enhanced_agent_bus.middleware` (singular). Avoid cross-imports between
`persistence/` and `saga_persistence/`.

## Testing

- **Framework**: pytest 8+ with `asyncio_mode = "auto"`.
- **Root markers**: `unit`, `integration`, `slow`, `constitutional`, `benchmark`,
  `governance`, `security`, `maci`, `chaos`, `pqc`.
- **Coverage**: root `fail_under = 70`; `packages/enhanced_agent_bus` sets `fail_under = 80`.
- **Fixtures**: root `conftest.py` sets repo-wide test env defaults including
  `ACGS2_SERVICE_SECRET`.
- **Rust-backed acgs-lite verification**: `maturin develop --release` then pytest.

## Anti-Patterns (Forbidden)

| Pattern | Alternative | Severity |
| ------- | ----------- | -------- |
| `eval()` / `exec()` | `ast.literal_eval()` or parsers | CRITICAL |
| Agents self-validating | Independent validators (MACI) | CRITICAL |
| Hardcoded secrets | Environment variables | CRITICAL |
| `allow_origins=["*"]` + creds | Explicit origin allowlists | CRITICAL |
| OPA fail-open | Always fail-closed | CRITICAL |
| Cross-tenant audit access | Scope queries to requesting tenant | CRITICAL |
| Bare `except:` | Specific exception types | HIGH |
| `print()` in production | Structured logging via `structlog` | HIGH |
| Import from `middleware/` | Use `middlewares/` | HIGH |
| Placeholder JWT secrets in production | Fail startup and require real secrets | CRITICAL |

## Subdirectory AGENTS.md Index

| Path | Scope |
| ---- | ----- |
| [`packages/acgs-lite/AGENTS.md`](packages/acgs-lite/AGENTS.md) | Standalone governance library |
| [`packages/enhanced_agent_bus/AGENTS.md`](packages/enhanced_agent_bus/AGENTS.md) | Platform engine |
| [`packages/enhanced_agent_bus/maci/AGENTS.md`](packages/enhanced_agent_bus/maci/AGENTS.md) | MACI role separation |
| [`packages/enhanced_agent_bus/opa_client/AGENTS.md`](packages/enhanced_agent_bus/opa_client/AGENTS.md) | OPA policy evaluation client |
| [`packages/enhanced_agent_bus/middlewares/AGENTS.md`](packages/enhanced_agent_bus/middlewares/AGENTS.md) | Canonical middleware stack |
| [`packages/enhanced_agent_bus/context_memory/AGENTS.md`](packages/enhanced_agent_bus/context_memory/AGENTS.md) | Context memory subsystem |
| [`packages/enhanced_agent_bus/observability/AGENTS.md`](packages/enhanced_agent_bus/observability/AGENTS.md) | Metrics and logging |
| [`packages/enhanced_agent_bus/persistence/AGENTS.md`](packages/enhanced_agent_bus/persistence/AGENTS.md) | PostgreSQL persistence |
| [`packages/enhanced_agent_bus/saga_persistence/AGENTS.md`](packages/enhanced_agent_bus/saga_persistence/AGENTS.md) | Saga persistence |
| [`packages/enhanced_agent_bus/constitutional/AGENTS.md`](packages/enhanced_agent_bus/constitutional/AGENTS.md) | Amendment engine |
| [`packages/enhanced_agent_bus/deliberation_layer/AGENTS.md`](packages/enhanced_agent_bus/deliberation_layer/AGENTS.md) | HITL and deliberation |
| [`packages/enhanced_agent_bus/mcp/AGENTS.md`](packages/enhanced_agent_bus/mcp/AGENTS.md) | MCP client and routing |
| [`packages/enhanced_agent_bus/optimization_toolkit/AGENTS.md`](packages/enhanced_agent_bus/optimization_toolkit/AGENTS.md) | Profiling and optimization |
| [`packages/enhanced_agent_bus/rust/AGENTS.md`](packages/enhanced_agent_bus/rust/AGENTS.md) | Rust kernels |
| [`src/core/services/api_gateway/AGENTS.md`](src/core/services/api_gateway/AGENTS.md) | API Gateway |
| [`src/core/shared/AGENTS.md`](src/core/shared/AGENTS.md) | Shared types, config, logging |
| [`src/core/shared/security/AGENTS.md`](src/core/shared/security/AGENTS.md) | Security subsystem |
| [`autoresearch/AGENTS.md`](autoresearch/AGENTS.md) | Benchmark optimization |

Constitutional Hash: `608508a9bd224290`
