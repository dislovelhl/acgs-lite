# Constitutional Hash: 608508a9bd224290
"""
Recording and query tests for transaction_coordinator_metrics.py.

Covers: TransactionMetricsInit, TransactionRecording, CompensationRecording,
CheckpointRecording, InternalTracking, MetricsQueries, all Timer classes.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from collections import deque
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Module under test
# ---------------------------------------------------------------------------
import enhanced_agent_bus.transaction_coordinator_metrics as tcm_module
from enhanced_agent_bus.transaction_coordinator_metrics import (
    CheckpointOperation,
    Gauge,
    HealthStatus,
    Histogram,
    Info,
    TransactionMetrics,
    _NoOpCounter,
    _NoOpGauge,
    _NoOpHistogram,
    reset_metrics_cache,
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
# TransactionMetrics -- initialization
# ===========================================================================


class TestTransactionMetricsInit:
    def test_initializes_without_error(self):
        reset_metrics_cache()
        m = TransactionMetrics()
        assert m._initialized is True

    def test_post_init_idempotent(self):
        """Calling __post_init__ again when _initialized=True is a no-op."""
        reset_metrics_cache()
        m = TransactionMetrics()
        # Manually call again -- should not raise
        m.__post_init__()
        assert m._initialized is True

    def test_default_internal_counters(self):
        reset_metrics_cache()
        m = TransactionMetrics()
        assert m._internal_total == 0
        assert m._internal_success == 0
        assert m._internal_failed == 0
        assert m._internal_compensations == 0
        assert m._internal_concurrent == 0

    def test_transaction_info_set_error_is_swallowed(self):
        """Simulate the info() call raising; must not propagate."""
        reset_metrics_cache()
        fake_info = MagicMock()
        fake_info.info.side_effect = RuntimeError("boom")

        with_noop = _NoOpCounter()

        def fake_get_or_create(cls, name, *a, **kw):
            if name == "acgs_transaction_coordinator_info":
                return fake_info
            if cls == Gauge or cls == _NoOpGauge:
                return _NoOpGauge()
            if cls == Histogram or cls == _NoOpHistogram:
                return _NoOpHistogram()
            return with_noop

        import enhanced_agent_bus.transaction_coordinator_metrics as mod

        original = mod._get_or_create_metric
        try:
            mod._get_or_create_metric = fake_get_or_create
            m = TransactionMetrics()
        finally:
            mod._get_or_create_metric = original
        assert m is not None


# ===========================================================================
# TransactionMetrics -- transaction recording
# ===========================================================================


class TestTransactionRecording:
    def setup_method(self):
        reset_metrics_cache()
        self.m = TransactionMetrics()

    def test_record_transaction_start(self):
        self.m.record_transaction_start()
        assert self.m._internal_total == 1
        assert self.m._internal_concurrent == 1

    def test_record_transaction_success(self):
        self.m.record_transaction_start()
        self.m.record_transaction_success(0.1)
        assert self.m._internal_success == 1
        assert self.m._internal_concurrent == 0

    def test_record_transaction_success_multiple(self):
        for _ in range(5):
            self.m.record_transaction_start()
            self.m.record_transaction_success(0.05)
        assert self.m._internal_success == 5
        assert self.m._internal_total == 5
        assert self.m._internal_concurrent == 0

    def test_record_transaction_failure(self):
        self.m.record_transaction_start()
        self.m.record_transaction_failure(0.2, reason="timeout")
        assert self.m._internal_failed == 1
        assert self.m._internal_concurrent == 0

    def test_record_transaction_failure_default_reason(self):
        self.m.record_transaction_start()
        self.m.record_transaction_failure(0.1)
        assert self.m._internal_failed == 1

    def test_record_transaction_timeout(self):
        self.m.record_transaction_start()
        self.m.record_transaction_timeout(5.0)
        assert self.m._internal_failed == 1
        assert self.m._internal_concurrent == 0

    def test_record_transaction_compensated(self):
        self.m.record_transaction_compensated()
        ratio = self.m.get_consistency_ratio()
        assert 0.0 <= ratio <= 1.0

    def test_concurrent_floor_at_zero(self):
        """Concurrent counter never goes negative."""
        self.m.record_transaction_success(0.1)
        assert self.m._internal_concurrent == 0

    def test_concurrent_with_multiple_start_success(self):
        self.m.record_transaction_start()
        self.m.record_transaction_start()
        assert self.m._internal_concurrent == 2
        self.m.record_transaction_success(0.01)
        assert self.m._internal_concurrent == 1


# ===========================================================================
# TransactionMetrics -- compensation recording
# ===========================================================================


class TestCompensationRecording:
    def setup_method(self):
        reset_metrics_cache()
        self.m = TransactionMetrics()

    def test_record_compensation_start_is_noop(self):
        self.m.record_compensation_start()

    def test_record_compensation_success(self):
        self.m.record_compensation_success(0.05)
        assert self.m._internal_compensations == 1
        assert len(self.m._compensation_samples) == 1

    def test_record_compensation_failure(self):
        self.m.record_compensation_failure(0.1)
        assert self.m._internal_compensations == 0

    def test_compensation_samples_stored_in_ms(self):
        self.m.record_compensation_success(1.0)
        assert self.m._compensation_samples[-1] == pytest.approx(1000.0)


# ===========================================================================
# TransactionMetrics -- checkpoint recording
# ===========================================================================


class TestCheckpointRecording:
    def setup_method(self):
        reset_metrics_cache()
        self.m = TransactionMetrics()

    def test_record_checkpoint_save_success(self):
        self.m.record_checkpoint_save(0.01, success=True)

    def test_record_checkpoint_save_failure(self):
        self.m.record_checkpoint_save(0.01, success=False)

    def test_record_checkpoint_restore_success(self):
        self.m.record_checkpoint_restore(0.02, success=True)

    def test_record_checkpoint_restore_failure(self):
        self.m.record_checkpoint_restore(0.02, success=False)

    def test_record_checkpoint_save_default_success(self):
        self.m.record_checkpoint_save(0.005)


# ===========================================================================
# TransactionMetrics -- internal tracking
# ===========================================================================


class TestInternalTracking:
    def setup_method(self):
        reset_metrics_cache()
        self.m = TransactionMetrics()

    def test_record_duration_appends(self):
        self.m._record_duration(0.5)
        assert len(self.m._duration_samples) == 1
        assert self.m._duration_samples[0] == pytest.approx(500.0)

    def test_record_duration_caps_at_max_samples(self):
        self.m._max_samples = 5
        self.m._duration_samples = deque(maxlen=5)
        for i in range(10):
            self.m._record_duration(float(i) * 0.1)
        assert len(self.m._duration_samples) == 5
        # Only the last 5 values are kept
        assert self.m._duration_samples[-1] == pytest.approx(900.0)

    def test_record_compensation_duration_appends(self):
        self.m._record_compensation_duration(0.2)
        assert len(self.m._compensation_samples) == 1
        assert self.m._compensation_samples[0] == pytest.approx(200.0)

    def test_record_compensation_duration_caps(self):
        self.m._max_samples = 3
        self.m._compensation_samples = deque(maxlen=3)
        for i in range(6):
            self.m._record_compensation_duration(float(i) * 0.1)
        assert len(self.m._compensation_samples) == 3

    def test_update_consistency_ratio_sets_gauge(self):
        """_update_consistency_ratio must call consistency_ratio.set()."""
        self.m.consistency_ratio = MagicMock()
        self.m.record_transaction_start()
        self.m.record_transaction_success(0.01)
        self.m.consistency_ratio.set.assert_called()


# ===========================================================================
# TransactionMetrics -- metrics queries
# ===========================================================================


class TestMetricsQueries:
    def setup_method(self):
        reset_metrics_cache()
        self.m = TransactionMetrics()

    def test_get_consistency_ratio_no_transactions(self):
        assert self.m.get_consistency_ratio() == 1.0

    def test_get_consistency_ratio_all_success(self):
        for _ in range(3):
            self.m.record_transaction_start()
            self.m.record_transaction_success(0.01)
        assert self.m.get_consistency_ratio() == pytest.approx(1.0)

    def test_get_consistency_ratio_mixed(self):
        for _ in range(3):
            self.m.record_transaction_start()
            self.m.record_transaction_success(0.01)
        for _ in range(1):
            self.m.record_transaction_start()
            self.m.record_transaction_failure(0.01)
        ratio = self.m.get_consistency_ratio()
        assert ratio == pytest.approx(3 / 4)

    def test_get_latency_percentiles_empty(self):
        result = self.m.get_latency_percentiles()
        assert result == {"p50": 0.0, "p95": 0.0, "p99": 0.0}

    def test_get_latency_percentiles_with_samples(self):
        for i in range(1, 101):
            self.m._record_duration(i * 0.001)
        result = self.m.get_latency_percentiles()
        assert "p50" in result
        assert "p95" in result
        assert "p99" in result
        assert result["p50"] <= result["p95"] <= result["p99"]

    def test_get_latency_percentiles_single_sample(self):
        self.m._record_duration(0.1)
        result = self.m.get_latency_percentiles()
        assert result["p50"] == pytest.approx(100.0)
        assert result["p99"] == pytest.approx(100.0)

    def test_get_compensation_percentiles_empty(self):
        result = self.m.get_compensation_percentiles()
        assert result == {"p50": 0.0, "p95": 0.0, "p99": 0.0}

    def test_get_compensation_percentiles_with_samples(self):
        for i in range(1, 50):
            self.m._record_compensation_duration(i * 0.002)
        result = self.m.get_compensation_percentiles()
        assert result["p50"] <= result["p95"] <= result["p99"]

    def test_get_latency_percentiles_uses_rust_kernel_when_available(self, monkeypatch):
        called = {"value": False}

        def _fake_kernel(values: list[float], percentiles: list[float]) -> list[float]:
            called["value"] = True
            assert percentiles == [50.0, 95.0, 99.0]
            assert values == sorted(values)
            return [200.0, 200.0, 200.0]

        monkeypatch.setattr(tcm_module, "PERF_KERNELS_AVAILABLE", True)
        monkeypatch.setattr(
            tcm_module,
            "compute_percentiles_floor_index",
            _fake_kernel,
            raising=False,
        )

        self.m._record_duration(0.1)
        self.m._record_duration(0.2)
        result = self.m.get_latency_percentiles()
        assert called["value"] is True
        assert result == {"p50": 200.0, "p95": 200.0, "p99": 200.0}

    def test_get_compensation_percentiles_python_fallback(self, monkeypatch):
        monkeypatch.setattr(tcm_module, "PERF_KERNELS_AVAILABLE", False)

        self.m._record_compensation_duration(0.1)
        self.m._record_compensation_duration(0.2)
        result = self.m.get_compensation_percentiles()
        assert result["p50"] == pytest.approx(200.0)
        assert result["p95"] == pytest.approx(200.0)
        assert result["p99"] == pytest.approx(200.0)

    def test_get_health_status_healthy(self):
        for _ in range(5):
            self.m.record_transaction_start()
            self.m.record_transaction_success(0.001)
        assert self.m.get_health_status_enum() == HealthStatus.HEALTHY

    def test_get_health_status_degraded(self):
        # 990 success, 10 failure -> 99.0% >= 99% but < 99.9% -> DEGRADED
        for _ in range(990):
            self.m.record_transaction_start()
            self.m.record_transaction_success(0.001)
        for _ in range(10):
            self.m.record_transaction_start()
            self.m.record_transaction_failure(0.001)
        status = self.m.get_health_status_enum()
        assert status == HealthStatus.DEGRADED

    def test_get_health_status_unhealthy(self):
        # 980 success, 20 failure -> 98% < 99% -> UNHEALTHY
        for _ in range(980):
            self.m.record_transaction_start()
            self.m.record_transaction_success(0.001)
        for _ in range(20):
            self.m.record_transaction_start()
            self.m.record_transaction_failure(0.001)
        status = self.m.get_health_status_enum()
        assert status == HealthStatus.UNHEALTHY

    def test_get_health_status_no_transactions(self):
        assert self.m.get_health_status_enum() == HealthStatus.HEALTHY

    def test_update_health_gauge_healthy(self):
        mock_gauge = MagicMock()
        self.m.health_status = mock_gauge
        for _ in range(5):
            self.m.record_transaction_start()
            self.m.record_transaction_success(0.001)
        self.m.update_health_gauge()
        mock_gauge.set.assert_called_with(2)

    def test_update_health_gauge_degraded(self):
        mock_gauge = MagicMock()
        self.m.health_status = mock_gauge
        for _ in range(990):
            self.m.record_transaction_start()
            self.m.record_transaction_success(0.001)
        for _ in range(10):
            self.m.record_transaction_start()
            self.m.record_transaction_failure(0.001)
        self.m.update_health_gauge()
        mock_gauge.set.assert_called_with(1)

    def test_update_health_gauge_unhealthy(self):
        mock_gauge = MagicMock()
        self.m.health_status = mock_gauge
        for _ in range(980):
            self.m.record_transaction_start()
            self.m.record_transaction_success(0.001)
        for _ in range(20):
            self.m.record_transaction_start()
            self.m.record_transaction_failure(0.001)
        self.m.update_health_gauge()
        mock_gauge.set.assert_called_with(0)

    def test_get_metrics_summary_structure(self):
        self.m.record_transaction_start()
        self.m.record_transaction_success(0.05)
        summary = self.m.get_metrics_summary()
        assert "consistency_ratio" in summary
        assert "health_status" in summary
        assert "latency_ms" in summary
        assert "compensation_latency_ms" in summary
        assert "concurrent_transactions" in summary
        assert "constitutional_hash" in summary

    def test_get_metrics_summary_values(self):
        summary = self.m.get_metrics_summary()
        assert summary["consistency_ratio"] == 1.0
        assert summary["concurrent_transactions"] == 0.0

    def test_get_counter_value_returns_float(self):
        val = self.m._get_counter_value(self.m.transactions_success)
        assert isinstance(val, float)

    def test_get_counter_value_with_labels(self):
        val = self.m._get_counter_value(self.m.transactions_total, status="success")
        assert isinstance(val, float)

    def test_get_counter_value_exception_returns_zero(self):
        bad_counter = MagicMock()
        bad_counter.labels.side_effect = RuntimeError("boom")
        val = self.m._get_counter_value(bad_counter, status="x")
        assert val == 0.0

    def test_get_gauge_value_concurrent_transactions(self):
        self.m.record_transaction_start()
        val = self.m._get_gauge_value(self.m.concurrent_transactions)
        assert val == 1.0

    def test_get_gauge_value_other_gauge(self):
        mock_gauge = MagicMock()
        mock_val = MagicMock()
        mock_val.get.return_value = 42.0
        mock_gauge._value = mock_val
        val = self.m._get_gauge_value(mock_gauge)
        assert val == pytest.approx(42.0)

    def test_get_gauge_value_non_numeric(self):
        mock_gauge = MagicMock()
        mock_val = MagicMock()
        mock_val.get.return_value = "not-a-number"
        mock_gauge._value = mock_val
        val = self.m._get_gauge_value(mock_gauge)
        assert val == 0.0

    def test_get_gauge_value_no_value_attr(self):
        mock_gauge = MagicMock(spec=[])
        val = self.m._get_gauge_value(mock_gauge)
        assert val == 0.0

    def test_get_gauge_value_attribute_error(self):
        bad_gauge = MagicMock()
        type(bad_gauge)._value = property(
            lambda self: (_ for _ in ()).throw(AttributeError("no attr"))
        )
        val = self.m._get_gauge_value(bad_gauge)
        assert val == 0.0

    def test_get_gauge_value_generic_exception(self):
        """Cover lines 872-873: except (AttributeError, Exception) -> return 0.0."""
        bad_gauge = MagicMock()
        mock_value = MagicMock()
        mock_value.get.side_effect = Exception("unexpected")
        bad_gauge._value = mock_value
        val = self.m._get_gauge_value(bad_gauge)
        assert val == 0.0

    def test_get_counter_value_callable_getter_int(self):
        mock_counter = MagicMock()
        mock_counter._value = MagicMock()
        mock_counter._value.get.return_value = 5
        val = self.m._get_counter_value(mock_counter)
        assert val == pytest.approx(5.0)

    def test_get_counter_value_callable_getter_string(self):
        mock_counter = MagicMock()
        mock_counter._value = MagicMock()
        mock_counter._value.get.return_value = "not-a-number"
        val = self.m._get_counter_value(mock_counter)
        assert val == 0.0

    def test_get_counter_value_no_get_attribute(self):
        mock_counter = MagicMock()
        mock_counter._value = "plain-string-not-callable"
        val = self.m._get_counter_value(mock_counter)
        assert val == 0.0

    def test_get_counter_value_with_labels_and_no_value(self):
        mock_counter = MagicMock()
        labeled = MagicMock()
        labeled._value = None
        mock_counter.labels.return_value = labeled
        val = self.m._get_counter_value(mock_counter, status="ok")
        assert val == 0.0


# ===========================================================================
# TransactionMetrics -- context managers
# ===========================================================================


class TestTransactionTimer:
    def setup_method(self):
        reset_metrics_cache()
        self.m = TransactionMetrics()

    def test_transaction_timer_success(self):
        with self.m.transaction_timer() as ctx:
            assert "start_time" in ctx
        assert ctx["recorded"] is True
        assert self.m._internal_success == 1

    def test_transaction_timer_explicit_success_true(self):
        with self.m.transaction_timer(expected_success=True) as ctx:
            pass
        assert self.m._internal_success == 1

    def test_transaction_timer_explicit_success_false(self):
        with self.m.transaction_timer(expected_success=False) as ctx:
            pass
        assert self.m._internal_failed == 1

    def test_transaction_timer_exception_records_failure(self):
        with pytest.raises(RuntimeError):
            with self.m.transaction_timer() as ctx:
                raise RuntimeError("test error")
        assert ctx["recorded"] is True
        assert self.m._internal_failed == 1

    def test_transaction_timer_manual_record(self):
        """If context['recorded'] is set True manually, timer doesn't double-record."""
        with self.m.transaction_timer() as ctx:
            ctx["recorded"] = True
        assert self.m._internal_success == 0
        assert self.m._internal_failed == 0

    def test_transaction_timer_exception_not_in_tuple_propagates(self):
        """An exception NOT in _TRANSACTION_METRICS_OPERATION_ERRORS still propagates."""

        class CustomError(Exception):
            pass

        with pytest.raises(CustomError):
            with self.m.transaction_timer():
                raise CustomError("unexpected")

    def test_transaction_timer_marks_success_false_on_runtime_error(self):
        with pytest.raises(ValueError):
            with self.m.transaction_timer(expected_success=True) as ctx:
                raise ValueError("bad value")
        assert ctx["success"] is False


class TestCompensationTimer:
    def setup_method(self):
        reset_metrics_cache()
        self.m = TransactionMetrics()

    def test_compensation_timer_success(self):
        with self.m.compensation_timer() as ctx:
            assert "start_time" in ctx
        assert ctx["recorded"] is True
        assert self.m._internal_compensations == 1

    def test_compensation_timer_failure(self):
        with pytest.raises(RuntimeError):
            with self.m.compensation_timer() as ctx:
                raise RuntimeError("comp failure")
        assert ctx["recorded"] is True
        assert self.m._internal_compensations == 0

    def test_compensation_timer_manual_record(self):
        with self.m.compensation_timer() as ctx:
            ctx["recorded"] = True
        assert self.m._internal_compensations == 0

    def test_compensation_timer_exception_sets_success_false(self):
        with pytest.raises(TypeError):
            with self.m.compensation_timer() as ctx:
                raise TypeError("type err")
        assert ctx["success"] is False


class TestCheckpointTimer:
    def setup_method(self):
        reset_metrics_cache()
        self.m = TransactionMetrics()

    def test_checkpoint_timer_save_success(self):
        with self.m.checkpoint_timer(CheckpointOperation.SAVE) as ctx:
            assert ctx["operation"] == CheckpointOperation.SAVE
        assert ctx["recorded"] is True

    def test_checkpoint_timer_restore_success(self):
        with self.m.checkpoint_timer(CheckpointOperation.RESTORE) as ctx:
            pass
        assert ctx["recorded"] is True

    def test_checkpoint_timer_save_failure(self):
        with pytest.raises(OSError):
            with self.m.checkpoint_timer(CheckpointOperation.SAVE) as ctx:
                raise OSError("disk full")
        assert ctx["success"] is False
        assert ctx["recorded"] is True

    def test_checkpoint_timer_restore_failure(self):
        with pytest.raises(ConnectionError):
            with self.m.checkpoint_timer(CheckpointOperation.RESTORE):
                raise ConnectionError("conn lost")

    def test_checkpoint_timer_manual_record(self):
        with self.m.checkpoint_timer(CheckpointOperation.SAVE) as ctx:
            ctx["recorded"] = True
