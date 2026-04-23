"""Tests for governance halt notifications."""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

from acgs_lite.circuit_breaker import (
    GovernanceCircuitBreaker,
    HaltEvent,
    StructuredLogNotificationChannel,
    WebhookNotificationChannel,
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


def test_webhook_channel_rejects_non_http_scheme() -> None:
    channel = WebhookNotificationChannel(url="file:///etc/passwd")
    event = HaltEvent(
        system_id="system-4",
        reason="test",
        timestamp="2026-04-07T12:00:00+00:00",
        signal_path="/tmp/acgs-halt-system-4",
    )
    # Should swallow the ValueError and log a warning (not propagate)
    channel.notify(event)  # must not raise


def test_webhook_channel_posts_to_https_url() -> None:
    channel = WebhookNotificationChannel(url="https://hooks.example.com/event")
    event = HaltEvent(
        system_id="system-5",
        reason="test",
        timestamp="2026-04-07T12:00:00+00:00",
        signal_path="/tmp/acgs-halt-system-5",
    )
    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        channel.notify(event)
    mock_open.assert_called_once()
