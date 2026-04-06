# acgs

[![PyPI](https://img.shields.io/pypi/v/acgs)](https://pypi.org/project/acgs/)
[![Python](https://img.shields.io/pypi/pyversions/acgs)](https://pypi.org/project/acgs/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

**Thin `acgs` namespace package — re-exports `acgs-lite` core plus Cedar policy evaluation and persistent audit stores.**

`acgs` (PyPI package name) is the `acgs-core` layer. It re-exports the essential `acgs-lite` symbols under the `acgs` namespace and adds three things: a `PolicyBackend` abstraction with a Cedar embedded-policy implementation, a SQLite-backed durable audit store, and an in-memory `AuditStore` conforming to the same ABC.

> **Version:** `1.0.0a2` (alpha). API is stable for the re-exported symbols; Cedar and audit-store APIs may evolve.

## Installation

```bash
pip install acgs
```

With Cedar policy evaluation (requires `cedarpy` Rust extension):

```bash
pip install "acgs[cedar]"
```

With FastAPI route helpers:

```bash
pip install "acgs[fastapi]"
```

## Quick Start

### 1. Import core governance symbols

```python
from acgs import (
    Constitution, Rule, Severity,
    GovernanceEngine, ValidationResult, Violation,
    MACIEnforcer, MACIRole,
    AuditLog, AuditEntry,
    ConstitutionalViolationError,
    fail_closed,
)

constitution = Constitution.from_yaml("rules.yaml")
engine = GovernanceEngine(constitution)
result = engine.validate("deploy to production", agent_id="ci-bot")
```

### 2. Cedar embedded policy evaluation

```python
from acgs.cedar import CedarBackend

cedar = CedarBackend(
    policies="""
    permit(
        principal == Agent::"ci-bot",
        action == Action::"read",
        resource
    );
    """,
    entities=[
        {"uid": {"type": "Agent", "id": "ci-bot"}, "attrs": {}, "parents": []},
    ],
)

decision = cedar.evaluate("read", agent_id="ci-bot")
print(decision.allowed)   # True
print(decision.backend)   # "cedar"
```

Load Cedar policies from a directory of `.cedar` files:

```python
cedar = CedarBackend.from_policy_dir("policies/")
decision = cedar.evaluate("deploy", agent_id="agent-1")
```

### 3. Persistent audit stores

```python
# SQLite (durable, hash-chain integrity)
from acgs.audit_sqlite import SQLiteAuditStore

store = SQLiteAuditStore("acgs_audit.db")
entry_id = store.append(audit_entry)
entries = store.list_entries(agent_id="ci-bot", limit=50)

# In-memory (wraps AuditLog, conforms to AuditStore ABC)
from acgs.audit_memory import InMemoryAuditStore

store = InMemoryAuditStore()
```

### 4. Pluggable policy backends

```python
from acgs.policy.backend import PolicyBackend, PolicyDecision, HeuristicBackend

# HeuristicBackend wraps GovernanceEngine as a PolicyBackend
engine = GovernanceEngine(constitution)
backend: PolicyBackend = HeuristicBackend(engine)

decision: PolicyDecision = backend.evaluate("propose change", agent_id="agent-1")
print(decision.allowed, decision.latency_ms)
```

## Key Features

- **`acgs` namespace** — clean single-name import for all core governance symbols from `acgs-lite`
- **Cedar evaluation** — `CedarBackend` implements embedded Cedar via `cedarpy` (Rust-backed, in-process, no OPA server)
- **`PolicyBackend` ABC** — swap `HeuristicBackend` ↔ `CedarBackend` without changing calling code
- **`SQLiteAuditStore`** — zero-dependency persistent audit store with hash-chain integrity (stdlib `sqlite3` + `hashlib`)
- **`InMemoryAuditStore`** — `AuditStore`-conformant wrapper around `acgs-lite`'s `AuditLog`
- **`AuditStore` ABC** — define custom backends (`append`, `get`, `list_entries`, `count`)

## API Reference

### Re-exported from `acgs-lite`

| Symbol | Description |
|--------|-------------|
| `Constitution` | Constitutional rule set |
| `Rule` | Single governance rule |
| `Severity` | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` |
| `GovernanceEngine` | Validates actions against a constitution |
| `ValidationResult` | Validation outcome |
| `Violation` | Single rule violation |
| `MACIEnforcer` | Enforces MACI role separation |
| `MACIRole` | `PROPOSER`, `VALIDATOR`, `EXECUTOR`, `OBSERVER` |
| `AuditLog` | Hash-chained in-memory audit trail |
| `AuditEntry` | Single audit record |
| `ConstitutionalViolationError` | Raised on blocked actions |
| `fail_closed` | Decorator: errors block execution |

### Cedar (`acgs.cedar`)

| Symbol | Description |
|--------|-------------|
| `CedarBackend` | Cedar-based `PolicyBackend`; `CedarBackend(policies, entities, schema)` or `.from_policy_dir(path)` |
| `CEDAR_AVAILABLE` | `True` when `cedarpy` is installed |

### Policy backends (`acgs.policy.backend`)

| Symbol | Description |
|--------|-------------|
| `PolicyBackend` | ABC — implement `evaluate(action, *, agent_id, context)` |
| `PolicyDecision` | Frozen dataclass: `allowed`, `violations`, `latency_ms`, `backend`, `metadata` |
| `HeuristicBackend` | Wraps `GovernanceEngine` as a `PolicyBackend` |

### Audit stores

| Import | Symbol | Description |
|--------|--------|-------------|
| `acgs.audit_store` | `AuditStore` | ABC: `append`, `get`, `list_entries`, `count` |
| `acgs.audit_sqlite` | `SQLiteAuditStore` | SQLite-backed, hash-chain integrity |
| `acgs.audit_memory` | `InMemoryAuditStore` | Wraps `AuditLog` |

## Runtime dependencies

- `acgs-lite>=2.5`
- `pydantic>=2.0`
- `pyyaml>=6.0`

Cedar requires `cedarpy>=4.0` (`pip install acgs[cedar]`).

## License

AGPL-3.0-or-later.

## Links

- [Homepage](https://acgs.ai)
- [PyPI](https://pypi.org/project/acgs/)
- [Issues](https://github.com/dislovelhl/acgs-core/issues)
