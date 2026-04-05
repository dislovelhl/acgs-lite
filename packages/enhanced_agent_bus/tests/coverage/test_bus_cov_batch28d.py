"""
Comprehensive coverage tests for batch 28d:
- src/core/shared/metrics/_registry.py
- packages/enhanced_agent_bus/adapters/huggingface_adapter.py
- packages/enhanced_agent_bus/_ext_context_memory.py
- packages/enhanced_agent_bus/adapters/deepseek_adapter.py
- packages/enhanced_agent_bus/optimization_toolkit/context.py

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. _registry.py imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus._compat.metrics._registry import (
    _METRICS_CACHE,
    _find_existing_metric,
    _get_or_create_counter,
    _get_or_create_gauge,
    _get_or_create_histogram,
    _get_or_create_info,
)

# ---------------------------------------------------------------------------
# 2. adapters imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.adapters.base import (
    MessageRole,
    ModelMessage,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    StreamChunk,
)
from enhanced_agent_bus.adapters.deepseek_adapter import DeepSeekAdapter
from enhanced_agent_bus.adapters.huggingface_adapter import HuggingFaceAdapter

# ---------------------------------------------------------------------------
# 3. context optimizer imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.optimization_toolkit.context import (
    ContextCompressor,
    ContextWindowOptimizer,
    compress_context,
)


# ===========================================================================
# _registry.py tests -- cover missing lines 29-31, 44-45, 54-59, 69-70,
# 76-81, 91-92, 98-103, 113-114, 120-125
# ===========================================================================
class TestMetricsRegistryFindExisting:
    """Tests for _find_existing_metric covering collector iteration and
    error-handling branches."""

    def _clear_cache(self):
        _METRICS_CACHE.clear()

    def test_find_existing_by_collector_name_attribute(self):
        """Cover lines 26-29: iteration over collectors with _name attribute."""
        mock_collector = MagicMock()
        mock_collector._name = "test_find_by_attr_metric"

        mock_registry = MagicMock()
        mock_registry._names_to_collectors = {
            "other_key": mock_collector,
        }

        with patch("src.core.shared.metrics._registry.REGISTRY", mock_registry):
            result = _find_existing_metric("test_find_by_attr_metric")
            assert result is mock_collector

    def test_find_existing_returns_none_when_not_found(self):
        """Cover the return None branch (line 32)."""
        mock_registry = MagicMock()
        mock_registry._names_to_collectors = {}
        with patch("src.core.shared.metrics._registry.REGISTRY", mock_registry):
            result = _find_existing_metric("nonexistent_metric_xyz")
            assert result is None

    def test_find_existing_handles_runtime_error(self):
        """Cover line 30-31: exception handling in _find_existing_metric."""
        mock_registry = MagicMock()
        mock_registry._names_to_collectors.__contains__ = MagicMock(
            side_effect=RuntimeError("boom")
        )
        with patch("src.core.shared.metrics._registry.REGISTRY", mock_registry):
            result = _find_existing_metric("whatever")
            assert result is None


class TestGetOrCreateHistogram:
    def setup_method(self):
        _METRICS_CACHE.clear()

    def test_returns_cached_histogram(self):
        """Cover line 39-40: cache hit path."""
        sentinel = object()
        _METRICS_CACHE["cached_hist"] = sentinel
        result = _get_or_create_histogram("cached_hist", "desc", ["l"])
        assert result is sentinel
        del _METRICS_CACHE["cached_hist"]

    def test_returns_existing_from_registry(self):
        """Cover lines 43-45: existing metric in registry."""
        sentinel = object()
        with patch(
            "src.core.shared.metrics._registry._find_existing_metric",
            return_value=sentinel,
        ):
            result = _get_or_create_histogram("hist_existing_reg", "desc", ["l"])
            assert result is sentinel
        _METRICS_CACHE.pop("hist_existing_reg", None)

    def test_valueerror_fallback_to_existing(self):
        """Cover lines 54-59: ValueError during creation, fallback to existing."""
        sentinel = object()
        with (
            patch(
                "src.core.shared.metrics._registry._find_existing_metric",
                side_effect=[None, sentinel],
            ),
            patch(
                "src.core.shared.metrics._registry.Histogram",
                side_effect=ValueError("dup"),
            ),
        ):
            result = _get_or_create_histogram("hist_ve", "d", ["l"])
            assert result is sentinel
        _METRICS_CACHE.pop("hist_ve", None)

    def test_valueerror_reraise_when_not_found(self):
        """Cover line 59: ValueError re-raised when no existing metric found."""
        with (
            patch(
                "src.core.shared.metrics._registry._find_existing_metric",
                return_value=None,
            ),
            patch(
                "src.core.shared.metrics._registry.Histogram",
                side_effect=ValueError("dup"),
            ),
        ):
            with pytest.raises(ValueError, match="dup"):
                _get_or_create_histogram("hist_ve_raise", "d", ["l"])
        _METRICS_CACHE.pop("hist_ve_raise", None)

    def test_histogram_with_buckets(self):
        """Cover line 49: buckets branch."""
        mock_hist = MagicMock()
        with (
            patch(
                "src.core.shared.metrics._registry._find_existing_metric",
                return_value=None,
            ),
            patch(
                "src.core.shared.metrics._registry.Histogram",
                return_value=mock_hist,
            ),
        ):
            result = _get_or_create_histogram("hist_buckets", "d", ["l"], buckets=[0.1, 0.5, 1.0])
            assert result is mock_hist
        _METRICS_CACHE.pop("hist_buckets", None)


class TestGetOrCreateCounter:
    def setup_method(self):
        _METRICS_CACHE.clear()

    def test_returns_existing_from_registry(self):
        """Cover lines 67-70."""
        sentinel = object()
        with patch(
            "src.core.shared.metrics._registry._find_existing_metric",
            return_value=sentinel,
        ):
            result = _get_or_create_counter("ctr_exist", "d", ["l"])
            assert result is sentinel
        _METRICS_CACHE.pop("ctr_exist", None)

    def test_valueerror_fallback(self):
        """Cover lines 76-81."""
        sentinel = object()
        with (
            patch(
                "src.core.shared.metrics._registry._find_existing_metric",
                side_effect=[None, sentinel],
            ),
            patch(
                "src.core.shared.metrics._registry.Counter",
                side_effect=ValueError("dup"),
            ),
        ):
            result = _get_or_create_counter("ctr_ve", "d", ["l"])
            assert result is sentinel
        _METRICS_CACHE.pop("ctr_ve", None)

    def test_valueerror_reraise(self):
        """Cover line 81: re-raise when no existing metric."""
        with (
            patch(
                "src.core.shared.metrics._registry._find_existing_metric",
                return_value=None,
            ),
            patch(
                "src.core.shared.metrics._registry.Counter",
                side_effect=ValueError("dup"),
            ),
        ):
            with pytest.raises(ValueError, match="dup"):
                _get_or_create_counter("ctr_ve_rr", "d", ["l"])
        _METRICS_CACHE.pop("ctr_ve_rr", None)


class TestGetOrCreateGauge:
    def setup_method(self):
        _METRICS_CACHE.clear()

    def test_returns_existing_from_registry(self):
        """Cover lines 89-92."""
        sentinel = object()
        with patch(
            "src.core.shared.metrics._registry._find_existing_metric",
            return_value=sentinel,
        ):
            result = _get_or_create_gauge("gauge_exist", "d", ["l"])
            assert result is sentinel
        _METRICS_CACHE.pop("gauge_exist", None)

    def test_valueerror_fallback(self):
        """Cover lines 98-103."""
        sentinel = object()
        with (
            patch(
                "src.core.shared.metrics._registry._find_existing_metric",
                side_effect=[None, sentinel],
            ),
            patch(
                "src.core.shared.metrics._registry.Gauge",
                side_effect=ValueError("dup"),
            ),
        ):
            result = _get_or_create_gauge("gauge_ve", "d", ["l"])
            assert result is sentinel
        _METRICS_CACHE.pop("gauge_ve", None)

    def test_valueerror_reraise(self):
        with (
            patch(
                "src.core.shared.metrics._registry._find_existing_metric",
                return_value=None,
            ),
            patch(
                "src.core.shared.metrics._registry.Gauge",
                side_effect=ValueError("dup"),
            ),
        ):
            with pytest.raises(ValueError, match="dup"):
                _get_or_create_gauge("gauge_ve_rr", "d", ["l"])
        _METRICS_CACHE.pop("gauge_ve_rr", None)


class TestGetOrCreateInfo:
    def setup_method(self):
        _METRICS_CACHE.clear()

    def test_returns_existing_from_registry(self):
        """Cover lines 111-114."""
        sentinel = object()
        with patch(
            "src.core.shared.metrics._registry._find_existing_metric",
            return_value=sentinel,
        ):
            result = _get_or_create_info("info_exist", "d")
            assert result is sentinel
        _METRICS_CACHE.pop("info_exist", None)

    def test_valueerror_fallback(self):
        """Cover lines 120-125."""
        sentinel = object()
        with (
            patch(
                "src.core.shared.metrics._registry._find_existing_metric",
                side_effect=[None, sentinel],
            ),
            patch(
                "src.core.shared.metrics._registry.Info",
                side_effect=ValueError("dup"),
            ),
        ):
            result = _get_or_create_info("info_ve", "d")
            assert result is sentinel
        _METRICS_CACHE.pop("info_ve", None)

    def test_valueerror_reraise(self):
        with (
            patch(
                "src.core.shared.metrics._registry._find_existing_metric",
                return_value=None,
            ),
            patch(
                "src.core.shared.metrics._registry.Info",
                side_effect=ValueError("dup"),
            ),
        ):
            with pytest.raises(ValueError, match="dup"):
                _get_or_create_info("info_ve_rr", "d")
        _METRICS_CACHE.pop("info_ve_rr", None)


# ===========================================================================
# HuggingFace adapter tests -- cover missing lines
# ===========================================================================
class TestHuggingFaceAdapter:
    def _make_adapter(self):
        return HuggingFaceAdapter(api_key="test-key", timeout_seconds=10)

    def _make_request(self, **kwargs):
        defaults = {
            "messages": [
                ModelMessage(role=MessageRole.SYSTEM, content="You are helpful."),
                ModelMessage(role=MessageRole.USER, content="Hello"),
            ],
            "model": "test-model",
        }
        defaults.update(kwargs)
        return ModelRequest(**defaults)

    def test_init(self):
        adapter = self._make_adapter()
        assert adapter.provider == ModelProvider.HUGGINGFACE
        assert adapter.default_model == "meta-llama/Llama-3.1-8B-Instruct"
        assert adapter._client is None

    def test_translate_request(self):
        """Cover lines 78-93: translate_request with system/user roles."""
        adapter = self._make_adapter()
        request = self._make_request()
        payload = adapter.translate_request(request)
        assert payload["model"] == "test-model"
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"
        assert payload["stream"] is False

    def test_translate_request_uses_default_model(self):
        """Cover line 87: model fallback to default when model is empty/falsy."""
        adapter = self._make_adapter()
        request = self._make_request(model="")
        payload = adapter.translate_request(request)
        # Empty string is falsy, so `request.model or self.default_model` uses default
        assert payload["model"] == "meta-llama/Llama-3.1-8B-Instruct"

    def test_translate_response_string(self):
        """Cover lines 98-100: string response."""
        adapter = self._make_adapter()
        resp = adapter.translate_response("Hello world")
        assert resp.content == "Hello world"
        assert resp.provider == ModelProvider.HUGGINGFACE

    def test_translate_response_generated_text(self):
        """Cover lines 101-103: dict with generated_text."""
        adapter = self._make_adapter()
        resp = adapter.translate_response({"generated_text": "Response text"})
        assert resp.content == "Response text"

    def test_translate_response_choices_format(self):
        """Cover lines 104-105: dict with choices format."""
        adapter = self._make_adapter()
        resp = adapter.translate_response({"choices": [{"message": {"content": "From choices"}}]})
        assert resp.content == "From choices"

    def test_translate_response_empty_dict(self):
        """Cover empty dict path."""
        adapter = self._make_adapter()
        resp = adapter.translate_response({})
        assert resp.content == ""

    async def test_ensure_client_import_error(self):
        """Cover lines 62-68: ImportError when huggingface_hub not available."""
        adapter = self._make_adapter()
        with patch.dict(sys.modules, {"huggingface_hub": None}):
            with patch(
                "builtins.__import__",
                side_effect=ImportError("No module named 'huggingface_hub'"),
            ):
                with pytest.raises(ImportError, match="HuggingFace Hub not installed"):
                    await adapter._ensure_client()

    async def test_ensure_client_success(self):
        """Cover lines 69-73: successful client creation."""
        adapter = self._make_adapter()
        mock_client = MagicMock()
        mock_module = MagicMock()
        mock_module.AsyncInferenceClient = MagicMock(return_value=mock_client)

        with patch.dict(sys.modules, {"huggingface_hub": mock_module}):
            client = await adapter._ensure_client()
            assert client is mock_client

    async def test_ensure_client_cached(self):
        """Cover line 62: cached client returned."""
        adapter = self._make_adapter()
        sentinel = object()
        adapter._client = sentinel
        client = await adapter._ensure_client()
        assert client is sentinel

    async def test_complete(self):
        """Cover lines 117-138: complete method."""
        adapter = self._make_adapter()

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 20
        mock_usage.total_tokens = 30

        mock_choice = MagicMock()
        mock_choice.message.content = "Completed response"
        mock_choice.finish_reason = "stop"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_client = AsyncMock()
        mock_client.chat_completion = AsyncMock(return_value=mock_response)
        adapter._client = mock_client

        request = self._make_request()
        result = await adapter.complete(request)
        assert result.content == "Completed response"
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 20

    async def test_complete_no_usage(self):
        """Cover lines 134-136: usage is None."""
        adapter = self._make_adapter()

        mock_choice = MagicMock()
        mock_choice.message.content = "No usage"
        mock_choice.finish_reason = "stop"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        mock_client = AsyncMock()
        mock_client.chat_completion = AsyncMock(return_value=mock_response)
        adapter._client = mock_client

        request = self._make_request()
        result = await adapter.complete(request)
        assert result.prompt_tokens == 0
        assert result.completion_tokens == 0
        assert result.total_tokens == 0

    async def test_stream(self):
        """Cover lines 140-158: stream method."""
        adapter = self._make_adapter()

        mock_delta = MagicMock()
        mock_delta.content = "chunk1"
        mock_choice = MagicMock()
        mock_choice.delta = mock_delta
        mock_choice.finish_reason = None
        mock_chunk1 = MagicMock()
        mock_chunk1.choices = [mock_choice]

        mock_delta2 = MagicMock()
        mock_delta2.content = "chunk2"
        mock_choice2 = MagicMock()
        mock_choice2.delta = mock_delta2
        mock_choice2.finish_reason = "stop"
        mock_chunk2 = MagicMock()
        mock_chunk2.choices = [mock_choice2]

        async def mock_stream_iter():
            yield mock_chunk1
            yield mock_chunk2

        mock_client = AsyncMock()
        mock_client.chat_completion = AsyncMock(return_value=mock_stream_iter())
        adapter._client = mock_client

        request = self._make_request(stream=True)
        chunks = []
        async for chunk in adapter.stream(request):
            chunks.append(chunk)
        assert len(chunks) == 2
        assert chunks[0].content == "chunk1"
        assert chunks[1].is_final is True


# ===========================================================================
# DeepSeek adapter tests -- cover missing lines
# ===========================================================================
class TestDeepSeekAdapter:
    def _make_adapter(self):
        return DeepSeekAdapter(api_key="test-key", timeout_seconds=10)

    def _make_request(self, **kwargs):
        defaults = {
            "messages": [
                ModelMessage(role=MessageRole.SYSTEM, content="System"),
                ModelMessage(role=MessageRole.USER, content="Hello"),
                ModelMessage(role=MessageRole.ASSISTANT, content="Hi"),
            ],
            "model": "deepseek-chat",
        }
        defaults.update(kwargs)
        return ModelRequest(**defaults)

    def test_init(self):
        adapter = self._make_adapter()
        assert adapter.provider == ModelProvider.DEEPSEEK
        assert adapter.default_model == "deepseek-chat"
        assert adapter._client is None

    def test_translate_request(self):
        """Cover lines 79-100: role mapping and payload construction."""
        adapter = self._make_adapter()
        request = self._make_request()
        payload = adapter.translate_request(request)
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"
        assert payload["messages"][2]["role"] == "assistant"
        assert payload["model"] == "deepseek-chat"

    def test_translate_response(self):
        """Cover lines 104-118: full response translation."""
        adapter = self._make_adapter()
        raw = {
            "id": "resp-1",
            "model": "deepseek-chat",
            "choices": [
                {
                    "message": {"content": "Hello from DeepSeek"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 10,
                "total_tokens": 15,
            },
        }
        resp = adapter.translate_response(raw)
        assert resp.content == "Hello from DeepSeek"
        assert resp.model == "deepseek-chat"
        assert resp.provider == ModelProvider.DEEPSEEK
        assert resp.prompt_tokens == 5
        assert resp.completion_tokens == 10
        assert resp.total_tokens == 15
        assert resp.response_id == "resp-1"

    def test_translate_response_empty(self):
        """Cover default fallback values."""
        adapter = self._make_adapter()
        resp = adapter.translate_response({})
        assert resp.content == ""
        assert resp.model == ""
        assert resp.finish_reason == "stop"

    async def test_ensure_client_import_error(self):
        """Cover lines 63-69: ImportError path."""
        adapter = self._make_adapter()
        with patch.dict(sys.modules, {"openai": None}):
            with patch(
                "builtins.__import__",
                side_effect=ImportError("No module named 'openai'"),
            ):
                with pytest.raises(ImportError, match="OpenAI package not installed"):
                    await adapter._ensure_client()

    async def test_ensure_client_success(self):
        """Cover lines 70-75: successful OpenAI client creation."""
        adapter = self._make_adapter()
        mock_client = MagicMock()
        mock_module = MagicMock()
        mock_module.AsyncOpenAI = MagicMock(return_value=mock_client)

        with patch.dict(sys.modules, {"openai": mock_module}):
            client = await adapter._ensure_client()
            assert client is mock_client

    async def test_ensure_client_cached(self):
        adapter = self._make_adapter()
        sentinel = object()
        adapter._client = sentinel
        assert (await adapter._ensure_client()) is sentinel

    async def test_complete(self):
        """Cover lines 122-125: complete method."""
        adapter = self._make_adapter()

        mock_resp_obj = MagicMock()
        mock_resp_obj.model_dump.return_value = {
            "id": "resp-2",
            "model": "deepseek-chat",
            "choices": [{"message": {"content": "Answer"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 7, "total_tokens": 10},
        }

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp_obj)
        adapter._client = mock_client

        request = self._make_request()
        result = await adapter.complete(request)
        assert result.content == "Answer"
        assert result.total_tokens == 10

    async def test_stream(self):
        """Cover lines 127-141: stream method."""
        adapter = self._make_adapter()

        mock_delta1 = MagicMock()
        mock_delta1.content = "s1"
        mock_choice1 = MagicMock()
        mock_choice1.delta = mock_delta1
        mock_choice1.finish_reason = None
        mock_chunk1 = MagicMock()
        mock_chunk1.choices = [mock_choice1]

        mock_delta2 = MagicMock()
        mock_delta2.content = "s2"
        mock_choice2 = MagicMock()
        mock_choice2.delta = mock_delta2
        mock_choice2.finish_reason = "stop"
        mock_chunk2 = MagicMock()
        mock_chunk2.choices = [mock_choice2]

        async def mock_aiter():
            yield mock_chunk1
            yield mock_chunk2

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_aiter())
        adapter._client = mock_client

        request = self._make_request()
        chunks = []
        async for chunk in adapter.stream(request):
            chunks.append(chunk)
        assert len(chunks) == 2
        assert chunks[0].content == "s1"
        assert chunks[1].is_final is True

    async def test_stream_empty_choices(self):
        """Cover line 135: chunk with no choices."""
        adapter = self._make_adapter()

        mock_chunk_empty = MagicMock()
        mock_chunk_empty.choices = []

        mock_delta = MagicMock()
        mock_delta.content = "final"
        mock_choice = MagicMock()
        mock_choice.delta = mock_delta
        mock_choice.finish_reason = "stop"
        mock_chunk_final = MagicMock()
        mock_chunk_final.choices = [mock_choice]

        async def mock_aiter():
            yield mock_chunk_empty
            yield mock_chunk_final

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_aiter())
        adapter._client = mock_client

        request = self._make_request()
        chunks = []
        async for chunk in adapter.stream(request):
            chunks.append(chunk)
        # Empty choices chunk should be skipped
        assert len(chunks) == 1
        assert chunks[0].content == "final"


# ===========================================================================
# _ext_context_memory.py tests -- cover missing lines 40-71
# (ImportError fallback branch)
# ===========================================================================
class TestExtContextMemoryFallbacks:
    """Test that the extension module correctly falls back to object stubs
    when context_memory subpackage is unavailable."""

    def test_import_success_path(self):
        """Cover lines 4-39: successful import sets CONTEXT_MEMORY_AVAILABLE=True."""
        mod = importlib.import_module("enhanced_agent_bus._ext_context_memory")
        # The flag is set based on whether context_memory is importable
        assert hasattr(mod, "CONTEXT_MEMORY_AVAILABLE")
        assert isinstance(mod.CONTEXT_MEMORY_AVAILABLE, bool)

    def test_all_exports_present(self):
        """All names in _EXT_ALL must be attributes of the module."""
        mod = importlib.import_module("enhanced_agent_bus._ext_context_memory")
        for name in mod._EXT_ALL:
            assert hasattr(mod, name), f"Missing export: {name}"

    def test_fallback_stubs_when_import_fails(self):
        """Cover lines 40-71: force ImportError and verify fallback stubs."""
        # Remove cached module so we can re-import
        mod_name = "enhanced_agent_bus._ext_context_memory"
        orig_mod = sys.modules.pop(mod_name, None)

        # Also block the context_memory subpackage
        blocked = "enhanced_agent_bus.context_memory"
        orig_cm = sys.modules.get(blocked)
        sys.modules[blocked] = None  # type: ignore[assignment]

        try:
            # Force re-import with blocked dependency
            mod = importlib.import_module(mod_name)
            importlib.reload(mod)

            assert mod.CONTEXT_MEMORY_AVAILABLE is False

            # All fallback names should be `object`
            fallback_names = [
                "ContextMemoryChunk",
                "ContextPriority",
                "ContextRetrievalResult",
                "ContextType",
                "ContextMemoryWindow",
                "EpisodicMemoryEntry",
                "JRTConfig",
                "MambaConfig",
                "MemoryConsolidationResult",
                "MemoryOperation",
                "MemoryOperationType",
                "MemoryQuery",
                "SemanticMemoryEntry",
                "MambaProcessor",
                "Mamba2SSMLayer",
                "MambaProcessorConfig",
                "HybridContextManager",
                "HybridContextConfig",
                "ProcessingMode",
                "JRTContextPreparer",
                "JRTRetrievalStrategy",
                "CriticalSectionMarker",
                "LongTermMemoryStore",
                "LongTermMemoryConfig",
                "MemoryTier",
                "ConsolidationStrategy",
                "ConstitutionalContextCache",
                "CacheConfig",
                "ContextMemoryCacheEntry",
                "CacheStats",
            ]
            for name in fallback_names:
                val = getattr(mod, name)
                assert val is object, f"{name} should be object stub, got {val}"
        finally:
            # Restore original modules
            if orig_mod is not None:
                sys.modules[mod_name] = orig_mod
            elif mod_name in sys.modules:
                del sys.modules[mod_name]
            if orig_cm is not None:
                sys.modules[blocked] = orig_cm
            else:
                sys.modules.pop(blocked, None)


# ===========================================================================
# optimization_toolkit/context.py tests -- cover missing lines
# ===========================================================================
class TestContextWindowOptimizer:
    def test_estimate_tokens(self):
        opt = ContextWindowOptimizer(max_tokens=100)
        assert opt.estimate_tokens("abcdefgh") == 2  # 8 chars / 4
        assert opt.estimate_tokens("") == 0

    def test_compress_no_compression_needed(self):
        """Cover line 71: no compression needed."""
        opt = ContextWindowOptimizer(max_tokens=1000)
        short = "Hello world"
        assert opt.compress_context(short) == short

    def test_compress_short_content_truncation(self):
        """Cover lines 75-84: short content (<= 20 lines) truncation."""
        opt = ContextWindowOptimizer(max_tokens=5)
        # 10 lines, each 20 chars = 200 chars total, 50 tokens > 5
        lines = ["x" * 20 for _ in range(10)]
        text = "\n".join(lines)
        result = opt.compress_context(text)
        assert "[...context compressed...]" in result

    def test_compress_short_content_fits_after_check(self):
        """Cover lines 78-79: short content fits within target_chars."""
        opt = ContextWindowOptimizer(max_tokens=10)
        # 5 lines, each 4 chars = very short, but > max_tokens in estimate
        # Need estimated > limit but actual chars <= target
        lines = ["ab"] * 15  # 15 lines, short content
        text = "\n".join(lines)
        # estimate = len(text)//4, text length = 15*2 + 14 = 44 chars, ~11 tokens > 10
        result = opt.compress_context(text)
        assert "[...context compressed...]" in result

    def test_compress_long_content_intelligent(self):
        """Cover lines 88-109: intelligent compression for >20 lines."""
        opt = ContextWindowOptimizer(max_tokens=50)
        # Create >20 lines of content that exceeds budget
        lines = [f"Content line {i}" for i in range(30)]
        text = "\n".join(lines)
        result = opt.compress_context(text)
        # Should have processed system_segment + distilled_middle + recent_segment
        assert isinstance(result, str)

    def test_compress_filters_low_value_lines(self):
        """Cover line 93: _is_low_value filtering in middle segment."""
        opt = ContextWindowOptimizer(max_tokens=40)
        lines = ["System line " + str(i) for i in range(5)]
        lines += ["DEBUG: some debug output"] * 10  # low value
        lines += ["Important data " + str(i) for i in range(10)]
        lines += ["Recent line " + str(i) for i in range(10)]
        text = "\n".join(lines)
        result = opt.compress_context(text)
        assert "DEBUG:" not in result or "[...context compressed...]" in result

    def test_compress_further_truncation_large_middle(self):
        """Cover lines 101-107: further truncation when distilled_middle > 50."""
        opt = ContextWindowOptimizer(max_tokens=100)
        lines = ["System " + str(i) for i in range(5)]
        lines += ["Important data " + str(i) for i in range(60)]
        lines += ["Recent " + str(i) for i in range(10)]
        text = "\n".join(lines)
        result = opt.compress_context(text)
        assert isinstance(result, str)

    def test_compress_final_safety_truncation(self):
        """Cover lines 112-118: final safety truncation."""
        opt = ContextWindowOptimizer(max_tokens=10)
        lines = ["Important " + str(i) for i in range(25)]
        text = "\n".join(lines)
        result = opt.compress_context(text)
        assert "[...context compressed...]" in result

    def test_prioritize_context_empty(self):
        """Cover line 143: empty contexts list."""
        opt = ContextWindowOptimizer()
        assert opt.prioritize_context([], 100) == []

    def test_prioritize_context_fits(self):
        """Cover lines 146-161: contexts fit within budget."""
        opt = ContextWindowOptimizer()
        contexts = [
            {"content": "Short", "priority": 1, "timestamp": 100},
            {"content": "Also short", "priority": 2, "timestamp": 200},
        ]
        result = opt.prioritize_context(contexts, 1000)
        assert len(result) == 2
        # Higher priority first
        assert result[0]["priority"] == 2

    def test_prioritize_context_overflow_with_compression(self):
        """Cover lines 163-172: overflow triggers compression."""
        opt = ContextWindowOptimizer()
        contexts = [
            {"content": "A" * 400, "priority": 2, "timestamp": 200},
            {"content": "B" * 400, "priority": 1, "timestamp": 100},
        ]
        # Budget allows first but not second fully
        result = opt.prioritize_context(contexts, 150)
        assert len(result) >= 1
        # Check if second was compressed
        if len(result) == 2:
            assert result[1].get("compressed", False) is True

    def test_prioritize_context_remaining_too_small(self):
        """Cover the < 50 remaining tokens path (no compression attempted)."""
        opt = ContextWindowOptimizer()
        contexts = [
            {"content": "X" * 400, "priority": 2, "timestamp": 200},
            {"content": "Y" * 400, "priority": 1, "timestamp": 100},
        ]
        # Budget barely fits first item
        result = opt.prioritize_context(contexts, 101)
        assert len(result) == 1

    def test_is_low_value_patterns(self):
        """Cover lines 186-200: _is_low_value pattern matching."""
        opt = ContextWindowOptimizer()
        assert opt._is_low_value("DEBUG: something") is True
        assert opt._is_low_value("INFO: something") is True
        assert opt._is_low_value("TRACE: something") is True
        assert opt._is_low_value("[2024-01-15 12:30:00] event") is True
        assert opt._is_low_value("Traceback") is True
        assert opt._is_low_value("    at com.example.Class") is True
        assert opt._is_low_value('{"key": "value"}') is True
        assert opt._is_low_value("=" * 10) is True
        assert opt._is_low_value("   ") is True
        assert opt._is_low_value("# This is a comment") is True
        assert opt._is_low_value("GET /api/endpoint") is True
        assert opt._is_low_value("Host: example.com") is True
        assert opt._is_low_value("+++ a/file.py") is True
        assert opt._is_low_value("Normal content line") is False


class TestContextCompressor:
    def test_legacy_compress(self):
        """Cover line 209: ContextCompressor.compress legacy wrapper."""
        comp = ContextCompressor(max_tokens=1000)
        result = comp.compress("Short text")
        assert result == "Short text"

    def test_legacy_compress_with_long_content(self):
        comp = ContextCompressor(max_tokens=10)
        lines = ["Line " + str(i) for i in range(25)]
        text = "\n".join(lines)
        result = comp.compress(text)
        assert isinstance(result, str)


class TestCompressContextFunction:
    def test_convenience_function(self):
        """Cover lines 223-224: module-level compress_context function."""
        result = compress_context("Short text", max_tokens=1000)
        assert result == "Short text"

    def test_convenience_function_compression(self):
        text = "A" * 20000
        result = compress_context(text, max_tokens=100)
        assert "[...context compressed...]" in result
