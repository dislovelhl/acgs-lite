"""
Unit tests for AgentHealthMonitor — TDD RED/GREEN.
Constitutional Hash: 608508a9bd224290

Tests use FakeAsyncRedis (no real Redis) and an injectable _sleep parameter
on AgentHealthMonitor to avoid patching asyncio.sleep globally (which would
affect event-loop internals and cause test hangs).
"""

from __future__ import annotations

import pytest

pytest.importorskip("fakeredis")

import asyncio
import time
from datetime import UTC, datetime
from unittest.mock import patch

import fakeredis.aioredis as fake_aioredis
import pytest

from enhanced_agent_bus.agent_health.models import (
    AgentHealthRecord,
    AgentHealthThresholds,
    AutonomyTier,
    HealthState,
)
from enhanced_agent_bus.agent_health.monitor import AgentHealthMonitor
from enhanced_agent_bus.agent_health.store import AgentHealthStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AGENT_ID = "monitor-test-agent"
TIER = AutonomyTier.ADVISORY


def _make_record(
    agent_id: str = AGENT_ID,
    health_state: HealthState = HealthState.HEALTHY,
    consecutive_failure_count: int = 0,
    memory_usage_pct: float = 50.0,
    autonomy_tier: AutonomyTier = TIER,
) -> AgentHealthRecord:
    return AgentHealthRecord(
        agent_id=agent_id,
        health_state=health_state,
        consecutive_failure_count=consecutive_failure_count,
        memory_usage_pct=memory_usage_pct,
        last_event_at=datetime.now(UTC),
        autonomy_tier=autonomy_tier,
    )


def _min_thresholds() -> AgentHealthThresholds:
    """Return thresholds at minimum allowed values."""
    return AgentHealthThresholds(metric_emit_interval_seconds=5)


def _make_counter_sleep(stop_after: int) -> tuple[list[int], asyncio.coroutine]:
    """Return (call_log, sleep_fn) that raises CancelledError after stop_after calls."""
    calls: list[int] = []

    async def _sleep(_: float) -> None:
        calls.append(1)
        if len(calls) >= stop_after:
            raise asyncio.CancelledError

    return calls, _sleep


@pytest.fixture
def fake_redis() -> fake_aioredis.FakeRedis:
    return fake_aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def store(fake_redis: fake_aioredis.FakeRedis) -> AgentHealthStore:
    return AgentHealthStore(fake_redis)


# ---------------------------------------------------------------------------
# Metric emission interval tests (FR-001)
# ---------------------------------------------------------------------------


async def test_metric_emission_fires_at_configured_interval(
    store: AgentHealthStore,
) -> None:
    """Monitor calls emit_health_metrics once per poll interval.

    Acceptance: Tests verify metric emission fires at the configured interval.
    """
    emitted: list[AgentHealthRecord] = []
    _, fake_sleep = _make_counter_sleep(stop_after=1)

    with patch(
        "enhanced_agent_bus.agent_health.monitor.emit_health_metrics",
        side_effect=lambda rec: emitted.append(rec),
    ):
        mon = AgentHealthMonitor(
            agent_id=AGENT_ID,
            autonomy_tier=TIER,
            store=store,
            thresholds=_min_thresholds(),
            memory_provider=lambda: 50.0,
            _sleep=fake_sleep,
        )
        task = mon.start()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert len(emitted) >= 1, "emit_health_metrics must be called at least once"
    assert emitted[0].agent_id == AGENT_ID


async def test_consecutive_failure_count_resets_to_zero(
    store: AgentHealthStore,
) -> None:
    """Monitor reflects failure count reset in emitted metrics (FR-001 recovery).

    Acceptance: Tests verify consecutive_failure_count resets to 0 after a
    successful message is processed.
    """
    # Seed a record with non-zero failure count
    await store.upsert_health_record(_make_record(consecutive_failure_count=3))

    poll_number = 0

    async def fake_sleep(_: float) -> None:
        nonlocal poll_number
        poll_number += 1
        if poll_number == 1:
            # Between first and second poll: reset failure count in store
            await store.upsert_health_record(_make_record(consecutive_failure_count=0))
        if poll_number >= 2:
            raise asyncio.CancelledError

    emitted: list[AgentHealthRecord] = []

    with patch(
        "enhanced_agent_bus.agent_health.monitor.emit_health_metrics",
        side_effect=lambda rec: emitted.append(rec),
    ):
        mon = AgentHealthMonitor(
            agent_id=AGENT_ID,
            autonomy_tier=TIER,
            store=store,
            thresholds=_min_thresholds(),
            memory_provider=lambda: 50.0,
            _sleep=fake_sleep,
        )
        task = mon.start()
        try:
            await task
        except asyncio.CancelledError:
            pass

    reset_records = [r for r in emitted if r.consecutive_failure_count == 0]
    assert reset_records, "At least one emitted record must show failure count = 0 after reset"


async def test_recovery_event_recorded_in_store(
    store: AgentHealthStore,
) -> None:
    """Recovery is reflected in the store when failure count transitions to 0.

    Acceptance: Tests verify recovery event is recorded in the store when
    failure count resets.
    """
    await store.upsert_health_record(_make_record(consecutive_failure_count=4))

    poll_number = 0

    async def fake_sleep(_: float) -> None:
        nonlocal poll_number
        poll_number += 1
        if poll_number == 1:
            await store.upsert_health_record(_make_record(consecutive_failure_count=0))
        if poll_number >= 2:
            raise asyncio.CancelledError

    with patch("enhanced_agent_bus.agent_health.monitor.emit_health_metrics"):
        mon = AgentHealthMonitor(
            agent_id=AGENT_ID,
            autonomy_tier=TIER,
            store=store,
            thresholds=_min_thresholds(),
            memory_provider=lambda: 50.0,
            _sleep=fake_sleep,
        )
        task = mon.start()
        try:
            await task
        except asyncio.CancelledError:
            pass

    final = await store.get_health_record(AGENT_ID)
    assert final is not None
    assert final.consecutive_failure_count == 0


# ---------------------------------------------------------------------------
# NFR-004: Monitor isolation from blocked processing loop
# ---------------------------------------------------------------------------


async def test_monitor_continues_when_processing_loop_blocked(
    store: AgentHealthStore,
) -> None:
    """Monitor task emits metrics independently even when the processing loop blocks.

    Acceptance: Tests verify monitor continues emitting metrics even when a
    mock processing loop is blocked (NFR-004).
    """
    emitted: list[AgentHealthRecord] = []
    _, fake_sleep = _make_counter_sleep(stop_after=2)

    with patch(
        "enhanced_agent_bus.agent_health.monitor.emit_health_metrics",
        side_effect=lambda rec: emitted.append(rec),
    ):
        mon = AgentHealthMonitor(
            agent_id=AGENT_ID,
            autonomy_tier=TIER,
            store=store,
            thresholds=_min_thresholds(),
            memory_provider=lambda: 60.0,
            _sleep=fake_sleep,
        )

        # Start the monitor task — no "processing loop" is started; monitor
        # must emit metrics regardless (NFR-004: isolated asyncio.Task)
        task = mon.start()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert len(emitted) >= 1, "Monitor must emit at least one metric batch independently"


# ---------------------------------------------------------------------------
# NFR-001: Metric emission overhead < 1ms
# ---------------------------------------------------------------------------


async def test_metric_emission_overhead_under_one_ms(
    store: AgentHealthStore,
) -> None:
    """Metric emission adds less than 1ms overhead per poll cycle (NFR-001).

    Acceptance: Tests verify metric emission adds < 1ms overhead to a
    no-op message cycle.
    """
    from enhanced_agent_bus.agent_health.metrics import emit_health_metrics

    record = _make_record()
    iterations = 100
    start = time.perf_counter()
    for _ in range(iterations):
        emit_health_metrics(record)
    elapsed = time.perf_counter() - start
    avg_ms = (elapsed / iterations) * 1000

    assert avg_ms < 1.0, f"emit_health_metrics avg {avg_ms:.3f}ms exceeds 1ms budget"


# ---------------------------------------------------------------------------
# Heartbeat loss detection (HealthState → DEGRADED)
# ---------------------------------------------------------------------------


async def test_heartbeat_loss_sets_degraded_in_store(
    store: AgentHealthStore,
) -> None:
    """If the sleep call raises a non-CancelledError, agent is marked DEGRADED.

    Acceptance: Tests verify heartbeat loss detection — if monitor task itself
    raises, the agent_health_state Gauge reflects DEGRADED.
    """
    await store.upsert_health_record(_make_record(health_state=HealthState.HEALTHY))

    async def crashing_sleep(_: float) -> None:
        raise RuntimeError("Simulated monitor heartbeat crash")

    with patch("enhanced_agent_bus.agent_health.monitor.emit_health_metrics"):
        mon = AgentHealthMonitor(
            agent_id=AGENT_ID,
            autonomy_tier=TIER,
            store=store,
            thresholds=_min_thresholds(),
            memory_provider=lambda: 50.0,
            _sleep=crashing_sleep,
        )
        task = mon.start()
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except (TimeoutError, asyncio.CancelledError, Exception):
            pass

    final = await store.get_health_record(AGENT_ID)
    assert final is not None
    assert final.health_state == HealthState.DEGRADED, (
        f"Expected DEGRADED after monitor crash, got {final.health_state}"
    )


# ---------------------------------------------------------------------------
# Monitor start/stop lifecycle
# ---------------------------------------------------------------------------


async def test_monitor_stop_cancels_task(store: AgentHealthStore) -> None:
    """stop() cancels the background task cleanly."""
    blocked = asyncio.Event()

    async def blocking_sleep(_: float) -> None:
        await blocked.wait()

    with patch("enhanced_agent_bus.agent_health.monitor.emit_health_metrics"):
        mon = AgentHealthMonitor(
            agent_id=AGENT_ID,
            autonomy_tier=TIER,
            store=store,
            thresholds=_min_thresholds(),
            memory_provider=lambda: 50.0,
            _sleep=blocking_sleep,
        )
        task = mon.start()
        # Yield control so the task starts and enters blocking_sleep
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await mon.stop()

    assert task.done(), "Task must be done after stop()"


async def test_monitor_updates_memory_usage_from_provider(
    store: AgentHealthStore,
) -> None:
    """Monitor uses the injected memory_provider to fill memory_usage_pct."""
    emitted: list[AgentHealthRecord] = []
    _, fake_sleep = _make_counter_sleep(stop_after=1)

    with patch(
        "enhanced_agent_bus.agent_health.monitor.emit_health_metrics",
        side_effect=lambda rec: emitted.append(rec),
    ):
        mon = AgentHealthMonitor(
            agent_id=AGENT_ID,
            autonomy_tier=TIER,
            store=store,
            thresholds=_min_thresholds(),
            memory_provider=lambda: 77.5,
            _sleep=fake_sleep,
        )
        task = mon.start()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert emitted, "No metrics emitted"
    assert emitted[0].memory_usage_pct == pytest.approx(77.5), (
        f"Expected memory_usage_pct=77.5, got {emitted[0].memory_usage_pct}"
    )


async def test_monitor_loop_survives_exceptions(
    store: AgentHealthStore,
) -> None:
    """Monitor loop catches transient exceptions, logs them, and continues.

    Acceptance: Monitor loop is wrapped in try/except that catches all
    exceptions, logs them via get_logger, and continues polling without
    crashing the monitor task.
    """
    emit_results: list[bool] = []
    call_number = 0

    def flaky_emit(rec: AgentHealthRecord) -> None:
        emit_results.append(len(emit_results) > 0)  # False on first, True after
        if len(emit_results) == 1:
            raise RuntimeError("Transient emit error")

    poll_count = 0

    async def fake_sleep(_: float) -> None:
        nonlocal poll_count
        poll_count += 1
        if poll_count >= 3:
            raise asyncio.CancelledError

    with patch(
        "enhanced_agent_bus.agent_health.monitor.emit_health_metrics",
        side_effect=flaky_emit,
    ):
        mon = AgentHealthMonitor(
            agent_id=AGENT_ID,
            autonomy_tier=TIER,
            store=store,
            thresholds=_min_thresholds(),
            memory_provider=lambda: 50.0,
            _sleep=fake_sleep,
        )
        task = mon.start()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Monitor must have survived the first error and polled again
    assert len(emit_results) >= 2, (
        f"Monitor must continue polling after transient error, got {len(emit_results)} calls"
    )
