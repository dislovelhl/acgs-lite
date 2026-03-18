"""
ACGS-2 Enhanced Agent Bus - SIEM Integration
Constitutional Hash: cdd01ef066bc6cf2

Lightweight SIEM formatting, alerting, and buffering support.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum, IntEnum
from functools import wraps
from typing import Any, Callable

try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .runtime_security import SecurityEvent, SecurityEventType, SecuritySeverity

try:
    from .rust.fast_hash import fast_hash

    FAST_HASH_AVAILABLE = True
except ImportError:  # pragma: no cover - optional acceleration
    fast_hash = None
    FAST_HASH_AVAILABLE = False


class SIEMFormat(str, Enum):
    JSON = "json"
    CEF = "cef"
    LEEF = "leef"
    SYSLOG = "syslog"


class AlertLevel(IntEnum):
    NOTIFY = 1
    PAGE = 2
    ESCALATE = 3
    CRITICAL = 4


@dataclass(frozen=True)
class AlertThreshold:
    event_type: SecurityEventType
    count_threshold: int
    time_window_seconds: int
    alert_level: AlertLevel
    cooldown_seconds: int = 300
    escalation_multiplier: int = 2


DEFAULT_ALERT_THRESHOLDS = [
    AlertThreshold(
        event_type=SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH,
        count_threshold=1,
        time_window_seconds=60,
        alert_level=AlertLevel.CRITICAL,
        cooldown_seconds=0,
    ),
    AlertThreshold(
        event_type=SecurityEventType.PROMPT_INJECTION_ATTEMPT,
        count_threshold=3,
        time_window_seconds=60,
        alert_level=AlertLevel.PAGE,
    ),
    AlertThreshold(
        event_type=SecurityEventType.AUTHENTICATION_FAILURE,
        count_threshold=5,
        time_window_seconds=60,
        alert_level=AlertLevel.NOTIFY,
    ),
]


@dataclass
class SIEMConfig:
    format: SIEMFormat = SIEMFormat.JSON
    endpoint_url: str | None = None
    enable_alerting: bool = True
    include_constitutional_hash: bool = True
    max_queue_size: int = 1000
    drop_on_overflow: bool = True
    flush_interval_seconds: float = 1.0
    correlation_window_seconds: int = 60
    alert_callback: Callable[[AlertLevel, str, JSONDict], Any] | None = None


class SIEMEventFormatter:
    def __init__(self, format_type: SIEMFormat = SIEMFormat.JSON) -> None:
        self.format_type = format_type

    def format(self, event: SecurityEvent, correlation_id: str | None = None) -> str:
        if self.format_type == SIEMFormat.JSON:
            return self._format_json(event, correlation_id)
        if self.format_type == SIEMFormat.CEF:
            return self._format_cef(event, correlation_id)
        if self.format_type == SIEMFormat.LEEF:
            return self._format_leef(event, correlation_id)
        return self._format_syslog(event, correlation_id)

    def _format_json(self, event: SecurityEvent, correlation_id: str | None) -> str:
        payload = event.to_dict()
        if correlation_id is not None:
            payload["correlation_id"] = correlation_id
        payload["_siem"] = {"vendor": "ACGS-2", "product": "EnhancedAgentBus", "version": "2.4.0"}
        return json.dumps(payload, default=str)

    def _format_cef(self, event: SecurityEvent, correlation_id: str | None) -> str:
        ext = {
            "msg": self._escape(event.message),
            "TenantID": event.tenant_id or "",
            "AgentID": event.agent_id or "",
            "ConstitutionalHash": event.constitutional_hash,
        }
        if correlation_id is not None:
            ext["CorrelationID"] = correlation_id
        extension = " ".join(f"{key}={value}" for key, value in ext.items())
        return (
            f"CEF:0|ACGS-2|EnhancedAgentBus|2.4.0|{event.event_type.value}|"
            f"{event.event_type.value}|{self._cef_severity(event.severity)}|{extension}"
        )

    def _format_leef(self, event: SecurityEvent, correlation_id: str | None) -> str:
        values = {
            "eventType": event.event_type.value,
            "severity": event.severity.value,
            "message": self._escape(event.message),
            "tenantId": event.tenant_id or "",
            "agentId": event.agent_id or "",
            "constitutionalHash": event.constitutional_hash,
        }
        if correlation_id is not None:
            values["correlationId"] = correlation_id
        body = "\t".join(f"{key}={value}" for key, value in values.items())
        return f"LEEF:2.0|ACGS-2|EnhancedAgentBus|2.4.0|{body}"

    def _format_syslog(self, event: SecurityEvent, correlation_id: str | None) -> str:
        structured = [
            '[acgs2@12345',
            f'event_type="{event.event_type.value}"',
            f'severity="{event.severity.value}"',
            f'constitutional_hash="{event.constitutional_hash}"',
        ]
        if correlation_id is not None:
            structured.append(f'correlation_id="{correlation_id}"')
        structured.append("]")
        ts = event.timestamp.astimezone(UTC).isoformat()
        return f"<134>1 {ts} EnhancedAgentBus - - - {' '.join(structured)} {event.message}"

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace("|", "\\|").replace("=", "\\=")

    @staticmethod
    def _cef_severity(severity: SecuritySeverity) -> int:
        mapping = {
            SecuritySeverity.INFO: 1,
            SecuritySeverity.LOW: 3,
            SecuritySeverity.MEDIUM: 5,
            SecuritySeverity.HIGH: 8,
            SecuritySeverity.CRITICAL: 10,
        }
        return mapping[severity]


class AlertManager:
    def __init__(
        self,
        thresholds: list[AlertThreshold] | None = None,
        callback: Callable[[AlertLevel, str, JSONDict], Any] | None = None,
    ) -> None:
        self.thresholds = thresholds or list(DEFAULT_ALERT_THRESHOLDS)
        self.callback = callback
        self._events: dict[SecurityEventType, deque[datetime]] = defaultdict(deque)
        self._last_alert_at: dict[SecurityEventType, datetime] = {}
        self._states: dict[str, JSONDict] = {}

    async def process_event(self, event: SecurityEvent) -> AlertLevel | None:
        threshold = self._find_threshold(event.event_type)
        if threshold is None and event.severity == SecuritySeverity.CRITICAL:
            threshold = AlertThreshold(event.event_type, 1, 60, AlertLevel.CRITICAL, cooldown_seconds=0)
        if threshold is None:
            return None

        now = event.timestamp.astimezone(UTC)
        events = self._events[event.event_type]
        events.append(now)
        cutoff = now.timestamp() - threshold.time_window_seconds
        while events and events[0].timestamp() < cutoff:
            events.popleft()

        count = len(events)
        last_alert = self._last_alert_at.get(event.event_type)
        if last_alert is not None and threshold.cooldown_seconds > 0:
            if (now - last_alert).total_seconds() < threshold.cooldown_seconds:
                self._record_state(event.event_type, count, None)
                return None

        if count < threshold.count_threshold:
            self._record_state(event.event_type, count, None)
            return None

        level = self._escalate_level(threshold, count)
        self._last_alert_at[event.event_type] = now
        context: JSONDict = {
            "event_type": event.event_type.value,
            "severity": event.severity.value,
            "constitutional_hash": event.constitutional_hash,
            "tenant_id": event.tenant_id,
            "agent_id": event.agent_id,
            "metadata": event.metadata,
            "event_count": count,
        }
        self._record_state(event.event_type, count, level)
        await self._invoke_callback(level, event.message, context)
        return level

    def get_alert_states(self) -> dict[str, JSONDict]:
        return {key: dict(value) for key, value in self._states.items()}

    def reset_alert_state(self, event_type: SecurityEventType) -> None:
        self._events[event_type].clear()
        self._last_alert_at.pop(event_type, None)
        self._states[event_type.value] = {"event_count": 0, "current_level": None}

    def _find_threshold(self, event_type: SecurityEventType) -> AlertThreshold | None:
        for threshold in self.thresholds:
            if threshold.event_type == event_type:
                return threshold
        return None

    def _escalate_level(self, threshold: AlertThreshold, count: int) -> AlertLevel:
        level = threshold.alert_level
        if threshold.escalation_multiplier <= 1:
            return level
        steps = max(0, count // threshold.count_threshold - 1)
        return AlertLevel(min(AlertLevel.CRITICAL.value, level.value + steps))

    async def _invoke_callback(self, level: AlertLevel, message: str, context: JSONDict) -> None:
        if self.callback is None:
            return
        result = self.callback(level, message, context)
        if inspect.isawaitable(result):
            await result

    def _record_state(
        self, event_type: SecurityEventType, count: int, level: AlertLevel | None
    ) -> None:
        self._states[event_type.value] = {
            "event_count": count,
            "current_level": level.name if level is not None else None,
        }


class EventCorrelator:
    def __init__(self, window_seconds: int = 60) -> None:
        self.window_seconds = window_seconds
        self._events: list[SecurityEvent] = []
        self._correlations: dict[str, list[SecurityEvent]] = {}

    async def add_event(self, event: SecurityEvent) -> str | None:
        self._events.append(event)
        now = event.timestamp.astimezone(UTC)
        self._events = [
            item
            for item in self._events
            if (now - item.timestamp.astimezone(UTC)).total_seconds() <= self.window_seconds
        ]

        same_tenant = [
            item
            for item in self._events
            if item.tenant_id and item.tenant_id == event.tenant_id and item.severity in {SecuritySeverity.HIGH, SecuritySeverity.CRITICAL}
        ]
        if event.tenant_id and len(same_tenant) >= 3:
            correlation_id = self._generate_correlation_id("tenant_attack", event.tenant_id)
            self._correlations[correlation_id] = same_tenant
            return correlation_id

        matching_type = [item for item in self._events if item.event_type == event.event_type]
        unique_agents = {item.agent_id for item in matching_type if item.agent_id}
        if len(unique_agents) >= 3:
            correlation_id = self._generate_correlation_id("distributed_attack", event.event_type.value)
            self._correlations[correlation_id] = matching_type
            return correlation_id

        return None

    def get_correlated_events(self, correlation_id: str) -> list[SecurityEvent]:
        return list(self._correlations.get(correlation_id, []))

    def _generate_correlation_id(self, pattern: str, discriminator: str) -> str:
        value = f"{pattern}:{discriminator}"
        if FAST_HASH_AVAILABLE and fast_hash is not None:
            return f"{fast_hash(value):016x}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


class SIEMIntegration:
    def __init__(self, config: SIEMConfig | None = None) -> None:
        self.config = config or SIEMConfig()
        self.formatter = SIEMEventFormatter(self.config.format)
        self.alert_manager = AlertManager(callback=self.config.alert_callback)
        self.correlator = EventCorrelator(window_seconds=self.config.correlation_window_seconds)
        self._queue: asyncio.Queue[tuple[SecurityEvent, str | None]] = asyncio.Queue(
            maxsize=self.config.max_queue_size
        )
        self._running = False
        self._worker: asyncio.Task[None] | None = None
        self._metrics: dict[str, int | bool] = {
            "events_logged": 0,
            "events_dropped": 0,
            "events_shipped": 0,
            "alerts_triggered": 0,
            "correlations_detected": 0,
            "running": False,
        }

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._metrics["running"] = True
        self._worker = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._metrics["running"] = False
        if self._worker is not None:
            await self._queue.join()
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    async def log_event(self, event: SecurityEvent) -> None:
        correlation_id = await self.correlator.add_event(event)
        if correlation_id is not None:
            self._metrics["correlations_detected"] += 1

        if self.config.enable_alerting:
            level = await self.alert_manager.process_event(event)
            if level is not None:
                self._metrics["alerts_triggered"] += 1

        try:
            self._queue.put_nowait((event, correlation_id))
            self._metrics["events_logged"] += 1
        except asyncio.QueueFull:
            if self.config.drop_on_overflow:
                self._metrics["events_dropped"] += 1
                return
            await self._queue.put((event, correlation_id))
            self._metrics["events_logged"] += 1

    def get_metrics(self) -> dict[str, int | bool]:
        return {
            **self._metrics,
            "queue_size": self._queue.qsize(),
        }

    def get_alert_states(self) -> dict[str, JSONDict]:
        return self.alert_manager.get_alert_states()

    async def _flush_loop(self) -> None:
        try:
            while True:
                try:
                    event, correlation_id = await asyncio.wait_for(
                        self._queue.get(), timeout=self.config.flush_interval_seconds
                    )
                except asyncio.TimeoutError:
                    if not self._running and self._queue.empty():
                        return
                    continue
                _payload = self.formatter.format(event, correlation_id)
                self._metrics["events_shipped"] += 1
                self._queue.task_done()
        except asyncio.CancelledError:
            raise


_GLOBAL_SIEM: SIEMIntegration | None = None


async def initialize_siem(config: SIEMConfig | None = None) -> SIEMIntegration:
    global _GLOBAL_SIEM
    if _GLOBAL_SIEM is None:
        _GLOBAL_SIEM = SIEMIntegration(config or SIEMConfig())
        await _GLOBAL_SIEM.start()
    return _GLOBAL_SIEM


def get_siem_integration() -> SIEMIntegration | None:
    return _GLOBAL_SIEM


async def close_siem() -> None:
    global _GLOBAL_SIEM
    if _GLOBAL_SIEM is not None:
        await _GLOBAL_SIEM.stop()
        _GLOBAL_SIEM = None


async def log_security_event(
    event_type: SecurityEventType,
    severity: SecuritySeverity,
    message: str,
    tenant_id: str | None = None,
    agent_id: str | None = None,
    metadata: JSONDict | None = None,
) -> None:
    siem = get_siem_integration()
    if siem is None:
        return
    await siem.log_event(
        SecurityEvent(
            event_type=event_type,
            severity=severity,
            message=message,
            tenant_id=tenant_id,
            agent_id=agent_id,
            metadata=metadata or {},
        )
    )


def security_audit(
    event_type: SecurityEventType,
    severity: SecuritySeverity,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                result = await func(*args, **kwargs)
                await log_security_event(
                    event_type=event_type,
                    severity=severity,
                    message=f"{func.__name__} succeeded",
                )
                return result
            except Exception as exc:
                await log_security_event(
                    event_type=event_type,
                    severity=SecuritySeverity.HIGH,
                    message=f"{func.__name__} failed: {exc}",
                )
                raise RuntimeError(f"{func.__name__} failed: {exc}") from exc

        return wrapper

    return decorator


__all__ = [
    "DEFAULT_ALERT_THRESHOLDS",
    "AlertLevel",
    "AlertManager",
    "AlertThreshold",
    "EventCorrelator",
    "FAST_HASH_AVAILABLE",
    "SIEMConfig",
    "SIEMEventFormatter",
    "SIEMFormat",
    "SIEMIntegration",
    "close_siem",
    "fast_hash",
    "get_siem_integration",
    "initialize_siem",
    "log_security_event",
    "security_audit",
]
