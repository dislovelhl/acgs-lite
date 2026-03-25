"""
ACGS-2 Enhanced Agent Bus - LLM Provider Failover System
Constitutional Hash: 608508a9bd224290

Implements enhanced failover capabilities for LLM providers with:
- LLM-specific circuit breaker configurations
- Provider health scoring (latency, errors, quality)
- Proactive failover (switch before failure)
- Provider warmup mechanism
- Request hedging for critical operations

Success Metrics:
- Provider failover < 500ms
- Zero single-provider dependency for critical paths
"""

from __future__ import annotations

import asyncio
import inspect
import statistics
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.circuit_breaker import (
    CONSTITUTIONAL_HASH,
    FallbackStrategy,
    ServiceCircuitConfig,
    ServiceSeverity,
)
from enhanced_agent_bus.governance_constants import (
    LLM_CB_DEFAULT_FAILURE_THRESHOLD,
    LLM_CB_DEFAULT_FALLBACK_TTL_SECONDS,
    LLM_CB_DEFAULT_HALF_OPEN_REQUESTS,
    LLM_CB_DEFAULT_TIMEOUT_SECONDS,
)
from enhanced_agent_bus.llm_adapters.capability_matrix import (
    CapabilityRegistry,
    CapabilityRequirement,
    get_capability_registry,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
_LLM_FAILOVER_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


# =============================================================================
# LLM-Specific Circuit Breaker Configs
# =============================================================================


class LLMProviderType(str, Enum):
    """LLM provider types for configuration."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    AZURE = "azure"
    BEDROCK = "bedrock"
    COHERE = "cohere"
    MISTRAL = "mistral"
    KIMI = "kimi"
    OPENCLAW = "openclaw"
    LOCAL = "local"


# LLM-specific circuit breaker configurations
LLM_CIRCUIT_CONFIGS: dict[str, ServiceCircuitConfig] = {
    # OpenAI - High reliability, moderate timeouts
    "llm:openai": ServiceCircuitConfig(
        name="llm:openai",
        failure_threshold=LLM_CB_DEFAULT_FAILURE_THRESHOLD,
        timeout_seconds=LLM_CB_DEFAULT_TIMEOUT_SECONDS,
        half_open_requests=LLM_CB_DEFAULT_HALF_OPEN_REQUESTS,
        fallback_strategy=FallbackStrategy.CACHED_VALUE,
        fallback_ttl_seconds=LLM_CB_DEFAULT_FALLBACK_TTL_SECONDS,
        severity=ServiceSeverity.HIGH,
        description="OpenAI LLM Provider - uses cached responses on failure",
    ),
    # Anthropic - High reliability, longer timeouts for complex reasoning
    "llm:anthropic": ServiceCircuitConfig(
        name="llm:anthropic",
        failure_threshold=LLM_CB_DEFAULT_FAILURE_THRESHOLD,
        timeout_seconds=45.0,
        half_open_requests=LLM_CB_DEFAULT_HALF_OPEN_REQUESTS,
        fallback_strategy=FallbackStrategy.CACHED_VALUE,
        fallback_ttl_seconds=LLM_CB_DEFAULT_FALLBACK_TTL_SECONDS,
        severity=ServiceSeverity.HIGH,
        description="Anthropic LLM Provider - uses cached responses on failure",
    ),
    # Google - Variable latency, higher threshold
    "llm:google": ServiceCircuitConfig(
        name="llm:google",
        failure_threshold=7,
        timeout_seconds=60.0,
        half_open_requests=5,
        fallback_strategy=FallbackStrategy.CACHED_VALUE,
        fallback_ttl_seconds=120,
        severity=ServiceSeverity.MEDIUM,
        description="Google LLM Provider - higher tolerance for variable latency",
    ),
    # Azure OpenAI - Enterprise-grade, moderate settings
    "llm:azure": ServiceCircuitConfig(
        name="llm:azure",
        failure_threshold=LLM_CB_DEFAULT_FAILURE_THRESHOLD,
        timeout_seconds=LLM_CB_DEFAULT_TIMEOUT_SECONDS,
        half_open_requests=LLM_CB_DEFAULT_HALF_OPEN_REQUESTS,
        fallback_strategy=FallbackStrategy.CACHED_VALUE,
        fallback_ttl_seconds=LLM_CB_DEFAULT_FALLBACK_TTL_SECONDS,
        severity=ServiceSeverity.HIGH,
        description="Azure OpenAI Provider - enterprise reliability",
    ),
    # AWS Bedrock - Enterprise-grade, moderate settings
    "llm:bedrock": ServiceCircuitConfig(
        name="llm:bedrock",
        failure_threshold=LLM_CB_DEFAULT_FAILURE_THRESHOLD,
        timeout_seconds=LLM_CB_DEFAULT_TIMEOUT_SECONDS,
        half_open_requests=LLM_CB_DEFAULT_HALF_OPEN_REQUESTS,
        fallback_strategy=FallbackStrategy.CACHED_VALUE,
        fallback_ttl_seconds=LLM_CB_DEFAULT_FALLBACK_TTL_SECONDS,
        severity=ServiceSeverity.HIGH,
        description="AWS Bedrock Provider - enterprise reliability",
    ),
    # Kimi (Moonshot AI) - Free tier with moderate limits
    "llm:kimi": ServiceCircuitConfig(
        name="llm:kimi",
        failure_threshold=LLM_CB_DEFAULT_FAILURE_THRESHOLD,
        timeout_seconds=LLM_CB_DEFAULT_TIMEOUT_SECONDS,
        half_open_requests=LLM_CB_DEFAULT_HALF_OPEN_REQUESTS,
        fallback_strategy=FallbackStrategy.CACHED_VALUE,
        fallback_ttl_seconds=LLM_CB_DEFAULT_FALLBACK_TTL_SECONDS,
        severity=ServiceSeverity.MEDIUM,
        description="Kimi LLM Provider - Moonshot AI with free tier",
    ),
    # OpenClaw - Local gateway proxy, moderate timeouts
    "llm:openclaw": ServiceCircuitConfig(
        name="llm:openclaw",
        failure_threshold=LLM_CB_DEFAULT_FAILURE_THRESHOLD,
        timeout_seconds=LLM_CB_DEFAULT_TIMEOUT_SECONDS,
        half_open_requests=LLM_CB_DEFAULT_HALF_OPEN_REQUESTS,
        fallback_strategy=FallbackStrategy.CACHED_VALUE,
        fallback_ttl_seconds=LLM_CB_DEFAULT_FALLBACK_TTL_SECONDS,
        severity=ServiceSeverity.MEDIUM,
        description="OpenClaw Gateway - local agent runtime proxy",
    ),
    # Local models - Higher tolerance, faster recovery
    "llm:local": ServiceCircuitConfig(
        name="llm:local",
        failure_threshold=3,
        timeout_seconds=10.0,
        half_open_requests=5,
        fallback_strategy=FallbackStrategy.BYPASS,
        severity=ServiceSeverity.LOW,
        description="Local LLM Provider - fast recovery expected",
    ),
}


def get_llm_circuit_config(provider_type: str) -> ServiceCircuitConfig:
    """Get LLM-specific circuit breaker configuration."""
    key = f"llm:{provider_type.lower()}"
    if key in LLM_CIRCUIT_CONFIGS:
        return LLM_CIRCUIT_CONFIGS[key]

    # Default LLM config
    return ServiceCircuitConfig(
        name=key,
        failure_threshold=LLM_CB_DEFAULT_FAILURE_THRESHOLD,
        timeout_seconds=LLM_CB_DEFAULT_TIMEOUT_SECONDS,
        half_open_requests=LLM_CB_DEFAULT_HALF_OPEN_REQUESTS,
        fallback_strategy=FallbackStrategy.CACHED_VALUE,
        fallback_ttl_seconds=LLM_CB_DEFAULT_FALLBACK_TTL_SECONDS,
        severity=ServiceSeverity.MEDIUM,
        description=f"Auto-configured LLM circuit breaker for {provider_type}",
    )


# =============================================================================
# Health Scoring
# =============================================================================


@dataclass
class HealthMetrics:
    """Metrics for provider health scoring."""

    # Latency metrics (in milliseconds)
    latency_samples: deque[float] = field(default_factory=lambda: deque(maxlen=100))
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0

    # Error metrics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    timeout_count: int = 0
    rate_limit_count: int = 0
    error_rate: float = 0.0

    # Quality metrics (0.0 - 1.0)
    response_quality_scores: deque[float] = field(default_factory=lambda: deque(maxlen=50))
    avg_quality_score: float = 1.0

    # Availability
    last_success_time: datetime | None = None
    last_failure_time: datetime | None = None
    consecutive_failures: int = 0
    uptime_percentage: float = 100.0

    # Overall health score (0.0 - 1.0)
    health_score: float = 1.0

    # Constitutional hash
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class ProviderHealthScore:
    """
    Health score for an LLM provider.

    Constitutional Hash: 608508a9bd224290
    """

    provider_id: str
    health_score: float  # 0.0 - 1.0
    latency_score: float  # Based on latency percentiles
    error_score: float  # Based on error rate
    quality_score: float  # Based on response quality
    availability_score: float  # Based on uptime

    is_healthy: bool
    is_degraded: bool
    is_unhealthy: bool

    metrics: HealthMetrics
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for serialization."""
        return {
            "provider_id": self.provider_id,
            "health_score": round(self.health_score, 3),
            "latency_score": round(self.latency_score, 3),
            "error_score": round(self.error_score, 3),
            "quality_score": round(self.quality_score, 3),
            "availability_score": round(self.availability_score, 3),
            "is_healthy": self.is_healthy,
            "is_degraded": self.is_degraded,
            "is_unhealthy": self.is_unhealthy,
            "metrics": {
                "avg_latency_ms": round(self.metrics.avg_latency_ms, 2),
                "p95_latency_ms": round(self.metrics.p95_latency_ms, 2),
                "error_rate": round(self.metrics.error_rate, 4),
                "total_requests": self.metrics.total_requests,
                "consecutive_failures": self.metrics.consecutive_failures,
            },
            "last_updated": self.last_updated.isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }


class ProviderHealthScorer:
    """
    Scores provider health based on multiple factors.

    Constitutional Hash: 608508a9bd224290

    Health score components:
    - Latency (30%): Based on P95 latency vs expected
    - Errors (35%): Based on error rate
    - Quality (15%): Based on response quality feedback
    - Availability (20%): Based on uptime and consecutive failures
    """

    # Weight factors for health score components
    LATENCY_WEIGHT = 0.30
    ERROR_WEIGHT = 0.35
    QUALITY_WEIGHT = 0.15
    AVAILABILITY_WEIGHT = 0.20

    # Thresholds
    HEALTHY_THRESHOLD = 0.8
    DEGRADED_THRESHOLD = 0.5

    def __init__(self) -> None:
        """Initialize health scorer."""
        self._metrics: dict[str, HealthMetrics] = {}
        self._expected_latency: dict[str, float] = {}  # provider -> expected P95 ms
        self._lock = asyncio.Lock()

    def set_expected_latency(self, provider_id: str, latency_ms: float) -> None:
        """Set expected P95 latency for a provider."""
        self._expected_latency[provider_id] = latency_ms

    async def record_request(
        self,
        provider_id: str,
        latency_ms: float,
        success: bool,
        error_type: str | None = None,
        quality_score: float | None = None,
    ) -> None:
        """Record a request result for health scoring."""
        async with self._lock:
            if provider_id not in self._metrics:
                self._metrics[provider_id] = HealthMetrics()

            metrics = self._metrics[provider_id]

            # Update request counts
            metrics.total_requests += 1
            if success:
                metrics.successful_requests += 1
                metrics.last_success_time = datetime.now(UTC)
                metrics.consecutive_failures = 0
            else:
                metrics.failed_requests += 1
                metrics.last_failure_time = datetime.now(UTC)
                metrics.consecutive_failures += 1

                if error_type == "timeout":
                    metrics.timeout_count += 1
                elif error_type == "rate_limit":
                    metrics.rate_limit_count += 1

            # Update latency
            metrics.latency_samples.append(latency_ms)
            self._update_latency_stats(metrics)

            # Update error rate
            metrics.error_rate = (
                metrics.failed_requests / metrics.total_requests
                if metrics.total_requests > 0
                else 0.0
            )

            # Update quality score
            if quality_score is not None:
                metrics.response_quality_scores.append(quality_score)
                metrics.avg_quality_score = (
                    statistics.mean(metrics.response_quality_scores)
                    if metrics.response_quality_scores
                    else 1.0
                )

            # Update uptime
            self._update_uptime(metrics)

            # Recalculate health score
            metrics.health_score = self._calculate_health_score(provider_id, metrics)

    def _update_latency_stats(self, metrics: HealthMetrics) -> None:
        """Update latency statistics."""
        if not metrics.latency_samples:
            return

        samples = list(metrics.latency_samples)
        metrics.avg_latency_ms = statistics.mean(samples)
        metrics.p50_latency_ms = statistics.median(samples)

        sorted_samples = sorted(samples)
        n = len(sorted_samples)
        metrics.p95_latency_ms = sorted_samples[int(n * 0.95)] if n > 0 else 0
        metrics.p99_latency_ms = sorted_samples[int(n * 0.99)] if n > 0 else 0

    def _update_uptime(self, metrics: HealthMetrics) -> None:
        """Update uptime percentage."""
        if metrics.total_requests == 0:
            metrics.uptime_percentage = 100.0
        else:
            metrics.uptime_percentage = (metrics.successful_requests / metrics.total_requests) * 100

    def _calculate_health_score(self, provider_id: str, metrics: HealthMetrics) -> float:
        """Calculate overall health score."""
        # Latency score
        expected_latency = self._expected_latency.get(provider_id, 500.0)  # Default 500ms
        latency_score = max(0, 1 - (metrics.p95_latency_ms / (expected_latency * 2)))

        # Error score
        error_score = max(0, 1 - (metrics.error_rate * 5))  # 20% error rate = 0 score

        # Quality score
        quality_score = metrics.avg_quality_score

        # Availability score
        availability_score = metrics.uptime_percentage / 100
        # Penalize consecutive failures
        if metrics.consecutive_failures > 0:
            penalty = min(0.5, metrics.consecutive_failures * 0.1)
            availability_score = max(0, availability_score - penalty)

        # Weighted combination
        health_score = (
            self.LATENCY_WEIGHT * latency_score
            + self.ERROR_WEIGHT * error_score
            + self.QUALITY_WEIGHT * quality_score
            + self.AVAILABILITY_WEIGHT * availability_score
        )

        return max(0.0, min(1.0, health_score))

    def get_health_score(self, provider_id: str) -> ProviderHealthScore:
        """Get current health score for a provider."""
        metrics = self._metrics.get(provider_id, HealthMetrics())

        # Calculate component scores
        expected_latency = self._expected_latency.get(provider_id, 500.0)
        latency_score = max(0, 1 - (metrics.p95_latency_ms / (expected_latency * 2)))
        error_score = max(0, 1 - (metrics.error_rate * 5))
        quality_score = metrics.avg_quality_score
        availability_score = metrics.uptime_percentage / 100

        health_score = metrics.health_score

        return ProviderHealthScore(
            provider_id=provider_id,
            health_score=health_score,
            latency_score=latency_score,
            error_score=error_score,
            quality_score=quality_score,
            availability_score=availability_score,
            is_healthy=health_score >= self.HEALTHY_THRESHOLD,
            is_degraded=self.DEGRADED_THRESHOLD <= health_score < self.HEALTHY_THRESHOLD,
            is_unhealthy=health_score < self.DEGRADED_THRESHOLD,
            metrics=metrics,
        )

    def get_all_scores(self) -> dict[str, ProviderHealthScore]:
        """Get health scores for all tracked providers."""
        return {provider_id: self.get_health_score(provider_id) for provider_id in self._metrics}

    def reset(self, provider_id: str | None = None) -> None:
        """Reset health metrics."""
        if provider_id:
            if provider_id in self._metrics:
                self._metrics[provider_id] = HealthMetrics()
        else:
            self._metrics.clear()


# =============================================================================
# Proactive Failover
# =============================================================================


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


# =============================================================================
# Provider Warmup
# =============================================================================


@dataclass
class WarmupResult:
    """Result of a provider warmup attempt."""

    provider_id: str
    success: bool
    latency_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    error: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


class ProviderWarmupManager:
    """
    Manages provider warmup to reduce cold-start latency.

    Constitutional Hash: 608508a9bd224290

    Features:
    - Periodic warmup requests to keep connections alive
    - Warmup before failover to target provider
    - Tracks warmup status per provider
    """

    DEFAULT_WARMUP_INTERVAL = timedelta(minutes=5)
    WARMUP_TIMEOUT_MS = 10000  # 10 seconds

    def __init__(self) -> None:
        """Initialize warmup manager."""
        self._warmup_handlers: dict[str, Callable[[], object]] = {}
        self._last_warmup: dict[str, datetime] = {}
        self._warmup_results: dict[str, WarmupResult] = {}
        self._warmup_tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    def register_warmup_handler(
        self,
        provider_id: str,
        handler: Callable[[], object],
    ) -> None:
        """Register a warmup handler for a provider."""
        self._warmup_handlers[provider_id] = handler

    async def warmup(self, provider_id: str) -> WarmupResult:
        """Execute warmup for a provider."""
        if provider_id not in self._warmup_handlers:
            return WarmupResult(
                provider_id=provider_id,
                success=False,
                latency_ms=0,
                error="No warmup handler registered",
            )

        handler = self._warmup_handlers[provider_id]
        start_time = time.time()

        try:
            # Execute warmup with timeout
            await asyncio.wait_for(
                handler() if inspect.iscoroutinefunction(handler) else asyncio.to_thread(handler),
                timeout=self.WARMUP_TIMEOUT_MS / 1000,
            )

            latency_ms = (time.time() - start_time) * 1000
            result = WarmupResult(
                provider_id=provider_id,
                success=True,
                latency_ms=latency_ms,
            )

            logger.debug(
                f"[{CONSTITUTIONAL_HASH}] Warmup success for {provider_id} ({latency_ms:.1f}ms)"
            )

        except TimeoutError:
            latency_ms = (time.time() - start_time) * 1000
            result = WarmupResult(
                provider_id=provider_id,
                success=False,
                latency_ms=latency_ms,
                error="Timeout",
            )
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Warmup timeout for {provider_id}")

        except _LLM_FAILOVER_OPERATION_ERRORS as e:
            latency_ms = (time.time() - start_time) * 1000
            result = WarmupResult(
                provider_id=provider_id,
                success=False,
                latency_ms=latency_ms,
                error=str(e),
            )
            logger.error(f"[{CONSTITUTIONAL_HASH}] Warmup failed for {provider_id}: {e}")

        async with self._lock:
            self._last_warmup[provider_id] = datetime.now(UTC)
            self._warmup_results[provider_id] = result

        return result

    async def warmup_if_needed(
        self,
        provider_id: str,
        interval: timedelta | None = None,
    ) -> WarmupResult | None:
        """Warmup provider if interval has elapsed."""
        interval = interval or self.DEFAULT_WARMUP_INTERVAL

        last = self._last_warmup.get(provider_id)
        if last is None or datetime.now(UTC) - last > interval:
            return await self.warmup(provider_id)

        return None

    async def warmup_before_failover(
        self,
        target_provider: str,
    ) -> WarmupResult:
        """Warmup target provider before failover."""
        logger.info(f"[{CONSTITUTIONAL_HASH}] Pre-failover warmup for {target_provider}")
        return await self.warmup(target_provider)

    def start_periodic_warmup(
        self,
        provider_id: str,
        interval: timedelta | None = None,
    ) -> None:
        """Start periodic warmup task for a provider."""
        interval = interval or self.DEFAULT_WARMUP_INTERVAL

        async def warmup_loop():
            try:
                while True:
                    await asyncio.sleep(interval.total_seconds())
                    try:
                        await self.warmup(provider_id)
                    except asyncio.CancelledError:
                        raise
                    except _LLM_FAILOVER_OPERATION_ERRORS as e:
                        logger.warning(f"Warmup failed for {provider_id}: {e}")
            except asyncio.CancelledError:
                logger.debug(f"Warmup loop cancelled for {provider_id}")

        if provider_id in self._warmup_tasks:
            self._warmup_tasks[provider_id].cancel()

        self._warmup_tasks[provider_id] = asyncio.create_task(warmup_loop())

    def stop_periodic_warmup(self, provider_id: str) -> None:
        """Stop periodic warmup for a provider."""
        if provider_id in self._warmup_tasks:
            self._warmup_tasks[provider_id].cancel()
            del self._warmup_tasks[provider_id]

    def get_warmup_status(self, provider_id: str) -> JSONDict:
        """Get warmup status for a provider."""
        result = self._warmup_results.get(provider_id)
        last = self._last_warmup.get(provider_id)

        return {
            "provider_id": provider_id,
            "has_handler": provider_id in self._warmup_handlers,
            "last_warmup": last.isoformat() if last else None,
            "last_result": (
                {
                    "success": result.success,
                    "latency_ms": result.latency_ms,
                    "error": result.error,
                }
                if result
                else None
            ),
            "periodic_enabled": provider_id in self._warmup_tasks,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


# =============================================================================
# Request Hedging
# =============================================================================


@dataclass
class HedgedRequest:
    """A hedged request to multiple providers."""

    request_id: str
    providers: list[str]
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    winning_provider: str | None = None
    responses: JSONDict = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    latencies_ms: dict[str, float] = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH


class RequestHedgingManager:
    """
    Implements request hedging for critical operations.

    Constitutional Hash: 608508a9bd224290

    Features:
    - Send same request to multiple providers
    - Use first successful response
    - Cancel other requests when response received
    - Track hedging statistics
    """

    def __init__(
        self,
        default_hedge_count: int = 2,
        hedge_delay_ms: int = 100,  # Delay before sending hedged requests
    ) -> None:
        """Initialize hedging manager."""
        self._default_hedge_count = default_hedge_count
        self._hedge_delay_ms = hedge_delay_ms
        self._hedged_requests: deque[HedgedRequest] = deque(maxlen=1000)
        self._lock = asyncio.Lock()

    async def execute_hedged(
        self,
        request_id: str,
        providers: list[str],
        execute_fn: Callable[[str], Awaitable[object]],
        hedge_count: int | None = None,
    ) -> tuple[str, object]:
        """
        Execute a hedged request across multiple providers.

        Args:
            request_id: Unique request ID
            providers: List of provider IDs to use
            execute_fn: Async function taking provider_id and returning response
            hedge_count: Number of providers to hedge (default: 2)

        Returns:
            Tuple of (winning_provider_id, response)
        """
        hedge_count = hedge_count or self._default_hedge_count
        selected_providers = providers[:hedge_count]

        if not selected_providers:
            raise ValueError("No providers available for hedging")

        hedged = HedgedRequest(
            request_id=request_id,
            providers=selected_providers,
        )

        # Create and execute hedged tasks
        tasks = self._create_hedged_tasks(request_id, selected_providers, execute_fn, hedged)

        # Wait for first success
        winner, result = await self._wait_for_first_success(tasks)

        # Record completion
        await self._record_hedged_completion(hedged, winner)

        return winner, result

    async def _execute_with_provider(
        self,
        provider_id: str,
        execute_fn: Callable[[str], Awaitable[object]],
        hedged: HedgedRequest,
        delay_ms: int = 0,
    ) -> tuple[str, object]:
        """Execute request with a specific provider."""
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000)

        start_time = time.time()
        try:
            result = await execute_fn(provider_id)
            latency = (time.time() - start_time) * 1000
            hedged.latencies_ms[provider_id] = latency
            hedged.responses[provider_id] = result
            return provider_id, result
        except _LLM_FAILOVER_OPERATION_ERRORS as e:
            latency = (time.time() - start_time) * 1000
            hedged.latencies_ms[provider_id] = latency
            hedged.errors[provider_id] = str(e)
            raise

    def _create_hedged_tasks(
        self,
        request_id: str,
        selected_providers: list[str],
        execute_fn: Callable[[str], Awaitable[object]],
        hedged: HedgedRequest,
    ) -> list[asyncio.Task]:
        """Create tasks with staggered start for hedged execution."""
        tasks = []
        for i, provider_id in enumerate(selected_providers):
            delay = i * self._hedge_delay_ms
            task = asyncio.create_task(
                self._execute_with_provider(provider_id, execute_fn, hedged, delay),
                name=f"hedge-{request_id}-{provider_id}",
            )
            tasks.append(task)
        return tasks

    async def _wait_for_first_success(self, tasks: list[asyncio.Task]) -> tuple[str, object]:
        """Wait for the first successful task result."""
        done: set[asyncio.Task] = set()
        pending: set[asyncio.Task] = set(tasks)
        winner = None
        result = None

        try:
            while pending and winner is None:
                done, pending = await asyncio.wait(
                    pending,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                winner, result = self._process_completed_tasks(done, pending)

        finally:
            # Ensure all remaining tasks are cancelled
            for task in pending:
                task.cancel()

        if winner is None:
            raise RuntimeError("All hedged providers failed")

        return winner, result

    def _process_completed_tasks(
        self, done: set[asyncio.Task], pending: set[asyncio.Task]
    ) -> tuple[str | None, object | None]:
        """Process completed tasks and return winner if found."""
        for task in done:
            try:
                provider_id, response = task.result()
                # First successful task wins
                for p in pending:
                    p.cancel()
                pending.clear()
                return provider_id, response
            except (RuntimeError, ValueError, ConnectionError, TimeoutError):
                # Task failed, continue waiting for others
                continue
        return None, None

    async def _record_hedged_completion(self, hedged: HedgedRequest, winner: str | None) -> None:
        """Record the completion of a hedged request."""
        hedged.completed_at = datetime.now(UTC)
        hedged.winning_provider = winner

        async with self._lock:
            self._hedged_requests.append(hedged)

        if winner is None:
            # All providers failed
            errors = ", ".join(f"{p}: {e}" for p, e in hedged.errors.items())
            raise RuntimeError(f"All hedged providers failed: {errors}")

        logger.debug(
            f"[{CONSTITUTIONAL_HASH}] Hedged request {hedged.request_id} won by {winner} "
            f"({hedged.latencies_ms.get(winner, 0):.1f}ms)"
        )

    def get_hedging_stats(self) -> JSONDict:
        """Get hedging statistics."""
        requests = list(self._hedged_requests)
        if not requests:
            return {
                "total_hedged_requests": 0,
                "avg_latency_improvement_ms": 0,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }

        # Calculate stats
        successful = [r for r in requests if r.winning_provider]
        latency_improvements = []

        for r in successful:
            if len(r.latencies_ms) > 1:
                winner_latency = r.latencies_ms.get(r.winning_provider, 0)
                other_latencies = [
                    latency for p, latency in r.latencies_ms.items() if p != r.winning_provider
                ]
                if other_latencies:
                    avg_other = statistics.mean(other_latencies)
                    improvement = avg_other - winner_latency
                    latency_improvements.append(improvement)

        return {
            "total_hedged_requests": len(requests),
            "successful_requests": len(successful),
            "success_rate": len(successful) / len(requests) if requests else 1.0,
            "avg_latency_improvement_ms": (
                statistics.mean(latency_improvements) if latency_improvements else 0
            ),
            "provider_win_counts": {
                provider: sum(1 for r in successful if r.winning_provider == provider)
                for provider in set(r.winning_provider for r in successful if r.winning_provider)
            },
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


# =============================================================================
# LLM Failover Orchestrator (re-exported from failover/ package)
# =============================================================================

from enhanced_agent_bus.llm_adapters.failover.orchestrator import (
    LLMFailoverOrchestrator,
    get_llm_failover_orchestrator,
    reset_llm_failover_orchestrator,
)

# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "LLM_CIRCUIT_CONFIGS",
    # Failover
    "FailoverEvent",
    # Health Scoring
    "HealthMetrics",
    # Hedging
    "HedgedRequest",
    # Orchestrator
    "LLMFailoverOrchestrator",
    # Enums
    "LLMProviderType",
    "ProactiveFailoverManager",
    "ProviderHealthScore",
    "ProviderHealthScorer",
    "ProviderWarmupManager",
    "RequestHedgingManager",
    # Warmup
    "WarmupResult",
    # Configuration
    "get_llm_circuit_config",
    "get_llm_failover_orchestrator",
    "reset_llm_failover_orchestrator",
]
