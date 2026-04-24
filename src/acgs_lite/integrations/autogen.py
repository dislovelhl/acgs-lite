"""ACGS-Lite AG2/AutoGen Integration.

Adds constitutional governance to AG2 (formerly AutoGen) agents by wrapping
the model client with input/output validation.

Usage::

    from acgs_lite.integrations.autogen import GovernedModelClient
    from autogen_agentchat.agents import AssistantAgent
    from autogen_ext.models.openai import OpenAIChatCompletionClient

    base_client = OpenAIChatCompletionClient(model="gpt-5.4")
    governed_client = GovernedModelClient(base_client)
    agent = AssistantAgent("assistant", model_client=governed_client)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Mapping, Sequence
from typing import Any

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine

logger = logging.getLogger(__name__)

try:
    from autogen_core import CancellationToken  # noqa: F401
    from autogen_core.models import (
        ChatCompletionClient,
        CreateResult,  # noqa: F401
        LLMMessage,  # noqa: F401
        ModelCapabilities,  # noqa: F401
        ModelInfo,  # noqa: F401
        RequestUsage,
    )

    AUTOGEN_AVAILABLE = True
except ImportError:
    AUTOGEN_AVAILABLE = False
    ChatCompletionClient = object  # type: ignore[assignment,misc]


def _extract_message_text(messages: Sequence[Any]) -> str:
    """Extract text from AG2 LLM messages."""
    texts: list[str] = []
    for msg in messages:
        if hasattr(msg, "content"):
            content = msg.content
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, str):
                        texts.append(part)
                    elif hasattr(part, "text"):
                        texts.append(str(part.text))
    return " ".join(texts)


def _extract_result_text(result: Any) -> str:
    """Extract text from a CreateResult."""
    if hasattr(result, "content"):
        if isinstance(result.content, str):
            return result.content
        if isinstance(result.content, list):
            parts = []
            for p in result.content:
                if isinstance(p, str):
                    parts.append(p)
                elif hasattr(p, "text"):
                    parts.append(str(p.text))
            return " ".join(parts)
    return ""


class GovernedModelClient:
    """Governed wrapper around any AG2 ChatCompletionClient.

    Validates messages before sending to the model and validates
    responses after receiving them.

    Usage::

        from autogen_ext.models.openai import OpenAIChatCompletionClient
        from acgs_lite.integrations.autogen import GovernedModelClient

        base = OpenAIChatCompletionClient(model="gpt-5.4")
        governed = GovernedModelClient(base)
        # Use governed client with any AG2 agent
    """

    def __init__(
        self,
        client: Any,
        *,
        constitution: Constitution | None = None,
        agent_id: str = "autogen-agent",
        strict: bool = True,
    ) -> None:
        if not AUTOGEN_AVAILABLE:
            raise ImportError(
                "autogen-core is required. Install with: pip install acgs-lite[autogen]"
            )

        self._client = client
        self.constitution = constitution or Constitution.default()
        self.audit_log = AuditLog()
        self.engine = GovernanceEngine(
            self.constitution,
            audit_log=self.audit_log,
            strict=strict,
            audit_mode="full",
        )
        self.agent_id = agent_id

    async def create(
        self,
        messages: Sequence[Any],
        *,
        tools: Sequence[Any] = (),
        json_output: bool | type | None = None,
        extra_create_args: Mapping[str, Any] = {},
        cancellation_token: Any | None = None,
    ) -> Any:
        """Create a completion with governance validation."""
        # Validate input messages
        text = _extract_message_text(messages)
        if text:
            self.engine.validate(text, agent_id=self.agent_id)

        # Delegate to underlying client
        result = await self._client.create(
            messages,
            tools=tools,
            json_output=json_output,
            extra_create_args=extra_create_args,
            cancellation_token=cancellation_token,
        )

        # Validate output (non-blocking)
        resp_text = _extract_result_text(result)
        if resp_text:
            val_result = self.engine.validate(
                resp_text, agent_id=f"{self.agent_id}:output", strict=False
            )
            if not val_result.valid:
                logger.warning(
                    "AG2 response governance violations: %s",
                    [v.rule_id for v in val_result.violations],
                )

        return result

    async def create_stream(
        self,
        messages: Sequence[Any],
        *,
        tools: Sequence[Any] = (),
        json_output: bool | type | None = None,
        extra_create_args: Mapping[str, Any] = {},
        cancellation_token: Any | None = None,
    ) -> AsyncGenerator[Any, None]:
        """Stream completions with governance validation on input."""
        text = _extract_message_text(messages)
        if text:
            self.engine.validate(text, agent_id=self.agent_id)

        async for chunk in self._client.create_stream(
            messages,
            tools=tools,
            json_output=json_output,
            extra_create_args=extra_create_args,
            cancellation_token=cancellation_token,
        ):
            yield chunk

    def actual_usage(self) -> RequestUsage | None:
        """Delegate to underlying client."""
        if hasattr(self._client, "actual_usage"):
            return self._client.actual_usage()  # type: ignore[no-any-return]
        return None

    def total_usage(self) -> RequestUsage | None:
        """Delegate to underlying client."""
        if hasattr(self._client, "total_usage"):
            return self._client.total_usage()  # type: ignore[no-any-return]
        return None

    @property
    def model_info(self) -> Any:
        """Delegate to underlying client."""
        return self._client.model_info

    @property
    def capabilities(self) -> Any:
        """Delegate to underlying client."""
        return getattr(self._client, "capabilities", None)

    def count_tokens(self, messages: Sequence[Any], *, tools: Sequence[Any] = ()) -> int:
        """Delegate token counting to underlying client."""
        if hasattr(self._client, "count_tokens"):
            return self._client.count_tokens(messages, tools=tools)  # type: ignore[no-any-return]
        return 0

    def remaining_tokens(self, messages: Sequence[Any], *, tools: Sequence[Any] = ()) -> int:
        """Delegate to underlying client."""
        if hasattr(self._client, "remaining_tokens"):
            return self._client.remaining_tokens(messages, tools=tools)  # type: ignore[no-any-return]
        return 0

    @property
    def stats(self) -> dict[str, Any]:
        """Return governance statistics."""
        return {
            **self.engine.stats,
            "agent_id": self.agent_id,
            "audit_chain_valid": self.audit_log.verify_chain(),
        }
