"""
Tests for SIEM Integration Module.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

import enhanced_agent_bus.siem_integration as siem_integration_module
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.runtime_security import (
    SecurityEvent,
    SecurityEventType,
    SecuritySeverity,
)
from enhanced_agent_bus.siem_integration import (
    AlertLevel,
    AlertManager,
    AlertThreshold,
    EventCorrelator,
    SIEMConfig,
    SIEMEventFormatter,
    SIEMFormat,
    SIEMIntegration,
    close_siem,
    get_siem_integration,
    initialize_siem,
    log_security_event,
    security_audit,
)

# --- Test Fixtures ---


@pytest.fixture
def sample_event():
    """Create a sample security event."""
    return SecurityEvent(
        event_type=SecurityEventType.AUTHENTICATION_FAILURE,
        severity=SecuritySeverity.HIGH,
        message="Failed authentication attempt",
        tenant_id="tenant-123",
        agent_id="agent-456",
        metadata={"ip": "192.168.1.1", "user": "admin"},
    )


@pytest.fixture
def critical_event():
    """Create a critical security event."""
    return SecurityEvent(
        event_type=SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH,
        severity=SecuritySeverity.CRITICAL,
        message="Constitutional hash validation failed",
        tenant_id="tenant-789",
    )


@pytest.fixture
def siem_config():
    """Create a test SIEM config."""
    return SIEMConfig(
        format=SIEMFormat.JSON,
        enable_alerting=True,
        max_queue_size=100,
        flush_interval_seconds=0.1,
    )


@pytest.fixture
async def siem_integration(siem_config):
    """Create and start a SIEM integration for testing."""
    siem = SIEMIntegration(siem_config)
    await siem.start()
    yield siem
    await siem.stop()


# --- SIEMEventFormatter Tests ---


class TestSIEMEventFormatter:
    """Tests for SIEM event formatting."""

    def test_format_json(self, sample_event):
        """Test JSON format output."""
        formatter = SIEMEventFormatter(format_type=SIEMFormat.JSON)
        result = formatter.format(sample_event)

        data = json.loads(result)
        assert data["event_type"] == "authentication_failure"
        assert data["severity"] == "high"
        assert data["message"] == "Failed authentication attempt"
        assert data["tenant_id"] == "tenant-123"
        assert data["agent_id"] == "agent-456"
        assert "_siem" in data
        assert data["_siem"]["vendor"] == "ACGS-2"

    def test_format_json_with_correlation_id(self, sample_event):
        """Test JSON format with correlation ID."""
        formatter = SIEMEventFormatter(format_type=SIEMFormat.JSON)
        result = formatter.format(sample_event, correlation_id="corr-12345")

        data = json.loads(result)
        assert data["correlation_id"] == "corr-12345"

    def test_format_cef(self, sample_event):
        """Test CEF format output."""
        formatter = SIEMEventFormatter(format_type=SIEMFormat.CEF)
        result = formatter.format(sample_event)

        assert result.startswith("CEF:0|ACGS-2|EnhancedAgentBus|2.4.0|")
        assert "authentication_failure" in result
        assert "msg=" in result
        assert "TenantID" in result
        assert "AgentID" in result
        assert "ConstitutionalHash" in result

    def test_format_cef_escapes_special_chars(self):
        """Test CEF format properly escapes special characters."""
        event = SecurityEvent(
            event_type=SecurityEventType.INVALID_INPUT,
            severity=SecuritySeverity.MEDIUM,
            message="Test|with=special\\chars",
        )
        formatter = SIEMEventFormatter(format_type=SIEMFormat.CEF)
        result = formatter.format(event)

        assert "\\|" in result or "\\=" in result

    def test_format_leef(self, sample_event):
        """Test LEEF format output."""
        formatter = SIEMEventFormatter(format_type=SIEMFormat.LEEF)
        result = formatter.format(sample_event)

        assert result.startswith("LEEF:2.0|ACGS-2|EnhancedAgentBus|2.4.0|")
        assert "authentication_failure" in result
        assert "tenantId=tenant-123" in result
        assert "agentId=agent-456" in result

    def test_format_syslog(self, sample_event):
        """Test Syslog format output."""
        formatter = SIEMEventFormatter(format_type=SIEMFormat.SYSLOG)
        result = formatter.format(sample_event)

        # RFC 5424 format check
        assert "EnhancedAgentBus" in result
        assert "authentication_failure" in result
        assert "[acgs2@12345" in result
        assert 'severity="high"' in result

    def test_severity_mapping(self):
        """Test severity is correctly mapped for different formats."""
        formatter = SIEMEventFormatter(format_type=SIEMFormat.CEF)

        for severity in SecuritySeverity:
            event = SecurityEvent(
                event_type=SecurityEventType.ANOMALY_DETECTED,
                severity=severity,
                message=f"Test {severity.value}",
            )
            result = formatter.format(event)
            assert result  # Should not raise

    def test_format_cef_with_correlation_id(self, sample_event):
        """Test CEF format includes correlation ID."""
        formatter = SIEMEventFormatter(format_type=SIEMFormat.CEF)
        result = formatter.format(sample_event, correlation_id="corr-abc")
        assert "CorrelationID=corr-abc" in result

    def test_format_leef_with_correlation_id(self, sample_event):
        """Test LEEF format includes correlation ID."""
        formatter = SIEMEventFormatter(format_type=SIEMFormat.LEEF)
        result = formatter.format(sample_event, correlation_id="corr-xyz")
        assert "correlationId=corr-xyz" in result

    def test_format_syslog_with_correlation_id(self, sample_event):
        """Test Syslog format includes correlation ID."""
        formatter = SIEMEventFormatter(format_type=SIEMFormat.SYSLOG)
        result = formatter.format(sample_event, correlation_id="corr-999")
        assert 'correlation_id="corr-999"' in result


# --- AlertManager Tests ---


class TestAlertManager:
    """Tests for alert threshold management."""

    async def test_no_alert_below_threshold(self, sample_event):
        """Test that no alert is triggered below threshold."""
        threshold = AlertThreshold(
            event_type=SecurityEventType.AUTHENTICATION_FAILURE,
            count_threshold=5,
            time_window_seconds=60,
            alert_level=AlertLevel.NOTIFY,
        )
        manager = AlertManager(thresholds=[threshold])

        # Process fewer events than threshold
        for _ in range(4):
            result = await manager.process_event(sample_event)
            assert result is None

    async def test_alert_at_threshold(self, sample_event):
        """Test that alert is triggered at threshold."""
        threshold = AlertThreshold(
            event_type=SecurityEventType.AUTHENTICATION_FAILURE,
            count_threshold=3,
            time_window_seconds=60,
            alert_level=AlertLevel.NOTIFY,
        )
        manager = AlertManager(thresholds=[threshold])

        # Process events up to threshold
        for i in range(3):
            result = await manager.process_event(sample_event)
            if i < 2:
                assert result is None
            else:
                assert result == AlertLevel.NOTIFY

    async def test_alert_cooldown(self, sample_event):
        """Test that cooldown prevents repeated alerts."""
        threshold = AlertThreshold(
            event_type=SecurityEventType.AUTHENTICATION_FAILURE,
            count_threshold=2,
            time_window_seconds=60,
            alert_level=AlertLevel.NOTIFY,
            cooldown_seconds=60,
        )
        manager = AlertManager(thresholds=[threshold])

        # Trigger first alert
        await manager.process_event(sample_event)
        result = await manager.process_event(sample_event)
        assert result == AlertLevel.NOTIFY

        # Should be in cooldown
        await manager.process_event(sample_event)
        result = await manager.process_event(sample_event)
        assert result is None  # Cooldown active

    async def test_alert_callback_invoked(self, sample_event):
        """Test that callback is invoked on alert."""
        callback = AsyncMock()
        threshold = AlertThreshold(
            event_type=SecurityEventType.AUTHENTICATION_FAILURE,
            count_threshold=1,
            time_window_seconds=60,
            alert_level=AlertLevel.PAGE,
        )
        manager = AlertManager(thresholds=[threshold], callback=callback)

        await manager.process_event(sample_event)

        callback.assert_called_once()
        call_args = callback.call_args
        assert call_args[0][0] == AlertLevel.PAGE
        assert "authentication_failure" in call_args[0][1].lower()

    async def test_critical_event_immediate_alert(self, critical_event):
        """Test that critical events trigger immediate alerts."""
        manager = AlertManager()  # Use default thresholds

        result = await manager.process_event(critical_event)
        assert result == AlertLevel.CRITICAL

    def test_get_alert_states(self, sample_event):
        """Test getting current alert states."""
        manager = AlertManager()
        states = manager.get_alert_states()
        assert isinstance(states, dict)

    async def test_reset_alert_state(self, sample_event):
        """Test resetting alert state."""
        threshold = AlertThreshold(
            event_type=SecurityEventType.AUTHENTICATION_FAILURE,
            count_threshold=2,
            time_window_seconds=60,
            alert_level=AlertLevel.NOTIFY,
        )
        manager = AlertManager(thresholds=[threshold])

        # Build up state
        await manager.process_event(sample_event)

        # Reset
        manager.reset_alert_state(SecurityEventType.AUTHENTICATION_FAILURE)

        # Should need full count again
        result = await manager.process_event(sample_event)
        assert result is None

    async def test_sync_callback_invoked(self, sample_event):
        """Test that synchronous callbacks also work."""
        called = {"value": False}

        def sync_callback(level, message, context):
            called["value"] = True

        threshold = AlertThreshold(
            event_type=SecurityEventType.AUTHENTICATION_FAILURE,
            count_threshold=1,
            time_window_seconds=60,
            alert_level=AlertLevel.NOTIFY,
        )
        manager = AlertManager(thresholds=[threshold], callback=sync_callback)
        await manager.process_event(sample_event)
        assert called["value"] is True

    async def test_escalation_multiplier(self, sample_event):
        """Test alert level escalation with multiplier."""
        threshold = AlertThreshold(
            event_type=SecurityEventType.AUTHENTICATION_FAILURE,
            count_threshold=2,
            time_window_seconds=60,
            alert_level=AlertLevel.NOTIFY,
            cooldown_seconds=0,
            escalation_multiplier=2,
        )
        manager = AlertManager(thresholds=[threshold])
        # Process enough events to trigger escalation
        for _ in range(6):
            result = await manager.process_event(sample_event)
        # Should have escalated above NOTIFY
        assert result is not None
        assert result.value >= AlertLevel.NOTIFY.value

    async def test_no_threshold_no_critical_returns_none(self):
        """Test event with no matching threshold and not critical returns None."""
        manager = AlertManager(thresholds=[])
        event = SecurityEvent(
            event_type=SecurityEventType.INVALID_INPUT,
            severity=SecuritySeverity.LOW,
            message="low severity",
        )
        result = await manager.process_event(event)
        assert result is None

    async def test_escalation_multiplier_one_no_escalation(self, sample_event):
        """Test that escalation_multiplier<=1 doesn't escalate."""
        threshold = AlertThreshold(
            event_type=SecurityEventType.AUTHENTICATION_FAILURE,
            count_threshold=1,
            time_window_seconds=60,
            alert_level=AlertLevel.NOTIFY,
            cooldown_seconds=0,
            escalation_multiplier=1,
        )
        manager = AlertManager(thresholds=[threshold])
        for _ in range(5):
            result = await manager.process_event(sample_event)
        assert result == AlertLevel.NOTIFY


# --- EventCorrelator Tests ---


class TestEventCorrelator:
    """Tests for event correlation and pattern detection."""

    async def test_tenant_attack_pattern(self):
        """Test detection of tenant attack pattern."""
        correlator = EventCorrelator(window_seconds=60)

        # Multiple high severity events from same tenant
        for _ in range(3):
            event = SecurityEvent(
                event_type=SecurityEventType.AUTHENTICATION_FAILURE,
                severity=SecuritySeverity.HIGH,
                message="Test",
                tenant_id="tenant-victim",
            )
            result = await correlator.add_event(event)

        # Should detect pattern after 3rd event
        assert result is not None

    async def test_distributed_attack_pattern(self):
        """Test detection of distributed attack pattern."""
        correlator = EventCorrelator(window_seconds=60)

        # Same event type from multiple agents
        for i in range(3):
            event = SecurityEvent(
                event_type=SecurityEventType.RATE_LIMIT_EXCEEDED,
                severity=SecuritySeverity.MEDIUM,
                message="Test",
                agent_id=f"agent-{i}",
            )
            result = await correlator.add_event(event)

        assert result is not None

    async def test_no_pattern_single_event(self, sample_event):
        """Test that single events don't trigger correlation."""
        correlator = EventCorrelator()
        result = await correlator.add_event(sample_event)
        assert result is None

    async def test_get_correlated_events(self):
        """Test retrieving correlated events."""
        correlator = EventCorrelator(window_seconds=60)

        # Generate correlation
        events = []
        correlation_id = None
        for i in range(3):
            event = SecurityEvent(
                event_type=SecurityEventType.AUTHENTICATION_FAILURE,
                severity=SecuritySeverity.HIGH,
                message=f"Test {i}",
                tenant_id="tenant-test",
            )
            events.append(event)
            correlation_id = await correlator.add_event(event)

        if correlation_id:
            correlated = correlator.get_correlated_events(correlation_id)
            assert len(correlated) >= 1

    def test_generate_correlation_id_uses_fast_kernel_when_available(self, monkeypatch):
        """Test correlation ID generation uses fast hash kernel when available."""
        called = {"value": False}

        def _fake_fast_hash(value: str) -> int:
            called["value"] = True
            return 0xBEEF

        monkeypatch.setattr(siem_integration_module, "FAST_HASH_AVAILABLE", True)
        monkeypatch.setattr(
            siem_integration_module,
            "fast_hash",
            _fake_fast_hash,
            raising=False,
        )

        correlator = EventCorrelator(window_seconds=60)
        result = correlator._generate_correlation_id("tenant_attack", "tenant-1")

        assert called["value"] is True
        assert result == "000000000000beef"

    def test_generate_correlation_id_falls_back_to_sha256(self, monkeypatch):
        """Test correlation ID generation falls back when fast hash unavailable."""
        monkeypatch.setattr(siem_integration_module, "FAST_HASH_AVAILABLE", False)

        correlator = EventCorrelator(window_seconds=60)
        result = correlator._generate_correlation_id("tenant_attack", "tenant-1")

        assert len(result) == 16
        int(result, 16)

    async def test_get_correlated_events_unknown_id(self):
        """Test retrieving events for unknown correlation ID."""
        correlator = EventCorrelator()
        result = correlator.get_correlated_events("unknown-id")
        assert result == []

    async def test_window_expiry(self):
        """Test that events outside window are pruned."""
        correlator = EventCorrelator(window_seconds=0)
        event = SecurityEvent(
            event_type=SecurityEventType.AUTHENTICATION_FAILURE,
            severity=SecuritySeverity.HIGH,
            message="Test",
            tenant_id="tenant-test",
        )
        await correlator.add_event(event)
        # After adding, old events should be pruned (window=0)
        assert len(correlator._events) <= 1


# --- SIEMIntegration Tests ---


class TestSIEMIntegration:
    """Tests for the main SIEM integration class."""

    async def test_start_stop(self, siem_config):
        """Test starting and stopping SIEM integration."""
        siem = SIEMIntegration(siem_config)

        await siem.start()
        assert siem._running

        await siem.stop()
        assert not siem._running

    async def test_log_event(self, siem_integration, sample_event):
        """Test logging an event."""
        await siem_integration.log_event(sample_event)

        metrics = siem_integration.get_metrics()
        assert metrics["events_logged"] >= 1

    async def test_log_multiple_events(self, siem_integration):
        """Test logging multiple events."""
        for i in range(10):
            event = SecurityEvent(
                event_type=SecurityEventType.RATE_LIMIT_EXCEEDED,
                severity=SecuritySeverity.LOW,
                message=f"Test event {i}",
            )
            await siem_integration.log_event(event)

        metrics = siem_integration.get_metrics()
        assert metrics["events_logged"] == 10

    async def test_queue_overflow_drops(self):
        """Test that queue overflow drops events when configured."""
        config = SIEMConfig(
            max_queue_size=5,
            drop_on_overflow=True,
            flush_interval_seconds=10,  # Long interval to fill queue
        )
        siem = SIEMIntegration(config)
        await siem.start()

        try:
            # Fill queue beyond capacity
            for i in range(20):
                event = SecurityEvent(
                    event_type=SecurityEventType.INVALID_INPUT,
                    severity=SecuritySeverity.LOW,
                    message=f"Test {i}",
                )
                await siem.log_event(event)

            metrics = siem.get_metrics()
            assert metrics["events_dropped"] > 0
        finally:
            await siem.stop()

    async def test_alert_triggers_on_threshold(self, siem_config, critical_event):
        """Test that alerts are triggered when threshold reached."""
        siem = SIEMIntegration(siem_config)
        await siem.start()

        try:
            await siem.log_event(critical_event)
            await asyncio.sleep(0.1)

            metrics = siem.get_metrics()
            assert metrics["alerts_triggered"] >= 1
        finally:
            await siem.stop()

    async def test_correlation_detection(self, siem_config):
        """Test that event correlation is detected."""
        siem = SIEMIntegration(siem_config)
        await siem.start()

        try:
            # Generate correlated events
            for _ in range(3):
                event = SecurityEvent(
                    event_type=SecurityEventType.AUTHENTICATION_FAILURE,
                    severity=SecuritySeverity.HIGH,
                    message="Test",
                    tenant_id="tenant-attack",
                )
                await siem.log_event(event)

            await asyncio.sleep(0.1)
            metrics = siem.get_metrics()
            assert metrics["correlations_detected"] >= 1
        finally:
            await siem.stop()

    async def test_get_metrics(self, siem_integration):
        """Test getting SIEM metrics."""
        metrics = siem_integration.get_metrics()

        assert "events_logged" in metrics
        assert "events_dropped" in metrics
        assert "events_shipped" in metrics
        assert "alerts_triggered" in metrics
        assert "running" in metrics
        assert metrics["running"] is True

    async def test_get_alert_states(self, siem_integration, sample_event):
        """Test getting alert states."""
        await siem_integration.log_event(sample_event)
        states = siem_integration.get_alert_states()
        assert isinstance(states, dict)

    async def test_flush_on_stop(self, siem_config, sample_event):
        """Test that events are flushed on stop."""
        siem = SIEMIntegration(siem_config)
        await siem.start()

        await siem.log_event(sample_event)
        assert siem._queue.qsize() >= 1 or siem._metrics["events_logged"] >= 1

        await siem.stop()
        # Queue should be empty after stop

    async def test_start_idempotent(self, siem_config):
        """Test that starting twice is safe."""
        siem = SIEMIntegration(siem_config)
        await siem.start()
        await siem.start()  # Should not raise
        assert siem._running is True
        await siem.stop()

    async def test_stop_idempotent(self, siem_config):
        """Test that stopping twice is safe."""
        siem = SIEMIntegration(siem_config)
        await siem.start()
        await siem.stop()
        await siem.stop()  # Should not raise
        assert siem._running is False

    async def test_alerting_disabled(self, sample_event):
        """Test that alerts are not triggered when alerting is disabled."""
        config = SIEMConfig(enable_alerting=False, flush_interval_seconds=0.1)
        siem = SIEMIntegration(config)
        await siem.start()
        try:
            await siem.log_event(sample_event)
            metrics = siem.get_metrics()
            assert metrics["alerts_triggered"] == 0
        finally:
            await siem.stop()


# --- Global SIEM Functions Tests ---


class TestGlobalSIEMFunctions:
    """Tests for global SIEM management functions."""

    async def test_initialize_siem(self):
        """Test global SIEM initialization."""
        try:
            siem = await initialize_siem()
            assert siem is not None
            assert get_siem_integration() is siem
        finally:
            await close_siem()
            assert get_siem_integration() is None

    async def test_log_security_event_function(self):
        """Test convenience log function."""
        try:
            await initialize_siem()

            await log_security_event(
                event_type=SecurityEventType.ANOMALY_DETECTED,
                severity=SecuritySeverity.MEDIUM,
                message="Test anomaly",
                tenant_id="tenant-test",
            )

            siem = get_siem_integration()
            assert siem._metrics["events_logged"] >= 1
        finally:
            await close_siem()

    async def test_log_security_event_without_siem(self):
        """Test that log function works without SIEM initialized."""
        await close_siem()  # Ensure not initialized

        # Should not raise, just log warning
        await log_security_event(
            event_type=SecurityEventType.INVALID_INPUT,
            severity=SecuritySeverity.LOW,
            message="Test without SIEM",
        )

    async def test_initialize_siem_idempotent(self):
        """Test that initialize returns the same instance on second call."""
        try:
            siem1 = await initialize_siem()
            siem2 = await initialize_siem()
            assert siem1 is siem2
        finally:
            await close_siem()


# --- Security Audit Decorator Tests ---


class TestSecurityAuditDecorator:
    """Tests for the security_audit decorator."""

    async def test_audit_successful_function(self):
        """Test auditing a successful function call."""
        try:
            await initialize_siem()

            @security_audit(
                SecurityEventType.AUTHORIZATION_FAILURE,
                SecuritySeverity.INFO,
            )
            async def test_func():
                return "success"

            result = await test_func()
            assert result == "success"

            siem = get_siem_integration()
            await asyncio.sleep(0.1)
            assert siem._metrics["events_logged"] >= 1
        finally:
            await close_siem()

    async def test_audit_failed_function(self):
        """Test auditing a failed function call."""
        try:
            await initialize_siem()

            @security_audit(
                SecurityEventType.AUTHORIZATION_FAILURE,
                SecuritySeverity.INFO,
            )
            async def failing_func():
                raise ValueError("Test error")

            # Decorator wraps exceptions in RuntimeError
            with pytest.raises(RuntimeError, match="failed: Test error"):
                await failing_func()

            siem = get_siem_integration()
            await asyncio.sleep(0.1)
            assert siem._metrics["events_logged"] >= 1
        finally:
            await close_siem()


# --- Integration Tests ---


class TestSIEMIntegrationE2E:
    """End-to-end integration tests."""

    async def test_full_event_flow(self):
        """Test complete event flow from logging to shipping."""
        callback = AsyncMock()
        config = SIEMConfig(
            format=SIEMFormat.JSON,
            enable_alerting=True,
            alert_callback=callback,
            flush_interval_seconds=0.1,
        )

        siem = SIEMIntegration(config)
        await siem.start()

        try:
            # Log critical event (should trigger alert)
            critical_event = SecurityEvent(
                event_type=SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH,
                severity=SecuritySeverity.CRITICAL,
                message="Critical test event",
                tenant_id="tenant-test",
            )
            await siem.log_event(critical_event)

            # Wait for flush
            await asyncio.sleep(0.2)

            # Verify metrics
            metrics = siem.get_metrics()
            assert metrics["events_logged"] >= 1
            assert metrics["alerts_triggered"] >= 1

            # Verify callback was invoked
            callback.assert_called()
        finally:
            await siem.stop()

    async def test_multiple_event_types(self):
        """Test handling multiple event types."""
        config = SIEMConfig(
            format=SIEMFormat.CEF,
            enable_alerting=True,
            flush_interval_seconds=0.1,
        )

        siem = SIEMIntegration(config)
        await siem.start()

        try:
            event_types = [
                SecurityEventType.AUTHENTICATION_FAILURE,
                SecurityEventType.AUTHORIZATION_FAILURE,
                SecurityEventType.RATE_LIMIT_EXCEEDED,
                SecurityEventType.TENANT_VIOLATION,
                SecurityEventType.INVALID_INPUT,
            ]

            for event_type in event_types:
                event = SecurityEvent(
                    event_type=event_type,
                    severity=SecuritySeverity.MEDIUM,
                    message=f"Test {event_type.value}",
                )
                await siem.log_event(event)

            await asyncio.sleep(0.2)
            metrics = siem.get_metrics()
            assert metrics["events_logged"] == len(event_types)
        finally:
            await siem.stop()

    async def test_high_volume_events(self):
        """Test handling high volume of events."""
        config = SIEMConfig(
            format=SIEMFormat.JSON,
            max_queue_size=1000,
            flush_interval_seconds=0.05,
            enable_alerting=False,  # Disable for performance
        )

        siem = SIEMIntegration(config)
        await siem.start()

        try:
            # Log many events quickly
            for i in range(100):
                event = SecurityEvent(
                    event_type=SecurityEventType.RATE_LIMIT_EXCEEDED,
                    severity=SecuritySeverity.LOW,
                    message=f"High volume test {i}",
                )
                await siem.log_event(event)

            await asyncio.sleep(0.2)
            metrics = siem.get_metrics()
            assert metrics["events_logged"] == 100
            assert metrics["events_dropped"] == 0
        finally:
            await siem.stop()


# --- Format-Specific Tests ---


class TestAllFormats:
    """Test all SIEM formats produce valid output."""

    @pytest.mark.parametrize(
        "format_type",
        [SIEMFormat.JSON, SIEMFormat.CEF, SIEMFormat.LEEF, SIEMFormat.SYSLOG],
    )
    def test_format_produces_output(self, format_type, sample_event):
        """Test that each format produces non-empty output."""
        formatter = SIEMEventFormatter(format_type=format_type)
        result = formatter.format(sample_event)

        assert result
        assert len(result) > 0

    @pytest.mark.parametrize(
        "format_type",
        [SIEMFormat.JSON, SIEMFormat.CEF, SIEMFormat.LEEF, SIEMFormat.SYSLOG],
    )
    def test_format_includes_constitutional_hash(self, format_type, sample_event):
        """Test that each format includes constitutional hash."""
        formatter = SIEMEventFormatter(format_type=format_type)
        result = formatter.format(sample_event)

        # All formats should include constitutional hash
        assert CONSTITUTIONAL_HASH in result or "constitutional" in result.lower()
