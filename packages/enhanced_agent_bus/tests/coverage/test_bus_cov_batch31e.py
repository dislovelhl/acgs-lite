"""
Comprehensive coverage tests for enhanced_agent_bus modules (batch 31e).

Targets:
- enhanced_agent_bus.transaction_coordinator_metrics (88.9%, 44 missing lines)
- enhanced_agent_bus.session_governance_sdk (85.6%, 44 missing lines)
- enhanced_agent_bus.deliberation_layer.impact_scorer (86.9%, 44 missing lines)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

# =============================================================================
# Module 1: transaction_coordinator_metrics
# =============================================================================


class TestNoOpClasses:
    """Test no-op metric classes for duplicate registration fallback."""

    def test_noop_counter_init(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import _NoOpCounter

        c = _NoOpCounter("name", "doc", extra=True)
        assert c is not None

    def test_noop_counter_labels_returns_self(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import _NoOpCounter

        c = _NoOpCounter()
        assert c.labels(status="ok") is c

    def test_noop_counter_inc_noop(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import _NoOpCounter

        c = _NoOpCounter()
        c.inc()
        c.inc(5.0)

    def test_noop_gauge_init(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import _NoOpGauge

        g = _NoOpGauge("name", "doc")
        assert g is not None

    def test_noop_gauge_labels_returns_self(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import _NoOpGauge

        g = _NoOpGauge()
        assert g.labels(key="val") is g

    def test_noop_gauge_set(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import _NoOpGauge

        g = _NoOpGauge()
        g.set(42.0)

    def test_noop_gauge_inc_dec(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import _NoOpGauge

        g = _NoOpGauge()
        g.inc()
        g.inc(2.0)
        g.dec()
        g.dec(3.0)

    def test_noop_histogram_init(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import _NoOpHistogram

        h = _NoOpHistogram("name", "doc")
        assert h is not None

    def test_noop_histogram_labels_returns_self(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import _NoOpHistogram

        h = _NoOpHistogram()
        assert h.labels(op="save") is h

    def test_noop_histogram_observe(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import _NoOpHistogram

        h = _NoOpHistogram()
        h.observe(0.5)


class TestGetOrCreateMetric:
    """Test _get_or_create_metric caching and fallback paths."""

    def test_cache_hit(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            _METRICS_CACHE,
            Counter,
            _get_or_create_metric,
        )

        sentinel = object()
        cache_key = "Counter:__test_cache_hit_metric"
        _METRICS_CACHE[cache_key] = sentinel
        try:
            result = _get_or_create_metric(Counter, "__test_cache_hit_metric", "doc")
            assert result is sentinel
        finally:
            _METRICS_CACHE.pop(cache_key, None)

    def test_noop_fallback_for_unknown_class_type(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            _METRICS_CACHE,
            PROMETHEUS_AVAILABLE,
            _get_or_create_metric,
            _NoOpCounter,
        )

        if PROMETHEUS_AVAILABLE:
            pytest.skip("Need prometheus unavailable for this test path")

        cache_key = "object:__test_unknown_class"
        _METRICS_CACHE.pop(cache_key, None)
        result = _get_or_create_metric(object, "__test_unknown_class", "doc")
        assert isinstance(result, _NoOpCounter)
        _METRICS_CACHE.pop(cache_key, None)

    def test_value_error_duplicate_returns_noop_histogram(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            _METRICS_CACHE,
            Histogram,
            _get_or_create_metric,
            _NoOpHistogram,
        )

        cache_key = "Histogram:__test_dup_hist"
        _METRICS_CACHE.pop(cache_key, None)

        with patch(
            "enhanced_agent_bus.transaction_coordinator_metrics.PROMETHEUS_AVAILABLE",
            True,
        ):
            with patch.object(
                Histogram, "__init__", side_effect=ValueError("Duplicated timeseries")
            ):
                with patch(
                    "enhanced_agent_bus.transaction_coordinator_metrics.REGISTRY",
                    None,
                ):
                    result = _get_or_create_metric(
                        Histogram, "__test_dup_hist", "doc", buckets=[0.1]
                    )
                    assert isinstance(result, _NoOpHistogram)
        _METRICS_CACHE.pop(cache_key, None)

    def test_value_error_duplicate_returns_noop_gauge(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            _METRICS_CACHE,
            Gauge,
            _get_or_create_metric,
            _NoOpGauge,
        )

        cache_key = "Gauge:__test_dup_gauge"
        _METRICS_CACHE.pop(cache_key, None)

        with patch(
            "enhanced_agent_bus.transaction_coordinator_metrics.PROMETHEUS_AVAILABLE",
            True,
        ):
            with patch.object(Gauge, "__init__", side_effect=ValueError("already registered")):
                with patch(
                    "enhanced_agent_bus.transaction_coordinator_metrics.REGISTRY",
                    None,
                ):
                    result = _get_or_create_metric(Gauge, "__test_dup_gauge", "doc")
                    assert isinstance(result, _NoOpGauge)
        _METRICS_CACHE.pop(cache_key, None)

    def test_value_error_duplicate_returns_noop_counter(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            _METRICS_CACHE,
            Counter,
            _get_or_create_metric,
            _NoOpCounter,
        )

        cache_key = "Counter:__test_dup_counter"
        _METRICS_CACHE.pop(cache_key, None)

        with patch(
            "enhanced_agent_bus.transaction_coordinator_metrics.PROMETHEUS_AVAILABLE",
            True,
        ):
            with patch.object(Counter, "__init__", side_effect=ValueError("already registered")):
                with patch(
                    "enhanced_agent_bus.transaction_coordinator_metrics.REGISTRY",
                    None,
                ):
                    result = _get_or_create_metric(Counter, "__test_dup_counter", "doc")
                    assert isinstance(result, _NoOpCounter)
        _METRICS_CACHE.pop(cache_key, None)

    def test_value_error_registry_lookup(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            _METRICS_CACHE,
            Counter,
            _get_or_create_metric,
        )

        cache_key = "Counter:__test_registry_lookup"
        _METRICS_CACHE.pop(cache_key, None)

        mock_collector = MagicMock()
        mock_collector._name = "__test_registry_lookup"
        mock_registry = MagicMock()
        mock_registry._names_to_collectors = {"test": mock_collector}

        with patch(
            "enhanced_agent_bus.transaction_coordinator_metrics.PROMETHEUS_AVAILABLE",
            True,
        ):
            with patch.object(Counter, "__init__", side_effect=ValueError("Duplicated timeseries")):
                with patch(
                    "enhanced_agent_bus.transaction_coordinator_metrics.REGISTRY",
                    mock_registry,
                ):
                    result = _get_or_create_metric(Counter, "__test_registry_lookup", "doc")
                    assert result is mock_collector
        _METRICS_CACHE.pop(cache_key, None)

    def test_value_error_registry_attribute_error(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            _METRICS_CACHE,
            Counter,
            _get_or_create_metric,
            _NoOpCounter,
        )

        cache_key = "Counter:__test_reg_attr_err"
        _METRICS_CACHE.pop(cache_key, None)

        mock_registry = MagicMock()
        type(mock_registry)._names_to_collectors = PropertyMock(
            side_effect=AttributeError("no attr")
        )

        with patch(
            "enhanced_agent_bus.transaction_coordinator_metrics.PROMETHEUS_AVAILABLE",
            True,
        ):
            with patch.object(Counter, "__init__", side_effect=ValueError("Duplicated timeseries")):
                with patch(
                    "enhanced_agent_bus.transaction_coordinator_metrics.REGISTRY",
                    mock_registry,
                ):
                    result = _get_or_create_metric(Counter, "__test_reg_attr_err", "doc")
                    assert isinstance(result, _NoOpCounter)
        _METRICS_CACHE.pop(cache_key, None)


class TestResetMetricsCache:
    def test_reset_clears(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            _METRICS_CACHE,
            reset_metrics_cache,
        )

        _METRICS_CACHE["__test_key"] = "value"
        reset_metrics_cache()
        assert "__test_key" not in _METRICS_CACHE


class TestTransactionMetrics:
    def _make_metrics(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            TransactionMetrics,
            reset_metrics_cache,
        )

        reset_metrics_cache()
        return TransactionMetrics()

    def test_post_init_sets_initialized(self):
        m = self._make_metrics()
        assert m._initialized is True

    def test_post_init_skip_if_initialized(self):
        m = self._make_metrics()
        old_total = m.transactions_total
        m.__post_init__()
        assert m.transactions_total is old_total

    def test_record_transaction_start(self):
        m = self._make_metrics()
        m.record_transaction_start()
        assert m._internal_total == 1
        assert m._internal_concurrent == 1

    def test_record_transaction_success(self):
        m = self._make_metrics()
        m.record_transaction_start()
        m.record_transaction_success(0.5)
        assert m._internal_success == 1
        assert m._internal_concurrent == 0
        assert len(m._duration_samples) == 1

    def test_record_transaction_failure(self):
        m = self._make_metrics()
        m.record_transaction_start()
        m.record_transaction_failure(0.3, reason="timeout")
        assert m._internal_failed == 1
        assert m._internal_concurrent == 0

    def test_record_transaction_timeout(self):
        m = self._make_metrics()
        m.record_transaction_start()
        m.record_transaction_timeout(5.0)
        assert m._internal_failed == 1
        assert m._internal_concurrent == 0

    def test_record_transaction_compensated(self):
        m = self._make_metrics()
        m.record_transaction_compensated()

    def test_record_compensation_start_noop(self):
        m = self._make_metrics()
        m.record_compensation_start()

    def test_record_compensation_success(self):
        m = self._make_metrics()
        m.record_compensation_success(0.2)
        assert m._internal_compensations == 1
        assert len(m._compensation_samples) == 1

    def test_record_compensation_failure(self):
        m = self._make_metrics()
        m.record_compensation_failure(0.1)

    def test_record_checkpoint_save_success(self):
        m = self._make_metrics()
        m.record_checkpoint_save(0.05, success=True)

    def test_record_checkpoint_save_failure(self):
        m = self._make_metrics()
        m.record_checkpoint_save(0.05, success=False)

    def test_record_checkpoint_restore_success(self):
        m = self._make_metrics()
        m.record_checkpoint_restore(0.03, success=True)

    def test_record_checkpoint_restore_failure(self):
        m = self._make_metrics()
        m.record_checkpoint_restore(0.03, success=False)

    def test_concurrent_does_not_go_negative(self):
        m = self._make_metrics()
        m.record_transaction_success(0.1)
        assert m._internal_concurrent == 0

    def test_consistency_ratio_no_transactions(self):
        m = self._make_metrics()
        assert m.get_consistency_ratio() == 1.0

    def test_consistency_ratio_mixed(self):
        m = self._make_metrics()
        m.record_transaction_start()
        m.record_transaction_success(0.1)
        m.record_transaction_start()
        m.record_transaction_failure(0.1)
        ratio = m.get_consistency_ratio()
        assert ratio == 0.5

    def test_get_latency_percentiles_empty(self):
        m = self._make_metrics()
        p = m.get_latency_percentiles()
        assert p == {"p50": 0.0, "p95": 0.0, "p99": 0.0}

    def test_get_latency_percentiles_with_samples(self):
        m = self._make_metrics()
        for i in range(100):
            m._record_duration(i * 0.01)
        p = m.get_latency_percentiles()
        assert p["p50"] > 0
        assert p["p95"] > p["p50"]
        assert p["p99"] >= p["p95"]

    def test_get_compensation_percentiles_empty(self):
        m = self._make_metrics()
        p = m.get_compensation_percentiles()
        assert p == {"p50": 0.0, "p95": 0.0, "p99": 0.0}

    def test_get_compensation_percentiles_with_samples(self):
        m = self._make_metrics()
        for i in range(50):
            m._record_compensation_duration(i * 0.01)
        p = m.get_compensation_percentiles()
        assert p["p50"] >= 0

    def test_health_status_healthy(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import HealthStatus

        m = self._make_metrics()
        assert m.get_health_status_enum() == HealthStatus.HEALTHY

    def test_health_status_degraded(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import HealthStatus

        m = self._make_metrics()
        # 99.5% success = degraded
        for _ in range(995):
            m._internal_total += 1
            m._internal_success += 1
        for _ in range(5):
            m._internal_total += 1
        assert m.get_health_status_enum() == HealthStatus.DEGRADED

    def test_health_status_unhealthy(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import HealthStatus

        m = self._make_metrics()
        m._internal_total = 100
        m._internal_success = 50
        assert m.get_health_status_enum() == HealthStatus.UNHEALTHY

    def test_update_health_gauge(self):
        m = self._make_metrics()
        m.update_health_gauge()

    def test_get_metrics_summary(self):
        m = self._make_metrics()
        m.record_transaction_start()
        m.record_transaction_success(0.1)
        summary = m.get_metrics_summary()
        assert "consistency_ratio" in summary
        assert "health_status" in summary
        assert "latency_ms" in summary
        assert "compensation_latency_ms" in summary
        assert "concurrent_transactions" in summary
        assert "constitutional_hash" in summary

    def test_get_gauge_value_for_concurrent(self):
        m = self._make_metrics()
        m._internal_concurrent = 5
        val = m._get_gauge_value(m.concurrent_transactions)
        assert val == 5.0

    def test_get_gauge_value_fallback(self):
        m = self._make_metrics()
        mock_gauge = MagicMock()
        mock_gauge._value = None
        val = m._get_gauge_value(mock_gauge)
        assert val == 0.0

    def test_get_gauge_value_exception(self):
        m = self._make_metrics()
        mock_gauge = MagicMock()
        type(mock_gauge)._value = PropertyMock(side_effect=AttributeError)
        val = m._get_gauge_value(mock_gauge)
        assert val == 0.0

    def test_get_counter_value_no_labels(self):
        m = self._make_metrics()
        val = m._get_counter_value(m.transactions_success)
        assert isinstance(val, float)

    def test_get_counter_value_exception(self):
        m = self._make_metrics()
        mock_counter = MagicMock()
        mock_counter.labels.side_effect = RuntimeError("err")
        val = m._get_counter_value(mock_counter, status="ok")
        assert val == 0.0


class TestTransactionTimer:
    def _make_metrics(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            TransactionMetrics,
            reset_metrics_cache,
        )

        reset_metrics_cache()
        return TransactionMetrics()

    def test_transaction_timer_success(self):
        m = self._make_metrics()
        with m.transaction_timer() as ctx:
            pass
        assert ctx["recorded"] is True
        assert m._internal_success == 1

    def test_transaction_timer_failure_on_exception(self):
        m = self._make_metrics()
        with pytest.raises(RuntimeError):
            with m.transaction_timer() as ctx:
                raise RuntimeError("fail")
        assert ctx["success"] is False
        assert m._internal_failed == 1

    def test_transaction_timer_expected_failure(self):
        m = self._make_metrics()
        with m.transaction_timer(expected_success=False) as ctx:
            pass
        assert ctx["recorded"] is True
        assert m._internal_failed == 1

    def test_compensation_timer_success(self):
        m = self._make_metrics()
        with m.compensation_timer() as ctx:
            pass
        assert ctx["recorded"] is True
        assert m._internal_compensations == 1

    def test_compensation_timer_failure(self):
        m = self._make_metrics()
        with pytest.raises(ValueError):
            with m.compensation_timer() as ctx:
                raise ValueError("comp fail")
        assert ctx["success"] is False

    def test_checkpoint_timer_save(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            CheckpointOperation,
        )

        m = self._make_metrics()
        with m.checkpoint_timer(CheckpointOperation.SAVE) as ctx:
            pass
        assert ctx["recorded"] is True

    def test_checkpoint_timer_restore(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            CheckpointOperation,
        )

        m = self._make_metrics()
        with m.checkpoint_timer(CheckpointOperation.RESTORE) as ctx:
            pass
        assert ctx["recorded"] is True

    def test_checkpoint_timer_exception(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            CheckpointOperation,
        )

        m = self._make_metrics()
        with pytest.raises(TypeError):
            with m.checkpoint_timer(CheckpointOperation.SAVE) as ctx:
                raise TypeError("chk fail")
        assert ctx["success"] is False


class TestTransactionEnums:
    def test_transaction_status_values(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import TransactionStatus

        assert TransactionStatus.SUCCESS == "success"
        assert TransactionStatus.FAILURE == "failure"
        assert TransactionStatus.TIMEOUT == "timeout"
        assert TransactionStatus.COMPENSATED == "compensated"

    def test_compensation_status_values(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import CompensationStatus

        assert CompensationStatus.SUCCESS == "success"
        assert CompensationStatus.FAILURE == "failure"

    def test_checkpoint_operation_values(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import CheckpointOperation

        assert CheckpointOperation.SAVE == "save"
        assert CheckpointOperation.RESTORE == "restore"

    def test_health_status_values(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import HealthStatus

        assert HealthStatus.HEALTHY == "healthy"
        assert HealthStatus.DEGRADED == "degraded"
        assert HealthStatus.UNHEALTHY == "unhealthy"


class TestComputePercentilesFromSamples:
    def test_empty_samples(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import TransactionMetrics

        result = TransactionMetrics._compute_percentiles_from_samples([])
        assert result == {"p50": 0.0, "p95": 0.0, "p99": 0.0}

    def test_single_sample(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import TransactionMetrics

        result = TransactionMetrics._compute_percentiles_from_samples([5.0])
        assert result["p50"] == 5.0
        assert result["p95"] == 5.0
        assert result["p99"] == 5.0

    def test_many_samples(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import TransactionMetrics

        samples = list(range(1, 101))
        result = TransactionMetrics._compute_percentiles_from_samples(samples)
        assert result["p50"] <= result["p95"] <= result["p99"]


class TestGetTransactionMetrics:
    def test_get_creates_singleton(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            TransactionMetrics,
            get_transaction_metrics,
        )

        m = get_transaction_metrics()
        assert isinstance(m, TransactionMetrics)

    def test_reset_transaction_metrics(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            get_transaction_metrics,
            reset_transaction_metrics,
        )

        reset_transaction_metrics()
        m = get_transaction_metrics()
        assert m._internal_total == 0


# =============================================================================
# Module 2: session_governance_sdk
# =============================================================================


class TestRiskLevel:
    def test_values(self):
        from enhanced_agent_bus.session_governance_sdk import RiskLevel

        assert RiskLevel.LOW == "low"
        assert RiskLevel.MEDIUM == "medium"
        assert RiskLevel.HIGH == "high"
        assert RiskLevel.CRITICAL == "critical"


class TestAutomationLevel:
    def test_values(self):
        from enhanced_agent_bus.session_governance_sdk import AutomationLevel

        assert AutomationLevel.FULL == "full"
        assert AutomationLevel.PARTIAL == "partial"
        assert AutomationLevel.NONE == "none"


class TestSessionSDKErrors:
    def test_base_error(self):
        from enhanced_agent_bus.session_governance_sdk import SessionSDKError

        err = SessionSDKError("test error", status_code=500, response_body={"detail": "test"})
        assert err.status_code == 500
        assert err.response_body == {"detail": "test"}
        assert "test error" in str(err)

    def test_not_found_error(self):
        from enhanced_agent_bus.session_governance_sdk import SessionNotFoundError

        err = SessionNotFoundError("not found", 404)
        assert err.http_status_code == 404
        assert err.error_code == "SESSION_NOT_FOUND"

    def test_tenant_access_denied(self):
        from enhanced_agent_bus.session_governance_sdk import TenantAccessDeniedError

        err = TenantAccessDeniedError("denied", 403)
        assert err.http_status_code == 403

    def test_validation_error(self):
        from enhanced_agent_bus.session_governance_sdk import SessionValidationError

        err = SessionValidationError("invalid", 400)
        assert err.http_status_code == 400

    def test_service_unavailable(self):
        from enhanced_agent_bus.session_governance_sdk import ServiceUnavailableError

        err = ServiceUnavailableError("unavailable", 503)
        assert err.http_status_code == 503


class TestGovernanceConfig:
    def test_to_dict_minimal(self):
        from enhanced_agent_bus.session_governance_sdk import GovernanceConfig

        cfg = GovernanceConfig(tenant_id="t1")
        d = cfg.to_dict()
        assert d["tenant_id"] == "t1"
        assert d["risk_level"] == "medium"
        assert "user_id" not in d

    def test_to_dict_full(self):
        from enhanced_agent_bus.session_governance_sdk import (
            AutomationLevel,
            GovernanceConfig,
            RiskLevel,
        )

        cfg = GovernanceConfig(
            tenant_id="t1",
            user_id="u1",
            risk_level=RiskLevel.HIGH,
            policy_id="p1",
            policy_overrides={"key": "val"},
            enabled_policies=["ep1"],
            disabled_policies=["dp1"],
            require_human_approval=True,
            max_automation_level=AutomationLevel.PARTIAL,
        )
        d = cfg.to_dict()
        assert d["user_id"] == "u1"
        assert d["risk_level"] == "high"
        assert d["policy_id"] == "p1"
        assert d["policy_overrides"] == {"key": "val"}
        assert d["enabled_policies"] == ["ep1"]
        assert d["disabled_policies"] == ["dp1"]
        assert d["require_human_approval"] is True
        assert d["max_automation_level"] == "partial"

    def test_to_dict_string_risk_level(self):
        from enhanced_agent_bus.session_governance_sdk import GovernanceConfig

        cfg = GovernanceConfig(tenant_id="t1", risk_level="custom")
        d = cfg.to_dict()
        assert d["risk_level"] == "custom"

    def test_to_dict_string_automation_level(self):
        from enhanced_agent_bus.session_governance_sdk import GovernanceConfig

        cfg = GovernanceConfig(tenant_id="t1", max_automation_level="custom_auto")
        d = cfg.to_dict()
        assert d["max_automation_level"] == "custom_auto"


class TestSession:
    def test_from_dict_minimal(self):
        from enhanced_agent_bus.session_governance_sdk import Session

        data = {"session_id": "s1", "tenant_id": "t1"}
        s = Session.from_dict(data)
        assert s.session_id == "s1"
        assert s.tenant_id == "t1"
        assert s.risk_level == "medium"
        assert s.policy_id is None

    def test_from_dict_full(self):
        from enhanced_agent_bus.session_governance_sdk import Session

        data = {
            "session_id": "s1",
            "tenant_id": "t1",
            "risk_level": "high",
            "policy_id": "p1",
            "policy_overrides": {"x": 1},
            "enabled_policies": ["e1"],
            "disabled_policies": ["d1"],
            "require_human_approval": True,
            "max_automation_level": "full",
            "metadata": {"env": "test"},
            "created_at": "2025-01-01",
            "updated_at": "2025-01-02",
            "expires_at": "2025-01-03",
            "ttl_remaining": 3600,
            "constitutional_hash": "abc123",
        }
        s = Session.from_dict(data)
        assert s.risk_level == "high"
        assert s.policy_id == "p1"
        assert s.require_human_approval is True
        assert s.max_automation_level == "full"
        assert s.ttl_remaining == 3600
        assert s.constitutional_hash == "abc123"


class TestSessionMetrics:
    def test_from_dict_defaults(self):
        from enhanced_agent_bus.session_governance_sdk import SessionMetrics

        m = SessionMetrics.from_dict({})
        assert m.cache_hits == 0
        assert m.cache_misses == 0
        assert m.cache_capacity == 1000

    def test_from_dict_full(self):
        from enhanced_agent_bus.session_governance_sdk import SessionMetrics

        data = {
            "cache_hits": 10,
            "cache_misses": 5,
            "creates": 3,
            "reads": 20,
            "updates": 2,
            "deletes": 1,
            "errors": 0,
            "cache_hit_rate": 0.67,
            "cache_size": 50,
            "cache_capacity": 500,
        }
        m = SessionMetrics.from_dict(data)
        assert m.cache_hits == 10
        assert m.cache_hit_rate == 0.67


class TestSessionGovernanceClient:
    def test_init_strips_trailing_slash(self):
        from enhanced_agent_bus.session_governance_sdk import SessionGovernanceClient

        c = SessionGovernanceClient(base_url="http://localhost:8000/")
        assert c.base_url == "http://localhost:8000"

    def test_get_headers_with_tenant(self):
        from enhanced_agent_bus.session_governance_sdk import SessionGovernanceClient

        c = SessionGovernanceClient(default_tenant_id="default-t")
        h = c._get_headers()
        assert h["X-Tenant-ID"] == "default-t"

    def test_get_headers_override_tenant(self):
        from enhanced_agent_bus.session_governance_sdk import SessionGovernanceClient

        c = SessionGovernanceClient(default_tenant_id="default-t")
        h = c._get_headers(tenant_id="override-t")
        assert h["X-Tenant-ID"] == "override-t"

    def test_get_headers_no_tenant_raises(self):
        from enhanced_agent_bus.session_governance_sdk import SessionGovernanceClient

        c = SessionGovernanceClient()
        with pytest.raises(ValueError, match="tenant_id is required"):
            c._get_headers()

    def test_handle_error_404(self):
        from enhanced_agent_bus.session_governance_sdk import (
            SessionGovernanceClient,
            SessionNotFoundError,
        )

        c = SessionGovernanceClient(default_tenant_id="t")
        resp = MagicMock()
        resp.status_code = 404
        resp.json.return_value = {"detail": "not found"}
        with pytest.raises(SessionNotFoundError):
            c._handle_error(resp)

    def test_handle_error_403(self):
        from enhanced_agent_bus.session_governance_sdk import (
            SessionGovernanceClient,
            TenantAccessDeniedError,
        )

        c = SessionGovernanceClient(default_tenant_id="t")
        resp = MagicMock()
        resp.status_code = 403
        resp.json.return_value = {"detail": "denied"}
        with pytest.raises(TenantAccessDeniedError):
            c._handle_error(resp)

    def test_handle_error_400(self):
        from enhanced_agent_bus.session_governance_sdk import (
            SessionGovernanceClient,
            SessionValidationError,
        )

        c = SessionGovernanceClient(default_tenant_id="t")
        resp = MagicMock()
        resp.status_code = 400
        resp.json.return_value = {"detail": "bad request"}
        with pytest.raises(SessionValidationError):
            c._handle_error(resp)

    def test_handle_error_422(self):
        from enhanced_agent_bus.session_governance_sdk import (
            SessionGovernanceClient,
            SessionValidationError,
        )

        c = SessionGovernanceClient(default_tenant_id="t")
        resp = MagicMock()
        resp.status_code = 422
        resp.json.return_value = {"detail": "unprocessable"}
        with pytest.raises(SessionValidationError):
            c._handle_error(resp)

    def test_handle_error_503(self):
        from enhanced_agent_bus.session_governance_sdk import (
            ServiceUnavailableError,
            SessionGovernanceClient,
        )

        c = SessionGovernanceClient(default_tenant_id="t")
        resp = MagicMock()
        resp.status_code = 503
        resp.json.return_value = {"detail": "unavailable"}
        with pytest.raises(ServiceUnavailableError):
            c._handle_error(resp)

    def test_handle_error_generic(self):
        from enhanced_agent_bus.session_governance_sdk import (
            SessionGovernanceClient,
            SessionSDKError,
        )

        c = SessionGovernanceClient(default_tenant_id="t")
        resp = MagicMock()
        resp.status_code = 502
        resp.json.return_value = {"detail": "bad gateway"}
        with pytest.raises(SessionSDKError):
            c._handle_error(resp)

    def test_handle_error_json_parse_failure(self):
        from enhanced_agent_bus.session_governance_sdk import (
            SessionGovernanceClient,
            SessionSDKError,
        )

        c = SessionGovernanceClient(default_tenant_id="t")
        resp = MagicMock()
        resp.status_code = 500
        resp.json.side_effect = ValueError("bad json")
        resp.text = "internal error"
        with pytest.raises(SessionSDKError):
            c._handle_error(resp)

    async def test_connect_creates_client(self):
        from enhanced_agent_bus.session_governance_sdk import SessionGovernanceClient

        c = SessionGovernanceClient(default_tenant_id="t")
        assert c._client is None
        await c.connect()
        assert c._client is not None
        await c.close()

    async def test_close_sets_none(self):
        from enhanced_agent_bus.session_governance_sdk import SessionGovernanceClient

        c = SessionGovernanceClient(default_tenant_id="t")
        await c.connect()
        await c.close()
        assert c._client is None

    async def test_close_when_no_client(self):
        from enhanced_agent_bus.session_governance_sdk import SessionGovernanceClient

        c = SessionGovernanceClient(default_tenant_id="t")
        await c.close()
        assert c._client is None

    async def test_aenter_aexit(self):
        from enhanced_agent_bus.session_governance_sdk import SessionGovernanceClient

        async with SessionGovernanceClient(default_tenant_id="t") as c:
            assert c._client is not None
        assert c._client is None

    async def test_create_session_no_tenant_raises(self):
        from enhanced_agent_bus.session_governance_sdk import SessionGovernanceClient

        c = SessionGovernanceClient()
        with pytest.raises(ValueError, match="tenant_id is required"):
            await c.create_session()

    async def test_create_session_auto_connect(self):
        from enhanced_agent_bus.session_governance_sdk import SessionGovernanceClient

        c = SessionGovernanceClient(default_tenant_id="t")
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"session_id": "s1", "tenant_id": "t"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            session = await c.create_session()
            assert session.session_id == "s1"
        await c.close()


class TestCreateClient:
    def test_create_client_default(self):
        from enhanced_agent_bus.session_governance_sdk import create_client

        c = create_client()
        assert c.base_url == "http://localhost:8000"
        assert c.default_tenant_id is None

    def test_create_client_with_tenant(self):
        from enhanced_agent_bus.session_governance_sdk import create_client

        c = create_client(tenant_id="my-tenant", timeout=60.0)
        assert c.default_tenant_id == "my-tenant"
        assert c.timeout == 60.0


# =============================================================================
# Module 3: deliberation_layer.impact_scorer
# =============================================================================


class TestImpactScorerInit:
    def test_default_init(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        scorer = ImpactScorer(enable_caching=False)
        assert scorer._enable_minicpm is False
        assert scorer._onnx_enabled is False
        assert scorer._enable_loco_operator is False
        assert scorer._embedding_cache is None

    def test_init_with_caching(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        scorer = ImpactScorer(enable_caching=True)
        assert scorer._embedding_cache is not None

    def test_init_loco_operator_failure_graceful(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        # LocoOperator init will fail (import or config error) and be caught gracefully
        scorer = ImpactScorer(
            enable_caching=False,
            enable_loco_operator=True,
        )
        # Should not raise; client may be None if import/init failed
        assert scorer._enable_loco_operator is True


class TestImpactScorerProperties:
    def test_minicpm_enabled(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        scorer = ImpactScorer(enable_caching=False)
        assert scorer.minicpm_enabled is False

    def test_loco_operator_available_no_client(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        scorer = ImpactScorer(enable_caching=False)
        assert scorer.loco_operator_available is False

    def test_loco_operator_available_client_not_available(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        scorer = ImpactScorer(enable_caching=False)
        scorer._loco_client = MagicMock()
        scorer._loco_client.is_available = False
        assert scorer.loco_operator_available is False

    def test_spec_to_artifact_score_no_evals(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        scorer = ImpactScorer(enable_caching=False)
        assert scorer.spec_to_artifact_score == 1.0

    def test_spec_to_artifact_score_with_overrides(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        scorer = ImpactScorer(enable_caching=False)
        scorer._total_evaluations = 10
        scorer._overrides = 2
        assert scorer.spec_to_artifact_score == 0.8


class TestImpactScorerMethods:
    def _make_scorer(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        return ImpactScorer(enable_caching=False)

    def test_calculate_impact_score_empty_message(self):
        scorer = self._make_scorer()
        score = scorer.calculate_impact_score({}, {})
        assert 0.0 <= score <= 1.0

    def test_calculate_impact_score_none_message(self):
        scorer = self._make_scorer()
        score = scorer.calculate_impact_score(None, {})
        assert 0.0 <= score <= 1.0

    def test_calculate_impact_score_critical_priority(self):
        scorer = self._make_scorer()
        score = scorer.calculate_impact_score({"content": "hello", "priority": "critical"}, {})
        assert score >= 0.7

    def test_calculate_impact_score_high_semantic(self):
        scorer = self._make_scorer()
        score = scorer.calculate_impact_score({"content": "critical security breach exploit"}, {})
        assert score >= 0.5

    def test_calculate_impact_score_semantic_override(self):
        scorer = self._make_scorer()
        score = scorer.calculate_impact_score({"content": "hello"}, {"semantic_override": 0.95})
        assert score >= 0.5

    def test_calculate_impact_score_object_message(self):
        scorer = self._make_scorer()
        msg = MagicMock()
        msg.from_agent = "agent-1"
        msg.priority = "normal"
        msg.tools = []
        msg.content = "test message"
        msg.payload = {}
        msg.message_type = ""
        score = scorer.calculate_impact_score(msg, {})
        assert 0.0 <= score <= 1.0

    def test_calculate_impact_score_priority_enum(self):
        scorer = self._make_scorer()
        priority_enum = MagicMock()
        priority_enum.name = "CRITICAL"
        score = scorer.calculate_impact_score({"content": "hello", "priority": priority_enum}, {})
        assert score >= 0.5

    def test_record_override(self):
        scorer = self._make_scorer()
        scorer.record_override()
        assert scorer._overrides == 1

    def test_get_spec_to_artifact_metrics(self):
        scorer = self._make_scorer()
        scorer._total_evaluations = 5
        scorer._overrides = 1
        metrics = scorer.get_spec_to_artifact_metrics()
        assert metrics["total_evaluations"] == 5
        assert metrics["overrides"] == 1
        assert metrics["override_rate"] == 0.2
        assert metrics["spec_to_artifact_score"] == 0.8

    def test_get_spec_to_artifact_metrics_zero_evals(self):
        scorer = self._make_scorer()
        metrics = scorer.get_spec_to_artifact_metrics()
        assert metrics["override_rate"] == 0.0

    def test_reset_history(self):
        scorer = self._make_scorer()
        scorer.calculate_impact_score({"from_agent": "a"}, {})
        scorer.reset_history()
        assert scorer._volume_counts == {}
        assert scorer._drift_history == {}


class TestPermissionScore:
    def _make_scorer(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        return ImpactScorer(enable_caching=False)

    def test_no_tools(self):
        scorer = self._make_scorer()
        assert scorer._calculate_permission_score({}) == 0.1

    def test_high_risk_tool(self):
        scorer = self._make_scorer()
        score = scorer._calculate_permission_score({"tools": [{"name": "execute_command"}]})
        assert score >= 0.7

    def test_read_tool(self):
        scorer = self._make_scorer()
        score = scorer._calculate_permission_score({"tools": [{"name": "read_file"}]})
        assert score == 0.2

    def test_unknown_tool(self):
        scorer = self._make_scorer()
        score = scorer._calculate_permission_score({"tools": [{"name": "custom_tool"}]})
        assert score == 0.3

    def test_string_tool(self):
        scorer = self._make_scorer()
        score = scorer._calculate_permission_score({"tools": ["shell_exec"]})
        assert score >= 0.7

    def test_object_message_tools(self):
        scorer = self._make_scorer()
        msg = MagicMock()
        msg.tools = [{"name": "get_data"}]
        score = scorer._calculate_permission_score(msg)
        assert score >= 0.1


class TestVolumeScore:
    def _make_scorer(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        return ImpactScorer(enable_caching=False)

    def test_new_agent(self):
        scorer = self._make_scorer()
        score = scorer._calculate_volume_score("new-agent")
        assert score == 0.1

    def test_medium_volume(self):
        scorer = self._make_scorer()
        for _ in range(30):
            scorer._calculate_volume_score("agent-x")
        score = scorer._calculate_volume_score("agent-x")
        assert score >= 0.2

    def test_high_volume(self):
        scorer = self._make_scorer()
        for _ in range(101):
            scorer._calculate_volume_score("agent-y")
        assert scorer._calculate_volume_score("agent-y") == 1.0


class TestContextScore:
    def _make_scorer(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        return ImpactScorer(enable_caching=False)

    def test_no_payload(self):
        scorer = self._make_scorer()
        score = scorer._calculate_context_score({}, {})
        assert score == 0.1

    def test_high_amount_payload(self):
        scorer = self._make_scorer()
        score = scorer._calculate_context_score({"payload": {"amount": 50000}}, {})
        assert score >= 0.5

    def test_object_message_no_dict_payload(self):
        scorer = self._make_scorer()
        msg = MagicMock()
        msg.payload = "string_payload"
        msg.content = "test"
        score = scorer._calculate_context_score(msg, {})
        assert score == 0.1


class TestDriftScore:
    def _make_scorer(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        return ImpactScorer(enable_caching=False)

    def test_first_request_no_drift(self):
        scorer = self._make_scorer()
        score = scorer._calculate_drift_score("agent-1", 0.4)
        assert score == 0.0

    def test_stable_agent_no_drift(self):
        scorer = self._make_scorer()
        for _ in range(5):
            scorer._calculate_drift_score("agent-2", 0.4)
        score = scorer._calculate_drift_score("agent-2", 0.4)
        assert score == 0.0

    def test_drifting_agent(self):
        scorer = self._make_scorer()
        for _ in range(5):
            scorer._calculate_drift_score("agent-3", 0.1)
        score = scorer._calculate_drift_score("agent-3", 0.9)
        assert score > 0.0


class TestSemanticScore:
    def _make_scorer(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        return ImpactScorer(enable_caching=False)

    def test_empty_text(self):
        scorer = self._make_scorer()
        assert scorer._calculate_semantic_score({}) == 0.0

    def test_keyword_hit(self):
        scorer = self._make_scorer()
        assert scorer._calculate_semantic_score({"content": "security alert"}) == 0.95

    def test_no_keyword(self):
        scorer = self._make_scorer()
        assert scorer._calculate_semantic_score({"content": "hello world"}) == 0.1


class TestKeywordScore:
    def _make_scorer(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        return ImpactScorer(enable_caching=False)

    def test_no_match(self):
        scorer = self._make_scorer()
        assert scorer._get_keyword_score("hello world") == 0.1

    def test_one_match(self):
        scorer = self._make_scorer()
        assert scorer._get_keyword_score("security issue") == 0.5

    def test_two_matches(self):
        scorer = self._make_scorer()
        assert scorer._get_keyword_score("security breach") == 0.75

    def test_many_matches(self):
        scorer = self._make_scorer()
        score = scorer._get_keyword_score("critical security breach exploit attack")
        assert score >= 0.75


class TestTypeFactor:
    def _make_scorer(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        return ImpactScorer(enable_caching=False)

    def test_governance_type(self):
        scorer = self._make_scorer()
        assert scorer._calculate_type_factor({"message_type": "governance"}) == 1.5

    def test_security_type(self):
        scorer = self._make_scorer()
        assert scorer._calculate_type_factor({"message_type": "security"}) == 1.4

    def test_financial_type(self):
        scorer = self._make_scorer()
        assert scorer._calculate_type_factor({"message_type": "financial"}) == 1.3

    def test_unknown_type(self):
        scorer = self._make_scorer()
        assert scorer._calculate_type_factor({"message_type": "info"}) == 1.0

    def test_object_message(self):
        scorer = self._make_scorer()
        msg = MagicMock()
        msg.message_type = "governance"
        assert scorer._calculate_type_factor(msg) == 1.5


class TestPriorityFactor:
    def _make_scorer(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        return ImpactScorer(enable_caching=False)

    def test_critical(self):
        scorer = self._make_scorer()
        assert scorer._calculate_priority_factor({"priority": "critical"}) == 1.0

    def test_high(self):
        scorer = self._make_scorer()
        assert scorer._calculate_priority_factor({"priority": "high"}) == 0.8

    def test_medium(self):
        scorer = self._make_scorer()
        assert scorer._calculate_priority_factor({"priority": "medium"}) == 0.5

    def test_low(self):
        scorer = self._make_scorer()
        assert scorer._calculate_priority_factor({"priority": "low"}) == 0.2

    def test_unknown(self):
        scorer = self._make_scorer()
        assert scorer._calculate_priority_factor({"priority": "weird"}) == 0.5

    def test_numeric_priority_3(self):
        scorer = self._make_scorer()
        assert scorer._calculate_priority_factor({"priority": "3"}) == 1.0

    def test_priority_from_context(self):
        scorer = self._make_scorer()
        assert (
            scorer._calculate_priority_factor({"priority": "low"}, {"priority": "critical"}) == 1.0
        )

    def test_priority_enum_with_value(self):
        scorer = self._make_scorer()
        p = MagicMock()
        p.value = "high"
        del p.name
        assert scorer._calculate_priority_factor({"priority": p}) == 0.8


class TestExtractContent:
    def _make_scorer(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        return ImpactScorer(enable_caching=False)

    def test_dict_content(self):
        scorer = self._make_scorer()
        text = scorer._extract_text_content({"content": "hello"})
        assert "hello" in text

    def test_object_content(self):
        scorer = self._make_scorer()
        msg = MagicMock()
        msg.content = "object content"
        msg.tools = []
        text = scorer._extract_text_content(msg)
        assert "object content" in text

    def test_payload_message(self):
        scorer = self._make_scorer()
        text = scorer._extract_text_content({"payload": {"message": "payload msg"}})
        assert "payload msg" in text

    def test_action_details_keys(self):
        scorer = self._make_scorer()
        text = scorer._extract_text_content(
            {"action": "do_thing", "details": "some details", "description": "desc", "text": "txt"}
        )
        assert "do_thing" in text
        assert "some details" in text

    def test_tool_names_dict(self):
        scorer = self._make_scorer()
        text = scorer._extract_text_content({"tools": [{"name": "my_tool"}]})
        assert "my_tool" in text

    def test_tool_names_string(self):
        scorer = self._make_scorer()
        text = scorer._extract_text_content({"tools": ["str_tool"]})
        assert "str_tool" in text

    def test_tool_names_from_object(self):
        scorer = self._make_scorer()
        msg = MagicMock()
        msg.content = ""
        msg.tools = ["obj_tool"]
        text = scorer._extract_text_content(msg)
        assert "obj_tool" in text


class TestBatchScoring:
    def _make_scorer(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        return ImpactScorer(enable_caching=False)

    def test_batch_score_impact(self):
        scorer = self._make_scorer()
        messages = [{"content": "hello"}, {"content": "security breach"}]
        scores = scorer.batch_score_impact(messages)
        assert len(scores) == 2
        assert all(0.0 <= s <= 1.0 for s in scores)

    def test_batch_score_impact_with_contexts(self):
        scorer = self._make_scorer()
        messages = [{"content": "a"}, {"content": "b"}]
        contexts = [{"priority": "low"}, {"priority": "high"}]
        scores = scorer.batch_score_impact(messages, contexts)
        assert len(scores) == 2

    def test_batch_score_impact_mismatched_contexts(self):
        scorer = self._make_scorer()
        with pytest.raises(ValueError, match="contexts length"):
            scorer.batch_score_impact([{"content": "a"}], [{}, {}])

    def test_score_messages_batch_fallback(self):
        scorer = self._make_scorer()
        messages = [{"content": "test1"}, {"content": "test2"}]
        scores = scorer.score_messages_batch(messages)
        assert len(scores) == 2


class TestImpactScorerAsync:
    async def test_initialize_no_cache(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        scorer = ImpactScorer(enable_caching=False)
        result = await scorer.initialize()
        assert result is True

    async def test_close_no_cache(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        scorer = ImpactScorer(enable_caching=False)
        await scorer.close()

    async def test_score_with_loco_operator_unavailable(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        scorer = ImpactScorer(enable_caching=False)
        result = await scorer._score_with_loco_operator("action", {})
        assert result is None

    async def test_initialize_with_cache(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        scorer = ImpactScorer(enable_caching=True)
        mock_cache = AsyncMock()
        mock_cache.initialize = AsyncMock(return_value=True)
        scorer._embedding_cache = mock_cache
        result = await scorer.initialize()
        assert result is True

    async def test_close_with_cache(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        scorer = ImpactScorer(enable_caching=True)
        mock_cache = AsyncMock()
        scorer._embedding_cache = mock_cache
        await scorer.close()
        mock_cache.close.assert_called_once()


class TestImpactScorerMisc:
    def test_reset_class_cache(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        ImpactScorer.reset_class_cache()

    def test_clear_tokenization_cache(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        scorer = ImpactScorer(enable_caching=False)
        scorer._tokenization_cache["key"] = "val"
        scorer.clear_tokenization_cache()
        assert scorer._tokenization_cache == {}

    def test_generate_cache_key(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        scorer = ImpactScorer(enable_caching=False)
        key = scorer._generate_cache_key("test text")
        assert key.startswith("impact:embedding:")
        assert len(key) > 20

    def test_generate_cache_key_deterministic(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        scorer = ImpactScorer(enable_caching=False)
        k1 = scorer._generate_cache_key("same text")
        k2 = scorer._generate_cache_key("same text")
        assert k1 == k2

    def test_generate_cache_key_different_text(self):
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        scorer = ImpactScorer(enable_caching=False)
        k1 = scorer._generate_cache_key("text a")
        k2 = scorer._generate_cache_key("text b")
        assert k1 != k2
