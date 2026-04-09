"""Types and helpers used by the governance validation engine.

Extracted from ``core.py`` to keep that module focused on the
:class:`GovernanceEngine` class itself.
"""

from __future__ import annotations

import itertools

from acgs_lite.audit import AuditEntry

from .models import CustomValidator, ValidationResult, Violation, _dedup_violations

_ANON = "anonymous"  # interned sentinel for compact allow-record detection
_EMPTY_VIOLATIONS: list = []  # shared empty-violation list for allow-path records


class _NoopRecorder:
    """Discards all appended audit records; tracks call count for stats.

    exp59: Default _fast_records replaces the real list to eliminate per-call
    tuple creation (~50ns) and list.append overhead (~16ns). Only the count
    is preserved for engine.stats["total_validations"].
    """

    __slots__ = ("_count",)

    def __init__(self) -> None:
        self._count = 0

    def append(self, item: object) -> None:  # noqa: ARG002
        self._count += 1

    def __len__(self) -> int:
        return self._count


class _FastAuditLog:
    """Lightweight audit log: stores raw tuples instead of AuditEntry objects.

    Used as the default when GovernanceEngine is constructed without an
    explicit audit_log. Avoids SHA256 chain hashing AND AuditEntry dataclass
    instantiation on every validate() call. Pass AuditLog() explicitly for
    tamper-evident chain verification.

    Allow-path records use a compact 2-tuple (request_id, action) when
    agent_id is the default "anonymous", saving ~0.15µs vs the full 8-tuple.
    Deny/escalate records always use the full 8-tuple format.
    """

    def __init__(self, const_hash: str = "") -> None:
        self._records: list[tuple] = []
        self._const_hash = const_hash

    @property
    def entries(self) -> list[AuditEntry]:
        # Reconstruct AuditEntry objects on demand (rare operation)
        _ch = self._const_hash
        return [
            AuditEntry(
                id=r[0],
                type="validation",
                agent_id=_ANON,
                action=r[1],
                valid=True,
                violations=[],
                constitutional_hash=_ch,
                latency_ms=0.0,
                timestamp="",
            )
            if len(r) == 2  # compact allow record: (request_id, action)
            else AuditEntry(
                id=r[0],
                type="validation",
                agent_id=r[1],
                action=r[2],
                valid=r[3],
                violations=r[4],
                constitutional_hash=r[5],
                latency_ms=r[6],
                timestamp=r[7],
            )
            for r in self._records
        ]

    def record_fast(
        self,
        req_id: str,
        agent_id: str,
        action: str,
        valid: bool,
        violation_ids: list[str],
        const_hash: str,
        latency_ms: float,
        timestamp: str,
    ) -> None:
        self._records.append(
            (req_id, agent_id, action, valid, violation_ids, const_hash, latency_ms, timestamp)
        )

    def record(self, entry: AuditEntry) -> str:
        """Compatibility shim for callers passing AuditEntry objects."""
        self._records.append(
            (
                entry.id,
                entry.agent_id,
                entry.action,
                entry.valid,
                entry.violations,
                entry.constitutional_hash,
                entry.latency_ms,
                entry.timestamp,
            )
        )
        return ""

    def __len__(self) -> int:
        return len(self._records)


_request_counter = itertools.count(1)

__all__ = [
    "CustomValidator",
    "ValidationResult",
    "Violation",
    "_dedup_violations",
    "_ANON",
    "_FastAuditLog",
    "_NoopRecorder",
    "_request_counter",
]
