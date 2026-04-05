"""In-memory AuditStore backed by acgs_lite.audit.AuditLog.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from acgs_lite.audit import AuditEntry, AuditLog

from .audit_store import AuditStore


class InMemoryAuditStore(AuditStore):
    """Wraps the existing AuditLog for AuditStore conformance."""

    def __init__(self, log: AuditLog | None = None) -> None:
        self._log = log if log is not None else AuditLog()

    def append(self, entry: AuditEntry) -> str:
        self._log.record(entry)
        return entry.id

    def get(self, entry_id: str) -> AuditEntry | None:
        for e in self._log.entries:
            if e.id == entry_id:
                return e
        return None

    def list_entries(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        agent_id: str | None = None,
    ) -> list[AuditEntry]:
        entries = self._log.entries
        if agent_id is not None:
            entries = [e for e in entries if e.agent_id == agent_id]
        return entries[offset : offset + limit]

    def count(self) -> int:
        return len(self._log)

    def verify_chain(self) -> bool:
        return self._log.verify_chain()
