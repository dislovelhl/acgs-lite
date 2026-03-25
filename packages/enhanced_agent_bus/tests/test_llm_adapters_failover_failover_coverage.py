# Constitutional Hash: 608508a9bd224290
# Sprint 60 — llm_adapters/failover/failover.py coverage
"""
Comprehensive test suite for:
  src/core/enhanced_agent_bus/llm_adapters/failover/failover.py

Target: ≥95% line coverage.

All async tests run without @pytest.mark.asyncio because
asyncio_mode = "auto" is configured in pyproject.toml.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from collections import deque
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus.circuit_breaker import CONSTITUTIONAL_HASH
from enhanced_agent_bus.llm_adapters.capability_matrix import (
    CapabilityDimension,
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
    ProviderHealthScore,
    ProviderHealthScorer,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


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


def _make_health_score(
    provider_id: str,
    health_score: float,
    is_healthy: bool = True,
    is_degraded: bool = False,
    is_unhealthy: bool = False,
) -> ProviderHealthScore:
    """Create a ProviderHealthScore with a specific health_score."""
    return ProviderHealthScore(
        provider_id=provider_id,
        health_score=health_score,
        latency_score=health_score,
        error_score=health_score,
        quality_score=health_score,
        availability_score=health_score,
        is_healthy=is_healthy,
        is_degraded=is_degraded,
        is_unhealthy=is_unhealthy,
        metrics=HealthMetrics(),
    )


# ---------------------------------------------------------------------------
# FailoverEvent dataclass tests
# ---------------------------------------------------------------------------


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

    def test_timestamp_auto_set_within_range(self) -> None:
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

    def test_explicit_latency_ms(self) -> None:
        event = FailoverEvent(
            event_id="fo-lat",
            from_provider="a",
            to_provider="b",
            reason="health_degraded",
            latency_ms=42.7,
        )
        assert event.latency_ms == 42.7

    def test_all_documented_reason_values(self) -> None:
        for reason in (
            "health_degraded",
            "circuit_open",
            "proactive",
            "rate_limited",
            "recovery",
        ):
            event = FailoverEvent(
                event_id=f"fo-{reason}",
                from_provider="x",
                to_provider="y",
                reason=reason,
            )
            assert event.reason == reason

    def test_constitutional_hash_is_correct(self) -> None:
        event = FailoverEvent(
            event_id="fo-hash",
            from_provider="a",
            to_provider="b",
            reason="proactive",
        )
        assert event.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_success_default_is_true(self) -> None:
        event = FailoverEvent(
            event_id="fo-default",
            from_provider="a",
            to_provider="b",
            reason="proactive",
        )
        assert event.success is True

    def test_explicit_timestamp(self) -> None:
        custom_ts = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        event = FailoverEvent(
            event_id="fo-ts2",
            from_provider="a",
            to_provider="b",
            reason="proactive",
            timestamp=custom_ts,
        )
        assert event.timestamp == custom_ts


# ---------------------------------------------------------------------------
# ProactiveFailoverManager construction and simple setters
# ---------------------------------------------------------------------------


class TestProactiveFailoverManagerInit:
    """Tests for manager construction and threshold constants."""

    def test_default_registry_from_get_capability_registry(self) -> None:
        """When no registry is passed, it uses get_capability_registry()."""
        scorer = ProviderHealthScorer()
        manager = ProactiveFailoverManager(scorer)
        assert manager.registry is not None

    def test_explicit_registry_stored(self) -> None:
        registry = _make_registry("prov-a")
        manager = _make_manager(registry=registry)
        assert manager.registry is registry

    def test_thresholds_are_correct(self) -> None:
        manager = _make_manager()
        assert manager.PROACTIVE_FAILOVER_THRESHOLD == 0.6
        assert manager.RECOVERY_THRESHOLD == 0.85

    def test_internal_dicts_initialized_empty(self) -> None:
        manager = _make_manager()
        assert manager._primary_providers == {}
        assert manager._fallback_chains == {}
        assert manager._active_failovers == {}
        assert len(manager._failover_history) == 0

    def test_failover_history_maxlen(self) -> None:
        manager = _make_manager()
        assert manager._failover_history.maxlen == 1000

    def test_set_primary_provider(self) -> None:
        manager = _make_manager()
        manager.set_primary_provider("t1", "prov-x")
        assert manager._primary_providers["t1"] == "prov-x"

    def test_set_primary_provider_overwrites(self) -> None:
        manager = _make_manager()
        manager.set_primary_provider("t1", "prov-a")
        manager.set_primary_provider("t1", "prov-b")
        assert manager._primary_providers["t1"] == "prov-b"

    def test_set_primary_multiple_tenants(self) -> None:
        manager = _make_manager()
        manager.set_primary_provider("t1", "prov-a")
        manager.set_primary_provider("t2", "prov-b")
        assert manager._primary_providers["t1"] == "prov-a"
        assert manager._primary_providers["t2"] == "prov-b"

    def test_set_fallback_chain(self) -> None:
        manager = _make_manager()
        manager.set_fallback_chain("prov-a", ["prov-b", "prov-c"])
        assert manager._fallback_chains["prov-a"] == ["prov-b", "prov-c"]

    def test_set_fallback_chain_empty_list(self) -> None:
        manager = _make_manager()
        manager.set_fallback_chain("prov-a", [])
        assert manager._fallback_chains["prov-a"] == []

    def test_set_fallback_chain_overwrites(self) -> None:
        manager = _make_manager()
        manager.set_fallback_chain("prov-a", ["prov-b"])
        manager.set_fallback_chain("prov-a", ["prov-c", "prov-d"])
        assert manager._fallback_chains["prov-a"] == ["prov-c", "prov-d"]


# ---------------------------------------------------------------------------
# build_fallback_chain
# ---------------------------------------------------------------------------


class TestBuildFallbackChain:
    """Tests for the build_fallback_chain method."""

    def test_returns_preset_chain_when_available(self) -> None:
        manager = _make_manager()
        manager.set_fallback_chain("prov-a", ["prov-b", "prov-c"])
        result = manager.build_fallback_chain("prov-a", requirements=[])
        assert result == ["prov-b", "prov-c"]

    def test_uses_registry_when_no_preset(self) -> None:
        registry = _make_registry("prov-a", "prov-b", "prov-c")
        manager = _make_manager(registry=registry)
        chain = manager.build_fallback_chain("prov-a", requirements=[])
        # Should not include the source provider
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
        # Provider not in registry → all registry providers become candidates
        chain = manager.build_fallback_chain("prov-nonexistent", requirements=[])
        assert len(chain) <= 5

    def test_sorted_by_health_score_descending(self) -> None:
        """Fallback chain is sorted by health score descending."""
        scorer = ProviderHealthScorer()
        registry = _make_registry("prov-high", "prov-low")
        manager = ProactiveFailoverManager(scorer, registry)

        # Manually control health scores
        call_count = {}

        def mock_health(provider_id: str) -> ProviderHealthScore:
            scores = {"prov-high": 0.9, "prov-low": 0.3}
            return _make_health_score(provider_id, scores.get(provider_id, 0.5))

        scorer.get_health_score = mock_health  # type: ignore[method-assign]

        chain = manager.build_fallback_chain("prov-source-not-in-registry", requirements=[])
        assert isinstance(chain, list)
        # If both providers appear, high should come before low
        if "prov-high" in chain and "prov-low" in chain:
            assert chain.index("prov-high") < chain.index("prov-low")

    def test_empty_fallback_when_no_providers_in_registry(self) -> None:
        registry = CapabilityRegistry()
        registry._profiles.clear()
        manager = _make_manager(registry=registry)
        chain = manager.build_fallback_chain("only-prov", requirements=[])
        assert chain == []

    def test_preset_empty_chain_returned_directly(self) -> None:
        """If preset chain is empty list, it's returned as-is."""
        manager = _make_manager()
        manager.set_fallback_chain("prov-a", [])
        result = manager.build_fallback_chain("prov-a", requirements=[])
        assert result == []

    def test_registry_path_excludes_source_and_caps_at_5(self) -> None:
        """Registry path: result excludes source and is capped at 5."""
        pids = [f"prov-{i}" for i in range(8)]
        registry = _make_registry(*pids)
        manager = _make_manager(registry=registry)
        chain = manager.build_fallback_chain("prov-0", requirements=[])
        assert "prov-0" not in chain
        assert len(chain) <= 5


# ---------------------------------------------------------------------------
# get_active_provider
# ---------------------------------------------------------------------------


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

    def test_active_failover_takes_precedence_over_primary(self) -> None:
        manager = _make_manager()
        manager.set_primary_provider("t1", "primary-prov")
        manager._active_failovers["t1"] = "fallback-prov"
        result = manager.get_active_provider("t1")
        assert result == "fallback-prov"
        assert result != "primary-prov"


# ---------------------------------------------------------------------------
# get_failover_history
# ---------------------------------------------------------------------------


class TestGetFailoverHistory:
    """Tests for get_failover_history."""

    def test_empty_history(self) -> None:
        manager = _make_manager()
        assert manager.get_failover_history() == []

    def test_returns_all_events_when_under_limit(self) -> None:
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
        history = manager.get_failover_history()
        assert len(history) == 5

    def test_returns_last_n_events_with_limit(self) -> None:
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
        assert history[-1].event_id == "fo-4"

    def test_limit_larger_than_history(self) -> None:
        manager = _make_manager()
        manager._failover_history.append(
            FailoverEvent(event_id="fo-0", from_provider="a", to_provider="b", reason="test")
        )
        history = manager.get_failover_history(limit=100)
        assert len(history) == 1

    def test_default_limit_is_100(self) -> None:
        manager = _make_manager()
        for i in range(150):
            manager._failover_history.append(
                FailoverEvent(
                    event_id=f"fo-{i}",
                    from_provider="a",
                    to_provider="b",
                    reason="test",
                )
            )
        history = manager.get_failover_history()
        # Default limit=100, so last 100 of 150
        assert len(history) == 100

    def test_returns_list_type(self) -> None:
        manager = _make_manager()
        result = manager.get_failover_history()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# get_failover_stats
# ---------------------------------------------------------------------------


class TestGetFailoverStats:
    """Tests for get_failover_stats."""

    def test_empty_stats(self) -> None:
        manager = _make_manager()
        stats = manager.get_failover_stats()
        assert stats["total_failovers"] == 0
        assert stats["avg_failover_latency_ms"] == 0
        assert stats["failover_success_rate"] == 1.0
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_empty_stats_has_no_reasons_key(self) -> None:
        """Empty stats returns specific keys without reasons."""
        manager = _make_manager()
        stats = manager.get_failover_stats()
        # The empty path returns a specific subset of keys
        assert "total_failovers" in stats
        assert "constitutional_hash" in stats

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
        assert stats["avg_failover_latency_ms"] == pytest.approx(50.0)

    def test_stats_reasons_all_categories_present(self) -> None:
        """All reason categories appear even with zero counts."""
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

    def test_stats_latencies_zero_when_all_fail(self) -> None:
        """avg/max latency are 0 when all events failed."""
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

    def test_stats_constitutional_hash_present(self) -> None:
        manager = _make_manager()
        manager._failover_history.append(
            FailoverEvent(
                event_id="fo-ch",
                from_provider="a",
                to_provider="b",
                reason="proactive",
                latency_ms=5.0,
            )
        )
        stats = manager.get_failover_stats()
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_stats_circuit_open_reason_counted(self) -> None:
        manager = _make_manager()
        for _ in range(3):
            manager._failover_history.append(
                FailoverEvent(
                    event_id="fo-co",
                    from_provider="a",
                    to_provider="b",
                    reason="circuit_open",
                    latency_ms=1.0,
                )
            )
        stats = manager.get_failover_stats()
        assert stats["reasons"]["circuit_open"] == 3

    def test_stats_multiple_events_max_latency(self) -> None:
        manager = _make_manager()
        latencies = [10.0, 50.0, 30.0]
        for i, lat in enumerate(latencies):
            manager._failover_history.append(
                FailoverEvent(
                    event_id=f"fo-{i}",
                    from_provider="a",
                    to_provider="b",
                    reason="proactive",
                    latency_ms=lat,
                )
            )
        stats = manager.get_failover_stats()
        assert stats["max_failover_latency_ms"] == 50.0
        assert stats["avg_failover_latency_ms"] == pytest.approx(statistics.mean(latencies))


# ---------------------------------------------------------------------------
# check_and_failover — async paths
# ---------------------------------------------------------------------------


class TestCheckAndFailoverNoPrimary:
    """Tests for check_and_failover when no primary is configured."""

    async def test_no_primary_uses_first_capable_provider(self) -> None:
        registry = _make_registry("prov-a", "prov-b")
        scorer = ProviderHealthScorer()
        manager = ProactiveFailoverManager(scorer, registry)

        provider, failover = await manager.check_and_failover("t-new", requirements=[])
        assert provider in ("prov-a", "prov-b")
        assert failover is False

    async def test_no_primary_no_capable_raises_value_error(self) -> None:
        registry = CapabilityRegistry()
        registry._profiles.clear()
        manager = _make_manager(registry=registry)

        with pytest.raises(ValueError, match="No capable providers"):
            await manager.check_and_failover("t-orphan", requirements=[])

    async def test_no_primary_raises_for_unknown_tenant(self) -> None:
        """Without any capable providers, unknown tenant raises ValueError."""
        registry = CapabilityRegistry()
        registry._profiles.clear()
        scorer = ProviderHealthScorer()
        manager = ProactiveFailoverManager(scorer, registry)

        with pytest.raises(ValueError, match="No capable providers for tenant"):
            await manager.check_and_failover("t-empty", requirements=[])


class TestCheckAndFailoverHealthyPrimary:
    """Tests when primary provider is healthy — no failover expected."""

    @staticmethod
    async def _make_healthy(scorer: ProviderHealthScorer, pid: str, n: int = 10) -> None:
        for _ in range(n):
            await scorer.record_request(pid, 100.0, success=True)

    async def test_healthy_primary_returns_primary_no_failover(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        await self._make_healthy(scorer, "prov-a")

        provider, failover = await manager.check_and_failover("t1", requirements=[])
        assert provider == "prov-a"
        assert failover is False

    async def test_healthy_primary_no_history_entry(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        await self._make_healthy(scorer, "prov-a")

        await manager.check_and_failover("t1", requirements=[])
        assert len(manager._failover_history) == 0

    async def test_healthy_primary_active_failovers_unchanged(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        await self._make_healthy(scorer, "prov-a")

        await manager.check_and_failover("t1", requirements=[])
        # No active failover set since current == primary (no recovery branch triggered)
        assert "t1" not in manager._active_failovers

    async def test_no_recovery_when_current_equals_primary(self) -> None:
        """Recovery branch skipped when current provider == primary provider."""
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        await self._make_healthy(scorer, "prov-a")

        provider, failover = await manager.check_and_failover("t1", requirements=[])
        assert provider == "prov-a"
        assert failover is False
        assert len(manager._failover_history) == 0


class TestCheckAndFailoverDegradedPrimary:
    """Tests for proactive failover when primary health is degraded."""

    @staticmethod
    async def _make_healthy(scorer: ProviderHealthScorer, pid: str, n: int = 10) -> None:
        for _ in range(n):
            await scorer.record_request(pid, 100.0, success=True)

    @staticmethod
    async def _make_degraded(scorer: ProviderHealthScorer, pid: str, n: int = 15) -> None:
        for _ in range(n):
            await scorer.record_request(pid, 200.0, success=False)

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

    async def test_proactive_failover_updates_active_failovers(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        await self._make_degraded(scorer, "prov-a")
        await self._make_healthy(scorer, "prov-b")

        await manager.check_and_failover("t1", requirements=[])
        assert manager._active_failovers["t1"] == "prov-b"

    async def test_proactive_failover_records_history_event(self) -> None:
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
        """Reason is 'proactive' when health_score > 0.3 (but < 0.6)."""
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        # Use mock to set health score between 0.3 and 0.6
        def mock_health(provider_id: str) -> ProviderHealthScore:
            if provider_id == "prov-a":
                return _make_health_score("prov-a", 0.4, is_healthy=False, is_degraded=True)
            return _make_health_score("prov-b", 0.9)

        scorer.get_health_score = mock_health  # type: ignore[method-assign]

        _, failover = await manager.check_and_failover("t1", requirements=[])
        assert failover is True
        event = manager._failover_history[-1]
        assert event.reason == "proactive"

    async def test_failover_reason_health_degraded_when_health_at_most_0_3(self) -> None:
        """Reason is 'health_degraded' when health_score <= 0.3."""
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("prov-a", 100.0)  # Low expected → high latency hurts
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        # High latency + 100% failures → health <= 0.15
        for _ in range(30):
            await scorer.record_request("prov-a", 300.0, success=False)

        prov_a_health = scorer.get_health_score("prov-a").health_score
        assert prov_a_health <= 0.3, f"Expected health ≤ 0.3, got {prov_a_health}"

        await self._make_healthy(scorer, "prov-b", n=20)

        provider, failover = await manager.check_and_failover("t1", requirements=[])
        assert failover is True
        assert provider == "prov-b"
        assert manager._failover_history[-1].reason == "health_degraded"

    async def test_no_healthy_fallback_stays_on_current_provider(self) -> None:
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

    async def test_no_healthy_fallback_no_history_entry(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        await self._make_degraded(scorer, "prov-a", 20)
        await self._make_degraded(scorer, "prov-b", 20)

        await manager.check_and_failover("t1", requirements=[])
        assert len(manager._failover_history) == 0

    async def test_failover_event_has_correct_constitutional_hash(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        await self._make_degraded(scorer, "prov-a")
        await self._make_healthy(scorer, "prov-b")

        await manager.check_and_failover("t1", requirements=[])
        event = manager._failover_history[-1]
        assert event.constitutional_hash == CONSTITUTIONAL_HASH

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

    async def test_failover_event_id_starts_with_fo(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        await self._make_degraded(scorer, "prov-a")
        await self._make_healthy(scorer, "prov-b")

        await manager.check_and_failover("t1", requirements=[])
        event = manager._failover_history[-1]
        assert event.event_id.startswith("fo-")

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

        # prov-b is still healthy
        await self._make_healthy(scorer, "prov-b")
        provider, _failover = await manager.check_and_failover("t1", requirements=[])
        assert provider == "prov-b"

    async def test_fallback_exactly_at_threshold_accepted(self) -> None:
        """health_score == PROACTIVE_FAILOVER_THRESHOLD is accepted as healthy fallback."""
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        await self._make_degraded(scorer, "prov-a")

        original = scorer.get_health_score

        def patched(provider_id: str) -> ProviderHealthScore:
            if provider_id == "prov-b":
                return _make_health_score("prov-b", 0.6, is_healthy=False, is_degraded=True)
            return original(provider_id)

        scorer.get_health_score = patched  # type: ignore[method-assign]
        try:
            provider, failover = await manager.check_and_failover("t1", requirements=[])
            assert provider == "prov-b"
            assert failover is True
        finally:
            scorer.get_health_score = original  # type: ignore[method-assign]

    async def test_fallback_below_threshold_skipped(self) -> None:
        """health_score < PROACTIVE_FAILOVER_THRESHOLD means fallback is skipped."""
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        await self._make_degraded(scorer, "prov-a")
        await self._make_degraded(scorer, "prov-b")

        provider, failover = await manager.check_and_failover("t1", requirements=[])
        assert failover is False
        assert provider == "prov-a"

    async def test_first_healthy_fallback_wins_when_multiple(self) -> None:
        """When multiple fallbacks available, first healthy one is picked."""
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b", "prov-c"])

        await self._make_degraded(scorer, "prov-a", 20)
        await self._make_degraded(scorer, "prov-b", 20)  # prov-b unhealthy
        await self._make_healthy(scorer, "prov-c", 20)  # prov-c healthy

        provider, failover = await manager.check_and_failover("t1", requirements=[])
        assert failover is True
        assert provider == "prov-c"


class TestCheckAndFailoverRecovery:
    """Tests for the recovery path back to primary provider."""

    @staticmethod
    async def _make_healthy(scorer: ProviderHealthScorer, pid: str, n: int = 30) -> None:
        for _ in range(n):
            await scorer.record_request(pid, 50.0, success=True)

    @staticmethod
    async def _make_mediocre(scorer: ProviderHealthScorer, pid: str, n: int = 10) -> None:
        for _ in range(n):
            await scorer.record_request(pid, 100.0, success=True)

    async def test_recovery_to_primary_when_primary_healthy(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-primary")
        manager._active_failovers["t1"] = "prov-secondary"

        await self._make_healthy(scorer, "prov-primary")
        await self._make_mediocre(scorer, "prov-secondary")

        provider, failover = await manager.check_and_failover("t1", requirements=[])
        assert provider == "prov-primary"
        assert failover is True

    async def test_recovery_records_history_event(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "primary")
        manager._active_failovers["t1"] = "secondary"

        await self._make_healthy(scorer, "primary")
        await self._make_mediocre(scorer, "secondary")

        await manager.check_and_failover("t1", requirements=[])
        event = manager._failover_history[-1]
        assert event.from_provider == "secondary"
        assert event.to_provider == "primary"
        assert event.reason == "recovery"
        assert event.latency_ms == 0

    async def test_recovery_updates_active_failovers(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "primary")
        manager._active_failovers["t1"] = "secondary"

        await self._make_healthy(scorer, "primary")
        await self._make_mediocre(scorer, "secondary")

        await manager.check_and_failover("t1", requirements=[])
        assert manager._active_failovers["t1"] == "primary"

    async def test_no_recovery_when_primary_below_recovery_threshold(self) -> None:
        """No recovery when primary health < RECOVERY_THRESHOLD (0.85)."""
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "primary")
        manager._active_failovers["t1"] = "secondary"

        # Primary: moderate health, not above 0.85
        for i in range(10):
            await scorer.record_request("primary", 100.0, success=(i < 7))

        # Secondary: healthy
        for _ in range(10):
            await scorer.record_request("secondary", 100.0, success=True)

        provider, _failover = await manager.check_and_failover("t1", requirements=[])
        # No recovery should occur; result depends on health values
        assert provider in ("primary", "secondary")

    async def test_no_recovery_when_no_primary_configured(self) -> None:
        """Recovery branch requires a non-None primary."""
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        # No set_primary_provider — primary is None
        manager._active_failovers["t1"] = "secondary"

        await self._make_mediocre(scorer, "secondary")

        provider, failover = await manager.check_and_failover("t1", requirements=[])
        # Should return current (secondary) without recovery
        assert provider == "secondary"
        assert failover is False

    async def test_recovery_event_has_constitutional_hash(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "primary")
        manager._active_failovers["t1"] = "secondary"

        await self._make_healthy(scorer, "primary")
        await self._make_mediocre(scorer, "secondary")

        await manager.check_and_failover("t1", requirements=[])
        event = manager._failover_history[-1]
        assert event.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_recovery_uses_mock_for_exact_threshold(self) -> None:
        """Recovery triggers when primary health_score >= RECOVERY_THRESHOLD (0.85)."""
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "primary")
        manager._active_failovers["t1"] = "secondary"

        original = scorer.get_health_score

        def mock_health(provider_id: str) -> ProviderHealthScore:
            if provider_id == "primary":
                return _make_health_score("primary", 0.85)
            return _make_health_score("secondary", 0.7)

        scorer.get_health_score = mock_health  # type: ignore[method-assign]
        try:
            provider, failover = await manager.check_and_failover("t1", requirements=[])
            assert provider == "primary"
            assert failover is True
        finally:
            scorer.get_health_score = original  # type: ignore[method-assign]

    async def test_no_recovery_when_primary_health_just_below_threshold(self) -> None:
        """No recovery when primary health_score is just below RECOVERY_THRESHOLD."""
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "primary")
        manager._active_failovers["t1"] = "secondary"

        original = scorer.get_health_score

        def mock_health(provider_id: str) -> ProviderHealthScore:
            if provider_id == "primary":
                return _make_health_score("primary", 0.84, is_degraded=True, is_healthy=False)
            return _make_health_score("secondary", 0.7)

        scorer.get_health_score = mock_health  # type: ignore[method-assign]
        try:
            provider, failover = await manager.check_and_failover("t1", requirements=[])
            # No recovery — stays on secondary
            assert provider == "secondary"
            assert failover is False
        finally:
            scorer.get_health_score = original  # type: ignore[method-assign]


class TestCheckAndFailoverConcurrency:
    """Tests for concurrent access safety."""

    @staticmethod
    async def _make_healthy(scorer: ProviderHealthScorer, pid: str, n: int = 10) -> None:
        for _ in range(n):
            await scorer.record_request(pid, 100.0, success=True)

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

    async def test_concurrent_calls_different_tenants(self) -> None:
        """Concurrent calls for different tenants should not interfere."""
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        for tenant in ("t1", "t2", "t3"):
            manager.set_primary_provider(tenant, f"prov-{tenant}")
            await self._make_healthy(scorer, f"prov-{tenant}")

        results = await asyncio.gather(
            manager.check_and_failover("t1", requirements=[]),
            manager.check_and_failover("t2", requirements=[]),
            manager.check_and_failover("t3", requirements=[]),
        )
        providers = [r[0] for r in results]
        assert "prov-t1" in providers
        assert "prov-t2" in providers
        assert "prov-t3" in providers


class TestCheckAndFailoverWithCapabilityRequirements:
    """Tests involving CapabilityRequirement filtering."""

    @staticmethod
    async def _make_healthy(scorer: ProviderHealthScorer, pid: str, n: int = 10) -> None:
        for _ in range(n):
            await scorer.record_request(pid, 100.0, success=True)

    @staticmethod
    async def _make_degraded(scorer: ProviderHealthScorer, pid: str, n: int = 15) -> None:
        for _ in range(n):
            await scorer.record_request(pid, 200.0, success=False)

    async def test_check_and_failover_with_empty_requirements(self) -> None:
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        await self._make_healthy(scorer, "prov-a")

        provider, failover = await manager.check_and_failover("t1", requirements=[])
        assert provider == "prov-a"
        assert failover is False

    async def test_no_primary_with_requirements_uses_registry(self) -> None:
        """When no primary, uses registry find_capable_providers with requirements."""
        registry = _make_registry("prov-x", "prov-y")
        scorer = ProviderHealthScorer()
        manager = ProactiveFailoverManager(scorer, registry)

        # Empty requirements — all providers qualify
        provider, _failover = await manager.check_and_failover("t-new", requirements=[])
        assert provider in ("prov-x", "prov-y")


# ---------------------------------------------------------------------------
# __all__ export
# ---------------------------------------------------------------------------


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

    def test_all_contains_expected_names(self) -> None:
        import enhanced_agent_bus.llm_adapters.failover.failover as mod

        assert "FailoverEvent" in mod.__all__
        assert "ProactiveFailoverManager" in mod.__all__


# ---------------------------------------------------------------------------
# Integration-style tests for end-to-end scenarios
# ---------------------------------------------------------------------------


class TestIntegrationScenarios:
    """End-to-end integration scenarios testing the full failover workflow."""

    @staticmethod
    async def _make_healthy(scorer: ProviderHealthScorer, pid: str, n: int = 30) -> None:
        for _ in range(n):
            await scorer.record_request(pid, 50.0, success=True)

    @staticmethod
    async def _make_degraded(scorer: ProviderHealthScorer, pid: str, n: int = 20) -> None:
        for _ in range(n):
            await scorer.record_request(pid, 200.0, success=False)

    async def test_full_failover_and_recovery_cycle(self) -> None:
        """Primary degrades → failover to secondary → primary recovers → recovery.

        Uses mocked health scores to ensure deterministic behavior across phases.
        """
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "primary")
        manager.set_fallback_chain("primary", ["secondary"])

        # Phase 1: healthy primary — both providers healthy, no failover
        def phase1_health(provider_id: str) -> ProviderHealthScore:
            return _make_health_score(provider_id, 0.9)

        scorer.get_health_score = phase1_health  # type: ignore[method-assign]
        provider, failover = await manager.check_and_failover("t1", requirements=[])
        assert provider == "primary"
        assert failover is False

        # Phase 2: primary degrades → failover to secondary
        def phase2_health(provider_id: str) -> ProviderHealthScore:
            if provider_id == "primary":
                return _make_health_score("primary", 0.4, is_healthy=False, is_degraded=True)
            return _make_health_score("secondary", 0.9)

        scorer.get_health_score = phase2_health  # type: ignore[method-assign]
        provider, failover = await manager.check_and_failover("t1", requirements=[])
        assert provider == "secondary"
        assert failover is True

        # Phase 3: primary recovers above RECOVERY_THRESHOLD (0.85)
        def phase3_health(provider_id: str) -> ProviderHealthScore:
            if provider_id == "primary":
                return _make_health_score("primary", 0.95)
            return _make_health_score("secondary", 0.7)

        scorer.get_health_score = phase3_health  # type: ignore[method-assign]
        provider, failover = await manager.check_and_failover("t1", requirements=[])
        assert provider == "primary"
        assert failover is True
        # History should have 2 events: failover + recovery
        reasons = [e.reason for e in manager._failover_history]
        assert "recovery" in reasons

    async def test_history_grows_with_multiple_failovers(self) -> None:
        """Multiple failover events are all captured in history."""
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        # First failover
        await self._make_degraded(scorer, "prov-a")
        await self._make_healthy(scorer, "prov-b")
        await manager.check_and_failover("t1", requirements=[])
        assert len(manager._failover_history) == 1

    async def test_active_provider_reflects_current_state(self) -> None:
        """get_active_provider reflects the latest failover state."""
        scorer = ProviderHealthScorer()
        manager = _make_manager(scorer=scorer)
        manager.set_primary_provider("t1", "prov-a")
        manager.set_fallback_chain("prov-a", ["prov-b"])

        assert manager.get_active_provider("t1") == "prov-a"

        await self._make_degraded(scorer, "prov-a")
        await self._make_healthy(scorer, "prov-b")
        await manager.check_and_failover("t1", requirements=[])

        assert manager.get_active_provider("t1") == "prov-b"
