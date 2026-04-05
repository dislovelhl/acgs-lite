# Example: Mock/Stub Pattern (Pluggable Protocol)

ACGS uses **structural subtyping** via `typing.Protocol` to decouple business
logic from external services. Every external dependency ships with an
`InMemory*` stub that runs in tests with zero credentials, zero network.

## The pattern

```
typing.Protocol          ← interface contract (structural typing)
     ↑                         ↑
InMemory*Stub            RealImplementation
(tests, CI, dev)         (production, swap at runtime)
```

No inheritance required — any class with matching method signatures satisfies
the Protocol.

## Built-in stubs in ACGS

| Protocol | InMemory stub | Production swap |
|----------|--------------|-----------------|
| `GovernanceStateBackend` | `InMemoryGovernanceStateBackend` | `JsonFileGovernanceStateBackend` |
| `ChainSubmitter` | `InMemorySubmitter` | `BittensorSubmitter` |
| `ArweaveClient` | `InMemoryArweaveClient` | `RealArweaveClient` |
| `AuditChainSubmitter` | `InMemoryAuditChainSubmitter` | `BittensorAuditSubmitter` |
| `CapabilityRegistry` | `InMemoryCapabilityRegistry` | `RedisCapabilityRegistry` |

## Run

```bash
python packages/acgs-lite/examples/mock_stub_testing/main.py
```

## Write your own stub

```python
from typing import Protocol, Any

# 1. Declare the interface
class MyStorage(Protocol):
    def save(self, key: str, value: dict[str, Any]) -> str: ...
    def load(self, key: str) -> dict[str, Any] | None: ...

# 2. InMemory stub for tests
class InMemoryMyStorage:
    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    def save(self, key: str, value: dict[str, Any]) -> str:
        self._store[key] = value
        return f"inmem-{key}"

    def load(self, key: str) -> dict[str, Any] | None:
        return self._store.get(key)

# 3. Consume via Protocol — same code works for both
def my_business_logic(storage: MyStorage) -> None:
    storage.save("decision-1", {"allowed": True})

# Tests: use stub
my_business_logic(InMemoryMyStorage())      # ✅ zero I/O

# Production: swap to real implementation
# my_business_logic(S3MyStorage(bucket="acgs-prod"))
```

## In pytest

```python
import pytest
from my_module import InMemoryMyStorage, my_business_logic

@pytest.fixture
def storage() -> InMemoryMyStorage:
    return InMemoryMyStorage()

def test_saves_decision(storage: InMemoryMyStorage) -> None:
    my_business_logic(storage)
    assert storage.load("decision-1") == {"allowed": True}
```

## Design rules

1. **Define Protocol first** — before writing any implementation
2. **InMemory* stub always ships alongside the Protocol** — never import live services in tests
3. **No `isinstance()` checks** — structural typing means duck typing; the Protocol is documentation, not a base class
4. **Chaos stubs for error paths** — write a `FailingFoo` stub to test exception handling
5. **`save_calls` / `load_calls` lists** — add call recording to stubs for assertion
