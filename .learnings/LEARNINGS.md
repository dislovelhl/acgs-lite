## [LRN-20260330-001] best_practice

**Logged**: 2026-03-30T04:30:36.144449-04:00
**Priority**: high
**Context**: A revocation-related auth failure surfaced while reviewing shared security tests and coverage batches.
**What happened**: Runtime auth code had already been hardened to fail closed in production when JWT revocation checks cannot run, but multiple older tests still encoded fail-open expectations. That kind of drift can pressure future edits toward weakening production auth instead of fixing stale tests.
**Fix/Learning**: When auth, revocation, or other security-critical behavior changes to a stricter contract, proactively sweep nearby coverage and duplicate test files for stale graceful-degradation assertions. Prefer split expectations: non-production can degrade gracefully, production-like environments must fail closed.

