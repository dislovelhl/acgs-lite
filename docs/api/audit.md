# Audit Trail

The audit trail records every governance decision in a SHA-256 chained log. Any tampering is mathematically detectable. Records are immutable once written.

## Class Reference

::: acgs_lite.audit.AuditTrail
    options:
      members:
        - record
        - verify_chain
        - export
        - export_pdf
      show_source: true

::: acgs_lite.audit.AuditRecord

::: acgs_lite.audit.ChainVerificationResult

## Examples

### Access the audit trail

```python
from acgs_lite import GovernedAgent, Constitution
from acgs_lite.audit import AuditTrail

agent = GovernedAgent(my_agent, constitution=Constitution.from_template("general"))
result = agent.run("some request")

# The trail is automatically populated
trail: AuditTrail = agent.audit_trail
```

### Verify chain integrity

```python
result = trail.verify_chain()
if not result.valid:
    print(f"Tamper detected at record {result.first_invalid_index}")
```

### Export records

```python
# JSON export
records = trail.export(format="json")

# PDF compliance report
trail.export_pdf("audit_report.pdf")
```

### Query records

```python
violations = [r for r in trail.records if r.action == "BLOCK"]
print(f"{len(violations)} blocked actions in this session")
```
