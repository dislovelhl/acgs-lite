# MessageProcessor Coverage-Regeneration Cleanup Plan

> Updated: 2026-04-01
> Scope: wrapper retirement after coordinator/finalizer extraction

This document turns the remaining `MessageProcessor` wrapper cleanup into an execution plan that is
compatible with the current constraint:

- **Do not hand-edit files under `packages/enhanced_agent_bus/tests/coverage/*`.**

Instead, handwritten tests and mainline orchestration are migrated first, then the remaining wrapper
surface is retired in batches once the coverage shards are regenerated or replaced.

---

## 1. Current status

### Already deleted safely

These wrappers were removed without touching coverage shards because they no longer had required
non-doc call sites:

- `_execute_verification_and_processing(...)`
- `_persist_flywheel_decision_event(...)`

### Remaining wrappers by disposition

#### Delete after coverage regeneration
- `_extract_session_context(...)`
- `_perform_security_scan(...)`
- `_requires_independent_validation(...)`
- `_enforce_independent_validator_gate(...)`
- `_enforce_autonomy_tier(...)`
- `_extract_message_session_id(...)`
- `_attach_session_context(...)`

#### Keep for compat / orchestration
- `_send_to_dlq(...)`
- `_detect_prompt_injection(...)`
- `_handle_successful_processing(...)`
- `_handle_failed_processing(...)`

Notes:
- `_send_to_dlq(...)` still has non-coverage tests and owns `_dlq_redis` reset semantics.
- `_detect_prompt_injection(...)` has an explicit compat requirement in
  `tests/test_processor_redesign.py`.
- `_handle_successful_processing(...)` and `_handle_failed_processing(...)` remain useful facade
  seams for `VerificationCoordinator` and explicit sink orchestration.

---

## 2. Coverage shard blocker matrix

The table below is the exact current blocker map for wrapper deletion.

| Coverage shard | Blocking wrappers |
| --- | --- |
| `test_bus_cov_batch7.py` | `_requires_independent_validation`, `_enforce_independent_validator_gate` |
| `test_bus_cov_batch13.py` | `_requires_independent_validation`, `_enforce_independent_validator_gate` |
| `test_bus_cov_batch14.py` | `_requires_independent_validation`, `_enforce_independent_validator_gate` |
| `test_bus_cov_batch20a.py` | `_extract_session_context`, `_perform_security_scan`, `_requires_independent_validation`, `_enforce_independent_validator_gate`, `_enforce_autonomy_tier`, `_extract_message_session_id`, `_attach_session_context`, `_send_to_dlq`, `_handle_successful_processing`, `_handle_failed_processing` |
| `test_bus_cov_batch24e.py` | `_extract_session_context`, `_perform_security_scan`, `_requires_independent_validation`, `_enforce_independent_validator_gate`, `_send_to_dlq`, `_detect_prompt_injection`, `_handle_successful_processing`, `_handle_failed_processing` |
| `test_bus_cov_batch31a.py` | `_send_to_dlq`, `_handle_failed_processing` |
| `test_bus_cov_batch32a.py` | `_enforce_independent_validator_gate`, `_send_to_dlq` |

---

## 3. Per-wrapper blocker detail

### A. Validation-policy wrappers

#### `_requires_independent_validation(...)`
Blocked by:
- `test_bus_cov_batch7.py`
- `test_bus_cov_batch13.py`
- `test_bus_cov_batch14.py`
- `test_bus_cov_batch20a.py`
- `test_bus_cov_batch24e.py`

Replacement coverage already exists in handwritten tests:
- `tests/test_gate_coordinator.py`

#### `_enforce_independent_validator_gate(...)`
Blocked by:
- `test_bus_cov_batch7.py`
- `test_bus_cov_batch13.py`
- `test_bus_cov_batch14.py`
- `test_bus_cov_batch20a.py`
- `test_bus_cov_batch24e.py`
- `test_bus_cov_batch32a.py`

Replacement coverage already exists in handwritten tests:
- `tests/test_gate_coordinator.py`

### B. Session/security wrappers

#### `_extract_session_context(...)`
Blocked by:
- `test_bus_cov_batch20a.py`
- `test_bus_cov_batch24e.py`

Replacement coverage already exists in handwritten tests:
- `tests/test_session_coordinator.py`

#### `_perform_security_scan(...)`
Blocked by:
- `test_bus_cov_batch20a.py`
- `test_bus_cov_batch24e.py`

Replacement coverage already exists in handwritten tests:
- `tests/test_gate_coordinator.py`

#### `_attach_session_context(...)`
Blocked by:
- `test_bus_cov_batch20a.py`

Replacement coverage already exists in handwritten tests:
- `tests/test_session_coordinator.py`

### C. Thin helper wrappers

#### `_enforce_autonomy_tier(...)`
Blocked by:
- `test_bus_cov_batch20a.py`

Replacement coverage already exists in handwritten tests:
- `tests/test_gate_coordinator.py`

#### `_extract_message_session_id(...)`
Blocked by:
- `test_bus_cov_batch20a.py`

Replacement coverage already exists in handwritten tests:
- `tests/test_session_coordinator.py`

### D. Compat-kept wrappers

#### `_send_to_dlq(...)`
Coverage blockers:
- `test_bus_cov_batch20a.py`
- `test_bus_cov_batch24e.py`
- `test_bus_cov_batch31a.py`
- `test_bus_cov_batch32a.py`

Additional non-coverage blockers:
- `tests/test_kafka_streaming_coverage.py`
- `tests/test_kafka_event_streaming.py`

Decision:
- **keep for now**
- reconsider only after moving `_dlq_redis` reset semantics into a dedicated collaborator or after
  intentionally changing the compat surface

#### `_detect_prompt_injection(...)`
Coverage blockers:
- `test_bus_cov_batch24e.py`

Additional non-coverage blockers:
- `tests/test_message_processor_coverage.py`
- `tests/test_processor_redesign.py` explicitly states the helper must remain for downstream compat

Decision:
- **keep for compat**

#### `_handle_successful_processing(...)`
Coverage blockers:
- `test_bus_cov_batch20a.py`
- `test_bus_cov_batch24e.py`

Decision:
- **keep for orchestration**
- it remains a useful facade seam used by `VerificationCoordinator`

#### `_handle_failed_processing(...)`
Coverage blockers:
- `test_bus_cov_batch20a.py`
- `test_bus_cov_batch24e.py`
- `test_bus_cov_batch31a.py`

Decision:
- **keep for orchestration**
- it remains a useful facade seam used by `VerificationCoordinator`

---

## 4. Deletion dependency order

This is the recommended deletion order once coverage regeneration is available.

### Batch 1 — policy/gate wrappers
Delete first because they are already fully covered by `GateCoordinator` tests and are not needed by
mainline orchestration.

1. `_requires_independent_validation(...)`
2. `_enforce_independent_validator_gate(...)`

Blocked coverage shards:
- `test_bus_cov_batch7.py`
- `test_bus_cov_batch13.py`
- `test_bus_cov_batch14.py`
- `test_bus_cov_batch20a.py`
- `test_bus_cov_batch24e.py`
- `test_bus_cov_batch32a.py`

Ready-to-run sequence once coverage is regenerated:
1. `make health-bus-wrappers`
2. `make health-bus-wrappers-batch1-ready`
3. verify regenerated shards no longer reference the two wrappers
4. delete the two wrappers from `message_processor.py`
5. run handwritten regressions
6. run `packages/enhanced_agent_bus/tests/coverage/test_bus_cov_batch20a.py`
7. update architecture/audit docs

### Batch 2 — session/security wrappers
Delete next because coordinator coverage is already in place and mainline orchestration already uses
`SessionCoordinator` directly.

3. `_extract_session_context(...)`
4. `_perform_security_scan(...)`
5. `_attach_session_context(...)`

Blocked coverage shards:
- `test_bus_cov_batch20a.py`
- `test_bus_cov_batch24e.py`

### Batch 3 — isolated thin helpers
Delete after batch 2 because the only remaining pressure is a narrow slice of coverage-shard usage.

6. `_enforce_autonomy_tier(...)`
7. `_extract_message_session_id(...)`

Blocked coverage shards:
- `test_bus_cov_batch20a.py`

### Keep batch — do not delete in the next round
Do **not** schedule these for the next deletion batch unless the compatibility decision changes.

- `_send_to_dlq(...)`
- `_detect_prompt_injection(...)`
- `_handle_successful_processing(...)`
- `_handle_failed_processing(...)`

---

## 5. Coverage-regeneration execution checklist

### Phase A — pre-regeneration confirmation
- [ ] Run the wrapper audit gate:
  - `python packages/enhanced_agent_bus/tools/message_processor_wrapper_audit.py --check`
  - or `make health-bus-wrappers`
- [ ] Confirm handwritten test ownership remains in:
  - `tests/test_session_coordinator.py`
  - `tests/test_gate_coordinator.py`
  - `tests/test_verification_coordinator.py`
  - `tests/test_result_finalizer.py`
  - `tests/test_message_processor_architecture.py`
- [ ] Confirm mainline `MessageProcessor` path still bypasses removed wrappers
- [ ] Confirm no new non-coverage tests were added that directly call the delete-after-regeneration wrappers

### Phase B — regenerate coverage shards
- [ ] Re-run the repository's coverage-shard generation workflow
- [ ] Verify regenerated shards stop calling:
  - `_requires_independent_validation(...)`
  - `_enforce_independent_validator_gate(...)`
  - `_extract_session_context(...)`
  - `_perform_security_scan(...)`
  - `_attach_session_context(...)`
  - `_enforce_autonomy_tier(...)`
  - `_extract_message_session_id(...)`
- [ ] Do not hand-edit `tests/coverage/*`

### Phase C — wrapper deletion batches
- [ ] Delete Batch 1 wrappers
- [ ] Run targeted pytest + coverage shard smoke
- [ ] Delete Batch 2 wrappers
- [ ] Run targeted pytest + coverage shard smoke
- [ ] Delete Batch 3 wrappers
- [ ] Run targeted pytest + coverage shard smoke

### Phase D — post-delete audit update
- [ ] Update `MESSAGE_PROCESSOR_ARCHITECTURE.md`
- [ ] Update `MESSAGE_PROCESSOR_FINAL_ARCHITECTURE_AUDIT.md`
- [ ] Reclassify remaining wrappers into permanent keep vs future compat review

---

## 6. Verification commands

### Wrapper audit gate
```bash
python packages/enhanced_agent_bus/tools/message_processor_wrapper_audit.py --check
# or
make health-bus-wrappers
```

### Batch 1 readiness gate
```bash
python packages/enhanced_agent_bus/tools/message_processor_wrapper_audit.py --ready-batch batch1
# or
make health-bus-wrappers-batch1-ready
```

### Handwritten regression set
```bash
python -m pytest \
  packages/enhanced_agent_bus/tests/test_session_coordinator.py \
  packages/enhanced_agent_bus/tests/test_gate_coordinator.py \
  packages/enhanced_agent_bus/tests/test_verification_coordinator.py \
  packages/enhanced_agent_bus/tests/test_result_finalizer.py \
  packages/enhanced_agent_bus/tests/test_message_processor_extracted_components.py \
  packages/enhanced_agent_bus/tests/test_message_processor_architecture.py \
  packages/enhanced_agent_bus/tests/test_message_processor_helpers.py \
  packages/enhanced_agent_bus/tests/test_governance_core.py \
  packages/enhanced_agent_bus/tests/test_message_processor_session.py \
  packages/enhanced_agent_bus/tests/test_message_processor_independent_validator_gate.py \
  --import-mode=importlib -q
```

### Coverage-shard smoke set
```bash
python -m pytest \
  packages/enhanced_agent_bus/tests/coverage/test_bus_cov_batch20a.py \
  --import-mode=importlib -q
```

### Ruff
```bash
python -m ruff check \
  packages/enhanced_agent_bus/message_processor.py \
  packages/enhanced_agent_bus/tools/message_processor_wrapper_audit.py \
  packages/enhanced_agent_bus/tests/test_message_processor_architecture.py \
  packages/enhanced_agent_bus/docs/MESSAGE_PROCESSOR_ARCHITECTURE.md \
  packages/enhanced_agent_bus/docs/MESSAGE_PROCESSOR_FINAL_ARCHITECTURE_AUDIT.md \
  packages/enhanced_agent_bus/docs/MESSAGE_PROCESSOR_COVERAGE_REGEN_CLEANUP_PLAN.md
```
