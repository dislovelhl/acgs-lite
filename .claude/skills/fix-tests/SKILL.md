---
name: fix-tests
description: Systematic test failure resolution — cluster by root cause, fix incrementally with tiered test runs, commit only on full green
version: 1.1.0
---

# Fix Tests

## Workflow

1. **Collect** — Run full suite once, capture all failures:
   ```bash
   python -m pytest <target> -v --import-mode=importlib --tb=short 2>&1 | tail -80
   ```

2. **Cluster** — Group failures by root cause:
   - Import errors (missing modules, circular imports, shadowed packages)
   - Fixture issues (missing fixtures, wrong scope, test pollution)
   - Assertion failures (logic bugs, stale expectations)
   - Type/attribute errors (renamed fields, API changes)

3. **Fix one cluster** — Apply minimal fix for one root-cause group.

4. **Targeted tests** — Run only the affected tests to confirm the fix.

5. **Package suite** — Run the affected package suite before moving to the next cluster:
   ```bash
   make test-lite    # acgs-lite
   make test-bus     # enhanced-agent-bus
   make test-gw      # gateway
   ```

6. **Repeat** steps 3-5 for each remaining cluster.

7. **Full suite gate** — Run `make test` (or all package suites) before commit. Zero failures required.

8. **Commit** — Conventional format:
   ```
   fix: resolve <N> test failures in <package>

   Root causes:
   - <cause 1>: <files affected>
   - <cause 2>: <files affected>
   ```

## Debugging Discipline

After 2 failed fix attempts on the same cluster:
- Stop editing
- Write top 3 hypotheses with evidence
- Choose next step from evidence, not guesswork

## Anti-patterns

- Do not change test expectations unless the test is provably wrong
- Do not commit with known regressions
- Do not run full suite after every single edit — use tiered runs
- Do not `git add -A` — only stage files you modified
- Do not add `# noqa` without checking that the import is actually a re-export
