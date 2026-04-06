# ACGS -- Constitutional AI Governance

**The missing safety layer between your LLM and production.**

ACGS is constitutional governance infrastructure for AI agents. Define rules in YAML, enforce them at runtime with MACI role separation, and prove compliance with tamper-evident audit trails. 

As autonomous AI agents take on increasingly complex tasks, traditional "bolted-on" security measures fall short. ACGS introduces **Governed Autonomy**—a model where agents operate freely within mathematically and procedurally defined "safe zones" but must trigger escalation paths or human-in-the-loop (HITL) reviews for high-risk actions.

## 5-Line Quickstart

```python
from acgs_lite import Constitution, GovernedAgent

# 1. Load rules from your Constitution
constitution = Constitution.from_yaml("rules.yaml")

# 2. Wrap your existing agent
agent = GovernedAgent(my_llm_agent, constitution=constitution)

# 3. Safely execute with deterministic validation
result = agent.run("Process this request")
```

## Out-of-the-Box Compliance Coverage

ACGS automatically maps governance constraints to 18 global regulatory frameworks, streamlining audits and risk assessments.

| Framework | Business Risk | Auto-Coverage |
|---|---|---|
| **EU AI Act** | 7% global revenue penalty | 5/9 |
| **NIST AI RMF** | US Federal procurement gate | 7/16 |
| **ISO/IEC 42001** | International audit failure | 9/18 |
| **SOC 2 + AI** | Enterprise gate / lost contracts | 10/16 |
| **HIPAA + AI** | $1.5M fine per violation | 9/15 |
| **GDPR Art. 22** | 4% global revenue | 10/12 |
| **ECOA/FCRA** | Unlimited damages | 6/12 |
| **NYC LL 144** | $1,500/day | 6/12 |
| **OECD AI** | Baseline standard | 10/15 |

**Run `acgs assess` to see coverage for your jurisdiction and domain.**

## Next Steps & Guides

Explore the architecture and setup guides to integrate ACGS into your agentic workflows:

- [Why Constitutional Governance?](why-governance.md) -- Understand the Agentic Firewall and emerging AI risks
- [Industry Use Cases](use-cases.md) -- Healthcare, Finance, and Legal in practice
- [OWASP 2026 Mitigation](owasp-2026.md) -- Mitigating the Top 10 risks for agents
- [2026 Regulatory Compliance](compliance-2026.md) -- EU AI Act, SB 205, and TRAIGA
- [MCP Governance Server](mcp.md) -- Centralized safety for the agentic mesh
- [Advanced Safety Patterns](supervisor-models.md) -- Verification Kernels & Supervisor Models
- [MCP Governance Guide](mcp-guide.md) -- Master the Model Context Protocol
- [Testing Governance](testing-governance.md) -- Verifying your Agentic Firewall
- [Quickstart](quickstart.md) -- Install and govern your first agent
- [Integrations](integrations.md) -- Guides for Anthropic, OpenAI, LangChain, AutoGen, CrewAI, and more
- [Compliance](compliance.md) -- Deep dive into multi-framework assessment
- [MACI Architecture](maci.md) -- Implementing separation of powers for AI
- [Architecture Overview](architecture.md) -- Internal engine and validation lifecycle
- [CLI Reference](cli.md) -- All CLI commands for CI/CD and terminal use

---
!!! info "Constitutional Hash"
    `608508a9bd224290` -- documented constitutional hash for this release line. `acgs verify` currently validates license key integrity only.
