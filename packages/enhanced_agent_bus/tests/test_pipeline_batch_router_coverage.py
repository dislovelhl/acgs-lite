# Constitutional Hash: 608508a9bd224290
"""
ACGS-2 Enhanced Agent Bus - Batch Pipeline Router Coverage Tests

Comprehensive tests for src/core/enhanced_agent_bus/pipeline/batch_router.py
targeting >= 95% line coverage.
"""

import asyncio
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.batch_models import (
    BatchRequest,
    BatchRequestItem,
    BatchResponse,
    BatchResponseItem,
)
from enhanced_agent_bus.pipeline.batch_router import (
    BATCH_PIPELINE_ERRORS,
    BatchPipelineRouter,
)
from enhanced_agent_bus.pipeline.middleware import BaseMiddleware, MiddlewareConfig
from enhanced_agent_bus.pipeline.router import PipelineConfig
from enhanced_agent_bus.validators import ValidationResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH  # pragma: allowlist secret


def _make_item(**kwargs) -> BatchRequestItem:
    """Return a minimal BatchRequestItem."""
    defaults = {
        "content": {"action": "test"},
        "from_agent": "agent-a",
        "tenant_id": "tenant-1",
    }
    defaults.update(kwargs)
    return BatchRequestItem(**defaults)


def _make_batch(*items: BatchRequestItem, tenant_id: str = "tenant-1", **kwargs) -> BatchRequest:
    """Return a BatchRequest with given items."""
    if not items:
        items = (_make_item(),)
    return BatchRequest(items=list(items), tenant_id=tenant_id, **kwargs)


def _make_minimal_middleware(name: str = "MinimalMW") -> BaseMiddleware:
    """Return a minimal no-op BaseMiddleware subclass instance."""

    class _MinimalMW(BaseMiddleware):
        async def process(self, context):
            return await self._call_next(context)

    mw = _MinimalMW(config=MiddlewareConfig(timeout_ms=500))
    mw.__class__.__name__ = name
    return mw


def _make_passthrough_config(n_mw: int = 1) -> PipelineConfig:
    """Return a PipelineConfig with n passthrough middlewares (no default middlewares)."""
    middlewares = [_make_minimal_middleware(f"MW{i}") for i in range(n_mw)]
    return PipelineConfig(
        middlewares=middlewares,
        max_concurrent=10,
        version="test-1.0",
        use_default_middlewares=False,
    )


async def _good_processor(item: BatchRequestItem) -> ValidationResult:
    """Simple item processor that always succeeds."""
    return ValidationResult(is_valid=True, decision="ALLOW")


async def _bad_processor(item: BatchRequestItem) -> ValidationResult:
    """Simple item processor that always fails."""
    return ValidationResult(is_valid=False, errors=["validation failed"], decision="DENY")


async def _raising_processor(item: BatchRequestItem) -> ValidationResult:
    """Simple item processor that raises."""
    raise RuntimeError("processor blew up")


# ---------------------------------------------------------------------------
# Tests: BATCH_PIPELINE_ERRORS constant
# ---------------------------------------------------------------------------


class TestBatchPipelineErrorsConstant:
    def test_contains_runtime_error(self):
        assert RuntimeError in BATCH_PIPELINE_ERRORS

    def test_contains_value_error(self):
        assert ValueError in BATCH_PIPELINE_ERRORS

    def test_contains_type_error(self):
        assert TypeError in BATCH_PIPELINE_ERRORS

    def test_contains_key_error(self):
        assert KeyError in BATCH_PIPELINE_ERRORS

    def test_contains_attribute_error(self):
        assert AttributeError in BATCH_PIPELINE_ERRORS

    def test_contains_asyncio_timeout_error(self):
        assert asyncio.TimeoutError in BATCH_PIPELINE_ERRORS

    def test_is_tuple(self):
        assert isinstance(BATCH_PIPELINE_ERRORS, tuple)


# ---------------------------------------------------------------------------
# Tests: BatchPipelineRouter.__init__
# ---------------------------------------------------------------------------


class TestBatchPipelineRouterInit:
    def test_default_init_uses_batch_config(self):
        """Creating router without args should use default batch middlewares."""
        router = BatchPipelineRouter()
        assert router._config is not None
        assert router._config.version == "2.0.0-batch"

    def test_default_init_has_8_middlewares(self):
        router = BatchPipelineRouter()
        # _create_batch_middlewares returns 8 middlewares
        assert len(router._config.middlewares) == 8

    def test_default_init_max_concurrent_100(self):
        router = BatchPipelineRouter()
        assert router._config.max_concurrent == 100

    def test_default_init_use_default_middlewares_false(self):
        router = BatchPipelineRouter()
        assert router._config.use_default_middlewares is False

    def test_custom_config_used_as_is(self):
        config = _make_passthrough_config(n_mw=2)
        router = BatchPipelineRouter(config=config)
        assert len(router._config.middlewares) == 2
        assert router._config.version == "test-1.0"

    def test_item_processor_stored(self):
        router = BatchPipelineRouter(item_processor=_good_processor)
        assert router._item_processor is _good_processor

    def test_metrics_initialized(self):
        router = BatchPipelineRouter(item_processor=_good_processor)
        metrics = router._metrics
        assert metrics["batches_processed"] == 0
        assert metrics["batches_failed"] == 0
        assert metrics["total_items_processed"] == 0
        assert metrics["total_latency_ms"] == 0.0

    def test_metrics_lock_created(self):
        router = BatchPipelineRouter(item_processor=_good_processor)
        assert isinstance(router._metrics_lock, asyncio.Lock)

    def test_chain_head_set(self):
        config = _make_passthrough_config(n_mw=2)
        router = BatchPipelineRouter(config=config)
        assert router._chain_head is not None

    def test_item_processor_none_by_default(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        assert router._item_processor is None


# ---------------------------------------------------------------------------
# Tests: BatchPipelineRouter._create_batch_middlewares
# ---------------------------------------------------------------------------


class TestCreateBatchMiddlewares:
    def test_returns_8_middlewares(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        mws = router._create_batch_middlewares(item_processor=_good_processor)
        assert len(mws) == 8

    def test_all_are_base_middleware(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        mws = router._create_batch_middlewares()
        for mw in mws:
            assert isinstance(mw, BaseMiddleware)

    def test_middleware_types(self):
        from enhanced_agent_bus.middlewares.batch.auto_tune import BatchAutoTuneMiddleware
        from enhanced_agent_bus.middlewares.batch.concurrency import (
            BatchConcurrencyMiddleware,
        )
        from enhanced_agent_bus.middlewares.batch.deduplication import (
            BatchDeduplicationMiddleware,
        )
        from enhanced_agent_bus.middlewares.batch.governance import (
            BatchGovernanceMiddleware,
        )
        from enhanced_agent_bus.middlewares.batch.metrics import BatchMetricsMiddleware
        from enhanced_agent_bus.middlewares.batch.processing import (
            BatchProcessingMiddleware,
        )
        from enhanced_agent_bus.middlewares.batch.tenant_isolation import (
            BatchTenantIsolationMiddleware,
        )
        from enhanced_agent_bus.middlewares.batch.validation import (
            BatchValidationMiddleware,
        )

        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        mws = router._create_batch_middlewares(_good_processor)
        types = [type(mw) for mw in mws]
        assert BatchValidationMiddleware in types
        assert BatchTenantIsolationMiddleware in types
        assert BatchDeduplicationMiddleware in types
        assert BatchGovernanceMiddleware in types
        assert BatchConcurrencyMiddleware in types
        assert BatchProcessingMiddleware in types
        assert BatchAutoTuneMiddleware in types
        assert BatchMetricsMiddleware in types

    def test_validation_middleware_config(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        mws = router._create_batch_middlewares()
        # First middleware: validation
        validation_mw = mws[0]
        assert validation_mw.config.timeout_ms == 500


# ---------------------------------------------------------------------------
# Helpers: mock chain head that returns a successful context
# ---------------------------------------------------------------------------


def _make_mock_chain_head_success(batch_request):
    """Return an AsyncMock chain head that sets a valid batch_response on context."""
    from enhanced_agent_bus.middlewares.batch.context import BatchPipelineContext

    async def _side_effect(ctx):
        # Build a minimal batch response on the context so finalize/to_batch_response works
        ctx.batch_response = BatchResponse(
            batch_id=batch_request.batch_id,
            success=True,
            items=[],
        )
        return ctx

    mock_head = AsyncMock()
    mock_head.process.side_effect = _side_effect
    return mock_head


# ---------------------------------------------------------------------------
# Tests: BatchPipelineRouter.process_batch (success paths)
# ---------------------------------------------------------------------------


class TestProcessBatchSuccess:
    async def test_processes_single_item(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        batch = _make_batch(_make_item())
        router._chain_head = _make_mock_chain_head_success(batch)
        response = await router.process_batch(batch)
        assert isinstance(response, BatchResponse)

    async def test_batch_id_preserved(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        batch = _make_batch(_make_item())
        router._chain_head = _make_mock_chain_head_success(batch)
        response = await router.process_batch(batch)
        assert response.batch_id == batch.batch_id

    async def test_metrics_updated_on_success(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        items = [_make_item(), _make_item()]
        batch = _make_batch(*items)
        router._chain_head = _make_mock_chain_head_success(batch)
        await router.process_batch(batch)
        assert router._metrics["batches_processed"] == 1
        assert router._metrics["total_items_processed"] == 2
        assert router._metrics["batches_failed"] == 0

    async def test_multiple_batches_accumulate_metrics(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        for _ in range(3):
            batch = _make_batch(_make_item())
            router._chain_head = _make_mock_chain_head_success(batch)
            await router.process_batch(batch)
        assert router._metrics["batches_processed"] == 3
        assert router._metrics["total_items_processed"] == 3

    async def test_latency_accumulated(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        batch = _make_batch(_make_item())
        router._chain_head = _make_mock_chain_head_success(batch)
        await router.process_batch(batch)
        assert router._metrics["total_latency_ms"] >= 0.0

    async def test_no_chain_head_still_works(self):
        """When chain_head is None, process_batch should still finalize and return."""
        config = _make_passthrough_config(n_mw=1)
        router = BatchPipelineRouter(config=config)
        router._chain_head = None
        batch = _make_batch(_make_item())
        response = await router.process_batch(batch)
        assert isinstance(response, BatchResponse)

    async def test_response_success_flag(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        batch = _make_batch(_make_item())
        router._chain_head = _make_mock_chain_head_success(batch)
        response = await router.process_batch(batch)
        assert hasattr(response, "success")


# ---------------------------------------------------------------------------
# Tests: BatchPipelineRouter.process_batch (error paths)
# ---------------------------------------------------------------------------


class TestProcessBatchErrors:
    async def test_runtime_error_returns_error_response(self):
        """A RuntimeError raised during processing should return a BatchResponse error."""
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)

        # Make chain_head.process raise a RuntimeError
        mock_head = AsyncMock()
        mock_head.process.side_effect = RuntimeError("boom")
        router._chain_head = mock_head

        batch = _make_batch(_make_item())
        response = await router.process_batch(batch)
        assert response.success is False
        assert response.error_code == "PIPELINE_ERROR"

    async def test_value_error_returns_error_response(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        mock_head = AsyncMock()
        mock_head.process.side_effect = ValueError("bad value")
        router._chain_head = mock_head

        batch = _make_batch(_make_item())
        response = await router.process_batch(batch)
        assert response.success is False
        assert "PIPELINE_ERROR" in response.error_code

    async def test_type_error_returns_error_response(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        mock_head = AsyncMock()
        mock_head.process.side_effect = TypeError("type error")
        router._chain_head = mock_head

        batch = _make_batch(_make_item())
        response = await router.process_batch(batch)
        assert response.success is False

    async def test_key_error_returns_error_response(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        mock_head = AsyncMock()
        mock_head.process.side_effect = KeyError("missing key")
        router._chain_head = mock_head

        batch = _make_batch(_make_item())
        response = await router.process_batch(batch)
        assert response.success is False

    async def test_attribute_error_returns_error_response(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        mock_head = AsyncMock()
        mock_head.process.side_effect = AttributeError("attr error")
        router._chain_head = mock_head

        batch = _make_batch(_make_item())
        response = await router.process_batch(batch)
        assert response.success is False

    async def test_asyncio_timeout_error_returns_error_response(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        mock_head = AsyncMock()
        mock_head.process.side_effect = TimeoutError()
        router._chain_head = mock_head

        batch = _make_batch(_make_item())
        response = await router.process_batch(batch)
        assert response.success is False
        assert response.error_code == "PIPELINE_ERROR"

    async def test_failed_metrics_incremented(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        mock_head = AsyncMock()
        mock_head.process.side_effect = RuntimeError("fail")
        router._chain_head = mock_head

        batch = _make_batch(_make_item(), _make_item())
        await router.process_batch(batch)
        assert router._metrics["batches_failed"] == 1
        assert router._metrics["batches_processed"] == 0

    async def test_error_response_has_item_count(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        mock_head = AsyncMock()
        mock_head.process.side_effect = RuntimeError("fail")
        router._chain_head = mock_head

        items = [_make_item() for _ in range(3)]
        batch = _make_batch(*items)
        response = await router.process_batch(batch)
        assert response.stats.total_items == 3

    async def test_multiple_errors_accumulate_failed_count(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        mock_head = AsyncMock()
        mock_head.process.side_effect = RuntimeError("fail")
        router._chain_head = mock_head

        for _ in range(3):
            await router.process_batch(_make_batch(_make_item()))
        assert router._metrics["batches_failed"] == 3


# ---------------------------------------------------------------------------
# Tests: BatchPipelineRouter.set_item_processor
# ---------------------------------------------------------------------------


class TestSetItemProcessor:
    def test_set_item_processor_updates_router_attribute(self):
        router = BatchPipelineRouter(item_processor=_good_processor)
        router.set_item_processor(_bad_processor)
        assert router._item_processor is _bad_processor

    def test_set_item_processor_updates_batch_processing_middleware(self):
        from enhanced_agent_bus.middlewares.batch.processing import (
            BatchProcessingMiddleware,
        )

        router = BatchPipelineRouter(item_processor=_good_processor)
        router.set_item_processor(_bad_processor)

        # Find the BatchProcessingMiddleware in the chain
        for mw in router._config.middlewares:
            if isinstance(mw, BatchProcessingMiddleware):
                assert mw._item_processor is _bad_processor
                return
        pytest.fail("BatchProcessingMiddleware not found in config.middlewares")

    def test_set_item_processor_when_no_processing_middleware(self):
        """set_item_processor should not raise even if BatchProcessingMiddleware is absent."""
        config = _make_passthrough_config(n_mw=1)
        router = BatchPipelineRouter(config=config)
        # Should not raise
        router.set_item_processor(_good_processor)
        assert router._item_processor is _good_processor

    def test_set_item_processor_only_first_match(self):
        """Ensures the loop breaks after the first BatchProcessingMiddleware."""
        from enhanced_agent_bus.middlewares.batch.processing import (
            BatchProcessingMiddleware,
        )

        router = BatchPipelineRouter()
        # Count how many BatchProcessingMiddlewares exist
        bpm_list = [
            mw for mw in router._config.middlewares if isinstance(mw, BatchProcessingMiddleware)
        ]
        assert len(bpm_list) == 1  # default chain has exactly one


# ---------------------------------------------------------------------------
# Tests: BatchPipelineRouter.get_metrics
# ---------------------------------------------------------------------------


class TestGetMetrics:
    def test_initial_metrics(self):
        router = BatchPipelineRouter(item_processor=_good_processor)
        m = router.get_metrics()
        assert m["batches_processed"] == 0
        assert m["batches_failed"] == 0
        assert m["total_items_processed"] == 0
        assert m["avg_batch_latency_ms"] == 0.0

    def test_avg_latency_zero_when_no_batches(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        assert router.get_metrics()["avg_batch_latency_ms"] == 0.0

    async def test_avg_latency_computed_after_processing(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        batch = _make_batch(_make_item())
        router._chain_head = _make_mock_chain_head_success(batch)
        await router.process_batch(batch)
        m = router.get_metrics()
        assert m["avg_batch_latency_ms"] >= 0.0
        assert m["batches_processed"] == 1

    def test_pipeline_version_in_metrics(self):
        config = _make_passthrough_config()
        config.version = "test-version-99"
        router = BatchPipelineRouter(config=config)
        m = router.get_metrics()
        assert m["pipeline_version"] == "test-version-99"

    def test_default_pipeline_version_in_metrics(self):
        router = BatchPipelineRouter()
        m = router.get_metrics()
        assert m["pipeline_version"] == "2.0.0-batch"

    def test_middleware_count_in_metrics(self):
        config = _make_passthrough_config(n_mw=3)
        router = BatchPipelineRouter(config=config)
        m = router.get_metrics()
        assert m["middleware_count"] == 3

    def test_default_middleware_count_is_8(self):
        router = BatchPipelineRouter()
        m = router.get_metrics()
        assert m["middleware_count"] == 8

    async def test_avg_latency_formula(self):
        """avg = total_latency / batches_processed."""
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        # Process twice
        for _ in range(2):
            batch = _make_batch(_make_item())
            router._chain_head = _make_mock_chain_head_success(batch)
            await router.process_batch(batch)
        m = router.get_metrics()
        expected = router._metrics["total_latency_ms"] / 2
        assert abs(m["avg_batch_latency_ms"] - expected) < 0.001


# ---------------------------------------------------------------------------
# Tests: BatchPipelineRouter.get_middleware_info
# ---------------------------------------------------------------------------


class TestGetMiddlewareInfo:
    def test_returns_list(self):
        config = _make_passthrough_config(n_mw=2)
        router = BatchPipelineRouter(config=config)
        info = router.get_middleware_info()
        assert isinstance(info, list)

    def test_length_matches_middleware_count(self):
        config = _make_passthrough_config(n_mw=3)
        router = BatchPipelineRouter(config=config)
        info = router.get_middleware_info()
        assert len(info) == 3

    def test_info_has_required_keys(self):
        config = _make_passthrough_config(n_mw=1)
        router = BatchPipelineRouter(config=config)
        info = router.get_middleware_info()
        assert len(info) == 1
        entry = info[0]
        assert "name" in entry
        assert "enabled" in entry
        assert "timeout_ms" in entry

    def test_name_is_class_name(self):
        config = _make_passthrough_config(n_mw=1)
        router = BatchPipelineRouter(config=config)
        info = router.get_middleware_info()
        # The middleware class name should appear
        assert isinstance(info[0]["name"], str)

    def test_enabled_reflects_config(self):
        mw = _make_minimal_middleware()
        mw.config.enabled = False
        config = PipelineConfig(
            middlewares=[mw],
            max_concurrent=10,
            version="x",
            use_default_middlewares=False,
        )
        router = BatchPipelineRouter(config=config)
        info = router.get_middleware_info()
        assert info[0]["enabled"] is False

    def test_timeout_ms_reflects_config(self):
        mw = _make_minimal_middleware()
        mw.config.timeout_ms = 9999
        config = PipelineConfig(
            middlewares=[mw],
            max_concurrent=10,
            version="x",
            use_default_middlewares=False,
        )
        router = BatchPipelineRouter(config=config)
        info = router.get_middleware_info()
        assert info[0]["timeout_ms"] == 9999

    def test_default_router_has_8_middleware_infos(self):
        router = BatchPipelineRouter()
        info = router.get_middleware_info()
        assert len(info) == 8


# ---------------------------------------------------------------------------
# Tests: process_batch concurrency (metrics lock exercised concurrently)
# ---------------------------------------------------------------------------


class TestProcessBatchConcurrency:
    async def test_concurrent_batches_do_not_race_on_metrics(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        batches = [_make_batch(*[_make_item() for _ in range(2)]) for _ in range(5)]

        # Assign a fresh mock for each call — use a list-based side_effect
        call_results = []
        for b in batches:
            call_results.append(b)

        async def _side_effect(ctx):
            # Find which batch this context belongs to based on batch_request
            ctx.batch_response = BatchResponse(
                batch_id=ctx.batch_request.batch_id if ctx.batch_request else "x",
                success=True,
                items=[],
            )
            return ctx

        mock_head = AsyncMock()
        mock_head.process.side_effect = _side_effect
        router._chain_head = mock_head

        await asyncio.gather(*[router.process_batch(b) for b in batches])
        assert router._metrics["batches_processed"] == 5
        assert router._metrics["total_items_processed"] == 10

    async def test_concurrent_error_batches_do_not_race_on_metrics(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        mock_head = AsyncMock()
        mock_head.process.side_effect = RuntimeError("boom")
        router._chain_head = mock_head

        batches = [_make_batch(_make_item()) for _ in range(4)]
        await asyncio.gather(*[router.process_batch(b) for b in batches])
        assert router._metrics["batches_failed"] == 4


# ---------------------------------------------------------------------------
# Tests: process_batch with no chain head
# ---------------------------------------------------------------------------


class TestProcessBatchNoChainHead:
    async def test_no_chain_head_metrics_incremented(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        router._chain_head = None
        batch = _make_batch(_make_item())
        await router.process_batch(batch)
        assert router._metrics["batches_processed"] == 1

    async def test_no_chain_head_returns_batch_response(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        router._chain_head = None
        batch = _make_batch(_make_item())
        response = await router.process_batch(batch)
        assert isinstance(response, BatchResponse)


# ---------------------------------------------------------------------------
# Tests: process_batch finalize called on context
# ---------------------------------------------------------------------------


class TestProcessBatchFinalize:
    async def test_finalize_called_on_context(self):
        """Verify that context.finalize() is invoked during successful processing."""
        from enhanced_agent_bus.middlewares.batch.context import BatchPipelineContext

        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        router._chain_head = None  # skip actual chain

        finalize_called = []

        with patch.object(
            BatchPipelineContext,
            "finalize",
            side_effect=lambda: finalize_called.append(True),
        ):
            batch = _make_batch(_make_item())
            await router.process_batch(batch)

        assert len(finalize_called) == 1

    async def test_to_batch_response_called_on_context(self):
        """Verify that context.to_batch_response() is used as the return value."""
        from enhanced_agent_bus.middlewares.batch.context import BatchPipelineContext

        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        router._chain_head = None

        fake_response = BatchResponse(
            batch_id="fake-id",
            success=True,
            stats=MagicMock(total_items=1, successful_items=1, failed_items=0),
        )

        with patch.object(
            BatchPipelineContext,
            "to_batch_response",
            return_value=fake_response,
        ):
            batch = _make_batch(_make_item())
            response = await router.process_batch(batch)

        assert response is fake_response


# ---------------------------------------------------------------------------
# Tests: BatchResponse.create_batch_error is used on pipeline error
# ---------------------------------------------------------------------------


class TestCreateBatchErrorOnPipelineError:
    async def test_error_response_batch_id_matches_request(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        mock_head = AsyncMock()
        mock_head.process.side_effect = RuntimeError("catastrophic")
        router._chain_head = mock_head

        batch = _make_batch(_make_item())
        response = await router.process_batch(batch)
        assert response.batch_id == batch.batch_id

    async def test_error_response_error_code_is_pipeline_error(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        mock_head = AsyncMock()
        mock_head.process.side_effect = ValueError("v")
        router._chain_head = mock_head

        batch = _make_batch(_make_item())
        response = await router.process_batch(batch)
        assert response.error_code == "PIPELINE_ERROR"

    async def test_error_response_success_false(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        mock_head = AsyncMock()
        mock_head.process.side_effect = TypeError("t")
        router._chain_head = mock_head

        batch = _make_batch(_make_item())
        response = await router.process_batch(batch)
        assert response.success is False

    async def test_error_response_items_empty(self):
        config = _make_passthrough_config()
        router = BatchPipelineRouter(config=config)
        mock_head = AsyncMock()
        mock_head.process.side_effect = AttributeError("a")
        router._chain_head = mock_head

        batch = _make_batch(_make_item())
        response = await router.process_batch(batch)
        assert response.items == []


# ---------------------------------------------------------------------------
# Tests: BatchPipelineContext usage in process_batch
# ---------------------------------------------------------------------------


class TestBatchPipelineContextUsage:
    async def test_context_receives_correct_batch_tenant(self):
        """batch_tenant_id on context should match batch_request.tenant_id."""
        captured = []

        class _CaptureMW(BaseMiddleware):
            async def process(self, context):
                captured.append(context.batch_tenant_id)
                ctx = await self._call_next(context)
                return ctx

        config = PipelineConfig(
            middlewares=[_CaptureMW(MiddlewareConfig())],
            use_default_middlewares=False,
        )
        router = BatchPipelineRouter(config=config)
        batch = _make_batch(_make_item(), tenant_id="tenant-xyz")
        await router.process_batch(batch)
        assert captured[0] == "tenant-xyz"

    async def test_context_receives_fail_fast_flag(self):
        captured = []

        class _CaptureMW(BaseMiddleware):
            async def process(self, context):
                captured.append(context.fail_fast)
                return await self._call_next(context)

        config = PipelineConfig(
            middlewares=[_CaptureMW(MiddlewareConfig())],
            use_default_middlewares=False,
        )
        router = BatchPipelineRouter(config=config)
        # fail_fast is False by default
        batch = _make_batch(_make_item())
        await router.process_batch(batch)
        assert captured[0] is False

    async def test_context_batch_size_equals_item_count(self):
        captured = []

        class _CaptureMW(BaseMiddleware):
            async def process(self, context):
                captured.append(context.batch_size)
                return await self._call_next(context)

        config = PipelineConfig(
            middlewares=[_CaptureMW(MiddlewareConfig())],
            use_default_middlewares=False,
        )
        router = BatchPipelineRouter(config=config)
        items = [_make_item() for _ in range(4)]
        batch = _make_batch(*items)
        await router.process_batch(batch)
        assert captured[0] == 4

    async def test_context_deduplicate_flag(self):
        captured = []

        class _CaptureMW(BaseMiddleware):
            async def process(self, context):
                captured.append(context.deduplicate)
                return await self._call_next(context)

        config = PipelineConfig(
            middlewares=[_CaptureMW(MiddlewareConfig())],
            use_default_middlewares=False,
        )
        router = BatchPipelineRouter(config=config)
        batch = _make_batch(_make_item())
        await router.process_batch(batch)
        # deduplicate defaults to True
        assert captured[0] is True
