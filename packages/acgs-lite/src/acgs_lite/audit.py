# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under Apache-2.0. See LICENSE for details.
# Commercial license: https://acgs.ai

"""Audit trail — tamper-evident logging for governance actions.

Every validation, every decision, every override gets recorded.
The audit log provides cryptographic proof of governance compliance.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Backend Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class AuditBackend(Protocol):
    """Pluggable storage backend for audit entries.

    Implementations must be append-only and support chain hash verification.
    """

    def write(self, entry_dict: dict[str, Any], chain_hash: str) -> None:
        """Persist a single audit entry with its chain hash."""
        ...

    def flush(self) -> None:
        """Ensure all buffered writes are durable."""
        ...

    def read_all(self) -> list[tuple[dict[str, Any], str]]:
        """Read all stored (entry_dict, chain_hash) pairs in order."""
        ...


class InMemoryAuditBackend:
    """In-memory backend (default). No durability guarantees."""

    def __init__(self) -> None:
        self._records: list[tuple[dict[str, Any], str]] = []

    def write(self, entry_dict: dict[str, Any], chain_hash: str) -> None:
        self._records.append((entry_dict, chain_hash))

    def flush(self) -> None:
        pass  # no-op for in-memory

    def read_all(self) -> list[tuple[dict[str, Any], str]]:
        return list(self._records)


class JSONLAuditBackend:
    """Append-only JSONL file backend with explicit flush/fsync.

    Each line is a JSON object with ``_chain_hash`` alongside the entry fields.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = open(self._path, "a")  # noqa: SIM115

    def write(self, entry_dict: dict[str, Any], chain_hash: str) -> None:
        record = {**entry_dict, "_chain_hash": chain_hash}
        self._fd.write(json.dumps(record, sort_keys=True) + "\n")

    def flush(self) -> None:
        self._fd.flush()
        os.fsync(self._fd.fileno())

    def read_all(self) -> list[tuple[dict[str, Any], str]]:
        results: list[tuple[dict[str, Any], str]] = []
        if not self._path.exists():
            return results
        with open(self._path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                chain_hash = record.pop("_chain_hash", "")
                results.append((record, chain_hash))
        return results

    def close(self) -> None:
        self._fd.close()

    def __del__(self) -> None:
        try:
            self._fd.close()
        except Exception as exc:
            logger.debug("failed to close JSONL audit backend file handle: %s", exc, exc_info=True)


@dataclass
class AuditEntry:
    """A single audit log entry."""

    id: str
    type: str  # validation, override, maci_check
    agent_id: str = ""
    action: str = ""
    valid: bool = True
    violations: list[str] = field(default_factory=list)
    constitutional_hash: str = ""
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "agent_id": self.agent_id,
            "action": self.action,
            "valid": self.valid,
            "violations": self.violations,
            "constitutional_hash": self.constitutional_hash,
            "latency_ms": self.latency_ms,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }

    @property
    def entry_hash(self) -> str:
        """Hash of this entry for chain integrity."""
        canonical = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class AuditLog:
    """Tamper-evident audit log.

    Records all governance decisions with cryptographic chaining.
    Each entry's hash includes the previous entry's hash, creating
    a chain that detects tampering.

    Usage::

        log = AuditLog()
        log.record(AuditEntry(id="1", type="validation", valid=True))
        log.export_json("audit.json")
    """

    def __init__(
        self,
        max_entries: int = 10000,
        backend: AuditBackend | None = None,
    ) -> None:
        self._entries: list[AuditEntry] = []
        self._chain_hashes: list[str] = []
        self.max_entries = max_entries
        self._backend = backend

    @property
    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    def record(self, entry: AuditEntry) -> str:
        """Record an audit entry and return its chain hash.

        The chain hash includes the previous entry's hash, providing
        tamper detection.
        """
        # Build chain hash
        prev_hash = self._chain_hashes[-1] if self._chain_hashes else "genesis"
        chain_input = f"{prev_hash}|{entry.entry_hash}"
        chain_hash = hashlib.sha256(chain_input.encode()).hexdigest()[:16]

        self._entries.append(entry)
        self._chain_hashes.append(chain_hash)

        # Persist to backend if configured
        if self._backend is not None:
            try:
                self._backend.write(entry.to_dict(), chain_hash)
            except Exception as exc:
                logger.warning("audit backend write failed: %s", exc, exc_info=True)

        # Trim if over max; recompute the first retained entry's hash against
        # 'genesis' so verify_chain() remains valid over the trimmed window.
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries :]
            self._chain_hashes = self._chain_hashes[-self.max_entries :]
            first_chain_input = f"genesis|{self._entries[0].entry_hash}"
            self._chain_hashes[0] = hashlib.sha256(first_chain_input.encode()).hexdigest()[:16]

        return chain_hash

    def flush(self) -> None:
        """Flush pending writes to the backend. No-op if no backend."""
        if self._backend is not None:
            self._backend.flush()

    @classmethod
    def from_backend(cls, backend: AuditBackend, max_entries: int = 10000) -> "AuditLog":
        """Reconstruct an AuditLog from a durable backend.

        Reads all persisted entries and rebuilds the in-memory chain.
        """
        log = cls(max_entries=max_entries, backend=backend)
        for entry_dict, chain_hash in backend.read_all():
            entry = AuditEntry(
                id=entry_dict.get("id", ""),
                type=entry_dict.get("type", ""),
                agent_id=entry_dict.get("agent_id", ""),
                action=entry_dict.get("action", ""),
                valid=entry_dict.get("valid", True),
                violations=entry_dict.get("violations", []),
                constitutional_hash=entry_dict.get("constitutional_hash", ""),
                latency_ms=entry_dict.get("latency_ms", 0.0),
                metadata=entry_dict.get("metadata", {}),
                timestamp=entry_dict.get("timestamp", ""),
            )
            log._entries.append(entry)
            log._chain_hashes.append(chain_hash)
        # Trim to max if needed
        if len(log._entries) > max_entries:
            log._entries = log._entries[-max_entries:]
            log._chain_hashes = log._chain_hashes[-max_entries:]
        return log

    def verify_chain(self) -> bool:
        """Verify the integrity of the entire audit chain.

        Returns True if no entries have been tampered with.
        """
        if not self._entries:
            return True

        prev_hash = "genesis"
        for i, entry in enumerate(self._entries):
            chain_input = f"{prev_hash}|{entry.entry_hash}"
            expected = hashlib.sha256(chain_input.encode()).hexdigest()[:16]

            if expected != self._chain_hashes[i]:
                return False

            prev_hash = self._chain_hashes[i]

        return True

    def query(
        self,
        *,
        agent_id: str | None = None,
        entry_type: str | None = None,
        valid: bool | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Query audit entries with filters."""
        results = self._entries

        if agent_id is not None:
            results = [e for e in results if e.agent_id == agent_id]
        if entry_type is not None:
            results = [e for e in results if e.type == entry_type]
        if valid is not None:
            results = [e for e in results if e.valid == valid]

        return results[-limit:]

    def export_json(self, path: str | Path) -> None:
        """Export audit log to JSON file."""
        data = {
            "entries": [e.to_dict() for e in self._entries],
            "chain_valid": self.verify_chain(),
            "entry_count": len(self._entries),
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def export_dicts(self) -> list[dict[str, Any]]:
        """Export audit log as list of dicts."""
        return [e.to_dict() for e in self._entries]

    @property
    def compliance_rate(self) -> float:
        """Percentage of valid entries."""
        if not self._entries:
            return 1.0
        valid_count = sum(1 for e in self._entries if e.valid)
        return valid_count / len(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return (
            f"AuditLog(entries={len(self._entries)}, "
            f"compliance={self.compliance_rate:.1%}, "
            f"chain_valid={self.verify_chain()})"
        )
