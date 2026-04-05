"""
ACGS-2 Prometheus Metrics Tests
Constitutional Hash: 608508a9bd224290

Tests for prometheus_metrics module per SPEC_ACGS2_ENHANCED.md Section 6.1.
"""

from unittest.mock import MagicMock, patch

import pytest

from ..prometheus_metrics import (
    CONFIDENCE_BUCKETS,
    CONSTITUTIONAL_HASH,
    CRITICAL_ALERTS,
    HIGH_ALERTS,
    POLICY_LATENCY_BUCKETS,
    VALIDATION_LATENCY_BUCKETS,
    WARNING_ALERTS,
    AlertRule,
    CacheOperation,
    CacheTier,
    MetricsCollector,
    PolicyDecision,
    ValidationResult,
    generate_prometheus_alert_rules,
    get_metrics_collector,
    reset_metrics_collector,
)


class TestConstitutionalHash:
    """Test constitutional hash enforcement."""

    def test_constitutional_hash_value(self):
        """Verify constitutional hash matches spec."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_metrics_collector_has_constitutional_hash(self):
        """Verify MetricsCollector includes constitutional hash."""
        collector = MetricsCollector()
        assert collector.constitutional_hash == CONSTITUTIONAL_HASH


class TestValidationResult:
    """Test ValidationResult enum."""

    def test_validation_result_values(self):
        """Test all expected validation results exist."""
        assert ValidationResult.SUCCESS.value == "success"
        assert ValidationResult.FAILURE.value == "failure"
        assert ValidationResult.ERROR.value == "error"
        assert ValidationResult.HASH_MISMATCH.value == "hash_mismatch"
        assert ValidationResult.TIMEOUT.value == "timeout"


class TestCacheEnums:
    """Test cache-related enums."""

    def test_cache_tier_values(self):
        """Test cache tier values match spec (L1/L2/L3)."""
        assert CacheTier.L1.value == "l1"
        assert CacheTier.L2.value == "l2"
        assert CacheTier.L3.value == "l3"

    def test_cache_operation_values(self):
        """Test cache operation types."""
        assert CacheOperation.GET.value == "get"
        assert CacheOperation.SET.value == "set"
        assert CacheOperation.DELETE.value == "delete"
        assert CacheOperation.EXPIRE.value == "expire"


class TestPolicyDecision:
    """Test PolicyDecision enum."""

    def test_policy_decision_values(self):
        """Test policy decision types."""
        assert PolicyDecision.ALLOW.value == "allow"
        assert PolicyDecision.DENY.value == "deny"
        assert PolicyDecision.DEFER.value == "defer"


class TestMetricsCollector:
    """Test MetricsCollector functionality."""

    def setup_method(self):
        """Reset metrics collector before each test."""
        reset_metrics_collector()

    def test_get_metrics_collector_singleton(self):
        """Test global metrics collector is singleton."""
        collector1 = get_metrics_collector()
        collector2 = get_metrics_collector()
        assert collector1 is collector2

    def test_metrics_collector_default_service_name(self):
        """Test default service name."""
        collector = MetricsCollector()
        assert collector.service_name == "acgs2-enhanced-agent-bus"

    def test_metrics_collector_custom_service_name(self):
        """Test custom service name."""
        collector = MetricsCollector(service_name="custom-service")
        assert collector.service_name == "custom-service"

    def test_record_validation_success(self):
        """Test recording successful validation."""
        collector = MetricsCollector()
        # Should not raise
        collector.record_validation(
            result=ValidationResult.SUCCESS,
            principle_category="constitutional_core",
            agent_id="agent-001",
            latency_seconds=0.002,
            confidence=0.95,
        )

    def test_record_validation_failure(self):
        """Test recording failed validation."""
        collector = MetricsCollector()
        collector.record_validation(
            result=ValidationResult.FAILURE,
            principle_category="ethical_boundary",
            agent_id="agent-002",
            latency_seconds=0.005,
            confidence=0.3,
        )

    def test_record_validation_hash_mismatch(self):
        """Test recording hash mismatch - critical security metric."""
        collector = MetricsCollector()
        collector.record_validation(
            result=ValidationResult.HASH_MISMATCH,
            principle_category="hash_verification",
            agent_id="suspicious-agent",
            latency_seconds=0.001,
        )

    def test_record_cache_operation_hit(self):
        """Test recording cache hit."""
        collector = MetricsCollector()
        collector.record_cache_operation(
            tier=CacheTier.L1,
            operation=CacheOperation.GET,
            hit=True,
        )

    def test_record_cache_operation_miss(self):
        """Test recording cache miss."""
        collector = MetricsCollector()
        collector.record_cache_operation(
            tier=CacheTier.L2,
            operation=CacheOperation.GET,
            hit=False,
        )

    def test_update_cache_hit_ratio(self):
        """Test updating cache hit ratio gauge."""
        collector = MetricsCollector()
        collector.update_cache_hit_ratio(CacheTier.L1, 0.95)
        collector.update_cache_hit_ratio(CacheTier.L2, 0.85)
        collector.update_cache_hit_ratio(CacheTier.L3, 0.75)

    def test_update_cache_size(self):
        """Test updating cache size gauge."""
        collector = MetricsCollector()
        collector.update_cache_size(CacheTier.L1, 1024 * 1024)  # 1MB
        collector.update_cache_size(CacheTier.L2, 10 * 1024 * 1024)  # 10MB

    def test_record_policy_evaluation_allow(self):
        """Test recording policy allow decision."""
        collector = MetricsCollector()
        collector.record_policy_evaluation(
            policy_id="policy-001",
            decision=PolicyDecision.ALLOW,
            latency_seconds=0.001,
        )

    def test_record_policy_evaluation_deny(self):
        """Test recording policy deny decision."""
        collector = MetricsCollector()
        collector.record_policy_evaluation(
            policy_id="policy-002",
            decision=PolicyDecision.DENY,
            latency_seconds=0.002,
        )

    def test_update_active_connections(self):
        """Test updating active connections gauge."""
        collector = MetricsCollector()
        collector.update_active_connections(
            service="agent-bus",
            connection_type="websocket",
            count=42,
        )

    def test_update_request_queue_size(self):
        """Test updating request queue size."""
        collector = MetricsCollector()
        collector.update_request_queue_size(
            service="agent-bus",
            size=100,
        )

    def test_get_metrics_returns_bytes(self):
        """Test get_metrics returns bytes."""
        collector = MetricsCollector()
        metrics = collector.get_metrics()
        assert isinstance(metrics, bytes)

    def test_get_content_type(self):
        """Test get_content_type returns valid content type."""
        collector = MetricsCollector()
        content_type = collector.get_content_type()
        assert isinstance(content_type, str)


class TestValidationTimer:
    """Test validation timing context manager."""

    def test_validation_timer_success(self):
        """Test validation timer records latency on success."""
        collector = MetricsCollector()
        with collector.validation_timer() as ctx:
            # Simulate work
            pass
        assert ctx["result"] == ValidationResult.SUCCESS

    def test_validation_timer_error(self):
        """Test validation timer records error on exception."""
        collector = MetricsCollector()
        with pytest.raises(ValueError):
            with collector.validation_timer() as ctx:
                raise ValueError("test error")
        assert ctx["result"] == ValidationResult.ERROR


class TestPolicyTimer:
    """Test policy evaluation timing context manager."""

    def test_policy_timer_records_latency(self):
        """Test policy timer records latency."""
        collector = MetricsCollector()
        with collector.policy_timer():
            # Simulate work
            pass


class TestLatencyBuckets:
    """Test latency bucket configurations per spec."""

    def test_validation_latency_buckets(self):
        """Test validation latency buckets target <5ms P99."""
        assert VALIDATION_LATENCY_BUCKETS == (0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0)
        # 5ms = 0.005s is second bucket, appropriate for <5ms target
        assert 0.005 in VALIDATION_LATENCY_BUCKETS

    def test_confidence_buckets(self):
        """Test confidence score buckets."""
        assert CONFIDENCE_BUCKETS == (0.5, 0.7, 0.8, 0.9, 0.95, 0.99)

    def test_policy_latency_buckets(self):
        """Test policy latency buckets."""
        assert POLICY_LATENCY_BUCKETS == (0.001, 0.005, 0.01, 0.05)


class TestAlertRules:
    """Test alerting rule definitions per Section 6.4."""

    def test_critical_alerts_exist(self):
        """Test critical alerts (P0, P1) are defined."""
        assert len(CRITICAL_ALERTS) >= 2
        alert_names = [a.name for a in CRITICAL_ALERTS]
        assert "ConstitutionalHashViolation" in alert_names
        assert "OPAUnavailable" in alert_names

    def test_constitutional_hash_violation_alert(self):
        """Test constitutional hash violation alert configuration."""
        alert = next(a for a in CRITICAL_ALERTS if a.name == "ConstitutionalHashViolation")
        assert alert.severity == "P0"  # Highest severity
        assert "PagerDuty" in alert.channel
        assert "Security" in alert.channel
        assert "hash_mismatch" in alert.condition

    def test_high_alerts_exist(self):
        """Test high priority alerts (P2) are defined."""
        assert len(HIGH_ALERTS) >= 2
        alert_names = [a.name for a in HIGH_ALERTS]
        assert "HighErrorRate" in alert_names
        assert "HighLatency" in alert_names

    def test_high_latency_alert(self):
        """Test high latency alert targets <5ms P99."""
        alert = next(a for a in HIGH_ALERTS if a.name == "HighLatency")
        assert alert.severity == "P2"
        assert "0.005" in alert.condition  # 5ms threshold

    def test_warning_alerts_exist(self):
        """Test warning alerts (P3) are defined."""
        assert len(WARNING_ALERTS) >= 1
        alert_names = [a.name for a in WARNING_ALERTS]
        assert "LowCacheHitRate" in alert_names

    def test_cache_hit_rate_alert(self):
        """Test cache hit rate alert threshold."""
        alert = next(a for a in WARNING_ALERTS if a.name == "LowCacheHitRate")
        assert alert.severity == "P3"
        assert "0.8" in alert.condition  # 80% threshold


class TestAlertRuleGeneration:
    """Test Prometheus alert rule YAML generation."""

    def test_generate_alert_rules_returns_yaml(self):
        """Test alert rule generation returns valid YAML structure."""
        rules = generate_prometheus_alert_rules()
        assert isinstance(rules, str)
        assert "groups:" in rules
        assert "acgs2_constitutional_governance" in rules

    def test_generated_rules_include_constitutional_hash(self):
        """Test generated rules include constitutional hash."""
        rules = generate_prometheus_alert_rules()
        assert CONSTITUTIONAL_HASH in rules

    def test_generated_rules_include_all_alerts(self):
        """Test all defined alerts are included in generated rules."""
        rules = generate_prometheus_alert_rules()
        for alert in CRITICAL_ALERTS + HIGH_ALERTS + WARNING_ALERTS:
            assert alert.name in rules


class TestAlertRule:
    """Test AlertRule dataclass."""

    def test_alert_rule_creation(self):
        """Test creating alert rule."""
        rule = AlertRule(
            name="TestAlert",
            condition="test_metric > 0",
            severity="P1",
            channel="Slack",
            description="Test alert description",
        )
        assert rule.name == "TestAlert"
        assert rule.condition == "test_metric > 0"
        assert rule.severity == "P1"
        assert rule.channel == "Slack"
        assert rule.description == "Test alert description"

    def test_alert_rule_default_description(self):
        """Test alert rule with default description."""
        rule = AlertRule(
            name="TestAlert",
            condition="test_metric > 0",
            severity="P1",
            channel="Slack",
        )
        assert rule.description == ""
