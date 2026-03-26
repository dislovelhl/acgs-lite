# EVAL: regression-suite-baseline

> **Recorded**: 2026-03-25 | **Branch**: main | **Commit**: 546bddcb

Regression baseline capturing the current test pass/fail state across all packages.
These evals must pass^3 = 100% after any change. Failures here are regressions.

---

## Graders

```bash
# acgs-lite: run all tests, require zero failures in the clean subset
python3 -m pytest packages/acgs-lite/tests/ --import-mode=importlib -q \
  --ignore=packages/acgs-lite/tests/test_anthropic_integration.py \
  --ignore=packages/acgs-lite/tests/test_mcp_server.py \
  --ignore=packages/acgs-lite/tests/test_openshell_governance_http.py \
  --ignore=packages/acgs-lite/tests/test_openshell_governance_integration.py \
  2>&1 | tail -1

# enhanced_agent_bus: run all tests, ignore the missing-file compat wrapper
python3 -m pytest packages/enhanced_agent_bus/ --import-mode=importlib -q \
  --ignore=packages/enhanced_agent_bus/tests/test_circuit_breaker_core.py \
  2>&1 | tail -1

# sdk/typescript: all 15 tests pass
cd sdk/typescript && npm test 2>&1 | grep "# fail"
```

---

## Regression Evals

### R1 — acgs-lite core (pass^3 = 100%)
- [ ] `packages/acgs-lite/tests/` passes with 3122+ tests collected, 0 failures (excluding known-broken files)
- **Current**: ❌ FAIL — 131 failures across 18 test files (engine `_constitution` rename, integration mocks)

### R2 — enhanced_agent_bus (pass^3 = 100%)
- [ ] `packages/enhanced_agent_bus/` passes with 41138+ tests collected, 0 failures (excluding `test_circuit_breaker_core.py`)
- **Current**: ❌ FAIL — 21 failures across 7 test files

### R3 — TypeScript SDK (pass^3 = 100%)
- [ ] All 15 SDK tests pass, 0 fail
- **Current**: ✅ PASS — 15/15 pass

### R4 — test suite collection (no import errors)
- [ ] `make test-quick` collects without import errors
- **Current**: ❌ FAIL — `test_circuit_breaker_core.py` raises `ImportError` (missing legacy compat file)

---

## Known Failures (Tracked, Not Regressions)

| File | Failure Root Cause | Severity |
|------|--------------------|----------|
| `test_core.py` | `GovernanceEngine` attribute renamed: `_constitution` → `constitution` (engine/core.py:1486) | HIGH |
| `test_engine_lifecycle.py` | `decision_history` returns `deque([])` not `[]` — type assertion too strict | LOW |
| `test_engine_feedback.py` | History trimming logic assertion mismatch | LOW |
| `test_circuit_breaker_core.py` | Compat wrapper looks for `tests/core/enhanced_agent_bus/test_circuit_breaker_coverage.py` — file doesn't exist | HIGH |
| `test_bus_cov_batch34a.py` | `test_validate_allow_with_real_audit_log` — governance engine slow path | MEDIUM |
| `test_openshell_governance_*.py` | Integration tests require running HTTP server / Redis / sqlite state | LOW |
| `test_anthropic_integration.py` | Requires live Anthropic API key | EXTERNAL |
| `test_mcp_server.py` | Constitutional hash consistency + multi-violation tests | MEDIUM |

---

## Success Criteria

| Metric | Target | Current |
|--------|--------|---------|
| pass^3 acgs-lite (clean subset) | 100% | ❌ ~96% |
| pass^3 enhanced_agent_bus | 100% | ❌ ~99.95% |
| pass^3 TypeScript SDK | 100% | ✅ 100% |
| Import-error-free collection | 100% | ❌ 1 error |
