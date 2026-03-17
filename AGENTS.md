# ACGS Agent Guide

> **Constitutional Hash**: `cdd01ef066bc6cf2` | **Python**: 3.11+ | **Line Length**: 100

AI governance platform: Constitutional validation, MACI separation-of-powers, and high-performance
agent message routing.

## Structure

```
acgs/
├── packages/
│   ├── acgs-lite/                  # Standalone governance library (pip install acgs-lite)
│   │   ├── src/acgs_lite/          # Core: engine, constitution, MACI, audit, compliance
│   │   ├── rust/                   # PyO3 Rust extension (560ns P50 validator)
│   │   ├── tests/                  # 16 test files, 286 tests
│   │   └── examples/               # Quickstart examples
│   │
│   └── enhanced-agent-bus/         # Platform engine
│       ├── api/                    # FastAPI entrypoint, routes, auth
│       ├── maci/                   # MACI role separation enforcement
│       ├── circuit_breaker/        # Resilience patterns
│       ├── opa_client/             # OPA policy evaluation
│       ├── constitutional/         # Amendment engine
│       ├── deliberation_layer/     # HITL, voting, impact scoring
│       ├── observability/          # Prometheus metrics, logging
│       └── tests/                  # ~560 test files
│
├── src/core/
│   ├── services/api_gateway/       # API Gateway (FastAPI, auth, rate limiting)
│   └── shared/                     # Types, config, security, logging
│
├── autoresearch/                   # Benchmark optimization harness
├── start_agent_bus.py              # Agent Bus entry point
└── ecosystem.config.cjs            # PM2 service definitions
```

## Commands

```bash
make setup           # Install deps
make test            # Full test suite
make test-quick      # Skip slow tests
make test-lite       # acgs-lite tests
make test-bus        # Agent Bus tests
make lint            # Ruff + MyPy
make format          # Auto-fix
make bench           # Benchmarks
```

## Where to Look

| Task                   | Location                                              |
| ---------------------- | ----------------------------------------------------- |
| Governance library API | `packages/acgs-lite/src/acgs_lite/__init__.py`        |
| Message routing        | `packages/enhanced-agent-bus/message_processor.py`    |
| MACI enforcement       | `packages/enhanced-agent-bus/maci/`                   |
| Policy evaluation      | `packages/enhanced-agent-bus/opa_client/`             |
| Constitutional hash    | `src/core/shared/constants.py`                        |
| Type definitions       | `src/core/shared/types.py`                            |
| API Gateway            | `src/core/services/api_gateway/main.py`               |
| Public API v1          | `packages/enhanced-agent-bus/api/routes/public_v1.py` |

## Conventions

- Explicit types everywhere. Use `X | Y` union syntax (3.11+). No `any`.
- `async def` for all I/O operations.
- Structured logging via `structlog`. Never `print()` in production.
- Pydantic models for all API boundaries.

## MACI (Separation of Powers)

| Role          | Can                              | Cannot              |
| ------------- | -------------------------------- | ------------------- |
| **Proposer**  | Suggest governance actions       | Approve or validate |
| **Validator** | Verify constitutional compliance | Propose             |
| **Executor**  | Execute approved actions         | Validate own work   |

**Golden Rule**: Agents NEVER validate their own output.

## Anti-Patterns (Forbidden)

| Pattern                 | Alternative                     |
| ----------------------- | ------------------------------- |
| `eval()` / `exec()`     | `ast.literal_eval()` or parsers |
| Bare `except:`          | Specific exceptions             |
| `print()` in production | Structured logging              |
| Agents self-validating  | Independent validators (MACI)   |
| Hardcoded secrets       | Environment variables           |

Constitutional Hash: `cdd01ef066bc6cf2`
