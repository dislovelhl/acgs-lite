"""Tests for ChainAnchor — Phase 2.1 on-chain proof anchoring."""

from __future__ import annotations

import pytest
from constitutional_swarm.bittensor.chain_anchor import (
    AnchorRecord,
    ChainAnchor,
    InMemorySubmitter,
    ProofEvidence,
    _compute_merkle_root,
)

CONST_HASH = "608508a9bd224290"


def _make_proof(
    root_hash: str = "aabbccdd",
    content_hash: str = "11223344",
    vote_hashes: tuple[str, ...] = ("v1", "v2", "v3"),
    constitutional_hash: str = CONST_HASH,
) -> ProofEvidence:
    return ProofEvidence.from_mesh_proof(
        root_hash=root_hash,
        content_hash=content_hash,
        vote_hashes=vote_hashes,
        constitutional_hash=constitutional_hash,
    )


# ---------------------------------------------------------------------------
# Merkle root
# ---------------------------------------------------------------------------


class TestMerkleRoot:
    def test_empty(self):
        root = _compute_merkle_root([])
        assert root  # SHA-256 of empty bytes

    def test_single_leaf(self):
        root = _compute_merkle_root(["abc"])
        assert root  # valid hash

    def test_deterministic(self):
        leaves = ["leaf1", "leaf2", "leaf3"]
        r1 = _compute_merkle_root(leaves)
        r2 = _compute_merkle_root(leaves)
        assert r1 == r2

    def test_order_independent(self):
        """Sorted inputs → same root regardless of insertion order."""
        r1 = _compute_merkle_root(["b", "a", "c"])
        r2 = _compute_merkle_root(["c", "b", "a"])
        assert r1 == r2

    def test_different_leaves_different_root(self):
        r1 = _compute_merkle_root(["leaf1", "leaf2"])
        r2 = _compute_merkle_root(["leaf1", "leaf3"])
        assert r1 != r2

    def test_two_leaves(self):
        root = _compute_merkle_root(["a", "b"])
        assert len(root) == 64  # SHA-256 hex length

    def test_odd_number_of_leaves(self):
        root = _compute_merkle_root(["a", "b", "c"])
        assert len(root) == 64


# ---------------------------------------------------------------------------
# ProofEvidence
# ---------------------------------------------------------------------------


class TestProofEvidence:
    def test_create(self):
        p = _make_proof()
        assert p.proof_id
        assert p.root_hash == "aabbccdd"
        assert p.constitutional_hash == CONST_HASH

    def test_membership_leaf_deterministic(self):
        p = _make_proof()
        assert p.membership_leaf() == p.membership_leaf()

    def test_different_proofs_different_leaves(self):
        p1 = _make_proof(root_hash="hash1")
        p2 = _make_proof(root_hash="hash2")
        assert p1.membership_leaf() != p2.membership_leaf()

    def test_unique_proof_ids(self):
        p1 = _make_proof()
        p2 = _make_proof()
        assert p1.proof_id != p2.proof_id


# ---------------------------------------------------------------------------
# InMemorySubmitter
# ---------------------------------------------------------------------------


class TestInMemorySubmitter:
    def test_submit_increments_block(self):
        sub = InMemorySubmitter(start_block=100)
        b1 = sub.submit("root1", CONST_HASH, 10)
        b2 = sub.submit("root2", CONST_HASH, 5)
        assert b1 == 100
        assert b2 == 101

    def test_submission_recorded(self):
        sub = InMemorySubmitter()
        sub.submit("batch_root_abc", CONST_HASH, 7)
        assert len(sub.submissions) == 1
        assert sub.submissions[0]["batch_root"] == "batch_root_abc"
        assert sub.submissions[0]["proof_count"] == 7


# ---------------------------------------------------------------------------
# ChainAnchor
# ---------------------------------------------------------------------------


class TestChainAnchor:
    def test_initial_state(self):
        anchor = ChainAnchor(CONST_HASH, batch_size=10)
        assert anchor.pending_count == 0
        assert anchor.total_proofs_anchored == 0
        assert anchor.anchor_history == []

    def test_add_proof_below_threshold(self):
        anchor = ChainAnchor(CONST_HASH, batch_size=10)
        p = _make_proof()
        result = anchor.add_proof(p)
        assert result is None
        assert anchor.pending_count == 1

    def test_auto_flush_at_batch_size(self):
        anchor = ChainAnchor(CONST_HASH, batch_size=3)
        proofs = [_make_proof(root_hash=f"root_{i}") for i in range(3)]
        for i, p in enumerate(proofs):
            result = anchor.add_proof(p)
            if i < 2:
                assert result is None
            else:
                assert result is not None
                assert isinstance(result, AnchorRecord)

        assert anchor.pending_count == 0
        assert anchor.total_proofs_anchored == 3

    def test_manual_flush(self):
        anchor = ChainAnchor(CONST_HASH, batch_size=100)
        for i in range(5):
            anchor.add_proof(_make_proof(root_hash=f"r{i}"))

        record = anchor.flush()
        assert record is not None
        assert record.proof_count == 5
        assert anchor.pending_count == 0

    def test_flush_empty_returns_none(self):
        anchor = ChainAnchor(CONST_HASH)
        assert anchor.flush() is None

    def test_hash_mismatch_rejected(self):
        anchor = ChainAnchor(CONST_HASH)
        bad = _make_proof(constitutional_hash="wrong_hash")
        with pytest.raises(ValueError, match="mismatch"):
            anchor.add_proof(bad)

    def test_anchor_history_preserved(self):
        anchor = ChainAnchor(CONST_HASH, batch_size=2)
        for i in range(6):
            anchor.add_proof(_make_proof(root_hash=f"r{i}"))

        assert len(anchor.anchor_history) == 3
        assert anchor.total_proofs_anchored == 6

    def test_block_heights_sequential(self):
        sub = InMemorySubmitter(start_block=1000)
        anchor = ChainAnchor(CONST_HASH, submitter=sub, batch_size=1)

        anchor.add_proof(_make_proof(root_hash="r1"))
        anchor.add_proof(_make_proof(root_hash="r2"))
        anchor.add_proof(_make_proof(root_hash="r3"))

        blocks = [r.block_height for r in anchor.anchor_history]
        assert blocks == [1000, 1001, 1002]

    def test_proof_membership_verification(self):
        anchor = ChainAnchor(CONST_HASH, batch_size=5)
        proofs = [_make_proof(root_hash=f"root_{i}") for i in range(5)]
        for p in proofs:
            anchor.add_proof(p)

        record = anchor.anchor_history[0]
        for p in proofs:
            assert record.verify_membership(p) is True

    def test_non_member_proof_not_verified(self):
        anchor = ChainAnchor(CONST_HASH, batch_size=5)
        for i in range(5):
            anchor.add_proof(_make_proof(root_hash=f"r{i}"))

        record = anchor.anchor_history[0]
        outsider = _make_proof(root_hash="not_in_batch")
        assert record.verify_membership(outsider) is False

    def test_verify_proof_in_history(self):
        anchor = ChainAnchor(CONST_HASH, batch_size=3)
        p1 = _make_proof(root_hash="batch1_proof1")
        p2 = _make_proof(root_hash="batch2_proof1")

        # Batch 1
        for i in range(2):
            anchor.add_proof(_make_proof(root_hash=f"b1p{i}"))
        anchor.add_proof(p1)

        # Batch 2
        anchor.add_proof(p2)
        for i in range(2):
            anchor.add_proof(_make_proof(root_hash=f"b2p{i}"))

        found1 = anchor.verify_proof_in_history(p1)
        assert found1 is not None

        found2 = anchor.verify_proof_in_history(p2)
        assert found2 is not None

        assert found1.anchor_id != found2.anchor_id

    def test_summary(self):
        anchor = ChainAnchor(CONST_HASH, batch_size=10)
        s = anchor.summary()
        assert s["constitutional_hash"] == CONST_HASH
        assert s["batch_size"] == 10
        assert s["pending"] == 0
        assert s["total_anchored"] == 0

    def test_anchor_record_immutable(self):
        anchor = ChainAnchor(CONST_HASH, batch_size=1)
        anchor.add_proof(_make_proof())
        record = anchor.anchor_history[0]
        with pytest.raises(AttributeError):
            record.batch_root = "changed"  # type: ignore[misc]

    def test_to_dict(self):
        anchor = ChainAnchor(CONST_HASH, batch_size=2)
        anchor.add_proof(_make_proof(root_hash="r1"))
        anchor.add_proof(_make_proof(root_hash="r2"))
        record = anchor.anchor_history[0]
        d = record.to_dict()
        assert d["constitutional_hash"] == CONST_HASH
        assert d["proof_count"] == 2
        assert len(d["leaf_hashes"]) == 2
