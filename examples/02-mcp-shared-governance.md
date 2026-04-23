# Example 2: MCP Shared Governance Service for Multiple Agents

**Scenario:** Five different agents (data analyst, code reviewer, email sender, file manager, API caller) share a single governance server. One policy. Every agent validated. Central audit trail.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Governance MCP Server                     │
│                  acgs serve --port 8080                      │
│                                                              │
│   Constitution (shared policy)  ←  constitutional_hash      │
│   GovernanceEngine (fail-closed)                             │
│   AuditLog (SHA-256 chained, SQLite)                         │
└──────────┬──────────┬──────────┬──────────┬─────────────────┘
           │          │          │          │          │
    data-   code-    email-   file-      api-
   analyst reviewer  sender  manager   caller
   agent    agent    agent    agent     agent
```

## Start the Governance Server

```bash
# Option 1: CLI (simplest)
acgs serve --host 0.0.0.0 --port 8080 --constitution shared-policy.yaml

# Option 2: Python
from acgs_lite.integrations.mcp_server import create_mcp_server
from acgs_lite import Constitution

constitution = Constitution.from_yaml("shared-policy.yaml")
app = create_mcp_server(constitution=constitution)
# uvicorn app:app --port 8080
```

## Shared Policy (shared-policy.yaml)

```yaml
constitutional_hash: "608508a9bd224290"
rules:
  - id: no-pii-exfiltration
    pattern: "SSN|passport|credit.card|social.security"
    severity: CRITICAL
    workflow_action: halt_and_alert
    message: "PII exfiltration blocked"

  - id: no-destructive-ops
    pattern: "delete|drop.table|rm -rf|format"
    severity: HIGH
    workflow_action: require_human_review
    message: "Destructive operation requires human approval"

  - id: external-transfer-gate
    pattern: "transfer|wire|send.payment"
    severity: HIGH
    workflow_action: require_human_review
    message: "Financial operation requires CFO approval"

  - id: code-injection-guard
    pattern: "eval\(|exec\(|subprocess|__import__"
    severity: CRITICAL
    workflow_action: block
    message: "Code injection pattern blocked"
```

## Each Agent Calls the Shared Server

```python
import httpx

GOVERNANCE_URL = "http://localhost:8080"

def governed_action(agent_id: str, action: str) -> dict:
    """Call shared governance before any agent action."""
    response = httpx.post(
        f"{GOVERNANCE_URL}/validate",
        json={"action": action, "agent_id": agent_id},
    )
    result = response.json()
    if not result["valid"]:
        raise RuntimeError(f"Action blocked: {result['violations']}")
    return result

# Each agent uses the same governance check
governed_action("data-analyst", "summarize Q4 revenue report")      # ✅ Passes
governed_action("email-sender", "send quarterly update to team")     # ✅ Passes
governed_action("file-manager", "delete /tmp/scratch")               # 🔶 Requires review
governed_action("api-caller", "transfer $5000 to vendor-account")    # 🔶 Requires review
governed_action("code-reviewer", "eval(user_input)")                 # 🚫 Blocked
```

## Violation Under Quarantine

When an agent triggers a `halt_and_alert` rule, it is automatically quarantined:

```python
# After PII violation:
# 1. data-analyst agent is quarantined
# 2. All subsequent validate() calls return blocked until quarantine is lifted
# 3. Alert sent to operator

# Operator lifts quarantine:
acgs resume --agent-id data-analyst --reason "false positive confirmed"
```

## Inspect the Shared Audit Trail

```bash
# All agents' decisions in one chain
acgs audit --tail 50

# Filter by agent
acgs audit --agent-id email-sender

# Verify no tampering across all 5 agents' decisions
acgs audit --verify-chain

# Export per-agent compliance evidence
acgs assess --framework hipaa --agent-id data-analyst --output hipaa-data-analyst.pdf
```

## Why Shared Governance Is Better Than Per-Agent

| | Per-agent governance | Shared MCP governance |
|---|---|---|
| Policy drift | Each agent has its own version | One policy, enforced everywhere |
| Audit trail | Fragmented across agents | Single verifiable chain |
| Updates | Update each agent separately | Update one server, all agents inherit |
| Quarantine | Agent-local | Cross-agent: one agent's violation can trigger review of others |
| Compliance proof | Aggregate manually | Single `acgs audit --verify-chain` |

## Run This Example

```bash
# Terminal 1: Start governance server
acgs serve --port 8080

# Terminal 2: Run the multi-agent demo
python examples/mcp_agent_client.py
```

See [`examples/mcp_agent_client.py`](./mcp_agent_client.py) for a working client example.
