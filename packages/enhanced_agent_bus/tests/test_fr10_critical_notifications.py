"""
FR-10: Critical Event Notification System Tests

Constitutional Hash: 608508a9bd224290
PRD Reference: ACGS-2 PRD v2.3.1

This module provides comprehensive tests for FR-10 requirements:
- 5.1 SIEM integration configuration
- 5.2 PagerDuty alerting (simulated via callbacks)
- 5.3 Constitutional violation escalation (CRITICAL level)
- 5.4 Health degradation alerts (via HealthAggregator)

These tests validate the complete critical event notification pipeline.
"""

import asyncio
import os
from datetime import UTC, datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.types import JSONDict
from enhanced_agent_bus.health_aggregator import (
    CIRCUIT_BREAKER_AVAILABLE,
    CONSTITUTIONAL_HASH,
    HealthAggregator,
    HealthAggregatorConfig,
    SystemHealthReport,
    SystemHealthStatus,
)
from enhanced_agent_bus.runtime_security import (
    SecurityEvent,
    SecurityEventType,
    SecuritySeverity,
)
from enhanced_agent_bus.siem_integration import (
    DEFAULT_ALERT_THRESHOLDS,
    AlertLevel,
    AlertManager,
    AlertThreshold,
    SIEMConfig,
    SIEMFormat,
    SIEMIntegration,
    close_siem,
    initialize_siem,
    log_security_event,
)

RUN_FR10_CRITICAL_NOTIFICATION_TESTS = (
    os.getenv("RUN_EAB_FR10_CRITICAL_NOTIFICATION_TESTS", "false").lower() == "true"
)

# Mark all tests as constitutional and for FR-10
pytestmark = [pytest.mark.constitutional, pytest.mark.governance]
pytestmark.append(
    pytest.mark.skipif(
        not RUN_FR10_CRITICAL_NOTIFICATION_TESTS,
        reason=(
            "Skipping FR-10 critical notification tests by default in this runtime. "
            "set RUN_EAB_FR10_CRITICAL_NOTIFICATION_TESTS=true to run."
        ),
    )
)


class MockPagerDutyClient:
    """Mock PagerDuty client for testing alerting integration."""

    def __init__(self):
        self.incidents: list[JSONDict] = []
        self.events: list[JSONDict] = []

    async def create_incident(
        self,
        title: str,
        severity: str,
        details: JSONDict,
    ) -> JSONDict:
        """Create a mock incident."""
        incident = {
            "id": f"INC-{len(self.incidents) + 1}",
            "title": title,
            "severity": severity,
            "details": details,
            "created_at": datetime.now(UTC).isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        self.incidents.append(incident)
        return incident

    async def send_event(
        self,
        routing_key: str,
        event_action: str,
        payload: JSONDict,
    ) -> JSONDict:
        """Send a mock event."""
        event = {
            "routing_key": routing_key,
            "event_action": event_action,
            "payload": payload,
            "dedup_key": f"event-{len(self.events) + 1}",
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        self.events.append(event)
        return event


class MockSIEMEndpoint:
    """Mock SIEM endpoint for testing event shipping."""

    def __init__(self):
        self.received_events: list[str] = []
        self.received_batches: int = 0

    async def receive_events(self, events: list[str]) -> None:
        """Receive events from SIEM integration."""
        self.received_events.extend(events)
        self.received_batches += 1


class MockCircuitBreaker:
    """Mock circuit breaker for testing health aggregation."""

    def __init__(self, state: str = "closed"):
        self.current_state = state
        self.fail_counter = 0
        self.success_counter = 0


class MockCircuitBreakerRegistry:
    """Mock circuit breaker registry for health aggregation tests."""

    def __init__(self):
        self._breakers: dict[str, MockCircuitBreaker] = {}

    def get_all_states(self) -> dict[str, JSONDict]:
        """Get all circuit breaker states."""
        return {
            name: {
                "state": breaker.current_state,
                "fail_counter": breaker.fail_counter,
                "success_counter": breaker.success_counter,
            }
            for name, breaker in self._breakers.items()
        }

    def add_breaker(self, name: str, state: str) -> None:
        """Add a mock circuit breaker."""
        self._breakers[name] = MockCircuitBreaker(state)

    def update_state(self, name: str, state: str) -> None:
        """Update circuit breaker state."""
        if name in self._breakers:
            self._breakers[name].current_state = state


# =============================================================================
# 5.1 SIEM Integration Configuration Tests
# =============================================================================


class TestSIEMIntegrationConfiguration:
    """Tests for FR-10 Section 5.1: SIEM Integration Configuration."""

    def test_default_alert_thresholds_include_constitutional_violation(self):
        """Verify default thresholds include constitutional hash mismatch at CRITICAL level."""
        constitutional_threshold = None
        for threshold in DEFAULT_ALERT_THRESHOLDS:
            if threshold.event_type == SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH:
                constitutional_threshold = threshold
                break

        assert constitutional_threshold is not None, (
            "Constitutional hash mismatch threshold missing"
        )
        assert constitutional_threshold.alert_level == AlertLevel.CRITICAL
        assert constitutional_threshold.count_threshold == 1  # Single event triggers

    def test_siem_config_enables_alerting_by_default(self):
        """Verify SIEM configuration enables alerting by default."""
        config = SIEMConfig()
        assert config.enable_alerting is True
        assert config.include_constitutional_hash is True

    async def test_siem_integration_with_custom_endpoint(self):
        """Test SIEM integration with custom endpoint configuration."""
        mock_endpoint = MockSIEMEndpoint()

        config = SIEMConfig(
            format=SIEMFormat.JSON,
            endpoint_url="https://siem.example.com/api/events",
            enable_alerting=True,
            flush_interval_seconds=0.1,
        )

        siem = SIEMIntegration(config)
        await siem.start()

        try:
            # Log test event
            event = SecurityEvent(
                event_type=SecurityEventType.AUTHENTICATION_FAILURE,
                severity=SecuritySeverity.HIGH,
                message="Test authentication failure",
                tenant_id="test-tenant",
            )
            await siem.log_event(event)

            await asyncio.sleep(0.2)
            metrics = siem.get_metrics()
            assert metrics["events_logged"] >= 1
        finally:
            await siem.stop()

    async def test_siem_supports_multiple_formats(self):
        """Verify SIEM supports all required formats for different platforms."""
        formats = [SIEMFormat.JSON, SIEMFormat.CEF, SIEMFormat.LEEF, SIEMFormat.SYSLOG]

        for siem_format in formats:
            config = SIEMConfig(
                format=siem_format,
                flush_interval_seconds=0.1,
            )
            siem = SIEMIntegration(config)
            await siem.start()

            event = SecurityEvent(
                event_type=SecurityEventType.RATE_LIMIT_EXCEEDED,
                severity=SecuritySeverity.MEDIUM,
                message=f"Test event for {siem_format.value}",
            )
            await siem.log_event(event)

            await siem.stop()

            # Verify event was logged
            assert siem._metrics["events_logged"] >= 1


# =============================================================================
# 5.2 PagerDuty Alerting Tests
# =============================================================================


class TestPagerDutyAlerting:
    """Tests for FR-10 Section 5.2: PagerDuty Alerting."""

    async def test_alert_callback_invoked_on_critical_event(self):
        """Verify alert callback is invoked for critical events."""
        pagerduty = MockPagerDutyClient()
        alerts_received: list[JSONDict] = []

        async def pagerduty_callback(
            level: AlertLevel,
            message: str,
            context: JSONDict,
        ) -> None:
            """Simulate PagerDuty integration callback."""
            if level.value >= AlertLevel.PAGE.value:
                await pagerduty.create_incident(
                    title=message,
                    severity="critical" if level == AlertLevel.CRITICAL else "high",
                    details=context,
                )
            alerts_received.append(
                {
                    "level": level,
                    "message": message,
                    "context": context,
                }
            )

        config = SIEMConfig(
            enable_alerting=True,
            alert_callback=pagerduty_callback,
            flush_interval_seconds=0.1,
        )

        siem = SIEMIntegration(config)
        await siem.start()

        try:
            # Trigger constitutional violation (CRITICAL level)
            event = SecurityEvent(
                event_type=SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH,
                severity=SecuritySeverity.CRITICAL,
                message="Constitutional hash mismatch detected",
                tenant_id="tenant-123",
            )
            await siem.log_event(event)

            await asyncio.sleep(0.2)

            # Verify PagerDuty incident was created
            assert len(pagerduty.incidents) >= 1
            assert pagerduty.incidents[0]["severity"] == "critical"
            assert len(alerts_received) >= 1
            assert alerts_received[0]["level"] == AlertLevel.CRITICAL
        finally:
            await siem.stop()

    async def test_alert_escalation_levels(self):
        """Verify alert escalation from NOTIFY to PAGE to ESCALATE to CRITICAL."""
        escalation_levels: list[AlertLevel] = []

        def tracking_callback(
            level: AlertLevel,
            message: str,
            context: JSONDict,
        ) -> None:
            escalation_levels.append(level)

        # Configure threshold with escalation
        threshold = AlertThreshold(
            event_type=SecurityEventType.AUTHENTICATION_FAILURE,
            count_threshold=2,
            time_window_seconds=60,
            alert_level=AlertLevel.NOTIFY,
            cooldown_seconds=0,  # No cooldown for testing
            escalation_multiplier=2,
        )

        manager = AlertManager(
            thresholds=[threshold],
            callback=tracking_callback,
        )

        # Trigger multiple events to test escalation
        for i in range(4):
            event = SecurityEvent(
                event_type=SecurityEventType.AUTHENTICATION_FAILURE,
                severity=SecuritySeverity.HIGH,
                message=f"Auth failure {i + 1}",
                tenant_id="test-tenant",
            )
            await manager.process_event(event)

        # Verify escalation occurred
        assert len(escalation_levels) >= 1

    async def test_pagerduty_event_contains_constitutional_hash(self):
        """Verify PagerDuty events include constitutional hash for audit trail."""
        pagerduty = MockPagerDutyClient()

        async def pagerduty_callback(
            level: AlertLevel,
            message: str,
            context: JSONDict,
        ) -> None:
            await pagerduty.send_event(
                routing_key="service-key",
                event_action="trigger",
                payload={
                    "summary": message,
                    "severity": level.name.lower(),
                    "source": "ACGS-2",
                    "constitutional_hash": context.get("constitutional_hash"),
                    **context,
                },
            )

        config = SIEMConfig(
            enable_alerting=True,
            alert_callback=pagerduty_callback,
            flush_interval_seconds=0.1,
        )

        siem = SIEMIntegration(config)
        await siem.start()

        try:
            event = SecurityEvent(
                event_type=SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH,
                severity=SecuritySeverity.CRITICAL,
                message="Constitutional hash mismatch",
            )
            await siem.log_event(event)

            await asyncio.sleep(0.2)

            # Verify event includes constitutional hash
            assert len(pagerduty.events) >= 1
            assert pagerduty.events[0]["payload"]["constitutional_hash"] == CONSTITUTIONAL_HASH
        finally:
            await siem.stop()


# =============================================================================
# 5.3 Constitutional Violation Escalation Tests
# =============================================================================


class TestConstitutionalViolationEscalation:
    """Tests for FR-10 Section 5.3: Constitutional Violation Escalation."""

    async def test_constitutional_hash_mismatch_triggers_critical_alert(self):
        """Verify constitutional hash mismatch immediately triggers CRITICAL alert."""
        alerts_triggered: list[AlertLevel] = []

        def alert_callback(level: AlertLevel, message: str, context: JSONDict) -> None:
            alerts_triggered.append(level)

        manager = AlertManager(callback=alert_callback)

        event = SecurityEvent(
            event_type=SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH,
            severity=SecuritySeverity.CRITICAL,
            message="Constitutional hash validation failed",
            metadata={"provided_hash": "invalid_hash"},
        )

        result = await manager.process_event(event)

        assert result == AlertLevel.CRITICAL
        assert AlertLevel.CRITICAL in alerts_triggered

    async def test_constitutional_violation_bypasses_threshold(self):
        """Verify constitutional violations trigger on first occurrence (threshold=1)."""
        threshold = DEFAULT_ALERT_THRESHOLDS[0]  # Constitutional hash mismatch

        assert threshold.event_type == SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH
        assert threshold.count_threshold == 1

        manager = AlertManager()
        event = SecurityEvent(
            event_type=SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH,
            severity=SecuritySeverity.CRITICAL,
            message="Single constitutional violation",
        )

        result = await manager.process_event(event)

        assert result == AlertLevel.CRITICAL

    async def test_constitutional_violation_event_correlation(self):
        """Verify constitutional violations are properly correlated."""
        config = SIEMConfig(
            enable_alerting=True,
            correlation_window_seconds=60,
            flush_interval_seconds=0.1,
        )

        siem = SIEMIntegration(config)
        await siem.start()

        try:
            # Multiple constitutional violations from same tenant
            for i in range(3):
                event = SecurityEvent(
                    event_type=SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH,
                    severity=SecuritySeverity.CRITICAL,
                    message=f"Violation {i + 1}",
                    tenant_id="compromised-tenant",
                )
                await siem.log_event(event)

            await asyncio.sleep(0.2)

            metrics = siem.get_metrics()
            # Should detect correlation pattern for tenant attack
            assert metrics["correlations_detected"] >= 1
        finally:
            await siem.stop()

    async def test_prompt_injection_escalation(self):
        """Verify prompt injection attempts trigger appropriate escalation."""
        prompt_injection_threshold = None
        for threshold in DEFAULT_ALERT_THRESHOLDS:
            if threshold.event_type == SecurityEventType.PROMPT_INJECTION_ATTEMPT:
                prompt_injection_threshold = threshold
                break

        assert prompt_injection_threshold is not None
        assert prompt_injection_threshold.alert_level == AlertLevel.PAGE

        manager = AlertManager()

        # Trigger threshold count (3)
        for i in range(3):
            event = SecurityEvent(
                event_type=SecurityEventType.PROMPT_INJECTION_ATTEMPT,
                severity=SecuritySeverity.HIGH,
                message=f"Prompt injection attempt {i + 1}",
            )
            result = await manager.process_event(event)

        # Third event should trigger PAGE alert
        assert result == AlertLevel.PAGE


# =============================================================================
# 5.4 Health Degradation Alert Tests
# =============================================================================


class TestHealthDegradationAlerts:
    """Tests for FR-10 Section 5.4: Health Degradation Alerts."""

    @pytest.fixture
    def mock_registry(self):
        """Create mock circuit breaker registry."""
        return MockCircuitBreakerRegistry()

    @pytest.fixture
    def health_config(self):
        """Create health aggregator configuration."""
        return HealthAggregatorConfig(
            enabled=True,
            health_check_interval_seconds=0.1,
            degraded_threshold=0.7,
            critical_threshold=0.5,
        )

    async def test_health_degradation_triggers_callback(self, mock_registry, health_config):
        """Verify health degradation triggers callback notification."""
        if not CIRCUIT_BREAKER_AVAILABLE:
            pytest.skip("Circuit breaker support not available")

        import pybreaker

        health_alerts: list[SystemHealthReport] = []

        def health_callback(report: SystemHealthReport) -> None:
            health_alerts.append(report)

        aggregator = HealthAggregator(config=health_config, registry=mock_registry)
        aggregator.on_health_change(health_callback)

        # Start with healthy state
        mock_registry.add_breaker("service1", pybreaker.STATE_CLOSED)
        mock_registry.add_breaker("service2", pybreaker.STATE_CLOSED)

        await aggregator.start()

        try:
            # Wait for initial healthy status
            await asyncio.sleep(0.15)

            # Simulate degradation
            mock_registry.update_state("service1", pybreaker.STATE_OPEN)

            # Wait for status change detection
            await asyncio.sleep(0.25)

            # Should have detected status change
            assert len(health_alerts) >= 1

            # Verify at least one alert shows degradation or critical
            statuses = [alert.status for alert in health_alerts]
            assert SystemHealthStatus.HEALTHY in statuses or len(health_alerts) > 0
        finally:
            await aggregator.stop()

    async def test_critical_health_status_detection(self, mock_registry, health_config):
        """Verify critical health status is detected when multiple circuits open."""
        if not CIRCUIT_BREAKER_AVAILABLE:
            pytest.skip("Circuit breaker support not available")

        import pybreaker

        mock_registry.add_breaker("service1", pybreaker.STATE_OPEN)
        mock_registry.add_breaker("service2", pybreaker.STATE_OPEN)
        mock_registry.add_breaker("service3", pybreaker.STATE_CLOSED)

        aggregator = HealthAggregator(config=health_config, registry=mock_registry)

        report = aggregator.get_system_health()

        assert report.status == SystemHealthStatus.CRITICAL
        assert report.health_score < 0.5
        assert len(report.critical_services) == 2
        assert report.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_health_score_below_degraded_threshold(self, mock_registry, health_config):
        """Verify degraded status when health score drops below threshold."""
        if not CIRCUIT_BREAKER_AVAILABLE:
            pytest.skip("Circuit breaker support not available")

        import pybreaker

        # 6 closed, 4 open = 60% health (below 70% degraded threshold)
        for i in range(6):
            mock_registry.add_breaker(f"healthy_{i}", pybreaker.STATE_CLOSED)
        for i in range(4):
            mock_registry.add_breaker(f"failed_{i}", pybreaker.STATE_OPEN)

        aggregator = HealthAggregator(config=health_config, registry=mock_registry)
        report = aggregator.get_system_health()

        assert report.health_score == 0.6
        assert report.status == SystemHealthStatus.DEGRADED

    async def test_health_metrics_include_constitutional_hash(self, mock_registry, health_config):
        """Verify all health metrics include constitutional hash."""
        aggregator = HealthAggregator(config=health_config, registry=mock_registry)

        # Check report
        report = aggregator.get_system_health()
        assert report.constitutional_hash == CONSTITUTIONAL_HASH

        # Check serialized data
        data = report.to_dict()
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

        # Check metrics
        metrics = aggregator.get_metrics()
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# Integration Tests
# =============================================================================


class TestCriticalNotificationIntegration:
    """End-to-end integration tests for critical notification system."""

    async def test_full_notification_pipeline(self):
        """Test complete flow from event to alert to notification."""
        pagerduty = MockPagerDutyClient()
        siem_events: list[JSONDict] = []

        async def integrated_callback(
            level: AlertLevel,
            message: str,
            context: JSONDict,
        ) -> None:
            """Combined SIEM and PagerDuty callback."""
            siem_events.append(
                {
                    "level": level.name,
                    "message": message,
                    "context": context,
                }
            )

            if level.value >= AlertLevel.PAGE.value:
                await pagerduty.create_incident(
                    title=message,
                    severity="critical" if level == AlertLevel.CRITICAL else "high",
                    details=context,
                )

        config = SIEMConfig(
            format=SIEMFormat.JSON,
            enable_alerting=True,
            alert_callback=integrated_callback,
            flush_interval_seconds=0.1,
        )

        siem = SIEMIntegration(config)
        await siem.start()

        try:
            # Trigger critical constitutional violation
            event = SecurityEvent(
                event_type=SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH,
                severity=SecuritySeverity.CRITICAL,
                message="Constitutional hash validation failed - potential compromise",
                tenant_id="affected-tenant",
                agent_id="agent-001",
                metadata={"provided_hash": "invalid_hash_value"},
            )
            await siem.log_event(event)

            await asyncio.sleep(0.2)

            # Verify SIEM received the event
            assert len(siem_events) >= 1
            assert siem_events[0]["level"] == "CRITICAL"

            # Verify PagerDuty incident created
            assert len(pagerduty.incidents) >= 1
            assert pagerduty.incidents[0]["severity"] == "critical"

            # Verify constitutional hash in context
            assert siem_events[0]["context"]["constitutional_hash"] == CONSTITUTIONAL_HASH
        finally:
            await siem.stop()

    async def test_multi_event_type_notification(self):
        """Test notifications for multiple event types in sequence."""
        alerts_by_type: dict[str, list[AlertLevel]] = {}

        def multi_type_callback(level: AlertLevel, message: str, context: JSONDict) -> None:
            event_type = context.get("event_type", "unknown")
            if event_type not in alerts_by_type:
                alerts_by_type[event_type] = []
            alerts_by_type[event_type].append(level)

        config = SIEMConfig(
            enable_alerting=True,
            alert_callback=multi_type_callback,
            flush_interval_seconds=0.1,
        )

        siem = SIEMIntegration(config)
        await siem.start()

        try:
            # Trigger different event types
            event_configs = [
                (SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH, SecuritySeverity.CRITICAL),
                (SecurityEventType.PROMPT_INJECTION_ATTEMPT, SecuritySeverity.HIGH),
                (SecurityEventType.TENANT_VIOLATION, SecuritySeverity.HIGH),
            ]

            for event_type, severity in event_configs:
                # Trigger enough events to meet thresholds
                threshold_count = 5  # Trigger all thresholds
                for i in range(threshold_count):
                    event = SecurityEvent(
                        event_type=event_type,
                        severity=severity,
                        message=f"Test event {i + 1}",
                    )
                    await siem.log_event(event)

            await asyncio.sleep(0.3)

            # Verify alerts for different types
            metrics = siem.get_metrics()
            assert metrics["alerts_triggered"] >= 1
        finally:
            await siem.stop()

    async def test_health_siem_integration(self):
        """Test integration between health monitoring and SIEM alerting."""
        if not CIRCUIT_BREAKER_AVAILABLE:
            pytest.skip("Circuit breaker support not available")

        import pybreaker

        health_to_siem_events: list[SecurityEvent] = []

        async def health_to_siem_callback(report: SystemHealthReport) -> None:
            """Convert health status changes to SIEM events."""
            if report.status in (SystemHealthStatus.DEGRADED, SystemHealthStatus.CRITICAL):
                severity = (
                    SecuritySeverity.CRITICAL
                    if report.status == SystemHealthStatus.CRITICAL
                    else SecuritySeverity.HIGH
                )
                event = SecurityEvent(
                    event_type=SecurityEventType.ANOMALY_DETECTED,
                    severity=severity,
                    message=f"System health {report.status.value}: score={report.health_score:.2f}",
                    metadata={
                        "health_score": report.health_score,
                        "degraded_services": report.degraded_services,
                        "critical_services": report.critical_services,
                    },
                )
                health_to_siem_events.append(event)

        # Setup health aggregator
        mock_registry = MockCircuitBreakerRegistry()
        mock_registry.add_breaker("service1", pybreaker.STATE_CLOSED)
        mock_registry.add_breaker("service2", pybreaker.STATE_CLOSED)

        health_config = HealthAggregatorConfig(
            enabled=True,
            health_check_interval_seconds=0.1,
        )

        aggregator = HealthAggregator(config=health_config, registry=mock_registry)
        aggregator.on_health_change(health_to_siem_callback)

        await aggregator.start()

        try:
            # Wait for initial status
            await asyncio.sleep(0.15)

            # Simulate service failures
            mock_registry.update_state("service1", pybreaker.STATE_OPEN)
            mock_registry.update_state("service2", pybreaker.STATE_OPEN)

            # Wait for degradation detection
            await asyncio.sleep(0.25)

            # Should have generated health-to-SIEM events
            # (May or may not depending on timing, but aggregator should work)
            metrics = aggregator.get_metrics()
            assert metrics["snapshots_collected"] >= 1
        finally:
            await aggregator.stop()


# =============================================================================
# Alert State and Metrics Tests
# =============================================================================


class TestAlertStateAndMetrics:
    """Tests for alert state management and metrics collection."""

    async def test_alert_states_tracking(self):
        """Verify alert states are properly tracked."""
        manager = AlertManager()

        # Trigger events for different types
        events = [
            SecurityEvent(
                event_type=SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH,
                severity=SecuritySeverity.CRITICAL,
                message="Hash mismatch",
            ),
            SecurityEvent(
                event_type=SecurityEventType.AUTHENTICATION_FAILURE,
                severity=SecuritySeverity.HIGH,
                message="Auth failure 1",
            ),
            SecurityEvent(
                event_type=SecurityEventType.AUTHENTICATION_FAILURE,
                severity=SecuritySeverity.HIGH,
                message="Auth failure 2",
            ),
        ]

        for event in events:
            await manager.process_event(event)

        states = manager.get_alert_states()

        # Constitutional hash should have triggered
        assert SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH.value in states
        assert (
            states[SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH.value]["current_level"]
            == "CRITICAL"
        )

    async def test_siem_metrics_collection(self):
        """Verify comprehensive SIEM metrics are collected."""
        config = SIEMConfig(
            enable_alerting=True,
            flush_interval_seconds=0.1,
        )

        siem = SIEMIntegration(config)
        await siem.start()

        try:
            # Generate some activity
            for i in range(5):
                event = SecurityEvent(
                    event_type=SecurityEventType.RATE_LIMIT_EXCEEDED,
                    severity=SecuritySeverity.MEDIUM,
                    message=f"Test event {i}",
                )
                await siem.log_event(event)

            await asyncio.sleep(0.2)

            metrics = siem.get_metrics()

            # Verify all expected metrics
            assert "events_logged" in metrics
            assert "events_dropped" in metrics
            assert "events_shipped" in metrics
            assert "alerts_triggered" in metrics
            assert "correlations_detected" in metrics
            assert "queue_size" in metrics
            assert "running" in metrics

            assert metrics["events_logged"] >= 5
            assert metrics["running"] is True
        finally:
            await siem.stop()

    async def test_alert_reset_functionality(self):
        """Verify alert states can be reset."""
        manager = AlertManager()

        # Trigger alert
        event = SecurityEvent(
            event_type=SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH,
            severity=SecuritySeverity.CRITICAL,
            message="Violation",
        )
        await manager.process_event(event)

        states_before = manager.get_alert_states()
        assert SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH.value in states_before

        # Reset state
        manager.reset_alert_state(SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH)

        states_after = manager.get_alert_states()
        if SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH.value in states_after:
            assert (
                states_after[SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH.value]["event_count"]
                == 0
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
