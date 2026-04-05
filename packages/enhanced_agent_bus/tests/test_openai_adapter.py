"""Tests for llm_adapters/openai_adapter.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.llm_adapters.base import (
    AdapterStatus,
    CostEstimate,
    HealthCheckResult,
    LLMMessage,
    StreamingMode,
)
from enhanced_agent_bus.llm_adapters.openai_adapter import OpenAIAdapter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def adapter():
    """Create an adapter with a fake API key so __init__ does not fail."""
    with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-key-fake"}):
        return OpenAIAdapter(model="gpt-5.2", api_key="sk-test-key-fake")


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------


class TestOpenAIAdapterInit:
    def test_default_model(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-fake"}):
            a = OpenAIAdapter(api_key="sk-fake")
        assert a.model == "gpt-5.4"

    def test_custom_model(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-fake"}):
            a = OpenAIAdapter(model="gpt-4o", api_key="sk-fake")
        assert a.model == "gpt-4o"

    def test_provider_name(self, adapter):
        assert adapter.get_provider_name() == "openai"

    def test_streaming_mode(self, adapter):
        assert adapter.get_streaming_mode() == StreamingMode.SUPPORTED


# ---------------------------------------------------------------------------
# Cost estimation tests
# ---------------------------------------------------------------------------


class TestEstimateCost:
    def test_known_model(self, adapter):
        cost = adapter.estimate_cost(prompt_tokens=1000, completion_tokens=500)
        assert isinstance(cost, CostEstimate)
        assert cost.total_cost_usd > 0
        assert cost.currency == "USD"

    def test_unknown_model_fallback(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-fake"}):
            a = OpenAIAdapter(model="totally-unknown-model", api_key="sk-fake")
        cost = a.estimate_cost(prompt_tokens=1000, completion_tokens=500)
        # Falls back to gpt-5.4 pricing
        assert cost.total_cost_usd > 0

    def test_zero_tokens(self, adapter):
        cost = adapter.estimate_cost(prompt_tokens=0, completion_tokens=0)
        assert cost.total_cost_usd == 0.0

    def test_gpt4o_pricing(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-fake"}):
            a = OpenAIAdapter(model="gpt-4o", api_key="sk-fake")
        cost = a.estimate_cost(prompt_tokens=1000, completion_tokens=1000)
        assert cost.prompt_cost_usd == pytest.approx(2.50, abs=0.01)
        assert cost.completion_cost_usd == pytest.approx(10.00, abs=0.01)


# ---------------------------------------------------------------------------
# Token counting tests
# ---------------------------------------------------------------------------


class TestCountTokens:
    def test_count_tokens_basic(self, adapter):
        try:
            import tiktoken
        except ImportError:
            pytest.skip("tiktoken not installed")

        messages = [
            LLMMessage(role="user", content="Hello world"),
        ]
        count = adapter.count_tokens(messages)
        assert count > 0
        # At minimum: 4 (msg format) + role tokens + content tokens + 2 (reply priming)
        assert count >= 6

    def test_count_tokens_with_name(self, adapter):
        try:
            import tiktoken
        except ImportError:
            pytest.skip("tiktoken not installed")

        messages = [
            LLMMessage(role="user", content="Hi", name="Alice"),
        ]
        count = adapter.count_tokens(messages)
        assert count > 0

    def test_count_tokens_no_tiktoken(self, adapter):
        with patch.dict("sys.modules", {"tiktoken": None}):
            # Re-trigger the import error path by clearing cached encoder
            adapter._tiktoken_encoder = None
            with pytest.raises(ImportError, match="tiktoken"):
                adapter.count_tokens([LLMMessage(role="user", content="test")])


# ---------------------------------------------------------------------------
# Client creation tests
# ---------------------------------------------------------------------------


class TestClientCreation:
    def test_get_client_no_api_key_raises(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-fake"}):
            a = OpenAIAdapter(model="gpt-5.2", api_key="sk-fake")
        a.api_key = None
        with pytest.raises(ValueError, match="API key"):
            a._get_client()

    def test_get_async_client_no_api_key_raises(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-fake"}):
            a = OpenAIAdapter(model="gpt-5.2", api_key="sk-fake")
        a.api_key = None
        with pytest.raises(ValueError, match="API key"):
            a._get_async_client()

    def test_get_client_no_openai_raises(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-fake"}):
            a = OpenAIAdapter(model="gpt-5.2", api_key="sk-fake")
        with patch.dict("sys.modules", {"openai": None}):
            a._client = None
            with pytest.raises(ImportError, match="openai"):
                a._get_client()

    def test_get_async_client_no_openai_raises(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-fake"}):
            a = OpenAIAdapter(model="gpt-5.2", api_key="sk-fake")
        with patch.dict("sys.modules", {"openai": None}):
            a._async_client = None
            with pytest.raises(ImportError, match="openai"):
                a._get_async_client()


# ---------------------------------------------------------------------------
# Complete / acomplete tests (mocked)
# ---------------------------------------------------------------------------


class TestComplete:
    def _mock_response(self):
        """Build a mock OpenAI response."""
        mock_resp = MagicMock()
        mock_resp.model_dump.return_value = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "model": "gpt-5.2",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        return mock_resp

    def test_complete_sync(self, adapter):
        mock_resp = self._mock_response()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        adapter._client = mock_client

        messages = [LLMMessage(role="user", content="Hi")]
        response = adapter.complete(messages)
        assert response.content == "Hello!"
        assert response.usage.prompt_tokens == 10
        assert response.cost.total_cost_usd > 0

    @pytest.mark.asyncio
    async def test_acomplete(self, adapter):
        mock_resp = self._mock_response()
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
        adapter._async_client = mock_client

        messages = [LLMMessage(role="user", content="Hi")]
        response = await adapter.acomplete(messages)
        assert response.content == "Hello!"

    def test_complete_with_optional_params(self, adapter):
        mock_resp = self._mock_response()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        adapter._client = mock_client

        messages = [LLMMessage(role="user", content="Hi")]
        response = adapter.complete(
            messages,
            temperature=0.5,
            max_tokens=100,
            stop=["END"],
            tools=[{"type": "function"}],
            tool_choice="auto",
            response_format={"type": "json"},
            frequency_penalty=0.5,
            presence_penalty=0.5,
        )
        assert response.content == "Hello!"


# ---------------------------------------------------------------------------
# Health check tests (mocked)
# ---------------------------------------------------------------------------


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_success(self, adapter):
        mock_client = MagicMock()
        mock_client.models.list = AsyncMock(return_value=[])
        adapter._async_client = mock_client

        result = await adapter.health_check()
        assert result.status == AdapterStatus.HEALTHY
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_health_check_failure(self, adapter):
        mock_client = MagicMock()
        mock_client.models.list = AsyncMock(side_effect=ConnectionError("API down"))
        adapter._async_client = mock_client

        result = await adapter.health_check()
        assert result.status == AdapterStatus.UNHEALTHY
        assert "API down" in result.message


# ---------------------------------------------------------------------------
# Streaming helper tests
# ---------------------------------------------------------------------------


class TestStreamingHelpers:
    def test_extract_chunk_content(self, adapter):
        chunk = MagicMock()
        delta = MagicMock()
        delta.content = "world"
        choice = MagicMock()
        choice.delta = delta
        chunk.choices = [choice]
        assert adapter._extract_chunk_content(chunk) == "world"

    def test_extract_chunk_content_none(self, adapter):
        chunk = MagicMock()
        delta = MagicMock()
        delta.content = None
        choice = MagicMock()
        choice.delta = delta
        chunk.choices = [choice]
        assert adapter._extract_chunk_content(chunk) is None

    def test_extract_chunk_content_no_choices(self, adapter):
        chunk = MagicMock()
        chunk.choices = []
        assert adapter._extract_chunk_content(chunk) is None

    def test_build_streaming_params(self, adapter):
        messages = [LLMMessage(role="user", content="Hi")]
        params = adapter._build_streaming_params(
            messages,
            temperature=0.5,
            max_tokens=100,
            top_p=0.9,
            stop=["END"],
            tools=[{"type": "function"}],
        )
        assert params["stream"] is True
        assert params["temperature"] == 0.5
        assert params["max_tokens"] == 100
        assert params["stop"] == ["END"]

    def test_process_stream_chunks(self, adapter):
        chunk1 = MagicMock()
        delta1 = MagicMock()
        delta1.content = "Hello"
        choice1 = MagicMock()
        choice1.delta = delta1
        chunk1.choices = [choice1]

        chunk2 = MagicMock()
        delta2 = MagicMock()
        delta2.content = None
        choice2 = MagicMock()
        choice2.delta = delta2
        chunk2.choices = [choice2]

        results = list(adapter._process_stream_chunks(iter([chunk1, chunk2])))
        assert results == ["Hello"]


# ---------------------------------------------------------------------------
# MODEL_PRICING class var
# ---------------------------------------------------------------------------


class TestModelPricing:
    def test_pricing_dict_has_expected_models(self):
        pricing = OpenAIAdapter.MODEL_PRICING
        assert "gpt-5.2" in pricing
        assert "gpt-4o" in pricing
        assert "gpt-3.5-turbo" in pricing
        for model_pricing in pricing.values():
            assert "prompt" in model_pricing
            assert "completion" in model_pricing
