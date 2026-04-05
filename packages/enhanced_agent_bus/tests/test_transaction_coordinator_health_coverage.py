# Constitutional Hash: 608508a9bd224290
"""
Comprehensive coverage tests for transaction_coordinator_health.py.

Targets ≥95% coverage of all classes, methods, branches, and edge cases.
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any
from unittest.mock import MagicMock, patch

from enhanced_agent_bus._compat.types import CONSTITUTIONAL_HASH

# Import via the metrics module to avoid circular import issues.
# transaction_coordinator_metrics re-exports everything from the health module.
from enhanced_agent_bus.transaction_coordinator_metrics import (
    DashboardQueries,
    HealthChecker,
    HealthCheckResult,
    HealthStatus,
    TransactionMetrics,
    reset_metrics_cache,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_metrics() -> TransactionMetrics:
    """Return a fresh TransactionMetrics with cleared cache to avoid collisions."""
    reset_metrics_cache()
    return TransactionMetrics()


class _StubMetrics:
    def __init__(self, consistency_ratio: float, latency: dict | None, concurrent: float):
        self.concurrent_transactions = MagicMock()
        self.get_consistency_ratio = MagicMock(return_value=consistency_ratio)
        self.get_latency_percentiles = MagicMock(
            return_value=latency or {"p50": 0.0, "p95": 0.0, "p99": 0.0}
        )
        self._get_gauge_value = MagicMock(return_value=concurrent)
        self.update_health_gauge = MagicMock()


def _mock_metrics(
    consistency_ratio: float = 1.0,
    latency: dict | None = None,
    concurrent: float = 0.0,
) -> Any:
    """Return a stub TransactionMetrics with preset return values.

    Using a stub class avoids mock spec/AttributeError issues when running
    in large test suites where MagicMock might be globally intercepted.
    """
    return _StubMetrics(consistency_ratio, latency, concurrent)


# ===========================================================================
# HealthCheckResult dataclass
# ===========================================================================


class TestHealthCheckResult:
    def test_fields_exist(self):
        """HealthCheckResult has the expected fields."""
        field_names = {f.name for f in fields(HealthCheckResult)}
        assert "status" in field_names
        assert "consistency_ratio" in field_names
        assert "message" in field_names
        assert "details" in field_names

    def test_instantiation_defaults(self):
        """details defaults to an empty dict."""
        result = HealthCheckResult(
            status=HealthStatus.HEALTHY,
            consistency_ratio=1.0,
            message="ok",
        )
        assert result.details == {}

    def test_instantiation_with_details(self):
        result = HealthCheckResult(
            status=HealthStatus.DEGRADED,
            consistency_ratio=0.995,
            message="degraded",
            details={"key": "value"},
        )
        assert result.details == {"key": "value"}
        assert result.status == HealthStatus.DEGRADED
        assert result.consistency_ratio == 0.995

    def test_instantiation_unhealthy(self):
        result = HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            consistency_ratio=0.9,
            message="unhealthy",
        )
        assert result.status == HealthStatus.UNHEALTHY

    def test_details_default_factory_independent(self):
        """Each instance gets its own details dict."""
        r1 = HealthCheckResult(status=HealthStatus.HEALTHY, consistency_ratio=1.0, message="a")
        r2 = HealthCheckResult(status=HealthStatus.HEALTHY, consistency_ratio=1.0, message="b")
        r1.details["x"] = 1
        assert "x" not in r2.details


# ===========================================================================
# HealthChecker - initialisation
# ===========================================================================


class TestHealthCheckerInit:
    def test_default_thresholds(self):
        m = _mock_metrics()
        hc = HealthChecker(metrics=m)
        assert hc.healthy_threshold == 0.999
        assert hc.degraded_threshold == 0.99
        assert hc.metrics is m

    def test_custom_thresholds(self):
        m = _mock_metrics()
        hc = HealthChecker(metrics=m, healthy_threshold=0.9, degraded_threshold=0.8)
        assert hc.healthy_threshold == 0.9
        assert hc.degraded_threshold == 0.8

    def test_metrics_stored(self):
        m = _mock_metrics()
        hc = HealthChecker(metrics=m)
        assert hc.metrics is m


# ===========================================================================
# HealthChecker.check_health - status branches
# ===========================================================================


class TestHealthCheckerCheckHealth:
    def _checker(self, ratio: float, **kwargs) -> HealthChecker:
        return HealthChecker(metrics=_mock_metrics(consistency_ratio=ratio), **kwargs)

    # --- HEALTHY branch ---

    def test_healthy_when_ratio_equals_threshold(self):
        hc = self._checker(0.999)
        result = hc.check_health()
        assert result.status == HealthStatus.HEALTHY

    def test_healthy_when_ratio_above_threshold(self):
        hc = self._checker(1.0)
        result = hc.check_health()
        assert result.status == HealthStatus.HEALTHY

    def test_healthy_message_contains_ratio(self):
        hc = self._checker(1.0)
        result = hc.check_health()
        assert "100.00%" in result.message

    def test_healthy_consistency_ratio_returned(self):
        hc = self._checker(0.999)
        result = hc.check_health()
        assert result.consistency_ratio == 0.999

    # --- DEGRADED branch ---

    def test_degraded_when_ratio_equals_degraded_threshold(self):
        hc = self._checker(0.99)
        result = hc.check_health()
        assert result.status == HealthStatus.DEGRADED

    def test_degraded_when_ratio_between_thresholds(self):
        hc = self._checker(0.995)
        result = hc.check_health()
        assert result.status == HealthStatus.DEGRADED

    def test_degraded_message_contains_ratio(self):
        hc = self._checker(0.995)
        result = hc.check_health()
        assert "99.50%" in result.message

    def test_degraded_consistency_ratio_returned(self):
        hc = self._checker(0.995)
        result = hc.check_health()
        assert result.consistency_ratio == 0.995

    # --- UNHEALTHY branch ---

    def test_unhealthy_when_ratio_below_degraded_threshold(self):
        hc = self._checker(0.98)
        result = hc.check_health()
        assert result.status == HealthStatus.UNHEALTHY

    def test_unhealthy_when_ratio_zero(self):
        hc = self._checker(0.0)
        result = hc.check_health()
        assert result.status == HealthStatus.UNHEALTHY

    def test_unhealthy_message_contains_ratio(self):
        hc = self._checker(0.5)
        result = hc.check_health()
        assert "50.00%" in result.message

    def test_unhealthy_consistency_ratio_returned(self):
        hc = self._checker(0.0)
        result = hc.check_health()
        assert result.consistency_ratio == 0.0

    # --- details dict ---

    def test_details_contains_consistency_ratio(self):
        hc = self._checker(1.0)
        result = hc.check_health()
        assert "consistency_ratio" in result.details
        assert result.details["consistency_ratio"] == 1.0

    def test_details_contains_latency_percentiles(self):
        hc = self._checker(1.0)
        result = hc.check_health()
        assert "latency_percentiles_ms" in result.details

    def test_details_contains_concurrent_transactions(self):
        hc = self._checker(1.0)
        result = hc.check_health()
        assert "concurrent_transactions" in result.details

    def test_details_contains_thresholds(self):
        hc = self._checker(1.0)
        result = hc.check_health()
        assert "thresholds" in result.details
        assert result.details["thresholds"]["healthy"] == 0.999
        assert result.details["thresholds"]["degraded"] == 0.99

    def test_details_thresholds_reflect_custom_values(self):
        hc = self._checker(1.0, healthy_threshold=0.95, degraded_threshold=0.90)
        result = hc.check_health()
        assert result.details["thresholds"]["healthy"] == 0.95
        assert result.details["thresholds"]["degraded"] == 0.90

    def test_update_health_gauge_called(self):
        m = _mock_metrics(1.0)
        hc = HealthChecker(metrics=m)
        hc.check_health()
        m.update_health_gauge.assert_called_once()

    def test_get_latency_percentiles_called(self):
        m = _mock_metrics(1.0)
        hc = HealthChecker(metrics=m)
        hc.check_health()
        m.get_latency_percentiles.assert_called_once()

    def test_get_gauge_value_called_with_concurrent(self):
        m = _mock_metrics(1.0)
        hc = HealthChecker(metrics=m)
        hc.check_health()
        m._get_gauge_value.assert_called_once_with(m.concurrent_transactions)

    def test_latency_values_in_details(self):
        latency = {"p50": 1.0, "p95": 5.0, "p99": 10.0}
        m = _mock_metrics(1.0, latency=latency)
        hc = HealthChecker(metrics=m)
        result = hc.check_health()
        assert result.details["latency_percentiles_ms"] == latency

    def test_concurrent_value_in_details(self):
        m = _mock_metrics(1.0, concurrent=7.0)
        hc = HealthChecker(metrics=m)
        result = hc.check_health()
        assert result.details["concurrent_transactions"] == 7.0

    # --- boundary conditions ---

    def test_just_above_healthy_threshold(self):
        hc = self._checker(0.9991)
        result = hc.check_health()
        assert result.status == HealthStatus.HEALTHY

    def test_just_below_healthy_threshold(self):
        hc = self._checker(0.9989)
        result = hc.check_health()
        assert result.status == HealthStatus.DEGRADED

    def test_just_above_degraded_threshold(self):
        hc = self._checker(0.9901)
        result = hc.check_health()
        assert result.status == HealthStatus.DEGRADED

    def test_just_below_degraded_threshold(self):
        hc = self._checker(0.9899)
        result = hc.check_health()
        assert result.status == HealthStatus.UNHEALTHY

    # --- with real TransactionMetrics ---

    def test_with_real_metrics_no_transactions(self):
        """No transactions → perfect consistency → HEALTHY."""
        m = _fresh_metrics()
        hc = HealthChecker(metrics=m)
        result = hc.check_health()
        assert result.status == HealthStatus.HEALTHY
        assert result.consistency_ratio == 1.0

    def test_with_real_metrics_after_failures(self):
        """Many failures → UNHEALTHY."""
        m = _fresh_metrics()
        # 10 total, 0 success → ratio = 0.0
        for _ in range(10):
            m.record_transaction_start()
            m.record_transaction_failure(0.1)
        hc = HealthChecker(metrics=m)
        result = hc.check_health()
        assert result.status == HealthStatus.UNHEALTHY

    def test_with_real_metrics_mostly_success(self):
        """High success rate → HEALTHY."""
        m = _fresh_metrics()
        # 1000 total, 1000 success → 100%
        for _ in range(1000):
            m.record_transaction_start()
            m.record_transaction_success(0.001)
        hc = HealthChecker(metrics=m)
        result = hc.check_health()
        assert result.status == HealthStatus.HEALTHY


# ===========================================================================
# HealthChecker.is_healthy
# ===========================================================================


class TestHealthCheckerIsHealthy:
    def test_returns_true_when_healthy(self):
        hc = HealthChecker(metrics=_mock_metrics(1.0))
        assert hc.is_healthy() is True

    def test_returns_false_when_degraded(self):
        hc = HealthChecker(metrics=_mock_metrics(0.995))
        assert hc.is_healthy() is False

    def test_returns_false_when_unhealthy(self):
        hc = HealthChecker(metrics=_mock_metrics(0.0))
        assert hc.is_healthy() is False

    def test_is_healthy_at_exact_threshold(self):
        hc = HealthChecker(metrics=_mock_metrics(0.999))
        assert hc.is_healthy() is True

    def test_is_healthy_just_below_threshold(self):
        hc = HealthChecker(metrics=_mock_metrics(0.9989))
        assert hc.is_healthy() is False

    def test_is_healthy_calls_check_health(self):
        m = _mock_metrics(1.0)
        hc = HealthChecker(metrics=m)
        # Each call to is_healthy calls check_health which calls update_health_gauge
        hc.is_healthy()
        m.update_health_gauge.assert_called_once()

    def test_is_healthy_with_real_metrics(self):
        m = _fresh_metrics()
        hc = HealthChecker(metrics=m)
        assert hc.is_healthy() is True


# ===========================================================================
# HealthChecker.to_dict
# ===========================================================================


class TestHealthCheckerToDict:
    def test_returns_dict(self):
        hc = HealthChecker(metrics=_mock_metrics(1.0))
        result = hc.to_dict()
        assert isinstance(result, dict)

    def test_contains_status_key(self):
        hc = HealthChecker(metrics=_mock_metrics(1.0))
        result = hc.to_dict()
        assert "status" in result

    def test_status_value_is_string(self):
        hc = HealthChecker(metrics=_mock_metrics(1.0))
        result = hc.to_dict()
        assert isinstance(result["status"], str)

    def test_status_healthy_string(self):
        hc = HealthChecker(metrics=_mock_metrics(1.0))
        result = hc.to_dict()
        assert result["status"] == HealthStatus.HEALTHY.value

    def test_status_degraded_string(self):
        hc = HealthChecker(metrics=_mock_metrics(0.995))
        result = hc.to_dict()
        assert result["status"] == HealthStatus.DEGRADED.value

    def test_status_unhealthy_string(self):
        hc = HealthChecker(metrics=_mock_metrics(0.0))
        result = hc.to_dict()
        assert result["status"] == HealthStatus.UNHEALTHY.value

    def test_contains_consistency_ratio(self):
        hc = HealthChecker(metrics=_mock_metrics(0.999))
        result = hc.to_dict()
        assert "consistency_ratio" in result
        assert result["consistency_ratio"] == 0.999

    def test_contains_message(self):
        hc = HealthChecker(metrics=_mock_metrics(1.0))
        result = hc.to_dict()
        assert "message" in result
        assert isinstance(result["message"], str)

    def test_contains_details(self):
        hc = HealthChecker(metrics=_mock_metrics(1.0))
        result = hc.to_dict()
        assert "details" in result
        assert isinstance(result["details"], dict)

    def test_contains_constitutional_hash(self):
        hc = HealthChecker(metrics=_mock_metrics(1.0))
        result = hc.to_dict()
        assert "constitutional_hash" in result
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_constitutional_hash_value(self):
        hc = HealthChecker(metrics=_mock_metrics(1.0))
        result = hc.to_dict()
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_calls_check_health_once(self):
        m = _mock_metrics(1.0)
        hc = HealthChecker(metrics=m)
        hc.to_dict()
        # update_health_gauge is called once inside check_health
        m.update_health_gauge.assert_called_once()

    def test_to_dict_with_real_metrics(self):
        m = _fresh_metrics()
        hc = HealthChecker(metrics=m)
        result = hc.to_dict()
        assert result["status"] == HealthStatus.HEALTHY.value
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH


# ===========================================================================
# DashboardQueries - static methods
# ===========================================================================


class TestDashboardQueriesTransactionRate:
    def test_default_time_window(self):
        q = DashboardQueries.transaction_rate()
        assert "5m" in q
        assert "acgs_transactions_total" in q
        assert 'status="started"' in q

    def test_custom_time_window(self):
        q = DashboardQueries.transaction_rate("10m")
        assert "10m" in q

    def test_returns_string(self):
        assert isinstance(DashboardQueries.transaction_rate(), str)

    def test_rate_function_present(self):
        q = DashboardQueries.transaction_rate()
        assert q.startswith("rate(")


class TestDashboardQueriesSuccessRate:
    def test_default_time_window(self):
        q = DashboardQueries.success_rate()
        assert "5m" in q
        assert "acgs_transactions_success_total" in q
        assert "acgs_transactions_total" in q

    def test_custom_time_window(self):
        q = DashboardQueries.success_rate("1m")
        assert "1m" in q

    def test_contains_division_operator(self):
        q = DashboardQueries.success_rate()
        assert "/" in q

    def test_returns_string(self):
        assert isinstance(DashboardQueries.success_rate(), str)


class TestDashboardQueriesLatencyPercentile:
    def test_p50_computation(self):
        q = DashboardQueries.latency_percentile(50)
        assert "0.5" in q

    def test_p95_computation(self):
        q = DashboardQueries.latency_percentile(95)
        assert "0.95" in q

    def test_p99_computation(self):
        q = DashboardQueries.latency_percentile(99)
        assert "0.99" in q

    def test_default_status_success(self):
        q = DashboardQueries.latency_percentile(99)
        assert 'status="success"' in q

    def test_custom_status(self):
        q = DashboardQueries.latency_percentile(99, status="failure")
        assert 'status="failure"' in q

    def test_histogram_quantile_function(self):
        q = DashboardQueries.latency_percentile(50)
        assert "histogram_quantile" in q

    def test_bucket_label(self):
        q = DashboardQueries.latency_percentile(50)
        assert "by (le)" in q

    def test_metric_name_present(self):
        q = DashboardQueries.latency_percentile(50)
        assert "acgs_transaction_latency_seconds_bucket" in q

    def test_returns_string(self):
        assert isinstance(DashboardQueries.latency_percentile(50), str)


class TestDashboardQueriesP50P95P99Latency:
    def test_p50_latency_default(self):
        q = DashboardQueries.p50_latency()
        assert "0.5" in q
        assert 'status="success"' in q

    def test_p50_latency_custom_status(self):
        q = DashboardQueries.p50_latency(status="failure")
        assert 'status="failure"' in q

    def test_p95_latency_default(self):
        q = DashboardQueries.p95_latency()
        assert "0.95" in q
        assert 'status="success"' in q

    def test_p95_latency_custom_status(self):
        q = DashboardQueries.p95_latency(status="timeout")
        assert 'status="timeout"' in q

    def test_p99_latency_default(self):
        q = DashboardQueries.p99_latency()
        assert "0.99" in q
        assert 'status="success"' in q

    def test_p99_latency_custom_status(self):
        q = DashboardQueries.p99_latency(status="compensated")
        assert 'status="compensated"' in q

    def test_p50_delegates_to_latency_percentile(self):
        assert DashboardQueries.p50_latency() == DashboardQueries.latency_percentile(50, "success")

    def test_p95_delegates_to_latency_percentile(self):
        assert DashboardQueries.p95_latency() == DashboardQueries.latency_percentile(95, "success")

    def test_p99_delegates_to_latency_percentile(self):
        assert DashboardQueries.p99_latency() == DashboardQueries.latency_percentile(99, "success")


class TestDashboardQueriesCompensationRate:
    def test_default_time_window(self):
        q = DashboardQueries.compensation_rate()
        assert "5m" in q
        assert "acgs_compensations_total" in q

    def test_custom_time_window(self):
        q = DashboardQueries.compensation_rate("15m")
        assert "15m" in q

    def test_returns_string(self):
        assert isinstance(DashboardQueries.compensation_rate(), str)

    def test_rate_function_present(self):
        q = DashboardQueries.compensation_rate()
        assert q.startswith("rate(")


class TestDashboardQueriesCheckpointSaveRate:
    def test_default_time_window(self):
        q = DashboardQueries.checkpoint_save_rate()
        assert "5m" in q
        assert "acgs_checkpoint_saves_total" in q

    def test_custom_time_window(self):
        q = DashboardQueries.checkpoint_save_rate("30m")
        assert "30m" in q

    def test_returns_string(self):
        assert isinstance(DashboardQueries.checkpoint_save_rate(), str)

    def test_rate_function_present(self):
        q = DashboardQueries.checkpoint_save_rate()
        assert q.startswith("rate(")


class TestDashboardQueriesConcurrentTransactions:
    def test_returns_metric_name(self):
        q = DashboardQueries.concurrent_transactions()
        assert q == "acgs_concurrent_transactions"

    def test_returns_string(self):
        assert isinstance(DashboardQueries.concurrent_transactions(), str)


class TestDashboardQueriesConsistencyRatio:
    def test_returns_metric_name(self):
        q = DashboardQueries.consistency_ratio()
        assert q == "acgs_consistency_ratio"

    def test_returns_string(self):
        assert isinstance(DashboardQueries.consistency_ratio(), str)


class TestDashboardQueriesHealthStatus:
    def test_returns_metric_name(self):
        q = DashboardQueries.health_status()
        assert q == "acgs_transaction_coordinator_health"

    def test_returns_string(self):
        assert isinstance(DashboardQueries.health_status(), str)


# ===========================================================================
# Integration: HealthChecker with full real metrics lifecycle
# ===========================================================================


class TestHealthCheckerIntegration:
    def test_degraded_ratio_real_metrics(self):
        """~99.5% success → DEGRADED."""
        m = _fresh_metrics()
        # 200 total: 199 success, 1 failure → 99.5%
        for _ in range(199):
            m.record_transaction_start()
            m.record_transaction_success(0.001)
        m.record_transaction_start()
        m.record_transaction_failure(0.1)
        hc = HealthChecker(metrics=m)
        result = hc.check_health()
        assert result.status == HealthStatus.DEGRADED

    def test_to_dict_unhealthy_status(self):
        """to_dict reflects unhealthy status correctly."""
        m = _mock_metrics(0.0)
        hc = HealthChecker(metrics=m)
        d = hc.to_dict()
        assert d["status"] == "unhealthy"

    def test_to_dict_degraded_status(self):
        m = _mock_metrics(0.995)
        hc = HealthChecker(metrics=m)
        d = hc.to_dict()
        assert d["status"] == "degraded"

    def test_check_health_returns_health_check_result(self):
        hc = HealthChecker(metrics=_mock_metrics(1.0))
        result = hc.check_health()
        assert isinstance(result, HealthCheckResult)

    def test_multiple_check_health_calls(self):
        """Repeated calls work without error."""
        m = _mock_metrics(1.0)
        hc = HealthChecker(metrics=m)
        for _ in range(5):
            result = hc.check_health()
            assert result.status == HealthStatus.HEALTHY

    def test_is_healthy_multiple_calls(self):
        hc = HealthChecker(metrics=_mock_metrics(1.0))
        for _ in range(3):
            assert hc.is_healthy() is True

    def test_custom_thresholds_healthy(self):
        """Custom thresholds: 90% = healthy."""
        m = _mock_metrics(0.91)
        hc = HealthChecker(metrics=m, healthy_threshold=0.9, degraded_threshold=0.8)
        assert hc.check_health().status == HealthStatus.HEALTHY

    def test_custom_thresholds_degraded(self):
        """Custom thresholds: 85% = degraded."""
        m = _mock_metrics(0.85)
        hc = HealthChecker(metrics=m, healthy_threshold=0.9, degraded_threshold=0.8)
        assert hc.check_health().status == HealthStatus.DEGRADED

    def test_custom_thresholds_unhealthy(self):
        """Custom thresholds: 70% = unhealthy."""
        m = _mock_metrics(0.70)
        hc = HealthChecker(metrics=m, healthy_threshold=0.9, degraded_threshold=0.8)
        assert hc.check_health().status == HealthStatus.UNHEALTHY

    def test_all_dashboard_queries_return_nonempty_strings(self):
        """All static query methods return non-empty strings."""
        methods = [
            DashboardQueries.transaction_rate,
            DashboardQueries.success_rate,
            lambda: DashboardQueries.latency_percentile(50),
            DashboardQueries.p50_latency,
            DashboardQueries.p95_latency,
            DashboardQueries.p99_latency,
            DashboardQueries.compensation_rate,
            DashboardQueries.checkpoint_save_rate,
            DashboardQueries.concurrent_transactions,
            DashboardQueries.consistency_ratio,
            DashboardQueries.health_status,
        ]
        for method in methods:
            q = method()
            assert isinstance(q, str) and len(q) > 0
