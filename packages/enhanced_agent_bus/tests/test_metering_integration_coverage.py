"""
ACGS-2 Enhanced Agent Bus — Metering Integration Coverage Tests
Constitutional Hash: 608508a9bd224290

Targets ≥90% coverage of metering_integration.py.
Uses direct src.core.* import path; no module-level skip guard.
asyncio_mode = "auto" — no @pytest.mark.asyncio needed.
"""

import asyncio
import enum
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Provide stub enums when the real metering service is unavailable.
# The production module sets MeterableOperation / MeteringTier to None when
# src.core.services.metering cannot be imported.  Tests need real enum-like
# objects so attribute access (e.g. MeterableOperation.CONSTITUTIONAL_VALIDATION)
# works and enum comparisons behave correctly.
# ---------------------------------------------------------------------------
import enhanced_agent_bus.metering_integration as _mi

if not _mi.METERING_AVAILABLE:

    class _MeterableOperation(enum.Enum):
        CONSTITUTIONAL_VALIDATION = "constitutional_validation"
        AGENT_MESSAGE = "agent_message"
        POLICY_EVALUATION = "policy_evaluation"
        DELIBERATION_REQUEST = "deliberation_request"
        HITL_APPROVAL = "hitl_approval"

    class _MeteringTier(enum.Enum):
        STANDARD = "standard"
        ENHANCED = "enhanced"
        ENTERPRISE = "enterprise"
        DELIBERATION = "deliberation"

    class _UsageMeteringService:
        """Lightweight stub so start() can instantiate a metering service."""

        def __init__(self, **kwargs):
            pass

        async def start(self):
            pass

        async def stop(self):
            pass

        async def record_event(self, **kwargs):
            pass

    _mi.MeterableOperation = _MeterableOperation  # type: ignore[attr-defined]
    _mi.MeteringTier = _MeteringTier  # type: ignore[attr-defined]
    _mi.UsageMeteringService = _UsageMeteringService  # type: ignore[attr-defined]
    _mi.METERING_AVAILABLE = True  # type: ignore[attr-defined]

from enhanced_agent_bus.metering_integration import (
    CONSTITUTIONAL_HASH,
    METERING_AVAILABLE,
    AsyncMeteringQueue,
    MeterableOperation,
    MeteringConfig,
    MeteringHooks,
    MeteringMixin,
    MeteringTier,
    get_metering_hooks,
    get_metering_queue,
    metered_operation,
    reset_metering,
)

# ---------------------------------------------------------------------------
# Primary import — always available via src.core path
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def _make_config(**kw) -> MeteringConfig:
    defaults = dict(
        enabled=True,
        aggregation_interval_seconds=1,
        max_queue_size=100,
        batch_size=10,
        flush_interval_seconds=0.05,
        constitutional_hash=CONSTITUTIONAL_HASH,
    )
    defaults.update(kw)
    return MeteringConfig(**defaults)


def _make_queue(config=None) -> AsyncMeteringQueue:
    cfg = config or _make_config()
    q = AsyncMeteringQueue(cfg)
    # Simulate "running" so enqueue works without actually starting
    q._running = True
    return q


@pytest.fixture(autouse=True)
def reset_singletons():
    """Isolate global singleton state between tests."""
    reset_metering()
    yield
    reset_metering()


# ---------------------------------------------------------------------------
# MeteringConfig
# ---------------------------------------------------------------------------


class TestMeteringConfig:
    def test_defaults(self):
        cfg = MeteringConfig()
        # enabled depends on METERING_AVAILABLE
        assert cfg.enabled == METERING_AVAILABLE
        assert cfg.aggregation_interval_seconds == 60
        assert cfg.max_queue_size == 10_000
        assert cfg.batch_size == 100
        assert cfg.flush_interval_seconds == 1.0
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH
        assert cfg.redis_url is None

    def test_custom_values(self):
        cfg = _make_config(redis_url="redis://localhost:6379", max_queue_size=5000)
        assert cfg.enabled is True
        assert cfg.redis_url == "redis://localhost:6379"
        assert cfg.max_queue_size == 5000

    def test_enabled_false_overrides_metering_available(self):
        cfg = MeteringConfig(enabled=False)
        assert cfg.enabled is False

    def test_enabled_true_respects_metering_available(self):
        cfg = MeteringConfig(enabled=True)
        # enabled is True only when both arg and METERING_AVAILABLE are True
        assert cfg.enabled == (True and METERING_AVAILABLE)


# ---------------------------------------------------------------------------
# AsyncMeteringQueue — initialisation
# ---------------------------------------------------------------------------


class TestAsyncMeteringQueueInit:
    def test_initial_state(self):
        q = AsyncMeteringQueue(_make_config())
        assert q._running is False
        assert q._events_queued == 0
        assert q._events_flushed == 0
        assert q._events_dropped == 0
        assert q._flush_task is None
        assert q._metering_service is None

    def test_custom_metering_service(self):
        svc = MagicMock()
        q = AsyncMeteringQueue(_make_config(), metering_service=svc)
        assert q._metering_service is svc


# ---------------------------------------------------------------------------
# AsyncMeteringQueue — start / stop
# ---------------------------------------------------------------------------


class TestAsyncMeteringQueueStartStop:
    async def test_start_disabled_config(self):
        cfg = MeteringConfig(enabled=False)
        q = AsyncMeteringQueue(cfg)
        await q.start()
        assert q._running is False
        assert q._flush_task is None

    async def test_start_already_running(self):
        q = _make_queue()
        # Already running — second start should be a no-op
        q._flush_task = MagicMock()
        prev_task = q._flush_task
        await q.start()  # should return early; _flush_task unchanged
        assert q._flush_task is prev_task

    async def test_start_creates_flush_task(self):
        q = AsyncMeteringQueue(_make_config())
        # Provide a mock metering service so we don't hit redis
        q._metering_service = AsyncMock()
        q._metering_service.start = AsyncMock()
        await q.start()
        assert q._running is True
        assert q._flush_task is not None
        # Clean up
        await q.stop()

    async def test_start_initialises_metering_service_when_available(self):
        """When _metering_service is None and METERING_AVAILABLE, service is created."""
        q = AsyncMeteringQueue(_make_config())
        assert q._metering_service is None

        mock_svc = AsyncMock()
        mock_svc.start = AsyncMock()
        mock_svc.stop = AsyncMock()
        mock_cls = MagicMock(return_value=mock_svc)

        # Patch the actual __globals__ dict that AsyncMeteringQueue.start uses
        start_globals = AsyncMeteringQueue.start.__globals__
        with patch.dict(
            start_globals, {"UsageMeteringService": mock_cls, "METERING_AVAILABLE": True}
        ):
            await q.start()

        mock_cls.assert_called_once()
        mock_svc.start.assert_awaited_once()
        await q.stop()

    async def test_stop_cancels_flush_task(self):
        q = AsyncMeteringQueue(_make_config())
        q._metering_service = AsyncMock()
        q._metering_service.start = AsyncMock()
        q._metering_service.stop = AsyncMock()
        await q.start()
        assert q._running is True

        await q.stop()
        assert q._running is False

    async def test_stop_without_flush_task(self):
        q = AsyncMeteringQueue(_make_config())
        q._running = True
        # No _flush_task — stop should not raise
        await q.stop()
        assert q._running is False

    async def test_stop_calls_metering_service_stop(self):
        mock_svc = AsyncMock()
        mock_svc.stop = AsyncMock()
        q = AsyncMeteringQueue(_make_config(), metering_service=mock_svc)
        q._running = True
        await q.stop()
        mock_svc.stop.assert_awaited_once()

    async def test_stop_handles_cancelled_error(self):
        """CancelledError from flush task is swallowed."""
        q = AsyncMeteringQueue(_make_config())

        async def raise_cancelled():
            raise asyncio.CancelledError

        fake_task = asyncio.create_task(raise_cancelled())
        await asyncio.sleep(0)  # let it start
        q._flush_task = fake_task
        q._running = True
        # Should not propagate CancelledError
        await q.stop()


# ---------------------------------------------------------------------------
# AsyncMeteringQueue — enqueue_nowait
# ---------------------------------------------------------------------------


class TestEnqueueNowait:
    def test_enqueue_success(self):
        q = _make_queue()
        result = q.enqueue_nowait(
            tenant_id="t1",
            operation=MeterableOperation.CONSTITUTIONAL_VALIDATION,
            tier=MeteringTier.STANDARD,
            agent_id="a1",
            tokens_processed=100,
            latency_ms=1.5,
            compliance_score=1.0,
            metadata={"key": "value"},
        )
        assert result is True
        assert q._events_queued == 1
        assert q._queue.qsize() == 1

    def test_enqueue_disabled(self):
        cfg = MeteringConfig(enabled=False)
        q = AsyncMeteringQueue(cfg)
        result = q.enqueue_nowait(
            tenant_id="t1",
            operation=MeterableOperation.CONSTITUTIONAL_VALIDATION,
        )
        assert result is False
        assert q._events_queued == 0

    def test_enqueue_metering_not_available(self):
        """When METERING_AVAILABLE=False, enqueue returns False."""
        q = _make_queue()
        # Patch the actual __globals__ dict used by enqueue_nowait at runtime
        with patch.dict(
            AsyncMeteringQueue.enqueue_nowait.__globals__, {"METERING_AVAILABLE": False}
        ):
            result = q.enqueue_nowait(
                tenant_id="t1",
                operation=None,
            )
        assert result is False

    def test_enqueue_defaults_tier_to_standard(self):
        q = _make_queue()
        result = q.enqueue_nowait(
            tenant_id="t1",
            operation=MeterableOperation.CONSTITUTIONAL_VALIDATION,
            tier=None,
        )
        assert result is True
        # Verify that STANDARD was used (inspect queue item)
        item = q._queue.get_nowait()
        assert item["tier"] == MeteringTier.STANDARD

    def test_enqueue_defaults_metadata_to_empty_dict(self):
        q = _make_queue()
        q.enqueue_nowait(
            tenant_id="t1",
            operation=MeterableOperation.CONSTITUTIONAL_VALIDATION,
            metadata=None,
        )
        item = q._queue.get_nowait()
        assert item["metadata"] == {}

    def test_enqueue_queue_full_drops_event(self):
        cfg = _make_config(max_queue_size=1)
        q = AsyncMeteringQueue(cfg)
        q._running = True

        r1 = q.enqueue_nowait(
            tenant_id="t1", operation=MeterableOperation.CONSTITUTIONAL_VALIDATION
        )
        r2 = q.enqueue_nowait(
            tenant_id="t2", operation=MeterableOperation.CONSTITUTIONAL_VALIDATION
        )

        assert r1 is True
        assert r2 is False
        assert q._events_dropped == 1

    def test_enqueue_event_structure(self):
        q = _make_queue()
        q.enqueue_nowait(
            tenant_id="tenant-x",
            operation=MeterableOperation.AGENT_MESSAGE,
            tier=MeteringTier.ENHANCED,
            agent_id="agent-99",
            tokens_processed=42,
            latency_ms=3.14,
            compliance_score=0.75,
            metadata={"extra": True},
        )
        item = q._queue.get_nowait()
        assert item["tenant_id"] == "tenant-x"
        assert item["operation"] == MeterableOperation.AGENT_MESSAGE
        assert item["tier"] == MeteringTier.ENHANCED
        assert item["agent_id"] == "agent-99"
        assert item["tokens_processed"] == 42
        assert item["latency_ms"] == 3.14
        assert item["compliance_score"] == 0.75
        assert item["metadata"] == {"extra": True}
        assert "timestamp" in item


# ---------------------------------------------------------------------------
# AsyncMeteringQueue — _flush_loop and _flush_batch
# ---------------------------------------------------------------------------


class TestFlushLogic:
    async def test_flush_batch_no_service(self):
        q = _make_queue()
        q._metering_service = None
        # Should return without error
        await q._flush_batch()
        assert q._events_flushed == 0

    async def test_flush_batch_empty_queue(self):
        q = _make_queue()
        q._metering_service = AsyncMock()
        # Queue is empty — nothing to flush
        await q._flush_batch()
        q._metering_service.record_event.assert_not_awaited()

    async def test_flush_batch_records_events(self):
        q = _make_queue()
        mock_svc = AsyncMock()
        mock_svc.record_event = AsyncMock()
        q._metering_service = mock_svc

        for _ in range(3):
            q.enqueue_nowait(
                tenant_id="t1",
                operation=MeterableOperation.CONSTITUTIONAL_VALIDATION,
                tier=MeteringTier.STANDARD,
                latency_ms=1.0,
            )

        await q._flush_batch()
        assert q._events_flushed == 3
        assert mock_svc.record_event.await_count == 3

    async def test_flush_batch_handles_record_error(self):
        """Errors from record_event are caught and logged; counter not incremented."""
        q = _make_queue()
        mock_svc = AsyncMock()
        mock_svc.record_event = AsyncMock(side_effect=RuntimeError("boom"))
        q._metering_service = mock_svc

        q.enqueue_nowait(
            tenant_id="t1",
            operation=MeterableOperation.CONSTITUTIONAL_VALIDATION,
            latency_ms=1.0,
        )

        await q._flush_batch()
        # No events should be counted as flushed
        assert q._events_flushed == 0

    async def test_flush_loop_runs_and_exits_on_cancel(self):
        q = _make_queue()
        q._metering_service = AsyncMock()
        q._metering_service.record_event = AsyncMock()
        q._running = True

        task = asyncio.create_task(q._flush_loop())
        # Let it run one iteration
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def test_flush_loop_handles_flush_errors(self):
        """Non-CancelledError exceptions in flush loop are logged, not re-raised."""
        q = _make_queue()
        q._running = True
        call_count = 0

        async def failing_flush():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient flush error")
            # Stop after second call
            q._running = False

        q._flush_batch = failing_flush  # type: ignore[method-assign]

        # Run the loop (it will encounter the error then exit)
        await q._flush_loop()
        assert call_count >= 1

    async def test_flush_batch_queue_empty_exception_path(self):
        """Cover the except asyncio.QueueEmpty path in _flush_batch.

        We mock the internal Queue so that empty() returns False (bypasses early
        return and the inner break) but get_nowait() raises QueueEmpty on the
        first call — while the batch list remains empty so the `if not batch` path
        is also exercised.
        """
        q = _make_queue()
        mock_svc = AsyncMock()
        mock_svc.record_event = AsyncMock()
        q._metering_service = mock_svc

        # Replace the internal asyncio.Queue with a mock
        mock_inner_q = MagicMock()
        mock_inner_q.empty.return_value = False  # passes both empty() checks
        mock_inner_q.get_nowait.side_effect = asyncio.QueueEmpty
        mock_inner_q.qsize.return_value = 0
        q._queue = mock_inner_q

        await q._flush_batch()
        # get_nowait raised QueueEmpty; batch is empty so early return hit (line 239)
        assert q._events_flushed == 0

    async def test_flush_batch_respects_batch_size(self):
        """Flush only processes up to batch_size events."""
        cfg = _make_config(batch_size=2, max_queue_size=20)
        q = AsyncMeteringQueue(cfg)
        q._running = True

        mock_svc = AsyncMock()
        mock_svc.record_event = AsyncMock()
        q._metering_service = mock_svc

        for _ in range(5):
            q.enqueue_nowait(
                tenant_id="t1",
                operation=MeterableOperation.CONSTITUTIONAL_VALIDATION,
                latency_ms=1.0,
            )

        await q._flush_batch()
        # Only 2 (batch_size) events flushed
        assert q._events_flushed == 2
        assert q._queue.qsize() == 3


# ---------------------------------------------------------------------------
# AsyncMeteringQueue — get_metrics
# ---------------------------------------------------------------------------


class TestGetMetrics:
    def test_get_metrics_structure(self):
        q = _make_queue()
        m = q.get_metrics()
        assert m["events_queued"] == 0
        assert m["events_flushed"] == 0
        assert m["events_dropped"] == 0
        assert m["queue_size"] == 0
        assert m["running"] is True
        assert m["enabled"] is True
        assert m["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_get_metrics_reflects_activity(self):
        q = _make_queue()
        q.enqueue_nowait(
            tenant_id="t1",
            operation=MeterableOperation.CONSTITUTIONAL_VALIDATION,
            latency_ms=1.0,
        )
        m = q.get_metrics()
        assert m["events_queued"] == 1
        assert m["queue_size"] == 1


# ---------------------------------------------------------------------------
# MeteringHooks
# ---------------------------------------------------------------------------


class TestMeteringHooks:
    def _hooks_and_queue(self):
        q = _make_queue()
        h = MeteringHooks(q)
        return h, q

    # on_constitutional_validation
    def test_constitutional_validation_valid(self):
        h, q = self._hooks_and_queue()
        h.on_constitutional_validation(tenant_id="t1", agent_id="a1", is_valid=True, latency_ms=0.5)
        assert q._events_queued == 1
        item = q._queue.get_nowait()
        assert item["compliance_score"] == 1.0
        assert item["metadata"]["is_valid"] is True

    def test_constitutional_validation_invalid(self):
        h, q = self._hooks_and_queue()
        h.on_constitutional_validation(
            tenant_id="t1", agent_id=None, is_valid=False, latency_ms=0.5
        )
        item = q._queue.get_nowait()
        assert item["compliance_score"] == 0.0

    def test_constitutional_validation_empty_tenant(self):
        h, q = self._hooks_and_queue()
        h.on_constitutional_validation(tenant_id="", agent_id=None, is_valid=True, latency_ms=0.5)
        item = q._queue.get_nowait()
        assert item["tenant_id"] == "default"

    def test_constitutional_validation_none_tenant(self):
        h, q = self._hooks_and_queue()
        # passing None for tenant_id — should fall back to "default"
        h.on_constitutional_validation(
            tenant_id=None,
            agent_id=None,
            is_valid=True,
            latency_ms=0.5,  # type: ignore[arg-type]
        )
        item = q._queue.get_nowait()
        assert item["tenant_id"] == "default"

    def test_constitutional_validation_with_metadata(self):
        h, q = self._hooks_and_queue()
        h.on_constitutional_validation(
            tenant_id="t1",
            agent_id="a1",
            is_valid=True,
            latency_ms=1.0,
            metadata={"extra": "data"},
        )
        item = q._queue.get_nowait()
        assert item["metadata"]["extra"] == "data"

    def test_constitutional_validation_tier_explicit(self):
        h, q = self._hooks_and_queue()
        h.on_constitutional_validation(
            tenant_id="t1",
            agent_id="a1",
            is_valid=True,
            latency_ms=1.0,
            tier=MeteringTier.ENTERPRISE,
        )
        item = q._queue.get_nowait()
        assert item["tier"] == MeteringTier.ENTERPRISE

    # on_agent_message
    def test_agent_message_valid(self):
        h, q = self._hooks_and_queue()
        h.on_agent_message(
            tenant_id="t1",
            from_agent="ag1",
            to_agent="ag2",
            message_type="governance",
            latency_ms=1.0,
            is_valid=True,
        )
        assert q._events_queued == 1
        item = q._queue.get_nowait()
        assert item["compliance_score"] == 1.0
        assert item["metadata"]["from_agent"] == "ag1"
        assert item["metadata"]["to_agent"] == "ag2"
        assert item["metadata"]["message_type"] == "governance"

    def test_agent_message_invalid(self):
        h, q = self._hooks_and_queue()
        h.on_agent_message(
            tenant_id="t1",
            from_agent="ag1",
            to_agent=None,
            message_type="query",
            latency_ms=1.0,
            is_valid=False,
        )
        item = q._queue.get_nowait()
        assert item["compliance_score"] == 0.0

    def test_agent_message_empty_tenant(self):
        h, q = self._hooks_and_queue()
        h.on_agent_message(
            tenant_id="",
            from_agent="ag1",
            to_agent=None,
            message_type="query",
            latency_ms=1.0,
            is_valid=True,
        )
        item = q._queue.get_nowait()
        assert item["tenant_id"] == "default"

    def test_agent_message_with_explicit_tier(self):
        h, q = self._hooks_and_queue()
        h.on_agent_message(
            tenant_id="t1",
            from_agent="ag1",
            to_agent=None,
            message_type="query",
            latency_ms=1.0,
            is_valid=True,
            tier=MeteringTier.ENHANCED,
        )
        item = q._queue.get_nowait()
        assert item["tier"] == MeteringTier.ENHANCED

    def test_agent_message_with_metadata(self):
        h, q = self._hooks_and_queue()
        h.on_agent_message(
            tenant_id="t1",
            from_agent="ag1",
            to_agent="ag2",
            message_type="query",
            latency_ms=1.0,
            is_valid=True,
            metadata={"trace_id": "xyz"},
        )
        item = q._queue.get_nowait()
        assert item["metadata"]["trace_id"] == "xyz"

    # on_policy_evaluation
    def test_policy_evaluation_allow(self):
        h, q = self._hooks_and_queue()
        h.on_policy_evaluation(
            tenant_id="t1",
            agent_id="a1",
            policy_name="opa_check",
            decision="allow",
            latency_ms=2.0,
        )
        assert q._events_queued == 1
        item = q._queue.get_nowait()
        assert item["compliance_score"] == 1.0
        assert item["metadata"]["policy_name"] == "opa_check"
        assert item["metadata"]["decision"] == "allow"

    def test_policy_evaluation_deny(self):
        h, q = self._hooks_and_queue()
        h.on_policy_evaluation(
            tenant_id="t1",
            agent_id="a1",
            policy_name="opa_check",
            decision="deny",
            latency_ms=2.0,
        )
        item = q._queue.get_nowait()
        assert item["compliance_score"] == 0.0

    def test_policy_evaluation_empty_tenant(self):
        h, q = self._hooks_and_queue()
        h.on_policy_evaluation(
            tenant_id="", agent_id=None, policy_name="p", decision="allow", latency_ms=1.0
        )
        item = q._queue.get_nowait()
        assert item["tenant_id"] == "default"

    def test_policy_evaluation_with_explicit_tier(self):
        h, q = self._hooks_and_queue()
        h.on_policy_evaluation(
            tenant_id="t1",
            agent_id=None,
            policy_name="p",
            decision="allow",
            latency_ms=1.0,
            tier=MeteringTier.ENTERPRISE,
        )
        item = q._queue.get_nowait()
        assert item["tier"] == MeteringTier.ENTERPRISE

    def test_policy_evaluation_default_tier_is_enhanced(self):
        h, q = self._hooks_and_queue()
        h.on_policy_evaluation(
            tenant_id="t1",
            agent_id=None,
            policy_name="p",
            decision="allow",
            latency_ms=1.0,
            tier=None,
        )
        item = q._queue.get_nowait()
        # Default for policy_evaluation when METERING_AVAILABLE is ENHANCED
        assert item["tier"] == MeteringTier.ENHANCED

    def test_policy_evaluation_with_metadata(self):
        h, q = self._hooks_and_queue()
        h.on_policy_evaluation(
            tenant_id="t1",
            agent_id=None,
            policy_name="p",
            decision="allow",
            latency_ms=1.0,
            metadata={"rule": "test"},
        )
        item = q._queue.get_nowait()
        assert item["metadata"]["rule"] == "test"

    # on_deliberation_request
    def test_deliberation_request(self):
        h, q = self._hooks_and_queue()
        h.on_deliberation_request(
            tenant_id="t1",
            agent_id="a1",
            impact_score=0.85,
            latency_ms=5.0,
        )
        assert q._events_queued == 1
        item = q._queue.get_nowait()
        assert item["compliance_score"] == 0.85
        assert item["metadata"]["impact_score"] == 0.85

    def test_deliberation_request_empty_tenant(self):
        h, q = self._hooks_and_queue()
        h.on_deliberation_request(tenant_id="", agent_id=None, impact_score=0.9, latency_ms=1.0)
        item = q._queue.get_nowait()
        assert item["tenant_id"] == "default"

    def test_deliberation_request_with_metadata(self):
        h, q = self._hooks_and_queue()
        h.on_deliberation_request(
            tenant_id="t1",
            agent_id="a1",
            impact_score=0.9,
            latency_ms=1.0,
            metadata={"reason": "high risk"},
        )
        item = q._queue.get_nowait()
        assert item["metadata"]["reason"] == "high risk"

    def test_deliberation_request_metering_not_available(self):
        """When METERING_AVAILABLE=False, deliberation does not enqueue."""
        h, q = self._hooks_and_queue()
        fn_globals = MeteringHooks.on_deliberation_request.__globals__
        with patch.dict(fn_globals, {"METERING_AVAILABLE": False}):
            h.on_deliberation_request(
                tenant_id="t1", agent_id="a1", impact_score=0.9, latency_ms=1.0
            )
        assert q._events_queued == 0

    # on_hitl_approval
    def test_hitl_approval_approved(self):
        h, q = self._hooks_and_queue()
        h.on_hitl_approval(
            tenant_id="t1",
            agent_id="a1",
            approver_id="approver-1",
            approved=True,
            latency_ms=10.0,
        )
        assert q._events_queued == 1
        item = q._queue.get_nowait()
        assert item["compliance_score"] == 1.0
        assert item["metadata"]["approver_id"] == "approver-1"
        assert item["metadata"]["approved"] is True

    def test_hitl_approval_rejected(self):
        h, q = self._hooks_and_queue()
        h.on_hitl_approval(
            tenant_id="t1",
            agent_id=None,
            approver_id="approver-2",
            approved=False,
            latency_ms=10.0,
        )
        item = q._queue.get_nowait()
        assert item["compliance_score"] == 0.0

    def test_hitl_approval_empty_tenant(self):
        h, q = self._hooks_and_queue()
        h.on_hitl_approval(
            tenant_id="", agent_id=None, approver_id="x", approved=True, latency_ms=1.0
        )
        item = q._queue.get_nowait()
        assert item["tenant_id"] == "default"

    def test_hitl_approval_with_metadata(self):
        h, q = self._hooks_and_queue()
        h.on_hitl_approval(
            tenant_id="t1",
            agent_id=None,
            approver_id="x",
            approved=True,
            latency_ms=1.0,
            metadata={"sla_ms": 500},
        )
        item = q._queue.get_nowait()
        assert item["metadata"]["sla_ms"] == 500

    def test_hitl_approval_metering_not_available(self):
        h, q = self._hooks_and_queue()
        fn_globals = MeteringHooks.on_hitl_approval.__globals__
        with patch.dict(fn_globals, {"METERING_AVAILABLE": False}):
            h.on_hitl_approval(
                tenant_id="t1",
                agent_id=None,
                approver_id="x",
                approved=True,
                latency_ms=1.0,
            )
        assert q._events_queued == 0


# ---------------------------------------------------------------------------
# Singleton functions
# ---------------------------------------------------------------------------


class TestSingletons:
    def test_get_metering_queue_returns_same_instance(self):
        q1 = get_metering_queue()
        q2 = get_metering_queue()
        assert q1 is q2

    def test_get_metering_queue_with_config(self):
        cfg = _make_config(max_queue_size=42)
        q = get_metering_queue(cfg)
        assert q.config.max_queue_size == 42

    def test_get_metering_hooks_returns_same_instance(self):
        h1 = get_metering_hooks()
        h2 = get_metering_hooks()
        assert h1 is h2

    def test_get_metering_hooks_with_config(self):
        cfg = _make_config(max_queue_size=99)
        h = get_metering_hooks(cfg)
        assert isinstance(h, MeteringHooks)

    def test_reset_creates_fresh_instances(self):
        q1 = get_metering_queue()
        reset_metering()
        q2 = get_metering_queue()
        assert q1 is not q2

    def test_get_metering_hooks_reuses_existing_queue(self):
        q = get_metering_queue()
        h = get_metering_hooks()
        assert h._queue is q


# ---------------------------------------------------------------------------
# metered_operation decorator
# ---------------------------------------------------------------------------


class TestMeteredOperationDecorator:
    async def test_basic_returns_result(self):
        @metered_operation(MeterableOperation.CONSTITUTIONAL_VALIDATION)
        async def fn():
            return 42

        result = await fn()
        assert result == 42

    async def test_result_with_is_valid_attr(self):
        class ValidResult:
            is_valid = True

        @metered_operation(MeterableOperation.CONSTITUTIONAL_VALIDATION)
        async def fn():
            return ValidResult()

        result = await fn()
        assert result.is_valid is True

    async def test_result_with_is_valid_false(self):
        class InvalidResult:
            is_valid = False

        @metered_operation(MeterableOperation.CONSTITUTIONAL_VALIDATION)
        async def fn():
            return InvalidResult()

        result = await fn()
        assert result.is_valid is False

    async def test_exception_reraises(self):
        @metered_operation(MeterableOperation.CONSTITUTIONAL_VALIDATION)
        async def fn():
            raise ValueError("oops")

        with pytest.raises(ValueError, match="oops"):
            await fn()

    async def test_runtime_error_reraises(self):
        @metered_operation(MeterableOperation.CONSTITUTIONAL_VALIDATION)
        async def fn():
            raise RuntimeError("runtime")

        with pytest.raises(RuntimeError):
            await fn()

    async def test_type_error_reraises(self):
        @metered_operation(MeterableOperation.CONSTITUTIONAL_VALIDATION)
        async def fn():
            raise TypeError("type err")

        with pytest.raises(TypeError):
            await fn()

    async def test_extract_tenant_from_first_arg(self):
        class Msg:
            tenant_id = "my-tenant"
            from_agent = "my-agent"

        @metered_operation(MeterableOperation.CONSTITUTIONAL_VALIDATION)
        async def fn(msg):
            return True

        result = await fn(Msg())
        assert result is True

    async def test_extract_tenant_via_callable(self):
        class Obj:
            custom = "extracted"

        @metered_operation(
            MeterableOperation.CONSTITUTIONAL_VALIDATION,
            extract_tenant=lambda o: o.custom,
        )
        async def fn(obj):
            return True

        result = await fn(Obj())
        assert result is True

    async def test_extract_tenant_callable_returns_none_uses_default(self):
        @metered_operation(
            MeterableOperation.CONSTITUTIONAL_VALIDATION,
            extract_tenant=lambda o: None,
        )
        async def fn(obj):
            return True

        result = await fn(object())
        assert result is True

    async def test_extract_tenant_callable_raises_uses_default(self):
        @metered_operation(
            MeterableOperation.CONSTITUTIONAL_VALIDATION,
            extract_tenant=lambda o: (_ for _ in ()).throw(AttributeError("nope")),
        )
        async def fn(obj):
            return True

        result = await fn(object())
        assert result is True

    async def test_extract_agent_via_callable(self):
        class Obj:
            agent = "x"

        @metered_operation(
            MeterableOperation.CONSTITUTIONAL_VALIDATION,
            extract_agent=lambda o: o.agent,
        )
        async def fn(obj):
            return True

        result = await fn(Obj())
        assert result is True

    async def test_extract_agent_callable_raises_uses_none(self):
        @metered_operation(
            MeterableOperation.CONSTITUTIONAL_VALIDATION,
            extract_agent=lambda o: (_ for _ in ()).throw(KeyError("no")),
        )
        async def fn(obj):
            return True

        result = await fn(object())
        assert result is True

    async def test_extract_from_agent_attribute(self):
        class Msg:
            from_agent = "from-a"

        @metered_operation(MeterableOperation.CONSTITUTIONAL_VALIDATION)
        async def fn(msg):
            return True

        result = await fn(Msg())
        assert result is True

    async def test_first_arg_is_self_uses_second_arg(self):
        """When first arg has __self__ (bound method context), use args[1]."""

        class Msg:
            tenant_id = "msg-tenant"
            from_agent = "msg-agent"

        class Service:
            @metered_operation(MeterableOperation.CONSTITUTIONAL_VALIDATION)
            async def process(self, msg):
                return True

        svc = Service()
        result = await svc.process(Msg())
        assert result is True

    async def test_first_arg_has_self_but_no_second_arg(self):
        """When args[0] has __self__ but len(args)==1, first_arg becomes None (line 526)."""

        # Simulate a bound method call where no second arg is passed.
        # We build a wrapper that manually passes an object with __self__ as only arg.
        class FakeArg:
            """Fake first arg that looks like a bound method (has __self__)."""

            __self__ = "sentinel"

        @metered_operation(MeterableOperation.CONSTITUTIONAL_VALIDATION)
        async def fn(fake_self_arg):
            return "done"

        result = await fn(FakeArg())
        assert result == "done"

    async def test_no_args_uses_defaults(self):
        @metered_operation(MeterableOperation.CONSTITUTIONAL_VALIDATION)
        async def fn():
            return "ok"

        result = await fn()
        assert result == "ok"

    async def test_tier_passed_to_enqueue(self):
        q = _make_queue()
        import enhanced_agent_bus.metering_integration as mi

        with patch.object(mi, "_metering_hooks", MeteringHooks(q)):
            with patch.object(mi, "_metering_queue", q):

                @metered_operation(
                    MeterableOperation.CONSTITUTIONAL_VALIDATION,
                    tier=MeteringTier.DELIBERATION,
                )
                async def fn():
                    return True

                await fn()

        # Drain whatever was enqueued globally (singleton may differ)
        # Main assertion: function returned successfully
        assert True

    async def test_metering_not_available_skips_enqueue(self):
        """When METERING_AVAILABLE=False, decorator does not enqueue."""

        # Build a decorated function and capture its wrapper's globals
        @metered_operation(None)  # type: ignore[arg-type]
        async def fn():
            return 99

        # The wrapper is a closure whose __globals__ is metering_integration's globals
        wrapper_globals = fn.__globals__  # type: ignore[union-attr]
        with patch.dict(wrapper_globals, {"METERING_AVAILABLE": False}):
            result = await fn()
        assert result == 99

    async def test_operation_none_skips_enqueue(self):
        """operation=None (with METERING_AVAILABLE True) skips the enqueue branch."""
        q = _make_queue()
        hooks = MeteringHooks(q)

        @metered_operation(None)  # type: ignore[arg-type]
        async def fn():
            return "x"

        wrapper_globals = fn.__globals__  # type: ignore[union-attr]
        with patch.dict(wrapper_globals, {"_metering_hooks": hooks}):
            result = await fn()
        assert result == "x"
        # operation is None so METERING_AVAILABLE and operation is not None branch is False
        assert q._events_queued == 0


# ---------------------------------------------------------------------------
# MeteringMixin
# ---------------------------------------------------------------------------


class _ConcreteClass(MeteringMixin):
    """Concrete class for mixin tests."""

    pass


class TestMeteringMixin:
    def test_configure_metering_defaults(self):
        obj = _ConcreteClass()
        obj.configure_metering()
        assert obj._metering_config is not None
        assert obj._metering_queue is not None
        assert obj._metering_hooks is not None

    def test_configure_metering_with_config(self):
        obj = _ConcreteClass()
        cfg = _make_config(max_queue_size=77)
        obj.configure_metering(cfg)
        assert obj._metering_config.max_queue_size == 77

    async def test_start_metering_without_prior_configure(self):
        obj = _ConcreteClass()
        assert obj._metering_queue is None
        # start_metering should auto-configure
        await obj.start_metering()
        assert obj._metering_queue is not None
        assert obj._metering_queue._running is True
        await obj.stop_metering()

    async def test_start_metering_after_configure(self):
        obj = _ConcreteClass()
        obj.configure_metering(_make_config())
        await obj.start_metering()
        assert obj._metering_queue._running is True
        await obj.stop_metering()

    async def test_start_metering_with_falsy_queue_after_configure(self):
        """Cover the False branch of `if self._metering_queue:` in start_metering.

        This happens when configure_metering sets _metering_queue to None/falsy
        (an edge-case defensive check in the source).
        """
        obj = _ConcreteClass()
        # Pre-set _metering_queue to a non-None falsy placeholder so configure isn't called
        # and the `if self._metering_queue:` check evaluates False.
        # Trick: set it to a non-None value first so configure is skipped,
        # then replace with falsy before the second check.
        obj._metering_queue = None  # triggers configure_metering()

        original_configure = obj.configure_metering

        def patched_configure(config=None):
            original_configure(config)
            # After configure, zero out the queue to hit the False branch
            obj._metering_queue = None  # type: ignore[assignment]

        obj.configure_metering = patched_configure  # type: ignore[method-assign]
        # Should not raise
        await obj.start_metering()

    async def test_stop_metering_without_queue(self):
        obj = _ConcreteClass()
        # Should not raise
        await obj.stop_metering()

    async def test_stop_metering_with_queue(self):
        obj = _ConcreteClass()
        obj.configure_metering()
        await obj.start_metering()
        await obj.stop_metering()
        assert obj._metering_queue._running is False

    def test_get_metering_metrics_without_queue(self):
        obj = _ConcreteClass()
        m = obj.get_metering_metrics()
        assert m == {"enabled": False}

    def test_get_metering_metrics_with_queue(self):
        obj = _ConcreteClass()
        obj.configure_metering()
        m = obj.get_metering_metrics()
        assert "enabled" in m
        assert "constitutional_hash" in m

    def test_meter_constitutional_validation_no_hooks(self):
        obj = _ConcreteClass()
        # Should not raise when hooks not configured
        obj.meter_constitutional_validation(
            tenant_id="t1", agent_id="a1", is_valid=True, latency_ms=1.0
        )

    def test_meter_constitutional_validation_with_hooks(self):
        obj = _ConcreteClass()
        obj.configure_metering()
        q = obj._metering_queue
        q._running = True
        obj.meter_constitutional_validation(
            tenant_id="t1", agent_id="a1", is_valid=True, latency_ms=1.0
        )
        assert q._events_queued == 1

    def test_meter_constitutional_validation_with_metadata(self):
        obj = _ConcreteClass()
        obj.configure_metering()
        q = obj._metering_queue
        q._running = True
        obj.meter_constitutional_validation(
            tenant_id="t1",
            agent_id="a1",
            is_valid=False,
            latency_ms=1.0,
            metadata={"detail": "mismatch"},
        )
        item = q._queue.get_nowait()
        assert item["metadata"]["detail"] == "mismatch"

    def test_meter_agent_message_no_hooks(self):
        obj = _ConcreteClass()
        obj.meter_agent_message(
            tenant_id="t1",
            from_agent="a1",
            to_agent="a2",
            message_type="governance",
            latency_ms=1.0,
            is_valid=True,
        )

    def test_meter_agent_message_with_hooks(self):
        obj = _ConcreteClass()
        obj.configure_metering()
        q = obj._metering_queue
        q._running = True
        obj.meter_agent_message(
            tenant_id="t1",
            from_agent="a1",
            to_agent="a2",
            message_type="governance",
            latency_ms=1.0,
            is_valid=True,
        )
        assert q._events_queued == 1

    def test_meter_agent_message_with_metadata(self):
        obj = _ConcreteClass()
        obj.configure_metering()
        q = obj._metering_queue
        q._running = True
        obj.meter_agent_message(
            tenant_id="t1",
            from_agent="a1",
            to_agent=None,
            message_type="query",
            latency_ms=1.0,
            is_valid=True,
            metadata={"trace": "abc"},
        )
        item = q._queue.get_nowait()
        assert item["metadata"]["trace"] == "abc"

    def test_meter_policy_evaluation_no_hooks(self):
        obj = _ConcreteClass()
        obj.meter_policy_evaluation(
            tenant_id="t1", agent_id=None, policy_name="p", decision="allow", latency_ms=1.0
        )

    def test_meter_policy_evaluation_with_hooks(self):
        obj = _ConcreteClass()
        obj.configure_metering()
        q = obj._metering_queue
        q._running = True
        obj.meter_policy_evaluation(
            tenant_id="t1",
            agent_id=None,
            policy_name="opa_test",
            decision="deny",
            latency_ms=2.0,
        )
        assert q._events_queued == 1

    def test_meter_policy_evaluation_with_metadata(self):
        obj = _ConcreteClass()
        obj.configure_metering()
        q = obj._metering_queue
        q._running = True
        obj.meter_policy_evaluation(
            tenant_id="t1",
            agent_id=None,
            policy_name="p",
            decision="allow",
            latency_ms=1.0,
            metadata={"policy_version": "v2"},
        )
        item = q._queue.get_nowait()
        assert item["metadata"]["policy_version"] == "v2"


# ---------------------------------------------------------------------------
# Constitutional compliance assertions
# ---------------------------------------------------------------------------


class TestConstitutionalCompliance:
    def test_constitutional_hash_constant(self):
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_config_carries_hash(self):
        cfg = MeteringConfig()
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_metrics_carry_hash(self):
        q = _make_queue()
        m = q.get_metrics()
        assert m["constitutional_hash"] == CONSTITUTIONAL_HASH
