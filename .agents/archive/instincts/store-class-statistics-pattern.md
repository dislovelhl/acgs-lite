---
id: store-class-statistics-pattern
trigger: "when implementing a store, manager, or registry class"
confidence: 0.82
domain: code-style
source: session-observation
session: 2026-03-29-subnet-gtm-sprint
---

# Standard Statistics Interface for Store Classes

## Action
Every store/manager class should implement:

1. `size` property → count of **active** records
2. `total_stored` property → count including revoked/inactive
3. At least one distribution method → `escalation_distribution()`, `type_counts()`, etc.
4. `summary() -> dict[str, Any]` → all key stats in one dict for logging/inspection

## Template

```python
@property
def size(self) -> int:
    """Number of active records."""
    return sum(1 for r in self._records.values() if r.is_active)

@property
def total_stored(self) -> int:
    """Total records including revoked."""
    return len(self._records)

def escalation_distribution(self) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in self._records.values():
        if r.is_active:
            key = r.category.value
            counts[key] = counts.get(key, 0) + 1
    return counts

def summary(self) -> dict[str, Any]:
    return {
        "active": self.size,
        "total": self.total_stored,
        "revoked": self.total_stored - self.size,
        "distribution": self.escalation_distribution(),
        "constitution_hash": self._constitutional_hash,
    }
```

## Why
- `size` vs `total_stored` is critical for audit stores (revoked != deleted)
- `summary()` makes debugging trivial — one call, complete picture
- Consistent interface across all stores means no guessing which method to call

## Evidence
- 2026-03-29: PrecedentStore, ChainAnchor, SubnetOwner, ConstitutionalValidator,
  ConstitutionReceiver all implement this pattern.
- In testing, `store.summary()` assertions were the most common final assertion
  in integration-style tests.
