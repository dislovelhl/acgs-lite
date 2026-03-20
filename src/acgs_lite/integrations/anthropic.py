"""ACGS-Lite Anthropic Integration.

Wraps Anthropic's Messages API with constitutional governance.

Usage::

    from acgs_lite.integrations.anthropic import GovernedAnthropic

    client = GovernedAnthropic(api_key="sk-ant-...")
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Hello!"}],
    )

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import logging
from typing import Any

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine

logger = logging.getLogger(__name__)

try:
    from anthropic import Anthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    Anthropic = object  # type: ignore[assignment,misc]


class GovernedMessages:
    """Governed wrapper around Anthropic's messages API."""

    def __init__(
        self,
        client: Any,
        engine: GovernanceEngine,
        agent_id: str,
    ) -> None:
        self._client = client
        self._engine = engine
        self._agent_id = agent_id

    def create(self, **kwargs: Any) -> Any:
        """Create a message with governance."""
        messages = kwargs.get("messages", [])

        # Validate last user message
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    self._engine.validate(content, agent_id=self._agent_id)
                elif isinstance(content, list):
                    # Anthropic supports content blocks
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            self._engine.validate(block["text"], agent_id=self._agent_id)
                break

        # Also validate system prompt if present
        system = kwargs.get("system", "")
        if isinstance(system, str) and system:
            old_strict = self._engine.strict
            self._engine.strict = False
            self._engine.validate(system, agent_id=f"{self._agent_id}:system")
            self._engine.strict = old_strict

        # Call Anthropic
        response = self._client.messages.create(**kwargs)

        # Validate output
        if hasattr(response, "content") and response.content:
            for block in response.content:
                if hasattr(block, "text") and block.text:
                    old_strict = self._engine.strict
                    self._engine.strict = False
                    result = self._engine.validate(block.text, agent_id=f"{self._agent_id}:output")
                    self._engine.strict = old_strict

                    if not result.valid:
                        logger.warning(
                            "Anthropic response violations: %s",
                            [v.rule_id for v in result.violations],
                        )

        return response


class GovernedAnthropic:
    """Drop-in replacement for Anthropic() with constitutional governance.

    Usage::

        from acgs_lite.integrations.anthropic import GovernedAnthropic

        client = GovernedAnthropic()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Hello!"}],
        )
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        constitution: Constitution | None = None,
        agent_id: str = "anthropic-agent",
        strict: bool = True,
        **anthropic_kwargs: Any,
    ) -> None:
        if not ANTHROPIC_AVAILABLE:
            raise ImportError(
                "The 'anthropic' package is required. "
                "Install with: pip install acgs-lite[anthropic]"
            )

        self._client = Anthropic(api_key=api_key, **anthropic_kwargs)  # type: ignore[operator]
        self.constitution = constitution or Constitution.default()
        self.audit_log = AuditLog()
        self.engine = GovernanceEngine(
            self.constitution,
            audit_log=self.audit_log,
            strict=strict,
        )
        self.agent_id = agent_id
        self.messages = GovernedMessages(self._client, self.engine, agent_id)

    @property
    def stats(self) -> dict[str, Any]:
        return {
            **self.engine.stats,
            "agent_id": self.agent_id,
            "audit_chain_valid": self.audit_log.verify_chain(),
        }
