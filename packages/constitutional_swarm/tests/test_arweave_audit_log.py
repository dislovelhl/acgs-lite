"""Tests for ArweaveAuditLogger — Phase 2.3."""

from __future__ import annotations

import json
import uuid

import pytest
from constitutional_swarm.bittensor.arweave_audit_log import (
    ArweaveAuditLogger,
    AuditBatch,
    AuditDecisionType,
    AuditLogEntry,
    InMemoryArweaveClient,
    _compute_merkle_root,
    _merkle_path_for_index,
    verify_merkle_path,
)

CONST_HASH = "608508a9bd224290"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _entry(
    entry_id: str | None = None,
    case_id: str = "ESC-001",
    compliance_passed: bool = True,
    decision_type: AuditDecisionType = AuditDecisionType.ESCALATED,
) -> AuditLogEntry:
    return AuditLogEntry(
        entry_id=entry_id or uuid.uuid4().hex[:8],
        case_id=case_id,
        constitutional_hash=CONST_HASH,
        decision_type=decision_type,
        compliance_passed=compliance_passed,
        impact_score=0.82,
        escalation_type="security",
        resolution="allow_with_conditions",
        miner_uid="miner-01",
        validator_grade=0.91,
    )


def _logger(batch_size: int = 50) -> tuple[ArweaveAuditLogger, InMemoryArweaveClient]:
    arweave = InMemoryArweaveClient()
    logger = ArweaveAuditLogger(
        constitutional_hash=CONST_HASH,
        arweave_client=arweave,
        batch_size=batch_size,
    )
    return logger, arweave


# ---------------------------------------------------------------------------
# AuditLogEntry
# ---------------------------------------------------------------------------


class TestAuditLogEntry:
    def test_leaf_hash_is_hex(self):
        e = _entry()
        assert len(e.leaf_hash()) == 64  # SHA-256 hex

    def test_leaf_hash_deterministic(self):
        e = _entry("id-1")
        assert e.leaf_hash() == e.leaf_hash()

    def test_different_entries_different_hashes(self):
        e1 = _entry("id-1", case_id="ESC-001")
        e2 = _entry("id-2", case_id="ESC-002")
        assert e1.leaf_hash() != e2.leaf_hash()

    def test_immutability(self):
        e = _entry()
        with pytest.raises(AttributeError):
            e.case_id = "tampered"  # type: ignore[misc]

    def test_to_dict(self):
        e = _entry()
        d = e.to_dict()
        assert d["constitutional_hash"] == CONST_HASH
        assert d["decision_type"] == "escalated"

    def test_roundtrip_dict(self):
        e = _entry("rt-1")
        e2 = AuditLogEntry.from_dict(e.to_dict())
        assert e2.entry_id == e.entry_id
        assert e2.decision_type == e.decision_type
        assert e2.leaf_hash() == e.leaf_hash()


# ---------------------------------------------------------------------------
# Merkle utilities
# ---------------------------------------------------------------------------


class TestMerkleUtilities:
    def test_single_leaf(self):
        leaves = ["abc"]
        root = _compute_merkle_root(leaves)
        path = _merkle_path_for_index(leaves, 0)
        assert path == []
        assert verify_merkle_path("abc", path, root)

    def test_two_leaves(self):
        leaves = ["leaf0", "leaf1"]
        root = _compute_merkle_root(leaves)
        path0 = _merkle_path_for_index(leaves, 0)
        path1 = _merkle_path_for_index(leaves, 1)
        assert verify_merkle_path("leaf0", path0, root)
        assert verify_merkle_path("leaf1", path1, root)

    def test_four_leaves(self):
        leaves = ["L0", "L1", "L2", "L3"]
        root = _compute_merkle_root(leaves)
        for i, leaf in enumerate(leaves):
            path = _merkle_path_for_index(leaves, i)
            assert verify_merkle_path(leaf, path, root), f"failed at index {i}"

    def test_odd_leaves(self):
        leaves = ["L0", "L1", "L2"]  # odd — last is duplicated
        root = _compute_merkle_root(leaves)
        for i, leaf in enumerate(leaves):
            path = _merkle_path_for_index(leaves, i)
            assert verify_merkle_path(leaf, path, root), f"failed at index {i}"

    def test_wrong_leaf_fails(self):
        leaves = ["L0", "L1", "L2", "L3"]
        root = _compute_merkle_root(leaves)
        path = _merkle_path_for_index(leaves, 0)
        # Use wrong leaf hash
        assert not verify_merkle_path("WRONG", path, root)

    def test_tampered_root_fails(self):
        leaves = ["L0", "L1"]
        path = _merkle_path_for_index(leaves, 0)
        assert not verify_merkle_path("L0", path, "tampered-root")

    def test_large_batch(self):
        leaves = [f"leaf-{i:04d}" for i in range(100)]
        root = _compute_merkle_root(leaves)
        for i in [0, 1, 33, 49, 99]:
            path = _merkle_path_for_index(leaves, i)
            assert verify_merkle_path(leaves[i], path, root), f"failed at {i}"

    def test_deterministic_root(self):
        leaves = ["a", "b", "c", "d"]
        r1 = _compute_merkle_root(leaves)
        r2 = _compute_merkle_root(leaves)
        assert r1 == r2

    def test_empty_leaves(self):
        root = _compute_merkle_root([])
        assert len(root) == 64


# ---------------------------------------------------------------------------
# AuditBatch
# ---------------------------------------------------------------------------


class TestAuditBatch:
    def test_batch_root_stable(self):
        entries = [_entry(f"id-{i}") for i in range(5)]
        batch = AuditBatch("b1", CONST_HASH, entries)
        assert len(batch.batch_root) == 64

    def test_merkle_path_verify(self):
        entries = [_entry(f"id-{i}") for i in range(4)]
        batch = AuditBatch("b1", CONST_HASH, entries)
        for entry in entries:
            path = batch.merkle_path_for(entry.entry_id)
            assert verify_merkle_path(entry.leaf_hash(), path, batch.batch_root)

    def test_verify_entry_method(self):
        entries = [_entry(f"id-{i}") for i in range(3)]
        batch = AuditBatch("b1", CONST_HASH, entries)
        for entry in entries:
            assert batch.verify_entry(entry)

    def test_unknown_entry_id_raises(self):
        batch = AuditBatch("b1", CONST_HASH, [_entry("real")])
        with pytest.raises(KeyError):
            batch.merkle_path_for("does-not-exist")

    def test_unknown_entry_verify_false(self):
        batch = AuditBatch("b1", CONST_HASH, [_entry("real")])
        unknown = _entry("other")
        assert not batch.verify_entry(unknown)

    def test_find_entry(self):
        entries = [_entry(f"id-{i}") for i in range(3)]
        batch = AuditBatch("b1", CONST_HASH, entries)
        assert batch.find_entry("id-1") is not None
        assert batch.find_entry("missing") is None

    def test_compliance_rate(self):
        entries = [_entry(f"p{i}", compliance_passed=True) for i in range(8)] + [
            _entry(f"f{i}", compliance_passed=False) for i in range(2)
        ]
        batch = AuditBatch("b1", CONST_HASH, entries)
        assert batch.compliance_rate() == pytest.approx(0.8)

    def test_single_entry_batch(self):
        e = _entry("solo")
        batch = AuditBatch("b1", CONST_HASH, [e])
        assert batch.verify_entry(e)

    def test_roundtrip_json(self):
        entries = [_entry(f"id-{i}") for i in range(3)]
        batch = AuditBatch("b1", CONST_HASH, entries)
        b2 = AuditBatch.from_dict(batch.to_dict())
        assert b2.batch_root == batch.batch_root
        assert b2.entry_count == batch.entry_count
        for e in entries:
            assert b2.verify_entry(e)


# ---------------------------------------------------------------------------
# InMemoryArweaveClient
# ---------------------------------------------------------------------------


class TestInMemoryArweaveClient:
    def test_upload_returns_tx_id(self):
        client = InMemoryArweaveClient()
        tx_id = client.upload(b"data", {"key": "val"})
        assert tx_id.startswith("ar_")

    def test_upload_deterministic(self):
        client = InMemoryArweaveClient()
        tx1 = client.upload(b"same-data")
        tx2 = client.upload(b"same-data")
        assert tx1 == tx2

    def test_fetch_uploaded(self):
        client = InMemoryArweaveClient()
        data = b"governance-log-entry"
        tx_id = client.upload(data)
        assert client.fetch(tx_id) == data

    def test_fetch_missing_raises(self):
        client = InMemoryArweaveClient()
        with pytest.raises(KeyError):
            client.fetch("nonexistent")

    def test_tags_stored(self):
        client = InMemoryArweaveClient()
        tx_id = client.upload(b"data", {"constitutional_hash": CONST_HASH})
        tags = client.get_tags(tx_id)
        assert tags["constitutional_hash"] == CONST_HASH


# ---------------------------------------------------------------------------
# ArweaveAuditLogger
# ---------------------------------------------------------------------------


class TestArweaveAuditLogger:
    def test_flush_returns_receipt(self):
        logger, _ = _logger()
        logger.add_entry(_entry())
        receipt = logger.flush()
        assert receipt is not None
        assert receipt.entry_count == 1

    def test_receipt_is_immutable(self):
        logger, _ = _logger()
        logger.add_entry(_entry())
        receipt = logger.flush()
        assert receipt is not None
        with pytest.raises(AttributeError):
            receipt.batch_root = "tampered"  # type: ignore[misc]

    def test_empty_flush_returns_none(self):
        logger, _ = _logger()
        assert logger.flush() is None

    def test_auto_flush_on_batch_size(self):
        logger, _ = _logger(batch_size=3)
        for i in range(3):
            logger.add_entry(_entry(f"id-{i}"))
        # Third add triggers auto-flush
        assert logger.pending_count == 0

    def test_arweave_upload_content(self):
        logger, arweave = _logger()
        e = _entry("check-id")
        logger.add_entry(e)
        receipt = logger.flush()
        assert receipt is not None

        raw = arweave.fetch(receipt.arweave_tx_id)
        batch = AuditBatch.from_dict(json.loads(raw))
        assert batch.batch_root == receipt.batch_root
        assert batch.verify_entry(e)

    def test_constitutional_hash_mismatch_raises(self):
        logger, _ = _logger()
        bad_entry = AuditLogEntry(
            entry_id="bad",
            case_id="ESC-999",
            constitutional_hash="wrong-hash",
            decision_type=AuditDecisionType.AUTO_PASS,
            compliance_passed=True,
        )
        with pytest.raises(ValueError, match="mismatch"):
            logger.add_entry(bad_entry)

    def test_chain_submitter_block_height_in_receipt(self):
        """When a ChainSubmitter is wired in, receipt has block_height."""
        from constitutional_swarm.bittensor.chain_anchor import InMemorySubmitter

        submitter = InMemorySubmitter(start_block=42)
        arweave = InMemoryArweaveClient()
        logger = ArweaveAuditLogger(
            constitutional_hash=CONST_HASH,
            arweave_client=arweave,
            chain_submitter=submitter,
            batch_size=10,
        )
        logger.add_entry(_entry())
        receipt = logger.flush()
        assert receipt is not None
        assert receipt.block_height == 42

    def test_no_chain_submitter_block_height_none(self):
        logger, _ = _logger()
        logger.add_entry(_entry())
        receipt = logger.flush()
        assert receipt is not None
        assert receipt.block_height is None

    def test_fetch_batch_via_receipt(self):
        logger, _ = _logger()
        entries = [_entry(f"id-{i}") for i in range(5)]
        for e in entries:
            logger.add_entry(e)
        receipt = logger.flush()
        assert receipt is not None

        batch = logger.fetch_batch(receipt)
        assert batch.batch_root == receipt.batch_root
        assert batch.entry_count == 5

    def test_multiple_batches(self):
        logger, _arweave = _logger(batch_size=3)
        for i in range(9):
            logger.add_entry(_entry(f"id-{i}"))
        logger.flush()  # remaining
        assert len(logger.receipts) >= 3

    def test_summary(self):
        logger, _ = _logger()
        logger.add_entry(_entry())
        logger.flush()
        s = logger.summary()
        assert s["total_flushed"] == 1
        assert s["batches_stored"] == 1

    def test_auditor_end_to_end_verification(self):
        """Full auditor workflow: chain anchor → fetch → verify membership."""
        from constitutional_swarm.bittensor.chain_anchor import InMemorySubmitter

        submitter = InMemorySubmitter()
        arweave = InMemoryArweaveClient()
        logger = ArweaveAuditLogger(
            constitutional_hash=CONST_HASH,
            arweave_client=arweave,
            chain_submitter=submitter,
        )

        target = _entry("audit-target")
        for i in range(4):
            logger.add_entry(_entry(f"bulk-{i}"))
        logger.add_entry(target)
        receipt = logger.flush()
        assert receipt is not None

        # 1. Auditor gets receipt from chain (on-chain: batch_root + block_height)
        assert receipt.block_height is not None  # anchored

        # 2. Auditor fetches batch from Arweave
        raw = arweave.fetch(receipt.arweave_tx_id)
        batch = AuditBatch.from_dict(json.loads(raw))

        # 3. Verify batch root matches chain anchor
        assert batch.batch_root == receipt.batch_root

        # 4. Verify target entry is in batch via Merkle proof
        path = batch.merkle_path_for(target.entry_id)
        assert verify_merkle_path(target.leaf_hash(), path, batch.batch_root)
