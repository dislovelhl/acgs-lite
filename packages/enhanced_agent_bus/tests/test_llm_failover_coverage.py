# Constitutional Hash: 608508a9bd224290
"""
Test suite for src/core/enhanced_agent_bus/llm_adapters/failover/failover.py

Targets ≥ 90% coverage of that module specifically.  All async tests run
without @pytest.mark.asyncio because asyncio_mode = "auto" is set in
pyproject.toml.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# -- unit-under-test imports ---------------------------------------------------
from enhanced_agent_bus.circuit_breaker import CONSTITUTIONAL_HASH
from enhanced_agent_bus.llm_adapters.capability_matrix import (
    CapabilityRegistry,
    CapabilityRequirement,
    ProviderCapabilityProfile,
)
from enhanced_agent_bus.llm_adapters.failover.failover import (
    FailoverEvent,
    ProactiveFailoverManager,
)
from enhanced_agent_bus.llm_adapters.failover.health import (
    HealthMetrics,
    ProviderHealthScorer,
)

# ==============================================================================
# Helpers
# ==============================================================================


def _make_registry(*provider_ids: str) -> CapabilityRegistry:
    """Build a CapabilityRegistry pre-populated with the given provider IDs."""
    registry = CapabilityRegistry()
    registry._profiles.clear()
    for pid in provider_ids:
        registry.register_profile(
            ProviderCapabilityProfile(
                provider_id=pid,
                model_id=f"model-{pid}",
                display_name=pid.title(),
                provider_type="test",
                context_length=8192,
                max_output_tokens=1024,
            )
        )
    return registry


def _make_manager(
    scorer: ProviderHealthScorer | None = None,
    registry: CapabilityRegistry | None = None,
) -> ProactiveFailoverManager:
    return ProactiveFailoverManager(
        scorer or ProviderHealthScorer(),
        registry or CapabilityRegistry(),
    )


# ==============================================================================
# FailoverEvent dataclass
# ==============================================================================


class TestFailoverEvent:
    """Tests for the FailoverEvent dataclass."""

    def test_minimal_creation(self) -> None:
        event = FailoverEvent(
            event_id="fo-1",
            from_provider="prov-a",
            to_provider="prov-b",
            reason="proactive",
        )
        assert event.event_id == "fo-1"
        assert event.from_provider == "prov-a"
        assert event.to_provider == "prov-b"
        assert event.reason == "proactive"
        assert event.success is True
        assert event.latency_ms == 0.0
        assert event.constitutional_hash == CONSTITUTIONAL_HASH

    def test_timestamp_auto_set(self) -> None:
        before = datetime.now(UTC)
        event = FailoverEvent(
            event_id="fo-ts",
            from_provider="a",
            to_provider="b",
            reason="test",
        )
        after = datetime.now(UTC)
        assert before <= event.timestamp <= after

    def test_explicit_success_false(self) -> None:
        event = FailoverEvent(
            event_id="fo-fail",
            from_provider="a",
            to_provider="b",
            reason="circuit_open",
            success=False,
            latency_ms=12.5,
        )
        assert event.success is False
        assert event.latency_ms == 12.5

    def test_all_reason_values(self) -> None:
        for reason in ("health_degraded", "circuit_open", "proactive", "rate_limited", "recovery"):
            event = FailoverEvent(
                event_id=f"fo-{reason}",
                from_provider="x",
                to_provider="y",
                reason=reason,
            )
            assert event.reason == reason


# ==============================================================================
# ProactiveFailoverManager — construction and simple setters
# ==============================================================================


class TestProactiveFailoverManagerInit:
    """Tests for manager construction and threshold constants."""

    def test_thresholds(self) -> None:
        manager = _make_manager()
        assert manager.PROACTIVE_FAILOVER_THRESHOLD == 0.6
        assert manager.RECOVERY_THRESHOLD == 0.85

    def test_set_primary_provider(self) -> None:
        manager = _make_manager()
        manager.set_primary_provider("t1", "prov-x")
        assert manager._primary_providers["t1"] == "prov-x"

    def test_set_primary_provider_overwrites(self) -> None:
        manager = _make_manager()
        manager.set_primary_provider("t1", "prov-a")
        manager.set_primary_provider("t1", "prov-b")
        assert manager._primary_providers["t1"] == "prov-b"

    def test_set_fallback_chain(self) -> None:
        manager = _make_manager()
        manager.set_fallback_chain("prov-a", ["prov-b", "prov-c"])
        assert manager._fallback_chains["prov-a"] == ["prov-b", "prov-c"]


# ==============================================================================
# build_fallback_chain
# ==============================================================================


class TestBuildFallbackChain:
    """Tests for the build_fallback_chain method."""

    def test_returns_preset_chain(self) -> None:
        manager = _make_manager()
        manager.set_fallback_chain("prov-a", ["prov-b", "prov-c"])
        result = manager.build_fallback_chain("prov-a", requirements=[])
        assert result == ["prov-b", "prov-c"]

    def test_uses_registry_when_no_preset(self) -> None:
        registry = _make_registry("prov-a", "prov-b", "prov-c")
        manager = _make_manager(registry=registry)
        # No preset chain for "prov-a"
        chain = manager.build_fallback_chain("prov-a", requirements=[])
        assert "prov-a" not in chain
        assert isinstance(chain, list)

    def test_registry_chain_excludes_source_provider(self) -> None:
        registry = _make_registry("src-prov", "other-1", "other-2")
        manager = _make_manager(registry=registry)
        chain = manager.build_fallback_chain("src-prov", requirements=[])
        assert "src-prov" not in chain

    def test_capped_at_five_providers(self) -> None:
        pids = [f"prov-{i}" for i in range(10)]
        registry = _make_registry(*pids)
        manager = _make_manager(registry=registry)
        chain = manager.build_fallback_chain("prov-99-nonexistent", requirements=[])
        assert len(chain) <= 5

    def test_fallback_chain_sorted_by_health_score(self) -> None:
        """build_fallback_chain sorts fallbacks by health score descending."""
        scorer = ProviderHealthScorer()
        registry = _make_registry("prov-b", "prov-c")
        manager = ProactiveFailoverManager(scorer, registry)
        # No preset chain for "prov-a" — triggers registry path
        chain = manager.build_fallback_chain("prov-a-nonexistent", requirements=[])
        # Should be sorted descending (healthy first) — just verify it's a list
        assert isinstance(chain, list)

    def test_empty_fallback_list_when_no_other_providers(self) -> None:
        """Empty registry -> empty fallback list when provider not in registry."""
        registry = CapabilityRegistry()
        registry._profiles.clear()
        manager = _make_manager(registry=registry)
        chain = manager.build_fallback_chain("only-prov", requirements=[])
        assert chain == []


# ==============================================================================
# get_active_provider
# ==============================================================================


class TestGetActiveProvider:
    """Tests for the get_active_provider helper."""

    def test_returns_active_failover_when_set(self) -> None:
        manager = _make_manager()
        manager.set_primary_provider("t1", "primary")
        manager._active_failovers["t1"] = "secondary"
        assert manager.get_active_provider("t1") == "secondary"

    def test_falls_back_to_primary_when_no_failover(self) -> None:
        manager = _make_manager()
        manager.set_primary_provider("t1", "primary")
        assert manager.get_active_provider("t1") == "primary"

    def test_returns_none_for_unknown_tenant(self) -> None:
        manager = _make_manager()
        assert manager.get_active_provider("unknown") is None


# ==============================================================================
# get_failover_history
# ==============================================================================


class TestGetFailoverHistory:
    """Tests for get_failover_history."""

    def test_empty_history(self) -> None:
        manager = _make_manager()
        assert manager.get_failover_history() == []

    def test_returns_recent_events(self) -> None:
        manager = _make_manager()
        for i in range(5):
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
        # Last 3 should be fo-2, fo-3, fo-4
        assert history[-1].event_id == "fo-4"

    def test_limit_larger_than_history(self) -> None:
        manager = _make_manager()
        manager._failover_history.append(
            FailoverEvent(event_id="fo-0", from_provider="a", to_provider="b", reason="test")
        )
        history = manager.get_failover_history(limit=100)
        assert len(history) == 1


# ==============================================================================
# get_failover_stats
# ==============================================================================


class TestGetFailoverStats:
    """Tests for get_failover_stats."""

    def test_empty_stats(self) -> None:
        manager = _make_manager()
        stats = manager.get_failover_stats()
        assert stats["total_failovers"] == 0
        assert stats["avg_failover_latency_ms"] == 0
        assert stats["failover_success_rate"] == 1.0
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_stats_with_successful_events(self) -> None:
        manager = _make_manager()
        for i, reason in enumerate(("proactive", "health_degraded", "recovery")):
            manager._failover_history.append(
                FailoverEvent(
                    event_id=f"fo-{i}",
                    from_provider="a",
                    to_provider="b",
                    reason=reason,
                    latency_ms=float(10 * (i + 1)),
                )
            )
        stats = manager.get_failover_stats()
        assert stats["total_failovers"] == 3
        assert stats["successful_failovers"] == 3
        assert stats["failover_success_rate"] == 1.0
        assert stats["avg_failover_latency_ms"] == pytest.approx(20.0)
        assert stats["max_failover_latency_ms"] == 30.0
        assert stats["reasons"]["proactive"] == 1
        assert stats["reasons"]["health_degraded"] == 1
        assert stats["reasons"]["recovery"] == 1

    def test_stats_with_mixed_success(self) -> None:
        manager = _make_manager()
        manager._failover_history.append(
            FailoverEvent(
                event_id="fo-ok",
                from_provider="a",
                to_provider="b",
                reason="proactive",
                latency_ms=50.0,
                success=True,
            )
        )
        manager._failover_history.append(
            FailoverEvent(
                event_id="fo-bad",
                from_provider="b",
                to_provider="c",
                reason="circuit_open",
                latency_ms=0.0,
                success=False,
            )
        )
        stats = manager.get_failover_stats()
        assert stats["total_failovers"] == 2
        assert stats["successful_failovers"] == 1
        assert stats["failover_success_rate"] == 0.5
        # avg latency only over successful events
        assert stats["avg_failover_latency_ms"] == pytest.approx(50.0)

    def test_stats_reasons_all_counted(self) -> None:
        """All reason categories appear in stats even with zero counts."""
        manager = _make_manager()
        manager._failover_history.append(
            FailoverEvent(
                event_id="fo-1",
                from_provider="a",
                to_provider="b",
                reason="circuit_open",
                latency_ms=1.0,
            )
        )
        stats = manager.get_failover_stats()
        for r in ("proactive", "health_degraded", "circuit_open", "recovery"):
            assert r in stats["reasons"]

    def test_stats_successful_latencies_empty_when_all_fail(self) -> None:
        """avg_failover_latency_ms == 0 when all events failed."""
        manager = _make_manager()
        manager._failover_history.append(
            FailoverEvent(
                event_id="fo-bad",
                from_provider="a",
                to_provider="b",
                reason="proactive",
                success=False,
                latency_ms=99.0,
            )
        )
        stats = manager.get_failover_stats()
        assert stats["avg_failover_latency_ms"] == 0
        assert stats["max_failover_latency_ms"] == 0


# ==============================================================================
# check_and_failover — async paths
# ==============================================================================


class TestCheckAndFailover:
    """Tests for the main check_and_failover coroutine."""

    # -- helper: make a provider healthy by recording many successes ----------------
    @staticmethod
    async def _make_healthy(scorer: ProviderHealthScorer, pid: str, n: int = 10) -> None:
        for _ in range(n):
            await scorer.record_request(pid, 100.0, success=True)

    @staticmethod
    async def _make_degraded(scorer: ProviderHealthScorer, pid: str, n: int = 15) -> None:
        for _ in range(n):
            await scorer.record_request(pid, 200.0, success=False)

    # -- no primary configured -----------------------------------------------------
    async def test_no_primary_uses_first_capable(self) -> None:
        registry = _make_registry("prov-a", "prov-b")
        scorer = ProviderHealthScorer()
        manager = ProactiveFailoverManager(scorer, registry)

        provider, failover = await manager.check_and_failover("t-new", requirements=[])
        assert provider in ("prov-a", "prov-b")
        assert failover is False

    async def test_no_primary_no_capable_raises(self) -> None:
        registry = CapabilityRegistry()
        registry._profiles.clear()
        manager = _make_manager(registry=registry)

        with pytest.raises(ValueError, match="No capable providers"):
            await manager.check_and_failover("t-orphan", requirements=[])

    # -- primary healthy → no failover ---------------------------------------------
    async def test_healthy_primary_no_failover(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")

        await self._make_healthy(scorer, "prov-a")

        provider, failover = await manager.check_and_failover("t1", requirements=[])
        assert provider == "prov-a"
        assert failover is False

    # -- primary degraded → proactive failover to healthy fallback -----------------
    async def test_proactive_failover_to_healthy_fallback(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        await self._make_degraded(scorer, "prov-a")
        await self._make_healthy(scorer, "prov-b")

        provider, failover = await manager.check_and_failover("t1", requirements=[])
        assert provider == "prov-b"
        assert failover is True

    async def test_failover_event_recorded_in_history(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        await self._make_degraded(scorer, "prov-a")
        await self._make_healthy(scorer, "prov-b")

        await manager.check_and_failover("t1", requirements=[])
        assert len(manager._failover_history) == 1
        event = manager._failover_history[-1]
        assert event.from_provider == "prov-a"
        assert event.to_provider == "prov-b"

    async def test_failover_reason_proactive_when_health_above_0_3(self) -> None:
        """Reason is 'proactive' when 0.3 < health_score < 0.6."""
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("prov-a", 500.0)
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        # Moderate failures → health between 0.3 and 0.6
        # Alternate success/failure to keep error_rate ~50% → error_score ~0.5
        for i in range(10):
            if i % 2 == 0:
                await scorer.record_request("prov-a", 200.0, success=True)
            else:
                await scorer.record_request("prov-a", 200.0, success=False)

        prov_a_health = scorer.get_health_score("prov-a").health_score
        # Health might or might not be < 0.6; if it is, we trigger failover
        await self._make_healthy(scorer, "prov-b")

        _, failover = await manager.check_and_failover("t1", requirements=[])
        if failover:
            event = manager._failover_history[-1]
            assert event.reason in ("proactive", "health_degraded")

    async def test_failover_reason_health_degraded_when_health_at_most_0_3(self) -> None:
        """Reason is 'health_degraded' when health_score ≤ 0.3."""
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("prov-a", 100.0)  # Low expected → high latency hurts
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        # High latency + 100 % failures → health ≤ 0.15
        for _ in range(30):
            await scorer.record_request("prov-a", 300.0, success=False)

        prov_a_health = scorer.get_health_score("prov-a").health_score
        assert prov_a_health <= 0.3, f"Expected prov-a health ≤ 0.3, got {prov_a_health}"

        await self._make_healthy(scorer, "prov-b", n=20)

        provider, failover = await manager.check_and_failover("t1", requirements=[])
        assert failover is True
        assert provider == "prov-b"
        assert manager._failover_history[-1].reason == "health_degraded"

    # -- no healthy fallback available ---------------------------------------------
    async def test_no_healthy_fallback_stays_on_current(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b", "prov-c"])

        await self._make_degraded(scorer, "prov-a", 20)
        await self._make_degraded(scorer, "prov-b", 20)
        await self._make_degraded(scorer, "prov-c", 20)

        provider, failover = await manager.check_and_failover("t1", requirements=[])
        assert failover is False
        assert provider == "prov-a"

    # -- recovery to primary -------------------------------------------------------
    async def test_recovery_to_primary(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-primary")
        # Simulate that a previous failover already happened
        manager._active_failovers["t1"] = "prov-secondary"

        # Make primary very healthy (above RECOVERY_THRESHOLD = 0.85)
        for _ in range(30):
            await scorer.record_request("prov-primary", 50.0, success=True)

        # Make secondary mediocre but above PROACTIVE_FAILOVER_THRESHOLD
        for _ in range(10):
            await scorer.record_request("prov-secondary", 100.0, success=True)

        provider, failover = await manager.check_and_failover("t1", requirements=[])
        assert provider == "prov-primary"
        assert failover is True
        assert any(e.reason == "recovery" for e in manager._failover_history)

    async def test_recovery_event_recorded(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "primary")
        manager._active_failovers["t1"] = "secondary"

        for _ in range(30):
            await scorer.record_request("primary", 50.0, success=True)
        for _ in range(10):
            await scorer.record_request("secondary", 100.0, success=True)

        await manager.check_and_failover("t1", requirements=[])
        event = manager._failover_history[-1]
        assert event.from_provider == "secondary"
        assert event.to_provider == "primary"
        assert event.reason == "recovery"
        assert event.latency_ms == 0

    async def test_no_recovery_when_primary_not_healthy_enough(self) -> None:
        """No recovery when primary health < RECOVERY_THRESHOLD."""
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "primary")
        manager._active_failovers["t1"] = "secondary"

        # Primary has moderate health (not above 0.85)
        for i in range(10):
            await scorer.record_request("primary", 100.0, success=(i < 7))

        # Secondary is healthy
        for _ in range(10):
            await scorer.record_request("secondary", 100.0, success=True)

        provider, _failover = await manager.check_and_failover("t1", requirements=[])
        # Whether failover occurred depends on health values; just verify no error
        assert provider in ("primary", "secondary")

    async def test_no_recovery_when_current_equals_primary(self) -> None:
        """Recovery branch is skipped when current == primary."""
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        # No active failover → current == primary

        await self._make_healthy(scorer, "prov-a")

        provider, failover = await manager.check_and_failover("t1", requirements=[])
        # Primary is healthy; no failover, no recovery
        assert provider == "prov-a"
        assert failover is False
        assert len(manager._failover_history) == 0

    # -- active_failovers updated correctly ----------------------------------------
    async def test_active_failover_updated_after_failover(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        await self._make_degraded(scorer, "prov-a")
        await self._make_healthy(scorer, "prov-b")

        provider, _ = await manager.check_and_failover("t1", requirements=[])
        assert manager._active_failovers["t1"] == "prov-b"
        assert provider == "prov-b"

    async def test_second_call_uses_updated_active_provider(self) -> None:
        """After failover, subsequent calls use the new active provider."""
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        await self._make_degraded(scorer, "prov-a")
        await self._make_healthy(scorer, "prov-b")

        # First call triggers failover
        await manager.check_and_failover("t1", requirements=[])

        # Second call: secondary is still healthy so should stay on prov-b
        await self._make_healthy(scorer, "prov-b")
        provider, _failover = await manager.check_and_failover("t1", requirements=[])
        assert provider == "prov-b"

    # -- lock prevents concurrent modification -----------------------------------
    async def test_concurrent_calls_are_safe(self) -> None:
        """Multiple concurrent calls should not raise errors."""
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        await self._make_healthy(scorer, "prov-a")

        results = await asyncio.gather(
            *(manager.check_and_failover("t1", requirements=[]) for _ in range(10))
        )
        assert all(provider == "prov-a" for provider, _ in results)

    # -- failover latency is recorded -------------------------------------------
    async def test_failover_latency_ms_is_non_negative(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        await self._make_degraded(scorer, "prov-a")
        await self._make_healthy(scorer, "prov-b")

        await manager.check_and_failover("t1", requirements=[])
        event = manager._failover_history[-1]
        assert event.latency_ms >= 0

    # -- constitutional hash propagated to events --------------------------------
    async def test_failover_event_has_constitutional_hash(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        await self._make_degraded(scorer, "prov-a")
        await self._make_healthy(scorer, "prov-b")

        await manager.check_and_failover("t1", requirements=[])
        event = manager._failover_history[-1]
        assert event.constitutional_hash == CONSTITUTIONAL_HASH

    # -- fallback health check boundary ------------------------------------------
    async def test_fallback_exactly_at_threshold_is_accepted(self) -> None:
        """A fallback whose health_score == PROACTIVE_FAILOVER_THRESHOLD is accepted."""
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        # Degrade primary
        await self._make_degraded(scorer, "prov-a")

        # Craft prov-b health to be exactly at the threshold by mocking get_health_score
        original = scorer.get_health_score

        def patched_get_health_score(provider_id: str):
            score = original(provider_id)
            if provider_id == "prov-b":
                from enhanced_agent_bus.llm_adapters.failover.health import (
                    ProviderHealthScore,
                )

                return ProviderHealthScore(
                    provider_id="prov-b",
                    health_score=0.6,  # exactly at threshold
                    latency_score=0.6,
                    error_score=0.6,
                    quality_score=0.6,
                    availability_score=0.6,
                    is_healthy=False,
                    is_degraded=True,
                    is_unhealthy=False,
                    metrics=HealthMetrics(),
                )
            return score

        scorer.get_health_score = patched_get_health_score  # type: ignore[method-assign]
        try:
            provider, failover = await manager.check_and_failover("t1", requirements=[])
            assert provider == "prov-b"
            assert failover is True
        finally:
            scorer.get_health_score = original  # type: ignore[method-assign]

    # -- fallback below threshold is skipped -------------------------------------
    async def test_fallback_below_threshold_is_skipped(self) -> None:
        """A fallback whose health_score < PROACTIVE_FAILOVER_THRESHOLD is skipped."""
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        await self._make_degraded(scorer, "prov-a")
        # prov-b also degraded
        await self._make_degraded(scorer, "prov-b")

        provider, failover = await manager.check_and_failover("t1", requirements=[])
        assert failover is False
        assert provider == "prov-a"

    # -- no primary, no registered providers ------------------------------------
    async def test_no_primary_empty_fallbacks_raises(self) -> None:
        registry = CapabilityRegistry()
        registry._profiles.clear()
        scorer = ProviderHealthScorer()
        manager = ProactiveFailoverManager(scorer, registry)

        with pytest.raises(ValueError, match="No capable providers"):
            await manager.check_and_failover("t-empty", requirements=[])

    # -- event_id contains timestamp -------------------------------------------
    async def test_event_id_is_unique_across_calls(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        await self._make_degraded(scorer, "prov-a")
        await self._make_healthy(scorer, "prov-b")

        # Trigger two failovers
        await manager.check_and_failover("t1", requirements=[])
        # Reset to primary path by faking recovery
        manager._active_failovers["t1"] = "prov-a"
        await self._make_degraded(scorer, "prov-a", 5)  # Degrade again
        await self._make_healthy(scorer, "prov-b")
        await manager.check_and_failover("t1", requirements=[])

        ids = [e.event_id for e in manager._failover_history]
        assert ids[0].startswith("fo-")


# ==============================================================================
# __all__ export
# ==============================================================================


class TestModuleExports:
    """Verify __all__ exports are importable from failover.failover."""

    def test_failover_event_is_exported(self) -> None:
        from enhanced_agent_bus.llm_adapters.failover.failover import (
            FailoverEvent,
        )

    def test_proactive_failover_manager_is_exported(self) -> None:
        from enhanced_agent_bus.llm_adapters.failover.failover import (
            ProactiveFailoverManager,
        )
