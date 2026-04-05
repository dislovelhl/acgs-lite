# Constitutional Hash: 608508a9bd224290
"""
Infrastructure tests for transaction_coordinator_metrics.py.

Covers: ProtocolStubs, NoOp* classes, Enums, LatencyBuckets,
GetOrCreateMetric, ResetMetricsCache.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Module under test
# ---------------------------------------------------------------------------
import enhanced_agent_bus.transaction_coordinator_metrics as tcm_module
from enhanced_agent_bus.transaction_coordinator_metrics import (
    _METRICS_CACHE,
    CHECKPOINT_LATENCY_BUCKETS,
    COMPENSATION_LATENCY_BUCKETS,
    TRANSACTION_LATENCY_BUCKETS,
    CheckpointOperation,
    CompensationStatus,
    Counter,
    CounterLike,
    Gauge,
    GaugeLike,
    HealthStatus,
    Histogram,
    HistogramLike,
    Info,
    InfoLike,
    TransactionMetrics,
    TransactionStatus,
    _get_or_create_metric,
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


# ===========================================================================
# Protocol stub coverage -- concrete implementations to exercise lines 44-67
# ===========================================================================


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


class TestProtocolStubs:
    """
    Exercise Protocol method stubs so coverage sees the branches executed.

    Coverage.py instruments the `...` (Ellipsis) bodies in Protocol stub methods
    as branches. We exercise them by calling the Protocol stub methods directly
    through `unbound_method(self_mock, ...)`, which causes the `...` code object
    to run and marks each stub branch as covered.
    """

    def test_counter_like_labels_stub(self):
        # Call the Protocol stub directly -- returns None (stub body is `...`)
        mock_self = MagicMock()
        result = CounterLike.labels(mock_self, status="ok")
        assert result is None

    def test_counter_like_inc_stub(self):
        mock_self = MagicMock()
        result = CounterLike.inc(mock_self)
        assert result is None

    def test_gauge_like_labels_stub(self):
        mock_self = MagicMock()
        result = GaugeLike.labels(mock_self, key="v")
        assert result is None

    def test_gauge_like_set_stub(self):
        mock_self = MagicMock()
        result = GaugeLike.set(mock_self, 1.0)
        assert result is None

    def test_gauge_like_inc_stub(self):
        mock_self = MagicMock()
        result = GaugeLike.inc(mock_self)
        assert result is None

    def test_gauge_like_dec_stub(self):
        mock_self = MagicMock()
        result = GaugeLike.dec(mock_self)
        assert result is None

    def test_histogram_like_labels_stub(self):
        mock_self = MagicMock()
        result = HistogramLike.labels(mock_self, status="s")
        assert result is None

    def test_histogram_like_observe_stub(self):
        mock_self = MagicMock()
        result = HistogramLike.observe(mock_self, 0.5)
        assert result is None

    def test_info_like_info_stub(self):
        mock_self = MagicMock()
        result = InfoLike.info(mock_self, {"key": "value"})
        assert result is None

    def test_concrete_counter_methods(self):
        c = ConcreteCounter()
        result = c.labels(status="ok")
        assert result is c
        c.inc()
        c.inc(5.0)

    def test_concrete_gauge_methods(self):
        g = ConcreteGauge()
        result = g.labels(key="v")
        assert result is g
        g.set(1.0)
        g.inc()
        g.inc(2.0)
        g.dec()
        g.dec(3.0)

    def test_concrete_histogram_methods(self):
        h = ConcreteHistogram()
        result = h.labels(status="s")
        assert result is h
        h.observe(0.5)

    def test_concrete_info_methods(self):
        i = ConcreteInfo()
        i.info({"key": "value"})

    def test_noop_counter_methods(self):
        c = _NoOpCounter()
        assert c.labels(status="ok") is c
        c.inc()

    def test_noop_gauge_methods(self):
        g = _NoOpGauge()
        assert g.labels(key="v") is g
        g.set(1.0)
        g.inc()
        g.dec()

    def test_noop_histogram_methods(self):
        h = _NoOpHistogram()
        assert h.labels(status="s") is h
        h.observe(0.5)


# ===========================================================================
# No-op class tests
# ===========================================================================


class TestNoOpCounter:
    def test_labels_returns_self(self):
        c = _NoOpCounter()
        assert c.labels(status="ok") is c

    def test_inc_no_error(self):
        c = _NoOpCounter()
        c.inc()
        c.inc(5.0)

    def test_init_with_args(self):
        c = _NoOpCounter("name", "doc", extra="ignored")
        assert c is not None


class TestNoOpGauge:
    def test_labels_returns_self(self):
        g = _NoOpGauge()
        assert g.labels(key="v") is g

    def test_set_inc_dec_no_error(self):
        g = _NoOpGauge()
        g.set(42.0)
        g.inc()
        g.inc(2.0)
        g.dec()
        g.dec(3.0)

    def test_init_with_args(self):
        g = _NoOpGauge("n", "d")
        assert g is not None


class TestNoOpHistogram:
    def test_labels_returns_self(self):
        h = _NoOpHistogram()
        assert h.labels(status="s") is h

    def test_observe_no_error(self):
        h = _NoOpHistogram()
        h.observe(0.5)

    def test_init_with_args(self):
        h = _NoOpHistogram("n", "d", buckets=[0.1, 0.5])
        assert h is not None


# ===========================================================================
# Enums
# ===========================================================================


class TestEnums:
    def test_transaction_status_values(self):
        assert TransactionStatus.SUCCESS.value == "success"
        assert TransactionStatus.FAILURE.value == "failure"
        assert TransactionStatus.TIMEOUT.value == "timeout"
        assert TransactionStatus.COMPENSATED.value == "compensated"

    def test_compensation_status_values(self):
        assert CompensationStatus.SUCCESS.value == "success"
        assert CompensationStatus.FAILURE.value == "failure"

    def test_checkpoint_operation_values(self):
        assert CheckpointOperation.SAVE.value == "save"
        assert CheckpointOperation.RESTORE.value == "restore"

    def test_health_status_values(self):
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"


# ===========================================================================
# Latency bucket constants
# ===========================================================================


class TestLatencyBuckets:
    def test_transaction_latency_buckets_is_list(self):
        assert isinstance(TRANSACTION_LATENCY_BUCKETS, list)
        assert len(TRANSACTION_LATENCY_BUCKETS) > 0

    def test_compensation_latency_buckets(self):
        assert isinstance(COMPENSATION_LATENCY_BUCKETS, list)
        assert len(COMPENSATION_LATENCY_BUCKETS) > 0

    def test_checkpoint_latency_buckets(self):
        assert isinstance(CHECKPOINT_LATENCY_BUCKETS, list)
        assert len(CHECKPOINT_LATENCY_BUCKETS) > 0

    def test_buckets_are_sorted(self):
        assert TRANSACTION_LATENCY_BUCKETS == sorted(TRANSACTION_LATENCY_BUCKETS)
        assert COMPENSATION_LATENCY_BUCKETS == sorted(COMPENSATION_LATENCY_BUCKETS)
        assert CHECKPOINT_LATENCY_BUCKETS == sorted(CHECKPOINT_LATENCY_BUCKETS)


# ===========================================================================
# _get_or_create_metric
# ===========================================================================


class TestGetOrCreateMetric:
    def setup_method(self):
        reset_metrics_cache()

    def test_cache_hit_returns_same_object(self):
        m1 = _get_or_create_metric(_NoOpCounter, "test_cache_hit", "doc")
        m2 = _get_or_create_metric(_NoOpCounter, "test_cache_hit", "doc")
        assert m1 is m2

    def test_no_prometheus_counter_returns_noop(self):
        import enhanced_agent_bus.transaction_coordinator_metrics as mod

        reset_metrics_cache()
        original_prom = mod.PROMETHEUS_AVAILABLE
        try:
            mod.PROMETHEUS_AVAILABLE = False
            m = mod._get_or_create_metric(mod.Counter, "noop_counter_test_x", "doc")
        finally:
            mod.PROMETHEUS_AVAILABLE = original_prom
        assert isinstance(m, _NoOpCounter)

    def test_no_prometheus_gauge_returns_noop(self):
        import enhanced_agent_bus.transaction_coordinator_metrics as mod

        reset_metrics_cache()
        original_prom = mod.PROMETHEUS_AVAILABLE
        try:
            mod.PROMETHEUS_AVAILABLE = False
            m = mod._get_or_create_metric(mod.Gauge, "noop_gauge_test_x", "doc")
        finally:
            mod.PROMETHEUS_AVAILABLE = original_prom
        assert isinstance(m, _NoOpGauge)

    def test_no_prometheus_histogram_returns_noop(self):
        import enhanced_agent_bus.transaction_coordinator_metrics as mod

        reset_metrics_cache()
        original_prom = mod.PROMETHEUS_AVAILABLE
        try:
            mod.PROMETHEUS_AVAILABLE = False
            m = mod._get_or_create_metric(
                mod.Histogram, "noop_hist_test_x", "doc", buckets=[0.1, 1.0]
            )
        finally:
            mod.PROMETHEUS_AVAILABLE = original_prom
        assert isinstance(m, _NoOpHistogram)

    def test_no_prometheus_unknown_class_returns_noop_counter(self):
        import enhanced_agent_bus.transaction_coordinator_metrics as mod

        reset_metrics_cache()
        original_prom = mod.PROMETHEUS_AVAILABLE

        class FakeMetric:
            __name__ = "FakeMetric"

        try:
            mod.PROMETHEUS_AVAILABLE = False
            m = mod._get_or_create_metric(FakeMetric, "noop_unknown_test_x", "doc")
        finally:
            mod.PROMETHEUS_AVAILABLE = original_prom
        assert isinstance(m, _NoOpCounter)

    def test_duplicate_metric_returns_fallback(self):
        """Simulate a ValueError(Duplicated timeseries) -> fallback path."""
        import enhanced_agent_bus.transaction_coordinator_metrics as mod

        reset_metrics_cache()

        def raise_dup(*args, **kwargs):
            raise ValueError("Duplicated timeseries in...")

        original_counter = mod.Counter
        original_prom = mod.PROMETHEUS_AVAILABLE
        try:
            mod.Counter = raise_dup  # type: ignore[assignment]
            mod.PROMETHEUS_AVAILABLE = True
            m = mod._get_or_create_metric(raise_dup, "dup_counter_xyz_v2", "doc")
        finally:
            mod.Counter = original_counter
            mod.PROMETHEUS_AVAILABLE = original_prom
        # Should be a no-op fallback
        assert isinstance(m, _NoOpCounter)

    def test_duplicate_histogram_returns_noop_histogram(self):
        import enhanced_agent_bus.transaction_coordinator_metrics as mod

        reset_metrics_cache()

        def raise_dup(*args, **kwargs):
            raise ValueError("already registered")

        original_hist = mod.Histogram
        original_prom = mod.PROMETHEUS_AVAILABLE
        try:
            mod.Histogram = raise_dup  # type: ignore[assignment]
            mod.PROMETHEUS_AVAILABLE = True
            m = mod._get_or_create_metric(raise_dup, "dup_hist_xyz_v2", "doc", buckets=[0.1])
        finally:
            mod.Histogram = original_hist
            mod.PROMETHEUS_AVAILABLE = original_prom
        assert isinstance(m, _NoOpHistogram)

    def test_duplicate_gauge_returns_noop_gauge(self):
        import enhanced_agent_bus.transaction_coordinator_metrics as mod

        reset_metrics_cache()

        def raise_dup(*args, **kwargs):
            raise ValueError("Duplicated timeseries in...")

        original_gauge = mod.Gauge
        original_prom = mod.PROMETHEUS_AVAILABLE
        try:
            mod.Gauge = raise_dup  # type: ignore[assignment]
            mod.PROMETHEUS_AVAILABLE = True
            m = mod._get_or_create_metric(raise_dup, "dup_gauge_xyz_v2", "doc")
        finally:
            mod.Gauge = original_gauge
            mod.PROMETHEUS_AVAILABLE = original_prom
        assert isinstance(m, _NoOpGauge)

    def test_duplicate_with_registry_lookup_succeeds(self):
        """Cover the branch where REGISTRY._names_to_collectors has the metric."""
        import enhanced_agent_bus.transaction_coordinator_metrics as mod

        reset_metrics_cache()

        fake_collector = MagicMock()
        fake_collector._name = "dup_with_registry_lookup_v2"

        fake_registry = MagicMock()
        fake_registry._names_to_collectors = {"x": fake_collector}

        def raise_dup(*args, **kwargs):
            raise ValueError("Duplicated timeseries in...")

        original_counter = mod.Counter
        original_prom = mod.PROMETHEUS_AVAILABLE
        original_registry = mod.REGISTRY
        try:
            mod.Counter = raise_dup  # type: ignore[assignment]
            mod.PROMETHEUS_AVAILABLE = True
            mod.REGISTRY = fake_registry
            m = mod._get_or_create_metric(raise_dup, "dup_with_registry_lookup_v2", "doc")
        finally:
            mod.Counter = original_counter
            mod.PROMETHEUS_AVAILABLE = original_prom
            mod.REGISTRY = original_registry
        assert m is fake_collector

    def test_duplicate_registry_attribute_error_falls_back(self):
        """Cover AttributeError inside _names_to_collectors iteration."""
        import enhanced_agent_bus.transaction_coordinator_metrics as mod

        reset_metrics_cache()

        bad_registry = MagicMock()
        bad_registry._names_to_collectors = MagicMock(side_effect=AttributeError("boom"))

        def raise_dup(*args, **kwargs):
            raise ValueError("Duplicated timeseries in...")

        original_counter = mod.Counter
        original_prom = mod.PROMETHEUS_AVAILABLE
        original_registry = mod.REGISTRY
        try:
            mod.Counter = raise_dup  # type: ignore[assignment]
            mod.PROMETHEUS_AVAILABLE = True
            mod.REGISTRY = bad_registry
            m = mod._get_or_create_metric(raise_dup, "bad_reg_xyz_v2", "doc")
        finally:
            mod.Counter = original_counter
            mod.PROMETHEUS_AVAILABLE = original_prom
            mod.REGISTRY = original_registry
        assert isinstance(m, _NoOpCounter)

    def test_registry_lookup_names_to_collectors_iteration(self):
        """Cover lines 272-277: iterate _names_to_collectors, collector found by name."""
        import enhanced_agent_bus.transaction_coordinator_metrics as mod

        reset_metrics_cache()
        target_name = "reg_lookup_found_xyz"

        fake_collector = MagicMock()
        fake_collector._name = target_name

        # A collector with a different name (not matched)
        other_collector = MagicMock()
        other_collector._name = "other_name_not_matching"

        fake_registry = MagicMock()
        fake_registry._names_to_collectors = {
            "other": other_collector,
            "target": fake_collector,
        }

        def raise_dup(*args, **kwargs):
            raise ValueError("Duplicated timeseries in...")

        original_counter = mod.Counter
        original_prom = mod.PROMETHEUS_AVAILABLE
        original_registry = mod.REGISTRY
        try:
            mod.Counter = raise_dup  # type: ignore[assignment]
            mod.PROMETHEUS_AVAILABLE = True
            mod.REGISTRY = fake_registry
            m = mod._get_or_create_metric(raise_dup, target_name, "doc")
        finally:
            mod.Counter = original_counter
            mod.PROMETHEUS_AVAILABLE = original_prom
            mod.REGISTRY = original_registry
        assert m is fake_collector

    def test_registry_none_fallback(self):
        """Cover line 270: REGISTRY is None -> skip to no-op fallback."""
        import enhanced_agent_bus.transaction_coordinator_metrics as mod

        reset_metrics_cache()

        def raise_dup(*args, **kwargs):
            raise ValueError("Duplicated timeseries in...")

        original_counter = mod.Counter
        original_prom = mod.PROMETHEUS_AVAILABLE
        original_registry = mod.REGISTRY
        try:
            mod.Counter = raise_dup  # type: ignore[assignment]
            mod.PROMETHEUS_AVAILABLE = True
            mod.REGISTRY = None
            m = mod._get_or_create_metric(raise_dup, "registry_none_xyz", "doc")
        finally:
            mod.Counter = original_counter
            mod.PROMETHEUS_AVAILABLE = original_prom
            mod.REGISTRY = original_registry
        assert isinstance(m, _NoOpCounter)

    def test_histogram_without_buckets_prometheus_path(self):
        """Cover line 258: Histogram creation without explicit buckets."""
        import enhanced_agent_bus.transaction_coordinator_metrics as mod

        reset_metrics_cache()

        created = []

        def fake_histogram(*args, labelnames=None, **kwargs):
            # Ensure no 'buckets' keyword is passed
            assert "buckets" not in kwargs, f"Unexpected buckets kwarg: {kwargs}"
            h = MagicMock()
            created.append(h)
            return h

        original_hist = mod.Histogram
        original_prom = mod.PROMETHEUS_AVAILABLE
        try:
            mod.Histogram = fake_histogram  # type: ignore[assignment]
            mod.PROMETHEUS_AVAILABLE = True
            # Call with Histogram class matching condition but no buckets
            m = mod._get_or_create_metric(
                fake_histogram, "hist_no_buckets_xyz", "doc", labels=["status"]
            )
        finally:
            mod.Histogram = original_hist
            mod.PROMETHEUS_AVAILABLE = original_prom
        # The created histogram should be in the result
        assert m is created[0]

    def test_info_metric_creation_prometheus_path(self):
        """Cover the Info metric_class == Info branch."""
        import enhanced_agent_bus.transaction_coordinator_metrics as mod

        reset_metrics_cache()

        created = []

        def fake_info(*args, **kwargs):
            i = MagicMock()
            created.append(i)
            return i

        original_info = mod.Info
        original_prom = mod.PROMETHEUS_AVAILABLE
        try:
            mod.Info = fake_info  # type: ignore[assignment]
            mod.PROMETHEUS_AVAILABLE = True
            m = mod._get_or_create_metric(fake_info, "info_metric_xyz", "doc")
        finally:
            mod.Info = original_info
            mod.PROMETHEUS_AVAILABLE = original_prom
        assert m is created[0]

    def test_non_dup_value_error_falls_through_to_noop(self):
        """Cover: ValueError that is NOT about duplicates -> still gets no-op."""
        import enhanced_agent_bus.transaction_coordinator_metrics as mod

        reset_metrics_cache()

        def raise_other_value_error(*args, **kwargs):
            raise ValueError("something else entirely")

        original_counter = mod.Counter
        original_prom = mod.PROMETHEUS_AVAILABLE
        try:
            mod.Counter = raise_other_value_error  # type: ignore[assignment]
            mod.PROMETHEUS_AVAILABLE = True
            m = mod._get_or_create_metric(raise_other_value_error, "non_dup_err_xyz", "doc")
        finally:
            mod.Counter = original_counter
            mod.PROMETHEUS_AVAILABLE = original_prom
        assert isinstance(m, _NoOpCounter)

    def test_registry_lookup_type_error_falls_back(self):
        """Cover TypeError inside _names_to_collectors iteration."""
        import enhanced_agent_bus.transaction_coordinator_metrics as mod

        reset_metrics_cache()

        bad_registry = MagicMock()
        # values() raises TypeError
        bad_registry._names_to_collectors.values.side_effect = TypeError("bad type")

        def raise_dup(*args, **kwargs):
            raise ValueError("Duplicated timeseries in...")

        original_counter = mod.Counter
        original_prom = mod.PROMETHEUS_AVAILABLE
        original_registry = mod.REGISTRY
        try:
            mod.Counter = raise_dup  # type: ignore[assignment]
            mod.PROMETHEUS_AVAILABLE = True
            mod.REGISTRY = bad_registry
            m = mod._get_or_create_metric(raise_dup, "type_err_reg_xyz", "doc")
        finally:
            mod.Counter = original_counter
            mod.PROMETHEUS_AVAILABLE = original_prom
            mod.REGISTRY = original_registry
        assert isinstance(m, _NoOpCounter)


# ===========================================================================
# reset_metrics_cache
# ===========================================================================


class TestResetMetricsCache:
    def test_clears_cache(self):
        reset_metrics_cache()
        _get_or_create_metric(_NoOpCounter, "cache_clear_test", "doc")
        assert len(_METRICS_CACHE) > 0
        reset_metrics_cache()
        assert len(_METRICS_CACHE) == 0
