# Constitutional Hash: 608508a9bd224290
# Sprint 54 — middlewares/batch/context.py coverage
"""
Comprehensive tests for BatchPipelineContext.

Targets ≥95% coverage of:
  src/core/enhanced_agent_bus/middlewares/batch/context.py
"""

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.batch_models import (
    BatchRequest,
    BatchRequestItem,
    BatchResponse,
    BatchResponseItem,
    BatchResponseStats,
)
from enhanced_agent_bus.middlewares.batch.context import BatchPipelineContext
from enhanced_agent_bus.models import AgentMessage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_request_item(request_id: str = "req-1", content: dict | None = None) -> BatchRequestItem:
    return BatchRequestItem(
        request_id=request_id,
        content=content or {"key": "value"},
        from_agent="agent-a",
    )


def make_response_item(request_id: str = "req-1", success: bool = True) -> BatchResponseItem:
    if success:
        return BatchResponseItem.create_success(
            request_id=request_id,
            valid=True,
            processing_time_ms=1.0,
        )
    return BatchResponseItem.create_error(
        request_id=request_id,
        error_code="ERR_001",
        error_message="something went wrong",
        processing_time_ms=0.5,
    )


def make_batch_request(n: int = 2) -> BatchRequest:
    items = [make_request_item(f"req-{i}", {"n": i}) for i in range(n)]
    return BatchRequest(items=items)


# ---------------------------------------------------------------------------
# Construction / defaults
# ---------------------------------------------------------------------------


class TestBatchPipelineContextDefaults:
    """Verify default field values."""

    def test_default_message_is_batch_sentinel(self) -> None:
        ctx = BatchPipelineContext()
        assert ctx.message.message_id == "batch"
        assert ctx.message.from_agent == "batch_processor"

    def test_batch_request_none_by_default(self) -> None:
        ctx = BatchPipelineContext()
        assert ctx.batch_request is None

    def test_batch_response_none_by_default(self) -> None:
        ctx = BatchPipelineContext()
        assert ctx.batch_response is None

    def test_lists_empty_by_default(self) -> None:
        ctx = BatchPipelineContext()
        assert ctx.batch_items == []
        assert ctx.processed_items == []
        assert ctx.failed_items == []
        assert ctx.warnings == []
        assert ctx.latency_history == []

    def test_numeric_defaults(self) -> None:
        ctx = BatchPipelineContext()
        assert ctx.batch_size == 0
        assert ctx.max_concurrency == 100
        assert ctx.batch_latency_ms == 0.0
        assert ctx.current_batch_size == 100
        assert ctx.target_p99_ms == 100.0
        assert ctx.deduplicated_count == 0

    def test_boolean_defaults(self) -> None:
        ctx = BatchPipelineContext()
        assert ctx.fail_fast is False
        assert ctx.deduplicate is True

    def test_seen_message_ids_empty_set(self) -> None:
        ctx = BatchPipelineContext()
        assert isinstance(ctx.seen_message_ids, set)
        assert len(ctx.seen_message_ids) == 0

    def test_metadata_empty_dict(self) -> None:
        ctx = BatchPipelineContext()
        assert ctx.metadata == {}

    def test_batch_tenant_id_none(self) -> None:
        ctx = BatchPipelineContext()
        assert ctx.batch_tenant_id is None


# ---------------------------------------------------------------------------
# Custom message
# ---------------------------------------------------------------------------


class TestBatchPipelineContextCustomMessage:
    """Verify that a custom AgentMessage overrides the default."""

    def test_custom_message(self) -> None:
        msg = AgentMessage(message_id="custom-id", from_agent="custom-agent", content={})
        ctx = BatchPipelineContext(message=msg)
        assert ctx.message.message_id == "custom-id"
        assert ctx.message.from_agent == "custom-agent"


# ---------------------------------------------------------------------------
# add_processed_item
# ---------------------------------------------------------------------------


class TestAddProcessedItem:
    def test_appends_item(self) -> None:
        ctx = BatchPipelineContext()
        item = make_response_item("req-1", success=True)
        ctx.add_processed_item(item)
        assert len(ctx.processed_items) == 1
        assert ctx.processed_items[0] is item

    def test_appends_multiple_items(self) -> None:
        ctx = BatchPipelineContext()
        for i in range(5):
            ctx.add_processed_item(make_response_item(f"req-{i}", success=True))
        assert len(ctx.processed_items) == 5

    def test_failed_item_not_in_processed(self) -> None:
        ctx = BatchPipelineContext()
        item = make_response_item("req-1", success=False)
        ctx.add_processed_item(item)
        # Still appended — the method does not filter by success
        assert len(ctx.processed_items) == 1


# ---------------------------------------------------------------------------
# add_failed_item
# ---------------------------------------------------------------------------


class TestAddFailedItem:
    def test_appends_tuple(self) -> None:
        ctx = BatchPipelineContext()
        req_item = make_request_item("req-1")
        ctx.add_failed_item(req_item, "timeout")
        assert len(ctx.failed_items) == 1
        stored_item, stored_error = ctx.failed_items[0]
        assert stored_item is req_item
        assert stored_error == "timeout"

    def test_appends_multiple_failures(self) -> None:
        ctx = BatchPipelineContext()
        for i in range(3):
            ctx.add_failed_item(make_request_item(f"req-{i}"), f"err-{i}")
        assert len(ctx.failed_items) == 3

    def test_error_message_stored_correctly(self) -> None:
        ctx = BatchPipelineContext()
        req_item = make_request_item()
        ctx.add_failed_item(req_item, "constitutional_violation")
        _, err = ctx.failed_items[0]
        assert err == "constitutional_violation"


# ---------------------------------------------------------------------------
# record_latency
# ---------------------------------------------------------------------------


class TestRecordLatency:
    def test_appends_latency(self) -> None:
        ctx = BatchPipelineContext()
        ctx.record_latency(10.0)
        assert ctx.latency_history == [10.0]

    def test_keeps_last_100(self) -> None:
        ctx = BatchPipelineContext()
        for i in range(110):
            ctx.record_latency(float(i))
        assert len(ctx.latency_history) == 100
        # The oldest 10 values (0..9) should have been dropped
        assert ctx.latency_history[0] == 10.0
        assert ctx.latency_history[-1] == 109.0

    def test_exactly_100_not_trimmed(self) -> None:
        ctx = BatchPipelineContext()
        for i in range(100):
            ctx.record_latency(float(i))
        assert len(ctx.latency_history) == 100

    def test_101_triggers_trim(self) -> None:
        ctx = BatchPipelineContext()
        for i in range(101):
            ctx.record_latency(float(i))
        assert len(ctx.latency_history) == 100
        assert ctx.latency_history[0] == 1.0


# ---------------------------------------------------------------------------
# get_p99_latency
# ---------------------------------------------------------------------------


class TestGetP99Latency:
    def test_empty_returns_zero(self) -> None:
        ctx = BatchPipelineContext()
        assert ctx.get_p99_latency() == 0.0

    def test_single_item(self) -> None:
        ctx = BatchPipelineContext()
        ctx.record_latency(42.0)
        assert ctx.get_p99_latency() == 42.0

    def test_p99_of_100_items(self) -> None:
        ctx = BatchPipelineContext()
        for i in range(1, 101):
            ctx.record_latency(float(i))
        # idx = int(100 * 0.99) = 99; sorted[99] = 100.0
        assert ctx.get_p99_latency() == 100.0

    def test_p99_clamps_to_last(self) -> None:
        """With 2 items idx=int(2*0.99)=1; sorted[min(1,1)]=max value."""
        ctx = BatchPipelineContext()
        ctx.record_latency(5.0)
        ctx.record_latency(10.0)
        assert ctx.get_p99_latency() == 10.0

    def test_p99_with_single_item_no_off_by_one(self) -> None:
        """With 1 item idx=int(1*0.99)=0; sorted[min(0,0)]=only value."""
        ctx = BatchPipelineContext()
        ctx.record_latency(7.5)
        assert ctx.get_p99_latency() == 7.5

    def test_p99_larger_list(self) -> None:
        ctx = BatchPipelineContext()
        for i in range(1, 11):  # 1..10
            ctx.record_latency(float(i))
        # idx = int(10*0.99)=9; sorted[9]=10.0
        assert ctx.get_p99_latency() == 10.0


# ---------------------------------------------------------------------------
# should_adjust_batch_size
# ---------------------------------------------------------------------------


class TestShouldAdjustBatchSize:
    def test_false_with_empty_history(self) -> None:
        ctx = BatchPipelineContext()
        assert ctx.should_adjust_batch_size() is False

    def test_false_with_nine_measurements(self) -> None:
        ctx = BatchPipelineContext()
        for _ in range(9):
            ctx.record_latency(1.0)
        assert ctx.should_adjust_batch_size() is False

    def test_true_with_ten_measurements(self) -> None:
        ctx = BatchPipelineContext()
        for _ in range(10):
            ctx.record_latency(1.0)
        assert ctx.should_adjust_batch_size() is True

    def test_true_with_more_than_ten(self) -> None:
        ctx = BatchPipelineContext()
        for _ in range(50):
            ctx.record_latency(1.0)
        assert ctx.should_adjust_batch_size() is True


# ---------------------------------------------------------------------------
# to_batch_response — cached branch
# ---------------------------------------------------------------------------


class TestToBatchResponseCached:
    def test_returns_existing_batch_response(self) -> None:
        ctx = BatchPipelineContext()
        existing = BatchResponse(
            batch_id="existing-batch",
            items=[],
            stats=BatchResponseStats(total_items=0),
        )
        ctx.batch_response = existing
        result = ctx.to_batch_response()
        assert result is existing


# ---------------------------------------------------------------------------
# to_batch_response — build branch
# ---------------------------------------------------------------------------


class TestToBatchResponseBuild:
    def _make_ctx_with_request(self, n_items: int = 2) -> BatchPipelineContext:
        ctx = BatchPipelineContext()
        ctx.batch_request = make_batch_request(n_items)
        ctx.batch_items = list(ctx.batch_request.items)
        ctx.batch_latency_ms = 12.5
        return ctx

    def test_all_successful_items(self) -> None:
        ctx = self._make_ctx_with_request(2)
        for item in ctx.batch_items:
            ctx.add_processed_item(make_response_item(item.request_id, success=True))
        response = ctx.to_batch_response()
        assert response.success is True
        assert response.stats.total_items == 2
        assert response.stats.successful_items == 2
        assert response.stats.failed_items == 0

    def test_mixed_success_and_failure(self) -> None:
        ctx = self._make_ctx_with_request(3)
        items = ctx.batch_items
        ctx.add_processed_item(make_response_item(items[0].request_id, success=True))
        ctx.add_processed_item(make_response_item(items[1].request_id, success=True))
        ctx.add_failed_item(items[2], "timeout")
        response = ctx.to_batch_response()
        assert response.success is False
        assert response.stats.failed_items == 1
        assert len(response.errors) == 1
        assert "timeout" in response.errors

    def test_all_failed_items(self) -> None:
        ctx = self._make_ctx_with_request(2)
        for item in ctx.batch_items:
            ctx.add_failed_item(item, "invalid")
        response = ctx.to_batch_response()
        assert response.success is False
        assert response.stats.successful_items == 0
        assert response.stats.failed_items == 2

    def test_skipped_items_counted(self) -> None:
        """Items in batch_items that are neither processed nor failed count as skipped."""
        ctx = self._make_ctx_with_request(3)
        # Only process 1 of 3
        ctx.add_processed_item(make_response_item(ctx.batch_items[0].request_id, success=True))
        response = ctx.to_batch_response()
        assert response.stats.skipped == 2

    def test_deduplicated_count_propagated(self) -> None:
        ctx = self._make_ctx_with_request(2)
        ctx.deduplicated_count = 5
        for item in ctx.batch_items:
            ctx.add_processed_item(make_response_item(item.request_id, success=True))
        response = ctx.to_batch_response()
        assert response.stats.deduplicated_count == 5

    def test_batch_latency_propagated(self) -> None:
        ctx = self._make_ctx_with_request(1)
        ctx.batch_latency_ms = 99.9
        ctx.add_processed_item(make_response_item(ctx.batch_items[0].request_id, success=True))
        response = ctx.to_batch_response()
        assert response.stats.processing_time_ms == 99.9

    def test_batch_id_from_request(self) -> None:
        ctx = self._make_ctx_with_request(1)
        bid = ctx.batch_request.batch_id
        ctx.add_processed_item(make_response_item(ctx.batch_items[0].request_id, success=True))
        response = ctx.to_batch_response()
        assert response.batch_id == bid

    def test_result_cached_after_build(self) -> None:
        """Second call returns the same object."""
        ctx = self._make_ctx_with_request(1)
        ctx.add_processed_item(make_response_item(ctx.batch_items[0].request_id, success=True))
        r1 = ctx.to_batch_response()
        r2 = ctx.to_batch_response()
        assert r1 is r2

    def test_no_batch_request_uses_unknown_id(self) -> None:
        """When batch_request is None, batch_id should be 'unknown'."""
        ctx = BatchPipelineContext()
        ctx.batch_items = [make_request_item("req-1")]
        ctx.add_processed_item(make_response_item("req-1", success=True))
        response = ctx.to_batch_response()
        assert response.batch_id == "unknown"

    def test_errors_list_contains_all_failure_messages(self) -> None:
        ctx = self._make_ctx_with_request(3)
        for i, item in enumerate(ctx.batch_items):
            ctx.add_failed_item(item, f"error-{i}")
        response = ctx.to_batch_response()
        assert response.errors == ["error-0", "error-1", "error-2"]

    def test_processed_items_passed_to_response(self) -> None:
        ctx = self._make_ctx_with_request(2)
        for item in ctx.batch_items:
            ctx.add_processed_item(make_response_item(item.request_id, success=True))
        response = ctx.to_batch_response()
        assert len(response.items) == 2


# ---------------------------------------------------------------------------
# to_batch_response — mixed success attribute
# ---------------------------------------------------------------------------


class TestToBatchResponseSuccessAttribute:
    """The success field is True iff failed == 0."""

    def test_zero_failures_means_success(self) -> None:
        ctx = BatchPipelineContext()
        ctx.batch_request = make_batch_request(1)
        ctx.batch_items = list(ctx.batch_request.items)
        ctx.add_processed_item(make_response_item(ctx.batch_items[0].request_id, success=True))
        assert ctx.to_batch_response().success is True

    def test_one_failure_means_not_success(self) -> None:
        ctx = BatchPipelineContext()
        ctx.batch_request = make_batch_request(1)
        ctx.batch_items = list(ctx.batch_request.items)
        ctx.add_failed_item(ctx.batch_items[0], "err")
        assert ctx.to_batch_response().success is False


# ---------------------------------------------------------------------------
# Inheritance from PipelineContext
# ---------------------------------------------------------------------------


class TestPipelineContextInheritance:
    """BatchPipelineContext must honour the PipelineContext API."""

    def test_add_middleware(self) -> None:
        ctx = BatchPipelineContext()
        ctx.add_middleware("TestMiddleware")
        assert "TestMiddleware" in ctx.middleware_path

    def test_finalize_does_not_raise(self) -> None:
        ctx = BatchPipelineContext()
        ctx.finalize()  # should not raise

    def test_constitutional_hash_default(self) -> None:
        ctx = BatchPipelineContext()
        assert ctx.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# Edge-cases / boundary conditions
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_record_latency_zero(self) -> None:
        ctx = BatchPipelineContext()
        ctx.record_latency(0.0)
        assert ctx.latency_history == [0.0]

    def test_get_p99_latency_two_items(self) -> None:
        ctx = BatchPipelineContext()
        ctx.record_latency(1.0)
        ctx.record_latency(2.0)
        # idx = int(2 * 0.99) = 1; min(1, 1) = 1; sorted[1] = 2.0
        assert ctx.get_p99_latency() == 2.0

    def test_empty_batch_no_items(self) -> None:
        ctx = BatchPipelineContext()
        ctx.batch_request = make_batch_request(1)
        ctx.batch_items = []  # no items assigned — all skipped
        response = ctx.to_batch_response()
        assert response.stats.total_items == 0

    def test_seen_message_ids_can_be_populated(self) -> None:
        ctx = BatchPipelineContext()
        ctx.seen_message_ids.add("msg-abc")
        assert "msg-abc" in ctx.seen_message_ids

    def test_warnings_list_can_be_populated(self) -> None:
        ctx = BatchPipelineContext()
        ctx.warnings.append("low concurrency")
        assert ctx.warnings == ["low concurrency"]

    def test_metadata_can_be_populated(self) -> None:
        ctx = BatchPipelineContext()
        ctx.metadata["tenant"] = "acme"
        assert ctx.metadata["tenant"] == "acme"

    def test_latency_trim_exact_boundary(self) -> None:
        """100 items stay, 101st triggers trim."""
        ctx = BatchPipelineContext()
        for _i in range(100):
            ctx.record_latency(1.0)
        assert len(ctx.latency_history) == 100
        ctx.record_latency(2.0)
        assert len(ctx.latency_history) == 100
        assert ctx.latency_history[-1] == 2.0

    def test_failed_item_tuple_order(self) -> None:
        ctx = BatchPipelineContext()
        req = make_request_item("r1")
        ctx.add_failed_item(req, "boom")
        item_stored, error_stored = ctx.failed_items[0]
        assert item_stored is req
        assert error_stored == "boom"

    def test_processed_item_with_failure_status_success_is_false(self) -> None:
        """Even a failure-status response item can be added via add_processed_item."""
        ctx = BatchPipelineContext()
        failed_resp = make_response_item("req-1", success=False)
        ctx.add_processed_item(failed_resp)
        assert len(ctx.processed_items) == 1
        assert ctx.processed_items[0].success is False
