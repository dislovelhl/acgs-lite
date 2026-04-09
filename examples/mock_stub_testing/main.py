"""
Example: Mock/Stub Pattern for External Dependencies
======================================================
ACGS uses the "Pluggable Protocol" pattern: every external dependency
(blockchain, Arweave, AI providers) is defined as a typing.Protocol,
with an InMemory* stub that runs in tests without any live service.

This file shows:
  1. The Protocol/InMemory* pattern structure
  2. Writing tests against InMemory stubs (no real services)
  3. Swapping stubs for production implementations at runtime
  4. Custom stubs for your own tests

Run:
    python examples/mock_stub_testing/main.py

No API keys, no network access, no database required.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol


# ─────────────────────────────────────────────────────────────────────────────
# 1. DEFINE: Protocol (interface contract)
# ─────────────────────────────────────────────────────────────────────────────


class AuditStorage(Protocol):
    """Interface for persisting governance audit entries.

    Any class that implements save() and load() satisfies this Protocol —
    no inheritance needed (structural subtyping).
    """

    def save(self, entry_id: str, payload: dict[str, Any]) -> str:
        """Persist an audit entry. Returns a receipt/transaction ID."""
        ...

    def load(self, entry_id: str) -> dict[str, Any] | None:
        """Retrieve a previously saved entry."""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# 2. STUB: InMemory implementation for tests (zero dependencies)
# ─────────────────────────────────────────────────────────────────────────────


class InMemoryAuditStorage:
    """Ephemeral in-process stub for AuditStorage.

    Satisfies the AuditStorage Protocol without any real I/O.
    Use in unit tests and CI pipelines.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self.save_calls: list[tuple[str, dict[str, Any]]] = []

    def save(self, entry_id: str, payload: dict[str, Any]) -> str:
        self._store[entry_id] = payload
        self.save_calls.append((entry_id, payload))
        canonical = json.dumps(payload, sort_keys=True)
        return "inmem-" + hashlib.sha256(canonical.encode()).hexdigest()[:12]

    def load(self, entry_id: str) -> dict[str, Any] | None:
        return self._store.get(entry_id)


# ─────────────────────────────────────────────────────────────────────────────
# 3. PRODUCTION implementation (swapped in at runtime)
# ─────────────────────────────────────────────────────────────────────────────


class FileAuditStorage:
    """Production AuditStorage backed by the local filesystem.

    Drop-in replacement for InMemoryAuditStorage — same Protocol interface.
    In real deployments, replace with ArweaveAuditStorage or S3AuditStorage.
    """

    def __init__(self, base_path: str = "/tmp/acgs_audit") -> None:
        import os

        os.makedirs(base_path, exist_ok=True)
        self._base_path = base_path

    def save(self, entry_id: str, payload: dict[str, Any]) -> str:
        import os

        path = os.path.join(self._base_path, f"{entry_id}.json")
        with open(path, "w") as f:
            json.dump(payload, f)
        canonical = json.dumps(payload, sort_keys=True)
        return "file-" + hashlib.sha256(canonical.encode()).hexdigest()[:12]

    def load(self, entry_id: str) -> dict[str, Any] | None:
        import os

        path = os.path.join(self._base_path, f"{entry_id}.json")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)


# ─────────────────────────────────────────────────────────────────────────────
# 4. CONSUMER: business logic depends only on the Protocol
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class GovernanceDecisionRecorder:
    """Records governance decisions to pluggable storage.

    Depends only on AuditStorage Protocol — works with any implementation.
    """

    storage: AuditStorage
    _decision_count: int = field(default=0, init=False)

    def record(self, decision_id: str, action: str, allowed: bool, reason: str = "") -> str:
        self._decision_count += 1
        payload = {
            "decision_id": decision_id,
            "action": action,
            "allowed": allowed,
            "reason": reason,
            "sequence": self._decision_count,
        }
        receipt = self.storage.save(decision_id, payload)
        return receipt

    def get_decision(self, decision_id: str) -> dict[str, Any] | None:
        return self.storage.load(decision_id)

    @property
    def total_decisions(self) -> int:
        return self._decision_count


# ─────────────────────────────────────────────────────────────────────────────
# 5. DEMO: tests using InMemory stub, production using FileAuditStorage
# ─────────────────────────────────────────────────────────────────────────────


def demo_with_stub() -> None:
    """Tests use InMemoryAuditStorage — zero I/O, zero credentials."""
    print("\n── 1. Unit Test Pattern (InMemory stub) ──────────────────────")

    stub = InMemoryAuditStorage()
    recorder = GovernanceDecisionRecorder(storage=stub)

    # Use exactly as you would in a pytest test
    r1 = recorder.record("dec-001", "approve_model_v2", allowed=True)
    r2 = recorder.record(
        "dec-002", "deploy_to_prod", allowed=False, reason="Validator rejected: missing audit trail"
    )
    r3 = recorder.record("dec-003", "rollback_v2", allowed=True)

    print(f"  Decisions recorded : {recorder.total_decisions}")
    print(f"  Receipt dec-001    : {r1}")
    print(f"  Receipt dec-002    : {r2}")

    # Assertions (as they would appear in pytest)
    assert recorder.total_decisions == 3
    d = recorder.get_decision("dec-002")
    assert d is not None
    assert d["allowed"] is False
    assert "rejected" in d["reason"]

    # Inspect all calls made to the stub
    print(f"  storage.save calls : {len(stub.save_calls)}")
    print("  ✅ All assertions passed — no network, no filesystem, no credentials")


def demo_swap_to_production() -> None:
    """Production swap: replace InMemory stub with FileAuditStorage."""
    print("\n── 2. Production Swap (FileAuditStorage) ─────────────────────")

    import os
    import tempfile
    import shutil

    tmp_dir = tempfile.mkdtemp(prefix="acgs_demo_")
    try:
        prod_storage = FileAuditStorage(base_path=tmp_dir)
        recorder = GovernanceDecisionRecorder(storage=prod_storage)

        receipt = recorder.record("prod-001", "promote_to_prod", allowed=True)
        print(f"  Receipt         : {receipt}")
        print(f"  Saved to        : {tmp_dir}/prod-001.json")

        loaded = recorder.get_decision("prod-001")
        assert loaded is not None and loaded["allowed"] is True
        print(f"  Loaded back     : allowed={loaded['allowed']}, action={loaded['action']}")
        print("  ✅ Same business logic, different storage backend")
    finally:
        shutil.rmtree(tmp_dir)


def demo_failing_stub() -> None:
    """Chaos stub: simulate storage failures in tests."""
    print("\n── 3. Chaos Stub (simulated failure) ─────────────────────────")

    class FailingAuditStorage:
        """Stub that always raises — tests error-handling paths."""

        def save(self, entry_id: str, payload: dict[str, Any]) -> str:
            raise IOError("Simulated storage failure")

        def load(self, entry_id: str) -> dict[str, Any] | None:
            return None

    recorder = GovernanceDecisionRecorder(storage=FailingAuditStorage())
    try:
        recorder.record("fail-001", "some_action", allowed=True)
        print("  ❌ Should have raised IOError")
    except IOError as exc:
        print(f"  ✅ Caught expected failure: {exc}")
        print("  — Error handling paths verified without touching real storage")


def demo_acgs_builtin_stubs() -> None:
    """Show the InMemory* stubs that ship with acgs-lite."""
    print("\n── 4. Built-in ACGS InMemory Stubs ───────────────────────────")

    from acgs_lite import InMemoryGovernanceStateBackend

    backend = InMemoryGovernanceStateBackend()
    state = backend.load_state()
    state["custom_key"] = "custom_value"
    backend.save_state(state)

    reloaded = backend.load_state()
    assert reloaded["custom_key"] == "custom_value"
    print("  acgs_lite.InMemoryGovernanceStateBackend — ✅ state round-trip")
    print("  (Same pattern used across: InMemoryArweaveClient,")
    print("   InMemorySubmitter, InMemoryCapabilityRegistry)")


if __name__ == "__main__":
    print("=" * 55)
    print("  Mock/Stub Pattern — Pluggable Protocol")
    print("=" * 55)

    demo_with_stub()
    demo_swap_to_production()
    demo_failing_stub()
    demo_acgs_builtin_stubs()

    print("\nDone. All demos ran with zero external dependencies.")
    print("Swap InMemory* → Real* to connect live services in production.")
