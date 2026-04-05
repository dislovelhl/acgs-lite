---
id: baseline-test-run-is-mandatory
trigger: "when starting any coding task in an existing codebase"
confidence: 0.92
domain: testing
source: session-observation
session: 2026-03-29-subnet-gtm-sprint
---

# Always Run Baseline Tests Before Writing Code

## Action
Run `pytest -q` (or equivalent) before writing a single line of code.
Record the exact baseline: N collected, N passed, N failed.
Report the delta at the end of the session.

## Template
```
Baseline: [commit SHA] — [N] tests, [N] passed, [N] failed
Final:    [commit SHA] — [N] tests, [N] passed, [N] failed
Delta:    +[N] tests, +[N] passed, [N] regressions
```

## Why
- "All tests pass" without a baseline is unverifiable
- Pre-existing failures get attributed to your changes
- The delta proves exactly what you added and that nothing broke

## Evidence
- 2026-03-29: 218-test baseline established. Final 307. Delta +89, 0 regressions.
  Clean proof that the sprint added value without breaking anything.
- This pattern has been consistent across all ACGS sessions.

## Note
In ACGS, always add `--import-mode=importlib` to pytest commands.
