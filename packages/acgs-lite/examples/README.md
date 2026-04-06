# ACGS-Lite 2026.1.0 — Examples

Runnable quickstarts covering the core **Agentic Firewall** and **MACI** governance patterns.
**No API keys or network access required** for any of these examples.

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

## Integration Demos

| File | Description |
|------|-------------|
| [`quickstart.py`](quickstart.py) | 5-minute core API walkthrough |
| [`eu_ai_act_quickstart.py`](eu_ai_act_quickstart.py) | EU AI Act regulatory tool demo |
| [`gitlab_mr_governance.py`](gitlab_mr_governance.py) | GitLab MR governance CI/CD integration |
| [`quickstart_healthcare.py`](quickstart_healthcare.py) | Healthcare-specific rules and PII protection |

## Learning path

```
basic_governance  →  mcp_agent_client  →  maci_separation
        ↓
compliance_eu_ai_act  →  audit_trail  →  mock_stub_testing
```

For production deployments, see [`CONTRIBUTING.md`](../CONTRIBUTING.md) and the
`InMemory*` stub pattern in [`mock_stub_testing/`](mock_stub_testing/).
To learn more about the 2026 safety standards, see [`docs/owasp-2026.md`](../docs/owasp-2026.md).
