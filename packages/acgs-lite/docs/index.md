# ACGS -- Constitutional AI Governance

**The missing safety layer between your LLM and production.**

ACGS is constitutional governance infrastructure for AI agents. Define rules in YAML,
enforce them at runtime with MACI role separation, and prove compliance with tamper-evident
audit trails.

## 5-Line Quickstart

```python
from acgs_lite import Constitution, GovernedAgent, MACIRole

constitution = Constitution.from_template("general")
agent = GovernedAgent(my_agent, constitution=constitution)
result = agent.run("process this request")  # Governed.
```

## Out-of-the-Box Compliance Coverage

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

**18 frameworks available. Run `acgs assess` to see coverage for your jurisdiction.**

## Next Steps

- [Quickstart](quickstart.md) -- Install and govern your first agent
- [Integrations](integrations.md) -- Anthropic, OpenAI, LangChain, and 8 more
- [Compliance](compliance.md) -- Multi-framework assessment
- [MACI Architecture](maci.md) -- Separation of powers for AI
- [CLI Reference](cli.md) -- All CLI commands
- [Contributing](contributing.md) -- How to contribute

!!! info "Constitutional Hash"
    `608508a9bd224290` -- documented constitutional hash for this release line. `acgs verify` currently validates license key integrity only.
