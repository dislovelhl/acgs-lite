"""Constitutional rules — the core of ACGS-Lite.

A Constitution is a set of Rules that govern agent behavior.
Rules can be loaded from YAML, dicts, or created programmatically.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar


@dataclass(frozen=True, slots=True)
class Obligation:
    """exp132: Immutable follow-up obligation created by governance decisions."""

    obligation_type: str
    sla_minutes: int = 0
    assignee: str = ""
    reason: str = ""
    rule_id: str = ""
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    _VALID_TYPES: ClassVar[tuple[str, ...]] = (
        "human_review",
        "notify",
        "log_enhanced",
        "time_bounded",
    )

    def __post_init__(self) -> None:
        if self.obligation_type not in self._VALID_TYPES:
            msg = (
                f"Invalid obligation_type {self.obligation_type!r}; "
                f"expected one of {self._VALID_TYPES}"
            )
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize obligation to a JSON-compatible dict."""
        return {
            "obligation_type": self.obligation_type,
            "sla_minutes": self.sla_minutes,
            "assignee": self.assignee,
            "reason": self.reason,
            "rule_id": self.rule_id,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


class ObligationSet:
    """exp132: In-memory set of governance obligations with resolution tracking."""

    __slots__ = ("_obligations", "_resolved")

    def __init__(self) -> None:
        self._obligations: list[Obligation] = []
        self._resolved: set[int] = set()

    def add(
        self,
        obligation_type: str,
        sla_minutes: int = 0,
        assignee: str = "",
        reason: str = "",
        rule_id: str = "",
        metadata: dict[str, Any] | None = None,
        created_at: str = "",
    ) -> Obligation:
        """Add a new obligation and return it."""
        ts = created_at or datetime.now(timezone.utc).isoformat()
        obligation = Obligation(
            obligation_type=obligation_type,
            sla_minutes=sla_minutes,
            assignee=assignee,
            reason=reason,
            rule_id=rule_id,
            created_at=ts,
            metadata=metadata or {},
        )
        self._obligations.append(obligation)
        return obligation

    def resolve(self, index_or_rule_id: int | str) -> None:
        """Mark obligations as resolved by index or rule_id."""
        if isinstance(index_or_rule_id, int):
            if index_or_rule_id < 0 or index_or_rule_id >= len(self._obligations):
                raise IndexError("Obligation index out of range")
            self._resolved.add(index_or_rule_id)
            return

        matched = False
        for idx, obligation in enumerate(self._obligations):
            if obligation.rule_id == index_or_rule_id:
                self._resolved.add(idx)
                matched = True
        if not matched:
            raise ValueError(f"No obligations found for rule_id {index_or_rule_id!r}")

    def pending(self) -> list[Obligation]:
        """Return unresolved obligations."""
        return [
            obligation
            for idx, obligation in enumerate(self._obligations)
            if idx not in self._resolved
        ]

    def all(self) -> list[Obligation]:
        """Return all obligations."""
        return list(self._obligations)

    def export(self) -> list[dict[str, Any]]:
        """Export obligations with resolved status."""
        exported: list[dict[str, Any]] = []
        for idx, obligation in enumerate(self._obligations):
            row = obligation.to_dict()
            row["resolved"] = idx in self._resolved
            exported.append(row)
        return exported

    def summary(self) -> dict[str, Any]:
        """Return aggregate obligation statistics."""
        by_type: dict[str, int] = {}
        for obligation in self._obligations:
            by_type[obligation.obligation_type] = by_type.get(obligation.obligation_type, 0) + 1

        total = len(self._obligations)
        resolved = len(self._resolved)
        pending = total - resolved

        return {
            "total": total,
            "resolved": resolved,
            "pending": pending,
            "by_type": by_type,
        }

    def __len__(self) -> int:
        return len(self._obligations)
