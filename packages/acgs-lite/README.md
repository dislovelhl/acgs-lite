# ACGS-Lite: Constitutional AI Governance for Agents

[![PyPI](https://img.shields.io/pypi/v/acgs-lite?color=blue&style=for-the-badge)](https://pypi.org/project/acgs-lite/)
[![Python](https://img.shields.io/pypi/pyversions/acgs-lite?style=for-the-badge)](https://pypi.org/project/acgs-lite/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-green.svg?style=for-the-badge)](https://www.apache.org/licenses/LICENSE-2.0)
[![Documentation](https://img.shields.io/badge/docs-acgs.ai-brightgreen?style=for-the-badge)](https://acgs.ai/docs)

**The missing safety layer between your LLM and production.**

`acgs-lite` is the core library for Constitutional AI Governance. It allows you to define rules in YAML, enforce them at runtime with MACI role separation, and prove compliance with tamper-evident audit trails. Stop bolting on security post-deployment; embed ethical principles and behavioral guidelines directly into your autonomous systems.

Unlike traditional AI security that relies on prompt engineering, ACGS interposes a deterministic Governance Engine between your agent and its tools. Every action is validated before execution. Violations are blocked, and every decision is written to a cryptographic audit log.

---

## 🚀 5-Line Quickstart

Wrap any LLM client, function, or LangChain/AutoGen agent in `GovernedAgent` to automatically apply constitutional constraints.

```python
from acgs_lite import Constitution, GovernedAgent

# 1. Load rules from your Constitution (YAML or Code)
constitution = Constitution.from_yaml("rules.yaml")

# 2. Wrap your existing agent or callable
agent = GovernedAgent(my_llm_agent, constitution=constitution)

# 3. Every call is strictly validated against the constitution before execution!
result = agent.run("Process this high-risk transaction") 
```

## 📦 Installation

```bash
pip install acgs-lite
```

Install with your favorite framework extras to get native adapters:
```bash
pip install "acgs-lite[openai]"       # OpenAI integration
pip install "acgs-lite[anthropic]"    # Anthropic integration
pip install "acgs-lite[langchain]"    # LangChain integration
pip install "acgs-lite[mcp]"          # MCP Server integration
pip install "acgs-lite[all]"          # All optional integrations
```

## 🛡️ Why ACGS? Key Features

### 1. The "Agentic Firewall"
A protocol-layer defense that verifies an agent's compliance with its constitution before granting access to sensitive tools or infrastructure. Define rules using keyword, pattern, and context matching.

### 2. MACI: Separation of Powers
Without MACI, an agent can propose an action and approve it in the same step. MACI (Monitor-Approve-Control-Inspect) makes this structurally impossible by separating roles:
*   **Proposer**: Generates proposed actions. Cannot execute or validate.
*   **Validator**: Checks actions against the constitution. Cannot propose or execute.
*   **Executor**: Carries out approved actions.
*   **Observer**: Cryptographically records the audit trail.

### 3. Out-of-the-Box Compliance Coverage
ACGS maps controls across 18 regulatory frameworks globally. Use `acgs assess` to see coverage for your jurisdiction.

| Framework | Business Risk | Auto-Coverage |
|---|---|---|
| **EU AI Act** | 7% global revenue penalty | 5/9 |
| **NIST AI RMF** | US Federal procurement gate | 7/16 |
| **SOC 2 + AI** | Enterprise gate / lost contracts | 10/16 |
| **HIPAA + AI** | $1.5M fine per violation | 9/15 |
| **GDPR Art. 22** | 4% global revenue penalty | 10/12 |

### 4. Tamper-Evident Audit Trails
Every governance decision produces an immutable `AuditEntry` chained via SHA-256 hashes (`JSONLAuditBackend` or `InMemoryAuditBackend`). Prove to auditors exactly why your agent made a decision, knowing the log cannot be retroactively altered.

### 5. Advanced Verification
For the highest-risk scenarios, ACGS supports:
*   **Z3 Formal Verification**: `Z3ConstraintVerifier` uses SMT solvers to mathematically prove safe states.
*   **Leanstral Proof Certificates**: `LeanstralVerifier` generates Lean 4 proofs via Mistral.

## 📖 Documentation & Next Steps

*   [Documentation Home](https://acgs.ai/docs)
*   [Integrations Guide](docs/integrations.md)
*   [Compliance Assessment](docs/compliance.md)
*   [MACI Architecture](docs/maci.md)
*   [Why AI Governance?](docs/why-governance.md)

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) and [Code of Conduct](CODE_OF_CONDUCT.md).

## 📄 License

Apache-2.0. Commercial enterprise licenses available at [https://acgs.ai](https://acgs.ai).
