"""ACGS-Lite xAI (Grok) Integration.

Wraps xAI's OpenAI-compatible API with constitutional governance.
Every prompt is validated before sending. Every response is validated before returning.

Usage::

    from acgs_lite.integrations.xai import GovernedXAI

    client = GovernedXAI(api_key="xai-...")
    response = client.chat.completions.create(
        model="grok-4-1-fast",
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

from . import GovernedChat, GovernedChatCompletions

logger = logging.getLogger(__name__)

XAI_API_BASE = "https://api.x.ai/v1"

try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = object  # type: ignore[assignment,misc]


class GovernedXAI:
    """Drop-in governed xAI client using OpenAI-compatible API.

    Usage::

        from acgs_lite.integrations.xai import GovernedXAI

        client = GovernedXAI()  # Uses XAI_API_KEY env var
        response = client.chat.completions.create(
            model="grok-4-1-fast",
            messages=[{"role": "user", "content": "Hello!"}],
        )

    With custom constitution::

        from acgs_lite import Constitution
        from acgs_lite.integrations.xai import GovernedXAI

        constitution = Constitution.from_yaml("rules.yaml")
        client = GovernedXAI(constitution=constitution)
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = XAI_API_BASE,
        constitution: Constitution | None = None,
        agent_id: str = "xai-agent",
        strict: bool = True,
        **openai_kwargs: Any,
    ) -> None:
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "The 'openai' package is required. "
                "Install with: pip install acgs-lite[openai]"
            )

        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            **openai_kwargs,
        )
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


__all__ = ["GovernedXAI"]
