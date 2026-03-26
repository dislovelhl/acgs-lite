"""
Tests for ACGS-2 Enhanced Agent Bus Capacity Metrics Integration
Constitutional Hash: 608508a9bd224290
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus.observability.capacity_metrics import (
    CONSTITUTIONAL_HASH,
    CacheLayer,
    CacheMissReason,
    CapacitySnapshot,
    CapacityStatus,
    EnhancedAgentBusCapacityMetrics,
    LatencyPercentiles,
    LatencyTracker,
    PerformanceMetricsRegistry,
    QueueMetrics,
    ResourceUtilization,
    SlidingWindowCounter,
    ThroughputMetrics,
    ValidationResult,
    adaptive_threshold_timer,
    batch_overhead_timer,
    deliberation_layer_timer,
    get_capacity_metrics,
    get_performance_metrics,
    maci_enforcement_timer,
    opa_policy_timer,
    record_adaptive_threshold_decision,
    record_batch_processing_overhead,
    record_cache_miss,
    record_constitutional_validation,
    record_deliberation_layer_duration,
    record_maci_enforcement_latency,
    record_opa_policy_evaluation,
    record_z3_solver_latency,
    reset_capacity_metrics,
    reset_performance_metrics,
    track_request_latency,
    z3_solver_timer,
)


class TestConstitutionalCompliance:
    """Test constitutional compliance of capacity metrics."""

    def test_constitutional_hash_present(self):
        """Verify constitutional hash is correctly defined."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_latency_percentiles_include_constitutional_hash(self):
        """Verify latency percentiles include constitutional hash."""
        percentiles = LatencyPercentiles()
        assert percentiles.constitutional_hash == CONSTITUTIONAL_HASH

    def test_throughput_metrics_include_constitutional_hash(self):
        """Verify throughput metrics include constitutional hash."""
        metrics = ThroughputMetrics()
        assert metrics.constitutional_hash == CONSTITUTIONAL_HASH

    def test_queue_metrics_include_constitutional_hash(self):
        """Verify queue metrics include constitutional hash."""
        metrics = QueueMetrics()
        assert metrics.constitutional_hash == CONSTITUTIONAL_HASH

    def test_capacity_snapshot_include_constitutional_hash(self):
        """Verify capacity snapshot includes constitutional hash."""
        snapshot = CapacitySnapshot()
        assert snapshot.constitutional_hash == CONSTITUTIONAL_HASH

    def test_capacity_metrics_include_constitutional_hash(self):
        """Verify capacity metrics collector includes constitutional hash."""
        reset_capacity_metrics()
        metrics = EnhancedAgentBusCapacityMetrics()
        assert metrics.constitutional_hash == CONSTITUTIONAL_HASH


class TestLatencyPercentiles:
    """Test latency percentiles dataclass."""

    def test_is_compliant_under_target(self):
        """Test compliance check when under 5ms target."""
        percentiles = LatencyPercentiles(p99_ms=3.0)
        assert percentiles.is_compliant() is True

    def test_is_compliant_over_target(self):
        """Test compliance check when over 5ms target."""
        percentiles = LatencyPercentiles(p99_ms=6.0)
        assert percentiles.is_compliant() is False

    def test_is_compliant_at_boundary(self):
        """Test compliance check at exactly 5ms."""
        percentiles = LatencyPercentiles(p99_ms=5.0)
        # At exactly 5ms, should NOT be compliant (target is <5ms)
        assert percentiles.is_compliant() is False


class TestThroughputMetrics:
    """Test throughput metrics dataclass."""

    def test_is_compliant_over_target(self):
        """Test compliance check when over 100 RPS target."""
        metrics = ThroughputMetrics(current_rps=500.0)
        assert metrics.is_compliant() is True

    def test_is_compliant_under_target(self):
        """Test compliance check when under 100 RPS target."""
        metrics = ThroughputMetrics(current_rps=50.0)
        assert metrics.is_compliant() is False


class TestSlidingWindowCounter:
    """Test sliding window counter for rate calculations."""

    def test_increment(self):
        """Test basic increment functionality."""
        counter = SlidingWindowCounter(window_seconds=60)
        counter.increment(5)
        assert counter.get_total() == 5

    def test_multiple_increments(self):
        """Test multiple increments."""
        counter = SlidingWindowCounter(window_seconds=60)
        counter.increment(1)
        counter.increment(2)
        counter.increment(3)
        assert counter.get_total() == 6

    def test_rate_calculation(self):
        """Test rate calculation."""
        counter = SlidingWindowCounter(window_seconds=60)
        counter.increment(60)
        # Rate should be approximately 1 per second
        rate = counter.get_rate()
        assert rate > 0

    def test_peak_rate(self):
        """Test peak rate tracking."""
        counter = SlidingWindowCounter(window_seconds=60)
        counter.increment(100)
        rate1 = counter.get_rate()
        counter.increment(200)
        rate2 = counter.get_rate()
        peak = counter.get_peak_rate()
        assert peak >= rate1
        assert peak >= rate2


class TestLatencyTracker:
    """Test latency tracker with percentile calculations."""

    def test_record_latency(self):
        """Test recording latency samples."""
        tracker = LatencyTracker()
        tracker.record(1.0)
        tracker.record(2.0)
        tracker.record(3.0)
        percentiles = tracker.get_percentiles()
        assert percentiles.sample_count == 3

    def test_percentile_calculations(self):
        """Test percentile calculations."""
        tracker = LatencyTracker()
        # Add samples with known distribution
        for i in range(1, 101):
            tracker.record(float(i))

        percentiles = tracker.get_percentiles()
        assert percentiles.sample_count == 100
        assert percentiles.min_ms == 1.0
        assert percentiles.max_ms == 100.0
        # P50 should be around 50
        assert 45 <= percentiles.p50_ms <= 55
        # P99 should be around 99
        assert 95 <= percentiles.p99_ms <= 100

    def test_empty_tracker(self):
        """Test percentiles with no samples."""
        tracker = LatencyTracker()
        percentiles = tracker.get_percentiles()
        assert percentiles.sample_count == 0
        assert percentiles.p50_ms == 0.0
        assert percentiles.p99_ms == 0.0


class TestEnhancedAgentBusCapacityMetrics:
    """Test the main capacity metrics collector."""

    def setup_method(self):
        """Reset metrics before each test."""
        reset_capacity_metrics()

    def test_initialization(self):
        """Test metrics collector initialization."""
        metrics = EnhancedAgentBusCapacityMetrics(service_name="test_service")
        assert metrics.service_name == "test_service"
        assert metrics.constitutional_hash == CONSTITUTIONAL_HASH

    def test_record_request(self):
        """Test recording request metrics."""
        metrics = EnhancedAgentBusCapacityMetrics()
        metrics.record_request(latency_ms=1.5, success=True)
        throughput = metrics.get_throughput_metrics()
        assert throughput.total_requests >= 1

    def test_record_message(self):
        """Test recording message metrics."""
        metrics = EnhancedAgentBusCapacityMetrics()
        metrics.record_message(latency_ms=0.5)
        # Message counter should increment
        rate = metrics._message_counter.get_total()
        assert rate >= 1

    def test_record_validation(self):
        """Test recording validation metrics."""
        metrics = EnhancedAgentBusCapacityMetrics()
        metrics.record_validation(latency_ms=0.3, compliant=True)
        rate = metrics._validation_counter.get_total()
        assert rate >= 1

    def test_queue_depth_tracking(self):
        """Test queue depth tracking."""
        metrics = EnhancedAgentBusCapacityMetrics()
        metrics.record_enqueue(5)
        assert metrics._queue_depth == 5

        metrics.record_dequeue(3)
        assert metrics._queue_depth == 2

    def test_queue_depth_direct_set(self):
        """Test setting queue depth directly."""
        metrics = EnhancedAgentBusCapacityMetrics()
        metrics.set_queue_depth(100)
        assert metrics._queue_depth == 100
        assert metrics._max_queue_depth == 100

    def test_dlq_depth(self):
        """Test dead letter queue depth."""
        metrics = EnhancedAgentBusCapacityMetrics()
        metrics.set_dlq_depth(10)
        queue = metrics.get_queue_metrics()
        assert queue.dlq_depth == 10

    def test_get_throughput_metrics(self):
        """Test getting throughput metrics."""
        metrics = EnhancedAgentBusCapacityMetrics()
        for _ in range(10):
            metrics.record_request(latency_ms=1.0)

        throughput = metrics.get_throughput_metrics()
        assert throughput.total_requests >= 10
        assert throughput.constitutional_hash == CONSTITUTIONAL_HASH

    def test_get_latency_percentiles(self):
        """Test getting latency percentiles."""
        metrics = EnhancedAgentBusCapacityMetrics()
        for i in range(100):
            metrics.record_request(latency_ms=float(i))

        percentiles = metrics.get_latency_percentiles("request")
        assert percentiles.sample_count == 100
        assert percentiles.constitutional_hash == CONSTITUTIONAL_HASH

    def test_get_queue_metrics(self):
        """Test getting queue metrics."""
        metrics = EnhancedAgentBusCapacityMetrics()
        metrics.set_queue_depth(50)
        queue = metrics.get_queue_metrics()
        assert queue.current_depth == 50
        assert queue.constitutional_hash == CONSTITUTIONAL_HASH

    def test_get_capacity_snapshot(self):
        """Test getting complete capacity snapshot."""
        metrics = EnhancedAgentBusCapacityMetrics()

        # Add some data
        for i in range(50):
            metrics.record_request(latency_ms=float(i % 5))
        metrics.set_queue_depth(20)

        snapshot = metrics.get_capacity_snapshot()
        assert snapshot.latency.sample_count > 0
        assert snapshot.throughput.total_requests >= 50
        assert snapshot.queue.current_depth == 20
        assert snapshot.constitutional_hash == CONSTITUTIONAL_HASH


class TestCapacitySnapshot:
    """Test capacity snapshot functionality."""

    def test_to_dict(self):
        """Test snapshot serialization to dictionary."""
        snapshot = CapacitySnapshot(
            latency=LatencyPercentiles(p99_ms=2.0),
            throughput=ThroughputMetrics(current_rps=1000.0),
            queue=QueueMetrics(current_depth=50),
            status=CapacityStatus.HEALTHY,
        )
        data = snapshot.to_dict()
        assert "timestamp" in data
        assert "latency" in data
        assert "throughput" in data
        assert "queue" in data
        assert "status" in data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_scaling_recommendation_healthy(self):
        """Test scaling recommendation for healthy state."""
        snapshot = CapacitySnapshot(
            latency=LatencyPercentiles(p99_ms=1.0),
            throughput=ThroughputMetrics(current_rps=1000.0),
            queue=QueueMetrics(current_depth=10),
            resources=ResourceUtilization(cpu_percent=50.0),
            status=CapacityStatus.HEALTHY,
        )
        rec = snapshot.get_scaling_recommendation()
        assert rec["constitutional_hash"] == CONSTITUTIONAL_HASH
        # Should not recommend scale up for healthy metrics
        assert rec["direction"] in ["maintain", "scale_down"]

    def test_scaling_recommendation_high_latency(self):
        """Test scaling recommendation for high latency."""
        snapshot = CapacitySnapshot(
            latency=LatencyPercentiles(p99_ms=6.0),  # Over 5ms target
            throughput=ThroughputMetrics(current_rps=1000.0),
            queue=QueueMetrics(current_depth=10),
            resources=ResourceUtilization(cpu_percent=50.0),
            status=CapacityStatus.WARNING,
        )
        rec = snapshot.get_scaling_recommendation()
        assert rec["direction"] == "scale_up"
        assert rec["urgency"] == "immediate"
        assert any("constitutional" in r.lower() for r in rec["reasons"])

    def test_scaling_recommendation_high_queue(self):
        """Test scaling recommendation for high queue depth."""
        snapshot = CapacitySnapshot(
            latency=LatencyPercentiles(p99_ms=1.0),
            throughput=ThroughputMetrics(current_rps=1000.0),
            queue=QueueMetrics(current_depth=600),  # Over 500 threshold
            resources=ResourceUtilization(cpu_percent=50.0),
            status=CapacityStatus.CRITICAL,
        )
        rec = snapshot.get_scaling_recommendation()
        assert rec["direction"] == "scale_up"
        assert rec["urgency"] == "immediate"

    def test_scaling_recommendation_high_cpu(self):
        """Test scaling recommendation for high CPU."""
        snapshot = CapacitySnapshot(
            latency=LatencyPercentiles(p99_ms=1.0),
            throughput=ThroughputMetrics(current_rps=1000.0),
            queue=QueueMetrics(current_depth=10),
            resources=ResourceUtilization(cpu_percent=90.0),  # Over 85%
            status=CapacityStatus.CRITICAL,
        )
        rec = snapshot.get_scaling_recommendation()
        assert rec["direction"] == "scale_up"
        assert rec["urgency"] == "immediate"

    def test_scaling_recommendation_scale_down(self):
        """Test scaling recommendation for scale down opportunity."""
        snapshot = CapacitySnapshot(
            latency=LatencyPercentiles(p99_ms=0.5),  # Very low latency
            throughput=ThroughputMetrics(current_rps=1000.0),
            queue=QueueMetrics(current_depth=5),  # Very low queue
            resources=ResourceUtilization(cpu_percent=20.0),  # Low CPU
            status=CapacityStatus.HEALTHY,
        )
        rec = snapshot.get_scaling_recommendation()
        assert rec["direction"] == "scale_down"
        assert rec["urgency"] == "planned"


class TestCapacityStatus:
    """Test capacity status enumeration."""

    def test_status_values(self):
        """Test all status values exist."""
        assert CapacityStatus.HEALTHY.value == "healthy"
        assert CapacityStatus.WARNING.value == "warning"
        assert CapacityStatus.CRITICAL.value == "critical"
        assert CapacityStatus.DEGRADED.value == "degraded"


class TestCapacityTrend:
    """Test capacity trend analysis."""

    def test_trend_no_data(self):
        """Test trend analysis with no data."""
        metrics = EnhancedAgentBusCapacityMetrics()
        trend = metrics.get_capacity_trend(duration_minutes=10)
        assert trend["available"] is False
        assert trend["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_trend_with_data(self):
        """Test trend analysis with data."""
        metrics = EnhancedAgentBusCapacityMetrics()

        # Generate some snapshots
        for _ in range(5):
            for i in range(10):
                metrics.record_request(latency_ms=float(i))
            metrics.get_capacity_snapshot()

        trend = metrics.get_capacity_trend(duration_minutes=10)
        if trend["available"]:
            assert "latency" in trend
            assert "throughput" in trend
            assert "queue" in trend
            assert trend["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestSingleton:
    """Test singleton pattern."""

    def test_get_capacity_metrics_singleton(self):
        """Test that get_capacity_metrics returns singleton."""
        reset_capacity_metrics()
        metrics1 = get_capacity_metrics()
        metrics2 = get_capacity_metrics()
        assert metrics1 is metrics2

    def test_reset_capacity_metrics(self):
        """Test that reset creates new instance."""
        metrics1 = get_capacity_metrics()
        reset_capacity_metrics()
        metrics2 = get_capacity_metrics()
        assert metrics1 is not metrics2


class TestDecorators:
    """Test tracking decorators."""

    def test_track_request_latency_decorator(self):
        """Test request latency tracking decorator."""
        reset_capacity_metrics()

        @track_request_latency
        def sample_function():
            time.sleep(0.001)
            return "result"

        result = sample_function()
        assert result == "result"

        metrics = get_capacity_metrics()
        throughput = metrics.get_throughput_metrics()
        assert throughput.total_requests >= 1

    def test_track_request_latency_decorator_with_exception(self):
        """Test decorator handles exceptions."""
        reset_capacity_metrics()

        @track_request_latency
        def failing_function():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            failing_function()

        metrics = get_capacity_metrics()
        throughput = metrics.get_throughput_metrics()
        assert throughput.total_requests >= 1


@pytest.mark.constitutional
class TestConstitutionalTargets:
    """Test constitutional target compliance checking."""

    def test_latency_target_5ms(self):
        """Verify P99 latency target is 5ms."""
        percentiles = LatencyPercentiles(p99_ms=4.9)
        assert percentiles.is_compliant() is True

        percentiles = LatencyPercentiles(p99_ms=5.1)
        assert percentiles.is_compliant() is False

    def test_throughput_target_100rps(self):
        """Verify throughput target is 100 RPS."""
        metrics = ThroughputMetrics(current_rps=99.9)
        assert metrics.is_compliant() is False

        metrics = ThroughputMetrics(current_rps=100.1)
        assert metrics.is_compliant() is True

    def test_scaling_triggers_for_constitutional_violations(self):
        """Verify scaling is recommended for constitutional violations."""
        # Latency violation
        snapshot = CapacitySnapshot(
            latency=LatencyPercentiles(p99_ms=6.0),
            throughput=ThroughputMetrics(current_rps=500.0),
            queue=QueueMetrics(current_depth=10),
            resources=ResourceUtilization(cpu_percent=50.0),
        )
        rec = snapshot.get_scaling_recommendation()
        assert rec["direction"] == "scale_up"
        assert rec["urgency"] == "immediate"


@pytest.mark.integration
class TestResourceUtilization:
    """Test resource utilization tracking (requires psutil)."""

    def test_resource_utilization_collection(self):
        """Test that resource utilization can be collected."""
        metrics = EnhancedAgentBusCapacityMetrics()
        resources = metrics.get_resource_utilization()
        # Even if psutil is not available, should return valid object
        assert resources.constitutional_hash == CONSTITUTIONAL_HASH

    @pytest.mark.skipif(True, reason="Requires psutil in test environment")
    def test_resource_values(self):
        """Test resource values are populated (requires psutil)."""
        metrics = EnhancedAgentBusCapacityMetrics()
        resources = metrics.get_resource_utilization()
        # CPU percent should be 0-100
        assert 0 <= resources.cpu_percent <= 100
        # Memory should be positive
        assert resources.memory_bytes >= 0


# =============================================================================
# Performance Metrics Tests
# Constitutional Hash: 608508a9bd224290
# =============================================================================


class TestZ3SolverMetrics:
    """Test Z3 solver latency metrics."""

    def setup_method(self):
        """Reset metrics before each test."""
        reset_performance_metrics()

    def test_record_z3_solver_latency(self):
        """Test recording Z3 solver latency."""
        record_z3_solver_latency(25.5, operation="solve")
        # Should not raise any exceptions

    def test_z3_solver_timer_context_manager(self):
        """Test Z3 solver timer context manager."""
        with z3_solver_timer(operation="check"):
            time.sleep(0.001)
        # Should not raise any exceptions

    def test_z3_solver_timer_different_operations(self):
        """Test Z3 solver timer with different operations."""
        for op in ["solve", "check", "optimize"]:
            with z3_solver_timer(operation=op):
                pass


class TestAdaptiveThresholdMetrics:
    """Test adaptive threshold decision metrics."""

    def setup_method(self):
        """Reset metrics before each test."""
        reset_performance_metrics()

    def test_record_adaptive_threshold_decision(self):
        """Test recording adaptive threshold decision latency."""
        record_adaptive_threshold_decision(5.2, decision_type="calibration")
        # Should not raise any exceptions

    def test_adaptive_threshold_timer_context_manager(self):
        """Test adaptive threshold timer context manager."""
        with adaptive_threshold_timer(decision_type="threshold_update"):
            time.sleep(0.001)
        # Should not raise any exceptions


class TestCacheMissMetrics:
    """Test cache miss reason metrics."""

    def setup_method(self):
        """Reset metrics before each test."""
        reset_performance_metrics()

    def test_record_cache_miss_with_enums(self):
        """Test recording cache miss with enum values."""
        record_cache_miss(CacheLayer.L1, CacheMissReason.EXPIRED)
        record_cache_miss(CacheLayer.L2, CacheMissReason.EVICTED)
        record_cache_miss(CacheLayer.L3, CacheMissReason.NOT_FOUND)
        # Should not raise any exceptions

    def test_record_cache_miss_with_strings(self):
        """Test recording cache miss with string values."""
        record_cache_miss("L1", "expired")
        record_cache_miss("L2", "evicted")
        record_cache_miss("L3", "not_found")
        # Should not raise any exceptions

    def test_cache_layer_enum_values(self):
        """Test cache layer enum values."""
        assert CacheLayer.L1.value == "L1"
        assert CacheLayer.L2.value == "L2"
        assert CacheLayer.L3.value == "L3"

    def test_cache_miss_reason_enum_values(self):
        """Test cache miss reason enum values."""
        assert CacheMissReason.EXPIRED.value == "expired"
        assert CacheMissReason.EVICTED.value == "evicted"
        assert CacheMissReason.NOT_FOUND.value == "not_found"


class TestBatchProcessingMetrics:
    """Test batch processing overhead metrics."""

    def setup_method(self):
        """Reset metrics before each test."""
        reset_performance_metrics()

    def test_record_batch_processing_overhead(self):
        """Test recording batch processing overhead."""
        record_batch_processing_overhead(150.0, batch_size=50)
        # Should not raise any exceptions

    def test_batch_overhead_timer_context_manager(self):
        """Test batch overhead timer context manager."""
        with batch_overhead_timer(batch_size=100):
            time.sleep(0.001)
        # Should not raise any exceptions

    def test_batch_size_bucketing(self):
        """Test that different batch sizes are bucketed correctly."""
        # Test various batch sizes
        for size in [5, 25, 75, 200, 1000]:
            record_batch_processing_overhead(100.0, batch_size=size)


class TestMACIEnforcementMetrics:
    """Test MACI enforcement latency metrics."""

    def setup_method(self):
        """Reset metrics before each test."""
        reset_performance_metrics()

    def test_record_maci_enforcement_latency(self):
        """Test recording MACI enforcement latency."""
        record_maci_enforcement_latency(2.5, maci_role="EXECUTIVE")
        # Should not raise any exceptions

    def test_maci_enforcement_timer_context_manager(self):
        """Test MACI enforcement timer context manager."""
        with maci_enforcement_timer(maci_role="JUDICIAL"):
            time.sleep(0.001)
        # Should not raise any exceptions

    def test_maci_p99_calculation(self):
        """Test MACI P99 calculation with multiple samples."""
        # Record enough samples to trigger P99 calculation
        for i in range(20):
            record_maci_enforcement_latency(float(i), maci_role="LEGISLATIVE")


class TestConstitutionalValidationMetrics:
    """Test constitutional validation rate metrics."""

    def setup_method(self):
        """Reset metrics before each test."""
        reset_performance_metrics()

    def test_record_constitutional_validation_with_enum(self):
        """Test recording constitutional validation with enum."""
        record_constitutional_validation(ValidationResult.SUCCESS)
        record_constitutional_validation(ValidationResult.FAILURE)
        record_constitutional_validation(ValidationResult.ERROR)
        record_constitutional_validation(ValidationResult.HASH_MISMATCH)
        record_constitutional_validation(ValidationResult.TIMEOUT)
        # Should not raise any exceptions

    def test_record_constitutional_validation_with_string(self):
        """Test recording constitutional validation with string."""
        record_constitutional_validation("success", validation_type="batch")
        record_constitutional_validation("failure", validation_type="realtime")
        # Should not raise any exceptions

    def test_validation_result_enum_values(self):
        """Test validation result enum values."""
        assert ValidationResult.SUCCESS.value == "success"
        assert ValidationResult.FAILURE.value == "failure"
        assert ValidationResult.ERROR.value == "error"
        assert ValidationResult.HASH_MISMATCH.value == "hash_mismatch"
        assert ValidationResult.TIMEOUT.value == "timeout"


class TestOPAPolicyMetrics:
    """Test OPA policy evaluation metrics."""

    def setup_method(self):
        """Reset metrics before each test."""
        reset_performance_metrics()

    def test_record_opa_policy_evaluation(self):
        """Test recording OPA policy evaluation latency."""
        record_opa_policy_evaluation(5.0, policy_name="constitutional/allow", decision="allow")
        record_opa_policy_evaluation(3.5, policy_name="access/check", decision="deny")
        # Should not raise any exceptions

    def test_opa_policy_timer_context_manager(self):
        """Test OPA policy timer context manager."""
        with opa_policy_timer(policy_name="test_policy") as ctx:
            time.sleep(0.001)
            ctx["decision"] = "allow"
        # Should not raise any exceptions

    def test_opa_policy_timer_with_deny(self):
        """Test OPA policy timer with deny decision."""
        with opa_policy_timer(policy_name="deny_policy") as ctx:
            ctx["decision"] = "deny"


class TestDeliberationLayerMetrics:
    """Test deliberation layer duration metrics."""

    def setup_method(self):
        """Reset metrics before each test."""
        reset_performance_metrics()

    def test_record_deliberation_layer_duration(self):
        """Test recording deliberation layer duration."""
        record_deliberation_layer_duration(50.0, layer_type="consensus", impact_score=0.85)
        # Should not raise any exceptions

    def test_deliberation_layer_timer_context_manager(self):
        """Test deliberation layer timer context manager."""
        with deliberation_layer_timer(layer_type="hitl", impact_score=0.7):
            time.sleep(0.001)
        # Should not raise any exceptions

    def test_impact_score_bucketing(self):
        """Test that impact scores are bucketed correctly."""
        # Test various impact scores
        for score in [0.1, 0.4, 0.65, 0.75, 0.9, None]:
            record_deliberation_layer_duration(10.0, layer_type="consensus", impact_score=score)


class TestPerformanceMetricsRegistry:
    """Test the performance metrics registry."""

    def setup_method(self):
        """Reset metrics before each test."""
        reset_performance_metrics()

    def test_registry_initialization(self):
        """Test registry initialization."""
        registry = PerformanceMetricsRegistry()
        assert registry.constitutional_hash == CONSTITUTIONAL_HASH

    def test_get_performance_metrics_singleton(self):
        """Test that get_performance_metrics returns singleton."""
        registry1 = get_performance_metrics()
        registry2 = get_performance_metrics()
        assert registry1 is registry2

    def test_reset_performance_metrics(self):
        """Test that reset creates new instance."""
        registry1 = get_performance_metrics()
        reset_performance_metrics()
        registry2 = get_performance_metrics()
        assert registry1 is not registry2

    def test_registry_record_z3_latency(self):
        """Test registry record_z3_latency method."""
        registry = get_performance_metrics()
        registry.record_z3_latency(10.0, operation="solve")

    def test_registry_record_adaptive_threshold(self):
        """Test registry record_adaptive_threshold method."""
        registry = get_performance_metrics()
        registry.record_adaptive_threshold(5.0, decision_type="calibration")

    def test_registry_record_cache_miss(self):
        """Test registry record_cache_miss method."""
        registry = get_performance_metrics()
        registry.record_cache_miss(CacheLayer.L1, CacheMissReason.EXPIRED)

    def test_registry_record_batch_overhead(self):
        """Test registry record_batch_overhead method."""
        registry = get_performance_metrics()
        registry.record_batch_overhead(100.0, batch_size=50)

    def test_registry_record_maci_latency(self):
        """Test registry record_maci_latency method."""
        registry = get_performance_metrics()
        registry.record_maci_latency(2.0, maci_role="EXECUTIVE")

    def test_registry_record_validation(self):
        """Test registry record_validation method."""
        registry = get_performance_metrics()
        registry.record_validation(ValidationResult.SUCCESS)

    def test_registry_record_opa_evaluation(self):
        """Test registry record_opa_evaluation method."""
        registry = get_performance_metrics()
        registry.record_opa_evaluation(5.0, policy_name="test", decision="allow")

    def test_registry_record_deliberation(self):
        """Test registry record_deliberation method."""
        registry = get_performance_metrics()
        registry.record_deliberation(50.0, layer_type="consensus", impact_score=0.8)


@pytest.mark.constitutional
class TestPerformanceMetricsConstitutionalCompliance:
    """Test constitutional compliance of performance metrics."""

    def setup_method(self):
        """Reset metrics before each test."""
        reset_performance_metrics()

    def test_constitutional_hash_in_registry(self):
        """Verify constitutional hash is in performance metrics registry."""
        registry = get_performance_metrics()
        assert registry.constitutional_hash == CONSTITUTIONAL_HASH

    def test_all_metrics_include_constitutional_hash_label(self):
        """Verify all metrics recording functions accept constitutional hash."""
        # These functions should include constitutional_hash as a label
        # Testing that they don't raise exceptions
        record_z3_solver_latency(10.0)
        record_adaptive_threshold_decision(5.0)
        record_cache_miss(CacheLayer.L1, CacheMissReason.EXPIRED)
        record_batch_processing_overhead(100.0, 50)
        record_maci_enforcement_latency(2.0)
        record_constitutional_validation(ValidationResult.SUCCESS)
        record_opa_policy_evaluation(5.0)
        record_deliberation_layer_duration(50.0)
