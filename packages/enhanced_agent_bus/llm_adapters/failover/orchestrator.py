"""
ACGS-2 LLM Failover - Orchestrator Module
Constitutional Hash: 608508a9bd224290

Main orchestrator for LLM provider failover integrating all components.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.circuit_breaker import (
    CONSTITUTIONAL_HASH,
    ServiceCircuitBreaker,
    get_circuit_breaker_registry,
)
from enhanced_agent_bus.llm_adapters.capability_matrix import (
    CapabilityRegistry,
    CapabilityRequirement,
    LatencyClass,
    get_capability_registry,
)

from .config import get_llm_circuit_config
from .failover import ProactiveFailoverManager
from .health import ProviderHealthScorer
from .hedging import RequestHedgingManager
from .warmup import ProviderWarmupManager

FAILOVER_EXECUTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    TimeoutError,
    OSError,
)


class LLMFailoverOrchestrator:
    """
    Main orchestrator for LLM provider failover.

    Constitutional Hash: 608508a9bd224290

    Integrates:
    - Circuit breakers (from existing module)
    - Health scoring
    - Proactive failover
    - Provider warmup
    - Request hedging
    """

    def __init__(
        self,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        """Initialize failover orchestrator."""
        self.registry = capability_registry or get_capability_registry()
        self.health_scorer = ProviderHealthScorer()
        self.failover_manager = ProactiveFailoverManager(
            self.health_scorer,
            self.registry,
        )
        self.warmup_manager = ProviderWarmupManager()
        self.hedging_manager = RequestHedgingManager()

        # Initialize expected latencies from capability profiles
        self._initialize_expected_latencies()

    def _initialize_expected_latencies(self) -> None:
        """Set expected latencies based on provider capability profiles."""
        latency_map = {
            LatencyClass.ULTRA_LOW: 100,
            LatencyClass.LOW: 200,
            LatencyClass.MEDIUM: 500,
            LatencyClass.HIGH: 1000,
            LatencyClass.VARIABLE: 750,
        }

        for profile in self.registry.get_all_profiles():
            expected = latency_map.get(profile.latency_class, 500)
            self.health_scorer.set_expected_latency(profile.provider_id, expected)

    async def get_llm_circuit_breaker(
        self,
        provider_id: str,
    ) -> ServiceCircuitBreaker:
        """Get or create LLM-specific circuit breaker."""
        # Extract provider type from ID
        provider_type = provider_id.split("-")[0] if "-" in provider_id else "default"
        config = get_llm_circuit_config(provider_type)

        cb_registry = get_circuit_breaker_registry()
        return await cb_registry.get_or_create(f"llm:{provider_id}", config)

    async def record_request_result(
        self,
        provider_id: str,
        latency_ms: float,
        success: bool,
        error_type: str | None = None,
        quality_score: float | None = None,
    ) -> None:
        """Record request result for health tracking and circuit breaker."""
        # Update health scorer
        await self.health_scorer.record_request(
            provider_id,
            latency_ms,
            success,
            error_type,
            quality_score,
        )

        # Update circuit breaker
        cb = await self.get_llm_circuit_breaker(provider_id)
        if success:
            await cb.record_success()
        else:
            await cb.record_failure(error_type=error_type or "unknown")

    async def select_provider(
        self,
        tenant_id: str,
        requirements: list[CapabilityRequirement],
        critical: bool = False,
    ) -> str:
        """
        Select the best available provider with failover support.

        Args:
            tenant_id: Tenant ID for tracking
            requirements: Capability requirements
            critical: If True, use hedging for reliability

        Returns:
            Selected provider ID
        """
        # Check for failover
        provider, failover_occurred = await self.failover_manager.check_and_failover(
            tenant_id,
            requirements,
        )

        # Warmup if failover occurred
        if failover_occurred:
            await self.warmup_manager.warmup_before_failover(provider)

        return provider

    async def execute_with_failover(
        self,
        tenant_id: str,
        requirements: list[CapabilityRequirement],
        execute_fn: Callable[[str], Awaitable[object]],
        critical: bool = False,
        hedge_count: int = 1,
    ) -> tuple[str, object]:
        """
        Execute a request with automatic failover support.

        Args:
            tenant_id: Tenant ID
            requirements: Capability requirements
            execute_fn: Async function taking provider_id
            critical: If True, use hedging
            hedge_count: Number of providers for hedging (if critical)

        Returns:
            Tuple of (provider_id, result)
        """
        if critical and hedge_count > 1:
            # Use hedging for critical requests
            capable = self.registry.find_capable_providers(requirements)
            providers = [p.provider_id for p, _ in capable[:hedge_count]]

            return await self.hedging_manager.execute_hedged(
                request_id=f"req-{int(time.time() * 1000)}",
                providers=providers,
                execute_fn=execute_fn,
                hedge_count=hedge_count,
            )

        # Normal execution with failover
        provider = await self.select_provider(tenant_id, requirements, critical)

        start_time = time.time()
        try:
            result = await execute_fn(provider)
            latency_ms = (time.time() - start_time) * 1000

            await self.record_request_result(
                provider,
                latency_ms,
                success=True,
            )

            return provider, result

        except FAILOVER_EXECUTION_ERRORS as e:
            latency_ms = (time.time() - start_time) * 1000
            error_type = type(e).__name__

            await self.record_request_result(
                provider,
                latency_ms,
                success=False,
                error_type=error_type,
            )

            # Try failover
            fallbacks = self.failover_manager.build_fallback_chain(provider, requirements)
            for fallback in fallbacks:
                try:
                    fb_start = time.time()
                    result = await execute_fn(fallback)
                    fb_latency = (time.time() - fb_start) * 1000

                    await self.record_request_result(
                        fallback,
                        fb_latency,
                        success=True,
                    )

                    return fallback, result
                except (RuntimeError, ValueError, ConnectionError, TimeoutError):
                    continue

            # All fallbacks failed
            raise

    def get_orchestrator_status(self) -> JSONDict:
        """Get comprehensive orchestrator status."""
        return {
            "health_scores": {
                p: s.to_dict() for p, s in self.health_scorer.get_all_scores().items()
            },
            "failover_stats": self.failover_manager.get_failover_stats(),
            "hedging_stats": self.hedging_manager.get_hedging_stats(),
            "timestamp": datetime.now(UTC).isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


# =============================================================================
# Global Instance
# =============================================================================

_orchestrator: LLMFailoverOrchestrator | None = None


def get_llm_failover_orchestrator() -> LLMFailoverOrchestrator:
    """Get or create the global LLM failover orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = LLMFailoverOrchestrator()
    return _orchestrator


def reset_llm_failover_orchestrator() -> None:
    """Reset the global orchestrator (for testing)."""
    global _orchestrator
    _orchestrator = None


__all__ = [
    "LLMFailoverOrchestrator",
    "get_llm_failover_orchestrator",
    "reset_llm_failover_orchestrator",
]
