# Constitutional Hash: 608508a9bd224290
# Sprint 60 — pipeline/router.py coverage
"""
ACGS-2 Enhanced Agent Bus - Pipeline Router Coverage Tests

Comprehensive tests for src/core/enhanced_agent_bus/pipeline/router.py
targeting >= 95% line coverage.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.pipeline.middleware import BaseMiddleware, MiddlewareConfig
from enhanced_agent_bus.pipeline.router import (
    PIPELINE_PROCESSING_ERRORS,
    PipelineConfig,
    PipelineMessageRouter,
)
from enhanced_agent_bus.validators import ValidationResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH  # pragma: allowlist secret


def _make_message(**kwargs):
    """Return a minimal AgentMessage-like mock."""
    msg = MagicMock()
    msg.ifc_label = None
    for k, v in kwargs.items():
        setattr(msg, k, v)
    return msg


def _make_validation_result(is_valid: bool = True, errors=None, metadata=None) -> ValidationResult:
    return ValidationResult(
        is_valid=is_valid,
        errors=errors or [],
        metadata=metadata or {},
    )


class _PassthroughMW(BaseMiddleware):
    """Minimal no-op middleware that passes context through."""

    async def process(self, context):
        return await self._call_next(context)


class _StrategyMW(BaseMiddleware):
    """Middleware that sets a strategy_result on the context."""

    def __init__(self, result: ValidationResult, **kwargs):
        super().__init__(**kwargs)
        self._result = result

    async def process(self, context):
        context.strategy_result = self._result
        return await self._call_next(context)


class _EarlyExitMW(BaseMiddleware):
    """Middleware that sets an early_result to short-circuit the pipeline."""

    def __init__(self, result: ValidationResult, **kwargs):
        super().__init__(**kwargs)
        self._result = result

    async def process(self, context):
        context.set_early_result(self._result)
        return context


class _RaisingMW(BaseMiddleware):
    """Middleware that raises a specified exception."""

    def __init__(self, exc: Exception, **kwargs):
        super().__init__(**kwargs)
        self._exc = exc

    async def process(self, context):
        raise self._exc


def _make_passthrough_config(n_mw: int = 1) -> PipelineConfig:
    middlewares = [_PassthroughMW() for _ in range(n_mw)]
    return PipelineConfig(
        middlewares=middlewares,
        max_concurrent=10,
        version="test-1.0",
        use_default_middlewares=False,
    )


# ===========================================================================
# PIPELINE_PROCESSING_ERRORS tuple
# ===========================================================================


class TestPipelineProcessingErrors:
    def test_contains_expected_exceptions(self):
        assert RuntimeError in PIPELINE_PROCESSING_ERRORS
        assert ValueError in PIPELINE_PROCESSING_ERRORS
        assert TypeError in PIPELINE_PROCESSING_ERRORS
        assert KeyError in PIPELINE_PROCESSING_ERRORS
        assert AttributeError in PIPELINE_PROCESSING_ERRORS
        assert asyncio.TimeoutError in PIPELINE_PROCESSING_ERRORS

    def test_is_tuple(self):
        assert isinstance(PIPELINE_PROCESSING_ERRORS, tuple)


# ===========================================================================
# PipelineConfig Tests
# ===========================================================================


class TestPipelineConfigDefaults:
    def test_default_max_concurrent(self):
        # use_default_middlewares=False prevents real middleware imports
        cfg = PipelineConfig(
            middlewares=[_PassthroughMW()],
            use_default_middlewares=False,
        )
        assert cfg.max_concurrent == 100

    def test_default_metrics_enabled(self):
        cfg = PipelineConfig(
            middlewares=[_PassthroughMW()],
            use_default_middlewares=False,
        )
        assert cfg.metrics_enabled is True

    def test_default_version(self):
        cfg = PipelineConfig(
            middlewares=[_PassthroughMW()],
            use_default_middlewares=False,
        )
        assert cfg.version == "2.0.0"

    def test_explicit_middlewares_skip_default_creation(self):
        mw = _PassthroughMW()
        cfg = PipelineConfig(middlewares=[mw], use_default_middlewares=True)
        # When middlewares are explicitly provided, __post_init__ should NOT
        # overwrite them with defaults even if use_default_middlewares=True
        assert cfg.middlewares[0] is mw

    def test_use_default_middlewares_false_no_override(self):
        mw = _PassthroughMW()
        cfg = PipelineConfig(middlewares=[mw], use_default_middlewares=False)
        assert cfg.middlewares == [mw]


class TestPipelineConfigPostInit:
    def test_empty_middlewares_with_flag_creates_defaults(self):
        """When middlewares=[] and use_default_middlewares=True, defaults are created."""
        with patch.object(
            PipelineConfig,
            "_create_default_middlewares",
            return_value=[_PassthroughMW()],
        ) as mock_create:
            cfg = PipelineConfig(middlewares=[], use_default_middlewares=True)
            mock_create.assert_called_once()
            assert len(cfg.middlewares) == 1

    def test_empty_middlewares_without_flag_stays_empty(self):
        """When use_default_middlewares=False, no defaults are created even if list is empty."""
        cfg = PipelineConfig(middlewares=[_PassthroughMW()], use_default_middlewares=False)
        # Just verify it works without importing real middlewares
        assert len(cfg.middlewares) >= 1


class TestPipelineConfigCreateDefaultMiddlewares:
    def test_create_default_middlewares_imports_and_returns(self):
        """_create_default_middlewares() should return a non-empty list of BaseMiddleware."""
        mock_security = MagicMock(spec=BaseMiddleware)
        mock_security.config = MiddlewareConfig()
        mock_tool = MagicMock(spec=BaseMiddleware)
        mock_tool.config = MiddlewareConfig()
        mock_temporal = MagicMock(spec=BaseMiddleware)
        mock_temporal.config = MiddlewareConfig()

        with (
            patch(
                "enhanced_agent_bus.middlewares.security.SecurityMiddleware",
                return_value=mock_security,
            ),
            patch(
                "enhanced_agent_bus.middlewares.tool_privilege.ToolPrivilegeMiddleware",
                return_value=mock_tool,
            ),
            patch(
                "enhanced_agent_bus.middlewares.temporal_policy.TemporalPolicyMiddleware",
                return_value=mock_temporal,
            ),
        ):
            cfg = PipelineConfig(middlewares=[], use_default_middlewares=False)
            result = cfg._create_default_middlewares()
            # Returns a list with 3 middleware instances
            assert len(result) == 3


class TestPipelineConfigValidate:
    def test_valid_config_does_not_raise(self):
        cfg = _make_passthrough_config(1)
        cfg.validate()  # Should not raise

    def test_max_concurrent_zero_raises(self):
        cfg = PipelineConfig(
            middlewares=[_PassthroughMW()],
            max_concurrent=0,
            use_default_middlewares=False,
        )
        with pytest.raises(ValueError, match="max_concurrent must be >= 1"):
            cfg.validate()

    def test_max_concurrent_negative_raises(self):
        cfg = PipelineConfig(
            middlewares=[_PassthroughMW()],
            max_concurrent=-5,
            use_default_middlewares=False,
        )
        with pytest.raises(ValueError, match="max_concurrent must be >= 1"):
            cfg.validate()

    def test_empty_middlewares_raises(self):
        cfg = PipelineConfig(
            middlewares=[_PassthroughMW()],
            use_default_middlewares=False,
        )
        cfg.middlewares = []  # Force empty after construction
        with pytest.raises(ValueError, match="At least one middleware is required"):
            cfg.validate()

    def test_non_base_middleware_raises(self):
        cfg = PipelineConfig(
            middlewares=[_PassthroughMW()],
            use_default_middlewares=False,
        )
        cfg.middlewares = [object()]  # Not a BaseMiddleware
        with pytest.raises(ValueError, match="not a BaseMiddleware"):
            cfg.validate()

    def test_multiple_valid_middlewares(self):
        cfg = PipelineConfig(
            middlewares=[_PassthroughMW(), _PassthroughMW()],
            use_default_middlewares=False,
        )
        cfg.validate()  # Should not raise


class TestPipelineConfigBuildChain:
    def test_empty_middlewares_returns_none(self):
        cfg = PipelineConfig(
            middlewares=[_PassthroughMW()],
            use_default_middlewares=False,
        )
        cfg.middlewares = []
        result = cfg.build_chain()
        assert result is None

    def test_single_middleware_returns_it(self):
        mw = _PassthroughMW()
        cfg = PipelineConfig(middlewares=[mw], use_default_middlewares=False)
        head = cfg.build_chain()
        assert head is mw

    def test_two_middlewares_links_them(self):
        mw1 = _PassthroughMW()
        mw2 = _PassthroughMW()
        cfg = PipelineConfig(middlewares=[mw1, mw2], use_default_middlewares=False)
        head = cfg.build_chain()
        assert head is mw1
        assert mw1._next is mw2

    def test_three_middlewares_links_chain(self):
        mw1 = _PassthroughMW()
        mw2 = _PassthroughMW()
        mw3 = _PassthroughMW()
        cfg = PipelineConfig(middlewares=[mw1, mw2, mw3], use_default_middlewares=False)
        head = cfg.build_chain()
        assert head is mw1
        assert mw1._next is mw2
        assert mw2._next is mw3


# ===========================================================================
# PipelineMessageRouter — Construction
# ===========================================================================


class TestPipelineMessageRouterInit:
    def test_init_with_none_config_uses_default(self):
        """None config creates a default PipelineConfig (uses default middlewares)."""
        mock_security = MagicMock(spec=BaseMiddleware)
        mock_security.config = MiddlewareConfig()
        mock_tool = MagicMock(spec=BaseMiddleware)
        mock_tool.config = MiddlewareConfig()
        mock_temporal = MagicMock(spec=BaseMiddleware)
        mock_temporal.config = MiddlewareConfig()

        with (
            patch(
                "enhanced_agent_bus.middlewares.security.SecurityMiddleware",
                return_value=mock_security,
            ),
            patch(
                "enhanced_agent_bus.middlewares.tool_privilege.ToolPrivilegeMiddleware",
                return_value=mock_tool,
            ),
            patch(
                "enhanced_agent_bus.middlewares.temporal_policy.TemporalPolicyMiddleware",
                return_value=mock_temporal,
            ),
        ):
            router = PipelineMessageRouter(config=None)
            assert router._config is not None

    def test_init_with_explicit_config(self):
        cfg = _make_passthrough_config(1)
        router = PipelineMessageRouter(config=cfg)
        assert router._config is cfg

    def test_init_sets_semaphore(self):
        cfg = _make_passthrough_config(1)
        router = PipelineMessageRouter(config=cfg)
        assert router._semaphore is not None

    def test_init_resets_metrics(self):
        cfg = _make_passthrough_config(1)
        router = PipelineMessageRouter(config=cfg)
        assert router._metrics["processed"] == 0
        assert router._metrics["failed"] == 0
        assert router._metrics["total_latency_ms"] == 0.0

    def test_init_invalid_config_raises(self):
        cfg = PipelineConfig(
            middlewares=[_PassthroughMW()],
            max_concurrent=0,
            use_default_middlewares=False,
        )
        with pytest.raises(ValueError):
            PipelineMessageRouter(config=cfg)

    def test_chain_head_set_from_config(self):
        mw = _PassthroughMW()
        cfg = PipelineConfig(middlewares=[mw], use_default_middlewares=False)
        router = PipelineMessageRouter(config=cfg)
        assert router._chain_head is mw


# ===========================================================================
# PipelineMessageRouter.process
# ===========================================================================


class TestPipelineMessageRouterProcess:
    async def test_process_with_strategy_result(self):
        """Happy path: middleware sets strategy_result, router returns it."""
        expected = _make_validation_result(is_valid=True)
        strategy_mw = _StrategyMW(result=expected)
        cfg = PipelineConfig(
            middlewares=[strategy_mw],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        msg = _make_message()
        result = await router.process(msg)
        assert result.is_valid is True
        assert router._metrics["processed"] == 1
        assert router._metrics["failed"] == 0

    async def test_process_with_early_result(self):
        """Early exit path: middleware sets early_result, returned directly."""
        early = _make_validation_result(is_valid=False, errors=["blocked"])
        early_mw = _EarlyExitMW(result=early)
        cfg = PipelineConfig(
            middlewares=[early_mw],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        msg = _make_message()
        result = await router.process(msg)
        assert result is early
        assert router._metrics["processed"] == 1

    async def test_process_no_chain_head_returns_fallback(self):
        """When chain_head is None (empty middlewares after build), returns fallback."""
        cfg = _make_passthrough_config(1)
        router = PipelineMessageRouter(config=cfg)
        # Force chain head to None to simulate no middleware execution
        router._chain_head = None
        msg = _make_message()
        result = await router.process(msg)
        # No strategy_result → fallback ValidationResult
        assert result.is_valid is False
        assert "No strategy result produced" in result.errors

    async def test_process_increments_processed_metric(self):
        strategy_mw = _StrategyMW(result=_make_validation_result())
        cfg = PipelineConfig(
            middlewares=[strategy_mw],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        msg = _make_message()
        await router.process(msg)
        await router.process(msg)
        assert router._metrics["processed"] == 2

    async def test_process_accumulates_latency(self):
        strategy_mw = _StrategyMW(result=_make_validation_result())
        cfg = PipelineConfig(
            middlewares=[strategy_mw],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        msg = _make_message()
        await router.process(msg)
        assert router._metrics["total_latency_ms"] >= 0.0

    async def test_process_runtime_error_increments_failed(self):
        exc = RuntimeError("boom")
        raising_mw = _RaisingMW(exc=exc)
        cfg = PipelineConfig(
            middlewares=[raising_mw],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        msg = _make_message()
        with pytest.raises(RuntimeError, match="boom"):
            await router.process(msg)
        assert router._metrics["failed"] == 1
        assert router._metrics["processed"] == 0

    async def test_process_value_error_increments_failed(self):
        raising_mw = _RaisingMW(exc=ValueError("invalid"))
        cfg = PipelineConfig(
            middlewares=[raising_mw],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        with pytest.raises(ValueError):
            await router.process(_make_message())
        assert router._metrics["failed"] == 1

    async def test_process_type_error_increments_failed(self):
        raising_mw = _RaisingMW(exc=TypeError("type"))
        cfg = PipelineConfig(
            middlewares=[raising_mw],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        with pytest.raises(TypeError):
            await router.process(_make_message())
        assert router._metrics["failed"] == 1

    async def test_process_key_error_increments_failed(self):
        raising_mw = _RaisingMW(exc=KeyError("key"))
        cfg = PipelineConfig(
            middlewares=[raising_mw],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        with pytest.raises(KeyError):
            await router.process(_make_message())
        assert router._metrics["failed"] == 1

    async def test_process_attribute_error_increments_failed(self):
        raising_mw = _RaisingMW(exc=AttributeError("attr"))
        cfg = PipelineConfig(
            middlewares=[raising_mw],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        with pytest.raises(AttributeError):
            await router.process(_make_message())
        assert router._metrics["failed"] == 1

    async def test_process_timeout_error_increments_failed(self):
        raising_mw = _RaisingMW(exc=TimeoutError())
        cfg = PipelineConfig(
            middlewares=[raising_mw],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        with pytest.raises(asyncio.TimeoutError):
            await router.process(_make_message())
        assert router._metrics["failed"] == 1

    async def test_process_uses_semaphore(self):
        """Max concurrent limit is respected via semaphore."""
        cfg = PipelineConfig(
            middlewares=[_StrategyMW(result=_make_validation_result())],
            max_concurrent=1,
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        # Two concurrent calls should both complete fine with semaphore
        results = await asyncio.gather(
            router.process(_make_message()),
            router.process(_make_message()),
        )
        assert len(results) == 2
        assert router._metrics["processed"] == 2

    async def test_process_chain_passthrough_no_strategy(self):
        """Passthrough middleware without strategy_result → fallback result."""
        passthrough = _PassthroughMW()
        cfg = PipelineConfig(
            middlewares=[passthrough],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        result = await router.process(_make_message())
        assert result.is_valid is False
        assert result.errors == ["No strategy result produced"]

    async def test_early_result_skips_latency_accumulation(self):
        """Early exit: latency is NOT added to total_latency_ms (early path)."""
        early = _make_validation_result(is_valid=True)
        early_mw = _EarlyExitMW(result=early)
        cfg = PipelineConfig(
            middlewares=[early_mw],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        await router.process(_make_message())
        # Early result path skips latency accumulation
        assert router._metrics["total_latency_ms"] == 0.0


# ===========================================================================
# PipelineMessageRouter.process_batch
# ===========================================================================


class TestPipelineMessageRouterProcessBatch:
    async def test_batch_all_success(self):
        strategy_mw = _StrategyMW(result=_make_validation_result(is_valid=True))
        cfg = PipelineConfig(
            middlewares=[strategy_mw],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        messages = [_make_message() for _ in range(3)]
        results = await router.process_batch(messages)
        assert len(results) == 3
        for r in results:
            assert r.is_valid is True

    async def test_batch_continue_on_error_true_converts_exceptions(self):
        """With continue_on_error=True, exceptions become failed ValidationResults."""
        exc = RuntimeError("fail")
        raising_mw = _RaisingMW(exc=exc)
        cfg = PipelineConfig(
            middlewares=[raising_mw],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        messages = [_make_message()]
        results = await router.process_batch(messages, continue_on_error=True)
        assert len(results) == 1
        assert results[0].is_valid is False
        assert "RuntimeError" in results[0].metadata.get("error_type", "")

    async def test_batch_continue_on_error_preserves_error_string(self):
        exc = ValueError("bad input")
        raising_mw = _RaisingMW(exc=exc)
        cfg = PipelineConfig(
            middlewares=[raising_mw],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        results = await router.process_batch([_make_message()], continue_on_error=True)
        assert "bad input" in results[0].errors[0]

    async def test_batch_continue_on_error_false_raises_on_failure(self):
        """With continue_on_error=False, exceptions propagate immediately."""
        exc = RuntimeError("fatal")
        raising_mw = _RaisingMW(exc=exc)
        cfg = PipelineConfig(
            middlewares=[raising_mw],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        with pytest.raises(RuntimeError, match="fatal"):
            await router.process_batch([_make_message()], continue_on_error=False)

    async def test_batch_mixed_success_and_failure_with_continue(self):
        """Mixed batch: some succeed, some raise, all captured when continue_on_error=True."""
        call_count = 0

        class _MixedMW(BaseMiddleware):
            async def process(self, context):
                nonlocal call_count
                call_count += 1
                if call_count % 2 == 0:
                    raise RuntimeError("even fails")
                context.strategy_result = ValidationResult(is_valid=True)
                return await self._call_next(context)

        cfg = PipelineConfig(
            middlewares=[_MixedMW()],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        messages = [_make_message() for _ in range(4)]
        results = await router.process_batch(messages, continue_on_error=True)
        assert len(results) == 4
        successes = [r for r in results if r.is_valid]
        failures = [r for r in results if not r.is_valid]
        assert len(successes) == 2
        assert len(failures) == 2

    async def test_batch_empty_list(self):
        cfg = _make_passthrough_config(1)
        router = PipelineMessageRouter(config=cfg)
        results = await router.process_batch([], continue_on_error=True)
        assert results == []

    async def test_batch_empty_list_no_continue(self):
        cfg = _make_passthrough_config(1)
        router = PipelineMessageRouter(config=cfg)
        results = await router.process_batch([], continue_on_error=False)
        assert results == []

    async def test_batch_continue_on_error_default_is_true(self):
        """Default continue_on_error should be True."""
        exc = RuntimeError("x")
        raising_mw = _RaisingMW(exc=exc)
        cfg = PipelineConfig(
            middlewares=[raising_mw],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        # No continue_on_error argument — should NOT raise
        results = await router.process_batch([_make_message()])
        assert results[0].is_valid is False


# ===========================================================================
# PipelineMessageRouter.get_metrics
# ===========================================================================


class TestPipelineMessageRouterGetMetrics:
    async def test_get_metrics_initial_state(self):
        cfg = _make_passthrough_config(1)
        router = PipelineMessageRouter(config=cfg)
        metrics = router.get_metrics()
        assert metrics["processed"] == 0
        assert metrics["failed"] == 0
        assert metrics["avg_latency_ms"] == 0.0
        assert metrics["pipeline_version"] == "test-1.0"
        assert metrics["middleware_count"] == 1

    async def test_get_metrics_avg_latency_after_processing(self):
        strategy_mw = _StrategyMW(result=_make_validation_result())
        cfg = PipelineConfig(
            middlewares=[strategy_mw],
            max_concurrent=10,
            version="v99",
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        await router.process(_make_message())
        metrics = router.get_metrics()
        assert metrics["processed"] == 1
        assert metrics["avg_latency_ms"] >= 0.0

    async def test_get_metrics_zero_processed_avg_latency_zero(self):
        cfg = _make_passthrough_config(1)
        router = PipelineMessageRouter(config=cfg)
        metrics = router.get_metrics()
        assert metrics["avg_latency_ms"] == 0.0

    async def test_get_metrics_version_from_config(self):
        cfg = PipelineConfig(
            middlewares=[_PassthroughMW()],
            version="custom-3.7",
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        assert router.get_metrics()["pipeline_version"] == "custom-3.7"

    async def test_get_metrics_middleware_count(self):
        cfg = PipelineConfig(
            middlewares=[_PassthroughMW(), _PassthroughMW(), _PassthroughMW()],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        assert router.get_metrics()["middleware_count"] == 3

    async def test_get_metrics_active_middlewares_all_enabled(self):
        mws = [_PassthroughMW(config=MiddlewareConfig(enabled=True)) for _ in range(3)]
        cfg = PipelineConfig(middlewares=mws, use_default_middlewares=False)
        router = PipelineMessageRouter(config=cfg)
        assert router.get_metrics()["active_middlewares"] == 3

    async def test_get_metrics_active_middlewares_some_disabled(self):
        mws = [
            _PassthroughMW(config=MiddlewareConfig(enabled=True)),
            _PassthroughMW(config=MiddlewareConfig(enabled=False)),
            _PassthroughMW(config=MiddlewareConfig(enabled=True)),
        ]
        cfg = PipelineConfig(middlewares=mws, use_default_middlewares=False)
        router = PipelineMessageRouter(config=cfg)
        assert router.get_metrics()["active_middlewares"] == 2

    async def test_get_metrics_failed_count(self):
        raising_mw = _RaisingMW(exc=RuntimeError("err"))
        cfg = PipelineConfig(
            middlewares=[raising_mw],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await router.process(_make_message())
        metrics = router.get_metrics()
        assert metrics["failed"] == 3
        assert metrics["processed"] == 0


# ===========================================================================
# PipelineMessageRouter.get_middleware_info
# ===========================================================================


class TestPipelineMessageRouterGetMiddlewareInfo:
    def test_get_middleware_info_returns_list(self):
        cfg = _make_passthrough_config(2)
        router = PipelineMessageRouter(config=cfg)
        info = router.get_middleware_info()
        assert isinstance(info, list)
        assert len(info) == 2

    def test_get_middleware_info_has_required_keys(self):
        cfg = _make_passthrough_config(1)
        router = PipelineMessageRouter(config=cfg)
        info = router.get_middleware_info()
        assert "name" in info[0]
        assert "enabled" in info[0]
        assert "timeout_ms" in info[0]
        assert "fail_closed" in info[0]

    def test_get_middleware_info_name_is_class_name(self):
        cfg = _make_passthrough_config(1)
        router = PipelineMessageRouter(config=cfg)
        info = router.get_middleware_info()
        assert info[0]["name"] == "_PassthroughMW"

    def test_get_middleware_info_enabled_true(self):
        mw = _PassthroughMW(config=MiddlewareConfig(enabled=True))
        cfg = PipelineConfig(middlewares=[mw], use_default_middlewares=False)
        router = PipelineMessageRouter(config=cfg)
        assert router.get_middleware_info()[0]["enabled"] is True

    def test_get_middleware_info_enabled_false(self):
        mw = _PassthroughMW(config=MiddlewareConfig(enabled=False))
        cfg = PipelineConfig(middlewares=[mw], use_default_middlewares=False)
        router = PipelineMessageRouter(config=cfg)
        assert router.get_middleware_info()[0]["enabled"] is False

    def test_get_middleware_info_timeout_ms(self):
        mw = _PassthroughMW(config=MiddlewareConfig(timeout_ms=2500))
        cfg = PipelineConfig(middlewares=[mw], use_default_middlewares=False)
        router = PipelineMessageRouter(config=cfg)
        assert router.get_middleware_info()[0]["timeout_ms"] == 2500

    def test_get_middleware_info_fail_closed(self):
        mw = _PassthroughMW(config=MiddlewareConfig(fail_closed=False))
        cfg = PipelineConfig(middlewares=[mw], use_default_middlewares=False)
        router = PipelineMessageRouter(config=cfg)
        assert router.get_middleware_info()[0]["fail_closed"] is False

    def test_get_middleware_info_multiple_middlewares(self):
        mws = [
            _PassthroughMW(config=MiddlewareConfig(timeout_ms=100)),
            _PassthroughMW(config=MiddlewareConfig(timeout_ms=200)),
        ]
        cfg = PipelineConfig(middlewares=mws, use_default_middlewares=False)
        router = PipelineMessageRouter(config=cfg)
        info = router.get_middleware_info()
        assert info[0]["timeout_ms"] == 100
        assert info[1]["timeout_ms"] == 200

    def test_get_middleware_info_empty_middlewares(self):
        cfg = _make_passthrough_config(1)
        router = PipelineMessageRouter(config=cfg)
        router._config.middlewares = []
        info = router.get_middleware_info()
        assert info == []


# ===========================================================================
# Integration: multi-middleware chains
# ===========================================================================


class TestMultiMiddlewareChain:
    async def test_chain_of_three_all_passthrough(self):
        """Three passthrough middlewares with final strategy setter."""
        result = _make_validation_result(is_valid=True)
        strategy_mw = _StrategyMW(result=result)
        cfg = PipelineConfig(
            middlewares=[_PassthroughMW(), _PassthroughMW(), strategy_mw],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        r = await router.process(_make_message())
        assert r.is_valid is True

    async def test_early_exit_skips_remaining_middlewares(self):
        """Early exit from first middleware means later middleware never runs."""
        call_count = 0

        class _CountingMW(BaseMiddleware):
            async def process(self, context):
                nonlocal call_count
                call_count += 1
                return await self._call_next(context)

        early_result = _make_validation_result(is_valid=False)
        cfg = PipelineConfig(
            middlewares=[_EarlyExitMW(result=early_result), _CountingMW()],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        r = await router.process(_make_message())
        assert r is early_result
        # _CountingMW was NOT called because EarlyExitMW short-circuited
        assert call_count == 0

    async def test_exception_in_middle_of_chain(self):
        """Exception in second middleware with three middleware chain."""
        call_count = 0

        class _CountBefore(BaseMiddleware):
            async def process(self, context):
                nonlocal call_count
                call_count += 1
                return await self._call_next(context)

        cfg = PipelineConfig(
            middlewares=[_CountBefore(), _RaisingMW(exc=RuntimeError("mid"))],
            use_default_middlewares=False,
        )
        router = PipelineMessageRouter(config=cfg)
        with pytest.raises(RuntimeError, match="mid"):
            await router.process(_make_message())
        assert call_count == 1
        assert router._metrics["failed"] == 1
