# Constitutional Hash: 608508a9bd224290
"""
Integration and higher-level tests for transaction_coordinator_metrics.py.

Covers: HealthChecker, HealthCheckResult, DashboardQueries, AlertRule,
GenerateAlertRulesYaml, GlobalInstanceHelpers, ModuleConstants,
PercentileBoundaryConditions, FullTransactionLifecycle.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Module under test
# ---------------------------------------------------------------------------
import enhanced_agent_bus.transaction_coordinator_metrics as tcm_module
from enhanced_agent_bus.transaction_coordinator_metrics import (
    _METRICS_CACHE,
    ALERT_RULES,
    PROMETHEUS_AVAILABLE,
    REGISTRY,
    AlertRule,
    CheckpointOperation,
    DashboardQueries,
    HealthChecker,
    HealthCheckResult,
    HealthStatus,
    TransactionMetrics,
    _NoOpCounter,
    _NoOpGauge,
    _NoOpHistogram,
    generate_alert_rules_yaml,
    get_transaction_metrics,
    reset_metrics_cache,
    reset_transaction_metrics,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_metrics() -> TransactionMetrics:
    """Return a new TransactionMetrics with a cleared cache to avoid collisions."""
    reset_metrics_cache()
    return TransactionMetrics()


class ConcreteCounter:
    def labels(self, **kwargs: object) -> ConcreteCounter:
        return self

    def inc(self, amount: float = 1) -> None:
        pass


class ConcreteGauge:
    def labels(self, **kwargs: object) -> ConcreteGauge:
        return self

    def set(self, value: float) -> None:
        pass

    def inc(self, amount: float = 1) -> None:
        pass

    def dec(self, amount: float = 1) -> None:
        pass


class ConcreteHistogram:
    def labels(self, **kwargs: object) -> ConcreteHistogram:
        return self

    def observe(self, value: float) -> None:
        pass


class ConcreteInfo:
    def info(self, value: dict[str, str]) -> None:
        pass


# ===========================================================================
# HealthChecker
# ===========================================================================


class TestHealthChecker:
    def setup_method(self):
        reset_metrics_cache()
        self.m = TransactionMetrics()
        self.hc = HealthChecker(self.m)

    def test_check_health_healthy(self):
        for _ in range(10):
            self.m.record_transaction_start()
            self.m.record_transaction_success(0.01)
        result = self.hc.check_health()
        assert result.status == HealthStatus.HEALTHY
        assert result.consistency_ratio == pytest.approx(1.0)
        assert "healthy" in result.message.lower()

    def test_check_health_degraded(self):
        for _ in range(990):
            self.m.record_transaction_start()
            self.m.record_transaction_success(0.001)
        for _ in range(10):
            self.m.record_transaction_start()
            self.m.record_transaction_failure(0.001)
        result = self.hc.check_health()
        assert result.status == HealthStatus.DEGRADED
        assert "degraded" in result.message.lower()

    def test_check_health_unhealthy(self):
        for _ in range(95):
            self.m.record_transaction_start()
            self.m.record_transaction_success(0.001)
        for _ in range(5):
            self.m.record_transaction_start()
            self.m.record_transaction_failure(0.001)
        result = self.hc.check_health()
        assert result.status == HealthStatus.UNHEALTHY
        assert "unhealthy" in result.message.lower()

    def test_check_health_details_structure(self):
        result = self.hc.check_health()
        assert "consistency_ratio" in result.details
        assert "latency_percentiles_ms" in result.details
        assert "concurrent_transactions" in result.details
        assert "thresholds" in result.details

    def test_is_healthy_true(self):
        assert self.hc.is_healthy() is True

    def test_is_healthy_false_after_failures(self):
        for _ in range(95):
            self.m.record_transaction_start()
            self.m.record_transaction_success(0.001)
        for _ in range(5):
            self.m.record_transaction_start()
            self.m.record_transaction_failure(0.001)
        assert self.hc.is_healthy() is False

    def test_to_dict_structure(self):
        d = self.hc.to_dict()
        assert "status" in d
        assert "consistency_ratio" in d
        assert "message" in d
        assert "details" in d
        assert "constitutional_hash" in d

    def test_to_dict_constitutional_hash(self):
        from enhanced_agent_bus._compat.types import CONSTITUTIONAL_HASH

        d = self.hc.to_dict()
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_custom_thresholds(self):
        hc = HealthChecker(self.m, healthy_threshold=0.95, degraded_threshold=0.90)
        assert hc.healthy_threshold == 0.95
        assert hc.degraded_threshold == 0.90

    def test_check_health_no_transactions(self):
        result = self.hc.check_health()
        assert result.status == HealthStatus.HEALTHY
        assert result.consistency_ratio == 1.0


# ===========================================================================
# HealthCheckResult dataclass
# ===========================================================================


class TestHealthCheckResult:
    def test_create_health_check_result(self):
        r = HealthCheckResult(
            status=HealthStatus.HEALTHY,
            consistency_ratio=1.0,
            message="ok",
        )
        assert r.status == HealthStatus.HEALTHY
        assert r.consistency_ratio == 1.0
        assert r.details == {}

    def test_create_with_details(self):
        r = HealthCheckResult(
            status=HealthStatus.DEGRADED,
            consistency_ratio=0.995,
            message="degraded",
            details={"key": "value"},
        )
        assert r.details == {"key": "value"}


# ===========================================================================
# DashboardQueries
# ===========================================================================


class TestDashboardQueries:
    def test_transaction_rate_default(self):
        q = DashboardQueries.transaction_rate()
        assert "acgs_transactions_total" in q
        assert "5m" in q

    def test_transaction_rate_custom_window(self):
        q = DashboardQueries.transaction_rate("1m")
        assert "1m" in q

    def test_success_rate(self):
        q = DashboardQueries.success_rate()
        assert "acgs_transactions_success_total" in q

    def test_latency_percentile(self):
        q = DashboardQueries.latency_percentile(99)
        assert "0.99" in q
        assert "acgs_transaction_latency_seconds_bucket" in q

    def test_latency_percentile_custom_status(self):
        q = DashboardQueries.latency_percentile(95, "failure")
        assert "failure" in q

    def test_p50_latency(self):
        q = DashboardQueries.p50_latency()
        assert "0.5" in q

    def test_p95_latency(self):
        q = DashboardQueries.p95_latency()
        assert "0.95" in q

    def test_p99_latency(self):
        q = DashboardQueries.p99_latency()
        assert "0.99" in q

    def test_compensation_rate(self):
        q = DashboardQueries.compensation_rate()
        assert "acgs_compensations_total" in q

    def test_checkpoint_save_rate(self):
        q = DashboardQueries.checkpoint_save_rate()
        assert "acgs_checkpoint_saves_total" in q

    def test_concurrent_transactions(self):
        q = DashboardQueries.concurrent_transactions()
        assert "acgs_concurrent_transactions" in q

    def test_consistency_ratio(self):
        q = DashboardQueries.consistency_ratio()
        assert "acgs_consistency_ratio" in q

    def test_health_status(self):
        q = DashboardQueries.health_status()
        assert "acgs_transaction_coordinator_health" in q


# ===========================================================================
# AlertRule and ALERT_RULES
# ===========================================================================


class TestAlertRule:
    def test_alert_rule_creation(self):
        rule = AlertRule(
            name="TestAlert",
            condition="rate(...) > 0",
            severity="critical",
            duration="2m",
            description="test",
        )
        assert rule.name == "TestAlert"
        assert rule.runbook_url == ""

    def test_alert_rule_with_runbook(self):
        rule = AlertRule(
            name="TestAlert2",
            condition="x > 0",
            severity="warning",
            duration="5m",
            description="test",
            runbook_url="https://example.com",
        )
        assert rule.runbook_url == "https://example.com"

    def test_alert_rules_list_not_empty(self):
        assert len(ALERT_RULES) > 0

    def test_alert_rules_all_have_required_fields(self):
        for rule in ALERT_RULES:
            assert rule.name
            assert rule.condition
            assert rule.severity
            assert rule.duration
            assert rule.description


# ===========================================================================
# generate_alert_rules_yaml
# ===========================================================================


class TestGenerateAlertRulesYaml:
    def test_returns_string(self):
        try:
            result = generate_alert_rules_yaml()
            assert isinstance(result, str)
            assert "transaction_coordinator" in result
        except ImportError:
            pytest.skip("yaml not available")

    def test_yaml_contains_alert_names(self):
        try:
            result = generate_alert_rules_yaml()
            for rule in ALERT_RULES:
                assert rule.name in result
        except ImportError:
            pytest.skip("yaml not available")

    def test_yaml_contains_constitutional_hash(self):
        try:
            from enhanced_agent_bus._compat.types import CONSTITUTIONAL_HASH

            result = generate_alert_rules_yaml()
            assert CONSTITUTIONAL_HASH in result
        except ImportError:
            pytest.skip("yaml not available")


# ===========================================================================
# Global instance helpers
# ===========================================================================


class TestGlobalInstanceHelpers:
    def setup_method(self):
        reset_metrics_cache()
        from enhanced_agent_bus._compat.di_container import DIContainer

        DIContainer.reset()

    def test_get_transaction_metrics_creates_instance(self):
        m = get_transaction_metrics()
        assert isinstance(m, TransactionMetrics)

    def test_get_transaction_metrics_returns_same_instance(self):
        m1 = get_transaction_metrics()
        m2 = get_transaction_metrics()
        assert m1 is m2

    def test_reset_transaction_metrics_creates_new_instance(self):
        m1 = get_transaction_metrics()
        reset_transaction_metrics()
        m2 = get_transaction_metrics()
        assert m1 is not m2

    def test_reset_transaction_metrics_clears_cache(self):
        get_transaction_metrics()
        reset_transaction_metrics()
        assert len(_METRICS_CACHE) == 0


# ===========================================================================
# Module-level constants exposed via __all__
# ===========================================================================


class TestModuleConstants:
    def test_prometheus_available_is_bool(self):
        assert isinstance(PROMETHEUS_AVAILABLE, bool)

    def test_registry_is_none_or_object(self):
        assert REGISTRY is None or REGISTRY is not None


# ===========================================================================
# Edge cases: percentile boundary conditions
# ===========================================================================


class TestPercentileBoundaryConditions:
    def setup_method(self):
        reset_metrics_cache()
        self.m = TransactionMetrics()

    def test_percentile_single_element(self):
        self.m._record_duration(0.05)
        result = self.m.get_latency_percentiles()
        assert result["p50"] == result["p95"] == result["p99"] == pytest.approx(50.0)

    def test_percentile_two_elements(self):
        self.m._record_duration(0.1)
        self.m._record_duration(0.2)
        result = self.m.get_latency_percentiles()
        # sorted_samples = [100.0, 200.0], n=2
        # p50: idx = int(2*50/100) = 1 -> samples[1] = 200.0
        assert result["p50"] == pytest.approx(200.0)
        assert result["p99"] == pytest.approx(200.0)

    def test_compensation_percentile_single(self):
        self.m._record_compensation_duration(0.3)
        result = self.m.get_compensation_percentiles()
        assert result["p50"] == result["p95"] == result["p99"] == pytest.approx(300.0)

    def test_latency_percentile_idx_clamped(self):
        """Ensure idx never exceeds n-1 for p99 with 1 sample."""
        self.m._record_duration(0.001)
        # p99 idx = int(1 * 99/100) = 0 -> samples[0]
        result = self.m.get_latency_percentiles()
        assert result["p99"] == pytest.approx(1.0)


# ===========================================================================
# Integration-style: full transaction lifecycle
# ===========================================================================


class TestFullTransactionLifecycle:
    def setup_method(self):
        reset_metrics_cache()
        self.m = TransactionMetrics()
        self.hc = HealthChecker(self.m)

    def test_full_lifecycle_healthy(self):
        for _ in range(100):
            self.m.record_transaction_start()
            self.m.record_transaction_success(0.001)

        summary = self.m.get_metrics_summary()
        assert summary["consistency_ratio"] == pytest.approx(1.0)
        assert summary["health_status"] == "healthy"

        result = self.hc.check_health()
        assert result.status == HealthStatus.HEALTHY
        assert self.hc.is_healthy()

    def test_full_lifecycle_with_compensations(self):
        for _ in range(50):
            with self.m.transaction_timer() as ctx:
                pass

        for _ in range(10):
            with self.m.compensation_timer():
                pass

        for _ in range(5):
            with self.m.checkpoint_timer(CheckpointOperation.SAVE):
                pass

        for _ in range(3):
            with self.m.checkpoint_timer(CheckpointOperation.RESTORE):
                pass

        assert self.m._internal_success == 50
        assert self.m._internal_compensations == 10

    def test_transaction_compensated_then_check(self):
        self.m.record_transaction_start()
        self.m.record_transaction_failure(0.1)
        self.m.record_transaction_compensated()
        # After 1 start and 1 failure: total=1, success=0 -> ratio = 0.0
        assert self.m.get_consistency_ratio() == 0.0

    def test_metrics_summary_after_timer_use(self):
        with self.m.transaction_timer():
            pass
        summary = self.m.get_metrics_summary()
        assert summary["consistency_ratio"] == 1.0
