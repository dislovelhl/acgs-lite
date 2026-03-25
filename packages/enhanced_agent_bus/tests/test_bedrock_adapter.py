"""
Tests for llm_adapters/bedrock_adapter.py - BedrockAdapter.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.llm_adapters.base import (
    AdapterStatus,
    LLMMessage,
    StreamingMode,
)
from enhanced_agent_bus.llm_adapters.bedrock_adapter import BedrockAdapter
from enhanced_agent_bus.llm_adapters.config import AWSBedrockAdapterConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(
    model: str = "anthropic.claude-sonnet-4-6-v1:0",
    **kw,
) -> AWSBedrockAdapterConfig:
    return AWSBedrockAdapterConfig.from_environment(model=model, **kw)


def _adapter(model: str = "anthropic.claude-sonnet-4-6-v1:0") -> BedrockAdapter:
    cfg = _config(model=model)
    return BedrockAdapter(config=cfg)


def _messages(user: str = "Hi") -> list[LLMMessage]:
    return [LLMMessage(role="user", content=user)]


def _anthropic_response(content: str = "Hello") -> str:
    return json.dumps(
        {
            "content": [{"type": "text", "text": content}],
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }
    )


def _meta_response(content: str = "Hello") -> str:
    return json.dumps(
        {
            "generation": content,
            "prompt_token_count": 10,
            "generation_token_count": 20,
        }
    )


def _amazon_response(content: str = "Hello") -> str:
    return json.dumps(
        {
            "results": [{"outputText": content, "tokenCount": 20}],
            "inputTextTokenCount": 10,
        }
    )


def _cohere_response(content: str = "Hello") -> str:
    return json.dumps({"text": content})


def _ai21_response(content: str = "Hello") -> str:
    return json.dumps({"completions": [{"data": {"text": content}}]})


def _generic_response(content: str = "Hello") -> str:
    return json.dumps({"completion": content})


# ===========================================================================
# Initialization
# ===========================================================================


class TestInit:
    def test_default_model(self):
        adapter = BedrockAdapter()
        assert "anthropic" in adapter.model or "claude" in adapter.model

    def test_explicit_model(self):
        adapter = BedrockAdapter(model="meta.llama3-8b-instruct-v1:0")
        assert adapter.model == "meta.llama3-8b-instruct-v1:0"

    def test_with_config(self):
        cfg = _config("amazon.titan-text-express-v1")
        adapter = BedrockAdapter(config=cfg)
        assert adapter.model == "amazon.titan-text-express-v1"

    def test_api_key_is_none(self):
        adapter = _adapter()
        assert adapter.api_key is None


# ===========================================================================
# Provider detection
# ===========================================================================


class TestGetProvider:
    @pytest.mark.parametrize(
        "model,expected",
        [
            ("anthropic.claude-sonnet-4-6-v1:0", "anthropic"),
            ("meta.llama3-8b-instruct-v1:0", "meta"),
            ("amazon.titan-text-express-v1", "amazon"),
            ("cohere.command-r-plus-v1:0", "cohere"),
            ("ai21.jamba-instruct-v1:0", "ai21"),
            ("unknown.model-v1", "anthropic"),  # fallback
        ],
    )
    def test_provider_detection(self, model, expected):
        adapter = _adapter(model)
        assert adapter._get_provider() == expected

    def test_provider_cached(self):
        adapter = _adapter()
        _ = adapter._get_provider()
        _ = adapter._get_provider()
        assert adapter._provider is not None


# ===========================================================================
# Request body building
# ===========================================================================


class TestBuildRequestBody:
    def test_anthropic_body(self):
        adapter = _adapter("anthropic.claude-sonnet-4-6-v1:0")
        msgs = [
            LLMMessage(role="system", content="Be helpful"),
            LLMMessage(role="user", content="Hi"),
        ]
        body_str = adapter._build_request_body(msgs, temperature=0.5, max_tokens=100)
        body = json.loads(body_str)
        assert body["anthropic_version"] == "bedrock-2023-05-31"
        assert body["system"] == "Be helpful"
        assert body["max_tokens"] == 100

    def test_anthropic_body_with_stop(self):
        adapter = _adapter("anthropic.claude-sonnet-4-6-v1:0")
        body_str = adapter._build_request_body(_messages(), stop=["END"], top_k=10)
        body = json.loads(body_str)
        assert body["stop_sequences"] == ["END"]
        assert body["top_k"] == 10

    def test_meta_body(self):
        adapter = _adapter("meta.llama3-8b-instruct-v1:0")
        body_str = adapter._build_request_body(_messages(), max_tokens=200)
        body = json.loads(body_str)
        assert "prompt" in body
        assert body["max_gen_len"] == 200

    def test_amazon_body(self):
        adapter = _adapter("amazon.titan-text-express-v1")
        body_str = adapter._build_request_body(_messages(), stop=["END"])
        body = json.loads(body_str)
        assert "inputText" in body
        assert body["textGenerationConfig"]["stopSequences"] == ["END"]

    def test_cohere_body(self):
        adapter = _adapter("cohere.command-r-plus-v1:0")
        msgs = [
            LLMMessage(role="user", content="First"),
            LLMMessage(role="assistant", content="Reply"),
            LLMMessage(role="user", content="Second"),
        ]
        body_str = adapter._build_request_body(msgs)
        body = json.loads(body_str)
        assert body["message"] == "Second"
        assert len(body["chat_history"]) == 2

    def test_ai21_body(self):
        adapter = _adapter("ai21.jamba-instruct-v1:0")
        body_str = adapter._build_request_body(_messages(), stop=["END"])
        body = json.loads(body_str)
        assert "prompt" in body
        assert body["stopSequences"] == ["END"]

    def test_generic_body(self):
        # Unknown model defaults to anthropic provider, so uses anthropic format
        adapter = _adapter("unknown.model-v1")
        body_str = adapter._build_request_body(_messages())
        body = json.loads(body_str)
        assert "messages" in body  # anthropic format

    def test_default_max_tokens(self):
        adapter = _adapter()
        body_str = adapter._build_request_body(_messages(), max_tokens=None)
        body = json.loads(body_str)
        assert body["max_tokens"] == 4096


# ===========================================================================
# Response parsing
# ===========================================================================


class TestParseResponseBody:
    def test_anthropic_response(self):
        adapter = _adapter("anthropic.claude-sonnet-4-6-v1:0")
        content, usage = adapter._parse_response_body(_anthropic_response("Hi"))
        assert content == "Hi"
        assert usage.prompt_tokens == 10
        assert usage.completion_tokens == 20

    def test_meta_response(self):
        adapter = _adapter("meta.llama3-8b-instruct-v1:0")
        content, usage = adapter._parse_response_body(_meta_response("Yo"))
        assert content == "Yo"
        assert usage.total_tokens == 30

    def test_amazon_response(self):
        adapter = _adapter("amazon.titan-text-express-v1")
        content, usage = adapter._parse_response_body(_amazon_response("Hi"))
        assert content == "Hi"

    def test_cohere_response(self):
        adapter = _adapter("cohere.command-r-plus-v1:0")
        content, usage = adapter._parse_response_body(_cohere_response("Hi"))
        assert content == "Hi"
        assert usage.total_tokens == 0

    def test_ai21_response(self):
        adapter = _adapter("ai21.jamba-instruct-v1:0")
        content, usage = adapter._parse_response_body(_ai21_response("Hi"))
        assert content == "Hi"

    def test_generic_response(self):
        # Unknown model defaults to anthropic provider
        adapter = _adapter("unknown.model-v1")
        content, usage = adapter._parse_response_body(_anthropic_response("Hi"))
        assert content == "Hi"


# ===========================================================================
# Complete (sync)
# ===========================================================================


class TestComplete:
    def test_complete_success(self):
        adapter = _adapter()
        mock_body = MagicMock()
        mock_body.read.return_value = _anthropic_response("World").encode()
        mock_client = MagicMock()
        mock_client.invoke_model.return_value = {
            "body": mock_body,
            "ResponseMetadata": {"RequestId": "req-123"},
        }
        adapter._client = mock_client

        response = adapter.complete(_messages())
        assert response.content == "World"
        assert "bedrock-anthropic" in response.metadata.provider

    def test_complete_with_guardrails(self):
        cfg = _config()
        cfg.guardrails_id = "guard-1"
        cfg.guardrails_version = "1"
        adapter = BedrockAdapter(config=cfg)

        mock_body = MagicMock()
        mock_body.read.return_value = _anthropic_response("ok").encode()
        mock_client = MagicMock()
        mock_client.invoke_model.return_value = {
            "body": mock_body,
            "ResponseMetadata": {},
        }
        adapter._client = mock_client

        adapter.complete(_messages())
        call_kwargs = mock_client.invoke_model.call_args.kwargs
        assert call_kwargs["guardrailIdentifier"] == "guard-1"

    def test_complete_empty_messages_raises(self):
        adapter = _adapter()
        with pytest.raises(ValueError, match="empty"):
            adapter.complete([])

    def test_complete_api_error(self):
        adapter = _adapter()
        mock_client = MagicMock()
        mock_client.invoke_model.side_effect = RuntimeError("AWS error")
        adapter._client = mock_client

        with pytest.raises(RuntimeError, match="AWS error"):
            adapter.complete(_messages())


# ===========================================================================
# Async complete
# ===========================================================================


class TestAComplete:
    @pytest.mark.asyncio
    async def test_acomplete_sync_fallback(self):
        """When aioboto3 is not available, falls back to sync client."""
        adapter = _adapter()
        adapter._async_client = None  # Force sync fallback

        mock_body = MagicMock()
        mock_body.read.return_value = _anthropic_response("async").encode()
        mock_client = MagicMock()
        mock_client.invoke_model.return_value = {
            "body": mock_body,
            "ResponseMetadata": {},
        }
        adapter._client = mock_client

        response = await adapter.acomplete(_messages())
        assert response.content == "async"


# ===========================================================================
# Token counting
# ===========================================================================


class TestCountTokens:
    @pytest.mark.parametrize(
        "model,provider",
        [
            ("anthropic.claude-sonnet-4-6-v1:0", "anthropic"),
            ("meta.llama3-8b-instruct-v1:0", "meta"),
            ("cohere.command-r-plus-v1:0", "cohere"),
        ],
    )
    def test_count_tokens(self, model, provider):
        adapter = _adapter(model)
        count = adapter.count_tokens(_messages("Hello world, how are you?"))
        assert count > 0


# ===========================================================================
# Cost estimation
# ===========================================================================


class TestEstimateCost:
    def test_known_model(self):
        adapter = _adapter("anthropic.claude-sonnet-4-6-v1:0")
        cost = adapter.estimate_cost(1000, 500)
        assert cost.total_cost_usd > 0
        assert cost.pricing_model == "anthropic.claude-sonnet-4-6-v1:0"

    def test_unknown_model_uses_default(self):
        adapter = _adapter("unknown.model-v1")
        cost = adapter.estimate_cost(1000, 500)
        assert cost.total_cost_usd > 0


# ===========================================================================
# Stream text extraction
# ===========================================================================


class TestExtractStreamText:
    def test_no_chunk(self):
        adapter = _adapter()
        assert adapter._extract_stream_text({}) is None

    def test_anthropic_chunk(self):
        text = BedrockAdapter._extract_anthropic_chunk_text(
            {"delta": {"type": "content_block_delta", "delta": {"text": "hi"}}}
        )
        assert text == "hi"

    def test_meta_chunk(self):
        text = BedrockAdapter._extract_meta_chunk_text({"generation": "yo"})
        assert text == "yo"

    def test_amazon_chunk(self):
        text = BedrockAdapter._extract_amazon_chunk_text({"outputText": "ok"})
        assert text == "ok"

    def test_generic_chunk(self):
        text = BedrockAdapter._extract_generic_chunk_text({"text": "gen"})
        assert text == "gen"


# ===========================================================================
# Misc
# ===========================================================================


class TestMisc:
    def test_get_streaming_mode(self):
        adapter = _adapter()
        assert adapter.get_streaming_mode() == StreamingMode.SUPPORTED

    def test_get_provider_name(self):
        adapter = _adapter()
        assert adapter.get_provider_name() == "bedrock-anthropic"

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        adapter = _adapter()
        # Force acomplete to raise
        adapter.acomplete = AsyncMock(side_effect=RuntimeError("no connection"))
        result = await adapter.health_check()
        assert result.status == AdapterStatus.UNHEALTHY
        assert "failed" in result.message.lower()

    def test_build_streaming_params(self):
        adapter = _adapter()
        params = adapter._build_streaming_params(_messages(), 0.7, 100, 1.0, None)
        assert params["modelId"] == adapter.model
        assert "body" in params

    def test_build_streaming_params_with_guardrails(self):
        cfg = _config()
        cfg.guardrails_id = "g1"
        cfg.guardrails_version = "v1"
        adapter = BedrockAdapter(config=cfg)
        params = adapter._build_streaming_params(_messages(), 0.7, 100, 1.0, None)
        assert params["guardrailIdentifier"] == "g1"

    def test_format_generic_prompt(self):
        adapter = _adapter()
        msgs = [
            LLMMessage(role="system", content="sys"),
            LLMMessage(role="user", content="usr"),
            LLMMessage(role="assistant", content="ast"),
        ]
        prompt = adapter._format_generic_prompt(
            msgs,
            system_prefix="S:",
            user_prefix="U:",
            assistant_prefix="A:",
            final_suffix="END",
        )
        assert "S:sys" in prompt
        assert "U:usr" in prompt
        assert "A:ast" in prompt
        assert prompt.endswith("END")
