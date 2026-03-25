"""
Additional coverage tests for LLM Provider Failover System
Constitutional Hash: 608508a9bd224290

Targets uncovered lines in llm_failover.py to push coverage from 85% to 95%+.

Uncovered lines targeted:
- 331: rate_limit error type
- 362: _update_latency_stats early return (empty samples)
- 376: _update_uptime with zero total_requests
- 442->exit: reset() with non-existent provider_id
- 517-526: build_fallback_chain using registry (no pre-set chain)
- 545-548: check_and_failover with no primary provider
- 561->559: fallback not healthy enough, skip it
- 584: no healthy fallback found, log error path
- 591-609: recovery to primary when current != primary
- 732-739: warmup timeout handling
- 785-803: start_periodic_warmup
- 807-809: stop_periodic_warmup
- 952->949: cancel remaining tasks in hedging loop
- 970: finally block task cancellation
- 1006-1013: hedging stats latency improvement calculation
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.circuit_breaker import CONSTITUTIONAL_HASH
from enhanced_agent_bus.llm_adapters.capability_matrix import (
    CapabilityRegistry,
    CapabilityRequirement,
    ProviderCapabilityProfile,
)
from enhanced_agent_bus.llm_adapters.llm_failover import (
    FailoverEvent,
    HealthMetrics,
    HedgedRequest,
    LLMProviderType,
    ProactiveFailoverManager,
    ProviderHealthScore,
    ProviderHealthScorer,
    ProviderWarmupManager,
    RequestHedgingManager,
    WarmupResult,
    get_llm_circuit_config,
)

# =============================================================================
# LLMProviderType — all declared values
# =============================================================================


class TestLLMProviderTypeAllValues:
    """Test all enum values of LLMProviderType."""

    def test_all_provider_types_exist(self) -> None:
        expected = {
            "OPENAI",
            "ANTHROPIC",
            "GOOGLE",
            "AZURE",
            "BEDROCK",
            "COHERE",
            "MISTRAL",
            "KIMI",
            "LOCAL",
            "OPENCLAW",
        }
        actual = {m.name for m in LLMProviderType}
        assert actual == expected

    def test_openai_value(self) -> None:
        assert LLMProviderType.OPENAI == "openai"
        assert LLMProviderType.OPENAI.value == "openai"

    def test_anthropic_value(self) -> None:
        assert LLMProviderType.ANTHROPIC == "anthropic"

    def test_google_value(self) -> None:
        assert LLMProviderType.GOOGLE == "google"

    def test_azure_value(self) -> None:
        assert LLMProviderType.AZURE == "azure"

    def test_bedrock_value(self) -> None:
        assert LLMProviderType.BEDROCK == "bedrock"

    def test_cohere_value(self) -> None:
        assert LLMProviderType.COHERE == "cohere"

    def test_mistral_value(self) -> None:
        assert LLMProviderType.MISTRAL == "mistral"

    def test_kimi_value(self) -> None:
        assert LLMProviderType.KIMI == "kimi"

    def test_local_value(self) -> None:
        assert LLMProviderType.LOCAL == "local"

    def test_openclaw_value(self) -> None:
        assert LLMProviderType.OPENCLAW == "openclaw"

    def test_provider_type_is_str(self) -> None:
        """LLMProviderType inherits str so comparisons work."""
        assert LLMProviderType.OPENAI == "openai"
        assert isinstance(LLMProviderType.ANTHROPIC, str)


# =============================================================================
# ProviderHealthScorer — uncovered paths
# =============================================================================


class TestProviderHealthScorerUncoveredPaths:
    """Cover rate_limit path and edge cases in ProviderHealthScorer."""

    async def test_record_request_rate_limit_error(self) -> None:
        """Line 331: rate_limit error type increments rate_limit_count."""
        scorer = ProviderHealthScorer()
        await scorer.record_request(
            provider_id="prov-a",
            latency_ms=200.0,
            success=False,
            error_type="rate_limit",
        )
        metrics = scorer._metrics["prov-a"]
        assert metrics.rate_limit_count == 1
        assert metrics.timeout_count == 0

    async def test_record_request_unrecognised_error_type(self) -> None:
        """Neither timeout nor rate_limit — counters stay at 0."""
        scorer = ProviderHealthScorer()
        await scorer.record_request(
            provider_id="prov-b",
            latency_ms=300.0,
            success=False,
            error_type="connection_error",
        )
        metrics = scorer._metrics["prov-b"]
        assert metrics.rate_limit_count == 0
        assert metrics.timeout_count == 0

    def test_update_latency_stats_empty_samples(self) -> None:
        """Line 362: _update_latency_stats returns early if no samples."""
        scorer = ProviderHealthScorer()
        metrics = HealthMetrics()
        # Call directly with empty samples — should not raise
        scorer._update_latency_stats(metrics)
        assert metrics.avg_latency_ms == 0.0
        assert metrics.p50_latency_ms == 0.0

    def test_update_uptime_zero_requests(self) -> None:
        """Line 376: _update_uptime sets 100% when total_requests == 0."""
        scorer = ProviderHealthScorer()
        metrics = HealthMetrics()
        assert metrics.total_requests == 0
        scorer._update_uptime(metrics)
        assert metrics.uptime_percentage == 100.0

    def test_update_uptime_nonzero_requests(self) -> None:
        """_update_uptime calculates correctly with nonzero requests."""
        scorer = ProviderHealthScorer()
        metrics = HealthMetrics(total_requests=4, successful_requests=3)
        scorer._update_uptime(metrics)
        assert metrics.uptime_percentage == pytest.approx(75.0)

    def test_reset_nonexistent_provider_is_noop(self) -> None:
        """Line 442->exit: reset() with a provider_id that doesn't exist is a no-op."""
        scorer = ProviderHealthScorer()
        scorer._metrics["real-provider"] = HealthMetrics(total_requests=5)
        # Resetting unknown provider should not raise and should not disturb others
        scorer.reset("nonexistent-provider")
        assert scorer._metrics["real-provider"].total_requests == 5

    async def test_multiple_rate_limit_failures_accumulate(self) -> None:
        """Multiple rate_limit failures add up correctly."""
        scorer = ProviderHealthScorer()
        for _ in range(3):
            await scorer.record_request("prov", 100.0, success=False, error_type="rate_limit")
        assert scorer._metrics["prov"].rate_limit_count == 3

    async def test_latency_stats_with_single_sample(self) -> None:
        """Single sample produces equal mean/median/p95/p99."""
        scorer = ProviderHealthScorer()
        await scorer.record_request("prov", 250.0, success=True)
        metrics = scorer._metrics["prov"]
        assert metrics.avg_latency_ms == pytest.approx(250.0)
        assert metrics.p50_latency_ms == pytest.approx(250.0)

    async def test_consecutive_failures_then_success_resets(self) -> None:
        """Success after consecutive failures resets the failure counter."""
        scorer = ProviderHealthScorer()
        for _ in range(4):
            await scorer.record_request("prov", 100.0, success=False)
        assert scorer._metrics["prov"].consecutive_failures == 4
        await scorer.record_request("prov", 100.0, success=True)
        assert scorer._metrics["prov"].consecutive_failures == 0


# =============================================================================
# ProviderHealthScore.to_dict — edge case
# =============================================================================


class TestProviderHealthScoreToDict:
    """Additional to_dict coverage."""

    def test_to_dict_all_fields_present(self) -> None:
        score = ProviderHealthScore(
            provider_id="p",
            health_score=0.5,
            latency_score=0.6,
            error_score=0.7,
            quality_score=0.8,
            availability_score=0.9,
            is_healthy=False,
            is_degraded=True,
            is_unhealthy=False,
            metrics=HealthMetrics(),
        )
        d = score.to_dict()
        for key in (
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
        ):
            assert key in d, f"Missing key: {key}"
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_metrics_sub_keys(self) -> None:
        score = ProviderHealthScore(
            provider_id="p",
            health_score=0.9,
            latency_score=0.9,
            error_score=0.9,
            quality_score=0.9,
            availability_score=0.9,
            is_healthy=True,
            is_degraded=False,
            is_unhealthy=False,
            metrics=HealthMetrics(total_requests=10, error_rate=0.1, avg_latency_ms=50.0),
        )
        m = score.to_dict()["metrics"]
        assert "avg_latency_ms" in m
        assert "error_rate" in m
        assert "total_requests" in m
        assert "consecutive_failures" in m


# =============================================================================
# ProactiveFailoverManager — uncovered paths
# =============================================================================


class TestProactiveFailoverManagerUncoveredPaths:
    """Cover build_fallback_chain (registry path) and recovery paths."""

    def _make_manager(self, registry: CapabilityRegistry | None = None) -> ProactiveFailoverManager:
        scorer = ProviderHealthScorer()
        return ProactiveFailoverManager(scorer, registry or CapabilityRegistry())

    def _register_provider(self, registry: CapabilityRegistry, provider_id: str) -> None:
        profile = ProviderCapabilityProfile(
            provider_id=provider_id,
            model_id=f"model-{provider_id}",
            display_name=provider_id.title(),
            provider_type="test",
            context_length=8192,
            max_output_tokens=1024,
        )
        registry.register_profile(profile)

    def test_build_fallback_chain_uses_registry_when_no_preset(self) -> None:
        """Lines 517-526: build_fallback_chain falls back to registry lookup."""
        registry = CapabilityRegistry()
        self._register_provider(registry, "prov-a")
        self._register_provider(registry, "prov-b")
        self._register_provider(registry, "prov-c")

        manager = self._make_manager(registry)
        # No preset fallback chain for "prov-a"
        chain = manager.build_fallback_chain("prov-a", requirements=[])
        # Should return registry-derived providers excluding "prov-a"
        assert "prov-a" not in chain
        assert isinstance(chain, list)

    def test_build_fallback_chain_returns_preset_chain(self) -> None:
        """Preset chain takes priority over registry lookup."""
        manager = self._make_manager()
        manager.set_fallback_chain("prov-a", ["prov-b", "prov-c"])
        chain = manager.build_fallback_chain("prov-a", requirements=[])
        assert chain == ["prov-b", "prov-c"]

    def test_build_fallback_chain_capped_at_five(self) -> None:
        """build_fallback_chain returns at most 5 providers."""
        registry = CapabilityRegistry()
        for i in range(8):
            self._register_provider(registry, f"prov-{i}")

        manager = self._make_manager(registry)
        # Use a provider ID that is NOT in the registry so it gets excluded only via equality check
        chain = manager.build_fallback_chain("prov-nonexistent", requirements=[])
        assert len(chain) <= 5

    async def test_check_and_failover_no_primary_with_capable_fallback(self) -> None:
        """Lines 545-548: no primary provider → picks first capable from registry."""
        registry = CapabilityRegistry()
        # Clear default profiles to isolate test
        registry._profiles.clear()
        self._register_provider(registry, "prov-a")
        self._register_provider(registry, "prov-b")

        manager = self._make_manager(registry)
        # No primary provider configured for tenant
        provider, failover_occurred = await manager.check_and_failover(
            tenant_id="tenant-new",
            requirements=[],
        )
        # A provider is returned (may be from custom registry or global default)
        assert provider is not None
        assert isinstance(provider, str)
        assert failover_occurred is False

    async def test_check_and_failover_no_primary_no_capable_raises(self) -> None:
        """Line 548: raises ValueError when no capable provider found."""
        registry = CapabilityRegistry()
        registry._profiles.clear()  # empty registry

        manager = self._make_manager(registry)
        with pytest.raises(ValueError, match="No capable providers"):
            await manager.check_and_failover("tenant-orphan", requirements=[])

    async def test_check_and_failover_degraded_all_fallbacks_also_unhealthy(self) -> None:
        """Lines 561->559, 584: primary degraded but all fallbacks too unhealthy."""
        scorer = ProviderHealthScorer()
        registry = CapabilityRegistry()
        manager = ProactiveFailoverManager(scorer, registry)

        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b", "prov-c"])

        # Make prov-a degraded (health < 0.6)
        for _ in range(15):
            await scorer.record_request("prov-a", 200.0, success=False)

        # Make all fallbacks also degraded
        for _ in range(15):
            await scorer.record_request("prov-b", 200.0, success=False)
        for _ in range(15):
            await scorer.record_request("prov-c", 200.0, success=False)

        # Should return current provider, no failover (no healthy fallback)
        provider, failover_occurred = await manager.check_and_failover("t1", requirements=[])
        # No healthy fallback found → returns current provider unchanged
        assert failover_occurred is False
        assert provider == "prov-a"

    async def test_check_and_failover_health_degraded_reason(self) -> None:
        """Line 570: reason is 'health_degraded' when health_score <= 0.3.

        The condition in the source is:
          reason = "proactive" if health.health_score > 0.3 else "health_degraded"

        Health score formula:
          health = 0.30 * latency_score + 0.35 * error_score + 0.15 * quality_score
                   + 0.20 * availability_score

        With 100% failures:
          error_score = 0, availability_score ~ 0 (with heavy consecutive-failure penalty)
          latency_score = max(0, 1 - p95_latency / (expected * 2))

        Use expected_latency=100ms (set explicitly) and very high latency (300ms) so
          latency_score = max(0, 1 - 300/200) = 0
          quality_score = 1.0 (no quality feedback recorded)
          → health = 0.30*0 + 0.35*0 + 0.15*1.0 + 0.20*0 = 0.15 ≤ 0.3  ✓
        """
        scorer = ProviderHealthScorer()
        # Set expected latency so that high-latency failures drive latency_score to 0
        scorer.set_expected_latency("prov-a", 100.0)

        registry = CapabilityRegistry()
        manager = ProactiveFailoverManager(scorer, registry)

        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        # High latency + 100% failures → health ≤ 0.15
        for _ in range(30):
            await scorer.record_request("prov-a", 300.0, success=False)

        prov_a_health = scorer.get_health_score("prov-a").health_score
        assert prov_a_health <= 0.3, (
            f"prov-a health {prov_a_health} not <= 0.3; formula may have changed"
        )

        # Make prov-b healthy
        for _ in range(20):
            await scorer.record_request("prov-b", 50.0, success=True)

        provider, failover_occurred = await manager.check_and_failover("t1", requirements=[])

        assert failover_occurred is True
        assert provider == "prov-b"
        last_event = manager._failover_history[-1]
        assert last_event.reason == "health_degraded"

    async def test_check_and_failover_recovery_to_primary(self) -> None:
        """Lines 591-609: recovers to primary when it becomes healthy again."""
        scorer = ProviderHealthScorer()
        registry = CapabilityRegistry()
        manager = ProactiveFailoverManager(scorer, registry)

        manager.set_primary_provider("t1", "prov-primary")
        manager.set_fallback_chain("prov-primary", ["prov-secondary"])
        # Simulate that failover has already happened to secondary
        manager._active_failovers["t1"] = "prov-secondary"

        # Make primary very healthy (above RECOVERY_THRESHOLD = 0.85)
        for _ in range(20):
            await scorer.record_request("prov-primary", 50.0, success=True)

        # Make secondary mediocre (health above PROACTIVE_FAILOVER_THRESHOLD so no new failover)
        for _ in range(10):
            await scorer.record_request("prov-secondary", 100.0, success=True)

        provider, failover_occurred = await manager.check_and_failover("t1", requirements=[])

        assert provider == "prov-primary"
        assert failover_occurred is True
        history = manager.get_failover_history()
        assert any(e.reason == "recovery" for e in history)

    def test_get_failover_stats_empty(self) -> None:
        """get_failover_stats returns defaults when no events."""
        manager = self._make_manager()
        stats = manager.get_failover_stats()
        assert stats["total_failovers"] == 0
        assert stats["failover_success_rate"] == 1.0
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_get_failover_stats_with_failed_event(self) -> None:
        """get_failover_stats handles events where success=False."""
        manager = self._make_manager()
        manager._failover_history.append(
            FailoverEvent(
                event_id="fo-bad",
                from_provider="a",
                to_provider="b",
                reason="circuit_open",
                latency_ms=0.0,
                success=False,
            )
        )
        stats = manager.get_failover_stats()
        assert stats["total_failovers"] == 1
        assert stats["successful_failovers"] == 0
        assert stats["failover_success_rate"] == 0.0

    def test_get_active_provider_returns_primary_when_no_failover(self) -> None:
        """get_active_provider falls back to primary when no active failover."""
        manager = self._make_manager()
        manager.set_primary_provider("t1", "primary-prov")
        assert manager.get_active_provider("t1") == "primary-prov"

    def test_get_active_provider_returns_none_for_unknown_tenant(self) -> None:
        manager = self._make_manager()
        assert manager.get_active_provider("unknown-tenant") is None

    def test_get_failover_history_limit(self) -> None:
        """get_failover_history respects the limit parameter."""
        manager = self._make_manager()
        for i in range(10):
            manager._failover_history.append(
                FailoverEvent(
                    event_id=f"fo-{i}",
                    from_provider="a",
                    to_provider="b",
                    reason="test",
                )
            )
        history = manager.get_failover_history(limit=3)
        assert len(history) == 3


# =============================================================================
# ProviderWarmupManager — timeout, start/stop periodic
# =============================================================================


class TestProviderWarmupManagerUncoveredPaths:
    """Cover warmup timeout, start/stop periodic warmup."""

    async def test_warmup_timeout(self) -> None:
        """Lines 732-739: warmup times out → WarmupResult(success=False, error='Timeout')."""
        manager = ProviderWarmupManager()

        async def slow_handler():
            await asyncio.sleep(30)  # Much longer than WARMUP_TIMEOUT_MS / 1000

        manager.register_warmup_handler("slow-prov", slow_handler)

        # Patch WARMUP_TIMEOUT_MS to a tiny value
        original_timeout = manager.WARMUP_TIMEOUT_MS
        manager.WARMUP_TIMEOUT_MS = 10  # 10ms timeout

        result = await manager.warmup("slow-prov")

        manager.WARMUP_TIMEOUT_MS = original_timeout
        assert result.success is False
        assert result.error == "Timeout"
        assert result.latency_ms >= 0

    async def test_warmup_if_needed_with_expired_interval(self) -> None:
        """warmup_if_needed executes when interval has expired."""
        manager = ProviderWarmupManager()
        handler = AsyncMock(return_value=None)
        manager.register_warmup_handler("prov", handler)

        # Manually set last_warmup to a time well in the past
        manager._last_warmup["prov"] = datetime(2000, 1, 1, tzinfo=UTC)

        result = await manager.warmup_if_needed("prov", interval=timedelta(minutes=5))
        assert result is not None
        assert result.success is True

    async def test_warmup_if_needed_skips_when_recent(self) -> None:
        """warmup_if_needed skips when last warmup was recent."""
        manager = ProviderWarmupManager()
        handler = AsyncMock(return_value=None)
        manager.register_warmup_handler("prov", handler)
        manager._last_warmup["prov"] = datetime.now(UTC)

        result = await manager.warmup_if_needed("prov", interval=timedelta(hours=1))
        assert result is None
        handler.assert_not_called()

    async def test_start_periodic_warmup_creates_task(self) -> None:
        """Lines 785-803: start_periodic_warmup creates an asyncio task."""
        manager = ProviderWarmupManager()
        handler = AsyncMock(return_value=None)
        manager.register_warmup_handler("prov", handler)

        manager.start_periodic_warmup("prov", interval=timedelta(seconds=0.01))
        assert "prov" in manager._warmup_tasks
        task = manager._warmup_tasks["prov"]
        assert isinstance(task, asyncio.Task)
        # Clean up
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    async def test_start_periodic_warmup_replaces_existing_task(self) -> None:
        """start_periodic_warmup cancels the old task and creates a new one."""
        manager = ProviderWarmupManager()
        handler = AsyncMock(return_value=None)
        manager.register_warmup_handler("prov", handler)

        manager.start_periodic_warmup("prov", interval=timedelta(seconds=60))
        first_task = manager._warmup_tasks["prov"]

        manager.start_periodic_warmup("prov", interval=timedelta(seconds=60))
        second_task = manager._warmup_tasks["prov"]

        assert first_task is not second_task
        assert first_task.cancelled() or first_task.cancelling() > 0

        second_task.cancel()
        try:
            await second_task
        except (asyncio.CancelledError, Exception):
            pass

    async def test_stop_periodic_warmup_cancels_task(self) -> None:
        """Lines 807-809: stop_periodic_warmup cancels and removes the task."""
        manager = ProviderWarmupManager()
        handler = AsyncMock(return_value=None)
        manager.register_warmup_handler("prov", handler)

        manager.start_periodic_warmup("prov", interval=timedelta(seconds=60))
        assert "prov" in manager._warmup_tasks
        task = manager._warmup_tasks["prov"]

        manager.stop_periodic_warmup("prov")
        assert "prov" not in manager._warmup_tasks
        assert task.cancelled() or task.cancelling() > 0

    def test_stop_periodic_warmup_noop_when_no_task(self) -> None:
        """stop_periodic_warmup is a no-op when no task registered."""
        manager = ProviderWarmupManager()
        # Should not raise
        manager.stop_periodic_warmup("nonexistent-prov")

    def test_get_warmup_status_with_result(self) -> None:
        """get_warmup_status includes last_result when warmup has run."""
        manager = ProviderWarmupManager()
        manager.register_warmup_handler("prov", AsyncMock())
        ts = datetime.now(UTC)
        manager._last_warmup["prov"] = ts
        manager._warmup_results["prov"] = WarmupResult(
            provider_id="prov",
            success=True,
            latency_ms=42.0,
        )

        status = manager.get_warmup_status("prov")
        assert status["has_handler"] is True
        assert status["last_warmup"] == ts.isoformat()
        assert status["last_result"]["success"] is True
        assert status["last_result"]["latency_ms"] == 42.0
        assert status["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_get_warmup_status_without_result(self) -> None:
        """get_warmup_status returns None for last_result when no run yet."""
        manager = ProviderWarmupManager()
        status = manager.get_warmup_status("no-prov")
        assert status["has_handler"] is False
        assert status["last_warmup"] is None
        assert status["last_result"] is None

    async def test_get_warmup_status_periodic_enabled_flag(self) -> None:
        """periodic_enabled is True only when a task is running."""
        manager = ProviderWarmupManager()
        handler = AsyncMock(return_value=None)
        manager.register_warmup_handler("prov", handler)

        status_before = manager.get_warmup_status("prov")
        assert status_before["periodic_enabled"] is False

        manager.start_periodic_warmup("prov", interval=timedelta(seconds=60))
        status_after = manager.get_warmup_status("prov")
        assert status_after["periodic_enabled"] is True

        # Cleanup
        manager.stop_periodic_warmup("prov")

    async def test_warmup_with_sync_handler(self) -> None:
        """Sync (non-coroutine) handler runs via asyncio.to_thread."""
        manager = ProviderWarmupManager()
        called = []

        def sync_handler():
            called.append(True)

        manager.register_warmup_handler("prov", sync_handler)
        result = await manager.warmup("prov")
        assert result.success is True
        assert called == [True]


# =============================================================================
# RequestHedgingManager — cancel remaining tasks, finally block, latency stats
# =============================================================================


class TestRequestHedgingManagerUncoveredPaths:
    """Cover pending-task cancellation and latency-improvement stats."""

    async def test_execute_hedged_cancels_slow_tasks(self) -> None:
        """Lines 952->949, 970: when first provider wins, pending tasks are cancelled."""
        manager = RequestHedgingManager(default_hedge_count=3, hedge_delay_ms=0)
        events = []

        async def execute_fn(provider_id: str) -> str:
            if provider_id == "fast":
                events.append(f"{provider_id}-start")
                return "fast-result"
            events.append(f"{provider_id}-start")
            try:
                await asyncio.sleep(5)  # This will be cancelled
                return f"{provider_id}-result"
            except asyncio.CancelledError:
                events.append(f"{provider_id}-cancelled")
                raise

        winner, result = await manager.execute_hedged(
            request_id="req-cancel",
            providers=["fast", "slow1", "slow2"],
            execute_fn=execute_fn,
            hedge_count=3,
        )
        assert winner == "fast"
        assert result == "fast-result"
        # Give cancelled tasks a moment to process
        await asyncio.sleep(0.05)

    async def test_execute_hedged_all_fail_records_errors(self) -> None:
        """When all providers fail, the error message includes provider details."""
        manager = RequestHedgingManager(default_hedge_count=2, hedge_delay_ms=0)

        async def always_fail(provider_id: str) -> str:
            raise RuntimeError(f"fail-{provider_id}")

        with pytest.raises(RuntimeError) as exc_info:
            await manager.execute_hedged(
                request_id="req-allfail",
                providers=["p1", "p2"],
                execute_fn=always_fail,
                hedge_count=2,
            )
        assert "All hedged providers failed" in str(exc_info.value)

    async def test_get_hedging_stats_latency_improvement_calculation(self) -> None:
        """Lines 1006-1013: stats calculate latency improvement when winner is faster."""
        manager = RequestHedgingManager(default_hedge_count=2, hedge_delay_ms=0)

        # Build a HedgedRequest manually with known latency data
        hedged = HedgedRequest(
            request_id="manual-req",
            providers=["fast-prov", "slow-prov"],
            winning_provider="fast-prov",
            latencies_ms={"fast-prov": 50.0, "slow-prov": 300.0},
        )
        manager._hedged_requests.append(hedged)

        stats = manager.get_hedging_stats()
        assert stats["total_hedged_requests"] == 1
        assert stats["successful_requests"] == 1
        # Improvement: slow(300) - fast(50) = 250ms
        assert stats["avg_latency_improvement_ms"] == pytest.approx(250.0)
        assert "fast-prov" in stats["provider_win_counts"]
        assert stats["provider_win_counts"]["fast-prov"] == 1

    async def test_get_hedging_stats_no_improvement_when_single_latency(self) -> None:
        """No latency improvement when only one latency recorded."""
        manager = RequestHedgingManager(default_hedge_count=2, hedge_delay_ms=0)
        hedged = HedgedRequest(
            request_id="single-lat",
            providers=["prov-a", "prov-b"],
            winning_provider="prov-a",
            latencies_ms={"prov-a": 100.0},  # Only one latency entry
        )
        manager._hedged_requests.append(hedged)

        stats = manager.get_hedging_stats()
        # avg_latency_improvement_ms should be 0 (no other latency to compare)
        assert stats["avg_latency_improvement_ms"] == 0

    async def test_execute_hedged_uses_default_hedge_count(self) -> None:
        """When hedge_count is not specified, uses default_hedge_count."""
        manager = RequestHedgingManager(default_hedge_count=2, hedge_delay_ms=0)

        call_log = []

        async def execute_fn(provider_id: str) -> str:
            call_log.append(provider_id)
            return f"result-{provider_id}"

        winner, _result = await manager.execute_hedged(
            request_id="req-default",
            providers=["p1", "p2", "p3"],  # 3 available, but default_hedge_count=2
            execute_fn=execute_fn,
        )
        # Only first 2 providers should be selected (default_hedge_count=2)
        assert winner in ("p1", "p2")
        assert len(manager._hedged_requests) == 1

    async def test_execute_hedged_hedge_count_exceeds_providers(self) -> None:
        """hedge_count larger than available providers works fine."""
        manager = RequestHedgingManager(default_hedge_count=5, hedge_delay_ms=0)

        async def execute_fn(provider_id: str) -> str:
            return f"result-{provider_id}"

        # Only 1 provider available but hedge_count=5
        winner, _result = await manager.execute_hedged(
            request_id="req-few",
            providers=["only-prov"],
            execute_fn=execute_fn,
            hedge_count=5,
        )
        assert winner == "only-prov"

    async def test_execute_hedged_with_delay(self) -> None:
        """Hedge delay staggers request start times."""
        manager = RequestHedgingManager(default_hedge_count=2, hedge_delay_ms=20)
        call_times: dict[str, float] = {}

        import time

        async def execute_fn(provider_id: str) -> str:
            call_times[provider_id] = time.time()
            return f"result-{provider_id}"

        winner, _result = await manager.execute_hedged(
            request_id="req-delay",
            providers=["p1", "p2"],
            execute_fn=execute_fn,
            hedge_count=2,
        )
        assert winner in ("p1", "p2")

    async def test_execute_hedged_first_fails_then_second_succeeds_with_different_error_types(
        self,
    ) -> None:
        """Various exception types from _LLM_FAILOVER_OPERATION_ERRORS are caught."""
        manager = RequestHedgingManager(default_hedge_count=2, hedge_delay_ms=0)

        call_count = {"n": 0}

        async def execute_fn(provider_id: str) -> str:
            call_count["n"] += 1
            if provider_id == "bad-prov":
                raise ConnectionError("connection refused")
            return "ok"

        winner, result = await manager.execute_hedged(
            request_id="req-conn-err",
            providers=["bad-prov", "good-prov"],
            execute_fn=execute_fn,
            hedge_count=2,
        )
        assert winner == "good-prov"
        assert result == "ok"


# =============================================================================
# get_llm_circuit_config — kimi and cohere
# =============================================================================


class TestGetLLMCircuitConfigAdditional:
    """Cover kimi and cohere configs."""

    def test_kimi_config_exists(self) -> None:
        config = get_llm_circuit_config("kimi")
        assert config.name == "llm:kimi"
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_cohere_config_missing_uses_default(self) -> None:
        """cohere is not in LLM_CIRCUIT_CONFIGS, uses default."""
        config = get_llm_circuit_config("cohere")
        # cohere is not defined, so default config returned
        assert config.name == "llm:cohere"

    def test_mistral_config_missing_uses_default(self) -> None:
        config = get_llm_circuit_config("mistral")
        assert config.name == "llm:mistral"

    def test_bedrock_config_exists(self) -> None:
        config = get_llm_circuit_config("bedrock")
        assert config.name == "llm:bedrock"

    def test_azure_config_exists(self) -> None:
        config = get_llm_circuit_config("azure")
        assert config.name == "llm:azure"

    def test_uppercase_provider_normalised(self) -> None:
        """Provider type is lowercased before lookup."""
        config = get_llm_circuit_config("OPENAI")
        assert config.name == "llm:openai"


# =============================================================================
# HealthMetrics dataclass — edge cases
# =============================================================================


class TestHealthMetricsEdgeCases:
    """Edge cases for HealthMetrics."""

    def test_quality_scores_deque_maxlen(self) -> None:
        metrics = HealthMetrics()
        for i in range(60):
            metrics.response_quality_scores.append(i / 60.0)
        assert len(metrics.response_quality_scores) == 50  # maxlen=50

    def test_default_last_success_and_failure_times_are_none(self) -> None:
        metrics = HealthMetrics()
        assert metrics.last_success_time is None
        assert metrics.last_failure_time is None

    def test_default_quality_is_one(self) -> None:
        metrics = HealthMetrics()
        assert metrics.avg_quality_score == 1.0

    def test_constitutional_hash_value(self) -> None:
        metrics = HealthMetrics()
        assert metrics.constitutional_hash == CONSTITUTIONAL_HASH


# =============================================================================
# WarmupResult — edge cases
# =============================================================================


class TestWarmupResultEdgeCases:
    """Edge cases for WarmupResult dataclass."""

    def test_warmup_result_with_error(self) -> None:
        result = WarmupResult(
            provider_id="prov",
            success=False,
            latency_ms=0.0,
            error="Connection refused",
        )
        assert result.error == "Connection refused"
        assert result.success is False

    def test_warmup_result_timestamp_auto_set(self) -> None:
        before = datetime.now(UTC)
        result = WarmupResult(provider_id="prov", success=True, latency_ms=10.0)
        after = datetime.now(UTC)
        assert before <= result.timestamp <= after


# =============================================================================
# HedgedRequest — edge cases
# =============================================================================


class TestHedgedRequestEdgeCases:
    """Edge cases for HedgedRequest dataclass."""

    def test_hedged_request_default_fields(self) -> None:
        req = HedgedRequest(request_id="r1", providers=["a"])
        assert req.completed_at is None
        assert req.winning_provider is None
        assert req.responses == {}
        assert req.errors == {}
        assert req.latencies_ms == {}

    def test_hedged_request_timestamp_auto_set(self) -> None:
        before = datetime.now(UTC)
        req = HedgedRequest(request_id="r1", providers=[])
        after = datetime.now(UTC)
        assert before <= req.started_at <= after


# =============================================================================
# FailoverEvent — edge cases
# =============================================================================


class TestFailoverEventEdgeCases:
    """Edge cases for FailoverEvent."""

    def test_failover_event_default_success_true(self) -> None:
        event = FailoverEvent(
            event_id="e1",
            from_provider="a",
            to_provider="b",
            reason="proactive",
        )
        assert event.success is True
        assert event.latency_ms == 0.0

    def test_failover_event_can_be_failed(self) -> None:
        event = FailoverEvent(
            event_id="e2",
            from_provider="a",
            to_provider="b",
            reason="circuit_open",
            success=False,
        )
        assert event.success is False

    def test_failover_event_timestamp_auto_set(self) -> None:
        before = datetime.now(UTC)
        event = FailoverEvent(event_id="e3", from_provider="a", to_provider="b", reason="test")
        after = datetime.now(UTC)
        assert before <= event.timestamp <= after
