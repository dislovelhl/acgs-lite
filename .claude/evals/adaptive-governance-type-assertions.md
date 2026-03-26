# EVAL: adaptive-governance-type-assertions

> **Recorded**: 2026-03-25 | **Branch**: main | **Commit**: 546bddcb
> **Type**: Regression · LOW severity

Two tests in `adaptive_governance` fail due to overly strict type assertions against
internal data structures that were changed from `list` to `deque`.

---

## Root Cause

```python
# test_engine_lifecycle.py:39
assert engine.decision_history == []   # deque([]) != []

# test_engine_feedback.py
# History trimming test expects list slicing semantics
```

`AdaptiveGovernanceEngine.decision_history` is a `collections.deque`, not a `list`.
The tests compare with `[]` directly — fails because `deque([]) != []`.

---

## Graders

```bash
python3 -m pytest \
  packages/enhanced_agent_bus/adaptive_governance/tests/engine/test_engine_lifecycle.py \
  packages/enhanced_agent_bus/adaptive_governance/tests/engine/test_engine_feedback.py \
  --import-mode=importlib -q 2>&1 | tail -5
```

---

## Capability Evals (after fix)

- [ ] `TestInstantiation::test_basic_creation` — PASS
- [ ] `TestUpdateMetrics::test_history_trimmed_when_over_max` — PASS

## Regression Evals

- [ ] `test_engine_evaluation.py` — still passes
- [ ] `test_engine_background.py` — still passes
- [ ] `test_engine_learning.py` — still passes

---

## Fix Options

| Option | Trade-off |
|--------|-----------|
| **A. Fix tests: `assert list(engine.decision_history) == []`** | Minimal, non-breaking | PREFERRED |
| **B. Change engine to use `list`** | May affect performance for large histories | RISKY |

---

## Success Criteria

- pass@1 = 100% for both failing tests
- pass^3 regression: remaining engine tests unaffected
