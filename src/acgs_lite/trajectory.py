"""Runtime trajectory monitoring for cross-request governance checks.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, cast, runtime_checkable


def _coerce_timestamp(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo is not None else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str) and raw:
        normalized = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _decision_metadata(decision: dict[str, Any]) -> dict[str, Any]:
    metadata = decision.get("metadata", {})
    if isinstance(metadata, dict):
        return cast(dict[str, Any], metadata)
    return {}


@dataclass(slots=True)
class TrajectoryViolation:
    rule_id: str
    evidence: str
    severity: str
    agent_id: str
    timestamp: str


@runtime_checkable
class TrajectoryRule(Protocol):
    def check(self, decisions: Sequence[dict[str, Any]]) -> TrajectoryViolation | None: ...


@dataclass(slots=True)
class TrajectorySession:
    session_id: str
    agent_id: str
    decisions: list[dict[str, Any]] = field(default_factory=list)

    def add(self, decision: dict[str, Any]) -> None:
        self.decisions.append(dict(decision))


@dataclass(slots=True)
class FrequencyThresholdRule:
    max_count: int
    window_seconds: int
    severity: str = "high"

    def check(self, decisions: Sequence[dict[str, Any]]) -> TrajectoryViolation | None:
        grouped: dict[str, list[tuple[datetime, dict[str, Any]]]] = {}
        for decision in decisions:
            action_type = str(decision.get("action_type", "")).strip()
            if not action_type:
                continue
            grouped.setdefault(action_type, []).append(
                (_coerce_timestamp(decision.get("timestamp")), decision)
            )

        for action_type, pairs in grouped.items():
            ordered = sorted(pairs, key=lambda p: p[0])
            left = 0
            for right, (current, decision) in enumerate(ordered):
                window_start = current - timedelta(seconds=self.window_seconds)
                while left <= right and ordered[left][0] < window_start:
                    left += 1
                count = right - left + 1
                if count > self.max_count:
                    return TrajectoryViolation(
                        rule_id="TRAJ-FREQ-001",
                        evidence=(
                            f"Action type {action_type!r} occurred {count} times within "
                            f"{self.window_seconds} seconds"
                        ),
                        severity=self.severity,
                        agent_id=str(decision.get("agent_id", "")),
                        timestamp=current.isoformat(),
                    )
        return None


@dataclass(slots=True)
class CumulativeValueRule:
    threshold: float
    severity: str = "high"

    def check(self, decisions: Sequence[dict[str, Any]]) -> TrajectoryViolation | None:
        total = 0.0
        last_timestamp = datetime.now(timezone.utc).isoformat()
        agent_id = ""
        for decision in decisions:
            metadata = _decision_metadata(decision)
            amount = metadata.get("amount")
            if isinstance(amount, (int, float)):
                total += float(amount)
                agent_id = str(decision.get("agent_id", agent_id))
                last_timestamp = _coerce_timestamp(decision.get("timestamp")).isoformat()

        if total > self.threshold:
            return TrajectoryViolation(
                rule_id="TRAJ-CUMVAL-001",
                evidence=f"Cumulative decision amount {total:.2f} exceeded threshold {self.threshold:.2f}",
                severity=self.severity,
                agent_id=agent_id,
                timestamp=last_timestamp,
            )
        return None


@dataclass(slots=True)
class SensitiveToolSequenceRule:
    sensitive_tools: set[str]
    precursor_flags: tuple[str, ...] = (
        "prompt_injection_suspected",
        "indirect_prompt_injection",
        "untrusted_input",
    )
    lookback: int = 3
    severity: str = "critical"

    def check(self, decisions: Sequence[dict[str, Any]]) -> TrajectoryViolation | None:
        recent_precursors: list[tuple[int, str]] = []
        normalized_sensitive_tools = {tool.lower() for tool in self.sensitive_tools}

        for index, decision in enumerate(decisions):
            metadata = _decision_metadata(decision)
            tool_name = str(metadata.get("tool_name", "")).strip().lower()
            precursor_match = next(
                (flag for flag in self.precursor_flags if bool(metadata.get(flag))),
                None,
            )
            if precursor_match is not None:
                recent_precursors.append((index, precursor_match))
                continue

            if not tool_name or tool_name not in normalized_sensitive_tools:
                continue

            window_precursors = [
                (precursor_index, flag)
                for precursor_index, flag in recent_precursors
                if index - precursor_index <= self.lookback
            ]
            if not window_precursors:
                continue

            _, matched_flag = window_precursors[-1]
            return TrajectoryViolation(
                rule_id="TRAJ-TOOLSEQ-001",
                evidence=(
                    f"Sensitive tool '{tool_name}' invoked after precursor flag '{matched_flag}' "
                    f"within {self.lookback} checkpoint(s)"
                ),
                severity=self.severity,
                agent_id=str(decision.get("agent_id", "")),
                timestamp=_coerce_timestamp(decision.get("timestamp")).isoformat(),
            )
        return None


@runtime_checkable
class TrajectoryStoreBackend(Protocol):
    def get(self, session_id: str) -> TrajectorySession | None: ...

    def put(self, session: TrajectorySession) -> None: ...


class InMemoryTrajectoryStore:
    def __init__(self) -> None:
        self._sessions: dict[str, TrajectorySession] = {}

    def get(self, session_id: str) -> TrajectorySession | None:
        return self._sessions.get(session_id)

    def put(self, session: TrajectorySession) -> None:
        self._sessions[session.session_id] = session


class TrajectoryMonitor:
    def __init__(self, rules: list[TrajectoryRule], store: TrajectoryStoreBackend) -> None:
        self._rules = list(rules)
        self._store = store
        self._lock = threading.Lock()

    def check_trajectory(self, session: TrajectorySession) -> list[TrajectoryViolation]:
        self._store.put(session)
        decisions = tuple(session.decisions)
        violations: list[TrajectoryViolation] = []
        for rule in self._rules:
            violation = rule.check(decisions)
            if violation is not None:
                violations.append(violation)
        return violations

    def check_checkpoint(
        self,
        *,
        session_id: str,
        agent_id: str,
        decision: dict[str, Any],
    ) -> list[TrajectoryViolation]:
        with self._lock:
            session = self._store.get(session_id)
            if session is None:
                session = TrajectorySession(session_id=session_id, agent_id=agent_id)
            session.add(decision)
            return self.check_trajectory(session)
