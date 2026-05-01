"""ACGS-Lite LangChain Integration.

Provides a governance Runnable that wraps any LangChain chain/agent.

Usage::

    from acgs_lite.integrations.langchain import GovernanceRunnable
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model="gpt-5.5")
    governed_llm = GovernanceRunnable.wrap(llm)
    result = governed_llm.invoke("Hello!")

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine

logger = logging.getLogger(__name__)

try:
    from langchain_core.callbacks import CallbackManagerForLLMRun  # noqa: F401
    from langchain_core.messages import AIMessage, BaseMessage, HumanMessage  # noqa: F401
    from langchain_core.outputs import ChatResult  # noqa: F401
    from langchain_core.runnables import Runnable, RunnableConfig  # noqa: F401

    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    Runnable = object  # type: ignore[assignment,misc]


class GovernanceRunnable:
    """LangChain Runnable that adds constitutional governance.

    Wraps any LangChain Runnable (LLM, chain, agent) with governance.

    Usage::

        from acgs_lite.integrations.langchain import GovernanceRunnable
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model="gpt-5.5")
        governed = GovernanceRunnable.wrap(llm)

        # String input
        result = governed.invoke("What is AI governance?")

        # Message input
        from langchain_core.messages import HumanMessage
        result = governed.invoke([HumanMessage(content="Hello!")])
    """

    def __init__(
        self,
        runnable: Any,
        *,
        constitution: Constitution | None = None,
        agent_id: str = "langchain-agent",
        strict: bool = True,
    ) -> None:
        if not LANGCHAIN_AVAILABLE:
            raise ImportError(
                "langchain-core is required. Install with: pip install acgs-lite[langchain]"
            )

        self._runnable = runnable
        self.constitution = constitution or Constitution.default()
        self.audit_log = AuditLog()
        self.engine = GovernanceEngine(
            self.constitution,
            audit_log=self.audit_log,
            strict=strict,
            audit_mode="full",
        )
        self.agent_id = agent_id

    @classmethod
    def wrap(
        cls,
        runnable: Any,
        *,
        constitution: Constitution | None = None,
        agent_id: str = "langchain-agent",
        strict: bool = True,
    ) -> GovernanceRunnable:
        """Wrap a LangChain Runnable with governance."""
        return cls(
            runnable,
            constitution=constitution,
            agent_id=agent_id,
            strict=strict,
        )

    def _extract_text(self, input: Any) -> str:
        """Extract text content from various LangChain input types."""
        if isinstance(input, str):
            return input
        if isinstance(input, dict):
            # Common patterns: {"input": "..."}, {"question": "..."}, {"query": "..."}
            for key in ("input", "question", "query", "text", "content"):
                if key in input:
                    return str(input[key])
            return str(input)
        if isinstance(input, list):
            # List of messages
            texts = []
            for item in input:
                if hasattr(item, "content"):
                    texts.append(str(item.content))
                elif isinstance(item, str):
                    texts.append(item)
            return " ".join(texts)
        if hasattr(input, "content"):
            return str(input.content)
        return str(input)

    def _validate_output(self, output: Any) -> None:
        """Validate output without raising (just log warnings)."""
        text = self._extract_text(output)
        if text:
            result = self.engine.validate(text, agent_id=f"{self.agent_id}:output", strict=False)
            if not result.valid:
                logger.warning(
                    "LangChain output governance violations: %s",
                    [v.rule_id for v in result.violations],
                )

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        """Invoke with governance."""
        text = self._extract_text(input)
        if text:
            self.engine.validate(text, agent_id=self.agent_id)

        result = self._runnable.invoke(input, config=config, **kwargs)

        self._validate_output(result)
        return result

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        """Async invoke with governance."""
        text = self._extract_text(input)
        if text:
            self.engine.validate(text, agent_id=self.agent_id)

        result = await self._runnable.ainvoke(input, config=config, **kwargs)

        self._validate_output(result)
        return result

    def batch(self, inputs: list[Any], config: Any = None, **kwargs: Any) -> list[Any]:
        """Batch invoke with governance."""
        for inp in inputs:
            text = self._extract_text(inp)
            if text:
                self.engine.validate(text, agent_id=self.agent_id)

        results: list[Any] = list(self._runnable.batch(inputs, config=config, **kwargs))

        for result in results:
            self._validate_output(result)

        return results

    def stream(self, input: Any, config: Any = None, **kwargs: Any) -> Iterator[Any]:
        """Stream with governance (validates input, streams output)."""
        text = self._extract_text(input)
        if text:
            self.engine.validate(text, agent_id=self.agent_id)

        yield from self._runnable.stream(input, config=config, **kwargs)

    @property
    def stats(self) -> dict[str, Any]:
        """Return governance statistics for this runnable."""
        return {
            **self.engine.stats,
            "agent_id": self.agent_id,
            "audit_chain_valid": self.audit_log.verify_chain(),
        }
