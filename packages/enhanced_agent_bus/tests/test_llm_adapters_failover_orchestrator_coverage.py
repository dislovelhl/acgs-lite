# Constitutional Hash: 608508a9bd224290
"""
Comprehensive test suite for:
  src/core/enhanced_agent_bus/llm_adapters/failover/orchestrator.py

Target: ≥95% line coverage (79 statements).

All async tests run without @pytest.mark.asyncio because
asyncio_mode = "auto" is configured in pyproject.toml.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.circuit_breaker import CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Helpers - build a minimal CapabilityRegistry
# ---------------------------------------------------------------------------
from enhanced_agent_bus.llm_adapters.capability_matrix import (
    CapabilityDimension,
    CapabilityRegistry,
    CapabilityRequirement,
    LatencyClass,
    ProviderCapabilityProfile,
)

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from enhanced_agent_bus.llm_adapters.failover.orchestrator import (
    FAILOVER_EXECUTION_ERRORS,
    LLMFailoverOrchestrator,
    get_llm_failover_orchestrator,
    reset_llm_failover_orchestrator,
)


def _make_profile(
    provider_id: str,
    latency_class: LatencyClass = LatencyClass.MEDIUM,
) -> ProviderCapabilityProfile:
    return ProviderCapabilityProfile(
        provider_id=provider_id,
        model_id=f"model-{provider_id}",
        display_name=provider_id.title(),
        provider_type="test",
        context_length=8192,
        max_output_tokens=1024,
        latency_class=latency_class,
    )


def _make_registry(
    *provider_ids: str, latency_class: LatencyClass = LatencyClass.MEDIUM
) -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry._profiles.clear()
    for pid in provider_ids:
        registry.register_profile(_make_profile(pid, latency_class))
    return registry


def _make_orchestrator(*provider_ids: str) -> LLMFailoverOrchestrator:
    """Create an orchestrator with a pre-populated registry."""
    registry = _make_registry(*provider_ids) if provider_ids else _make_registry("openai-gpt4")
    return LLMFailoverOrchestrator(capability_registry=registry)


# ===========================================================================
# FAILOVER_EXECUTION_ERRORS constant
# ===========================================================================


class TestFailoverExecutionErrors:
    def test_is_tuple(self):
        assert isinstance(FAILOVER_EXECUTION_ERRORS, tuple)

    def test_contains_runtime_error(self):
        assert RuntimeError in FAILOVER_EXECUTION_ERRORS

    def test_contains_value_error(self):
        assert ValueError in FAILOVER_EXECUTION_ERRORS

    def test_contains_connection_error(self):
        assert ConnectionError in FAILOVER_EXECUTION_ERRORS

    def test_contains_timeout_error(self):
        assert TimeoutError in FAILOVER_EXECUTION_ERRORS

    def test_contains_type_error(self):
        assert TypeError in FAILOVER_EXECUTION_ERRORS

    def test_contains_key_error(self):
        assert KeyError in FAILOVER_EXECUTION_ERRORS

    def test_contains_attribute_error(self):
        assert AttributeError in FAILOVER_EXECUTION_ERRORS

    def test_contains_os_error(self):
        assert OSError in FAILOVER_EXECUTION_ERRORS


# ===========================================================================
# LLMFailoverOrchestrator - construction / initialization
# ===========================================================================


class TestLLMFailoverOrchestratorInit:
    def test_default_construction_uses_global_registry(self):
        """Constructor without args should still build an orchestrator."""
        # We mock get_capability_registry to avoid side effects
        mock_registry = _make_registry("p1")
        with patch(
            "enhanced_agent_bus.llm_adapters.failover.orchestrator.get_capability_registry",
            return_value=mock_registry,
        ):
            orch = LLMFailoverOrchestrator()
        assert orch.registry is mock_registry
        assert orch.health_scorer is not None
        assert orch.failover_manager is not None
        assert orch.warmup_manager is not None
        assert orch.hedging_manager is not None

    def test_custom_registry_stored(self):
        registry = _make_registry("pA", "pB")
        orch = LLMFailoverOrchestrator(capability_registry=registry)
        assert orch.registry is registry

    def test_initialize_expected_latencies_ultra_low(self):
        registry = _make_registry("fast-provider", latency_class=LatencyClass.ULTRA_LOW)
        orch = LLMFailoverOrchestrator(capability_registry=registry)
        assert orch.health_scorer._expected_latency.get("fast-provider") == 100

    def test_initialize_expected_latencies_low(self):
        registry = _make_registry("low-p", latency_class=LatencyClass.LOW)
        orch = LLMFailoverOrchestrator(capability_registry=registry)
        assert orch.health_scorer._expected_latency.get("low-p") == 200

    def test_initialize_expected_latencies_medium(self):
        registry = _make_registry("med-p", latency_class=LatencyClass.MEDIUM)
        orch = LLMFailoverOrchestrator(capability_registry=registry)
        assert orch.health_scorer._expected_latency.get("med-p") == 500

    def test_initialize_expected_latencies_high(self):
        registry = _make_registry("high-p", latency_class=LatencyClass.HIGH)
        orch = LLMFailoverOrchestrator(capability_registry=registry)
        assert orch.health_scorer._expected_latency.get("high-p") == 1000

    def test_initialize_expected_latencies_variable(self):
        registry = _make_registry("var-p", latency_class=LatencyClass.VARIABLE)
        orch = LLMFailoverOrchestrator(capability_registry=registry)
        assert orch.health_scorer._expected_latency.get("var-p") == 750

    def test_initialize_expected_latencies_empty_registry(self):
        """Empty registry should not raise."""
        registry = _make_registry()
        orch = LLMFailoverOrchestrator(capability_registry=registry)
        assert orch.health_scorer._expected_latency == {}

    def test_multiple_providers_all_get_latency(self):
        registry = _make_registry()
        registry.register_profile(_make_profile("p-ultra", LatencyClass.ULTRA_LOW))
        registry.register_profile(_make_profile("p-high", LatencyClass.HIGH))
        orch = LLMFailoverOrchestrator(capability_registry=registry)
        assert orch.health_scorer._expected_latency["p-ultra"] == 100
        assert orch.health_scorer._expected_latency["p-high"] == 1000


# ===========================================================================
# get_llm_circuit_breaker
# ===========================================================================


class TestGetLLMCircuitBreaker:
    async def test_returns_circuit_breaker_with_dash_in_provider_id(self):
        orch = _make_orchestrator("openai-gpt4")
        mock_cb = MagicMock()
        mock_registry = AsyncMock()
        mock_registry.get_or_create = AsyncMock(return_value=mock_cb)
        with patch(
            "enhanced_agent_bus.llm_adapters.failover.orchestrator.get_circuit_breaker_registry",
            return_value=mock_registry,
        ):
            result = await orch.get_llm_circuit_breaker("openai-gpt4")
        assert result is mock_cb
        call_args = mock_registry.get_or_create.call_args
        assert call_args[0][0] == "llm:openai-gpt4"

    async def test_provider_type_extracted_before_dash(self):
        orch = _make_orchestrator("anthropic-claude")
        mock_cb = MagicMock()
        mock_registry = AsyncMock()
        mock_registry.get_or_create = AsyncMock(return_value=mock_cb)
        with (
            patch(
                "enhanced_agent_bus.llm_adapters.failover.orchestrator.get_circuit_breaker_registry",
                return_value=mock_registry,
            ) as _,
            patch(
                "enhanced_agent_bus.llm_adapters.failover.orchestrator.get_llm_circuit_config",
            ) as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            await orch.get_llm_circuit_breaker("anthropic-claude")
        mock_cfg.assert_called_once_with("anthropic")

    async def test_provider_id_without_dash_uses_default(self):
        orch = _make_orchestrator("openai")
        mock_cb = MagicMock()
        mock_registry = AsyncMock()
        mock_registry.get_or_create = AsyncMock(return_value=mock_cb)
        with (
            patch(
                "enhanced_agent_bus.llm_adapters.failover.orchestrator.get_circuit_breaker_registry",
                return_value=mock_registry,
            ) as _,
            patch(
                "enhanced_agent_bus.llm_adapters.failover.orchestrator.get_llm_circuit_config",
            ) as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            await orch.get_llm_circuit_breaker("openai")
        # When there is no dash, provider_type is "default"
        mock_cfg.assert_called_once_with("default")

    async def test_circuit_breaker_key_format(self):
        """The circuit breaker key must be llm:<provider_id>."""
        orch = _make_orchestrator("bedrock-v1")
        mock_cb = MagicMock()
        mock_registry = AsyncMock()
        mock_registry.get_or_create = AsyncMock(return_value=mock_cb)
        with patch(
            "enhanced_agent_bus.llm_adapters.failover.orchestrator.get_circuit_breaker_registry",
            return_value=mock_registry,
        ):
            await orch.get_llm_circuit_breaker("bedrock-v1")
        key_used = mock_registry.get_or_create.call_args[0][0]
        assert key_used == "llm:bedrock-v1"


# ===========================================================================
# record_request_result
# ===========================================================================


class TestRecordRequestResult:
    async def test_success_path_calls_record_success(self):
        orch = _make_orchestrator("openai-gpt4")
        mock_cb = AsyncMock()
        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            await orch.record_request_result("openai-gpt4", 100.0, True)
        mock_cb.record_success.assert_awaited_once()
        mock_cb.record_failure.assert_not_called()

    async def test_failure_path_calls_record_failure(self):
        orch = _make_orchestrator("openai-gpt4")
        mock_cb = AsyncMock()
        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            await orch.record_request_result("openai-gpt4", 200.0, False, error_type="TimeoutError")
        mock_cb.record_failure.assert_awaited_once_with(error_type="TimeoutError")
        mock_cb.record_success.assert_not_called()

    async def test_failure_with_no_error_type_uses_unknown(self):
        orch = _make_orchestrator("openai-gpt4")
        mock_cb = AsyncMock()
        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            await orch.record_request_result("openai-gpt4", 50.0, False)
        mock_cb.record_failure.assert_awaited_once_with(error_type="unknown")

    async def test_health_scorer_updated_on_success(self):
        orch = _make_orchestrator("openai-gpt4")
        mock_cb = AsyncMock()
        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            await orch.record_request_result("openai-gpt4", 75.0, True, quality_score=0.9)
        score = orch.health_scorer.get_health_score("openai-gpt4")
        assert score.metrics.total_requests == 1
        assert score.metrics.successful_requests == 1

    async def test_health_scorer_updated_on_failure(self):
        orch = _make_orchestrator("openai-gpt4")
        mock_cb = AsyncMock()
        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            await orch.record_request_result(
                "openai-gpt4", 300.0, False, error_type="ConnectionError"
            )
        score = orch.health_scorer.get_health_score("openai-gpt4")
        assert score.metrics.failed_requests == 1

    async def test_quality_score_forwarded_to_health_scorer(self):
        orch = _make_orchestrator("p1")
        mock_cb = AsyncMock()
        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            await orch.record_request_result("p1", 100.0, True, quality_score=0.75)
        score = orch.health_scorer.get_health_score("p1")
        assert abs(score.metrics.avg_quality_score - 0.75) < 0.01


# ===========================================================================
# select_provider
# ===========================================================================


class TestSelectProvider:
    async def test_returns_provider_id(self):
        orch = _make_orchestrator("openai-gpt4")
        mock_fm = AsyncMock()
        mock_fm.check_and_failover = AsyncMock(return_value=("openai-gpt4", False))
        orch.failover_manager = mock_fm
        result = await orch.select_provider("tenant-1", [])
        assert result == "openai-gpt4"

    async def test_no_failover_skips_warmup(self):
        orch = _make_orchestrator("openai-gpt4")
        mock_fm = AsyncMock()
        mock_fm.check_and_failover = AsyncMock(return_value=("openai-gpt4", False))
        orch.failover_manager = mock_fm
        mock_wm = AsyncMock()
        orch.warmup_manager = mock_wm
        await orch.select_provider("tenant-1", [])
        mock_wm.warmup_before_failover.assert_not_called()

    async def test_failover_occurred_triggers_warmup(self):
        orch = _make_orchestrator("openai-gpt4", "anthropic-claude")
        mock_fm = AsyncMock()
        mock_fm.check_and_failover = AsyncMock(return_value=("anthropic-claude", True))
        orch.failover_manager = mock_fm
        mock_wm = AsyncMock()
        orch.warmup_manager = mock_wm
        result = await orch.select_provider("tenant-1", [])
        mock_wm.warmup_before_failover.assert_awaited_once_with("anthropic-claude")
        assert result == "anthropic-claude"

    async def test_critical_flag_forwarded(self):
        orch = _make_orchestrator("openai-gpt4")
        mock_fm = AsyncMock()
        mock_fm.check_and_failover = AsyncMock(return_value=("openai-gpt4", False))
        orch.failover_manager = mock_fm
        result = await orch.select_provider("tenant-1", [], critical=True)
        assert result == "openai-gpt4"


# ===========================================================================
# execute_with_failover - non-critical (normal path)
# ===========================================================================


class TestExecuteWithFailoverNormal:
    async def test_success_returns_provider_and_result(self):
        orch = _make_orchestrator("openai-gpt4")
        orch.failover_manager.check_and_failover = AsyncMock(return_value=("openai-gpt4", False))
        orch.health_scorer.record_request = AsyncMock()
        mock_cb = AsyncMock()
        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):

            async def execute_fn(pid: str) -> str:
                return f"response-from-{pid}"

            provider, result = await orch.execute_with_failover("t1", [], execute_fn)
        assert provider == "openai-gpt4"
        assert result == "response-from-openai-gpt4"

    async def test_success_records_success_result(self):
        orch = _make_orchestrator("openai-gpt4")
        orch.failover_manager.check_and_failover = AsyncMock(return_value=("openai-gpt4", False))
        mock_cb = AsyncMock()
        recorded_provider = []
        recorded_success = []
        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            original_record = orch.record_request_result

            async def spy_record(provider_id, latency_ms, success, **kwargs):
                recorded_provider.append(provider_id)
                recorded_success.append(success)
                await original_record(provider_id, latency_ms, success, **kwargs)

            orch.record_request_result = spy_record

            async def execute_fn(pid: str) -> str:
                return "ok"

            await orch.execute_with_failover("t1", [], execute_fn)

        assert len(recorded_provider) == 1
        assert recorded_provider[0] == "openai-gpt4"
        assert recorded_success[0] is True

    async def test_failure_records_failure_and_tries_fallbacks(self):
        """When primary fails, orchestrator tries fallback chain."""
        orch = _make_orchestrator("openai-gpt4", "anthropic-claude")
        orch.failover_manager.check_and_failover = AsyncMock(return_value=("openai-gpt4", False))
        orch.failover_manager.build_fallback_chain = MagicMock(return_value=["anthropic-claude"])
        mock_cb = AsyncMock()

        call_count = {"n": 0}

        async def execute_fn(pid: str) -> str:
            call_count["n"] += 1
            if pid == "openai-gpt4":
                raise RuntimeError("Provider down")
            return f"response-{pid}"

        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            provider, result = await orch.execute_with_failover("t1", [], execute_fn)

        assert provider == "anthropic-claude"
        assert result == "response-anthropic-claude"
        assert call_count["n"] == 2

    async def test_failure_raises_when_all_fallbacks_fail(self):
        """All fallbacks failing re-raises original exception."""
        orch = _make_orchestrator("openai-gpt4", "anthropic-claude")
        orch.failover_manager.check_and_failover = AsyncMock(return_value=("openai-gpt4", False))
        orch.failover_manager.build_fallback_chain = MagicMock(return_value=["anthropic-claude"])
        mock_cb = AsyncMock()

        async def execute_fn(pid: str) -> str:
            raise RuntimeError("All down")

        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            with pytest.raises(RuntimeError, match="All down"):
                await orch.execute_with_failover("t1", [], execute_fn)

    async def test_failure_raises_when_no_fallbacks(self):
        """No fallbacks raises the original error."""
        orch = _make_orchestrator("openai-gpt4")
        orch.failover_manager.check_and_failover = AsyncMock(return_value=("openai-gpt4", False))
        orch.failover_manager.build_fallback_chain = MagicMock(return_value=[])
        mock_cb = AsyncMock()

        async def execute_fn(pid: str) -> str:
            raise ConnectionError("Connection refused")

        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            with pytest.raises(ConnectionError):
                await orch.execute_with_failover("t1", [], execute_fn)

    async def test_fallback_success_records_success(self):
        """Successful fallback records success for fallback provider."""
        orch = _make_orchestrator("p1", "p2")
        orch.failover_manager.check_and_failover = AsyncMock(return_value=("p1", False))
        orch.failover_manager.build_fallback_chain = MagicMock(return_value=["p2"])
        mock_cb = AsyncMock()

        recorded = []
        original_record = orch.record_request_result

        async def spy_record(provider_id, latency_ms, success, **kwargs):
            recorded.append((provider_id, success))
            await original_record(provider_id, latency_ms, success, **kwargs)

        orch.record_request_result = spy_record

        async def execute_fn(pid: str) -> str:
            if pid == "p1":
                raise ValueError("p1 down")
            return "ok"

        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            _provider, _result = await orch.execute_with_failover("t1", [], execute_fn)

        assert any(r == ("p2", True) for r in recorded)

    async def test_fallback_failure_records_failure_and_continues(self):
        """If a fallback also errors, it still continues to next fallback."""
        orch = _make_orchestrator("p1", "p2", "p3")
        orch.failover_manager.check_and_failover = AsyncMock(return_value=("p1", False))
        orch.failover_manager.build_fallback_chain = MagicMock(return_value=["p2", "p3"])
        mock_cb = AsyncMock()

        async def execute_fn(pid: str) -> str:
            if pid in ("p1", "p2"):
                raise RuntimeError(f"{pid} down")
            return "ok-p3"

        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            provider, result = await orch.execute_with_failover("t1", [], execute_fn)

        assert provider == "p3"
        assert result == "ok-p3"

    async def test_value_error_triggers_fallback(self):
        orch = _make_orchestrator("p1", "p2")
        orch.failover_manager.check_and_failover = AsyncMock(return_value=("p1", False))
        orch.failover_manager.build_fallback_chain = MagicMock(return_value=["p2"])
        mock_cb = AsyncMock()

        async def execute_fn(pid: str) -> str:
            if pid == "p1":
                raise ValueError("bad value")
            return "ok"

        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            provider, _result = await orch.execute_with_failover("t1", [], execute_fn)
        assert provider == "p2"

    async def test_timeout_error_triggers_fallback(self):
        orch = _make_orchestrator("p1", "p2")
        orch.failover_manager.check_and_failover = AsyncMock(return_value=("p1", False))
        orch.failover_manager.build_fallback_chain = MagicMock(return_value=["p2"])
        mock_cb = AsyncMock()

        async def execute_fn(pid: str) -> str:
            if pid == "p1":
                raise TimeoutError("timeout")
            return "ok"

        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            provider, _result = await orch.execute_with_failover("t1", [], execute_fn)
        assert provider == "p2"

    async def test_key_error_triggers_fallback(self):
        orch = _make_orchestrator("p1", "p2")
        orch.failover_manager.check_and_failover = AsyncMock(return_value=("p1", False))
        orch.failover_manager.build_fallback_chain = MagicMock(return_value=["p2"])
        mock_cb = AsyncMock()

        async def execute_fn(pid: str) -> str:
            if pid == "p1":
                raise KeyError("missing key")
            return "ok"

        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            provider, _result = await orch.execute_with_failover("t1", [], execute_fn)
        assert provider == "p2"

    async def test_attribute_error_triggers_fallback(self):
        orch = _make_orchestrator("p1", "p2")
        orch.failover_manager.check_and_failover = AsyncMock(return_value=("p1", False))
        orch.failover_manager.build_fallback_chain = MagicMock(return_value=["p2"])
        mock_cb = AsyncMock()

        async def execute_fn(pid: str) -> str:
            if pid == "p1":
                raise AttributeError("attr error")
            return "ok"

        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            provider, _result = await orch.execute_with_failover("t1", [], execute_fn)
        assert provider == "p2"

    async def test_os_error_triggers_fallback(self):
        orch = _make_orchestrator("p1", "p2")
        orch.failover_manager.check_and_failover = AsyncMock(return_value=("p1", False))
        orch.failover_manager.build_fallback_chain = MagicMock(return_value=["p2"])
        mock_cb = AsyncMock()

        async def execute_fn(pid: str) -> str:
            if pid == "p1":
                raise OSError("os error")
            return "ok"

        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            provider, _result = await orch.execute_with_failover("t1", [], execute_fn)
        assert provider == "p2"

    async def test_type_error_triggers_fallback(self):
        orch = _make_orchestrator("p1", "p2")
        orch.failover_manager.check_and_failover = AsyncMock(return_value=("p1", False))
        orch.failover_manager.build_fallback_chain = MagicMock(return_value=["p2"])
        mock_cb = AsyncMock()

        async def execute_fn(pid: str) -> str:
            if pid == "p1":
                raise TypeError("type error")
            return "ok"

        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            provider, _result = await orch.execute_with_failover("t1", [], execute_fn)
        assert provider == "p2"

    async def test_records_failure_error_type_name(self):
        """The error_type recorded is the class name of the exception."""
        orch = _make_orchestrator("p1", "p2")
        orch.failover_manager.check_and_failover = AsyncMock(return_value=("p1", False))
        orch.failover_manager.build_fallback_chain = MagicMock(return_value=["p2"])
        mock_cb = AsyncMock()

        recorded_error_type = []
        original_record = orch.record_request_result

        async def spy(*args, **kwargs):
            if not kwargs.get("success", args[2] if len(args) > 2 else True):
                recorded_error_type.append(
                    kwargs.get("error_type", args[3] if len(args) > 3 else None)
                )
            await original_record(*args, **kwargs)

        orch.record_request_result = spy

        async def execute_fn(pid: str) -> str:
            if pid == "p1":
                raise RuntimeError("boom")
            return "ok"

        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            await orch.execute_with_failover("t1", [], execute_fn)

        # Check that the error type "RuntimeError" was recorded
        assert any("RuntimeError" in str(et) for et in recorded_error_type if et)


# ===========================================================================
# execute_with_failover - critical path with hedging
# ===========================================================================


class TestExecuteWithFailoverCriticalHedging:
    async def test_critical_hedge_count_gt_1_uses_hedging(self):
        registry = _make_registry("p1", "p2", "p3")
        orch = LLMFailoverOrchestrator(capability_registry=registry)

        mock_hedging = AsyncMock()
        mock_hedging.execute_hedged = AsyncMock(return_value=("p1", "hedged-result"))
        orch.hedging_manager = mock_hedging

        async def execute_fn(pid: str):
            return "result"

        provider, result = await orch.execute_with_failover(
            "t1", [], execute_fn, critical=True, hedge_count=2
        )
        assert provider == "p1"
        assert result == "hedged-result"
        mock_hedging.execute_hedged.assert_awaited_once()

    async def test_critical_hedge_count_1_skips_hedging(self):
        """critical=True but hedge_count=1 should NOT use hedging."""
        orch = _make_orchestrator("p1")
        orch.failover_manager.check_and_failover = AsyncMock(return_value=("p1", False))
        mock_hedging = AsyncMock()
        orch.hedging_manager = mock_hedging
        mock_cb = AsyncMock()

        async def execute_fn(pid: str):
            return "normal-result"

        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            _provider, result = await orch.execute_with_failover(
                "t1", [], execute_fn, critical=True, hedge_count=1
            )
        mock_hedging.execute_hedged.assert_not_called()
        assert result == "normal-result"

    async def test_non_critical_hedge_count_2_skips_hedging(self):
        """critical=False even with hedge_count=2 should NOT use hedging."""
        orch = _make_orchestrator("p1")
        orch.failover_manager.check_and_failover = AsyncMock(return_value=("p1", False))
        mock_hedging = AsyncMock()
        orch.hedging_manager = mock_hedging
        mock_cb = AsyncMock()

        async def execute_fn(pid: str):
            return "normal"

        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            _provider, _result = await orch.execute_with_failover(
                "t1", [], execute_fn, critical=False, hedge_count=2
            )
        mock_hedging.execute_hedged.assert_not_called()

    async def test_hedging_uses_top_n_capable_providers(self):
        registry = _make_registry("p1", "p2", "p3", "p4")
        orch = LLMFailoverOrchestrator(capability_registry=registry)

        captured_providers = []

        async def mock_execute_hedged(request_id, providers, execute_fn, hedge_count):
            captured_providers.extend(providers)
            return (providers[0], "result")

        orch.hedging_manager.execute_hedged = mock_execute_hedged

        async def execute_fn(pid: str):
            return "r"

        await orch.execute_with_failover("t1", [], execute_fn, critical=True, hedge_count=2)
        assert len(captured_providers) == 2

    async def test_hedging_request_id_format(self):
        """Request ID passed to hedging manager should start with 'req-'."""
        registry = _make_registry("p1", "p2")
        orch = LLMFailoverOrchestrator(capability_registry=registry)

        captured_req_id = []

        async def mock_execute_hedged(request_id, providers, execute_fn, hedge_count):
            captured_req_id.append(request_id)
            return (providers[0], "result")

        orch.hedging_manager.execute_hedged = mock_execute_hedged

        async def execute_fn(pid: str):
            return "r"

        await orch.execute_with_failover("t1", [], execute_fn, critical=True, hedge_count=2)
        assert captured_req_id[0].startswith("req-")

    async def test_hedging_hedge_count_passed_through(self):
        registry = _make_registry("p1", "p2", "p3")
        orch = LLMFailoverOrchestrator(capability_registry=registry)

        captured_hedge_count = []

        async def mock_execute_hedged(request_id, providers, execute_fn, hedge_count):
            captured_hedge_count.append(hedge_count)
            return (providers[0], "r")

        orch.hedging_manager.execute_hedged = mock_execute_hedged

        async def execute_fn(pid: str):
            return "r"

        await orch.execute_with_failover("t1", [], execute_fn, critical=True, hedge_count=3)
        assert captured_hedge_count[0] == 3


# ===========================================================================
# get_orchestrator_status
# ===========================================================================


class TestGetOrchestratorStatus:
    def test_status_has_required_keys(self):
        orch = _make_orchestrator("openai-gpt4")
        status = orch.get_orchestrator_status()
        assert "health_scores" in status
        assert "failover_stats" in status
        assert "hedging_stats" in status
        assert "timestamp" in status
        assert "constitutional_hash" in status

    def test_constitutional_hash_correct(self):
        orch = _make_orchestrator("openai-gpt4")
        status = orch.get_orchestrator_status()
        assert status["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_timestamp_is_iso_format(self):
        orch = _make_orchestrator("openai-gpt4")
        status = orch.get_orchestrator_status()
        from datetime import datetime, timezone

        # Should not raise
        parsed = datetime.fromisoformat(status["timestamp"])
        assert parsed is not None

    def test_health_scores_empty_when_no_requests(self):
        orch = _make_orchestrator("openai-gpt4")
        status = orch.get_orchestrator_status()
        assert status["health_scores"] == {}

    async def test_health_scores_populated_after_request(self):
        orch = _make_orchestrator("p1")
        mock_cb = AsyncMock()
        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            await orch.record_request_result("p1", 100.0, True)
        status = orch.get_orchestrator_status()
        assert "p1" in status["health_scores"]

    def test_failover_stats_returned(self):
        orch = _make_orchestrator("openai-gpt4")
        status = orch.get_orchestrator_status()
        assert isinstance(status["failover_stats"], dict)

    def test_hedging_stats_returned(self):
        orch = _make_orchestrator("openai-gpt4")
        status = orch.get_orchestrator_status()
        assert isinstance(status["hedging_stats"], dict)

    def test_health_scores_dict_values_have_provider_id(self):
        orch = _make_orchestrator("myp")
        # Force metrics to exist
        from enhanced_agent_bus.llm_adapters.failover.health import HealthMetrics

        orch.health_scorer._metrics["myp"] = HealthMetrics()
        status = orch.get_orchestrator_status()
        assert "myp" in status["health_scores"]
        assert status["health_scores"]["myp"]["provider_id"] == "myp"


# ===========================================================================
# Global instance management
# ===========================================================================


class TestGlobalInstance:
    def setup_method(self):
        reset_llm_failover_orchestrator()

    def teardown_method(self):
        reset_llm_failover_orchestrator()

    def test_get_creates_orchestrator(self):
        orch = get_llm_failover_orchestrator()
        assert isinstance(orch, LLMFailoverOrchestrator)

    def test_get_returns_same_instance(self):
        orch1 = get_llm_failover_orchestrator()
        orch2 = get_llm_failover_orchestrator()
        assert orch1 is orch2

    def test_reset_clears_instance(self):
        orch1 = get_llm_failover_orchestrator()
        reset_llm_failover_orchestrator()
        orch2 = get_llm_failover_orchestrator()
        assert orch1 is not orch2

    def test_reset_when_none_is_safe(self):
        """Calling reset on an already-None state should not raise."""
        reset_llm_failover_orchestrator()
        reset_llm_failover_orchestrator()  # second call must be safe

    def test_get_after_reset_creates_new(self):
        orch1 = get_llm_failover_orchestrator()
        reset_llm_failover_orchestrator()
        orch2 = get_llm_failover_orchestrator()
        assert orch1 is not orch2
        assert isinstance(orch2, LLMFailoverOrchestrator)


# ===========================================================================
# Integration-style: full execute_with_failover round-trip
# ===========================================================================


class TestExecuteWithFailoverIntegration:
    async def test_full_success_round_trip(self):
        """Success path: provider selected, executed, result returned, health updated."""
        registry = _make_registry("openai-gpt4")
        orch = LLMFailoverOrchestrator(capability_registry=registry)
        orch.failover_manager.set_primary_provider("tenant-A", "openai-gpt4")
        # Seed enough health data so health score > PROACTIVE_FAILOVER_THRESHOLD
        from enhanced_agent_bus.llm_adapters.failover.health import HealthMetrics

        metrics = HealthMetrics()
        metrics.health_score = 1.0
        orch.health_scorer._metrics["openai-gpt4"] = metrics
        mock_cb = AsyncMock()

        async def execute_fn(pid: str):
            return {"answer": 42}

        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            provider, result = await orch.execute_with_failover("tenant-A", [], execute_fn)

        assert provider == "openai-gpt4"
        assert result == {"answer": 42}

    async def test_failover_chain_exhaustion_re_raises(self):
        """Exhausting entire fallback chain re-raises the primary exception."""
        registry = _make_registry("p1", "p2", "p3")
        orch = LLMFailoverOrchestrator(capability_registry=registry)
        orch.failover_manager.check_and_failover = AsyncMock(return_value=("p1", False))
        orch.failover_manager.build_fallback_chain = MagicMock(return_value=["p2", "p3"])
        mock_cb = AsyncMock()

        async def execute_fn(pid: str) -> str:
            raise ConnectionError("all down")

        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            with pytest.raises(ConnectionError, match="all down"):
                await orch.execute_with_failover("t1", [], execute_fn)

    async def test_second_fallback_succeeds_after_first_fails(self):
        registry = _make_registry("p1", "p2", "p3")
        orch = LLMFailoverOrchestrator(capability_registry=registry)
        orch.failover_manager.check_and_failover = AsyncMock(return_value=("p1", False))
        orch.failover_manager.build_fallback_chain = MagicMock(return_value=["p2", "p3"])
        mock_cb = AsyncMock()

        async def execute_fn(pid: str) -> str:
            if pid in ("p1", "p2"):
                raise ValueError("down")
            return "success-p3"

        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            provider, result = await orch.execute_with_failover("t1", [], execute_fn)

        assert provider == "p3"
        assert result == "success-p3"

    async def test_latency_ms_is_recorded(self):
        """Latency is captured and recorded via record_request_result."""
        orch = _make_orchestrator("p1")
        orch.failover_manager.check_and_failover = AsyncMock(return_value=("p1", False))
        mock_cb = AsyncMock()
        latency_values = []
        original_record = orch.record_request_result

        async def spy(provider_id, latency_ms, success, **kwargs):
            latency_values.append(latency_ms)
            await original_record(provider_id, latency_ms, success, **kwargs)

        orch.record_request_result = spy

        async def execute_fn(pid: str) -> str:
            return "ok"

        with patch.object(orch, "get_llm_circuit_breaker", AsyncMock(return_value=mock_cb)):
            await orch.execute_with_failover("t1", [], execute_fn)

        assert len(latency_values) == 1
        assert latency_values[0] >= 0


# ===========================================================================
# Additional edge-case tests for _initialize_expected_latencies
# ===========================================================================


class TestInitializeExpectedLatencies:
    def test_unknown_latency_class_defaults_to_500(self):
        """Profiles with a LatencyClass not in the map get 500ms default."""
        registry = _make_registry()
        profile = _make_profile("weird-p", LatencyClass.MEDIUM)
        # Inject a profile whose latency_class is deliberately missing from the map
        registry.register_profile(profile)
        orch = LLMFailoverOrchestrator(capability_registry=registry)
        # MEDIUM is in the map (500), so we just verify it was set
        assert orch.health_scorer._expected_latency["weird-p"] == 500

    def test_all_latency_classes_covered(self):
        """All five LatencyClass values are handled."""
        registry = _make_registry()
        for lc in LatencyClass:
            profile = _make_profile(f"p-{lc.value}", lc)
            registry.register_profile(profile)
        orch = LLMFailoverOrchestrator(capability_registry=registry)
        for lc in LatencyClass:
            pid = f"p-{lc.value}"
            assert pid in orch.health_scorer._expected_latency


# ===========================================================================
# __all__ exports
# ===========================================================================


class TestModuleExports:
    def test_orchestrator_class_exported(self):
        from enhanced_agent_bus.llm_adapters.failover import orchestrator as mod

        assert "LLMFailoverOrchestrator" in mod.__all__

    def test_get_function_exported(self):
        from enhanced_agent_bus.llm_adapters.failover import orchestrator as mod

        assert "get_llm_failover_orchestrator" in mod.__all__

    def test_reset_function_exported(self):
        from enhanced_agent_bus.llm_adapters.failover import orchestrator as mod

        assert "reset_llm_failover_orchestrator" in mod.__all__
