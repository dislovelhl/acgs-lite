---
id: immutable-dataclass-for-audit-records
trigger: "when designing audit records, version history entries, protocol messages, or compliance certificates"
confidence: 0.85
domain: code-style
source: session-observation
session: 2026-03-29-subnet-gtm-sprint
---

# Use frozen=True + slots=True for Audit Records

## Action
Use `@dataclass(frozen=True, slots=True)` for any record that must not be mutated
after creation. Always include an immutability test.

## Pattern

```python
@dataclass(frozen=True, slots=True)
class AnchorRecord:
    anchor_id: str
    batch_root: str
    constitutional_hash: str
    proof_count: int
    block_height: int
    submitted_at: float
    # ...

# Test:
def test_anchor_record_immutable(self):
    record = ...
    with pytest.raises(AttributeError):
        record.batch_root = "changed"  # type: ignore[misc]
```

## Why
- Audit records that can be mutated can be backdated or falsified
- Protocol messages must be identical from sender to receiver
- `slots=True` reduces memory overhead (~30%) for large volumes of records
- Immutability violations surface immediately in tests, not silently in production

## Applies to
- `AnchorRecord`, `ProofEvidence`, `ConstitutionVersionRecord`
- `DeliberationSynapse`, `JudgmentSynapse`, `ValidationSynapse`
- `PrecedentRecord`, `MinerConfig`, `ValidatorConfig`
- Any compliance certificate or audit log entry

## Evidence
- 2026-03-29: All 6 new record types use this pattern.
  Immutability tests caught one case where `dataclasses.replace()` was needed
  (PrecedentRecord revocation) vs direct mutation.
