"""Constitutional rules — the core of ACGS-Lite.

A Constitution is a set of Rules that govern agent behavior.
Rules can be loaded from YAML, dicts, or created programmatically.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar


@dataclass(frozen=True, slots=True)
class DriftSignal:
    """exp133: Immutable governance drift signal."""

    signal_type: str
    agent_id: str
    evidence: str
    severity: str
    timestamp: str
    metadata: dict[str, Any] = field(default_factory=dict)

    _VALID_SIGNAL_TYPES: ClassVar[tuple[str, ...]] = (
        "probing",
        "gaming",
        "escalation_suppression",
        "boundary_walking",
    )
    _VALID_SEVERITIES: ClassVar[tuple[str, ...]] = ("low", "medium", "high")

    def __post_init__(self) -> None:
        if self.signal_type not in self._VALID_SIGNAL_TYPES:
            msg = (
                f"Invalid signal_type {self.signal_type!r}; "
                f"expected one of {self._VALID_SIGNAL_TYPES}"
            )
            raise ValueError(msg)
        if self.severity not in self._VALID_SEVERITIES:
            msg = f"Invalid severity {self.severity!r}; expected one of {self._VALID_SEVERITIES}"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize signal to a JSON-compatible dict."""
        return {
            "signal_type": self.signal_type,
            "agent_id": self.agent_id,
            "evidence": self.evidence,
            "severity": self.severity,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class GovernanceDriftDetector:
    """exp133: Detect behavioral drift patterns from governance decision streams."""

    __slots__ = ("_thresholds", "_signals")

    def __init__(self) -> None:
        self._thresholds: dict[str, float | int] = {}
        self._signals: list[DriftSignal] = []
        self.configure_thresholds()

    def configure_thresholds(
        self,
        deny_rate_threshold: float = 0.4,
        consecutive_deny_threshold: int = 5,
        escalation_suppression_window: int = 10,
        boundary_walk_threshold: float = 0.3,
    ) -> None:
        """Configure detection thresholds."""
        self._thresholds = {
            "deny_rate_threshold": deny_rate_threshold,
            "consecutive_deny_threshold": consecutive_deny_threshold,
            "escalation_suppression_window": escalation_suppression_window,
            "boundary_walk_threshold": boundary_walk_threshold,
        }

    def analyze_decisions(
        self,
        decisions: Sequence[dict[str, Any]],
        agent_id: str = "",
    ) -> list[DriftSignal]:
        """Analyze decision stream and return newly generated drift signals."""
        if not decisions:
            return []

        created: list[DriftSignal] = []
        deny_count = 0
        escalate_count = 0
        warning_allow_count = 0

        for decision in decisions:
            d = str(decision.get("decision", ""))
            if d == "deny":
                deny_count += 1
            elif d == "escalate":
                escalate_count += 1
            elif d == "allow" and decision.get("rule_ids"):
                warning_allow_count += 1

        total = len(decisions)
        deny_rate = deny_count / total
        if deny_rate > float(self._thresholds["deny_rate_threshold"]):
            created.append(
                self._make_signal(
                    signal_type="probing",
                    agent_id=agent_id,
                    severity="high" if deny_rate > 0.7 else "medium",
                    evidence=(
                        f"Deny rate {deny_rate:.1%} exceeds threshold "
                        f"{float(self._thresholds['deny_rate_threshold']):.1%}"
                    ),
                    metadata={"deny_rate": deny_rate, "total_decisions": total},
                )
            )

        consecutive_threshold = int(self._thresholds["consecutive_deny_threshold"])
        streak = 0
        last_norm = ""
        for decision in decisions:
            if str(decision.get("decision", "")) != "deny":
                streak = 0
                last_norm = ""
                continue

            norm = self._normalize_action(str(decision.get("action", "")))
            if norm and norm == last_norm:
                streak += 1
            else:
                streak = 1
                last_norm = norm

            if streak >= consecutive_threshold:
                created.append(
                    self._make_signal(
                        signal_type="gaming",
                        agent_id=agent_id,
                        severity="high",
                        evidence=(
                            f"{streak} consecutive denied retries detected for "
                            f"action family {norm!r}"
                        ),
                        metadata={"streak": streak, "normalized_action": norm},
                    )
                )
                break

        boundary_ratio = (warning_allow_count / total) if total > 0 else 0.0
        if boundary_ratio > float(self._thresholds["boundary_walk_threshold"]):
            created.append(
                self._make_signal(
                    signal_type="boundary_walking",
                    agent_id=agent_id,
                    severity="medium",
                    evidence=(
                        f"Warning-allow ratio {boundary_ratio:.1%} exceeds threshold "
                        f"{float(self._thresholds['boundary_walk_threshold']):.1%}"
                    ),
                    metadata={
                        "warning_allow_count": warning_allow_count,
                        "boundary_ratio": boundary_ratio,
                    },
                )
            )

        suppression_window = int(self._thresholds["escalation_suppression_window"])
        if warning_allow_count >= suppression_window and escalate_count == 0:
            created.append(
                self._make_signal(
                    signal_type="escalation_suppression",
                    agent_id=agent_id,
                    severity="medium",
                    evidence=(
                        f"{warning_allow_count} warning allows with zero escalations "
                        f"in a {total}-decision window"
                    ),
                    metadata={
                        "warning_allow_count": warning_allow_count,
                        "escalate_count": escalate_count,
                        "window": total,
                    },
                )
            )

        self._signals.extend(created)
        return created

    def summary(self) -> dict[str, Any]:
        """Return aggregate drift signal counts."""
        by_type: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        by_agent: dict[str, int] = {}

        for signal in self._signals:
            by_type[signal.signal_type] = by_type.get(signal.signal_type, 0) + 1
            by_severity[signal.severity] = by_severity.get(signal.severity, 0) + 1
            key = signal.agent_id or "unknown"
            by_agent[key] = by_agent.get(key, 0) + 1

        return {
            "total_signals": len(self._signals),
            "by_type": by_type,
            "by_severity": by_severity,
            "by_agent": by_agent,
        }

    def export(self) -> list[dict[str, Any]]:
        """Export all drift signals as dictionaries."""
        return [signal.to_dict() for signal in self._signals]

    def clear(self) -> None:
        """Clear tracked signals."""
        self._signals.clear()

    @staticmethod
    def _normalize_action(action: str) -> str:
        compact = re.sub(r"\s+", " ", action.strip().lower())
        return re.sub(r"[^a-z0-9 ]", "", compact)

    @staticmethod
    def _make_signal(
        signal_type: str,
        agent_id: str,
        evidence: str,
        severity: str,
        metadata: dict[str, Any],
    ) -> DriftSignal:
        return DriftSignal(
            signal_type=signal_type,
            agent_id=agent_id,
            evidence=evidence,
            severity=severity,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=metadata,
        )
