"""
ACGS-2 LLM Failover - Request Hedging Module
Constitutional Hash: cdd01ef066bc6cf2

Implements request hedging for critical operations.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from packages.enhanced_agent_bus.circuit_breaker import CONSTITUTIONAL_HASH
from src.core.shared.types import JSONDict

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
HEDGED_EXECUTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)


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

    Constitutional Hash: cdd01ef066bc6cf2

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

        # Wait for first success, ensuring request is always recorded
        winner = None
        result = None
        try:
            winner, result = await self._wait_for_first_success(tasks, hedged.errors)
        finally:
            # Always record completion (success or failure)
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
        except HEDGED_EXECUTION_ERRORS as e:
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

    async def _wait_for_first_success(
        self, tasks: list[asyncio.Task], errors: dict[str, str] | None = None
    ) -> tuple[str, object]:
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
            if errors:
                error_details = "; ".join(f"{p}: {e}" for p, e in errors.items())
                raise RuntimeError(f"All hedged providers failed: {error_details}")
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

        if winner is not None:
            logger.debug(
                f"[{CONSTITUTIONAL_HASH}] Hedged request {hedged.request_id} won by {winner} "
                f"({hedged.latencies_ms.get(winner, 0):.1f}ms)"
            )
        else:
            logger.debug(
                f"[{CONSTITUTIONAL_HASH}] Hedged request {hedged.request_id} completed with no winner (all providers failed)"  # noqa: E501
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


__all__ = [
    "HedgedRequest",
    "RequestHedgingManager",
]
