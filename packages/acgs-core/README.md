# ACGS Core

`acgs` is the thin public ACGS namespace for constitutional governance in agent systems.
It layers the stable `acgs` import surface over `acgs-lite`, adds pluggable policy backends,
and exposes persistent audit stores for productized deployments.

No external policy server is required. Policy evaluation stays embedded in-process through
the default heuristic backend or the optional Cedar backend.

## Quickstart

```python
from acgs import Constitution, GovernanceEngine, Rule, Severity

constitution = Constitution.from_rules(
    [
        Rule(
            id="NO-SELF-APPROVAL",
            text="Agents may not self-approve production changes",
            severity=Severity.HIGH,
            keywords=["self-approve"],
        )
    ]
)

engine = GovernanceEngine(constitution, strict=False)
result = engine.validate("self-approve this deployment", agent_id="agent-7")

assert result.valid is False
assert result.violations[0].rule_id == "NO-SELF-APPROVAL"
```

## Audit Persistence

Use the in-memory wrapper for tests and ephemeral runs:

```python
from acgs.audit_memory import InMemoryAuditStore
```

Use SQLite for durable audit retention:

```python
from acgs.audit_sqlite import SQLiteAuditStore

store = SQLiteAuditStore("acgs_audit.db")
```

Each record stores a SHA-256 chain hash over:

`previous_hash + entry_id + action + valid`

`verify_chain()` replays the chain to detect tampering.

## Extras

- `pip install acgs[cedar]` for embedded Cedar evaluation through `cedarpy`
- `pip install acgs[fastapi]` for FastAPI and Uvicorn server surfaces
- `pip install acgs[openai]` for OpenAI adapters
- `pip install acgs[anthropic]` for Anthropic adapters
- `pip install acgs[langchain]` for LangChain integration helpers

## PolicyBackend Architecture

```text
                        +----------------------+
                        |   Application Code   |
                        +----------+-----------+
                                   |
                                   v
                        +----------------------+
                        |    PolicyBackend     |
                        |        ABC           |
                        +----+------------+----+
                             |            |
                  evaluate() |            | evaluate()
                             |            |
               +-------------v--+      +--v----------------+
               | HeuristicBackend|      |   CedarBackend    |
               |  acgs-lite      |      | cedarpy / in-proc |
               | GovernanceEngine|      | embedded Cedar    |
               +--------+--------+      +---------+---------+
                        |                         |
                        +------------+------------+
                                     |
                                     v
                          +----------------------+
                          |  PolicyDecision      |
                          | allowed / violations |
                          +----------------------+
```

## Notes

- `acgs` keeps the public API surface small and stable.
- `acgs-lite` remains the underlying governance engine implementation.
- Persistent audit storage and policy backend swapping are opt-in extensions on top of the
  same constitutional validation flow.
