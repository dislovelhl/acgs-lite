"""Types and helpers used by the governance validation engine.

Extracted from ``core.py`` to keep that module focused on the
:class:`GovernanceEngine` class itself.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from acgs_lite.audit import AuditEntry
from acgs_lite.constitution import Severity


class Violation(NamedTuple):
    """A single rule violation (NamedTuple for C-speed construction)."""

    rule_id: str
    rule_text: str
    severity: Severity
    matched_content: str
    category: str


@dataclass(slots=True)
class ValidationResult:
    """Result of validating an action against the constitution."""

    valid: bool
    constitutional_hash: str
    violations: list[Violation] = field(default_factory=list)
    rules_checked: int = 0
    latency_ms: float = 0.0
    request_id: str = ""
    timestamp: str = ""
    action: str = ""
    agent_id: str = ""

    @property
    def blocking_violations(self) -> list[Violation]:
        """Violations that block execution."""
        return [v for v in self.violations if v.severity.blocks()]

    @property
    def warnings(self) -> list[Violation]:
        """Non-blocking violations (warnings)."""
        return [v for v in self.violations if not v.severity.blocks()]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "valid": self.valid,
            "constitutional_hash": self.constitutional_hash,
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "rule_text": v.rule_text,
                    "severity": v.severity.value,
                    "matched_content": v.matched_content,
                    "category": v.category,
                }
                for v in self.violations
            ],
            "rules_checked": self.rules_checked,
            "latency_ms": self.latency_ms,
            "request_id": self.request_id,
            "action": self.action,
            "agent_id": self.agent_id,
        }


def _dedup_violations(violations: list) -> list:
    """Deduplicate violations by rule_id (called only when len > 1)."""
    seen: set[str] = set()
    result = []
    for v in violations:
        if v.rule_id not in seen:
            seen.add(v.rule_id)
            result.append(v)
    return result


# Type for custom validator functions
CustomValidator = Callable[[str, dict[str, Any]], list[Violation]]


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
