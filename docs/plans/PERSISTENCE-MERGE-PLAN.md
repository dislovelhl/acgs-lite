# Persistence Layer Merge Plan

Constitutional Hash: 608508a9bd224290
Created: 2026-04-06
Status: PENDING (18+ days overdue per project_simplification_research.md)

## Overview

Merge `packages/enhanced_agent_bus/saga_persistence/` (18 files, ~3,900 lines) into
`packages/enhanced_agent_bus/persistence/` (8 files, ~2,700 lines) to create a single
unified governance persistence package. The two packages already share a common base class
(`GovernanceRepository`) and serve the same system. They were separated for historical
domain-boundary reasons but the boundary adds maintenance cost without providing isolation
benefit -- `SagaStateRepository` already imports from `persistence/`.

## Current Architecture

### persistence/ (8 files, ~2,700 lines)

| File                   | Lines | Purpose                                    |
|------------------------|------:|--------------------------------------------|
| `__init__.py`          |    74 | Package exports                            |
| `models.py`            |   247 | Workflow models (Pydantic BaseModel)        |
| `repository.py`        |   416 | GovernanceRepository ABC + WorkflowRepository + InMemoryWorkflowRepository |
| `postgres_repository.py`|  853 | PostgresWorkflowRepository (asyncpg)       |
| `executor.py`          |   770 | DurableWorkflowExecutor + WorkflowContext   |
| `replay.py`            |   127 | ReplayEngine                               |
| `metrics.py`           |    71 | Prometheus counters/histograms             |
| `spacetime_client.py`  |   338 | SpacetimeDB governance client              |

### saga_persistence/ (18 files, ~3,900 lines)

| File                       | Lines | Purpose                                     |
|----------------------------|------:|---------------------------------------------|
| `__init__.py`              |   199 | Package exports with optional backend guards |
| `models.py`                |   791 | Saga models (dataclasses) + FlywheelRunRecord|
| `repository.py`            |   796 | SagaStateRepository ABC + exceptions + FlywheelRun convenience methods |
| `factory.py`               |   318 | Backend factory (Redis/Postgres auto-detect) |
| `postgres_repository.py`   |    48 | Backward-compat shim -> postgres/            |
| `redis_repository.py`      |    61 | Backward-compat shim -> redis/               |
| `postgres/__init__.py`     |    39 | Sub-package re-exports                      |
| `postgres/repository.py`   |   435 | PostgresSagaStateRepository core CRUD        |
| `postgres/schema.py`       |   111 | SCHEMA_SQL + constants + state transitions   |
| `postgres/queries.py`      |   241 | PostgresQueryOperations mixin               |
| `postgres/state.py`        |   460 | PostgresStateManager mixin                  |
| `postgres/locking.py`      |   353 | PostgresLockManager mixin                   |
| `redis/__init__.py`        |    53 | Sub-package re-exports                      |
| `redis/repository.py`      |   234 | RedisSagaStateRepository core CRUD           |
| `redis/keys.py`            |    56 | Key prefix constants + RedisKeyMixin         |
| `redis/queries.py`         |   216 | RedisQueryOperations mixin                  |
| `redis/state.py`           |   424 | RedisStateManager mixin + state transitions  |
| `redis/locking.py`         |   305 | RedisLockManager mixin                      |

### Existing Cross-Import (already violates the "no cross-imports" rule)

```
saga_persistence/repository.py:26: from enhanced_agent_bus.persistence.repository import GovernanceRepository
```

`SagaStateRepository` inherits from `GovernanceRepository[str, SagaCheckpoint, bool]`.

## Merge Direction: saga_persistence/ INTO persistence/

Rationale:
- `persistence/` already owns the base class (`GovernanceRepository`)
- `persistence/` is the name used in `_ext_persistence.py` and the bus `__init__.py`
- `persistence/` is shorter and more generic
- `saga_persistence/` explicitly depends on `persistence/`, not vice versa

## Target Structure

```
persistence/
├── __init__.py              (expanded: re-exports saga + workflow + factory)
├── models.py                (existing workflow models -- UNCHANGED)
├── repository.py            (existing -- GovernanceRepository, WorkflowRepository, InMemoryWorkflowRepository)
├── postgres_repository.py   (existing -- PostgresWorkflowRepository)
├── executor.py              (existing -- UNCHANGED)
├── replay.py                (existing -- UNCHANGED)
├── metrics.py               (existing -- UNCHANGED)
├── spacetime_client.py      (existing -- UNCHANGED)
├── saga/                    (NEW sub-package, moved from saga_persistence/)
│   ├── __init__.py          (re-exports from sub-modules)
│   ├── models.py            (from saga_persistence/models.py)
│   ├── repository.py        (from saga_persistence/repository.py)
│   ├── factory.py           (from saga_persistence/factory.py)
│   ├── postgres/            (from saga_persistence/postgres/)
│   │   ├── __init__.py
│   │   ├── repository.py
│   │   ├── schema.py
│   │   ├── queries.py
│   │   ├── state.py
│   │   └── locking.py
│   └── redis/               (from saga_persistence/redis/)
│       ├── __init__.py
│       ├── repository.py
│       ├── keys.py
│       ├── queries.py
│       ├── state.py
│       └── locking.py
```

## Dependency Map

### External consumers of saga_persistence/ (NEED import updates)

| File | Current Import |
|------|---------------|
| `src/core/services/api_gateway/lifespan.py` | `from enhanced_agent_bus.saga_persistence import create_saga_repository` |
| `packages/enhanced_agent_bus/data_flywheel/run_orchestrator.py` | `from enhanced_agent_bus.saga_persistence.models import ...` and `from enhanced_agent_bus.saga_persistence.repository import ...` |

### Test files requiring import updates

582 test functions across 8 test files and 8 coverage batch files reference
`enhanced_agent_bus.saga_persistence`. Key files:
- `tests/test_saga_persistence_repository_coverage.py` (174 tests)
- `tests/test_saga_persistence_queries_coverage.py` (69 tests)
- `tests/test_saga_persistence_locking_coverage.py` (85 tests)
- `tests/test_flywheel_run_orchestrator.py`
- `tests/test_flywheel_saga_run_state.py`
- `tests/test_saga_redis_state.py`
- `tests/test_saga_state_machine.py`
- `tests/coverage/test_bus_cov_batch7.py`
- `tests/coverage/test_bus_cov_batch14.py`
- `tests/coverage/test_bus_cov_batch17e.py`
- `tests/coverage/test_bus_cov_batch20f.py`
- `tests/coverage/test_bus_cov_batch29b.py`

## Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Circular imports | HIGH | `persistence/__init__.py` uses lazy imports for saga; consumers use `from enhanced_agent_bus.persistence.saga import ...` |
| 334 test import updates | MEDIUM | Backward-compat shim at old path; test updates done incrementally |
| Database schema conflicts | LOW | Separate tables (`workflow_instances` vs `saga_states`); schemas stay in separate files |
| Factory auto-detection logic | LOW | Pure path change; keep factory logic identical |
| Other agents in worktrees | LOW | Backward-compat shim ensures they work until rebased |

## Implementation Steps

### Phase 0: Setup (1 commit)
Create target directory structure (`persistence/saga/`, `persistence/saga/postgres/`, `persistence/saga/redis/`) with empty `__init__.py` files.
Verify: `python -c "import enhanced_agent_bus.persistence.saga"`

### Phase 1: Move saga source files (3 commits, 5-6 files each)

**Commit 1a: Move saga core files (5 files)**
- Copy `saga_persistence/{models,repository,factory}.py` -> `persistence/saga/`
- Update internal imports
- Create `persistence/saga/__init__.py` with full re-exports

**Commit 1b: Move saga postgres sub-package (6 files)**
- Copy `saga_persistence/postgres/` -> `persistence/saga/postgres/`
- Update imports

**Commit 1c: Move saga redis sub-package (6 files)**
- Copy `saga_persistence/redis/` -> `persistence/saga/redis/`
- Update imports

### Phase 2: Create backward-compat shim (1 commit)
Replace `saga_persistence/__init__.py` with deprecation shim that re-exports from `persistence/saga/`.
Verify: `make test-bus`

### Phase 3: Update production code imports (2 commits)
- Update `data_flywheel/run_orchestrator.py` and `api_gateway/lifespan.py`
- Optionally add saga exports to `persistence/__init__.py`

### Phase 4: Update test imports (4 commits, 5-8 files each)
- Batch 4a: 3 main saga test files
- Batch 4b: 5 saga-related test files
- Batch 4c: 5 coverage batch test files
- Batch 4d: remaining files
- Run `make test-bus` after each batch

### Phase 5: Cleanup (2 commits)
- Delete original saga_persistence source files (keep shims)
- Update documentation and AGENTS.md files

### Phase 6: (Future) Remove backward-compat shims
After a release cycle (v2.7.0), remove `saga_persistence/` entirely.

## Key Design Decisions

**Why a saga/ sub-package instead of flattening?**
Saga persistence has 13 files organized into postgres/ and redis/ sub-packages with mixin architecture. Flattening creates massive files (>800 lines) or a flat directory with 21+ files.

**Why keep both SCHEMA_SQLs separate?**
They define different database tables. Merging creates false coupling.

**Why deprecation shim instead of hard cutover?**
8+ active worktrees, 334 test functions with hard-coded imports, and external consumers require graceful migration.

**Why not merge the model files?**
`persistence/models.py` uses Pydantic. `saga_persistence/models.py` uses dataclasses. Different serialization patterns. Merging creates 1,000+ line file with mixed paradigms.

**Why not merge the repository ABCs?**
`WorkflowRepository` and `SagaStateRepository` are fundamentally different interfaces sharing only the `GovernanceRepository` checkpoint contract. Merging violates interface segregation.

## Estimated Effort

| Phase | Commits | Files | Time |
|-------|--------:|------:|------|
| 0     |       1 |     3 | 10 min |
| 1     |       3 |    17 | 45 min |
| 2     |       1 |     8 | 30 min |
| 3     |       2 |     5 | 20 min |
| 4     |       4 |    16 | 60 min |
| 5     |       2 |    15 | 20 min |
| **Total** | **13** | **~64** | **~3 hours** |

## Success Criteria

- [ ] All existing tests pass with zero failures
- [ ] `make lint` passes (ruff check)
- [ ] `make test-bus` passes
- [ ] `make test-quick` passes
- [ ] Old import paths work via deprecation shim
- [ ] New import paths work for all saga types
- [ ] No file exceeds 800 lines
- [ ] GovernanceRepository remains the single shared base class
- [ ] No circular imports
