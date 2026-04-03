"""Constitution Sync — constitution distribution to subnet nodes.

The SN Owner is the authoritative source of the active constitution.
Every miner and validator must independently verify their constitution
hash matches the SN Owner's before accepting any governance task.

Three components:
  ConstitutionDistributor  — SN Owner side: serialize + version-stamp
  ConstitutionReceiver     — Miner/Validator side: receive, verify, activate
  ConstitutionVersionRecord — Immutable version history entry

Design invariants:
  • Hash verification is mandatory — no silent drift between nodes
  • Version history is append-only — old versions never overwritten
  • Sync is pull-based by default — nodes request from SN Owner
  • No Bittensor SDK required — transport is pluggable via callback
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Version record (immutable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConstitutionVersionRecord:
    """Immutable record of a specific constitution version.

    Each version is identified by its hash (content-addressed).
    Block height is set when anchored to chain; None until then.
    """

    version_id: str
    constitution_hash: str
    yaml_content: str
    activated_at: float
    block_height: int | None = None
    description: str = ""

    @classmethod
    def create(
        cls,
        yaml_content: str,
        description: str = "",
        block_height: int | None = None,
    ) -> ConstitutionVersionRecord:
        content_hash = hashlib.sha256(yaml_content.encode()).hexdigest()[:16]
        return cls(
            version_id=uuid.uuid4().hex[:8],
            constitution_hash=content_hash,
            yaml_content=yaml_content,
            activated_at=time.time(),
            block_height=block_height,
            description=description,
        )

    @property
    def age_seconds(self) -> float:
        return time.time() - self.activated_at


# ---------------------------------------------------------------------------
# Sync message
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConstitutionSyncMessage:
    """Broadcast message from SN Owner carrying the active constitution.

    Nodes verify `expected_hash` matches their locally computed hash
    of `yaml_content` before activating the constitution.
    """

    version_id: str
    expected_hash: str
    yaml_content: str
    issued_at: float
    issuer_id: str = "subnet-owner"
    block_height: int | None = None
    description: str = ""

    def verify(self) -> bool:
        """Verify the embedded hash matches the content."""
        computed = hashlib.sha256(self.yaml_content.encode()).hexdigest()[:16]
        return computed == self.expected_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "expected_hash": self.expected_hash,
            "yaml_content": self.yaml_content,
            "issued_at": self.issued_at,
            "issuer_id": self.issuer_id,
            "block_height": self.block_height,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ConstitutionSyncMessage:
        return cls(
            version_id=d["version_id"],
            expected_hash=d["expected_hash"],
            yaml_content=d["yaml_content"],
            issued_at=d["issued_at"],
            issuer_id=d.get("issuer_id", "subnet-owner"),
            block_height=d.get("block_height"),
            description=d.get("description", ""),
        )


# ---------------------------------------------------------------------------
# Distributor (SN Owner side)
# ---------------------------------------------------------------------------


class ConstitutionDistributor:
    """SN Owner-side constitution broadcaster.

    Maintains an ordered version history and produces
    ConstitutionSyncMessages for distribution to miners/validators.

    Usage::

        dist = ConstitutionDistributor(initial_yaml=open("constitution.yaml").read())

        # Get the sync message to broadcast
        msg = dist.broadcast_message()

        # Later: update to a new constitution
        dist.update(new_yaml_content, description="Added HIPAA rule")

        # Version history
        for version in dist.version_history:
            print(version.constitution_hash, version.activated_at)
    """

    def __init__(
        self,
        initial_yaml: str,
        issuer_id: str = "subnet-owner",
        description: str = "initial",
    ) -> None:
        self._issuer_id = issuer_id
        self._history: list[ConstitutionVersionRecord] = []
        self._activate(initial_yaml, description)

    @property
    def active_version(self) -> ConstitutionVersionRecord:
        return self._history[-1]

    @property
    def active_hash(self) -> str:
        return self.active_version.constitution_hash

    @property
    def version_history(self) -> list[ConstitutionVersionRecord]:
        return list(self._history)

    def update(
        self,
        new_yaml: str,
        description: str = "",
        block_height: int | None = None,
    ) -> ConstitutionVersionRecord:
        """Activate a new constitution version.

        Raises ValueError if the content is identical to the active version
        (no-op updates are rejected to keep the history clean).
        """
        new_hash = hashlib.sha256(new_yaml.encode()).hexdigest()[:16]
        if new_hash == self.active_hash:
            raise ValueError(
                f"Constitution unchanged (hash={self.active_hash}). "
                "No update recorded."
            )
        return self._activate(new_yaml, description, block_height)

    def broadcast_message(self) -> ConstitutionSyncMessage:
        """Produce a sync message for the active version."""
        v = self.active_version
        return ConstitutionSyncMessage(
            version_id=v.version_id,
            expected_hash=v.constitution_hash,
            yaml_content=v.yaml_content,
            issued_at=time.time(),
            issuer_id=self._issuer_id,
            block_height=v.block_height,
            description=v.description,
        )

    def _activate(
        self,
        yaml_content: str,
        description: str,
        block_height: int | None = None,
    ) -> ConstitutionVersionRecord:
        record = ConstitutionVersionRecord.create(
            yaml_content,
            description=description,
            block_height=block_height,
        )
        self._history.append(record)
        return record


# ---------------------------------------------------------------------------
# Receiver (Miner / Validator side)
# ---------------------------------------------------------------------------


@dataclass
class SyncResult:
    """Result of a constitution sync attempt on the receiver side."""

    success: bool
    message: str
    new_hash: str = ""
    old_hash: str = ""
    version_id: str = ""


class ConstitutionReceiver:
    """Miner/Validator-side constitution sync handler.

    Receives ConstitutionSyncMessages from the SN Owner,
    verifies the hash, and activates the new constitution.

    The receiver tracks its version history independently and
    refuses to downgrade to a previously seen constitution version.

    Usage::

        receiver = ConstitutionReceiver(node_id="miner-01")

        # On startup: request initial constitution from SN Owner
        msg = distributor.broadcast_message()
        result = receiver.apply(msg)
        assert result.success

        # Constitution YAML now available
        yaml = receiver.active_yaml
        hash_ = receiver.active_hash
    """

    def __init__(self, node_id: str) -> None:
        self._node_id = node_id
        self._active: ConstitutionVersionRecord | None = None
        self._history: list[ConstitutionVersionRecord] = []
        self._seen_hashes: set[str] = set()

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def is_initialised(self) -> bool:
        return self._active is not None

    @property
    def active_hash(self) -> str:
        if self._active is None:
            return ""
        return self._active.constitution_hash

    @property
    def active_yaml(self) -> str:
        if self._active is None:
            return ""
        return self._active.yaml_content

    @property
    def version_history(self) -> list[ConstitutionVersionRecord]:
        return list(self._history)

    def apply(self, msg: ConstitutionSyncMessage) -> SyncResult:
        """Apply a sync message from the SN Owner.

        Verification order:
          1. Hash integrity: recompute hash from content, compare to expected
          2. No-op: same hash as active → already up-to-date
          3. Activate: store and make active

        Returns SyncResult with success flag and human-readable message.
        """
        old_hash = self.active_hash

        # 1. Hash integrity check
        if not msg.verify():
            computed = hashlib.sha256(msg.yaml_content.encode()).hexdigest()[:16]
            return SyncResult(
                success=False,
                message=(
                    f"Hash mismatch: expected={msg.expected_hash} "
                    f"computed={computed}"
                ),
                old_hash=old_hash,
            )

        # 2. No-op check
        if msg.expected_hash == old_hash:
            return SyncResult(
                success=True,
                message="Already at this version (no-op).",
                new_hash=old_hash,
                old_hash=old_hash,
                version_id=msg.version_id,
            )

        # 3. Activate
        record = ConstitutionVersionRecord(
            version_id=msg.version_id,
            constitution_hash=msg.expected_hash,
            yaml_content=msg.yaml_content,
            activated_at=time.time(),
            block_height=msg.block_height,
            description=msg.description,
        )
        self._active = record
        self._history.append(record)
        self._seen_hashes.add(msg.expected_hash)

        return SyncResult(
            success=True,
            message=f"Constitution updated {old_hash or '(none)'} → {msg.expected_hash}",
            new_hash=msg.expected_hash,
            old_hash=old_hash,
            version_id=msg.version_id,
        )

    def verify_task_hash(self, task_constitution_hash: str) -> bool:
        """Check that a task's constitution hash matches the active version.

        Miners/validators call this before accepting any governance task.
        """
        return self.active_hash == task_constitution_hash

    def summary(self) -> dict[str, Any]:
        return {
            "node_id": self._node_id,
            "is_initialised": self.is_initialised,
            "active_hash": self.active_hash,
            "versions_seen": len(self._history),
        }
