"""
Coverage tests for batch21d:
  1. agent_health/monitor.py
  2. agent_health/store.py
  3. llm_adapters/cost/anomaly.py
  4. adapters/openai_adapter.py

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# agent_health models (used by monitor + store tests)
# ---------------------------------------------------------------------------
from enhanced_agent_bus.agent_health.models import (
    AgentHealthRecord,
    AgentHealthThresholds,
    AutonomyTier,
    HealingAction,
    HealingActionType,
    HealingOverride,
    HealingTrigger,
    HealthState,
    OverrideMode,
)

# ---------------------------------------------------------------------------
# Modules under test
# ---------------------------------------------------------------------------
from enhanced_agent_bus.agent_health.monitor import (
    AgentHealthMonitor,
    _default_memory_provider,
)
from enhanced_agent_bus.agent_health.store import (
    HEALTH_RECORD_TTL_SECONDS,
    AgentHealthStore,
    _hash_to_override,
    _hash_to_record,
    _health_key,
    _override_key,
    _override_to_hash,
    _record_to_hash,
)
from enhanced_agent_bus.llm_adapters.cost.anomaly import CostAnomalyDetector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime.now(UTC)


def _make_record(
    agent_id: str = "agent-1",
    state: HealthState = HealthState.HEALTHY,
    failures: int = 0,
    memory: float = 25.0,
) -> AgentHealthRecord:
    return AgentHealthRecord(
        agent_id=agent_id,
        health_state=state,
        consecutive_failure_count=failures,
        memory_usage_pct=memory,
        last_event_at=NOW,
        autonomy_tier=AutonomyTier.BOUNDED,
    )


def _make_override(
    agent_id: str = "agent-1",
    override_id: str = "ov-1",
    mode: OverrideMode = OverrideMode.SUPPRESS_HEALING,
    expires_at: datetime | None = None,
) -> HealingOverride:
    return HealingOverride(
        override_id=override_id,
        agent_id=agent_id,
        mode=mode,
        reason="test reason",
        issued_by="operator",
        issued_at=NOW,
        expires_at=expires_at,
    )


def _make_healing_action(agent_id: str = "agent-1") -> HealingAction:
    return HealingAction(
        agent_id=agent_id,
        trigger=HealingTrigger.FAILURE_LOOP,
        action_type=HealingActionType.QUARANTINE,
        tier_determined_by=AutonomyTier.BOUNDED,
        initiated_at=NOW,
        audit_event_id="audit-1",
    )


def _fake_redis() -> AsyncMock:
    """Return a mock Redis client with standard async methods."""
    r = AsyncMock()
    r.hgetall = AsyncMock(return_value={})
    r.hset = AsyncMock()
    r.expire = AsyncMock()
    r.delete = AsyncMock(return_value=0)
    return r


# ===================================================================
# SECTION 1: agent_health/store.py
# ===================================================================


class TestStoreHelpers:
    """Tests for module-level serialisation helpers."""

    def test_health_key(self) -> None:
        assert _health_key("a1") == "agent_health:a1"

    def test_override_key(self) -> None:
        assert _override_key("a1") == "agent_healing_override:a1"

    def test_record_roundtrip(self) -> None:
        rec = _make_record()
        h = _record_to_hash(rec)
        assert isinstance(h, dict)
        assert h["agent_id"] == "agent-1"
        assert h["health_state"] == "HEALTHY"
        assert h["consecutive_failure_count"] == "0"
        restored = _hash_to_record(h)
        assert restored.agent_id == rec.agent_id
        assert restored.health_state == rec.health_state

    def test_record_roundtrip_with_optionals(self) -> None:
        rec = _make_record()
        rec.last_error_type = "RuntimeError"
        rec.healing_override_id = "ov-99"
        h = _record_to_hash(rec)
        restored = _hash_to_record(h)
        assert restored.last_error_type == "RuntimeError"
        assert restored.healing_override_id == "ov-99"

    def test_record_roundtrip_empty_optionals(self) -> None:
        rec = _make_record()
        h = _record_to_hash(rec)
        assert h["last_error_type"] == ""
        assert h["healing_override_id"] == ""
        restored = _hash_to_record(h)
        assert restored.last_error_type is None
        assert restored.healing_override_id is None

    def test_override_roundtrip(self) -> None:
        ov = _make_override()
        h = _override_to_hash(ov)
        assert h["mode"] == "SUPPRESS_HEALING"
        assert h["expires_at"] == ""
        restored = _hash_to_override(h)
        assert restored.override_id == ov.override_id
        assert restored.expires_at is None

    def test_override_roundtrip_with_expiry(self) -> None:
        exp = NOW + timedelta(hours=1)
        ov = _make_override(expires_at=exp)
        h = _override_to_hash(ov)
        assert h["expires_at"] != ""
        restored = _hash_to_override(h)
        assert restored.expires_at is not None


class TestAgentHealthStoreGetRecord:
    """Tests for AgentHealthStore.get_health_record."""

    async def test_returns_none_when_no_data(self) -> None:
        redis = _fake_redis()
        redis.hgetall.return_value = {}
        store = AgentHealthStore(redis)
        result = await store.get_health_record("agent-1")
        assert result is None

    async def test_returns_record_when_data_exists(self) -> None:
        rec = _make_record()
        redis = _fake_redis()
        redis.hgetall.return_value = _record_to_hash(rec)
        store = AgentHealthStore(redis)
        result = await store.get_health_record("agent-1")
        assert result is not None
        assert result.agent_id == "agent-1"

    async def test_raises_on_redis_error(self) -> None:
        redis = _fake_redis()
        redis.hgetall.side_effect = ConnectionError("down")
        store = AgentHealthStore(redis)
        with pytest.raises(ConnectionError):
            await store.get_health_record("agent-1")


class TestAgentHealthStoreUpsert:
    """Tests for AgentHealthStore.upsert_health_record."""

    async def test_upsert_calls_hset_and_expire(self) -> None:
        redis = _fake_redis()
        store = AgentHealthStore(redis)
        rec = _make_record()
        await store.upsert_health_record(rec)
        redis.hset.assert_awaited_once()
        redis.expire.assert_awaited_once_with(_health_key("agent-1"), HEALTH_RECORD_TTL_SECONDS)

    async def test_upsert_raises_on_redis_error(self) -> None:
        redis = _fake_redis()
        redis.hset.side_effect = ConnectionError("down")
        store = AgentHealthStore(redis)
        with pytest.raises(ConnectionError):
            await store.upsert_health_record(_make_record())


class TestAgentHealthStoreOverride:
    """Tests for override CRUD."""

    async def test_get_override_none(self) -> None:
        redis = _fake_redis()
        store = AgentHealthStore(redis)
        result = await store.get_override("agent-1")
        assert result is None

    async def test_get_override_exists(self) -> None:
        ov = _make_override()
        redis = _fake_redis()
        redis.hgetall.return_value = _override_to_hash(ov)
        store = AgentHealthStore(redis)
        result = await store.get_override("agent-1")
        assert result is not None
        assert result.mode == OverrideMode.SUPPRESS_HEALING

    async def test_get_override_raises(self) -> None:
        redis = _fake_redis()
        redis.hgetall.side_effect = ConnectionError("err")
        store = AgentHealthStore(redis)
        with pytest.raises(ConnectionError):
            await store.get_override("agent-1")

    async def test_set_override(self) -> None:
        redis = _fake_redis()
        store = AgentHealthStore(redis)
        ov = _make_override()
        await store.set_override(ov)
        redis.hset.assert_awaited_once()

    async def test_set_override_raises(self) -> None:
        redis = _fake_redis()
        redis.hset.side_effect = ConnectionError("err")
        store = AgentHealthStore(redis)
        with pytest.raises(ConnectionError):
            await store.set_override(_make_override())

    async def test_delete_override_existed(self) -> None:
        redis = _fake_redis()
        redis.delete.return_value = 1
        store = AgentHealthStore(redis)
        assert await store.delete_override("agent-1") is True

    async def test_delete_override_not_found(self) -> None:
        redis = _fake_redis()
        redis.delete.return_value = 0
        store = AgentHealthStore(redis)
        assert await store.delete_override("agent-1") is False

    async def test_delete_override_raises(self) -> None:
        redis = _fake_redis()
        redis.delete.side_effect = ConnectionError("err")
        store = AgentHealthStore(redis)
        with pytest.raises(ConnectionError):
            await store.delete_override("agent-1")


class TestAgentHealthStoreSaveHealingAction:
    """Tests for save_healing_action."""

    async def test_save_healing_action_success(self) -> None:
        redis = _fake_redis()
        store = AgentHealthStore(redis)
        action = _make_healing_action()
        await store.save_healing_action(action)
        redis.hset.assert_awaited_once()
        redis.expire.assert_awaited_once()

    async def test_save_healing_action_with_completed_at(self) -> None:
        redis = _fake_redis()
        store = AgentHealthStore(redis)
        action = _make_healing_action()
        # HealingAction is frozen, so build a new one with completed_at
        action2 = HealingAction(
            action_id=action.action_id,
            agent_id=action.agent_id,
            trigger=action.trigger,
            action_type=action.action_type,
            tier_determined_by=action.tier_determined_by,
            initiated_at=action.initiated_at,
            completed_at=NOW,
            audit_event_id=action.audit_event_id,
        )
        await store.save_healing_action(action2)
        redis.hset.assert_awaited_once()

    async def test_save_healing_action_raises(self) -> None:
        redis = _fake_redis()
        redis.hset.side_effect = ConnectionError("err")
        store = AgentHealthStore(redis)
        with pytest.raises(ConnectionError):
            await store.save_healing_action(_make_healing_action())


# ===================================================================
# SECTION 2: agent_health/monitor.py
# ===================================================================


class TestDefaultMemoryProvider:
    """Tests for _default_memory_provider."""

    def test_returns_float_with_psutil(self) -> None:
        mock_proc = MagicMock()
        mock_proc.memory_percent.return_value = 42.5
        with patch(
            "enhanced_agent_bus.agent_health.monitor.psutil",
            create=True,
        ) as mock_psutil:
            mock_psutil.Process.return_value = mock_proc
            # Re-import won't help; call directly
            result = _default_memory_provider()
            # psutil may or may not be available; just check float
            assert isinstance(result, float)

    def test_returns_zero_on_import_error(self) -> None:
        with patch.dict("sys.modules", {"psutil": None}):
            result = _default_memory_provider()
            assert result == 0.0


class TestAgentHealthMonitorInit:
    """Tests for monitor construction."""

    def test_defaults(self) -> None:
        store = MagicMock(spec=AgentHealthStore)
        mon = AgentHealthMonitor("a1", AutonomyTier.BOUNDED, store)
        assert mon._agent_id == "a1"
        assert mon._thresholds.metric_emit_interval_seconds == 30
        assert mon._prev_failure_count is None

    def test_custom_thresholds(self) -> None:
        store = MagicMock(spec=AgentHealthStore)
        th = AgentHealthThresholds(metric_emit_interval_seconds=10)
        mon = AgentHealthMonitor("a1", AutonomyTier.ADVISORY, store, thresholds=th)
        assert mon._thresholds.metric_emit_interval_seconds == 10


class TestAgentHealthMonitorPoll:
    """Tests for _poll cycle."""

    async def test_poll_creates_initial_record(self) -> None:
        store = AsyncMock(spec=AgentHealthStore)
        store.get_health_record.return_value = None
        store.upsert_health_record = AsyncMock()
        mon = AgentHealthMonitor(
            "a1",
            AutonomyTier.BOUNDED,
            store,
            memory_provider=lambda: 30.0,
        )
        with patch("enhanced_agent_bus.agent_health.monitor.emit_health_metrics"):
            await mon._poll()
        store.upsert_health_record.assert_awaited_once()
        rec = store.upsert_health_record.call_args[0][0]
        assert rec.health_state == HealthState.HEALTHY
        assert rec.memory_usage_pct == 30.0

    async def test_poll_updates_existing_record(self) -> None:
        existing = _make_record(memory=10.0)
        store = AsyncMock(spec=AgentHealthStore)
        store.get_health_record.return_value = existing
        store.upsert_health_record = AsyncMock()
        mon = AgentHealthMonitor(
            "agent-1",
            AutonomyTier.BOUNDED,
            store,
            memory_provider=lambda: 55.0,
        )
        with patch("enhanced_agent_bus.agent_health.monitor.emit_health_metrics"):
            await mon._poll()
        rec = store.upsert_health_record.call_args[0][0]
        assert rec.memory_usage_pct == 55.0

    async def test_poll_detects_recovery(self) -> None:
        existing = _make_record(failures=0)
        store = AsyncMock(spec=AgentHealthStore)
        store.get_health_record.return_value = existing
        store.upsert_health_record = AsyncMock()
        mon = AgentHealthMonitor(
            "agent-1",
            AutonomyTier.BOUNDED,
            store,
            memory_provider=lambda: 20.0,
        )
        # Simulate previous poll had failures > 0
        mon._prev_failure_count = 3
        with patch("enhanced_agent_bus.agent_health.monitor.emit_health_metrics"):
            with patch("enhanced_agent_bus.agent_health.monitor.logger") as mock_log:
                await mon._poll()
                mock_log.info.assert_called()

    async def test_poll_no_recovery_log_when_prev_none(self) -> None:
        existing = _make_record(failures=0)
        store = AsyncMock(spec=AgentHealthStore)
        store.get_health_record.return_value = existing
        store.upsert_health_record = AsyncMock()
        mon = AgentHealthMonitor(
            "agent-1",
            AutonomyTier.BOUNDED,
            store,
            memory_provider=lambda: 20.0,
        )
        # prev is None -- no recovery log
        mon._prev_failure_count = None
        with patch("enhanced_agent_bus.agent_health.monitor.emit_health_metrics"):
            with patch("enhanced_agent_bus.agent_health.monitor.logger") as mock_log:
                await mon._poll()
                mock_log.info.assert_not_called()


class TestAgentHealthMonitorMarkDegraded:
    """Tests for _mark_degraded."""

    async def test_mark_degraded_no_existing_record(self) -> None:
        store = AsyncMock(spec=AgentHealthStore)
        store.get_health_record.return_value = None
        store.upsert_health_record = AsyncMock()
        mon = AgentHealthMonitor("a1", AutonomyTier.BOUNDED, store)
        await mon._mark_degraded()
        rec = store.upsert_health_record.call_args[0][0]
        assert rec.health_state == HealthState.DEGRADED

    async def test_mark_degraded_existing_record(self) -> None:
        existing = _make_record()
        store = AsyncMock(spec=AgentHealthStore)
        store.get_health_record.return_value = existing
        store.upsert_health_record = AsyncMock()
        mon = AgentHealthMonitor("agent-1", AutonomyTier.BOUNDED, store)
        await mon._mark_degraded()
        rec = store.upsert_health_record.call_args[0][0]
        assert rec.health_state == HealthState.DEGRADED

    async def test_mark_degraded_swallows_exception(self) -> None:
        store = AsyncMock(spec=AgentHealthStore)
        store.get_health_record.side_effect = ConnectionError("dead")
        mon = AgentHealthMonitor("a1", AutonomyTier.BOUNDED, store)
        # Should not raise
        await mon._mark_degraded()


class TestAgentHealthMonitorRunLoop:
    """Tests for start/stop and _run_loop."""

    async def test_start_creates_task(self) -> None:
        store = AsyncMock(spec=AgentHealthStore)
        store.get_health_record.return_value = None
        store.upsert_health_record = AsyncMock()
        mon = AgentHealthMonitor(
            "a1",
            AutonomyTier.BOUNDED,
            store,
            memory_provider=lambda: 10.0,
            _sleep=AsyncMock(side_effect=asyncio.CancelledError),
        )
        with patch("enhanced_agent_bus.agent_health.monitor.emit_health_metrics"):
            task = mon.start()
            assert isinstance(task, asyncio.Task)
            await mon.stop()

    async def test_stop_when_no_task(self) -> None:
        store = AsyncMock(spec=AgentHealthStore)
        mon = AgentHealthMonitor("a1", AutonomyTier.BOUNDED, store)
        await mon.stop()  # Should not raise

    async def test_loop_continues_on_poll_error(self) -> None:
        store = AsyncMock(spec=AgentHealthStore)
        call_count = 0

        async def fake_sleep(_: float) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError

        store.get_health_record.side_effect = RuntimeError("boom")
        store.upsert_health_record = AsyncMock()
        mon = AgentHealthMonitor(
            "a1",
            AutonomyTier.BOUNDED,
            store,
            _sleep=fake_sleep,
        )
        with patch("enhanced_agent_bus.agent_health.monitor.emit_health_metrics"):
            task = mon.start()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_loop_stops_on_sleep_error(self) -> None:
        store = AsyncMock(spec=AgentHealthStore)
        store.get_health_record.return_value = None
        store.upsert_health_record = AsyncMock()

        async def exploding_sleep(_: float) -> None:
            raise RuntimeError("sleep broken")

        mon = AgentHealthMonitor(
            "a1",
            AutonomyTier.BOUNDED,
            store,
            memory_provider=lambda: 5.0,
            _sleep=exploding_sleep,
        )
        with patch("enhanced_agent_bus.agent_health.monitor.emit_health_metrics"):
            task = mon.start()
            await task  # Should complete (return) due to sleep error


# ===================================================================
# SECTION 3: llm_adapters/cost/anomaly.py
# ===================================================================


class TestCostAnomalyDetectorInit:
    """Tests for CostAnomalyDetector construction."""

    def test_defaults(self) -> None:
        d = CostAnomalyDetector()
        assert d._window_size == 100
        assert d._spike_threshold == 3.0
        assert d._warning_threshold == 0.8

    def test_custom_params(self) -> None:
        d = CostAnomalyDetector(window_size=50, spike_threshold=2.0, warning_threshold=0.9)
        assert d._window_size == 50
        assert d._spike_threshold == 2.0
        assert d._warning_threshold == 0.9


class TestCostAnomalyRecordCost:
    """Tests for record_cost."""

    async def test_no_anomaly_below_threshold(self) -> None:
        d = CostAnomalyDetector()
        for _ in range(15):
            result = await d.record_cost("t1", "p1", 1.0)
        assert result is None

    async def test_anomaly_detected_on_spike(self) -> None:
        d = CostAnomalyDetector(spike_threshold=2.0)
        for _ in range(15):
            await d.record_cost("t1", "p1", 1.0)
        result = await d.record_cost("t1", "p1", 100.0)
        assert result is not None
        assert result.anomaly_type == "spike"
        assert result.tenant_id == "t1"

    async def test_callback_invoked_on_anomaly(self) -> None:
        d = CostAnomalyDetector(spike_threshold=2.0)
        cb = MagicMock()
        d.register_callback(cb)
        for _ in range(15):
            await d.record_cost("t1", "p1", 1.0)
        await d.record_cost("t1", "p1", 100.0)
        cb.assert_called_once()

    async def test_callback_error_swallowed(self) -> None:
        d = CostAnomalyDetector(spike_threshold=2.0)
        cb = MagicMock(side_effect=RuntimeError("cb boom"))
        d.register_callback(cb)
        for _ in range(15):
            await d.record_cost("t1", "p1", 1.0)
        # Should not raise
        result = await d.record_cost("t1", "p1", 100.0)
        assert result is not None

    async def test_window_trimming(self) -> None:
        d = CostAnomalyDetector(window_size=12)
        for _i in range(20):
            await d.record_cost("t1", "p1", 1.0)
        key = "t1:p1"
        assert len(d._cost_history[key]) <= 12

    async def test_not_enough_data_returns_none(self) -> None:
        d = CostAnomalyDetector()
        for _ in range(5):
            result = await d.record_cost("t1", "p1", 1.0)
        assert result is None

    async def test_separate_keys_per_tenant_provider(self) -> None:
        d = CostAnomalyDetector()
        await d.record_cost("t1", "p1", 1.0)
        await d.record_cost("t2", "p2", 2.0)
        assert "t1:p1" in d._cost_history
        assert "t2:p2" in d._cost_history


class TestCostAnomalyDetectSpike:
    """Tests for _detect_spike internal method."""

    def test_no_spike_normal_cost(self) -> None:
        d = CostAnomalyDetector()
        history = [(NOW, 1.0) for _ in range(10)]
        result = d._detect_spike("t1", "p1", 1.0, history)
        assert result is None

    def test_spike_detected(self) -> None:
        d = CostAnomalyDetector(spike_threshold=2.0)
        history = [(NOW, 1.0) for _ in range(10)]
        history.append((NOW, 50.0))
        result = d._detect_spike("t1", "p1", 50.0, history)
        assert result is not None
        assert result.severity in ("low", "medium", "high", "critical")

    def test_not_enough_history(self) -> None:
        d = CostAnomalyDetector()
        history = [(NOW, 1.0) for _ in range(4)]
        result = d._detect_spike("t1", "p1", 1.0, history)
        assert result is None

    def test_mean_zero_returns_none(self) -> None:
        d = CostAnomalyDetector()
        history = [(NOW, 0.0) for _ in range(10)]
        history.append((NOW, 5.0))
        result = d._detect_spike("t1", "p1", 5.0, history)
        assert result is None

    def test_zero_stdev_uses_mean_fraction(self) -> None:
        d = CostAnomalyDetector(spike_threshold=2.0)
        # All same cost -> stdev=0 -> fallback to mean*0.1
        history = [(NOW, 10.0) for _ in range(10)]
        # current cost very high relative to mean/stdev
        history.append((NOW, 100.0))
        result = d._detect_spike("t1", "p1", 100.0, history)
        assert result is not None

    def test_severity_levels(self) -> None:
        d = CostAnomalyDetector(spike_threshold=1.0)
        # All constant -> stdev fallback to mean*0.1=1.0
        history = [(NOW, 10.0) for _ in range(10)]

        # z ~ (cost - 10)/1.0
        # threshold=1.0, so >1 = low, >2 = medium, >3 = high, >4 = critical
        # cost=12 -> z=2 -> low (>1 but <2)
        r = d._detect_spike("t1", "p1", 12.0, history + [(NOW, 12.0)])
        assert r is not None and r.severity == "low"

        # cost=13 -> z=3 -> medium (>2 but <3)
        r = d._detect_spike("t1", "p1", 13.0, history + [(NOW, 13.0)])
        assert r is not None and r.severity == "medium"

        # cost=14 -> z=4 -> high (>3 but <4)
        r = d._detect_spike("t1", "p1", 14.0, history + [(NOW, 14.0)])
        assert r is not None and r.severity == "high"

        # cost=15 -> z=5 -> critical (>4)
        r = d._detect_spike("t1", "p1", 15.0, history + [(NOW, 15.0)])
        assert r is not None and r.severity == "critical"


class TestCostAnomalyBudgetWarning:
    """Tests for check_budget_warning."""

    def test_no_warning_below_threshold(self) -> None:
        d = CostAnomalyDetector(warning_threshold=0.8)
        result = d.check_budget_warning("t1", 70.0, 100.0)
        assert result is None

    def test_warning_at_threshold(self) -> None:
        d = CostAnomalyDetector(warning_threshold=0.8)
        result = d.check_budget_warning("t1", 80.0, 100.0)
        assert result is not None
        assert result.anomaly_type == "budget_warning"
        assert result.severity == "low"

    def test_warning_medium(self) -> None:
        d = CostAnomalyDetector(warning_threshold=0.8)
        result = d.check_budget_warning("t1", 92.0, 100.0)
        assert result is not None
        assert result.severity == "medium"

    def test_warning_high(self) -> None:
        d = CostAnomalyDetector(warning_threshold=0.8)
        result = d.check_budget_warning("t1", 96.0, 100.0)
        assert result is not None
        assert result.severity == "high"

    def test_zero_limit(self) -> None:
        d = CostAnomalyDetector()
        assert d.check_budget_warning("t1", 50.0, 0.0) is None

    def test_negative_limit(self) -> None:
        d = CostAnomalyDetector()
        assert d.check_budget_warning("t1", 50.0, -10.0) is None


class TestCostAnomalyGetRecentAnomalies:
    """Tests for get_recent_anomalies with filters."""

    async def test_unfiltered(self) -> None:
        d = CostAnomalyDetector(spike_threshold=2.0)
        for _ in range(15):
            await d.record_cost("t1", "p1", 1.0)
        await d.record_cost("t1", "p1", 100.0)
        results = d.get_recent_anomalies()
        assert len(results) >= 1

    async def test_filter_by_tenant(self) -> None:
        d = CostAnomalyDetector(spike_threshold=2.0)
        for _ in range(15):
            await d.record_cost("t1", "p1", 1.0)
        await d.record_cost("t1", "p1", 100.0)
        assert len(d.get_recent_anomalies(tenant_id="t1")) >= 1
        assert len(d.get_recent_anomalies(tenant_id="t-nonexistent")) == 0

    async def test_filter_by_severity(self) -> None:
        d = CostAnomalyDetector(spike_threshold=2.0)
        for _ in range(15):
            await d.record_cost("t1", "p1", 1.0)
        await d.record_cost("t1", "p1", 100.0)
        anomaly = d.get_recent_anomalies()[0]
        assert len(d.get_recent_anomalies(severity=anomaly.severity)) >= 1

    async def test_filter_by_since(self) -> None:
        d = CostAnomalyDetector(spike_threshold=2.0)
        for _ in range(15):
            await d.record_cost("t1", "p1", 1.0)
        await d.record_cost("t1", "p1", 100.0)
        future = datetime.now(UTC) + timedelta(hours=1)
        assert len(d.get_recent_anomalies(since=future)) == 0


# ===================================================================
# SECTION 4: adapters/openai_adapter.py
# ===================================================================

from enhanced_agent_bus.adapters.base import (
    MessageRole,
    ModelMessage,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    StreamChunk,
)
from enhanced_agent_bus.adapters.openai_adapter import OPENAI_ROLE_MAP, OpenAIAdapter


class TestOpenAIAdapterInit:
    """Tests for OpenAIAdapter construction."""

    def test_defaults(self) -> None:
        adapter = OpenAIAdapter(api_key="test-key")
        assert adapter.provider == ModelProvider.OPENAI
        assert adapter.default_model == "gpt-4o"
        assert adapter.organization is None
        assert adapter._client is None

    def test_custom_params(self) -> None:
        adapter = OpenAIAdapter(
            api_key="k",
            base_url="http://local",
            default_model="gpt-3.5-turbo",
            timeout_seconds=30,
            organization="org-123",
        )
        assert adapter.base_url == "http://local"
        assert adapter.default_model == "gpt-3.5-turbo"
        assert adapter.organization == "org-123"
        assert adapter.timeout_seconds == 30


class TestOpenAIAdapterTranslateRequest:
    """Tests for translate_request."""

    def test_basic_request(self) -> None:
        adapter = OpenAIAdapter(api_key="k")
        req = ModelRequest(
            messages=[ModelMessage(role=MessageRole.USER, content="hello")],
            model="gpt-4o",
        )
        payload = adapter.translate_request(req)
        assert payload["model"] == "gpt-4o"
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["role"] == "user"
        assert payload["messages"][0]["content"] == "hello"

    def test_system_message_role(self) -> None:
        adapter = OpenAIAdapter(api_key="k")
        req = ModelRequest(
            messages=[ModelMessage(role=MessageRole.SYSTEM, content="sys")],
            model="gpt-4o",
        )
        payload = adapter.translate_request(req)
        assert payload["messages"][0]["role"] == "system"

    def test_message_with_name(self) -> None:
        adapter = OpenAIAdapter(api_key="k")
        req = ModelRequest(
            messages=[
                ModelMessage(role=MessageRole.USER, content="hi", name="alice"),
            ],
            model="gpt-4o",
        )
        payload = adapter.translate_request(req)
        assert payload["messages"][0]["name"] == "alice"

    def test_message_with_tool_call_id(self) -> None:
        adapter = OpenAIAdapter(api_key="k")
        req = ModelRequest(
            messages=[
                ModelMessage(
                    role=MessageRole.TOOL,
                    content="result",
                    tool_call_id="tc-1",
                ),
            ],
            model="gpt-4o",
        )
        payload = adapter.translate_request(req)
        assert payload["messages"][0]["tool_call_id"] == "tc-1"

    def test_message_with_tool_calls(self) -> None:
        adapter = OpenAIAdapter(api_key="k")
        tc = [{"id": "tc-1", "type": "function", "function": {"name": "f"}}]
        req = ModelRequest(
            messages=[
                ModelMessage(
                    role=MessageRole.ASSISTANT,
                    content="",
                    tool_calls=tc,
                ),
            ],
            model="gpt-4o",
        )
        payload = adapter.translate_request(req)
        assert payload["messages"][0]["tool_calls"] == tc

    def test_optional_fields(self) -> None:
        adapter = OpenAIAdapter(api_key="k")
        req = ModelRequest(
            messages=[ModelMessage(role=MessageRole.USER, content="hi")],
            model="gpt-4o",
            stop=["END"],
            tools=[{"type": "function"}],
            tool_choice="auto",
        )
        payload = adapter.translate_request(req)
        assert payload["stop"] == ["END"]
        assert payload["tools"] == [{"type": "function"}]
        assert payload["tool_choice"] == "auto"

    def test_no_model_uses_default(self) -> None:
        adapter = OpenAIAdapter(api_key="k", default_model="gpt-3.5-turbo")
        req = ModelRequest(
            messages=[ModelMessage(role=MessageRole.USER, content="hi")],
            model="",
        )
        payload = adapter.translate_request(req)
        # request.model is falsy (""), so `request.model or self.default_model` picks default
        assert payload["model"] == "gpt-3.5-turbo"


class TestOpenAIAdapterTranslateResponse:
    """Tests for translate_response."""

    def test_basic_response(self) -> None:
        adapter = OpenAIAdapter(api_key="k")
        raw: dict[str, Any] = {
            "id": "chatcmpl-1",
            "model": "gpt-4o",
            "choices": [
                {
                    "message": {"content": "hi there", "role": "assistant"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }
        resp = adapter.translate_response(raw)
        assert resp.content == "hi there"
        assert resp.model == "gpt-4o"
        assert resp.provider == ModelProvider.OPENAI
        assert resp.prompt_tokens == 10
        assert resp.completion_tokens == 5
        assert resp.total_tokens == 15
        assert resp.response_id == "chatcmpl-1"

    def test_empty_choices_raises(self) -> None:
        adapter = OpenAIAdapter(api_key="k")
        raw: dict[str, Any] = {"choices": [], "usage": {}}
        # Empty list causes IndexError on choices[0]
        with pytest.raises(IndexError):
            adapter.translate_response(raw)

    def test_missing_choices_key_uses_default(self) -> None:
        adapter = OpenAIAdapter(api_key="k")
        raw: dict[str, Any] = {"usage": {}}
        # No "choices" key -> default [{}] -> [{}][0] = {}
        resp = adapter.translate_response(raw)
        assert resp.content == ""
        assert resp.finish_reason == "stop"

    def test_tool_calls_in_response(self) -> None:
        adapter = OpenAIAdapter(api_key="k")
        tc = [{"id": "tc-1", "type": "function"}]
        raw: dict[str, Any] = {
            "choices": [
                {"message": {"content": "", "tool_calls": tc}, "finish_reason": "tool_calls"}
            ],
            "usage": {},
        }
        resp = adapter.translate_response(raw)
        assert resp.tool_calls == tc
        assert resp.finish_reason == "tool_calls"


class TestOpenAIAdapterEnsureClient:
    """Tests for _ensure_client."""

    async def test_ensure_client_import_error(self) -> None:
        adapter = OpenAIAdapter(api_key="k")
        with patch.dict("sys.modules", {"openai": None}):
            with patch(
                "builtins.__import__",
                side_effect=ImportError("no openai"),
            ):
                with pytest.raises(ImportError, match="OpenAI package not installed"):
                    await adapter._ensure_client()

    async def test_ensure_client_creates_once(self) -> None:
        adapter = OpenAIAdapter(api_key="k")
        mock_cls = MagicMock()
        mock_module = MagicMock()
        mock_module.AsyncOpenAI = mock_cls
        with patch.dict("sys.modules", {"openai": mock_module}):
            client1 = await adapter._ensure_client()
            client2 = await adapter._ensure_client()
            assert client1 is client2
            mock_cls.assert_called_once()


class TestOpenAIAdapterComplete:
    """Tests for complete."""

    async def test_complete_success(self) -> None:
        adapter = OpenAIAdapter(api_key="k")
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "id": "c1",
            "model": "gpt-4o",
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        }
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        adapter._client = mock_client

        req = ModelRequest(
            messages=[ModelMessage(role=MessageRole.USER, content="hi")],
            model="gpt-4o",
        )
        resp = await adapter.complete(req)
        assert resp.content == "ok"
        assert resp.total_tokens == 7

    async def test_complete_validation_error(self) -> None:
        adapter = OpenAIAdapter(api_key="k")
        req = ModelRequest(messages=[], model="gpt-4o")
        with pytest.raises(ValueError, match="Invalid request"):
            await adapter.complete(req)


class TestOpenAIAdapterStream:
    """Tests for stream."""

    async def test_stream_validation_error(self) -> None:
        adapter = OpenAIAdapter(api_key="k")
        req = ModelRequest(messages=[], model="gpt-4o")
        with pytest.raises(ValueError, match="Invalid request"):
            async for _ in adapter.stream(req):
                pass

    async def test_stream_yields_chunks(self) -> None:
        adapter = OpenAIAdapter(api_key="k")
        mock_client = AsyncMock()

        # Create mock chunks
        chunk1 = MagicMock()
        choice1 = MagicMock()
        choice1.delta.content = "hel"
        choice1.delta.tool_calls = None
        choice1.finish_reason = None
        chunk1.choices = [choice1]

        chunk2 = MagicMock()
        choice2 = MagicMock()
        choice2.delta.content = "lo"
        choice2.delta.tool_calls = None
        choice2.finish_reason = "stop"
        chunk2.choices = [choice2]

        # stream() does: response = await create(...); async for chunk in response
        # So create must return an awaitable that resolves to an async iterable.
        class _AsyncChunkIter:
            def __init__(self, items: list[Any]) -> None:
                self._items = items
                self._idx = 0

            def __aiter__(self) -> _AsyncChunkIter:
                return self

            async def __anext__(self) -> Any:
                if self._idx >= len(self._items):
                    raise StopAsyncIteration
                item = self._items[self._idx]
                self._idx += 1
                return item

        mock_client.chat.completions.create = AsyncMock(
            return_value=_AsyncChunkIter([chunk1, chunk2])
        )
        adapter._client = mock_client

        req = ModelRequest(
            messages=[ModelMessage(role=MessageRole.USER, content="hi")],
            model="gpt-4o",
        )
        chunks: list[StreamChunk] = []
        async for sc in adapter.stream(req):
            chunks.append(sc)
        assert len(chunks) == 2
        assert chunks[0].content == "hel"
        assert chunks[1].content == "lo"
        assert chunks[1].is_final is True

    async def test_stream_empty_choices(self) -> None:
        adapter = OpenAIAdapter(api_key="k")
        mock_client = AsyncMock()

        chunk = MagicMock()
        chunk.choices = []

        class _AsyncChunkIter:
            def __init__(self, items: list[Any]) -> None:
                self._items = items
                self._idx = 0

            def __aiter__(self) -> _AsyncChunkIter:
                return self

            async def __anext__(self) -> Any:
                if self._idx >= len(self._items):
                    raise StopAsyncIteration
                item = self._items[self._idx]
                self._idx += 1
                return item

        mock_client.chat.completions.create = AsyncMock(return_value=_AsyncChunkIter([chunk]))
        adapter._client = mock_client

        req = ModelRequest(
            messages=[ModelMessage(role=MessageRole.USER, content="hi")],
            model="gpt-4o",
        )
        chunks: list[StreamChunk] = []
        async for sc in adapter.stream(req):
            chunks.append(sc)
        # No delta -> no yield
        assert len(chunks) == 0


class TestOpenAIAdapterGetCapabilities:
    """Tests for get_capabilities."""

    def test_capabilities(self) -> None:
        adapter = OpenAIAdapter(api_key="k")
        caps = adapter.get_capabilities()
        assert caps["vision"] is True
        assert caps["json_mode"] is True
        assert caps["seed_support"] is True
        assert caps["max_context_tokens"] == 128000
        assert caps["provider"] == "openai"
        assert caps["streaming"] is True


class TestOpenAIRoleMap:
    """Tests for OPENAI_ROLE_MAP constant."""

    def test_all_roles_mapped(self) -> None:
        for role in MessageRole:
            assert role in OPENAI_ROLE_MAP
        assert OPENAI_ROLE_MAP[MessageRole.SYSTEM] == "system"
        assert OPENAI_ROLE_MAP[MessageRole.TOOL] == "tool"
        assert OPENAI_ROLE_MAP[MessageRole.FUNCTION] == "function"
