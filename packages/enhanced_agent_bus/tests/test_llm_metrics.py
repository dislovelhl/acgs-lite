"""
Module.

Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.deliberation_layer.llm_assistant import LLMAssistant


async def test_llm_metrics_recording():
    # 1. Setup
    assistant = LLMAssistant(model_name="test-model")
    assistant.llm = AsyncMock()

    # Mock response with token usage
    mock_response = MagicMock()
    mock_response.content = '{"decision": "approve", "reasoning": "all good"}'
    mock_response.response_metadata = {
        "token_usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
    }
    assistant.llm.ainvoke.return_value = mock_response

    # Mock MetricsRegistry
    with patch(
        "enhanced_agent_bus.deliberation_layer.llm_assistant.MetricsRegistry"
    ) as MockRegistry:
        mock_registry_instance = MockRegistry.return_value

        # 2. Execute
        result = await assistant._invoke_llm("Test prompt")

        # 3. Verify
        assert "_metrics" in result
        assert result["_metrics"]["latency_ms"] > 0
        assert result["_metrics"]["token_usage"]["total_tokens"] == 30

        # Verify MetricsRegistry calls
        mock_registry_instance.record_latency.assert_called_with(
            "llm_invocation_latency",
            pytest.approx(result["_metrics"]["latency_ms"]),
            {"model": "test-model"},
        )

        mock_registry_instance.increment_counter.assert_any_call(
            "llm_tokens_total", 30, {"model": "test-model"}
        )
        mock_registry_instance.increment_counter.assert_any_call(
            "llm_tokens_prompt", 10, {"model": "test-model"}
        )
        mock_registry_instance.increment_counter.assert_any_call(
            "llm_tokens_completion", 20, {"model": "test-model"}
        )


async def test_llm_metrics_failure_recording():
    # 1. Setup
    assistant = LLMAssistant(model_name="test-model")
    assistant.llm = AsyncMock()
    assistant.llm.ainvoke.side_effect = RuntimeError("API error")

    # Mock MetricsRegistry
    with patch(
        "enhanced_agent_bus.deliberation_layer.llm_assistant.MetricsRegistry"
    ) as MockRegistry:
        mock_registry_instance = MockRegistry.return_value

        # 2. Execute
        result = await assistant._invoke_llm("Test prompt")

        # 3. Verify
        assert result == {}

        # Verify failure metric recorded
        mock_registry_instance.increment_counter.assert_called_with(
            "llm_invocation_failure", 1, {"model": "test-model", "error": "<class 'RuntimeError'>"}
        )
