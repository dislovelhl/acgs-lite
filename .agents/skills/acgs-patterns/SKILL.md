---
name: acgs-patterns
description: Coding patterns extracted from acgs-clean repository (37 commits, 3 packages, 21K+ tests)
version: 1.0.0
source: local-git-analysis
analyzed_commits: 37
---

# ACGS Repository Patterns

## Commit Conventions

**Conventional commits used in 100% of commits** (37/37):
- `feat:` 46% (17 commits) — new features, services, subsystems
- `fix:` 30% (11 commits) — test failures, import fixes, linter issues
- `refactor:` 11% (4 commits) — cleanup, security hardening
- `chore:` 8% (3 commits) — build artifacts, gitignore
- `test:` 3% (1 commit) — cross-service integration tests
- `ci:` 3% (1 commit) — PyPI publishing pipeline

**Apply when:** Writing any commit message. Use `feat:` for new modules/endpoints, `fix:` for test/import/linter fixes, `refactor:` for non-functional changes.

## Code Architecture

### Package Structure (Monorepo with uv workspace)
```
pyproject.toml (root workspace)
├── packages/acgs-lite/          → standalone library, PyPI-published
├── packages/enhanced_agent_bus/ → platform engine, 80+ subsystems
├── src/core/                    → shared services, gateway, CLI
├── propriety-ai/                → Next.js + Vite frontend (pnpm)
└── sdk/typescript/              → TypeScript SDK (npm)
```

**Apply when:** Creating new modules. Place standalone library code in `packages/acgs-lite/`, platform features in `packages/enhanced_agent_bus/`, shared infra in `src/core/shared/`.

### Import Conventions
- `from enhanced_agent_bus.models import Priority` (NOT `MessagePriority`)
- `from enhanced_agent_bus.middlewares` (plural, NOT `middleware`)
- NEVER `from src.core.enhanced_agent_bus.*` — use `enhanced_agent_bus.*` directly
- Extension modules: `_ext_*.py` with try/except fallback pattern

### Naming Conventions
- Python files: `snake_case.py`
- TypeScript/React: `kebab-case.tsx` for components, `camelCase.ts` for utils
- Test files: `test_*.py` (Python), `*.test.ts` (TypeScript)
- Pytest markers as decorators: `@pytest.mark.constitutional`, `@pytest.mark.maci`

### File Size Distribution
- Target: 200-400 lines typical, 800 max
- Current hotspots needing extraction: `constitution.py` (4120 lines), `engine/core.py` (1579 lines), `metrics.py` (1428 lines)

## Workflows

### Feature Implementation Pattern (observed across 17 feat commits)
1. **Source + Tests co-created** — Every `feat:` commit includes both implementation and test files
2. **conftest.py updated** — New subsystems get their own `conftest.py` with fixtures
3. **CLAUDE.md updated** — Package-level CLAUDE.md files updated with new conventions
4. **Canonical imports established** — New modules immediately get proper import paths

### Fix Pattern (observed across 11 fix commits)
1. **Multi-file batch fixes** — Fix commits touch 5-15 files across packages
2. **Test files fixed alongside source** — Import fixes, assertion updates
3. **Gateway tests fixed separately** — API gateway fixes get dedicated commits

### Hotspot Files (changed in 3+ commits)
- `constitutional/proposal_engine.py` (7 changes) — governance proposal logic
- `api_gateway/main.py` (5 changes) — gateway entry point
- `dependency_bridge.py` (5 changes) — cross-package import resolution
- `impact_scorer.py` (4 changes) — deliberation scoring
- `builder.py` (4 changes) — agent bus builder pattern
- `engine/core.py` (4 changes) — acgs-lite validation core

**Apply when:** Planning work — expect these files to need changes for most features.

## Testing Patterns

### Framework & Configuration
- **Framework:** pytest 7.0+ with `--import-mode=importlib` (MANDATORY)
- **Async:** `asyncio_mode = "auto"` — no need for `@pytest.mark.asyncio`
- **Coverage:** 30% minimum threshold, `fail_under = 30` in pyproject.toml
- **Test-to-source ratio:** 28.8:1 (636 test files, 905 source files, 21,432 tests)

### Test Organization
- Root `conftest.py`: sets `ACGS2_SERVICE_SECRET`, `SERVICE_JWT_ALGORITHM`
- Package `conftest.py`: PYTHONPATH setup, singleton resets, module canonicalization
- Subsystem `conftest.py`: domain-specific fixtures (12 nested conftest files)
- `autouse=True` fixtures for singleton reset between tests

### Markers (11 registered + 3 unregistered)
Registered: `unit`, `integration`, `slow`, `constitutional`, `benchmark`, `governance`, `security`, `maci`, `chaos`, `pqc`, `e2e`
Unregistered (need fixing): `compliance`, `pqc_deprecation`, `enhanced_agent_bus`

### Known Test Issues
- 10 test files in `rollback_engine/` broken by relative imports from conftest
- `TestRequest`/`TestResult` Pydantic models in `policy_copilot/models.py` trigger pytest collection warnings
- PyTorch-dependent tests skip gracefully via `pytest.skip()`

## Error Handling Patterns

### Established Pattern: Silent Fallback for Optional Features
```python
try:
    optional_feature = import_optional("feature")
except ImportError:
    optional_feature = None  # Graceful degradation
```

### Issue: 12 Production Files Missing Logging on Except
Files needing `logger.exception()` added:
- `acl_adapters/z3_adapter.py` (5 bare excepts)
- `mcp/transports/http.py`, `loco_operator_client.py`
- `message_processor.py`, `config.py`, `context_optimization.py`
- Gateway: `billing.py`, `x402_governance.py`, `pqc_only_mode.py`
- Shared: `token_revocation.py`, `pqc_crypto.py`

## Security Patterns

### Constitutional Hash Enforcement
- Hash `cdd01ef066bc6cf2` embedded in configs, tests, validation paths
- MACI separation: Proposer/Validator/Executor roles enforced at middleware level
- No hardcoded secrets in production code (all test data properly marked `# noqa: S105`)

### Dependencies (CVE-aware)
- `pydantic>=2.12.1` (CVE-2025-6607 patched)
- `litellm>=1.61.6` (CVE-2025-1499 patched)
- Post-quantum cryptography via `liboqs-python` optional extra
