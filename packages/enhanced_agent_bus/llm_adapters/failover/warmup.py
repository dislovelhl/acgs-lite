"""
ACGS-2 LLM Failover - Provider Warmup Module
Constitutional Hash: cdd01ef066bc6cf2

Manages provider warmup to reduce cold-start latency.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.circuit_breaker import CONSTITUTIONAL_HASH
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
WARMUP_EXECUTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
)
WARMUP_LOOP_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
)


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

    Constitutional Hash: cdd01ef066bc6cf2

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
        import time

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

        except WARMUP_EXECUTION_ERRORS as e:
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
                    except WARMUP_LOOP_ERRORS as e:
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


__all__ = [
    "ProviderWarmupManager",
    "WarmupResult",
]
