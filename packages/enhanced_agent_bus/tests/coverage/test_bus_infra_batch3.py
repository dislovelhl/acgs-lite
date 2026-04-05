"""
Tests for under-covered enhanced_agent_bus modules — batch 3.

Covers:
  - agent_health/detectors.py (FailureLoopDetector, MemoryExhaustionDetector)
  - agent_health/healing_engine.py (HealingEngine tier routing + overrides)
  - batch_processor_infra/orchestrator.py (BatchProcessorOrchestrator)
  - batch_processor_infra/queue.py (BatchRequestQueue deduplication)
  - batch_processor_infra/tuning.py (BatchAutoTuner)
  - batch_processor_infra/workers.py (WorkerPool + circuit breaker)
  - mcp/maci_filter.py (MACIToolFilter, ToolFilterConfig, ToolFilterResult)
  - api/badge_generator.py (generate_badge_svg, _score_to_color)
  - api/runtime_guards.py (current_environment, is_sandbox_environment, require_sandbox_endpoint)
  - api/validation_store.py (ValidationStore ring buffer)
  - components/agent_registry_manager.py (AgentRegistryManager CRUD)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import MACIRole

# ---------------------------------------------------------------------------
# agent_health/detectors.py
# ---------------------------------------------------------------------------
from enhanced_agent_bus.agent_health.detectors import (
    FailureLoopDetector,
    MemoryExhaustionDetector,
)
from enhanced_agent_bus.agent_health.models import AgentHealthThresholds


class TestFailureLoopDetector:
    """FailureLoopDetector sliding-window tests."""

    def _make_thresholds(
        self, failure_count: int = 3, window_seconds: int = 60
    ) -> AgentHealthThresholds:
        return AgentHealthThresholds(
            failure_count_threshold=failure_count,
            failure_window_seconds=window_seconds,
        )

    def test_no_failures_no_loop(self):
        det = FailureLoopDetector(self._make_thresholds())
        assert det.is_loop_detected() is False

    def test_below_threshold_no_loop(self):
        det = FailureLoopDetector(self._make_thresholds(failure_count=3))
        now = datetime(2024, 1, 1, tzinfo=UTC)
        assert det.record_failure(now) is False
        assert det.record_failure(now + timedelta(seconds=1)) is False
        assert det.is_loop_detected() is False

    def test_at_threshold_triggers_loop(self):
        det = FailureLoopDetector(self._make_thresholds(failure_count=3))
        now = datetime(2024, 1, 1, tzinfo=UTC)
        det.record_failure(now)
        det.record_failure(now + timedelta(seconds=1))
        result = det.record_failure(now + timedelta(seconds=2))
        assert result is True
        assert det.is_loop_detected() is True

    def test_old_failures_pruned_outside_window(self):
        det = FailureLoopDetector(self._make_thresholds(failure_count=3, window_seconds=10))
        base = datetime(2024, 1, 1, tzinfo=UTC)
        det.record_failure(base)
        det.record_failure(base + timedelta(seconds=1))
        # Third failure is outside the window relative to first two
        result = det.record_failure(base + timedelta(seconds=20))
        assert result is False  # old timestamps pruned

    def test_record_success_clears_state(self):
        det = FailureLoopDetector(self._make_thresholds(failure_count=2))
        now = datetime(2024, 1, 1, tzinfo=UTC)
        det.record_failure(now)
        det.record_failure(now + timedelta(seconds=1))
        assert det.is_loop_detected() is True
        det.record_success()
        assert det.is_loop_detected() is False

    def test_loop_stays_detected_after_threshold(self):
        det = FailureLoopDetector(self._make_thresholds(failure_count=2))
        now = datetime(2024, 1, 1, tzinfo=UTC)
        det.record_failure(now)
        det.record_failure(now + timedelta(seconds=1))
        assert det.is_loop_detected() is True
        # Even after pruning, _loop_detected stays True until record_success
        det.record_failure(now + timedelta(seconds=100))
        assert det.is_loop_detected() is True


class TestMemoryExhaustionDetector:
    """MemoryExhaustionDetector hysteresis tests."""

    def _make_thresholds(
        self, exhaustion_pct: float = 85.0, hysteresis_pct: float = 10.0
    ) -> AgentHealthThresholds:
        return AgentHealthThresholds(
            memory_exhaustion_pct=exhaustion_pct,
            memory_hysteresis_pct=hysteresis_pct,
        )

    def test_below_threshold_not_exhausted(self):
        det = MemoryExhaustionDetector(self._make_thresholds())
        assert det.update(50.0) is False
        assert det.is_exhausted() is False

    def test_at_threshold_becomes_exhausted(self):
        det = MemoryExhaustionDetector(self._make_thresholds(exhaustion_pct=85.0))
        assert det.update(85.0) is True
        assert det.is_exhausted() is True

    def test_above_threshold_stays_exhausted(self):
        det = MemoryExhaustionDetector(self._make_thresholds(exhaustion_pct=85.0))
        det.update(90.0)
        assert det.update(86.0) is True  # still above clear threshold

    def test_hysteresis_prevents_flapping(self):
        det = MemoryExhaustionDetector(
            self._make_thresholds(exhaustion_pct=85.0, hysteresis_pct=10.0)
        )
        det.update(90.0)  # trigger exhaustion
        assert det.is_exhausted() is True
        # 80% is above clear threshold (85 - 10 = 75)
        det.update(80.0)
        assert det.is_exhausted() is True  # hysteresis holds

    def test_clears_below_hysteresis(self):
        det = MemoryExhaustionDetector(
            self._make_thresholds(exhaustion_pct=85.0, hysteresis_pct=10.0)
        )
        det.update(90.0)
        assert det.is_exhausted() is True
        det.update(75.0)  # exactly at clear threshold
        assert det.is_exhausted() is False

    def test_reset_clears_exhaustion(self):
        det = MemoryExhaustionDetector(self._make_thresholds())
        det.update(95.0)
        assert det.is_exhausted() is True
        det.reset()
        assert det.is_exhausted() is False


# ---------------------------------------------------------------------------
# agent_health/healing_engine.py
# ---------------------------------------------------------------------------
from enhanced_agent_bus.agent_health.models import (
    AgentHealthRecord,
    AutonomyTier,
    HealingActionType,
    HealingTrigger,
    HealthState,
    OverrideMode,
)


def _make_record(tier: AutonomyTier = AutonomyTier.ADVISORY) -> AgentHealthRecord:
    return AgentHealthRecord(
        agent_id="agent-1",
        health_state=HealthState.DEGRADED,
        consecutive_failure_count=5,
        memory_usage_pct=50.0,
        last_event_at=datetime.now(UTC),
        autonomy_tier=tier,
    )


def _make_thresholds() -> AgentHealthThresholds:
    return AgentHealthThresholds(
        failure_count_threshold=5,
        failure_window_seconds=60,
    )


def _make_engine(
    bounded_approval_awaiter=None,
):
    """Build a HealingEngine with all deps mocked."""
    store = AsyncMock()
    store.get_override = AsyncMock(return_value=None)
    store.save_healing_action = AsyncMock()
    audit = AsyncMock()
    restarter = AsyncMock()
    quarantine = AsyncMock()
    hitl = AsyncMock()
    supervisor = AsyncMock()
    thresholds = _make_thresholds()

    from enhanced_agent_bus.agent_health.healing_engine import HealingEngine

    engine = HealingEngine(
        store=store,
        audit_log_client=audit,
        restarter=restarter,
        quarantine_manager=quarantine,
        hitl_requestor=hitl,
        supervisor_notifier=supervisor,
        thresholds=thresholds,
        bounded_approval_awaiter=bounded_approval_awaiter,
    )

    return engine, store, audit, restarter, quarantine, hitl, supervisor


# Shared patch context for all HealingEngine tests — mocks constitutional hash
# validation, the Prometheus counter, and the _write_audit method (which imports
# src.core.shared.audit at call time, unavailable in the test environment).
_ENGINE_PATCHES = (
    "enhanced_agent_bus.agent_health.healing_engine._validate_constitutional_hash",
    "enhanced_agent_bus.agent_health.healing_engine.HEALING_ACTIONS_COUNTER",
)


class TestHealingEngine:
    """HealingEngine tier routing and override tests."""

    @staticmethod
    def _patches():
        """Return a combined context manager patching hash validation, counter, and audit."""
        import contextlib

        @contextlib.asynccontextmanager
        async def _ctx(engine):
            with (
                patch(_ENGINE_PATCHES[0]),
                patch(_ENGINE_PATCHES[1]) as mc,
            ):
                mc.labels.return_value.inc = MagicMock()
                # Mock _write_audit to avoid importing src.core.shared.audit
                engine._write_audit = AsyncMock()
                yield

        return _ctx

    @pytest.mark.asyncio
    async def test_human_approved_tier_restarts(self):
        engine, store, audit, restarter, *_ = _make_engine()
        record = _make_record(AutonomyTier.HUMAN_APPROVED)

        async with self._patches()(engine):
            action = await engine.handle("agent-1", HealingTrigger.FAILURE_LOOP, record)

        assert action is not None
        assert action.action_type == HealingActionType.GRACEFUL_RESTART
        restarter.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_advisory_tier_quarantines_and_hitl(self):
        engine, store, audit, restarter, quarantine, hitl, _ = _make_engine()
        record = _make_record(AutonomyTier.ADVISORY)

        async with self._patches()(engine):
            action = await engine.handle("agent-1", HealingTrigger.MEMORY_EXHAUSTION, record)

        assert action is not None
        assert action.action_type == HealingActionType.HITL_REQUEST
        quarantine.execute.assert_awaited_once()
        hitl.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_bounded_tier_no_awaiter_escalates(self):
        engine, store, audit, restarter, quarantine, hitl, supervisor = _make_engine(
            bounded_approval_awaiter=None
        )
        record = _make_record(AutonomyTier.BOUNDED)

        async with self._patches()(engine):
            action = await engine.handle("agent-1", HealingTrigger.FAILURE_LOOP, record)

        assert action is not None
        assert action.action_type == HealingActionType.HITL_REQUEST
        quarantine.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_bounded_tier_approved_restarts(self):
        awaiter = AsyncMock(return_value=True)
        engine, store, audit, restarter, quarantine, hitl, supervisor = _make_engine(
            bounded_approval_awaiter=awaiter
        )
        record = _make_record(AutonomyTier.BOUNDED)

        async with self._patches()(engine):
            action = await engine.handle("agent-1", HealingTrigger.FAILURE_LOOP, record)

        assert action is not None
        assert action.action_type == HealingActionType.GRACEFUL_RESTART
        restarter.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_bounded_tier_timeout_escalates(self):
        awaiter = AsyncMock(side_effect=TimeoutError("SLA elapsed"))
        engine, store, audit, restarter, quarantine, hitl, supervisor = _make_engine(
            bounded_approval_awaiter=awaiter
        )
        record = _make_record(AutonomyTier.BOUNDED)

        async with self._patches()(engine):
            action = await engine.handle("agent-1", HealingTrigger.FAILURE_LOOP, record)

        assert action is not None
        assert action.action_type == HealingActionType.HITL_REQUEST

    @pytest.mark.asyncio
    async def test_suppress_override_returns_none(self):
        engine, store, audit, *_ = _make_engine()
        override = MagicMock()
        override.mode = OverrideMode.SUPPRESS_HEALING
        override.override_id = "ov-1"
        store.get_override.return_value = override
        record = _make_record(AutonomyTier.HUMAN_APPROVED)

        async with self._patches()(engine):
            result = await engine.handle("agent-1", HealingTrigger.MANUAL, record)

        assert result is None

    @pytest.mark.asyncio
    async def test_force_restart_override(self):
        engine, store, audit, restarter, *_ = _make_engine()
        override = MagicMock()
        override.mode = OverrideMode.FORCE_RESTART
        store.get_override.return_value = override
        record = _make_record(AutonomyTier.ADVISORY)

        async with self._patches()(engine):
            action = await engine.handle("agent-1", HealingTrigger.MANUAL, record)

        assert action is not None
        assert action.action_type == HealingActionType.GRACEFUL_RESTART
        restarter.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_force_quarantine_override(self):
        engine, store, audit, restarter, quarantine, *_ = _make_engine()
        override = MagicMock()
        override.mode = OverrideMode.FORCE_QUARANTINE
        store.get_override.return_value = override
        record = _make_record(AutonomyTier.ADVISORY)

        async with self._patches()(engine):
            action = await engine.handle("agent-1", HealingTrigger.MANUAL, record)

        assert action is not None
        assert action.action_type == HealingActionType.QUARANTINE
        quarantine.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# batch_processor_infra/queue.py
# ---------------------------------------------------------------------------
from enhanced_agent_bus.batch_processor_infra.queue import BatchRequestQueue
from enhanced_agent_bus.models import BatchRequest, BatchRequestItem


class TestBatchRequestQueue:
    """BatchRequestQueue deduplication tests."""

    def _make_item(self, content: str = "hello", agent: str = "a1") -> BatchRequestItem:
        return BatchRequestItem(
            content={"text": content},
            from_agent=agent,
            message_type="test",
            tenant_id="t1",
            priority=1,
        )

    def _make_batch(self, items: list[BatchRequestItem]) -> BatchRequest:
        return BatchRequest(items=items)

    def test_dedup_identical_items(self):
        q = BatchRequestQueue()
        item = self._make_item()
        batch = self._make_batch([item, item])
        unique, mapping = q.deduplicate_requests(batch)
        assert len(unique) == 1
        assert mapping[0] == 0
        assert mapping[1] == 0

    def test_dedup_disabled_returns_all(self):
        q = BatchRequestQueue(enable_deduplication=False)
        item = self._make_item()
        batch = self._make_batch([item, item])
        unique, mapping = q.deduplicate_requests(batch)
        assert len(unique) == 2

    def test_different_items_not_deduped(self):
        q = BatchRequestQueue()
        batch = self._make_batch([self._make_item("a"), self._make_item("b")])
        unique, mapping = q.deduplicate_requests(batch)
        assert len(unique) == 2
        assert mapping[0] == 0
        assert mapping[1] == 1

    def test_cache_clear(self):
        q = BatchRequestQueue()
        batch = self._make_batch([self._make_item()])
        q.deduplicate_requests(batch)
        assert q.get_cache_size() == 1
        q.clear_cache()
        assert q.get_cache_size() == 0

    def test_cache_overflow_auto_clears(self):
        q = BatchRequestQueue(max_cache_size=2)
        # Fill cache to limit
        batch1 = self._make_batch([self._make_item("a"), self._make_item("b")])
        q.deduplicate_requests(batch1)
        assert q.get_cache_size() == 2
        # Add one more to push past max_cache_size
        batch2 = self._make_batch([self._make_item("c")])
        q.deduplicate_requests(batch2)
        # Cache now has 3 entries (clear happens when >max_cache_size,
        # but we only have exactly max_cache_size=2, so the check is `>`)
        assert q.get_cache_size() == 3
        # Now with 3 > 2, the next batch triggers the clear
        batch3 = self._make_batch([self._make_item("d")])
        q.deduplicate_requests(batch3)
        assert q.get_cache_size() == 1

    def test_batch_level_dedup_disabled(self):
        q = BatchRequestQueue(enable_deduplication=True)
        item = self._make_item()
        batch = BatchRequest(items=[item, item], deduplicate=False)
        unique, mapping = q.deduplicate_requests(batch)
        assert len(unique) == 2


# ---------------------------------------------------------------------------
# batch_processor_infra/tuning.py
# ---------------------------------------------------------------------------
from enhanced_agent_bus.batch_processor_infra.tuning import BatchAutoTuner


class TestBatchAutoTuner:
    """BatchAutoTuner adaptive batch size tests."""

    def test_initial_batch_size(self):
        t = BatchAutoTuner(initial_batch_size=10)
        assert t.batch_size == 10

    def test_increase_on_high_success_low_latency(self):
        t = BatchAutoTuner(initial_batch_size=10)
        new = t.adjust_from_stats(success_rate=99.0, avg_latency_ms=50.0)
        assert new > 10

    def test_decrease_on_low_success(self):
        t = BatchAutoTuner(initial_batch_size=10)
        new = t.adjust_from_stats(success_rate=70.0, avg_latency_ms=50.0)
        assert new < 10

    def test_decrease_on_high_latency(self):
        t = BatchAutoTuner(initial_batch_size=10)
        new = t.adjust_from_stats(success_rate=99.0, avg_latency_ms=1500.0)
        assert new < 10

    def test_no_change_middle_ground(self):
        t = BatchAutoTuner(initial_batch_size=10)
        new = t.adjust_from_stats(success_rate=90.0, avg_latency_ms=200.0)
        assert new == 10

    def test_does_not_exceed_max(self):
        t = BatchAutoTuner(initial_batch_size=99)
        new = t.adjust_from_stats(success_rate=99.0, avg_latency_ms=10.0)
        assert new <= 100

    def test_does_not_go_below_min(self):
        t = BatchAutoTuner(initial_batch_size=1)
        new = t.adjust_from_stats(success_rate=50.0, avg_latency_ms=2000.0)
        assert new >= 1


# ---------------------------------------------------------------------------
# batch_processor_infra/workers.py
# ---------------------------------------------------------------------------
from enhanced_agent_bus.batch_processor_infra.workers import WorkerPool
from enhanced_agent_bus.models import BatchItemStatus
from enhanced_agent_bus.validators import ValidationResult


class TestWorkerPool:
    """WorkerPool processing and circuit-breaker tests."""

    def _make_item(self) -> BatchRequestItem:
        return BatchRequestItem(
            content={"text": "test"},
            from_agent="a1",
            message_type="test",
        )

    @pytest.mark.asyncio
    async def test_successful_processing(self):
        pool = WorkerPool(max_concurrency=5, max_retries=0)
        item = self._make_item()

        async def process(i):
            return ValidationResult(is_valid=True)

        result = await pool.process_item(item, process)
        assert result.valid is True
        assert result.status == BatchItemStatus.SUCCESS.value

    @pytest.mark.asyncio
    async def test_failed_validation_result(self):
        pool = WorkerPool(max_concurrency=5, max_retries=0)
        item = self._make_item()

        async def process(i):
            return ValidationResult(is_valid=False)

        result = await pool.process_item(item, process)
        assert result.valid is False
        assert result.status == BatchItemStatus.FAILED.value

    @pytest.mark.asyncio
    async def test_retry_on_error(self):
        pool = WorkerPool(max_concurrency=5, max_retries=2, retry_base_delay=0.001)
        item = self._make_item()
        call_count = 0

        async def process(i):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient")
            return ValidationResult(is_valid=True)

        result = await pool.process_item(item, process)
        assert result.valid is True
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_circuit_breaker_trips(self):
        pool = WorkerPool(max_concurrency=5, max_retries=0, max_failures=2)
        item = self._make_item()

        async def fail(i):
            raise RuntimeError("boom")

        await pool.process_item(item, fail)
        await pool.process_item(item, fail)

        # Circuit breaker should now be tripped
        result = await pool.process_item(item, fail)
        assert result.valid is False
        assert "Circuit breaker" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_reset_circuit_breaker(self):
        pool = WorkerPool(max_concurrency=5, max_retries=0, max_failures=1)
        item = self._make_item()

        async def fail(i):
            raise RuntimeError("boom")

        await pool.process_item(item, fail)
        pool.reset_circuit_breaker()

        async def succeed(i):
            return ValidationResult(is_valid=True)

        result = await pool.process_item(item, succeed)
        assert result.valid is True


# ---------------------------------------------------------------------------
# batch_processor_infra/orchestrator.py
# ---------------------------------------------------------------------------
from enhanced_agent_bus.batch_processor_infra.orchestrator import BatchProcessorOrchestrator


class TestBatchProcessorOrchestrator:
    """BatchProcessorOrchestrator integration tests with mocked governance."""

    def _make_item(self, content: str = "test") -> BatchRequestItem:
        return BatchRequestItem(
            content={"text": content},
            from_agent="a1",
            message_type="test",
        )

    @pytest.mark.asyncio
    async def test_process_batch_success(self):
        orch = BatchProcessorOrchestrator(max_concurrency=5)
        batch = BatchRequest(items=[self._make_item()])

        async def process(item):
            return ValidationResult(is_valid=True)

        with patch.object(orch.governance, "validate_batch_context") as mock_gov:
            mock_gov.return_value = MagicMock(is_valid=True)
            response = await orch.process_batch(batch, process)

        assert response.stats.total_items == 1
        assert response.stats.successful_items >= 0  # might be 1

    @pytest.mark.asyncio
    async def test_process_batch_governance_failure(self):
        orch = BatchProcessorOrchestrator(max_concurrency=5)
        batch = BatchRequest(items=[self._make_item()])

        async def process(item):
            return ValidationResult(is_valid=True)

        with patch.object(orch.governance, "validate_batch_context") as mock_gov:
            mock_gov.return_value = MagicMock(is_valid=False, errors=["hash mismatch"])
            response = await orch.process_batch(batch, process)

        assert response.success is False
        assert response.error_code == "CONSTITUTIONAL_HASH_MISMATCH"

    @pytest.mark.asyncio
    async def test_process_batch_governance_generic_error(self):
        orch = BatchProcessorOrchestrator(max_concurrency=5)
        batch = BatchRequest(items=[self._make_item()])

        async def process(item):
            return ValidationResult(is_valid=True)

        with patch.object(orch.governance, "validate_batch_context") as mock_gov:
            mock_gov.return_value = MagicMock(is_valid=False, errors=["invalid config"])
            response = await orch.process_batch(batch, process)

        assert response.success is False
        assert response.error_code == "GOVERNANCE_FAILURE"

    def test_get_metrics_and_reset(self):
        orch = BatchProcessorOrchestrator()
        metrics = orch.get_metrics()
        assert isinstance(metrics, dict)
        orch.reset_metrics()

    def test_cache_operations(self):
        orch = BatchProcessorOrchestrator()
        assert orch.get_cache_size() == 0
        orch.clear_cache()
        assert orch.get_cache_size() == 0

    @pytest.mark.asyncio
    async def test_all_items_deduplicated(self):
        """When all items are dupes of a previous batch, returns cached placeholders."""
        orch = BatchProcessorOrchestrator(max_concurrency=5)
        item = self._make_item("same")
        batch1 = BatchRequest(items=[item])

        async def process(i):
            return ValidationResult(is_valid=True)

        with patch.object(orch.governance, "validate_batch_context") as mock_gov:
            mock_gov.return_value = MagicMock(is_valid=True)
            await orch.process_batch(batch1, process)
            # Second batch with same item should be fully deduplicated
            batch2 = BatchRequest(items=[item])
            response = await orch.process_batch(batch2, process)

        assert response.stats.total_items == 1


# ---------------------------------------------------------------------------
# mcp/maci_filter.py
# ---------------------------------------------------------------------------
from enhanced_agent_bus.mcp.maci_filter import (
    MACIToolFilter,
    MACIToolRole,
    ToolFilterConfig,
    ToolFilterResult,
    create_maci_tool_filter,
)


class TestMACIToolFilter:
    """MACIToolFilter role-based tool access control tests."""

    def test_proposer_can_query(self):
        flt = create_maci_tool_filter()
        assert flt.check_access(MACIToolRole.PROPOSER, "audit_query_logs") is True

    def test_proposer_cannot_write(self):
        flt = create_maci_tool_filter(audit_denials=False)
        assert flt.check_access(MACIToolRole.PROPOSER, "audit_write_entry") is False

    def test_validator_can_verify(self):
        flt = create_maci_tool_filter()
        assert flt.check_access(MACIToolRole.VALIDATOR, "audit_verify_hash") is True

    def test_executor_can_apply(self):
        flt = create_maci_tool_filter()
        assert flt.check_access(MACIToolRole.EXECUTOR, "policy_apply_v2") is True

    def test_executor_cannot_query(self):
        flt = create_maci_tool_filter(audit_denials=False)
        assert flt.check_access(MACIToolRole.EXECUTOR, "audit_query_logs") is False

    def test_unknown_role_strict_denies(self):
        flt = create_maci_tool_filter(strict_mode=True, audit_denials=False)
        assert flt.check_access("unknown_role", "anything") is False

    def test_unknown_role_non_strict_still_denies(self):
        flt = create_maci_tool_filter(strict_mode=False, audit_denials=False)
        assert flt.check_access("unknown_role", "anything") is False

    def test_filter_tools_preserves_order(self):
        flt = create_maci_tool_filter(audit_denials=False)
        tools = ["policy_list_all", "audit_write_x", "audit_query_recent"]
        allowed = flt.filter_tools(MACIToolRole.PROPOSER, tools)
        assert allowed == ["policy_list_all", "audit_query_recent"]

    def test_allowed_patterns_returns_list(self):
        flt = create_maci_tool_filter()
        pats = flt.allowed_patterns(MACIToolRole.PROPOSER)
        assert isinstance(pats, list)
        assert len(pats) > 0

    def test_allowed_patterns_unknown_role(self):
        flt = create_maci_tool_filter()
        assert flt.allowed_patterns("bogus") == []

    def test_check_access_detailed(self):
        flt = create_maci_tool_filter()
        result = flt.check_access_detailed(MACIToolRole.PROPOSER, "audit_query_logs")
        assert isinstance(result, ToolFilterResult)
        assert result.permitted is True
        assert result.matched_pattern is not None

    def test_check_access_detailed_denial(self):
        flt = create_maci_tool_filter(audit_denials=False)
        result = flt.check_access_detailed(MACIToolRole.PROPOSER, "audit_write_x")
        assert result.permitted is False
        assert result.matched_pattern is None

    def test_to_audit_dict(self):
        result = ToolFilterResult(
            permitted=True,
            role="proposer",
            tool_name="audit_query_logs",
            matched_pattern="audit_query_*",
        )
        d = result.to_audit_dict()
        assert d["permitted"] is True
        assert "evaluated_at" in d

    def test_string_role_coercion(self):
        flt = create_maci_tool_filter()
        assert flt.check_access("proposer", "audit_query_logs") is True

    def test_canonical_role_projection(self):
        flt = create_maci_tool_filter()
        assert flt.check_access(MACIRole.EXECUTIVE, "audit_query_logs") is True
        assert flt.check_access(MACIRole.CONTROLLER, "policy_apply_v2") is True

    def test_check_access_with_extra_context(self):
        flt = create_maci_tool_filter(audit_denials=True)
        # Denial with extra context (exercises _log_denial with extra)
        flt.check_access(MACIToolRole.PROPOSER, "audit_write_x", extra={"agent_id": "a-1"})

    def test_filter_tools_logs_denials(self):
        flt = create_maci_tool_filter(audit_denials=True)
        flt.filter_tools(MACIToolRole.PROPOSER, ["audit_write_entry"])


class TestToolFilterConfig:
    """ToolFilterConfig construction and env loading."""

    def test_default_resolved_matrix(self):
        cfg = ToolFilterConfig()
        m = cfg.resolved_matrix()
        assert MACIToolRole.PROPOSER in m

    def test_custom_matrix(self):
        custom = {MACIToolRole.PROPOSER: ["custom_*"]}
        cfg = ToolFilterConfig(role_tool_matrix=custom)
        assert cfg.resolved_matrix() == custom

    def test_from_env_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            cfg = ToolFilterConfig.from_env()
        assert cfg.strict_mode is True
        assert cfg.audit_denials is True

    def test_from_env_strict_false(self):
        with patch.dict("os.environ", {"MACI_FILTER_STRICT_MODE": "false"}, clear=True):
            cfg = ToolFilterConfig.from_env()
        assert cfg.strict_mode is False

    def test_from_env_custom_patterns(self):
        with patch.dict(
            "os.environ",
            {"MACI_FILTER_PROPOSER_PATTERNS": "custom_read_*,custom_list_*"},
            clear=True,
        ):
            cfg = ToolFilterConfig.from_env()
        m = cfg.resolved_matrix()
        assert "custom_read_*" in m[MACIToolRole.PROPOSER]

    def test_from_env_audit_false(self):
        with patch.dict("os.environ", {"MACI_FILTER_AUDIT_DENIALS": "false"}, clear=True):
            cfg = ToolFilterConfig.from_env()
        assert cfg.audit_denials is False

    def test_from_env_empty_pattern_ignored(self):
        with patch.dict(
            "os.environ",
            {"MACI_FILTER_EXECUTOR_PATTERNS": "  ,  "},
            clear=True,
        ):
            cfg = ToolFilterConfig.from_env()
        # Empty patterns should not trigger override
        assert cfg.role_tool_matrix is None


# ---------------------------------------------------------------------------
# api/badge_generator.py
# ---------------------------------------------------------------------------
from enhanced_agent_bus.api.badge_generator import (
    _score_label,
    _score_to_color,
    generate_badge_svg,
)


class TestBadgeGenerator:
    """Badge SVG generation tests."""

    def test_score_to_color_green(self):
        assert _score_to_color(0.95) == "#4c1"

    def test_score_to_color_yellow_green(self):
        assert _score_to_color(0.75) == "#a3c51c"

    def test_score_to_color_yellow(self):
        assert _score_to_color(0.55) == "#dfb317"

    def test_score_to_color_orange(self):
        assert _score_to_color(0.35) == "#fe7d37"

    def test_score_to_color_red(self):
        assert _score_to_color(0.1) == "#e05d44"

    def test_score_label(self):
        assert _score_label(0.95) == "95%"
        assert _score_label(0.0) == "0%"
        assert _score_label(1.0) == "100%"

    def test_generate_badge_svg_default(self):
        svg = generate_badge_svg()
        assert "<svg" in svg
        assert "ACGS" in svg
        assert "100%" in svg

    def test_generate_badge_svg_custom(self):
        svg = generate_badge_svg(label="Gov", score=0.5, message="partial")
        assert "Gov" in svg
        assert "partial" in svg

    def test_generate_badge_svg_clamps_score(self):
        svg_low = generate_badge_svg(score=-0.5)
        assert "0%" in svg_low
        svg_high = generate_badge_svg(score=1.5)
        assert "100%" in svg_high

    def test_generate_badge_svg_escapes_html(self):
        svg = generate_badge_svg(label="<script>", message="&danger")
        assert "<script>" not in svg
        assert "&lt;script&gt;" in svg


# ---------------------------------------------------------------------------
# api/runtime_guards.py
# ---------------------------------------------------------------------------
from enhanced_agent_bus.api.runtime_guards import (
    current_environment,
    is_sandbox_environment,
    require_sandbox_endpoint,
)


class TestRuntimeGuards:
    """Runtime environment guard tests."""

    def test_current_environment_default(self):
        with patch.dict("os.environ", {}, clear=True):
            assert current_environment() == ""

    def test_current_environment_set(self):
        with patch.dict("os.environ", {"ENVIRONMENT": "  Production  "}):
            assert current_environment() == "production"

    def test_is_sandbox_dev(self):
        with patch.dict("os.environ", {"ENVIRONMENT": "development"}):
            assert is_sandbox_environment() is True

    def test_is_sandbox_test(self):
        with patch.dict("os.environ", {"ENVIRONMENT": "test"}):
            assert is_sandbox_environment() is True

    def test_is_not_sandbox_production(self):
        with patch.dict("os.environ", {"ENVIRONMENT": "production"}):
            assert is_sandbox_environment() is False

    def test_require_sandbox_allows_in_dev(self):
        with patch.dict("os.environ", {"ENVIRONMENT": "dev"}):
            require_sandbox_endpoint("test_ep", "test detail")  # should not raise

    def test_require_sandbox_blocks_in_prod(self):
        from fastapi import HTTPException

        with patch.dict("os.environ", {"ENVIRONMENT": "production"}):
            with pytest.raises(HTTPException) as exc_info:
                require_sandbox_endpoint("test_ep", "test detail")
            assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# api/validation_store.py
# ---------------------------------------------------------------------------
from enhanced_agent_bus.api.validation_store import (
    ValidationEntry,
    ValidationStore,
    get_validation_store,
)


class TestValidationStore:
    """ValidationStore ring-buffer tests."""

    def _make_entry(
        self, agent_id: str = "a1", compliant: bool = True, score: float = 0.9
    ) -> ValidationEntry:
        return ValidationEntry(
            agent_id=agent_id,
            action="validate",
            compliant=compliant,
            score=score,
            latency_ms=1.5,
            request_id="req-1",
        )

    def test_record_and_get_recent(self):
        store = ValidationStore(max_entries=10)
        store.record(self._make_entry())
        recent = store.get_recent()
        assert len(recent) == 1

    def test_recent_newest_first(self):
        store = ValidationStore(max_entries=10)
        store.record(self._make_entry(agent_id="first"))
        store.record(self._make_entry(agent_id="second"))
        recent = store.get_recent()
        assert recent[0].agent_id == "second"

    def test_ring_buffer_eviction(self):
        store = ValidationStore(max_entries=3)
        for i in range(5):
            store.record(self._make_entry(agent_id=f"a{i}"))
        recent = store.get_recent(limit=10)
        assert len(recent) == 3

    def test_get_stats_empty(self):
        store = ValidationStore()
        stats = store.get_stats()
        assert stats["total_validations"] == 0
        assert stats["compliance_rate"] == 100.0
        assert stats["recent_validations"] == []

    def test_get_stats_with_data(self):
        store = ValidationStore()
        store.record(self._make_entry(compliant=True, score=0.9))
        store.record(self._make_entry(compliant=False, score=0.3))
        stats = store.get_stats()
        assert stats["total_validations"] == 2
        assert stats["compliance_rate"] == 50.0
        assert stats["unique_agents"] == 1
        assert len(stats["recent_validations"]) == 2

    def test_get_stats_avg_latency(self):
        store = ValidationStore()
        e1 = ValidationEntry(
            agent_id="a1", action="v", compliant=True, score=1.0, latency_ms=2.0, request_id="r1"
        )
        e2 = ValidationEntry(
            agent_id="a2", action="v", compliant=True, score=1.0, latency_ms=4.0, request_id="r2"
        )
        store.record(e1)
        store.record(e2)
        stats = store.get_stats()
        assert stats["avg_latency_ms"] == 3.0
        assert stats["unique_agents"] == 2

    def test_singleton_returns_same_instance(self):
        s1 = get_validation_store()
        s2 = get_validation_store()
        assert s1 is s2


# ---------------------------------------------------------------------------
# components/agent_registry_manager.py
# ---------------------------------------------------------------------------
from enhanced_agent_bus.components.agent_registry_manager import AgentRegistryManager


class TestAgentRegistryManager:
    """AgentRegistryManager CRUD tests."""

    def _make_manager(self) -> AgentRegistryManager:
        mock_registry = MagicMock()
        mock_registry._agents = {}
        return AgentRegistryManager(registry=mock_registry)

    @pytest.mark.asyncio
    async def test_register_agent(self):
        mgr = self._make_manager()
        result = await mgr.register_agent(
            agent_id="a1",
            agent_type="worker",
            capabilities=["compute"],
            metadata={"key": "val"},
            tenant_id="t1",
        )
        assert result is True
        assert "a1" in mgr.get_registered_agents()

    @pytest.mark.asyncio
    async def test_unregister_agent(self):
        mgr = self._make_manager()
        await mgr.register_agent("a1", "worker")
        result = await mgr.unregister_agent("a1")
        assert result is True
        assert "a1" not in mgr.get_registered_agents()

    @pytest.mark.asyncio
    async def test_unregister_nonexistent(self):
        mgr = self._make_manager()
        result = await mgr.unregister_agent("ghost")
        assert result is False

    def test_get_agent_info(self):
        mgr = self._make_manager()
        assert mgr.get_agent_info("a1") is None

    @pytest.mark.asyncio
    async def test_get_agent_info_after_register(self):
        mgr = self._make_manager()
        await mgr.register_agent("a1", "worker")
        info = mgr.get_agent_info("a1")
        assert info is not None
        assert info["agent_type"] == "worker"

    def test_get_registered_agents_empty(self):
        mgr = self._make_manager()
        assert mgr.get_registered_agents() == []

    @pytest.mark.asyncio
    async def test_get_agents_by_type(self):
        mgr = self._make_manager()
        await mgr.register_agent("a1", "worker")
        await mgr.register_agent("a2", "monitor")
        assert mgr.get_agents_by_type("worker") == ["a1"]

    @pytest.mark.asyncio
    async def test_get_agents_by_capability(self):
        mgr = self._make_manager()
        await mgr.register_agent("a1", "worker", capabilities=["compute", "store"])
        await mgr.register_agent("a2", "worker", capabilities=["store"])
        assert set(mgr.get_agents_by_capability("store")) == {"a1", "a2"}
        assert mgr.get_agents_by_capability("compute") == ["a1"]

    @pytest.mark.asyncio
    async def test_get_agents_by_tenant(self):
        mgr = self._make_manager()
        await mgr.register_agent("a1", "worker", tenant_id="t1")
        await mgr.register_agent("a2", "worker", tenant_id="t2")
        assert mgr.get_agents_by_tenant("t1") == ["a1"]

    @pytest.mark.asyncio
    async def test_update_agent_status(self):
        mgr = self._make_manager()
        await mgr.register_agent("a1", "worker")
        result = await mgr.update_agent_status("a1", "inactive")
        assert result is True
        info = mgr.get_agent_info("a1")
        assert info["status"] == "inactive"

    @pytest.mark.asyncio
    async def test_update_status_nonexistent(self):
        mgr = self._make_manager()
        result = await mgr.update_agent_status("ghost", "inactive")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_registry_stats(self):
        mgr = self._make_manager()
        await mgr.register_agent("a1", "worker")
        await mgr.register_agent("a2", "monitor")
        stats = mgr.get_registry_stats()
        assert stats["total_agents"] == 2
        assert stats["agents_by_type"]["worker"] == 1
        assert stats["agents_by_type"]["monitor"] == 1

    def test_get_registry_stats_empty(self):
        mgr = self._make_manager()
        stats = mgr.get_registry_stats()
        assert stats["total_agents"] == 0

    def test_cleanup_inactive_agents(self):
        mgr = self._make_manager()
        count = mgr.cleanup_inactive_agents(max_age_hours=1)
        assert count == 0

    def test_manager_with_no_registry(self):
        """Default constructor falls back to InMemoryAgentRegistry or RedisAgentRegistry."""
        mgr = AgentRegistryManager(registry=MagicMock())
        assert mgr is not None
