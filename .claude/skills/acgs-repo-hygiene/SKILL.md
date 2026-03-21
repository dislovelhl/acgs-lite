---
name: acgs-repo-hygiene
description: Repo hygiene patterns for ACGS-clean — gitignore coverage, build artifact management, commit conventions, and test-to-source ratios extracted from 35 commits
version: 1.0.0
source: local-git-analysis
analyzed_commits: 35
---

# ACGS Repo Hygiene Patterns

## Commit Conventions

Conventional commits used in 100% of 35 commits (16 feat, 11 fix, 4 refactor, 2 chore, 1 test, 1 ci). Pattern: `<type>: <description>`. No scope parentheses used. When Claude writes commits, use this exact format — no `feat(scope):`, just `feat:`.

## Known Hygiene Issues

### Committed Build Artifacts (HIGH)
`propriety-ai/dist/` has 4 tracked files including a 456KB JS bundle. Build outputs should never be tracked — they bloat history, cause merge conflicts, and leak source maps. **Fix:** Add `propriety-ai/.gitignore` with `dist/`, `.next/`, `node_modules/`, `*.tsbuildinfo` entries, then `git rm -r --cached propriety-ai/dist/`.

### Missing Sub-Package .gitignore (HIGH)
`propriety-ai/` has no `.gitignore` at all. The root `.gitignore` covers Python artifacts but misses frontend-specific patterns (`.next/`, `dist/`, `*.tsbuildinfo`). Every sub-package with its own build system needs its own `.gitignore`.

### Mega-Commit Pattern (MEDIUM)
Multiple commits touch 20-40 files across unrelated subsystems (e.g., "refactor: shared services cleanup" touches 37 files spanning api_gateway, cache, security, auth). This makes `git bisect` ineffective and code review difficult. Prefer scoped commits: one subsystem per commit.

## Healthy Patterns (Keep)

### .env Handling
Only `.env.example` is tracked. `.env` and `.env.*` are properly gitignored with the `!.env.example` exception. This is correct — secrets never enter version control.

### Test Coverage Ratio
731 test files to 1036 source files (0.71 ratio). For a governance system requiring high assurance, this is healthy. Tests use `test_*.py` naming convention with pytest, organized as sibling `tests/` directories within each module.

### Lock File Policy
`Cargo.lock` (2) and `pnpm-lock.yaml` (1) are tracked. Correct for applications and services (reproducible builds). Would only omit lock files for library-only packages published to registries.

### Gitignore Coverage
Root `.gitignore` (53 lines) covers: Python bytecode, virtualenvs, IDE files, testing artifacts, mypy/ruff caches, Rust targets, OS files, env files, node_modules, benchmarks. No gaps for the Python/Rust stack.

## Hotspot Files

These files changed most frequently (signal for refactoring opportunities):
- `packages/enhanced_agent_bus/constitutional/proposal_engine.py` — 7 changes in 35 commits
- `packages/enhanced_agent_bus/dependency_bridge.py` — 5 changes
- `packages/enhanced_agent_bus/adaptive_governance/tests/test_impact_scorer_coverage.py` — 5 changes
- `src/core/services/api_gateway/main.py` — 4 changes

When touching hotspot files, use smaller, more focused commits. These files are the most likely to cause merge conflicts in multi-agent workflows.
