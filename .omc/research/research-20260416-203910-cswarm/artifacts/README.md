# Structural Fix Scaffolds — constitutional_swarm

Three CI-gated scaffolds that close whole problem classes, not instances.

| # | Dir | Target file(s) in `constitutional_swarm/` | Closes |
|---|---|---|---|
| 1 | `import_boundary/` | `tests/test_import_boundaries.py` | Deep internal `acgs_lite.*` imports; acgs-lite refactor breaks |
| 2 | `findings_as_tests/` | `tests/security/test_finding_*.py`, `scripts/generate_security_report.py`, `.github/workflows/security.yml` | "Claimed fixed in SYSTEMIC_IMPROVEMENT.md" drift; audit staleness |
| 3 | `cite_verifier/` | `scripts/verify_citations.py`, `.github/workflows/verify-cites.yml` | Fabricated/placeholder arXiv IDs; self-citation passing as lit |

## Apply

Each scaffold is a drop-in. From `packages/constitutional_swarm/`:

```bash
# 1. Import boundary
cp <this-dir>/import_boundary/test_import_boundaries.py tests/
python -m pytest tests/test_import_boundaries.py --import-mode=importlib -v
# -> will FAIL initially (there ARE internal imports) — fix acgs-lite public surface OR
#    promote needed symbols in acgs-lite's __init__.py, then tighten.

# 2. Findings-as-tests
mkdir -p tests/security scripts
cp <this-dir>/findings_as_tests/test_finding_001_unauth_ws.py tests/security/
cp <this-dir>/findings_as_tests/generate_security_report.py scripts/
cp <this-dir>/findings_as_tests/security.yml .github/workflows/
# add `security` marker to pyproject.toml (see findings_as_tests/marker.snippet)
python -m pytest tests/security/ -m security --json-report --json-report-file=.security.json
python scripts/generate_security_report.py .security.json > security-audit-report.md

# 3. Citation verifier
cp <this-dir>/cite_verifier/verify_citations.py scripts/
cp <this-dir>/cite_verifier/verify-cites.yml .github/workflows/
python scripts/verify_citations.py --root . --skip-network  # offline sanity
python scripts/verify_citations.py --root .                   # full check
```

## Meta-principle

Every scaffold converts something currently enforced by "a reviewer reading prose" into something enforced by "a CI gate refusing a PR." Once merged, the problem cannot be silently reintroduced.

## Not in scope here (drafted earlier, 7-item list)

- Paper↔code single source of truth (literate programming / LaTeX table generated from `pytest --benchmark-json`)
- Transcript-chained replay resistance (cryptographic, not infrastructural)
- Actions SHA-pinning + Dependabot (pure config, no code)
- Research namespace separation (refactor, not gate)

Ask if you want any of those drafted next.
