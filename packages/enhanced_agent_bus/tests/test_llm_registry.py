"""
Tests for llm_adapters/registry.py - LLMAdapterRegistry, CircuitBreaker, AdapterMetrics.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.errors import (
    ResourceNotFoundError,
    ServiceUnavailableError,
)
from enhanced_agent_bus.circuit_breaker.enums import CircuitState as CircuitBreakerState
from enhanced_agent_bus.llm_adapters.base import (
    AdapterStatus,
    BaseLLMAdapter,
    CompletionMetadata,
    CostEstimate,
    HealthCheckResult,
    LLMMessage,
    LLMResponse,
    TokenUsage,
)
from enhanced_agent_bus.llm_adapters.registry import (
    AdapterMetrics,
    CircuitBreaker,
    CircuitBreakerConfig,
    FallbackChain,
    LLMAdapterRegistry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubAdapter(BaseLLMAdapter):
    """Minimal concrete adapter for testing."""

    def complete(self, messages, **kw):
        return self._make_response("ok")

    async def acomplete(self, messages, **kw):
        return self._make_response("ok")

    def stream(self, messages, **kw):
        yield "ok"

    async def astream(self, messages, **kw):
        yield "ok"

    def count_tokens(self, messages):
        return 10

    def estimate_cost(self, prompt_tokens, completion_tokens):
        return CostEstimate(total_cost_usd=0.001)

    async def health_check(self):
        return HealthCheckResult(status=AdapterStatus.HEALTHY, message="ok")

    def validate_constitutional_compliance(self, **kwargs: object) -> None:
        pass  # No-op for test stub

    def _make_response(self, content: str) -> LLMResponse:
        return LLMResponse(
            content=content,
            usage=TokenUsage(total_tokens=10),
            cost=CostEstimate(total_cost_usd=0.001),
            metadata=CompletionMetadata(model="stub", provider="test"),
        )


def _adapter(name: str = "stub") -> _StubAdapter:
    return _StubAdapter(model=name)


# ===========================================================================
# CircuitBreakerConfig
# ===========================================================================


class TestCircuitBreakerConfig:
    def test_defaults(self):
        cfg = CircuitBreakerConfig()
        assert cfg.failure_threshold == 5
        assert cfg.success_threshold == 2
        assert cfg.timeout_seconds == 60.0

    def test_to_dict(self):
        cfg = CircuitBreakerConfig(failure_threshold=3)
        d = cfg.to_dict()
        assert d["failure_threshold"] == 3


# ===========================================================================
# AdapterMetrics
# ===========================================================================


class TestAdapterMetrics:
    def test_initial_success_rate_is_zero(self):
        m = AdapterMetrics(adapter_id="a1")
        assert m.success_rate == 0.0

    def test_record_success(self):
        m = AdapterMetrics(adapter_id="a1")
        m.record_request(success=True, latency_ms=100.0, tokens=50, cost_usd=0.01)
        assert m.total_requests == 1
        assert m.successful_requests == 1
        assert m.total_tokens == 50
        assert m.avg_latency_ms == 100.0

    def test_record_failure(self):
        m = AdapterMetrics(adapter_id="a1")
        m.record_request(success=False, latency_ms=50.0)
        assert m.failed_requests == 1

    def test_ema_latency(self):
        m = AdapterMetrics(adapter_id="a1")
        m.record_request(success=True, latency_ms=100.0)
        m.record_request(success=True, latency_ms=200.0)
        # EMA: 0.9*100 + 0.1*200 = 110
        assert abs(m.avg_latency_ms - 110.0) < 0.01

    def test_to_dict(self):
        m = AdapterMetrics(adapter_id="a1")
        m.record_request(success=True, latency_ms=10.0)
        d = m.to_dict()
        assert d["adapter_id"] == "a1"
        assert d["total_requests"] == 1
        assert "success_rate" in d

    def test_record_with_prometheus_labels(self):
        """Prometheus metrics are best-effort; should not raise."""
        m = AdapterMetrics(adapter_id="a1")
        m.record_request(
            success=True,
            latency_ms=50.0,
            tokens=10,
            cost_usd=0.001,
            provider="test",
            model="stub",
        )
        assert m.total_requests == 1


# ===========================================================================
# CircuitBreaker
# ===========================================================================


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_closed_state_allows_calls(self):
        cb = CircuitBreaker("a1")
        result = await cb.call(AsyncMock(return_value="ok"))
        assert result == "ok"
        assert cb.state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker("a1", CircuitBreakerConfig(failure_threshold=2))
        failing = AsyncMock(side_effect=RuntimeError("fail"))
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(failing)
        assert cb.state == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_open_rejects_calls(self):
        cb = CircuitBreaker("a1", CircuitBreakerConfig(failure_threshold=1))
        with pytest.raises(RuntimeError):
            await cb.call(AsyncMock(side_effect=RuntimeError("fail")))
        assert cb.state == CircuitBreakerState.OPEN
        with pytest.raises(ServiceUnavailableError):
            await cb.call(AsyncMock(return_value="ok"))

    @pytest.mark.asyncio
    async def test_half_open_transitions_to_closed_on_success(self):
        cb = CircuitBreaker(
            "a1",
            CircuitBreakerConfig(failure_threshold=1, success_threshold=1, timeout_seconds=0),
        )
        with pytest.raises(RuntimeError):
            await cb.call(AsyncMock(side_effect=RuntimeError("fail")))
        assert cb.state == CircuitBreakerState.OPEN

        # Should transition to HALF_OPEN (timeout=0 means immediate)
        result = await cb.call(AsyncMock(return_value="ok"))
        assert result == "ok"
        assert cb.state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_back_to_open_on_failure(self):
        cb = CircuitBreaker(
            "a1",
            CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0),
        )
        with pytest.raises(RuntimeError):
            await cb.call(AsyncMock(side_effect=RuntimeError("fail")))

        # Now HALF_OPEN, another failure should go back to OPEN
        with pytest.raises(RuntimeError):
            await cb.call(AsyncMock(side_effect=RuntimeError("fail2")))
        assert cb.state == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_half_open_limit_reached(self):
        cb = CircuitBreaker(
            "a1",
            CircuitBreakerConfig(
                failure_threshold=1,
                timeout_seconds=9999,  # long timeout so OPEN stays OPEN
                half_open_max_calls=1,
            ),
        )
        with pytest.raises(RuntimeError):
            await cb.call(AsyncMock(side_effect=RuntimeError("fail")))
        assert cb.state == CircuitBreakerState.OPEN

        # Manually set to HALF_OPEN and exhaust calls
        cb.state = CircuitBreakerState.HALF_OPEN
        cb.half_open_calls = 0

        # First half-open call succeeds (uses the one allowed call)
        with pytest.raises(RuntimeError):
            await cb.call(AsyncMock(side_effect=RuntimeError("fail")))

        # Back to OPEN after failure in HALF_OPEN; force HALF_OPEN again
        cb.state = CircuitBreakerState.HALF_OPEN
        cb.half_open_calls = 1  # already at limit

        with pytest.raises(ServiceUnavailableError):
            await cb.call(AsyncMock(return_value="ok"))

    def test_is_available(self):
        cb = CircuitBreaker("a1")
        assert cb.is_available() is True
        cb.state = CircuitBreakerState.OPEN
        assert cb.is_available() is False

    def test_get_state(self):
        cb = CircuitBreaker("a1")
        assert cb.get_state() == CircuitBreakerState.CLOSED


# ===========================================================================
# FallbackChain
# ===========================================================================


class TestFallbackChain:
    def test_get_ordered_adapters(self):
        chain = FallbackChain(primary="a", fallbacks=["b", "c"])
        assert chain.get_ordered_adapters() == ["a", "b", "c"]

    def test_to_dict(self):
        chain = FallbackChain(primary="a", fallbacks=["b"])
        d = chain.to_dict()
        assert d["primary"] == "a"
        assert d["fallbacks"] == ["b"]


# ===========================================================================
# LLMAdapterRegistry
# ===========================================================================


class TestLLMAdapterRegistry:
    @pytest.fixture
    def registry(self):
        return LLMAdapterRegistry()

    @pytest.mark.asyncio
    async def test_register_and_get_adapter(self, registry):
        adapter = _adapter()
        await registry.register_adapter("a1", adapter, tags=["test"])
        result = await registry.get_adapter("a1")
        assert result is adapter

    @pytest.mark.asyncio
    async def test_get_missing_adapter(self, registry):
        assert await registry.get_adapter("nope") is None

    @pytest.mark.asyncio
    async def test_register_replaces_existing(self, registry):
        await registry.register_adapter("a1", _adapter("v1"))
        await registry.register_adapter("a1", _adapter("v2"))
        a = await registry.get_adapter("a1")
        assert a.model == "v2"

    @pytest.mark.asyncio
    async def test_unregister_adapter(self, registry):
        await registry.register_adapter("a1", _adapter())
        assert await registry.unregister_adapter("a1") is True
        assert await registry.get_adapter("a1") is None

    @pytest.mark.asyncio
    async def test_unregister_missing(self, registry):
        assert await registry.unregister_adapter("nope") is False

    @pytest.mark.asyncio
    async def test_list_adapters(self, registry):
        await registry.register_adapter("a1", _adapter(), tags=["gpu"])
        await registry.register_adapter("a2", _adapter(), tags=["cpu"])
        all_ids = await registry.list_adapters()
        assert set(all_ids) == {"a1", "a2"}

    @pytest.mark.asyncio
    async def test_list_adapters_filter_by_tags(self, registry):
        await registry.register_adapter("a1", _adapter(), tags=["gpu"])
        await registry.register_adapter("a2", _adapter(), tags=["cpu"])
        gpu_ids = await registry.list_adapters(tags=["gpu"])
        assert gpu_ids == ["a1"]

    @pytest.mark.asyncio
    async def test_list_adapters_filter_by_status(self, registry):
        await registry.register_adapter("a1", _adapter())
        ids = await registry.list_adapters(status=AdapterStatus.HEALTHY)
        assert "a1" in ids

    @pytest.mark.asyncio
    async def test_register_adapter_type(self, registry):
        await registry.register_adapter_type("stub", _StubAdapter)
        assert "stub" in registry._adapter_types

    @pytest.mark.asyncio
    async def test_configure_fallback_chain(self, registry):
        await registry.register_adapter("a1", _adapter())
        await registry.register_adapter("a2", _adapter())
        await registry.configure_fallback_chain("chain1", "a1", ["a2"])
        assert "chain1" in registry._fallback_chains

    @pytest.mark.asyncio
    async def test_configure_fallback_chain_missing_adapter(self, registry):
        await registry.register_adapter("a1", _adapter())
        with pytest.raises(ResourceNotFoundError):
            await registry.configure_fallback_chain("chain1", "a1", ["nonexistent"])

    @pytest.mark.asyncio
    async def test_unregister_removes_from_fallback_chain(self, registry):
        await registry.register_adapter("a1", _adapter())
        await registry.register_adapter("a2", _adapter())
        await registry.configure_fallback_chain("chain1", "a1", ["a2"])
        await registry.unregister_adapter("a1")
        assert "chain1" not in registry._fallback_chains

    @pytest.mark.asyncio
    async def test_health_check(self, registry):
        await registry.register_adapter("a1", _adapter())
        result = await registry.health_check("a1")
        assert result.status == AdapterStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_health_check_missing_adapter(self, registry):
        with pytest.raises(ResourceNotFoundError):
            await registry.health_check("nope")

    @pytest.mark.asyncio
    async def test_health_check_failure(self, registry):
        adapter = _adapter()
        adapter.health_check = AsyncMock(side_effect=RuntimeError("down"))
        await registry.register_adapter("a1", adapter)
        result = await registry.health_check("a1")
        assert result.status == AdapterStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_health_check_all(self, registry):
        await registry.register_adapter("a1", _adapter())
        await registry.register_adapter("a2", _adapter())
        results = await registry.health_check_all()
        assert len(results) == 2
        assert all(r.status == AdapterStatus.HEALTHY for r in results.values())

    @pytest.mark.asyncio
    async def test_get_metrics(self, registry):
        await registry.register_adapter("a1", _adapter())
        m = await registry.get_metrics("a1")
        assert m is not None
        assert m.adapter_id == "a1"

    @pytest.mark.asyncio
    async def test_get_metrics_missing(self, registry):
        assert await registry.get_metrics("nope") is None

    @pytest.mark.asyncio
    async def test_get_all_metrics(self, registry):
        await registry.register_adapter("a1", _adapter())
        all_m = await registry.get_all_metrics()
        assert "a1" in all_m

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_state(self, registry):
        await registry.register_adapter("a1", _adapter())
        state = await registry.get_circuit_breaker_state("a1")
        assert state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_state_missing(self, registry):
        assert await registry.get_circuit_breaker_state("nope") is None

    @pytest.mark.asyncio
    async def test_complete_with_fallback_success(self, registry):
        await registry.register_adapter("a1", _adapter())
        await registry.register_adapter("a2", _adapter())
        await registry.configure_fallback_chain("chain1", "a1", ["a2"])

        messages = [LLMMessage(role="user", content="hi")]
        response = await registry.complete_with_fallback("chain1", messages)
        assert response.content == "ok"

    @pytest.mark.asyncio
    async def test_complete_with_fallback_primary_fails(self, registry):
        bad = _adapter("bad")
        bad.acomplete = AsyncMock(side_effect=RuntimeError("fail"))
        good = _adapter("good")

        await registry.register_adapter("bad", bad)
        await registry.register_adapter("good", good)
        await registry.configure_fallback_chain("chain1", "bad", ["good"])

        messages = [LLMMessage(role="user", content="hi")]
        response = await registry.complete_with_fallback("chain1", messages)
        assert response.content == "ok"

    @pytest.mark.asyncio
    async def test_complete_with_fallback_all_fail(self, registry):
        bad1 = _adapter("b1")
        bad1.acomplete = AsyncMock(side_effect=RuntimeError("fail"))
        bad2 = _adapter("b2")
        bad2.acomplete = AsyncMock(side_effect=RuntimeError("fail"))

        await registry.register_adapter("b1", bad1)
        await registry.register_adapter("b2", bad2)
        await registry.configure_fallback_chain("chain1", "b1", ["b2"])

        messages = [LLMMessage(role="user", content="hi")]
        with pytest.raises(ServiceUnavailableError):
            await registry.complete_with_fallback("chain1", messages)

    @pytest.mark.asyncio
    async def test_complete_with_fallback_missing_chain(self, registry):
        messages = [LLMMessage(role="user", content="hi")]
        with pytest.raises(ResourceNotFoundError):
            await registry.complete_with_fallback("nope", messages)

    def test_to_dict(self):
        reg = LLMAdapterRegistry()
        d = reg.to_dict()
        assert "constitutional_hash" in d
        assert d["adapter_count"] == 0

    @pytest.mark.asyncio
    async def test_context_manager(self):
        reg = LLMAdapterRegistry(health_check_interval_seconds=9999)
        async with reg:
            assert reg._running is True
        assert reg._running is False

    @pytest.mark.asyncio
    async def test_start_stop_health_monitoring(self, registry):
        await registry.start_health_monitoring()
        assert registry._running is True
        # Starting again should be a no-op
        await registry.start_health_monitoring()
        await registry.stop_health_monitoring()
        assert registry._running is False
