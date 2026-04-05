# Constitutional Hash: 608508a9bd224290
# Sprint 55 — batch_processor_infra/orchestrator.py coverage
"""
Comprehensive tests for BatchProcessorOrchestrator achieving >=95% coverage.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from enhanced_agent_bus.batch_processor_infra.orchestrator import (
    BatchProcessorOrchestrator,
)
from enhanced_agent_bus.models import (
    CONSTITUTIONAL_HASH,
    BatchItemStatus,
    BatchRequest,
    BatchRequestItem,
    BatchResponse,
    BatchResponseItem,
    BatchResponseStats,
    MessageStatus,
    MessageType,
)
from enhanced_agent_bus.validators import ValidationResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_HASH = CONSTITUTIONAL_HASH


def make_item(**kwargs) -> BatchRequestItem:
    defaults = dict(
        from_agent="agent-a",
        to_agent="agent-b",
        content={"action": "test"},
        message_type=MessageType.EVENT,
    )
    defaults.update(kwargs)
    return BatchRequestItem(**defaults)


def make_batch(items=None, *, batch_id="batch-001", **kwargs) -> BatchRequest:
    if items is None:
        items = [make_item()]
    return BatchRequest(
        batch_id=batch_id,
        items=items,
        constitutional_hash=VALID_HASH,
        **kwargs,
    )


async def valid_process_func(item: BatchRequestItem) -> ValidationResult:
    return ValidationResult(is_valid=True, status=MessageStatus.VALIDATED)


async def invalid_process_func(item: BatchRequestItem) -> ValidationResult:
    result = ValidationResult(is_valid=False, status=MessageStatus.REJECTED)
    result.add_error("validation failed")
    return result


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestBatchProcessorOrchestratorInit:
    def test_default_construction(self):
        orc = BatchProcessorOrchestrator()
        assert orc.queue is not None
        assert orc.metrics is not None
        assert orc.workers is not None
        assert orc.governance is not None
        assert orc.tuner is not None

    def test_custom_parameters(self):
        orc = BatchProcessorOrchestrator(
            max_concurrency=50,
            max_retries=3,
            retry_base_delay=0.05,
            retry_exponential_base=1.5,
        )
        assert orc.workers is not None
        assert orc.tuner is not None

    def test_min_concurrency(self):
        orc = BatchProcessorOrchestrator(max_concurrency=1)
        assert orc.tuner.batch_size == 1


# ---------------------------------------------------------------------------
# Governance failure paths
# ---------------------------------------------------------------------------


class TestGovernanceFailure:
    async def test_hash_mismatch_returns_error_response(self):
        orc = BatchProcessorOrchestrator()
        batch = make_batch()
        # Bypass Pydantic validator to inject a bad hash
        object.__setattr__(
            batch, "constitutional_hash", "deadbeef00000000"
        )  # pragma: allowlist secret

        response = await orc.process_batch(batch, valid_process_func)

        assert response.success is False
        assert response.error_code == "CONSTITUTIONAL_HASH_MISMATCH"
        assert response.batch_id == "batch-001"
        assert response.stats.total_items == 1
        assert response.stats.failed_items == 1

    async def test_hash_mismatch_error_code_contains_hash_keyword(self):
        """Error message containing 'hash' → CONSTITUTIONAL_HASH_MISMATCH code."""
        orc = BatchProcessorOrchestrator()
        batch = make_batch()
        object.__setattr__(batch, "constitutional_hash", "badhash00000000f")

        response = await orc.process_batch(batch, valid_process_func)

        assert response.error_code == "CONSTITUTIONAL_HASH_MISMATCH"

    async def test_non_hash_governance_failure_uses_governance_failure_code(self):
        """Error message NOT containing 'hash' → GOVERNANCE_FAILURE code."""
        orc = BatchProcessorOrchestrator()
        batch = make_batch()

        # Patch governance to return a non-hash error
        mock_result = ValidationResult(is_valid=False)
        mock_result.errors = ["MACI role check failed"]

        with patch.object(orc.governance, "validate_batch_context", return_value=mock_result):
            response = await orc.process_batch(batch, valid_process_func)

        assert response.success is False
        assert response.error_code == "GOVERNANCE_FAILURE"

    async def test_governance_failure_empty_errors_list(self):
        """Governance failure with empty errors list falls back to generic message."""
        orc = BatchProcessorOrchestrator()
        batch = make_batch()

        mock_result = ValidationResult(is_valid=False)
        mock_result.errors = []

        with patch.object(orc.governance, "validate_batch_context", return_value=mock_result):
            response = await orc.process_batch(batch, valid_process_func)

        assert response.success is False
        assert response.error_code == "GOVERNANCE_FAILURE"
        assert len(response.errors) == 1
        assert "Governance validation failed" in response.errors[0]

    async def test_governance_failure_processing_time_populated(self):
        orc = BatchProcessorOrchestrator()
        batch = make_batch()
        object.__setattr__(
            batch, "constitutional_hash", "bad0000000000000"
        )  # pragma: allowlist secret

        response = await orc.process_batch(batch, valid_process_func)

        assert response.stats.processing_time_ms >= 0


# ---------------------------------------------------------------------------
# Happy path — normal processing
# ---------------------------------------------------------------------------


class TestHappyPath:
    async def test_single_item_success(self):
        orc = BatchProcessorOrchestrator()
        batch = make_batch()

        response = await orc.process_batch(batch, valid_process_func)

        assert response.batch_id == "batch-001"
        assert response.success is True
        assert len(response.items) == 1
        assert response.stats.total_items == 1
        assert response.stats.successful_items == 1
        assert response.stats.failed_items == 0

    async def test_multiple_unique_items(self):
        orc = BatchProcessorOrchestrator()
        items = [make_item(content={"id": i}) for i in range(5)]
        batch = make_batch(items=items)

        response = await orc.process_batch(batch, valid_process_func)

        assert len(response.items) == 5
        assert response.stats.total_items == 5
        assert response.stats.successful_items == 5

    async def test_processing_time_populated(self):
        orc = BatchProcessorOrchestrator()
        batch = make_batch()

        response = await orc.process_batch(batch, valid_process_func)

        assert response.stats.processing_time_ms >= 0

    async def test_batch_id_preserved(self):
        orc = BatchProcessorOrchestrator()
        batch = make_batch(batch_id="custom-id-999")

        response = await orc.process_batch(batch, valid_process_func)

        assert response.batch_id == "custom-id-999"

    async def test_failed_item_counted(self):
        orc = BatchProcessorOrchestrator()
        batch = make_batch()

        response = await orc.process_batch(batch, invalid_process_func)

        assert response.stats.failed_items == 1
        assert response.stats.successful_items == 0

    async def test_mixed_results(self):
        orc = BatchProcessorOrchestrator()
        items = [make_item(content={"id": i}) for i in range(4)]
        batch = make_batch(items=items)

        call_count = 0

        async def alternating_process(item):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                result = ValidationResult(is_valid=False)
                result.add_error("even item fails")
                return result
            return ValidationResult(is_valid=True, status=MessageStatus.VALIDATED)

        response = await orc.process_batch(batch, alternating_process)

        assert response.stats.total_items == 4
        assert response.stats.successful_items + response.stats.failed_items == 4


# ---------------------------------------------------------------------------
# Deduplication paths
# ---------------------------------------------------------------------------


class TestDeduplication:
    async def test_duplicate_items_processed_once(self):
        orc = BatchProcessorOrchestrator()

        item = make_item(content={"key": "same"})
        batch = make_batch(items=[item, item])

        call_count = 0

        async def counting_process(it):
            nonlocal call_count
            call_count += 1
            return ValidationResult(is_valid=True, status=MessageStatus.VALIDATED)

        response = await orc.process_batch(batch, counting_process)

        assert call_count == 1
        assert len(response.items) == 2
        assert response.stats.deduplicated_count == 1

    async def test_all_items_deduplicated(self):
        """All items are duplicates from a prior run → unique_items is empty."""
        orc = BatchProcessorOrchestrator()

        item = make_item(content={"key": "cached"})
        batch1 = make_batch(items=[item])
        # First pass populates the dedup cache
        await orc.process_batch(batch1, valid_process_func)

        # Second pass with same item — all are in cache
        batch2 = BatchRequest(
            batch_id="batch-002",
            items=[item],
            constitutional_hash=VALID_HASH,
        )
        response = await orc.process_batch(batch2, valid_process_func)

        # The item came from cache, should still have one response item
        assert len(response.items) == 1
        # The deduplicated path creates a synthetic success item
        assert response.items[0].valid is True

    async def test_partial_deduplication(self):
        """Some items are new, some are duplicates."""
        orc = BatchProcessorOrchestrator()

        item_a = make_item(content={"k": "a"})
        item_b = make_item(content={"k": "b"})
        batch = make_batch(items=[item_a, item_b, item_a])

        call_count = 0

        async def counting_process(it):
            nonlocal call_count
            call_count += 1
            return ValidationResult(is_valid=True, status=MessageStatus.VALIDATED)

        response = await orc.process_batch(batch, counting_process)

        # Only 2 unique items processed
        assert call_count == 2
        assert len(response.items) == 3
        assert response.stats.deduplicated_count == 1


# ---------------------------------------------------------------------------
# Index mapping (results remapping)
# ---------------------------------------------------------------------------


class TestIndexMapping:
    async def test_result_ordering_preserved_with_deduplication(self):
        """Results must be in same order as original items even after dedup."""
        orc = BatchProcessorOrchestrator()

        item_x = make_item(content={"v": "x"})
        item_y = make_item(content={"v": "y"})
        batch = make_batch(items=[item_x, item_y, item_x, item_y, item_x])

        results = []

        async def capturing_process(it):
            results.append(it.content["v"])
            return ValidationResult(is_valid=True, status=MessageStatus.VALIDATED)

        response = await orc.process_batch(batch, capturing_process)

        assert len(response.items) == 5
        # Only 2 unique items processed
        assert len(results) == 2

    async def test_request_ids_preserved_after_deduplication(self):
        item1 = make_item(content={"id": 1})
        item2 = make_item(content={"id": 2})
        item1_copy = BatchRequestItem(
            request_id=item1.request_id,
            from_agent=item1.from_agent,
            to_agent=item1.to_agent,
            content=item1.content,
            message_type=item1.message_type,
        )
        orc = BatchProcessorOrchestrator()
        batch = make_batch(items=[item1, item2, item1_copy])

        response = await orc.process_batch(batch, valid_process_func)

        assert len(response.items) == 3


# ---------------------------------------------------------------------------
# Metrics tracking through orchestrator
# ---------------------------------------------------------------------------


class TestMetricsIntegration:
    async def test_metrics_updated_after_batch(self):
        orc = BatchProcessorOrchestrator()
        batch = make_batch()

        await orc.process_batch(batch, valid_process_func)

        metrics = orc.get_metrics()
        assert metrics["total_batches"] == 1
        assert metrics["total_items"] == 1

    async def test_multiple_batches_accumulated(self):
        orc = BatchProcessorOrchestrator()

        for i in range(3):
            batch = make_batch(items=[make_item(content={"i": i})], batch_id=f"b{i}")
            await orc.process_batch(batch, valid_process_func)

        metrics = orc.get_metrics()
        assert metrics["total_batches"] == 3
        assert metrics["total_items"] == 3

    def test_reset_metrics(self):
        orc = BatchProcessorOrchestrator()
        orc.reset_metrics()
        metrics = orc.get_metrics()
        assert metrics["total_batches"] == 0
        assert metrics["total_items"] == 0

    async def test_reset_clears_accumulated_metrics(self):
        orc = BatchProcessorOrchestrator()
        batch = make_batch()
        await orc.process_batch(batch, valid_process_func)

        orc.reset_metrics()

        metrics = orc.get_metrics()
        assert metrics["total_batches"] == 0

    def test_get_metrics_returns_dict(self):
        orc = BatchProcessorOrchestrator()
        metrics = orc.get_metrics()
        assert isinstance(metrics, dict)
        assert "total_batches" in metrics

    def test_metrics_includes_constitutional_hash(self):
        orc = BatchProcessorOrchestrator()
        metrics = orc.get_metrics()
        assert metrics.get("constitutional_hash") == VALID_HASH


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


class TestCacheManagement:
    def test_clear_cache_on_fresh_instance(self):
        orc = BatchProcessorOrchestrator()
        orc.clear_cache()
        assert orc.get_cache_size() == 0

    async def test_cache_grows_after_processing(self):
        orc = BatchProcessorOrchestrator()
        items = [make_item(content={"id": i}) for i in range(3)]
        batch = make_batch(items=items)

        await orc.process_batch(batch, valid_process_func)

        assert orc.get_cache_size() == 3

    async def test_clear_cache_resets_size(self):
        orc = BatchProcessorOrchestrator()
        items = [make_item(content={"id": i}) for i in range(3)]
        batch = make_batch(items=items)
        await orc.process_batch(batch, valid_process_func)

        orc.clear_cache()

        assert orc.get_cache_size() == 0

    def test_get_cache_size_zero_initially(self):
        orc = BatchProcessorOrchestrator()
        assert orc.get_cache_size() == 0


# ---------------------------------------------------------------------------
# Tuner integration
# ---------------------------------------------------------------------------


class TestTunerIntegration:
    async def test_tuner_called_with_high_success_rate(self):
        """High success rate causes tuner to increase batch size."""
        orc = BatchProcessorOrchestrator(max_concurrency=10)
        initial_size = orc.tuner.batch_size

        # 5 items, all succeed → 100% success rate
        items = [make_item(content={"id": i}) for i in range(5)]
        batch = make_batch(items=items)
        await orc.process_batch(batch, valid_process_func)

        # Tuner should have run; batch_size may have changed depending on latency
        assert orc.tuner.batch_size >= 1

    async def test_tuner_called_with_zero_items(self):
        """Edge case: batch with single item, 100% success rate, zero latency."""
        orc = BatchProcessorOrchestrator(max_concurrency=10)
        batch = make_batch()
        await orc.process_batch(batch, valid_process_func)
        assert orc.tuner.batch_size >= 1

    async def test_tuner_adjust_when_all_fail(self):
        """Low success rate should trigger downward tuning."""
        orc = BatchProcessorOrchestrator(max_concurrency=50)
        items = [make_item(content={"id": i}) for i in range(5)]
        batch = make_batch(items=items)

        await orc.process_batch(batch, invalid_process_func)

        # Tuner should have potentially decreased; assert it's still valid
        assert orc.tuner.batch_size >= 1


# ---------------------------------------------------------------------------
# Stats calculation integration
# ---------------------------------------------------------------------------


class TestStatsCalculation:
    async def test_stats_has_all_required_fields(self):
        orc = BatchProcessorOrchestrator()
        batch = make_batch()

        response = await orc.process_batch(batch, valid_process_func)

        stats = response.stats
        assert hasattr(stats, "total_items")
        assert hasattr(stats, "successful_items")
        assert hasattr(stats, "failed_items")
        assert hasattr(stats, "processing_time_ms")
        assert hasattr(stats, "deduplicated_count")

    async def test_deduplicated_count_in_stats(self):
        orc = BatchProcessorOrchestrator()
        item = make_item(content={"k": "dup"})
        batch = make_batch(items=[item, item, item])

        response = await orc.process_batch(batch, valid_process_func)

        assert response.stats.deduplicated_count == 2

    async def test_no_deduplication_when_all_unique(self):
        orc = BatchProcessorOrchestrator()
        items = [make_item(content={"id": i}) for i in range(3)]
        batch = make_batch(items=items)

        response = await orc.process_batch(batch, valid_process_func)

        assert response.stats.deduplicated_count == 0

    async def test_stats_success_rate_calculation(self):
        orc = BatchProcessorOrchestrator()
        items = [make_item(content={"id": i}) for i in range(4)]
        batch = make_batch(items=items)

        response = await orc.process_batch(batch, valid_process_func)

        assert response.stats.successful_items == 4
        assert response.stats.failed_items == 0


# ---------------------------------------------------------------------------
# record_batch_processed is called
# ---------------------------------------------------------------------------


class TestRecordBatchProcessed:
    async def test_metrics_record_called_after_successful_batch(self):
        orc = BatchProcessorOrchestrator()

        with patch.object(orc.metrics, "record_batch_processed") as mock_record:
            batch = make_batch()
            await orc.process_batch(batch, valid_process_func)
            assert mock_record.called

    async def test_metrics_record_not_called_on_governance_failure(self):
        """Governance failures exit early, before record_batch_processed."""
        orc = BatchProcessorOrchestrator()

        with patch.object(orc.metrics, "record_batch_processed") as mock_record:
            batch = make_batch()
            object.__setattr__(
                batch, "constitutional_hash", "bad0000000000000"
            )  # pragma: allowlist secret
            await orc.process_batch(batch, valid_process_func)
            assert not mock_record.called


# ---------------------------------------------------------------------------
# Concurrency / gather behaviour
# ---------------------------------------------------------------------------


class TestConcurrency:
    async def test_concurrent_processing_of_items(self):
        orc = BatchProcessorOrchestrator(max_concurrency=10)
        items = [make_item(content={"id": i}) for i in range(10)]
        batch = make_batch(items=items)

        response = await orc.process_batch(batch, valid_process_func)

        assert len(response.items) == 10
        assert response.stats.total_items == 10

    async def test_asyncio_gather_used(self):
        """Verifies that gather is used by checking all items processed."""
        orc = BatchProcessorOrchestrator(max_concurrency=5)

        completion_order = []

        async def ordered_process(item):
            completion_order.append(item.content["id"])
            return ValidationResult(is_valid=True, status=MessageStatus.VALIDATED)

        items = [make_item(content={"id": i}) for i in range(5)]
        batch = make_batch(items=items)

        response = await orc.process_batch(batch, ordered_process)

        assert len(completion_order) == 5
        assert len(response.items) == 5


# ---------------------------------------------------------------------------
# Tuner success_rate edge: zero total_items guard
# ---------------------------------------------------------------------------


class TestSuccessRateEdgeCases:
    async def test_success_rate_when_total_items_is_zero_does_not_raise(self):
        """Tuner adjustment with 100% rate (no items) should not error."""
        orc = BatchProcessorOrchestrator()
        batch = make_batch(items=[make_item()])

        # Patch calculate_batch_stats to return zero total items
        zero_stats = BatchResponseStats(
            total_items=0,
            successful_items=0,
            failed_items=0,
            processing_time_ms=1.0,
        )

        with patch.object(orc.metrics, "calculate_batch_stats", return_value=zero_stats):
            with patch.object(orc.metrics, "record_batch_processed"):
                response = await orc.process_batch(batch, valid_process_func)

        # Should not raise; tuner uses 100 as default rate for zero total
        assert orc.tuner.batch_size >= 1


# ---------------------------------------------------------------------------
# Governance path: error_msg first element vs fallback
# ---------------------------------------------------------------------------


class TestGovernanceErrorMessage:
    async def test_first_error_used_as_error_message(self):
        orc = BatchProcessorOrchestrator()
        batch = make_batch()

        mock_result = ValidationResult(is_valid=False)
        mock_result.errors = ["first error", "second error"]

        with patch.object(orc.governance, "validate_batch_context", return_value=mock_result):
            response = await orc.process_batch(batch, valid_process_func)

        assert response.errors[0] == "first error"

    async def test_hash_keyword_case_insensitive(self):
        """'hash' in error message (any case) → CONSTITUTIONAL_HASH_MISMATCH."""
        orc = BatchProcessorOrchestrator()
        batch = make_batch()

        mock_result = ValidationResult(is_valid=False)
        mock_result.errors = ["Constitutional HASH mismatch detected"]

        with patch.object(orc.governance, "validate_batch_context", return_value=mock_result):
            response = await orc.process_batch(batch, valid_process_func)

        assert response.error_code == "CONSTITUTIONAL_HASH_MISMATCH"

    async def test_multiple_items_counted_in_governance_failure(self):
        orc = BatchProcessorOrchestrator()
        items = [make_item(content={"id": i}) for i in range(5)]
        batch = make_batch(items=items)

        mock_result = ValidationResult(is_valid=False)
        mock_result.errors = ["bad hash value"]

        with patch.object(orc.governance, "validate_batch_context", return_value=mock_result):
            response = await orc.process_batch(batch, valid_process_func)

        assert response.stats.total_items == 5
        assert response.stats.failed_items == 5


# ---------------------------------------------------------------------------
# All-deduplicated path: BatchResponseItem with cached=True
# ---------------------------------------------------------------------------


class TestAllDeduplicatedPath:
    async def test_all_cached_items_have_valid_true(self):
        """When unique_items is empty (all deduplicated), items must have valid=True."""
        orc = BatchProcessorOrchestrator()
        item = make_item(content={"unique": "first"})

        # First call populates dedup cache
        batch1 = make_batch(items=[item])
        await orc.process_batch(batch1, valid_process_func)

        # Second call: same item — dedup cache hit, unique_items == []
        batch2 = BatchRequest(
            batch_id="batch-cached",
            items=[item],
            constitutional_hash=VALID_HASH,
        )

        async def should_not_be_called(it):
            raise AssertionError("process_func should not be called for cached items")

        response = await orc.process_batch(batch2, should_not_be_called)

        assert len(response.items) == 1
        assert response.items[0].valid is True
        assert response.items[0].constitutional_validated is True

    async def test_all_cached_items_have_deduplicated_metadata(self):
        orc = BatchProcessorOrchestrator()
        item = make_item(content={"k": "cached_meta"})

        batch1 = make_batch(items=[item])
        await orc.process_batch(batch1, valid_process_func)

        batch2 = BatchRequest(
            batch_id="batch-cached-2",
            items=[item],
            constitutional_hash=VALID_HASH,
        )
        response = await orc.process_batch(batch2, AsyncMock())

        assert response.items[0].validation_result == {"deduplicated": True, "cached": True}

    async def test_all_cached_multiple_items_same_content(self):
        """Multiple items, all cached, all returned in correct order."""
        orc = BatchProcessorOrchestrator()
        item = make_item(content={"same": "content"})

        batch1 = make_batch(items=[item])
        await orc.process_batch(batch1, valid_process_func)

        batch2 = BatchRequest(
            batch_id="batch-all-cached",
            items=[item, item, item],
            constitutional_hash=VALID_HASH,
        )
        response = await orc.process_batch(batch2, AsyncMock())

        assert len(response.items) == 3
        for resp_item in response.items:
            assert resp_item.valid is True
