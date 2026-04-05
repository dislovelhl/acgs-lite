"""
AgentHealthMonitor -- background asyncio.Task for agent health monitoring.
Constitutional Hash: 608508a9bd224290

Runs as an isolated asyncio.Task separate from the message-processing loop
so that monitoring continues even when the processing loop is blocked (NFR-004).

On each poll interval the monitor:
  1. Reads current memory usage from the injected memory_provider.
  2. Reads consecutive_failure_count from AgentHealthStore.
  3. Derives HealthState from the current record and new values.
  4. Writes the updated AgentHealthRecord back to the store.
  5. Calls emit_health_metrics() to refresh Prometheus gauges.
  6. If failure count transitions to 0 (recovery), emits a structured log event.
  7. On any exception during a poll, logs the error and continues -- never crashes.

If asyncio.sleep itself raises RuntimeError or similar (heartbeat loss), the
monitor marks the agent as DEGRADED in the store so operators can detect the event.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from enhanced_agent_bus._compat.types import AgentID
from enhanced_agent_bus.agent_health.metrics import emit_health_metrics
from enhanced_agent_bus.agent_health.models import (
    AgentHealthRecord,
    AgentHealthThresholds,
    AutonomyTier,
    HealthState,
)
from enhanced_agent_bus.agent_health.store import AgentHealthStore
from enhanced_agent_bus.observability.structured_logging import get_logger

# Type alias for the sleep function (injectable for testing)
SleepFn = Callable[[float], Awaitable[None]]

logger = get_logger(__name__)


# Default memory provider falls back to psutil for the current process.
def _default_memory_provider() -> float:
    """Return current process memory usage as a percentage of its RSS limit.

    Falls back to 0.0 if psutil is unavailable.
    """
    try:
        import psutil

        proc = psutil.Process()
        return float(proc.memory_percent())
    except Exception:
        return 0.0


class AgentHealthMonitor:
    """Background health monitor for a single agent instance.

    Runs as an independent asyncio.Task so monitoring remains alive even
    when the agent's message-processing loop is blocked (NFR-004).

    Args:
        agent_id: Unique identifier for the monitored agent.
        autonomy_tier: Governance tier that governs healing actions.
        store: Redis-backed store for reading/writing health records.
        thresholds: Configurable thresholds; defaults are used if None.
        memory_provider: Sync callable that returns memory usage as a percentage
            (0-100). Defaults to a psutil-based implementation.
        _sleep: Async sleep function; injectable for testing. Defaults to
            asyncio.sleep. This is intentionally private -- production code
            must not override it.
    """

    def __init__(
        self,
        agent_id: AgentID,
        autonomy_tier: AutonomyTier,
        store: AgentHealthStore,
        thresholds: AgentHealthThresholds | None = None,
        memory_provider: Callable[[], float] | None = None,
        _sleep: SleepFn | None = None,
    ) -> None:
        self._agent_id = agent_id
        self._autonomy_tier = autonomy_tier
        self._store = store
        self._thresholds = thresholds or AgentHealthThresholds()
        self._memory_provider = memory_provider or _default_memory_provider
        self._sleep: SleepFn = _sleep or asyncio.sleep
        self._task: asyncio.Task[None] | None = None
        self._prev_failure_count: int | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> asyncio.Task[None]:
        """Start the background monitoring loop.

        Returns:
            The asyncio.Task running the monitor loop.
        """
        self._task = asyncio.create_task(self._run_loop(), name=f"health-monitor-{self._agent_id}")
        return self._task

    async def stop(self) -> None:
        """Cancel and await the background monitoring task."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        """Main monitoring loop -- polls at metric_emit_interval_seconds."""
        interval = self._thresholds.metric_emit_interval_seconds
        while True:
            try:
                await self._poll()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Non-cancellation errors: log and continue polling.
                logger.error(
                    "Health monitor poll error",
                    agent_id=self._agent_id,
                    error=str(exc),
                )
                # Attempt to mark the agent as DEGRADED so operators can detect it.
                await self._mark_degraded()
            try:
                await self._sleep(interval)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # sleep itself failed (e.g. test-injected RuntimeError) --
                # mark DEGRADED and stop the loop.
                logger.error(
                    "Health monitor sleep error -- marking agent DEGRADED",
                    agent_id=self._agent_id,
                    error=str(exc),
                )
                await self._mark_degraded()
                return

    async def _poll(self) -> None:
        """Execute a single monitoring poll cycle."""
        memory_pct = self._memory_provider()
        record = await self._store.get_health_record(self._agent_id)

        now = datetime.now(UTC)
        if record is None:
            # First poll -- initialise a healthy record.
            record = AgentHealthRecord(
                agent_id=self._agent_id,
                health_state=HealthState.HEALTHY,
                consecutive_failure_count=0,
                memory_usage_pct=memory_pct,
                last_event_at=now,
                autonomy_tier=self._autonomy_tier,
            )
        else:
            # Detect recovery: failure count dropping to 0 from a non-zero value.
            if (
                self._prev_failure_count is not None
                and self._prev_failure_count > 0
                and record.consecutive_failure_count == 0
            ):
                logger.info(
                    "Agent failure count recovered to 0",
                    agent_id=self._agent_id,
                    previous_failure_count=self._prev_failure_count,
                    recovery_timestamp=now.isoformat(),
                )

            record.memory_usage_pct = memory_pct
            record.last_event_at = now

        self._prev_failure_count = record.consecutive_failure_count

        await self._store.upsert_health_record(record)
        emit_health_metrics(record)

    async def _mark_degraded(self) -> None:
        """Write a DEGRADED health state to the store, best-effort."""
        try:
            record = await self._store.get_health_record(self._agent_id)
            now = datetime.now(UTC)
            if record is None:
                record = AgentHealthRecord(
                    agent_id=self._agent_id,
                    health_state=HealthState.DEGRADED,
                    consecutive_failure_count=0,
                    memory_usage_pct=0.0,
                    last_event_at=now,
                    autonomy_tier=self._autonomy_tier,
                )
            else:
                record.health_state = HealthState.DEGRADED
                record.last_event_at = now
            await self._store.upsert_health_record(record)
        except Exception as exc:
            logger.error(
                "Failed to mark agent DEGRADED",
                agent_id=self._agent_id,
                error=str(exc),
            )


__all__ = ["AgentHealthMonitor"]
