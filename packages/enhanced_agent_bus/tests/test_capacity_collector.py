"""Tests for observability/capacity_metrics/collector.py — EnhancedAgentBusCapacityMetrics."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus.observability.capacity_metrics.collector import (
    EnhancedAgentBusCapacityMetrics,
    get_capacity_metrics,
    reset_capacity_metrics,
)
from enhanced_agent_bus.observability.capacity_metrics.models import (
    CapacitySnapshot,
    CapacityStatus,
    LatencyPercentiles,
    QueueMetrics,
    ResourceUtilization,
    ThroughputMetrics,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset singleton before each test."""
    reset_capacity_metrics()
    yield
    reset_capacity_metrics()


@pytest.fixture()
def metrics() -> EnhancedAgentBusCapacityMetrics:
    return EnhancedAgentBusCapacityMetrics(service_name="test_service")


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------
class TestConstruction:
    def test_default_construction(self, metrics):
        assert metrics.service_name == "test_service"
        assert metrics.window_seconds == 60

    def test_custom_window(self):
        m = EnhancedAgentBusCapacityMetrics(window_seconds=120)
        assert m.window_seconds == 120


# ---------------------------------------------------------------------------
# Recording methods
# ---------------------------------------------------------------------------
class TestRecordingMethods:
    def test_record_request(self, metrics):
        metrics.record_request(latency_ms=1.5)
        tp = metrics.get_throughput_metrics()
        assert tp.total_requests >= 1

    def test_record_message_without_latency(self, metrics):
        metrics.record_message()
        # Should not raise

    def test_record_message_with_latency(self, metrics):
        metrics.record_message(latency_ms=2.0)
        p = metrics.get_latency_percentiles("processing")
        assert p.sample_count >= 1

    def test_record_validation(self, metrics):
        metrics.record_validation(latency_ms=0.5)
        p = metrics.get_latency_percentiles("validation")
        assert p.sample_count >= 1

    def test_record_enqueue_and_dequeue(self, metrics):
        metrics.record_enqueue(5)
        q = metrics.get_queue_metrics()
        assert q.current_depth == 5

        metrics.record_dequeue(3)
        q = metrics.get_queue_metrics()
        assert q.current_depth == 2

    def test_dequeue_does_not_go_negative(self, metrics):
        metrics.record_enqueue(2)
        metrics.record_dequeue(10)
        q = metrics.get_queue_metrics()
        assert q.current_depth == 0

    def test_set_queue_depth(self, metrics):
        metrics.set_queue_depth(42)
        q = metrics.get_queue_metrics()
        assert q.current_depth == 42

    def test_set_dlq_depth(self, metrics):
        metrics.set_dlq_depth(7)
        q = metrics.get_queue_metrics()
        assert q.dlq_depth == 7

    def test_max_queue_depth_tracked(self, metrics):
        metrics.record_enqueue(10)
        metrics.record_dequeue(5)
        metrics.record_enqueue(3)
        q = metrics.get_queue_metrics()
        assert q.max_depth == 10


# ---------------------------------------------------------------------------
# Retrieval methods
# ---------------------------------------------------------------------------
class TestRetrievalMethods:
    def test_get_throughput_metrics_defaults(self, metrics):
        tp = metrics.get_throughput_metrics()
        assert isinstance(tp, ThroughputMetrics)
        assert tp.total_requests == 0

    def test_get_latency_percentiles_request(self, metrics):
        for val in [1.0, 2.0, 3.0, 4.0, 5.0]:
            metrics.record_request(latency_ms=val)
        p = metrics.get_latency_percentiles("request")
        assert p.sample_count == 5
        assert p.min_ms == 1.0
        assert p.max_ms == 5.0

    def test_get_latency_percentiles_unknown_operation(self, metrics):
        p = metrics.get_latency_percentiles("unknown")
        assert p.sample_count == 0

    def test_get_queue_metrics_default(self, metrics):
        q = metrics.get_queue_metrics()
        assert isinstance(q, QueueMetrics)
        assert q.current_depth == 0

    def test_get_resource_utilization_without_psutil(self, metrics):
        metrics._psutil = None
        r = metrics.get_resource_utilization()
        assert isinstance(r, ResourceUtilization)
        assert r.cpu_percent == 0.0


# ---------------------------------------------------------------------------
# Capacity snapshot and status determination
# ---------------------------------------------------------------------------
class TestCapacitySnapshot:
    def test_snapshot_returns_snapshot(self, metrics):
        snap = metrics.get_capacity_snapshot()
        assert isinstance(snap, CapacitySnapshot)
        assert snap.status == CapacityStatus.HEALTHY

    def test_snapshot_critical_on_high_latency(self, metrics):
        # Record latencies above 5ms to trigger CRITICAL
        for _ in range(10):
            metrics.record_request(latency_ms=10.0)
        snap = metrics.get_capacity_snapshot()
        assert snap.status == CapacityStatus.CRITICAL

    def test_snapshot_warning_on_moderate_latency(self, metrics):
        for _ in range(10):
            metrics.record_request(latency_ms=4.0)
        snap = metrics.get_capacity_snapshot()
        assert snap.status == CapacityStatus.WARNING

    def test_snapshot_critical_on_high_queue_depth(self, metrics):
        metrics.set_queue_depth(600)
        snap = metrics.get_capacity_snapshot()
        assert snap.status == CapacityStatus.CRITICAL

    def test_snapshot_warning_on_moderate_queue_depth(self, metrics):
        metrics.set_queue_depth(150)
        snap = metrics.get_capacity_snapshot()
        assert snap.status == CapacityStatus.WARNING

    def test_snapshot_stored_in_history(self, metrics):
        metrics.get_capacity_snapshot()
        metrics.get_capacity_snapshot()
        assert len(metrics._snapshots) == 2


# ---------------------------------------------------------------------------
# Capacity trend
# ---------------------------------------------------------------------------
class TestCapacityTrend:
    def test_trend_no_data(self, metrics):
        trend = metrics.get_capacity_trend()
        assert trend["available"] is False

    def test_trend_with_data(self, metrics):
        # Generate a couple of snapshots
        metrics.record_request(latency_ms=1.0)
        metrics.get_capacity_snapshot()
        metrics.record_request(latency_ms=2.0)
        metrics.get_capacity_snapshot()

        trend = metrics.get_capacity_trend(duration_minutes=10)
        assert trend["available"] is True
        assert trend["samples"] >= 2
        assert "latency" in trend
        assert "throughput" in trend
        assert "queue" in trend


# ---------------------------------------------------------------------------
# Scaling recommendation
# ---------------------------------------------------------------------------
class TestScalingRecommendation:
    def test_scaling_recommendation_returns_dict(self, metrics):
        rec = metrics.get_scaling_recommendation()
        assert "direction" in rec
        assert "urgency" in rec
        assert "reasons" in rec


# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
class TestPrometheusMetrics:
    def test_prometheus_not_available_no_crash(self, metrics):
        metrics._prom_metrics = None
        snap = metrics.get_capacity_snapshot()
        assert snap is not None

    def test_update_prometheus_metrics_skipped_when_none(self, metrics):
        metrics._prom_metrics = None
        snap = metrics.get_capacity_snapshot()
        # Should not raise
        assert snap is not None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
class TestSingleton:
    def test_get_capacity_metrics_returns_instance(self):
        m = get_capacity_metrics()
        assert isinstance(m, EnhancedAgentBusCapacityMetrics)

    def test_get_capacity_metrics_is_singleton(self):
        m1 = get_capacity_metrics()
        m2 = get_capacity_metrics()
        assert m1 is m2

    def test_reset_capacity_metrics(self):
        m1 = get_capacity_metrics()
        reset_capacity_metrics()
        m2 = get_capacity_metrics()
        assert m1 is not m2
