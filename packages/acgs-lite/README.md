# acgs-lite

[![PyPI](https://img.shields.io/pypi/v/acgs-lite)](https://pypi.org/project/acgs-lite/)
[![Python](https://img.shields.io/pypi/pyversions/acgs-lite)](https://pypi.org/project/acgs-lite/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)

**Constitutional AI governance for any agent — enforce rules, audit decisions, and prevent self-validation.**

`acgs-lite` is the core ACGS library. Load a constitution (a set of rules), wrap any agent or callable in `GovernedAgent`, and every action is validated before it executes. Violations are blocked; every decision is written to a tamper-evident audit log. MACI (separation of powers) prevents a single agent from proposing, validating, and executing the same action.

## Installation

```bash
pip install acgs-lite
```

Install with framework extras as needed:

```bash
pip install "acgs-lite[openai]"       # OpenAI integration
pip install "acgs-lite[anthropic]"    # Anthropic integration
pip install "acgs-lite[langchain]"    # LangChain integration
pip install "acgs-lite[a2a]"          # A2A SDK integration
pip install "acgs-lite[all]"          # All optional integrations
```

## Quick Start

### 1. Wrap an agent with constitutional governance

```python
from acgs_lite import Constitution, GovernedAgent

# Load rules from YAML
constitution = Constitution.from_yaml("rules.yaml")

# Wrap any callable
agent = GovernedAgent(my_llm_agent, constitution=constitution)

# Every call is validated before execution
result = agent.run("summarize the document")
```

### 2. Validate actions directly

```python
from acgs_lite import Constitution, GovernanceEngine, Rule, Severity

constitution = Constitution.from_rules([
    Rule(id="no-pii", pattern="SSN|social security", severity=Severity.CRITICAL,
         description="Block PII exposure"),
    Rule(id="no-delete", pattern="delete|drop table", severity=Severity.HIGH,
         description="Block destructive operations"),
])

engine = GovernanceEngine(constitution)
result = engine.validate("summarize the quarterly report", agent_id="agent-1")

if not result.valid:
    for v in result.violations:
        print(f"Blocked by rule {v.rule_id}: {v.message}")
```

### 3. MACI separation of powers

```python
from acgs_lite import MACIRole, MACIEnforcer, AuditLog

audit = AuditLog()
enforcer = MACIEnforcer(audit_log=audit)

enforcer.assign_role("agent-a", MACIRole.PROPOSER)
enforcer.assign_role("agent-b", MACIRole.VALIDATOR)

# agent-a can propose but not validate
enforcer.check("agent-a", "propose")   # OK
enforcer.check("agent-a", "validate")  # raises MACIViolationError
```

### 4. Persistent audit log (JSONL)

```python
from acgs_lite import AuditLog, JSONLAuditBackend

audit = AuditLog(backend=JSONLAuditBackend("audit.jsonl"))
engine = GovernanceEngine(constitution, audit_log=audit)
```

## Key Features

- **Constitutional rule engine** — YAML or programmatic rules with keyword, pattern, and context matching
- **`GovernedAgent` wrapper** — add governance to any agent or callable in one line
- **MACI enforcement** — PROPOSER / VALIDATOR / EXECUTOR / OBSERVER roles, enforced at runtime
- **Tamper-evident audit log** — hash-chained entries; `InMemoryAuditBackend` (default) or `JSONLAuditBackend`
- **Governance circuit breaker** — `GovernanceCircuitBreaker` halts an agent after repeated violations (Article 14 kill-switch)
- **Fail-closed decorator** — `@fail_closed` ensures any governance error blocks execution
- **Impact scoring** — `ConstitutionalImpactScorer` and `RuleBasedScorer` classify action risk
- **Z3 formal verification** — `Z3ConstraintVerifier` for high-risk actions (requires `z3-solver`)
- **Leanstral proof certificates** — `LeanstralVerifier` generates Lean 4 proofs (requires Mistral + Lean)
- **OpenShell governance** — `create_openshell_governance_app` / `create_openshell_governance_router` for Starlette/FastAPI integration
- **Framework integrations** — OpenAI, Anthropic, LangChain, LiteLLM, Google GenAI, LlamaIndex, AutoGen, CrewAI, MCP, A2A
- **CLI** — `acgs` / `acgs-lite` command for constitution management
- **Licensing tiers** — `set_license(key)` unlocks PRO/ENTERPRISE features

## API Reference

| Symbol | Description |
|--------|-------------|
| `Constitution` | Pydantic model holding a list of `Rule`s; load with `.from_yaml()`, `.from_rules()`, `.from_dict()` |
| `ConstitutionBuilder` | Fluent builder for constructing constitutions programmatically |
| `Rule` | A single governance rule with `id`, `pattern`, `severity`, `description`, `condition`, `valid_from/until` |
| `Severity` | Enum: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` — CRITICAL/HIGH block execution |
| `GovernanceEngine` | Validates actions against a constitution; `engine.validate(action, agent_id=...)` |
| `ValidationResult` | Result of a validation: `valid`, `violations`, `latency_ms`, `constitutional_hash` |
| `BatchValidationResult` | Result of bulk validation via `engine.validate_batch(...)` |
| `GovernedAgent` | Wraps any agent; intercepts `.run()` calls with governance |
| `GovernedCallable` | Wraps a plain function with governance (decorator or wrapper) |
| `AuditLog` | Hash-chained audit trail; pluggable via `AuditBackend` protocol |
| `AuditEntry` | Single immutable audit record |
| `AuditBackend` | Protocol for custom backends |
| `InMemoryAuditBackend` | Default in-memory backend |
| `JSONLAuditBackend` | Append-only JSONL file backend with fsync |
| `MACIRole` | Enum: `PROPOSER`, `VALIDATOR`, `EXECUTOR`, `OBSERVER` |
| `MACIEnforcer` | Assigns roles and enforces separation of powers |
| `GovernanceCircuitBreaker` | Halts an agent after a configurable violation threshold |
| `GovernanceHaltError` | Raised when the circuit breaker trips |
| `ConstitutionalImpactScorer` | Scores action impact using constitutional rules |
| `RuleBasedScorer` | Keyword-based impact scorer |
| `score_impact` | Convenience function for one-off scoring |
| `Z3ConstraintVerifier` | Formal verification using Z3 SMT solver |
| `LeanstralVerifier` | Lean 4 proof certificate generation via Mistral |
| `fail_closed` | Decorator: any governance exception blocks execution |
| `set_license(key)` | Activate a PRO/ENTERPRISE license for this process |

## Configuration

Rules YAML format:

```yaml
name: my-constitution
rules:
  - id: no-pii
    pattern: "SSN|social security|date of birth"
    severity: critical
    description: Block PII exposure
  - id: no-delete
    pattern: "delete|drop table|truncate"
    severity: high
    description: Block destructive database operations
    condition: "context.get('db_access', False)"
  - id: rate-limit-warning
    pattern: "bulk export"
    severity: medium
    description: Warn on bulk data operations
```

## Runtime dependencies

- `pydantic>=2.0`
- `pyyaml>=6.0`
- `click>=8.0`

## License

Apache-2.0. Commercial license available at [https://acgs.ai](https://acgs.ai).

## Links

- [Homepage](https://acgs.ai)
- [Documentation](https://acgs.ai/docs)
- [PyPI](https://pypi.org/project/acgs-lite/)
- [Issues](https://github.com/dislovelhl/acgs-lite/issues)
