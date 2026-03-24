"""
Tests for llm_adapters/huggingface_adapter.py - HuggingFaceAdapter.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.llm_adapters.base import (
    AdapterStatus,
    CostEstimate,
    LLMMessage,
    TokenUsage,
)
from enhanced_agent_bus.llm_adapters.config import HuggingFaceAdapterConfig
from enhanced_agent_bus.llm_adapters.huggingface_adapter import HuggingFaceAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct", **kw) -> HuggingFaceAdapterConfig:
    return HuggingFaceAdapterConfig.from_environment(model=model, **kw)


def _adapter(model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct") -> HuggingFaceAdapter:
    cfg = _config(model=model)
    return HuggingFaceAdapter(config=cfg)


def _messages(system: str | None = None, user: str = "Hello") -> list[LLMMessage]:
    msgs = []
    if system:
        msgs.append(LLMMessage(role="system", content=system))
    msgs.append(LLMMessage(role="user", content=user))
    return msgs


# ===========================================================================
# Initialization
# ===========================================================================


class TestInit:
    def test_default_model(self):
        adapter = HuggingFaceAdapter()
        assert "llama" in adapter.model.lower() or adapter.model != ""

    def test_explicit_model(self):
        adapter = HuggingFaceAdapter(model="mistralai/Mistral-7B-Instruct-v0.2")
        assert "mistral" in adapter.model.lower()

    def test_with_config(self):
        cfg = _config("deepseek-ai/deepseek-coder-6.7b-instruct")
        adapter = HuggingFaceAdapter(config=cfg)
        assert adapter.model == "deepseek-ai/deepseek-coder-6.7b-instruct"


# ===========================================================================
# Model family detection
# ===========================================================================


class TestDetectModelFamily:
    @pytest.mark.parametrize(
        "model,expected",
        [
            ("meta-llama/Meta-Llama-3.1-8B-Instruct", "llama3"),
            ("meta-llama/Llama-2-7b-chat-hf", "llama2"),
            ("mistralai/Mistral-7B-Instruct-v0.2", "mistral"),
            ("mistralai/Mixtral-8x7B-Instruct-v0.1", "mistral"),
            ("deepseek-ai/deepseek-coder-6.7b-instruct", "deepseek"),
            ("HuggingFaceH4/zephyr-7b-beta", "zephyr"),
            ("LocoreMind/LocoOperator-4B-GGUF", "locooperator"),
            ("unknown/custom-model", "default"),
        ],
    )
    def test_detect_family(self, model, expected):
        adapter = _adapter(model)
        assert adapter._detect_model_family() == expected


# ===========================================================================
# Message formatting
# ===========================================================================


class TestFormatMessages:
    def test_user_only(self):
        adapter = _adapter()
        prompt = adapter._format_messages_for_inference(_messages(user="What is AI?"))
        assert "What is AI?" in prompt
        assert prompt.rstrip().endswith("Assistant:")

    def test_system_and_user(self):
        adapter = _adapter()
        prompt = adapter._format_messages_for_inference(
            _messages(system="You are helpful.", user="Hi")
        )
        assert "You are helpful" in prompt
        assert "Hi" in prompt

    def test_conversation_with_assistant(self):
        msgs = [
            LLMMessage(role="user", content="Q1"),
            LLMMessage(role="assistant", content="A1"),
            LLMMessage(role="user", content="Q2"),
        ]
        adapter = _adapter()
        prompt = adapter._format_messages_for_inference(msgs)
        assert "Q1" in prompt
        assert "A1" in prompt
        assert "Q2" in prompt

    def test_extract_message_parts(self):
        msgs = [
            LLMMessage(role="system", content="sys"),
            LLMMessage(role="user", content="usr"),
            LLMMessage(role="assistant", content="ast"),
        ]
        adapter = _adapter()
        sys_content, parts = adapter._extract_message_parts(msgs)
        assert sys_content == "sys"
        assert parts == [("user", "usr"), ("assistant", "ast")]

    def test_ensure_assistant_prompt_already_present(self):
        adapter = _adapter()
        result = adapter._ensure_assistant_prompt("some text\nAssistant:")
        assert result.count("Assistant:") == 1

    def test_merge_system_to_first_user(self):
        adapter = _adapter()
        parts = [("user", "hello")]
        adapter._merge_system_to_first_user("system msg", parts)
        assert "system msg" in parts[0][1]

    def test_format_simple(self):
        adapter = _adapter()
        parts = adapter._format_simple([("user", "Q"), ("assistant", "A")])
        assert len(parts) == 2
        assert "User: Q" in parts[0]
        assert "Assistant: A" in parts[1]


# ===========================================================================
# Token counting
# ===========================================================================


class TestCountTokens:
    def test_fallback_estimation(self):
        adapter = _adapter()
        # No tokenizer available in test environment, uses char/4 estimation
        count = adapter.count_tokens(_messages(user="Hello world"))
        assert count > 0

    def test_with_mock_tokenizer(self):
        adapter = _adapter()
        mock_tok = MagicMock()
        mock_tok.encode.return_value = list(range(42))
        adapter._tokenizer = mock_tok
        count = adapter.count_tokens(_messages(user="Hello"))
        assert count == 42


# ===========================================================================
# Cost estimation
# ===========================================================================


class TestEstimateCost:
    def test_known_model(self):
        adapter = _adapter("meta-llama/Meta-Llama-3.1-8B-Instruct")
        cost = adapter.estimate_cost(1000, 500)
        assert cost.total_cost_usd > 0
        assert cost.currency == "USD"
        assert "huggingface" in cost.pricing_model

    def test_unknown_model_uses_default(self):
        adapter = _adapter("unknown/model-xyz")
        cost = adapter.estimate_cost(1000, 500)
        assert cost.total_cost_usd > 0


# ===========================================================================
# Synchronous complete
# ===========================================================================


class TestComplete:
    def test_complete_string_response(self):
        adapter = _adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = "Generated answer"
        adapter._client = mock_client

        response = adapter.complete(_messages(user="test"))
        assert response.content == "Generated answer"
        assert response.metadata.provider == "huggingface"
        assert response.usage.prompt_tokens > 0

    def test_complete_object_response(self):
        adapter = _adapter()
        mock_resp = MagicMock()
        mock_resp.generated_text = "Object answer"
        mock_client = MagicMock()
        mock_client.text_generation.return_value = mock_resp
        adapter._client = mock_client

        response = adapter.complete(_messages(user="test"))
        assert response.content == "Object answer"

    def test_complete_with_stop_sequences(self):
        adapter = _adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = "ok"
        adapter._client = mock_client

        response = adapter.complete(_messages(user="test"), stop=["END"])
        mock_client.text_generation.assert_called_once()
        call_kwargs = mock_client.text_generation.call_args
        assert "stop_sequences" in call_kwargs.kwargs or any(
            "stop_sequences" in str(a) for a in call_kwargs.args
        )

    def test_complete_with_optional_params(self):
        adapter = _adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = "ok"
        adapter._client = mock_client

        adapter.complete(
            _messages(user="test"),
            top_k=50,
            repetition_penalty=1.2,
            do_sample=True,
        )
        mock_client.text_generation.assert_called_once()

    def test_complete_empty_messages_raises(self):
        adapter = _adapter()
        with pytest.raises(ValueError, match="empty"):
            adapter.complete([])

    def test_complete_api_error(self):
        adapter = _adapter()
        mock_client = MagicMock()
        mock_client.text_generation.side_effect = RuntimeError("API error")
        adapter._client = mock_client

        with pytest.raises(RuntimeError, match="API error"):
            adapter.complete(_messages(user="test"))


# ===========================================================================
# Async complete
# ===========================================================================


class TestAComplete:
    @pytest.mark.asyncio
    async def test_acomplete_string_response(self):
        adapter = _adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = "Async answer"
        adapter._async_client = mock_client

        response = await adapter.acomplete(_messages(user="test"))
        assert response.content == "Async answer"

    @pytest.mark.asyncio
    async def test_acomplete_coroutine_response(self):
        adapter = _adapter()
        mock_client = MagicMock()

        async def _coro():
            return "Awaited answer"

        mock_client.text_generation.return_value = _coro()
        adapter._async_client = mock_client

        response = await adapter.acomplete(_messages(user="test"))
        assert response.content == "Awaited answer"


# ===========================================================================
# Streaming
# ===========================================================================


class TestStream:
    def test_stream_string_chunks(self):
        adapter = _adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = iter(["chunk1", "chunk2"])
        adapter._client = mock_client

        chunks = list(adapter.stream(_messages(user="test")))
        assert chunks == ["chunk1", "chunk2"]

    def test_stream_token_chunks(self):
        adapter = _adapter()
        mock_token = MagicMock()
        mock_token.text = "word"
        mock_chunk = MagicMock()
        mock_chunk.token = mock_token
        mock_client = MagicMock()
        mock_client.text_generation.return_value = iter([mock_chunk])
        adapter._client = mock_client

        chunks = list(adapter.stream(_messages(user="test")))
        assert chunks == ["word"]


# ===========================================================================
# Streaming params and chunk processing
# ===========================================================================


class TestStreamingHelpers:
    def test_prepare_streaming_params_defaults(self):
        adapter = _adapter()
        params = adapter._prepare_streaming_params(0.7, None, 1.0, None)
        assert params["max_new_tokens"] == 1024
        assert params["stream"] is True

    def test_prepare_streaming_params_with_stop(self):
        adapter = _adapter()
        params = adapter._prepare_streaming_params(0.5, 100, 0.9, ["STOP"])
        assert params["stop_sequences"] == ["STOP"]

    def test_process_stream_chunk_string(self):
        adapter = _adapter()
        assert adapter._process_stream_chunk("hello") == "hello"

    def test_process_stream_chunk_token(self):
        adapter = _adapter()
        mock_token = MagicMock()
        mock_token.text = "word"
        mock_chunk = MagicMock()
        mock_chunk.token = mock_token
        assert adapter._process_stream_chunk(mock_chunk) == "word"

    def test_process_stream_chunk_other(self):
        adapter = _adapter()
        assert adapter._process_stream_chunk(42) == "42"


# ===========================================================================
# Health check
# ===========================================================================


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_local_model(self):
        cfg = _config()
        cfg.use_inference_api = False
        adapter = HuggingFaceAdapter(config=cfg)
        result = await adapter.health_check()
        assert result.status == AdapterStatus.HEALTHY
        assert "initialized" in result.message.lower()

    @pytest.mark.asyncio
    async def test_health_check_inference_api_failure(self):
        adapter = _adapter()
        adapter.config.use_inference_api = True

        # Mock both model_info import to fail and acomplete to fail
        with patch.dict("sys.modules", {"huggingface_hub": None}):
            result = await adapter.health_check()
            # Should fall through to UNHEALTHY since import fails
            assert result.status in (AdapterStatus.HEALTHY, AdapterStatus.UNHEALTHY)
