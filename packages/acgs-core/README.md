# acgs

[![PyPI](https://img.shields.io/pypi/v/acgs)](https://pypi.org/project/acgs/)
[![Python](https://img.shields.io/pypi/pyversions/acgs)](https://pypi.org/project/acgs/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

**Framework-agnostic governance SDK for AI agents.**

`acgs` is the stable public namespace over `acgs-lite`. It re-exports the core
governance primitives and adds pluggable policy backends plus persistent audit stores
without requiring an external policy server.

## Installation

`acgs` supports Python 3.10+.

```bash
pip install acgs
pip install acgs[cedar]
pip install acgs[fastapi]
pip install acgs[anthropic]
pip install acgs[openai]
pip install acgs[langchain]
```

## Quick Start

```python
from acgs import Constitution, GovernanceEngine, Rule, Severity

constitution = Constitution.from_rules([
    Rule(
        id="NO-SELF-APPROVAL",
        text="Agents may not self-approve production changes",
        severity=Severity.HIGH,
        keywords=["self-approve"],
    ),
])

engine = GovernanceEngine(constitution, strict=False)
result = engine.validate("self-approve this deployment", agent_id="agent-7")

assert result.valid is False
assert result.violations[0].rule_id == "NO-SELF-APPROVAL"
```

## Policy Backends

### Heuristic Backend

```python
from acgs import Constitution, GovernanceEngine
from acgs.policy import HeuristicBackend

constitution = Constitution.default()
engine = GovernanceEngine(constitution, strict=False)
backend = HeuristicBackend(engine)

decision = backend.evaluate(action="deploy to prod", agent_id="bot-1")
print(decision.allowed, decision.backend, decision.latency_ms)
```

### Cedar Backend

```python
from acgs.cedar import CedarBackend

backend = CedarBackend.from_policy_dir("./policies")
decision = backend.evaluate(
    action="read:patient-records",
    agent_id="clinical-bot",
    context={"role": "EXECUTIVE", "department": "cardiology"},
)
```

## Audit Stores

### SQLite Audit Store

```python
from acgs.audit_sqlite import SQLiteAuditStore

store = SQLiteAuditStore(path="acgs_audit.db")
entries = store.list_entries(agent_id="bot-1", limit=100)
chain_ok = store.verify_chain()
```

### In-Memory Audit Store

```python
from acgs.audit_memory import InMemoryAuditStore

store = InMemoryAuditStore()
print(store.count())
```

## What `acgs` Adds Over `acgs-lite`

| Layer | Package | Role |
| --- | --- | --- |
| Public API | `acgs` | Stable namespace, policy backends, audit stores |
| Engine | `acgs-lite` | Validation engine, MACI, integrations, CLI |

Import from `acgs` when you want the stable public SDK. Import `acgs-lite` directly
when you need package-specific integrations, middleware, or the CLI.

## Key Features

- Stable governance primitives re-exported from `acgs-lite`.
- Pluggable `PolicyBackend` interface with built-in heuristic and Cedar backends.
- Persistent audit storage through in-memory and SQLite implementations.
- Fail-closed policy evaluation and tamper-evident audit-chain verification.

## License

AGPL-3.0-or-later. Commercial licensing is available; contact `hello@acgs.ai`.

## Links

- [Homepage](https://acgs.ai)
- [Documentation](https://github.com/dislovelhl/acgs/tree/main/packages/acgs-core)
- [PyPI](https://pypi.org/project/acgs/)
- [Repository](https://github.com/dislovelhl/acgs)
- [Issues](https://github.com/dislovelhl/acgs/issues)
- [Changelog](https://github.com/dislovelhl/acgs/releases)

Constitutional Hash: `608508a9bd224290`
