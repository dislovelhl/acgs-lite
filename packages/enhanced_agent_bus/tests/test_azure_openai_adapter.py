"""Tests for enhanced_agent_bus.llm_adapters.azure_openai_adapter — coverage boost.

Constitutional Hash: 608508a9bd224290

Tests the AzureOpenAIAdapter class including initialization, request preparation,
response processing, token counting, cost estimation, streaming, and health checks.
All external dependencies (openai, tiktoken, azure.identity) are mocked.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.llm_adapters.azure_openai_adapter import AzureOpenAIAdapter
from enhanced_agent_bus.llm_adapters.base import (
    AdapterStatus,
    CostEstimate,
    HealthCheckResult,
    LLMMessage,
    LLMResponse,
    StreamingMode,
)
from enhanced_agent_bus.llm_adapters.config import AzureOpenAIAdapterConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_config(**overrides):
    """Create an AzureOpenAIAdapterConfig with sensible test defaults."""
    defaults = {
        "model": "gpt-5.4",
        "deployment_name": "test-deployment",
        "azure_endpoint": "https://test.openai.azure.com",
        "api_version": "2024-02-15-preview",
        "use_managed_identity": False,
    }
    defaults.update(overrides)
    return AzureOpenAIAdapterConfig(**defaults)


def _make_adapter(config=None, api_key="test-api-key", **kw):
    """Create an AzureOpenAIAdapter with a test config."""
    if config is None:
        config = _make_config()
    return AzureOpenAIAdapter(config=config, api_key=api_key, **kw)


def _make_messages():
    """Create a minimal list of LLMMessages."""
    return [LLMMessage(role="user", content="Hello")]


def _mock_openai_response():
    """Create a mock OpenAI response object."""
    choice = MagicMock()
    choice.message = MagicMock(content="Hello back", role="assistant")
    choice.finish_reason = "stop"
    choice.content_filter_results = None

    usage = MagicMock()
    usage.prompt_tokens = 10
    usage.completion_tokens = 5
    usage.total_tokens = 15

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    response.model = "gpt-5.4"
    response.id = "chatcmpl-test"
    response.created = 1234567890
    response.prompt_filter_results = None
    response.model_dump.return_value = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": "gpt-5.4",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello back"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }
    return response


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestAzureOpenAIAdapterInit:
    def test_init_with_config(self):
        adapter = _make_adapter()
        assert adapter.model == "gpt-5.4"
        assert adapter.deployment_name == "test-deployment"
        assert adapter.api_key == "test-api-key"

    def test_init_without_config_requires_deployment_name(self):
        with pytest.raises(ValueError, match="deployment_name is required"):
            AzureOpenAIAdapter(config=None, deployment_name=None)

    def test_init_without_config_default_model(self):
        with patch.dict(
            "os.environ",
            {"AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com"},
            clear=False,
        ):
            adapter = AzureOpenAIAdapter(
                config=None,
                deployment_name="my-deploy",
                api_key="key",
            )
            assert adapter.model == "gpt-5.4"

    def test_provider_name(self):
        adapter = _make_adapter()
        assert adapter.get_provider_name() == "azure_openai"

    def test_streaming_mode(self):
        adapter = _make_adapter()
        assert adapter.get_streaming_mode() == StreamingMode.SUPPORTED


# ---------------------------------------------------------------------------
# _get_credential
# ---------------------------------------------------------------------------


class TestGetCredential:
    def test_returns_none_when_not_managed_identity(self):
        config = _make_config(use_managed_identity=False)
        adapter = _make_adapter(config=config)
        assert adapter._get_credential() is None

    def test_managed_identity_imports_azure(self):
        config = _make_config(use_managed_identity=True)
        adapter = _make_adapter(config=config)
        mock_cred = MagicMock()

        with patch("enhanced_agent_bus.llm_adapters.azure_openai_adapter.import_module") as m:
            mock_module = MagicMock()
            mock_module.DefaultAzureCredential.return_value = mock_cred
            m.return_value = mock_module
            cred = adapter._get_credential()
            assert cred is mock_cred

    def test_managed_identity_import_error(self):
        config = _make_config(use_managed_identity=True)
        adapter = _make_adapter(config=config)

        with patch(
            "enhanced_agent_bus.llm_adapters.azure_openai_adapter.import_module",
            side_effect=ImportError("no azure"),
        ):
            with pytest.raises(ImportError, match="azure-identity"):
                adapter._get_credential()


# ---------------------------------------------------------------------------
# _get_client / _get_async_client
# ---------------------------------------------------------------------------


class TestGetClient:
    def test_get_client_no_openai_raises(self):
        adapter = _make_adapter()
        with patch.dict("sys.modules", {"openai": None}):
            with patch(
                "enhanced_agent_bus.llm_adapters.azure_openai_adapter.AzureOpenAIAdapter._get_client",
                wraps=adapter._get_client,
            ):
                # Direct import mock
                with patch(
                    "builtins.__import__",
                    side_effect=ImportError("no openai"),
                ):
                    with pytest.raises(ImportError):
                        adapter._client = None
                        adapter._get_client()

    def test_get_client_no_endpoint_raises(self):
        config = _make_config(azure_endpoint=None)
        config.api_base = None
        adapter = _make_adapter(config=config)
        adapter._client = None

        # Mock openai import to succeed
        mock_openai_cls = MagicMock()
        with patch.dict("sys.modules", {"openai": MagicMock(AzureOpenAI=mock_openai_cls)}):
            with pytest.raises(ValueError, match="endpoint is required"):
                adapter._get_client()


class TestGetAsyncClient:
    def test_get_async_client_no_endpoint_raises(self):
        config = _make_config(azure_endpoint=None)
        config.api_base = None
        adapter = _make_adapter(config=config)
        adapter._async_client = None

        mock_cls = MagicMock()
        with patch.dict("sys.modules", {"openai": MagicMock(AsyncAzureOpenAI=mock_cls)}):
            with pytest.raises(ValueError, match="endpoint is required"):
                adapter._get_async_client()


# ---------------------------------------------------------------------------
# _prepare_request_params
# ---------------------------------------------------------------------------


class TestPrepareRequestParams:
    def test_basic_params(self):
        adapter = _make_adapter()
        msgs = _make_messages()
        params = adapter._prepare_request_params(msgs)
        assert params["model"] == "test-deployment"
        assert "messages" in params
        assert params["temperature"] == 0.7
        assert "stream" not in params

    def test_with_max_tokens_and_stop(self):
        adapter = _make_adapter()
        msgs = _make_messages()
        params = adapter._prepare_request_params(msgs, max_tokens=100, stop=["END"], stream=True)
        assert params["max_tokens"] == 100
        assert params["stop"] == ["END"]
        assert params["stream"] is True


# ---------------------------------------------------------------------------
# _add_optional_parameters
# ---------------------------------------------------------------------------


class TestAddOptionalParameters:
    def test_adds_tools(self):
        adapter = _make_adapter()
        params = {}
        adapter._add_optional_parameters(params, tools=[{"type": "function"}])
        assert "tools" in params

    def test_ignores_empty(self):
        adapter = _make_adapter()
        params = {}
        adapter._add_optional_parameters(params, tools=None)
        assert "tools" not in params


# ---------------------------------------------------------------------------
# _extract_stream_content
# ---------------------------------------------------------------------------


class TestExtractStreamContent:
    def test_extracts_content(self):
        chunk = MagicMock()
        delta = MagicMock()
        delta.content = "hello"
        chunk.choices = [MagicMock(delta=delta)]
        assert AzureOpenAIAdapter._extract_stream_content(chunk) == "hello"

    def test_returns_none_no_choices(self):
        chunk = MagicMock()
        chunk.choices = []
        assert AzureOpenAIAdapter._extract_stream_content(chunk) is None

    def test_returns_none_empty_content(self):
        chunk = MagicMock()
        delta = MagicMock()
        delta.content = ""
        chunk.choices = [MagicMock(delta=delta)]
        assert AzureOpenAIAdapter._extract_stream_content(chunk) is None

    def test_returns_none_no_delta(self):
        chunk = MagicMock()
        choice = MagicMock(spec=[])  # No delta attribute
        del choice.delta
        chunk.choices = [choice]
        assert AzureOpenAIAdapter._extract_stream_content(chunk) is None


# ---------------------------------------------------------------------------
# _extract_content_filter_results
# ---------------------------------------------------------------------------


class TestExtractContentFilterResults:
    def test_extracts_prompt_filter(self):
        adapter = _make_adapter()
        response = MagicMock()
        response.prompt_filter_results = [{"severity": "safe"}]
        response.choices = []

        llm_resp = MagicMock()
        llm_resp.metadata.extra = {}

        adapter._extract_content_filter_results(response, llm_resp)
        assert "prompt_filter_results" in llm_resp.metadata.extra

    def test_no_filter_results(self):
        adapter = _make_adapter()
        response = MagicMock(spec=[])
        llm_resp = MagicMock()
        llm_resp.metadata.extra = {}
        adapter._extract_content_filter_results(response, llm_resp)
        assert "prompt_filter_results" not in llm_resp.metadata.extra


# ---------------------------------------------------------------------------
# estimate_cost
# ---------------------------------------------------------------------------


class TestEstimateCost:
    def test_known_model(self):
        adapter = _make_adapter()
        cost = adapter.estimate_cost(1000, 500)
        assert isinstance(cost, CostEstimate)
        assert cost.total_cost_usd > 0
        assert cost.currency == "USD"

    def test_unknown_model_falls_back(self):
        config = _make_config(model="unknown-model-xyz")
        adapter = _make_adapter(config=config)
        cost = adapter.estimate_cost(1000, 500)
        # Should fall back to gpt-5.2 pricing
        assert cost.total_cost_usd > 0

    def test_zero_tokens(self):
        adapter = _make_adapter()
        cost = adapter.estimate_cost(0, 0)
        assert cost.total_cost_usd == 0.0


# ---------------------------------------------------------------------------
# count_tokens
# ---------------------------------------------------------------------------


class TestCountTokens:
    def test_count_tokens_basic(self):
        adapter = _make_adapter()
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = [1, 2, 3]
        adapter._tiktoken_encoder = mock_encoder

        msgs = [LLMMessage(role="user", content="hello")]
        count = adapter.count_tokens(msgs)
        # 4 (formatting) + 3 (role) + 3 (content) + 2 (reply priming) = 12
        assert count > 0

    def test_count_tokens_with_name(self):
        adapter = _make_adapter()
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = [1, 2]
        adapter._tiktoken_encoder = mock_encoder

        msgs = [LLMMessage(role="user", content="hi", name="bob")]
        count = adapter.count_tokens(msgs)
        assert count > 0

    def test_count_tokens_empty_content(self):
        adapter = _make_adapter()
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = [1]
        adapter._tiktoken_encoder = mock_encoder

        msgs = [LLMMessage(role="user", content="")]
        count = adapter.count_tokens(msgs)
        assert count > 0


# ---------------------------------------------------------------------------
# _get_tiktoken_encoder
# ---------------------------------------------------------------------------


class TestGetTiktokenEncoder:
    def test_import_error(self):
        adapter = _make_adapter()
        adapter._tiktoken_encoder = None
        with patch.dict("sys.modules", {"tiktoken": None}):
            with patch("builtins.__import__", side_effect=ImportError("no tiktoken")):
                with pytest.raises(ImportError, match="tiktoken"):
                    adapter._get_tiktoken_encoder()


# ---------------------------------------------------------------------------
# complete (sync)
# ---------------------------------------------------------------------------


class TestComplete:
    def test_complete_success(self):
        adapter = _make_adapter()
        mock_response = _mock_openai_response()

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        adapter._client = mock_client

        msgs = _make_messages()
        result = adapter.complete(msgs)
        assert isinstance(result, LLMResponse)

    def test_complete_raises_on_error(self):
        adapter = _make_adapter()
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("API error")
        adapter._client = mock_client

        msgs = _make_messages()
        with pytest.raises(RuntimeError, match="API error"):
            adapter.complete(msgs)

    def test_complete_validates_empty_messages(self):
        adapter = _make_adapter()
        with pytest.raises(ValueError, match="empty"):
            adapter.complete([])


# ---------------------------------------------------------------------------
# acomplete (async)
# ---------------------------------------------------------------------------


class TestAcomplete:
    @pytest.mark.asyncio
    async def test_acomplete_success(self):
        adapter = _make_adapter()
        mock_response = _mock_openai_response()

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        adapter._async_client = mock_client

        msgs = _make_messages()
        result = await adapter.acomplete(msgs)
        assert isinstance(result, LLMResponse)

    @pytest.mark.asyncio
    async def test_acomplete_raises_on_error(self):
        adapter = _make_adapter()
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("async fail")
        adapter._async_client = mock_client

        msgs = _make_messages()
        with pytest.raises(RuntimeError, match="async fail"):
            await adapter.acomplete(msgs)


# ---------------------------------------------------------------------------
# stream (sync)
# ---------------------------------------------------------------------------


class TestStream:
    def test_stream_yields_content(self):
        adapter = _make_adapter()
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock(delta=MagicMock(content="Hello"))]
        chunk2 = MagicMock()
        chunk2.choices = [MagicMock(delta=MagicMock(content=" world"))]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = iter([chunk1, chunk2])
        adapter._client = mock_client

        msgs = _make_messages()
        chunks = list(adapter.stream(msgs))
        assert chunks == ["Hello", " world"]

    def test_stream_raises_on_error(self):
        adapter = _make_adapter()
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("stream fail")
        adapter._client = mock_client

        msgs = _make_messages()
        with pytest.raises(RuntimeError):
            list(adapter.stream(msgs))


# ---------------------------------------------------------------------------
# astream (async)
# ---------------------------------------------------------------------------


class TestAstream:
    @pytest.mark.asyncio
    async def test_astream_yields_content(self):
        adapter = _make_adapter()
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock(delta=MagicMock(content="Hi"))]

        class MockAsyncIter:
            def __init__(self):
                self._items = [chunk1]
                self._idx = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._idx >= len(self._items):
                    raise StopAsyncIteration
                item = self._items[self._idx]
                self._idx += 1
                return item

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MockAsyncIter()
        adapter._async_client = mock_client

        msgs = _make_messages()
        chunks = []
        async for chunk in adapter.astream(msgs):
            chunks.append(chunk)
        assert chunks == ["Hi"]


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy(self):
        adapter = _make_adapter()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock()
        adapter._async_client = mock_client

        result = await adapter.health_check()
        assert isinstance(result, HealthCheckResult)
        assert result.status == AdapterStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_unhealthy(self):
        adapter = _make_adapter()
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("down")
        adapter._async_client = mock_client

        result = await adapter.health_check()
        assert result.status == AdapterStatus.UNHEALTHY
        assert "down" in result.message
