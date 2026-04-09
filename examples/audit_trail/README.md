# Example: Tamper-Evident Audit Trail

Every governance decision is recorded in a cryptographically-chained audit log.
Chain integrity is verifiable at any time — no database required.

## What it shows

| Concept | Description |
|---------|-------------|
| `AuditLog` + `AuditEntry` | Record decisions with SHA-256 chain |
| `verify_chain()` | Detect tampering across the full log |
| `query()` | Filter by `agent_id`, `type`, `valid` |
| Export to JSON | Persist the log for compliance reporting |

## Run

```bash
python packages/acgs-lite/examples/audit_trail/main.py
```

## Key API

```python
from acgs_lite.audit import AuditLog, AuditEntry

log = AuditLog()

# Record a decision
log.record(AuditEntry(
    id="ev-001",
    type="validation",
    agent_id="agent-A",
    action="review_proposal",
    valid=True,
))

# Verify nothing was tampered with
assert log.verify_chain()

# Query by agent
violations = log.query(agent_id="agent-A", valid=False)

# Export for compliance
import json
json.dump([e.to_dict() for e in log.entries], open("audit.json", "w"))
```

## Chain integrity

Each entry's `chain_hash` is `SHA-256(prev_hash | entry_hash)`. Modifying any
historical entry breaks all subsequent chain hashes, which `verify_chain()` detects.

## Next steps

- [`../mock_stub_testing/`](../mock_stub_testing/) — test audit pipelines without external storage
