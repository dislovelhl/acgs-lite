"""Lifecycle evidence records and durable audit sink.

The sink provides a strict append-only contract with compare-and-swap
semantics: every ``append()`` must supply the expected previous hash,
and the operation fails atomically if another writer has advanced the
head since the caller last read it.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _freeze_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        frozen_items = {str(key): _freeze_metadata(item) for key, item in value.items()}
        return MappingProxyType(frozen_items)
    if isinstance(value, list | tuple):
        return tuple(_freeze_metadata(item) for item in value)
    return value


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    return value


@dataclass(frozen=True)
class LifecycleEvidenceRecord:
    """Single evidence entry for a lifecycle transition.

    Frozen so records are tamper-evident once created.
    """

    bundle_id: str
    tenant_id: str
    from_status: str
    to_status: str
    actor_id: str
    actor_role: str
    reason: str = ""
    timestamp: datetime = field(default_factory=_utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    @property
    def content_hash(self) -> str:
        """Deterministic hash of the record content."""
        canonical = json.dumps(
            {
                "bundle_id": self.bundle_id,
                "tenant_id": self.tenant_id,
                "from_status": self.from_status,
                "to_status": self.to_status,
                "actor_id": self.actor_id,
                "actor_role": self.actor_role,
                "reason": self.reason,
                "timestamp": self.timestamp.isoformat(),
                "metadata": _json_ready(self.metadata),
            },
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "tenant_id": self.tenant_id,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "actor_id": self.actor_id,
            "actor_role": self.actor_role,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
            "metadata": _json_ready(self.metadata),
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True)
class LifecycleAuditReceipt:
    """Returned by the sink after a successful append."""

    chain_hash: str
    index: int
    record: LifecycleEvidenceRecord


class LifecycleAuditSinkError(Exception):
    """Raised when an append fails the CAS check or durability contract."""


@runtime_checkable
class LifecycleAuditSink(Protocol):
    """Durable, append-only evidence sink with CAS head semantics.

    Implementations must guarantee:
    - ``head()`` reads the persisted head hash (not a cached value).
    - ``append()`` compares ``expected_prev_hash`` against the durable head
      and atomically appends if they match, raising on mismatch.
    """

    def head(self) -> str | None:
        """Return the chain hash of the last appended record, or None if empty."""
        ...

    def append(
        self,
        record: LifecycleEvidenceRecord,
        expected_prev_hash: str | None,
    ) -> LifecycleAuditReceipt:
        """Append a record with CAS on the previous head.

        Raises:
            LifecycleAuditSinkError: if ``expected_prev_hash`` does not
                match the current durable head.
        """
        ...

    def records(self) -> list[LifecycleEvidenceRecord]:
        """Return all stored records in append order."""
        ...


class InMemoryLifecycleAuditSink:
    """In-process sink for tests and single-process use."""

    def __init__(self) -> None:
        self._records: list[LifecycleEvidenceRecord] = []
        self._chain_hashes: list[str] = []
        self._lock = threading.Lock()

    def head(self) -> str | None:
        with self._lock:
            return self._chain_hashes[-1] if self._chain_hashes else None

    def append(
        self,
        record: LifecycleEvidenceRecord,
        expected_prev_hash: str | None,
    ) -> LifecycleAuditReceipt:
        with self._lock:
            current_head = self._chain_hashes[-1] if self._chain_hashes else None
            if expected_prev_hash != current_head:
                raise LifecycleAuditSinkError(
                    f"CAS mismatch: expected head {expected_prev_hash!r}, actual {current_head!r}"
                )

            prev = current_head or "genesis"
            chain_input = f"{prev}|{record.content_hash}"
            chain_hash = hashlib.sha256(chain_input.encode()).hexdigest()[:16]

            self._records.append(record)
            self._chain_hashes.append(chain_hash)

            return LifecycleAuditReceipt(
                chain_hash=chain_hash,
                index=len(self._records) - 1,
                record=record,
            )

    def records(self) -> list[LifecycleEvidenceRecord]:
        with self._lock:
            return list(self._records)

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)


__all__ = [
    "InMemoryLifecycleAuditSink",
    "LifecycleAuditReceipt",
    "LifecycleAuditSink",
    "LifecycleAuditSinkError",
    "LifecycleEvidenceRecord",
]
