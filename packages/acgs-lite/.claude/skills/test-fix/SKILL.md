# Test Fix Skill

1. Run full test suite: `python -m pytest packages/acgs-lite/tests/ --tb=short -q --import-mode=importlib`
2. Group failures by root cause
3. Fix each root cause (not each symptom)
4. Re-run after each fix group to verify no regressions
5. Commit only when ALL tests pass
