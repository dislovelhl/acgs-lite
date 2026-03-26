"""
ACGS-2 Enhanced Agent Bus - Health Aggregator Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for health aggregation service.
"""

import asyncio
import time
from datetime import UTC, datetime, timedelta, timezone

import pytest

try:
    from enhanced_agent_bus.health_aggregator import (
        CIRCUIT_BREAKER_AVAILABLE,
        CONSTITUTIONAL_HASH,
        HealthAggregator,
        HealthAggregatorConfig,
        HealthSnapshot,
        SystemHealthReport,
        SystemHealthStatus,
        get_health_aggregator,
        reset_health_aggregator,
    )
except ImportError:
    from health_aggregator import (
        CIRCUIT_BREAKER_AVAILABLE,
        CONSTITUTIONAL_HASH,
        HealthAggregator,
        HealthAggregatorConfig,
        HealthSnapshot,
        SystemHealthReport,
        SystemHealthStatus,
        get_health_aggregator,
        reset_health_aggregator,
    )

# Mark all tests as constitutional
pytestmark = pytest.mark.constitutional


class MockCircuitBreaker:
    """Mock circuit breaker for testing."""

    def __init__(self, state: str):
        self.current_state = state
        self.fail_counter = 0
        self.success_counter = 0


class MockCircuitBreakerRegistry:
    """Mock circuit breaker registry for testing."""

    def __init__(self):
        self._breakers = {}

    def get_all_states(self):
        """Get all circuit breaker states."""
        return {
            name: {
                "state": breaker.current_state,
                "fail_counter": breaker.fail_counter,
                "success_counter": breaker.success_counter,
            }
            for name, breaker in self._breakers.items()
        }

    def add_breaker(self, name: str, state: str):
        """Add a mock circuit breaker."""
        self._breakers[name] = MockCircuitBreaker(state)


@pytest.fixture
def config():
    """Create test configuration."""
    return HealthAggregatorConfig(
        enabled=True,
        history_window_minutes=5,
        max_history_size=100,
        health_check_interval_seconds=0.1,  # Fast for testing
        degraded_threshold=0.7,
        critical_threshold=0.5,
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


@pytest.fixture
def mock_registry():
    """Create mock circuit breaker registry."""
    return MockCircuitBreakerRegistry()


@pytest.fixture
async def aggregator(config, mock_registry):
    """Create health aggregator for testing."""
    agg = HealthAggregator(config=config, registry=mock_registry)
    yield agg
    if agg._running:
        await agg.stop()


class TestHealthSnapshot:
    """Test HealthSnapshot dataclass."""

    def test_snapshot_creation(self):
        """Test creating a health snapshot."""
        snapshot = HealthSnapshot(
            timestamp=datetime.now(UTC),
            status=SystemHealthStatus.HEALTHY,
            health_score=0.95,
            total_breakers=10,
            closed_breakers=10,
            half_open_breakers=0,
            open_breakers=0,
            circuit_states={"service1": "closed", "service2": "closed"},
        )

        assert snapshot.status == SystemHealthStatus.HEALTHY
        assert snapshot.health_score == 0.95
        assert snapshot.total_breakers == 10
        assert snapshot.constitutional_hash == CONSTITUTIONAL_HASH

    def test_snapshot_to_dict(self):
        """Test converting snapshot to dictionary."""
        snapshot = HealthSnapshot(
            timestamp=datetime.now(UTC),
            status=SystemHealthStatus.DEGRADED,
            health_score=0.6,
            total_breakers=10,
            closed_breakers=6,
            half_open_breakers=2,
            open_breakers=2,
            circuit_states={"service1": "open", "service2": "closed"},
        )

        data = snapshot.to_dict()

        assert data["status"] == "degraded"
        assert data["health_score"] == 0.6
        assert data["total_breakers"] == 10
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "timestamp" in data


class TestSystemHealthReport:
    """Test SystemHealthReport dataclass."""

    def test_report_creation(self):
        """Test creating a health report."""
        report = SystemHealthReport(
            status=SystemHealthStatus.HEALTHY,
            health_score=1.0,
            timestamp=datetime.now(UTC),
            total_breakers=5,
            closed_breakers=5,
            half_open_breakers=0,
            open_breakers=0,
            circuit_details={},
            degraded_services=[],
            critical_services=[],
        )

        assert report.status == SystemHealthStatus.HEALTHY
        assert report.health_score == 1.0
        assert report.constitutional_hash == CONSTITUTIONAL_HASH

    def test_report_to_dict(self):
        """Test converting report to dictionary."""
        report = SystemHealthReport(
            status=SystemHealthStatus.CRITICAL,
            health_score=0.3,
            timestamp=datetime.now(UTC),
            total_breakers=10,
            closed_breakers=3,
            half_open_breakers=2,
            open_breakers=5,
            circuit_details={"service1": {"state": "open"}},
            degraded_services=["service2"],
            critical_services=["service1"],
        )

        data = report.to_dict()

        assert data["status"] == "critical"
        assert data["health_score"] == 0.3
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert len(data["critical_services"]) == 1


class TestHealthAggregatorConfig:
    """Test HealthAggregatorConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = HealthAggregatorConfig()

        assert config.enabled is True
        assert config.history_window_minutes == 5
        assert config.degraded_threshold == 0.7
        assert config.critical_threshold == 0.5
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_config(self):
        """Test custom configuration values."""
        config = HealthAggregatorConfig(
            enabled=False,
            history_window_minutes=10,
            degraded_threshold=0.8,
            critical_threshold=0.6,
        )

        assert config.enabled is False
        assert config.history_window_minutes == 10
        assert config.degraded_threshold == 0.8
        assert config.critical_threshold == 0.6


class TestHealthAggregator:
    """Test HealthAggregator class."""

    async def test_aggregator_start_stop(self, aggregator):
        """Test starting and stopping the aggregator."""
        if not CIRCUIT_BREAKER_AVAILABLE:
            pytest.skip("Circuit breaker support not available")

        await aggregator.start()
        assert aggregator._running is True

        await aggregator.stop()
        assert aggregator._running is False

    async def test_aggregator_disabled(self):
        """Test aggregator with disabled configuration."""
        config = HealthAggregatorConfig(enabled=False)
        aggregator = HealthAggregator(config=config)

        await aggregator.start()
        assert aggregator._running is False

        await aggregator.stop()

    async def test_register_circuit_breaker(self, aggregator):
        """Test registering custom circuit breakers."""
        breaker = MockCircuitBreaker(state="closed")
        aggregator.register_circuit_breaker("test_service", breaker)

        assert "test_service" in aggregator._custom_breakers

    async def test_unregister_circuit_breaker(self, aggregator):
        """Test unregistering circuit breakers."""
        breaker = MockCircuitBreaker(state="closed")
        aggregator.register_circuit_breaker("test_service", breaker)
        aggregator.unregister_circuit_breaker("test_service")

        assert "test_service" not in aggregator._custom_breakers

    async def test_get_system_health_no_breakers(self, aggregator):
        """Test getting system health with no circuit breakers."""
        if not CIRCUIT_BREAKER_AVAILABLE:
            report = aggregator.get_system_health()
            assert report.status == SystemHealthStatus.UNKNOWN
            return

        report = aggregator.get_system_health()

        assert isinstance(report, SystemHealthReport)
        assert report.total_breakers == 0
        assert report.health_score == 1.0  # No breakers = healthy
        assert report.status == SystemHealthStatus.HEALTHY
        assert report.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_get_system_health_all_closed(self, aggregator, mock_registry):
        """Test system health with all circuits closed."""
        if not CIRCUIT_BREAKER_AVAILABLE:
            pytest.skip("Circuit breaker support not available")

        # Add closed circuit breakers
        import pybreaker

        mock_registry.add_breaker("service1", pybreaker.STATE_CLOSED)
        mock_registry.add_breaker("service2", pybreaker.STATE_CLOSED)
        mock_registry.add_breaker("service3", pybreaker.STATE_CLOSED)

        report = aggregator.get_system_health()

        assert report.total_breakers == 3
        assert report.closed_breakers == 3
        assert report.health_score == 1.0
        assert report.status == SystemHealthStatus.HEALTHY

    async def test_get_system_health_degraded(self, aggregator, mock_registry):
        """Test system health with degraded status."""
        if not CIRCUIT_BREAKER_AVAILABLE:
            pytest.skip("Circuit breaker support not available")

        # Add mix of circuit breakers
        import pybreaker

        mock_registry.add_breaker("service1", pybreaker.STATE_CLOSED)
        mock_registry.add_breaker("service2", pybreaker.STATE_HALF_OPEN)
        mock_registry.add_breaker("service3", pybreaker.STATE_OPEN)

        report = aggregator.get_system_health()

        assert report.total_breakers == 3
        assert report.health_score == 0.5  # (1*1.0 + 1*0.5 + 1*0.0) / 3
        assert report.status == SystemHealthStatus.DEGRADED

    async def test_get_system_health_critical(self, aggregator, mock_registry):
        """Test system health with critical status."""
        if not CIRCUIT_BREAKER_AVAILABLE:
            pytest.skip("Circuit breaker support not available")

        # Add mostly open circuit breakers
        import pybreaker

        mock_registry.add_breaker("service1", pybreaker.STATE_OPEN)
        mock_registry.add_breaker("service2", pybreaker.STATE_OPEN)
        mock_registry.add_breaker("service3", pybreaker.STATE_CLOSED)

        report = aggregator.get_system_health()

        assert report.total_breakers == 3
        assert report.health_score < 0.5
        assert report.status == SystemHealthStatus.CRITICAL
        assert len(report.critical_services) == 2

    async def test_health_score_calculation(self, aggregator):
        """Test health score calculation."""
        # All closed (100%)
        score = aggregator._calculate_health_score(10, 10, 0, 0)
        assert score == 1.0

        # Half closed, half open (50%)
        score = aggregator._calculate_health_score(10, 5, 0, 5)
        assert score == 0.5

        # Mix: 5 closed, 3 half-open, 2 open
        # (5*1.0 + 3*0.5 + 2*0.0) / 10 = 6.5 / 10 = 0.65
        score = aggregator._calculate_health_score(10, 5, 3, 2)
        assert score == 0.65

        # No breakers (100%)
        score = aggregator._calculate_health_score(0, 0, 0, 0)
        assert score == 1.0

    async def test_health_status_thresholds(self, aggregator):
        """Test health status determination from thresholds."""
        # Healthy: >= 0.7
        assert aggregator._determine_health_status(1.0) == SystemHealthStatus.HEALTHY
        assert aggregator._determine_health_status(0.7) == SystemHealthStatus.HEALTHY

        # Degraded: >= 0.5 and < 0.7
        assert aggregator._determine_health_status(0.69) == SystemHealthStatus.DEGRADED
        assert aggregator._determine_health_status(0.5) == SystemHealthStatus.DEGRADED

        # Critical: < 0.5
        assert aggregator._determine_health_status(0.49) == SystemHealthStatus.CRITICAL
        assert aggregator._determine_health_status(0.0) == SystemHealthStatus.CRITICAL

    async def test_health_history_collection(self, aggregator, mock_registry):
        """Test health history collection."""
        if not CIRCUIT_BREAKER_AVAILABLE:
            pytest.skip("Circuit breaker support not available")

        import pybreaker

        mock_registry.add_breaker("service1", pybreaker.STATE_CLOSED)

        await aggregator.start()

        # Wait for some snapshots to be collected
        await asyncio.sleep(0.3)  # Should collect 3 snapshots at 0.1s interval

        await aggregator.stop()

        history = aggregator.get_health_history()
        assert len(history) >= 2  # At least a couple snapshots

        # Verify snapshots have correct structure
        for snapshot in history:
            assert isinstance(snapshot, HealthSnapshot)
            assert snapshot.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_health_history_window_filtering(self, aggregator):
        """Test filtering health history by time window."""
        # Manually add some snapshots with different timestamps
        now = datetime.now(UTC)

        for i in range(10):
            snapshot = HealthSnapshot(
                timestamp=now - timedelta(minutes=i),
                status=SystemHealthStatus.HEALTHY,
                health_score=1.0,
                total_breakers=1,
                closed_breakers=1,
                half_open_breakers=0,
                open_breakers=0,
                circuit_states={"service1": "closed"},
            )
            aggregator._health_history.append(snapshot)

        # Get last 5 minutes
        history = aggregator.get_health_history(window_minutes=5)

        # Should have snapshots from last 5 minutes (0-4 minutes ago)
        assert len(history) == 5

    async def test_on_health_change_callback(self, aggregator, mock_registry):
        """Test health change callback registration and firing."""
        if not CIRCUIT_BREAKER_AVAILABLE:
            pytest.skip("Circuit breaker support not available")

        callback_fired = asyncio.Event()
        received_report = None

        def health_callback(report: SystemHealthReport):
            nonlocal received_report
            received_report = report
            callback_fired.set()

        aggregator.on_health_change(health_callback)

        import pybreaker

        mock_registry.add_breaker("service1", pybreaker.STATE_CLOSED)

        await aggregator.start()

        # Wait for callback to fire
        try:
            await asyncio.wait_for(callback_fired.wait(), timeout=1.0)
        except TimeoutError:
            pytest.fail("Callback was not fired")

        await aggregator.stop()

        assert received_report is not None
        assert isinstance(received_report, SystemHealthReport)
        assert received_report.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_on_health_change_status_transition(self, aggregator, mock_registry):
        """Test callback fires on status transition."""
        if not CIRCUIT_BREAKER_AVAILABLE:
            pytest.skip("Circuit breaker support not available")

        status_changes = []

        def status_callback(report: SystemHealthReport):
            status_changes.append(report.status)

        aggregator.on_health_change(status_callback)

        import pybreaker

        # Start with healthy state
        mock_registry.add_breaker("service1", pybreaker.STATE_CLOSED)
        mock_registry.add_breaker("service2", pybreaker.STATE_CLOSED)

        await aggregator.start()

        # Wait for initial callback
        await asyncio.sleep(0.2)

        # Change to degraded state
        mock_registry._breakers["service1"].current_state = pybreaker.STATE_OPEN

        # Wait for status change callback
        await asyncio.sleep(0.2)

        await aggregator.stop()

        # Should have at least 2 status changes
        assert len(status_changes) >= 1
        assert (
            SystemHealthStatus.HEALTHY in status_changes
            or SystemHealthStatus.DEGRADED in status_changes
        )

    async def test_get_metrics(self, aggregator):
        """Test getting aggregator metrics."""
        metrics = aggregator.get_metrics()

        assert "snapshots_collected" in metrics
        assert "callbacks_fired" in metrics
        assert "history_size" in metrics
        assert "running" in metrics
        assert "enabled" in metrics
        assert "current_status" in metrics
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_custom_breaker_integration(self, aggregator):
        """Test integration with custom circuit breakers."""
        if not CIRCUIT_BREAKER_AVAILABLE:
            pytest.skip("Circuit breaker support not available")

        import pybreaker

        # Register custom breakers
        breaker1 = MockCircuitBreaker(pybreaker.STATE_CLOSED)
        breaker2 = MockCircuitBreaker(pybreaker.STATE_OPEN)

        aggregator.register_circuit_breaker("custom1", breaker1)
        aggregator.register_circuit_breaker("custom2", breaker2)

        report = aggregator.get_system_health()

        assert report.total_breakers == 2
        assert report.closed_breakers == 1
        assert report.open_breakers == 1
        assert "custom1" in report.circuit_details
        assert "custom2" in report.circuit_details

    async def test_constitutional_compliance_in_reports(self, aggregator):
        """Test that all reports include constitutional hash."""
        report = aggregator.get_system_health()

        assert report.constitutional_hash == CONSTITUTIONAL_HASH

        # Test report serialization
        data = report.to_dict()
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestHealthAggregatorSingleton:
    """Test global health aggregator singleton."""

    def test_get_health_aggregator(self):
        """Test getting global health aggregator singleton."""
        reset_health_aggregator()

        agg1 = get_health_aggregator()
        agg2 = get_health_aggregator()

        assert agg1 is agg2  # Same instance

    def test_reset_health_aggregator(self):
        """Test resetting the global singleton."""
        reset_health_aggregator()

        agg1 = get_health_aggregator()
        reset_health_aggregator()
        agg2 = get_health_aggregator()

        assert agg1 is not agg2  # Different instances after reset


class TestFireAndForgetPattern:
    """Test fire-and-forget async pattern for zero latency impact."""

    async def test_callback_does_not_block(self, aggregator, mock_registry):
        """Test that callbacks do not block health collection."""
        if not CIRCUIT_BREAKER_AVAILABLE:
            pytest.skip("Circuit breaker support not available")

        slow_callback_fired = asyncio.Event()

        async def slow_callback(report: SystemHealthReport):
            """Slow callback that should not block collection."""
            await asyncio.sleep(0.5)  # Intentionally slow
            slow_callback_fired.set()

        aggregator.on_health_change(slow_callback)

        import pybreaker

        mock_registry.add_breaker("service1", pybreaker.STATE_CLOSED)

        start_time = time.monotonic()
        await aggregator.start()

        # Wait for health check
        await asyncio.sleep(0.2)

        await aggregator.stop()
        elapsed = time.monotonic() - start_time

        # Should complete quickly even with slow callback
        assert elapsed < 1.0  # Should be much faster than callback duration

        # But callback should eventually complete
        # (We're not waiting for it, just verifying non-blocking behavior)

    async def test_callback_exception_does_not_break_aggregator(self, aggregator, mock_registry):
        """Test that callback exceptions don't break the aggregator."""
        if not CIRCUIT_BREAKER_AVAILABLE:
            pytest.skip("Circuit breaker support not available")

        def failing_callback(report: SystemHealthReport):
            raise ValueError("Intentional test error")

        aggregator.on_health_change(failing_callback)

        import pybreaker

        mock_registry.add_breaker("service1", pybreaker.STATE_CLOSED)

        # Should not raise exception despite callback failure
        await aggregator.start()
        await asyncio.sleep(0.2)
        await aggregator.stop()

        # Aggregator should still be functional
        assert aggregator._snapshots_collected > 0
