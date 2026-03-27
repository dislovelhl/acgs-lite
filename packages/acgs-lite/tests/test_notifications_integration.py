"""Tests for the notifications integration adapter.

Covers: SlackNotifier, TeamsNotifier, WebhookNotifier, NotificationRouter,
GovernanceNotifier, severity filtering, error resilience, and stats tracking.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from acgs_lite.integrations.notifications import (
    _SEVERITY_COLORS,
    HTTPX_AVAILABLE,
    GovernanceEvent,
    GovernanceNotifier,
    NotificationChannel,
    NotificationRouter,
    SlackNotifier,
    TeamsNotifier,
    WebhookNotifier,
    _severity_passes_filter,
    _truncate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    *,
    severity: str = "HIGH",
    event_type: str = "violation",
    agent_id: str = "test-agent",
    action: str = "deploy production without review",
    rule_id: str = "R-001",
) -> GovernanceEvent:
    return GovernanceEvent(
        event_type=event_type,
        severity=severity,
        agent_id=agent_id,
        action=action,
        violations=[{"rule_id": rule_id, "rule_text": "Must have review", "severity": severity}],
        constitutional_hash="608508a9bd224290",
        timestamp="2026-03-27T12:00:00+00:00",
    )


class _FakeChannel:
    """In-memory notification channel for testing."""

    def __init__(
        self,
        name: str = "fake",
        *,
        should_fail: bool = False,
        severity_filter: str = "LOW",
    ) -> None:
        self._name = name
        self._should_fail = should_fail
        self._severity_filter = severity_filter
        self.sent_events: list[GovernanceEvent] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def severity_filter(self) -> str:
        return self._severity_filter

    async def send(self, event: GovernanceEvent) -> bool:
        if self._should_fail:
            raise ConnectionError("webhook unreachable")
        if not _severity_passes_filter(event.severity, self._severity_filter):
            return False
        self.sent_events.append(event)
        return True


# ---------------------------------------------------------------------------
# GovernanceEvent
# ---------------------------------------------------------------------------


class TestGovernanceEvent:
    def test_to_dict_round_trip(self) -> None:
        event = _make_event()
        d = event.to_dict()
        assert d["event_type"] == "violation"
        assert d["severity"] == "HIGH"
        assert d["agent_id"] == "test-agent"
        assert d["constitutional_hash"] == "608508a9bd224290"
        assert len(d["violations"]) == 1

    def test_default_timestamp_is_iso8601(self) -> None:
        event = GovernanceEvent(
            event_type="violation",
            severity="LOW",
            agent_id="a",
            action="b",
        )
        # Should contain 'T' separator and timezone info
        assert "T" in event.timestamp

    def test_frozen_dataclass(self) -> None:
        event = _make_event()
        with pytest.raises(AttributeError):
            event.severity = "LOW"  # type: ignore[misc]

    def test_metadata_field(self) -> None:
        event = GovernanceEvent(
            event_type="violation",
            severity="HIGH",
            agent_id="a",
            action="b",
            metadata={"key": "value"},
        )
        d = event.to_dict()
        assert d["metadata"] == {"key": "value"}

    def test_default_constitutional_hash(self) -> None:
        event = GovernanceEvent(
            event_type="test",
            severity="LOW",
            agent_id="a",
            action="b",
        )
        assert event.constitutional_hash == "608508a9bd224290"

    def test_custom_constitutional_hash(self) -> None:
        event = GovernanceEvent(
            event_type="test",
            severity="LOW",
            agent_id="a",
            action="b",
            constitutional_hash="custom_hash",
        )
        assert event.constitutional_hash == "custom_hash"


# ---------------------------------------------------------------------------
# Severity filtering
# ---------------------------------------------------------------------------


class TestSeverityFilter:
    @pytest.mark.parametrize(
        ("event_sev", "min_sev", "expected"),
        [
            ("CRITICAL", "LOW", True),
            ("HIGH", "LOW", True),
            ("MEDIUM", "LOW", True),
            ("LOW", "LOW", True),
            ("MEDIUM", "HIGH", False),
            ("LOW", "CRITICAL", False),
            ("HIGH", "HIGH", True),
            ("CRITICAL", "CRITICAL", True),
        ],
    )
    def test_severity_passes_filter(
        self, event_sev: str, min_sev: str, expected: bool
    ) -> None:
        assert _severity_passes_filter(event_sev, min_sev) is expected

    def test_case_insensitive(self) -> None:
        assert _severity_passes_filter("critical", "high") is True
        assert _severity_passes_filter("low", "HIGH") is False

    def test_unknown_severity(self) -> None:
        # Unknown severities get 0, so they should pass LOW filter
        assert _severity_passes_filter("UNKNOWN", "LOW") is True


# ---------------------------------------------------------------------------
# Truncation helper
# ---------------------------------------------------------------------------


class TestTruncate:
    def test_short_string_unchanged(self) -> None:
        assert _truncate("hello", 200) == "hello"

    def test_long_string_truncated(self) -> None:
        long = "x" * 300
        result = _truncate(long, 200)
        assert len(result) == 200
        assert result.endswith("...")

    def test_exact_boundary(self) -> None:
        exact = "x" * 200
        assert _truncate(exact, 200) == exact

    def test_default_max_len(self) -> None:
        long = "x" * 250
        result = _truncate(long)
        assert len(result) == 200


# ---------------------------------------------------------------------------
# SlackNotifier
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")
class TestSlackNotifier:
    def test_payload_structure(self) -> None:
        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        event = _make_event()
        payload = notifier._build_payload(event)

        assert "attachments" in payload
        attachment = payload["attachments"][0]
        assert attachment["color"] == _SEVERITY_COLORS["HIGH"]
        blocks = attachment["blocks"]

        # Header block
        assert blocks[0]["type"] == "header"
        assert "Constitutional Violation" in blocks[0]["text"]["text"]

        # Section with fields
        fields = blocks[1]["fields"]
        field_texts = [f["text"] for f in fields]
        assert any("test-agent" in t for t in field_texts)
        assert any("HIGH" in t for t in field_texts)
        assert any("R-001" in t for t in field_texts)

        # Context footer
        assert "608508a9bd224290" in blocks[2]["elements"][0]["text"]

    def test_channel_override(self) -> None:
        notifier = SlackNotifier(
            webhook_url="https://hooks.slack.com/test",
            channel="#alerts",
        )
        payload = notifier._build_payload(_make_event())
        assert payload["channel"] == "#alerts"

    def test_action_truncation_in_payload(self) -> None:
        long_action = "a" * 500
        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        event = _make_event(action=long_action)
        payload = notifier._build_payload(event)
        fields = payload["attachments"][0]["blocks"][1]["fields"]
        action_field = next(f for f in fields if "Action" in f["text"])
        # The visible text should be truncated
        assert len(action_field["text"]) < 500

    @pytest.mark.asyncio
    async def test_send_posts_to_webhook(self) -> None:
        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        event = _make_event()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("acgs_lite.integrations.notifications.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            result = await notifier.send(event)

        assert result is True
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert call_kwargs[0][0] == "https://hooks.slack.com/test"

    @pytest.mark.asyncio
    async def test_severity_filter_skips_low_events(self) -> None:
        notifier = SlackNotifier(
            webhook_url="https://hooks.slack.com/test",
            severity_filter="HIGH",
        )
        low_event = _make_event(severity="MEDIUM")

        # Should return False without calling httpx at all
        with patch("acgs_lite.integrations.notifications.httpx") as mock_httpx:
            result = await notifier.send(low_event)

        assert result is False
        mock_httpx.AsyncClient.assert_not_called()

    def test_name_property(self) -> None:
        notifier = SlackNotifier(webhook_url="https://test")
        assert notifier.name == "slack"

    def test_severity_filter_property(self) -> None:
        notifier = SlackNotifier(
            webhook_url="https://test", severity_filter="critical"
        )
        assert notifier.severity_filter == "CRITICAL"

    @pytest.mark.asyncio
    async def test_send_returns_false_on_server_error(self) -> None:
        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        event = _make_event()

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("acgs_lite.integrations.notifications.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            result = await notifier.send(event)

        assert result is False


# ---------------------------------------------------------------------------
# TeamsNotifier
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")
class TestTeamsNotifier:
    def test_payload_is_adaptive_card(self) -> None:
        notifier = TeamsNotifier(webhook_url="https://outlook.office.com/webhook/test")
        event = _make_event(severity="CRITICAL")
        payload = notifier._build_payload(event)

        assert payload["type"] == "message"
        card_content = payload["attachments"][0]["content"]
        assert card_content["type"] == "AdaptiveCard"
        assert card_content["version"] == "1.4"

        # Check header
        header = card_content["body"][0]
        assert "Constitutional Violation" in header["text"]

        # Check facts
        facts = card_content["body"][1]["facts"]
        fact_titles = [f["title"] for f in facts]
        assert "Agent ID" in fact_titles
        assert "Severity" in fact_titles
        assert "Rule ID" in fact_titles

        # Check constitutional hash in footer
        footer = card_content["body"][3]
        assert "608508a9bd224290" in footer["text"]

    @pytest.mark.asyncio
    async def test_send_posts_to_teams_webhook(self) -> None:
        notifier = TeamsNotifier(webhook_url="https://outlook.office.com/webhook/test")
        event = _make_event()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("acgs_lite.integrations.notifications.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            result = await notifier.send(event)

        assert result is True

    def test_name_property(self) -> None:
        notifier = TeamsNotifier(webhook_url="https://test")
        assert notifier.name == "teams"

    def test_action_in_payload(self) -> None:
        notifier = TeamsNotifier(webhook_url="https://test")
        event = _make_event(action="do something dangerous")
        payload = notifier._build_payload(event)
        action_block = payload["attachments"][0]["content"]["body"][2]
        assert "do something dangerous" in action_block["text"]


# ---------------------------------------------------------------------------
# WebhookNotifier
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")
class TestWebhookNotifier:
    @pytest.mark.asyncio
    async def test_sends_json_body(self) -> None:
        notifier = WebhookNotifier(url="https://my-siem.example.com/events")
        event = _make_event()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("acgs_lite.integrations.notifications.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            result = await notifier.send(event)

        assert result is True
        call_kwargs = mock_client.post.call_args
        body = json.loads(call_kwargs.kwargs["content"])
        assert body["event_type"] == "violation"
        assert body["agent_id"] == "test-agent"

    @pytest.mark.asyncio
    async def test_custom_headers(self) -> None:
        notifier = WebhookNotifier(
            url="https://siem.example.com",
            headers={"Authorization": "Bearer tok123"},
        )
        event = _make_event()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("acgs_lite.integrations.notifications.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            await notifier.send(event)

        call_kwargs = mock_client.post.call_args
        assert "Bearer tok123" in call_kwargs.kwargs["headers"]["Authorization"]

    def test_name_property(self) -> None:
        notifier = WebhookNotifier(url="https://test")
        assert notifier.name == "webhook"

    @pytest.mark.asyncio
    async def test_severity_filter(self) -> None:
        notifier = WebhookNotifier(
            url="https://test", severity_filter="CRITICAL"
        )
        event = _make_event(severity="HIGH")
        with patch("acgs_lite.integrations.notifications.httpx"):
            result = await notifier.send(event)
        assert result is False

    def test_default_content_type_header(self) -> None:
        notifier = WebhookNotifier(url="https://test")
        assert notifier._headers["Content-Type"] == "application/json"


# ---------------------------------------------------------------------------
# NotificationRouter
# ---------------------------------------------------------------------------


class TestNotificationRouter:
    @pytest.mark.asyncio
    async def test_fans_out_to_all_channels(self) -> None:
        ch1 = _FakeChannel("ch1")
        ch2 = _FakeChannel("ch2")
        router = NotificationRouter([ch1, ch2])
        event = _make_event()

        await router.notify(event)

        assert len(ch1.sent_events) == 1
        assert len(ch2.sent_events) == 1
        assert router.stats["total_sent"] == 2
        assert router.stats["total_failed"] == 0

    @pytest.mark.asyncio
    async def test_one_failure_does_not_block_others(self) -> None:
        ch_ok = _FakeChannel("ok")
        ch_fail = _FakeChannel("fail", should_fail=True)
        router = NotificationRouter([ch_ok, ch_fail])
        event = _make_event()

        await router.notify(event)

        assert len(ch_ok.sent_events) == 1
        assert router.stats["total_sent"] == 1
        assert router.stats["total_failed"] == 1
        assert router.stats["per_channel"]["ok"]["sent"] == 1
        assert router.stats["per_channel"]["fail"]["failed"] == 1

    @pytest.mark.asyncio
    async def test_per_channel_severity_filtering(self) -> None:
        ch_all = _FakeChannel("all", severity_filter="LOW")
        ch_high = _FakeChannel("high_only", severity_filter="HIGH")
        router = NotificationRouter([ch_all, ch_high])

        medium_event = _make_event(severity="MEDIUM")
        await router.notify(medium_event)

        assert len(ch_all.sent_events) == 1
        assert len(ch_high.sent_events) == 0
        # The HIGH channel returned False (filtered), so it shouldn't count
        # as either sent or failed.
        assert router.stats["total_sent"] == 1
        assert router.stats["total_failed"] == 0

    @pytest.mark.asyncio
    async def test_stats_accumulate(self) -> None:
        ch = _FakeChannel("acc")
        router = NotificationRouter([ch])

        await router.notify(_make_event())
        await router.notify(_make_event())

        assert router.stats["total_sent"] == 2
        assert router.stats["per_channel"]["acc"]["sent"] == 2

    @pytest.mark.asyncio
    async def test_empty_channels(self) -> None:
        router = NotificationRouter([])
        await router.notify(_make_event())
        assert router.stats["total_sent"] == 0

    @pytest.mark.asyncio
    async def test_three_channels_mixed(self) -> None:
        ch1 = _FakeChannel("ok1")
        ch2 = _FakeChannel("ok2")
        ch3 = _FakeChannel("fail", should_fail=True)
        router = NotificationRouter([ch1, ch2, ch3])

        await router.notify(_make_event())

        assert router.stats["total_sent"] == 2
        assert router.stats["total_failed"] == 1


# ---------------------------------------------------------------------------
# GovernanceNotifier (wraps GovernanceEngine)
# ---------------------------------------------------------------------------


class TestGovernanceNotifier:
    def _make_mock_engine(
        self, *, valid: bool = True, strict: bool = False
    ) -> MagicMock:
        engine = MagicMock()
        engine._const_hash = "608508a9bd224290"

        if valid:
            result = MagicMock()
            result.valid = True
            result.violations = []
            result.blocking_violations = []
            result.warnings = []
            result.constitutional_hash = "608508a9bd224290"
            engine.validate.return_value = result
        else:
            result = MagicMock()
            result.valid = False
            # Create violation-like objects
            violation = MagicMock()
            violation.rule_id = "R-001"
            violation.rule_text = "Must have review"
            violation.severity = MagicMock()
            violation.severity.value = "high"
            violation.severity.blocks.return_value = True
            violation.matched_content = "deploy"
            violation.category = "safety"
            result.violations = [violation]
            result.blocking_violations = [violation]
            result.warnings = []
            result.constitutional_hash = "608508a9bd224290"

            if strict:
                from acgs_lite.errors import ConstitutionalViolationError

                engine.validate.side_effect = ConstitutionalViolationError(
                    "Blocked by R-001",
                    rule_id="R-001",
                    severity="critical",
                    action="deploy production",
                )
            else:
                engine.validate.return_value = result

        return engine

    @pytest.mark.asyncio
    async def test_valid_action_no_notifications(self) -> None:
        engine = self._make_mock_engine(valid=True)
        ch = _FakeChannel("test")
        router = NotificationRouter([ch])
        notifier = GovernanceNotifier(engine=engine, router=router)

        result = notifier.validate("safe action", agent_id="bot-1")

        assert result.valid is True
        assert len(ch.sent_events) == 0

    @pytest.mark.asyncio
    async def test_violation_fires_notification(self) -> None:
        engine = self._make_mock_engine(valid=False)
        ch = _FakeChannel("test")
        router = NotificationRouter([ch])
        notifier = GovernanceNotifier(engine=engine, router=router)

        result = notifier.validate("deploy production", agent_id="bot-2")

        assert result.valid is False
        assert len(ch.sent_events) == 1
        sent = ch.sent_events[0]
        assert sent.event_type == "violation"
        assert sent.agent_id == "bot-2"

    @pytest.mark.asyncio
    async def test_strict_mode_raises_after_notification(self) -> None:
        from acgs_lite.errors import ConstitutionalViolationError

        engine = self._make_mock_engine(valid=False, strict=True)
        ch = _FakeChannel("test")
        router = NotificationRouter([ch])
        notifier = GovernanceNotifier(engine=engine, router=router)

        with pytest.raises(ConstitutionalViolationError):
            notifier.validate("deploy production", agent_id="bot-3")

        # Notification should still have been sent before re-raising
        assert len(ch.sent_events) == 1

    @pytest.mark.asyncio
    async def test_notify_on_deny_disabled(self) -> None:
        engine = self._make_mock_engine(valid=False)
        ch = _FakeChannel("test")
        router = NotificationRouter([ch])
        notifier = GovernanceNotifier(
            engine=engine, router=router, notify_on_deny=False
        )

        notifier.validate("deploy production", agent_id="bot-4")

        assert len(ch.sent_events) == 0

    @pytest.mark.asyncio
    async def test_warning_notification_when_enabled(self) -> None:
        engine = MagicMock()
        engine._const_hash = "608508a9bd224290"

        warning_violation = MagicMock()
        warning_violation.rule_id = "R-002"
        warning_violation.rule_text = "Prefer review"
        warning_violation.severity = MagicMock()
        warning_violation.severity.value = "medium"
        warning_violation.severity.blocks.return_value = False
        warning_violation.matched_content = "deploy"
        warning_violation.category = "best-practice"

        result = MagicMock()
        result.valid = False
        result.violations = [warning_violation]
        result.blocking_violations = []
        result.warnings = [warning_violation]
        result.constitutional_hash = "608508a9bd224290"
        engine.validate.return_value = result

        ch = _FakeChannel("test")
        router = NotificationRouter([ch])
        notifier = GovernanceNotifier(
            engine=engine, router=router, notify_on_warning=True
        )

        notifier.validate("deploy staging", agent_id="bot-5")

        assert len(ch.sent_events) == 1
        assert ch.sent_events[0].severity == "MEDIUM"

    @pytest.mark.asyncio
    async def test_audit_tamper_check(self) -> None:
        engine = MagicMock()
        engine._const_hash = "608508a9bd224290"
        engine.audit_log = MagicMock()
        engine.audit_log.verify_chain.return_value = False

        ch = _FakeChannel("test")
        router = NotificationRouter([ch])
        notifier = GovernanceNotifier(engine=engine, router=router)

        intact = await notifier.check_audit_integrity()

        assert intact is False
        assert len(ch.sent_events) == 1
        assert ch.sent_events[0].event_type == "audit_tamper"
        assert ch.sent_events[0].severity == "CRITICAL"

    @pytest.mark.asyncio
    async def test_audit_intact_no_notification(self) -> None:
        engine = MagicMock()
        engine.audit_log = MagicMock()
        engine.audit_log.verify_chain.return_value = True

        ch = _FakeChannel("test")
        router = NotificationRouter([ch])
        notifier = GovernanceNotifier(engine=engine, router=router)

        intact = await notifier.check_audit_integrity()

        assert intact is True
        assert len(ch.sent_events) == 0

    @pytest.mark.asyncio
    async def test_audit_no_log_returns_true(self) -> None:
        engine = MagicMock(spec=[])
        ch = _FakeChannel("test")
        router = NotificationRouter([ch])
        notifier = GovernanceNotifier(engine=engine, router=router)

        intact = await notifier.check_audit_integrity()
        assert intact is True

    def test_engine_property(self) -> None:
        engine = self._make_mock_engine(valid=True)
        router = NotificationRouter([])
        notifier = GovernanceNotifier(engine=engine, router=router)
        assert notifier.engine is engine

    def test_router_property(self) -> None:
        engine = self._make_mock_engine(valid=True)
        router = NotificationRouter([])
        notifier = GovernanceNotifier(engine=engine, router=router)
        assert notifier.router is router


# ---------------------------------------------------------------------------
# Stats tracking
# ---------------------------------------------------------------------------


class TestStatsTracking:
    @pytest.mark.asyncio
    async def test_total_sent_and_failed(self) -> None:
        ok = _FakeChannel("ok")
        fail = _FakeChannel("fail", should_fail=True)
        router = NotificationRouter([ok, fail])

        await router.notify(_make_event())
        await router.notify(_make_event())

        stats = router.stats
        assert stats["total_sent"] == 2
        assert stats["total_failed"] == 2
        assert stats["per_channel"]["ok"]["sent"] == 2
        assert stats["per_channel"]["fail"]["failed"] == 2

    @pytest.mark.asyncio
    async def test_stats_zero_initially(self) -> None:
        router = NotificationRouter([_FakeChannel("x")])
        stats = router.stats
        assert stats["total_sent"] == 0
        assert stats["total_failed"] == 0


# ---------------------------------------------------------------------------
# Graceful degradation when httpx is not installed
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    def test_slack_raises_import_error_without_httpx(self) -> None:
        with patch(
            "acgs_lite.integrations.notifications.HTTPX_AVAILABLE", False
        ), pytest.raises(ImportError, match="httpx"):
            SlackNotifier(webhook_url="https://test")

    def test_teams_raises_import_error_without_httpx(self) -> None:
        with patch(
            "acgs_lite.integrations.notifications.HTTPX_AVAILABLE", False
        ), pytest.raises(ImportError, match="httpx"):
            TeamsNotifier(webhook_url="https://test")

    def test_webhook_raises_import_error_without_httpx(self) -> None:
        with patch(
            "acgs_lite.integrations.notifications.HTTPX_AVAILABLE", False
        ), pytest.raises(ImportError, match="httpx"):
            WebhookNotifier(url="https://test")

    def test_governance_event_works_without_httpx(self) -> None:
        """GovernanceEvent and NotificationRouter have no httpx dependency."""
        event = _make_event()
        assert event.to_dict()["severity"] == "HIGH"

    @pytest.mark.asyncio
    async def test_router_works_with_non_httpx_channels(self) -> None:
        ch = _FakeChannel("memory")
        router = NotificationRouter([ch])
        await router.notify(_make_event())
        assert router.stats["total_sent"] == 1


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    def test_fake_channel_satisfies_protocol(self) -> None:
        ch = _FakeChannel("test")
        assert isinstance(ch, NotificationChannel)

    @pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")
    def test_slack_satisfies_protocol(self) -> None:
        ch = SlackNotifier(webhook_url="https://test")
        assert isinstance(ch, NotificationChannel)

    @pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")
    def test_teams_satisfies_protocol(self) -> None:
        ch = TeamsNotifier(webhook_url="https://test")
        assert isinstance(ch, NotificationChannel)

    @pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")
    def test_webhook_satisfies_protocol(self) -> None:
        ch = WebhookNotifier(url="https://test")
        assert isinstance(ch, NotificationChannel)
