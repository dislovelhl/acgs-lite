# Systemic Improvement Tracking
> Started: 2026-03-24 | Branch: main | Constitutional Hash: `cdd01ef066bc6cf2`

## Phase 1: Analysis — COMPLETE ✅

| Agent | Task | Status | Findings |
|-------|------|--------|----------|
| Security Auditor | Security audit | ✅ Done | 5 real issues (S104, S105×3, S603), 1 CRITICAL eval() in rlm_repl.py |
| Test Coverage Analyzer | Failing tests | ✅ Done | **2 test failures** in strict-mode HIGH-severity path |
| Code Style Improver | Ruff violations | ✅ Done | 668 non-security violations; 533 auto-fixable |
| Git Organizer | Recent history | ✅ Done | Clean conventional commits, no stale worktrees in main |

## Phase 2: Implementation — IN PROGRESS 🟡

| Agent | Task | Status | Notes |
|-------|------|--------|-------|
| Test Fixer | Fix 2 failing tests (HIGH strict path) | 🟡 Running | Root cause: `_validate_rust_no_context` missing strict+blocking raise |
| Style Fixer | Auto-fix 533 ruff violations | ⬜ Pending | `ruff check --fix` + sort imports |
| Security Annotator | Annotate false-positive S105 strings | ⬜ Pending | CLASS_SECRET, TEST_SUITE_PASS are classification labels, not passwords |

---

## Findings Detail

### 🔴 Test Failures (2 tests)

**Root cause**: `GovernanceEngine._validate_rust_no_context()` handles `_RUST_DENY` (HIGH-severity
bitmask) by building a violations list and returning the pooled escalate result — but **never
raises** `ConstitutionalViolationError`, even when `strict=True`. The caller only invokes this
method on the `strict=True` fast-path, so the missing raise means HIGH-severity violations silently
pass through in strict mode.

**Contrast**: `_validate_rust_gov_context()` already has the correct fix at line ~782:
```python
if _bv_ctx is not None and self.strict:
    raise ConstitutionalViolationError(...)
```

**Fix**: mirror that pattern inside `_validate_rust_no_context`'s `elif decision == _RUST_DENY:`
branch.

**Affected tests**:
- `packages/acgs-lite/tests/test_coverage_batch_e.py::TestGovernanceEngineValidate::test_deny_high_strict_returns_violations`
  - Expects `ConstitutionalViolationError` with `rule_id="T-HIGH"` for `"skip audit for this action"`
- `packages/acgs-lite/tests/test_engine_core_coverage.py::TestGovernanceEngineValidate::test_escalate_high_severity_no_block`
  - Expects `ConstitutionalViolationError` with `rule_id="FAIRNESS-001"` for `"apply age-based insurance pricing"`
  - Note: FAIRNESS-001 is keyword-only (keywords: [age, discrimination, bias]) — `"age"` matches

### 🟡 Security Notes

| Issue | File | Verdict |
|-------|------|---------|
| `S105` `CLASS_SECRET`/`CLASS_TOP_SECRET` | `abac.py` | False positive — classification label strings, not passwords |
| `S105` `TEST_SUITE_PASS` | `policy_lifecycle.py` | False positive — test result status string |
| `S105` `PASS` | `test_suite.py` | False positive — pass/fail literal |
| `S603` subprocess | `tools/browser_tool.py` | Acceptable — tool takes hardcoded args |
| `S104` bind-all | `start_api_gateway.py` | Acceptable in dev — document with noqa |
| `S307` eval() | `rlm_repl.py:329` | ⚠️ REAL — eval of compiled expression in REPL context; already guarded by sandbox |

### 🟢 Auto-fixable Style Violations (533)

| Code | Count | Description |
|------|-------|-------------|
| `I001` | 434 | Unsorted imports (auto-fix) |
| `F401` | 80 | Unused imports (auto-fix) |
| `UP035` | 4 | Deprecated imports (auto-fix) |
| `F541` | 7 | f-strings missing placeholders (auto-fix) |
| `B009` | 2 | getattr with constant (auto-fix) |
| `RUF022` | 2 | Unsorted `__all__` (auto-fix) |
| `RUF100` | 4 | Unused noqa (auto-fix) |

## Success Metrics

- [x] Root cause of 2 test failures identified
- [ ] 2 failing tests fixed (strict HIGH path in Rust fast-path)
- [ ] 533 auto-fixable style violations resolved
- [ ] False-positive security annotations added
- [ ] All 49,440 tests pass
