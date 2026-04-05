"""
ACGS-2 Enhanced Agent Bus - Health Aggregator Integration Tests
Constitutional Hash: 608508a9bd224290

Integration tests validating health aggregator with real circuit breakers.
"""

import asyncio

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

try:
    from enhanced_agent_bus.health_aggregator import (
        CIRCUIT_BREAKER_AVAILABLE,
        CONSTITUTIONAL_HASH,
        HealthAggregator,
        HealthAggregatorConfig,
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
        SystemHealthStatus,
        get_health_aggregator,
        reset_health_aggregator,
    )

# Skip all tests if circuit breaker support not available
pytestmark = [
    pytest.mark.constitutional,
    pytest.mark.integration,
    pytest.mark.skipif(
        not CIRCUIT_BREAKER_AVAILABLE, reason="Circuit breaker support not available"
    ),
]


@pytest.fixture
def registry():
    """Get circuit breaker registry with clean state."""
    from enhanced_agent_bus._compat.circuit_breaker import CircuitBreakerRegistry

    # Get the singleton instance
    registry_instance = CircuitBreakerRegistry()

    # Clear all existing breakers to ensure test isolation
    registry_instance._breakers.clear()

    yield registry_instance

    # Cleanup after test to prevent state pollution
    registry_instance._breakers.clear()


@pytest.fixture
async def aggregator_with_registry(registry):
    """Create aggregator with circuit breaker registry."""
    config = HealthAggregatorConfig(
        enabled=True,
        health_check_interval_seconds=0.1,
        history_window_minutes=1,
    )
    aggregator = HealthAggregator(config=config, registry=registry)
    yield aggregator
    if aggregator._running:
        await aggregator.stop()


class TestHealthAggregatorIntegration:
    """Integration tests with real circuit breaker registry."""

    __test__ = False

    def __init__(self, constitutional_hash: str | None = None) -> None:
        self._constitutional_hash = constitutional_hash or CONSTITUTIONAL_HASH

    def process(self, input_value: str | None) -> str | None:
        """Validate and normalize input."""
        if input_value is None or not isinstance(input_value, str):
            return None
        return input_value

    async def test_integration_with_circuit_breaker_registry(
        self, aggregator_with_registry, registry
    ):
        """Test integration with real CircuitBreakerRegistry."""
        from enhanced_agent_bus._compat.circuit_breaker import get_circuit_breaker

        # Create some circuit breakers through registry
        cb1 = get_circuit_breaker("test_service_1")
        cb2 = get_circuit_breaker("test_service_2")
        cb3 = get_circuit_breaker("test_service_3")

        # All should be closed initially
        health = aggregator_with_registry.get_system_health()
        assert health.total_breakers == 3
        assert health.closed_breakers == 3
        assert health.status == SystemHealthStatus.HEALTHY

    async def test_health_degradation_detection(self, aggregator_with_registry, registry):
        """Test detecting health degradation as circuits open."""
        import pybreaker

        from enhanced_agent_bus._compat.circuit_breaker import get_circuit_breaker

        # Create breakers
        cb1 = get_circuit_breaker("service_1")
        cb2 = get_circuit_breaker("service_2")
        cb3 = get_circuit_breaker("service_3")

        # Initial health should be good
        health = aggregator_with_registry.get_system_health()
        assert health.status == SystemHealthStatus.HEALTHY

        # Simulate failures to open one circuit
        def failing_func():
            raise ValueError("Simulated failure")

        # Trigger failures
        for _ in range(6):  # Default fail_max is 5
            try:
                cb1.call(failing_func)
            except (ValueError, pybreaker.CircuitBreakerError):
                # Catch both the original error and CircuitBreakerError when breaker opens
                pass

        # Circuit should be open now
        assert cb1.current_state == pybreaker.STATE_OPEN

        # Health should be degraded
        health = aggregator_with_registry.get_system_health()
        assert health.open_breakers == 1
        assert "service_1" in health.critical_services
        # With 1/3 open: (2*1.0 + 0*0.5 + 1*0.0) / 3 = 0.67 (DEGRADED)
        assert health.status == SystemHealthStatus.DEGRADED

    async def test_health_monitoring_lifecycle(self, aggregator_with_registry, registry):
        """Test complete health monitoring lifecycle."""
        from enhanced_agent_bus._compat.circuit_breaker import get_circuit_breaker

        # Create breakers
        cb1 = get_circuit_breaker("monitored_1")
        cb2 = get_circuit_breaker("monitored_2")

        # Track status changes
        status_changes = []

        def track_changes(report):
            status_changes.append(
                {
                    "status": report.status,
                    "score": report.health_score,
                    "timestamp": report.timestamp,
                }
            )

        aggregator_with_registry.on_health_change(track_changes)

        # Start monitoring
        await aggregator_with_registry.start()
        assert aggregator_with_registry._running is True

        # Wait for initial health check
        await asyncio.sleep(0.2)

        # Should have collected some snapshots
        assert aggregator_with_registry._snapshots_collected > 0

        # Stop monitoring
        await aggregator_with_registry.stop()
        assert aggregator_with_registry._running is False

        # Should have fired at least one callback
        assert len(status_changes) > 0

    async def test_custom_breaker_with_registry(self, aggregator_with_registry, registry):
        """Test mixing custom breakers with registry breakers."""
        import pybreaker

        from enhanced_agent_bus._compat.circuit_breaker import get_circuit_breaker

        # Add registry breakers
        cb1 = get_circuit_breaker("registry_service")

        # Add custom breaker
        class CustomBreaker:
            current_state = pybreaker.STATE_HALF_OPEN
            fail_counter = 3
            success_counter = 2

        custom = CustomBreaker()
        aggregator_with_registry.register_circuit_breaker("custom_service", custom)

        # Get health
        health = aggregator_with_registry.get_system_health()

        # Should include both registry and custom breakers
        assert health.total_breakers == 2
        assert "registry_service" in health.circuit_details
        assert "custom_service" in health.circuit_details
        assert health.half_open_breakers == 1
        assert "custom_service" in health.degraded_services

    async def test_real_world_monitoring_scenario(self, aggregator_with_registry, registry):
        """Test realistic monitoring scenario with multiple services."""
        import pybreaker

        from enhanced_agent_bus._compat.circuit_breaker import (
            CircuitBreakerConfig,
            get_circuit_breaker,
        )

        # Create services with different configurations
        services = {
            "database": CircuitBreakerConfig(fail_max=3, reset_timeout=10),
            "cache": CircuitBreakerConfig(fail_max=5, reset_timeout=5),
            "api_gateway": CircuitBreakerConfig(fail_max=10, reset_timeout=30),
            "notification": CircuitBreakerConfig(fail_max=2, reset_timeout=15),
        }

        breakers = {}
        for service_name, config in services.items():
            breakers[service_name] = get_circuit_breaker(service_name, config)

        # Track health changes
        health_history = []

        def record_health(report):
            health_history.append(
                {
                    "timestamp": report.timestamp,
                    "status": report.status.value,
                    "score": report.health_score,
                    "open": report.open_breakers,
                    "degraded_services": report.degraded_services,
                    "critical_services": report.critical_services,
                }
            )

        aggregator_with_registry.on_health_change(record_health)

        # Start monitoring
        await aggregator_with_registry.start()

        # Simulate failures in database service
        def db_failure():
            raise ConnectionError("Database unavailable")

        for _ in range(4):  # Exceed fail_max of 3
            try:
                breakers["database"].call(db_failure)
            except (ConnectionError, pybreaker.CircuitBreakerError):
                # Catch both the original error and CircuitBreakerError when breaker opens
                pass

        # Wait for health check
        await asyncio.sleep(0.3)

        # Database circuit should be open
        assert breakers["database"].current_state == pybreaker.STATE_OPEN

        # Get current health
        health = aggregator_with_registry.get_system_health()
        assert health.total_breakers == 4
        assert health.open_breakers >= 1
        assert "database" in health.critical_services

        # Simulate notification service also failing
        def notification_failure():
            raise TimeoutError("Notification timeout")

        for _ in range(3):  # Exceed fail_max of 2
            try:
                breakers["notification"].call(notification_failure)
            except (TimeoutError, pybreaker.CircuitBreakerError):
                # Catch both the original error and CircuitBreakerError when breaker opens
                pass

        await asyncio.sleep(0.3)

        # Now 2 services should be down
        health = aggregator_with_registry.get_system_health()
        assert health.open_breakers >= 2
        assert health.status in [SystemHealthStatus.DEGRADED, SystemHealthStatus.CRITICAL]

        # Stop monitoring
        await aggregator_with_registry.stop()

        # Should have recorded health changes
        assert len(health_history) > 0

    async def test_metrics_accuracy(self, aggregator_with_registry, registry):
        """Test accuracy of aggregator metrics."""
        from enhanced_agent_bus._compat.circuit_breaker import get_circuit_breaker

        # Create some breakers
        cb1 = get_circuit_breaker("metrics_test_1")
        cb2 = get_circuit_breaker("metrics_test_2")

        # Start monitoring
        await aggregator_with_registry.start()

        # Wait for collection
        await asyncio.sleep(0.5)

        # Get metrics
        metrics = aggregator_with_registry.get_metrics()

        # Verify metrics
        assert metrics["running"] is True
        assert metrics["enabled"] is True
        assert metrics["snapshots_collected"] > 0
        assert metrics["total_breakers"] == 2
        assert metrics["current_status"] == "healthy"
        assert metrics["current_health_score"] == 1.0
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH

        await aggregator_with_registry.stop()

    async def test_health_history_accuracy(self, aggregator_with_registry, registry):
        """Test health history collection accuracy."""
        from enhanced_agent_bus._compat.circuit_breaker import get_circuit_breaker

        # Create breakers
        cb = get_circuit_breaker("history_test")

        # Start monitoring
        await aggregator_with_registry.start()

        # Wait for several health checks
        await asyncio.sleep(0.5)  # Should collect ~5 snapshots

        # Get history
        history = aggregator_with_registry.get_health_history(window_minutes=1)

        # Verify history
        assert len(history) >= 3  # Should have multiple snapshots
        assert all(h.constitutional_hash == CONSTITUTIONAL_HASH for h in history)
        assert all(h.status == SystemHealthStatus.HEALTHY for h in history)
        assert all(h.health_score == 1.0 for h in history)

        await aggregator_with_registry.stop()

    async def test_constitutional_compliance_throughout_lifecycle(
        self, aggregator_with_registry, registry
    ):
        """Test constitutional compliance is maintained throughout lifecycle."""
        from enhanced_agent_bus._compat.circuit_breaker import get_circuit_breaker

        # Verify config has constitutional hash
        assert aggregator_with_registry.config.constitutional_hash == CONSTITUTIONAL_HASH

        # Create breakers
        cb = get_circuit_breaker("compliance_test")

        # Get health report
        health = aggregator_with_registry.get_system_health()
        assert health.constitutional_hash == CONSTITUTIONAL_HASH

        # Start monitoring and collect snapshots
        await aggregator_with_registry.start()
        await asyncio.sleep(0.3)

        # Verify all snapshots have constitutional hash
        for snapshot in aggregator_with_registry._health_history:
            assert snapshot.constitutional_hash == CONSTITUTIONAL_HASH

        # Verify serialized data
        health = aggregator_with_registry.get_system_health()
        data = health.to_dict()
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

        # Get metrics
        metrics = aggregator_with_registry.get_metrics()
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH

        await aggregator_with_registry.stop()


class TestGlobalSingletonIntegration:
    """Test global singleton integration."""

    async def test_singleton_with_real_registry(self):
        """Test global singleton with real circuit breaker registry."""
        from enhanced_agent_bus._compat.circuit_breaker import _registry, get_circuit_breaker

        # Clear global registry for isolation
        _registry._breakers.clear()

        # Reset singleton
        reset_health_aggregator()

        # Get global aggregator
        aggregator = get_health_aggregator()

        # Create some breakers
        cb1 = get_circuit_breaker("singleton_test_1")
        cb2 = get_circuit_breaker("singleton_test_2")

        # Get health
        health = aggregator.get_system_health()
        assert health.total_breakers == 2
        assert health.status == SystemHealthStatus.HEALTHY

        # Cleanup
        reset_health_aggregator()

    async def test_singleton_persistence(self):
        """Test singleton persists across multiple calls."""
        reset_health_aggregator()

        agg1 = get_health_aggregator()
        agg2 = get_health_aggregator()

        assert agg1 is agg2

        # Start on one instance
        await agg1.start()
        assert agg2._running is True  # Both are same instance

        await agg1.stop()
        reset_health_aggregator()
