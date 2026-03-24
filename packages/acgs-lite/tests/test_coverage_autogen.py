"""Tests for acgs_lite.integrations.autogen coverage gaps."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from acgs_lite.integrations.autogen import (
    GovernedModelClient,
    _extract_message_text,
    _extract_result_text,
)

# --- Helper extraction functions ---


class TestExtractMessageText:
    def test_empty_messages(self) -> None:
        assert _extract_message_text([]) == ""

    def test_string_content(self) -> None:
        msg = SimpleNamespace(content="hello world")
        assert _extract_message_text([msg]) == "hello world"

    def test_list_content_strings(self) -> None:
        msg = SimpleNamespace(content=["part1", "part2"])
        assert _extract_message_text([msg]) == "part1 part2"

    def test_list_content_with_text_attr(self) -> None:
        part = SimpleNamespace(text="structured")
        msg = SimpleNamespace(content=[part])
        assert _extract_message_text([msg]) == "structured"

    def test_no_content_attr(self) -> None:
        msg = {"key": "value"}
        assert _extract_message_text([msg]) == ""

    def test_multiple_messages(self) -> None:
        m1 = SimpleNamespace(content="hello")
        m2 = SimpleNamespace(content="world")
        assert _extract_message_text([m1, m2]) == "hello world"


class TestExtractResultText:
    def test_string_content(self) -> None:
        result = SimpleNamespace(content="response")
        assert _extract_result_text(result) == "response"

    def test_list_content_strings(self) -> None:
        result = SimpleNamespace(content=["a", "b"])
        assert _extract_result_text(result) == "a b"

    def test_list_content_with_text_attr(self) -> None:
        part = SimpleNamespace(text="rich")
        result = SimpleNamespace(content=[part])
        assert _extract_result_text(result) == "rich"

    def test_no_content(self) -> None:
        result = SimpleNamespace(other="x")
        assert _extract_result_text(result) == ""

    def test_mixed_list_content(self) -> None:
        part = SimpleNamespace(text="obj")
        result = SimpleNamespace(content=["str", part])
        assert _extract_result_text(result) == "str obj"


# --- GovernedModelClient ---


class MockClient:
    """Fake AG2 client for testing."""

    def __init__(self, response_content: str = "ok") -> None:
        self._response = SimpleNamespace(content=response_content)
        self.model_info = {"model": "test"}
        self.capabilities = {"streaming": True}

    async def create(self, messages: Any, **kwargs: Any) -> Any:
        return self._response

    async def create_stream(self, messages: Any, **kwargs: Any) -> Any:
        yield self._response

    def actual_usage(self) -> SimpleNamespace:
        return SimpleNamespace(prompt_tokens=10, completion_tokens=5)

    def total_usage(self) -> SimpleNamespace:
        return SimpleNamespace(prompt_tokens=20, completion_tokens=10)

    def count_tokens(self, messages: Any, *, tools: Any = ()) -> int:
        return 42

    def remaining_tokens(self, messages: Any, *, tools: Any = ()) -> int:
        return 100


class TestGovernedModelClient:
    def _make_client(self, **kwargs: Any) -> GovernedModelClient:
        return GovernedModelClient(MockClient(), **kwargs)

    def test_init_default(self) -> None:
        client = self._make_client()
        assert client.agent_id == "autogen-agent"

    def test_init_custom_agent_id(self) -> None:
        client = self._make_client(agent_id="my-agent")
        assert client.agent_id == "my-agent"

    @pytest.mark.asyncio
    async def test_create_validates_input(self) -> None:
        client = self._make_client(strict=False)
        msg = SimpleNamespace(content="test action")
        result = await client.create([msg])
        assert result.content == "ok"

    @pytest.mark.asyncio
    async def test_create_empty_messages(self) -> None:
        client = self._make_client(strict=False)
        result = await client.create([])
        assert result.content == "ok"

    @pytest.mark.asyncio
    async def test_create_stream(self) -> None:
        client = self._make_client(strict=False)
        msg = SimpleNamespace(content="stream test")
        chunks = []
        async for chunk in client.create_stream([msg]):
            chunks.append(chunk)
        assert len(chunks) == 1

    def test_actual_usage_delegates(self) -> None:
        client = self._make_client()
        usage = client.actual_usage()
        assert usage is not None
        assert usage.prompt_tokens == 10

    def test_total_usage_delegates(self) -> None:
        client = self._make_client()
        usage = client.total_usage()
        assert usage is not None
        assert usage.prompt_tokens == 20

    def test_actual_usage_none_when_missing(self) -> None:
        bare = SimpleNamespace(model_info={})
        client = GovernedModelClient(bare)
        assert client.actual_usage() is None

    def test_total_usage_none_when_missing(self) -> None:
        bare = SimpleNamespace(model_info={})
        client = GovernedModelClient(bare)
        assert client.total_usage() is None

    def test_model_info(self) -> None:
        client = self._make_client()
        assert client.model_info == {"model": "test"}

    def test_capabilities(self) -> None:
        client = self._make_client()
        assert client.capabilities == {"streaming": True}

    def test_capabilities_none_when_missing(self) -> None:
        bare = SimpleNamespace(model_info={})
        client = GovernedModelClient(bare)
        assert client.capabilities is None

    def test_count_tokens(self) -> None:
        client = self._make_client()
        assert client.count_tokens([]) == 42

    def test_count_tokens_zero_when_missing(self) -> None:
        bare = SimpleNamespace(model_info={})
        client = GovernedModelClient(bare)
        assert client.count_tokens([]) == 0

    def test_remaining_tokens(self) -> None:
        client = self._make_client()
        assert client.remaining_tokens([]) == 100

    def test_remaining_tokens_zero_when_missing(self) -> None:
        bare = SimpleNamespace(model_info={})
        client = GovernedModelClient(bare)
        assert client.remaining_tokens([]) == 0

    def test_stats(self) -> None:
        client = self._make_client()
        stats = client.stats
        assert "agent_id" in stats
        assert stats["agent_id"] == "autogen-agent"
        assert "audit_chain_valid" in stats
