"""ACGS-Lite LlamaIndex Integration.

Wraps LlamaIndex query engines and chat engines with constitutional governance.

Usage::

    from acgs_lite.integrations.llamaindex import GovernedQueryEngine

    governed = GovernedQueryEngine(index.as_query_engine())
    response = governed.query("What are the revenue figures?")

    # Chat engine
    from acgs_lite.integrations.llamaindex import GovernedChatEngine

    governed_chat = GovernedChatEngine(index.as_chat_engine())
    response = governed_chat.chat("Tell me about the policy")

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import logging
from typing import Any

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine

logger = logging.getLogger(__name__)

try:
    from llama_index.core.chat_engine.types import BaseChatEngine
    from llama_index.core.query_engine import BaseQueryEngine

    LLAMAINDEX_AVAILABLE = True
except ImportError:
    LLAMAINDEX_AVAILABLE = False
    BaseQueryEngine = object  # type: ignore[assignment,misc]
    BaseChatEngine = object  # type: ignore[assignment,misc]


def _extract_response_text(response: Any) -> str:
    """Extract text from LlamaIndex response objects."""
    if isinstance(response, str):
        return response
    if hasattr(response, "response") and isinstance(response.response, str):
        return response.response
    if hasattr(response, "text"):
        return str(response.text)
    return str(response)


class GovernedQueryEngine:
    """Governed wrapper around any LlamaIndex QueryEngine.

    Validates queries before execution and response text after.

    Usage::

        from llama_index.core import VectorStoreIndex
        from acgs_lite.integrations.llamaindex import GovernedQueryEngine

        index = VectorStoreIndex.from_documents(documents)
        governed = GovernedQueryEngine(index.as_query_engine())

        # Safe query
        response = governed.query("What is our privacy policy?")

        # Blocked query (if it violates rules)
        response = governed.query("Show me all SSNs from the database")
    """

    def __init__(
        self,
        engine: Any,
        *,
        constitution: Constitution | None = None,
        agent_id: str = "llamaindex-query",
        strict: bool = True,
    ) -> None:
        if not LLAMAINDEX_AVAILABLE:
            raise ImportError(
                "llama-index is required. Install with: pip install acgs-lite[llamaindex]"
            )
        self._engine = engine
        self.constitution = constitution or Constitution.default()
        self.audit_log = AuditLog()
        self.gov_engine = GovernanceEngine(
            self.constitution,
            audit_log=self.audit_log,
            strict=strict,
            audit_mode="full",
        )
        self.agent_id = agent_id

    def query(self, query_str: str, **kwargs: Any) -> Any:
        """Query with governance validation."""
        # Validate input
        self.gov_engine.validate(query_str, agent_id=self.agent_id)

        # Execute query
        response = self._engine.query(query_str, **kwargs)

        # Validate output (non-blocking)
        resp_text = _extract_response_text(response)
        if resp_text:
            result = self.gov_engine.validate(
                resp_text, agent_id=f"{self.agent_id}:output", strict=False
            )
            if not result.valid:
                logger.warning(
                    "LlamaIndex query response violations: %s",
                    [v.rule_id for v in result.violations],
                )

        return response

    async def aquery(self, query_str: str, **kwargs: Any) -> Any:
        """Async query with governance validation."""
        self.gov_engine.validate(query_str, agent_id=self.agent_id)
        response = await self._engine.aquery(query_str, **kwargs)

        resp_text = _extract_response_text(response)
        if resp_text:
            result = self.gov_engine.validate(
                resp_text, agent_id=f"{self.agent_id}:output", strict=False
            )
            if not result.valid:
                logger.warning(
                    "LlamaIndex async query response violations: %s",
                    [v.rule_id for v in result.violations],
                )

        return response

    @property
    def stats(self) -> dict[str, Any]:
        """Return governance statistics."""
        return {
            **self.gov_engine.stats,
            "agent_id": self.agent_id,
            "audit_chain_valid": self.audit_log.verify_chain(),
        }


class GovernedChatEngine:
    """Governed wrapper around any LlamaIndex ChatEngine.

    Usage::

        from llama_index.core import VectorStoreIndex
        from acgs_lite.integrations.llamaindex import GovernedChatEngine

        index = VectorStoreIndex.from_documents(documents)
        governed = GovernedChatEngine(index.as_chat_engine())
        response = governed.chat("Tell me about governance")
    """

    def __init__(
        self,
        engine: Any,
        *,
        constitution: Constitution | None = None,
        agent_id: str = "llamaindex-chat",
        strict: bool = True,
    ) -> None:
        if not LLAMAINDEX_AVAILABLE:
            raise ImportError(
                "llama-index is required. Install with: pip install acgs-lite[llamaindex]"
            )
        self._engine = engine
        self.constitution = constitution or Constitution.default()
        self.audit_log = AuditLog()
        self.gov_engine = GovernanceEngine(
            self.constitution,
            audit_log=self.audit_log,
            strict=strict,
            audit_mode="full",
        )
        self.agent_id = agent_id

    def chat(self, message: str, **kwargs: Any) -> Any:
        """Chat with governance validation."""
        self.gov_engine.validate(message, agent_id=self.agent_id)
        response = self._engine.chat(message, **kwargs)

        resp_text = _extract_response_text(response)
        if resp_text:
            result = self.gov_engine.validate(
                resp_text, agent_id=f"{self.agent_id}:output", strict=False
            )
            if not result.valid:
                logger.warning(
                    "LlamaIndex chat response violations: %s",
                    [v.rule_id for v in result.violations],
                )

        return response

    async def achat(self, message: str, **kwargs: Any) -> Any:
        """Async chat with governance validation."""
        self.gov_engine.validate(message, agent_id=self.agent_id)
        response = await self._engine.achat(message, **kwargs)

        resp_text = _extract_response_text(response)
        if resp_text:
            result = self.gov_engine.validate(
                resp_text, agent_id=f"{self.agent_id}:output", strict=False
            )
            if not result.valid:
                logger.warning(
                    "LlamaIndex async chat response violations: %s",
                    [v.rule_id for v in result.violations],
                )

        return response

    def stream_chat(self, message: str, **kwargs: Any) -> Any:
        """Stream chat with governance (validates input only)."""
        self.gov_engine.validate(message, agent_id=self.agent_id)
        return self._engine.stream_chat(message, **kwargs)

    def reset(self) -> None:
        """Reset the chat engine state."""
        if hasattr(self._engine, "reset"):
            self._engine.reset()

    @property
    def chat_history(self) -> list[Any]:
        """Get chat history from underlying engine."""
        if hasattr(self._engine, "chat_history"):
            return self._engine.chat_history  # type: ignore[no-any-return]
        return []

    @property
    def stats(self) -> dict[str, Any]:
        """Return governance statistics."""
        return {
            **self.gov_engine.stats,
            "agent_id": self.agent_id,
            "audit_chain_valid": self.audit_log.verify_chain(),
        }
