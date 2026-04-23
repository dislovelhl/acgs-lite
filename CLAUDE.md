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

### Testing

```bash
# Full suite
make test
python -m pytest tests/ -v --import-mode=importlib --rootdir=.

# Single file / single test
python -m pytest tests/test_lifecycle_router.py -v --import-mode=importlib
python -m pytest tests/test_lifecycle_router.py -k test_create_draft_200 -v --import-mode=importlib

# By category
python -m pytest -m "not e2e" -v --import-mode=importlib
python -m pytest -m e2e -v --import-mode=importlib
```

**Critical test notes:**

- Tests use `InMemory*` stubs and should not import live services.
- Set placeholder keys when needed: `OPENAI_API_KEY=test-key-for-unit-tests` and `ANTHROPIC_API_KEY=test-key-for-unit-tests`.

### Linting & Formatting

```bash
make lint
ruff check .
ruff format --check .
ruff format .
make typecheck
mypy src/acgs_lite
```

### Build

```bash
make build
python -m mkdocs build
```

---

## Repo Boundary

- `packages/acgs-lite` is a nested git repo inside the parent ACGS monorepo.
- Before staging, committing, or pushing, check git state both here and in the parent repo.

---

## Autonomous Verification (Mandatory)

Do not assume code changes are correct. Always verify before handing work back.

**Required sequence:**

```bash
make lint
make typecheck
make test
make build
```

If any step fails, fix the issue and rerun the full sequence from the top. Do not skip steps.

**Shortcut:** `bash .claude/commands/test-and-verify.sh`

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

## Coding Standards

### Naming Conventions

| Type | Convention | Example |
| --- | --- | --- |
| Classes | PascalCase | `ConstitutionLifecycle` |
| Functions | snake_case | `run_evaluation` |
| Constants | UPPER_SNAKE_CASE | `MAX_RETRIES` |
| Files | snake_case | `lifecycle_router.py` |

### Import Order

```python
# 1. Standard library
# 2. Third-party packages
# 3. Local / first-party
```

### Error Handling

```python
# Use project-specific error types. No bare except blocks or silent fallthrough.
```

### Logging

```python
# Use structured logging where available. Do not add print() for production flow.
```

---

## Testing Standards

### Coverage Requirements

| Scope | Minimum | Target |
| --- | --- | --- |
| System-wide | 80% | 90%+ |
| Critical paths | 90% | 95%+ |
| PRs | 80% | 90%+ |

### Mock Strategy

- External services: always mock in unit tests.
- File system: mock in unit tests, real in integration tests.
- Time and randomness: mock for deterministic assertions.
- Use `InMemory*` stubs instead of live SDKs in tests.

### Pytest Notes

- Default suite excludes `e2e` via `pytest.ini` / `pyproject.toml`.
- Run targeted lifecycle tests with `python -m pytest tests/test_lifecycle_router.py -v --import-mode=importlib`.
- When adding a branch, add tests for both the happy path and the failure path.

---

## Security

- Never hardcode secrets, API keys, tokens, or passwords.
- Validate all external input at service boundaries.
- Keep optional SDK imports out of module import time.
- Prefer safe placeholders in examples: `dev-*`, `test-*`, `your-*-here`.
- Do not weaken MACI or lifecycle auth checks to make tests pass.

---

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | `test-key-for-unit-tests` | Placeholder to silence import-time validation |
| `ANTHROPIC_API_KEY` | `test-key-for-unit-tests` | Placeholder to silence import-time validation |
| `ACGS_LIFECYCLE_ENABLED` | unset | Enables the lifecycle router in `server.py` |
| `ACGS_LIFECYCLE_API_KEY` | unset | API key required by lifecycle mutation endpoints |

---

## What NOT to Do

- Never import optional platform SDKs at module import time.
- Never bypass MACI enforcement in wrappers or integrations.
- Never change `matcher.py` hot-path behavior without targeted tests.
- Never rely on raw `cargo test` as the only verification for Python-facing Rust changes.
- Never skip the verification sequence before marking a task complete.

---

## Git Workflow

- Branch naming: `feature/`, `fix/`, `refactor/`, `docs/`, `test/`, `chore/`.
- Commits must follow the repo Lore commit protocol from the parent `AGENTS.md`.
- Keep commits atomic and bisectable.
- Never force push to shared branches.

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
