"""Arweave Audit Log — Phase 2.3: permanent off-chain governance audit trail.

On-chain storage is too expensive for full audit logs. Arweave provides
permanent, per-byte storage. The architecture from Q&A §3C:

    Batch audit log entries
         ↓  compute Merkle root
    Upload batch JSON → Arweave (permanent, content-addressed)
         ↓  anchor batch_root
    Submit batch_root → Bittensor chain (tamper-evident, cheap)
         ↓
    Auditors verify: merkle_root matches chain anchor AND
                     entry content matches the Merkle path

This produces the "Selective On-Chain / Off-Chain Split" from roadmap §2.4:
  On-chain (small, immutable):   batch Merkle root + constitutional hash
  Off-chain (large, permanent):  full audit log entries + reasoning text

Privacy: Entries store decision outcomes (pass/fail, escalation type), not
decision content. Individual judgment text lives in Arweave only, not chain.

Design:
  • Pluggable ArweaveClient Protocol — InMemoryArweaveClient for tests
  • AuditLogEntry is frozen=True, slots=True (audit immutability guarantee)
  • AuditBatch computes Merkle paths on demand — auditors can verify single
    entries without fetching the entire batch
  • ChainSubmitter is the same Protocol as chain_anchor.py — no new interface

Roadmap:  08-subnet-implementation-roadmap.md § Phase 2 On-Chain + Privacy
Q&A §3C: docs/strategy/07-subnet-concept-qa-responses.md
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# Decision type enum (from Q&A §2)
# ---------------------------------------------------------------------------


class AuditDecisionType(Enum):
    AUTO_PASS    = "auto_pass"    # confident automated approval
    AUTO_REJECT  = "auto_reject"  # constitutional violation, hard reject
    ESCALATED    = "escalated"    # sent to human miners
    INFRA_ERROR  = "infra_error"  # timeout, missing data, service failure
    PRECEDENT    = "precedent"    # auto-resolved via PrecedentStore


# ---------------------------------------------------------------------------
# Audit log entry — immutable audit record
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AuditLogEntry:
    """Immutable record of one governance decision.

    Stores outcome metadata only — not judgment content (too large for
    on-chain storage, stored separately in Arweave under the batch).

    Fields:
      entry_id:          unique identifier for this log entry
      case_id:           governance case / escalation ID
      constitutional_hash: which constitution governed this decision
      decision_type:     outcome category (AUTO_PASS, ESCALATED, etc.)
      compliance_passed: True if the decision passed constitutional rules
      impact_score:      aggregate 7-vector score (0.0–1.0)
      escalation_type:   which dimension caused escalation (if any)
      resolution:        final disposition (e.g. "allow", "deny", "allow_with_conditions")
      miner_uid:         miner who handled escalation (empty if auto-resolved)
      validator_grade:   quality score from validators (0.0–1.0, NaN if auto)
      decision_at:       Unix timestamp of the decision
      tags:              extensible metadata (client, framework, domain…)
    """

    entry_id: str
    case_id: str
    constitutional_hash: str
    decision_type: AuditDecisionType
    compliance_passed: bool
    impact_score: float = 0.0
    escalation_type: str = ""
    resolution: str = ""
    miner_uid: str = ""
    validator_grade: float = float("nan")
    decision_at: float = field(default_factory=time.time)
    tags: tuple[tuple[str, str], ...] = ()  # frozen-compatible key-value pairs

    def leaf_hash(self) -> str:
        """SHA-256 hash of the canonical entry representation.

        Used as the Merkle leaf for batch inclusion proofs.
        Deterministic: same entry always produces the same leaf hash.
        """
        payload = (
            f"{self.entry_id}:{self.case_id}:{self.constitutional_hash}:"
            f"{self.decision_type.value}:{self.compliance_passed}:"
            f"{self.impact_score:.6f}:{self.escalation_type}:{self.resolution}:"
            f"{self.miner_uid}:{self.validator_grade:.4f}:{self.decision_at:.3f}"
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "case_id": self.case_id,
            "constitutional_hash": self.constitutional_hash,
            "decision_type": self.decision_type.value,
            "compliance_passed": self.compliance_passed,
            "impact_score": round(self.impact_score, 6),
            "escalation_type": self.escalation_type,
            "resolution": self.resolution,
            "miner_uid": self.miner_uid,
            "validator_grade": self.validator_grade,
            "decision_at": self.decision_at,
            "tags": dict(self.tags),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AuditLogEntry":
        return cls(
            entry_id=d["entry_id"],
            case_id=d["case_id"],
            constitutional_hash=d["constitutional_hash"],
            decision_type=AuditDecisionType(d["decision_type"]),
            compliance_passed=d["compliance_passed"],
            impact_score=d.get("impact_score", 0.0),
            escalation_type=d.get("escalation_type", ""),
            resolution=d.get("resolution", ""),
            miner_uid=d.get("miner_uid", ""),
            validator_grade=d.get("validator_grade", float("nan")),
            decision_at=d.get("decision_at", time.time()),
            tags=tuple((k, v) for k, v in d.get("tags", {}).items()),
        )


# ---------------------------------------------------------------------------
# Arweave client interface (pluggable)
# ---------------------------------------------------------------------------


class ArweaveClient(Protocol):
    """Protocol for uploading to and fetching from Arweave.

    Implement for a real Arweave node/gateway:

        import arweave  # pip install arweave-python-client
        class RealArweaveClient:
            def upload(self, data: bytes, tags: dict[str, str]) -> str:
                tx = arweave.Transaction(wallet, data=data)
                for k, v in tags.items():
                    tx.add_tag(k, v)
                tx.sign()
                tx.send()
                return tx.id
            def fetch(self, tx_id: str) -> bytes:
                return arweave.Transaction.fetch(tx_id).data
    """

    def upload(self, data: bytes, tags: dict[str, str]) -> str:
        """Upload data. Returns the Arweave transaction ID."""
        ...

    def fetch(self, tx_id: str) -> bytes:
        """Fetch data by transaction ID."""
        ...


class InMemoryArweaveClient:
    """In-memory stub — no network I/O, for tests.

    Stores uploads in a dict keyed by deterministic SHA-256 of the data.
    """

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}
        self._tags: dict[str, dict[str, str]] = {}

    def upload(self, data: bytes, tags: dict[str, str] | None = None) -> str:
        tx_id = "ar_" + hashlib.sha256(data).hexdigest()[:16]
        self._store[tx_id] = data
        self._tags[tx_id] = tags or {}
        return tx_id

    def fetch(self, tx_id: str) -> bytes:
        if tx_id not in self._store:
            raise KeyError(f"Arweave tx not found: {tx_id}")
        return self._store[tx_id]

    def get_tags(self, tx_id: str) -> dict[str, str]:
        return dict(self._tags.get(tx_id, {}))

    @property
    def transaction_count(self) -> int:
        return len(self._store)


# ---------------------------------------------------------------------------
# ChainSubmitter interface (same protocol as chain_anchor.py — no new dep)
# ---------------------------------------------------------------------------


class AuditChainSubmitter(Protocol):
    """Protocol for anchoring an audit batch root on-chain.

    Re-declares the same interface as ChainSubmitter in chain_anchor.py.
    Either can be used interchangeably — no import required.
    """

    def submit(
        self,
        batch_root: str,
        constitutional_hash: str,
        proof_count: int,
    ) -> int:
        """Anchor batch_root on-chain. Returns block height."""
        ...


# ---------------------------------------------------------------------------
# Audit batch (produced by the logger at flush time)
# ---------------------------------------------------------------------------


class AuditBatch:
    """Finalized audit log batch, ready for Arweave upload + chain anchoring.

    Not frozen — it's a processing artifact, not an audit record itself.
    Computes Merkle paths on demand for auditor verification.

    The batch_root is anchored on-chain via ChainSubmitter.
    The full batch JSON is stored on Arweave.
    """

    def __init__(
        self,
        batch_id: str,
        constitutional_hash: str,
        entries: list[AuditLogEntry],
        created_at: float | None = None,
    ) -> None:
        self.batch_id = batch_id
        self.constitutional_hash = constitutional_hash
        self._entries: list[AuditLogEntry] = list(entries)
        self._leaf_hashes: list[str] = [e.leaf_hash() for e in self._entries]
        self.batch_root: str = _compute_merkle_root(self._leaf_hashes)
        self.entry_count: int = len(self._entries)
        self.created_at: float = created_at or time.time()

    @property
    def entries(self) -> list[AuditLogEntry]:
        return list(self._entries)

    @property
    def leaf_hashes(self) -> list[str]:
        return list(self._leaf_hashes)

    def find_entry(self, entry_id: str) -> AuditLogEntry | None:
        for e in self._entries:
            if e.entry_id == entry_id:
                return e
        return None

    def merkle_path_for(self, entry_id: str) -> list[tuple[str, str]]:
        """Return the Merkle path proving entry_id is in this batch.

        Each step is (sibling_hash, "left"|"right").
        Raises KeyError if entry_id not found.

        Verification::

            entry = batch.find_entry(entry_id)
            path  = batch.merkle_path_for(entry_id)
            assert verify_merkle_path(entry.leaf_hash(), path, batch.batch_root)
        """
        for idx, entry in enumerate(self._entries):
            if entry.entry_id == entry_id:
                return _merkle_path_for_index(self._leaf_hashes, idx)
        raise KeyError(f"Entry not found in batch: {entry_id}")

    def verify_entry(self, entry: AuditLogEntry) -> bool:
        """Verify that entry is included in this batch."""
        try:
            path = self.merkle_path_for(entry.entry_id)
        except KeyError:
            return False
        return verify_merkle_path(entry.leaf_hash(), path, self.batch_root)

    def compliance_rate(self) -> float:
        if not self._entries:
            return 1.0
        passed = sum(1 for e in self._entries if e.compliance_passed)
        return passed / len(self._entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "batch_root": self.batch_root,
            "constitutional_hash": self.constitutional_hash,
            "entry_count": self.entry_count,
            "created_at": self.created_at,
            "entries": [e.to_dict() for e in self._entries],
            "leaf_hashes": self._leaf_hashes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AuditBatch":
        entries = [AuditLogEntry.from_dict(e) for e in d["entries"]]
        batch = cls(
            batch_id=d["batch_id"],
            constitutional_hash=d["constitutional_hash"],
            entries=entries,
            created_at=d.get("created_at"),
        )
        return batch


# ---------------------------------------------------------------------------
# Audit log receipt (immutable — returned to the caller after flush)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AuditLogReceipt:
    """Immutable receipt from a successful audit log flush.

    Contains everything an auditor needs to verify a specific entry:
      1. Fetch batch from Arweave using arweave_tx_id
      2. Verify batch_root matches on-chain anchor at block_height
      3. Retrieve entry from batch → compute leaf_hash
      4. Compute Merkle path → verify against batch_root

    block_height is None when no chain_submitter is configured.
    """

    receipt_id: str
    batch_id: str
    batch_root: str
    arweave_tx_id: str
    entry_count: int
    constitutional_hash: str
    created_at: float
    block_height: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "batch_id": self.batch_id,
            "batch_root": self.batch_root,
            "arweave_tx_id": self.arweave_tx_id,
            "entry_count": self.entry_count,
            "constitutional_hash": self.constitutional_hash,
            "block_height": self.block_height,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Arweave audit logger
# ---------------------------------------------------------------------------


class ArweaveAuditLogger:
    """Batches governance decisions, uploads to Arweave, anchors roots on-chain.

    Usage::

        arweave = InMemoryArweaveClient()
        submitter = InMemorySubmitter()   # from chain_anchor.py or any stub
        logger = ArweaveAuditLogger(
            constitutional_hash="608508a9bd224290",
            arweave_client=arweave,
            chain_submitter=submitter,
            batch_size=50,
        )

        entry = AuditLogEntry(
            entry_id=uuid.uuid4().hex[:8],
            case_id="ESC-001",
            constitutional_hash="608508a9bd224290",
            decision_type=AuditDecisionType.ESCALATED,
            compliance_passed=True,
            impact_score=0.85,
            resolution="allow_with_conditions",
            miner_uid="miner-01",
            validator_grade=0.92,
        )
        logger.add_entry(entry)
        receipt = logger.flush()   # → AuditLogReceipt

        # Auditor verification:
        batch_bytes = arweave.fetch(receipt.arweave_tx_id)
        batch = AuditBatch.from_dict(json.loads(batch_bytes))
        assert batch.batch_root == receipt.batch_root
        assert batch.verify_entry(entry)
    """

    def __init__(
        self,
        constitutional_hash: str,
        arweave_client: ArweaveClient,
        chain_submitter: AuditChainSubmitter | None = None,
        batch_size: int = 100,
    ) -> None:
        self._constitutional_hash = constitutional_hash
        self._arweave = arweave_client
        self._chain_submitter = chain_submitter
        self._batch_size = batch_size
        self._pending: list[AuditLogEntry] = []
        self._receipts: list[AuditLogReceipt] = []

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def receipts(self) -> list[AuditLogReceipt]:
        return list(self._receipts)

    def add_entry(self, entry: AuditLogEntry) -> AuditLogReceipt | None:
        """Add an audit log entry. Auto-flushes when batch is full.

        Raises ValueError if entry's constitutional_hash doesn't match.
        Returns AuditLogReceipt if a flush occurred, else None.
        """
        if entry.constitutional_hash != self._constitutional_hash:
            raise ValueError(
                f"Entry constitutional hash mismatch: "
                f"expected={self._constitutional_hash} got={entry.constitutional_hash}"
            )
        self._pending.append(entry)
        if len(self._pending) >= self._batch_size:
            return self.flush()
        return None

    def flush(self) -> AuditLogReceipt | None:
        """Flush pending entries → Arweave upload + optional chain anchor.

        Returns AuditLogReceipt, or None if no pending entries.
        """
        if not self._pending:
            return None

        batch = AuditBatch(
            batch_id=uuid.uuid4().hex[:12],
            constitutional_hash=self._constitutional_hash,
            entries=list(self._pending),
        )
        self._pending = []

        # Upload full batch JSON to Arweave
        batch_json = json.dumps(batch.to_dict()).encode()
        tx_id = self._arweave.upload(
            batch_json,
            tags={
                "constitutional_hash": self._constitutional_hash,
                "batch_id": batch.batch_id,
                "batch_root": batch.batch_root,
                "App-Name": "ACGS-constitutional-swarm",
            },
        )

        # Anchor batch_root on-chain (optional)
        block_height: int | None = None
        if self._chain_submitter is not None:
            block_height = self._chain_submitter.submit(
                batch_root=batch.batch_root,
                constitutional_hash=self._constitutional_hash,
                proof_count=batch.entry_count,
            )

        receipt = AuditLogReceipt(
            receipt_id=uuid.uuid4().hex[:8],
            batch_id=batch.batch_id,
            batch_root=batch.batch_root,
            arweave_tx_id=tx_id,
            entry_count=batch.entry_count,
            constitutional_hash=self._constitutional_hash,
            created_at=time.time(),
            block_height=block_height,
        )
        self._receipts.append(receipt)
        return receipt

    def fetch_batch(self, receipt: AuditLogReceipt) -> AuditBatch:
        """Reconstruct an AuditBatch from Arweave using a receipt."""
        raw = self._arweave.fetch(receipt.arweave_tx_id)
        return AuditBatch.from_dict(json.loads(raw))

    def summary(self) -> dict[str, Any]:
        return {
            "constitutional_hash": self._constitutional_hash,
            "batch_size": self._batch_size,
            "pending": self._pending_count_safe(),
            "total_flushed": sum(r.entry_count for r in self._receipts),
            "batches_stored": len(self._receipts),
            "latest_block": (
                self._receipts[-1].block_height if self._receipts else None
            ),
        }

    def _pending_count_safe(self) -> int:
        return len(self._pending)


# ---------------------------------------------------------------------------
# Merkle utilities
# ---------------------------------------------------------------------------


def _compute_merkle_root(leaves: list[str]) -> str:
    """Binary Merkle root over leaf hashes (insertion order, not sorted).

    Insertion order is preserved for AuditBatch (unlike ChainAnchor which
    sorts for determinism). The batch stores the leaf order, so verification
    only requires the path + root, not a canonical sort.
    """
    if not leaves:
        return hashlib.sha256(b"").hexdigest()

    layer = list(leaves)
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])  # duplicate last (Bitcoin-style padding)
        next_layer: list[str] = []
        for i in range(0, len(layer), 2):
            combined = layer[i] + layer[i + 1]
            next_layer.append(hashlib.sha256(combined.encode()).hexdigest())
        layer = next_layer
    return layer[0]


def _merkle_path_for_index(
    leaves: list[str],
    target_idx: int,
) -> list[tuple[str, str]]:
    """Compute Merkle path for the leaf at target_idx.

    Returns a list of (sibling_hash, position) where position is:
      "right" — sibling is to the right (current node is left child)
      "left"  — sibling is to the left  (current node is right child)

    To verify: start from leaf_hash, at each step combine with sibling
    in the correct order, hash the result, repeat to the root.
    """
    if len(leaves) <= 1:
        return []

    layer = list(leaves)
    idx = target_idx
    path: list[tuple[str, str]] = []

    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])

        if idx % 2 == 0:
            # current is left child — sibling is to the right
            sibling = layer[idx + 1]
            path.append((sibling, "right"))
        else:
            # current is right child — sibling is to the left
            sibling = layer[idx - 1]
            path.append((sibling, "left"))

        # Build next layer
        next_layer: list[str] = []
        for i in range(0, len(layer), 2):
            combined = layer[i] + layer[i + 1]
            next_layer.append(hashlib.sha256(combined.encode()).hexdigest())
        layer = next_layer
        idx = idx // 2

    return path


def verify_merkle_path(
    leaf_hash: str,
    path: list[tuple[str, str]],
    expected_root: str,
) -> bool:
    """Verify a Merkle path against an expected root.

    Args:
        leaf_hash:     SHA-256 hash of the entry (AuditLogEntry.leaf_hash())
        path:          proof path from _merkle_path_for_index()
        expected_root: the batch_root anchored on-chain

    Returns True if the path proves leaf_hash is included in expected_root.
    """
    current = leaf_hash
    for sibling_hash, position in path:
        if position == "right":
            # sibling is right → current is left
            combined = current + sibling_hash
        else:
            # sibling is left → current is right
            combined = sibling_hash + current
        current = hashlib.sha256(combined.encode()).hexdigest()
    return current == expected_root
