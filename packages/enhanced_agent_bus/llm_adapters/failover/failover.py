"""
ACGS-2 LLM Failover - Proactive Failover Module
Constitutional Hash: 608508a9bd224290

Manages proactive failover between LLM providers before complete failure.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.circuit_breaker import CONSTITUTIONAL_HASH
from enhanced_agent_bus.llm_adapters.capability_matrix import (
    CapabilityRegistry,
    CapabilityRequirement,
    get_capability_registry,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

from .health import ProviderHealthScorer

logger = get_logger(__name__)


@dataclass
class FailoverEvent:
    """Record of a failover event."""

    event_id: str
    from_provider: str
    to_provider: str
    reason: str  # health_degraded, circuit_open, proactive, rate_limited
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    latency_ms: float = 0.0  # Time to complete failover
    success: bool = True
    constitutional_hash: str = CONSTITUTIONAL_HASH


class ProactiveFailoverManager:
    """
    Manages proactive failover between LLM providers.

    Constitutional Hash: 608508a9bd224290

    Features:
    - Monitors provider health scores
    - Triggers failover before complete failure
    - Maintains fallback chain based on capabilities
    - Records failover metrics for analysis
    """

    # Thresholds for proactive failover
    PROACTIVE_FAILOVER_THRESHOLD = 0.6  # Failover when health drops below this
    RECOVERY_THRESHOLD = 0.85  # Consider recovered when health exceeds this

    def __init__(
        self,
        health_scorer: ProviderHealthScorer,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        """Initialize failover manager."""
        self.health_scorer = health_scorer
        self.registry = capability_registry or get_capability_registry()

        self._primary_providers: dict[str, str] = {}  # tenant -> primary provider
        self._fallback_chains: dict[str, list[str]] = {}  # provider -> fallback list
        self._active_failovers: dict[str, str] = {}  # tenant -> current provider
        self._failover_history: deque[FailoverEvent] = deque(maxlen=1000)
        self._lock = asyncio.Lock()

    def set_primary_provider(self, tenant_id: str, provider_id: str) -> None:
        """Set primary provider for a tenant."""
        self._primary_providers[tenant_id] = provider_id

    def set_fallback_chain(self, provider_id: str, fallbacks: list[str]) -> None:
        """Set fallback chain for a provider."""
        self._fallback_chains[provider_id] = fallbacks

    def build_fallback_chain(
        self,
        provider_id: str,
        requirements: list[CapabilityRequirement],
    ) -> list[str]:
        """Build fallback chain based on capability requirements."""
        if provider_id in self._fallback_chains:
            return self._fallback_chains[provider_id]

        # Find capable providers
        capable = self.registry.find_capable_providers(requirements)
        fallbacks = [p.provider_id for p, _ in capable if p.provider_id != provider_id]

        # Sort by health score (descending)
        fallbacks.sort(
            key=lambda p: self.health_scorer.get_health_score(p).health_score,
            reverse=True,
        )

        return fallbacks[:5]  # Top 5 fallbacks

    async def check_and_failover(
        self,
        tenant_id: str,
        requirements: list[CapabilityRequirement],
    ) -> tuple[str, bool]:
        """
        Check provider health and failover if needed.

        Returns:
            Tuple of (provider_id, failover_occurred)
        """
        async with self._lock:
            primary = self._primary_providers.get(tenant_id)
            current = self._active_failovers.get(tenant_id, primary)

            if not current:
                # No configured provider, use first healthy capable provider
                fallbacks = self.build_fallback_chain("", requirements)
                if fallbacks:
                    return fallbacks[0], False
                raise ValueError(f"No capable providers for tenant {tenant_id}")

            # Get health score
            health = self.health_scorer.get_health_score(current)

            # Check if proactive failover needed
            if health.health_score < self.PROACTIVE_FAILOVER_THRESHOLD:
                start_time = time.time()

                # Find healthy fallback
                fallbacks = self.build_fallback_chain(current, requirements)
                for fallback in fallbacks:
                    fb_health = self.health_scorer.get_health_score(fallback)
                    if fb_health.health_score >= self.PROACTIVE_FAILOVER_THRESHOLD:
                        # Execute failover
                        self._active_failovers[tenant_id] = fallback

                        latency_ms = (time.time() - start_time) * 1000
                        event = FailoverEvent(
                            event_id=f"fo-{int(time.time() * 1000)}",
                            from_provider=current,
                            to_provider=fallback,
                            reason="proactive" if health.health_score > 0.3 else "health_degraded",
                            latency_ms=latency_ms,
                        )
                        self._failover_history.append(event)

                        logger.warning(
                            f"[{CONSTITUTIONAL_HASH}] Proactive failover: "
                            f"{current} -> {fallback} (health={health.health_score:.2f}, "
                            f"latency={latency_ms:.1f}ms)"
                        )

                        return fallback, True

                # No healthy fallback available
                logger.error(
                    f"[{CONSTITUTIONAL_HASH}] No healthy fallback for {current} "
                    f"(health={health.health_score:.2f})"
                )

            # Check if we can recover to primary
            if current != primary and primary:
                primary_health = self.health_scorer.get_health_score(primary)
                if primary_health.health_score >= self.RECOVERY_THRESHOLD:
                    self._active_failovers[tenant_id] = primary

                    event = FailoverEvent(
                        event_id=f"fo-{int(time.time() * 1000)}",
                        from_provider=current,
                        to_provider=primary,
                        reason="recovery",
                        latency_ms=0,
                    )
                    self._failover_history.append(event)

                    logger.info(
                        f"[{CONSTITUTIONAL_HASH}] Recovered to primary: "
                        f"{current} -> {primary} (health={primary_health.health_score:.2f})"
                    )

                    return primary, True

            return current, False

    def get_active_provider(self, tenant_id: str) -> str | None:
        """Get currently active provider for a tenant."""
        return self._active_failovers.get(
            tenant_id,
            self._primary_providers.get(tenant_id),
        )

    def get_failover_history(self, limit: int = 100) -> list[FailoverEvent]:
        """Get recent failover history."""
        return list(self._failover_history)[-limit:]

    def get_failover_stats(self) -> JSONDict:
        """Get failover statistics."""
        events = list(self._failover_history)
        if not events:
            return {
                "total_failovers": 0,
                "avg_failover_latency_ms": 0,
                "failover_success_rate": 1.0,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }

        successful = sum(1 for e in events if e.success)
        latencies = [e.latency_ms for e in events if e.success]

        return {
            "total_failovers": len(events),
            "successful_failovers": successful,
            "avg_failover_latency_ms": statistics.mean(latencies) if latencies else 0,
            "max_failover_latency_ms": max(latencies) if latencies else 0,
            "failover_success_rate": successful / len(events) if events else 1.0,
            "reasons": {
                reason: sum(1 for e in events if e.reason == reason)
                for reason in {"proactive", "health_degraded", "circuit_open", "recovery"}
            },
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


__all__ = [
    "FailoverEvent",
    "ProactiveFailoverManager",
]
