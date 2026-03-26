# EVAL: circuit-breaker-compat-wrapper

> **Recorded**: 2026-03-25 | **Branch**: main | **Commit**: 546bddcb
> **Type**: Regression · HIGH severity

`packages/enhanced_agent_bus/tests/test_circuit_breaker_core.py` is a compatibility wrapper
that tries to dynamically load `tests/core/enhanced_agent_bus/test_circuit_breaker_coverage.py`
from any ancestor directory. That file does not exist anywhere in the repo, causing a hard
`ImportError` at collection time — which aborts the entire `make test-quick` run.

---

## Root Cause

```python
# test_circuit_breaker_core.py:20
raise ImportError(
    "Unable to locate tests/core/enhanced_agent_bus/test_circuit_breaker_coverage.py"
)
```

The legacy file was never committed (or was deleted). The compat wrapper has no fallback.

---

## Graders

```bash
# FAIL: collection currently aborts
python3 -m pytest packages/enhanced_agent_bus/tests/test_circuit_breaker_core.py \
  --import-mode=importlib -q 2>&1 | grep -E "ImportError|ERROR|passed|failed"

# PASS after fix: collection succeeds (file skipped or stub provided)
python3 -m pytest packages/enhanced_agent_bus/ --import-mode=importlib -q \
  2>&1 | grep -E "^[0-9]+ (passed|failed)" | tail -1
```

---

## Options

| Option | Trade-off |
|--------|-----------|
| **A. Delete `test_circuit_breaker_core.py`** | Clean; loses compat intent | LOW risk |
| **B. Convert to `pytest.skip` when file missing** | Preserves intent, unblocks CI | PREFERRED |
| **C. Create the missing target file** | Full coverage; requires content | HIGH effort |

**Recommended**: Option B — add graceful skip.

```python
# Replace the raise ImportError with:
import pytest
pytest.skip("Legacy coverage file not found; skipping compat wrapper", allow_module_level=True)
```

---

## Capability Evals

- [ ] `make test-quick` completes without collection errors
- [ ] `python3 -m pytest packages/enhanced_agent_bus/tests/test_circuit_breaker_core.py` exits 0 or with skip (not error)

## Regression Evals

- [ ] `packages/enhanced_agent_bus/circuit_breaker/` unit tests (breaker, registry, router) still pass
- [ ] `make test-quick` total collected items ≥ 21600

---

## Success Criteria

- pass@1 = 100%: `make test-quick` collection succeeds
- pass^3: circuit_breaker module tests unaffected
