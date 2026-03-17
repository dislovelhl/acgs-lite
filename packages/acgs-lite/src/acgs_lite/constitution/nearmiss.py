"""Constitutional rules — the core of ACGS-Lite.

A Constitution is a set of Rules that govern agent behavior.
Rules can be loaded from YAML, dicts, or created programmatically.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class NearMissRecord:
    """exp131: Immutable near-miss governance record."""

    action: str
    rule_id: str
    rule_text: str
    margin_description: str
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize record to a JSON-compatible dict."""
        return {
            "action": self.action,
            "rule_id": self.rule_id,
            "rule_text": self.rule_text,
            "margin_description": self.margin_description,
            "timestamp": self.timestamp,
        }


class NearMissTracker:
    """exp131: Bounded in-memory tracker for governance near misses."""

    __slots__ = ("_records", "_max_records")

    def __init__(self, *, max_records: int = 10_000) -> None:
        self._records: list[NearMissRecord] = []
        self._max_records = max_records

    def record(
        self,
        action: str,
        rule_id: str,
        rule_text: str,
        margin_description: str,
        timestamp: str | None = None,
    ) -> NearMissRecord:
        """Record a near-miss event."""
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        record = NearMissRecord(
            action=action,
            rule_id=rule_id,
            rule_text=rule_text,
            margin_description=margin_description,
            timestamp=ts,
        )
        self._records.append(record)
        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records :]
        return record

    def query(
        self,
        rule_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[NearMissRecord]:
        """Query near-miss records using optional filters."""
        results: list[NearMissRecord] = []
        for record in self._records:
            if rule_id is not None and record.rule_id != rule_id:
                continue
            if since is not None and record.timestamp < since:
                continue
            if until is not None and record.timestamp >= until:
                continue
            results.append(record)
        return results

    def summary(self) -> dict[str, Any]:
        """Return aggregate near-miss statistics."""
        total = len(self._records)
        if total == 0:
            return {
                "total": 0,
                "by_rule": {},
                "time_range": None,
                "top_rules": [],
            }

        by_rule: dict[str, int] = {}
        for record in self._records:
            by_rule[record.rule_id] = by_rule.get(record.rule_id, 0) + 1

        top_rules = sorted(by_rule.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "total": total,
            "by_rule": by_rule,
            "time_range": {
                "earliest": self._records[0].timestamp,
                "latest": self._records[-1].timestamp,
            },
            "top_rules": [{"rule_id": rid, "count": count} for rid, count in top_rules],
        }

    def export(self) -> list[dict[str, Any]]:
        """Export all records as dictionaries."""
        return [record.to_dict() for record in self._records]

    def clear(self) -> None:
        """Clear all tracked records."""
        self._records.clear()

    def __len__(self) -> int:
        return len(self._records)
