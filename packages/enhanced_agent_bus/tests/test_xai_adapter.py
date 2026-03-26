"""Tests for xAI (Grok) LLM adapter.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.llm_adapters.base import (
    AdapterStatus,
    CostEstimate,
    LLMMessage,
    StreamingMode,
)
from enhanced_agent_bus.llm_adapters.config import AdapterType, XAIAdapterConfig
from enhanced_agent_bus.llm_adapters.xai_adapter import XAI_API_BASE, XAIAdapter

# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestXAIAdapterConfig:
    """Tests for XAIAdapterConfig."""

    def test_default_config(self):
        config = XAIAdapterConfig(model="grok-4-1-fast")
        assert config.adapter_type == AdapterType.XAI
        assert config.model == "grok-4-1-fast"
        assert config.enable_web_search is False
        assert config.enable_x_search is False
        assert config.enable_code_execution is False

    def test_from_environment(self, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-test-key")
        monkeypatch.setenv("XAI_API_BASE", "https://custom.x.ai/v1")
        monkeypatch.setenv("XAI_RPM", "100")
        monkeypatch.setenv("XAI_TPM", "500000")

        config = XAIAdapterConfig.from_environment(model="grok-4.20")
        assert config.model == "grok-4.20"
        assert config.api_base == "https://custom.x.ai/v1"
        assert config.rate_limit.requests_per_minute == 100
        assert config.rate_limit.tokens_per_minute == 500000

    def test_from_environment_defaults(self, monkeypatch):
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        config = XAIAdapterConfig.from_environment()
        assert config.model == "grok-4-1-fast"
        assert config.api_base == "https://api.x.ai/v1"
        assert config.rate_limit.requests_per_minute == 607
        assert config.rate_limit.tokens_per_minute == 4_000_000

    def test_server_side_tool_flags(self):
        config = XAIAdapterConfig(
            model="grok-4.20",
            enable_web_search=True,
            enable_x_search=True,
            enable_code_execution=True,
            search_allowed_domains=["docs.x.ai"],
        )
        assert config.enable_web_search is True
        assert config.enable_x_search is True
        assert config.enable_code_execution is True
        assert config.search_allowed_domains == ["docs.x.ai"]


# ---------------------------------------------------------------------------
# Adapter tests
# ---------------------------------------------------------------------------


class TestXAIAdapter:
    """Tests for XAIAdapter."""

    def _make_adapter(self, model: str = "grok-4-1-fast") -> XAIAdapter:
        config = XAIAdapterConfig(model=model, api_base=XAI_API_BASE)
        return XAIAdapter(config=config, api_key="xai-test-key")

    def test_init_defaults(self):
        adapter = self._make_adapter()
        assert adapter.model == "grok-4-1-fast"
        assert adapter.api_key == "xai-test-key"
        assert adapter.get_provider_name() == "xai"

    def test_init_from_env(self, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-env-key")
        adapter = XAIAdapter(model="grok-4.20")
        assert adapter.model == "grok-4.20"
        assert adapter.config.api_base == XAI_API_BASE

    def test_streaming_mode(self):
        adapter = self._make_adapter()
        assert adapter.get_streaming_mode() == StreamingMode.SUPPORTED

    # -- Cost estimation ---------------------------------------------------

    def test_estimate_cost_grok_4_1_fast(self):
        adapter = self._make_adapter("grok-4-1-fast")
        cost = adapter.estimate_cost(prompt_tokens=1_000_000, completion_tokens=1_000_000)
        assert isinstance(cost, CostEstimate)
        assert cost.prompt_cost_usd == pytest.approx(0.20)
        assert cost.completion_cost_usd == pytest.approx(0.50)
        assert cost.total_cost_usd == pytest.approx(0.70)

    def test_estimate_cost_grok_4_20(self):
        adapter = self._make_adapter("grok-4.20")
        cost = adapter.estimate_cost(prompt_tokens=1_000_000, completion_tokens=1_000_000)
        assert cost.prompt_cost_usd == pytest.approx(2.00)
        assert cost.completion_cost_usd == pytest.approx(6.00)

    def test_estimate_cost_grok_4(self):
        adapter = self._make_adapter("grok-4")
        cost = adapter.estimate_cost(prompt_tokens=1_000_000, completion_tokens=1_000_000)
        assert cost.prompt_cost_usd == pytest.approx(3.00)
        assert cost.completion_cost_usd == pytest.approx(15.00)

    def test_estimate_cost_unknown_model_falls_back(self):
        adapter = self._make_adapter("grok-unknown")
        cost = adapter.estimate_cost(prompt_tokens=1_000_000, completion_tokens=1_000_000)
        # Falls back to grok-4-1-fast pricing
        assert cost.prompt_cost_usd == pytest.approx(0.20)

    def test_estimate_cost_with_cached_tokens(self):
        adapter = self._make_adapter("grok-4-1-fast")
        cost = adapter.estimate_cost(
            prompt_tokens=1_000_000,
            completion_tokens=100_000,
            cached_tokens=900_000,
        )
        # 100K uncached at $0.20/M + 900K cached at $0.05/M
        expected_prompt = (100_000 / 1e6) * 0.20 + (900_000 / 1e6) * 0.05
        assert cost.prompt_cost_usd == pytest.approx(expected_prompt)

    def test_estimate_cost_with_reasoning_tokens(self):
        adapter = self._make_adapter("grok-4-1-fast")
        cost = adapter.estimate_cost(
            prompt_tokens=100_000,
            completion_tokens=10_000,
            reasoning_tokens=300_000,
        )
        # Reasoning tokens billed at completion rate
        expected_completion = ((10_000 + 300_000) / 1e6) * 0.50
        assert cost.completion_cost_usd == pytest.approx(expected_completion)

    def test_estimate_cost_from_real_xai_response(self):
        """Test cost from actual xAI response shape (reasoning + cached)."""
        adapter = self._make_adapter("grok-4-1-fast")
        usage = {
            "prompt_tokens": 174,
            "completion_tokens": 3,
            "total_tokens": 501,
            "prompt_tokens_details": {
                "text_tokens": 174,
                "audio_tokens": 0,
                "image_tokens": 0,
                "cached_tokens": 173,
            },
            "completion_tokens_details": {
                "reasoning_tokens": 324,
                "audio_tokens": 0,
                "accepted_prediction_tokens": 0,
                "rejected_prediction_tokens": 0,
            },
        }
        cost = adapter._estimate_cost_from_usage(usage)
        assert cost.prompt_cost_usd > 0
        assert cost.completion_cost_usd > 0
        # Reasoning tokens (324) + completion (3) = 327 at $0.50/M
        expected_completion = (327 / 1e6) * 0.50
        assert cost.completion_cost_usd == pytest.approx(expected_completion)

    # -- Completion (mocked) -----------------------------------------------

    @patch("enhanced_agent_bus.llm_adapters.xai_adapter.XAIAdapter._get_client")
    def test_complete_calls_openai_client(self, mock_get_client):
        adapter = self._make_adapter()

        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "id": "chatcmpl-xai-123",
            "object": "chat.completion",
            "model": "grok-4-1-fast",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello from Grok!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        messages = [LLMMessage(role="user", content="Hello!")]
        response = adapter.complete(messages, temperature=0.5, max_tokens=100)

        assert response.content == "Hello from Grok!"
        assert response.metadata.provider == "xai"
        assert response.usage.total_tokens == 15

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs[1]["model"] == "grok-4-1-fast"

    # -- Async completion (mocked) -----------------------------------------

    @pytest.mark.asyncio
    @patch("enhanced_agent_bus.llm_adapters.xai_adapter.XAIAdapter._get_async_client")
    async def test_acomplete_calls_async_client(self, mock_get_async_client):
        adapter = self._make_adapter()

        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "id": "chatcmpl-xai-456",
            "object": "chat.completion",
            "model": "grok-4-1-fast",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Async Grok!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 8,
                "completion_tokens": 3,
                "total_tokens": 11,
            },
        }

        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_async_client.return_value = mock_client

        messages = [LLMMessage(role="user", content="Hello async!")]
        response = await adapter.acomplete(messages, temperature=0.3)

        assert response.content == "Async Grok!"
        assert response.metadata.provider == "xai"

    # -- Health check (mocked) --------------------------------------------

    @pytest.mark.asyncio
    @patch("enhanced_agent_bus.llm_adapters.xai_adapter.XAIAdapter._get_async_client")
    async def test_health_check_healthy(self, mock_get_async_client):
        adapter = self._make_adapter()

        mock_client = AsyncMock()
        mock_client.models.list.return_value = MagicMock()
        mock_get_async_client.return_value = mock_client

        result = await adapter.health_check()
        assert result.status == AdapterStatus.HEALTHY
        assert result.details["provider"] == "xai"

    @pytest.mark.asyncio
    @patch("enhanced_agent_bus.llm_adapters.xai_adapter.XAIAdapter._get_async_client")
    async def test_health_check_unhealthy(self, mock_get_async_client):
        adapter = self._make_adapter()

        mock_client = AsyncMock()
        mock_client.models.list.side_effect = ConnectionError("timeout")
        mock_get_async_client.return_value = mock_client

        result = await adapter.health_check()
        assert result.status == AdapterStatus.UNHEALTHY

    # -- Client creation ---------------------------------------------------

    def test_get_client_requires_api_key(self):
        config = XAIAdapterConfig(model="grok-4-1-fast", api_base=XAI_API_BASE)
        adapter = XAIAdapter(config=config, api_key=None)
        adapter.api_key = None

        with pytest.raises(ValueError, match="xAI API key is required"):
            adapter._get_client()

    def test_get_async_client_requires_api_key(self):
        config = XAIAdapterConfig(model="grok-4-1-fast", api_base=XAI_API_BASE)
        adapter = XAIAdapter(config=config, api_key=None)
        adapter.api_key = None

        with pytest.raises(ValueError, match="xAI API key is required"):
            adapter._get_async_client()

    # -- xAI server-side tools pass-through --------------------------------

    @patch("enhanced_agent_bus.llm_adapters.xai_adapter.XAIAdapter._get_client")
    def test_xai_tools_passed_through(self, mock_get_client):
        adapter = self._make_adapter()

        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "id": "chatcmpl-tools",
            "object": "chat.completion",
            "model": "grok-4-1-fast",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Found results."},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
        }

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        xai_tools = [{"type": "web_search"}, {"type": "x_search"}]
        messages = [LLMMessage(role="user", content="Search for xAI news")]
        adapter.complete(messages, xai_tools=xai_tools)

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs[1]["tools"] == xai_tools
