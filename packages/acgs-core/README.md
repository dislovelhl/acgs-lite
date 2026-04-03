# acgs

Constitutional AI Governance for Any Agent.

Validate agent actions against constitutional rules, enforce MACI role
separation (Proposer / Validator / Executor / Observer), and maintain
hash-chained audit trails. Framework-agnostic — works with any AI agent.

## Quickstart

```python
from acgs import Constitution, GovernanceEngine, Rule, Severity

constitution = Constitution.from_rules([
    Rule(id="R1", text="No self-approval", severity=Severity.HIGH,
         keywords=["self-approve"])
])
engine = GovernanceEngine(constitution, strict=False)
result = engine.validate("self-approve this change")
print(result.valid)       # False
print(result.violations)  # [Violation(rule_id='R1', ...)]
```

## Install

```bash
pip install acgs                  # core (zero heavy deps)
pip install acgs[cedar]           # embedded Cedar policy engine
pip install acgs[fastapi]         # HTTP server
pip install acgs[anthropic]       # Anthropic adapter
pip install acgs[langchain]       # LangChain adapter
```

## Architecture

```
Agent (any framework)
  │
  ▼
GovernanceEngine.validate(action)
  │
  ├── PolicyBackend (pluggable)
  │   ├── HeuristicBackend (default, <0.3ms)
  │   └── CedarBackend     (pip install acgs[cedar], sub-ms)
  │
  ├── MACIEnforcer (role separation)
  │   ├── Proposer  → propose, draft, suggest, read
  │   ├── Validator → validate, review, audit, read
  │   ├── Executor  → execute, deploy, apply, read
  │   └── Observer  → read, query, export, observe
  │
  └── AuditStore (pluggable)
      ├── InMemoryAuditStore (default)
      └── SQLiteAuditStore   (persistent, hash-chained)
```

No external policy server required. No OPA. No Rego.
Cedar is optional and embedded (cedarpy, Rust-backed).

## Public API

| Export | Purpose |
|--------|---------|
| `Constitution` | Rule set with hash integrity |
| `Rule` | Individual governance rule |
| `Severity` | CRITICAL / HIGH / MEDIUM / LOW |
| `GovernanceEngine` | Core validation engine |
| `ValidationResult` | Validation outcome |
| `Violation` | Individual rule violation |
| `MACIRole` | Role enum for separation of powers |
| `MACIEnforcer` | Role-based access control |
| `AuditEntry` | Single audit record |
| `AuditLog` | In-memory audit trail |
| `fail_closed` | Decorator for fail-closed error handling |

## License

AGPL-3.0-or-later. Commercial license available at https://acgs.ai.
