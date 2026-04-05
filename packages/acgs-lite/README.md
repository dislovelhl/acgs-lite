# acgs-lite

[![PyPI](https://img.shields.io/pypi/v/acgs-lite)](https://pypi.org/project/acgs-lite/)
[![Python](https://img.shields.io/pypi/pyversions/acgs-lite)](https://pypi.org/project/acgs-lite/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![CI](https://github.com/dislovelhl/acgs-lite/actions/workflows/ci.yml/badge.svg)](https://github.com/dislovelhl/acgs-lite/actions/workflows/ci.yml)

**Constitutional governance infrastructure for AI agents.**

`acgs-lite` lets you define constitutional rules in YAML or code, validate inputs and
outputs deterministically, enforce MACI role separation, and maintain tamper-evident
audit trails. Install name: `acgs-lite`. Import namespace: `acgs_lite`.

## Installation

`acgs-lite` supports Python 3.10+.

```bash
pip install acgs-lite
pip install acgs-lite[anthropic]
pip install acgs-lite[openai]
pip install acgs-lite[langchain]
pip install acgs-lite[mcp]
pip install acgs-lite[gitlab]
pip install acgs-lite[autonoma]
pip install acgs-lite[pdf]
pip install acgs-lite[all]
```

## Quick Start

```python
from acgs_lite import Constitution, GovernedAgent

constitution = Constitution.from_template("general")
agent = GovernedAgent(my_agent, constitution=constitution)
result = agent.run("process this request")
```

### Custom Rules

```python
from acgs_lite import Constitution, GovernedAgent, Rule, Severity

constitution = Constitution.from_rules([
    Rule(
        id="NO-PII",
        text="Do not include personally identifiable information",
        severity=Severity.CRITICAL,
        keywords=["ssn", "social security", "passport"],
    ),
    Rule(
        id="NO-HARM",
        text="Do not provide harmful instructions",
        severity=Severity.HIGH,
        keywords=["malware", "exploit"],
    ),
])

agent = GovernedAgent(my_agent, constitution=constitution)
result = agent.run("summarize the report")
```

### YAML Rules

```yaml
# rules.yaml
rules:
  - id: NO-PII
    text: Never include personally identifiable information
    severity: CRITICAL
    keywords: [ssn, social security, passport]
  - id: NO-MEDICAL-ADVICE
    text: Do not provide specific medical diagnoses
    severity: HIGH
    keywords: [diagnose, prescription, dosage]
```

```python
from acgs_lite import Constitution, GovernedAgent

constitution = Constitution.from_yaml("rules.yaml")
agent = GovernedAgent(my_agent, constitution=constitution)
```

### MACI Role Separation

```python
from acgs_lite import Constitution, GovernedAgent, MACIRole

constitution = Constitution.from_template("general")
agent = GovernedAgent(
    my_agent,
    constitution=constitution,
    maci_role=MACIRole.PROPOSER,
    enforce_maci=True,
)

result = agent.run("draft deployment plan", governance_action="propose")
```

### Compliance Assessment

```python
from acgs_lite.compliance import MultiFrameworkAssessor

assessor = MultiFrameworkAssessor()
report = assessor.assess(
    {
        "system_id": "claims-triage",
        "jurisdiction": "european_union",
        "domain": "healthcare",
    }
)

print(report.frameworks_assessed)
print(f"Coverage: {report.acgs_lite_total_coverage:.0%}")
```

### HTTP Middleware

```python
from acgs_lite import Constitution
from acgs_lite.middleware import GovernanceASGIMiddleware

constitution = Constitution.from_template("general")
app.add_middleware(
    GovernanceASGIMiddleware,
    constitution=constitution,
    strict=False,
    validate_responses=True,
)
```

### Async Execution

```python
result = await agent.arun("async task")
```

## Key Features

- Deterministic constitutional validation with YAML rules, regex support, severity
  levels, merge/diff helpers, and hash verification.
- MACI role separation with explicit proposer, validator, executor, and observer
  boundaries.
- Compliance helpers spanning EU AI Act, NIST AI RMF, ISO 42001, SOC 2 + AI, HIPAA
  + AI, GDPR Article 22, ECOA/FCRA, NYC LL 144, and OECD AI.
- Tamper-evident audit trails with SHA-256 chain verification and telemetry hooks.
- Optional integrations for Anthropic, OpenAI, LangChain, LiteLLM, Google GenAI,
  LlamaIndex, AutoGen, MCP, GitLab CI/CD, A2A, CrewAI, and ASGI/FastAPI servers.
- Constrained output and remediation-oriented retry flows for stricter production
  governance.

## CLI

```bash
acgs init
acgs assess --jurisdiction EU
acgs report --pdf
acgs lint rules.yaml
acgs test --fixtures tests.yaml
acgs eu-ai-act --domain healthcare
acgs refusal "approve deployment"
acgs observe "action" --prometheus
```

## License

Apache-2.0. See [LICENSE](LICENSE) for details.

## Links

- [Homepage](https://acgs.ai)
- [Documentation](https://acgs.ai/docs)
- [PyPI](https://pypi.org/project/acgs-lite/)
- [GitHub](https://github.com/dislovelhl/acgs-lite)
- [Issues](https://github.com/dislovelhl/acgs-lite/issues)
- [Changelog](https://github.com/dislovelhl/acgs-lite/blob/main/CHANGELOG.md)

Constitutional Hash: `608508a9bd224290`
