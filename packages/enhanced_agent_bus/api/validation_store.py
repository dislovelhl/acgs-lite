"""
ACGS-2 Validation Store — In-Memory Ring Buffer
Constitutional Hash: 608508a9bd224290

Thread-safe storage for recent validation results.
Production: replace with Redis or PostgreSQL.
"""

import threading
import time
from collections import deque
from dataclasses import dataclass, field

from typing_extensions import TypedDict

MAX_ENTRIES = 100
RECENT_VALIDATIONS_LIMIT = 20


class RecentValidationRecord(TypedDict):
    """Serialized recent validation record for API responses."""

    agent_id: str
    action: str
    compliant: bool
    score: float
    latency_ms: float
    timestamp: float


class ValidationStats(TypedDict):
    """Aggregated validation stats payload shape."""

    total_validations: int
    compliance_rate: float
    avg_latency_ms: float
    unique_agents: int
    recent_validations: list[RecentValidationRecord]


@dataclass
class ValidationEntry:
    """A single validation result."""

    agent_id: str
    action: str
    compliant: bool
    score: float
    latency_ms: float
    request_id: str
    timestamp: float = field(default_factory=time.time)


class ValidationStore:
    """Thread-safe ring buffer for recent validation results."""

    def __init__(self, max_entries: int = MAX_ENTRIES) -> None:
        self._entries: deque[ValidationEntry] = deque(maxlen=max_entries)
        self._lock = threading.Lock()
        self._total_count = 0

    def record(self, entry: ValidationEntry) -> None:
        """Record a validation result."""
        with self._lock:
            self._entries.append(entry)
            self._total_count += 1

    def get_recent(self, limit: int = 20) -> list[ValidationEntry]:
        """Return the most recent entries (newest first)."""
        with self._lock:
            entries = list(self._entries)
        return list(reversed(entries))[:limit]

    def _empty_stats(self, total: int) -> ValidationStats:
        """Build stats payload when no validation data exists."""
        return {
            "total_validations": total,
            "compliance_rate": 100.0,
            "avg_latency_ms": 0.0,
            "unique_agents": 0,
            "recent_validations": [],
        }

    def _serialize_recent_validations(
        self, entries: list[ValidationEntry], limit: int = RECENT_VALIDATIONS_LIMIT
    ) -> list[RecentValidationRecord]:
        """Serialize recent entries newest-first for API responses."""
        return [
            {
                "agent_id": entry.agent_id,
                "action": entry.action,
                "compliant": entry.compliant,
                "score": entry.score,
                "latency_ms": entry.latency_ms,
                "timestamp": entry.timestamp,
            }
            for entry in reversed(entries[-limit:])
        ]

    def get_stats(self) -> ValidationStats:
        """Return aggregated statistics from stored validations."""
        with self._lock:
            entries = list(self._entries)
            total = self._total_count

        if not entries:
            return self._empty_stats(total)

        compliant_count = sum(1 for e in entries if e.compliant)
        avg_latency = sum(e.latency_ms for e in entries) / len(entries)
        unique_agents = len({e.agent_id for e in entries})
        entry_count = len(entries)

        return {
            "total_validations": total,
            "compliance_rate": (compliant_count / entry_count) * 100,
            "avg_latency_ms": round(avg_latency, 3),
            "unique_agents": unique_agents,
            "recent_validations": self._serialize_recent_validations(entries),
        }


# Singleton instance
_store = ValidationStore()


def get_validation_store() -> ValidationStore:
    """Return the global validation store singleton."""
    return _store
