# Constitutional Hash: 608508a9bd224290
"""
Tests for enhanced_agent_bus.llm_adapters.llm_failover module.

Targets classes and functions defined directly in llm_failover.py:
- LLMProviderType enum
- get_llm_circuit_config()
- LLM_CIRCUIT_CONFIGS dict
- HealthMetrics / ProviderHealthScore dataclasses
- ProviderHealthScorer
- ProviderWarmupManager / WarmupResult
- RequestHedgingManager / HedgedRequest
- ProactiveFailoverManager (via re-export)

All async tests use asyncio_mode = "auto" from pyproject.toml.
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.circuit_breaker import (
    CONSTITUTIONAL_HASH,
    FallbackStrategy,
    ServiceSeverity,
)
from enhanced_agent_bus.llm_adapters.llm_failover import (
    LLM_CIRCUIT_CONFIGS,
    HealthMetrics,
    HedgedRequest,
    LLMProviderType,
    ProviderHealthScore,
    ProviderHealthScorer,
    ProviderWarmupManager,
    RequestHedgingManager,
    WarmupResult,
    get_llm_circuit_config,
)

# =============================================================================
# LLMProviderType enum
# =============================================================================


class TestLLMProviderType:
    def test_all_providers_exist(self) -> None:
        expected = {
            "openai",
            "anthropic",
            "google",
            "azure",
            "bedrock",
            "cohere",
            "mistral",
            "kimi",
            "openclaw",
            "local",
        }
        actual = {p.value for p in LLMProviderType}
        assert actual == expected

    def test_is_str_enum(self) -> None:
        assert isinstance(LLMProviderType.OPENAI, str)
        assert LLMProviderType.OPENAI == "openai"


# =============================================================================
# LLM_CIRCUIT_CONFIGS and get_llm_circuit_config
# =============================================================================


class TestLLMCircuitConfigs:
    def test_known_providers_have_configs(self) -> None:
        for key in (
            "llm:openai",
            "llm:anthropic",
            "llm:google",
            "llm:azure",
            "llm:bedrock",
            "llm:kimi",
            "llm:openclaw",
            "llm:local",
        ):
            assert key in LLM_CIRCUIT_CONFIGS

    def test_openai_config_values(self) -> None:
        cfg = LLM_CIRCUIT_CONFIGS["llm:openai"]
        assert cfg.name == "llm:openai"
        assert cfg.fallback_strategy == FallbackStrategy.CACHED_VALUE
        assert cfg.severity == ServiceSeverity.HIGH

    def test_anthropic_has_longer_timeout(self) -> None:
        cfg = LLM_CIRCUIT_CONFIGS["llm:anthropic"]
        assert cfg.timeout_seconds == 45.0

    def test_local_uses_bypass_strategy(self) -> None:
        cfg = LLM_CIRCUIT_CONFIGS["llm:local"]
        assert cfg.fallback_strategy == FallbackStrategy.BYPASS
        assert cfg.severity == ServiceSeverity.LOW

    def test_get_known_provider(self) -> None:
        cfg = get_llm_circuit_config("openai")
        assert cfg.name == "llm:openai"

    def test_get_known_provider_case_insensitive(self) -> None:
        cfg = get_llm_circuit_config("OpenAI")
        assert cfg.name == "llm:openai"

    def test_get_unknown_provider_returns_default(self) -> None:
        cfg = get_llm_circuit_config("unknown_provider_xyz")
        assert cfg.name == "llm:unknown_provider_xyz"
        assert cfg.severity == ServiceSeverity.MEDIUM
        assert "Auto-configured" in cfg.description


# =============================================================================
# HealthMetrics dataclass
# =============================================================================


class TestHealthMetrics:
    def test_defaults(self) -> None:
        m = HealthMetrics()
        assert m.total_requests == 0
        assert m.error_rate == 0.0
        assert m.health_score == 1.0
        assert m.uptime_percentage == 100.0
        assert m.avg_quality_score == 1.0
        assert m.constitutional_hash == CONSTITUTIONAL_HASH

    def test_latency_samples_is_bounded_deque(self) -> None:
        m = HealthMetrics()
        assert isinstance(m.latency_samples, deque)
        assert m.latency_samples.maxlen == 100

    def test_quality_scores_is_bounded_deque(self) -> None:
        m = HealthMetrics()
        assert isinstance(m.response_quality_scores, deque)
        assert m.response_quality_scores.maxlen == 50


# =============================================================================
# ProviderHealthScore dataclass
# =============================================================================


class TestProviderHealthScore:
    def _make_score(self, **overrides) -> ProviderHealthScore:
        defaults = {
            "provider_id": "test-provider",
            "health_score": 0.9,
            "latency_score": 0.85,
            "error_score": 0.95,
            "quality_score": 0.8,
            "availability_score": 0.99,
            "is_healthy": True,
            "is_degraded": False,
            "is_unhealthy": False,
            "metrics": HealthMetrics(),
        }
        defaults.update(overrides)
        return ProviderHealthScore(**defaults)

    def test_to_dict_keys(self) -> None:
        score = self._make_score()
        d = score.to_dict()
        expected_keys = {
            "provider_id",
            "health_score",
            "latency_score",
            "error_score",
            "quality_score",
            "availability_score",
            "is_healthy",
            "is_degraded",
            "is_unhealthy",
            "metrics",
            "last_updated",
            "constitutional_hash",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_rounds_scores(self) -> None:
        score = self._make_score(health_score=0.12345678)
        d = score.to_dict()
        assert d["health_score"] == 0.123

    def test_to_dict_metrics_subset(self) -> None:
        score = self._make_score()
        d = score.to_dict()
        m = d["metrics"]
        assert "avg_latency_ms" in m
        assert "p95_latency_ms" in m
        assert "error_rate" in m
        assert "total_requests" in m
        assert "consecutive_failures" in m

    def test_constitutional_hash(self) -> None:
        score = self._make_score()
        assert score.constitutional_hash == CONSTITUTIONAL_HASH
        assert score.to_dict()["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# ProviderHealthScorer
# =============================================================================


class TestProviderHealthScorer:
    def test_initial_state(self) -> None:
        scorer = ProviderHealthScorer()
        score = scorer.get_health_score("nonexistent")
        assert score.health_score == 1.0
        assert score.is_healthy is True

    def test_weight_constants(self) -> None:
        total = (
            ProviderHealthScorer.LATENCY_WEIGHT
            + ProviderHealthScorer.ERROR_WEIGHT
            + ProviderHealthScorer.QUALITY_WEIGHT
            + ProviderHealthScorer.AVAILABILITY_WEIGHT
        )
        assert total == pytest.approx(1.0)

    async def test_record_successful_request(self) -> None:
        scorer = ProviderHealthScorer()
        await scorer.record_request("p1", latency_ms=100.0, success=True)

        score = scorer.get_health_score("p1")
        assert score.metrics.total_requests == 1
        assert score.metrics.successful_requests == 1
        assert score.metrics.failed_requests == 0
        assert score.metrics.consecutive_failures == 0
        assert score.metrics.last_success_time is not None

    async def test_record_failed_request(self) -> None:
        scorer = ProviderHealthScorer()
        await scorer.record_request("p1", latency_ms=200.0, success=False)

        score = scorer.get_health_score("p1")
        assert score.metrics.total_requests == 1
        assert score.metrics.failed_requests == 1
        assert score.metrics.consecutive_failures == 1
        assert score.metrics.last_failure_time is not None

    async def test_timeout_error_type_tracked(self) -> None:
        scorer = ProviderHealthScorer()
        await scorer.record_request("p1", 500.0, success=False, error_type="timeout")
        assert scorer._metrics["p1"].timeout_count == 1

    async def test_rate_limit_error_type_tracked(self) -> None:
        scorer = ProviderHealthScorer()
        await scorer.record_request("p1", 100.0, success=False, error_type="rate_limit")
        assert scorer._metrics["p1"].rate_limit_count == 1

    async def test_quality_score_recorded(self) -> None:
        scorer = ProviderHealthScorer()
        await scorer.record_request("p1", 100.0, success=True, quality_score=0.9)
        await scorer.record_request("p1", 100.0, success=True, quality_score=0.7)
        assert scorer._metrics["p1"].avg_quality_score == pytest.approx(0.8)

    async def test_error_rate_calculation(self) -> None:
        scorer = ProviderHealthScorer()
        await scorer.record_request("p1", 100.0, success=True)
        await scorer.record_request("p1", 100.0, success=False)
        assert scorer._metrics["p1"].error_rate == pytest.approx(0.5)

    async def test_consecutive_failures_reset_on_success(self) -> None:
        scorer = ProviderHealthScorer()
        await scorer.record_request("p1", 100.0, success=False)
        await scorer.record_request("p1", 100.0, success=False)
        assert scorer._metrics["p1"].consecutive_failures == 2

        await scorer.record_request("p1", 100.0, success=True)
        assert scorer._metrics["p1"].consecutive_failures == 0

    async def test_latency_stats_computed(self) -> None:
        scorer = ProviderHealthScorer()
        for lat in [100.0, 200.0, 300.0, 400.0, 500.0]:
            await scorer.record_request("p1", lat, success=True)

        m = scorer._metrics["p1"]
        assert m.avg_latency_ms == pytest.approx(300.0)
        assert m.p50_latency_ms == pytest.approx(300.0)
        assert m.p95_latency_ms > 0
        assert m.p99_latency_ms > 0

    async def test_uptime_percentage(self) -> None:
        scorer = ProviderHealthScorer()
        await scorer.record_request("p1", 100.0, success=True)
        await scorer.record_request("p1", 100.0, success=True)
        await scorer.record_request("p1", 100.0, success=False)
        m = scorer._metrics["p1"]
        assert m.uptime_percentage == pytest.approx(200 / 3)

    async def test_health_degrades_with_failures(self) -> None:
        scorer = ProviderHealthScorer()
        for _ in range(20):
            await scorer.record_request("p1", 1000.0, success=False)

        score = scorer.get_health_score("p1")
        assert score.health_score < 0.3
        assert score.is_unhealthy is True

    async def test_health_stays_high_with_successes(self) -> None:
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("p1", 500.0)
        for _ in range(20):
            await scorer.record_request("p1", 100.0, success=True)

        score = scorer.get_health_score("p1")
        assert score.health_score >= 0.8
        assert score.is_healthy is True

    async def test_degraded_state(self) -> None:
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("p1", 200.0)
        # Mix of successes and failures to land in degraded range
        for i in range(20):
            await scorer.record_request("p1", 300.0, success=(i % 3 != 0))

        score = scorer.get_health_score("p1")
        # Score should be somewhere in between; just verify the flags are consistent
        if 0.5 <= score.health_score < 0.8:
            assert score.is_degraded is True

    def test_set_expected_latency(self) -> None:
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("p1", 250.0)
        assert scorer._expected_latency["p1"] == 250.0

    def test_get_all_scores_empty(self) -> None:
        scorer = ProviderHealthScorer()
        assert scorer.get_all_scores() == {}

    async def test_get_all_scores_multiple_providers(self) -> None:
        scorer = ProviderHealthScorer()
        await scorer.record_request("p1", 100.0, success=True)
        await scorer.record_request("p2", 200.0, success=False)

        all_scores = scorer.get_all_scores()
        assert "p1" in all_scores
        assert "p2" in all_scores

    def test_reset_single_provider(self) -> None:
        scorer = ProviderHealthScorer()
        scorer._metrics["p1"] = HealthMetrics(total_requests=10)
        scorer._metrics["p2"] = HealthMetrics(total_requests=5)

        scorer.reset("p1")
        assert scorer._metrics["p1"].total_requests == 0
        assert scorer._metrics["p2"].total_requests == 5

    def test_reset_all(self) -> None:
        scorer = ProviderHealthScorer()
        scorer._metrics["p1"] = HealthMetrics(total_requests=10)
        scorer._metrics["p2"] = HealthMetrics(total_requests=5)

        scorer.reset()
        assert len(scorer._metrics) == 0

    def test_reset_nonexistent_provider_is_noop(self) -> None:
        scorer = ProviderHealthScorer()
        scorer.reset("does-not-exist")  # Should not raise

    async def test_consecutive_failure_penalty_on_availability(self) -> None:
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("p1", 500.0)
        # Record many consecutive failures
        for _ in range(10):
            await scorer.record_request("p1", 100.0, success=False)

        score = scorer.get_health_score("p1")
        # Availability score should be penalized by consecutive failures
        assert score.availability_score < 0.5

    async def test_latency_score_degrades_with_high_latency(self) -> None:
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("p1", 100.0)
        # Latency much higher than expected
        for _ in range(10):
            await scorer.record_request("p1", 500.0, success=True)

        score = scorer.get_health_score("p1")
        assert score.latency_score < 0.5


# =============================================================================
# WarmupResult dataclass
# =============================================================================


class TestWarmupResult:
    def test_success_result(self) -> None:
        r = WarmupResult(provider_id="p1", success=True, latency_ms=50.0)
        assert r.success is True
        assert r.error is None
        assert r.constitutional_hash == CONSTITUTIONAL_HASH

    def test_failure_result(self) -> None:
        r = WarmupResult(provider_id="p1", success=False, latency_ms=0, error="Timeout")
        assert r.success is False
        assert r.error == "Timeout"


# =============================================================================
# ProviderWarmupManager
# =============================================================================


class TestProviderWarmupManager:
    def test_register_handler(self) -> None:
        mgr = ProviderWarmupManager()
        handler = MagicMock()
        mgr.register_warmup_handler("p1", handler)
        assert "p1" in mgr._warmup_handlers

    async def test_warmup_no_handler_returns_failure(self) -> None:
        mgr = ProviderWarmupManager()
        result = await mgr.warmup("unregistered")
        assert result.success is False
        assert "No warmup handler" in result.error

    async def test_warmup_async_handler_success(self) -> None:
        mgr = ProviderWarmupManager()
        handler = AsyncMock(return_value=None)
        mgr.register_warmup_handler("p1", handler)

        result = await mgr.warmup("p1")
        assert result.success is True
        assert result.latency_ms >= 0
        handler.assert_awaited_once()

    async def test_warmup_sync_handler_success(self) -> None:
        mgr = ProviderWarmupManager()
        handler = MagicMock(return_value=None)
        mgr.register_warmup_handler("p1", handler)

        result = await mgr.warmup("p1")
        assert result.success is True
        assert result.latency_ms >= 0

    async def test_warmup_handler_timeout(self) -> None:
        mgr = ProviderWarmupManager()

        async def slow_handler():
            await asyncio.sleep(30)

        mgr.register_warmup_handler("p1", slow_handler)
        # Override timeout to be very short for test
        mgr.WARMUP_TIMEOUT_MS = 50

        result = await mgr.warmup("p1")
        assert result.success is False
        assert result.error == "Timeout"

    async def test_warmup_handler_raises_error(self) -> None:
        mgr = ProviderWarmupManager()

        async def failing_handler():
            raise ConnectionError("Connection refused")

        mgr.register_warmup_handler("p1", failing_handler)

        result = await mgr.warmup("p1")
        assert result.success is False
        assert "Connection refused" in result.error

    async def test_warmup_updates_last_warmup_and_results(self) -> None:
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p1", AsyncMock(return_value=None))

        await mgr.warmup("p1")
        assert "p1" in mgr._last_warmup
        assert "p1" in mgr._warmup_results

    async def test_warmup_if_needed_first_time(self) -> None:
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p1", AsyncMock(return_value=None))

        result = await mgr.warmup_if_needed("p1")
        assert result is not None
        assert result.success is True

    async def test_warmup_if_needed_within_interval(self) -> None:
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p1", AsyncMock(return_value=None))

        await mgr.warmup("p1")
        # Immediately call again - should skip since interval not elapsed
        result = await mgr.warmup_if_needed("p1", interval=timedelta(minutes=5))
        assert result is None

    async def test_warmup_if_needed_after_interval(self) -> None:
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p1", AsyncMock(return_value=None))

        await mgr.warmup("p1")
        # Force the last warmup to be old
        mgr._last_warmup["p1"] = datetime.now(UTC) - timedelta(minutes=10)

        result = await mgr.warmup_if_needed("p1", interval=timedelta(minutes=5))
        assert result is not None
        assert result.success is True

    async def test_warmup_before_failover(self) -> None:
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("target", AsyncMock(return_value=None))

        result = await mgr.warmup_before_failover("target")
        assert result.success is True

    def test_get_warmup_status_no_handler(self) -> None:
        mgr = ProviderWarmupManager()
        status = mgr.get_warmup_status("p1")
        assert status["has_handler"] is False
        assert status["last_warmup"] is None
        assert status["last_result"] is None
        assert status["periodic_enabled"] is False
        assert status["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_get_warmup_status_after_warmup(self) -> None:
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p1", AsyncMock(return_value=None))
        await mgr.warmup("p1")

        status = mgr.get_warmup_status("p1")
        assert status["has_handler"] is True
        assert status["last_warmup"] is not None
        assert status["last_result"]["success"] is True

    async def test_start_periodic_warmup(self) -> None:
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p1", AsyncMock(return_value=None))
        mgr.start_periodic_warmup("p1", interval=timedelta(seconds=60))

        assert "p1" in mgr._warmup_tasks
        status = mgr.get_warmup_status("p1")
        assert status["periodic_enabled"] is True

        # Cleanup
        mgr.stop_periodic_warmup("p1")

    async def test_stop_periodic_warmup(self) -> None:
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p1", AsyncMock(return_value=None))
        mgr.start_periodic_warmup("p1")
        mgr.stop_periodic_warmup("p1")

        assert "p1" not in mgr._warmup_tasks

    def test_stop_periodic_warmup_not_started(self) -> None:
        mgr = ProviderWarmupManager()
        mgr.stop_periodic_warmup("p1")  # Should not raise

    async def test_start_periodic_warmup_replaces_existing(self) -> None:
        mgr = ProviderWarmupManager()
        mgr.register_warmup_handler("p1", AsyncMock(return_value=None))
        mgr.start_periodic_warmup("p1")
        old_task = mgr._warmup_tasks["p1"]

        mgr.start_periodic_warmup("p1")
        new_task = mgr._warmup_tasks["p1"]

        assert old_task is not new_task
        # Task is in "cancelling" state; give it a tick to fully cancel
        await asyncio.sleep(0)
        assert old_task.cancelled()

        # Cleanup
        mgr.stop_periodic_warmup("p1")


# =============================================================================
# HedgedRequest dataclass
# =============================================================================


class TestHedgedRequest:
    def test_defaults(self) -> None:
        hr = HedgedRequest(request_id="r1", providers=["p1", "p2"])
        assert hr.winning_provider is None
        assert hr.completed_at is None
        assert hr.responses == {}
        assert hr.errors == {}
        assert hr.latencies_ms == {}
        assert hr.constitutional_hash == CONSTITUTIONAL_HASH


# =============================================================================
# RequestHedgingManager
# =============================================================================


class TestRequestHedgingManager:
    def test_init_defaults(self) -> None:
        mgr = RequestHedgingManager()
        assert mgr._default_hedge_count == 2
        assert mgr._hedge_delay_ms == 100

    def test_init_custom(self) -> None:
        mgr = RequestHedgingManager(default_hedge_count=3, hedge_delay_ms=50)
        assert mgr._default_hedge_count == 3
        assert mgr._hedge_delay_ms == 50

    async def test_execute_hedged_single_provider(self) -> None:
        mgr = RequestHedgingManager(hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            return f"response-{provider_id}"

        winner, result = await mgr.execute_hedged("r1", ["p1"], execute_fn, hedge_count=1)
        assert winner == "p1"
        assert result == "response-p1"

    async def test_execute_hedged_fastest_wins(self) -> None:
        mgr = RequestHedgingManager(hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            if provider_id == "slow":
                await asyncio.sleep(1.0)
            return f"response-{provider_id}"

        winner, result = await mgr.execute_hedged("r1", ["fast", "slow"], execute_fn, hedge_count=2)
        assert winner == "fast"
        assert result == "response-fast"

    async def test_execute_hedged_fallback_on_first_failure(self) -> None:
        mgr = RequestHedgingManager(hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            if provider_id == "bad":
                raise ConnectionError("down")
            return f"response-{provider_id}"

        winner, result = await mgr.execute_hedged("r1", ["bad", "good"], execute_fn, hedge_count=2)
        assert winner == "good"
        assert result == "response-good"

    async def test_execute_hedged_all_fail_raises(self) -> None:
        mgr = RequestHedgingManager(hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            raise RuntimeError(f"{provider_id} failed")

        with pytest.raises(RuntimeError, match="All hedged providers failed"):
            await mgr.execute_hedged("r1", ["p1", "p2"], execute_fn, hedge_count=2)

    async def test_execute_hedged_no_providers_raises(self) -> None:
        mgr = RequestHedgingManager()

        async def execute_fn(provider_id: str):
            return "ok"

        with pytest.raises(ValueError, match="No providers available"):
            await mgr.execute_hedged("r1", [], execute_fn)

    async def test_hedged_request_recorded(self) -> None:
        mgr = RequestHedgingManager(hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            return "ok"

        await mgr.execute_hedged("r1", ["p1"], execute_fn, hedge_count=1)
        assert len(mgr._hedged_requests) == 1
        req = mgr._hedged_requests[0]
        assert req.request_id == "r1"
        assert req.winning_provider == "p1"
        assert req.completed_at is not None

    async def test_hedge_count_limits_providers(self) -> None:
        mgr = RequestHedgingManager(hedge_delay_ms=0)
        call_count = 0

        async def execute_fn(provider_id: str):
            nonlocal call_count
            call_count += 1
            return "ok"

        await mgr.execute_hedged("r1", ["p1", "p2", "p3", "p4"], execute_fn, hedge_count=2)
        # Only 2 providers should have been attempted
        assert call_count <= 2

    def test_get_hedging_stats_empty(self) -> None:
        mgr = RequestHedgingManager()
        stats = mgr.get_hedging_stats()
        assert stats["total_hedged_requests"] == 0
        assert stats["avg_latency_improvement_ms"] == 0
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_get_hedging_stats_with_data(self) -> None:
        mgr = RequestHedgingManager(hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            if provider_id == "slow":
                await asyncio.sleep(0.05)
            return "ok"

        await mgr.execute_hedged("r1", ["fast", "slow"], execute_fn, hedge_count=2)

        stats = mgr.get_hedging_stats()
        assert stats["total_hedged_requests"] == 1
        assert stats["successful_requests"] == 1
        assert stats["success_rate"] == 1.0
        assert "provider_win_counts" in stats

    async def test_hedged_errors_tracked(self) -> None:
        mgr = RequestHedgingManager(hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            if provider_id == "bad":
                raise ValueError("broken")
            return "ok"

        await mgr.execute_hedged("r1", ["bad", "good"], execute_fn, hedge_count=2)
        req = mgr._hedged_requests[0]
        assert "bad" in req.errors
        assert "broken" in req.errors["bad"]

    async def test_hedged_latencies_tracked(self) -> None:
        mgr = RequestHedgingManager(hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            return "ok"

        await mgr.execute_hedged("r1", ["p1"], execute_fn, hedge_count=1)
        req = mgr._hedged_requests[0]
        assert "p1" in req.latencies_ms
        assert req.latencies_ms["p1"] >= 0


# =============================================================================
# Module-level exports
# =============================================================================


class TestModuleExports:
    def test_all_key_exports_importable(self) -> None:
        from enhanced_agent_bus.llm_adapters.llm_failover import (
            CONSTITUTIONAL_HASH,
            LLM_CIRCUIT_CONFIGS,
            FailoverEvent,
            HealthMetrics,
            HedgedRequest,
            LLMFailoverOrchestrator,
            LLMProviderType,
            ProactiveFailoverManager,
            ProviderHealthScore,
            ProviderHealthScorer,
            ProviderWarmupManager,
            RequestHedgingManager,
            WarmupResult,
            get_llm_circuit_config,
            get_llm_failover_orchestrator,
            reset_llm_failover_orchestrator,
        )
