"""
Tests for ProactiveFailoverManager trigger logic.
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from unittest.mock import MagicMock

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.llm_adapters.failover.failover import (
    FailoverEvent,
    ProactiveFailoverManager,
)
from enhanced_agent_bus.llm_adapters.failover.health import (
    HealthMetrics,
    ProviderHealthScore,
    ProviderHealthScorer,
)


def _make_health(score: float, provider_id: str = "test-provider") -> ProviderHealthScore:
    """Create a minimal ProviderHealthScore with the given score."""
    return ProviderHealthScore(
        provider_id=provider_id,
        health_score=score,
        latency_score=score,
        error_score=score,
        quality_score=score,
        availability_score=score,
        is_healthy=score >= 0.8,
        is_degraded=0.6 <= score < 0.8,
        is_unhealthy=score < 0.6,
        metrics=HealthMetrics(),
    )


def _mock_health_scorer(scores: dict[str, float]) -> ProviderHealthScorer:
    """Build a ProviderHealthScorer mock returning given per-provider scores."""
    scorer = MagicMock(spec=ProviderHealthScorer)
    scorer.get_health_score.side_effect = lambda pid: _make_health(scores.get(pid, 0.9))
    return scorer


async def test_failover_triggers_when_health_below_threshold() -> None:
    """Health score below PROACTIVE_FAILOVER_THRESHOLD must trigger failover."""
    scorer = _mock_health_scorer({"primary": 0.3, "fallback": 0.95})
    manager = ProactiveFailoverManager(health_scorer=scorer)
    manager.set_primary_provider("tenant-A", "primary")
    manager.set_fallback_chain("primary", ["fallback"])

    provider, failover_occurred = await manager.check_and_failover("tenant-A", [])

    assert failover_occurred is True
    assert provider == "fallback"
    # Failover event should be recorded
    assert len(manager._failover_history) == 1
    event: FailoverEvent = manager._failover_history[0]
    assert event.from_provider == "primary"
    assert event.to_provider == "fallback"
    assert event.constitutional_hash == CONSTITUTIONAL_HASH


async def test_no_failover_when_health_above_threshold() -> None:
    """Health score above threshold must keep current provider and not trigger failover."""
    scorer = _mock_health_scorer({"primary": 0.95})
    manager = ProactiveFailoverManager(health_scorer=scorer)
    manager.set_primary_provider("tenant-B", "primary")

    provider, failover_occurred = await manager.check_and_failover("tenant-B", [])

    assert failover_occurred is False
    assert provider == "primary"
    assert len(manager._failover_history) == 0


async def test_fallback_chain_sorted_by_descending_health() -> None:
    """build_fallback_chain must return providers ordered highest health first."""
    scorer = _mock_health_scorer({"p1": 0.8, "p2": 0.5, "p3": 0.95, "p4": 0.7})
    registry = MagicMock()
    provider_mocks = [(MagicMock(provider_id=pid), None) for pid in ["p1", "p2", "p3", "p4"]]
    registry.find_capable_providers.return_value = provider_mocks

    manager = ProactiveFailoverManager(health_scorer=scorer, capability_registry=registry)

    chain = manager.build_fallback_chain("primary-x", [])
    health_values = [scorer.get_health_score(p).health_score for p in chain]

    assert health_values == sorted(health_values, reverse=True), (
        "Fallback chain must be sorted by descending health score"
    )


async def test_fallback_chain_excludes_primary_provider() -> None:
    """build_fallback_chain must not include the primary provider in the results."""
    scorer = _mock_health_scorer({"provider-X": 0.85, "provider-Y": 0.75})
    registry = MagicMock()
    registry.find_capable_providers.return_value = [
        (MagicMock(provider_id="provider-X"), None),
        (MagicMock(provider_id="provider-Y"), None),
    ]

    manager = ProactiveFailoverManager(health_scorer=scorer, capability_registry=registry)
    chain = manager.build_fallback_chain("provider-X", [])

    assert "provider-X" not in chain


async def test_failover_event_has_constitutional_hash() -> None:
    """Every FailoverEvent recorded must carry the canonical constitutional hash."""
    scorer = _mock_health_scorer({"low-health": 0.1, "good": 0.9})
    manager = ProactiveFailoverManager(health_scorer=scorer)
    manager.set_primary_provider("tenant-C", "low-health")
    manager.set_fallback_chain("low-health", ["good"])

    await manager.check_and_failover("tenant-C", [])

    assert manager._failover_history[0].constitutional_hash == CONSTITUTIONAL_HASH
