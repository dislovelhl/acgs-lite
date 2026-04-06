# Governance Core Test Plan

This test plan adapts the subsystem-oriented testing style from the inspected Claude CLI workspace
and makes it specific to ACGS governance code.

> Part of the ACGS workflow docs. Start at [`../README.md`](../README.md) for the full workflow/reference set.

## Scope

Primary scope:
- `packages/enhanced_agent_bus/message_processor.py`
- `packages/enhanced_agent_bus/governance_core.py`
- `packages/enhanced_agent_bus/verification_orchestrator.py`
- `packages/enhanced_agent_bus/config.py`
- related targeted regression tests under `packages/enhanced_agent_bus/tests/`

Primary fast gate:

```bash
make health-bus-governance
```

## What This Plan Must Prove

| Area | Expected outcome |
| --- | --- |
| Governance decisions | Approvals, denials, and receipts are attached consistently |
| Independent validation | Proposer and validator roles remain separated |
| Failure handling | Rejections and verification failures flow through consistent sinks with metadata |
| Config safety | Security/governance defaults stay fail-closed |
| Backward compatibility | Existing governance-core tests still pass |

## Targeted Command Set

### 1. Lint only the governance slice

```bash
ruff check \
  packages/enhanced_agent_bus/governance_core.py \
  packages/enhanced_agent_bus/message_processor.py \
  packages/enhanced_agent_bus/verification_orchestrator.py \
  packages/enhanced_agent_bus/config.py \
  packages/enhanced_agent_bus/tests/test_governance_core.py \
  packages/enhanced_agent_bus/tests/test_config.py
```

### 2. Run the governance regression slice

```bash
python3 -m pytest --import-mode=importlib -q \
  packages/enhanced_agent_bus/tests/test_governance_core.py \
  packages/enhanced_agent_bus/tests/test_config.py \
  packages/enhanced_agent_bus/tests/test_message_processor_coverage.py \
  packages/enhanced_agent_bus/tests/test_processor_redesign.py::TestMessageProcessorBackwardCompat \
  packages/enhanced_agent_bus/tests/test_environment_check.py \
  packages/enhanced_agent_bus/tests/test_security_defaults.py \
  packages/enhanced_agent_bus/tests/test_message_processor_independent_validator_gate.py
```

### 3. Expand if the change touches wider routing or constitutional code

```bash
python3 -m pytest packages/enhanced_agent_bus/tests/ -m "constitutional or maci" \
  --import-mode=importlib -v
```

## Scenario Matrix

### A. Governance receipt propagation

- approvals produce a governance receipt
- denials produce rejection metadata
- cache-hit and replay paths preserve governance metadata

### B. Independent validator gate

- proposer output is not treated as self-validating
- validator failures reject execution
- executor behavior only proceeds after valid approval

### C. Common failure sink behavior

- early gate failures are recorded consistently
- verification failures are recorded consistently
- audit/DLQ/persistence behavior stays aligned across failure stages

### D. Security/config defaults

- missing critical config fails closed
- stale constitutional hash is rejected
- insecure default toggles do not silently enable risky behavior

## When to Expand Beyond This Plan

Escalate from `make health-bus-governance` to broader checks when:
- shared auth/security code changes
- API gateway request/response contracts change
- persistence or saga semantics change
- frontend or worker integrations are affected

Recommended expansion path:

```bash
make test-bus
make test-quick
bash .claude/commands/test-and-verify.sh --quick
```

## Expected Deliverables for Governance-Core Work

- updated eval under `.claude/evals/`
- targeted regression tests for the bug/fix/change
- explicit note on whether failures are baseline debt or newly introduced
- verification output citing the exact governance command(s) run

## Related docs

- [`../testing-spec.md`](../testing-spec.md) — repository-wide testing model
- [`../subagent-execution.md`](../subagent-execution.md) — how to delegate governance-core implementation and verification safely
- [`../worktree-isolation.md`](../worktree-isolation.md) — isolation pattern for risky governance changes
