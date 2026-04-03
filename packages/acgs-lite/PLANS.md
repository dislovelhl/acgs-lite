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

## Outcomes & Retrospective

- Public wrapper behavior is now protected by regression tests.
- API stats wiring now reports the actual audit trail used by the engine.
- Remaining work is mostly contract/documentation consolidation rather than emergency bug fixing.

## Surprises & Discoveries

- Full-package tests were already strong enough to safely tighten wrapper behavior once targeted regressions were added.
- `maci_role` had become a semantic trap: documented enough to imply enforcement, but not actually enforced.
- Whole-package `ruff check` still has substantial legacy debt outside the touched files.
