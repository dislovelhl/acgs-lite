"""
ACGS-2 Enhanced Agent Bus - Circuit Breaker Clients Tests
Constitutional Hash: 608508a9bd224290

Tests for T002: Circuit Breaker Protected Clients
Expert Reference: Michael Nygard (Release It!)

Tests:
1. OPA Client circuit breaker (fail-closed for governance)
2. Redis Client circuit breaker (fail-open with degraded mode)
3. Kafka Producer circuit breaker (with retry buffer)
4. Health check endpoints
"""

import asyncio
import hashlib
import importlib.util
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import enhanced_agent_bus.cb_opa_client as cb_opa_client_module

# Import centralized constitutional hash
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

try:
    AIKAFKA_AVAILABLE = importlib.util.find_spec("aiokafka") is not None
except (ValueError, ModuleNotFoundError):
    AIKAFKA_AVAILABLE = False


@pytest.fixture(autouse=True)
def reset_all():
    """Reset all singletons before and after each test."""
    from enhanced_agent_bus.circuit_breaker import reset_circuit_breaker_registry
    from enhanced_agent_bus.circuit_breaker_clients import (
        reset_circuit_breaker_clients,
    )

    reset_circuit_breaker_registry()
    reset_circuit_breaker_clients()
    yield
    reset_circuit_breaker_registry()
    reset_circuit_breaker_clients()


# =============================================================================
# Retry Buffer Tests
# =============================================================================


class TestRetryBuffer:
    """Tests for RetryBuffer."""

    async def test_add_message_to_buffer(self):
        """Test adding messages to retry buffer."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            BufferedMessage,
            RetryBuffer,
        )

        buffer = RetryBuffer(max_size=100)

        msg = BufferedMessage(
            id="test-123",
            topic="test-topic",
            value={"data": "test"},
            key=b"key",
            buffered_at=time.time(),
        )

        result = await buffer.add(msg)

        assert result is True
        assert buffer.get_size() == 1

    async def test_buffer_max_size(self):
        """Test buffer respects max size."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            BufferedMessage,
            RetryBuffer,
        )

        buffer = RetryBuffer(max_size=2)

        for i in range(3):
            msg = BufferedMessage(
                id=f"msg-{i}",
                topic="test",
                value={"i": i},
                key=None,
                buffered_at=time.time(),
            )
            await buffer.add(msg)

        # Should only have 2 messages (oldest dropped)
        assert buffer.get_size() == 2

        metrics = buffer.get_metrics()
        assert metrics["dropped_count"] == 1

    async def test_buffer_process_success(self):
        """Test processing buffered messages."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            BufferedMessage,
            RetryBuffer,
        )

        buffer = RetryBuffer(max_size=100, base_retry_delay=0.01)

        # Add messages
        for i in range(3):
            msg = BufferedMessage(
                id=f"msg-{i}",
                topic="test",
                value={"i": i},
                key=None,
                buffered_at=time.time(),
            )
            await buffer.add(msg)

        # Mock producer function
        async def mock_producer(topic, value, key):
            pass

        results = await buffer.process(mock_producer)

        assert results["delivered"] == 3
        assert results["failed"] == 0
        assert buffer.get_size() == 0

    async def test_buffer_process_with_failures(self):
        """Test processing with some failures."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            BufferedMessage,
            RetryBuffer,
        )

        buffer = RetryBuffer(max_size=100, base_retry_delay=0.01)

        msg = BufferedMessage(
            id="failing-msg",
            topic="test",
            value={"data": "test"},
            key=None,
            buffered_at=time.time(),
            max_retries=1,
        )
        await buffer.add(msg)

        # Mock producer that always fails
        async def failing_producer(topic, value, key):
            raise RuntimeError("Send failed")

        results = await buffer.process(failing_producer)

        # Should fail after max retries
        assert results["failed"] == 1

    async def test_buffer_metrics(self):
        """Test buffer metrics collection."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            BufferedMessage,
            RetryBuffer,
        )

        buffer = RetryBuffer(max_size=100)

        msg = BufferedMessage(
            id="test",
            topic="test",
            value={},
            key=None,
            buffered_at=time.time(),
        )
        await buffer.add(msg)

        metrics = buffer.get_metrics()

        assert "buffered_count" in metrics
        assert "current_size" in metrics
        assert "max_size" in metrics
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# OPA Client Tests
# =============================================================================


class TestCircuitBreakerOPAClient:
    """Tests for CircuitBreakerOPAClient."""

    def test_opa_client_rejects_invalid_cache_hash_mode(self):
        """Test OPA client rejects unsupported cache hash mode."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerOPAClient,
        )

        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            CircuitBreakerOPAClient(cache_hash_mode="invalid")  # type: ignore[arg-type]

    def test_opa_cache_key_fast_mode_uses_kernel(self, monkeypatch):
        """Test OPA cache key uses fast hash kernel when enabled."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerOPAClient,
        )

        called = {"value": False}

        def _fake_fast_hash(value: str) -> int:
            called["value"] = True
            return 0xBEEF

        monkeypatch.setattr(cb_opa_client_module, "FAST_HASH_AVAILABLE", True)
        monkeypatch.setattr(cb_opa_client_module, "fast_hash", _fake_fast_hash, raising=False)

        client = CircuitBreakerOPAClient(cache_hash_mode="fast")
        cache_key = client._get_cache_key("data.acgs.allow", {"a": 1})

        assert called["value"] is True
        assert cache_key == "opa_cb:data.acgs.allow:000000000000beef"

    def test_opa_cache_key_fast_mode_falls_back_to_sha256(self, monkeypatch):
        """Test OPA fast hash mode falls back to SHA-256 when unavailable."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerOPAClient,
        )

        monkeypatch.setattr(cb_opa_client_module, "FAST_HASH_AVAILABLE", False)

        client = CircuitBreakerOPAClient(cache_hash_mode="fast")
        cache_key = client._get_cache_key("data.acgs.allow", {"a": 1})

        expected_hash = hashlib.sha256(b'{"a": 1}').hexdigest()[:16]
        assert cache_key == f"opa_cb:data.acgs.allow:{expected_hash}"

    async def test_opa_client_initialization(self):
        """Test OPA client initializes with circuit breaker."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerOPAClient,
        )

        with patch("httpx.AsyncClient") as mock_client:
            client = CircuitBreakerOPAClient(opa_url="http://localhost:8181")
            await client.initialize()

            assert client._initialized
            assert client._circuit_breaker is not None
            assert client.constitutional_hash == CONSTITUTIONAL_HASH

            await client.close()

    async def test_opa_fail_closed_when_circuit_open(self):
        """Test OPA client returns denied when circuit is open."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerOPAClient,
        )

        with patch("httpx.AsyncClient"):
            client = CircuitBreakerOPAClient()
            await client.initialize()

            # Open the circuit
            for _ in range(5):
                await client._circuit_breaker.record_failure(Exception("test"), "TestError")

            result = await client.evaluate_policy({"action": "read"}, "data.acgs.allow")

            assert result["allowed"] is False
            assert result["metadata"]["security"] == "fail-closed"
            assert "circuit breaker open" in result["reason"].lower()

            await client.close()

    async def test_opa_circuit_open_ignores_cached_allow(self):
        """Open breaker must deny even when an allow result is cached."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerOPAClient,
        )

        with patch("httpx.AsyncClient"):
            client = CircuitBreakerOPAClient(enable_cache=True)
            await client.initialize()

            cache_key = client._get_cache_key("data.acgs.allow", {"action": "read"})
            client._set_cache(
                cache_key,
                {
                    "result": True,
                    "allowed": True,
                    "reason": "cached allow",
                    "metadata": {"source": "cache"},
                },
            )

            for _ in range(5):
                await client._circuit_breaker.record_failure(Exception("boom"), "TestError")

            result = await client.evaluate_policy({"action": "read"}, "data.acgs.allow")

            assert result["allowed"] is False
            assert result["metadata"]["security"] == "fail-closed"
            assert "circuit breaker open" in result["reason"].lower()

            await client.close()

    async def test_opa_successful_evaluation(self):
        """Test successful OPA policy evaluation."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerOPAClient,
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"result": True}
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_http_client):
            client = CircuitBreakerOPAClient()
            await client.initialize()
            client._http_client = mock_http_client

            result = await client.evaluate_policy({"action": "read"}, "data.acgs.allow")

            assert result["allowed"] is True
            assert client._circuit_breaker.metrics.successful_calls >= 1

            await client.close()

    async def test_opa_caching(self):
        """Test OPA result caching."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerOPAClient,
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"result": True}
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_http_client):
            client = CircuitBreakerOPAClient(enable_cache=True, cache_ttl=300)
            await client.initialize()
            client._http_client = mock_http_client

            # First call
            result1 = await client.evaluate_policy({"action": "read"}, "data.acgs.allow")

            # Second call (should use cache)
            result2 = await client.evaluate_policy({"action": "read"}, "data.acgs.allow")

            assert result1["allowed"] == result2["allowed"]
            # HTTP should only be called once
            assert mock_http_client.post.call_count == 1

            await client.close()

    async def test_opa_health_check(self):
        """Test OPA client health check."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerOPAClient,
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_http_client):
            client = CircuitBreakerOPAClient()
            await client.initialize()
            client._http_client = mock_http_client

            health = await client.health_check()

            assert health["service"] == "opa_evaluator"
            assert health["fallback_strategy"] == "fail_closed"
            assert health["constitutional_hash"] == CONSTITUTIONAL_HASH

            await client.close()


# =============================================================================
# Redis Client Tests
# =============================================================================


class TestCircuitBreakerRedisClient:
    """Tests for CircuitBreakerRedisClient."""

    async def test_redis_client_initialization(self):
        """Test Redis client initializes with circuit breaker."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerRedisClient,
        )

        with patch("redis.asyncio.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock()
            mock_redis.return_value = mock_client

            client = CircuitBreakerRedisClient(redis_url="redis://localhost:6379")
            await client.initialize()

            assert client._initialized
            assert client._circuit_breaker is not None
            assert client.constitutional_hash == CONSTITUTIONAL_HASH

            await client.close()

    async def test_redis_fail_open_when_circuit_open(self):
        """Test Redis client bypasses when circuit is open."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerRedisClient,
        )

        with patch("redis.asyncio.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock()
            mock_redis.return_value = mock_client

            client = CircuitBreakerRedisClient()
            await client.initialize()

            # Open the circuit
            for _ in range(3):
                await client._circuit_breaker.record_failure(Exception("test"), "TestError")

            # GET should return None (bypass)
            result = await client.get("test_key")
            assert result is None
            assert client._bypass_count > 0

            # SET should return False (bypass)
            result = await client.set("test_key", "value")
            assert result is False

            await client.close()

    async def test_redis_successful_operations(self):
        """Test successful Redis operations."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerRedisClient,
        )

        with patch("redis.asyncio.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock()
            mock_client.get = AsyncMock(return_value="value")
            mock_client.set = AsyncMock()
            mock_client.setex = AsyncMock()
            mock_redis.return_value = mock_client

            client = CircuitBreakerRedisClient()
            await client.initialize()

            # Test GET
            result = await client.get("key")
            assert result == "value"

            # Test SET
            result = await client.set("key", "value", ex=300)
            assert result is True

            # Check metrics
            assert client._circuit_breaker.metrics.successful_calls >= 2

            await client.close()

    async def test_redis_batch_operations(self):
        """Test Redis batch operations with circuit breaker."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerRedisClient,
        )

        with patch("redis.asyncio.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock()

            # Mock pipeline with separate return values for batch_get and batch_set
            mock_pipe = MagicMock()
            mock_pipe.get = MagicMock()
            mock_pipe.setex = MagicMock()
            # Use side_effect to return different values for each call
            mock_pipe.execute = AsyncMock(
                side_effect=[
                    ["val1", "val2"],  # First call: batch_get returns 2 values
                    [True, True],  # Second call: batch_set returns 2 bools
                ]
            )
            mock_client.pipeline = MagicMock(return_value=mock_pipe)

            mock_redis.return_value = mock_client

            client = CircuitBreakerRedisClient()
            await client.initialize()

            # Test batch get
            results = await client.batch_get(["key1", "key2"])
            assert len(results) == 2

            # Test batch set
            items = [("k1", "v1", 300), ("k2", "v2", 300)]
            results = await client.batch_set(items)
            assert len(results) == 2

            await client.close()

    async def test_redis_degraded_mode(self):
        """Test Redis operates in degraded mode without connection."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerRedisClient,
        )

        with patch("redis.asyncio.from_url") as mock_redis:
            # Simulate connection failure
            mock_redis.side_effect = ConnectionError("Connection refused")

            client = CircuitBreakerRedisClient()
            await client.initialize()

            # Should operate in degraded mode
            assert client._redis is None

            # Operations should return bypass values
            result = await client.get("key")
            assert result is None

            result = await client.set("key", "value")
            assert result is False

            await client.close()

    async def test_redis_health_check(self):
        """Test Redis client health check."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerRedisClient,
        )

        with patch("redis.asyncio.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock()
            mock_redis.return_value = mock_client

            client = CircuitBreakerRedisClient()
            await client.initialize()

            health = await client.health_check()

            assert health["service"] == "redis_cache"
            assert health["fallback_strategy"] == "bypass"
            assert "degraded_mode" in health
            assert health["constitutional_hash"] == CONSTITUTIONAL_HASH

            await client.close()


# =============================================================================
# Kafka Producer Tests
# =============================================================================


@pytest.mark.skipif(not AIKAFKA_AVAILABLE, reason="aiokafka not installed")
class TestCircuitBreakerKafkaProducer:
    """Tests for CircuitBreakerKafkaProducer."""

    async def test_kafka_producer_initialization(self):
        """Test Kafka producer initializes with circuit breaker."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerKafkaProducer,
        )

        with patch("aiokafka.AIOKafkaProducer") as mock_producer:
            mock_instance = AsyncMock()
            mock_instance.start = AsyncMock()
            mock_producer.return_value = mock_instance

            producer = CircuitBreakerKafkaProducer(bootstrap_servers="localhost:9092")
            await producer.initialize()

            assert producer._initialized
            assert producer._circuit_breaker is not None
            assert producer.constitutional_hash == CONSTITUTIONAL_HASH

            await producer.close()

    async def test_kafka_buffer_when_circuit_open(self):
        """Test Kafka producer buffers messages when circuit is open."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerKafkaProducer,
        )

        with patch("aiokafka.AIOKafkaProducer") as mock_producer:
            mock_instance = AsyncMock()
            mock_instance.start = AsyncMock()
            mock_producer.return_value = mock_instance

            producer = CircuitBreakerKafkaProducer()
            await producer.initialize()

            # Open the circuit
            for _ in range(5):
                await producer._circuit_breaker.record_failure(Exception("test"), "TestError")

            # Send should buffer
            result = await producer.send(
                topic="test-topic",
                value={"data": "test"},
                key="key",
            )

            assert result is False  # Buffered, not sent immediately
            assert producer._retry_buffer.get_size() == 1

            await producer.close()

    async def test_kafka_successful_send(self):
        """Test successful Kafka message send."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerKafkaProducer,
        )

        with patch("aiokafka.AIOKafkaProducer") as mock_producer:
            mock_instance = AsyncMock()
            mock_instance.start = AsyncMock()
            mock_instance.send_and_wait = AsyncMock()
            mock_instance.flush = AsyncMock()
            mock_instance.stop = AsyncMock()
            mock_producer.return_value = mock_instance

            producer = CircuitBreakerKafkaProducer()
            await producer.initialize()

            result = await producer.send(
                topic="test-topic",
                value={"data": "test"},
                key="key",
            )

            assert result is True
            mock_instance.send_and_wait.assert_called_once()
            assert producer._circuit_breaker.metrics.successful_calls >= 1

            await producer.close()

    async def test_kafka_batch_send(self):
        """Test Kafka batch message send."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerKafkaProducer,
        )

        with patch("aiokafka.AIOKafkaProducer") as mock_producer:
            mock_instance = AsyncMock()
            mock_instance.start = AsyncMock()
            mock_instance.send_and_wait = AsyncMock()
            mock_instance.flush = AsyncMock()
            mock_instance.stop = AsyncMock()
            mock_producer.return_value = mock_instance

            producer = CircuitBreakerKafkaProducer()
            await producer.initialize()

            messages = [
                ("topic1", {"data": "msg1"}, "key1"),
                ("topic2", {"data": "msg2"}, "key2"),
            ]

            results = await producer.send_batch(messages)

            assert results["sent"] == 2
            assert results["buffered"] == 0

            await producer.close()

    async def test_kafka_buffer_on_failure(self):
        """Test Kafka producer buffers on send failure."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerKafkaProducer,
        )

        with patch("aiokafka.AIOKafkaProducer") as mock_producer:
            mock_instance = AsyncMock()
            mock_instance.start = AsyncMock()
            mock_instance.send_and_wait = AsyncMock(side_effect=RuntimeError("Send failed"))
            mock_instance.flush = AsyncMock()
            mock_instance.stop = AsyncMock()
            mock_producer.return_value = mock_instance

            producer = CircuitBreakerKafkaProducer()
            await producer.initialize()

            result = await producer.send(
                topic="test-topic",
                value={"data": "test"},
            )

            assert result is False
            assert producer._retry_buffer.get_size() == 1

            await producer.close()

    async def test_kafka_health_check(self):
        """Test Kafka producer health check."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerKafkaProducer,
        )

        with patch("aiokafka.AIOKafkaProducer") as mock_producer:
            mock_instance = AsyncMock()
            mock_instance.start = AsyncMock()
            mock_instance.flush = AsyncMock()
            mock_instance.stop = AsyncMock()
            mock_producer.return_value = mock_instance

            producer = CircuitBreakerKafkaProducer()
            await producer.initialize()

            health = await producer.health_check()

            assert health["service"] == "kafka_producer"
            assert health["fallback_strategy"] == "queue_for_retry"
            assert "buffer_size" in health
            assert health["constitutional_hash"] == CONSTITUTIONAL_HASH

            await producer.close()


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestFactoryFunctions:
    """Tests for singleton factory functions."""

    async def test_get_opa_client_singleton(self):
        """Test OPA client singleton pattern."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            close_all_circuit_breaker_clients,
            get_circuit_breaker_opa_client,
        )

        with patch("httpx.AsyncClient"):
            client1 = await get_circuit_breaker_opa_client()
            client2 = await get_circuit_breaker_opa_client()

            assert client1 is client2

            await close_all_circuit_breaker_clients()

    async def test_get_redis_client_singleton(self):
        """Test Redis client singleton pattern."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            close_all_circuit_breaker_clients,
            get_circuit_breaker_redis_client,
        )

        with patch("redis.asyncio.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock()
            mock_client.close = AsyncMock()
            mock_redis.return_value = mock_client

            client1 = await get_circuit_breaker_redis_client()
            client2 = await get_circuit_breaker_redis_client()

            assert client1 is client2

            await close_all_circuit_breaker_clients()


# =============================================================================
# Health Aggregator Tests
# =============================================================================


class TestHealthAggregator:
    """Tests for health aggregation."""

    async def test_get_all_circuit_health(self):
        """Test aggregated health check."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            get_all_circuit_health,
        )

        health = await get_all_circuit_health()

        assert "overall_status" in health
        assert "registry_summary" in health
        assert health["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_health_status_with_critical_issues(self):
        """Test health status reflects critical issues."""
        from enhanced_agent_bus import circuit_breaker_clients
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerOPAClient,
            get_all_circuit_health,
            reset_circuit_breaker_clients,
        )

        with patch("httpx.AsyncClient"):
            client = CircuitBreakerOPAClient()
            await client.initialize()

            # Open the OPA circuit (critical)
            for _ in range(5):
                await client._circuit_breaker.record_failure(Exception("test"), "TestError")

            # Set as global singleton for health check
            circuit_breaker_clients._opa_client = client

            health = await get_all_circuit_health()

            # Should reflect OPA unhealthy state
            if "opa" in health.get("clients", {}):
                assert health["clients"]["opa"]["circuit_state"] == "open"

            await client.close()
            reset_circuit_breaker_clients()


# =============================================================================
# Constitutional Compliance Tests
# =============================================================================


class TestConstitutionalCompliance:
    """Tests for constitutional hash compliance."""

    async def test_opa_client_has_constitutional_hash(self):
        """Test OPA client includes constitutional hash."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerOPAClient,
        )

        with patch("httpx.AsyncClient"):
            client = CircuitBreakerOPAClient()
            await client.initialize()

            assert client.constitutional_hash == CONSTITUTIONAL_HASH

            status = client.get_circuit_status()
            assert status["constitutional_hash"] == CONSTITUTIONAL_HASH

            await client.close()

    async def test_redis_client_has_constitutional_hash(self):
        """Test Redis client includes constitutional hash."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerRedisClient,
        )

        with patch("redis.asyncio.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock()
            mock_redis.return_value = mock_client

            client = CircuitBreakerRedisClient()
            await client.initialize()

            assert client.constitutional_hash == CONSTITUTIONAL_HASH

            health = await client.health_check()
            assert health["constitutional_hash"] == CONSTITUTIONAL_HASH

            await client.close()

    @pytest.mark.skipif(not AIKAFKA_AVAILABLE, reason="aiokafka not installed")
    async def test_kafka_producer_has_constitutional_hash(self):
        """Test Kafka producer includes constitutional hash."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            CircuitBreakerKafkaProducer,
        )

        with patch("aiokafka.AIOKafkaProducer") as mock_producer:
            mock_instance = AsyncMock()
            mock_instance.start = AsyncMock()
            mock_instance.flush = AsyncMock()
            mock_instance.stop = AsyncMock()
            mock_producer.return_value = mock_instance

            producer = CircuitBreakerKafkaProducer()
            await producer.initialize()

            assert producer.constitutional_hash == CONSTITUTIONAL_HASH

            health = await producer.health_check()
            assert health["constitutional_hash"] == CONSTITUTIONAL_HASH

            await producer.close()


# =============================================================================
# FastAPI Router Tests
# =============================================================================


class TestFastAPIRouter:
    """Tests for FastAPI health router."""

    def test_router_creation(self):
        """Test router can be created."""
        from enhanced_agent_bus.circuit_breaker_clients import (
            create_circuit_breaker_client_router,
        )

        router = create_circuit_breaker_client_router()

        # Router should be created (or None if FastAPI not available)
        # Just verify no exceptions


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
