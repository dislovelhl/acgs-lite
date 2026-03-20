"""Tests for acgs_lite.integrations.llamaindex coverage gaps."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from acgs_lite.integrations.llamaindex import (
    GovernedChatEngine,
    GovernedQueryEngine,
    _extract_response_text,
)


class TestExtractResponseText:
    def test_string_input(self) -> None:
        assert _extract_response_text("hello") == "hello"

    def test_response_attr(self) -> None:
        obj = SimpleNamespace(response="from response attr")
        assert _extract_response_text(obj) == "from response attr"

    def test_text_attr(self) -> None:
        obj = SimpleNamespace(text="from text attr")
        assert _extract_response_text(obj) == "from text attr"

    def test_fallback_to_str(self) -> None:
        assert _extract_response_text(42) == "42"


class FakeQueryEngine:
    def query(self, query_str: str, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(response=f"answer: {query_str}")

    async def aquery(self, query_str: str, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(response=f"async answer: {query_str}")


class FakeChatEngine:
    def __init__(self) -> None:
        self._history: list[str] = []

    def chat(self, message: str, **kwargs: Any) -> SimpleNamespace:
        self._history.append(message)
        return SimpleNamespace(response=f"chat: {message}")

    async def achat(self, message: str, **kwargs: Any) -> SimpleNamespace:
        self._history.append(message)
        return SimpleNamespace(response=f"async chat: {message}")

    def stream_chat(self, message: str, **kwargs: Any) -> str:
        return f"stream: {message}"

    def reset(self) -> None:
        self._history.clear()

    @property
    def chat_history(self) -> list[str]:
        return self._history


class TestGovernedQueryEngine:
    def _make(self, **kwargs: Any) -> GovernedQueryEngine:
        return GovernedQueryEngine(FakeQueryEngine(), **kwargs)

    def test_query(self) -> None:
        engine = self._make(strict=False)
        result = engine.query("test query")
        assert result.response == "answer: test query"

    @pytest.mark.asyncio
    async def test_aquery(self) -> None:
        engine = self._make(strict=False)
        result = await engine.aquery("async q")
        assert result.response == "async answer: async q"

    def test_stats(self) -> None:
        engine = self._make()
        stats = engine.stats
        assert stats["agent_id"] == "llamaindex-query"
        assert "audit_chain_valid" in stats

    def test_custom_agent_id(self) -> None:
        engine = self._make(agent_id="custom")
        assert engine.agent_id == "custom"


class TestGovernedChatEngine:
    def _make(self, **kwargs: Any) -> GovernedChatEngine:
        return GovernedChatEngine(FakeChatEngine(), **kwargs)

    def test_chat(self) -> None:
        engine = self._make(strict=False)
        result = engine.chat("hello")
        assert result.response == "chat: hello"

    @pytest.mark.asyncio
    async def test_achat(self) -> None:
        engine = self._make(strict=False)
        result = await engine.achat("async hello")
        assert result.response == "async chat: async hello"

    def test_stream_chat(self) -> None:
        engine = self._make(strict=False)
        result = engine.stream_chat("stream msg")
        assert result == "stream: stream msg"

    def test_reset(self) -> None:
        engine = self._make(strict=False)
        engine.chat("msg1")
        engine.reset()
        assert engine.chat_history == []

    def test_chat_history(self) -> None:
        engine = self._make(strict=False)
        engine.chat("msg1")
        engine.chat("msg2")
        assert len(engine.chat_history) == 2

    def test_chat_history_empty_when_missing(self) -> None:
        bare = SimpleNamespace()
        engine = GovernedChatEngine(bare)
        assert engine.chat_history == []

    def test_stats(self) -> None:
        engine = self._make()
        stats = engine.stats
        assert stats["agent_id"] == "llamaindex-chat"
