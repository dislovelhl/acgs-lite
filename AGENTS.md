# ACGS Agent Guide

> **Generated**: 2026-03-16 | **Commit**: `44be6f9` | **Branch**: `main`
> **Constitutional Hash**: `cdd01ef066bc6cf2` | **Python**: 3.11+ | **Line Length**: 100

Constitutional governance infrastructure for AI agents. Validates agent actions against
constitutional rules at 560ns median latency with tamper-evident audit trails and
MACI separation-of-powers enforcement.

## Structure

```
acgs/
├── packages/
│   ├── acgs-lite/                  # Standalone library (pip install acgs-lite)
│   │   ├── src/acgs_lite/          # Engine, constitution, MACI, audit, compliance
│   │   ├── rust/                   # PyO3 Rust extension (560ns P50)
│   │   ├── tests/                  # 286 tests
│   │   └── examples/               # Quickstart
│   │
│   └── enhanced_agent_bus/         # Platform engine (1300+ .py files)
│       ├── api/                    # FastAPI entrypoint, app factory, routes
│       ├── maci/                   # MACI role separation (enforcer, roles, matrix)
│       ├── constitutional/         # Amendment engine (proposals → review → activate)
│       ├── deliberation_layer/     # HITL, voting, impact scoring (28 files)
│       ├── mcp/                    # MCP client, routing, MACI filtering
│       ├── mcp_server/             # MCP server (stdio/SSE transport)
│       ├── circuit_breaker/        # Resilience patterns
│       ├── opa_client/             # OPA policy evaluation
│       ├── middlewares/            # Session, batch, security, IFC (canonical)
│       ├── context_memory/         # Mamba-2 hybrid context (canonical)
│       ├── persistence/            # Event sourcing, PostgreSQL
│       ├── saga_persistence/       # Distributed saga state, Redis+PG
│       ├── observability/          # Prometheus metrics, logging
│       ├── optimization_toolkit/   # Profiling, cost, context compression
│       ├── rust/                   # Rust kernels (SIMD, parallel validation)
│       └── tests/                  # 3,534 tests
│
├── src/core/
│   ├── services/api_gateway/       # API Gateway (port 8080, auth, rate limiting, SSO)
│   └── shared/                     # Types, config, auth, security, logging, metrics
│       └── security/               # CORS, rate limiting, token revocation, crypto
│
├── autoresearch/                   # Benchmark optimization harness (autonomous loop)
├── start_agent_bus.py              # Agent Bus entry point (port 8000)
└── ecosystem.config.cjs            # PM2 service definitions (7 services)
```

## Commands

```bash
make setup           # Install deps + pre-commit hooks
make test            # Full test suite (pytest --import-mode=importlib)
make test-quick      # Skip slow tests (-m "not slow" -x)
make test-lite       # acgs-lite tests only
make test-bus        # Enhanced Agent Bus tests only
make test-gw         # API Gateway tests only
make lint            # Ruff check + MyPy strict
make format          # Ruff fix + ruff format
make bench           # Autoresearch benchmarks
make clean           # Remove caches

# PM2 services
pm2 start ecosystem.config.cjs              # All 7 services
pm2 start ecosystem.config.cjs --only agent-bus-8000
```

## Codex Bootstrap

- Repo-local Codex entry: `.agents/skills/acgs-codex-bootstrap/`.
- Use `make codex-doctor` for the quick local readiness check.
- The target runs `.agents/skills/acgs-codex-bootstrap/scripts/codex-doctor.sh` under the hood.
- For OpenAI product/API questions, prefer the configured `openaiDeveloperDocs` MCP server over
  ad hoc web search.
- The stable Codex CLI in this workspace does not expose a repo hook manager yet; use tracked
  scripts and Make targets as the hook equivalent.

## Where to Look

| Task                        | Location                                               |
| --------------------------- | ------------------------------------------------------ |
| Governance library API      | `packages/acgs-lite/src/acgs_lite/__init__.py`         |
| Message routing             | `packages/enhanced_agent_bus/message_processor.py`     |
| MACI enforcement            | `packages/enhanced_agent_bus/maci/`                    |
| Policy evaluation           | `packages/enhanced_agent_bus/opa_client/`              |
| Constitutional amendments   | `packages/enhanced_agent_bus/constitutional/`           |
| Deliberation / HITL         | `packages/enhanced_agent_bus/deliberation_layer/`      |
| MCP integration             | `packages/enhanced_agent_bus/mcp/`                     |
| MCP server                  | `packages/enhanced_agent_bus/mcp_server/`              |
| Optional deps (`_ext_*.py`) | `packages/enhanced_agent_bus/_ext_*.py`                |
| Constitutional hash         | `src/core/shared/constants.py`                         |
| Type definitions            | `src/core/shared/types.py`                             |
| API Gateway                 | `src/core/services/api_gateway/main.py`                |
| Auth / CORS / rate limiting | `src/core/shared/security/`                            |
| Public API v1               | `packages/enhanced_agent_bus/api/routes/public_v1.py`  |
| Benchmark optimization      | `autoresearch/program.md`                              |

## Services (PM2)

| Service              | Port | Entry Point                                  |
| -------------------- | ---- | -------------------------------------------- |
| Agent Bus            | 8000 | `start_agent_bus.py`                         |
| API Gateway          | 8080 | `src/core/services/api_gateway/main.py`      |
| Arch Fitness         | 8085 | Configured in `ecosystem.config.cjs`         |
| x402 Governance API  | 8402 | `agent_earn serve`                           |
| EU AI Act Tool       | 8403 | `eu_ai_act_tool.app`                         |
| Mistral LLM          | 8090 | Configured in `ecosystem.config.cjs`         |
| Analytics API        | 8082 | `scripts/pm2/start.cjs analytics-api`        |

## Conventions

- Explicit types everywhere. Use `X | Y` union syntax (3.11+). No `any`.
- `async def` for all I/O operations.
- Structured logging via `structlog`. Never `print()` in production.
- Pydantic models for all API boundaries.
- Ruff: line-length 100, target py311, max-complexity 15.
- MyPy strict mode. `--ignore-missing-imports` for optional deps.
- Constitutional hash `cdd01ef066bc6cf2` in all validation paths.
- `--import-mode=importlib` required for all pytest runs.

## MACI (Separation of Powers)

| Role          | Can                              | Cannot              |
| ------------- | -------------------------------- | ------------------- |
| **Proposer**  | Suggest governance actions       | Approve or validate |
| **Validator** | Verify constitutional compliance | Propose             |
| **Executor**  | Execute approved actions         | Validate own work   |

**Golden Rule**: Agents NEVER validate their own output.

## Namespace Contracts (Enhanced Agent Bus)

| Namespace         | Status               | Use Instead       |
| ----------------- | -------------------- | ----------------- |
| `middlewares/`    | **Canonical**        | —                 |
| ~~`middleware/`~~ | **Deleted**          | `middlewares/`    |
| `context_memory/` | **Canonical**        | —                 |
| `context/`        | **Legacy (shimmed)** | `context_memory/` |
| `persistence/`    | **Canonical** (PG)   | —                 |
| `saga_persistence/`| **Canonical** (Redis+PG) | —             |

Never import from `enhanced_agent_bus.middleware` (singular). No cross-imports between
`persistence/` and `saga_persistence/`.

## Testing

- **Framework**: pytest 8+ with `asyncio_mode = "auto"`
- **Markers**: `unit`, `integration`, `slow`, `constitutional`, `benchmark`, `governance`,
  `security`, `maci`, `chaos`, `pqc`, `e2e`, `compliance`
- **Coverage**: fail_under=30 (root), 80 (enhanced-agent-bus), 90+ (governance critical)
- **Fixtures**: `conftest.py` at root resets singletons; use `_make_*` factory functions
- **Rust tests**: `maturin develop --release` then `pytest` (not `cargo test`)

## Anti-Patterns (Forbidden)

| Pattern                          | Alternative                              | Severity |
| -------------------------------- | ---------------------------------------- | -------- |
| `eval()` / `exec()`             | `ast.literal_eval()` or parsers          | CRITICAL |
| Agents self-validating           | Independent validators (MACI)            | CRITICAL |
| Hardcoded secrets                | Environment variables                    | CRITICAL |
| `allow_origins=["*"]` + creds   | Explicit origin allowlists               | CRITICAL |
| OPA fail-open                    | Always fail-closed (VULN-002)            | CRITICAL |
| Cross-tenant audit access        | Scope queries to requesting tenant       | CRITICAL |
| Shedding governance/health reqs  | `NEVER_SHED` frozenset (CI-2 invariant)  | CRITICAL |
| Bare `except:`                   | Specific exception types                 | HIGH     |
| `print()` in production          | Structured logging via `structlog`       | HIGH     |
| Import from `middleware/` (sg.)  | Use `middlewares/` (plural)              | HIGH     |
| Weak JWT (HS256) in production   | RS256/EdDSA (migration pending)          | HIGH     |
| Placeholder JWT_SECRET in prod   | Raises `ValueError`                      | CRITICAL |

## Subdirectory AGENTS.md Index

| Path | Scope |
| ---- | ----- |
| [`packages/acgs-lite/AGENTS.md`](packages/acgs-lite/AGENTS.md) | Standalone governance library |
| [`packages/enhanced_agent_bus/AGENTS.md`](packages/enhanced_agent_bus/AGENTS.md) | Platform engine |
| [`packages/enhanced_agent_bus/constitutional/AGENTS.md`](packages/enhanced_agent_bus/constitutional/AGENTS.md) | Amendment engine |
| [`packages/enhanced_agent_bus/deliberation_layer/AGENTS.md`](packages/enhanced_agent_bus/deliberation_layer/AGENTS.md) | HITL, voting, impact scoring |
| [`packages/enhanced_agent_bus/mcp/AGENTS.md`](packages/enhanced_agent_bus/mcp/AGENTS.md) | MCP client & routing |
| [`packages/enhanced_agent_bus/optimization_toolkit/AGENTS.md`](packages/enhanced_agent_bus/optimization_toolkit/AGENTS.md) | Profiling & cost optimization |
| [`packages/enhanced_agent_bus/rust/AGENTS.md`](packages/enhanced_agent_bus/rust/AGENTS.md) | Rust SIMD kernels |
| [`src/core/services/api_gateway/AGENTS.md`](src/core/services/api_gateway/AGENTS.md) | API Gateway |
| [`src/core/shared/AGENTS.md`](src/core/shared/AGENTS.md) | Shared types, config, logging |
| [`src/core/shared/security/AGENTS.md`](src/core/shared/security/AGENTS.md) | Security subsystem |
| [`autoresearch/AGENTS.md`](autoresearch/AGENTS.md) | Benchmark optimization |

Constitutional Hash: `cdd01ef066bc6cf2`
