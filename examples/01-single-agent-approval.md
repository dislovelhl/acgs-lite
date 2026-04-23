# Example 1: Single-Agent High-Value Action Approval

**Scenario:** Financial analyst agent attempts to execute a $500,000 wire transfer.

## The Problem Without Governance

```python
# Without acgs-lite: agent calls execute_transfer → money moves immediately
agent.execute_transfer(amount=500_000, recipient="external-account-9f3a")
```

## Constitution (constitution.yaml)

```yaml
constitutional_hash: "608508a9bd224290"
rules:
  - id: high_value_transfer
    pattern: "transfer|wire|payment"
    condition: "amount > 100000"
    severity: CRITICAL
    workflow_action: require_human_review
    message: "High-value transfer requires CFO approval"

  - id: standard_transfer
    pattern: "transfer|wire|payment"
    severity: HIGH
    workflow_action: block_and_notify
    message: "Transfer blocked — use approved channels"
```

## Runtime Integration

```python
from acgs_lite import Constitution, GovernanceEngine
from acgs_lite import ConstitutionalViolationError

constitution = Constitution.from_yaml("constitution.yaml")
engine = GovernanceEngine(constitution, strict=True)

# Agent proposes action
action = "wire transfer $500,000 to external-account-9f3a"

try:
    result = engine.validate(action, agent_id="analyst-agent-01")
    if result.valid:
        execute_transfer(amount=500_000)
except ConstitutionalViolationError as exc:
    # Action blocked before execution
    for v in exc.violations:
        print(f"BLOCKED [{v.severity}]: {v.rule_id} — {v.description}")
```

## What Happens at Runtime

1. `analyst-agent-01` proposes the transfer action
2. `GovernanceEngine.validate()` matches `high_value_transfer` rule → **BLOCKED**
3. Audit entry created immediately:

```json
{
  "decision_id": "dec_9f3a2b",
  "timestamp": "2026-04-23T03:41:12Z",
  "agent_id": "analyst-agent-01",
  "action": "wire transfer $500,000 to external-account-9f3a",
  "verdict": "require_human_review",
  "rule_matched": "high_value_transfer",
  "constitutional_hash": "608508a9bd224290",
  "audit_hash": "a7f9c2d3e1b04890f2a1c3d5e7f9a2b4"
}
```

4. Human reviewer receives alert with approve/deny link
5. Transfer executes **only** after human approval is recorded in the audit chain

## Evidence for Auditors

```bash
# Inspect the decision chain
acgs audit --tail 10

# Verify chain integrity (tamper detection)
acgs audit --verify-chain

# Export compliance report
acgs assess --framework eu-ai-act --output compliance-report.pdf
```

Every decision — including the block, the human review request, and the eventual approval or denial — is in the tamper-evident SHA-256 chain.

## Run This Example

```bash
pip install acgs-lite
python examples/basic_governance/main.py
```

For a runnable version of this scenario, see [`examples/basic_governance/`](./basic_governance/).
