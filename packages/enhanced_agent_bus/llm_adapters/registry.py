"""
ACGS-2 Enhanced Agent Bus - LLM Adapter Registry
Constitutional Hash: cdd01ef066bc6cf2

Registry system for discovering, registering, and managing LLM adapters
with fallback chains, health checks, and circuit breaker pattern.
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone

from src.core.shared import metrics as shared_metrics

# Import centralized constitutional hash from shared module
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from src.core.shared.errors.exceptions import (
    ResourceNotFoundError,
    ServiceUnavailableError,
)
from src.core.shared.errors.exceptions import (
    ValidationError as ACGSValidationError,
)

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from ..circuit_breaker.enums import CircuitState as CircuitBreakerState
from .base import (
    AdapterStatus,
    BaseLLMAdapter,
    HealthCheckResult,
    LLMMessage,
    LLMResponse,
)
from .config import AdapterConfig, AdapterType

logger = get_logger(__name__)
_REGISTRY_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker pattern.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: float = 60.0
    half_open_max_calls: int = 1
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "failure_threshold": self.failure_threshold,
            "success_threshold": self.success_threshold,
            "timeout_seconds": self.timeout_seconds,
            "half_open_max_calls": self.half_open_max_calls,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class AdapterMetrics:
    """Metrics tracking for an adapter.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    adapter_id: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    avg_latency_ms: float = 0.0
    last_request_time: datetime | None = None
    last_health_check: datetime | None = None
    last_health_status: AdapterStatus = AdapterStatus.HEALTHY
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "adapter_id": self.adapter_id,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "avg_latency_ms": self.avg_latency_ms,
            "success_rate": self.success_rate,
            "last_request_time": (
                self.last_request_time.isoformat() if self.last_request_time else None
            ),
            "last_health_check": (
                self.last_health_check.isoformat() if self.last_health_check else None
            ),
            "last_health_status": self.last_health_status.value,
            "constitutional_hash": self.constitutional_hash,
        }

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100.0

    def record_request(
        self,
        success: bool,
        latency_ms: float,
        tokens: int = 0,
        cost_usd: float = 0.0,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        """Record a request and update metrics.

        When provider/model are supplied, also emit shared Prometheus metrics
        for LLM usage and latency. Prometheus updates are best-effort and
        must never raise.
        """
        self.total_requests += 1
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1

        self.total_tokens += tokens
        self.total_cost_usd += cost_usd

        # Update rolling average latency
        if self.avg_latency_ms == 0.0:
            self.avg_latency_ms = latency_ms
        else:
            # Exponential moving average with alpha=0.1
            self.avg_latency_ms = 0.9 * self.avg_latency_ms + 0.1 * latency_ms

        self.last_request_time = datetime.now(UTC)

        # Best-effort Prometheus metrics for LLM usage
        if provider and model:
            try:
                outcome = "success" if success else "error"
                # Convert ms to seconds for histogram
                shared_metrics.LLM_REQUEST_DURATION.labels(
                    provider=provider,
                    model=model,
                    outcome=outcome,
                ).observe(latency_ms / 1000.0)
                shared_metrics.LLM_REQUESTS_TOTAL.labels(
                    provider=provider,
                    model=model,
                    outcome=outcome,
                ).inc()

                if tokens > 0:
                    shared_metrics.LLM_TOKENS_TOTAL.labels(
                        provider=provider,
                        model=model,
                        token_type="total",
                    ).inc(tokens)

                if cost_usd > 0.0:
                    shared_metrics.LLM_COST_USD_TOTAL.labels(
                        provider=provider,
                        model=model,
                    ).inc(cost_usd)
            except Exception:  # pragma: no cover - metrics must never break registry
                # Metrics failures are intentionally ignored to keep the
                # adapter registry on the fast path even if Prometheus
                # instrumentation misbehaves.
                return


class CircuitBreaker:
    """Circuit breaker for adapter fault tolerance.

    .. deprecated::
        Use ``src.core.shared.errors.circuit_breaker.SimpleCircuitBreaker`` (or the
        ``@circuit_breaker`` decorator) instead.
        This local implementation in the LLM adapter registry exists for
        historical reasons and is not maintained as the canonical version.

    Constitutional Hash: cdd01ef066bc6cf2

    Implements the circuit breaker pattern to prevent cascading failures
    and allow adapters to recover from temporary issues.
    """

    def __init__(
        self,
        adapter_id: str,
        config: CircuitBreakerConfig | None = None,
    ) -> None:
        """Initialize circuit breaker.

        Args:
            adapter_id: Unique identifier for the adapter
            config: Circuit breaker configuration
        """
        self.adapter_id = adapter_id
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float | None = None
        self.half_open_calls = 0
        self._lock = asyncio.Lock()

    async def call(self, func: object, *args: object, **kwargs: object) -> object:
        """Execute function through circuit breaker.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from successful function execution

        Raises:
            Exception: If circuit is open or function fails
        """
        async with self._lock:
            if self.state == CircuitBreakerState.OPEN:
                if self._should_attempt_reset():
                    logger.info(f"Circuit breaker for {self.adapter_id} moving to HALF_OPEN")
                    self.state = CircuitBreakerState.HALF_OPEN
                    self.half_open_calls = 0
                else:
                    raise ServiceUnavailableError(
                        f"Circuit breaker OPEN for adapter {self.adapter_id}",
                        error_code="LLM_CIRCUIT_BREAKER_OPEN",
                    )

            if self.state == CircuitBreakerState.HALF_OPEN:
                if self.half_open_calls >= self.config.half_open_max_calls:
                    raise ServiceUnavailableError(
                        f"Circuit breaker HALF_OPEN limit reached for {self.adapter_id}",
                        error_code="LLM_CIRCUIT_BREAKER_HALF_OPEN_LIMIT",
                    )
                self.half_open_calls += 1

        # Execute the function
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except _REGISTRY_OPERATION_ERRORS as e:
            await self._on_failure()
            raise e

    async def _on_success(self) -> None:
        """Handle successful request."""
        async with self._lock:
            self.failure_count = 0

            if self.state == CircuitBreakerState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    logger.info(f"Circuit breaker for {self.adapter_id} moving to CLOSED")
                    self.state = CircuitBreakerState.CLOSED
                    self.success_count = 0

    async def _on_failure(self) -> None:
        """Handle failed request."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitBreakerState.HALF_OPEN:
                logger.warning(f"Circuit breaker for {self.adapter_id} moving back to OPEN")
                self.state = CircuitBreakerState.OPEN
                self.success_count = 0
            elif self.failure_count >= self.config.failure_threshold:
                logger.warning(
                    f"Circuit breaker for {self.adapter_id} moving to OPEN "
                    f"after {self.failure_count} failures"
                )
                self.state = CircuitBreakerState.OPEN

    def _should_attempt_reset(self) -> bool:
        """Check if we should attempt to reset circuit breaker."""
        if self.last_failure_time is None:
            return True

        elapsed = time.time() - self.last_failure_time
        return elapsed >= self.config.timeout_seconds

    def get_state(self) -> CircuitBreakerState:
        """Get current circuit breaker state."""
        return self.state

    def is_available(self) -> bool:
        """Check if circuit breaker allows requests."""
        if self.state == CircuitBreakerState.CLOSED:
            return True
        if self.state == CircuitBreakerState.HALF_OPEN:
            return self.half_open_calls < self.config.half_open_max_calls
        return False


@dataclass
class FallbackChain:
    """Configuration for adapter fallback chain.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    primary: str
    fallbacks: list[str] = field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def get_ordered_adapters(self) -> list[str]:
        """Get adapters in priority order."""
        return [self.primary] + self.fallbacks

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "primary": self.primary,
            "fallbacks": self.fallbacks,
            "constitutional_hash": self.constitutional_hash,
        }


class LLMAdapterRegistry:
    """Registry for managing LLM adapters with fallback chains.

    Constitutional Hash: cdd01ef066bc6cf2

    Provides:
    - Dynamic adapter registration and discovery
    - Fallback chain management
    - Health checks and circuit breaker pattern
    - Metrics tracking per adapter
    - Thread-safe operations
    """

    def __init__(
        self,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
        health_check_interval_seconds: float = 60.0,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ) -> None:
        """Initialize adapter registry.

        Args:
            circuit_breaker_config: Configuration for circuit breakers
            health_check_interval_seconds: Interval between health checks
            constitutional_hash: Constitutional hash for compliance
        """
        self.constitutional_hash = constitutional_hash
        self.circuit_breaker_config = circuit_breaker_config or CircuitBreakerConfig()
        self.health_check_interval = health_check_interval_seconds

        # Registry storage
        self._adapters: dict[str, BaseLLMAdapter] = {}
        self._adapter_types: dict[str, type[BaseLLMAdapter]] = {}
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._metrics: dict[str, AdapterMetrics] = {}
        self._fallback_chains: dict[str, FallbackChain] = {}
        self._tags: dict[str, set[str]] = defaultdict(set)

        # Thread safety
        self._lock = asyncio.Lock()

        # Health check task
        self._health_check_task: asyncio.Task | None = None
        self._running = False

        logger.info(
            f"Initialized LLMAdapterRegistry with constitutional hash: "
            f"{self.constitutional_hash[:8]}..."
        )

    async def register_adapter_type(
        self,
        adapter_type: str,
        adapter_class: type[BaseLLMAdapter],
    ) -> None:
        """Register an adapter class for dynamic instantiation.

        Args:
            adapter_type: type identifier (e.g., "openai", "anthropic")
            adapter_class: Adapter class to register
        """
        async with self._lock:
            self._adapter_types[adapter_type] = adapter_class
            logger.info(f"Registered adapter type: {adapter_type}")

    async def register_adapter(
        self,
        adapter_id: str,
        adapter: BaseLLMAdapter,
        tags: list[str] | None = None,
    ) -> None:
        """Register an adapter instance.

        Args:
            adapter_id: Unique identifier for the adapter
            adapter: Adapter instance to register
            tags: Optional tags for categorization
        """
        async with self._lock:
            if adapter_id in self._adapters:
                logger.warning(f"Adapter {adapter_id} already registered, replacing")

            self._adapters[adapter_id] = adapter
            self._circuit_breakers[adapter_id] = CircuitBreaker(
                adapter_id,
                self.circuit_breaker_config,
            )
            self._metrics[adapter_id] = AdapterMetrics(adapter_id=adapter_id)

            if tags:
                self._tags[adapter_id] = set(tags)

            logger.info(f"Registered adapter: {adapter_id}")

    async def unregister_adapter(self, adapter_id: str) -> bool:
        """Unregister an adapter.

        Args:
            adapter_id: Adapter to unregister

        Returns:
            True if adapter was unregistered, False if not found
        """
        async with self._lock:
            if adapter_id not in self._adapters:
                return False

            del self._adapters[adapter_id]
            del self._circuit_breakers[adapter_id]
            del self._metrics[adapter_id]
            self._tags.pop(adapter_id, None)

            # Remove from fallback chains
            for chain_id, chain in list(self._fallback_chains.items()):
                if adapter_id == chain.primary or adapter_id in chain.fallbacks:
                    del self._fallback_chains[chain_id]

            logger.info(f"Unregistered adapter: {adapter_id}")
            return True

    async def get_adapter(self, adapter_id: str) -> BaseLLMAdapter | None:
        """Get an adapter by ID.

        Args:
            adapter_id: Adapter identifier

        Returns:
            Adapter instance or None if not found
        """
        async with self._lock:
            return self._adapters.get(adapter_id)

    async def list_adapters(
        self,
        tags: list[str] | None = None,
        status: AdapterStatus | None = None,
    ) -> list[str]:
        """list registered adapters.

        Args:
            tags: Filter by tags (any match)
            status: Filter by health status

        Returns:
            list of adapter IDs
        """
        async with self._lock:
            adapter_ids = list(self._adapters.keys())

            # Filter by tags
            if tags:
                adapter_ids = [
                    aid
                    for aid in adapter_ids
                    if any(tag in self._tags.get(aid, set()) for tag in tags)
                ]

            # Filter by status
            if status:
                adapter_ids = [
                    aid
                    for aid in adapter_ids
                    if self._metrics.get(aid, AdapterMetrics(aid)).last_health_status == status
                ]

            return adapter_ids

    async def configure_fallback_chain(
        self,
        chain_id: str,
        primary: str,
        fallbacks: list[str],
    ) -> None:
        """Configure a fallback chain for adapter redundancy.

        Args:
            chain_id: Unique identifier for the chain
            primary: Primary adapter ID
            fallbacks: Ordered list of fallback adapter IDs

        Raises:
            ValueError: If any adapter in chain is not registered
        """
        async with self._lock:
            # Validate all adapters exist
            all_adapters = [primary] + fallbacks
            for adapter_id in all_adapters:
                if adapter_id not in self._adapters:
                    raise ResourceNotFoundError(
                        f"Adapter {adapter_id} not registered",
                        error_code="LLM_ADAPTER_NOT_REGISTERED",
                    )

            self._fallback_chains[chain_id] = FallbackChain(
                primary=primary,
                fallbacks=fallbacks,
            )

            logger.info(
                f"Configured fallback chain '{chain_id}': primary={primary}, fallbacks={fallbacks}"
            )

    async def complete_with_fallback(
        self,
        chain_id: str,
        messages: list[LLMMessage],
        **kwargs: object,
    ) -> LLMResponse:
        """Execute completion with automatic fallback.

        Args:
            chain_id: Fallback chain identifier
            messages: Messages for completion
            **kwargs: Additional parameters for completion

        Returns:
            LLMResponse from first successful adapter

        Raises:
            RuntimeError: If all adapters in chain fail
        """
        chain = self._fallback_chains.get(chain_id)
        if not chain:
            raise ResourceNotFoundError(
                f"Fallback chain {chain_id} not found",
                error_code="LLM_FALLBACK_CHAIN_NOT_FOUND",
            )

        adapters = chain.get_ordered_adapters()
        last_error = None

        for adapter_id in adapters:
            adapter = await self.get_adapter(adapter_id)
            if not adapter:
                logger.warning(f"Adapter {adapter_id} not found in chain {chain_id}")
                continue

            # Check circuit breaker
            breaker = self._circuit_breakers.get(adapter_id)
            if not breaker or not breaker.is_available():
                logger.warning(f"Adapter {adapter_id} circuit breaker is open, trying next")
                continue

            # Try completion
            try:
                start_time = time.time()

                # Wrap in circuit breaker (bind adapter to avoid B023)
                async def _complete(adapter=adapter):
                    return await adapter.acomplete(messages, **kwargs)

                response = await breaker.call(_complete)

                # Record metrics
                latency_ms = (time.time() - start_time) * 1000
                metrics = self._metrics.get(adapter_id)
                if metrics:
                    metrics.record_request(
                        success=True,
                        latency_ms=latency_ms,
                        tokens=response.usage.total_tokens,
                        cost_usd=response.cost.total_cost_usd,
                        provider=response.metadata.provider,
                        model=response.metadata.model,
                    )

                logger.info(
                    f"Completion successful with adapter {adapter_id} "
                    f"in chain {chain_id} (latency: {latency_ms:.2f}ms)"
                )

                return response

            except _REGISTRY_OPERATION_ERRORS as e:
                last_error = e
                logger.warning(
                    f"Adapter {adapter_id} failed in chain {chain_id}: {e}, trying next fallback"
                )

                # Record failed request
                metrics = self._metrics.get(adapter_id)
                if metrics:
                    metrics.record_request(
                        success=False,
                        latency_ms=0,
                        tokens=0,
                        cost_usd=0.0,
                        provider=None,
                        model=None,
                    )

        # All adapters failed
        raise ServiceUnavailableError(
            f"All adapters in fallback chain {chain_id} failed. Last error: {last_error}",
            error_code="LLM_ALL_ADAPTERS_FAILED",
        )

    async def health_check(self, adapter_id: str) -> HealthCheckResult:
        """Perform health check on an adapter.

        Args:
            adapter_id: Adapter to check

        Returns:
            HealthCheckResult

        Raises:
            ValueError: If adapter not found
        """
        adapter = await self.get_adapter(adapter_id)
        if not adapter:
            raise ResourceNotFoundError(
                f"Adapter {adapter_id} not found",
                error_code="LLM_ADAPTER_NOT_FOUND",
            )

        try:
            result = await adapter.health_check()

            # Update metrics
            metrics = self._metrics.get(adapter_id)
            if metrics:
                metrics.last_health_check = datetime.now(UTC)
                metrics.last_health_status = result.status

            return result

        except _REGISTRY_OPERATION_ERRORS as e:
            logger.error(f"Health check failed for adapter {adapter_id}: {e}")

            result = HealthCheckResult(
                status=AdapterStatus.UNHEALTHY,
                message=f"Health check error: {e}",
                details={"error": str(e)},
            )

            # Update metrics
            metrics = self._metrics.get(adapter_id)
            if metrics:
                metrics.last_health_check = datetime.now(UTC)
                metrics.last_health_status = result.status

            return result

    async def health_check_all(self) -> dict[str, HealthCheckResult]:
        """Perform health checks on all registered adapters.

        Returns:
            Dictionary mapping adapter IDs to health check results
        """
        results = {}
        adapters = await self.list_adapters()

        for adapter_id in adapters:
            try:
                results[adapter_id] = await self.health_check(adapter_id)
            except _REGISTRY_OPERATION_ERRORS as e:
                logger.error(f"Failed to health check adapter {adapter_id}: {e}")
                results[adapter_id] = HealthCheckResult(
                    status=AdapterStatus.UNAVAILABLE,
                    message=str(e),
                )

        return results

    async def get_metrics(self, adapter_id: str) -> AdapterMetrics | None:
        """Get metrics for an adapter.

        Args:
            adapter_id: Adapter identifier

        Returns:
            AdapterMetrics or None if not found
        """
        async with self._lock:
            return self._metrics.get(adapter_id)

    async def get_all_metrics(self) -> dict[str, AdapterMetrics]:
        """Get metrics for all adapters.

        Returns:
            Dictionary mapping adapter IDs to metrics
        """
        async with self._lock:
            return dict(self._metrics)

    async def get_circuit_breaker_state(
        self,
        adapter_id: str,
    ) -> CircuitBreakerState | None:
        """Get circuit breaker state for an adapter.

        Args:
            adapter_id: Adapter identifier

        Returns:
            CircuitBreakerState or None if not found
        """
        async with self._lock:
            breaker = self._circuit_breakers.get(adapter_id)
            return breaker.get_state() if breaker else None

    async def start_health_monitoring(self) -> None:
        """Start background health monitoring task."""
        if self._running:
            logger.warning("Health monitoring already running")
            return

        self._running = True
        self._health_check_task = asyncio.create_task(self._health_monitor_loop())
        logger.info("Started adapter health monitoring")

    async def stop_health_monitoring(self) -> None:
        """Stop background health monitoring task."""
        self._running = False

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None

        logger.info("Stopped adapter health monitoring")

    async def _health_monitor_loop(self) -> None:
        """Background task for periodic health checks."""
        while self._running:
            try:
                await self.health_check_all()
            except _REGISTRY_OPERATION_ERRORS as e:
                logger.error(f"Error in health monitor loop: {e}")

            await asyncio.sleep(self.health_check_interval)

    def to_dict(self) -> JSONDict:
        """Convert registry state to dictionary.

        Returns:
            Dictionary representation of registry state
        """
        return {
            "constitutional_hash": self.constitutional_hash,
            "adapters": list(self._adapters.keys()),
            "adapter_count": len(self._adapters),
            "fallback_chains": {
                chain_id: chain.to_dict() for chain_id, chain in self._fallback_chains.items()
            },
            "metrics": {
                adapter_id: metrics.to_dict() for adapter_id, metrics in self._metrics.items()
            },
            "circuit_breakers": {
                adapter_id: {
                    "state": breaker.get_state().value,
                    "failure_count": breaker.failure_count,
                    "available": breaker.is_available(),
                }
                for adapter_id, breaker in self._circuit_breakers.items()
            },
        }

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start_health_monitoring()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop_health_monitoring()


__all__ = [
    # Metrics and fallback
    "AdapterMetrics",
    # Circuit breaker
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerState",
    "FallbackChain",
    # Main registry class
    "LLMAdapterRegistry",
]
