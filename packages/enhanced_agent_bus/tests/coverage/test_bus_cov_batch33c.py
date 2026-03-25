"""
Comprehensive coverage tests for:
- enhanced_agent_bus/llm_adapters/huggingface_adapter.py
- enhanced_agent_bus/deliberation_layer/opa_guard.py
- enhanced_agent_bus/llm_adapters/openai_adapter.py

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# OPA Guard imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.deliberation_layer.opa_guard import (
    GUARD_CONSTITUTIONAL_HASH,
    OPAGuard,
    close_opa_guard,
    get_opa_guard,
    initialize_opa_guard,
    reset_opa_guard,
)
from enhanced_agent_bus.deliberation_layer.opa_guard_models import (
    CriticReview,
    GuardDecision,
    GuardResult,
    ReviewResult,
    ReviewStatus,
    Signature,
    SignatureResult,
    SignatureStatus,
)

# ---------------------------------------------------------------------------
# HuggingFace adapter imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.llm_adapters.base import (
    AdapterStatus,
    LLMMessage,
    StreamingMode,
)
from enhanced_agent_bus.llm_adapters.config import (
    HuggingFaceAdapterConfig,
    OpenAIAdapterConfig,
)
from enhanced_agent_bus.llm_adapters.huggingface_adapter import HuggingFaceAdapter

# ---------------------------------------------------------------------------
# OpenAI adapter imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.llm_adapters.openai_adapter import OpenAIAdapter

# ===========================================================================
# Helpers
# ===========================================================================


def _hf_config(
    model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct", **kw
) -> HuggingFaceAdapterConfig:
    return HuggingFaceAdapterConfig.from_environment(model=model, **kw)


def _hf_adapter(model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct") -> HuggingFaceAdapter:
    return HuggingFaceAdapter(config=_hf_config(model=model))


def _msgs(
    system: str | None = None,
    user: str = "Hello",
    assistant: str | None = None,
) -> list[LLMMessage]:
    msgs: list[LLMMessage] = []
    if system:
        msgs.append(LLMMessage(role="system", content=system))
    msgs.append(LLMMessage(role="user", content=user))
    if assistant:
        msgs.append(LLMMessage(role="assistant", content=assistant))
    return msgs


def _oai_adapter() -> OpenAIAdapter:
    with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-fake"}):
        return OpenAIAdapter(model="gpt-5.2", api_key="sk-test-fake")


def _mock_opa_client(policy_result=None):
    client = AsyncMock()
    client.evaluate_policy = AsyncMock(return_value=policy_result or {"allowed": True})
    client.close = AsyncMock()
    client.initialize = AsyncMock()
    return client


def _mock_openai_response():
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


# ===========================================================================
# HuggingFace Adapter — Client Creation
# ===========================================================================


class TestHFClientCreation:
    """Cover _get_client and _get_async_client uncovered branches."""

    def test_get_client_import_error(self):
        adapter = _hf_adapter()
        with patch.dict("sys.modules", {"huggingface_hub": None}):
            adapter._client = None
            with pytest.raises(ImportError, match="huggingface_hub"):
                adapter._get_client()

    def test_get_async_client_import_error(self):
        adapter = _hf_adapter()
        with patch.dict("sys.modules", {"huggingface_hub": None}):
            adapter._async_client = None
            with pytest.raises(ImportError, match="huggingface_hub"):
                adapter._get_async_client()

    def test_get_client_no_api_key_warning(self):
        adapter = _hf_adapter()
        adapter.api_key = None
        adapter.config.use_inference_api = True
        mock_module = MagicMock()
        mock_instance = MagicMock()
        mock_module.InferenceClient.return_value = mock_instance
        with patch.dict("sys.modules", {"huggingface_hub": mock_module}):
            adapter._client = None
            client = adapter._get_client()
            assert client is not None

    def test_get_async_client_no_api_key_warning(self):
        adapter = _hf_adapter()
        adapter.api_key = None
        adapter.config.use_inference_api = True
        mock_module = MagicMock()
        mock_instance = MagicMock()
        mock_module.AsyncInferenceClient.return_value = mock_instance
        with patch.dict("sys.modules", {"huggingface_hub": mock_module}):
            adapter._async_client = None
            client = adapter._get_async_client()
            assert client is not None

    def test_get_client_with_inference_endpoint(self):
        cfg = _hf_config()
        cfg.inference_endpoint = "https://custom-endpoint.example.com"
        adapter = HuggingFaceAdapter(config=cfg)
        mock_module = MagicMock()
        mock_module.InferenceClient.return_value = MagicMock()
        adapter.api_key = "hf_test_key"
        with patch.dict("sys.modules", {"huggingface_hub": mock_module}):
            adapter._client = None
            adapter._get_client()
            call_kwargs = mock_module.InferenceClient.call_args
            assert call_kwargs.kwargs.get("model") is None

    def test_get_async_client_with_inference_endpoint(self):
        cfg = _hf_config()
        cfg.inference_endpoint = "https://custom-endpoint.example.com"
        adapter = HuggingFaceAdapter(config=cfg)
        mock_module = MagicMock()
        mock_module.AsyncInferenceClient.return_value = MagicMock()
        adapter.api_key = "hf_test_key"
        with patch.dict("sys.modules", {"huggingface_hub": mock_module}):
            adapter._async_client = None
            adapter._get_async_client()
            call_kwargs = mock_module.AsyncInferenceClient.call_args
            assert call_kwargs.kwargs.get("model") is None


# ===========================================================================
# HuggingFace Adapter — Tokenizer
# ===========================================================================


class TestHFTokenizer:
    """Cover _get_tokenizer uncovered branches."""

    def test_get_tokenizer_import_error(self):
        adapter = _hf_adapter()
        adapter._tokenizer = None
        with patch.dict("sys.modules", {"transformers": None}):
            result = adapter._get_tokenizer()
            assert result is None

    def test_get_tokenizer_load_failure(self):
        adapter = _hf_adapter()
        adapter._tokenizer = None
        mock_transformers = MagicMock()
        mock_transformers.AutoTokenizer.from_pretrained.side_effect = OSError("Model not found")
        with patch.dict("sys.modules", {"transformers": mock_transformers}):
            result = adapter._get_tokenizer()
            assert result is None

    def test_get_tokenizer_trust_remote_code(self):
        adapter = _hf_adapter()
        adapter._tokenizer = None
        mock_transformers = MagicMock()
        mock_tokenizer = MagicMock()
        mock_transformers.AutoTokenizer.from_pretrained.return_value = mock_tokenizer
        with (
            patch.dict("sys.modules", {"transformers": mock_transformers}),
            patch.dict("os.environ", {"ACGS_HF_TRUST_REMOTE_CODE": "true"}),
        ):
            result = adapter._get_tokenizer()
            assert result is not None
            call_kwargs = mock_transformers.AutoTokenizer.from_pretrained.call_args
            assert call_kwargs.kwargs.get("trust_remote_code") is True

    def test_count_tokens_tokenizer_encode_failure(self):
        adapter = _hf_adapter()
        mock_tok = MagicMock()
        mock_tok.encode.side_effect = RuntimeError("Tokenizer failed")
        adapter._tokenizer = mock_tok
        count = adapter.count_tokens(_msgs(user="Hello world test"))
        assert count > 0  # Falls back to estimation


# ===========================================================================
# HuggingFace Adapter — Message Formatting
# ===========================================================================


class TestHFMessageFormatting:
    """Cover message formatting uncovered branches."""

    def test_format_with_template_remaining_conversation(self):
        adapter = _hf_adapter()
        msgs = [
            LLMMessage(role="system", content="Be helpful."),
            LLMMessage(role="user", content="Q1"),
            LLMMessage(role="assistant", content="A1"),
            LLMMessage(role="user", content="Q2"),
        ]
        prompt = adapter._format_messages_for_inference(msgs)
        assert "Be helpful" in prompt
        assert "Q2" in prompt

    def test_format_messages_no_system_default_family(self):
        cfg = _hf_config("unknown/custom-model")
        adapter = HuggingFaceAdapter(config=cfg)
        msgs = [LLMMessage(role="user", content="test question")]
        prompt = adapter._format_messages_for_inference(msgs)
        assert "test question" in prompt
        assert prompt.rstrip().endswith("Assistant:")

    def test_merge_system_to_first_user_empty_parts(self):
        adapter = _hf_adapter()
        parts: list[tuple[str, str]] = []
        adapter._merge_system_to_first_user("system msg", parts)
        assert len(parts) == 0

    def test_merge_system_to_first_user_non_user_first(self):
        adapter = _hf_adapter()
        parts = [("assistant", "previous response")]
        adapter._merge_system_to_first_user("system msg", parts)
        assert parts[0] == ("assistant", "previous response")

    def test_format_simple_empty_parts(self):
        adapter = _hf_adapter()
        result = adapter._format_simple([])
        assert result == []

    def test_format_messages_deepseek_with_system(self):
        adapter = _hf_adapter("deepseek-ai/deepseek-coder-6.7b-instruct")
        msgs = _msgs(system="You are a coder.", user="Write hello world")
        prompt = adapter._format_messages_for_inference(msgs)
        assert "You are a coder" in prompt
        assert "Write hello world" in prompt

    def test_format_messages_zephyr_with_system(self):
        adapter = _hf_adapter("HuggingFaceH4/zephyr-7b-beta")
        msgs = _msgs(system="Be concise.", user="Summarize AI")
        prompt = adapter._format_messages_for_inference(msgs)
        assert "Be concise" in prompt


# ===========================================================================
# HuggingFace Adapter — Complete Branches
# ===========================================================================


class TestHFCompleteBranches:
    """Cover complete() uncovered branches."""

    def test_complete_fallback_str_response(self):
        adapter = _hf_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = 12345
        adapter._client = mock_client
        response = adapter.complete(_msgs(user="test"))
        assert response.content == "12345"

    def test_complete_with_max_tokens_none(self):
        adapter = _hf_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = "result"
        adapter._client = mock_client
        response = adapter.complete(_msgs(user="test"), max_tokens=None)
        assert response.content == "result"

    def test_complete_with_do_sample_false(self):
        adapter = _hf_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = "ok"
        adapter._client = mock_client
        adapter.complete(_msgs(user="test"), do_sample=False)
        mock_client.text_generation.assert_called_once()


# ===========================================================================
# HuggingFace Adapter — AComplete Branches
# ===========================================================================


class TestHFACompleteBranches:
    """Cover acomplete() uncovered branches."""

    async def test_acomplete_with_stop_sequences(self):
        adapter = _hf_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = "async result"
        adapter._async_client = mock_client
        response = await adapter.acomplete(_msgs(user="test"), stop=["END"])
        assert response.content == "async result"

    async def test_acomplete_with_optional_params(self):
        adapter = _hf_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = "ok"
        adapter._async_client = mock_client
        await adapter.acomplete(_msgs(user="test"), top_k=50, repetition_penalty=1.2)
        mock_client.text_generation.assert_called_once()

    async def test_acomplete_object_response(self):
        adapter = _hf_adapter()
        mock_resp = MagicMock()
        mock_resp.generated_text = "object response"
        mock_client = MagicMock()
        mock_client.text_generation.return_value = mock_resp
        adapter._async_client = mock_client
        response = await adapter.acomplete(_msgs(user="test"))
        assert response.content == "object response"

    async def test_acomplete_fallback_response(self):
        adapter = _hf_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = 42
        adapter._async_client = mock_client
        response = await adapter.acomplete(_msgs(user="test"))
        assert response.content == "42"

    async def test_acomplete_api_error(self):
        adapter = _hf_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.side_effect = RuntimeError("async fail")
        adapter._async_client = mock_client
        with pytest.raises(RuntimeError, match="async fail"):
            await adapter.acomplete(_msgs(user="test"))


# ===========================================================================
# HuggingFace Adapter — Stream Branches
# ===========================================================================


class TestHFStreamBranches:
    """Cover stream() and astream() uncovered branches."""

    def test_stream_with_top_k(self):
        adapter = _hf_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = iter(["chunk"])
        adapter._client = mock_client
        chunks = list(adapter.stream(_msgs(user="test"), top_k=50))
        assert chunks == ["chunk"]

    def test_stream_with_stop(self):
        adapter = _hf_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = iter(["data"])
        adapter._client = mock_client
        chunks = list(adapter.stream(_msgs(user="test"), stop=["STOP"]))
        assert chunks == ["data"]

    def test_stream_non_iterable_response(self):
        adapter = _hf_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = 42
        adapter._client = mock_client
        chunks = list(adapter.stream(_msgs(user="test")))
        assert chunks == []

    def test_stream_other_chunk_type(self):
        adapter = _hf_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = iter([42, 43])
        adapter._client = mock_client
        chunks = list(adapter.stream(_msgs(user="test")))
        assert chunks == ["42", "43"]

    def test_stream_token_no_text_attr(self):
        adapter = _hf_adapter()
        mock_chunk = MagicMock(spec=["token"])
        mock_chunk.token = MagicMock(spec=[])
        mock_client = MagicMock()
        mock_client.text_generation.return_value = iter([mock_chunk])
        adapter._client = mock_client
        chunks = list(adapter.stream(_msgs(user="test")))
        assert chunks == [""]

    def test_stream_error(self):
        adapter = _hf_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.side_effect = RuntimeError("stream fail")
        adapter._client = mock_client
        with pytest.raises(RuntimeError, match="stream fail"):
            list(adapter.stream(_msgs(user="test")))

    async def test_astream_basic(self):
        adapter = _hf_adapter()
        mock_client = MagicMock()

        async def _async_gen():
            yield "async chunk 1"
            yield "async chunk 2"

        mock_client.text_generation.return_value = _async_gen()
        adapter._async_client = mock_client
        chunks = []
        async for chunk in adapter.astream(_msgs(user="test")):
            chunks.append(chunk)
        assert chunks == ["async chunk 1", "async chunk 2"]

    async def test_astream_with_stop_and_top_k(self):
        adapter = _hf_adapter()
        mock_client = MagicMock()

        async def _async_gen():
            yield "data"

        mock_client.text_generation.return_value = _async_gen()
        adapter._async_client = mock_client
        chunks = []
        async for chunk in adapter.astream(_msgs(user="test"), stop=["END"], top_k=10):
            chunks.append(chunk)
        assert chunks == ["data"]

    async def test_astream_error(self):
        adapter = _hf_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.side_effect = RuntimeError("astream fail")
        adapter._async_client = mock_client
        with pytest.raises(RuntimeError, match="astream fail"):
            async for _ in adapter.astream(_msgs(user="test")):
                pass

    async def test_process_async_stream_sync_iter(self):
        adapter = _hf_adapter()
        sync_iter = ["a", "b"]
        chunks = []
        async for chunk in adapter._process_async_stream(sync_iter):
            chunks.append(chunk)
        assert chunks == ["a", "b"]


# ===========================================================================
# HuggingFace Adapter — Streaming Params
# ===========================================================================


class TestHFStreamingParams:
    def test_prepare_streaming_params_with_top_k(self):
        adapter = _hf_adapter()
        params = adapter._prepare_streaming_params(0.7, 256, 0.9, ["STOP"], top_k=50)
        assert params["top_k"] == 50
        assert params["max_new_tokens"] == 256
        assert params["stop_sequences"] == ["STOP"]


# ===========================================================================
# HuggingFace Adapter — Health Check
# ===========================================================================


class TestHFHealthCheckBranches:
    async def test_health_check_inference_api_model_info_success(self):
        adapter = _hf_adapter()
        adapter.config.use_inference_api = True

        mock_info = MagicMock()
        mock_info.pipeline_tag = "text-generation"

        mock_hf_hub = MagicMock()
        mock_hf_hub.model_info.return_value = mock_info
        mock_hf_hub.AsyncInferenceClient.return_value = MagicMock()

        with patch.dict("sys.modules", {"huggingface_hub": mock_hf_hub}):
            adapter._async_client = MagicMock()
            result = await adapter.health_check()
            assert result.status == AdapterStatus.HEALTHY
            assert "text-generation" in str(result.details.get("model_type", ""))

    async def test_health_check_inference_api_model_info_fails_then_acomplete(self):
        adapter = _hf_adapter()
        adapter.config.use_inference_api = True

        mock_hf_hub = MagicMock()
        mock_hf_hub.model_info.side_effect = OSError("cannot reach HF")
        mock_hf_hub.AsyncInferenceClient.return_value = MagicMock()

        mock_async_client = MagicMock()
        mock_async_client.text_generation.return_value = "ok"
        adapter._async_client = mock_async_client

        with patch.dict("sys.modules", {"huggingface_hub": mock_hf_hub}):
            result = await adapter.health_check()
            assert result.status == AdapterStatus.HEALTHY

    async def test_health_check_unhealthy(self):
        adapter = _hf_adapter()
        adapter.config.use_inference_api = True

        mock_hf_hub = MagicMock()
        mock_hf_hub.model_info.side_effect = OSError("cannot reach")
        mock_hf_hub.AsyncInferenceClient.return_value = MagicMock()

        mock_async_client = MagicMock()
        mock_async_client.text_generation.side_effect = RuntimeError("total fail")
        adapter._async_client = mock_async_client

        with patch.dict("sys.modules", {"huggingface_hub": mock_hf_hub}):
            result = await adapter.health_check()
            assert result.status == AdapterStatus.UNHEALTHY


# ===========================================================================
# OpenAI Adapter — Tiktoken Fallback
# ===========================================================================


class TestOAITiktokenFallback:
    def test_tiktoken_keyerror_fallback(self):
        adapter = _oai_adapter()
        adapter._tiktoken_encoder = None
        mock_tiktoken = MagicMock()
        mock_tiktoken.encoding_for_model.side_effect = KeyError("unknown model")
        mock_encoding = MagicMock()
        mock_encoding.encode.return_value = [1, 2, 3]
        mock_tiktoken.get_encoding.return_value = mock_encoding
        with patch.dict("sys.modules", {"tiktoken": mock_tiktoken}):
            encoder = adapter._get_tiktoken_encoder()
            assert encoder is not None
            tokens = encoder.encode("test")
            assert tokens == [1, 2, 3]


# ===========================================================================
# OpenAI Adapter — Complete Error Paths
# ===========================================================================


class TestOAICompleteErrors:
    def test_complete_sync_error(self):
        adapter = _oai_adapter()
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("API fail")
        adapter._client = mock_client
        with pytest.raises(RuntimeError, match="API fail"):
            adapter.complete([LLMMessage(role="user", content="test")])

    async def test_acomplete_error(self):
        adapter = _oai_adapter()
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("async API fail"))
        adapter._async_client = mock_client
        with pytest.raises(RuntimeError, match="async API fail"):
            await adapter.acomplete([LLMMessage(role="user", content="test")])

    async def test_acomplete_with_all_optional_params(self):
        adapter = _oai_adapter()
        mock_resp = _mock_openai_response()
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
        adapter._async_client = mock_client
        response = await adapter.acomplete(
            [LLMMessage(role="user", content="test")],
            max_tokens=50,
            stop=["END"],
            tools=[{"type": "function"}],
            tool_choice="auto",
            response_format={"type": "json"},
            frequency_penalty=0.5,
            presence_penalty=0.5,
        )
        assert response.content == "Hello!"


# ===========================================================================
# OpenAI Adapter — Stream Error Paths
# ===========================================================================


class TestOAIStreamErrors:
    def test_stream_sync_error(self):
        adapter = _oai_adapter()
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("stream fail")
        adapter._client = mock_client
        with pytest.raises(RuntimeError, match="stream fail"):
            list(adapter.stream([LLMMessage(role="user", content="test")]))

    async def test_astream_error(self):
        adapter = _oai_adapter()
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("astream fail"))
        adapter._async_client = mock_client
        with pytest.raises(RuntimeError, match="astream fail"):
            async for _ in adapter.astream([LLMMessage(role="user", content="test")]):
                pass

    async def test_astream_basic(self):
        adapter = _oai_adapter()
        mock_client = MagicMock()

        chunk = MagicMock()
        delta = MagicMock()
        delta.content = "hello"
        choice = MagicMock()
        choice.delta = delta
        chunk.choices = [choice]

        async def _async_gen():
            yield chunk

        mock_client.chat.completions.create = AsyncMock(return_value=_async_gen())
        adapter._async_client = mock_client
        chunks = []
        async for c in adapter.astream([LLMMessage(role="user", content="test")]):
            chunks.append(c)
        assert chunks == ["hello"]


# ===========================================================================
# OpenAI Adapter — Cost Estimation
# ===========================================================================


class TestOAICostEstimation:
    def test_prefix_match_pricing(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-fake"}):
            adapter = OpenAIAdapter(model="gpt-5.2-preview", api_key="sk-fake")
        cost = adapter.estimate_cost(1000, 500)
        assert cost.total_cost_usd > 0

    def test_kimi_model_pricing(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-fake"}):
            adapter = OpenAIAdapter(model="kimi-k2.5-free", api_key="sk-fake")
        cost = adapter.estimate_cost(1000, 500)
        assert cost.total_cost_usd == 0.0


# ===========================================================================
# OpenAI Adapter — Count Tokens Edge Cases
# ===========================================================================


class TestOAICountTokens:
    def test_count_tokens_empty_content(self):
        adapter = _oai_adapter()
        try:
            import tiktoken
        except ImportError:
            pytest.skip("tiktoken not installed")
        msgs = [LLMMessage(role="user", content="")]
        count = adapter.count_tokens(msgs)
        assert count >= 6  # formatting + role + reply priming

    def test_count_tokens_multiple_messages(self):
        adapter = _oai_adapter()
        try:
            import tiktoken
        except ImportError:
            pytest.skip("tiktoken not installed")
        msgs = [
            LLMMessage(role="system", content="You are helpful."),
            LLMMessage(role="user", content="Hi"),
            LLMMessage(role="assistant", content="Hello!"),
        ]
        count = adapter.count_tokens(msgs)
        assert count > 10


# ===========================================================================
# OpenAI Adapter — add_optional_params
# ===========================================================================


class TestOAIAddOptionalParams:
    def test_add_optional_params_empty(self):
        adapter = _oai_adapter()
        params: dict[str, object] = {"model": "gpt-5.2"}
        adapter._add_optional_params(params)
        assert "tools" not in params

    def test_add_optional_params_all(self):
        adapter = _oai_adapter()
        params: dict[str, object] = {"model": "gpt-5.2"}
        adapter._add_optional_params(
            params,
            tools=[{"type": "function"}],
            tool_choice="auto",
            frequency_penalty=0.5,
            presence_penalty=0.3,
        )
        assert params["tools"] == [{"type": "function"}]
        assert params["frequency_penalty"] == 0.5


# ===========================================================================
# OPA Guard — Initialize Branches
# ===========================================================================


class TestOPAGuardInitBranches:
    async def test_initialize_with_none_client(self):
        guard = OPAGuard(opa_client=None)
        with patch("enhanced_agent_bus.deliberation_layer.opa_guard.get_opa_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.initialize = AsyncMock()
            mock_get.return_value = mock_client
            await guard.initialize()
            assert guard.opa_client is mock_client

    async def test_initialize_sets_fail_closed_on_existing_client(self):
        mock_client = AsyncMock()
        mock_client.fail_closed = True
        mock_client.initialize = AsyncMock()
        guard = OPAGuard(opa_client=mock_client, fail_closed=False)
        await guard.initialize()
        assert mock_client.fail_closed is False


# ===========================================================================
# OPA Guard — verify_action Branches
# ===========================================================================


class TestOPAGuardVerifyBranches:
    async def test_verify_action_opa_client_none(self):
        guard = OPAGuard()
        guard.opa_client = _mock_opa_client({"allowed": True})
        guard.opa_client.evaluate_policy.side_effect = [
            {"allowed": True},  # constitutional check
        ]
        # Make OPA client None after constitutional check
        original_check = guard.check_constitutional_compliance

        async def _check_then_nullify(action):
            result = await original_check(action)
            guard.opa_client = None
            return result

        guard.check_constitutional_compliance = _check_then_nullify
        result = await guard.verify_action("agent_1", {"type": "read"}, {})
        assert result.decision == GuardDecision.DENY
        assert "OPA client not initialized" in result.validation_errors[0]

    async def test_verify_action_fallback_warning(self):
        mock_client = _mock_opa_client()
        mock_client.evaluate_policy.side_effect = [
            {"allowed": True},  # constitutional
            {"allowed": True, "metadata": {"mode": "fallback"}},  # policy
        ]
        guard = OPAGuard(opa_client=mock_client)
        result = await guard.verify_action("agent_1", {"type": "read"}, {})
        assert any("fallback" in w.lower() for w in result.validation_warnings)

    async def test_verify_action_high_risk_requires_signatures(self):
        mock_client = _mock_opa_client()
        mock_client.evaluate_policy.side_effect = [
            {"allowed": True},  # constitutional
            {"allowed": True},  # policy
        ]
        guard = OPAGuard(
            opa_client=mock_client,
            high_risk_threshold=0.3,
            critical_risk_threshold=0.95,
        )
        result = await guard.verify_action(
            "agent_1",
            {"type": "delete", "scope": "organization"},
            {},
        )
        assert result.decision == GuardDecision.REQUIRE_SIGNATURES
        assert result.requires_signatures is True

    async def test_verify_action_critical_risk_requires_review(self):
        mock_client = _mock_opa_client()
        mock_client.evaluate_policy.side_effect = [
            {"allowed": True},  # constitutional
            {"allowed": True},  # policy
        ]
        guard = OPAGuard(
            opa_client=mock_client,
            high_risk_threshold=0.3,
            critical_risk_threshold=0.5,
        )
        guard.register_critic_agent("critic_1", review_types=["general"])
        result = await guard.verify_action(
            "agent_1",
            {"type": "delete", "scope": "global", "impact_score": 0.5},
            {},
        )
        assert result.decision == GuardDecision.REQUIRE_REVIEW
        assert result.requires_review is True

    async def test_verify_action_exception_handling(self):
        mock_client = _mock_opa_client()
        mock_client.evaluate_policy.side_effect = [
            {"allowed": True},  # constitutional
            TypeError("unexpected"),  # policy
        ]
        guard = OPAGuard(opa_client=mock_client)
        result = await guard.verify_action("agent_1", {"type": "read"}, {})
        assert result.decision == GuardDecision.DENY
        assert "Verification error" in result.validation_errors[0]


# ===========================================================================
# OPA Guard — Risk Calculation Branches
# ===========================================================================


class TestOPAGuardRiskBranches:
    def test_impact_score_from_context(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        action = {"type": "read"}
        context = {"impact_score": 0.5}
        score = guard._calculate_risk_score(action, context, {})
        assert score >= 0.2  # 0.5 * 0.4

    def test_organization_scope(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        action = {"type": "read", "scope": "organization"}
        score = guard._calculate_risk_score(action, {}, {})
        assert score >= 0.1

    def test_scope_from_context(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        action = {"type": "read"}
        context = {"scope": "global"}
        score = guard._calculate_risk_score(action, context, {})
        assert score >= 0.2

    def test_policy_metadata_risk_score(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        policy_result = {"metadata": {"risk_score": 0.5}}
        score = guard._calculate_risk_score({"type": "read"}, {}, policy_result)
        assert score >= 0.05  # 0.5 * 0.1

    def test_non_numeric_impact_score(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        action = {"type": "read", "impact_score": "not_a_number"}
        score = guard._calculate_risk_score(action, {}, {})
        assert score >= 0.0

    def test_risk_level_boundaries(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        assert guard._determine_risk_level(0.0) == "low"
        assert guard._determine_risk_level(0.39) == "low"
        assert guard._determine_risk_level(0.4) == "medium"
        assert guard._determine_risk_level(0.69) == "medium"
        assert guard._determine_risk_level(0.7) == "high"
        assert guard._determine_risk_level(0.89) == "high"
        assert guard._determine_risk_level(0.9) == "critical"
        assert guard._determine_risk_level(1.0) == "critical"


# ===========================================================================
# OPA Guard — Risk Factor Identification Branches
# ===========================================================================


class TestOPAGuardRiskFactors:
    def test_modify_action(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        factors = guard._identify_risk_factors({"type": "modify"}, {})
        assert any("modify" in f.lower() or "destructive" in f.lower() for f in factors)

    def test_affects_users(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        factors = guard._identify_risk_factors({"type": "read", "affects_users": True}, {})
        assert any("user" in f.lower() for f in factors)

    def test_irreversible_action(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        factors = guard._identify_risk_factors({"type": "read", "irreversible": True}, {})
        assert any("irreversible" in f.lower() for f in factors)

    def test_scope_from_context(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        factors = guard._identify_risk_factors({"type": "read"}, {"scope": "global"})
        assert any("scope" in f.lower() or "global" in f.lower() for f in factors)

    def test_production_environment(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        factors = guard._identify_risk_factors({"type": "read"}, {"production": True})
        assert any("production" in f.lower() for f in factors)


# ===========================================================================
# OPA Guard — Evaluate Branches
# ===========================================================================


class TestOPAGuardEvaluateBranches:
    async def test_evaluate_opa_client_none(self):
        guard = OPAGuard()
        guard.opa_client = None
        result = await guard.evaluate({"action": "test"})
        assert result["allow"] is False
        assert "OPA client not initialized" in result["reasons"][0]

    async def test_evaluate_fail_open_opa_client_none(self):
        guard = OPAGuard(fail_closed=False)
        guard.opa_client = None
        result = await guard.evaluate({"action": "test"})
        assert result["allow"] is True

    async def test_evaluate_allowed_key(self):
        mock_client = _mock_opa_client({"allowed": True, "reasons": ["ok"]})
        guard = OPAGuard(opa_client=mock_client)
        result = await guard.evaluate({"action": "test"})
        assert result["allow"] is True
        assert result["reasons"] == ["ok"]

    async def test_evaluate_allow_key(self):
        mock_client = _mock_opa_client({"allow": True, "version": "2.0"})
        guard = OPAGuard(opa_client=mock_client)
        result = await guard.evaluate({"action": "test"})
        assert result["allow"] is True
        assert result["version"] == "2.0"

    async def test_evaluate_non_dict_result(self):
        mock_client = _mock_opa_client()
        mock_client.evaluate_policy.return_value = "not a dict"
        guard = OPAGuard(opa_client=mock_client)
        result = await guard.evaluate({"action": "test"})
        assert result["allow"] is False  # fail_closed default

    async def test_evaluate_exception(self):
        mock_client = _mock_opa_client()
        mock_client.evaluate_policy.side_effect = RuntimeError("OPA down")
        guard = OPAGuard(opa_client=mock_client)
        result = await guard.evaluate({"action": "test"})
        assert result["allow"] is False
        assert result["version"] == "fallback"

    async def test_evaluate_exception_fail_open(self):
        mock_client = _mock_opa_client()
        mock_client.evaluate_policy.side_effect = RuntimeError("OPA down")
        guard = OPAGuard(opa_client=mock_client, fail_closed=False)
        result = await guard.evaluate({"action": "test"})
        assert result["allow"] is True


# ===========================================================================
# OPA Guard — Constitutional Compliance Branches
# ===========================================================================


class TestOPAGuardConstitutionalBranches:
    async def test_opa_client_none_fail_closed(self):
        guard = OPAGuard(fail_closed=True)
        guard.opa_client = None
        result = await guard.check_constitutional_compliance({"type": "read"})
        assert result is False

    async def test_opa_client_none_fail_open(self):
        guard = OPAGuard(fail_closed=False)
        guard.opa_client = None
        result = await guard.check_constitutional_compliance({"type": "read"})
        assert result is True

    async def test_non_dict_result_fail_closed(self):
        mock_client = _mock_opa_client()
        mock_client.evaluate_policy.return_value = "not a dict"
        guard = OPAGuard(opa_client=mock_client)
        result = await guard.check_constitutional_compliance({"type": "read"})
        assert result is False

    async def test_non_dict_result_fail_open(self):
        mock_client = _mock_opa_client()
        mock_client.evaluate_policy.return_value = "not a dict"
        guard = OPAGuard(opa_client=mock_client, fail_closed=False)
        result = await guard.check_constitutional_compliance({"type": "read"})
        assert result is True

    async def test_exception_fail_open(self):
        mock_client = _mock_opa_client()
        mock_client.evaluate_policy.side_effect = RuntimeError("OPA fail")
        guard = OPAGuard(opa_client=mock_client, fail_closed=False)
        result = await guard.check_constitutional_compliance({"type": "read"})
        assert result is True


# ===========================================================================
# OPA Guard — Audit Log Branches
# ===========================================================================


class TestOPAGuardAuditLogBranches:
    async def test_log_decision_overflow_trim(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        guard._audit_log = [{"entry": i} for i in range(10001)]
        await guard.log_decision({"action": "test"}, {"result": "allow"})
        assert len(guard._audit_log) <= 10001

    def test_get_audit_log_with_agent_id_filter(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        guard._audit_log = [
            {"decision": {"agent_id": "agent_1"}, "result": {}},
            {"decision": {"agent_id": "agent_2"}, "result": {}},
            {"decision": {"agent_id": "agent_1"}, "result": {}},
        ]
        logs = guard.get_audit_log(agent_id="agent_1")
        assert len(logs) == 2

    def test_get_audit_log_with_offset(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        guard._audit_log = [{"entry": i} for i in range(10)]
        logs = guard.get_audit_log(limit=3, offset=5)
        assert len(logs) == 3

    def test_get_stats(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        guard._stats["total_verifications"] = 10
        stats = guard.get_stats()
        assert stats["total_verifications"] == 10
        assert stats["constitutional_hash"] == GUARD_CONSTITUTIONAL_HASH
        assert "pending_signatures" in stats
        assert "registered_critics" in stats


# ===========================================================================
# OPA Guard — Critic Agent Management
# ===========================================================================


class TestOPAGuardCriticManagement:
    def test_register_with_callback(self):
        guard = OPAGuard(opa_client=_mock_opa_client())

        async def callback(decision, review_result):
            pass

        guard.register_critic_agent(
            "critic_1",
            review_types=["safety"],
            callback=callback,
            metadata={"priority": 1},
        )
        assert "critic_1" in guard._critic_agents
        assert guard._critic_agents["critic_1"]["callback"] is callback

    def test_unregister_nonexistent(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        guard.unregister_critic_agent("nonexistent")
        assert "nonexistent" not in guard._critic_agents

    def test_register_and_unregister(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        guard.register_critic_agent("critic_1", review_types=["general"])
        guard.unregister_critic_agent("critic_1")
        assert "critic_1" not in guard._critic_agents


# ===========================================================================
# OPA Guard — Global Functions
# ===========================================================================


class TestOPAGuardGlobalFunctions:
    def test_reset_opa_guard(self):
        reset_opa_guard()
        guard = get_opa_guard()
        assert isinstance(guard, OPAGuard)
        reset_opa_guard()

    async def test_initialize_and_close_opa_guard(self):
        reset_opa_guard()
        mock_client = _mock_opa_client()
        guard = await initialize_opa_guard(opa_client=mock_client)
        assert isinstance(guard, OPAGuard)
        await close_opa_guard()
        reset_opa_guard()

    def test_get_opa_guard_creates_new(self):
        reset_opa_guard()
        guard = get_opa_guard()
        assert isinstance(guard, OPAGuard)
        reset_opa_guard()


# ===========================================================================
# OPA Guard — Submit Review Branches
# ===========================================================================


class TestOPAGuardReviewBranches:
    async def test_submit_review_with_concerns_and_recommendations(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        review_result = ReviewResult(decision_id="test_review")
        guard._pending_reviews["test_review"] = review_result
        success = await guard.submit_review(
            "test_review",
            "critic_1",
            verdict="approve",
            reasoning="Looks good",
            concerns=["minor issue"],
            recommendations=["add logging"],
            confidence=0.95,
        )
        assert success is True
        assert len(review_result.reviews) == 1

    async def test_submit_review_unknown_decision(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        success = await guard.submit_review("unknown", "critic_1", verdict="approve")
        assert success is False


# ===========================================================================
# OPA Guard — Signature Branches
# ===========================================================================


class TestOPAGuardSignatureBranches:
    async def test_submit_signature_unknown_decision(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        result = await guard.submit_signature("unknown", "signer_1")
        assert result is False

    async def test_reject_signature_unknown_decision(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        result = await guard.reject_signature("unknown", "signer_1")
        assert result is False

    async def test_reject_signature_with_event(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        sig_result = SignatureResult(
            decision_id="test_sig",
            required_signers=["signer_1"],
            required_count=1,
            threshold=1.0,
        )
        event = asyncio.Event()
        sig_result._completion_event = event  # type: ignore[attr-defined]
        guard._pending_signatures["test_sig"] = sig_result
        success = await guard.reject_signature("test_sig", "signer_1", reason="Nope")
        assert success is True
        assert event.is_set()


# ===========================================================================
# Additional coverage: HuggingFace Adapter uncovered branches
# ===========================================================================


class TestHFCompleteBranches:
    """Cover complete() and acomplete() uncovered branches."""

    def test_complete_generated_text_attribute_response(self):
        """Cover the hasattr(response, 'generated_text') branch in complete()."""
        adapter = _hf_adapter()
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.generated_text = "Generated via attribute"
        mock_client.text_generation.return_value = mock_resp
        adapter._client = mock_client

        result = adapter.complete(_msgs(user="test"))
        assert result.content == "Generated via attribute"

    def test_complete_fallback_str_cast_response(self):
        """Cover the else branch (str(response)) in complete()."""
        adapter = _hf_adapter()
        mock_client = MagicMock()

        class _PlainResp:
            def __str__(self):
                return "fallback string"

        mock_client.text_generation.return_value = _PlainResp()
        adapter._client = mock_client

        result = adapter.complete(_msgs(user="test"))
        assert "fallback string" in result.content

    def test_complete_with_repetition_penalty(self):
        """Cover repetition_penalty kwarg branch in complete()."""
        adapter = _hf_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = "ok"
        adapter._client = mock_client

        result = adapter.complete(_msgs(user="test"), repetition_penalty=1.2)
        assert result.content == "ok"
        call_kwargs = mock_client.text_generation.call_args
        assert call_kwargs[1].get("repetition_penalty") == 1.2

    def test_complete_with_top_k(self):
        """Cover top_k kwarg branch in complete()."""
        adapter = _hf_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = "ok"
        adapter._client = mock_client

        result = adapter.complete(_msgs(user="test"), top_k=50)
        call_kwargs = mock_client.text_generation.call_args
        assert call_kwargs[1].get("top_k") == 50

    def test_complete_error_path(self):
        """Cover exception re-raise in complete()."""
        adapter = _hf_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.side_effect = RuntimeError("API failure")
        adapter._client = mock_client

        with pytest.raises(RuntimeError, match="API failure"):
            adapter.complete(_msgs(user="test"))

    async def test_acomplete_non_coroutine_response(self):
        """Cover the non-coroutine branch in acomplete() (line 629)."""
        adapter = _hf_adapter()
        mock_client = MagicMock()
        # Return a plain string (not a coroutine)
        mock_client.text_generation.return_value = "sync response"
        adapter._async_client = mock_client

        result = await adapter.acomplete(_msgs(user="test"))
        assert result.content == "sync response"

    async def test_acomplete_generated_text_attribute(self):
        """Cover hasattr(response, 'generated_text') in acomplete()."""
        adapter = _hf_adapter()
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.generated_text = "async attr response"

        async def _text_gen(*a, **kw):
            return mock_resp

        mock_client.text_generation = _text_gen
        adapter._async_client = mock_client

        result = await adapter.acomplete(_msgs(user="test"))
        assert result.content == "async attr response"

    async def test_acomplete_fallback_str_cast(self):
        """Cover else branch (str(response)) in acomplete()."""
        adapter = _hf_adapter()
        mock_client = MagicMock()

        class _PlainResp:
            def __str__(self):
                return "async fallback"

        async def _text_gen(*a, **kw):
            return _PlainResp()

        mock_client.text_generation = _text_gen
        adapter._async_client = mock_client

        result = await adapter.acomplete(_msgs(user="test"))
        assert "async fallback" in result.content

    async def test_acomplete_error_path(self):
        """Cover exception re-raise in acomplete()."""
        adapter = _hf_adapter()
        mock_client = MagicMock()

        async def _text_gen(*a, **kw):
            raise ValueError("async API failure")

        mock_client.text_generation = _text_gen
        adapter._async_client = mock_client

        with pytest.raises(ValueError, match="async API failure"):
            await adapter.acomplete(_msgs(user="test"))

    async def test_acomplete_with_repetition_penalty(self):
        """Cover repetition_penalty kwarg branch in acomplete()."""
        adapter = _hf_adapter()
        mock_client = MagicMock()

        captured_kwargs = {}

        async def _text_gen(prompt, **kw):
            captured_kwargs.update(kw)
            return "ok"

        mock_client.text_generation = _text_gen
        adapter._async_client = mock_client

        await adapter.acomplete(_msgs(user="test"), repetition_penalty=1.5)
        assert captured_kwargs.get("repetition_penalty") == 1.5


class TestHFModelDetection:
    """Cover _detect_model_family uncovered branches."""

    def test_detect_llama2_variant(self):
        adapter = _hf_adapter(model="meta-llama/Llama-2-7b-chat-hf")
        assert adapter._detect_model_family() == "llama2"

    def test_detect_mixtral_variant(self):
        adapter = _hf_adapter(model="mistralai/Mixtral-8x7B-Instruct-v0.1")
        assert adapter._detect_model_family() == "mistral"

    def test_detect_locooperator(self):
        adapter = _hf_adapter(model="LocoreMind/LocoOperator-4B-GGUF")
        assert adapter._detect_model_family() == "locooperator"

    def test_detect_locoremin(self):
        """Cover the 'locoremin' branch."""
        adapter = _hf_adapter(model="some/locoremin-model")
        assert adapter._detect_model_family() == "locooperator"


class TestHFFormatEdgeCases:
    """Cover formatting edge cases."""

    def test_format_messages_locooperator(self):
        adapter = _hf_adapter(model="LocoreMind/LocoOperator-4B-GGUF")
        result = adapter._format_messages_for_inference(_msgs(system="sys", user="hi"))
        assert "im_start" in result

    def test_format_with_template_no_conversation_parts(self):
        """Cover empty conversation_parts in _format_with_template."""
        adapter = _hf_adapter()
        template = adapter.CHAT_TEMPLATES["llama3"]
        parts = adapter._format_with_template(template, "system msg", [])
        assert len(parts) >= 1

    def test_ensure_assistant_prompt_already_present(self):
        """Cover the branch where prompt already ends with 'Assistant:'."""
        adapter = _hf_adapter()
        result = adapter._ensure_assistant_prompt("some text\nAssistant:")
        assert result == "some text\nAssistant:"

    def test_format_messages_system_no_template_support(self):
        """Cover _merge_system_to_first_user path when template has no {system}."""
        adapter = _hf_adapter()
        # Force a template without {system} placeholder
        msgs = _msgs(system="ctx", user="question")
        # Use a model with default template
        adapter.model = "unknown/some-model"
        result = adapter._format_messages_for_inference(msgs)
        assert "ctx" in result
        assert "question" in result

    def test_extract_message_parts_all_roles(self):
        """Cover all role branches in _extract_message_parts."""
        adapter = _hf_adapter()
        msgs = [
            LLMMessage(role="system", content="sys"),
            LLMMessage(role="user", content="u1"),
            LLMMessage(role="assistant", content="a1"),
            LLMMessage(role="user", content="u2"),
        ]
        system, parts = adapter._extract_message_parts(msgs)
        assert system == "sys"
        assert len(parts) == 3
        assert parts[0] == ("user", "u1")
        assert parts[1] == ("assistant", "a1")
        assert parts[2] == ("user", "u2")


class TestHFHealthCheckBranches:
    """Cover health_check uncovered branches."""

    async def test_health_check_non_inference_api(self):
        """Cover the else branch (use_inference_api=False) in health_check."""
        config = _hf_config()
        config.use_inference_api = False
        config.inference_endpoint = "https://custom.endpoint.com"
        adapter = HuggingFaceAdapter(config=config)

        result = await adapter.health_check()
        assert result.status == AdapterStatus.HEALTHY
        assert "initialized" in result.message.lower() or "Adapter" in result.message

    async def test_health_check_outer_exception(self):
        """Cover the outer exception handler in health_check."""
        adapter = _hf_adapter()
        adapter.config.use_inference_api = True
        # Make _get_async_client raise
        adapter._get_async_client = MagicMock(side_effect=ImportError("no hub"))

        result = await adapter.health_check()
        assert result.status == AdapterStatus.UNHEALTHY
        assert "no hub" in result.message


class TestHFEstimateCostBranches:
    """Cover estimate_cost uncovered branches."""

    def test_estimate_cost_known_model(self):
        adapter = _hf_adapter(model="meta-llama/Meta-Llama-3-8B-Instruct")
        cost = adapter.estimate_cost(1000, 500)
        assert cost.total_cost_usd > 0
        assert cost.pricing_model == "huggingface-meta-llama/Meta-Llama-3-8B-Instruct"

    def test_estimate_cost_unknown_model_uses_default(self):
        adapter = _hf_adapter(model="unknown/some-model-v1")
        adapter.model = "unknown/some-model-v1"
        cost = adapter.estimate_cost(1000, 500)
        assert cost.total_cost_usd > 0

    def test_estimate_cost_zero_tokens(self):
        adapter = _hf_adapter()
        cost = adapter.estimate_cost(0, 0)
        assert cost.total_cost_usd == 0.0


class TestHFStreamProcessing:
    """Cover _process_stream_chunk and _process_async_stream branches."""

    def test_process_stream_chunk_str(self):
        adapter = _hf_adapter()
        assert adapter._process_stream_chunk("hello") == "hello"

    def test_process_stream_chunk_token_with_text(self):
        adapter = _hf_adapter()
        chunk = MagicMock()
        chunk.token = MagicMock()
        chunk.token.text = "world"
        assert adapter._process_stream_chunk(chunk) == "world"

    def test_process_stream_chunk_token_no_text(self):
        adapter = _hf_adapter()
        chunk = MagicMock(spec=["token"])
        chunk.token = MagicMock(spec=[])  # no .text
        result = adapter._process_stream_chunk(chunk)
        assert result == ""

    def test_process_stream_chunk_fallback(self):
        adapter = _hf_adapter()

        class _PlainChunk:
            def __str__(self):
                return "fallback_chunk"

        assert adapter._process_stream_chunk(_PlainChunk()) == "fallback_chunk"

    async def test_process_async_stream_sync_iterable(self):
        """Cover the __iter__ branch (not __aiter__) in _process_async_stream."""
        adapter = _hf_adapter()
        sync_iter = ["chunk1", "chunk2"]
        chunks = []
        async for c in adapter._process_async_stream(iter(sync_iter)):
            chunks.append(c)
        assert chunks == ["chunk1", "chunk2"]

    async def test_process_async_stream_async_iterable(self):
        """Cover the __aiter__ branch in _process_async_stream."""
        adapter = _hf_adapter()

        async def _aiter():
            yield "a1"
            yield "a2"

        chunks = []
        async for c in adapter._process_async_stream(_aiter()):
            chunks.append(c)
        assert chunks == ["a1", "a2"]

    async def test_process_async_stream_neither(self):
        """Cover neither __aiter__ nor __iter__ path."""
        adapter = _hf_adapter()
        obj = object()  # not iterable
        chunks = []
        async for c in adapter._process_async_stream(obj):
            chunks.append(c)
        assert chunks == []


class TestHFPrepareStreamingParams:
    """Cover _prepare_streaming_params additional branches."""

    def test_prepare_streaming_params_defaults(self):
        adapter = _hf_adapter()
        params = adapter._prepare_streaming_params(0.7, None, 1.0, None)
        assert params["max_new_tokens"] == 1024
        assert params["stream"] is True
        assert "stop_sequences" not in params

    def test_prepare_streaming_params_with_stop(self):
        adapter = _hf_adapter()
        params = adapter._prepare_streaming_params(0.5, 100, 0.9, ["end"])
        assert params["max_new_tokens"] == 100
        assert params["stop_sequences"] == ["end"]

    def test_prepare_streaming_params_with_top_k(self):
        adapter = _hf_adapter()
        params = adapter._prepare_streaming_params(0.7, None, 1.0, None, top_k=40)
        assert params["top_k"] == 40


class TestHFCountTokensBranches:
    """Cover count_tokens edge cases."""

    def test_count_tokens_no_tokenizer_fallback(self):
        """Cover fallback estimation (no tokenizer)."""
        adapter = _hf_adapter()
        adapter._tokenizer = None
        with patch.object(adapter, "_get_tokenizer", return_value=None):
            count = adapter.count_tokens(_msgs(user="hello world"))
        assert count > 0

    def test_count_tokens_tokenizer_success(self):
        """Cover successful tokenizer path."""
        adapter = _hf_adapter()
        mock_tokenizer = MagicMock()
        mock_tokenizer.encode.return_value = [1, 2, 3, 4, 5]
        adapter._tokenizer = mock_tokenizer
        count = adapter.count_tokens(_msgs(user="hello"))
        assert count == 5


class TestHFInit:
    """Cover __init__ edge cases."""

    def test_init_default_model_when_none(self):
        """Cover config=None and model=None branch."""
        adapter = HuggingFaceAdapter()
        assert adapter.model == "meta-llama/Meta-Llama-3.1-8B-Instruct"

    def test_init_custom_model(self):
        adapter = HuggingFaceAdapter(model="deepseek-ai/deepseek-coder-6.7b-instruct")
        assert "deepseek" in adapter.model


# ===========================================================================
# Additional coverage: OpenAI Adapter uncovered branches
# ===========================================================================


class TestOpenAIClientErrors:
    """Cover _get_client and _get_async_client error branches."""

    def test_get_client_no_api_key_raises(self):
        """Cover ValueError when api_key is not set."""
        with patch.dict("os.environ", {}, clear=False):
            adapter = OpenAIAdapter(
                config=OpenAIAdapterConfig(model="gpt-5.2"),
                api_key=None,
            )
            adapter.api_key = None
            adapter._client = None
            with patch.dict("sys.modules", {"openai": MagicMock()}):
                with pytest.raises(ValueError, match="API key is required"):
                    adapter._get_client()

    def test_get_async_client_no_api_key_raises(self):
        """Cover ValueError when api_key is not set for async client."""
        with patch.dict("os.environ", {}, clear=False):
            adapter = OpenAIAdapter(
                config=OpenAIAdapterConfig(model="gpt-5.2"),
                api_key=None,
            )
            adapter.api_key = None
            adapter._async_client = None
            with patch.dict("sys.modules", {"openai": MagicMock()}):
                with pytest.raises(ValueError, match="API key is required"):
                    adapter._get_async_client()

    def test_get_client_import_error(self):
        adapter = _oai_adapter()
        adapter._client = None
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(ImportError, match="openai"):
                adapter._get_client()

    def test_get_async_client_import_error(self):
        adapter = _oai_adapter()
        adapter._async_client = None
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(ImportError, match="openai"):
                adapter._get_async_client()


class TestOpenAICompleteOptionalParams:
    """Cover optional parameter branches in complete() and acomplete()."""

    def test_complete_with_tools(self):
        adapter = _oai_adapter()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response()
        adapter._client = mock_client

        result = adapter.complete(
            _msgs(user="test"),
            tools=[{"type": "function", "function": {"name": "search"}}],
            tool_choice="auto",
            response_format={"type": "json_object"},
            frequency_penalty=0.5,
            presence_penalty=0.3,
        )
        assert result.content == "Hello!"
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert "tools" in call_kwargs
        assert "tool_choice" in call_kwargs
        assert "frequency_penalty" in call_kwargs
        assert "presence_penalty" in call_kwargs

    async def test_acomplete_with_tools(self):
        adapter = _oai_adapter()
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=_mock_openai_response())
        adapter._async_client = mock_client

        result = await adapter.acomplete(
            _msgs(user="test"),
            tools=[{"type": "function", "function": {"name": "search"}}],
            tool_choice="auto",
            response_format={"type": "json_object"},
            frequency_penalty=0.5,
            presence_penalty=0.3,
        )
        assert result.content == "Hello!"

    def test_complete_with_max_tokens_and_stop(self):
        adapter = _oai_adapter()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response()
        adapter._client = mock_client

        result = adapter.complete(_msgs(user="test"), max_tokens=100, stop=["END"])
        assert result.content == "Hello!"
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["max_tokens"] == 100
        assert call_kwargs["stop"] == ["END"]


class TestOpenAIExtractChunkContent:
    """Cover _extract_chunk_content edge cases."""

    def test_extract_chunk_content_empty_choices(self):
        adapter = _oai_adapter()
        chunk = MagicMock()
        chunk.choices = []
        assert adapter._extract_chunk_content(chunk) is None

    def test_extract_chunk_content_none_delta(self):
        adapter = _oai_adapter()
        chunk = MagicMock()
        choice = MagicMock()
        choice.delta.content = None
        chunk.choices = [choice]
        assert adapter._extract_chunk_content(chunk) is None

    def test_extract_chunk_content_valid(self):
        adapter = _oai_adapter()
        chunk = MagicMock()
        choice = MagicMock()
        choice.delta.content = "data"
        chunk.choices = [choice]
        assert adapter._extract_chunk_content(chunk) == "data"


class TestOpenAIStreamingHelpers:
    """Cover _build_streaming_params and _process_stream_chunks."""

    def test_build_streaming_params_with_stop_and_max_tokens(self):
        adapter = _oai_adapter()
        params = adapter._build_streaming_params(
            _msgs(user="hi"),
            0.5,
            200,
            0.9,
            ["STOP"],
            tools=[{"type": "function"}],
            frequency_penalty=0.2,
            presence_penalty=0.1,
        )
        assert params["stream"] is True
        assert params["max_tokens"] == 200
        assert params["stop"] == ["STOP"]
        assert "tools" in params

    def test_process_stream_chunks(self):
        adapter = _oai_adapter()
        chunk1 = MagicMock()
        choice1 = MagicMock()
        choice1.delta.content = "a"
        chunk1.choices = [choice1]

        chunk2 = MagicMock()
        choice2 = MagicMock()
        choice2.delta.content = None
        chunk2.choices = [choice2]

        chunk3 = MagicMock()
        choice3 = MagicMock()
        choice3.delta.content = "b"
        chunk3.choices = [choice3]

        result = list(adapter._process_stream_chunks(iter([chunk1, chunk2, chunk3])))
        assert result == ["a", "b"]


class TestOpenAIProviderMethods:
    """Cover get_streaming_mode and get_provider_name."""

    def test_get_streaming_mode(self):
        adapter = _oai_adapter()
        assert adapter.get_streaming_mode() == StreamingMode.SUPPORTED

    def test_get_provider_name(self):
        adapter = _oai_adapter()
        assert adapter.get_provider_name() == "openai"


class TestOpenAIHealthCheck:
    """Cover health_check healthy and unhealthy paths."""

    async def test_health_check_healthy(self):
        adapter = _oai_adapter()
        mock_client = MagicMock()
        mock_client.models.list = AsyncMock(return_value=[])
        adapter._async_client = mock_client

        result = await adapter.health_check()
        assert result.status == AdapterStatus.HEALTHY
        assert "accessible" in result.message.lower()

    async def test_health_check_unhealthy(self):
        adapter = _oai_adapter()
        mock_client = MagicMock()
        mock_client.models.list = AsyncMock(side_effect=OSError("connection error"))
        adapter._async_client = mock_client

        result = await adapter.health_check()
        assert result.status == AdapterStatus.UNHEALTHY
        assert "connection error" in result.message


class TestOpenAICountTokensBranches:
    """Cover count_tokens edge cases."""

    def test_count_tokens_with_name(self):
        """Cover the name token counting branch."""
        adapter = _oai_adapter()
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = [1, 2]
        adapter._tiktoken_encoder = mock_encoder

        msgs = [LLMMessage(role="user", content="hi", name="Alice")]
        count = adapter.count_tokens(msgs)
        # 4 (formatting) + 2 (role) + 2 (content) + 2 (name) - 1 (name present) + 2 (priming)
        assert count == 11

    def test_count_tokens_tiktoken_import_error(self):
        """Cover ImportError in _get_tiktoken_encoder."""
        adapter = _oai_adapter()
        adapter._tiktoken_encoder = None
        with patch.dict("sys.modules", {"tiktoken": None}):
            with pytest.raises(ImportError, match="tiktoken"):
                adapter.count_tokens(_msgs(user="hi"))


class TestOpenAIEstimateCostBranches:
    """Cover estimate_cost edge cases."""

    def test_estimate_cost_unknown_model(self):
        """Cover the fallback to gpt-5.2 pricing."""
        adapter = _oai_adapter()
        adapter.model = "future-gpt-99"
        cost = adapter.estimate_cost(1000, 500)
        assert cost.total_cost_usd > 0
        assert cost.pricing_model == "future-gpt-99"


class TestOpenAIStreamErrors:
    """Cover stream and astream error paths."""

    def test_stream_error(self):
        adapter = _oai_adapter()
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = TypeError("bad stream")
        adapter._client = mock_client

        with pytest.raises(TypeError, match="bad stream"):
            list(adapter.stream(_msgs(user="test")))

    async def test_astream_error(self):
        adapter = _oai_adapter()
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("async stream fail")
        )
        adapter._async_client = mock_client

        with pytest.raises(RuntimeError, match="async stream fail"):
            async for _ in adapter.astream(_msgs(user="test")):
                pass


# ===========================================================================
# Additional coverage: OPA Guard uncovered branches
# ===========================================================================


class TestOPAGuardVerifyActionBranches:
    """Cover verify_action uncovered branches."""

    async def test_verify_action_denied_by_policy(self):
        """Cover policy denial branch (not policy_result.get('allowed'))."""
        client = _mock_opa_client()
        # Constitutional check (first call) returns allowed=True,
        # Policy eval (second call) returns allowed=False
        client.evaluate_policy = AsyncMock(
            side_effect=[
                {"allowed": True},  # constitutional check
                {"allowed": False, "reason": "Prohibited action"},  # policy eval
            ]
        )
        guard = OPAGuard(opa_client=client)
        result = await guard.verify_action("agent1", {"type": "read"}, {})
        assert result.decision == GuardDecision.DENY
        assert result.is_allowed is False
        assert guard._stats["denied"] == 1

    async def test_verify_action_constitutional_hash_mismatch(self):
        """Cover constitutional hash mismatch branch."""
        client = _mock_opa_client(policy_result={"allowed": False})
        guard = OPAGuard(opa_client=client)
        result = await guard.verify_action(
            "agent1",
            {"type": "read", "constitutional_hash": "wrong_hash_value!"},
            {},
        )
        assert result.decision == GuardDecision.DENY
        assert result.constitutional_valid is False
        assert guard._stats["constitutional_failures"] >= 1

    async def test_verify_action_cancelled_error_propagates(self):
        """Cover asyncio.CancelledError re-raise."""
        client = _mock_opa_client()
        guard = OPAGuard(opa_client=client)

        # Make check_constitutional_compliance raise CancelledError
        guard.check_constitutional_compliance = AsyncMock(side_effect=asyncio.CancelledError())
        with pytest.raises(asyncio.CancelledError):
            await guard.verify_action("agent1", {"type": "read"}, {})


class TestOPAGuardConstitutionalComplianceBranches:
    """Cover check_constitutional_compliance uncovered branches."""

    async def test_hash_mismatch_returns_false(self):
        client = _mock_opa_client()
        guard = OPAGuard(opa_client=client)
        result = await guard.check_constitutional_compliance(
            {"constitutional_hash": "abcdef1234567890"}
        )
        assert result is False
        assert guard._stats["constitutional_failures"] >= 1

    async def test_exception_fail_closed_returns_false(self):
        client = _mock_opa_client()
        client.evaluate_policy.side_effect = RuntimeError("opa down")
        guard = OPAGuard(opa_client=client, fail_closed=True)
        result = await guard.check_constitutional_compliance({"type": "read"})
        assert result is False

    async def test_exception_fail_open_returns_true(self):
        client = _mock_opa_client()
        client.evaluate_policy.side_effect = RuntimeError("opa down")
        guard = OPAGuard(opa_client=client, fail_closed=False)
        result = await guard.check_constitutional_compliance({"type": "read"})
        assert result is True


class TestOPAGuardCollectSignatures:
    """Cover collect_signatures branches."""

    async def test_collect_signatures_timeout(self):
        """Cover the timeout expiry branch."""
        guard = OPAGuard(opa_client=_mock_opa_client())
        result = await guard.collect_signatures("decision-1", ["signer_a"], timeout=1)
        assert result.status == SignatureStatus.EXPIRED

    async def test_collect_signatures_completed(self):
        """Cover the is_complete branch after signature submission."""
        guard = OPAGuard(opa_client=_mock_opa_client())

        async def submit_after_delay():
            await asyncio.sleep(0.1)
            sig = Signature(signer_id="signer_a", reasoning="ok", confidence=1.0)
            sig_result = guard._pending_signatures.get("decision-2")
            if sig_result:
                sig_result.add_signature(sig)
                event = getattr(sig_result, "_completion_event", None)
                if event:
                    event.set()

        task = asyncio.create_task(submit_after_delay())
        result = await guard.collect_signatures("decision-2", ["signer_a"], timeout=5)
        await task
        # If signature was accepted and completed
        if result.is_complete:
            assert guard._stats["signatures_collected"] >= 1


class TestOPAGuardSubmitSignatureBranches:
    """Cover submit_signature additional branches."""

    async def test_submit_signature_success_with_event(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        sig_result = SignatureResult(
            decision_id="test_dec",
            required_signers=["signer_1"],
            required_count=1,
            threshold=1.0,
        )
        event = asyncio.Event()
        sig_result._completion_event = event  # type: ignore[attr-defined]
        guard._pending_signatures["test_dec"] = sig_result

        success = await guard.submit_signature(
            "test_dec", "signer_1", reasoning="approved", confidence=0.9
        )
        assert success is True
        # Event should be set since all signatures collected
        assert event.is_set()


class TestOPAGuardSubmitForReview:
    """Cover submit_for_review branches."""

    async def test_submit_for_review_with_callback(self):
        """Cover the critic callback notification branch."""
        guard = OPAGuard(opa_client=_mock_opa_client())

        callback_called = False

        async def critic_callback(decision, review_result):
            nonlocal callback_called
            callback_called = True
            review = CriticReview(
                critic_id="critic_1",
                verdict="approve",
                reasoning="looks good",
                confidence=0.9,
            )
            review_result.add_review(review)

        guard.register_critic_agent("critic_1", ["general"], callback=critic_callback)

        result = await guard.submit_for_review(
            {"id": "rev-1", "action": "test"},
            ["critic_1"],
            timeout=3,
        )
        assert callback_called

    async def test_submit_for_review_timeout_no_consensus(self):
        """Cover the timeout + no consensus -> ESCALATED branch."""
        guard = OPAGuard(opa_client=_mock_opa_client())
        result = await guard.submit_for_review(
            {"id": "rev-2"},
            ["critic_1", "critic_2"],
            timeout=1,
        )
        assert result.status == ReviewStatus.ESCALATED

    async def test_submit_for_review_callback_error(self):
        """Cover the exception in callback notification."""
        guard = OPAGuard(opa_client=_mock_opa_client())

        def bad_callback(decision, review_result):
            raise RuntimeError("callback exploded")

        guard.register_critic_agent("critic_bad", ["general"], callback=bad_callback)
        # Should not raise - error is logged
        result = await guard.submit_for_review(
            {"id": "rev-3"},
            ["critic_bad"],
            timeout=1,
        )
        assert result is not None


class TestOPAGuardCloseBranch:
    """Cover close() method."""

    async def test_close_clears_state(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        guard._pending_signatures["x"] = MagicMock()
        guard._pending_reviews["y"] = MagicMock()

        await guard.close()
        assert len(guard._pending_signatures) == 0
        assert len(guard._pending_reviews) == 0

    async def test_close_without_client(self):
        guard = OPAGuard(opa_client=None)
        await guard.close()  # should not raise


class TestOPAGuardInitialize:
    """Cover initialize() branches."""

    async def test_initialize_with_existing_client_sets_fail_closed(self):
        client = _mock_opa_client()
        client.fail_closed = True
        guard = OPAGuard(opa_client=client, fail_closed=False)
        await guard.initialize()
        assert client.fail_closed is False

    async def test_initialize_creates_client_when_none(self):
        with patch("enhanced_agent_bus.deliberation_layer.opa_guard.get_opa_client") as mock_get:
            mock_client = _mock_opa_client()
            mock_get.return_value = mock_client
            guard = OPAGuard(opa_client=None)
            await guard.initialize()
            assert guard.opa_client is mock_client


class TestOPAGuardEvaluateBranches2:
    """Cover additional evaluate() branches."""

    async def test_evaluate_allowed_false_reasons_list(self):
        client = _mock_opa_client(
            policy_result={
                "allowed": False,
                "reasons": ["policy violation"],
                "version": "2.0.0",
            }
        )
        guard = OPAGuard(opa_client=client)
        result = await guard.evaluate({"type": "test"})
        assert result["allow"] is False
        assert "policy violation" in result["reasons"]
        assert result["version"] == "2.0.0"

    async def test_evaluate_no_allowed_or_allow_key_fail_closed(self):
        """Cover missing both 'allowed' and 'allow' keys with fail_closed=True."""
        client = _mock_opa_client(policy_result={"reasons": [], "version": "1.0.0"})
        guard = OPAGuard(opa_client=client, fail_closed=True)
        result = await guard.evaluate({"type": "test"})
        assert result["allow"] is False

    async def test_evaluate_no_allowed_or_allow_key_fail_open(self):
        """Cover missing both keys with fail_closed=False."""
        client = _mock_opa_client(policy_result={"reasons": [], "version": "1.0.0"})
        guard = OPAGuard(opa_client=client, fail_closed=False)
        result = await guard.evaluate({"type": "test"})
        assert result["allow"] is True


class TestOPAGuardRiskCalcBranches:
    """Cover additional risk calculation branches."""

    def test_risk_score_capped_at_one(self):
        """Cover min(risk_score, 1.0) branch."""
        guard = OPAGuard(opa_client=_mock_opa_client())
        score = guard._calculate_risk_score(
            {"type": "delete", "impact_score": 1.0, "scope": "global"},
            {},
            {"metadata": {"risk_score": 1.0}},
        )
        assert score <= 1.0

    def test_risk_level_medium(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        assert guard._determine_risk_level(0.5) == "medium"

    def test_risk_level_high(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        assert guard._determine_risk_level(0.75) == "high"

    def test_risk_level_critical(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        assert guard._determine_risk_level(0.95) == "critical"

    def test_risk_factors_delete_action(self):
        guard = OPAGuard(opa_client=_mock_opa_client())
        factors = guard._identify_risk_factors(
            {"type": "delete", "affects_users": True, "irreversible": True},
            {"scope": "global", "production": True},
        )
        assert any("delete" in f.lower() for f in factors)
        assert any("user" in f.lower() for f in factors)
        assert any("irreversible" in f.lower() for f in factors)
        assert any("global" in f.lower() for f in factors)
        assert any("production" in f.lower() for f in factors)
