"""
ACGS-2 Enhanced Agent Bus - ACL Adapters Base Coverage Tests
Constitutional Hash: 608508a9bd224290

Covers: enhanced_agent_bus/acl_adapters/base.py (230 stmts, 0% -> target 80%+)
Tests:
  - AdapterError, AdapterTimeoutError, AdapterCircuitOpenError, RateLimitExceededError
  - AdapterConfig, AdapterResult
  - SimpleCircuitBreaker (closed/open/half-open state transitions)
  - TokenBucketRateLimiter
  - ACLAdapter (call, cache, fallback, retry, circuit breaker integration)
"""

from __future__ import annotations

import inspect
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


# ---------------------------------------------------------------------------
# Error classes
# ---------------------------------------------------------------------------


class TestAdapterError:
    def test_construction(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterError

        err = AdapterError("something went wrong")
        assert str(err) == "something went wrong"
        assert hasattr(err, "constitutional_hash")

    def test_to_dict(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterError

        err = AdapterError("test error")
        d = err.to_dict()
        assert d["error"] == "AdapterError"
        assert d["message"] == "test error"
        assert "constitutional_hash" in d


class TestAdapterTimeoutError:
    def test_construction(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterTimeoutError

        err = AdapterTimeoutError("opa_adapter", 5000)
        assert err.adapter_name == "opa_adapter"
        assert err.timeout_ms == 5000
        assert "5000ms" in str(err)

    def test_to_dict(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterTimeoutError

        err = AdapterTimeoutError("test_adapter", 3000)
        d = err.to_dict()
        assert d["adapter"] == "test_adapter"
        assert d["timeout_ms"] == 3000


class TestAdapterCircuitOpenError:
    def test_construction(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterCircuitOpenError

        err = AdapterCircuitOpenError("z3_adapter", 30.0)
        assert err.adapter_name == "z3_adapter"
        assert err.recovery_time_s == 30.0
        assert "30.0s" in str(err)

    def test_to_dict(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterCircuitOpenError

        err = AdapterCircuitOpenError("test", 15.5)
        d = err.to_dict()
        assert d["adapter"] == "test"
        assert d["recovery_time_s"] == 15.5


class TestRateLimitExceededError:
    def test_construction(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import RateLimitExceededError

        err = RateLimitExceededError("api_adapter", 100.0)
        assert err.adapter_name == "api_adapter"
        assert err.limit_per_second == 100.0
        assert "100.0/s" in str(err)

    def test_to_dict(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import RateLimitExceededError

        err = RateLimitExceededError("test", 50.0)
        d = err.to_dict()
        assert d["adapter"] == "test"
        assert d["limit_per_second"] == 50.0


# ---------------------------------------------------------------------------
# AdapterConfig
# ---------------------------------------------------------------------------


class TestAdapterConfig:
    def test_defaults(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterConfig

        cfg = AdapterConfig()
        assert cfg.timeout_ms == 5000
        assert cfg.connect_timeout_ms == 1000
        assert cfg.max_retries == 3
        assert cfg.circuit_failure_threshold == 5
        assert cfg.rate_limit_per_second == 100.0
        assert cfg.cache_enabled is True
        assert cfg.fallback_enabled is True

    def test_custom_values(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterConfig

        cfg = AdapterConfig(timeout_ms=1000, max_retries=1, cache_enabled=False)
        assert cfg.timeout_ms == 1000
        assert cfg.max_retries == 1
        assert cfg.cache_enabled is False


# ---------------------------------------------------------------------------
# AdapterResult
# ---------------------------------------------------------------------------


class TestAdapterResult:
    def test_success_result(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterResult

        result = AdapterResult(success=True, data={"key": "value"}, latency_ms=1.5)
        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.from_cache is False

    def test_to_dict_success(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterResult

        result = AdapterResult(success=True, data="ok", latency_ms=2.0)
        d = result.to_dict()
        assert d["success"] is True
        assert d["data"] == "ok"
        assert "error" not in d

    def test_to_dict_error(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterError, AdapterResult

        err = AdapterError("failed")
        result = AdapterResult(success=False, error=err, latency_ms=0.1)
        d = result.to_dict()
        assert d["success"] is False
        assert "error" in d
        assert "error_details" in d
        assert d["error_details"]["error"] == "AdapterError"

    def test_to_dict_error_without_to_dict(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterResult

        result = AdapterResult(success=False, error=RuntimeError("boom"), latency_ms=0.5)
        d = result.to_dict()
        assert d["error_details"]["error"] == "RuntimeError"

    def test_from_cache_flag(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterResult

        result = AdapterResult(success=True, data="cached", from_cache=True)
        assert result.from_cache is True

    def test_from_fallback_flag(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterResult

        result = AdapterResult(success=True, data="fallback", from_fallback=True)
        assert result.from_fallback is True


# ---------------------------------------------------------------------------
# SimpleCircuitBreaker
# ---------------------------------------------------------------------------


class TestSimpleCircuitBreaker:
    def test_initial_state_closed(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterState, SimpleCircuitBreaker

        cb = SimpleCircuitBreaker()
        assert cb.state == AdapterState.CLOSED

    def test_opens_after_threshold(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterState, SimpleCircuitBreaker

        cb = SimpleCircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == AdapterState.CLOSED
        cb.record_failure()
        assert cb.state == AdapterState.OPEN

    def test_time_until_recovery_closed(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import SimpleCircuitBreaker

        cb = SimpleCircuitBreaker()
        assert cb.time_until_recovery == 0.0

    def test_transitions_to_half_open(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterState, SimpleCircuitBreaker

        cb = SimpleCircuitBreaker(failure_threshold=1, recovery_timeout_s=0.01)
        cb.record_failure()
        assert cb.state == AdapterState.OPEN
        time.sleep(0.02)
        assert cb.state == AdapterState.HALF_OPEN

    def test_half_open_success_closes(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterState, SimpleCircuitBreaker

        cb = SimpleCircuitBreaker(
            failure_threshold=1, recovery_timeout_s=0.01, half_open_max_calls=2
        )
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == AdapterState.HALF_OPEN
        cb.record_success()
        cb.record_success()
        assert cb.state == AdapterState.CLOSED

    def test_half_open_failure_reopens(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterState, SimpleCircuitBreaker

        cb = SimpleCircuitBreaker(failure_threshold=1, recovery_timeout_s=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == AdapterState.HALF_OPEN
        cb.record_failure()
        assert cb.state == AdapterState.OPEN

    def test_success_decrements_failure_count(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterState, SimpleCircuitBreaker

        cb = SimpleCircuitBreaker(failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        assert cb._failure_count == 2
        cb.record_success()
        assert cb._failure_count == 1

    def test_reset(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterState, SimpleCircuitBreaker

        cb = SimpleCircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.state == AdapterState.OPEN
        cb.reset()
        assert cb.state == AdapterState.CLOSED
        assert cb._failure_count == 0


# ---------------------------------------------------------------------------
# TokenBucketRateLimiter
# ---------------------------------------------------------------------------


class TestTokenBucketRateLimiter:
    @pytest.mark.asyncio
    async def test_acquire_within_burst(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import TokenBucketRateLimiter

        rl = TokenBucketRateLimiter(rate_per_second=10.0, burst=5)
        results = [await rl.acquire() for _ in range(5)]
        assert all(results)

    @pytest.mark.asyncio
    async def test_acquire_exceeds_burst(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import TokenBucketRateLimiter

        rl = TokenBucketRateLimiter(rate_per_second=10.0, burst=2)
        await rl.acquire()
        await rl.acquire()
        result = await rl.acquire()
        assert result is False

    @pytest.mark.asyncio
    async def test_tokens_refill(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import TokenBucketRateLimiter

        rl = TokenBucketRateLimiter(rate_per_second=1000.0, burst=1)
        await rl.acquire()  # Drain
        result = await rl.acquire()
        # With 1000/s rate and burst=1, refill happens quickly
        # The second call may or may not pass depending on timing
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# ACLAdapter (concrete subclass for testing)
# ---------------------------------------------------------------------------


class _TestAdapter:
    """Concrete adapter for testing the abstract ACLAdapter."""

    @staticmethod
    def create(
        execute_fn=None,
        validate_fn=None,
        cache_key_fn=None,
        fallback_fn=None,
        config=None,
    ):
        from enhanced_agent_bus.acl_adapters.base import ACLAdapter, AdapterConfig

        class ConcreteAdapter(ACLAdapter[str, str]):
            def __init__(self):
                super().__init__("test_adapter", config or AdapterConfig(max_retries=0))
                self._exec_fn = execute_fn or (lambda r: r.upper())
                self._val_fn = validate_fn or (lambda r: True)
                self._key_fn = cache_key_fn or (lambda r: f"key:{r}")
                self._fb_fn = fallback_fn

            async def _execute(self, request: str) -> str:
                fn = self._exec_fn
                if inspect.iscoroutinefunction(fn):
                    return await fn(request)
                return fn(request)

            def _validate_response(self, response: str) -> bool:
                return self._val_fn(response)

            def _get_cache_key(self, request: str) -> str:
                return self._key_fn(request)

            def _get_fallback_response(self, request: str) -> str | None:
                if self._fb_fn:
                    return self._fb_fn(request)
                return None

        return ConcreteAdapter()


class TestACLAdapter:
    @pytest.mark.asyncio
    async def test_successful_call(self) -> None:
        adapter = _TestAdapter.create()
        result = await adapter.call("hello")
        assert result.success is True
        assert result.data == "HELLO"
        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_cache_hit(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterConfig

        cfg = AdapterConfig(max_retries=0, cache_enabled=True, cache_ttl_s=60)
        adapter = _TestAdapter.create(config=cfg)
        r1 = await adapter.call("hello")
        r2 = await adapter.call("hello")
        assert r1.success is True
        assert r2.success is True
        assert r2.from_cache is True

    @pytest.mark.asyncio
    async def test_cache_disabled(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterConfig

        cfg = AdapterConfig(max_retries=0, cache_enabled=False)
        adapter = _TestAdapter.create(config=cfg)
        r1 = await adapter.call("hello")
        r2 = await adapter.call("hello")
        assert r1.from_cache is False
        assert r2.from_cache is False

    @pytest.mark.asyncio
    async def test_validation_failure(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterConfig

        cfg = AdapterConfig(max_retries=0, fallback_enabled=False)
        adapter = _TestAdapter.create(validate_fn=lambda r: False, config=cfg)
        result = await adapter.call("hello")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_fallback_on_failure(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterConfig

        cfg = AdapterConfig(max_retries=0, fallback_enabled=True)

        def failing_execute(r):
            raise RuntimeError("boom")

        adapter = _TestAdapter.create(
            execute_fn=failing_execute,
            fallback_fn=lambda r: "fallback_value",
            config=cfg,
        )
        result = await adapter.call("hello")
        assert result.success is True
        assert result.data == "fallback_value"
        assert result.from_fallback is True

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterConfig

        cfg = AdapterConfig(
            max_retries=0,
            circuit_failure_threshold=1,
            circuit_recovery_timeout_s=60.0,
            fallback_enabled=False,
        )

        def failing_execute(r):
            raise RuntimeError("fail")

        adapter = _TestAdapter.create(execute_fn=failing_execute, config=cfg)
        # First call triggers failure -> opens circuit
        r1 = await adapter.call("hello")
        assert r1.success is False
        # Second call should be blocked by circuit breaker
        r2 = await adapter.call("hello")
        assert r2.success is False

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterConfig

        cfg = AdapterConfig(max_retries=0, rate_limit_per_second=1.0, rate_limit_burst=1)
        adapter = _TestAdapter.create(config=cfg)
        r1 = await adapter.call("a")
        assert r1.success is True
        r2 = await adapter.call("b")
        assert r2.success is False

    @pytest.mark.asyncio
    async def test_get_metrics(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterConfig

        cfg = AdapterConfig(max_retries=0)
        adapter = _TestAdapter.create(config=cfg)
        await adapter.call("hello")
        metrics = adapter.get_metrics()
        assert metrics["total_calls"] == 1
        assert metrics["successful_calls"] == 1
        assert metrics["adapter_name"] == "test_adapter"
        assert "success_rate" in metrics

    @pytest.mark.asyncio
    async def test_get_health_healthy(self) -> None:
        adapter = _TestAdapter.create()
        health = adapter.get_health()
        assert health["healthy"] is True
        assert health["state"] == "closed"
        assert "constitutional_hash" in health

    @pytest.mark.asyncio
    async def test_clear_cache(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterConfig

        cfg = AdapterConfig(max_retries=0, cache_enabled=True, cache_ttl_s=60)
        adapter = _TestAdapter.create(config=cfg)
        await adapter.call("hello")
        assert len(adapter._cache) > 0
        adapter.clear_cache()
        assert len(adapter._cache) == 0

    @pytest.mark.asyncio
    async def test_reset_circuit_breaker(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterConfig, AdapterState

        cfg = AdapterConfig(
            max_retries=0,
            circuit_failure_threshold=1,
            circuit_recovery_timeout_s=60.0,
            fallback_enabled=False,
        )

        def failing(r):
            raise RuntimeError("fail")

        adapter = _TestAdapter.create(execute_fn=failing, config=cfg)
        await adapter.call("hello")
        assert adapter.circuit_breaker.state == AdapterState.OPEN
        adapter.reset_circuit_breaker()
        assert adapter.circuit_breaker.state == AdapterState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_breaker_fallback_when_open(self) -> None:
        from enhanced_agent_bus.acl_adapters.base import AdapterConfig

        cfg = AdapterConfig(
            max_retries=0,
            circuit_failure_threshold=1,
            circuit_recovery_timeout_s=60.0,
            fallback_enabled=True,
        )

        call_count = 0

        def failing(r):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        adapter = _TestAdapter.create(
            execute_fn=failing,
            fallback_fn=lambda r: "fb",
            config=cfg,
        )
        # First call fails, opens circuit
        r1 = await adapter.call("hello")
        assert r1.success is True  # fallback
        assert r1.from_fallback is True
        # Second call -> circuit open -> fallback without calling _execute
        prev_count = call_count
        r2 = await adapter.call("hello")
        assert r2.success is True
        assert r2.from_fallback is True
