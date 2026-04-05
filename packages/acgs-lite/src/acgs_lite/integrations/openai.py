"""ACGS-Lite OpenAI Integration.

Wraps OpenAI's ChatCompletion API with constitutional governance.
Every prompt is validated before sending. Every response is validated before returning.

Usage::

    from acgs_lite.integrations.openai import GovernedOpenAI

    client = GovernedOpenAI(api_key="sk-...")
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": "Hello!"}],
    )

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import logging
from typing import Any

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine
from acgs_lite.errors import ConstitutionalViolationError  # noqa: F401

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
    from openai.types.chat import ChatCompletion

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = object  # type: ignore[assignment,misc]
    ChatCompletion = object  # type: ignore[assignment,misc]

__all__ = ["GovernedChat", "GovernedChatCompletions", "GovernedOpenAI"]


class GovernedChatCompletions:
    """Governed wrapper around OpenAI's chat.completions API."""

    def __init__(
        self,
        client: Any,  # OpenAI client
        engine: GovernanceEngine,
        agent_id: str,
    ) -> None:
        self._client = client
        self._engine = engine
        self._agent_id = agent_id

    def create(self, **kwargs: Any) -> Any:
        """Create a chat completion with governance.

        Validates the last user message before sending.
        Validates the response content before returning.
        """
        messages = kwargs.get("messages", [])

        # Validate input: check the last user message
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    self._engine.validate(content, agent_id=self._agent_id)
                break

        # Call OpenAI
        response = self._client.chat.completions.create(**kwargs)

        # Validate output
        if hasattr(response, "choices") and response.choices:
            for choice in response.choices:
                if hasattr(choice, "message") and choice.message.content:
                    # Use non-strict for output (don't block, just log)
                    old_strict = self._engine.strict
                    self._engine.strict = False
                    result = self._engine.validate(
                        choice.message.content,
                        agent_id=f"{self._agent_id}:output",
                    )
                    self._engine.strict = old_strict

                    if not result.valid:
                        logger.warning(
                            "OpenAI response triggered governance violations: %s",
                            [v.rule_id for v in result.violations],
                        )

        return response

    async def acreate(self, **kwargs: Any) -> Any:
        """Async version of create()."""
        messages = kwargs.get("messages", [])

        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    self._engine.validate(content, agent_id=self._agent_id)
                break

        try:
            from openai import AsyncOpenAI  # noqa: F401
        except ImportError as e:
            raise ImportError("openai package required: pip install acgs-lite[openai]") from e

        # Note: caller should pass an async client
        response = await self._client.chat.completions.create(**kwargs)

        if hasattr(response, "choices") and response.choices:
            for choice in response.choices:
                if hasattr(choice, "message") and choice.message.content:
                    old_strict = self._engine.strict
                    self._engine.strict = False
                    self._engine.validate(
                        choice.message.content,
                        agent_id=f"{self._agent_id}:output",
                    )
                    self._engine.strict = old_strict

        return response


class GovernedChat:
    """Governed wrapper around OpenAI's chat namespace."""

    def __init__(self, completions: GovernedChatCompletions) -> None:
        self.completions = completions


class GovernedOpenAI:
    """Drop-in replacement for OpenAI() with constitutional governance.

    Usage::

        from acgs_lite.integrations.openai import GovernedOpenAI

        client = GovernedOpenAI()  # Uses OPENAI_API_KEY env var
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello!"}],
        )

    With custom constitution::

        from acgs_lite import Constitution
        from acgs_lite.integrations.openai import GovernedOpenAI

        constitution = Constitution.from_yaml("rules.yaml")
        client = GovernedOpenAI(constitution=constitution)
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        constitution: Constitution | None = None,
        agent_id: str = "openai-agent",
        strict: bool = True,
        **openai_kwargs: Any,
    ) -> None:
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "The 'openai' package is required. Install with: pip install acgs-lite[openai]"
            )

        self._client = OpenAI(api_key=api_key, **openai_kwargs)
        self.constitution = constitution or Constitution.default()
        self.audit_log = AuditLog()
        self.engine = GovernanceEngine(
            self.constitution,
            audit_log=self.audit_log,
            strict=strict,
        )
        self.agent_id = agent_id

        completions = GovernedChatCompletions(self._client, self.engine, agent_id)
        self.chat = GovernedChat(completions)

    @property
    def stats(self) -> dict[str, Any]:
        """Return governance statistics."""
        return {
            **self.engine.stats,
            "agent_id": self.agent_id,
            "audit_chain_valid": self.audit_log.verify_chain(),
        }
