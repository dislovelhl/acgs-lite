# Changelog

<!-- Constitutional Hash: 608508a9bd224290 -->

All notable changes to the Enhanced Agent Bus are documented in this file.

## [2.5.0] - 2026-02-01

### Added

- **Saga Persistence Layer**: Full-featured saga state management with PostgreSQL and Redis backends
  - Factory-based repository creation with automatic backend detection
  - Alembic migrations for PostgreSQL schema management
  - Optimistic locking and distributed locking support
  - Multi-tenant isolation and checkpoint-based recovery

- **Swarm Intelligence v3.0**: Advanced multi-agent coordination
  - Dynamic capability-based agent spawning
  - DAG-based task decomposition
  - Byzantine fault-tolerant consensus mechanisms
  - Inter-agent message bus with constitutional compliance

- **Performance Module**: Comprehensive profiling and optimization
  - `PerformanceProfiler` with budget enforcement and warnings
  - `FastLaneOptimizer` with LRU caching and optimization levels
  - `Z3SolverPool` and `OPABatchEvaluator` for pooled evaluation
  - Performance budgets for constitutional AI operations

### Changed

- **Code Quality**: Replaced 96+ bare exception handlers with specific types
- **Pre-commit**: Migrated from deprecated `safety` hook to `pip-audit`
- **Dependencies**: Updated cryptography (46.0.3), websockets (16.0), neo4j (6.1.0), aiofiles (25.1.0)
- **Test Coverage**: Expanded to 3,534 tests with 99.92% pass rate

### Fixed

- Fixed thread safety issues in swarm intelligence coordinator
- Fixed Pact contract test using matchers in HTTP request body
- Fixed coverage config and security test imports
- Fixed dependency resolution and flaky timing tests

### Security

- Replaced deprecated `datetime.utcnow()` with timezone-aware `datetime.now(UTC)`

## [2.2.0] - 2025-12-21

### Added

- **Phase 5 Completion**: Full integration of Rust-based Deliberation Layer and Security modules.
- **Enhanced Impact Scoring**: Multi-dimensional scoring with ONNX (DistilBERT) fallback support in Rust.
- **Prompt Injection Defense**: Pre-compiled regex-based adversarial pattern detection in Rust core.
- **Adaptive Routing**: Real-time threshold adjustment based on feedback loops.

### Changed

- **Version Bump**: Global version update to `2.2.0` across all documentation and project configs.
- **Doc Cleanup**: Removed outdated temporary files and local test logs.
- **Blueprint Update**: Production blueprint updated to reflect verified status of all 5 phases.

### Security

- Synchronized prompt injection patterns between Python and Rust implementations.

## [1.1.0] - 2025-12-21

### Added

- **S3/MinIO Storage Integration**: Full cloud storage support in `storage_service.py`
  - Automatic fallback to local filesystem when S3 unavailable
  - MinIO endpoint support via `S3_ENDPOINT_URL` environment variable
  - Constitutional hash metadata in S3 object tags
  - `bundle_exists()` method for checking bundle availability

- **Authorization Caching**: Performance optimization in `opa_service.py`
  - 15-minute TTL cache for RBAC authorization decisions
  - Role-based caching (not user-specific) for better hit rates
  - Automatic cache cleanup for expired entries
  - `invalidate_cache()` method for manual cache clearing

- **Policy Version Caching**: Faster lookups in `policy_service.py`
  - Active version caching with 1-hour TTL
  - Automatic cache invalidation on version activation
  - Integrated with existing cache service

### Changed

- **Logging Migration**: Replaced `print()` with proper logging
  - `impact_scorer.py`: ONNX model loading → `logger.info()`
  - `impact_scorer.py`: AI model failure → `logger.warning()`
  - `hitl_manager.py`: Mock audit → `logger.debug()`
  - `hitl_manager.py`: Initialization → `logger.info()`

- **Exception Handling**: Replaced bare `except:` with specific types
  - `health_check_endpoints.py`: `ValueError`, `TypeError`, `aiohttp.ContentTypeError`
  - `retrieval_engine.py`: `ValueError`, `TypeError`, `AttributeError`
  - `constraint_generator.py`: `KeyError`, `IndexError`, `TypeError`
  - `notification_service.py`: `asyncio.QueueFull`, `RuntimeError`, `AttributeError`

### Security

- Added security documentation comments for `exec()` usage in test files
- Verified secrets management uses environment variables (no hardcoded secrets)

### Documentation

- Updated README.md with v1.1.0 release notes
- Added "Recent Updates" section documenting improvements
- Enhanced contributing guidelines with code quality standards
- Created CHANGELOG.md for version tracking

## [1.0.0] - 2025-12-17

### Initial Release

- Core message bus implementation with Python/Rust backends
- Constitutional validation with hash `608508a9bd224290`
- OPA policy integration
- Policy registry client
- Deliberation layer for AI-powered review
- Circuit breaker patterns
- Prometheus metrics integration
- 515 tests with 80% coverage
- P99 latency: 0.023ms
- Throughput: 55,978 RPS

---

_Constitutional Hash: 608508a9bd224290_
