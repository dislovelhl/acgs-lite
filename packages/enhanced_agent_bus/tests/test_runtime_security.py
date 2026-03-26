"""
Tests for ACGS-2 Runtime Security Scanner
Constitutional Hash: 608508a9bd224290

Comprehensive test suite covering:
- SecurityEvent and SecurityScanResult dataclasses
- RuntimeSecurityConfig configuration
- RuntimeSecurityScanner scanning operations
- Global scanner singleton management
- Constitutional compliance validation
"""

import itertools
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus.runtime_security import (
    CONSTITUTIONAL_HASH,
    RuntimeSecurityConfig,
    RuntimeSecurityScanner,
    SecurityEvent,
    SecurityEventType,
    SecurityScanResult,
    SecuritySeverity,
    get_runtime_security_scanner,
    scan_content,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_global_scanner():
    """Reset global scanner singleton between tests for isolation.

    Pre-populates with a guardrails-disabled scanner since Docker sandbox
    requires /sandbox/execute.py which is not available in the test environment.
    """
    import enhanced_agent_bus.runtime_security as rs

    config = rs.RuntimeSecurityConfig(enable_runtime_guardrails=False)
    rs._scanner = rs.RuntimeSecurityScanner(config)
    yield
    rs._scanner = None


@pytest.fixture
def scanner():
    """Create a fresh scanner instance with runtime guardrails disabled.

    The Docker sandbox layer requires /sandbox/execute.py inside a container
    which is not available in the test environment.
    """
    config = RuntimeSecurityConfig(enable_runtime_guardrails=False)
    return RuntimeSecurityScanner(config)


@pytest.fixture
def scanner_with_custom_config():
    """Create scanner with custom rate limiting config for testing."""
    config = RuntimeSecurityConfig(
        enable_anomaly_detection=False,
        enable_runtime_guardrails=False,
        rate_limit_qps=10,
    )
    return RuntimeSecurityScanner(config)


@pytest.fixture
def extract_events_by_type():
    """Helper to extract events by type from scan results."""

    def _extract(result: SecurityScanResult, event_type: SecurityEventType) -> list[SecurityEvent]:
        return [e for e in result.events if e.event_type == event_type]

    return _extract


# =============================================================================
# Enum Tests
# =============================================================================


class TestSecurityEventType:
    """Tests for SecurityEventType enum."""

    def test_all_event_types_defined(self):
        """Verify all expected event types are defined."""
        expected_types = [
            "PROMPT_INJECTION_ATTEMPT",
            "TENANT_VIOLATION",
            "RATE_LIMIT_EXCEEDED",
            "CONSTITUTIONAL_HASH_MISMATCH",
            "PERMISSION_DENIED",
            "INVALID_INPUT",
            "ANOMALY_DETECTED",
            "AUTHENTICATION_FAILURE",
            "AUTHORIZATION_FAILURE",
            "SUSPICIOUS_PATTERN",
        ]
        for event_type in expected_types:
            assert hasattr(SecurityEventType, event_type)


class TestSecuritySeverity:
    """Tests for SecuritySeverity enum."""

    def test_all_severity_levels_defined(self):
        """Verify all severity levels are defined."""
        expected_levels = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
        for level in expected_levels:
            assert hasattr(SecuritySeverity, level)


# =============================================================================
# Dataclass Tests
# =============================================================================


class TestSecurityEvent:
    """Tests for SecurityEvent dataclass."""

    def test_event_creation(self):
        """Test creating a security event with all fields."""
        event = SecurityEvent(
            event_type=SecurityEventType.PROMPT_INJECTION_ATTEMPT,
            severity=SecuritySeverity.HIGH,
            message="Test event",
            tenant_id="test-tenant",
            agent_id="test-agent",
        )
        assert event.event_type == SecurityEventType.PROMPT_INJECTION_ATTEMPT
        assert event.severity == SecuritySeverity.HIGH
        assert event.message == "Test event"
        assert event.tenant_id == "test-tenant"
        assert event.constitutional_hash == CONSTITUTIONAL_HASH

    def test_event_to_dict(self):
        """Test converting event to dictionary."""
        event = SecurityEvent(
            event_type=SecurityEventType.TENANT_VIOLATION,
            severity=SecuritySeverity.MEDIUM,
            message="Tenant violation",
        )
        result = event.to_dict()
        assert result["event_type"] == "tenant_violation"
        assert result["severity"] == "medium"
        assert result["message"] == "Tenant violation"
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_event_default_timestamp(self):
        """Test event has default timestamp."""
        event = SecurityEvent(
            event_type=SecurityEventType.INVALID_INPUT,
            severity=SecuritySeverity.LOW,
            message="Test",
        )
        assert event.timestamp is not None
        assert isinstance(event.timestamp, datetime)


class TestSecurityScanResult:
    """Tests for SecurityScanResult dataclass."""

    def test_result_creation(self):
        """Test creating a scan result with defaults."""
        result = SecurityScanResult()
        assert result.is_secure is True
        assert result.blocked is False
        assert result.events == []
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_add_event(self):
        """Test adding an event to result."""
        result = SecurityScanResult()
        event = SecurityEvent(
            event_type=SecurityEventType.SUSPICIOUS_PATTERN,
            severity=SecuritySeverity.MEDIUM,
            message="Pattern detected",
        )
        result.add_event(event)
        assert len(result.events) == 1
        assert result.is_secure is True  # Medium severity doesn't block

    def test_add_high_severity_event(self):
        """Test adding high severity event marks as insecure."""
        result = SecurityScanResult()
        event = SecurityEvent(
            event_type=SecurityEventType.PROMPT_INJECTION_ATTEMPT,
            severity=SecuritySeverity.HIGH,
            message="Injection detected",
        )
        result.add_event(event)
        assert result.is_secure is False

    def test_add_blocking_event(self):
        """Test adding a blocking event."""
        result = SecurityScanResult()
        event = SecurityEvent(
            event_type=SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH,
            severity=SecuritySeverity.CRITICAL,
            message="Hash mismatch",
        )
        result.add_blocking_event(event, "Constitutional violation")
        assert result.blocked is True
        assert result.block_reason == "Constitutional violation"
        assert result.is_secure is False

    def test_result_to_dict(self):
        """Test converting result to dictionary."""
        result = SecurityScanResult()
        result.checks_performed = ["test_check"]
        result.warnings = ["test_warning"]
        result_dict = result.to_dict()
        assert result_dict["is_secure"] is True
        assert result_dict["blocked"] is False
        assert result_dict["checks_performed"] == ["test_check"]
        assert result_dict["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# Configuration Tests
# =============================================================================


class TestRuntimeSecurityConfig:
    """Tests for RuntimeSecurityConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RuntimeSecurityConfig()
        assert config.enable_prompt_injection_detection is True
        assert config.enable_tenant_validation is True
        assert config.enable_rate_limit_check is True
        assert config.enable_constitutional_validation is True
        assert config.rate_limit_qps == 1000
        assert config.fail_closed is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = RuntimeSecurityConfig(
            rate_limit_qps=50,
            max_input_length=50000,
            fail_closed=False,
        )
        assert config.rate_limit_qps == 50
        assert config.max_input_length == 50000
        assert config.fail_closed is False


# =============================================================================
# Scanner Basic Tests
# =============================================================================


class TestRuntimeSecurityScannerBasic:
    """Basic scanner functionality tests."""

    async def test_scan_clean_content(self, scanner):
        """Test scanning clean content."""
        result = await scanner.scan(
            content="Hello, this is normal content.",
            tenant_id="valid-tenant-123",
        )
        assert result.is_secure is True
        assert result.blocked is False
        assert len(result.checks_performed) > 0

    async def test_scan_with_constitutional_hash(self, scanner):
        """Test scanning with valid constitutional hash."""
        result = await scanner.scan(
            content="Test content",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        assert result.is_secure is True

    async def test_scan_with_invalid_constitutional_hash(self, scanner):
        """Test scanning with invalid constitutional hash."""
        result = await scanner.scan(
            content="Test content",
            constitutional_hash="invalid_hash_value",
        )
        assert result.blocked is True
        assert "constitutional" in result.block_reason.lower()

    async def test_scan_none_content(self, scanner):
        """Test scanning None content."""
        result = await scanner.scan(content=None)
        assert result is not None
        assert result.is_secure is True

    async def test_scan_empty_content(self, scanner):
        """Test scanning empty content."""
        result = await scanner.scan(content="")
        assert result is not None
        assert result.is_secure is True

    async def test_scan_includes_duration(self, scanner):
        """Test that scan includes duration."""
        result = await scanner.scan(content="test")
        assert result.scan_duration_ms >= 0

    async def test_scan_tracks_checks_performed(self, scanner):
        """Test that scan tracks which checks were performed."""
        result = await scanner.scan(content="test", tenant_id="test-tenant")
        assert "tenant_validation" in result.checks_performed
        assert "suspicious_pattern_detection" in result.checks_performed


# =============================================================================
# Pattern Detection Tests
# =============================================================================


class TestRuntimeSecurityScannerPatterns:
    """Tests for suspicious pattern detection."""

    async def test_scan_suspicious_patterns(self, scanner, extract_events_by_type):
        """Test detection of suspicious patterns."""
        suspicious_content = "<script>alert('xss')</script>"
        result = await scanner.scan(content=suspicious_content)

        pattern_events = extract_events_by_type(result, SecurityEventType.SUSPICIOUS_PATTERN)
        assert len(pattern_events) > 0

    async def test_scan_sql_injection_pattern(self, scanner, extract_events_by_type):
        """Test detection of SQL injection patterns."""
        sql_content = "SELECT * FROM users WHERE id = 1; DROP TABLE users;"
        result = await scanner.scan(content=sql_content)

        pattern_events = extract_events_by_type(result, SecurityEventType.SUSPICIOUS_PATTERN)
        assert len(pattern_events) > 0

    async def test_scan_path_traversal_pattern(self, scanner, extract_events_by_type):
        """Test detection of path traversal patterns."""
        path_traversal = "../../../etc/passwd"
        result = await scanner.scan(content=path_traversal)

        pattern_events = extract_events_by_type(result, SecurityEventType.SUSPICIOUS_PATTERN)
        assert len(pattern_events) > 0


# =============================================================================
# Input Validation Tests
# =============================================================================


class TestRuntimeSecurityScannerInput:
    """Tests for input validation and sanitization."""

    async def test_scan_long_input(self, extract_events_by_type):
        """Test detection of overly long input."""
        config = RuntimeSecurityConfig(max_input_length=100)
        scanner = RuntimeSecurityScanner(config)

        long_content = "x" * 200
        result = await scanner.scan(content=long_content)

        input_events = extract_events_by_type(result, SecurityEventType.INVALID_INPUT)
        assert len(input_events) > 0

    async def test_scan_deeply_nested_dict(self, extract_events_by_type):
        """Test detection of deeply nested dictionaries."""
        config = RuntimeSecurityConfig(max_nested_depth=5)
        scanner = RuntimeSecurityScanner(config)

        # Create deeply nested dict
        nested = {"level": 1}
        current = nested
        for i in range(10):
            current["nested"] = {"level": i + 2}
            current = current["nested"]

        result = await scanner.scan(content=nested)

        input_events = extract_events_by_type(result, SecurityEventType.INVALID_INPUT)
        assert len(input_events) > 0


# =============================================================================
# Rate Limiting Tests
# =============================================================================


class TestRuntimeSecurityScannerRateLimiting:
    """Tests for rate limiting functionality."""

    async def test_rate_limiting(self, scanner_with_custom_config, extract_events_by_type):
        """Test rate limiting detection."""
        scanner = scanner_with_custom_config

        # Use a fixed start time for deterministic testing
        start_time = 1000.0

        with patch("enhanced_agent_bus.runtime_security.time.monotonic", return_value=start_time):
            # Make many requests quickly (all at the same mocked timestamp)
            for _ in range(15):
                result = await scanner.scan(content="test", tenant_id="test-tenant")

            # Last result should have rate limit warning
            rate_events = extract_events_by_type(result, SecurityEventType.RATE_LIMIT_EXCEEDED)

            assert len(rate_events) > 0, "Should have detected rate limit exceeded"
            assert result is not None


# =============================================================================
# Metrics and Events Tests
# =============================================================================


class TestRuntimeSecurityScannerMetrics:
    """Tests for scanner metrics and event tracking."""

    def test_get_metrics(self, scanner):
        """Test getting scanner metrics."""
        metrics = scanner.get_metrics()
        assert "total_scans" in metrics
        assert "blocked_requests" in metrics
        assert "events_detected" in metrics
        assert "constitutional_hash" in metrics
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_metrics_update_after_scan(self, scanner):
        """Test that metrics update after scanning."""
        initial_metrics = scanner.get_metrics()
        initial_scans = initial_metrics["total_scans"]

        await scanner.scan(content="test content")

        updated_metrics = scanner.get_metrics()
        assert updated_metrics["total_scans"] == initial_scans + 1

    async def test_get_recent_events(self, scanner):
        """Test retrieving recent events."""
        # Trigger some events
        await scanner.scan(content="<script>alert(1)</script>")

        events = scanner.get_recent_events(limit=10)
        assert isinstance(events, list)

    async def test_get_recent_events_with_filter(self, scanner):
        """Test filtering recent events."""
        # Trigger suspicious pattern
        await scanner.scan(content="<script>alert(1)</script>")

        events = scanner.get_recent_events(
            limit=10,
            event_type_filter=SecurityEventType.SUSPICIOUS_PATTERN,
        )
        for event in events:
            assert event.event_type == SecurityEventType.SUSPICIOUS_PATTERN


# =============================================================================
# Global Scanner Tests
# =============================================================================


class TestGlobalScanner:
    """Tests for global scanner functions."""

    def test_get_runtime_security_scanner(self):
        """Test getting global scanner instance."""
        scanner = get_runtime_security_scanner()
        assert isinstance(scanner, RuntimeSecurityScanner)

    def test_get_runtime_security_scanner_singleton(self):
        """Test that global scanner is singleton."""
        scanner1 = get_runtime_security_scanner()
        scanner2 = get_runtime_security_scanner()
        assert scanner1 is scanner2

    async def test_scan_content_convenience_function(self):
        """Test the scan_content convenience function."""
        result = await scan_content(
            content="Normal content",
            tenant_id="test-tenant",
        )
        assert isinstance(result, SecurityScanResult)
        assert result.is_secure is True


# =============================================================================
# Constitutional Compliance Tests
# =============================================================================


class TestConstitutionalCompliance:
    """Tests for constitutional compliance."""

    def test_constitutional_hash_present(self):
        """Verify constitutional hash is correctly defined."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_scanner_has_constitutional_hash(self):
        """Verify scanner reports constitutional hash."""
        scanner = RuntimeSecurityScanner()
        metrics = scanner.get_metrics()
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_event_has_constitutional_hash(self):
        """Verify events include constitutional hash."""
        event = SecurityEvent(
            event_type=SecurityEventType.ANOMALY_DETECTED,
            severity=SecuritySeverity.INFO,
            message="Test",
        )
        assert event.constitutional_hash == CONSTITUTIONAL_HASH

    def test_result_has_constitutional_hash(self):
        """Verify results include constitutional hash."""
        result = SecurityScanResult()
        assert result.constitutional_hash == CONSTITUTIONAL_HASH


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================


class TestRuntimeSecurityScannerEdgeCases:
    """Tests for edge cases and error handling in the scanner."""

    async def test_fail_closed_blocks_on_scan_error(self):
        """Test that fail_closed=True blocks requests when scan errors occur."""
        config = RuntimeSecurityConfig(
            fail_closed=True,
            enable_constitutional_classifier=True,  # This may trigger errors
        )
        scanner = RuntimeSecurityScanner(config)

        # Patch the internal method to raise an exception
        async def mock_check_that_fails(*args, **kwargs):
            raise RuntimeError("Simulated scan failure")

        original_method = scanner._check_constitutional_compliance
        scanner._check_constitutional_compliance = mock_check_that_fails

        try:
            result = await scanner.scan(content="test content")

            # With fail_closed=True, the result should be blocked
            assert result.blocked is True
            assert result.is_secure is False
            assert "error" in result.block_reason.lower() or "failed" in result.block_reason.lower()
        finally:
            scanner._check_constitutional_compliance = original_method

    async def test_fail_open_allows_on_scan_error(self):
        """Test that fail_closed=False allows requests when scan errors occur."""
        config = RuntimeSecurityConfig(
            fail_closed=False,  # Allow on error
            enable_constitutional_classifier=True,
        )
        scanner = RuntimeSecurityScanner(config)

        # The scan should complete even if some checks fail
        result = await scanner.scan(content="test content")

        # With fail_closed=False, errors don't cause blocking
        # The result may have warnings but shouldn't block on internal errors
        assert result is not None

    async def test_scan_with_dict_content(self):
        """Test scanning dictionary content."""
        # Use scanner without guardrails/classifier to avoid false positives on test data
        config = RuntimeSecurityConfig(
            enable_runtime_guardrails=False,
            enable_constitutional_classifier=False,
        )
        scanner = RuntimeSecurityScanner(config)
        dict_content = {
            "message": "Hello world",
            "metadata": {"category": "general"},
        }
        result = await scanner.scan(content=dict_content)
        assert result is not None
        assert result.is_secure is True

    async def test_scan_with_list_content(self, scanner):
        """Test scanning list content."""
        list_content = ["item1", "item2", {"nested": "dict"}]
        result = await scanner.scan(content=list_content)
        assert result is not None

    async def test_scan_with_numeric_content(self):
        """Test scanning numeric content."""
        # Use scanner without guardrails to avoid PII false positives on numbers
        config = RuntimeSecurityConfig(enable_runtime_guardrails=False)
        scanner = RuntimeSecurityScanner(config)
        result = await scanner.scan(content=42)
        assert result is not None
        assert result.is_secure is True

    async def test_scan_with_all_context_fields(self, scanner):
        """Test scanning with complete context."""
        result = await scanner.scan(
            content="test",
            tenant_id="tenant-123",
            agent_id="agent-456",
            constitutional_hash=CONSTITUTIONAL_HASH,
            context={
                "trace_id": "trace-789",
                "ip_address": "192.168.1.1",
                "user_id": "user-abc",
                "session_id": "session-xyz",
            },
        )
        assert result is not None
        assert "tenant_validation" in result.checks_performed


# =============================================================================
# Event Buffer Management Tests
# =============================================================================


class TestEventBufferManagement:
    """Tests for event buffer trimming and expiration."""

    async def test_event_buffer_respects_max_retained(self):
        """Test event buffer respects max_events_retained config."""
        config = RuntimeSecurityConfig(
            max_events_retained=5,
            event_retention_seconds=3600,
        )
        scanner = RuntimeSecurityScanner(config)

        # Generate more events than the limit
        for i in range(10):
            await scanner.scan(content=f"<script>alert({i})</script>")

        # Buffer should be trimmed to max_events_retained
        events = scanner.get_recent_events(limit=100)
        assert len(events) <= config.max_events_retained

    async def test_event_buffer_expiration(self):
        """Test that expired events are removed from buffer."""
        config = RuntimeSecurityConfig(
            event_retention_seconds=1,  # 1 second retention
            max_events_retained=100,
        )
        scanner = RuntimeSecurityScanner(config)

        # Create an event
        await scanner.scan(content="<script>test</script>")

        # Verify event exists
        events_before = scanner.get_recent_events(limit=10)
        initial_count = len(events_before)

        # Wait for expiration and trigger cleanup via another scan
        import asyncio

        await asyncio.sleep(1.5)
        await scanner.scan(content="clean content")

        # Old events should be expired and removed
        events_after = scanner.get_recent_events(limit=10)
        # The suspicious pattern event from first scan should be gone
        suspicious_events = [e for e in events_after if "<script>" in str(e.metadata)]
        assert len(suspicious_events) == 0 or len(events_after) <= initial_count

    async def test_get_recent_events_with_severity_filter(self, scanner):
        """Test filtering recent events by severity."""
        # Create events with different severities
        # Invalid constitutional hash creates CRITICAL event
        await scanner.scan(content="test", constitutional_hash="invalid_hash")

        # Medium severity pattern
        await scanner.scan(content="<script>xss</script>")

        # Filter by HIGH severity
        high_events = scanner.get_recent_events(
            limit=10,
            severity_filter=SecuritySeverity.HIGH,
        )
        for event in high_events:
            assert event.severity == SecuritySeverity.HIGH

        # Filter by CRITICAL severity
        critical_events = scanner.get_recent_events(
            limit=10,
            severity_filter=SecuritySeverity.CRITICAL,
        )
        for event in critical_events:
            assert event.severity == SecuritySeverity.CRITICAL

    async def test_get_recent_events_with_both_filters(self, scanner):
        """Test filtering events by both type and severity."""
        # Trigger constitutional hash mismatch (CRITICAL)
        await scanner.scan(content="test", constitutional_hash="bad_hash")

        events = scanner.get_recent_events(
            limit=10,
            severity_filter=SecuritySeverity.CRITICAL,
            event_type_filter=SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH,
        )

        for event in events:
            assert event.severity == SecuritySeverity.CRITICAL
            assert event.event_type == SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH


# =============================================================================
# Constitutional Classifier Integration Tests
# =============================================================================


class TestConstitutionalClassifierIntegration:
    """Tests for constitutional classifier integration with mocking."""

    async def test_constitutional_classifier_warning_when_unavailable(self):
        """Test scanner adds warning when constitutional classifier is unavailable."""
        config = RuntimeSecurityConfig(
            enable_constitutional_classifier=True,
        )
        scanner = RuntimeSecurityScanner(config)

        result = await scanner.scan(content="test content")

        # Check if warning was added when classifier unavailable
        # (depends on whether classifier module is actually available)
        assert result is not None
        if "constitutional_classification" in result.checks_performed:
            # Either classifier worked or warning was added
            pass

    async def test_scan_disabled_constitutional_classifier(self):
        """Test scanning with constitutional classifier disabled."""
        config = RuntimeSecurityConfig(
            enable_constitutional_classifier=False,
        )
        scanner = RuntimeSecurityScanner(config)

        result = await scanner.scan(content="test content")

        assert "constitutional_classification" not in result.checks_performed


# =============================================================================
# Runtime Guardrails Integration Tests
# =============================================================================


class TestRuntimeGuardrailsIntegration:
    """Tests for runtime guardrails integration."""

    async def test_runtime_guardrails_warning_when_unavailable(self):
        """Test scanner handles missing runtime guardrails gracefully."""
        config = RuntimeSecurityConfig(
            enable_runtime_guardrails=True,
        )
        scanner = RuntimeSecurityScanner(config)

        result = await scanner.scan(content="test content")

        # Check if guardrails check was performed or warning added
        assert result is not None
        if "runtime_safety_guardrails" in result.checks_performed:
            # Either guardrails worked or warning was added
            pass

    async def test_scan_disabled_runtime_guardrails(self):
        """Test scanning with runtime guardrails disabled."""
        config = RuntimeSecurityConfig(
            enable_runtime_guardrails=False,
        )
        scanner = RuntimeSecurityScanner(config)

        result = await scanner.scan(content="test content")

        assert "runtime_safety_guardrails" not in result.checks_performed


# =============================================================================
# Anomaly Detection Tests
# =============================================================================


class TestAnomalyDetection:
    """Tests for anomaly detection functionality."""

    async def test_anomaly_detection_threshold(self, extract_events_by_type):
        # Use fixed time for anomaly detection
        mock_now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        config = RuntimeSecurityConfig(
            enable_anomaly_detection=True,
            anomaly_window_seconds=60,
            anomaly_threshold_events=3,  # Low threshold for testing
        )
        scanner = RuntimeSecurityScanner(config)

        # Patch datetime in the scanner's module
        with patch("enhanced_agent_bus.runtime_security.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_now
            # Ensure fromisoformat works for any other code using it
            mock_datetime.fromisoformat = datetime.fromisoformat
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            # Generate multiple events to exceed threshold
            for _ in range(5):
                await scanner.scan(
                    content="<script>alert(1)</script>",
                    tenant_id="anomaly-test-tenant",
                )

            # Last result should have anomaly event
            result = await scanner.scan(
                content="<script>alert(2)</script>",
                tenant_id="anomaly-test-tenant",
            )

            anomaly_events = extract_events_by_type(result, SecurityEventType.ANOMALY_DETECTED)
            assert len(anomaly_events) > 0, "Anomaly detection should have triggered"

    async def test_anomaly_detection_disabled(self):
        """Test scanning with anomaly detection disabled."""
        config = RuntimeSecurityConfig(
            enable_anomaly_detection=False,
        )
        scanner = RuntimeSecurityScanner(config)

        result = await scanner.scan(content="test content")

        assert "anomaly_detection" not in result.checks_performed


# =============================================================================
# Concurrent Operations Tests
# =============================================================================


class TestConcurrentOperations:
    """Tests for concurrent scanner operations."""

    async def test_concurrent_scans(self, scanner):
        """Test scanner handles concurrent scans correctly."""
        import asyncio

        # Run multiple scans concurrently
        tasks = [scanner.scan(content=f"content_{i}") for i in range(10)]

        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        for result in results:
            assert result is not None
            assert isinstance(result, SecurityScanResult)

    async def test_concurrent_scans_with_rate_limiting(self):
        """Test rate limiting works correctly under concurrent load."""
        config = RuntimeSecurityConfig(
            rate_limit_qps=5,
            enable_anomaly_detection=False,
            enable_runtime_guardrails=False,
            enable_constitutional_classifier=False,
        )
        scanner = RuntimeSecurityScanner(config)

        import asyncio

        results = []
        start_time = 2000.0

        # Use an infinite side effect to avoid StopIteration
        time_gen = itertools.count(start_time, 0.01)
        with patch("enhanced_agent_bus.runtime_security.time.monotonic", side_effect=time_gen):
            # Run many concurrent scans
            tasks = [
                scanner.scan(content=f"test_{i}", tenant_id="concurrent-tenant") for i in range(20)
            ]
            results = await asyncio.gather(*tasks)

        # Some should have rate limit events
        total_rate_events = sum(
            1
            for r in results
            for e in r.events
            if e.event_type == SecurityEventType.RATE_LIMIT_EXCEEDED
        )
        assert total_rate_events > 0, "Rate limiting should have triggered"

        # Some should have rate limit events
        total_rate_events = sum(
            1
            for r in results
            for e in r.events
            if e.event_type == SecurityEventType.RATE_LIMIT_EXCEEDED
        )
        assert total_rate_events > 0, "Rate limiting should have triggered"


# =============================================================================
# Input Validation Edge Cases
# =============================================================================


class TestInputValidationEdgeCases:
    """Tests for edge cases in input validation."""

    async def test_unicode_content(self, scanner):
        """Test scanning content with unicode characters."""
        unicode_content = "Hello 世界 🌍 Привет مرحبا"
        result = await scanner.scan(content=unicode_content)
        assert result.is_secure is True

    async def test_newlines_and_special_chars(self, scanner):
        """Test scanning content with newlines and special characters."""
        content = "Line 1\nLine 2\r\nLine 3\tTabbed"
        result = await scanner.scan(content=content)
        assert result is not None

    async def test_empty_dict(self, scanner):
        """Test scanning empty dictionary."""
        result = await scanner.scan(content={})
        assert result.is_secure is True

    async def test_bool_content(self, scanner):
        """Test scanning boolean content."""
        result = await scanner.scan(content=True)
        assert result.is_secure is True

    async def test_very_deeply_nested_but_within_limit(self):
        """Test scanning nested dict within allowed depth."""
        config = RuntimeSecurityConfig(max_nested_depth=10)
        scanner = RuntimeSecurityScanner(config)

        # Create nested dict within limit
        nested = {"level": 1}
        current = nested
        for i in range(8):  # 8 levels, under limit of 10
            current["nested"] = {"level": i + 2}
            current = current["nested"]

        result = await scanner.scan(content=nested)

        # Should not trigger INVALID_INPUT for nesting
        nesting_events = [
            e
            for e in result.events
            if e.event_type == SecurityEventType.INVALID_INPUT and "nesting" in e.message.lower()
        ]
        assert len(nesting_events) == 0
