"""exp186: GovernanceAnomalyDetector — statistical divergence detection.

Tracks governance decision distributions over time windows and flags
anomalies: sudden spikes in denials, unusual agent patterns, severity
distribution shifts, or rule firing frequency changes.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class AnomalySignal:
    anomaly_type: str
    metric: str
    expected_value: float
    observed_value: float
    deviation: float
    severity: str
    timestamp: datetime
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "anomaly_type": self.anomaly_type,
            "metric": self.metric,
            "expected_value": round(self.expected_value, 4),
            "observed_value": round(self.observed_value, 4),
            "deviation": round(self.deviation, 4),
            "severity": self.severity,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
        }


@dataclass
class DecisionRecord:
    outcome: str
    agent_id: str
    rule_ids: list[str]
    severity: str
    timestamp: datetime


class GovernanceAnomalyDetector:
    """Detects statistical anomalies in governance decision patterns.

    Maintains a sliding window of decisions and compares current-window
    statistics against historical baselines using z-score deviation.
    """

    __slots__ = (
        "_window_size",
        "_z_threshold",
        "_records",
        "_anomalies",
        "_baseline_deny_rate",
        "_baseline_samples",
        "_rule_fire_counts",
        "_agent_deny_counts",
    )

    def __init__(
        self,
        window_size: int = 100,
        z_threshold: float = 2.5,
    ) -> None:
        self._window_size = window_size
        self._z_threshold = z_threshold
        self._records: deque[DecisionRecord] = deque(maxlen=window_size * 10)
        self._anomalies: list[AnomalySignal] = []
        self._baseline_deny_rate: float = 0.0
        self._baseline_samples: int = 0
        self._rule_fire_counts: dict[str, int] = {}
        self._agent_deny_counts: dict[str, int] = {}

    def record_decision(
        self,
        outcome: str,
        agent_id: str,
        rule_ids: list[str] | None = None,
        severity: str = "low",
    ) -> list[AnomalySignal]:
        record = DecisionRecord(
            outcome=outcome,
            agent_id=agent_id,
            rule_ids=rule_ids or [],
            severity=severity,
            timestamp=datetime.now(timezone.utc),
        )
        self._records.append(record)

        for rid in record.rule_ids:
            self._rule_fire_counts[rid] = self._rule_fire_counts.get(rid, 0) + 1

        if outcome == "deny":
            self._agent_deny_counts[agent_id] = self._agent_deny_counts.get(agent_id, 0) + 1

        self._baseline_samples += 1
        if outcome == "deny":
            self._baseline_deny_rate = (
                self._baseline_deny_rate * (self._baseline_samples - 1) + 1.0
            ) / self._baseline_samples
        else:
            self._baseline_deny_rate = (
                self._baseline_deny_rate * (self._baseline_samples - 1)
            ) / self._baseline_samples

        if len(self._records) >= self._window_size:
            return self._check_anomalies()
        return []

    def _check_anomalies(self) -> list[AnomalySignal]:
        signals: list[AnomalySignal] = []
        now = datetime.now(timezone.utc)

        window = list(self._records)[-self._window_size :]
        window_denials = sum(1 for r in window if r.outcome == "deny")
        window_deny_rate = window_denials / len(window)

        deny_signal = self._check_rate_deviation(
            "deny_rate", self._baseline_deny_rate, window_deny_rate, now
        )
        if deny_signal:
            signals.append(deny_signal)

        severity_counts: dict[str, int] = {}
        for r in window:
            if r.outcome == "deny":
                severity_counts[r.severity] = severity_counts.get(r.severity, 0) + 1

        critical_count = severity_counts.get("critical", 0)
        if critical_count > 0:
            critical_rate = critical_count / len(window)
            if critical_rate > 0.1:
                signals.append(
                    AnomalySignal(
                        anomaly_type="critical_spike",
                        metric="critical_denial_rate",
                        expected_value=0.0,
                        observed_value=critical_rate,
                        deviation=critical_rate * 10,
                        severity="high",
                        timestamp=now,
                        details={"critical_denials_in_window": critical_count},
                    )
                )

        window_agents: dict[str, int] = {}
        for r in window:
            if r.outcome == "deny":
                window_agents[r.agent_id] = window_agents.get(r.agent_id, 0) + 1

        if window_denials > 0:
            for agent_id, count in window_agents.items():
                concentration = count / window_denials
                if concentration > 0.8 and window_denials >= 5:
                    signals.append(
                        AnomalySignal(
                            anomaly_type="agent_concentration",
                            metric="denial_concentration",
                            expected_value=0.5,
                            observed_value=concentration,
                            deviation=concentration - 0.5,
                            severity="medium",
                            timestamp=now,
                            details={
                                "agent_id": agent_id,
                                "denials": count,
                                "total": window_denials,
                            },
                        )
                    )

        self._anomalies.extend(signals)
        return signals

    def _check_rate_deviation(
        self,
        metric: str,
        baseline: float,
        observed: float,
        timestamp: datetime,
    ) -> AnomalySignal | None:
        if self._baseline_samples < self._window_size:
            return None

        std_dev = math.sqrt(baseline * (1 - baseline) / self._window_size) if baseline > 0 else 0.1
        if std_dev < 0.001:
            std_dev = 0.001

        z_score = abs(observed - baseline) / std_dev
        if z_score > self._z_threshold:
            if z_score > self._z_threshold * 2:
                severity = "critical"
            elif z_score > self._z_threshold * 1.5:
                severity = "high"
            else:
                severity = "medium"

            return AnomalySignal(
                anomaly_type="rate_deviation",
                metric=metric,
                expected_value=baseline,
                observed_value=observed,
                deviation=z_score,
                severity=severity,
                timestamp=timestamp,
                details={"z_score": round(z_score, 2), "window_size": self._window_size},
            )
        return None

    def recent_anomalies(self, limit: int = 20) -> list[AnomalySignal]:
        return self._anomalies[-limit:]

    def anomaly_count_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for a in self._anomalies:
            counts[a.anomaly_type] = counts.get(a.anomaly_type, 0) + 1
        return counts

    def rule_fire_ranking(self, top_n: int = 10) -> list[tuple[str, int]]:
        sorted_rules = sorted(self._rule_fire_counts.items(), key=lambda x: x[1], reverse=True)
        return sorted_rules[:top_n]

    def agent_denial_ranking(self, top_n: int = 10) -> list[tuple[str, int]]:
        sorted_agents = sorted(self._agent_deny_counts.items(), key=lambda x: x[1], reverse=True)
        return sorted_agents[:top_n]

    def stats(self) -> dict[str, Any]:
        return {
            "total_decisions": len(self._records),
            "baseline_deny_rate": round(self._baseline_deny_rate, 4),
            "baseline_samples": self._baseline_samples,
            "total_anomalies": len(self._anomalies),
            "anomalies_by_type": self.anomaly_count_by_type(),
            "unique_rules_fired": len(self._rule_fire_counts),
            "unique_agents_denied": len(self._agent_deny_counts),
        }

    def reset(self) -> None:
        self._records.clear()
        self._anomalies.clear()
        self._baseline_deny_rate = 0.0
        self._baseline_samples = 0
        self._rule_fire_counts.clear()
        self._agent_deny_counts.clear()
