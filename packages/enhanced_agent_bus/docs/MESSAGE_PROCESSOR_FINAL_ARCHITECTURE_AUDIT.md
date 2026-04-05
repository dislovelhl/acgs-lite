# MessageProcessor Final Architecture Audit

> Updated: 2026-04-01
> Scope: `packages/enhanced_agent_bus/message_processor.py`

## Executive Summary

The high-risk architectural issues that motivated the refactor are now materially addressed:

- hidden governance state no longer lives on `AgentMessage`
- early failures use common sink paths
- stage ownership is explicit via extracted coordinators/finalizer
- `MessageProcessor` now acts primarily as a facade/orchestrator

The remaining issues are mostly **compatibility and maintainability debt**, not major integrity
failures.

---

## 1. Wrapper Inventory

`MessageProcessor` still contains transitional facade wrappers, but one full batch of pure
forwarders has already been retired. The remaining wrappers now fall into four practical
categories: keep-for-now sink adapters, compatibility/coverage debt, already-retired forwarders,
and small helpers worth keeping.

### A. Wrappers that should stay for now

These are still directly referenced by tests and/or serve as stable monkeypatch seams:

| Wrapper | Why it should stay for now |
| --- | --- |
| `_handle_successful_processing(...)` | Facade-owned sink binding point into `ResultFinalizer`; still a useful orchestration seam |
| `_handle_failed_processing(...)` | Facade-owned sink binding point into `ResultFinalizer`; still a useful orchestration seam |
| `_attach_session_context(...)` | Backward-compatible bridge that still accepts both `MessageProcessingContext` and legacy `AgentMessage` inputs; mainline processing no longer uses it |
| `_send_to_dlq(...)` | Small compatibility adapter that binds cached Redis acquisition and reset semantics into `ResultFinalizer`; mainline processing no longer uses it |

### B. Wrappers now mostly kept only for compatibility / coverage debt

Handwritten tests have now been migrated to `SessionCoordinator`, `GateCoordinator`,
`VerificationCoordinator`, and `ResultFinalizer` for these behaviors. The mainline processor path
also now bypasses several of these wrappers directly. What remains is mostly coverage-shard and
downstream compatibility pressure.

| Wrapper | Current blocker to removal |
| --- | --- |
| `_extract_session_context(...)` | Legacy/coverage tests still call the facade method directly |
| `_perform_security_scan(...)` | Legacy/coverage tests still call the facade method directly |
| `_requires_independent_validation(...)` | Coverage shards still exercise facade policy-threshold behavior |
| `_enforce_independent_validator_gate(...)` | Coverage shards still exercise facade gate behavior |
| `_enforce_autonomy_tier(...)` | Coverage shards still patch/call the facade-level helper |
| `_extract_message_session_id(...)` | Coverage shards still patch `extract_session_id_for_pacar` through the facade module |
| `_detect_prompt_injection(...)` | Coverage shards and explicit compat tests still call the facade helper |

### C. Wrappers already retired in the latest cleanup pass

The following facade-level pure forwarders were removed and their behavior is now exercised through
coordinator/finalizer-level tests:

- `_initialize_session_context_manager(...)`
- `_build_session_resolver(...)`
- `_perform_sdpc_verification(...)`
- `_perform_pqc_validation(...)`
- `_run_validation_gates(...)`
- `_build_governance_input(...)`
- `_run_governance_core(...)`
- `_store_governance_artifacts(...)`
- `_attach_governance_metadata(...)`
- `_build_governance_failure_result(...)`
- `_schedule_governance_audit_event(...)`
- `_emit_governance_audit_event(...)`
- `_execute_verification_and_processing(...)`
- `_persist_flywheel_decision_event(...)`

### D. Wrappers likely worth keeping permanently

These are small and improve readability even if they delegate:

| Wrapper | Why keeping it may be reasonable |
| --- | --- |
| `_compute_cache_key(...)` | Keeps cache policy close to facade orchestration |
| `_clone_validation_result(...)` | Small utility with clear facade ownership |
| `_extract_rejection_reason(...)` | Harmless adapter with stable call site |

---

## 2. Delete-Readiness Table

The current removal plan, under the explicit constraint of **not hand-editing coverage shards**, is:

| Wrapper | Readiness | Rationale |
| --- | --- | --- |
| `_execute_verification_and_processing(...)` | **deleted now** | Mainline no longer used it; no remaining non-doc call sites required it |
| `_persist_flywheel_decision_event(...)` | **deleted now** | Mainline no longer used it; direct behavior is covered at `ResultFinalizer` level |
| `_extract_session_context(...)` | **delete after coverage regeneration** | Remaining repo references are coverage-driven facade calls |
| `_perform_security_scan(...)` | **delete after coverage regeneration** | Remaining repo references are coverage-driven facade calls |
| `_requires_independent_validation(...)` | **delete after coverage regeneration** | Remaining repo references are mainly coverage-shard facade assertions |
| `_enforce_independent_validator_gate(...)` | **delete after coverage regeneration** | Remaining repo references are mainly coverage-shard facade assertions |
| `_enforce_autonomy_tier(...)` | **delete after coverage regeneration** | Remaining repo references are coverage-shard facade delegation tests |
| `_extract_message_session_id(...)` | **delete after coverage regeneration** | Remaining repo references are coverage-shard facade assertions and commentary |
| `_attach_session_context(...)` | **delete after coverage regeneration** | Backward-compatible signature remains exercised by coverage shards |
| `_send_to_dlq(...)` | **keep for compat (for now)** | Non-coverage tests still call the facade method and the adapter owns `_dlq_redis` reset semantics |
| `_detect_prompt_injection(...)` | **keep for compat** | Explicit compat test states it must remain for downstream callers |
| `_handle_successful_processing(...)` | **keep for compat / orchestration** | Useful facade-owned sink seam used by `VerificationCoordinator` |
| `_handle_failed_processing(...)` | **keep for compat / orchestration** | Useful facade-owned sink seam used by `VerificationCoordinator` |

This table should be treated as the source of truth for the next deletion batches.
For the coverage-shard-by-shard blocker map and executable cleanup order, see
`MESSAGE_PROCESSOR_COVERAGE_REGEN_CLEANUP_PLAN.md`.

---

## 3. Dependency-Synchronization Audit

### What was improved

Runtime dependency synchronization is now more centralized:

- `SessionCoordinator.sync_runtime(...)`
- `GateCoordinator.sync_runtime(...)`
- `GovernanceCoordinator.sync_runtime(...)`
- `VerificationCoordinator.sync_runtime(...)`
- `MessageProcessor._sync_coordinator_runtime()` provides one push point
- `MessageProcessor._sync_runtime_state_from_coordinators()` provides one pull point

This is better than direct attribute mutation scattered across multiple wrapper methods.

### What still remains

There is still a **runtime re-binding pattern** because existing tests monkeypatch facade fields such
as:

- `_security_scanner`
- `_record_agent_workflow_event`
- `_verification_orchestrator`
- `_processing_strategy`
- `_handle_successful_processing`
- `_handle_failed_processing`

As long as those remain supported seams, some sync step is unavoidable.

### Is further reduction worth it?

**Not immediately.**

To remove more sync logic, the project would need to intentionally migrate tests and downstream code
away from mutating facade internals and toward injecting collaborators at construction time or
patching coordinator instances directly.

That is feasible, but it is a separate cleanup project, not a correctness fix.

---

## 4. Remaining Theoretical Risks

### Risk 1 — Compatibility wrappers keep the facade large

**Severity:** Low  
**Type:** Maintainability

Even after extraction, `MessageProcessor` remains larger than ideal because it preserves a legacy
private-helper surface.

**Worth further splitting?**
- **Not urgently** for correctness
- **Yes eventually** if the team is ready to migrate tests to coordinator-level coverage

### Risk 2 — Monkeypatch-driven runtime rebinding

**Severity:** Low-to-medium  
**Type:** Testability / maintenance

The coordinator sync layer exists because tests and some internal call paths still treat the facade
as a patch surface.

**Worth further splitting?**
- **Only if** the project is willing to standardize constructor injection and reduce monkeypatching
- Otherwise the current centralized sync is an acceptable compromise

### Risk 3 — ResultFinalizer still uses wide call-time dependency injection

**Severity:** Low  
**Type:** API ergonomics

`ResultFinalizer` is stateless, which is good, but its methods accept many runtime dependencies from
`MessageProcessor`.

**Worth further splitting?**
- **Probably not now**
- A future `ResultSinkBindings` object could reduce parameter width, but this is cosmetic unless it
  becomes hard to reason about

### Risk 4 — Constructor wiring is still dense

**Severity:** Low  
**Type:** Readability

`MessageProcessor.__init__` still performs a lot of runtime assembly.

**Worth further splitting?**
- **Possibly**, via a `MessageProcessorRuntimeFactory` or builder
- But this is secondary to the already-completed integrity hardening work

### Risk 5 — Governance/session/cache orchestration still lives in one facade method

**Severity:** Low  
**Type:** Readability / change risk

`_do_process(...)` is now much simpler than before, but it still sequences multiple concerns.

**Worth further splitting?**
- **Not necessary** unless future feature growth makes `_do_process(...)` complex again
- Right now it is serving as the intended high-level orchestration layer

---

## 5. What no longer looks like a major risk

The following former concerns are now substantially mitigated:

- hidden governance state on message objects
- inconsistent failure sink behavior across early exits
- missing failure-stage metadata for rejected results
- audit gaps for non-governance failures
- over-centralized gate/governance/verification implementations

---

## 6. Recommendation

### Recommended stopping point for this refactor

**Stop here for architectural correctness.**

The remaining work is mostly cleanup and simplification, not remediation of dangerous theoretical
integrity issues.

### Optional future cleanup project

If desired, a future low-risk cleanup session could:

1. migrate helper tests from facade-private methods to coordinator-level tests
2. remove no-longer-needed facade wrappers in batches
3. introduce a small `ResultFinalizerBindings` or runtime-factory object if constructor/finalizer
   wiring becomes cumbersome

That work would improve elegance, but it is not required to consider the architecture materially
hardened.
