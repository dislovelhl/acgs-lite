---
id: pluggable-protocol-for-external-deps
trigger: "when implementing a module that depends on an external system (blockchain, DB, network, LLM)"
confidence: 0.88
domain: code-style
source: session-observation
session: 2026-03-29-subnet-gtm-sprint
---

# Pluggable Protocol Pattern for External Dependencies

## Action
1. Define a `Protocol` class for the external dependency with typed method signatures
2. Provide an `InMemory*` stub that implements it with pure in-memory logic, no I/O
3. Inject via constructor (`submitter: ChainSubmitter | None = None`)
4. Tests use the stub; production wires the real client

## Pattern

```python
class ChainSubmitter(Protocol):
    def submit(self, batch_root: str, constitutional_hash: str, proof_count: int) -> int:
        ...

class InMemorySubmitter:
    def __init__(self, start_block: int = 1) -> None:
        self._block = start_block
        self.submissions: list[dict] = []

    def submit(self, batch_root: str, constitutional_hash: str, proof_count: int) -> int:
        block = self._block; self._block += 1
        self.submissions.append({"block": block, "batch_root": batch_root, ...})
        return block

class ChainAnchor:
    def __init__(self, constitutional_hash: str, submitter: ChainSubmitter | None = None):
        self._submitter = submitter or InMemorySubmitter()
```

## Why
- All tests run without any external service
- Real client is one class swap away
- Tests can inspect stub state (`submitter.submissions`) to verify calls
- Avoids `unittest.mock` for the core path

## Evidence
- 2026-03-29: ChainSubmitter/InMemorySubmitter made all 307 tests run without Bittensor SDK
- Same pattern: DeliberationHandler in ConstitutionalMiner, Constitution.from_yaml injectable
- Seen across all constitutional_swarm modules that touch external systems
