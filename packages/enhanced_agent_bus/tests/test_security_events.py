"""
Tests for Security Event Logging Stream.

Constitutional Hash: 608508a9bd224290

Tests cover:
- SecurityEventLogger initialization and lifecycle
- All security event types (MACI, constitutional, tenant, rate limit, etc.)
- Async non-blocking logging
- Event serialization to JSON
- Metrics collection
- Global singleton management
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.security_events import (
    CONSTITUTIONAL_HASH,
    AuthenticationFailureEvent,
    AuthorizationDenialEvent,
    ConstitutionalHashMismatchEvent,
    CrossTenantAccessEvent,
    MACIViolationEvent,
    PolicyVersionConflictEvent,
    RateLimitExhaustionEvent,
    SecurityEventData,
    SecurityEventLogger,
    SecurityEventType,
    SecuritySeverity,
    close_security_event_logger,
    get_security_event_logger,
    initialize_security_event_logger,
)


class TestSecurityEventType:
    """Test SecurityEventType enum."""

    def test_all_event_types_defined(self) -> None:
        """Test that all required event types are defined."""
        expected_types = [
            "MACI_PERMISSION_VIOLATION",
            "CONSTITUTIONAL_HASH_MISMATCH",
            "CROSS_TENANT_ACCESS_ATTEMPT",
            "RATE_LIMIT_EXHAUSTION",
            "POLICY_VERSION_CONFLICT",
            "AUTHENTICATION_FAILURE",
            "AUTHORIZATION_DENIAL",
        ]
        for event_type in expected_types:
            assert hasattr(SecurityEventType, event_type)

    def test_event_type_values(self) -> None:
        """Test event type string values."""
        assert SecurityEventType.MACI_PERMISSION_VIOLATION.value == "maci_permission_violation"
        assert (
            SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH.value == "constitutional_hash_mismatch"
        )
        assert SecurityEventType.CROSS_TENANT_ACCESS_ATTEMPT.value == "cross_tenant_access_attempt"


class TestSecuritySeverity:
    """Test SecuritySeverity enum."""

    def test_all_severity_levels_defined(self) -> None:
        """Test that all severity levels are defined."""
        expected_levels = ["INFO", "WARNING", "ERROR", "CRITICAL"]
        for level in expected_levels:
            assert hasattr(SecuritySeverity, level)

    def test_severity_values(self) -> None:
        """Test severity string values."""
        assert SecuritySeverity.INFO.value == "INFO"
        assert SecuritySeverity.WARNING.value == "WARNING"
        assert SecuritySeverity.ERROR.value == "ERROR"
        assert SecuritySeverity.CRITICAL.value == "CRITICAL"


class TestSecurityEventData:
    """Test SecurityEventData base class."""

    def test_creation_with_defaults(self) -> None:
        """Test event creation with default values."""
        event = SecurityEventData(
            event_type=SecurityEventType.MACI_PERMISSION_VIOLATION,
            severity=SecuritySeverity.ERROR,
            message="Test event",
        )
        assert event.event_type == SecurityEventType.MACI_PERMISSION_VIOLATION
        assert event.severity == SecuritySeverity.ERROR
        assert event.message == "Test event"
        assert event.constitutional_hash == CONSTITUTIONAL_HASH
        assert event.tenant_id is None
        assert isinstance(event.correlation_id, str)
        assert isinstance(event.timestamp, datetime)

    def test_to_dict(self) -> None:
        """Test event dictionary serialization."""
        event = SecurityEventData(
            event_type=SecurityEventType.MACI_PERMISSION_VIOLATION,
            severity=SecuritySeverity.ERROR,
            message="Test event",
            tenant_id="test-tenant",
            correlation_id="test-correlation-id",
        )
        result = event.to_dict()
        assert result["event_type"] == "maci_permission_violation"
        assert result["severity"] == "ERROR"
        assert result["message"] == "Test event"
        assert result["tenant_id"] == "test-tenant"
        assert result["correlation_id"] == "test-correlation-id"
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_json(self) -> None:
        """Test event JSON serialization."""
        event = SecurityEventData(
            event_type=SecurityEventType.MACI_PERMISSION_VIOLATION,
            severity=SecuritySeverity.ERROR,
            message="Test event",
        )
        json_str = event.to_json()
        parsed = json.loads(json_str)
        assert parsed["event_type"] == "maci_permission_violation"
        assert parsed["severity"] == "ERROR"


class TestMACIViolationEvent:
    """Test MACIViolationEvent."""

    def test_creation(self) -> None:
        """Test MACI violation event creation."""
        event = MACIViolationEvent(
            event_type=SecurityEventType.MACI_PERMISSION_VIOLATION,
            severity=SecuritySeverity.ERROR,
            message="",
            agent_id="agent-001",
            attempted_action="validate",
            required_role="judicial",
            actual_role="executive",
        )
        assert event.agent_id == "agent-001"
        assert event.attempted_action == "validate"
        assert event.required_role == "judicial"
        assert event.actual_role == "executive"
        assert "MACI permission violation" in event.message

    def test_to_dict_includes_maci_details(self) -> None:
        """Test that MACI details are included in dict."""
        event = MACIViolationEvent(
            event_type=SecurityEventType.MACI_PERMISSION_VIOLATION,
            severity=SecuritySeverity.ERROR,
            message="",
            agent_id="agent-001",
            attempted_action="validate",
            required_role="judicial",
            actual_role="executive",
        )
        result = event.to_dict()
        assert "maci_details" in result
        assert result["maci_details"]["agent_id"] == "agent-001"
        assert result["maci_details"]["attempted_action"] == "validate"


class TestConstitutionalHashMismatchEvent:
    """Test ConstitutionalHashMismatchEvent."""

    def test_creation(self) -> None:
        """Test constitutional hash mismatch event creation."""
        event = ConstitutionalHashMismatchEvent(
            event_type=SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH,
            severity=SecuritySeverity.CRITICAL,
            message="",
            expected_hash=CONSTITUTIONAL_HASH,
            received_hash="invalid-hash",
            source="policy-service",
        )
        assert event.expected_hash == CONSTITUTIONAL_HASH
        assert event.received_hash == "invalid-hash"
        assert event.source == "policy-service"
        assert event.severity == SecuritySeverity.CRITICAL

    def test_to_dict_includes_hash_details(self) -> None:
        """Test that hash details are included in dict."""
        event = ConstitutionalHashMismatchEvent(
            event_type=SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH,
            severity=SecuritySeverity.CRITICAL,
            message="",
            expected_hash=CONSTITUTIONAL_HASH,
            received_hash="invalid-hash",
            source="policy-service",
        )
        result = event.to_dict()
        assert "hash_details" in result
        assert result["hash_details"]["expected_hash"] == CONSTITUTIONAL_HASH
        assert result["hash_details"]["received_hash"] == "invalid-hash"


class TestCrossTenantAccessEvent:
    """Test CrossTenantAccessEvent."""

    def test_creation(self) -> None:
        """Test cross-tenant access event creation."""
        event = CrossTenantAccessEvent(
            event_type=SecurityEventType.CROSS_TENANT_ACCESS_ATTEMPT,
            severity=SecuritySeverity.ERROR,
            message="",
            source_tenant="tenant-a",
            target_tenant="tenant-b",
            resource_type="policy",
        )
        assert event.source_tenant == "tenant-a"
        assert event.target_tenant == "tenant-b"
        assert event.resource_type == "policy"

    def test_to_dict_includes_tenant_details(self) -> None:
        """Test that tenant details are included in dict."""
        event = CrossTenantAccessEvent(
            event_type=SecurityEventType.CROSS_TENANT_ACCESS_ATTEMPT,
            severity=SecuritySeverity.ERROR,
            message="",
            source_tenant="tenant-a",
            target_tenant="tenant-b",
            resource_type="policy",
        )
        result = event.to_dict()
        assert "tenant_details" in result
        assert result["tenant_details"]["source_tenant"] == "tenant-a"


class TestRateLimitExhaustionEvent:
    """Test RateLimitExhaustionEvent."""

    def test_creation(self) -> None:
        """Test rate limit exhaustion event creation."""
        event = RateLimitExhaustionEvent(
            event_type=SecurityEventType.RATE_LIMIT_EXHAUSTION,
            severity=SecuritySeverity.WARNING,
            message="",
            client_id="client-123",
            endpoint="/api/v1/validate",
            limit=100,
            current_count=101,
        )
        assert event.client_id == "client-123"
        assert event.endpoint == "/api/v1/validate"
        assert event.limit == 100
        assert event.current_count == 101

    def test_to_dict_includes_rate_limit_details(self) -> None:
        """Test that rate limit details are included in dict."""
        event = RateLimitExhaustionEvent(
            event_type=SecurityEventType.RATE_LIMIT_EXHAUSTION,
            severity=SecuritySeverity.WARNING,
            message="",
            client_id="client-123",
            endpoint="/api/v1/validate",
            limit=100,
            current_count=101,
        )
        result = event.to_dict()
        assert "rate_limit_details" in result
        assert result["rate_limit_details"]["limit"] == 100


class TestPolicyVersionConflictEvent:
    """Test PolicyVersionConflictEvent."""

    def test_creation(self) -> None:
        """Test policy version conflict event creation."""
        event = PolicyVersionConflictEvent(
            event_type=SecurityEventType.POLICY_VERSION_CONFLICT,
            severity=SecuritySeverity.WARNING,
            message="",
            policy_id="policy-001",
            expected_version="v1.2.0",
            actual_version="v1.1.0",
        )
        assert event.policy_id == "policy-001"
        assert event.expected_version == "v1.2.0"
        assert event.actual_version == "v1.1.0"


class TestAuthenticationFailureEvent:
    """Test AuthenticationFailureEvent."""

    def test_creation(self) -> None:
        """Test authentication failure event creation."""
        event = AuthenticationFailureEvent(
            event_type=SecurityEventType.AUTHENTICATION_FAILURE,
            severity=SecuritySeverity.WARNING,
            message="",
            user_id="user-123",
            failure_reason="invalid_password",
            ip_address="192.168.1.100",
        )
        assert event.user_id == "user-123"
        assert event.failure_reason == "invalid_password"
        assert event.ip_address == "192.168.1.100"

    def test_to_dict_includes_auth_details(self) -> None:
        """Test that auth details are included in dict."""
        event = AuthenticationFailureEvent(
            event_type=SecurityEventType.AUTHENTICATION_FAILURE,
            severity=SecuritySeverity.WARNING,
            message="",
            user_id="user-123",
            failure_reason="invalid_password",
            ip_address="192.168.1.100",
        )
        result = event.to_dict()
        assert "auth_details" in result
        assert result["auth_details"]["user_id"] == "user-123"


class TestAuthorizationDenialEvent:
    """Test AuthorizationDenialEvent."""

    def test_creation(self) -> None:
        """Test authorization denial event creation."""
        event = AuthorizationDenialEvent(
            event_type=SecurityEventType.AUTHORIZATION_DENIAL,
            severity=SecuritySeverity.WARNING,
            message="",
            user_id="user-123",
            resource="/api/admin",
            action="DELETE",
            denial_reason="insufficient_permissions",
        )
        assert event.user_id == "user-123"
        assert event.resource == "/api/admin"
        assert event.action == "DELETE"
        assert event.denial_reason == "insufficient_permissions"


class TestSecurityEventLogger:
    """Test SecurityEventLogger class."""

    async def test_initialization(self) -> None:
        """Test logger initialization."""
        logger = SecurityEventLogger()
        assert logger.constitutional_hash == CONSTITUTIONAL_HASH
        assert not logger._running

    async def test_start_stop_lifecycle(self) -> None:
        """Test logger start and stop lifecycle."""
        logger = SecurityEventLogger()
        await logger.start()
        assert logger._running

        await logger.stop()
        assert not logger._running

    async def test_log_maci_violation(self) -> None:
        """Test logging MACI violation."""
        logger = SecurityEventLogger(flush_interval_seconds=0.1)
        await logger.start()

        await logger.log_maci_violation(
            agent_id="agent-001",
            attempted_action="validate",
            required_role="judicial",
            actual_role="executive",
            tenant_id="test-tenant",
        )

        # Wait for flush
        await asyncio.sleep(0.2)

        metrics = logger.get_metrics()
        assert metrics["events_logged"] >= 1

        await logger.stop()

    async def test_log_constitutional_hash_mismatch(self) -> None:
        """Test logging constitutional hash mismatch."""
        logger = SecurityEventLogger(flush_interval_seconds=0.1)
        await logger.start()

        await logger.log_constitutional_hash_mismatch(
            expected_hash=CONSTITUTIONAL_HASH,
            received_hash="invalid-hash",
            source="policy-service",
            tenant_id="test-tenant",
        )

        await asyncio.sleep(0.2)
        metrics = logger.get_metrics()
        assert metrics["events_logged"] >= 1

        await logger.stop()

    async def test_log_cross_tenant_access(self) -> None:
        """Test logging cross-tenant access attempt."""
        logger = SecurityEventLogger(flush_interval_seconds=0.1)
        await logger.start()

        await logger.log_cross_tenant_access(
            source_tenant="tenant-a",
            target_tenant="tenant-b",
            resource_type="policy",
        )

        await asyncio.sleep(0.2)
        metrics = logger.get_metrics()
        assert metrics["events_logged"] >= 1

        await logger.stop()

    async def test_log_rate_limit_exhaustion(self) -> None:
        """Test logging rate limit exhaustion."""
        logger = SecurityEventLogger(flush_interval_seconds=0.1)
        await logger.start()

        await logger.log_rate_limit_exhaustion(
            client_id="client-123",
            endpoint="/api/v1/validate",
            limit=100,
            current_count=101,
        )

        await asyncio.sleep(0.2)
        metrics = logger.get_metrics()
        assert metrics["events_logged"] >= 1

        await logger.stop()

    async def test_log_policy_version_conflict(self) -> None:
        """Test logging policy version conflict."""
        logger = SecurityEventLogger(flush_interval_seconds=0.1)
        await logger.start()

        await logger.log_policy_version_conflict(
            policy_id="policy-001",
            expected_version="v1.2.0",
            actual_version="v1.1.0",
        )

        await asyncio.sleep(0.2)
        metrics = logger.get_metrics()
        assert metrics["events_logged"] >= 1

        await logger.stop()

    async def test_log_authentication_failure(self) -> None:
        """Test logging authentication failure."""
        logger = SecurityEventLogger(flush_interval_seconds=0.1)
        await logger.start()

        await logger.log_authentication_failure(
            user_id="user-123",
            failure_reason="invalid_password",
            ip_address="192.168.1.100",
        )

        await asyncio.sleep(0.2)
        metrics = logger.get_metrics()
        assert metrics["events_logged"] >= 1

        await logger.stop()

    async def test_log_authorization_denial(self) -> None:
        """Test logging authorization denial."""
        logger = SecurityEventLogger(flush_interval_seconds=0.1)
        await logger.start()

        await logger.log_authorization_denial(
            user_id="user-123",
            resource="/api/admin",
            action="DELETE",
            denial_reason="insufficient_permissions",
        )

        await asyncio.sleep(0.2)
        metrics = logger.get_metrics()
        assert metrics["events_logged"] >= 1

        await logger.stop()

    async def test_log_generic_event(self) -> None:
        """Test logging generic event."""
        logger = SecurityEventLogger(flush_interval_seconds=0.1)
        await logger.start()

        await logger.log_generic_event(
            event_type=SecurityEventType.MACI_PERMISSION_VIOLATION,
            severity=SecuritySeverity.ERROR,
            message="Custom generic event",
            tenant_id="test-tenant",
        )

        await asyncio.sleep(0.2)
        metrics = logger.get_metrics()
        assert metrics["events_logged"] >= 1

        await logger.stop()

    async def test_custom_event_handler(self) -> None:
        """Test custom event handler."""
        handled_events: list = []

        def handler(event: SecurityEventData) -> None:
            handled_events.append(event)

        logger = SecurityEventLogger(flush_interval_seconds=0.1, event_handler=handler)
        await logger.start()

        await logger.log_maci_violation(
            agent_id="agent-001",
            attempted_action="validate",
            required_role="judicial",
            actual_role="executive",
        )

        await asyncio.sleep(0.2)
        assert len(handled_events) >= 1

        await logger.stop()

    async def test_async_event_handler(self) -> None:
        """Test async event handler."""
        handled_events: list = []

        async def async_handler(event: SecurityEventData) -> None:
            handled_events.append(event)

        logger = SecurityEventLogger(flush_interval_seconds=0.1, event_handler=async_handler)
        await logger.start()

        await logger.log_maci_violation(
            agent_id="agent-001",
            attempted_action="validate",
            required_role="judicial",
            actual_role="executive",
        )

        await asyncio.sleep(0.2)
        assert len(handled_events) >= 1

        await logger.stop()

    async def test_get_recent_events(self) -> None:
        """Test getting recent events."""
        logger = SecurityEventLogger(flush_interval_seconds=0.1)
        await logger.start()

        for i in range(5):
            await logger.log_maci_violation(
                agent_id=f"agent-{i}",
                attempted_action="validate",
                required_role="judicial",
                actual_role="executive",
            )

        await asyncio.sleep(0.2)
        events = logger.get_recent_events(limit=3)
        assert len(events) <= 3

        await logger.stop()

    async def test_queue_overflow_drop(self) -> None:
        """Test queue overflow with drop behavior."""
        logger = SecurityEventLogger(
            max_queue_size=5,
            flush_interval_seconds=10,  # Long interval to fill queue
            drop_on_overflow=True,
        )
        await logger.start()

        # Fill queue beyond capacity
        for i in range(10):
            await logger.log_maci_violation(
                agent_id=f"agent-{i}",
                attempted_action="validate",
                required_role="judicial",
                actual_role="executive",
            )

        metrics = logger.get_metrics()
        assert metrics["events_dropped"] > 0

        await logger.stop()

    async def test_metrics(self) -> None:
        """Test metrics collection."""
        logger = SecurityEventLogger()
        await logger.start()

        metrics = logger.get_metrics()
        assert "events_logged" in metrics
        assert "events_dropped" in metrics
        assert "events_processed" in metrics
        assert "flush_count" in metrics
        assert "queue_size" in metrics
        assert "running" in metrics
        assert "constitutional_hash" in metrics

        await logger.stop()


class TestGlobalSecurityEventLogger:
    """Test global SecurityEventLogger singleton functions."""

    async def test_initialize_and_get(self) -> None:
        """Test initializing and getting global logger."""
        # Ensure clean state
        await close_security_event_logger()

        logger = await initialize_security_event_logger()
        assert logger is not None
        assert logger._running

        # Get should return same instance
        same_logger = get_security_event_logger()
        assert same_logger is logger

        await close_security_event_logger()

    async def test_close(self) -> None:
        """Test closing global logger."""
        await initialize_security_event_logger()
        await close_security_event_logger()

        logger = get_security_event_logger()
        assert logger is None

    async def test_reinitialize(self) -> None:
        """Test reinitializing global logger."""
        await close_security_event_logger()

        logger1 = await initialize_security_event_logger()
        await close_security_event_logger()

        logger2 = await initialize_security_event_logger()
        # Should be different instances after close
        assert logger2 is not logger1

        await close_security_event_logger()


@pytest.mark.constitutional
class TestConstitutionalCompliance:
    """Test constitutional hash compliance."""

    def test_constitutional_hash_constant(self) -> None:
        """Test constitutional hash constant is correct."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_events_include_constitutional_hash(self) -> None:
        """Test all events include constitutional hash."""
        event = SecurityEventData(
            event_type=SecurityEventType.MACI_PERMISSION_VIOLATION,
            severity=SecuritySeverity.ERROR,
            message="Test event",
        )
        assert event.constitutional_hash == CONSTITUTIONAL_HASH

    def test_logger_has_constitutional_hash(self) -> None:
        """Test logger has constitutional hash."""
        logger = SecurityEventLogger()
        assert logger.constitutional_hash == CONSTITUTIONAL_HASH

    def test_json_output_includes_constitutional_hash(self) -> None:
        """Test JSON output includes constitutional hash."""
        event = SecurityEventData(
            event_type=SecurityEventType.MACI_PERMISSION_VIOLATION,
            severity=SecuritySeverity.ERROR,
            message="Test event",
        )
        json_str = event.to_json()
        parsed = json.loads(json_str)
        assert parsed["constitutional_hash"] == CONSTITUTIONAL_HASH
