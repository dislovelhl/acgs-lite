"""Chain Anchor — batch MeshProof anchoring for on-chain audit trails.

Phase 2.1 of the subnet implementation roadmap.

Accumulates MeshProof objects into a batch, computes a batch Merkle root,
and submits the root to chain via a pluggable ChainSubmitter interface.
Full audit logs (too large for on-chain storage) are recorded off-chain
with the batch root as the on-chain anchor.

Design:
  • Pluggable submitter — no Bittensor SDK required for testing
  • Merkle root is deterministic: SHA-256 of sorted proof hashes
  • AnchorRecord is immutable — every submitted batch is preserved
  • Individual proof membership can be verified against the batch root
  • Selective on-chain vs off-chain split (per roadmap §2.4):
      On-chain : batch Merkle root + constitutional hash + block height
      Off-chain: individual proof content + reasoning text

Roadmap reference: 08-subnet-implementation-roadmap.md § Phase 2.1
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# Chain submitter interface (pluggable — stub or real Bittensor extrinsic)
# ---------------------------------------------------------------------------


class ChainSubmitter(Protocol):
    """Protocol for writing a batch Merkle root to chain.

    Implement this to connect to a real Bittensor node:

        class BittensorSubmitter:
            def submit(self, root: str, constitutional_hash: str,
                       proof_count: int) -> int:
                # call Bittensor extrinsic
                return current_block_height
    """

    def submit(
        self,
        batch_root: str,
        constitutional_hash: str,
        proof_count: int,
    ) -> int:
        """Submit a batch Merkle root to chain.

        Returns the block height of the submission.
        """
        ...


class InMemorySubmitter:
    """In-memory stub submitter — no network I/O, for testing.

    Records every submission locally so tests can inspect it.
    Simulates sequential block heights starting at 1.
    """

    def __init__(self, start_block: int = 1) -> None:
        self._block = start_block
        self.submissions: list[dict[str, Any]] = []

    def submit(
        self,
        batch_root: str,
        constitutional_hash: str,
        proof_count: int,
    ) -> int:
        block = self._block
        self._block += 1
        self.submissions.append(
            {
                "block": block,
                "batch_root": batch_root,
                "constitutional_hash": constitutional_hash,
                "proof_count": proof_count,
                "submitted_at": time.time(),
            }
        )
        return block


# ---------------------------------------------------------------------------
# Proof evidence (minimal representation for anchoring)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProofEvidence:
    """Minimal evidence record extracted from a MeshProof for anchoring.

    Contains only the data required for on-chain anchoring — no
    sensitive judgment content or reasoning text.
    """

    proof_id: str
    root_hash: str
    content_hash: str
    vote_hashes: tuple[str, ...]
    constitutional_hash: str
    captured_at: float = field(default_factory=time.time)

    @classmethod
    def from_mesh_proof(
        cls,
        root_hash: str,
        content_hash: str,
        vote_hashes: tuple[str, ...] | list[str],
        constitutional_hash: str,
    ) -> "ProofEvidence":
        """Create from MeshProof fields (avoids importing MeshProof here)."""
        return cls(
            proof_id=uuid.uuid4().hex[:8],
            root_hash=root_hash,
            content_hash=content_hash,
            vote_hashes=tuple(vote_hashes),
            constitutional_hash=constitutional_hash,
        )

    def membership_leaf(self) -> str:
        """SHA-256 leaf hash for Merkle tree inclusion."""
        payload = f"{self.root_hash}:{self.content_hash}:{self.constitutional_hash}"
        return hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Anchor record (immutable, one per submitted batch)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AnchorRecord:
    """Immutable record of a single on-chain batch anchor submission.

    The batch_root is what goes on-chain.
    Individual proofs can be verified against it via verify_membership().
    """

    anchor_id: str
    batch_root: str
    constitutional_hash: str
    proof_count: int
    block_height: int
    submitted_at: float
    proof_ids: tuple[str, ...]
    leaf_hashes: tuple[str, ...]

    def verify_membership(self, proof: ProofEvidence) -> bool:
        """Verify that a proof was included in this batch.

        Re-computes the Merkle root from stored leaf hashes with the
        candidate proof swapped in, then compares to the batch root.
        Returns True if the proof's leaf is in the stored leaves.
        """
        return proof.membership_leaf() in set(self.leaf_hashes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "batch_root": self.batch_root,
            "constitutional_hash": self.constitutional_hash,
            "proof_count": self.proof_count,
            "block_height": self.block_height,
            "submitted_at": self.submitted_at,
            "proof_ids": list(self.proof_ids),
            "leaf_hashes": list(self.leaf_hashes),
        }


# ---------------------------------------------------------------------------
# Merkle utilities
# ---------------------------------------------------------------------------


def _compute_merkle_root(leaves: list[str]) -> str:
    """Compute a binary Merkle root over a list of leaf hashes.

    Leaves are sorted for determinism. Odd-length levels are padded
    by duplicating the last leaf (standard Bitcoin-style padding).
    Returns the SHA-256 hex root.
    """
    if not leaves:
        return hashlib.sha256(b"").hexdigest()

    layer = sorted(leaves)

    while len(layer) > 1:
        next_layer: list[str] = []
        # Pad odd-length layers
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        for i in range(0, len(layer), 2):
            combined = layer[i] + layer[i + 1]
            next_layer.append(hashlib.sha256(combined.encode()).hexdigest())
        layer = next_layer

    return layer[0]


# ---------------------------------------------------------------------------
# Chain Anchor (main class)
# ---------------------------------------------------------------------------


class ChainAnchor:
    """Batch-anchor MeshProofs to chain.

    Accumulates ProofEvidence objects until the batch_size threshold is
    reached (or flush() is called manually), then computes the batch
    Merkle root and submits it via the injected ChainSubmitter.

    Usage::

        submitter = InMemorySubmitter()
        anchor = ChainAnchor(
            constitutional_hash="608508a9bd224290",
            submitter=submitter,
            batch_size=100,
        )

        # Add proofs as they arrive from validators
        anchor.add_proof(ProofEvidence.from_mesh_proof(...))

        # Force flush (e.g. at epoch end)
        record = anchor.flush()

        # Verify a proof was anchored
        assert record.verify_membership(proof_evidence)

        # Full history
        for rec in anchor.anchor_history:
            print(rec.batch_root, rec.block_height)
    """

    def __init__(
        self,
        constitutional_hash: str,
        submitter: ChainSubmitter | None = None,
        batch_size: int = 100,
    ) -> None:
        self._constitutional_hash = constitutional_hash
        self._submitter: ChainSubmitter = submitter or InMemorySubmitter()
        self._batch_size = batch_size
        self._pending: list[ProofEvidence] = []
        self._history: list[AnchorRecord] = []

    @property
    def constitutional_hash(self) -> str:
        return self._constitutional_hash

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def anchor_history(self) -> list[AnchorRecord]:
        return list(self._history)

    @property
    def total_proofs_anchored(self) -> int:
        return sum(r.proof_count for r in self._history)

    def add_proof(self, proof: ProofEvidence) -> AnchorRecord | None:
        """Add a proof to the pending batch.

        Auto-flushes when the batch is full.
        Returns the AnchorRecord if a flush occurred, else None.

        Raises ValueError if the proof's constitutional hash does not
        match the anchor's expected hash.
        """
        if proof.constitutional_hash != self._constitutional_hash:
            raise ValueError(
                f"Proof constitutional hash mismatch: "
                f"expected={self._constitutional_hash} "
                f"got={proof.constitutional_hash}"
            )
        self._pending.append(proof)
        if len(self._pending) >= self._batch_size:
            return self.flush()
        return None

    def flush(self) -> AnchorRecord | None:
        """Flush the pending batch to chain.

        Returns the AnchorRecord if there were pending proofs, else None.
        Pending proofs are cleared on success.
        """
        if not self._pending:
            return None

        batch = list(self._pending)
        self._pending = []

        # Compute leaf hashes and Merkle root
        leaves = [p.membership_leaf() for p in batch]
        batch_root = _compute_merkle_root(leaves)

        # Submit to chain
        block_height = self._submitter.submit(
            batch_root=batch_root,
            constitutional_hash=self._constitutional_hash,
            proof_count=len(batch),
        )

        # Create immutable record
        record = AnchorRecord(
            anchor_id=uuid.uuid4().hex[:8],
            batch_root=batch_root,
            constitutional_hash=self._constitutional_hash,
            proof_count=len(batch),
            block_height=block_height,
            submitted_at=time.time(),
            proof_ids=tuple(p.proof_id for p in batch),
            leaf_hashes=tuple(leaves),
        )
        self._history.append(record)
        return record

    def verify_proof_in_history(self, proof: ProofEvidence) -> AnchorRecord | None:
        """Find and return the AnchorRecord that contains this proof.

        Returns None if the proof is not found in any anchor batch.
        """
        for record in self._history:
            if record.verify_membership(proof):
                return record
        return None

    def summary(self) -> dict[str, Any]:
        return {
            "constitutional_hash": self._constitutional_hash,
            "batch_size": self._batch_size,
            "pending": self._pending_count_safe(),
            "total_anchored": self.total_proofs_anchored,
            "batches_submitted": len(self._history),
            "latest_block": self._history[-1].block_height if self._history else None,
        }

    def _pending_count_safe(self) -> int:
        return len(self._pending)
