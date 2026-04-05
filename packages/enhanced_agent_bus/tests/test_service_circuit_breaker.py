"""
ACGS-2 Enhanced Agent Bus - Service Circuit Breaker Tests
Constitutional Hash: 608508a9bd224290

Tests for T002: Circuit Breaker Configuration
Expert Reference: Michael Nygard (Release It!)
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import centralized constitutional hash
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the circuit breaker registry before each test."""
    from enhanced_agent_bus.circuit_breaker import reset_circuit_breaker_registry

    reset_circuit_breaker_registry()
    yield
    reset_circuit_breaker_registry()


class TestServiceCircuitConfig:
    """Tests for ServiceCircuitConfig."""

    def test_default_configs_exist(self):
        """Test that all required default configs are defined."""
        from enhanced_agent_bus.circuit_breaker import SERVICE_CIRCUIT_CONFIGS

        # T002 required services
        required_services = [
            "policy_registry",
            "opa_evaluator",
            "blockchain_anchor",
            "redis_cache",
            "kafka_producer",  # Added for T002 enhanced
        ]

        for service in required_services:
            assert service in SERVICE_CIRCUIT_CONFIGS, f"Missing config for {service}"

    def test_policy_registry_config(self):
        """Test policy_registry configuration matches T002 requirements."""
        from enhanced_agent_bus.circuit_breaker import (
            SERVICE_CIRCUIT_CONFIGS,
            FallbackStrategy,
        )

        config = SERVICE_CIRCUIT_CONFIGS["policy_registry"]

        assert config.failure_threshold == 3
        assert config.timeout_seconds == 10.0
        assert config.fallback_strategy == FallbackStrategy.CACHED_VALUE
        assert config.fallback_ttl_seconds == 300  # 5 minutes

    def test_opa_evaluator_config(self):
        """Test opa_evaluator configuration matches T002 requirements."""
        from enhanced_agent_bus.circuit_breaker import (
            SERVICE_CIRCUIT_CONFIGS,
            FallbackStrategy,
            ServiceSeverity,
        )

        config = SERVICE_CIRCUIT_CONFIGS["opa_evaluator"]

        assert config.failure_threshold == 5
        assert config.timeout_seconds == 5.0
        assert config.fallback_strategy == FallbackStrategy.FAIL_CLOSED
        assert config.severity == ServiceSeverity.CRITICAL

    def test_blockchain_anchor_config(self):
        """Test blockchain_anchor configuration matches T002 requirements."""
        from enhanced_agent_bus.circuit_breaker import (
            SERVICE_CIRCUIT_CONFIGS,
            FallbackStrategy,
        )

        config = SERVICE_CIRCUIT_CONFIGS["blockchain_anchor"]

        assert config.failure_threshold == 10
        assert config.timeout_seconds == 60.0
        assert config.fallback_strategy == FallbackStrategy.QUEUE_FOR_RETRY
        assert config.fallback_max_queue_size == 10000
        assert config.fallback_retry_interval_seconds == 300  # 5 minutes

    def test_redis_cache_config(self):
        """Test redis_cache configuration matches T002 requirements."""
        from enhanced_agent_bus.circuit_breaker import (
            SERVICE_CIRCUIT_CONFIGS,
            FallbackStrategy,
        )

        config = SERVICE_CIRCUIT_CONFIGS["redis_cache"]

        assert config.failure_threshold == 3
        assert config.timeout_seconds == 1.0
        assert config.fallback_strategy == FallbackStrategy.BYPASS

    def test_kafka_producer_config(self):
        """Test kafka_producer configuration matches T002 requirements."""
        from enhanced_agent_bus.circuit_breaker import (
            SERVICE_CIRCUIT_CONFIGS,
            FallbackStrategy,
            ServiceSeverity,
        )

        config = SERVICE_CIRCUIT_CONFIGS["kafka_producer"]

        assert config.failure_threshold == 5
        assert config.timeout_seconds == 30.0
        assert config.fallback_strategy == FallbackStrategy.QUEUE_FOR_RETRY
        assert config.fallback_max_queue_size == 10000
        assert config.severity == ServiceSeverity.HIGH

    def test_config_to_dict(self):
        """Test configuration serialization."""
        from enhanced_agent_bus.circuit_breaker import SERVICE_CIRCUIT_CONFIGS

        config = SERVICE_CIRCUIT_CONFIGS["policy_registry"]
        config_dict = config.to_dict()

        assert config_dict["name"] == "policy_registry"
        assert config_dict["failure_threshold"] == 3
        assert config_dict["fallback_strategy"] == "cached_value"
        assert config_dict["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestServiceCircuitBreaker:
    """Tests for ServiceCircuitBreaker state transitions."""

    async def test_initial_state_is_closed(self):
        """Test that circuit breaker starts in closed state."""
        from enhanced_agent_bus.circuit_breaker import (
            CircuitState,
            get_service_circuit_breaker,
        )

        cb = await get_service_circuit_breaker("policy_registry")

        assert cb.state == CircuitState.CLOSED
        assert cb.is_closed
        assert not cb.is_open
        assert not cb.is_half_open

    async def test_transition_to_open_after_failures(self):
        """Test circuit opens after failure threshold is reached."""
        from enhanced_agent_bus.circuit_breaker import (
            CircuitState,
            get_service_circuit_breaker,
        )

        cb = await get_service_circuit_breaker("policy_registry")

        # Record failures up to threshold (3 for policy_registry)
        for _i in range(3):
            await cb.record_failure(Exception("test failure"), "TestError")

        assert cb.state == CircuitState.OPEN
        assert cb.is_open
        assert not await cb.can_execute()

    async def test_transition_to_half_open_after_timeout(self):
        """Test circuit transitions to half-open after timeout."""
        from enhanced_agent_bus.circuit_breaker import (
            CircuitState,
            ServiceCircuitBreaker,
            ServiceCircuitConfig,
        )

        # Create a breaker with very short timeout for testing
        config = ServiceCircuitConfig(
            name="test_service",
            failure_threshold=1,
            timeout_seconds=0.1,  # 100ms timeout
        )
        cb = ServiceCircuitBreaker(config)

        # Trigger circuit open
        await cb.record_failure(Exception("test"), "TestError")
        assert cb.state == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(0.15)

        # Next can_execute should transition to half-open
        can_execute = await cb.can_execute()
        assert can_execute
        assert cb.state == CircuitState.HALF_OPEN

    async def test_transition_to_closed_after_successes(self):
        """Test circuit closes after successful half-open requests."""
        from enhanced_agent_bus.circuit_breaker import (
            CircuitState,
            ServiceCircuitBreaker,
            ServiceCircuitConfig,
        )

        config = ServiceCircuitConfig(
            name="test_service",
            failure_threshold=1,
            timeout_seconds=0.1,
            half_open_requests=2,
        )
        cb = ServiceCircuitBreaker(config)

        # Open the circuit
        await cb.record_failure(Exception("test"), "TestError")
        assert cb.state == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(0.15)
        await cb.can_execute()
        assert cb.state == CircuitState.HALF_OPEN

        # Record successes in half-open state
        await cb.record_success()
        await cb.record_success()

        assert cb.state == CircuitState.CLOSED

    async def test_half_open_failure_reopens_circuit(self):
        """Test that failure in half-open state reopens the circuit."""
        from enhanced_agent_bus.circuit_breaker import (
            CircuitState,
            ServiceCircuitBreaker,
            ServiceCircuitConfig,
        )

        config = ServiceCircuitConfig(
            name="test_service",
            failure_threshold=1,
            timeout_seconds=0.1,
            half_open_requests=3,
        )
        cb = ServiceCircuitBreaker(config)

        # Open -> wait -> half-open
        await cb.record_failure(Exception("test"), "TestError")
        await asyncio.sleep(0.15)
        await cb.can_execute()
        assert cb.state == CircuitState.HALF_OPEN

        # One success
        await cb.record_success()

        # Then a failure
        await cb.record_failure(Exception("test"), "TestError")

        # Should reopen the circuit
        assert cb.state == CircuitState.OPEN


class TestFallbackStrategies:
    """Tests for fallback strategy implementations."""

    async def test_cached_value_fallback(self):
        """Test CACHED_VALUE fallback returns cached data."""
        from enhanced_agent_bus.circuit_breaker import get_service_circuit_breaker

        cb = await get_service_circuit_breaker("policy_registry")

        # Set cached fallback
        test_data = {"policies": ["policy1", "policy2"]}
        cb.set_cached_fallback("test_key", test_data)

        # Verify retrieval
        cached = cb.get_cached_fallback("test_key")
        assert cached == test_data

    async def test_cached_value_expiry(self):
        """Test cached values expire after TTL."""
        from enhanced_agent_bus.circuit_breaker import (
            ServiceCircuitBreaker,
            ServiceCircuitConfig,
        )

        config = ServiceCircuitConfig(
            name="test_service",
            failure_threshold=3,
            timeout_seconds=10.0,
            fallback_ttl_seconds=1,  # 1 second TTL
        )
        cb = ServiceCircuitBreaker(config)

        # Set cached value
        cb.set_cached_fallback("test_key", {"data": "test"})
        assert cb.get_cached_fallback("test_key") is not None

        # Wait for expiry
        await asyncio.sleep(1.1)

        # Should be expired
        assert cb.get_cached_fallback("test_key") is None

    async def test_queue_for_retry(self):
        """Test QUEUE_FOR_RETRY fallback queues requests."""
        from enhanced_agent_bus.circuit_breaker import get_service_circuit_breaker

        cb = await get_service_circuit_breaker("blockchain_anchor")

        # Queue a request
        result = await cb.queue_for_retry(
            "request_123",
            ("arg1", "arg2"),
            {"key": "value"},
        )

        assert result is True
        assert cb.get_queue_size() == 1

    async def test_queue_max_size_limit(self):
        """Test retry queue respects max size limit."""
        from enhanced_agent_bus.circuit_breaker import (
            ServiceCircuitBreaker,
            ServiceCircuitConfig,
        )

        config = ServiceCircuitConfig(
            name="test_service",
            failure_threshold=3,
            timeout_seconds=10.0,
            fallback_max_queue_size=2,
        )
        cb = ServiceCircuitBreaker(config)

        # Queue up to limit
        await cb.queue_for_retry("req_1", (), {})
        await cb.queue_for_retry("req_2", (), {})

        # Third should fail
        result = await cb.queue_for_retry("req_3", (), {})
        assert result is False
        assert cb.get_queue_size() == 2


class TestCircuitBreakerRegistry:
    """Tests for ServiceCircuitBreakerRegistry."""

    async def test_get_or_create(self):
        """Test getting or creating circuit breakers."""
        from enhanced_agent_bus.circuit_breaker import get_circuit_breaker_registry

        registry = get_circuit_breaker_registry()

        cb1 = await registry.get_or_create("policy_registry")
        cb2 = await registry.get_or_create("policy_registry")

        # Same instance returned
        assert cb1 is cb2

    async def test_initialize_default_circuits(self):
        """Test initialization of all default circuit breakers."""
        from enhanced_agent_bus.circuit_breaker import (
            SERVICE_CIRCUIT_CONFIGS,
            get_circuit_breaker_registry,
        )

        registry = get_circuit_breaker_registry()
        await registry.initialize_default_circuits()

        states = registry.get_all_states()

        # All configured services should be initialized
        for service in SERVICE_CIRCUIT_CONFIGS.keys():
            assert service in states

    async def test_health_summary(self):
        """Test health summary calculation."""
        from enhanced_agent_bus.circuit_breaker import get_circuit_breaker_registry

        registry = get_circuit_breaker_registry()
        await registry.initialize_default_circuits()

        summary = registry.get_health_summary()

        assert "status" in summary
        assert "health_score" in summary
        assert "total_circuits" in summary
        assert "closed" in summary
        assert "open" in summary
        assert "half_open" in summary
        assert summary["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_reset_single_circuit(self):
        """Test resetting a single circuit breaker."""
        from enhanced_agent_bus.circuit_breaker import (
            CircuitState,
            get_circuit_breaker_registry,
        )

        registry = get_circuit_breaker_registry()
        cb = await registry.get_or_create("policy_registry")

        # Open the circuit
        for _ in range(3):
            await cb.record_failure(Exception("test"), "TestError")

        assert cb.state == CircuitState.OPEN

        # Reset
        success = await registry.reset("policy_registry")
        assert success
        assert cb.state == CircuitState.CLOSED

    async def test_reset_all_circuits(self):
        """Test resetting all circuit breakers."""
        from enhanced_agent_bus.circuit_breaker import (
            CircuitState,
            get_circuit_breaker_registry,
        )

        registry = get_circuit_breaker_registry()

        # Create and open multiple circuits
        cb1 = await registry.get_or_create("policy_registry")
        cb2 = await registry.get_or_create("opa_evaluator")

        for _ in range(5):
            await cb1.record_failure(Exception("test"), "TestError")
            await cb2.record_failure(Exception("test"), "TestError")

        # Reset all
        await registry.reset_all()

        assert cb1.state == CircuitState.CLOSED
        assert cb2.state == CircuitState.CLOSED


class TestCircuitBreakerDecorator:
    """Tests for with_service_circuit_breaker decorator."""

    async def test_decorator_records_success(self):
        """Test decorator records successful calls."""
        from enhanced_agent_bus.circuit_breaker import (
            get_service_circuit_breaker,
            with_service_circuit_breaker,
        )

        @with_service_circuit_breaker("policy_registry")
        async def mock_service():
            return {"result": "success"}

        result = await mock_service()

        assert result["result"] == "success"

        cb = await get_service_circuit_breaker("policy_registry")
        assert cb.metrics.successful_calls == 1

    async def test_decorator_records_failure(self):
        """Test decorator records failed calls."""
        from enhanced_agent_bus.circuit_breaker import (
            get_service_circuit_breaker,
            with_service_circuit_breaker,
        )

        @with_service_circuit_breaker("policy_registry")
        async def failing_service():
            raise ValueError("Service error")

        with pytest.raises(ValueError):
            await failing_service()

        cb = await get_service_circuit_breaker("policy_registry")
        assert cb.metrics.failed_calls == 1

    async def test_decorator_fail_closed_when_open(self):
        """Test FAIL_CLOSED strategy raises exception when circuit is open."""
        from enhanced_agent_bus.circuit_breaker import (
            CircuitBreakerOpen,
            get_service_circuit_breaker,
            with_service_circuit_breaker,
        )

        # Pre-open the circuit
        cb = await get_service_circuit_breaker("opa_evaluator")
        for _ in range(5):
            await cb.record_failure(Exception("test"), "TestError")

        @with_service_circuit_breaker("opa_evaluator")
        async def opa_service():
            return {"allowed": True}

        with pytest.raises(CircuitBreakerOpen) as exc_info:
            await opa_service()

        assert "opa_evaluator" in str(exc_info.value)
        assert "fail_closed" in str(exc_info.value)

    async def test_decorator_cached_fallback(self):
        """Test CACHED_VALUE strategy returns cached value when circuit is open."""
        from enhanced_agent_bus.circuit_breaker import (
            get_service_circuit_breaker,
            with_service_circuit_breaker,
        )

        # Pre-populate cache
        cb = await get_service_circuit_breaker("policy_registry")
        cb.set_cached_fallback("policy_registry", {"policies": ["cached"]})

        # Open the circuit
        for _ in range(3):
            await cb.record_failure(Exception("test"), "TestError")

        @with_service_circuit_breaker("policy_registry", cache_key="policy_registry")
        async def policy_service():
            return {"policies": ["live"]}

        result = await policy_service()

        assert result["policies"] == ["cached"]

    async def test_decorator_bypass_strategy(self):
        """Test BYPASS strategy returns fallback value when circuit is open."""
        from enhanced_agent_bus.circuit_breaker import (
            get_service_circuit_breaker,
            with_service_circuit_breaker,
        )

        # Open the circuit
        cb = await get_service_circuit_breaker("redis_cache")
        for _ in range(3):
            await cb.record_failure(Exception("test"), "TestError")

        @with_service_circuit_breaker("redis_cache", fallback_value=None)
        async def redis_get():
            return {"data": "from_redis"}

        result = await redis_get()

        # Bypass returns fallback_value (None)
        assert result is None


class TestCircuitBreakerMetrics:
    """Tests for Prometheus metrics integration."""

    async def test_metrics_are_updated(self):
        """Test that Prometheus metrics are updated correctly."""
        from enhanced_agent_bus.circuit_breaker import get_service_circuit_breaker

        cb = await get_service_circuit_breaker("policy_registry")

        # Record some activity
        await cb.record_success()
        await cb.record_success()
        await cb.record_failure(Exception("test"), "TestError")

        assert cb.metrics.total_calls == 3
        assert cb.metrics.successful_calls == 2
        assert cb.metrics.failed_calls == 1

    async def test_status_includes_all_fields(self):
        """Test get_status includes all required fields."""
        from enhanced_agent_bus.circuit_breaker import get_service_circuit_breaker

        cb = await get_service_circuit_breaker("policy_registry")
        status = cb.get_status()

        required_fields = [
            "name",
            "state",
            "consecutive_failures",
            "failure_threshold",
            "timeout_seconds",
            "half_open_requests",
            "fallback_strategy",
            "severity",
            "metrics",
            "constitutional_hash",
        ]

        for field in required_fields:
            assert field in status, f"Missing field: {field}"


class TestConstitutionalCompliance:
    """Tests for constitutional hash compliance."""

    def test_configs_include_constitutional_hash(self):
        """Test all configs include constitutional hash."""
        from enhanced_agent_bus.circuit_breaker import SERVICE_CIRCUIT_CONFIGS

        for name, config in SERVICE_CIRCUIT_CONFIGS.items():
            assert config.constitutional_hash == CONSTITUTIONAL_HASH, (
                f"Config {name} has incorrect constitutional hash"
            )

    async def test_circuit_breaker_has_constitutional_hash(self):
        """Test circuit breaker instances have constitutional hash."""
        from enhanced_agent_bus.circuit_breaker import get_service_circuit_breaker

        cb = await get_service_circuit_breaker("policy_registry")

        assert cb.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_status_includes_constitutional_hash(self):
        """Test status output includes constitutional hash."""
        from enhanced_agent_bus.circuit_breaker import get_service_circuit_breaker

        cb = await get_service_circuit_breaker("policy_registry")
        status = cb.get_status()

        assert status["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestCircuitHealthRouter:
    """Tests for the /health/circuits endpoint router."""

    async def test_router_creation(self):
        """Test that the circuit health router can be created."""
        from enhanced_agent_bus.circuit_breaker import create_circuit_health_router

        router = create_circuit_health_router()

        # Router should be created (or None if FastAPI not available)
        # We just check it doesn't raise an exception


class TestUnifiedConfigIntegration:
    """Tests for unified configuration integration (T002 requirement)."""

    def test_get_service_config_static_fallback(self):
        """Test get_service_config works with static config when unified config unavailable."""
        from enhanced_agent_bus.circuit_breaker import get_service_config

        # Use static config
        config = get_service_config("policy_registry", use_unified_config=False)

        assert config.name == "policy_registry"
        assert config.failure_threshold == 3
        assert config.timeout_seconds == 10.0
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_get_service_config_unknown_service(self):
        """Test get_service_config returns default for unknown services."""
        from enhanced_agent_bus.circuit_breaker import (
            FallbackStrategy,
            ServiceSeverity,
            get_service_config,
        )

        config = get_service_config("unknown_service", use_unified_config=False)

        assert config.name == "unknown_service"
        assert config.failure_threshold == 5
        assert config.timeout_seconds == 30.0
        assert config.fallback_strategy == FallbackStrategy.FAIL_CLOSED
        assert config.severity == ServiceSeverity.MEDIUM
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_get_service_config_with_unified_config(self):
        """Test get_service_config can load from unified config."""
        from enhanced_agent_bus.circuit_breaker import get_service_config

        # This will attempt to load from unified config
        # Should succeed or fall back gracefully
        config = get_service_config("policy_registry", use_unified_config=True)

        assert config.name == "policy_registry"
        assert config.constitutional_hash == CONSTITUTIONAL_HASH
        # Values should be present (either from unified or static)
        assert config.failure_threshold > 0
        assert config.timeout_seconds > 0

    def test_all_t002_services_have_configs(self):
        """Test all T002 required services have configurations."""
        from enhanced_agent_bus.circuit_breaker import SERVICE_CIRCUIT_CONFIGS

        # T002 required services
        required_services = [
            "policy_registry",
            "opa_evaluator",
            "blockchain_anchor",
            "redis_cache",
            "kafka_producer",
            "audit_service",
            "deliberation_layer",
        ]

        for service in required_services:
            assert service in SERVICE_CIRCUIT_CONFIGS, (
                f"T002 required service '{service}' missing from SERVICE_CIRCUIT_CONFIGS"
            )

    def test_opa_evaluator_is_critical(self):
        """Test OPA evaluator is marked as CRITICAL severity (T002)."""
        from enhanced_agent_bus.circuit_breaker import (
            SERVICE_CIRCUIT_CONFIGS,
            FallbackStrategy,
            ServiceSeverity,
        )

        config = SERVICE_CIRCUIT_CONFIGS["opa_evaluator"]

        assert config.severity == ServiceSeverity.CRITICAL
        assert config.fallback_strategy == FallbackStrategy.FAIL_CLOSED

    def test_blockchain_anchor_uses_queue_for_retry(self):
        """Test blockchain anchor uses queue_for_retry fallback (T002)."""
        from enhanced_agent_bus.circuit_breaker import (
            SERVICE_CIRCUIT_CONFIGS,
            FallbackStrategy,
        )

        config = SERVICE_CIRCUIT_CONFIGS["blockchain_anchor"]

        assert config.fallback_strategy == FallbackStrategy.QUEUE_FOR_RETRY
        assert config.fallback_max_queue_size == 10000
        assert config.fallback_retry_interval_seconds == 300


class TestCircuitBreakerStateTracking:
    """Tests for circuit breaker state tracking (T002 requirement)."""

    async def test_state_tracking_metrics(self):
        """Test state changes are properly tracked in metrics."""
        from enhanced_agent_bus.circuit_breaker import (
            CircuitState,
            ServiceCircuitBreaker,
            ServiceCircuitConfig,
        )

        config = ServiceCircuitConfig(
            name="test_tracking",
            failure_threshold=2,
            timeout_seconds=0.1,
        )
        cb = ServiceCircuitBreaker(config)

        # Initial state
        assert cb.state == CircuitState.CLOSED
        assert cb.metrics.state_changes == 0

        # Trigger open
        await cb.record_failure(Exception("test"), "TestError")
        await cb.record_failure(Exception("test 2"), "TestError")

        assert cb.state == CircuitState.OPEN
        assert cb.metrics.state_changes == 1

        # Wait for half-open
        await asyncio.sleep(0.15)
        await cb.can_execute()

        assert cb.state == CircuitState.HALF_OPEN
        assert cb.metrics.state_changes == 2

    async def test_metrics_timestamps(self):
        """Test metrics include proper timestamps."""
        from enhanced_agent_bus.circuit_breaker import get_service_circuit_breaker

        cb = await get_service_circuit_breaker("policy_registry")

        # Record success
        await cb.record_success()
        assert cb.metrics.last_success_time is not None

        # Record failure - single failure doesn't trigger state change
        await cb.record_failure(Exception("test"), "TestError")
        assert cb.metrics.last_failure_time is not None

        # last_state_change_time should be None since no state transition occurred yet
        # (a single failure doesn't exceed the failure_threshold=3 for policy_registry)
        assert cb.metrics.last_state_change_time is None

        # Trigger enough failures to cause a state change (CLOSED -> OPEN)
        # policy_registry has failure_threshold=3, we already have 1 failure
        await cb.record_failure(Exception("test"), "TestError")
        await cb.record_failure(Exception("test 2"), "TestError")

        # Now a state change should have occurred
        assert cb.metrics.last_state_change_time is not None
        assert cb.metrics.state_changes >= 1


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
