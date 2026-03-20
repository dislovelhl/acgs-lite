"""ACGS-Lite LiteLLM Integration.

Universal LLM governance — validates calls across 100+ providers
(OpenAI, Anthropic, Google, Cohere, Mistral, Ollama, etc.) through
LiteLLM's unified API.

Usage::

    from acgs_lite.integrations.litellm import GovernedLiteLLM

    llm = GovernedLiteLLM()
    response = llm.completion(model="gpt-4o", messages=[...])
    response = await llm.acompletion(model="claude-sonnet-4-20250514", messages=[...])

    # Or use the module-level functions:
    from acgs_lite.integrations.litellm import governed_completion
    response = governed_completion(model="gpt-4o", messages=[...])

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
    import litellm as _litellm

    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    _litellm = None  # type: ignore[assignment]


def _extract_user_message(messages: list[dict[str, Any]]) -> str:
    """Extract the last user message text from a messages list."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = [
                    p.get("text", "")
                    for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                return " ".join(parts)
    return ""


def _extract_response_text(response: Any) -> str:
    """Extract text from a LiteLLM response."""
    try:
        if hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            if hasattr(choice, "message") and hasattr(choice.message, "content"):
                return choice.message.content or ""
    except (IndexError, AttributeError):
        pass
    return ""


class GovernedLiteLLM:
    """Governed wrapper around LiteLLM's unified API.

    Adds constitutional governance to any LLM provider supported by LiteLLM.

    Usage::

        llm = GovernedLiteLLM()
        response = llm.completion(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello!"}],
        )

    With custom rules::

        from acgs_lite import Constitution
        llm = GovernedLiteLLM(constitution=Constitution.from_yaml("rules.yaml"))
    """

    def __init__(
        self,
        *,
        constitution: Constitution | None = None,
        agent_id: str = "litellm-agent",
        strict: bool = True,
    ) -> None:
        if not LITELLM_AVAILABLE:
            raise ImportError("litellm is required. Install with: pip install acgs-lite[litellm]")
        self.constitution = constitution or Constitution.default()
        self.audit_log = AuditLog()
        self.engine = GovernanceEngine(
            self.constitution,
            audit_log=self.audit_log,
            strict=strict,
        )
        self.agent_id = agent_id

    def _validate_input(self, messages: list[dict[str, Any]]) -> None:
        """Validate the user message before the LLM call."""
        text = _extract_user_message(messages)
        if text:
            self.engine.validate(text, agent_id=self.agent_id)

    def _validate_output(self, response: Any) -> None:
        """Validate the response (non-blocking)."""
        text = _extract_response_text(response)
        if text:
            old_strict = self.engine.strict
            self.engine.strict = False
            result = self.engine.validate(text, agent_id=f"{self.agent_id}:output")
            self.engine.strict = old_strict
            if not result.valid:
                logger.warning(
                    "LiteLLM response governance violations: %s",
                    [v.rule_id for v in result.violations],
                )

    def completion(self, **kwargs: Any) -> Any:
        """Governed litellm.completion()."""
        messages = kwargs.get("messages", [])
        self._validate_input(messages)
        response = _litellm.completion(**kwargs)  # type: ignore[union-attr]
        self._validate_output(response)
        return response

    async def acompletion(self, **kwargs: Any) -> Any:
        """Governed litellm.acompletion()."""
        messages = kwargs.get("messages", [])
        self._validate_input(messages)
        response = await _litellm.acompletion(**kwargs)  # type: ignore[union-attr]
        self._validate_output(response)
        return response

    def embedding(self, **kwargs: Any) -> Any:
        """Pass-through litellm.embedding() (no governance needed)."""
        return _litellm.embedding(**kwargs)  # type: ignore[union-attr]

    @property
    def stats(self) -> dict[str, Any]:
        """Return governance statistics."""
        return {
            **self.engine.stats,
            "agent_id": self.agent_id,
            "audit_chain_valid": self.audit_log.verify_chain(),
        }


# ─── Module-level convenience functions ───────────────────────────────────

_default_engine: GovernedLiteLLM | None = None


def _get_default() -> GovernedLiteLLM:
    global _default_engine
    if _default_engine is None:
        _default_engine = GovernedLiteLLM(strict=True)
    return _default_engine


def governed_completion(**kwargs: Any) -> Any:
    """Module-level governed completion.

    Usage::

        from acgs_lite.integrations.litellm import governed_completion
        response = governed_completion(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello!"}],
        )
    """
    return _get_default().completion(**kwargs)


async def governed_acompletion(**kwargs: Any) -> Any:
    """Module-level governed async completion."""
    return await _get_default().acompletion(**kwargs)


def configure(
    *,
    constitution: Constitution | None = None,
    agent_id: str = "litellm-agent",
    strict: bool = True,
) -> None:
    """Configure the default governed LiteLLM instance."""
    global _default_engine
    _default_engine = GovernedLiteLLM(
        constitution=constitution,
        agent_id=agent_id,
        strict=strict,
    )
