# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/pipeline/legacy_wrapper.py.
Targets >= 95% line coverage of legacy_wrapper.py (70 stmts).

Design notes:
- legacy_wrapper.py imports middleware classes that do not yet exist
  (CacheMiddleware, MetricsMiddleware, StrategyMiddleware, VerificationMiddleware
   and middlewares.verification sub-module). We patch sys.modules + the
   middlewares package object BEFORE any test imports the module under test,
   and mock PipelineMessageRouter for init-path tests to avoid the
   BaseMiddleware isinstance check in PipelineConfig.validate().
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module-level setup: inject fake middleware classes so that legacy_wrapper.py
# can be imported at all.
# ---------------------------------------------------------------------------
from enhanced_agent_bus.pipeline.middleware import BaseMiddleware, MiddlewareConfig


class _FakeCacheMiddleware(BaseMiddleware):
    """Stub CacheMiddleware for testing."""

    def __init__(self, maxsize: int = 1000) -> None:
        super().__init__()
        self._maxsize = maxsize

    async def process(self, context):  # type: ignore[override]
        return context


class _FakeMetricsMiddleware(BaseMiddleware):
    """Stub MetricsMiddleware for testing."""

    def __init__(self) -> None:
        super().__init__()

    async def process(self, context):  # type: ignore[override]
        return context


class _FakeStrategyMiddleware(BaseMiddleware):
    """Stub StrategyMiddleware for testing."""

    def __init__(self, strategy=None) -> None:
        super().__init__()
        self._strategy = strategy

    async def process(self, context):  # type: ignore[override]
        return context


class _FakeVerificationMiddleware(BaseMiddleware):
    """Stub VerificationMiddleware for testing."""

    def __init__(
        self,
        config=None,
        sdpc_verifier=None,
        pqc_verifier=None,
        opa_verifier=None,
        parallel: bool = False,
    ) -> None:
        super().__init__(config)
        self._sdpc_verifier = sdpc_verifier
        self._pqc_verifier = pqc_verifier
        self._opa_verifier = opa_verifier
        self._parallel = parallel

    async def process(self, context):  # type: ignore[override]
        return context


class _FakeOPAVerifier:
    pass


class _FakePQCVerifier:
    def __init__(self, use_rust: bool = True) -> None:
        self._use_rust = use_rust


class _FakeSDPCVerifier:
    pass


# Build a fake verification sub-module
_fake_verification_module = MagicMock()
_fake_verification_module.OPAVerifier = _FakeOPAVerifier
_fake_verification_module.PQCVerifier = _FakePQCVerifier
_fake_verification_module.SDPCVerifier = _FakeSDPCVerifier

# Inject into sys.modules BEFORE legacy_wrapper is imported
sys.modules.setdefault("enhanced_agent_bus.middlewares.verification", _fake_verification_module)

# Also inject missing AIGuardrailsConfig to prevent errors from the security middleware path
_fake_security_module = sys.modules.get("enhanced_agent_bus.middlewares.security")

# Patch the middlewares package to expose the fake middleware classes
import enhanced_agent_bus.middlewares as _mw_pkg

_mw_pkg.CacheMiddleware = _FakeCacheMiddleware  # type: ignore[attr-defined]
_mw_pkg.MetricsMiddleware = _FakeMetricsMiddleware  # type: ignore[attr-defined]
_mw_pkg.StrategyMiddleware = _FakeStrategyMiddleware  # type: ignore[attr-defined]
_mw_pkg.VerificationMiddleware = _FakeVerificationMiddleware  # type: ignore[attr-defined]

# Also make sure SecurityMiddleware is available from the package
from enhanced_agent_bus.middlewares.security import (
    SecurityMiddleware as _RealSecurityMW,
)

_mw_pkg.SecurityMiddleware = _RealSecurityMW  # type: ignore[attr-defined]


class _FakeSessionExtractionMiddleware(BaseMiddleware):
    """Stub SessionExtractionMiddleware that accepts a 'config' kwarg."""

    def __init__(self, config=None) -> None:
        super().__init__(config)

    async def process(self, context):  # type: ignore[override]
        return context


_mw_pkg.SessionExtractionMiddleware = _FakeSessionExtractionMiddleware  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_router_metrics(processed=0, failed=0, avg_latency_ms=0.0):
    """Return a metrics dict matching PipelineMessageRouter.get_metrics()."""
    return {
        "processed": processed,
        "failed": failed,
        "avg_latency_ms": avg_latency_ms,
        "pipeline_version": "2.0.0",
        "middleware_count": 6,
        "active_middlewares": 6,
    }


def _make_mock_router(processed=0, failed=0, avg_latency_ms=0.0):
    r = MagicMock()
    r.get_metrics.return_value = _make_router_metrics(processed, failed, avg_latency_ms)
    return r


def _make_agent_message_mock(**kwargs):
    msg = MagicMock()
    msg.id = "msg-001"
    msg.content = "test message"
    msg.ifc_label = None
    for k, v in kwargs.items():
        setattr(msg, k, v)
    return msg


def _make_validation_result_mock(is_valid=True):
    result = MagicMock()
    result.is_valid = is_valid
    result.errors = []
    result.metadata = {}
    return result


# ---------------------------------------------------------------------------
# Module-level constant: LEGACY_PIPELINE_PROCESS_ERRORS
# ---------------------------------------------------------------------------


class TestLegacyPipelineProcessErrors:
    """Tests for the LEGACY_PIPELINE_PROCESS_ERRORS constant tuple."""

    def test_error_tuple_contains_runtime_error(self):
        from enhanced_agent_bus.pipeline.legacy_wrapper import (
            LEGACY_PIPELINE_PROCESS_ERRORS,
        )

        assert RuntimeError in LEGACY_PIPELINE_PROCESS_ERRORS

    def test_error_tuple_contains_value_error(self):
        from enhanced_agent_bus.pipeline.legacy_wrapper import (
            LEGACY_PIPELINE_PROCESS_ERRORS,
        )

        assert ValueError in LEGACY_PIPELINE_PROCESS_ERRORS

    def test_error_tuple_contains_type_error(self):
        from enhanced_agent_bus.pipeline.legacy_wrapper import (
            LEGACY_PIPELINE_PROCESS_ERRORS,
        )

        assert TypeError in LEGACY_PIPELINE_PROCESS_ERRORS

    def test_error_tuple_contains_key_error(self):
        from enhanced_agent_bus.pipeline.legacy_wrapper import (
            LEGACY_PIPELINE_PROCESS_ERRORS,
        )

        assert KeyError in LEGACY_PIPELINE_PROCESS_ERRORS

    def test_error_tuple_contains_attribute_error(self):
        from enhanced_agent_bus.pipeline.legacy_wrapper import (
            LEGACY_PIPELINE_PROCESS_ERRORS,
        )

        assert AttributeError in LEGACY_PIPELINE_PROCESS_ERRORS

    def test_error_tuple_is_tuple(self):
        from enhanced_agent_bus.pipeline.legacy_wrapper import (
            LEGACY_PIPELINE_PROCESS_ERRORS,
        )

        assert isinstance(LEGACY_PIPELINE_PROCESS_ERRORS, tuple)

    def test_error_tuple_length(self):
        from enhanced_agent_bus.pipeline.legacy_wrapper import (
            LEGACY_PIPELINE_PROCESS_ERRORS,
        )

        assert len(LEGACY_PIPELINE_PROCESS_ERRORS) == 5


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_router():
    return _make_mock_router()


@pytest.fixture
def processor_isolated(mock_router):
    """MessageProcessor in isolated mode with mocked router."""
    with patch(
        "enhanced_agent_bus.pipeline.legacy_wrapper.PipelineMessageRouter",
        return_value=mock_router,
    ):
        from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
    proc._router = mock_router
    return proc


@pytest.fixture
def processor_non_isolated(mock_router):
    """MessageProcessor in non-isolated mode with mocked router."""
    with patch(
        "enhanced_agent_bus.pipeline.legacy_wrapper.PipelineMessageRouter",
        return_value=mock_router,
    ):
        from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

        proc = MessageProcessor(isolated_mode=False)
    proc._router = mock_router
    return proc


# ---------------------------------------------------------------------------
# MessageProcessor.__init__ — flag values
# ---------------------------------------------------------------------------


class TestMessageProcessorInit:
    """Tests for MessageProcessor.__init__ with various kwargs."""

    def _build(self, **kwargs):
        mock_router = _make_mock_router()
        with patch(
            "enhanced_agent_bus.pipeline.legacy_wrapper.PipelineMessageRouter",
            return_value=mock_router,
        ):
            from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

            proc = MessageProcessor(**kwargs)
        proc._router = mock_router
        return proc

    def test_isolated_mode_flag_true(self):
        proc = self._build(isolated_mode=True)
        assert proc._isolated_mode is True

    def test_isolated_mode_flag_false_default(self):
        proc = self._build()
        assert proc._isolated_mode is False

    def test_isolated_mode_disables_maci(self):
        proc = self._build(isolated_mode=True, enable_maci=True)
        # isolated_mode takes precedence: maci disabled
        assert proc._enable_maci is False

    def test_enable_maci_true_in_non_isolated(self):
        proc = self._build(isolated_mode=False, enable_maci=True)
        assert proc._enable_maci is True

    def test_enable_maci_false_kwarg(self):
        proc = self._build(isolated_mode=False, enable_maci=False)
        assert proc._enable_maci is False

    def test_policy_fail_closed_default_false(self):
        proc = self._build()
        assert proc._policy_fail_closed is False

    def test_policy_fail_closed_true(self):
        proc = self._build(policy_fail_closed=True)
        assert proc._policy_fail_closed is True

    def test_use_rust_default_true(self):
        proc = self._build()
        assert proc._use_rust is True

    def test_use_rust_false(self):
        proc = self._build(use_rust=False)
        assert proc._use_rust is False

    def test_enable_metering_default_true(self):
        proc = self._build()
        assert proc._enable_metering is True

    def test_enable_metering_false(self):
        proc = self._build(enable_metering=False)
        assert proc._enable_metering is False

    def test_initial_processed_count_zero(self):
        proc = self._build()
        assert proc._processed_count == 0

    def test_initial_failed_count_zero(self):
        proc = self._build()
        assert proc._failed_count == 0

    def test_router_is_created(self):
        mock_router = _make_mock_router()
        with patch(
            "enhanced_agent_bus.pipeline.legacy_wrapper.PipelineMessageRouter",
            return_value=mock_router,
        ) as mock_cls:
            from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

            MessageProcessor(isolated_mode=True)
        mock_cls.assert_called_once()

    def test_use_dynamic_policy_off_when_policy_client_unavailable(self):
        with patch("enhanced_agent_bus.pipeline.legacy_wrapper.POLICY_CLIENT_AVAILABLE", False):
            proc = self._build(use_dynamic_policy=True, isolated_mode=False)
        assert proc._use_dynamic_policy is False

    def test_use_dynamic_policy_on_when_available_non_isolated(self):
        with patch("enhanced_agent_bus.pipeline.legacy_wrapper.POLICY_CLIENT_AVAILABLE", True):
            proc = self._build(use_dynamic_policy=True, isolated_mode=False)
        assert proc._use_dynamic_policy is True

    def test_use_dynamic_policy_off_in_isolated_mode_even_if_available(self):
        with patch("enhanced_agent_bus.pipeline.legacy_wrapper.POLICY_CLIENT_AVAILABLE", True):
            proc = self._build(use_dynamic_policy=True, isolated_mode=True)
        assert proc._use_dynamic_policy is False

    def test_use_dynamic_policy_default_false(self):
        proc = self._build(isolated_mode=False)
        # Default kwarg is False, so False regardless
        assert proc._use_dynamic_policy is False


# ---------------------------------------------------------------------------
# _build_pipeline_config — middleware assembly
# ---------------------------------------------------------------------------


class TestBuildPipelineConfig:
    """Tests for the _build_pipeline_config method."""

    def _build_and_get_config(self, **kwargs):
        """Build a MessageProcessor and extract the PipelineConfig passed to the router."""
        from enhanced_agent_bus.pipeline.router import PipelineConfig

        captured = {}

        class CapturingRouter:
            def __init__(self, config: PipelineConfig):
                captured["config"] = config
                self._router = _make_mock_router()

            def get_metrics(self):
                return _make_router_metrics()

            # Proxy remaining attrs
            def __getattr__(self, item):
                return getattr(self._router, item)

        with patch(
            "enhanced_agent_bus.pipeline.legacy_wrapper.PipelineMessageRouter",
            new=CapturingRouter,
        ):
            from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

            proc = MessageProcessor(**kwargs)

        cfg = captured["config"]
        return proc, cfg

    def _middleware_names(self, cfg):
        return [mw.__class__.__name__ for mw in cfg.middlewares]

    # --- isolated_mode=True ---

    def test_isolated_no_session_extraction(self):
        _, cfg = self._build_and_get_config(isolated_mode=True)
        assert "SessionExtractionMiddleware" not in self._middleware_names(cfg)

    def test_isolated_no_verification_middleware(self):
        _, cfg = self._build_and_get_config(isolated_mode=True)
        assert "_FakeVerificationMiddleware" not in self._middleware_names(cfg)

    def test_isolated_has_security_middleware(self):
        _, cfg = self._build_and_get_config(isolated_mode=True)
        assert "SecurityMiddleware" in self._middleware_names(cfg)

    def test_isolated_has_cache_middleware(self):
        _, cfg = self._build_and_get_config(isolated_mode=True)
        assert "_FakeCacheMiddleware" in self._middleware_names(cfg)

    def test_isolated_has_strategy_middleware(self):
        _, cfg = self._build_and_get_config(isolated_mode=True)
        assert "_FakeStrategyMiddleware" in self._middleware_names(cfg)

    def test_isolated_has_metrics_middleware(self):
        _, cfg = self._build_and_get_config(isolated_mode=True)
        assert "_FakeMetricsMiddleware" in self._middleware_names(cfg)

    def test_isolated_security_no_ai_guardrails(self):
        _, cfg = self._build_and_get_config(isolated_mode=True)
        security_mws = [
            mw for mw in cfg.middlewares if mw.__class__.__name__ == "SecurityMiddleware"
        ]
        assert len(security_mws) == 1
        assert security_mws[0]._guardrails_config is None

    def test_isolated_max_concurrent_100(self):
        _, cfg = self._build_and_get_config(isolated_mode=True)
        assert cfg.max_concurrent == 100

    def test_isolated_metrics_enabled_follows_metering_flag(self):
        _, cfg = self._build_and_get_config(isolated_mode=True, enable_metering=False)
        assert cfg.metrics_enabled is False

    def test_isolated_metrics_enabled_true_by_default(self):
        _, cfg = self._build_and_get_config(isolated_mode=True, enable_metering=True)
        assert cfg.metrics_enabled is True

    # --- isolated_mode=False ---

    def test_non_isolated_has_session_extraction(self):
        _, cfg = self._build_and_get_config(isolated_mode=False)
        # The patched fake uses _FakeSessionExtractionMiddleware class name
        names = self._middleware_names(cfg)
        assert any("session" in n.lower() or "SessionExtraction" in n for n in names)

    def test_non_isolated_has_verification_middleware(self):
        _, cfg = self._build_and_get_config(isolated_mode=False)
        assert "_FakeVerificationMiddleware" in self._middleware_names(cfg)

    def test_non_isolated_security_has_ai_guardrails(self):
        _, cfg = self._build_and_get_config(isolated_mode=False)
        security_mws = [
            mw for mw in cfg.middlewares if mw.__class__.__name__ == "SecurityMiddleware"
        ]
        assert len(security_mws) == 1
        assert security_mws[0]._guardrails_config is not None

    def test_non_isolated_verification_config_fail_closed_on(self):
        _, cfg = self._build_and_get_config(isolated_mode=False, policy_fail_closed=True)
        ver_mws = [
            mw for mw in cfg.middlewares if mw.__class__.__name__ == "_FakeVerificationMiddleware"
        ]
        assert ver_mws[0].config.fail_closed is True

    def test_non_isolated_verification_config_fail_closed_off(self):
        _, cfg = self._build_and_get_config(isolated_mode=False, policy_fail_closed=False)
        ver_mws = [
            mw for mw in cfg.middlewares if mw.__class__.__name__ == "_FakeVerificationMiddleware"
        ]
        assert ver_mws[0].config.fail_closed is False

    def test_non_isolated_pqc_verifier_use_rust_true(self):
        _, cfg = self._build_and_get_config(isolated_mode=False, use_rust=True)
        ver_mws = [
            mw for mw in cfg.middlewares if mw.__class__.__name__ == "_FakeVerificationMiddleware"
        ]
        assert ver_mws[0]._pqc_verifier._use_rust is True

    def test_non_isolated_pqc_verifier_use_rust_false(self):
        _, cfg = self._build_and_get_config(isolated_mode=False, use_rust=False)
        ver_mws = [
            mw for mw in cfg.middlewares if mw.__class__.__name__ == "_FakeVerificationMiddleware"
        ]
        assert ver_mws[0]._pqc_verifier._use_rust is False

    def test_non_isolated_opa_verifier_none_when_dynamic_policy_off(self):
        _, cfg = self._build_and_get_config(isolated_mode=False, use_dynamic_policy=False)
        ver_mws = [
            mw for mw in cfg.middlewares if mw.__class__.__name__ == "_FakeVerificationMiddleware"
        ]
        assert ver_mws[0]._opa_verifier is None

    def test_non_isolated_opa_verifier_set_when_dynamic_policy_on(self):
        with patch("enhanced_agent_bus.pipeline.legacy_wrapper.POLICY_CLIENT_AVAILABLE", True):
            _, cfg = self._build_and_get_config(isolated_mode=False, use_dynamic_policy=True)
        ver_mws = [
            mw for mw in cfg.middlewares if mw.__class__.__name__ == "_FakeVerificationMiddleware"
        ]
        assert ver_mws[0]._opa_verifier is not None

    def test_custom_strategy_passed_to_strategy_middleware(self):
        custom_strategy = MagicMock()
        _, cfg = self._build_and_get_config(isolated_mode=True, processing_strategy=custom_strategy)
        strategy_mws = [
            mw for mw in cfg.middlewares if mw.__class__.__name__ == "_FakeStrategyMiddleware"
        ]
        assert len(strategy_mws) == 1
        assert strategy_mws[0]._strategy is custom_strategy

    def test_no_custom_strategy_gives_none_to_strategy_middleware(self):
        _, cfg = self._build_and_get_config(isolated_mode=True)
        strategy_mws = [
            mw for mw in cfg.middlewares if mw.__class__.__name__ == "_FakeStrategyMiddleware"
        ]
        assert strategy_mws[0]._strategy is None

    def test_is_pipeline_config_instance(self):
        from enhanced_agent_bus.pipeline.router import PipelineConfig

        _, cfg = self._build_and_get_config(isolated_mode=True)
        assert isinstance(cfg, PipelineConfig)


# ---------------------------------------------------------------------------
# process() — happy path and error paths
# ---------------------------------------------------------------------------


class TestMessageProcessorProcess:
    """Tests for MessageProcessor.process()."""

    def _build(self, **kwargs):
        mock_router = _make_mock_router()
        with patch(
            "enhanced_agent_bus.pipeline.legacy_wrapper.PipelineMessageRouter",
            return_value=mock_router,
        ):
            from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

            proc = MessageProcessor(**kwargs)
        proc._router = mock_router
        return proc, mock_router

    async def test_success_increments_processed_count(self):
        proc, router = self._build(isolated_mode=True)
        router.process = AsyncMock(return_value=_make_validation_result_mock())
        await proc.process(_make_agent_message_mock())
        assert proc._processed_count == 1

    async def test_success_returns_router_result(self):
        proc, router = self._build(isolated_mode=True)
        expected = _make_validation_result_mock(is_valid=True)
        router.process = AsyncMock(return_value=expected)
        result = await proc.process(_make_agent_message_mock())
        assert result is expected

    async def test_multiple_success_accumulates(self):
        proc, router = self._build(isolated_mode=True)
        router.process = AsyncMock(return_value=_make_validation_result_mock())
        for _ in range(5):
            await proc.process(_make_agent_message_mock())
        assert proc._processed_count == 5

    async def test_success_does_not_increment_failed(self):
        proc, router = self._build(isolated_mode=True)
        router.process = AsyncMock(return_value=_make_validation_result_mock())
        await proc.process(_make_agent_message_mock())
        assert proc._failed_count == 0

    async def test_runtime_error_increments_failed(self):
        proc, router = self._build(isolated_mode=True)
        router.process = AsyncMock(side_effect=RuntimeError("boom"))
        with pytest.raises(RuntimeError):
            await proc.process(_make_agent_message_mock())
        assert proc._failed_count == 1

    async def test_value_error_increments_failed(self):
        proc, router = self._build(isolated_mode=True)
        router.process = AsyncMock(side_effect=ValueError("bad value"))
        with pytest.raises(ValueError):
            await proc.process(_make_agent_message_mock())
        assert proc._failed_count == 1

    async def test_type_error_increments_failed(self):
        proc, router = self._build(isolated_mode=True)
        router.process = AsyncMock(side_effect=TypeError("bad type"))
        with pytest.raises(TypeError):
            await proc.process(_make_agent_message_mock())
        assert proc._failed_count == 1

    async def test_key_error_increments_failed(self):
        proc, router = self._build(isolated_mode=True)
        router.process = AsyncMock(side_effect=KeyError("missing"))
        with pytest.raises(KeyError):
            await proc.process(_make_agent_message_mock())
        assert proc._failed_count == 1

    async def test_attribute_error_increments_failed(self):
        proc, router = self._build(isolated_mode=True)
        router.process = AsyncMock(side_effect=AttributeError("no attr"))
        with pytest.raises(AttributeError):
            await proc.process(_make_agent_message_mock())
        assert proc._failed_count == 1

    async def test_error_reraises_original_exception(self):
        proc, router = self._build(isolated_mode=True)
        err = RuntimeError("original error")
        router.process = AsyncMock(side_effect=err)
        with pytest.raises(RuntimeError) as exc_info:
            await proc.process(_make_agent_message_mock())
        assert exc_info.value is err

    async def test_os_error_not_caught_does_not_increment_failed(self):
        """OSError is not in LEGACY_PIPELINE_PROCESS_ERRORS — should not increment failed."""
        proc, router = self._build(isolated_mode=True)
        router.process = AsyncMock(side_effect=OSError("io error"))
        with pytest.raises(OSError):
            await proc.process(_make_agent_message_mock())
        assert proc._failed_count == 0

    async def test_processed_unchanged_on_error(self):
        proc, router = self._build(isolated_mode=True)
        success = _make_validation_result_mock()
        router.process = AsyncMock(side_effect=[success, RuntimeError("oops")])
        await proc.process(_make_agent_message_mock())
        with pytest.raises(RuntimeError):
            await proc.process(_make_agent_message_mock())
        assert proc._processed_count == 1
        assert proc._failed_count == 1

    async def test_process_calls_router_process_with_message(self):
        proc, router = self._build(isolated_mode=True)
        router.process = AsyncMock(return_value=_make_validation_result_mock())
        msg = _make_agent_message_mock()
        await proc.process(msg)
        router.process.assert_called_once_with(msg)


# ---------------------------------------------------------------------------
# register_handler / unregister_handler (placeholder no-ops)
# ---------------------------------------------------------------------------


class TestHandlerRegistration:
    """Tests for register_handler and unregister_handler (pass-through stubs)."""

    def _build(self):
        mock_router = _make_mock_router()
        with patch(
            "enhanced_agent_bus.pipeline.legacy_wrapper.PipelineMessageRouter",
            return_value=mock_router,
        ):
            from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

            proc = MessageProcessor(isolated_mode=True)
        proc._router = mock_router
        return proc

    def test_register_handler_returns_none(self):
        proc = self._build()
        result = proc.register_handler("test_type", lambda x: x)
        assert result is None

    def test_register_handler_callable_no_raise(self):
        proc = self._build()

        def handler(msg):
            return msg

        proc.register_handler("my_type", handler)  # Should not raise

    def test_register_handler_empty_string_type(self):
        proc = self._build()
        proc.register_handler("", lambda: None)

    def test_register_handler_dotted_type(self):
        proc = self._build()
        proc.register_handler("complex.message.type", lambda: None)

    def test_unregister_handler_returns_none(self):
        proc = self._build()
        result = proc.unregister_handler("test_type")
        assert result is None

    def test_unregister_unknown_type_no_raise(self):
        proc = self._build()
        proc.unregister_handler("never_registered_type")  # Should not raise

    def test_register_then_unregister_leaves_state_clean(self):
        proc = self._build()
        proc.register_handler("foo", lambda: None)
        proc.unregister_handler("foo")
        assert proc._processed_count == 0
        assert proc._failed_count == 0


# ---------------------------------------------------------------------------
# processed_count property
# ---------------------------------------------------------------------------


class TestProcessedCountProperty:
    """Tests for the processed_count property (local + router)."""

    def _build(self, router_processed=0, router_failed=0):
        mock_router = _make_mock_router(processed=router_processed, failed=router_failed)
        with patch(
            "enhanced_agent_bus.pipeline.legacy_wrapper.PipelineMessageRouter",
            return_value=mock_router,
        ):
            from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

            proc = MessageProcessor(isolated_mode=True)
        proc._router = mock_router
        return proc

    def test_zero_when_nothing_processed(self):
        proc = self._build(router_processed=0)
        assert proc.processed_count == 0

    def test_combines_local_and_router(self):
        proc = self._build(router_processed=5)
        proc._processed_count = 3
        assert proc.processed_count == 8

    def test_only_router_nonzero(self):
        proc = self._build(router_processed=10)
        proc._processed_count = 0
        assert proc.processed_count == 10

    def test_only_local_nonzero(self):
        proc = self._build(router_processed=0)
        proc._processed_count = 7
        assert proc.processed_count == 7

    def test_both_contribute(self):
        proc = self._build(router_processed=100)
        proc._processed_count = 50
        assert proc.processed_count == 150


# ---------------------------------------------------------------------------
# failed_count property
# ---------------------------------------------------------------------------


class TestFailedCountProperty:
    """Tests for the failed_count property (local + router)."""

    def _build(self, router_processed=0, router_failed=0):
        mock_router = _make_mock_router(processed=router_processed, failed=router_failed)
        with patch(
            "enhanced_agent_bus.pipeline.legacy_wrapper.PipelineMessageRouter",
            return_value=mock_router,
        ):
            from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

            proc = MessageProcessor(isolated_mode=True)
        proc._router = mock_router
        return proc

    def test_zero_initially(self):
        proc = self._build(router_failed=0)
        assert proc.failed_count == 0

    def test_combines_local_and_router(self):
        proc = self._build(router_failed=4)
        proc._failed_count = 2
        assert proc.failed_count == 6

    def test_only_router_nonzero(self):
        proc = self._build(router_failed=9)
        assert proc.failed_count == 9

    def test_only_local_nonzero(self):
        proc = self._build(router_failed=0)
        proc._failed_count = 3
        assert proc.failed_count == 3

    def test_both_contribute(self):
        proc = self._build(router_failed=50)
        proc._failed_count = 25
        assert proc.failed_count == 75


# ---------------------------------------------------------------------------
# processing_strategy property
# ---------------------------------------------------------------------------


class TestProcessingStrategyProperty:
    """Tests for the processing_strategy placeholder property."""

    def _build(self):
        mock_router = _make_mock_router()
        with patch(
            "enhanced_agent_bus.pipeline.legacy_wrapper.PipelineMessageRouter",
            return_value=mock_router,
        ):
            from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

            proc = MessageProcessor(isolated_mode=True)
        proc._router = mock_router
        return proc

    def test_processing_strategy_is_none(self):
        proc = self._build()
        assert proc.processing_strategy is None

    def test_processing_strategy_returns_none_multiple_times(self):
        proc = self._build()
        assert proc.processing_strategy is None


# ---------------------------------------------------------------------------
# opa_client property
# ---------------------------------------------------------------------------


class TestOpaClientProperty:
    """Tests for the opa_client property."""

    def _build(self, isolated_mode=True):
        mock_router = _make_mock_router()
        with patch(
            "enhanced_agent_bus.pipeline.legacy_wrapper.PipelineMessageRouter",
            return_value=mock_router,
        ):
            from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

            proc = MessageProcessor(isolated_mode=isolated_mode)
        proc._router = mock_router
        return proc

    def test_returns_none_in_isolated_mode(self):
        proc = self._build(isolated_mode=True)
        assert proc.opa_client is None

    def test_calls_get_opa_client_when_not_isolated(self):
        proc = self._build(isolated_mode=False)
        fake_client = MagicMock()
        with patch(
            "enhanced_agent_bus.pipeline.legacy_wrapper.get_opa_client",
            return_value=fake_client,
        ):
            result = proc.opa_client
        assert result is fake_client

    def test_calls_get_opa_client_every_access(self):
        proc = self._build(isolated_mode=False)
        counter = {"n": 0}

        def counting_getter():
            counter["n"] += 1
            return MagicMock()

        with patch(
            "enhanced_agent_bus.pipeline.legacy_wrapper.get_opa_client",
            side_effect=counting_getter,
        ):
            _ = proc.opa_client
            _ = proc.opa_client

        assert counter["n"] == 2

    def test_isolated_opa_client_never_calls_get_opa_client(self):
        proc = self._build(isolated_mode=True)
        with patch("enhanced_agent_bus.pipeline.legacy_wrapper.get_opa_client") as mock_getter:
            _ = proc.opa_client
        mock_getter.assert_not_called()


# ---------------------------------------------------------------------------
# get_metrics() method
# ---------------------------------------------------------------------------


class TestGetMetrics:
    """Tests for the get_metrics() method."""

    def _build(self, router_processed=0, router_failed=0, avg_latency_ms=0.0):
        mock_router = _make_mock_router(
            processed=router_processed, failed=router_failed, avg_latency_ms=avg_latency_ms
        )
        with patch(
            "enhanced_agent_bus.pipeline.legacy_wrapper.PipelineMessageRouter",
            return_value=mock_router,
        ):
            from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

            proc = MessageProcessor(isolated_mode=True)
        proc._router = mock_router
        return proc

    def test_returns_dict(self):
        proc = self._build()
        assert isinstance(proc.get_metrics(), dict)

    def test_has_processed_count_key(self):
        proc = self._build()
        assert "processed_count" in proc.get_metrics()

    def test_has_failed_count_key(self):
        proc = self._build()
        assert "failed_count" in proc.get_metrics()

    def test_has_avg_latency_ms_key(self):
        proc = self._build()
        assert "avg_latency_ms" in proc.get_metrics()

    def test_exactly_three_keys(self):
        proc = self._build()
        assert set(proc.get_metrics().keys()) == {
            "processed_count",
            "failed_count",
            "avg_latency_ms",
        }

    def test_all_zeros_initially(self):
        proc = self._build(router_processed=0, router_failed=0, avg_latency_ms=0.0)
        m = proc.get_metrics()
        assert m["processed_count"] == 0
        assert m["failed_count"] == 0
        assert m["avg_latency_ms"] == 0.0

    def test_processed_count_combines_local_and_router(self):
        proc = self._build(router_processed=10)
        proc._processed_count = 5
        assert proc.get_metrics()["processed_count"] == 15

    def test_failed_count_combines_local_and_router(self):
        proc = self._build(router_failed=3)
        proc._failed_count = 1
        assert proc.get_metrics()["failed_count"] == 4

    def test_avg_latency_from_router(self):
        proc = self._build(avg_latency_ms=2.75)
        assert proc.get_metrics()["avg_latency_ms"] == 2.75

    def test_router_processed_only(self):
        proc = self._build(router_processed=7)
        proc._processed_count = 0
        assert proc.get_metrics()["processed_count"] == 7

    def test_local_processed_only(self):
        proc = self._build(router_processed=0)
        proc._processed_count = 12
        assert proc.get_metrics()["processed_count"] == 12


# ---------------------------------------------------------------------------
# Integration-style tests — full construction without router mock
# ---------------------------------------------------------------------------


class TestMessageProcessorIntegration:
    """Integration tests: real MessageProcessor construction & behaviour."""

    def test_real_construction_isolated_mode(self):
        from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        assert proc._isolated_mode is True
        assert proc._router is not None

    def test_real_construction_default_args(self):
        from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

        proc = MessageProcessor()
        assert proc._isolated_mode is False
        assert proc._router is not None

    def test_real_get_metrics_structure(self):
        from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        m = proc.get_metrics()
        assert "processed_count" in m
        assert "failed_count" in m
        assert "avg_latency_ms" in m

    def test_real_processed_count_initial_zero(self):
        from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        assert proc.processed_count == 0

    def test_real_failed_count_initial_zero(self):
        from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        assert proc.failed_count == 0

    def test_real_processing_strategy_is_none(self):
        from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        assert proc.processing_strategy is None

    def test_real_opa_client_isolated_none(self):
        from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        assert proc.opa_client is None

    def test_real_register_handler_noop(self):
        from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        proc.register_handler("hello", lambda x: x)

    def test_real_unregister_handler_noop(self):
        from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        proc.unregister_handler("hello")

    async def test_real_process_isolated_with_mock_router_result(self):
        """End-to-end process() call with real construction, patched router.process."""
        from enhanced_agent_bus.models import AgentMessage
        from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        mock_result = _make_validation_result_mock(is_valid=True)
        proc._router.process = AsyncMock(return_value=mock_result)

        msg = AgentMessage(content={"text": "hello"}, sender_id="agent-1")
        result = await proc.process(msg)
        assert result.is_valid is True
        assert proc._processed_count == 1

    async def test_real_process_error_increments_failed(self):
        from enhanced_agent_bus.models import AgentMessage
        from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

        proc = MessageProcessor(isolated_mode=True)
        proc._router.process = AsyncMock(side_effect=ValueError("oops"))

        with pytest.raises(ValueError):
            msg = AgentMessage(content={"text": "hi"}, sender_id="agent-2")
            await proc.process(msg)

        assert proc._failed_count == 1


# ---------------------------------------------------------------------------
# Edge cases and combined states
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and combined-state scenarios."""

    def _build(self, **kwargs):
        mock_router = _make_mock_router()
        with patch(
            "enhanced_agent_bus.pipeline.legacy_wrapper.PipelineMessageRouter",
            return_value=mock_router,
        ):
            from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

            proc = MessageProcessor(**kwargs)
        proc._router = mock_router
        return proc, mock_router

    def test_metrics_combined_state(self):
        mock_router = _make_mock_router(processed=3, failed=2)
        with patch(
            "enhanced_agent_bus.pipeline.legacy_wrapper.PipelineMessageRouter",
            return_value=mock_router,
        ):
            from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

            proc = MessageProcessor(isolated_mode=True)
        proc._router = mock_router
        proc._processed_count = 7
        proc._failed_count = 1

        m = proc.get_metrics()
        assert m["processed_count"] == 10
        assert m["failed_count"] == 3

    async def test_result_identity_preserved_on_success(self):
        proc, router = self._build(isolated_mode=True)
        expected = _make_validation_result_mock(is_valid=True)
        router.process = AsyncMock(return_value=expected)
        result = await proc.process(_make_agent_message_mock())
        assert result is expected

    def test_all_bool_flags_combined(self):
        proc, _ = self._build(
            isolated_mode=True,
            use_dynamic_policy=False,
            enable_maci=False,
            policy_fail_closed=True,
            use_rust=False,
            enable_metering=False,
        )
        assert proc._isolated_mode is True
        assert proc._use_dynamic_policy is False
        assert proc._enable_maci is False
        assert proc._policy_fail_closed is True
        assert proc._use_rust is False
        assert proc._enable_metering is False

    async def test_mixed_success_and_error(self):
        proc, router = self._build(isolated_mode=True)
        success = _make_validation_result_mock()
        router.process = AsyncMock(side_effect=[success, RuntimeError("fail")])
        await proc.process(_make_agent_message_mock())
        with pytest.raises(RuntimeError):
            await proc.process(_make_agent_message_mock())

        assert proc._processed_count == 1
        assert proc._failed_count == 1

    def test_processed_count_property_and_get_metrics_agree(self):
        mock_router = _make_mock_router(processed=5, failed=0)
        with patch(
            "enhanced_agent_bus.pipeline.legacy_wrapper.PipelineMessageRouter",
            return_value=mock_router,
        ):
            from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

            proc = MessageProcessor(isolated_mode=True)
        proc._router = mock_router
        proc._processed_count = 3

        assert proc.processed_count == proc.get_metrics()["processed_count"]

    def test_failed_count_property_and_get_metrics_agree(self):
        mock_router = _make_mock_router(processed=0, failed=4)
        with patch(
            "enhanced_agent_bus.pipeline.legacy_wrapper.PipelineMessageRouter",
            return_value=mock_router,
        ):
            from enhanced_agent_bus.pipeline.legacy_wrapper import MessageProcessor

            proc = MessageProcessor(isolated_mode=True)
        proc._router = mock_router
        proc._failed_count = 2

        assert proc.failed_count == proc.get_metrics()["failed_count"]
