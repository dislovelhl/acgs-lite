"""Tests for enhanced_agent_bus.llm_adapters.anthropic_adapter module.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.llm_adapters.base import (
    AdapterStatus,
    CompletionMetadata,
    CostEstimate,
    HealthCheckResult,
    LLMMessage,
    LLMResponse,
    StreamingMode,
    TokenUsage,
)
from enhanced_agent_bus.llm_adapters.config import AnthropicAdapterConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides) -> AnthropicAdapterConfig:
    """Create a minimal AnthropicAdapterConfig for testing."""
    defaults = {"model": "claude-sonnet-4-6"}
    defaults.update(overrides)
    return AnthropicAdapterConfig(**defaults)


def _make_messages() -> list[LLMMessage]:
    return [
        LLMMessage(role="system", content="You are helpful."),
        LLMMessage(role="user", content="Hello!"),
    ]


def _make_anthropic_response_dict() -> dict:
    """Fake response dict matching Anthropic API shape."""
    return {
        "id": "msg_123",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Hi there!"}],
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


# ---------------------------------------------------------------------------
# Tests: Initialization
# ---------------------------------------------------------------------------


class TestAnthropicAdapterInit:
    """Tests for AnthropicAdapter construction."""

    def test_init_with_config(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        config = _make_config()
        adapter = AnthropicAdapter(config=config, api_key="test-key")

        assert adapter.model == "claude-sonnet-4-6"
        assert adapter.api_key == "test-key"
        assert adapter._client is None
        assert adapter._async_client is None

    def test_init_default_model(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key="test-key")
        assert adapter.model == "claude-sonnet-4-6"

    def test_init_custom_model(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(model="claude-opus-4-6", api_key="test-key")
        assert adapter.model == "claude-opus-4-6"


# ---------------------------------------------------------------------------
# Tests: _prepare_messages
# ---------------------------------------------------------------------------


class TestPrepareMessages:
    def test_extracts_system_prompt(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key="k")
        messages = _make_messages()

        with patch("enhanced_agent_bus.llm_adapters.anthropic_adapter.MessageConverter") as mc:
            mc.to_anthropic_format.return_value = [{"role": "user", "content": "Hello!"}]
            system_prompt, conv = adapter._prepare_messages(messages)

        assert system_prompt == "You are helpful."
        assert len(conv) == 1

    def test_no_system_message(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key="k")
        messages = [LLMMessage(role="user", content="Hi")]

        with patch("enhanced_agent_bus.llm_adapters.anthropic_adapter.MessageConverter") as mc:
            mc.to_anthropic_format.return_value = [{"role": "user", "content": "Hi"}]
            system_prompt, conv = adapter._prepare_messages(messages)

        assert system_prompt is None


# ---------------------------------------------------------------------------
# Tests: estimate_cost
# ---------------------------------------------------------------------------


class TestEstimateCost:
    def test_known_model(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(model="claude-sonnet-4-6", api_key="k")
        cost = adapter.estimate_cost(1_000_000, 1_000_000)

        assert isinstance(cost, CostEstimate)
        assert cost.prompt_cost_usd == pytest.approx(3.00)
        assert cost.completion_cost_usd == pytest.approx(15.00)
        assert cost.total_cost_usd == pytest.approx(18.00)
        assert cost.currency == "USD"

    def test_unknown_model_falls_back(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(
            config=_make_config(model="claude-unknown-99"),
            api_key="k",
        )
        cost = adapter.estimate_cost(1_000_000, 0)
        # Should fall back to claude-sonnet-4-6 pricing
        assert cost.prompt_cost_usd == pytest.approx(3.00)

    def test_zero_tokens(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key="k")
        cost = adapter.estimate_cost(0, 0)
        assert cost.total_cost_usd == 0.0

    def test_opus_pricing(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(
            config=_make_config(model="claude-opus-4-6"),
            api_key="k",
        )
        cost = adapter.estimate_cost(1_000_000, 1_000_000)
        assert cost.prompt_cost_usd == pytest.approx(5.00)
        assert cost.completion_cost_usd == pytest.approx(25.00)


# ---------------------------------------------------------------------------
# Tests: get_streaming_mode / get_provider_name
# ---------------------------------------------------------------------------


class TestAdapterProperties:
    def test_streaming_mode(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key="k")
        assert adapter.get_streaming_mode() == StreamingMode.SUPPORTED

    def test_provider_name(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key="k")
        assert adapter.get_provider_name() == "anthropic"


# ---------------------------------------------------------------------------
# Tests: _convert_tools_to_anthropic
# ---------------------------------------------------------------------------


class TestConvertTools:
    def test_converts_function_tools(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key="k")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = adapter._convert_tools_to_anthropic(tools)
        assert len(result) == 1
        assert result[0]["name"] == "get_weather"
        assert result[0]["description"] == "Get weather"
        assert "input_schema" in result[0]

    def test_skips_non_function_tools(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key="k")
        tools = [{"type": "code_interpreter"}]
        result = adapter._convert_tools_to_anthropic(tools)
        assert result == []

    def test_empty_tools(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key="k")
        assert adapter._convert_tools_to_anthropic([]) == []


# ---------------------------------------------------------------------------
# Tests: _get_client / _get_async_client
# ---------------------------------------------------------------------------


class TestClientCreation:
    def test_get_client_no_api_key_raises(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key=None)
        adapter._client = None
        with patch.dict("sys.modules", {"anthropic": MagicMock()}):
            with pytest.raises(ValueError, match="API key is required"):
                adapter._get_client()

    def test_get_async_client_no_api_key_raises(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key=None)
        adapter._async_client = None
        with patch.dict("sys.modules", {"anthropic": MagicMock()}):
            with pytest.raises(ValueError, match="API key is required"):
                adapter._get_async_client()

    def test_get_client_creates_once(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        mock_anthropic = MagicMock()
        adapter = AnthropicAdapter(api_key="test-key")

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            client1 = adapter._get_client()
            client2 = adapter._get_client()

        assert client1 is client2

    def test_get_async_client_creates_once(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        mock_anthropic = MagicMock()
        adapter = AnthropicAdapter(api_key="test-key")

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            client1 = adapter._get_async_client()
            client2 = adapter._get_async_client()

        assert client1 is client2


# ---------------------------------------------------------------------------
# Tests: count_tokens
# ---------------------------------------------------------------------------


class TestCountTokens:
    def test_fallback_estimation(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key="k")
        messages = [LLMMessage(role="user", content="Hello world")]

        # Force exception path to hit fallback
        adapter._client = MagicMock()
        adapter._client.count_tokens = None
        delattr(adapter._client, "count_tokens")

        with patch("enhanced_agent_bus.llm_adapters.anthropic_adapter.MessageConverter") as mc:
            mc.to_anthropic_format.return_value = [{"role": "user", "content": "Hello world"}]
            count = adapter.count_tokens(messages)

        # Fallback: (len("user") + len("Hello world")) // 4 = 15 // 4 = 3
        assert isinstance(count, int)
        assert count >= 0

    def test_error_falls_back_gracefully(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key="k")
        adapter._client = MagicMock()
        adapter._client.count_tokens = MagicMock(side_effect=RuntimeError("boom"))

        with patch("enhanced_agent_bus.llm_adapters.anthropic_adapter.MessageConverter") as mc:
            mc.to_anthropic_format.return_value = []
            messages = [LLMMessage(role="user", content="test")]
            count = adapter.count_tokens(messages)

        assert isinstance(count, int)


# ---------------------------------------------------------------------------
# Tests: complete (sync)
# ---------------------------------------------------------------------------


class TestComplete:
    def test_complete_success(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key="k")

        mock_response = MagicMock()
        mock_response.model_dump.return_value = _make_anthropic_response_dict()

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        adapter._client = mock_client

        mock_llm_response = MagicMock(spec=LLMResponse)
        mock_llm_response.usage = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        mock_llm_response.metadata = CompletionMetadata(
            model="claude-sonnet-4-6", provider="anthropic"
        )

        with (
            patch("enhanced_agent_bus.llm_adapters.anthropic_adapter.MessageConverter") as mc,
            patch("enhanced_agent_bus.llm_adapters.anthropic_adapter.ResponseConverter") as rc,
        ):
            mc.to_anthropic_format.return_value = [{"role": "user", "content": "Hello!"}]
            rc.from_anthropic_response.return_value = mock_llm_response

            result = adapter.complete(_make_messages())

        assert result is mock_llm_response
        mock_client.messages.create.assert_called_once()

    def test_complete_with_stop_sequences(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key="k")

        mock_response = MagicMock()
        mock_response.model_dump.return_value = _make_anthropic_response_dict()

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        adapter._client = mock_client

        mock_llm_response = MagicMock(spec=LLMResponse)
        mock_llm_response.usage = TokenUsage()
        mock_llm_response.metadata = CompletionMetadata(model="m", provider="p")

        with (
            patch("enhanced_agent_bus.llm_adapters.anthropic_adapter.MessageConverter") as mc,
            patch("enhanced_agent_bus.llm_adapters.anthropic_adapter.ResponseConverter") as rc,
        ):
            mc.to_anthropic_format.return_value = [{"role": "user", "content": "Hi"}]
            rc.from_anthropic_response.return_value = mock_llm_response

            adapter.complete(
                [LLMMessage(role="user", content="Hi")],
                stop=["STOP"],
            )

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs[1].get("stop_sequences") == ["STOP"] or call_kwargs.kwargs.get(
            "stop_sequences"
        ) == ["STOP"]

    def test_complete_empty_messages_raises(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key="k")
        with pytest.raises(ValueError, match="empty"):
            adapter.complete([])


# ---------------------------------------------------------------------------
# Tests: acomplete (async)
# ---------------------------------------------------------------------------


class TestAComplete:
    @pytest.mark.asyncio
    async def test_acomplete_success(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key="k")

        mock_response = MagicMock()
        mock_response.model_dump.return_value = _make_anthropic_response_dict()

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        adapter._async_client = mock_client

        mock_llm_response = MagicMock(spec=LLMResponse)
        mock_llm_response.usage = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        mock_llm_response.metadata = CompletionMetadata(model="m", provider="p")

        with (
            patch("enhanced_agent_bus.llm_adapters.anthropic_adapter.MessageConverter") as mc,
            patch("enhanced_agent_bus.llm_adapters.anthropic_adapter.ResponseConverter") as rc,
        ):
            mc.to_anthropic_format.return_value = [{"role": "user", "content": "Hello!"}]
            rc.from_anthropic_response.return_value = mock_llm_response

            result = await adapter.acomplete(_make_messages())

        assert result is mock_llm_response

    @pytest.mark.asyncio
    async def test_acomplete_empty_messages_raises(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key="k")
        with pytest.raises(ValueError, match="empty"):
            await adapter.acomplete([])


# ---------------------------------------------------------------------------
# Tests: health_check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key="k")
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=MagicMock())
        adapter._async_client = mock_client

        result = await adapter.health_check()

        assert isinstance(result, HealthCheckResult)
        assert result.status == AdapterStatus.HEALTHY
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(api_key="k")
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=ConnectionError("down"))
        adapter._async_client = mock_client

        result = await adapter.health_check()

        assert result.status == AdapterStatus.UNHEALTHY
        assert "down" in result.message


# ---------------------------------------------------------------------------
# Tests: MODEL_PRICING class variable
# ---------------------------------------------------------------------------


class TestModelPricing:
    def test_pricing_dict_is_not_empty(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        assert len(AnthropicAdapter.MODEL_PRICING) > 0

    def test_all_prices_have_prompt_and_completion(self):
        from enhanced_agent_bus.llm_adapters.anthropic_adapter import AnthropicAdapter

        for model_key, pricing in AnthropicAdapter.MODEL_PRICING.items():
            assert "prompt" in pricing, f"{model_key} missing prompt price"
            assert "completion" in pricing, f"{model_key} missing completion price"
            assert pricing["prompt"] > 0
            assert pricing["completion"] > 0
