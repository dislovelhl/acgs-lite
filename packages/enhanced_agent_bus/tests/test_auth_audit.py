"""Tests for AuthAuditLogger.

Constitutional Hash: 608508a9bd224290

Tests authentication audit logging, alerting, filtering, stats, and cleanup.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from enhanced_agent_bus.mcp_integration.auth.auth_audit import (
    AuditLoggerConfig,
    AuditSeverity,
    AuthAuditEntry,
    AuthAuditEventType,
    AuthAuditLogger,
    AuthAuditStats,
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class TestAuthAuditEventType:
    def test_token_events(self) -> None:
        assert AuthAuditEventType.TOKEN_ACQUIRED.value == "token_acquired"
        assert AuthAuditEventType.TOKEN_REFRESHED.value == "token_refreshed"

    def test_auth_events(self) -> None:
        assert AuthAuditEventType.AUTH_SUCCESS.value == "auth_success"
        assert AuthAuditEventType.AUTH_FAILURE.value == "auth_failure"

    def test_security_events(self) -> None:
        assert AuthAuditEventType.SUSPICIOUS_ACTIVITY.value == "suspicious_activity"
        assert AuthAuditEventType.RATE_LIMIT_EXCEEDED.value == "rate_limit_exceeded"


class TestAuditSeverity:
    def test_severity_values(self) -> None:
        assert AuditSeverity.INFO.value == "info"
        assert AuditSeverity.WARNING.value == "warning"
        assert AuditSeverity.ERROR.value == "error"
        assert AuditSeverity.CRITICAL.value == "critical"


class TestAuthAuditEntry:
    def test_creation(self) -> None:
        entry = AuthAuditEntry(
            entry_id="test-id",
            event_type=AuthAuditEventType.AUTH_SUCCESS,
            timestamp=datetime(2025, 1, 1, tzinfo=UTC),
            agent_id="agent-1",
            message="Login OK",
        )
        assert entry.entry_id == "test-id"
        assert entry.success is True
        assert entry.severity == AuditSeverity.INFO

    def test_to_dict(self) -> None:
        ts = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        entry = AuthAuditEntry(
            entry_id="e1",
            event_type=AuthAuditEventType.AUTH_FAILURE,
            timestamp=ts,
            severity=AuditSeverity.WARNING,
            agent_id="agent-x",
            tool_name="tool-y",
            success=False,
            message="Bad creds",
            source_ip="1.2.3.4",
        )
        d = entry.to_dict()
        assert d["entry_id"] == "e1"
        assert d["event_type"] == "auth_failure"
        assert d["severity"] == "warning"
        assert d["agent_id"] == "agent-x"
        assert d["success"] is False
        assert d["source_ip"] == "1.2.3.4"
        assert "2025-06-01" in d["timestamp"]

    def test_to_json(self) -> None:
        entry = AuthAuditEntry(
            entry_id="e1",
            event_type=AuthAuditEventType.AUTH_SUCCESS,
            timestamp=datetime(2025, 1, 1, tzinfo=UTC),
        )
        j = entry.to_json()
        parsed = json.loads(j)
        assert parsed["entry_id"] == "e1"


class TestAuthAuditStats:
    def test_creation_defaults(self) -> None:
        stats = AuthAuditStats()
        assert stats.total_events == 0
        assert stats.success_rate == 0.0
        assert stats.failures == 0

    def test_to_dict(self) -> None:
        ts = datetime(2025, 1, 1, tzinfo=UTC)
        stats = AuthAuditStats(
            total_events=10,
            success_rate=0.8,
            failures=2,
            period_start=ts,
            period_end=ts,
        )
        d = stats.to_dict()
        assert d["total_events"] == 10
        assert d["success_rate"] == 0.8
        assert d["period_start"] is not None

    def test_to_dict_no_period(self) -> None:
        stats = AuthAuditStats()
        d = stats.to_dict()
        assert d["period_start"] is None
        assert d["period_end"] is None


class TestAuditLoggerConfig:
    def test_defaults(self) -> None:
        config = AuditLoggerConfig()
        assert config.max_entries_in_memory == 10000
        assert config.persist_to_disk is True
        assert config.retention_days == 90
        assert config.sample_rate == 1.0
        assert config.alert_on_failure is True
        assert config.alert_threshold_failures == 5

    def test_custom(self) -> None:
        config = AuditLoggerConfig(
            max_entries_in_memory=100,
            sample_rate=0.5,
            redis_url="redis://test:6379",
        )
        assert config.max_entries_in_memory == 100
        assert config.sample_rate == 0.5
        assert config.redis_url == "redis://test:6379"


# ---------------------------------------------------------------------------
# AuthAuditLogger
# ---------------------------------------------------------------------------


class TestAuthAuditLogger:
    @pytest.fixture
    def logger_no_persist(self, tmp_path) -> AuthAuditLogger:
        config = AuditLoggerConfig(
            persist_to_disk=False,
            storage_path=str(tmp_path / "audit"),
            alert_on_failure=False,
            sample_rate=1.0,
        )
        return AuthAuditLogger(config)

    @pytest.fixture
    def logger_with_persist(self, tmp_path) -> AuthAuditLogger:
        config = AuditLoggerConfig(
            persist_to_disk=True,
            storage_path=str(tmp_path / "audit"),
            alert_on_failure=False,
            sample_rate=1.0,
        )
        return AuthAuditLogger(config)

    async def test_log_event_basic(self, logger_no_persist) -> None:
        entry = await logger_no_persist.log_event(
            event_type=AuthAuditEventType.AUTH_SUCCESS,
            message="Login",
            agent_id="agent-1",
        )
        assert entry.event_type == AuthAuditEventType.AUTH_SUCCESS
        assert entry.entry_id != ""
        assert entry.timestamp is not None
        assert len(logger_no_persist._entries) == 1

    async def test_log_event_failure(self, logger_no_persist) -> None:
        entry = await logger_no_persist.log_event(
            event_type=AuthAuditEventType.AUTH_FAILURE,
            message="Bad password",
            success=False,
            agent_id="agent-1",
            severity=AuditSeverity.WARNING,
        )
        assert entry.success is False
        assert entry.severity == AuditSeverity.WARNING

    async def test_log_event_with_all_fields(self, logger_no_persist) -> None:
        entry = await logger_no_persist.log_event(
            event_type=AuthAuditEventType.TOKEN_ACQUIRED,
            message="Token OK",
            agent_id="agent-1",
            tool_name="tool-x",
            tenant_id="t1",
            session_id="s1",
            request_id="r1",
            source_ip="10.0.0.1",
            user_agent="TestBot/1.0",
            method="POST",
            path="/api/token",
            details={"scope": "read"},
        )
        assert entry.tool_name == "tool-x"
        assert entry.tenant_id == "t1"
        assert entry.source_ip == "10.0.0.1"
        assert entry.details["scope"] == "read"

    async def test_log_event_trims_entries(self) -> None:
        config = AuditLoggerConfig(
            max_entries_in_memory=5,
            persist_to_disk=False,
            alert_on_failure=False,
        )
        audit_logger = AuthAuditLogger(config)

        for i in range(10):
            await audit_logger.log_event(
                event_type=AuthAuditEventType.AUTH_SUCCESS,
                message=f"Event {i}",
            )

        assert len(audit_logger._entries) == 5
        assert audit_logger._entry_count == 10

    async def test_log_event_sampling(self) -> None:
        config = AuditLoggerConfig(
            sample_rate=0.0,  # Drop all
            persist_to_disk=False,
            alert_on_failure=False,
        )
        audit_logger = AuthAuditLogger(config)
        entry = await audit_logger.log_event(
            event_type=AuthAuditEventType.AUTH_SUCCESS,
            message="Sampled out",
        )
        # Entry is created but not stored
        assert entry is not None
        assert len(audit_logger._entries) == 0

    async def test_persist_to_disk(self, logger_with_persist) -> None:
        await logger_with_persist.log_event(
            event_type=AuthAuditEventType.AUTH_SUCCESS,
            message="Persisted",
        )
        storage_path = Path(logger_with_persist.config.storage_path)
        log_files = list(storage_path.glob("auth_audit_*.jsonl"))
        assert len(log_files) >= 1
        content = log_files[0].read_text()
        assert "Persisted" in content

    async def test_persist_rotation(self, tmp_path) -> None:
        config = AuditLoggerConfig(
            persist_to_disk=True,
            storage_path=str(tmp_path / "audit"),
            rotation_size_mb=0,  # Force rotation every time
            alert_on_failure=False,
        )
        audit_logger = AuthAuditLogger(config)

        await audit_logger.log_event(
            event_type=AuthAuditEventType.AUTH_SUCCESS,
            message="First",
        )
        # Force rotation
        audit_logger._current_log_size = 1024 * 1024 + 1
        await audit_logger.log_event(
            event_type=AuthAuditEventType.AUTH_SUCCESS,
            message="Second",
        )
        assert audit_logger._current_log_file is not None


# ---------------------------------------------------------------------------
# Filtering (get_entries)
# ---------------------------------------------------------------------------


class TestGetEntries:
    @pytest.fixture
    async def populated_logger(self) -> AuthAuditLogger:
        config = AuditLoggerConfig(
            persist_to_disk=False,
            alert_on_failure=False,
        )
        audit_logger = AuthAuditLogger(config)
        await audit_logger.log_event(
            event_type=AuthAuditEventType.AUTH_SUCCESS,
            message="OK 1",
            agent_id="agent-1",
            tool_name="tool-a",
        )
        await audit_logger.log_event(
            event_type=AuthAuditEventType.AUTH_FAILURE,
            message="Fail 1",
            success=False,
            severity=AuditSeverity.WARNING,
            agent_id="agent-2",
        )
        await audit_logger.log_event(
            event_type=AuthAuditEventType.TOKEN_ACQUIRED,
            message="Token",
            agent_id="agent-1",
            tool_name="tool-b",
        )
        return audit_logger

    async def test_get_all_entries(self, populated_logger) -> None:
        entries = await populated_logger.get_entries()
        assert len(entries) == 3

    async def test_filter_by_event_type(self, populated_logger) -> None:
        entries = await populated_logger.get_entries(event_type=AuthAuditEventType.AUTH_FAILURE)
        assert len(entries) == 1
        assert entries[0].event_type == AuthAuditEventType.AUTH_FAILURE

    async def test_filter_by_agent_id(self, populated_logger) -> None:
        entries = await populated_logger.get_entries(agent_id="agent-1")
        assert len(entries) == 2

    async def test_filter_by_tool_name(self, populated_logger) -> None:
        entries = await populated_logger.get_entries(tool_name="tool-a")
        assert len(entries) == 1

    async def test_filter_by_success(self, populated_logger) -> None:
        entries = await populated_logger.get_entries(success=False)
        assert len(entries) == 1

    async def test_filter_by_severity(self, populated_logger) -> None:
        entries = await populated_logger.get_entries(severity=AuditSeverity.WARNING)
        assert len(entries) == 1

    async def test_filter_by_time_range(self, populated_logger) -> None:
        since = datetime.now(UTC) - timedelta(hours=1)
        until = datetime.now(UTC) + timedelta(hours=1)
        entries = await populated_logger.get_entries(since=since, until=until)
        assert len(entries) == 3

    async def test_filter_by_time_range_excludes(self, populated_logger) -> None:
        future = datetime.now(UTC) + timedelta(hours=1)
        entries = await populated_logger.get_entries(since=future)
        assert len(entries) == 0

    async def test_limit(self, populated_logger) -> None:
        entries = await populated_logger.get_entries(limit=1)
        assert len(entries) == 1


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestGetStats:
    async def test_stats_empty(self) -> None:
        config = AuditLoggerConfig(persist_to_disk=False, alert_on_failure=False)
        audit_logger = AuthAuditLogger(config)
        stats = await audit_logger.get_stats()
        assert stats.total_events == 0
        assert stats.success_rate == 0.0

    async def test_stats_with_events(self) -> None:
        config = AuditLoggerConfig(persist_to_disk=False, alert_on_failure=False)
        audit_logger = AuthAuditLogger(config)
        await audit_logger.log_event(
            event_type=AuthAuditEventType.AUTH_SUCCESS,
            agent_id="a1",
            tool_name="t1",
        )
        await audit_logger.log_event(
            event_type=AuthAuditEventType.AUTH_FAILURE,
            success=False,
            severity=AuditSeverity.WARNING,
            agent_id="a2",
        )

        stats = await audit_logger.get_stats()
        assert stats.total_events == 2
        assert stats.success_rate == 0.5
        assert stats.failures == 1
        assert stats.unique_agents == 2
        assert stats.unique_tools == 1
        assert "auth_success" in stats.events_by_type
        assert "warning" in stats.events_by_severity


# ---------------------------------------------------------------------------
# Alerting
# ---------------------------------------------------------------------------


class TestAlerting:
    async def test_failure_tracking_triggers_alert(self) -> None:
        config = AuditLoggerConfig(
            persist_to_disk=False,
            alert_on_failure=True,
            alert_threshold_failures=2,
            alert_window_seconds=60,
        )
        audit_logger = AuthAuditLogger(config)

        # Log enough failures to trigger alert
        for i in range(3):
            await audit_logger.log_event(
                event_type=AuthAuditEventType.AUTH_FAILURE,
                message=f"Fail {i}",
                success=False,
            )

        assert len(audit_logger._recent_failures) >= 2

    async def test_alert_callback_called(self) -> None:
        config = AuditLoggerConfig(
            persist_to_disk=False,
            alert_on_failure=True,
            alert_threshold_failures=1,
            alert_window_seconds=60,
        )
        audit_logger = AuthAuditLogger(config)
        callback = AsyncMock()
        audit_logger.set_alert_callback(callback)

        await audit_logger.log_event(
            event_type=AuthAuditEventType.AUTH_FAILURE,
            message="Trigger alert",
            success=False,
        )
        callback.assert_awaited_once()

    async def test_alert_callback_error_handled(self) -> None:
        config = AuditLoggerConfig(
            persist_to_disk=False,
            alert_on_failure=True,
            alert_threshold_failures=1,
        )
        audit_logger = AuthAuditLogger(config)
        callback = AsyncMock(side_effect=RuntimeError("callback error"))
        audit_logger.set_alert_callback(callback)

        # Should not raise
        await audit_logger.log_event(
            event_type=AuthAuditEventType.AUTH_FAILURE,
            success=False,
        )


# ---------------------------------------------------------------------------
# Rate limiting detection
# ---------------------------------------------------------------------------


class TestRateLimitDetection:
    async def test_rate_limit_tracking(self) -> None:
        config = AuditLoggerConfig(
            persist_to_disk=False,
            alert_on_failure=False,
            rate_limit_window_seconds=60,
            rate_limit_max_requests=100,  # High limit to avoid recursive log_event
        )
        audit_logger = AuthAuditLogger(config)

        for _i in range(5):
            await audit_logger.log_event(
                event_type=AuthAuditEventType.AUTH_SUCCESS,
                agent_id="tracked-agent",
            )

        # Verify requests are tracked
        assert len(audit_logger._agent_request_counts["tracked-agent"]) == 5

    async def test_rate_limit_cleans_old_requests(self) -> None:
        config = AuditLoggerConfig(
            persist_to_disk=False,
            alert_on_failure=False,
            rate_limit_window_seconds=1,
            rate_limit_max_requests=1000,
        )
        audit_logger = AuthAuditLogger(config)

        # Add an old timestamp manually
        old_ts = datetime.now(UTC) - timedelta(seconds=60)
        audit_logger._agent_request_counts["agent-old"] = [old_ts, old_ts]

        await audit_logger._track_request("agent-old")
        # Old entries should be cleaned, only the new one remains
        assert len(audit_logger._agent_request_counts["agent-old"]) == 1


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


class TestCleanup:
    async def test_cleanup_old_entries_memory(self) -> None:
        config = AuditLoggerConfig(
            persist_to_disk=False,
            alert_on_failure=False,
            retention_days=1,
        )
        audit_logger = AuthAuditLogger(config)

        # Add an old entry directly
        old_entry = AuthAuditEntry(
            entry_id="old",
            event_type=AuthAuditEventType.AUTH_SUCCESS,
            timestamp=datetime.now(UTC) - timedelta(days=10),
        )
        audit_logger._entries.append(old_entry)

        # Add a recent entry
        await audit_logger.log_event(
            event_type=AuthAuditEventType.AUTH_SUCCESS,
            message="Recent",
        )

        removed = await audit_logger.cleanup_old_entries()
        assert removed >= 1
        assert len(audit_logger._entries) == 1

    async def test_cleanup_disk_files(self, tmp_path) -> None:
        storage = tmp_path / "audit"
        storage.mkdir()
        # Create an old log file
        old_file = storage / "auth_audit_20200101_000000.jsonl"
        old_file.write_text('{"test": true}\n')

        config = AuditLoggerConfig(
            persist_to_disk=True,
            storage_path=str(storage),
            alert_on_failure=False,
            retention_days=1,
        )
        audit_logger = AuthAuditLogger(config)

        removed = await audit_logger.cleanup_old_entries()
        assert removed >= 1
        assert not old_file.exists()

    async def test_cleanup_with_custom_retention(self) -> None:
        config = AuditLoggerConfig(
            persist_to_disk=False,
            alert_on_failure=False,
        )
        audit_logger = AuthAuditLogger(config)

        old_entry = AuthAuditEntry(
            entry_id="old",
            event_type=AuthAuditEventType.AUTH_SUCCESS,
            timestamp=datetime.now(UTC) - timedelta(days=5),
        )
        audit_logger._entries.append(old_entry)

        removed = await audit_logger.cleanup_old_entries(retention_days=1)
        assert removed >= 1


# ---------------------------------------------------------------------------
# Convenience methods
# ---------------------------------------------------------------------------


class TestConvenienceMethods:
    @pytest.fixture
    def audit_logger(self) -> AuthAuditLogger:
        config = AuditLoggerConfig(
            persist_to_disk=False,
            alert_on_failure=False,
        )
        return AuthAuditLogger(config)

    async def test_log_token_acquired(self, audit_logger) -> None:
        entry = await audit_logger.log_token_acquired(
            agent_id="agent-1",
            token_type="bearer",
            scopes=["read", "write"],
        )
        assert entry.event_type == AuthAuditEventType.TOKEN_ACQUIRED
        assert entry.details["token_type"] == "bearer"
        assert entry.details["scopes"] == ["read", "write"]

    async def test_log_auth_success(self, audit_logger) -> None:
        entry = await audit_logger.log_auth_success(
            agent_id="agent-1",
            method="oauth2",
        )
        assert entry.event_type == AuthAuditEventType.AUTH_SUCCESS
        assert entry.success is True
        assert entry.details["auth_method"] == "oauth2"

    async def test_log_auth_failure(self, audit_logger) -> None:
        entry = await audit_logger.log_auth_failure(
            agent_id="agent-1",
            reason="Invalid token",
        )
        assert entry.event_type == AuthAuditEventType.AUTH_FAILURE
        assert entry.success is False
        assert entry.severity == AuditSeverity.WARNING

    async def test_log_credential_access(self, audit_logger) -> None:
        entry = await audit_logger.log_credential_access(
            agent_id="agent-1",
            credential_id="cred-123",
            tool_name="github-tool",
        )
        assert entry.event_type == AuthAuditEventType.CREDENTIAL_ACCESSED
        assert entry.details["credential_id"] == "cred-123"
        assert entry.tool_name == "github-tool"

    async def test_log_suspicious_activity(self, audit_logger) -> None:
        entry = await audit_logger.log_suspicious_activity(
            description="Multiple failed logins from unknown IP",
            agent_id="agent-suspect",
        )
        assert entry.event_type == AuthAuditEventType.SUSPICIOUS_ACTIVITY
        assert entry.severity == AuditSeverity.ERROR
        assert entry.success is False


# ---------------------------------------------------------------------------
# Redis publish (mocked)
# ---------------------------------------------------------------------------


class TestRedisPublish:
    async def test_no_redis_url_skips(self) -> None:
        config = AuditLoggerConfig(
            persist_to_disk=False,
            alert_on_failure=False,
            redis_url=None,
        )
        audit_logger = AuthAuditLogger(config)
        entry = AuthAuditEntry(
            entry_id="e1",
            event_type=AuthAuditEventType.AUTH_SUCCESS,
            timestamp=datetime.now(UTC),
        )
        # Should not raise
        await audit_logger._publish_to_redis(entry)

    @patch("enhanced_agent_bus.mcp_integration.auth.auth_audit.redis", create=True)
    async def test_redis_publish_error_handled(self, mock_redis_mod) -> None:
        config = AuditLoggerConfig(
            persist_to_disk=False,
            alert_on_failure=False,
            redis_url="redis://localhost:6379",
        )
        audit_logger = AuthAuditLogger(config)
        mock_client = AsyncMock()
        mock_client.publish.side_effect = ConnectionError("lost")
        audit_logger._redis = mock_client

        entry = AuthAuditEntry(
            entry_id="e1",
            event_type=AuthAuditEventType.AUTH_SUCCESS,
            timestamp=datetime.now(UTC),
        )
        # Should not raise
        await audit_logger._publish_to_redis(entry)
