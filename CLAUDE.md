# ACGS-Lite

For repo-wide rules, see the parent repo guide at `../../CLAUDE.md` and `.claude/rules/`.
Claude Code auto-loads parent `CLAUDE.md` files; this file should stay package-specific.
AGENTS.md serves Codex/OMX.

## Project Overview

| Key | Value |
| --- | --- |
| **Project** | ACGS-Lite |
| **Language** | Python |
| **Framework** | FastAPI, MkDocs |
| **Package Mgr** | pip / Make |
| **Line Length** | 100 |
| **Target** | Python 3.10+ |

AI governance library for constitutional rule enforcement, lifecycle management, and audit-backed validation.

## Quick Commands

```bash
# Verify (required before marking complete)
bash .claude/commands/test-and-verify.sh
# or step by step:
make lint && make typecheck && make test && make build

# Single test
python -m pytest tests/test_lifecycle_router.py -v --import-mode=importlib
python -m pytest tests/test_lifecycle_router.py -k test_create_draft_200 -v --import-mode=importlib

# Format
ruff format .
```

**Test notes:** Tests use `InMemory*` stubs. Set `OPENAI_API_KEY=test-key-for-unit-tests` and `ANTHROPIC_API_KEY=test-key-for-unit-tests` when needed.

---

## Repo Boundary

`packages/acgs-lite` is a nested git repo inside the parent ACGS monorepo.
Before staging, committing, or pushing, check git state both here and in the parent repo.

---

## Architecture & Conventions

- Keep integrations optional through extras and lazy imports.
- Keep Python fallbacks when optional Rust or third-party acceleration exists.
- CLI command wiring lives in `src/acgs_lite/commands/`; `acgs arckit` is routed through that surface.
- Arckit bridge code and templates live in `src/acgs_lite/arckit/`.
- Observation and reporting helpers live in `src/acgs_lite/observability/`.
- Constitution lifecycle code lives in `src/acgs_lite/constitution/`.
- HTTP surfaces live in `src/acgs_lite/server.py` and `src/acgs_lite/constitution/lifecycle_router.py`.
- Docs for API surfaces live under `docs/api/`.
- Use `_make_*` helpers in tests for fixture creation when available.

---

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | `test-key-for-unit-tests` | Placeholder to silence import-time validation |
| `ANTHROPIC_API_KEY` | `test-key-for-unit-tests` | Placeholder to silence import-time validation |
| `ACGS_LIFECYCLE_ENABLED` | unset | Enables the lifecycle router in `server.py` |
| `ACGS_LIFECYCLE_API_KEY` | unset | API key required by lifecycle mutation endpoints |

---

## Compounding Knowledge

Update this section whenever a mistake is made so it never happens again.

| ID | Lesson | Detail |
| --- | --- | --- |
| CK-001 | Optional integrations stay lazy | Import optional SDKs only inside guarded code paths. |
| CK-002 | Validation failures raise | `GovernanceEngine.validate()` raises `ConstitutionalViolationError` instead of returning `valid=False`. |
| CK-003 | Bundle hashes are derived | `ConstitutionBundle.constitutional_hash` is populated from `constitution.hash`. |

---

## Skill Routing

Package-local workflow routing should stay minimal here.
Prefer the parent repo `CLAUDE.md` and `.claude/rules/` as the authoritative routing source so package guidance does not drift from installed skills.
