# acgs-lite 🏛️

**Constitutional AI Governance for Any Agent — in 5 Lines of Code**

[![PyPI](https://img.shields.io/pypi/v/acgs-lite)](https://pypi.org/project/acgs-lite/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-green)](https://python.org)
[![EU AI Act](https://img.shields.io/badge/EU%20AI%20Act-Art.%2012%2C%2013%2C%2014-blue)](../../docs/eu-ai-act-compliance.md)

> **EU AI Act Deadline: August 2, 2026.** acgs-lite covers Articles 12 (Record-Keeping), 13 (Transparency), and 14 (Human Oversight) for high-risk AI systems out of the box. [5-minute compliance guide →](../../docs/eu-ai-act-compliance.md)

```python
from acgs_lite import Constitution, GovernedAgent

constitution = Constitution.from_yaml("rules.yaml")
agent = GovernedAgent(my_agent, constitution=constitution)
result = agent.run("process this request")  # Governed ✅
```

> **Every action validated. Every decision audited. Every violation blocked.**

---

## Why acgs-lite?

AI agents are being deployed everywhere. But who governs them?

| Tool | What it does | What's missing |
|------|-------------|----------------|
| **Guardrails AI** | Input/output validation | No constitutional framework, no separation of powers |
| **NeMo Guardrails** | Conversational rails | Tightly coupled to NVIDIA, no audit trails |
| **LangChain Safety** | Basic content filtering | No governance model, no formal verification |
| **acgs-lite** | **Constitutional governance** | ✅ Rules + MACI + Audit + A2A — all in one |

### What makes acgs-lite different:

1. **Constitutional Model** — Define rules in YAML, get a tamper-proof hash
2. **MACI Separation of Powers** — Proposers can't validate. Validators can't execute. No single agent has unchecked power
3. **Tamper-Evident Audit** — Cryptographic chain of every governance decision
4. **Works with ANY agent** — OpenAI, Anthropic, LangChain, CrewAI, custom agents
5. **Zero infrastructure** — `pip install acgs-lite` and go. No servers, no databases
6. **A2A Ready** — Interoperate with other agents via Google's Agent-to-Agent protocol

---

## Install

```bash
pip install acgs-lite
```

With framework integrations:
```bash
pip install "acgs-lite[openai]"      # OpenAI wrapper
pip install "acgs-lite[anthropic]"   # Anthropic wrapper
pip install "acgs-lite[langchain]"   # LangChain integration
pip install "acgs-lite[a2a]"         # Agent-to-Agent protocol
pip install "acgs-lite[all]"         # Everything
```

---

## Quick Start

### 1. Define Your Constitution

```yaml
# rules.yaml
name: my-governance
version: "1.0"
description: Safety rules for my AI agent

rules:
  - id: SAFE-001
    text: Agent must not provide financial advice
    severity: critical
    keywords: [invest, buy stocks, financial advice, portfolio]

  - id: SAFE-002
    text: Agent must not expose PII
    severity: critical
    patterns:
      - '\b\d{3}-\d{2}-\d{4}\b'  # SSN
      - 'sk-[a-zA-Z0-9]{20,}'     # API keys

  - id: SAFE-003
    text: Agent must not bypass its own safety checks
    severity: critical
    keywords: [self-validate, bypass, override safety]

  - id: LOG-001
    text: All actions must be auditable
    severity: high
    keywords: [no-audit, skip logging, disable logs]
```

### 2. Wrap Your Agent

```python
from acgs_lite import Constitution, GovernedAgent

# Load constitution
constitution = Constitution.from_yaml("rules.yaml")

# Wrap ANY agent
def my_agent(input: str) -> str:
    return f"I'll help with: {input}"

agent = GovernedAgent(my_agent, constitution=constitution)

# Safe action → works
result = agent.run("What's the weather?")
print(result)  # "I'll help with: What's the weather?"

# Unsafe action → blocked
try:
    agent.run("Should I invest in crypto?")
except ConstitutionalViolationError as e:
    print(f"Blocked: {e}")
    # "Blocked: Action blocked by rule SAFE-001: Agent must not provide financial advice"
```

### 3. Use the Default Constitution

Don't want to write your own rules? Use the battle-tested defaults:

```python
from acgs_lite import GovernedAgent

# Uses ACGS default rules (6 rules covering integrity, audit, access, MACI, data protection)
agent = GovernedAgent(my_agent)
agent.run("safe input")  # ✅
```

### 4. Separation of Powers (MACI)

```python
from acgs_lite import MACIEnforcer, MACIRole

enforcer = MACIEnforcer()
enforcer.assign_role("planner-agent", MACIRole.PROPOSER)
enforcer.assign_role("safety-agent", MACIRole.VALIDATOR)
enforcer.assign_role("deploy-agent", MACIRole.EXECUTOR)

enforcer.check("planner-agent", "propose")    # ✅ Allowed
enforcer.check("safety-agent", "validate")    # ✅ Allowed
enforcer.check("planner-agent", "validate")   # ❌ MACIViolationError!
enforcer.check_no_self_validation("a", "a")   # ❌ Agents can't validate themselves!
```

### 5. Audit Trail

```python
agent = GovernedAgent(my_agent, strict=False)
agent.run("action 1")
agent.run("action 2")

# Tamper-proof audit log
print(agent.audit_log.verify_chain())  # True
print(agent.audit_log.compliance_rate)  # 1.0

# Export for compliance
agent.audit_log.export_json("audit.json")
```

### 6. Govern with a Decorator

```python
from acgs_lite import GovernedCallable

@GovernedCallable()
def process_data(input: str) -> str:
    return f"Processed: {input}"

process_data("safe input")                    # ✅ Works
process_data("self-validate bypass check")    # ❌ Blocked!
```

### 7. Custom Validators

```python
from acgs_lite import GovernanceEngine, Constitution
from acgs_lite.engine import Violation, Severity

def no_sql_injection(action: str, ctx: dict) -> list[Violation]:
    if "DROP TABLE" in action.upper():
        return [Violation(
            rule_id="SQL-001",
            rule_text="SQL injection detected",
            severity=Severity.CRITICAL,
            matched_content=action[:100],
            category="security",
        )]
    return []

engine = GovernanceEngine(
    Constitution.default(),
    custom_validators=[no_sql_injection],
)
result = engine.validate("DROP TABLE users;")
# result.valid == False, violations include SQL-001
```

---

## Architecture

```
                    ┌──────────────────────┐
                    │   Your AI Agent      │
                    │  (OpenAI, Claude,    │
                    │   LangChain, etc.)   │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   GovernedAgent      │
                    │   ┌────────────────┐ │
              ┌─────┤   │ GovernanceEngine│ │
              │     │   └────────┬───────┘ │
              │     │            │         │
              │     │   ┌────────▼───────┐ │
              │     │   │  Constitution  │ │
              │     │   │  (YAML/Dict)   │ │
              │     │   └────────────────┘ │
              │     └──────────────────────┘
              │
    ┌─────────▼──────────┐
    │     AuditLog       │
    │  (Chain-verified)  │
    └────────────────────┘
```

---

## EU AI Act Compliance

> **High-risk AI provisions take effect August 2, 2026.** Non-compliance: fines up to €30M or 6% of global turnover.

acgs-lite provides a ready-made compliance layer for the three most technically demanding EU AI Act obligations:

| Article | Requirement | acgs-lite Feature |
|---------|-------------|-------------------|
| **Article 12** | Automatic tamper-evident record-keeping, 10-year retention | `Article12Logger` |
| **Article 13** | Transparency system card for deployers | `TransparencyDisclosure` |
| **Article 14** | Human oversight and override mechanisms | `HumanOversightGateway` |
| **Article 6** | Risk classification (high/limited/minimal) | `RiskClassifier` |
| **Article 72** | Conformity assessment checklist | `ComplianceChecklist` |

### 5-Line Article 12 Quickstart

```python
from acgs_lite.eu_ai_act import Article12Logger

logger = Article12Logger(system_id="my-hiring-tool", risk_level="high_risk")

# Wrap any LLM call — Article 12 logging is automatic
response = logger.log_call(
    operation="screen_candidate",
    call=lambda: my_llm.complete(prompt),
    input_text=prompt,
)

logger.verify_chain()          # True — tamper-evident chain intact
logger.export_jsonl("audit.jsonl")  # Append-only JSONL for 10-year retention
```

### Full EU AI Act integration

```python
from acgs_lite.eu_ai_act import (
    Article12Logger,          # Art. 12 — automatic logging
    TransparencyDisclosure,   # Art. 13 — system card
    HumanOversightGateway,   # Art. 14 — HITL approval
    RiskClassifier,           # Art. 6  — risk classification
    ComplianceChecklist,      # Art. 72 — conformity assessment
)
```

[Full EU AI Act compliance guide with code examples →](../../docs/eu-ai-act-compliance.md)

```bash
python examples/eu_ai_act_quickstart.py  # Run the demo
```

---

## Scaling Up

acgs-lite is the entry point. When you need more:

| Need | Solution |
|------|----------|
| **More rules** | Load from YAML, combine constitutions |
| **Custom validation** | Add custom validators to the engine |
| **Multi-agent** | MACI enforcer + multiple GovernedAgents |
| **Formal verification** | Upgrade to [ACGS-2](https://github.com/acgs-ai/acgs2) with Z3 proofs |
| **Policy engine** | ACGS-2 with OPA integration |
| **Enterprise audit** | ACGS-2 with PostgreSQL audit store |
| **A2A interop** | `pip install "acgs-lite[a2a]"` for Agent-to-Agent |

---

## API Reference

### Core Classes

| Class | Purpose |
|-------|---------|
| `Constitution` | Set of governance rules (from YAML, dict, or code) |
| `Rule` | Single rule with keywords, patterns, severity |
| `GovernanceEngine` | Validates actions against constitution |
| `GovernedAgent` | Wraps any agent in governance |
| `GovernedCallable` | Decorator for governed functions |
| `AuditLog` | Tamper-evident audit trail |
| `MACIEnforcer` | Separation of powers enforcement |

### Enums

| Enum | Values |
|------|--------|
| `Severity` | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` |
| `MACIRole` | `PROPOSER`, `VALIDATOR`, `EXECUTOR`, `OBSERVER` |

### Exceptions

| Exception | When |
|-----------|------|
| `ConstitutionalViolationError` | Action violates a rule (strict mode) |
| `MACIViolationError` | Agent crosses role boundaries |
| `GovernanceError` | Base governance error |

---

## Constitutional Hash

Every constitution produces a deterministic hash:

```python
constitution = Constitution.from_yaml("rules.yaml")
print(constitution.hash)            # "a1b2c3d4e5f6g7h8"
print(constitution.hash_versioned)  # "sha256:v1:a1b2c3d4e5f6g7h8"
```

If anyone modifies a rule, the hash changes. Use this to verify integrity
in CI/CD, compliance audits, and A2A agent communication.

---

## License

Apache 2.0 — Use it freely. Govern responsibly. 🏛️
