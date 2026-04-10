# ACGS-Lite 2026.1.0 — Examples

Runnable quickstarts covering the core **Agentic Firewall** and **MACI** governance patterns.
**No API keys or network access required** for any of these examples.

## Canonical demo path

If you only try three things, do them in this order:

### 1. Block an unsafe action
Run [`basic_governance/`](./basic_governance/) first.

```bash
pip install acgs-lite
python examples/basic_governance/main.py
```

This is the fastest proof that `acgs-lite` is real: safe requests pass, unsafe ones are blocked.

### 2. Inspect the audit evidence
Run [`audit_trail/`](./audit_trail/).

```bash
python examples/audit_trail/main.py
```

This shows that governance decisions are not just transient checks, they become tamper-evident evidence.

### 3. Run governance as infrastructure
Run [`mcp_agent_client.py`](./mcp_agent_client.py).

```bash
pip install "acgs-lite[mcp]"
python examples/mcp_agent_client.py
```

This is the shared-service story: agent actions can be validated against a governance server before execution.

## Quickstart

```bash
pip install "acgs-lite[mcp]==2026.1.0"

# Run any example
python examples/basic_governance/main.py
python examples/mcp_agent_client.py
```

## 2026-Ready Examples

| Example | What it teaches | Difficulty |
|---------|----------------|------------|
| [`mcp_agent_client.py`](mcp_agent_client.py) | **MCP Governance Hub**: Connect an agent to a centralized safety server | ⭐⭐ Intermediate |
| [`basic_governance/`](basic_governance/) | Wrap any callable with a `Constitution` + `Rule` objects | ⭐ Beginner |
| [`compliance_eu_ai_act/`](compliance_eu_ai_act/) | EU AI Act risk-tier inference and article-level gap assessment | ⭐⭐ Intermediate |
| [`maci_separation/`](maci_separation/) | Proposer → Validator → Executor role gates; Golden Rule enforcement | ⭐⭐ Intermediate |
| [`audit_trail/`](audit_trail/) | Tamper-evident audit chain; query + JSON export | ⭐⭐ Intermediate |
| [`mock_stub_testing/`](mock_stub_testing/) | `typing.Protocol` + `InMemory*` stub pattern for production-grade testing | ⭐⭐⭐ Advanced |
| [`lean_runtime/`](lean_runtime/) | Lean runtime wrapper + `acgs lean-smoke` setup for real Lean/Lake projects | ⭐⭐ Intermediate |

## Integration Demos

| File | Description |
|------|-------------|
| [`quickstart.py`](quickstart.py) | 5-minute core API walkthrough |
| [`eu_ai_act_quickstart.py`](eu_ai_act_quickstart.py) | EU AI Act regulatory tool demo |
| [`gitlab_mr_governance.py`](gitlab_mr_governance.py) | GitLab MR governance CI/CD integration |
| [`quickstart_healthcare.py`](quickstart_healthcare.py) | Healthcare-specific rules and PII protection |

## Learning path

```text
basic_governance  →  audit_trail  →  mcp_agent_client
        ↓
maci_separation   →  compliance_eu_ai_act  →  mock_stub_testing
```

For production deployments, see [`CONTRIBUTING.md`](../CONTRIBUTING.md), the
`InMemory*` stub pattern in [`mock_stub_testing/`](mock_stub_testing/), and the
Lean toolchain wrapper example in [`lean_runtime/`](lean_runtime/).
To learn more about the 2026 safety standards, see [`docs/owasp-2026.md`](../docs/owasp-2026.md).
