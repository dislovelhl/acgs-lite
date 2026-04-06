# ACGS Testing Specification

This document adapts the best parts of the external Claude CLI workspace testing docs to ACGS.
It intentionally cherry-picks the **workflow patterns**, not the source project's runtime code.

> Part of the ACGS workflow docs. Start at [`README.md`](README.md) for the full workflow/reference set.

## 1. Goals

| Goal | Why it matters in ACGS |
| --- | --- |
| Prevent regressions | Governance, MACI, and policy paths are safety-critical and must not silently drift |
| Validate constitutional behavior | Tests should prove fail-closed behavior, role separation, and hash consistency |
| Document expected behavior | High-value tests act as living docs for governance-critical flows |
| Keep feedback loops fast | Start with package-scoped or health-target checks before expanding to the full suite |

## 2. Test Stack

| Area | Standard |
| --- | --- |
| Python tests | `pytest` 8+ |
| Import mode | **Always** `--import-mode=importlib` for repository-level runs |
| Async tests | `asyncio_mode = auto` |
| Quality gates | `ruff`, scoped `mypy`, package-local health targets |
| Frontend tests | `npm run test` / `npm run test:unit` under `packages/acgs.ai` |
| Worker tests | `npm run test` under `workers/governance-proxy` |

## 3. Test Layers

### 3.1 Unit tests

Use for pure functions, parsers, serializers, policy transforms, constitutional hash helpers, and
small coordination helpers.

Examples:
- `packages/acgs-lite/tests/`
- `packages/enhanced_agent_bus/tests/` focused helper/unit files
- `src/core/shared/tests/`

### 3.2 Integration tests

Use for cross-module flows with real orchestration boundaries: message processing, governance
receipt propagation, policy evaluation, auth dependencies, API routes, and persistence adapters.

Examples:
- `packages/enhanced_agent_bus/tests/test_message_processor_*.py`
- `src/core/services/api_gateway/tests/`
- cross-package compliance/report flows in `packages/acgs-lite/tests/`

### 3.3 Governance / constitutional tests

These are not ordinary integrations. They must validate:
- fail-closed behavior
- MACI separation of powers
- constitutional hash consistency
- validator/executor independence
- audit and rejection metadata on denied actions

Prefer explicit marker usage where relevant:

```bash
python -m pytest packages/enhanced_agent_bus/tests/ -m "constitutional or maci" \
  --import-mode=importlib -v
```

### 3.4 Package-health gates

For package-scoped work, use the narrowest health target first:

```bash
make health-lite
make health-bus
make health-bus-governance
make health-gw
make health-constitutional-swarm
make health-frontend
make health-worker
```

These are the closest analogue to subsystem test plans and should usually be run before broader
repo-wide verification.

## 4. File Layout

```text
packages/
├── acgs-lite/tests/                    # library tests
├── enhanced_agent_bus/tests/           # runtime + governance tests
├── acgs.ai/                       # frontend tests/scripts
└── constitutional_swarm/tests/         # package-local swarm tests
src/core/
├── services/api_gateway/tests/         # API service tests
└── shared/tests/                       # shared auth/config/security tests
.claude/evals/                          # eval-first success criteria
docs/test-plans/                        # subsystem-oriented test planning artifacts
```

Test plans should be stored under `docs/test-plans/` and referenced from evals, plans, or PR notes
when the work touches critical subsystems.

## 5. Writing Rules

- Use Arrange / Act / Assert structure.
- Each test should validate one behavior.
- Cover happy path, failure path, and at least one boundary case.
- Prefer specific exception expectations over broad `except` handling.
- For async code, test coroutine behavior directly instead of wrapping it in sync helpers.
- Do not weaken governance/security assertions to make tests pass.
- For bug fixes, add a regression test before or alongside the implementation.

## 6. Mock Strategy

| Dependency type | Strategy |
| --- | --- |
| Optional Python deps (`_ext_*.py`) | Test both availability flags and fallback behavior where practical |
| External services (OPA, Redis, Kafka, SIEM, WorkOS, etc.) | Mock at the service boundary in unit tests; use real adapters only in intentional integration coverage |
| Governance collaborators | Use explicit stubs/fakes that preserve MACI separation semantics |
| Time / UUID / randomness | Freeze or inject deterministic values |

Do not mock away the trust boundary you are trying to validate.

## 7. Priority Areas

### P0 — Governance core

Target the message processor, governance/verification coordinators, constitutional validation,
MACI enforcement, and security defaults.

### P1 — Package boundaries and adapters

Target API gateway auth/rate limiting, `acgs-lite` compliance routing, MCP routing, and package
health commands.

### P2 — UX and deployment edges

Target frontend workflows, worker behavior, and environment/bootstrap checks.

## 8. Standard Commands

```bash
# Narrowest meaningful scope first
python -m pytest packages/acgs-lite/tests/ -v --import-mode=importlib
python -m pytest packages/enhanced_agent_bus/tests/ -v --import-mode=importlib
python -m pytest src/core/services/api_gateway/tests/ -v --import-mode=importlib

# Fast repo feedback
make test-quick
bash .claude/commands/test-and-verify.sh --quick

# Package-health slices
make health-bus-governance

# Full repository validation
make test
make lint
bash .claude/commands/test-and-verify.sh
```

## 9. Definition of Done

A change is not done until:
- the relevant eval exists or was updated first,
- the narrowest meaningful tests pass,
- broader verification is run if the change touches shared/critical paths,
- baseline debt vs new failures is called out explicitly,
- and governance/security behavior remains fail-closed.

## Related docs

- [`README.md`](README.md) — docs index for the workflow/reference set
- [`test-plans/01-governance-core.md`](test-plans/01-governance-core.md) — concrete subsystem test-plan example
- [`subagent-execution.md`](subagent-execution.md) — delegation model for implementation + verification workers
- [`context-compaction.md`](context-compaction.md) — how to preserve verification state across handoff/compaction
