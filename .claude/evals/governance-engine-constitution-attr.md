# EVAL: governance-engine-constitution-attr

> **Recorded**: 2026-03-25 | **Branch**: main | **Commit**: 546bddcb
> **Type**: Regression · HIGH severity

The `GovernanceEngine` in `packages/acgs-lite/src/acgs_lite/engine/core.py` has a broken
attribute reference at line 1486. Code accesses `self._constitution` but the attribute was
renamed to `self.constitution` (public). This breaks 8+ tests in `test_core.py` and cascades
into many other test files.

---

## Root Cause

```python
# packages/acgs-lite/src/acgs_lite/engine/core.py:1486
for rule in self._constitution.rules:   # ← AttributeError
```

The attribute is stored as `self.constitution` (no leading underscore).

---

## Graders

```bash
# PASS when attribute error is gone from core tests
python3 -m pytest packages/acgs-lite/tests/test_core.py --import-mode=importlib -q \
  2>&1 | grep -E "^(PASSED|FAILED|ERROR|[0-9]+ (passed|failed))" | tail -3

# Confirm the attribute name in source
grep -n "_constitution" packages/acgs-lite/src/acgs_lite/engine/core.py | head -20
grep -n "self\.constitution" packages/acgs-lite/src/acgs_lite/engine/core.py | head -5
```

---

## Capability Evals (all must pass after fix)

- [ ] `TestGovernedAgent::test_wrap_callable` — PASS
- [ ] `TestGovernedAgent::test_wrap_class_with_run` — PASS
- [ ] `TestGovernedAgent::test_validates_output` — PASS
- [ ] `TestGovernedAgent::test_custom_constitution` — PASS
- [ ] `TestGovernedAgent::test_stats` — PASS
- [ ] `TestGovernedCallable::test_decorator` — PASS
- [ ] `TestAsyncGovernedAgent::test_async_run` — PASS
- [ ] `TestIntegration::test_full_governance_pipeline` — PASS

## Regression Evals (must not break after fix)

- [ ] `packages/acgs-lite/tests/test_engine_refactor.py` — still passes
- [ ] `packages/acgs-lite/tests/test_engine_core_coverage.py` — still passes

---

## Fix Plan

```python
# In packages/acgs-lite/src/acgs_lite/engine/core.py ~line 1486
# Change: self._constitution.rules
# To:     self.constitution.rules
```

Scan for all occurrences:
```bash
grep -n "_constitution" packages/acgs-lite/src/acgs_lite/engine/core.py
```

---

## Success Criteria

- pass@1 = 100% for all 8 listed test cases after fix
- pass^3 regression: `test_engine_refactor.py`, `test_engine_core_coverage.py` still green
