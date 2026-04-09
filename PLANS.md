# ACGS-Lite Plans

## Purpose / Big Picture

Stabilize `packages/acgs-lite/` as a publishable governance library with:
- explicit MACI semantics
- predictable wrapper validation for structured inputs/outputs
- consistent audit behavior in API surfaces
- packaging/docs that match the shipped wheel

## Active Remediation Plan

### Phase 1 — Close correctness gaps in public wrappers
Status: completed on 2026-04-02

Goals:
- validate keyword arguments in `GovernedCallable`
- validate structured outputs in `GovernedAgent` / `GovernedCallable`
- ensure `/stats` reflects the real engine audit log
- ship both `acgs` and `acgs-lite` console scripts

Verification:
- targeted regression tests added in `tests/test_core.py`, `tests/test_server.py`, `tests/test_cli_governance.py`
- full package pytest run passes
- wheel build exports both console script aliases

### Phase 2 — Make MACI enforcement explicit without breaking compatibility
Status: completed on 2026-04-02

Decision:
- `maci_role` remains metadata by default
- explicit enforcement now requires opt-in via `enforce_maci=True`
- enforced runs must also provide `governance_action=...`

Rationale:
- existing callers and tests treat `maci_role` as descriptive metadata
- automatic enforcement on all governed runs would be a breaking semantic change
- explicit opt-in preserves compatibility while enabling real separation-of-duties checks

Verification targets:
- proposer + `governance_action="propose"` passes
- proposer + `governance_action="validate"` fails with `MACIViolationError`
- enforced agent with no `governance_action` fails fast with `GovernanceError`

### Phase 3 — Consolidate governance serialization
Status: completed on 2026-04-02

Goals:
- move wrapper-side payload normalization into a shared helper/module
- support dataclasses, pydantic models, and bounded serialization
- centralize truncation / fallback behavior for large or unserializable objects

Verification:
- shared helper added at `src/acgs_lite/serialization.py`
- wrappers now consume the shared helper instead of private local helpers
- targeted tests cover dataclass, pydantic, and truncation behavior

### Phase 4 — Clarify audit modes
Status: completed on 2026-04-02

Goals:
- document and formalize `fast` vs `full` audit behavior in `GovernanceEngine`
- keep server/API surfaces on full audit by default
- keep benchmark/hot-path usage allowed to use fast audit intentionally

Verification:
- `GovernanceEngine` now exposes explicit `audit_mode`
- stats now report `audit_mode` and `audit_entry_count`
- fast mode rejects an explicit durable `audit_log` to avoid ambiguous semantics
- server and governed wrappers now opt into `audit_mode="full"` explicitly

## Decision Log

- 2026-04-02: preserve backward compatibility by making MACI enforcement opt-in instead of implicit.
- 2026-04-02: wrapper governance must treat structured outputs as first-class validation payloads, not string-only payloads.
- 2026-04-02: package metadata must match actual wheel entry points.

## Active Remediation Plan

### Phase 5 — Harden Leanstral verifier theorem construction
Status: completed on 2026-04-06

Goals:
- lock `lean_verify.py` behavior with targeted regression tests before refactoring
- stop guessing Lean predicate names from rule IDs; derive theorem references from generated declarations
- encode available action/context assumptions into the theorem statement so kernel verification matches runtime inputs more closely
- make the documented `leanstral` → `codestral-latest` fallback real when the preferred model is unavailable

Verification targets:
- targeted regressions in `tests/test_lean_verify.py` cover predicate-name derivation, context assumptions, and model fallback
- `python -m pytest tests/test_lean_verify.py -q --import-mode=importlib` passes
- `python -m ruff check src/acgs_lite/lean_verify.py tests/test_lean_verify.py` passes
- `python -m mypy src/acgs_lite/lean_verify.py` passes

### Phase 6 — Harden the real Lean execution environment
Status: completed on 2026-04-06

Goals:
- make the Lean kernel command configurable for real deployments without code changes
- support running verification inside an explicit Lean/Lake working directory when provided
- tighten subprocess isolation and diagnostics for kernel failures and missing toolchains
- preserve existing mocked verifier behavior while adding runtime-specific regression coverage

Verification targets:
- targeted regressions cover command override, working-directory override, and stdout-only diagnostics
- `python -m pytest tests/test_lean_verify.py -q --import-mode=importlib` passes
- `python -m ruff check src/acgs_lite/lean_verify.py tests/test_lean_verify.py` passes
- `python -m mypy src/acgs_lite/lean_verify.py` passes

### Phase 7 — Add Lean runtime smoke-check CLI
Status: completed on 2026-04-06

Goals:
- add a small CLI command to validate `ACGS_LEAN_CMD` / `ACGS_LEAN_WORKDIR` against a real Lean toolchain
- keep the command dependency-light and reuse `lean_verify` runtime helpers instead of duplicating subprocess logic
- support human-readable and JSON output for scripting
- preserve existing CLI behavior and parser compatibility

Verification targets:
- targeted CLI regressions cover parser registration, success output, and failure output
- `python -m pytest tests/test_cli_governance.py -q --import-mode=importlib -k lean_smoke` passes
- `python -m pytest tests/test_lean_verify.py -q --import-mode=importlib` passes
- `python -m ruff check src/acgs_lite/cli.py src/acgs_lite/commands/lean_smoke.py src/acgs_lite/lean_verify.py tests/test_cli_governance.py tests/test_lean_verify.py` passes
- `python -m mypy src/acgs_lite/cli.py src/acgs_lite/commands/lean_smoke.py src/acgs_lite/lean_verify.py` passes

### Phase 8 — Close remaining Lean runtime risks
Status: completed on 2026-04-06

Goals:
- exercise the Lean runtime path with a real subprocess in tests instead of mocks only
- make `ACGS_LEAN_CMD` parsing more robust and script-friendly
- fail fast on unsupported shell syntax with actionable remediation guidance
- preserve backwards compatibility for existing command-string configuration

Verification targets:
- targeted regressions cover JSON-array command parsing, shell-syntax rejection, and fake-binary live subprocess execution
- `python -m pytest tests/test_lean_verify.py -q --import-mode=importlib -k "fake_runtime or json_command or shell_syntax"` passes
- `python -m pytest tests/test_cli_governance.py -q --import-mode=importlib -k lean_smoke` passes
- `python -m ruff check src/acgs_lite/cli.py src/acgs_lite/commands/lean_smoke.py src/acgs_lite/lean_verify.py tests/test_cli_governance.py tests/test_lean_verify.py` passes
- `python -m mypy src/acgs_lite/cli.py src/acgs_lite/commands/lean_smoke.py src/acgs_lite/lean_verify.py` passes

### Phase 9 — Document wrapper-script setup and optional Lean integration coverage
Status: completed on 2026-04-06

Goals:
- provide a sample wrapper script for Lean/Lake project execution
- document the preferred JSON-array `ACGS_LEAN_CMD` form and wrapper-script fallback
- add a real-toolchain pytest integration test that auto-runs only when `LEAN_INTEGRATION=1`
- keep the optional integration test skipped by default for normal package CI

Verification targets:
- `python -m pytest tests/test_lean_verify.py -q --import-mode=importlib -k real_toolchain` is skipped by default and ready to run when `LEAN_INTEGRATION=1`
- docs/examples mention `acgs lean-smoke`, wrapper scripts, and `LEAN_INTEGRATION=1`
- `python -m ruff check tests/test_lean_verify.py` passes

### Phase 10 — Unify ValidationResult and clear package mypy debt
Status: completed on 2026-04-06

### Phase 11 — Promote acgs-lite mypy to a real CI gate
Status: completed on 2026-04-06

Goals:
- remove failure suppression from the existing `mypy (acgs-lite)` workflow step
- run the step from `packages/acgs-lite` with the verified package-local mypy path
- enable merge-blocking type regression detection for `packages/acgs-lite`

Verification targets:
- `.github/workflows/ci.yml` no longer contains `|| true` in `mypy (acgs-lite)`
- `.github/workflows/ci.yml` runs `mypy (acgs-lite)` with `working-directory: packages/acgs-lite`
- `cd packages/acgs-lite && uv run mypy src/acgs_lite --ignore-missing-imports --no-error-summary` passes

### Phase 12 — Harden optional Z3 coverage for package CI
Status: completed on 2026-04-06

Goals:
- stop assuming `z3-solver` is always installed in `acgs-lite` test environments
- keep real-Z3 coverage when the optional solver is present
- preserve the graceful no-Z3 runtime contract while keeping the not-slow suite green

Verification targets:
- `python -m pytest tests/test_z3_verify_coverage.py -q --import-mode=importlib` passes
- `uv run pytest packages/acgs-lite/tests/ --import-mode=importlib -m "not slow" -x -q --timeout=120 --tb=short` passes
- `python -m ruff check src/acgs_lite/z3_verify.py tests/test_z3_verify_coverage.py` passes

### Phase 13 — Clean up acgs-lite test warnings
Status: completed on 2026-04-06

Goals:
- remove `PytestCollectionWarning` noise caused by imported `Test*` helper types in `test_rule_metrics.py`
- remove `InsecureKeyLengthWarning` noise from the invalid JWT test in `test_autonoma.py`
- keep the not-slow suite green without changing production behavior

Verification targets:
- `uv run pytest packages/acgs-lite/tests/test_rule_metrics.py packages/acgs-lite/tests/test_autonoma.py --import-mode=importlib -q --tb=short` passes without those warnings
- `uv run pytest packages/acgs-lite/tests/ --import-mode=importlib -m "not slow" -x -q --timeout=120 --tb=short` passes

Goals:
- collapse `engine.types.ValidationResult` and `engine.models.ValidationResult` onto one canonical class
- preserve public import compatibility while removing nominal-type divergence
- clean remaining package mypy errors in small, focused batches
- keep Lean/runtime regressions green while refactoring shared engine types

Verification targets:
- canonical `ValidationResult` regression passes
- `python -m pytest tests/test_lean_verify.py -q --import-mode=importlib` passes
- `python -m mypy src/acgs_lite` passes
- `python -m ruff check src/acgs_lite tests/test_acgs_namespace.py tests/test_lean_verify.py` passes

## Outcomes & Retrospective

- Public wrapper behavior is now protected by regression tests.
- API stats wiring now reports the actual audit trail used by the engine.
- Remaining work is mostly contract/documentation consolidation rather than emergency bug fixing.

## Surprises & Discoveries

- Full-package tests were already strong enough to safely tighten wrapper behavior once targeted regressions were added.
- `maci_role` had become a semantic trap: documented enough to imply enforcement, but not actually enforced.
- Whole-package `ruff check` still has substantial legacy debt outside the touched files.
