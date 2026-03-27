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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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

    def __init__(self, max_entries: int = 10000) -> None:
        self._entries: list[AuditEntry] = []
        self._chain_hashes: list[str] = []
        self.max_entries = max_entries

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

        # Trim if over max; recompute the first retained entry's hash against
        # 'genesis' so verify_chain() remains valid over the trimmed window.
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries :]
            self._chain_hashes = self._chain_hashes[-self.max_entries :]
            first_chain_input = f"genesis|{self._entries[0].entry_hash}"
            self._chain_hashes[0] = hashlib.sha256(first_chain_input.encode()).hexdigest()[:16]

        return chain_hash

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
