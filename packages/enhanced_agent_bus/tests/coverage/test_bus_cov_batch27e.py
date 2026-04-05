"""
Coverage tests for batch27e: cost/batch, streaming, bus/batch,
invariant_guard, api/routes/batch, builder.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. llm_adapters/cost/batch.py  (BatchOptimizer)
# ---------------------------------------------------------------------------

try:
    from enhanced_agent_bus.llm_adapters.capability_matrix import (
        CapabilityDimension,
        CapabilityRequirement,
    )
    from enhanced_agent_bus.llm_adapters.cost.batch import BatchOptimizer
    from enhanced_agent_bus.llm_adapters.cost.enums import (
        QualityLevel,
        UrgencyLevel,
    )
    from enhanced_agent_bus.llm_adapters.cost.models import (
        BatchRequest as CostBatchRequest,
    )
    from enhanced_agent_bus.llm_adapters.cost.models import (
        BatchResult as CostBatchResult,
    )

    HAS_COST_BATCH = True
except ImportError:
    HAS_COST_BATCH = False


def _make_cost_batch_request(
    request_id: str,
    tenant_id: str = "t1",
    urgency: Any = None,
    quality: Any = None,
    estimated_tokens: int = 100,
) -> CostBatchRequest:
    if urgency is None:
        urgency = UrgencyLevel.LOW
    if quality is None:
        quality = QualityLevel.STANDARD
    return CostBatchRequest(
        request_id=request_id,
        tenant_id=tenant_id,
        content="hello",
        requirements=[CapabilityRequirement(dimension=CapabilityDimension.CONTEXT_LENGTH)],
        urgency=urgency,
        quality=quality,
        max_wait_time=None,
        estimated_tokens=estimated_tokens,
    )


@pytest.mark.skipif(not HAS_COST_BATCH, reason="cost batch imports unavailable")
class TestBatchOptimizer:
    """Tests for llm_adapters/cost/batch.BatchOptimizer."""

    async def test_add_high_urgency_returns_none(self):
        opt = BatchOptimizer()
        req = _make_cost_batch_request("r1", urgency=UrgencyLevel.HIGH)
        result = await opt.add_request(req)
        assert result is None

    async def test_add_critical_urgency_returns_none(self):
        opt = BatchOptimizer()
        req = _make_cost_batch_request("r1", urgency=UrgencyLevel.CRITICAL)
        result = await opt.add_request(req)
        assert result is None

    async def test_add_low_urgency_queues_request(self):
        opt = BatchOptimizer()
        req = _make_cost_batch_request("r1", urgency=UrgencyLevel.LOW)
        result = await opt.add_request(req)
        assert result is None
        assert opt.get_pending_count() == 1

    async def test_batch_triggers_at_max_size(self):
        opt = BatchOptimizer(max_batch_size=3, min_batch_size=1)
        for i in range(2):
            await opt.add_request(_make_cost_batch_request(f"r{i}", urgency=UrgencyLevel.LOW))
        # Third request triggers batch
        result = await opt.add_request(_make_cost_batch_request("r2", urgency=UrgencyLevel.LOW))
        assert result is not None
        assert result.startswith("batch-")
        assert opt.get_pending_count() == 0

    async def test_get_result_after_batch_execution(self):
        opt = BatchOptimizer(max_batch_size=2, min_batch_size=1)
        await opt.add_request(
            _make_cost_batch_request("r0", urgency=UrgencyLevel.LOW, estimated_tokens=500)
        )
        batch_id = await opt.add_request(
            _make_cost_batch_request("r1", urgency=UrgencyLevel.LOW, estimated_tokens=500)
        )
        assert batch_id is not None
        result = opt.get_result(batch_id)
        assert result is not None
        assert len(result.requests) == 2
        assert result.total_cost > 0
        assert result.savings_percentage > 0

    async def test_get_result_missing(self):
        opt = BatchOptimizer()
        assert opt.get_result("nonexistent") is None

    async def test_flush_batches_respects_min_size(self):
        opt = BatchOptimizer(min_batch_size=5, max_batch_size=100)
        # Add only 2 requests -- below min
        for i in range(2):
            await opt.add_request(_make_cost_batch_request(f"r{i}", urgency=UrgencyLevel.LOW))
        flushed = await opt.flush_batches()
        assert flushed == []
        assert opt.get_pending_count() == 2

    async def test_flush_batches_executes_when_enough(self):
        opt = BatchOptimizer(min_batch_size=2, max_batch_size=100)
        for i in range(3):
            await opt.add_request(_make_cost_batch_request(f"r{i}", urgency=UrgencyLevel.LOW))
        flushed = await opt.flush_batches()
        assert len(flushed) == 1
        assert opt.get_pending_count() == 0

    async def test_max_wait_time_triggers_batch(self):
        """When oldest request exceeds max_wait_time and min_batch_size met."""
        opt = BatchOptimizer(
            min_batch_size=2,
            max_batch_size=100,
            max_wait_time=timedelta(seconds=0),  # immediate
        )
        await opt.add_request(_make_cost_batch_request("r0", urgency=UrgencyLevel.LOW))
        # Second request should trigger via wait-time path
        batch_id = await opt.add_request(_make_cost_batch_request("r1", urgency=UrgencyLevel.LOW))
        assert batch_id is not None

    async def test_execute_batch_empty_requests(self):
        """_execute_batch with no matching pending requests."""
        opt = BatchOptimizer()
        opt._batches["key"] = ["nonexistent"]
        batch_id = await opt._execute_batch("key")
        assert batch_id.startswith("batch-")

    async def test_batch_key_grouping(self):
        opt = BatchOptimizer()
        r1 = _make_cost_batch_request("r1", tenant_id="t1", urgency=UrgencyLevel.LOW)
        r2 = _make_cost_batch_request("r2", tenant_id="t2", urgency=UrgencyLevel.LOW)
        key1 = opt._get_batch_key(r1)
        key2 = opt._get_batch_key(r2)
        assert key1 != key2  # different tenants produce different keys


# ---------------------------------------------------------------------------
# 2. context_memory/optimizer/streaming.py  (StreamingProcessor)
# ---------------------------------------------------------------------------

try:
    from enhanced_agent_bus.context_memory.optimizer.streaming import (
        NUMPY_AVAILABLE,
        StreamingProcessor,
    )

    HAS_STREAMING = True
except ImportError:
    HAS_STREAMING = False


@pytest.mark.skipif(not HAS_STREAMING, reason="streaming imports unavailable")
class TestStreamingProcessor:
    """Tests for context_memory/optimizer/streaming.StreamingProcessor."""

    async def test_init_default(self):
        sp = StreamingProcessor()
        assert sp.buffer_size == 8192
        assert sp.overlap_ratio == 0.1

    async def test_init_invalid_hash_raises(self):
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            StreamingProcessor(constitutional_hash="bad-hash")

    async def test_stream_process_non_numpy_sync_fn(self):
        sp = StreamingProcessor()
        data = [1, 2, 3, 4]

        def processor(x: object) -> object:
            return x

        result = await sp.stream_process(data, processor)
        assert result.chunks_streamed == 1
        assert result.overlap_tokens == 0
        assert result.total_tokens == 4
        assert result.constitutional_validated is True

    async def test_stream_process_non_numpy_async_fn(self):
        sp = StreamingProcessor()
        data = [10, 20]

        async def processor(x: object) -> object:
            return x

        result = await sp.stream_process(data, processor)
        assert result.chunks_streamed == 1
        assert result.output_embeddings == [10, 20]

    async def test_stream_process_no_len(self):
        """Non-numpy object without __len__."""
        sp = StreamingProcessor()
        obj = 42  # int has no __len__

        def processor(x: object) -> object:
            return x

        result = await sp.stream_process(obj, processor)
        assert result.total_tokens == 0

    async def test_get_metrics(self):
        sp = StreamingProcessor()
        metrics = sp.get_metrics()
        assert metrics["streams_processed"] == 0
        assert metrics["total_tokens"] == 0
        assert "buffer_size" in metrics

    async def test_metrics_update_after_processing(self):
        sp = StreamingProcessor()
        await sp.stream_process([1, 2, 3], lambda x: x)
        metrics = sp.get_metrics()
        assert metrics["streams_processed"] == 1
        assert metrics["total_tokens"] == 3

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="numpy not installed")
    async def test_stream_process_numpy_2d(self):
        import numpy as np

        sp = StreamingProcessor(buffer_size=4, overlap_ratio=0.25)
        # 2D array: (seq_len=10, dim=3)
        embeddings = np.ones((10, 3))

        def processor(x: object) -> object:
            return x

        result = await sp.stream_process(embeddings, processor)
        assert result.chunks_streamed >= 1
        assert result.total_tokens == 10
        assert result.memory_peak_mb >= 0

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="numpy not installed")
    async def test_stream_process_numpy_3d(self):
        import numpy as np

        sp = StreamingProcessor(buffer_size=4, overlap_ratio=0.25)
        # 3D array: (batch=2, seq_len=10, dim=3)
        embeddings = np.ones((2, 10, 3))

        def processor(x: object) -> object:
            return x

        result = await sp.stream_process(embeddings, processor)
        assert result.chunks_streamed >= 1
        assert result.total_tokens == 10

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="numpy not installed")
    async def test_stream_process_numpy_async_fn(self):
        import numpy as np

        sp = StreamingProcessor(buffer_size=3, overlap_ratio=0.1)
        embeddings = np.ones((6, 2))

        async def processor(x: object) -> object:
            return x

        result = await sp.stream_process(embeddings, processor)
        assert result.chunks_streamed >= 1

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="numpy not installed")
    async def test_stream_process_numpy_small_input(self):
        """Input smaller than buffer_size -- single chunk, no overlap."""
        import numpy as np

        sp = StreamingProcessor(buffer_size=100, overlap_ratio=0.1)
        embeddings = np.ones((5, 3))
        result = await sp.stream_process(embeddings, lambda x: x)
        assert result.chunks_streamed == 1
        assert result.overlap_tokens == 0


# ---------------------------------------------------------------------------
# 3. bus/batch.py  (BatchProcessor)
# ---------------------------------------------------------------------------

try:
    from enhanced_agent_bus.bus.batch import BatchProcessor

    HAS_BUS_BATCH = True
except ImportError:
    HAS_BUS_BATCH = False


def _make_bus_batch_processor(**overrides: Any) -> BatchProcessor:
    defaults: dict[str, Any] = {
        "processor": MagicMock(),
        "validator": MagicMock(),
        "enable_maci": False,
        "maci_registry": None,
        "maci_enforcer": None,
        "maci_strict_mode": False,
        "metering_manager": MagicMock(is_enabled=False),
        "metrics": {"messages_sent": 0, "messages_failed": 0, "sent": 0, "failed": 0},
    }
    defaults.update(overrides)
    return BatchProcessor(**defaults)


@pytest.mark.skipif(not HAS_BUS_BATCH, reason="bus/batch imports unavailable")
class TestBusBatchProcessor:
    """Tests for bus/batch.BatchProcessor."""

    async def test_tenant_mismatch_returns_error_response(self):
        from enhanced_agent_bus.batch_models import (
            BatchRequest,
            BatchRequestItem,
        )

        bp = _make_bus_batch_processor()
        items = [
            BatchRequestItem(
                content={"action": "read"},
                from_agent="a1",
                tenant_id="tenant-other",
            ),
        ]
        req = BatchRequest(
            items=items,
            tenant_id="tenant-main",
        )
        response = await bp.process_batch(req)
        assert response.errors
        assert any("Tenant isolation" in e for e in response.errors)
        assert response.stats.failed_items == len(items)

    async def test_successful_batch_processing(self):
        from enhanced_agent_bus.batch_models import (
            BatchRequest,
            BatchRequestItem,
            BatchResponse,
            BatchResponseStats,
        )

        mock_batch_proc = MagicMock()
        mock_response = BatchResponse(
            batch_id="test-batch",
            items=[],
            stats=BatchResponseStats(
                total_items=1,
                successful_items=1,
                failed_items=0,
                skipped=0,
                processing_time_ms=1.0,
                p50_latency_ms=0.5,
                p95_latency_ms=0.8,
                p99_latency_ms=1.0,
            ),
        )
        mock_batch_proc.process_batch = AsyncMock(return_value=mock_response)

        bp = _make_bus_batch_processor()
        items = [
            BatchRequestItem(
                content={"action": "read"},
                from_agent="a1",
                tenant_id="tenant-1",
            ),
        ]
        req = BatchRequest(items=items, tenant_id="tenant-1")

        with patch(
            "enhanced_agent_bus.batch_processor.BatchMessageProcessor",
            return_value=mock_batch_proc,
        ):
            response = await bp.process_batch(req)
        assert response.stats.successful_items == 1

    async def test_metering_records_when_enabled(self):
        from enhanced_agent_bus.batch_models import (
            BatchRequest,
            BatchRequestItem,
            BatchResponse,
            BatchResponseStats,
        )

        mock_response = BatchResponse(
            batch_id="b1",
            items=[],
            stats=BatchResponseStats(
                total_items=1,
                successful_items=1,
                failed_items=0,
                skipped=0,
                processing_time_ms=1.0,
                p50_latency_ms=0.5,
                p95_latency_ms=0.8,
                p99_latency_ms=1.0,
            ),
        )
        mock_batch_proc = MagicMock()
        mock_batch_proc.process_batch = AsyncMock(return_value=mock_response)

        hooks = MagicMock()
        hooks.on_batch_processed = MagicMock()
        metering = MagicMock(is_enabled=True, hooks=hooks)
        bp = _make_bus_batch_processor(metering_manager=metering)

        items = [
            BatchRequestItem(
                content={"action": "read"},
                from_agent="a1",
                tenant_id="t1",
            ),
        ]
        req = BatchRequest(items=items, tenant_id="t1")

        with patch(
            "enhanced_agent_bus.batch_processor.BatchMessageProcessor",
            return_value=mock_batch_proc,
        ):
            await bp.process_batch(req)

        hooks.on_batch_processed.assert_called_once()

    async def test_metering_fallback_no_on_batch_processed(self):
        """When hooks lack on_batch_processed, uses record_agent_message fallback."""
        from enhanced_agent_bus.batch_models import (
            BatchRequest,
            BatchRequestItem,
            BatchResponse,
            BatchResponseItem,
            BatchResponseStats,
        )

        resp_item = BatchResponseItem(
            request_id="req-1",
            status="success",
            valid=True,
            processing_time_ms=0.5,
        )
        mock_response = BatchResponse(
            batch_id="b1",
            items=[resp_item],
            stats=BatchResponseStats(
                total_items=1,
                successful_items=1,
                failed_items=0,
                skipped=0,
                processing_time_ms=1.0,
                p50_latency_ms=0.5,
                p95_latency_ms=0.8,
                p99_latency_ms=1.0,
            ),
        )
        mock_batch_proc = MagicMock()
        mock_batch_proc.process_batch = AsyncMock(return_value=mock_response)

        hooks = MagicMock(spec=[])  # no on_batch_processed
        metering = MagicMock(is_enabled=True, hooks=hooks)
        metering.record_agent_message = MagicMock()
        bp = _make_bus_batch_processor(metering_manager=metering)

        items = [
            BatchRequestItem(
                content={"action": "read"},
                from_agent="a1",
                tenant_id="t1",
                request_id="req-1",
            ),
        ]
        req = BatchRequest(items=items, tenant_id="t1")

        with patch(
            "enhanced_agent_bus.batch_processor.BatchMessageProcessor",
            return_value=mock_batch_proc,
        ):
            await bp.process_batch(req)

        metering.record_agent_message.assert_called_once()

    async def test_metering_error_is_swallowed(self):
        """Metering errors should not propagate."""
        from enhanced_agent_bus.batch_models import (
            BatchRequest,
            BatchRequestItem,
            BatchResponse,
            BatchResponseStats,
        )

        mock_response = BatchResponse(
            batch_id="b1",
            items=[],
            stats=BatchResponseStats(
                total_items=1,
                successful_items=1,
                failed_items=0,
                skipped=0,
                processing_time_ms=1.0,
                p50_latency_ms=0.5,
                p95_latency_ms=0.8,
                p99_latency_ms=1.0,
            ),
        )
        mock_batch_proc = MagicMock()
        mock_batch_proc.process_batch = AsyncMock(return_value=mock_response)

        hooks = MagicMock()
        hooks.on_batch_processed = MagicMock(side_effect=RuntimeError("boom"))
        metering = MagicMock(is_enabled=True, hooks=hooks)
        bp = _make_bus_batch_processor(metering_manager=metering)

        items = [
            BatchRequestItem(
                content={"action": "read"},
                from_agent="a1",
                tenant_id="t1",
            ),
        ]
        req = BatchRequest(items=items, tenant_id="t1")

        with patch(
            "enhanced_agent_bus.batch_processor.BatchMessageProcessor",
            return_value=mock_batch_proc,
        ):
            response = await bp.process_batch(req)
        assert response is not None

    async def test_metering_disabled_skips_recording(self):
        from enhanced_agent_bus.batch_models import (
            BatchRequest,
            BatchRequestItem,
            BatchResponse,
            BatchResponseStats,
        )

        mock_response = BatchResponse(
            batch_id="b1",
            items=[],
            stats=BatchResponseStats(
                total_items=1,
                successful_items=1,
                failed_items=0,
                skipped=0,
                processing_time_ms=1.0,
                p50_latency_ms=0.5,
                p95_latency_ms=0.8,
                p99_latency_ms=1.0,
            ),
        )
        mock_batch_proc = MagicMock()
        mock_batch_proc.process_batch = AsyncMock(return_value=mock_response)

        metering = MagicMock(is_enabled=False)
        bp = _make_bus_batch_processor(metering_manager=metering)

        items = [
            BatchRequestItem(
                content={"action": "read"},
                from_agent="a1",
                tenant_id="t1",
            ),
        ]
        req = BatchRequest(items=items, tenant_id="t1")

        with patch(
            "enhanced_agent_bus.batch_processor.BatchMessageProcessor",
            return_value=mock_batch_proc,
        ):
            await bp.process_batch(req)
        # hooks should not be accessed
        assert not hasattr(metering, "_mock_children") or "hooks" not in str(metering.method_calls)

    async def test_record_batch_metering_no_hooks(self):
        """_record_batch_metering early-returns when hooks is None."""
        metering = MagicMock(is_enabled=True, hooks=None)
        bp = _make_bus_batch_processor(metering_manager=metering)
        # Should not raise
        bp._record_batch_metering(MagicMock(), MagicMock(), 1.0)

    async def test_record_batch_metering_no_manager(self):
        bp = _make_bus_batch_processor(metering_manager=None)
        bp._record_batch_metering(MagicMock(), MagicMock(), 1.0)


# ---------------------------------------------------------------------------
# 4. constitutional/invariant_guard.py
# ---------------------------------------------------------------------------

try:
    from enhanced_agent_bus.constitutional.invariant_guard import (
        ConstitutionalInvariantViolation,
        InvariantClassifier,
        ProposalInvariantValidator,
        RuntimeMutationGuard,
    )
    from enhanced_agent_bus.constitutional.invariants import (
        ChangeClassification,
        InvariantDefinition,
        InvariantManifest,
        InvariantScope,
    )

    HAS_INVARIANT = True
except ImportError:
    HAS_INVARIANT = False


def _make_manifest(
    invariants: list[InvariantDefinition] | None = None,
) -> InvariantManifest:
    if invariants is None:
        invariants = [
            InvariantDefinition(
                invariant_id="INV-T1",
                name="Test Hard",
                scope=InvariantScope.HARD,
                protected_paths=["maci", "maci/enforcer.py"],
            ),
            InvariantDefinition(
                invariant_id="INV-T2",
                name="Test Soft",
                scope=InvariantScope.SOFT,
                protected_paths=["config"],
            ),
        ]
    return InvariantManifest(
        constitutional_hash="608508a9bd224290",
        invariants=invariants,
    )


@pytest.mark.skipif(not HAS_INVARIANT, reason="invariant_guard imports unavailable")
class TestInvariantClassifier:
    def test_empty_manifest_blocks_all(self):
        manifest = InvariantManifest(constitutional_hash="608508a9bd224290", invariants=[])
        classifier = InvariantClassifier(manifest)
        result = classifier.classify_change(["anything"])
        assert result.blocked is True
        assert "Empty invariant manifest" in (result.reason or "")

    def test_no_match_returns_clean(self):
        classifier = InvariantClassifier(_make_manifest())
        result = classifier.classify_change(["unrelated/path"])
        assert result.touches_invariants is False
        assert result.blocked is False

    def test_hard_invariant_blocks_and_requires_refoundation(self):
        classifier = InvariantClassifier(_make_manifest())
        result = classifier.classify_change(["maci"])
        assert result.touches_invariants is True
        assert result.blocked is True
        assert result.requires_refoundation is True

    def test_soft_invariant_allows(self):
        classifier = InvariantClassifier(_make_manifest())
        result = classifier.classify_change(["config.some_setting"])
        assert result.touches_invariants is True
        assert result.blocked is False
        assert result.requires_refoundation is False

    def test_dot_prefix_match(self):
        classifier = InvariantClassifier(_make_manifest())
        result = classifier.classify_change(["maci.role_assignment"])
        assert result.touches_invariants is True

    def test_slash_prefix_match(self):
        classifier = InvariantClassifier(_make_manifest())
        result = classifier.classify_change(["maci/enforcer.py"])
        assert result.touches_invariants is True

    def test_path_matches_exact(self):
        assert InvariantClassifier._path_matches("maci", "maci") is True

    def test_path_matches_dot(self):
        assert InvariantClassifier._path_matches("maci.sub", "maci") is True

    def test_path_matches_slash(self):
        assert InvariantClassifier._path_matches("maci/file.py", "maci") is True

    def test_path_no_match(self):
        assert InvariantClassifier._path_matches("other", "maci") is False

    def test_classification_error_fails_closed(self):
        classifier = InvariantClassifier(_make_manifest())
        # Force an error in _do_classify
        with patch.object(classifier, "_do_classify", side_effect=RuntimeError("boom")):
            result = classifier.classify_change(["anything"])
        assert result.blocked is True
        assert "Classification error" in (result.reason or "")


@pytest.mark.skipif(not HAS_INVARIANT, reason="invariant_guard imports unavailable")
class TestProposalInvariantValidator:
    async def test_clean_proposal_passes(self):
        validator = ProposalInvariantValidator(_make_manifest())
        result = await validator.validate_proposal({}, ["unrelated"])
        assert result.touches_invariants is False
        assert result.blocked is False

    async def test_hard_invariant_raises(self):
        validator = ProposalInvariantValidator(_make_manifest())
        with pytest.raises(ConstitutionalInvariantViolation):
            await validator.validate_proposal({}, ["maci"])

    async def test_soft_invariant_returns_classification(self):
        validator = ProposalInvariantValidator(_make_manifest())
        result = await validator.validate_proposal({}, ["config.x"])
        assert result.touches_invariants is True
        assert result.blocked is False

    async def test_invariant_hash_property(self):
        manifest = _make_manifest()
        validator = ProposalInvariantValidator(manifest)
        assert validator.invariant_hash == manifest.invariant_hash

    async def test_validation_error_raises_violation(self):
        validator = ProposalInvariantValidator(_make_manifest())
        with patch.object(
            validator._classifier,
            "classify_change",
            side_effect=RuntimeError("bad"),
        ):
            with pytest.raises(ConstitutionalInvariantViolation):
                await validator.validate_proposal({}, ["x"])


@pytest.mark.skipif(not HAS_INVARIANT, reason="invariant_guard imports unavailable")
class TestRuntimeMutationGuard:
    def test_allowed_mutation(self):
        guard = RuntimeMutationGuard(_make_manifest())
        # unrelated path -- should not raise
        guard.validate_mutation("unrelated/path", "write", "admin")

    def test_hard_invariant_blocked(self):
        guard = RuntimeMutationGuard(_make_manifest())
        with pytest.raises(ConstitutionalInvariantViolation):
            guard.validate_mutation("maci", "write", "admin")

    def test_recommendation_only_role_blocked_on_soft(self):
        guard = RuntimeMutationGuard(_make_manifest())
        with pytest.raises(ConstitutionalInvariantViolation):
            guard.validate_mutation("config.x", "write", "sdpc")

    def test_recommendation_only_role_adaptive_governance(self):
        guard = RuntimeMutationGuard(_make_manifest())
        with pytest.raises(ConstitutionalInvariantViolation):
            guard.validate_mutation("config.x", "write", "adaptive_governance")

    def test_non_recommendation_role_allowed_on_soft(self):
        guard = RuntimeMutationGuard(_make_manifest())
        # "admin" is not recommendation-only
        guard.validate_mutation("config.x", "write", "admin")

    def test_violation_exception_message(self):
        cls = ChangeClassification(
            touches_invariants=True,
            touched_invariant_ids=["INV-1"],
            blocked=True,
            reason="test reason",
        )
        exc = ConstitutionalInvariantViolation(cls, "custom msg")
        assert str(exc) == "custom msg"
        assert exc.classification is cls

    def test_violation_exception_default_message(self):
        cls = ChangeClassification(
            touches_invariants=True,
            touched_invariant_ids=[],
            blocked=True,
            reason="some reason",
        )
        exc = ConstitutionalInvariantViolation(cls)
        assert str(exc) == "some reason"

    def test_violation_exception_no_reason(self):
        cls = ChangeClassification(
            touches_invariants=True,
            touched_invariant_ids=[],
            blocked=True,
            reason=None,
        )
        exc = ConstitutionalInvariantViolation(cls)
        assert str(exc) == "Invariant violation"


# ---------------------------------------------------------------------------
# 5. api/routes/batch.py  (route helpers)
# ---------------------------------------------------------------------------

try:
    from enhanced_agent_bus.api.routes.batch import (
        _check_batch_rate_limit_or_raise,
        _rate_limit_http_exception,
        _resolve_client_id,
        _validate_batch_request_safety,
    )

    HAS_API_BATCH = True
except ImportError:
    HAS_API_BATCH = False


@pytest.mark.skipif(not HAS_API_BATCH, reason="api/routes/batch imports unavailable")
class TestApiBatchRouteHelpers:
    def test_rate_limit_http_exception(self):
        from fastapi import HTTPException

        err = MagicMock(spec=Exception)
        with patch("enhanced_agent_bus.api.routes.batch.logger"):
            exc = _rate_limit_http_exception(err)
        assert isinstance(exc, HTTPException)
        assert exc.status_code == 429

    def test_resolve_client_id_no_rate_limiting(self):
        with patch("enhanced_agent_bus.api.routes.batch.RATE_LIMITING_AVAILABLE", False):
            result = _resolve_client_id(MagicMock())
            assert result == "default"

    def test_resolve_client_id_with_rate_limiting(self):
        mock_request = MagicMock()
        with (
            patch("enhanced_agent_bus.api.routes.batch.RATE_LIMITING_AVAILABLE", True),
            patch(
                "enhanced_agent_bus.api.routes.batch.get_remote_address",
                return_value="1.2.3.4",
            ),
        ):
            result = _resolve_client_id(mock_request)
            assert result == "1.2.3.4"

    async def test_check_batch_rate_limit_or_raise_ok(self):
        with patch(
            "enhanced_agent_bus.api.routes.batch.check_batch_rate_limit",
            new_callable=AsyncMock,
        ):
            await _check_batch_rate_limit_or_raise("client1", 10)

    async def test_check_batch_rate_limit_or_raise_exceeded(self):
        from fastapi import HTTPException

        # Get the actual RateLimitExceeded class used in routes/batch.py
        from enhanced_agent_bus.api.routes import batch as _batch_mod

        RLE = _batch_mod.RateLimitExceeded
        # Create a proper instance -- it may come from slowapi or fallback stubs
        try:
            from slowapi.wrappers import Limit

            limit_obj = MagicMock(spec=Limit)
            limit_obj.error_message = "rate limited"
            mock_err = RLE(limit_obj)
        except ImportError:
            mock_err = RLE(agent_id="x", message="limit", retry_after_ms=100)

        with (
            patch(
                "enhanced_agent_bus.api.routes.batch.check_batch_rate_limit",
                new_callable=AsyncMock,
                side_effect=mock_err,
            ),
            patch("enhanced_agent_bus.api.routes.batch.logger"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await _check_batch_rate_limit_or_raise("client1", 10)
            assert exc_info.value.status_code == 429

    def test_validate_batch_request_safety_size_error(self):
        from fastapi import HTTPException

        mock_req = MagicMock()
        mock_req.tenant_id = ""
        with (
            patch(
                "enhanced_agent_bus.api.routes.batch.validate_item_sizes",
                return_value="too big",
            ),
            patch("enhanced_agent_bus.api.routes.batch.logger"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _validate_batch_request_safety(mock_req, "t1")
            assert exc_info.value.status_code == 413

    def test_validate_batch_request_safety_tenant_mismatch(self):
        from fastapi import HTTPException

        mock_req = MagicMock()
        mock_req.tenant_id = "different-tenant"
        with patch(
            "enhanced_agent_bus.api.routes.batch.validate_item_sizes",
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc_info:
                _validate_batch_request_safety(mock_req, "expected-tenant")
            assert exc_info.value.status_code == 400

    def test_validate_batch_request_safety_consistency_fail(self):
        from fastapi import HTTPException

        mock_req = MagicMock()
        mock_req.tenant_id = ""
        mock_req.validate_tenant_consistency = MagicMock(return_value="error")
        with (
            patch(
                "enhanced_agent_bus.api.routes.batch.validate_item_sizes",
                return_value=None,
            ),
            patch("enhanced_agent_bus.api.routes.batch.logger"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _validate_batch_request_safety(mock_req, "t1")
            assert exc_info.value.status_code == 400

    def test_validate_batch_request_safety_ok(self):
        mock_req = MagicMock()
        mock_req.tenant_id = ""
        mock_req.validate_tenant_consistency = None
        with patch(
            "enhanced_agent_bus.api.routes.batch.validate_item_sizes",
            return_value=None,
        ):
            _validate_batch_request_safety(mock_req, "t1")
        assert mock_req.tenant_id == "t1"


# ---------------------------------------------------------------------------
# 6. builder.py  (build_sdpc_verifiers, build_pqc_service)
# ---------------------------------------------------------------------------

try:
    from enhanced_agent_bus.builder import (
        SDPCVerifiers,
        build_pqc_service,
        build_sdpc_verifiers,
    )

    HAS_BUILDER = True
except ImportError:
    HAS_BUILDER = False


@pytest.mark.skipif(not HAS_BUILDER, reason="builder imports unavailable")
class TestBuilder:
    def setup_method(self):
        """Reset global caches before each test."""
        import enhanced_agent_bus.builder as _b

        _b._cached_sdpc = None
        _b._cached_pqc = None

    def test_build_sdpc_verifiers_import_error_fallback(self):
        config = MagicMock()
        with patch(
            "enhanced_agent_bus.builder.build_sdpc_verifiers",
            wraps=build_sdpc_verifiers,
        ):
            # Force ImportError on SDPC imports by patching builtins
            import builtins

            real_import = builtins.__import__

            def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
                if "sdpc" in name or "intent_classifier" in name:
                    raise ImportError(f"no module {name}")
                return real_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                result = build_sdpc_verifiers(config)

            assert isinstance(result, SDPCVerifiers)
            assert result.intent_classifier is not None

    def test_build_sdpc_verifiers_caching(self):
        import enhanced_agent_bus.builder as _b

        config = MagicMock()
        # Force fallback (simpler)
        import builtins

        real_import = builtins.__import__

        def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if "sdpc" in name or "intent_classifier" in name:
                raise ImportError(f"no module {name}")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            r1 = build_sdpc_verifiers(config)
            r2 = build_sdpc_verifiers(config)
        assert r1 is r2

    def test_build_pqc_service_disabled(self):
        config = MagicMock()
        config.enable_pqc = False
        result = build_pqc_service(config)
        assert result is None

    def test_build_pqc_service_import_error(self):
        config = MagicMock()
        config.enable_pqc = True
        with patch("importlib.import_module", side_effect=ImportError("no pqc")):
            result = build_pqc_service(config)
        assert result is None

    def test_build_pqc_service_runtime_error(self):
        config = MagicMock()
        config.enable_pqc = True
        with patch("importlib.import_module", side_effect=RuntimeError("fail")):
            result = build_pqc_service(config)
        assert result is None

    def test_build_pqc_service_caching(self):
        import enhanced_agent_bus.builder as _b

        config = MagicMock()
        config.enable_pqc = True
        sentinel = MagicMock()
        _b._cached_pqc = sentinel
        result = build_pqc_service(config)
        assert result is sentinel

    def test_build_pqc_service_success(self):
        config = MagicMock()
        config.enable_pqc = True
        config.pqc_mode = "hybrid"
        config.pqc_verification_mode = "strict"
        config.pqc_migration_phase = "phase_1"
        config.pqc_key_algorithm = "kyber768"

        mock_module = MagicMock()
        mock_config_cls = MagicMock()
        mock_service_cls = MagicMock()
        mock_module.PQCConfig = mock_config_cls
        mock_module.PQCCryptoService = mock_service_cls

        with patch("importlib.import_module", return_value=mock_module):
            result = build_pqc_service(config)
        mock_config_cls.assert_called_once()
        mock_service_cls.assert_called_once()

    def test_build_pqc_service_classical_only_mode(self):
        import enhanced_agent_bus.builder as _b

        _b._cached_pqc = None
        config = MagicMock()
        config.enable_pqc = True
        config.pqc_mode = "classical_only"
        config.pqc_verification_mode = "classical_only"
        config.pqc_migration_phase = None  # will default to phase_0

        mock_module = MagicMock()
        with patch("importlib.import_module", return_value=mock_module):
            build_pqc_service(config)
        call_kwargs = mock_module.PQCConfig.call_args
        assert call_kwargs is not None

    def test_build_pqc_service_unknown_mode_defaults(self):
        import enhanced_agent_bus.builder as _b

        _b._cached_pqc = None
        config = MagicMock()
        config.enable_pqc = True
        config.pqc_mode = "unknown_mode"
        config.pqc_verification_mode = "unknown_verify"
        config.pqc_migration_phase = "not_a_phase"

        mock_module = MagicMock()
        with patch("importlib.import_module", return_value=mock_module):
            build_pqc_service(config)
        call_kwargs = mock_module.PQCConfig.call_args[1]
        assert call_kwargs["pqc_mode"] == "classical_only"
        assert call_kwargs["verification_mode"] == "strict"
        assert call_kwargs["migration_phase"] == "phase_0"


# ---------------------------------------------------------------------------
# Additional edge-case tests for completeness
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_COST_BATCH, reason="cost batch imports unavailable")
class TestBatchOptimizerEdgeCases:
    async def test_batch_urgency(self):
        """BATCH urgency should be queued."""
        opt = BatchOptimizer()
        req = _make_cost_batch_request("r1", urgency=UrgencyLevel.BATCH)
        result = await opt.add_request(req)
        assert result is None
        assert opt.get_pending_count() == 1

    async def test_multiple_batch_keys(self):
        opt = BatchOptimizer(max_batch_size=2, min_batch_size=1)
        r1 = _make_cost_batch_request("r1", tenant_id="t1")
        r2 = _make_cost_batch_request("r2", tenant_id="t2")
        r3 = _make_cost_batch_request("r3", tenant_id="t1")
        await opt.add_request(r1)
        await opt.add_request(r2)
        # This should trigger batch for t1
        batch_id = await opt.add_request(r3)
        assert batch_id is not None
        assert opt.get_pending_count() == 1  # r2 still pending
