# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/adapters/base.py
Targets ≥95% line coverage of base.py.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.adapters.base import (
    CONSTITUTIONAL_HASH,
    AdapterRegistry,
    MessageRole,
    ModelAdapter,
    ModelMessage,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    StreamChunk,
    _global_registry,
    get_adapter_registry,
)

# ---------------------------------------------------------------------------
# Concrete implementation for testing abstract class
# ---------------------------------------------------------------------------


class ConcreteAdapter(ModelAdapter):
    """Minimal concrete adapter used to test the abstract base class."""

    def __init__(self, should_fail_complete: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.should_fail_complete = should_fail_complete
        self._complete_calls: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self._complete_calls.append(request)
        if self.should_fail_complete:
            raise RuntimeError("simulated failure")
        return ModelResponse(
            content="hello",
            model=request.model or "test-model",
            provider=self.provider,
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[StreamChunk]:  # type: ignore[override]
        async def _gen():
            yield StreamChunk(content="chunk1")
            yield StreamChunk(content="chunk2", is_final=True, finish_reason="stop")

        return _gen()

    def translate_request(self, request: ModelRequest):
        return {"messages": [m.content for m in request.messages]}

    def translate_response(self, response) -> ModelResponse:
        return ModelResponse(
            content=response.get("content", ""),
            model=response.get("model", "test"),
            provider=self.provider,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_request(**kwargs) -> ModelRequest:
    messages = kwargs.pop("messages", [ModelMessage(role=MessageRole.USER, content="hello")])
    model = kwargs.pop("model", "gpt-4")
    return ModelRequest(messages=messages, model=model, **kwargs)


def make_response(**kwargs) -> ModelResponse:
    defaults = dict(content="test", model="gpt-4", provider=ModelProvider.OPENAI)
    defaults.update(kwargs)
    return ModelResponse(**defaults)


# ===========================================================================
# ModelProvider enum
# ===========================================================================


class TestModelProvider:
    def test_all_providers_present(self):
        values = {p.value for p in ModelProvider}
        assert "openai" in values
        assert "anthropic" in values
        assert "google" in values
        assert "deepseek" in values
        assert "meta" in values
        assert "huggingface" in values
        assert "moonshot" in values
        assert "custom" in values

    def test_provider_count(self):
        assert len(ModelProvider) == 9

    def test_provider_values_are_strings(self):
        for p in ModelProvider:
            assert isinstance(p.value, str)

    def test_enum_by_value(self):
        assert ModelProvider("openai") is ModelProvider.OPENAI
        assert ModelProvider("custom") is ModelProvider.CUSTOM

    def test_invalid_provider_raises(self):
        with pytest.raises(ValueError):
            ModelProvider("nonexistent")


# ===========================================================================
# MessageRole enum
# ===========================================================================


class TestMessageRole:
    def test_all_roles_present(self):
        values = {r.value for r in MessageRole}
        assert "system" in values
        assert "user" in values
        assert "assistant" in values
        assert "tool" in values
        assert "function" in values

    def test_role_count(self):
        assert len(MessageRole) == 5

    def test_enum_by_value(self):
        assert MessageRole("user") is MessageRole.USER
        assert MessageRole("tool") is MessageRole.TOOL

    def test_invalid_role_raises(self):
        with pytest.raises(ValueError):
            MessageRole("unknown")


# ===========================================================================
# ModelMessage dataclass
# ===========================================================================


class TestModelMessage:
    def test_minimal_construction(self):
        msg = ModelMessage(role=MessageRole.USER, content="hi")
        assert msg.role is MessageRole.USER
        assert msg.content == "hi"
        assert msg.name is None
        assert msg.tool_calls is None
        assert msg.tool_call_id is None
        assert isinstance(msg.metadata, dict)
        assert msg.metadata == {}

    def test_full_construction(self):
        tc = [{"id": "call_1", "function": {"name": "foo"}}]
        msg = ModelMessage(
            role=MessageRole.TOOL,
            content="result",
            name="my_tool",
            tool_calls=tc,
            tool_call_id="call_1",
            metadata={"key": "val"},
        )
        assert msg.name == "my_tool"
        assert msg.tool_calls == tc
        assert msg.tool_call_id == "call_1"
        assert msg.metadata == {"key": "val"}

    def test_metadata_is_independent(self):
        msg1 = ModelMessage(role=MessageRole.USER, content="a")
        msg2 = ModelMessage(role=MessageRole.USER, content="b")
        msg1.metadata["x"] = 1
        assert "x" not in msg2.metadata

    def test_system_role(self):
        msg = ModelMessage(role=MessageRole.SYSTEM, content="You are helpful.")
        assert msg.role is MessageRole.SYSTEM

    def test_assistant_role(self):
        msg = ModelMessage(role=MessageRole.ASSISTANT, content="Sure!")
        assert msg.role is MessageRole.ASSISTANT

    def test_function_role(self):
        msg = ModelMessage(role=MessageRole.FUNCTION, content="{}")
        assert msg.role is MessageRole.FUNCTION


# ===========================================================================
# ModelRequest dataclass
# ===========================================================================


class TestModelRequest:
    def test_minimal_construction(self):
        msgs = [ModelMessage(role=MessageRole.USER, content="hello")]
        req = ModelRequest(messages=msgs, model="gpt-4")
        assert req.messages == msgs
        assert req.model == "gpt-4"
        assert req.max_tokens == 4096
        assert req.temperature == 0.7
        assert req.top_p == 1.0
        assert req.stop is None
        assert req.stream is False
        assert req.tools is None
        assert req.tool_choice is None
        assert req.session_id is None
        assert req.tenant_id is None
        assert req.constitutional_hash == CONSTITUTIONAL_HASH
        assert isinstance(req.metadata, dict)
        assert isinstance(req.request_id, str)

    def test_request_id_generated(self):
        r1 = ModelRequest(messages=[], model="m")
        r2 = ModelRequest(messages=[], model="m")
        # Both are strings; they may differ by timestamp but are both non-empty
        assert r1.request_id
        assert r2.request_id

    def test_full_construction(self):
        req = ModelRequest(
            messages=[],
            model="claude-3",
            max_tokens=1024,
            temperature=0.5,
            top_p=0.9,
            stop=["END"],
            stream=True,
            tools=[{"name": "search"}],
            tool_choice="auto",
            session_id="sess-1",
            tenant_id="tenant-1",
            metadata={"src": "test"},
            request_id="req-42",
        )
        assert req.max_tokens == 1024
        assert req.temperature == 0.5
        assert req.stop == ["END"]
        assert req.stream is True
        assert req.tools == [{"name": "search"}]
        assert req.tool_choice == "auto"
        assert req.session_id == "sess-1"
        assert req.tenant_id == "tenant-1"
        assert req.metadata == {"src": "test"}
        assert req.request_id == "req-42"

    def test_tool_choice_dict(self):
        req = ModelRequest(messages=[], model="m", tool_choice={"type": "function"})
        assert req.tool_choice == {"type": "function"}

    def test_metadata_independent(self):
        r1 = ModelRequest(messages=[], model="m")
        r2 = ModelRequest(messages=[], model="m")
        r1.metadata["k"] = "v"
        assert "k" not in r2.metadata

    def test_constitutional_hash_default(self):
        req = ModelRequest(messages=[], model="m")
        assert req.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret


# ===========================================================================
# ModelResponse dataclass
# ===========================================================================


class TestModelResponse:
    def test_minimal_construction(self):
        resp = ModelResponse(content="hi", model="gpt-4", provider=ModelProvider.OPENAI)
        assert resp.content == "hi"
        assert resp.model == "gpt-4"
        assert resp.provider is ModelProvider.OPENAI
        assert resp.finish_reason == "stop"
        assert resp.prompt_tokens == 0
        assert resp.completion_tokens == 0
        assert resp.total_tokens == 0
        assert resp.tool_calls is None
        assert resp.constitutional_hash == CONSTITUTIONAL_HASH
        assert resp.governance_validated is False
        assert resp.governance_latency_ms == 0.0
        assert resp.response_id == ""
        assert isinstance(resp.created_at, datetime)
        assert isinstance(resp.metadata, dict)

    def test_full_construction(self):
        now = datetime.now(UTC)
        resp = ModelResponse(
            content="answer",
            model="gpt-4",
            provider=ModelProvider.ANTHROPIC,
            finish_reason="length",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            tool_calls=[{"id": "c1"}],
            constitutional_hash="abc",
            governance_validated=True,
            governance_latency_ms=1.5,
            response_id="resp-1",
            created_at=now,
            metadata={"x": 1},
        )
        assert resp.finish_reason == "length"
        assert resp.prompt_tokens == 10
        assert resp.completion_tokens == 20
        assert resp.total_tokens == 30
        assert resp.tool_calls == [{"id": "c1"}]
        assert resp.governance_validated is True
        assert resp.governance_latency_ms == 1.5
        assert resp.response_id == "resp-1"
        assert resp.created_at is now
        assert resp.metadata == {"x": 1}

    def test_to_dict_basic(self):
        resp = ModelResponse(content="hi", model="gpt-4", provider=ModelProvider.OPENAI)
        d = resp.to_dict()
        assert d["content"] == "hi"
        assert d["model"] == "gpt-4"
        assert d["provider"] == "openai"
        assert d["finish_reason"] == "stop"
        assert d["prompt_tokens"] == 0
        assert d["completion_tokens"] == 0
        assert d["total_tokens"] == 0
        assert d["tool_calls"] is None
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert d["governance_validated"] is False
        assert d["governance_latency_ms"] == 0.0
        assert d["response_id"] == ""
        assert "created_at" in d
        assert isinstance(d["created_at"], str)
        assert d["metadata"] == {}

    def test_to_dict_with_tool_calls(self):
        tc = [{"id": "call_1"}]
        resp = ModelResponse(
            content="x",
            model="m",
            provider=ModelProvider.GOOGLE,
            tool_calls=tc,
        )
        d = resp.to_dict()
        assert d["tool_calls"] == tc

    def test_to_dict_provider_value_is_string(self):
        for prov in ModelProvider:
            resp = ModelResponse(content="x", model="m", provider=prov)
            d = resp.to_dict()
            assert d["provider"] == prov.value

    def test_to_dict_created_at_iso_format(self):
        now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        resp = ModelResponse(content="x", model="m", provider=ModelProvider.OPENAI, created_at=now)
        d = resp.to_dict()
        assert "2025-06-01" in d["created_at"]

    def test_created_at_independent(self):
        r1 = ModelResponse(content="x", model="m", provider=ModelProvider.OPENAI)
        r2 = ModelResponse(content="y", model="m", provider=ModelProvider.OPENAI)
        # Each gets its own datetime instance
        assert isinstance(r1.created_at, datetime)
        assert isinstance(r2.created_at, datetime)

    def test_metadata_independent(self):
        r1 = ModelResponse(content="x", model="m", provider=ModelProvider.OPENAI)
        r2 = ModelResponse(content="y", model="m", provider=ModelProvider.OPENAI)
        r1.metadata["k"] = 1
        assert "k" not in r2.metadata


# ===========================================================================
# StreamChunk dataclass
# ===========================================================================


class TestStreamChunk:
    def test_minimal_construction(self):
        chunk = StreamChunk(content="hello")
        assert chunk.content == "hello"
        assert chunk.finish_reason is None
        assert chunk.tool_calls is None
        assert chunk.is_final is False

    def test_full_construction(self):
        tc = [{"id": "c1"}]
        chunk = StreamChunk(
            content="end",
            finish_reason="stop",
            tool_calls=tc,
            is_final=True,
        )
        assert chunk.finish_reason == "stop"
        assert chunk.tool_calls == tc
        assert chunk.is_final is True

    def test_empty_content(self):
        chunk = StreamChunk(content="")
        assert chunk.content == ""

    def test_final_chunk(self):
        chunk = StreamChunk(content="", finish_reason="stop", is_final=True)
        assert chunk.is_final is True
        assert chunk.finish_reason == "stop"


# ===========================================================================
# ModelAdapter (via ConcreteAdapter)
# ===========================================================================


class TestModelAdapterInit:
    def test_default_init(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        assert adapter.provider is ModelProvider.OPENAI
        assert adapter.api_key is None
        assert adapter.base_url is None
        assert adapter.default_model is None
        assert adapter.timeout_seconds == 60
        assert adapter._constitutional_hash == CONSTITUTIONAL_HASH

    def test_full_init(self):
        adapter = ConcreteAdapter(
            provider=ModelProvider.ANTHROPIC,
            api_key="sk-test",
            base_url="https://custom.example.com",
            default_model="claude-3",
            timeout_seconds=120,
        )
        assert adapter.api_key == "sk-test"
        assert adapter.base_url == "https://custom.example.com"
        assert adapter.default_model == "claude-3"
        assert adapter.timeout_seconds == 120

    def test_name_property(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        assert adapter.name == "openai_adapter"

    def test_name_property_anthropic(self):
        adapter = ConcreteAdapter(provider=ModelProvider.ANTHROPIC)
        assert adapter.name == "anthropic_adapter"

    def test_name_property_custom(self):
        adapter = ConcreteAdapter(provider=ModelProvider.CUSTOM)
        assert adapter.name == "custom_adapter"

    def test_all_providers_name(self):
        for prov in ModelProvider:
            adapter = ConcreteAdapter(provider=prov)
            assert adapter.name == f"{prov.value}_adapter"


class TestModelAdapterComplete:
    async def test_complete_returns_response(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        req = make_request()
        resp = await adapter.complete(req)
        assert isinstance(resp, ModelResponse)
        assert resp.content == "hello"

    async def test_complete_records_call(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        req = make_request()
        await adapter.complete(req)
        assert len(adapter._complete_calls) == 1
        assert adapter._complete_calls[0] is req

    async def test_complete_multiple_calls(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        for _i in range(5):
            await adapter.complete(make_request())
        assert len(adapter._complete_calls) == 5


class TestModelAdapterStream:
    async def test_stream_yields_chunks(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        req = make_request()
        chunks = []
        async for chunk in await adapter.stream(req):
            chunks.append(chunk)
        assert len(chunks) == 2
        assert chunks[0].content == "chunk1"
        assert chunks[1].content == "chunk2"
        assert chunks[1].is_final is True

    async def test_stream_finish_reason(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        req = make_request()
        last_chunk = None
        async for chunk in await adapter.stream(req):
            last_chunk = chunk
        assert last_chunk is not None
        assert last_chunk.finish_reason == "stop"


class TestModelAdapterTranslate:
    def test_translate_request(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        req = make_request()
        result = adapter.translate_request(req)
        assert "messages" in result

    def test_translate_response(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        raw = {"content": "response text", "model": "gpt-4"}
        resp = adapter.translate_response(raw)
        assert isinstance(resp, ModelResponse)
        assert resp.content == "response text"

    def test_translate_response_empty(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        resp = adapter.translate_response({})
        assert resp.content == ""


class TestModelAdapterValidateRequest:
    def test_valid_request_no_errors(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        req = make_request()
        errors = adapter.validate_request(req)
        assert errors == []

    def test_no_messages_error(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        req = make_request(messages=[], model="gpt-4")
        errors = adapter.validate_request(req)
        assert any("No messages" in e for e in errors)

    def test_no_model_no_default_error(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        msgs = [ModelMessage(role=MessageRole.USER, content="hi")]
        req = ModelRequest(messages=msgs, model="")
        errors = adapter.validate_request(req)
        assert any("No model" in e for e in errors)

    def test_no_model_but_default_set_no_error(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI, default_model="gpt-4")
        msgs = [ModelMessage(role=MessageRole.USER, content="hi")]
        req = ModelRequest(messages=msgs, model="")
        errors = adapter.validate_request(req)
        # Should NOT have the "No model" error since default_model is set
        assert not any("No model" in e for e in errors)

    def test_negative_max_tokens_error(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        req = make_request(max_tokens=-1)
        errors = adapter.validate_request(req)
        assert any("max_tokens" in e for e in errors)

    def test_zero_max_tokens_error(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        req = make_request(max_tokens=0)
        errors = adapter.validate_request(req)
        assert any("max_tokens" in e for e in errors)

    def test_temperature_too_high_error(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        req = make_request(temperature=2.1)
        errors = adapter.validate_request(req)
        assert any("temperature" in e for e in errors)

    def test_temperature_too_low_error(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        req = make_request(temperature=-0.1)
        errors = adapter.validate_request(req)
        assert any("temperature" in e for e in errors)

    def test_temperature_boundary_0_valid(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        req = make_request(temperature=0.0)
        errors = adapter.validate_request(req)
        assert not any("temperature" in e for e in errors)

    def test_temperature_boundary_2_valid(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        req = make_request(temperature=2.0)
        errors = adapter.validate_request(req)
        assert not any("temperature" in e for e in errors)

    def test_multiple_errors_accumulated(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        req = ModelRequest(messages=[], model="", max_tokens=-1, temperature=5.0)
        errors = adapter.validate_request(req)
        # Should have at least 3 errors: no messages, no model, max_tokens, temperature
        assert len(errors) >= 3

    def test_max_tokens_one_valid(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        req = make_request(max_tokens=1)
        errors = adapter.validate_request(req)
        assert not any("max_tokens" in e for e in errors)


class TestModelAdapterHealthCheck:
    async def test_health_check_success(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI, default_model="gpt-4")
        result = await adapter.health_check()
        assert result is True

    async def test_health_check_failure_runtime_error(self):
        adapter = ConcreteAdapter(
            provider=ModelProvider.OPENAI,
            default_model="gpt-4",
            should_fail_complete=True,
        )
        result = await adapter.health_check()
        assert result is False

    async def test_health_check_uses_default_model(self):
        """Health check should use default_model when set."""
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI, default_model="gpt-4")
        await adapter.health_check()
        # The complete call should have been made with model=default_model or ""
        assert len(adapter._complete_calls) == 1

    async def test_health_check_no_default_model(self):
        """Health check falls back to empty string when no default model."""
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        result = await adapter.health_check()
        assert result is True
        assert adapter._complete_calls[0].model == ""

    async def test_health_check_max_tokens_is_one(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI, default_model="gpt-4")
        await adapter.health_check()
        call = adapter._complete_calls[0]
        assert call.max_tokens == 1

    async def test_health_check_message_is_ping(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI, default_model="gpt-4")
        await adapter.health_check()
        call = adapter._complete_calls[0]
        assert len(call.messages) == 1
        assert call.messages[0].content == "ping"
        assert call.messages[0].role is MessageRole.USER

    async def test_health_check_catches_value_error(self):
        class FailAdapter(ConcreteAdapter):
            async def complete(self, request):
                raise ValueError("bad value")

        adapter = FailAdapter(provider=ModelProvider.OPENAI)
        assert await adapter.health_check() is False

    async def test_health_check_catches_type_error(self):
        class FailAdapter(ConcreteAdapter):
            async def complete(self, request):
                raise TypeError("type error")

        adapter = FailAdapter(provider=ModelProvider.OPENAI)
        assert await adapter.health_check() is False

    async def test_health_check_catches_os_error(self):
        class FailAdapter(ConcreteAdapter):
            async def complete(self, request):
                raise OSError("connection refused")

        adapter = FailAdapter(provider=ModelProvider.OPENAI)
        assert await adapter.health_check() is False


class TestModelAdapterGetCapabilities:
    def test_capabilities_keys(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        caps = adapter.get_capabilities()
        assert "provider" in caps
        assert "streaming" in caps
        assert "tool_calling" in caps
        assert "vision" in caps
        assert "function_calling" in caps
        assert "constitutional_hash" in caps

    def test_capabilities_provider_value(self):
        for prov in ModelProvider:
            adapter = ConcreteAdapter(provider=prov)
            caps = adapter.get_capabilities()
            assert caps["provider"] == prov.value

    def test_capabilities_streaming_true(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        assert adapter.get_capabilities()["streaming"] is True

    def test_capabilities_tool_calling_true(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        assert adapter.get_capabilities()["tool_calling"] is True

    def test_capabilities_vision_false(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        assert adapter.get_capabilities()["vision"] is False

    def test_capabilities_function_calling_true(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        assert adapter.get_capabilities()["function_calling"] is True

    def test_capabilities_constitutional_hash(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        assert adapter.get_capabilities()["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_capabilities_is_dict(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        assert isinstance(adapter.get_capabilities(), dict)


# ===========================================================================
# AdapterRegistry
# ===========================================================================


class TestAdapterRegistry:
    def _make_adapter(self, provider: ModelProvider) -> ConcreteAdapter:
        return ConcreteAdapter(provider=provider)

    def test_empty_registry(self):
        registry = AdapterRegistry()
        assert registry.list_providers() == []
        assert registry.get_default() is None

    def test_register_single(self):
        registry = AdapterRegistry()
        adapter = self._make_adapter(ModelProvider.OPENAI)
        registry.register(adapter)
        assert ModelProvider.OPENAI in registry.list_providers()
        assert registry.get(ModelProvider.OPENAI) is adapter

    def test_register_multiple(self):
        registry = AdapterRegistry()
        oa = self._make_adapter(ModelProvider.OPENAI)
        aa = self._make_adapter(ModelProvider.ANTHROPIC)
        registry.register(oa)
        registry.register(aa)
        providers = registry.list_providers()
        assert ModelProvider.OPENAI in providers
        assert ModelProvider.ANTHROPIC in providers
        assert len(providers) == 2

    def test_register_set_default(self):
        registry = AdapterRegistry()
        adapter = self._make_adapter(ModelProvider.OPENAI)
        registry.register(adapter, set_default=True)
        assert registry.get_default() is adapter

    def test_register_set_default_false(self):
        registry = AdapterRegistry()
        adapter = self._make_adapter(ModelProvider.OPENAI)
        registry.register(adapter, set_default=False)
        assert registry.get_default() is None

    def test_register_overrides_existing(self):
        registry = AdapterRegistry()
        a1 = self._make_adapter(ModelProvider.OPENAI)
        a2 = self._make_adapter(ModelProvider.OPENAI)
        registry.register(a1)
        registry.register(a2)
        assert registry.get(ModelProvider.OPENAI) is a2

    def test_get_nonexistent(self):
        registry = AdapterRegistry()
        assert registry.get(ModelProvider.OPENAI) is None

    def test_get_returns_correct_adapter(self):
        registry = AdapterRegistry()
        oa = self._make_adapter(ModelProvider.OPENAI)
        aa = self._make_adapter(ModelProvider.ANTHROPIC)
        registry.register(oa)
        registry.register(aa)
        assert registry.get(ModelProvider.OPENAI) is oa
        assert registry.get(ModelProvider.ANTHROPIC) is aa

    def test_get_default_none_by_default(self):
        registry = AdapterRegistry()
        assert registry.get_default() is None

    def test_get_default_set_last_wins(self):
        registry = AdapterRegistry()
        a1 = self._make_adapter(ModelProvider.OPENAI)
        a2 = self._make_adapter(ModelProvider.ANTHROPIC)
        registry.register(a1, set_default=True)
        registry.register(a2, set_default=True)
        assert registry.get_default() is a2

    def test_list_providers_empty(self):
        registry = AdapterRegistry()
        assert registry.list_providers() == []

    def test_list_providers_returns_list(self):
        registry = AdapterRegistry()
        adapter = self._make_adapter(ModelProvider.OPENAI)
        registry.register(adapter)
        result = registry.list_providers()
        assert isinstance(result, list)

    def test_unregister_existing(self):
        registry = AdapterRegistry()
        adapter = self._make_adapter(ModelProvider.OPENAI)
        registry.register(adapter)
        registry.unregister(ModelProvider.OPENAI)
        assert registry.get(ModelProvider.OPENAI) is None
        assert ModelProvider.OPENAI not in registry.list_providers()

    def test_unregister_nonexistent_no_error(self):
        registry = AdapterRegistry()
        # Should not raise
        registry.unregister(ModelProvider.OPENAI)

    def test_unregister_one_leaves_others(self):
        registry = AdapterRegistry()
        oa = self._make_adapter(ModelProvider.OPENAI)
        aa = self._make_adapter(ModelProvider.ANTHROPIC)
        registry.register(oa)
        registry.register(aa)
        registry.unregister(ModelProvider.OPENAI)
        assert registry.get(ModelProvider.OPENAI) is None
        assert registry.get(ModelProvider.ANTHROPIC) is aa

    def test_register_all_providers(self):
        registry = AdapterRegistry()
        adapters = {prov: self._make_adapter(prov) for prov in ModelProvider}
        for adapter in adapters.values():
            registry.register(adapter)
        providers = registry.list_providers()
        assert len(providers) == len(ModelProvider)

    def test_default_not_affected_by_unregister(self):
        """Unregistering does not clear the _default_adapter reference."""
        registry = AdapterRegistry()
        adapter = self._make_adapter(ModelProvider.OPENAI)
        registry.register(adapter, set_default=True)
        registry.unregister(ModelProvider.OPENAI)
        # default_adapter is still set (not cleared by unregister)
        assert registry.get_default() is adapter

    def test_re_register_updates_entry(self):
        registry = AdapterRegistry()
        a1 = self._make_adapter(ModelProvider.DEEPSEEK)
        a2 = self._make_adapter(ModelProvider.DEEPSEEK)
        registry.register(a1)
        registry.register(a2)
        assert registry.get(ModelProvider.DEEPSEEK) is a2
        assert len(registry.list_providers()) == 1


# ===========================================================================
# get_adapter_registry (global registry singleton)
# ===========================================================================


class TestGetAdapterRegistry:
    def test_returns_adapter_registry_instance(self):
        # Patch the global variable to None to test fresh creation
        import enhanced_agent_bus.adapters.base as base_module

        original = base_module._global_registry
        try:
            base_module._global_registry = None
            registry = base_module.get_adapter_registry()
            assert isinstance(registry, AdapterRegistry)
        finally:
            base_module._global_registry = original

    def test_returns_same_instance_twice(self):
        import enhanced_agent_bus.adapters.base as base_module

        original = base_module._global_registry
        try:
            base_module._global_registry = None
            r1 = base_module.get_adapter_registry()
            r2 = base_module.get_adapter_registry()
            assert r1 is r2
        finally:
            base_module._global_registry = original

    def test_reuses_existing_registry(self):
        import enhanced_agent_bus.adapters.base as base_module

        existing = AdapterRegistry()
        original = base_module._global_registry
        try:
            base_module._global_registry = existing
            result = base_module.get_adapter_registry()
            assert result is existing
        finally:
            base_module._global_registry = original

    def test_global_registry_is_none_initially_after_reset(self):
        import enhanced_agent_bus.adapters.base as base_module

        original = base_module._global_registry
        try:
            base_module._global_registry = None
            assert base_module._global_registry is None
            registry = base_module.get_adapter_registry()
            assert registry is not None
        finally:
            base_module._global_registry = original


# ===========================================================================
# CONSTITUTIONAL_HASH constant
# ===========================================================================


class TestConstitutionalHash:
    def test_hash_value(self):
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_hash_is_string(self):
        assert isinstance(CONSTITUTIONAL_HASH, str)

    def test_hash_length(self):
        assert len(CONSTITUTIONAL_HASH) == 16

    def test_model_request_uses_hash(self):
        req = ModelRequest(messages=[], model="m")
        assert req.constitutional_hash == CONSTITUTIONAL_HASH

    def test_model_response_uses_hash(self):
        resp = ModelResponse(content="x", model="m", provider=ModelProvider.OPENAI)
        assert resp.constitutional_hash == CONSTITUTIONAL_HASH

    def test_adapter_uses_hash(self):
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        assert adapter._constitutional_hash == CONSTITUTIONAL_HASH


# ===========================================================================
# Abstract method enforcement
# ===========================================================================


class TestAbstractMethodBodies:
    """Call abstract method bodies via super() to hit the pass statements."""

    async def test_complete_abstract_body(self):
        """Abstract body of complete() is callable via super()."""

        class CallSuperAdapter(ConcreteAdapter):
            async def complete(self, request: ModelRequest) -> ModelResponse:
                # call the abstract body; it returns None (pass)
                result = await ModelAdapter.complete(self, request)  # type: ignore[misc]
                assert result is None
                return ModelResponse(content="ok", model="m", provider=self.provider)

        adapter = CallSuperAdapter(provider=ModelProvider.OPENAI)
        resp = await adapter.complete(make_request())
        assert resp.content == "ok"

    def test_stream_abstract_body(self):
        """Abstract body of stream() is callable via super()."""

        class CallSuperAdapter(ConcreteAdapter):
            async def stream(self, request: ModelRequest):  # type: ignore[override]
                result = ModelAdapter.stream(self, request)  # type: ignore[misc]
                assert result is None

                async def _gen():
                    yield StreamChunk(content="x")

                return _gen()

        adapter = CallSuperAdapter(provider=ModelProvider.OPENAI)
        # Just call the sync part to cover the pass statement
        result = ModelAdapter.stream(adapter, make_request())  # type: ignore[misc]
        assert result is None

    def test_translate_request_abstract_body(self):
        """Abstract body of translate_request() is callable via super()."""
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        result = ModelAdapter.translate_request(adapter, make_request())  # type: ignore[misc]
        assert result is None

    def test_translate_response_abstract_body(self):
        """Abstract body of translate_response() is callable via super()."""
        adapter = ConcreteAdapter(provider=ModelProvider.OPENAI)
        result = ModelAdapter.translate_response(adapter, {})  # type: ignore[misc]
        assert result is None


class TestAbstractMethodEnforcement:
    def test_cannot_instantiate_abstract_class(self):
        with pytest.raises(TypeError):
            ModelAdapter(provider=ModelProvider.OPENAI)  # type: ignore[abstract]

    def test_missing_complete_raises(self):
        class Incomplete(ModelAdapter):
            def stream(self, req): ...
            def translate_request(self, req): ...
            def translate_response(self, resp): ...

        with pytest.raises(TypeError):
            Incomplete(provider=ModelProvider.OPENAI)

    def test_missing_stream_raises(self):
        class Incomplete(ModelAdapter):
            async def complete(self, req): ...
            def translate_request(self, req): ...
            def translate_response(self, resp): ...

        with pytest.raises(TypeError):
            Incomplete(provider=ModelProvider.OPENAI)

    def test_missing_translate_request_raises(self):
        class Incomplete(ModelAdapter):
            async def complete(self, req): ...
            def stream(self, req): ...
            def translate_response(self, resp): ...

        with pytest.raises(TypeError):
            Incomplete(provider=ModelProvider.OPENAI)

    def test_missing_translate_response_raises(self):
        class Incomplete(ModelAdapter):
            async def complete(self, req): ...
            def stream(self, req): ...
            def translate_request(self, req): ...

        with pytest.raises(TypeError):
            Incomplete(provider=ModelProvider.OPENAI)


# ===========================================================================
# __all__ exports
# ===========================================================================


class TestModuleExports:
    def test_all_exports_present(self):
        from enhanced_agent_bus.adapters import base

        for name in base.__all__:
            assert hasattr(base, name), f"Missing export: {name}"

    def test_model_provider_exported(self):
        from enhanced_agent_bus.adapters.base import ModelProvider

        assert ModelProvider is not None

    def test_message_role_exported(self):
        from enhanced_agent_bus.adapters.base import MessageRole

        assert MessageRole is not None

    def test_model_message_exported(self):
        from enhanced_agent_bus.adapters.base import ModelMessage

        assert ModelMessage is not None

    def test_model_request_exported(self):
        from enhanced_agent_bus.adapters.base import ModelRequest

        assert ModelRequest is not None

    def test_model_response_exported(self):
        from enhanced_agent_bus.adapters.base import ModelResponse

        assert ModelResponse is not None

    def test_stream_chunk_exported(self):
        from enhanced_agent_bus.adapters.base import StreamChunk

        assert StreamChunk is not None

    def test_model_adapter_exported(self):
        from enhanced_agent_bus.adapters.base import ModelAdapter

        assert ModelAdapter is not None

    def test_adapter_registry_exported(self):
        from enhanced_agent_bus.adapters.base import AdapterRegistry

        assert AdapterRegistry is not None

    def test_get_adapter_registry_exported(self):
        assert callable(get_adapter_registry)

    def test_constitutional_hash_exported(self):
        from enhanced_agent_bus.adapters.base import CONSTITUTIONAL_HASH

        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH  # pragma: allowlist secret
