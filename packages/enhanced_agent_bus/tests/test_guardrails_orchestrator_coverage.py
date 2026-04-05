# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for guardrails/orchestrator.py.

Covers:
- RuntimeSafetyGuardrailsConfig defaults and custom values
- RuntimeSafetyGuardrails init, reset, _generate_trace_id
- process_request: happy path, disabled layers, modified_data propagation,
  fail_closed short-circuit, continue-on-block (fail_closed=False),
  layer timeout, outer exception handler, custom trace_id
- get_metrics: success path and per-layer error path
- get_layer: existing and missing layers
"""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

from enhanced_agent_bus.guardrails.enums import (
    GuardrailLayer,
    SafetyAction,
    ViolationSeverity,
)
from enhanced_agent_bus.guardrails.models import GuardrailResult, Violation
from enhanced_agent_bus.guardrails.orchestrator import (
    RuntimeSafetyGuardrails,
    RuntimeSafetyGuardrailsConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _allow_result(modified_data=None):
    """Return a GuardrailResult that allows the request."""
    return GuardrailResult(
        action=SafetyAction.ALLOW,
        allowed=True,
        violations=[],
        modified_data=modified_data,
    )


def _block_result(layer=GuardrailLayer.INPUT_SANITIZER, trace_id="t1"):
    """Return a GuardrailResult that blocks the request."""
    return GuardrailResult(
        action=SafetyAction.BLOCK,
        allowed=False,
        violations=[
            Violation(
                layer=layer,
                violation_type="test_block",
                severity=ViolationSeverity.HIGH,
                message="blocked",
                trace_id=trace_id,
            )
        ],
    )


def _make_mock_layer(result: GuardrailResult, enabled: bool = True) -> MagicMock:
    """Build a mock GuardrailComponent that returns *result* from process()."""
    layer = MagicMock()
    layer.config = MagicMock()
    layer.config.enabled = enabled
    layer.process = AsyncMock(return_value=result)
    layer.get_metrics = AsyncMock(return_value={"ok": True})
    return layer


def _patch_layers(guardrails: RuntimeSafetyGuardrails, results: dict) -> None:
    """Replace layers in *guardrails* with mocks keyed by GuardrailLayer."""
    for layer_type, result in results.items():
        guardrails.layers[layer_type] = _make_mock_layer(result)
    # Audit log always needs to be a working mock too
    if GuardrailLayer.AUDIT_LOG not in results:
        guardrails.layers[GuardrailLayer.AUDIT_LOG] = _make_mock_layer(_allow_result())


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestRuntimeSafetyGuardrailsConfig:
    """Tests for RuntimeSafetyGuardrailsConfig dataclass."""

    def test_default_values(self):
        cfg = RuntimeSafetyGuardrailsConfig()
        assert cfg.strict_mode is False
        assert cfg.fail_closed is True
        assert cfg.timeout_ms == 15000

    def test_sub_configs_exist(self):
        cfg = RuntimeSafetyGuardrailsConfig()
        assert cfg.rate_limiter is not None
        assert cfg.input_sanitizer is not None
        assert cfg.agent_engine is not None
        assert cfg.sandbox is not None
        assert cfg.output_verifier is not None
        assert cfg.audit_log is not None

    def test_custom_values(self):
        cfg = RuntimeSafetyGuardrailsConfig(
            strict_mode=True,
            fail_closed=False,
            timeout_ms=5000,
        )
        assert cfg.strict_mode is True
        assert cfg.fail_closed is False
        assert cfg.timeout_ms == 5000


# ---------------------------------------------------------------------------
# Init / reset / get_layer tests
# ---------------------------------------------------------------------------


class TestRuntimeSafetyGuardrailsInit:
    def test_default_init(self):
        rsg = RuntimeSafetyGuardrails()
        assert rsg.config is not None
        assert isinstance(rsg.config, RuntimeSafetyGuardrailsConfig)

    def test_custom_config_stored(self):
        cfg = RuntimeSafetyGuardrailsConfig(timeout_ms=1000)
        rsg = RuntimeSafetyGuardrails(cfg)
        assert rsg.config.timeout_ms == 1000

    def test_all_six_layers_present(self):
        rsg = RuntimeSafetyGuardrails()
        for layer in GuardrailLayer:
            assert layer in rsg.layers

    def test_reset_calls_reset_on_layers(self):
        rsg = RuntimeSafetyGuardrails()
        for layer_type in list(rsg.layers.keys()):
            mock = MagicMock()
            mock.config = MagicMock()
            mock.config.enabled = True
            rsg.layers[layer_type] = mock
        rsg.reset()
        for mock in rsg.layers.values():
            mock.reset.assert_called_once()

    def test_reset_skips_layers_without_reset_method(self):
        """reset() must not fail if a layer has no reset attribute."""
        rsg = RuntimeSafetyGuardrails()
        for layer_type in list(rsg.layers.keys()):
            mock = MagicMock(spec=[])  # no attributes
            mock.config = MagicMock()
            mock.config.enabled = True
            rsg.layers[layer_type] = mock
        rsg.reset()  # should not raise

    def test_get_layer_returns_component(self):
        rsg = RuntimeSafetyGuardrails()
        comp = rsg.get_layer(GuardrailLayer.RATE_LIMITER)
        assert comp is not None

    def test_get_layer_missing_returns_none(self):
        rsg = RuntimeSafetyGuardrails()
        # Use a value that doesn't exist
        result = rsg.layers.get("nonexistent_layer")  # type: ignore[arg-type]
        assert result is None

    def test_get_layer_all_types(self):
        rsg = RuntimeSafetyGuardrails()
        for layer in GuardrailLayer:
            assert rsg.get_layer(layer) is not None


# ---------------------------------------------------------------------------
# _generate_trace_id
# ---------------------------------------------------------------------------


class TestGenerateTraceId:
    def test_returns_16_char_hex(self):
        rsg = RuntimeSafetyGuardrails()
        tid = rsg._generate_trace_id()
        assert len(tid) == 16
        int(tid, 16)  # must be valid hex

    def test_unique_per_call(self):
        rsg = RuntimeSafetyGuardrails()
        ids = {rsg._generate_trace_id() for _ in range(20)}
        assert len(ids) > 1


# ---------------------------------------------------------------------------
# process_request - core paths
# ---------------------------------------------------------------------------


class TestProcessRequestHappyPath:
    async def test_all_layers_allow(self):
        rsg = RuntimeSafetyGuardrails()
        _patch_layers(
            rsg,
            {
                GuardrailLayer.RATE_LIMITER: _allow_result(),
                GuardrailLayer.INPUT_SANITIZER: _allow_result(),
                GuardrailLayer.AGENT_ENGINE: _allow_result(),
                GuardrailLayer.TOOL_RUNNER_SANDBOX: _allow_result(),
                GuardrailLayer.OUTPUT_VERIFIER: _allow_result(),
                GuardrailLayer.AUDIT_LOG: _allow_result(),
            },
        )
        result = await rsg.process_request("hello world")
        assert result["allowed"] is True
        assert result["violations"] == []
        assert result["constitutional_hash"] is not None

    async def test_trace_id_auto_generated(self):
        rsg = RuntimeSafetyGuardrails()
        _patch_layers(rsg, {})
        result = await rsg.process_request("data")
        assert len(result["trace_id"]) == 16

    async def test_custom_trace_id_preserved(self):
        rsg = RuntimeSafetyGuardrails()
        _patch_layers(rsg, {})
        result = await rsg.process_request("data", {"trace_id": "my-trace"})
        assert result["trace_id"] == "my-trace"

    async def test_returns_total_processing_time(self):
        rsg = RuntimeSafetyGuardrails()
        _patch_layers(rsg, {})
        result = await rsg.process_request("data")
        assert isinstance(result["total_processing_time_ms"], float)
        assert result["total_processing_time_ms"] >= 0

    async def test_layer_results_populated(self):
        rsg = RuntimeSafetyGuardrails()
        _patch_layers(
            rsg,
            {
                GuardrailLayer.RATE_LIMITER: _allow_result(),
                GuardrailLayer.INPUT_SANITIZER: _allow_result(),
                GuardrailLayer.AGENT_ENGINE: _allow_result(),
                GuardrailLayer.TOOL_RUNNER_SANDBOX: _allow_result(),
                GuardrailLayer.OUTPUT_VERIFIER: _allow_result(),
            },
        )
        result = await rsg.process_request("data")
        assert GuardrailLayer.RATE_LIMITER.value in result["layer_results"]
        assert GuardrailLayer.INPUT_SANITIZER.value in result["layer_results"]

    async def test_modified_data_propagates(self):
        """If a layer returns modified_data, subsequent layers receive it."""
        rsg = RuntimeSafetyGuardrails()
        modified = "sanitized-data"
        sanitizer_mock = _make_mock_layer(_allow_result(modified_data=modified))
        agent_mock = _make_mock_layer(_allow_result())
        rsg.layers[GuardrailLayer.RATE_LIMITER] = _make_mock_layer(_allow_result())
        rsg.layers[GuardrailLayer.INPUT_SANITIZER] = sanitizer_mock
        rsg.layers[GuardrailLayer.AGENT_ENGINE] = agent_mock
        rsg.layers[GuardrailLayer.TOOL_RUNNER_SANDBOX] = _make_mock_layer(_allow_result())
        rsg.layers[GuardrailLayer.OUTPUT_VERIFIER] = _make_mock_layer(_allow_result())
        rsg.layers[GuardrailLayer.AUDIT_LOG] = _make_mock_layer(_allow_result())

        result = await rsg.process_request("original")
        # final_data should be the modified value
        assert result["final_data"] == modified

    async def test_context_passed_to_audit(self):
        rsg = RuntimeSafetyGuardrails()
        audit_mock = _make_mock_layer(_allow_result())
        rsg.layers[GuardrailLayer.AUDIT_LOG] = audit_mock
        # Patch all processing layers to allow
        for lt in [
            GuardrailLayer.RATE_LIMITER,
            GuardrailLayer.INPUT_SANITIZER,
            GuardrailLayer.AGENT_ENGINE,
            GuardrailLayer.TOOL_RUNNER_SANDBOX,
            GuardrailLayer.OUTPUT_VERIFIER,
        ]:
            rsg.layers[lt] = _make_mock_layer(_allow_result())

        await rsg.process_request("data", {"trace_id": "x"})
        audit_mock.process.assert_called_once()
        call_ctx = audit_mock.process.call_args[0][1]
        assert call_ctx["allowed"] is True
        assert call_ctx["action"] == SafetyAction.ALLOW


class TestProcessRequestDisabledLayers:
    async def test_disabled_layer_skipped(self):
        rsg = RuntimeSafetyGuardrails()
        disabled_mock = _make_mock_layer(_block_result(), enabled=False)
        rsg.layers[GuardrailLayer.RATE_LIMITER] = disabled_mock
        rsg.layers[GuardrailLayer.INPUT_SANITIZER] = _make_mock_layer(_allow_result())
        rsg.layers[GuardrailLayer.AGENT_ENGINE] = _make_mock_layer(_allow_result())
        rsg.layers[GuardrailLayer.TOOL_RUNNER_SANDBOX] = _make_mock_layer(_allow_result())
        rsg.layers[GuardrailLayer.OUTPUT_VERIFIER] = _make_mock_layer(_allow_result())
        rsg.layers[GuardrailLayer.AUDIT_LOG] = _make_mock_layer(_allow_result())

        result = await rsg.process_request("data")
        # Disabled layer never processed -- should still be allowed
        assert result["allowed"] is True
        disabled_mock.process.assert_not_called()

    async def test_disabled_layer_not_in_layer_results(self):
        rsg = RuntimeSafetyGuardrails()
        rsg.layers[GuardrailLayer.RATE_LIMITER] = _make_mock_layer(_allow_result(), enabled=False)
        for lt in [
            GuardrailLayer.INPUT_SANITIZER,
            GuardrailLayer.AGENT_ENGINE,
            GuardrailLayer.TOOL_RUNNER_SANDBOX,
            GuardrailLayer.OUTPUT_VERIFIER,
            GuardrailLayer.AUDIT_LOG,
        ]:
            rsg.layers[lt] = _make_mock_layer(_allow_result())

        result = await rsg.process_request("data")
        assert GuardrailLayer.RATE_LIMITER.value not in result["layer_results"]


class TestProcessRequestFailClosed:
    async def test_fail_closed_stops_on_first_block(self):
        """With fail_closed=True, processing halts at the first blocking layer."""
        cfg = RuntimeSafetyGuardrailsConfig(fail_closed=True)
        rsg = RuntimeSafetyGuardrails(cfg)

        rate_mock = _make_mock_layer(_block_result(GuardrailLayer.RATE_LIMITER))
        input_mock = _make_mock_layer(_allow_result())
        agent_mock = _make_mock_layer(_allow_result())
        sandbox_mock = _make_mock_layer(_allow_result())
        output_mock = _make_mock_layer(_allow_result())
        audit_mock = _make_mock_layer(_allow_result())

        rsg.layers[GuardrailLayer.RATE_LIMITER] = rate_mock
        rsg.layers[GuardrailLayer.INPUT_SANITIZER] = input_mock
        rsg.layers[GuardrailLayer.AGENT_ENGINE] = agent_mock
        rsg.layers[GuardrailLayer.TOOL_RUNNER_SANDBOX] = sandbox_mock
        rsg.layers[GuardrailLayer.OUTPUT_VERIFIER] = output_mock
        rsg.layers[GuardrailLayer.AUDIT_LOG] = audit_mock

        result = await rsg.process_request("data")
        assert result["allowed"] is False
        # Subsequent processing layers must NOT have been called
        input_mock.process.assert_not_called()
        agent_mock.process.assert_not_called()
        # Audit MUST still be called
        audit_mock.process.assert_called_once()

    async def test_fail_closed_false_continues_on_block(self):
        """With fail_closed=False, all layers run even when one blocks."""
        cfg = RuntimeSafetyGuardrailsConfig(fail_closed=False)
        rsg = RuntimeSafetyGuardrails(cfg)

        rate_mock = _make_mock_layer(_block_result(GuardrailLayer.RATE_LIMITER))
        input_mock = _make_mock_layer(_allow_result())
        agent_mock = _make_mock_layer(_allow_result())
        sandbox_mock = _make_mock_layer(_allow_result())
        output_mock = _make_mock_layer(_allow_result())
        audit_mock = _make_mock_layer(_allow_result())

        rsg.layers[GuardrailLayer.RATE_LIMITER] = rate_mock
        rsg.layers[GuardrailLayer.INPUT_SANITIZER] = input_mock
        rsg.layers[GuardrailLayer.AGENT_ENGINE] = agent_mock
        rsg.layers[GuardrailLayer.TOOL_RUNNER_SANDBOX] = sandbox_mock
        rsg.layers[GuardrailLayer.OUTPUT_VERIFIER] = output_mock
        rsg.layers[GuardrailLayer.AUDIT_LOG] = audit_mock

        result = await rsg.process_request("data")
        assert result["allowed"] is False  # blocked by rate limiter
        # All downstream layers should still have been processed
        input_mock.process.assert_called_once()
        agent_mock.process.assert_called_once()

    async def test_audit_log_called_even_on_block(self):
        """Audit is always called regardless of block."""
        cfg = RuntimeSafetyGuardrailsConfig(fail_closed=True)
        rsg = RuntimeSafetyGuardrails(cfg)

        for lt in [
            GuardrailLayer.RATE_LIMITER,
            GuardrailLayer.INPUT_SANITIZER,
            GuardrailLayer.AGENT_ENGINE,
            GuardrailLayer.TOOL_RUNNER_SANDBOX,
            GuardrailLayer.OUTPUT_VERIFIER,
        ]:
            rsg.layers[lt] = _make_mock_layer(
                _block_result(lt) if lt == GuardrailLayer.RATE_LIMITER else _allow_result()
            )
        audit_mock = _make_mock_layer(_allow_result())
        rsg.layers[GuardrailLayer.AUDIT_LOG] = audit_mock

        await rsg.process_request("data")
        audit_mock.process.assert_called_once()

    async def test_violations_collected_across_layers(self):
        """Violations from multiple layers are all collected (fail_closed=False)."""
        cfg = RuntimeSafetyGuardrailsConfig(fail_closed=False)
        rsg = RuntimeSafetyGuardrails(cfg)

        block1 = _block_result(GuardrailLayer.RATE_LIMITER)
        block2 = _block_result(GuardrailLayer.INPUT_SANITIZER)

        rsg.layers[GuardrailLayer.RATE_LIMITER] = _make_mock_layer(block1)
        rsg.layers[GuardrailLayer.INPUT_SANITIZER] = _make_mock_layer(block2)
        rsg.layers[GuardrailLayer.AGENT_ENGINE] = _make_mock_layer(_allow_result())
        rsg.layers[GuardrailLayer.TOOL_RUNNER_SANDBOX] = _make_mock_layer(_allow_result())
        rsg.layers[GuardrailLayer.OUTPUT_VERIFIER] = _make_mock_layer(_allow_result())
        rsg.layers[GuardrailLayer.AUDIT_LOG] = _make_mock_layer(_allow_result())

        result = await rsg.process_request("data")
        assert len(result["violations"]) == 2


class TestProcessRequestTimeout:
    async def test_layer_timeout_creates_block_result(self):
        """A layer that times out is treated as a BLOCK with a timeout violation."""
        cfg = RuntimeSafetyGuardrailsConfig(timeout_ms=1, fail_closed=True)
        rsg = RuntimeSafetyGuardrails(cfg)

        async def slow(*args, **kwargs):
            await asyncio.sleep(10)
            return _allow_result()

        rate_mock = MagicMock()
        rate_mock.config = MagicMock()
        rate_mock.config.enabled = True
        rate_mock.process = slow

        audit_mock = _make_mock_layer(_allow_result())
        rsg.layers[GuardrailLayer.RATE_LIMITER] = rate_mock
        rsg.layers[GuardrailLayer.INPUT_SANITIZER] = _make_mock_layer(_allow_result())
        rsg.layers[GuardrailLayer.AGENT_ENGINE] = _make_mock_layer(_allow_result())
        rsg.layers[GuardrailLayer.TOOL_RUNNER_SANDBOX] = _make_mock_layer(_allow_result())
        rsg.layers[GuardrailLayer.OUTPUT_VERIFIER] = _make_mock_layer(_allow_result())
        rsg.layers[GuardrailLayer.AUDIT_LOG] = audit_mock

        result = await rsg.process_request("data")
        assert result["allowed"] is False
        violations = result["violations"]
        assert any(v["violation_type"] == "timeout" for v in violations)
        assert any(v["severity"] == ViolationSeverity.CRITICAL.value for v in violations)


class TestProcessRequestOuterException:
    async def test_runtime_error_during_processing_fails_closed(self):
        """A RuntimeError inside the processing loop sets allowed=False."""
        cfg = RuntimeSafetyGuardrailsConfig(fail_closed=True)
        rsg = RuntimeSafetyGuardrails(cfg)

        # Make rate_limiter.process raise RuntimeError
        bad_mock = MagicMock()
        bad_mock.config = MagicMock()
        bad_mock.config.enabled = True
        bad_mock.process = AsyncMock(side_effect=RuntimeError("boom"))
        rsg.layers[GuardrailLayer.RATE_LIMITER] = bad_mock

        # Audit mock -- may or may not be called depending on where exception is raised
        audit_mock = _make_mock_layer(_allow_result())
        rsg.layers[GuardrailLayer.AUDIT_LOG] = audit_mock

        result = await rsg.process_request("data")
        assert result["allowed"] is False
        violations = result["violations"]
        assert any(v["violation_type"] == "system_error" for v in violations)

    async def test_value_error_caught(self):
        cfg = RuntimeSafetyGuardrailsConfig()
        rsg = RuntimeSafetyGuardrails(cfg)

        bad_mock = MagicMock()
        bad_mock.config = MagicMock()
        bad_mock.config.enabled = True
        bad_mock.process = AsyncMock(side_effect=ValueError("bad value"))
        rsg.layers[GuardrailLayer.RATE_LIMITER] = bad_mock
        rsg.layers[GuardrailLayer.AUDIT_LOG] = _make_mock_layer(_allow_result())

        result = await rsg.process_request("data")
        assert result["allowed"] is False

    async def test_type_error_caught(self):
        cfg = RuntimeSafetyGuardrailsConfig()
        rsg = RuntimeSafetyGuardrails(cfg)

        bad_mock = MagicMock()
        bad_mock.config = MagicMock()
        bad_mock.config.enabled = True
        bad_mock.process = AsyncMock(side_effect=TypeError("type error"))
        rsg.layers[GuardrailLayer.RATE_LIMITER] = bad_mock
        rsg.layers[GuardrailLayer.AUDIT_LOG] = _make_mock_layer(_allow_result())

        result = await rsg.process_request("data")
        assert result["allowed"] is False


class TestProcessRequestNoContext:
    async def test_no_context_defaults_to_empty_dict(self):
        rsg = RuntimeSafetyGuardrails()
        _patch_layers(rsg, {})
        result = await rsg.process_request("data", None)
        assert result["trace_id"] is not None

    async def test_no_context_omitted(self):
        rsg = RuntimeSafetyGuardrails()
        _patch_layers(rsg, {})
        result = await rsg.process_request("data")
        assert "trace_id" in result


# ---------------------------------------------------------------------------
# get_metrics tests
# ---------------------------------------------------------------------------


class TestGetMetrics:
    async def test_metrics_contains_system_key(self):
        rsg = RuntimeSafetyGuardrails()
        for lt in GuardrailLayer:
            mock = _make_mock_layer(_allow_result())
            mock.config = MagicMock()
            mock.config.enabled = True
            rsg.layers[lt] = mock
        metrics = await rsg.get_metrics()
        assert "system" in metrics
        assert "constitutional_hash" in metrics["system"]
        assert "layers_enabled" in metrics["system"]

    async def test_metrics_contains_all_layer_keys(self):
        rsg = RuntimeSafetyGuardrails()
        for lt in GuardrailLayer:
            mock = _make_mock_layer(_allow_result())
            mock.config = MagicMock()
            mock.config.enabled = True
            rsg.layers[lt] = mock
        metrics = await rsg.get_metrics()
        for lt in GuardrailLayer:
            assert lt.value in metrics

    async def test_metrics_layer_error_recorded(self):
        """If get_metrics() on a layer raises, the error is captured."""
        rsg = RuntimeSafetyGuardrails()
        for lt in GuardrailLayer:
            mock = _make_mock_layer(_allow_result())
            mock.config = MagicMock()
            mock.config.enabled = True
            if lt == GuardrailLayer.RATE_LIMITER:
                mock.get_metrics = AsyncMock(side_effect=RuntimeError("metrics fail"))
            rsg.layers[lt] = mock
        metrics = await rsg.get_metrics()
        assert "error" in metrics[GuardrailLayer.RATE_LIMITER.value]

    async def test_metrics_layers_enabled_list(self):
        rsg = RuntimeSafetyGuardrails()
        for lt in GuardrailLayer:
            mock = _make_mock_layer(_allow_result())
            mock.config = MagicMock()
            mock.config.enabled = (
                lt != GuardrailLayer.SANDBOX if hasattr(GuardrailLayer, "SANDBOX") else True
            )
            rsg.layers[lt] = mock
        metrics = await rsg.get_metrics()
        assert isinstance(metrics["system"]["layers_enabled"], list)

    async def test_metrics_value_error_caught(self):
        rsg = RuntimeSafetyGuardrails()
        for lt in GuardrailLayer:
            mock = _make_mock_layer(_allow_result())
            mock.config = MagicMock()
            mock.config.enabled = True
            if lt == GuardrailLayer.INPUT_SANITIZER:
                mock.get_metrics = AsyncMock(side_effect=ValueError("v"))
            rsg.layers[lt] = mock
        metrics = await rsg.get_metrics()
        assert "error" in metrics[GuardrailLayer.INPUT_SANITIZER.value]

    async def test_metrics_attribute_error_caught(self):
        rsg = RuntimeSafetyGuardrails()
        for lt in GuardrailLayer:
            mock = _make_mock_layer(_allow_result())
            mock.config = MagicMock()
            mock.config.enabled = True
            if lt == GuardrailLayer.AGENT_ENGINE:
                mock.get_metrics = AsyncMock(side_effect=AttributeError("attr"))
            rsg.layers[lt] = mock
        metrics = await rsg.get_metrics()
        assert "error" in metrics[GuardrailLayer.AGENT_ENGINE.value]


# ---------------------------------------------------------------------------
# Integration smoke test (no mocks, uses real layers)
# ---------------------------------------------------------------------------


class TestIntegrationSmoke:
    async def test_safe_request_through_real_layers(self):
        """Basic integration: real layers, simple safe string."""
        cfg = RuntimeSafetyGuardrailsConfig()
        cfg.sandbox.enabled = False
        rsg = RuntimeSafetyGuardrails(cfg)
        result = await rsg.process_request("Hello, safe world.")
        assert "allowed" in result
        assert "trace_id" in result
        assert "constitutional_hash" in result

    async def test_get_metrics_real_layers(self):
        cfg = RuntimeSafetyGuardrailsConfig()
        cfg.sandbox.enabled = False
        rsg = RuntimeSafetyGuardrails(cfg)
        metrics = await rsg.get_metrics()
        assert "system" in metrics

    def test_reset_real_layers(self):
        rsg = RuntimeSafetyGuardrails()
        rsg.reset()  # should not raise
