# Constitutional Hash: 608508a9bd224290
"""
Tests for src/core/enhanced_agent_bus/llm_adapters/base.py
Target: >=90% coverage
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.resilience.retry import RetryConfig as SharedRetryConfig
from enhanced_agent_bus.llm_adapters.base import (
    LEGACY_RATE_LIMIT_ERRORS,
    LEGACY_SERVER_ERRORS,
    LEGACY_TIMEOUT_ERRORS,
    RETRY_EXECUTION_ERRORS,
    AdapterStatus,
    BaseLLMAdapter,
    CompletionMetadata,
    CostEstimate,
    HealthCheckResult,
    LLMMessage,
    LLMResponse,
    LLMRetryConfig,
    RetryConfig,
    StreamingMode,
    TokenUsage,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

# ---------------------------------------------------------------------------
# Concrete adapter for testing abstract base class
# ---------------------------------------------------------------------------


class ConcreteAdapter(BaseLLMAdapter):
    """Minimal concrete implementation for testing BaseLLMAdapter."""

    def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float = 1.0,
        stop: list[str] | None = None,
        **kwargs: object,
    ) -> LLMResponse:
        return self._make_response("sync")

    async def acomplete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float = 1.0,
        stop: list[str] | None = None,
        **kwargs: object,
    ) -> LLMResponse:
        return self._make_response("async")

    def stream(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float = 1.0,
        stop: list[str] | None = None,
        **kwargs: object,
    ) -> Iterator[str]:
        yield "token"

    def astream(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float = 1.0,
        stop: list[str] | None = None,
        **kwargs: object,
    ) -> AsyncIterator[str]:
        async def _gen() -> AsyncIterator[str]:
            yield "async-token"

        return _gen()

    def count_tokens(self, messages: list[LLMMessage]) -> int:
        return sum(len(m.content.split()) for m in messages)

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> CostEstimate:
        return CostEstimate(
            prompt_cost_usd=prompt_tokens * 0.001,
            completion_cost_usd=completion_tokens * 0.002,
            total_cost_usd=prompt_tokens * 0.001 + completion_tokens * 0.002,
        )

    async def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(status=AdapterStatus.HEALTHY, latency_ms=1.0)

    def validate_constitutional_compliance(self, **kwargs: object) -> None:
        pass  # No-op for test stub

    def _make_response(self, tag: str) -> LLMResponse:
        meta = CompletionMetadata(model=self.model, provider="test")
        return LLMResponse(content=f"response-{tag}", metadata=meta)


# ---------------------------------------------------------------------------
# Module-level constant tests
# ---------------------------------------------------------------------------


class TestModuleLevelConstants:
    def test_retry_execution_errors_tuple(self):
        assert RuntimeError in RETRY_EXECUTION_ERRORS
        assert ValueError in RETRY_EXECUTION_ERRORS
        assert asyncio.TimeoutError in RETRY_EXECUTION_ERRORS
        assert ConnectionError in RETRY_EXECUTION_ERRORS

    def test_legacy_timeout_errors(self):
        assert TimeoutError in LEGACY_TIMEOUT_ERRORS
        assert asyncio.TimeoutError in LEGACY_TIMEOUT_ERRORS

    def test_legacy_rate_limit_errors(self):
        assert RuntimeError in LEGACY_RATE_LIMIT_ERRORS

    def test_legacy_server_errors(self):
        assert ConnectionError in LEGACY_SERVER_ERRORS
        assert OSError in LEGACY_SERVER_ERRORS

    def test_retry_config_alias(self):
        """RetryConfig is an alias for LLMRetryConfig."""
        assert RetryConfig is LLMRetryConfig


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestStreamingMode:
    def test_values(self):
        assert StreamingMode.NONE.value == "none"
        assert StreamingMode.SUPPORTED.value == "supported"
        assert StreamingMode.REQUIRED.value == "required"

    def test_membership(self):
        modes = list(StreamingMode)
        assert len(modes) == 3


class TestAdapterStatus:
    def test_values(self):
        assert AdapterStatus.HEALTHY.value == "healthy"
        assert AdapterStatus.DEGRADED.value == "degraded"
        assert AdapterStatus.UNHEALTHY.value == "unhealthy"
        assert AdapterStatus.UNAVAILABLE.value == "unavailable"


# ---------------------------------------------------------------------------
# TokenUsage tests
# ---------------------------------------------------------------------------


class TestTokenUsage:
    def test_defaults(self):
        tu = TokenUsage()
        assert tu.prompt_tokens == 0
        assert tu.completion_tokens == 0
        assert tu.total_tokens == 0
        assert tu.constitutional_hash == CONSTITUTIONAL_HASH

    def test_tokens_property(self):
        tu = TokenUsage(total_tokens=42)
        assert tu.tokens == 42

    def test_to_dict(self):
        tu = TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        d = tu.to_dict()
        assert d["prompt_tokens"] == 10
        assert d["completion_tokens"] == 20
        assert d["total_tokens"] == 30
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_custom_values(self):
        tu = TokenUsage(prompt_tokens=5, completion_tokens=10, total_tokens=15)
        assert tu.tokens == 15


# ---------------------------------------------------------------------------
# CostEstimate tests
# ---------------------------------------------------------------------------


class TestCostEstimate:
    def test_defaults(self):
        ce = CostEstimate()
        assert ce.prompt_cost_usd == 0.0
        assert ce.total_cost_usd == 0.0
        assert ce.currency == "USD"
        assert ce.pricing_model == "unknown"
        assert ce.constitutional_hash == CONSTITUTIONAL_HASH

    def test_to_dict(self):
        ce = CostEstimate(
            prompt_cost_usd=0.01,
            completion_cost_usd=0.02,
            total_cost_usd=0.03,
            currency="USD",
            pricing_model="gpt-4",
        )
        d = ce.to_dict()
        assert d["prompt_cost_usd"] == 0.01
        assert d["completion_cost_usd"] == 0.02
        assert d["total_cost_usd"] == 0.03
        assert d["currency"] == "USD"
        assert d["pricing_model"] == "gpt-4"
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# CompletionMetadata tests
# ---------------------------------------------------------------------------


class TestCompletionMetadata:
    def test_minimal(self):
        meta = CompletionMetadata(model="gpt-4", provider="openai")
        assert meta.model == "gpt-4"
        assert meta.provider == "openai"
        assert meta.request_id == ""
        assert meta.finish_reason == "stop"
        assert meta.constitutional_hash == CONSTITUTIONAL_HASH
        assert isinstance(meta.timestamp, datetime)

    def test_to_dict(self):
        meta = CompletionMetadata(
            model="claude-3",
            provider="anthropic",
            request_id="req-123",
            latency_ms=50.0,
            finish_reason="length",
            extra={"key": "value"},
        )
        d = meta.to_dict()
        assert d["model"] == "claude-3"
        assert d["provider"] == "anthropic"
        assert d["request_id"] == "req-123"
        assert d["latency_ms"] == 50.0
        assert d["finish_reason"] == "length"
        assert d["extra"] == {"key": "value"}
        assert "timestamp" in d
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_timestamp_is_utc(self):
        meta = CompletionMetadata(model="m", provider="p")
        assert meta.timestamp.tzinfo is not None


# ---------------------------------------------------------------------------
# LLMMessage tests
# ---------------------------------------------------------------------------


class TestLLMMessage:
    def test_basic(self):
        msg = LLMMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.name is None
        assert msg.function_call is None
        assert msg.tool_calls is None
        assert msg.tool_call_id is None

    def test_with_optional_fields(self):
        msg = LLMMessage(
            role="assistant",
            content="Hi",
            name="bot",
            function_call={"name": "fn"},
            tool_calls=[{"id": "t1"}],
            tool_call_id="tc-1",
        )
        assert msg.name == "bot"
        assert msg.function_call == {"name": "fn"}
        assert msg.tool_calls == [{"id": "t1"}]
        assert msg.tool_call_id == "tc-1"

    def test_model_dump(self):
        msg = LLMMessage(role="system", content="You are helpful")
        d = msg.model_dump()
        assert d["role"] == "system"
        assert d["content"] == "You are helpful"


# ---------------------------------------------------------------------------
# LLMResponse tests
# ---------------------------------------------------------------------------


class TestLLMResponse:
    def _make_meta(self) -> CompletionMetadata:
        return CompletionMetadata(model="test-model", provider="test")

    def test_minimal(self):
        resp = LLMResponse(content="hi", metadata=self._make_meta())
        assert resp.content == "hi"
        assert resp.constitutional_hash == CONSTITUTIONAL_HASH
        assert isinstance(resp.usage, TokenUsage)
        assert isinstance(resp.cost, CostEstimate)
        assert resp.tool_calls is None
        assert resp.raw_response is None

    def test_to_dict(self):
        meta = self._make_meta()
        usage = TokenUsage(prompt_tokens=5, completion_tokens=10, total_tokens=15)
        cost = CostEstimate(total_cost_usd=0.05)
        msg = LLMMessage(role="user", content="q")
        resp = LLMResponse(
            content="answer",
            messages=[msg],
            usage=usage,
            cost=cost,
            metadata=meta,
            tool_calls=[{"id": "tc"}],
        )
        d = resp.to_dict()
        assert d["content"] == "answer"
        assert len(d["messages"]) == 1
        assert d["usage"]["total_tokens"] == 15
        assert d["cost"]["total_cost_usd"] == 0.05
        assert d["tool_calls"] == [{"id": "tc"}]
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_with_raw_response(self):
        meta = self._make_meta()
        resp = LLMResponse(content="x", metadata=meta, raw_response={"raw": True})
        assert resp.raw_response == {"raw": True}


# ---------------------------------------------------------------------------
# LLMRetryConfig tests
# ---------------------------------------------------------------------------


class TestLLMRetryConfig:
    def test_defaults(self):
        rc = LLMRetryConfig()
        assert rc.max_retries == 3
        assert rc.initial_delay_ms == 1000.0
        assert rc.max_delay_ms == 60000.0
        assert rc.exponential_base == 2.0
        assert rc.jitter is True
        assert rc.retry_on_timeout is True
        assert rc.retry_on_rate_limit is True
        assert rc.retry_on_server_error is True
        assert rc.constitutional_hash == CONSTITUTIONAL_HASH

    def test_to_shared_retry_config_defaults(self):
        rc = LLMRetryConfig()
        shared = rc.to_shared_retry_config()
        assert isinstance(shared, SharedRetryConfig)
        assert shared.max_retries == 3
        assert shared.base_delay == pytest.approx(1.0)
        assert shared.max_delay == pytest.approx(60.0)
        assert shared.multiplier == pytest.approx(2.0)
        assert shared.jitter is True
        assert shared.raise_on_exhausted is False

    def test_to_shared_retry_config_no_timeout(self):
        rc = LLMRetryConfig(retry_on_timeout=False)
        shared = rc.to_shared_retry_config()
        # TimeoutError and asyncio.TimeoutError should NOT be in retryable
        assert TimeoutError not in shared.retryable_exceptions
        assert asyncio.TimeoutError not in shared.retryable_exceptions

    def test_to_shared_retry_config_no_rate_limit(self):
        rc = LLMRetryConfig(retry_on_rate_limit=False)
        shared = rc.to_shared_retry_config()
        # LEGACY_RATE_LIMIT_ERRORS should not be added
        # (RuntimeError still in base list)
        assert isinstance(shared, SharedRetryConfig)

    def test_to_shared_retry_config_no_server_error(self):
        rc = LLMRetryConfig(retry_on_server_error=False)
        shared = rc.to_shared_retry_config()
        assert ConnectionError not in shared.retryable_exceptions
        assert OSError not in shared.retryable_exceptions

    def test_to_shared_retry_config_all_disabled(self):
        rc = LLMRetryConfig(
            retry_on_timeout=False,
            retry_on_rate_limit=False,
            retry_on_server_error=False,
        )
        shared = rc.to_shared_retry_config()
        assert isinstance(shared, SharedRetryConfig)
        # Only base errors remain
        assert RuntimeError in shared.retryable_exceptions

    def test_deduplication(self):
        """Errors that appear in multiple lists must be deduplicated."""
        rc = LLMRetryConfig(
            retry_on_timeout=True,
            retry_on_rate_limit=True,
            retry_on_server_error=True,
        )
        shared = rc.to_shared_retry_config()
        # Count occurrences - must be unique
        exc_list = list(shared.retryable_exceptions)
        assert len(exc_list) == len(set(exc_list))

    def test_custom_delays(self):
        rc = LLMRetryConfig(initial_delay_ms=500.0, max_delay_ms=5000.0)
        shared = rc.to_shared_retry_config()
        assert shared.base_delay == pytest.approx(0.5)
        assert shared.max_delay == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# HealthCheckResult tests
# ---------------------------------------------------------------------------


class TestHealthCheckResult:
    def test_minimal(self):
        hcr = HealthCheckResult(status=AdapterStatus.HEALTHY)
        assert hcr.status == AdapterStatus.HEALTHY
        assert hcr.latency_ms == 0.0
        assert hcr.message == ""
        assert hcr.constitutional_hash == CONSTITUTIONAL_HASH
        assert isinstance(hcr.timestamp, datetime)

    def test_to_dict(self):
        hcr = HealthCheckResult(
            status=AdapterStatus.DEGRADED,
            latency_ms=15.5,
            message="partial",
            details={"key": "val"},
        )
        d = hcr.to_dict()
        assert d["status"] == "degraded"
        assert d["latency_ms"] == 15.5
        assert d["message"] == "partial"
        assert d["details"] == {"key": "val"}
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "timestamp" in d

    def test_all_statuses_in_to_dict(self):
        for status in AdapterStatus:
            hcr = HealthCheckResult(status=status)
            d = hcr.to_dict()
            assert d["status"] == status.value


# ---------------------------------------------------------------------------
# BaseLLMAdapter __init__ and helpers
# ---------------------------------------------------------------------------


class TestBaseLLMAdapterInit:
    def test_basic_init(self):
        adapter = ConcreteAdapter(model="test-model")
        assert adapter.model == "test-model"
        assert adapter.api_key is None
        assert adapter.constitutional_hash == CONSTITUTIONAL_HASH
        assert isinstance(adapter.retry_config, SharedRetryConfig)

    def test_init_with_api_key(self):
        adapter = ConcreteAdapter(model="m", api_key="sk-test")
        assert adapter.api_key == "sk-test"

    def test_init_with_llm_retry_config(self):
        rc = LLMRetryConfig(max_retries=5)
        adapter = ConcreteAdapter(model="m", retry_config=rc)
        assert adapter.retry_config.max_retries == 5

    def test_init_with_shared_retry_config(self):
        src = SharedRetryConfig(max_retries=7)
        adapter = ConcreteAdapter(model="m", retry_config=src)
        assert adapter.retry_config.max_retries == 7

    def test_init_with_none_retry_config(self):
        adapter = ConcreteAdapter(model="m", retry_config=None)
        assert isinstance(adapter.retry_config, SharedRetryConfig)

    def test_init_unsupported_retry_config_type(self):
        with pytest.raises(TypeError, match="Unsupported retry config type"):
            ConcreteAdapter(model="m", retry_config="bad-type")  # type: ignore[arg-type]

    def test_init_with_extra_kwargs(self):
        adapter = ConcreteAdapter(model="m", timeout=30, base_url="http://localhost")
        assert adapter.config["timeout"] == 30
        assert adapter.config["base_url"] == "http://localhost"

    def test_non_standard_constitutional_hash_logs_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            adapter = ConcreteAdapter(model="m", constitutional_hash="deadbeef")
        assert adapter.constitutional_hash == "deadbeef"
        assert any("non-standard" in r.message for r in caplog.records)

    def test_standard_constitutional_hash_no_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            ConcreteAdapter(model="m", constitutional_hash=CONSTITUTIONAL_HASH)
        assert not any("non-standard" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# BaseLLMAdapter optional methods
# ---------------------------------------------------------------------------


class TestBaseLLMAdapterOptionalMethods:
    def setup_method(self):
        self.adapter = ConcreteAdapter(model="test-model")

    def test_get_streaming_mode_default(self):
        assert self.adapter.get_streaming_mode() == StreamingMode.SUPPORTED

    def test_get_provider_name(self):
        name = self.adapter.get_provider_name()
        # ConcreteAdapter → "concrete" (removes trailing "adapter" from lowercase)
        assert "adapter" not in name
        assert name == "concrete"

    def test_validate_messages_empty_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            self.adapter.validate_messages([])

    def test_validate_messages_invalid_role(self):
        msg = LLMMessage(role="badRole", content="hi")
        with pytest.raises(ValueError, match="Invalid role"):
            self.adapter.validate_messages([msg])

    def test_validate_messages_first_is_assistant_raises(self):
        msg = LLMMessage(role="assistant", content="hi")
        with pytest.raises(ValueError, match="First message cannot be from assistant"):
            self.adapter.validate_messages([msg])

    def test_validate_messages_valid(self):
        msgs = [
            LLMMessage(role="system", content="sys"),
            LLMMessage(role="user", content="hello"),
            LLMMessage(role="assistant", content="hi"),
        ]
        # Should not raise
        self.adapter.validate_messages(msgs)

    def test_validate_messages_all_valid_roles(self):
        valid_roles = ["system", "user", "function", "tool"]
        for role in valid_roles:
            msgs = [LLMMessage(role=role, content="content")]
            self.adapter.validate_messages(msgs)

    def test_validate_constitutional_compliance_no_op(self):
        # Base implementation is a no-op; should not raise
        self.adapter.validate_constitutional_compliance(temperature=0.7, model="gpt-4")

    def test_repr(self):
        r = repr(self.adapter)
        assert "ConcreteAdapter" in r
        assert "test-model" in r
        assert "concrete" in r
        # Only first 8 chars of constitutional hash shown
        assert CONSTITUTIONAL_HASH[:8] in r

    def test_complete_returns_response(self):
        msgs = [LLMMessage(role="user", content="hi")]
        resp = self.adapter.complete(msgs)
        assert isinstance(resp, LLMResponse)
        assert resp.content == "response-sync"

    async def test_acomplete_returns_response(self):
        msgs = [LLMMessage(role="user", content="hi")]
        resp = await self.adapter.acomplete(msgs)
        assert isinstance(resp, LLMResponse)
        assert resp.content == "response-async"

    def test_stream_yields_tokens(self):
        msgs = [LLMMessage(role="user", content="hi")]
        tokens = list(self.adapter.stream(msgs))
        assert tokens == ["token"]

    async def test_astream_yields_tokens(self):
        msgs = [LLMMessage(role="user", content="hi")]
        tokens = [t async for t in self.adapter.astream(msgs)]
        assert tokens == ["async-token"]

    def test_count_tokens(self):
        msgs = [LLMMessage(role="user", content="hello world")]
        count = self.adapter.count_tokens(msgs)
        assert count == 2

    def test_estimate_cost(self):
        ce = self.adapter.estimate_cost(100, 50)
        assert isinstance(ce, CostEstimate)
        assert ce.prompt_cost_usd == pytest.approx(0.1)
        assert ce.completion_cost_usd == pytest.approx(0.1)

    async def test_health_check(self):
        result = await self.adapter.health_check()
        assert result.status == AdapterStatus.HEALTHY


# ---------------------------------------------------------------------------
# retry_with_backoff tests
# ---------------------------------------------------------------------------


class TestRetryWithBackoff:
    def setup_method(self):
        self.adapter = ConcreteAdapter(model="m")

    async def test_async_func_success(self):
        async def async_fn(x: int) -> int:
            return x * 2

        result = await self.adapter.retry_with_backoff(async_fn, 5)
        assert result == 10

    async def test_sync_func_success(self):
        def sync_fn(x: int) -> int:
            return x + 1

        result = await self.adapter.retry_with_backoff(sync_fn, 9)
        assert result == 10

    async def test_async_func_with_kwargs(self):
        async def async_fn(a: int, b: int = 0) -> int:
            return a + b

        result = await self.adapter.retry_with_backoff(async_fn, 3, b=7)
        assert result == 10

    async def test_sync_func_with_kwargs(self):
        def sync_fn(a: int, b: int = 0) -> int:
            return a + b

        result = await self.adapter.retry_with_backoff(sync_fn, 3, b=7)
        assert result == 10

    async def test_retries_on_retryable_exception(self):
        """Verify the function is retried when a retryable exception occurs."""
        call_count = 0

        async def flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("transient")
            return "ok"

        # RetryConfig with max_retries=3 so one retry is fine
        adapter = ConcreteAdapter(model="m", retry_config=LLMRetryConfig(max_retries=3))
        result = await adapter.retry_with_backoff(flaky)
        assert result == "ok"
        assert call_count == 2


# ---------------------------------------------------------------------------
# _to_shared_retry_config edge cases
# ---------------------------------------------------------------------------


class TestToSharedRetryConfig:
    def test_unsupported_type_raises_type_error(self):
        adapter = ConcreteAdapter.__new__(ConcreteAdapter)
        adapter.model = "m"
        adapter.api_key = None
        adapter.constitutional_hash = CONSTITUTIONAL_HASH
        adapter.config = {}
        with pytest.raises(TypeError, match="Unsupported retry config type"):
            adapter._to_shared_retry_config(42)  # type: ignore[arg-type]

    def test_none_returns_default_shared(self):
        adapter = ConcreteAdapter.__new__(ConcreteAdapter)
        result = adapter._to_shared_retry_config(None)
        assert isinstance(result, SharedRetryConfig)

    def test_llm_retry_config_converted(self):
        adapter = ConcreteAdapter.__new__(ConcreteAdapter)
        rc = LLMRetryConfig(max_retries=2)
        result = adapter._to_shared_retry_config(rc)
        assert isinstance(result, SharedRetryConfig)
        assert result.max_retries == 2

    def test_shared_retry_config_passed_through(self):
        adapter = ConcreteAdapter.__new__(ConcreteAdapter)
        src = SharedRetryConfig(max_retries=9)
        result = adapter._to_shared_retry_config(src)
        assert result is src


# ---------------------------------------------------------------------------
# Provider name edge cases
# ---------------------------------------------------------------------------


class TestGetProviderName:
    def test_name_strips_adapter_suffix(self):
        class OpenAIAdapter(BaseLLMAdapter):
            def complete(self, *a, **kw):
                pass

            async def acomplete(self, *a, **kw):
                pass

            def stream(self, *a, **kw):
                pass

            def astream(self, *a, **kw):
                pass

            def count_tokens(self, *a, **kw):
                return 0

            def estimate_cost(self, *a, **kw):
                return CostEstimate()

            async def health_check(self):
                return HealthCheckResult(status=AdapterStatus.HEALTHY)

            def validate_constitutional_compliance(self, **kwargs: object) -> None:
                pass  # No-op for test stub

        a = OpenAIAdapter(model="x")
        assert a.get_provider_name() == "openai"

    def test_name_no_adapter_suffix(self):
        class GroqLLM(BaseLLMAdapter):
            def complete(self, *a, **kw):
                pass

            async def acomplete(self, *a, **kw):
                pass

            def stream(self, *a, **kw):
                pass

            def astream(self, *a, **kw):
                pass

            def count_tokens(self, *a, **kw):
                return 0

            def estimate_cost(self, *a, **kw):
                return CostEstimate()

            async def health_check(self):
                return HealthCheckResult(status=AdapterStatus.HEALTHY)

            def validate_constitutional_compliance(self, **kwargs: object) -> None:
                pass  # No-op for test stub

        a = GroqLLM(model="x")
        # No trailing "adapter" substring, name is the full lowercased class name
        assert a.get_provider_name() == "groqllm"


# ---------------------------------------------------------------------------
# validate_messages comprehensive role coverage
# ---------------------------------------------------------------------------


class TestValidateMessagesRoles:
    def setup_method(self):
        self.adapter = ConcreteAdapter(model="m")

    def test_user_first_valid(self):
        self.adapter.validate_messages([LLMMessage(role="user", content="hi")])

    def test_system_first_valid(self):
        self.adapter.validate_messages([LLMMessage(role="system", content="sys")])

    def test_function_first_valid(self):
        self.adapter.validate_messages([LLMMessage(role="function", content="fn")])

    def test_tool_first_valid(self):
        self.adapter.validate_messages([LLMMessage(role="tool", content="tool")])

    def test_multi_message_conversation(self):
        msgs = [
            LLMMessage(role="user", content="a"),
            LLMMessage(role="assistant", content="b"),
            LLMMessage(role="user", content="c"),
        ]
        self.adapter.validate_messages(msgs)

    def test_invalid_role_in_middle(self):
        msgs = [
            LLMMessage(role="user", content="a"),
            LLMMessage(role="invalid", content="b"),
        ]
        with pytest.raises(ValueError, match="Invalid role"):
            self.adapter.validate_messages(msgs)


# ---------------------------------------------------------------------------
# __all__ exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_all_exported(self):
        from enhanced_agent_bus.llm_adapters import base as base_mod

        for name in base_mod.__all__:
            assert hasattr(base_mod, name), f"Missing export: {name}"

    def test_expected_names_in_all(self):
        from enhanced_agent_bus.llm_adapters import base as base_mod

        expected = {
            "StreamingMode",
            "AdapterStatus",
            "TokenUsage",
            "CostEstimate",
            "CompletionMetadata",
            "RetryConfig",
            "HealthCheckResult",
            "LLMMessage",
            "LLMResponse",
            "BaseLLMAdapter",
        }
        actual = set(base_mod.__all__)
        assert expected.issubset(actual)
