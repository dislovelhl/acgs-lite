# Quickstart: Deploying Your First Agentic Firewall

**Meta Description**: Get started with ACGS-Lite in under 5 minutes. Learn how to install the library, create a constitution, and govern your first autonomous AI agent.

---

Welcome to ACGS-Lite! This guide will help you set up your first **Agentic Firewall** to protect your infrastructure from autonomous agent risks.

## 1. Install ACGS-Lite

Install the core library via pip. For production use, we recommend installing with the `mcp` extra to enable the 2026-standard governance server.

```bash
pip install "acgs-lite[mcp]"
```

## 2. Create Your Constitution

A **Constitution** is a set of deterministic rules that your agent must follow. In 2026, it is best practice to define these in a `rules.yaml` file for version control and auditability.

Create a file named `rules.yaml`:

```yaml
# rules.yaml
name: standard-enterprise-safety
version: "2026.1.0"
rules:
  - id: block-pii
    pattern: "ssn|social security|passport number"
    severity: critical
    description: "Prevent PII leakage in agent output"
    
  - id: no-destructive-db
    pattern: "drop table|truncate|delete from .* where 1=1"
    severity: critical
    description: "Block destructive database operations"

  - id: formal-tone
    pattern: "stupid|idiot|hate"
    severity: medium
    description: "Enforce professional communication standards"
```

## 3. Govern Your First Agent

Wrap your existing agent or LLM client with `GovernedAgent`. ACGS-Lite intercepts all calls to ensure they are compliant *before* they execute.

```python
from acgs_lite import Constitution, GovernedAgent

# 1. Load your rules
constitution = Constitution.from_yaml("rules.yaml")

# 2. Wrap any callable (function, OpenAI client, LangChain agent, etc.)
# Here we wrap a simple mock agent
def my_agent(prompt: str) -> str:
    return f"Processed: {prompt}"

agent = GovernedAgent(my_agent, constitution=constitution)

# 3. Safe execution
try:
    result = agent.run("Summarize the report")
    print(f"Success: {result}")
    
    # This will trigger a ConstitutionalViolationError!
    agent.run("My social security number is 123-45-6789")
except Exception as e:
    print(f"Blocked by Governance: {e}")
```

## 4. Run the MCP Governance Server (2026 Standard)

In a multi-agent environment, you should run ACGS-Lite as a centralized **MCP Server**. This allows all your agents (and IDEs like Claude Desktop) to share the same safety rules.

```bash
# Run the governance server over stdio
python -m acgs_lite.integrations.mcp_server --constitution rules.yaml
```

## 5. Verify Your Audit Trail

Every decision made by the governance engine is cryptographically logged. You can inspect the trail to prove compliance to auditors.

```python
from acgs_lite import AuditLog

log = AuditLog()
for entry in log.entries[-5:]:
    print(f"[{entry.timestamp}] {entry.action} -> {entry.result} (Rules: {entry.rule_ids})")
```

---

## 🚀 Next Steps

*   **Deep Dive**: Learn about [MACI Architecture](maci.md) and separation of powers.
*   **Compliance**: Run an [EU AI Act Assessment](compliance-2026.md).
*   **Integrations**: See how to wrap [LangChain, AutoGen, or CrewAI](integrations.md).
*   **Advanced**: Implement [Verification Kernels](supervisor-models.md) for high-stakes tasks.
