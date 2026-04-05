"""
ACGS-2 Enhanced Agent Bus - ACL Adapter Registry Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the AdapterRegistry class covering:
- Singleton pattern enforcement
- Adapter lifecycle management (create, get, remove, clear)
- Health aggregation across adapters
- Metrics collection and aggregation
- Async close operations
"""

import pytest

pytest.importorskip("acl_adapters.base")


from datetime import UTC, datetime, timezone
from typing import Any, Optional
from unittest.mock import Mock

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.types import JSONDict
from enhanced_agent_bus.acl_adapters.base import ACLAdapter, AdapterConfig
from enhanced_agent_bus.acl_adapters.registry import (
    AdapterRegistry,
    get_adapter,
    get_registry,
)


class MockAdapter(ACLAdapter[Any, JSONDict]):
    """Mock adapter for testing registry operations."""

    def __init__(self, name: str, config: AdapterConfig | None = None):
        super().__init__(name=name, config=config)
        self._healthy = True
        self._closed = False
        self._custom_metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "cache_hits": 0,
            "fallback_uses": 0,
        }

    async def _execute(self, request: Any) -> JSONDict:
        """Implement abstract method for testing."""
        self._custom_metrics["total_calls"] += 1
        self._custom_metrics["successful_calls"] += 1
        return {"result": "success"}

    def _validate_response(self, response: Any) -> bool:
        """Validate response - always returns True for testing."""
        return True

    def _get_cache_key(self, request: Any) -> str:
        """Generate cache key for testing."""
        return f"mock_cache_key_{hash(str(request))}"

    def _get_fallback_response(self, request: Any) -> JSONDict | None:
        """Provide fallback response for testing."""
        self._custom_metrics["fallback_uses"] += 1
        return {"result": "fallback"}

    def get_health(self) -> JSONDict:
        """Override to allow setting healthy state for testing."""
        return {
            "healthy": self._healthy,
            "adapter_name": self.name,
            "constitutional_hash": self.constitutional_hash,
            "state": "closed" if self._healthy else "open",
            "time_until_recovery": 0,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def get_metrics(self) -> JSONDict:
        """Override to return custom test metrics."""
        return self._custom_metrics.copy()

    async def close(self) -> None:
        """Close the adapter."""
        self._closed = True


class MockAdapterNoClose(ACLAdapter[Any, JSONDict]):
    """Mock adapter without close method for testing graceful handling."""

    def __init__(self, name: str, config: AdapterConfig | None = None):
        super().__init__(name=name, config=config)

    async def _execute(self, request: Any) -> JSONDict:
        """Implement abstract method for testing."""
        return {"result": "success"}

    def _validate_response(self, response: Any) -> bool:
        """Validate response - always returns True for testing."""
        return True

    def _get_cache_key(self, request: Any) -> str:
        """Generate cache key for testing."""
        return f"mock_cache_key_{hash(str(request))}"

    def get_health(self) -> JSONDict:
        """Simple health check."""
        return {
            "healthy": True,
            "adapter_name": self.name,
            "constitutional_hash": self.constitutional_hash,
            "state": "closed",
            "time_until_recovery": 0,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def get_metrics(self) -> JSONDict:
        """Simple metrics."""
        return {"total_calls": 0}


@pytest.fixture
def fresh_registry():
    """Create a fresh registry instance by resetting the singleton."""
    AdapterRegistry._instance = None
    AdapterRegistry._adapters = {}
    registry = AdapterRegistry()
    yield registry
    # Cleanup
    registry.clear()
    AdapterRegistry._instance = None
    AdapterRegistry._adapters = {}


@pytest.fixture
def registry_with_adapters(fresh_registry):
    """Create a registry with some pre-registered adapters."""
    adapter1 = fresh_registry.get_or_create("adapter-1", MockAdapter)
    adapter2 = fresh_registry.get_or_create("adapter-2", MockAdapter)
    return fresh_registry


class TestAdapterRegistrySingleton:
    """Tests for singleton pattern."""

    def test_singleton_returns_same_instance(self, fresh_registry):
        """Test that multiple instantiations return the same instance."""
        registry1 = AdapterRegistry()
        registry2 = AdapterRegistry()

        assert registry1 is registry2

    def test_singleton_preserves_state(self, fresh_registry):
        """Test that singleton preserves state across instantiations."""
        registry1 = AdapterRegistry()
        registry1.get_or_create("test-adapter", MockAdapter)

        registry2 = AdapterRegistry()
        assert "test-adapter" in registry2.list_adapters()


class TestGetOrCreate:
    """Tests for get_or_create method."""

    def test_create_new_adapter(self, fresh_registry):
        """Test creating a new adapter."""
        adapter = fresh_registry.get_or_create("new-adapter", MockAdapter)

        assert adapter is not None
        assert isinstance(adapter, MockAdapter)
        assert adapter.name == "new-adapter"
        assert "new-adapter" in fresh_registry.list_adapters()

    def test_get_existing_adapter(self, fresh_registry):
        """Test getting an existing adapter returns same instance."""
        adapter1 = fresh_registry.get_or_create("test-adapter", MockAdapter)
        adapter2 = fresh_registry.get_or_create("test-adapter", MockAdapter)

        assert adapter1 is adapter2

    def test_create_with_config(self, fresh_registry):
        """Test creating adapter with configuration."""
        config = AdapterConfig(timeout_ms=5000, max_retries=5)
        adapter = fresh_registry.get_or_create("configured-adapter", MockAdapter, config=config)

        assert adapter is not None
        assert adapter.config is not None
        assert adapter.config.timeout_ms == 5000
        assert adapter.config.max_retries == 5

    def test_create_multiple_adapters(self, fresh_registry):
        """Test creating multiple different adapters."""
        adapter1 = fresh_registry.get_or_create("adapter-1", MockAdapter)
        adapter2 = fresh_registry.get_or_create("adapter-2", MockAdapter)

        assert adapter1 is not adapter2
        assert len(fresh_registry.list_adapters()) == 2


class TestGet:
    """Tests for get method."""

    def test_get_existing_adapter(self, registry_with_adapters):
        """Test getting an existing adapter."""
        adapter = registry_with_adapters.get("adapter-1")

        assert adapter is not None
        assert isinstance(adapter, MockAdapter)

    def test_get_nonexistent_adapter(self, fresh_registry):
        """Test getting a non-existent adapter returns None."""
        adapter = fresh_registry.get("nonexistent")

        assert adapter is None


class TestRemove:
    """Tests for remove method."""

    def test_remove_existing_adapter(self, registry_with_adapters):
        """Test removing an existing adapter."""
        initial_count = len(registry_with_adapters.list_adapters())

        result = registry_with_adapters.remove("adapter-1")

        assert result is True
        assert "adapter-1" not in registry_with_adapters.list_adapters()
        assert len(registry_with_adapters.list_adapters()) == initial_count - 1

    def test_remove_nonexistent_adapter(self, fresh_registry):
        """Test removing a non-existent adapter returns False."""
        result = fresh_registry.remove("nonexistent")

        assert result is False


class TestListAdapters:
    """Tests for list_adapters method."""

    def test_list_empty_registry(self, fresh_registry):
        """Test listing adapters from empty registry."""
        adapters = fresh_registry.list_adapters()

        assert adapters == []

    def test_list_populated_registry(self, registry_with_adapters):
        """Test listing adapters from populated registry."""
        adapters = registry_with_adapters.list_adapters()

        assert len(adapters) == 2
        assert "adapter-1" in adapters
        assert "adapter-2" in adapters


class TestResetAll:
    """Tests for reset_all method."""

    def test_reset_all_adapters(self, fresh_registry):
        """Test resetting all adapters."""
        # Create adapters with mock methods
        adapter1 = fresh_registry.get_or_create("adapter-1", MockAdapter)
        adapter2 = fresh_registry.get_or_create("adapter-2", MockAdapter)

        # Mock the reset methods
        adapter1.reset_circuit_breaker = Mock()
        adapter1.clear_cache = Mock()
        adapter2.reset_circuit_breaker = Mock()
        adapter2.clear_cache = Mock()

        fresh_registry.reset_all()

        adapter1.reset_circuit_breaker.assert_called_once()
        adapter1.clear_cache.assert_called_once()
        adapter2.reset_circuit_breaker.assert_called_once()
        adapter2.clear_cache.assert_called_once()


class TestGetAllHealth:
    """Tests for get_all_health method."""

    def test_health_empty_registry(self, fresh_registry):
        """Test health check on empty registry."""
        health = fresh_registry.get_all_health()

        assert health["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert health["overall_health"] == "healthy"
        assert health["health_score"] == 1.0
        assert health["total_count"] == 0
        assert health["healthy_count"] == 0
        assert health["adapters"] == {}

    def test_health_all_healthy(self, fresh_registry):
        """Test health check when all adapters are healthy."""
        adapter1 = fresh_registry.get_or_create("adapter-1", MockAdapter)
        adapter2 = fresh_registry.get_or_create("adapter-2", MockAdapter)
        adapter1._healthy = True
        adapter2._healthy = True

        health = fresh_registry.get_all_health()

        assert health["overall_health"] == "healthy"
        assert health["health_score"] == 1.0
        assert health["healthy_count"] == 2
        assert health["total_count"] == 2

    def test_health_some_degraded(self, fresh_registry):
        """Test health check when some adapters are unhealthy."""
        adapter1 = fresh_registry.get_or_create("adapter-1", MockAdapter)
        adapter2 = fresh_registry.get_or_create("adapter-2", MockAdapter)
        adapter1._healthy = True
        adapter2._healthy = False

        health = fresh_registry.get_all_health()

        assert health["overall_health"] == "degraded"
        assert health["health_score"] == 0.5
        assert health["healthy_count"] == 1
        assert health["total_count"] == 2

    def test_health_includes_timestamp(self, fresh_registry):
        """Test that health includes a timestamp."""
        fresh_registry.get_or_create("adapter-1", MockAdapter)

        health = fresh_registry.get_all_health()

        assert "timestamp" in health
        # Verify it's a valid ISO format timestamp
        datetime.fromisoformat(health["timestamp"].replace("Z", "+00:00"))


class TestGetAllMetrics:
    """Tests for get_all_metrics method."""

    def test_metrics_empty_registry(self, fresh_registry):
        """Test metrics from empty registry."""
        metrics = fresh_registry.get_all_metrics()

        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert metrics["totals"]["total_calls"] == 0
        assert metrics["totals"]["success_rate"] == 0.0
        assert metrics["adapters"] == {}

    def test_metrics_aggregation(self, fresh_registry):
        """Test metrics are properly aggregated."""
        adapter1 = fresh_registry.get_or_create("adapter-1", MockAdapter)
        adapter2 = fresh_registry.get_or_create("adapter-2", MockAdapter)

        # Set custom metrics (using _custom_metrics which get_metrics() returns)
        adapter1._custom_metrics = {
            "total_calls": 100,
            "successful_calls": 90,
            "failed_calls": 10,
            "cache_hits": 50,
            "fallback_uses": 5,
        }
        adapter2._custom_metrics = {
            "total_calls": 200,
            "successful_calls": 180,
            "failed_calls": 20,
            "cache_hits": 100,
            "fallback_uses": 10,
        }

        metrics = fresh_registry.get_all_metrics()
        totals = metrics["totals"]

        assert totals["total_calls"] == 300
        assert totals["successful_calls"] == 270
        assert totals["failed_calls"] == 30
        assert totals["cache_hits"] == 150
        assert totals["fallback_uses"] == 15
        assert totals["success_rate"] == 0.9  # 270/300
        assert totals["cache_hit_rate"] == 0.5  # 150/300

    def test_metrics_includes_per_adapter(self, fresh_registry):
        """Test that metrics include per-adapter breakdown."""
        fresh_registry.get_or_create("adapter-1", MockAdapter)
        fresh_registry.get_or_create("adapter-2", MockAdapter)

        metrics = fresh_registry.get_all_metrics()

        assert "adapter-1" in metrics["adapters"]
        assert "adapter-2" in metrics["adapters"]


class TestCloseAll:
    """Tests for close_all method."""

    async def test_close_all_adapters(self, fresh_registry):
        """Test closing all adapters."""
        adapter1 = fresh_registry.get_or_create("adapter-1", MockAdapter)
        adapter2 = fresh_registry.get_or_create("adapter-2", MockAdapter)

        await fresh_registry.close_all()

        assert adapter1._closed is True
        assert adapter2._closed is True

    async def test_close_adapters_without_close_method(self, fresh_registry):
        """Test closing adapters that don't have close method."""
        # MockAdapterNoClose doesn't have a close method
        fresh_registry.get_or_create("no-close-adapter", MockAdapterNoClose)

        # Should not raise
        await fresh_registry.close_all()

    async def test_close_handles_errors(self, fresh_registry):
        """Test that close handles errors gracefully."""
        adapter = fresh_registry.get_or_create("error-adapter", MockAdapter)

        # Make close raise an exception
        async def failing_close():
            raise RuntimeError("Close failed")

        adapter.close = failing_close

        # Should not raise, just log the error
        await fresh_registry.close_all()


class TestClear:
    """Tests for clear method."""

    def test_clear_removes_all_adapters(self, registry_with_adapters):
        """Test clearing removes all adapters."""
        assert len(registry_with_adapters.list_adapters()) > 0

        registry_with_adapters.clear()

        assert len(registry_with_adapters.list_adapters()) == 0

    def test_clear_empty_registry(self, fresh_registry):
        """Test clearing an empty registry doesn't raise."""
        fresh_registry.clear()

        assert len(fresh_registry.list_adapters()) == 0


class TestGetRegistry:
    """Tests for get_registry helper function."""

    def test_get_registry_returns_singleton(self, fresh_registry):
        """Test get_registry returns the singleton instance."""
        registry = get_registry()

        assert registry is not None
        assert isinstance(registry, AdapterRegistry)


class TestGetAdapter:
    """Tests for get_adapter helper function."""

    def test_get_adapter_returns_existing(self, fresh_registry):
        """Test get_adapter returns an existing adapter by name."""
        # First create an adapter using the registry
        created_adapter = fresh_registry.get_or_create("helper-adapter", MockAdapter)

        # Then get it using get_adapter
        adapter = get_adapter("helper-adapter")

        assert adapter is not None
        assert adapter is created_adapter
        assert isinstance(adapter, MockAdapter)
        assert adapter.name == "helper-adapter"

    def test_get_adapter_returns_none_for_missing(self, fresh_registry):
        """Test get_adapter returns None when adapter doesn't exist."""
        adapter = get_adapter("nonexistent-adapter")

        assert adapter is None


class TestConstitutionalCompliance:
    """Tests for constitutional compliance."""

    @pytest.mark.constitutional
    def test_health_includes_constitutional_hash(self, registry_with_adapters):
        """Test that health reports include constitutional hash."""
        health = registry_with_adapters.get_all_health()

        assert health["constitutional_hash"] == CONSTITUTIONAL_HASH

    @pytest.mark.constitutional
    def test_metrics_includes_constitutional_hash(self, registry_with_adapters):
        """Test that metrics reports include constitutional hash."""
        metrics = registry_with_adapters.get_all_metrics()

        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestConcurrency:
    """Tests for concurrent operations."""

    def test_multiple_creates_same_adapter(self, fresh_registry):
        """Test that concurrent creates return the same adapter."""
        import threading

        adapters = []
        errors = []

        def create_adapter():
            try:
                adapter = fresh_registry.get_or_create("concurrent-adapter", MockAdapter)
                adapters.append(adapter)
            except (RuntimeError, ValueError, TypeError, AssertionError) as e:
                errors.append(e)

        threads = [threading.Thread(target=create_adapter) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # All should be the same instance
        assert all(a is adapters[0] for a in adapters)


class TestEdgeCases:
    """Tests for edge cases."""

    def test_adapter_with_empty_name(self, fresh_registry):
        """Test creating adapter with empty name."""
        adapter = fresh_registry.get_or_create("", MockAdapter)

        assert adapter is not None
        assert "" in fresh_registry.list_adapters()

    def test_health_threshold_boundary(self, fresh_registry):
        """Test health threshold at exactly 80%."""
        # Create 5 adapters, 4 healthy (80%)
        for i in range(5):
            adapter = fresh_registry.get_or_create(f"adapter-{i}", MockAdapter)
            adapter._healthy = i < 4  # First 4 are healthy

        health = fresh_registry.get_all_health()

        assert health["health_score"] == 0.8
        assert health["overall_health"] == "healthy"  # >= 0.8 is healthy
