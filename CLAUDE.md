# CLAUDE.md

Compatibility note for tools that still read `CLAUDE.md`.

`AGENTS.md` is the canonical repo guide. Start there first, then read the nearest scoped
`AGENTS.md` for the package you are changing.

## Commands

```bash
make test-quick
make lint
make format
make codex-doctor
```

Use package-specific commands when possible:
- `make test-lite`
- `make test-bus`
- `make test-gw`
- `make health-overview`

## Verification

- repository pytest runs must include `--import-mode=importlib`
- run the narrowest meaningful verification first
- expand to broader checks when shared, security-sensitive, or governance-critical paths change
- do not hand off code without reporting what you ran and what still remains unverified

## Refactoring

- Never batch-refactor (exception narrowing, type changes, import rewrites) across 20+ files without incremental verification
- Work in batches of 5–10 files, run the affected package tests after each batch, commit passing states
- If a batch causes >5 test failures, revert it and try a more conservative approach
- Sub-agents may explore/analyze in parallel, but mutations flow through one sequential path with test gates

## Constraints

- use canonical enhanced-agent-bus namespaces
- keep governance, auth, and policy behavior fail-closed
- never self-validate agent output in violation of MACI role separation
- do not rely on unchecked PM2 entries as operational truth
