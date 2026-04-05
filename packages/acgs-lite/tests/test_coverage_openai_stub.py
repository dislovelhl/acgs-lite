"""Tests for acgs_lite.integrations.openai re-export stub."""

from __future__ import annotations


def test_openai_re_exports() -> None:
    from acgs_lite.integrations.openai import (
        GovernedChat,
        GovernedChatCompletions,
        GovernedOpenAI,
    )

    assert GovernedOpenAI is not None
    assert GovernedChat is not None
    assert GovernedChatCompletions is not None


def test_openai_all() -> None:
    import acgs_lite.integrations.openai as mod

    assert "GovernedOpenAI" in mod.__all__
    assert "GovernedChat" in mod.__all__
    assert "GovernedChatCompletions" in mod.__all__
