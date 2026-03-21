# ACGS -- HTTPS for AI

**Constitutional governance infrastructure for AI agents. Five lines of code. Nine regulatory frameworks. Tamper-evident audit trail.**

The EU AI Act takes full enforcement **August 2026**. Fines up to **7% of global annual revenue**. Deployment without provable governance is becoming uninsurable. ACGS gives you cryptographic proof that AI decisions are constitutionally compliant.

```bash
pip install acgs
```

```python
from acgs_lite import Constitution, GovernedAgent

constitution = Constitution.from_yaml("rules.yaml")
agent = GovernedAgent(my_agent, constitution=constitution)
result = agent.run("process this request")  # Governed.
```

Every action validated against constitutional rules. Every decision recorded in a tamper-evident audit trail. Every role boundary enforced.

---

## Before / After

```python
# BEFORE: Ungoverned
agent.run("Should I invest in crypto?")  # Executes. No record. No limits.

# AFTER: ACGS-Lite
agent = GovernedAgent(my_agent, constitution=constitution)
agent.run("Should I invest in crypto?")  # Blocked: SAFE-001. Logged. Auditable.
```

---

## Regulatory Compliance (9 Frameworks)

| Framework | Jurisdiction | Penalty | ACGS-Lite Coverage |
|---|---|---|---|
| **EU AI Act** | EU (27 states) | 7% global revenue | 5/9 items auto |
| **NIST AI RMF** | US (federal) | Procurement gate | 7/16 items auto |
| **ISO/IEC 42001** | International | Audit failure | 9/18 items auto |
| **GDPR Art. 22** | EU | 4% global revenue | 10/12 items auto |
| **SOC 2 + AI** | International | Lost contracts | 10/16 items auto |
| **HIPAA + AI** | US (healthcare) | $1.5M/violation | 9/15 items auto |
| **ECOA/FCRA** | US (finance) | Unlimited damages | 6/12 items auto |
| **NYC LL 144** | New York City | $1,500/day | 6/12 items auto |
| **OECD AI** | 46 countries | Baseline standard | 10/15 items auto |

**125 compliance checklist items. 72 auto-populated by ACGS-Lite.**

```python
from acgs_lite.compliance import MultiFrameworkAssessor

assessor = MultiFrameworkAssessor()
report = assessor.assess({"jurisdiction": "EU", "domain": "healthcare"})
print(report.overall_score)        # 0.62 (auto-populated)
print(report.cross_framework_gaps) # Items needing manual evidence
```

---

## MACI Separation of Powers

Agents never validate their own output.

- **Proposer** submits actions or amendments
- **Validator** independently evaluates constitutional compliance
- **Executor** performs approved actions
- **Observer** monitors and audits

Self-validation prevention, action risk classification (LOW/MEDIUM/HIGH/CRITICAL), escalation tiers, and full audit trail of every role assignment.

---

## Platform Integrations

| Platform | Install | Status |
|----------|---------|--------|
| **Anthropic** | `acgs[anthropic]` | Production |
| **MCP** | `acgs[mcp]` | Production |
| OpenAI | `acgs[openai]` | Maintained |
| LangChain | `acgs[langchain]` | Maintained |
| LiteLLM | `acgs[litellm]` | Maintained |
| Google GenAI | `acgs[google]` | Experimental |
| LlamaIndex | `acgs[llamaindex]` | Experimental |
| AutoGen | `acgs[autogen]` | Experimental |
| CrewAI | `acgs[crewai]` | Experimental |
| A2A | `acgs[a2a]` | Experimental |

---

## Architecture

```
                        Your AI Agent
                   (OpenAI, Claude, Gemini,
                    LangChain, CrewAI, etc.)
                            |
                            v
               +------------------------+
               |     GovernedAgent      |
               |                        |
               |  +------------------+  |         +------------------+
               |  | GovernanceEngine |--+-------->|    AuditLog      |
               |  |                  |  |         | (chain-verified) |
               |  |  Constitution    |  |         +------------------+
               |  |  (YAML / Dict)   |  |
               |  |                  |  |         +------------------+
               |  |  MACI Enforcer  |--+-------->| Role Boundaries  |
               |  |                  |  |         | (separation of   |
               |  +------------------+  |         |  powers)         |
               +------------------------+         +------------------+
                            |
            +---------------+----------------+
            |               |                |
            v               v                v
    GitLab Webhook    MCP Server       CI/CD Gate
    (MR governance)   (Duo Chat)    (pipeline stage)
```

---

## Quick Start

### Define Your Constitution

```yaml
# rules.yaml
name: my-governance
version: "1.0"
rules:
  - id: SAFE-001
    text: Agent must not provide financial advice
    severity: critical
    keywords: [invest, buy stocks, financial advice]

  - id: SAFE-002
    text: Agent must not expose PII
    severity: critical
    patterns:
      - '\b\d{3}-\d{2}-\d{4}\b'   # SSN
      - 'sk-[a-zA-Z0-9]{20,}'      # API keys
```

### Use a Pre-Built Template

```python
from acgs_lite import Constitution, GovernanceEngine

constitution = Constitution.from_template("gitlab")
engine = GovernanceEngine(constitution)

report = engine.validate_batch_report([
    "deploy to staging",
    "auto-approve merge request",   # Blocked: GL-001 (MACI)
    "commit clean code",
])
print(report.summary)  # "FAIL: 1/3 actions blocked, compliance=66.7%"
```

### Build Programmatically

```python
from acgs_lite import ConstitutionBuilder

constitution = (
    ConstitutionBuilder("my-governance", version="2.0.0")
    .add_rule("SAFE-001", "No financial advice", severity="critical",
              keywords=["invest", "buy stocks"], workflow_action="block")
    .add_rule("SAFE-002", "No PII exposure", severity="critical",
              patterns=[r"\b\d{3}-\d{2}-\d{4}\b"], workflow_action="block_and_notify")
    .build()
)
```

---

## API Reference

| Class | Purpose |
|-------|---------|
| `Constitution` | Rule set from YAML, dict, or code |
| `GovernanceEngine` | Validates actions against constitution |
| `GovernedAgent` | Wraps any agent in governance |
| `GovernedCallable` | Decorator for governed functions |
| `AuditLog` | Tamper-evident audit trail |
| `MACIEnforcer` | Separation of powers enforcement |
| `ConstitutionBuilder` | Fluent API for code-first governance |
| `MultiFrameworkAssessor` | Multi-framework compliance assessment |

---

## More

- [Origin story: How a non-technical founder built this with AI](docs/ORIGIN.md)
- [GitLab Duo integration guide](docs/GITLAB.md)
- [Full feature reference](docs/FEATURES.md)

---

## License

Apache-2.0 -- Use it freely. Govern responsibly.

---

*Built with Claude. Governed by constitution.*
