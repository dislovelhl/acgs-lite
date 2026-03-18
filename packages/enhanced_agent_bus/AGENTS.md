# AGENTS.md - Enhanced Agent Bus

Scope: `packages/enhanced_agent_bus/` — 637 py files, largest subsystem.

## Overview

Core governance/agent runtime. FastAPI entrypoint lives in `api/` with the app factory in
`api/app.py`; the module entrypoint is `python -m packages.enhanced_agent_bus.api`. MCP server
lives in `mcp_server/`.

## Structure

- `api/`: FastAPI package entrypoint and app factory.
- `agent_bus.py`, `message_processor.py`: core routing and orchestration.
- `meta_orchestrator.py`: apex lifecycle coordinator.
- `maci/`: MACI role separation (Proposer/Validator/Executor) — decomposed into `enforcer.py`, `config.py`, `roles.py`, `registry.py`, `matrix.py`.
- `routes/`: API routers.
- `policies/`: OPA policies and governance rules.
- `deliberation_layer/`: Impact scoring, HITL, consensus (24 files).
- `mcp_server/`: MCP server entrypoints and tooling.
- `circuit_breaker/`: Circuit breaker pattern implementation.
- `optimization_toolkit/`: Multi-agent optimization, profiling.
- `tests/`: unit/integration tests for bus (228 test files).
- `rust/`: Rust extension build artifacts (do not edit generated files).

## Where to Look

- API handlers: `routes/`
- Governance/validation: `constitutional/`, `validators.py`, `policy_resolver.py`
- MCP interface: `mcp_server/`
- Performance/cache: `batch_cache.py`, `redis_pool.py`, `batch_*`
- Deliberation: `deliberation_layer/` (impact scoring, HITL, consensus)
- Swarm: `swarm_intelligence.py`, saga coordination
- Health/recovery: `health_aggregator.py`, `recovery_orchestrator.py`

## Namespace Contracts

Canonical vs deprecated/legacy namespaces. The enforcement script
`scripts/check_eab_namespace_imports.py` blocks imports from banned namespaces.

| Namespace                    | Status               | Purpose                                                                                                   | Consumers                                              |
| ---------------------------- | -------------------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| `middlewares/`               | **Canonical**        | Session extraction, batch processing, tool privilege, orchestration, temporal policy, PROV, security, IFC | 53 imports across 22 files                             |
| ~~`middleware/`~~            | **Deleted (Wave 1)** | Was byte-for-byte duplicate of `middlewares/session_extraction.py`                                        | Zero (dead code, removed)                              |
| `context_memory/`            | **Canonical**        | Mamba processor, hybrid context, JRT preparer, long-term memory, constitutional cache, optimizer          | 35+ exports; used by breakthrough/, coordinators/, RLM |
| `context/`                   | **Legacy (shimmed)** | Standalone Mamba-2 implementation (`mamba_hybrid.py`)                                                     | 1 test file; re-export shim added, marked deprecated   |
| `mamba2_hybrid_processor.py` | **Canonical**        | Phase 1.2 Mamba-2 integration (top-level)                                                                 | meta_orchestrator, coordinators/context_coordinator    |
| `context_optimization.py`    | **Canonical**        | Phase 4 context optimization (top-level)                                                                  | Via `_ext_context_optimization.py`                     |
| `persistence/`               | **Canonical**        | Workflow execution lifecycle, event sourcing, PostgreSQL-only                                             | api.routes.workflows, api.app, \_ext_persistence       |
| `saga_persistence/`          | **Canonical**        | Distributed saga state, multi-backend (Redis+PG), factory                                                 | Self-contained, no external consumers                  |

### Import Rules

1. **Never** import from `enhanced_agent_bus.middleware` (singular) — deleted.
2. **Prefer** `context_memory/` over `context/` for all new code.
3. **Do not** add cross-domain imports between `persistence/` and `saga_persistence/`.
4. **All** new middleware modules go in `middlewares/` (plural).

## Conventions

- Use structured logging (`structlog`); avoid `print()` in production paths.
- Do not use `object`; prefer shared types in `src/core/shared/types.py`.
- Fail closed on auth/policy decisions.
- Include constitutional hash in validation paths when required.

## Commands

- Bus tests: `python -m pytest tests/ -v --tb=short`
- OPA tests: `cd policies && opa test . -v`

## Optional Dependency Matrix

Each `_ext_*.py` module wraps an optional heavy dependency with a lazy-load
stub. When the dependency is absent the module exports its availability flag
as `False` and all type names as `object` stubs, allowing the bus `__init__`
to re-export them unconditionally.

| Module                            | Availability Flag                   | Optional Dependency                      | Key Exports                                                           |
| --------------------------------- | ----------------------------------- | ---------------------------------------- | --------------------------------------------------------------------- |
| `_ext_cache_warming.py`           | `CACHE_WARMING_AVAILABLE`           | Internal cache warming subsystem         | `CacheWarmingStrategy`, `WarmingScheduler`                            |
| `_ext_chaos.py`                   | `CHAOS_AVAILABLE`                   | Chaos engineering toolkit                | `ChaosScenario`, `ChaosOrchestrator`                                  |
| `_ext_circuit_breaker_clients.py` | `CIRCUIT_BREAKER_CLIENTS_AVAILABLE` | External-client circuit wrappers         | `RedisCircuitClient`, `OPACircuitClient`                              |
| `_ext_circuit_breaker.py`         | `SERVICE_CIRCUIT_BREAKER_AVAILABLE` | `circuit_breaker/` sub-package           | `ServiceCircuitBreaker`, `CircuitState`, `FallbackStrategy`           |
| `_ext_cognitive.py`               | `COGNITIVE_AVAILABLE`               | `cognitive/` sub-package (DSPy/GraphRAG) | `GovernanceKnowledgeGraph`, `MultiAgentPlanner`, `LongContextManager` |
| `_ext_context_memory.py`          | `CONTEXT_MEMORY_AVAILABLE`          | Context memory store                     | `ContextMemoryStore`, `MemoryEntry`                                   |
| `_ext_decision_store.py`          | `DECISION_STORE_AVAILABLE`          | Decision persistence layer               | `DecisionStore`, `DecisionRecord`                                     |
| `_ext_explanation_service.py`     | `EXPLANATION_SERVICE_AVAILABLE`     | LLM explanation layer                    | `ExplanationService`, `ExplanationRequest`                            |
| `_ext_langgraph.py`               | `LANGGRAPH_AVAILABLE`               | LangGraph workflow engine                | `LangGraphOrchestrator`, `WorkflowNode`                               |
| `_ext_mcp.py`                     | `MCP_AVAILABLE`                     | MCP server integration                   | `MCPServer`, `MCPTool`                                                |
| `_ext_persistence.py`             | `PERSISTENCE_AVAILABLE`             | Async persistence backend                | `PersistenceBackend`, `PersistenceRecord`                             |
| `_ext_pqc.py`                     | `PQC_AVAILABLE`                     | Post-quantum cryptography                | `PQCSigner`, `PQCVerifier`                                            |

**Adding a new optional module**: copy the pattern from `_ext_circuit_breaker.py`:

1. Wrap the import in `try/except ImportError`.
2. In the `except` block stub every exported name to `object` with `# type: ignore[assignment, misc]`.
3. Populate `_EXT_ALL` with **all** names (flag + types) so the bus `__init__` can re-export them.
4. Add a row to this table.

## Testing

- **3,534 tests** across 400+ test files.
- `conftest.py` resets singletons via `_reset_singletons()` (autouse) — prevents state pollution.
- Module canonicalization handles dual identity (`packages.enhanced_agent_bus.X` vs `enhanced_agent_bus.X`).
- `TEST_WITH_RUST=1` to enable Rust backend in tests (default: Python fallback).
- Coverage: fail_under=80.
- `_make_*` factory functions for complex test object creation.

## Subdirectory AGENTS.md Index

| Path | Scope |
| ---- | ----- |
| [`constitutional/AGENTS.md`](constitutional/AGENTS.md) | Amendment engine (proposals → review → activate) |
| [`deliberation_layer/AGENTS.md`](deliberation_layer/AGENTS.md) | HITL, voting, impact scoring, consensus |
| [`mcp/AGENTS.md`](mcp/AGENTS.md) | MCP client, routing, MACI filtering |
| [`optimization_toolkit/AGENTS.md`](optimization_toolkit/AGENTS.md) | Profiling, cost, context compression |
| [`rust/AGENTS.md`](rust/AGENTS.md) | SIMD kernels, parallel validation |

## Anti-Patterns

- Do not edit generated artifacts (`htmlcov/`, `mlruns/`, `coverage.json`, `audit_*.json`).
- Do not bypass policy enforcement or allow fail-open paths.
- No `eval()`/`exec()`.
- Do not use `object` as type — prefer shared types in `src/core/shared/types.py`.
