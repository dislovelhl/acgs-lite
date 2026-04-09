"""Tests for optional PQC audit signing."""

from __future__ import annotations

from acgs_lite._meta import CONSTITUTIONAL_HASH
from acgs_lite.audit import AuditEntry, AuditLog, JSONLAuditBackend
from acgs_lite.pqc import InMemoryPQCSigner


def test_audit_log_with_signer_adds_pqc_signature() -> None:
    signer = InMemoryPQCSigner()
    log = AuditLog(pqc_signer=signer)

    first = AuditEntry(id="1", type="validation", constitutional_hash=CONSTITUTIONAL_HASH)
    second = AuditEntry(id="2", type="validation", constitutional_hash=CONSTITUTIONAL_HASH)

    log.record(first)
    log.record(second)

    assert first.pqc_signature is not None
    assert second.pqc_signature is not None
    assert signer.verify(first.entry_hash.encode(), first.pqc_signature)
    assert signer.verify(second.entry_hash.encode(), second.pqc_signature)


def test_audit_log_without_signer_keeps_pqc_signature_none() -> None:
    log = AuditLog()
    entry = AuditEntry(id="1", type="validation", constitutional_hash=CONSTITUTIONAL_HASH)

    log.record(entry)

    assert entry.pqc_signature is None


def test_jsonl_backend_round_trip_preserves_pqc_signature(tmp_path) -> None:
    backend = JSONLAuditBackend(tmp_path / "audit.jsonl")
    signer = InMemoryPQCSigner()
    entry = AuditEntry(id="1", type="validation", constitutional_hash=CONSTITUTIONAL_HASH)
    log = AuditLog(backend=backend, pqc_signer=signer)

    log.record(entry)
    log.flush()

    restored = AuditLog.from_backend(backend)

    assert restored.entries[0].pqc_signature == entry.pqc_signature
    assert restored.entries[0].to_dict()["pqc_signature"] == entry.pqc_signature
