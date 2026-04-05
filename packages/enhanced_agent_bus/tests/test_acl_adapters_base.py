"""
ACGS-2 ACL Adapter Base Classes Tests
Constitutional Hash: 608508a9bd224290

Tests for ACL adapter exceptions, configuration, circuit breaker,
rate limiter, and abstract base class.
"""

import pytest

pytest.importorskip("acl_adapters.base")


import asyncio
import time

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

try:
    from acl_adapters.base import (
        CONSTITUTIONAL_HASH,
        ACLAdapter,
        AdapterCircuitOpenError,
        AdapterConfig,
        AdapterResult,
        AdapterState,
        AdapterTimeoutError,
        RateLimitExceededError,
        SimpleCircuitBreaker,
        TokenBucketRateLimiter,
    )
except ImportError:
    from ..acl_adapters.base import (
        CONSTITUTIONAL_HASH,
        ACLAdapter,
        AdapterCircuitOpenError,
        AdapterConfig,
        AdapterResult,
        AdapterState,
        AdapterTimeoutError,
        RateLimitExceededError,
        SimpleCircuitBreaker,
        TokenBucketRateLimiter,
    )


class TestAdapterState:
    """Tests for AdapterState enum."""

    def test_closed_state(self):
        """CLOSED state represents normal operation."""
        assert AdapterState.CLOSED.value == "closed"

    def test_open_state(self):
        """OPEN state rejects calls."""
        assert AdapterState.OPEN.value == "open"

    def test_half_open_state(self):
        """HALF_OPEN state tests recovery."""
        assert AdapterState.HALF_OPEN.value == "half_open"


class TestAdapterTimeoutError:
    """Tests for AdapterTimeoutError exception."""

    def test_error_creation(self):
        """Error initializes with correct attributes."""
        error = AdapterTimeoutError("test_adapter", 5000)

        assert error.adapter_name == "test_adapter"
        assert error.timeout_ms == 5000
        assert error.constitutional_hash == CONSTITUTIONAL_HASH

    def test_error_message(self):
        """Error message contains relevant information."""
        error = AdapterTimeoutError("my_adapter", 3000)
        message = str(error)

        assert "my_adapter" in message
        assert "3000ms" in message
        assert CONSTITUTIONAL_HASH in message

    def test_to_dict(self):
        """Error serializes to dictionary."""
        error = AdapterTimeoutError("adapter1", 1000)
        data = error.to_dict()

        assert data["error"] == "AdapterTimeoutError"
        assert data["adapter"] == "adapter1"
        assert data["timeout_ms"] == 1000
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestAdapterCircuitOpenError:
    """Tests for AdapterCircuitOpenError exception."""

    def test_error_creation(self):
        """Error initializes with correct attributes."""
        error = AdapterCircuitOpenError("test_adapter", 30.0)

        assert error.adapter_name == "test_adapter"
        assert error.recovery_time_s == 30.0
        assert error.constitutional_hash == CONSTITUTIONAL_HASH

    def test_error_message(self):
        """Error message contains relevant information."""
        error = AdapterCircuitOpenError("my_adapter", 15.5)
        message = str(error)

        assert "my_adapter" in message
        assert "circuit is open" in message
        assert CONSTITUTIONAL_HASH in message

    def test_to_dict(self):
        """Error serializes to dictionary."""
        error = AdapterCircuitOpenError("adapter1", 25.0)
        data = error.to_dict()

        assert data["error"] == "AdapterCircuitOpenError"
        assert data["adapter"] == "adapter1"
        assert data["recovery_time_s"] == 25.0
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestRateLimitExceededError:
    """Tests for RateLimitExceededError exception."""

    def test_error_creation(self):
        """Error initializes with correct attributes."""
        error = RateLimitExceededError("test_adapter", 100.0)

        assert error.adapter_name == "test_adapter"
        assert error.limit_per_second == 100.0
        assert error.constitutional_hash == CONSTITUTIONAL_HASH

    def test_error_message(self):
        """Error message contains relevant information."""
        error = RateLimitExceededError("my_adapter", 50.0)
        message = str(error)

        assert "my_adapter" in message
        assert "rate limit exceeded" in message
        assert CONSTITUTIONAL_HASH in message

    def test_to_dict(self):
        """Error serializes to dictionary."""
        error = RateLimitExceededError("adapter1", 75.0)
        data = error.to_dict()

        assert data["error"] == "RateLimitExceededError"
        assert data["adapter"] == "adapter1"
        assert data["limit_per_second"] == 75.0
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestAdapterConfig:
    """Tests for AdapterConfig dataclass."""

    def test_default_values(self):
        """Config has sensible defaults."""
        config = AdapterConfig()

        assert config.timeout_ms == 5000
        assert config.connect_timeout_ms == 1000
        assert config.max_retries == 3
        assert config.retry_base_delay_ms == 100
        assert config.retry_max_delay_ms == 5000
        assert config.retry_exponential_base == 2.0
        assert config.circuit_failure_threshold == 5
        assert config.circuit_recovery_timeout_s == 30.0
        assert config.circuit_half_open_max_calls == 3
        assert config.rate_limit_per_second == 100.0
        assert config.rate_limit_burst == 10
        assert config.cache_enabled is True
        assert config.cache_ttl_s == 300
        assert config.fallback_enabled is True

    def test_custom_values(self):
        """Config accepts custom values."""
        config = AdapterConfig(
            timeout_ms=10000,
            max_retries=5,
            circuit_failure_threshold=10,
            rate_limit_per_second=50.0,
        )

        assert config.timeout_ms == 10000
        assert config.max_retries == 5
        assert config.circuit_failure_threshold == 10
        assert config.rate_limit_per_second == 50.0


class TestAdapterResult:
    """Tests for AdapterResult dataclass."""

    def test_success_result(self):
        """Success result has correct attributes."""
        result = AdapterResult(success=True, data="test_data", latency_ms=5.5)

        assert result.success is True
        assert result.data == "test_data"
        assert result.latency_ms == 5.5
        assert result.error is None
        assert result.from_cache is False
        assert result.from_fallback is False
        assert result.retry_count == 0
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_failure_result(self):
        """Failure result has error attribute."""
        error = ValueError("test error")
        result = AdapterResult(success=False, error=error)

        assert result.success is False
        assert result.data is None
        assert result.error == error

    def test_cached_result(self):
        """Cached result has from_cache flag."""
        result = AdapterResult(success=True, data="cached", from_cache=True)

        assert result.from_cache is True

    def test_fallback_result(self):
        """Fallback result has from_fallback flag."""
        result = AdapterResult(success=True, data="fallback", from_fallback=True)

        assert result.from_fallback is True

    def test_to_dict_success(self):
        """Success result serializes correctly."""
        result = AdapterResult(
            success=True,
            data="data",
            latency_ms=10.5,
            from_cache=True,
            retry_count=1,
        )
        data = result.to_dict()

        assert data["success"] is True
        assert data["latency_ms"] == 10.5
        assert data["from_cache"] is True
        assert data["retry_count"] == 1
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "error" not in data

    def test_to_dict_with_error(self):
        """Error result serializes correctly."""
        error = AdapterTimeoutError("adapter", 5000)
        result = AdapterResult(success=False, error=error)
        data = result.to_dict()

        assert data["success"] is False
        assert "error" in data
        assert "error_details" in data
        assert data["error_details"]["error"] == "AdapterTimeoutError"


class TestSimpleCircuitBreaker:
    """Tests for SimpleCircuitBreaker."""

    def test_initial_state_closed(self):
        """Circuit breaker starts in CLOSED state."""
        cb = SimpleCircuitBreaker()

        assert cb.state == AdapterState.CLOSED
        assert cb.time_until_recovery == 0.0

    def test_custom_thresholds(self):
        """Circuit breaker accepts custom thresholds."""
        cb = SimpleCircuitBreaker(
            failure_threshold=10,
            recovery_timeout_s=60.0,
            half_open_max_calls=5,
        )

        assert cb.failure_threshold == 10
        assert cb.recovery_timeout_s == 60.0
        assert cb.half_open_max_calls == 5

    def test_record_success_in_closed(self):
        """Recording success in CLOSED state decrements failure count."""
        cb = SimpleCircuitBreaker()
        cb._failure_count = 3

        cb.record_success()

        assert cb._failure_count == 2
        assert cb.state == AdapterState.CLOSED

    def test_opens_after_threshold_failures(self):
        """Circuit opens after failure threshold is reached."""
        cb = SimpleCircuitBreaker(failure_threshold=3)

        for _ in range(3):
            cb.record_failure()

        assert cb.state == AdapterState.OPEN

    def test_stays_closed_below_threshold(self):
        """Circuit stays closed below failure threshold."""
        cb = SimpleCircuitBreaker(failure_threshold=5)

        for _ in range(4):
            cb.record_failure()

        assert cb.state == AdapterState.CLOSED
        assert cb._failure_count == 4

    def test_time_until_recovery(self):
        """time_until_recovery calculates correctly."""
        cb = SimpleCircuitBreaker(
            failure_threshold=1,
            recovery_timeout_s=10.0,
        )

        cb.record_failure()  # Opens circuit
        assert cb.state == AdapterState.OPEN

        recovery_time = cb.time_until_recovery
        assert 9.0 < recovery_time <= 10.0

    def test_transitions_to_half_open(self):
        """Circuit transitions to HALF_OPEN after recovery timeout."""
        cb = SimpleCircuitBreaker(
            failure_threshold=1,
            recovery_timeout_s=0.01,  # 10ms for fast test
        )

        cb.record_failure()  # Opens circuit
        assert cb.state == AdapterState.OPEN

        time.sleep(0.02)  # Wait for recovery

        assert cb.state == AdapterState.HALF_OPEN

    def test_half_open_to_closed_on_success(self):
        """Circuit returns to CLOSED after successes in HALF_OPEN."""
        cb = SimpleCircuitBreaker(
            failure_threshold=1,
            recovery_timeout_s=0.01,
            half_open_max_calls=1,
        )

        cb.record_failure()  # Opens circuit
        time.sleep(0.02)  # Wait for HALF_OPEN

        assert cb.state == AdapterState.HALF_OPEN

        cb.record_success()

        assert cb.state == AdapterState.CLOSED

    def test_half_open_to_open_on_failure(self):
        """Circuit returns to OPEN on failure in HALF_OPEN."""
        cb = SimpleCircuitBreaker(
            failure_threshold=1,
            recovery_timeout_s=0.01,
        )

        cb.record_failure()  # Opens circuit
        time.sleep(0.02)  # Wait for HALF_OPEN

        assert cb.state == AdapterState.HALF_OPEN

        cb.record_failure()

        assert cb.state == AdapterState.OPEN

    def test_reset(self):
        """reset() returns circuit to initial state."""
        cb = SimpleCircuitBreaker(failure_threshold=1)

        cb.record_failure()  # Opens circuit
        assert cb.state == AdapterState.OPEN

        cb.reset()

        assert cb.state == AdapterState.CLOSED
        assert cb._failure_count == 0
        assert cb._success_count == 0
        assert cb._last_failure_time is None


class TestTokenBucketRateLimiter:
    """Tests for TokenBucketRateLimiter."""

    async def test_initial_burst(self):
        """Rate limiter allows burst of requests initially."""
        limiter = TokenBucketRateLimiter(rate_per_second=10.0, burst=5)

        # Should allow burst of 5 requests
        for _ in range(5):
            assert await limiter.acquire() is True

    async def test_rate_limited_after_burst(self):
        """Rate limiter rejects after burst exhausted."""
        limiter = TokenBucketRateLimiter(rate_per_second=10.0, burst=3)

        # Exhaust burst
        for _ in range(3):
            await limiter.acquire()

        # Next request should be rejected
        assert await limiter.acquire() is False

    async def test_tokens_refill(self):
        """Tokens refill over time."""
        limiter = TokenBucketRateLimiter(rate_per_second=100.0, burst=1)

        # Use initial token
        assert await limiter.acquire() is True
        assert await limiter.acquire() is False

        # Wait for refill (10ms = 1 token at 100/s)
        await asyncio.sleep(0.015)

        assert await limiter.acquire() is True


class ConcreteAdapter(ACLAdapter[str, str]):
    """Concrete adapter implementation for testing."""

    def __init__(
        self,
        name: str,
        config: AdapterConfig = None,
        execute_fn=None,
        validate_fn=None,
        fallback_response=None,
    ):
        super().__init__(name, config)
        self._execute_fn = execute_fn or (lambda r: f"response:{r}")
        self._validate_fn = validate_fn or (lambda r: True)
        self._fallback_response = fallback_response

    async def _execute(self, request: str) -> str:
        if callable(self._execute_fn):
            result = self._execute_fn(request)
            if asyncio.iscoroutine(result):
                return await result
            return result
        return self._execute_fn

    def _validate_response(self, response: str) -> bool:
        return self._validate_fn(response)

    def _get_cache_key(self, request: str) -> str:
        return f"cache:{request}"

    def _get_fallback_response(self, request: str) -> str | None:
        return self._fallback_response


class TestACLAdapter:
    """Tests for ACLAdapter abstract base class."""

    async def test_successful_call(self):
        """Successful call returns result."""
        adapter = ConcreteAdapter("test")

        result = await adapter.call("request1")

        assert result.success is True
        assert result.data == "response:request1"
        assert result.from_cache is False
        assert result.from_fallback is False

    async def test_caching(self):
        """Repeated calls use cache."""
        adapter = ConcreteAdapter("test")

        # First call
        result1 = await adapter.call("request1")
        assert result1.from_cache is False

        # Second call should be cached
        result2 = await adapter.call("request1")
        assert result2.success is True
        assert result2.from_cache is True
        assert result2.data == result1.data

    async def test_cache_disabled(self):
        """Caching can be disabled."""
        config = AdapterConfig(cache_enabled=False)
        adapter = ConcreteAdapter("test", config=config)

        await adapter.call("request1")
        result2 = await adapter.call("request1")

        assert result2.from_cache is False

    async def test_timeout_error(self):
        """Timeout errors are handled correctly."""

        async def slow_execute(r):
            await asyncio.sleep(10)  # Much longer than timeout
            return f"response:{r}"

        config = AdapterConfig(timeout_ms=10, max_retries=0)
        adapter = ConcreteAdapter("test", config=config, execute_fn=slow_execute)

        result = await adapter.call("request1")

        assert result.success is False
        assert isinstance(result.error, AdapterTimeoutError)

    async def test_retry_on_failure(self):
        """Adapter retries on failure."""
        call_count = 0

        def failing_then_success(r):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("temporary failure")
            return f"response:{r}"

        config = AdapterConfig(max_retries=3, retry_base_delay_ms=1)
        adapter = ConcreteAdapter("test", config=config, execute_fn=failing_then_success)

        result = await adapter.call("request1")

        assert result.success is True
        assert result.retry_count == 2  # 0-indexed, so 2 means 3rd attempt
        assert call_count == 3

    async def test_fallback_on_circuit_open(self):
        """Fallback is used when circuit is open."""
        adapter = ConcreteAdapter(
            "test",
            config=AdapterConfig(circuit_failure_threshold=1, max_retries=0),
            execute_fn=lambda r: (_ for _ in ()).throw(ValueError("fail")),
            fallback_response="fallback_value",
        )

        # First call fails and opens circuit
        await adapter.call("request1")
        assert adapter.circuit_breaker.state == AdapterState.OPEN

        # Second call uses fallback
        result = await adapter.call("request2")

        assert result.success is True
        assert result.data == "fallback_value"
        assert result.from_fallback is True

    async def test_circuit_open_no_fallback(self):
        """Circuit open without fallback returns error."""
        adapter = ConcreteAdapter(
            "test",
            config=AdapterConfig(
                circuit_failure_threshold=1,
                max_retries=0,
                fallback_enabled=False,
            ),
            execute_fn=lambda r: (_ for _ in ()).throw(ValueError("fail")),
        )

        # First call fails and opens circuit
        await adapter.call("request1")

        # Second call returns circuit open error
        result = await adapter.call("request2")

        assert result.success is False
        assert isinstance(result.error, AdapterCircuitOpenError)

    async def test_invalid_response_handling(self):
        """Invalid responses trigger circuit breaker."""
        adapter = ConcreteAdapter(
            "test",
            config=AdapterConfig(circuit_failure_threshold=2, max_retries=0),
            validate_fn=lambda r: False,  # Always invalid
        )

        await adapter.call("request1")
        result = await adapter.call("request2")

        assert adapter.circuit_breaker.state == AdapterState.OPEN

    async def test_get_metrics(self):
        """get_metrics returns adapter statistics."""
        adapter = ConcreteAdapter("test")

        await adapter.call("request1")
        await adapter.call("request1")  # Cache hit

        metrics = adapter.get_metrics()

        assert metrics["adapter_name"] == "test"
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert metrics["total_calls"] == 2
        assert metrics["successful_calls"] == 1
        assert metrics["cache_hits"] == 1
        assert metrics["circuit_state"] == "closed"

    async def test_get_health(self):
        """get_health returns health status."""
        adapter = ConcreteAdapter("test")

        health = adapter.get_health()

        assert health["adapter_name"] == "test"
        assert health["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert health["healthy"] is True
        assert health["state"] == "closed"
        assert "timestamp" in health

    async def test_clear_cache(self):
        """clear_cache removes cached entries."""
        adapter = ConcreteAdapter("test")

        await adapter.call("request1")
        adapter.clear_cache()

        result = await adapter.call("request1")
        assert result.from_cache is False

    async def test_reset_circuit_breaker(self):
        """reset_circuit_breaker restores closed state."""
        adapter = ConcreteAdapter(
            "test",
            config=AdapterConfig(circuit_failure_threshold=1, max_retries=0),
            execute_fn=lambda r: (_ for _ in ()).throw(ValueError("fail")),
        )

        await adapter.call("request1")
        assert adapter.circuit_breaker.state == AdapterState.OPEN

        adapter.reset_circuit_breaker()

        assert adapter.circuit_breaker.state == AdapterState.CLOSED


class TestConstitutionalHash:
    """Tests for constitutional hash in ACL adapter module."""

    def test_hash_value(self):
        """CONSTITUTIONAL_HASH has correct value."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_exceptions_include_hash(self):
        """All exceptions include constitutional hash."""
        timeout_err = AdapterTimeoutError("adapter", 1000)
        circuit_err = AdapterCircuitOpenError("adapter", 10.0)
        rate_err = RateLimitExceededError("adapter", 50.0)

        assert timeout_err.constitutional_hash == CONSTITUTIONAL_HASH
        assert circuit_err.constitutional_hash == CONSTITUTIONAL_HASH
        assert rate_err.constitutional_hash == CONSTITUTIONAL_HASH

    def test_result_includes_hash(self):
        """AdapterResult includes constitutional hash."""
        result = AdapterResult(success=True)
        assert result.constitutional_hash == CONSTITUTIONAL_HASH
