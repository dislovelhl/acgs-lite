"""Tests for governance halt notifications."""

from __future__ import annotations

import json
import logging

from acgs_lite.circuit_breaker import (
    GovernanceCircuitBreaker,
    HaltEvent,
    StructuredLogNotificationChannel,
)


class _RecordingChannel:
    def __init__(self) -> None:
        self.events: list[HaltEvent] = []

    def notify(self, event: HaltEvent) -> None:
        self.events.append(event)


class _ExplodingChannel:
    def notify(self, event: HaltEvent) -> None:
        raise RuntimeError(f"boom:{event.system_id}")


def test_breaker_trip_notifies_channels(tmp_path) -> None:
    channel = _RecordingChannel()
    breaker = GovernanceCircuitBreaker(
        system_id="system-1",
        signal_dir=tmp_path,
        notification_channels=[channel],
    )

    breaker.trip(reason="manual review")

    assert len(channel.events) == 1
    assert channel.events[0].system_id == "system-1"
    assert channel.events[0].reason == "manual review"


def test_breaker_trip_swallows_notification_exceptions(tmp_path) -> None:
    breaker = GovernanceCircuitBreaker(
        system_id="system-2",
        signal_dir=tmp_path,
        notification_channels=[_ExplodingChannel()],
    )

    breaker.trip(reason="fail closed")

    assert breaker.is_tripped is True


def test_structured_log_notification_channel_emits_critical_log(caplog) -> None:
    channel = StructuredLogNotificationChannel()
    event = HaltEvent(
        system_id="system-3",
        reason="critical issue",
        timestamp="2026-04-07T12:00:00+00:00",
        signal_path="/tmp/acgs-halt-system-3",
    )

    with caplog.at_level(logging.CRITICAL, logger="acgs.halt"):
        channel.notify(event)

    assert any(
        record.levelno == logging.CRITICAL
        and json.loads(record.getMessage())["system_id"] == "system-3"
        for record in caplog.records
    )
