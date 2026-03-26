"""ACGS-Lite Google GenAI (Gemini) Integration.

Wraps the google-genai SDK with constitutional governance.

Usage::

    from acgs_lite.integrations.google_genai import GovernedGenAI

    client = GovernedGenAI(api_key="...")
    response = client.generate_content(
        model="gemini-2.0-flash",
        contents="Hello!",
    )

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
    from google import genai  # noqa: F401
    from google.genai import Client as GenAIClient

    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    GenAIClient = None  # type: ignore[assignment,misc]


def _extract_content_text(contents: Any) -> str:
    """Extract text from various content formats."""
    if isinstance(contents, str):
        return contents
    if isinstance(contents, list):
        texts: list[str] = []
        for item in contents:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict) and "text" in item:
                texts.append(item["text"])
            elif hasattr(item, "text"):
                texts.append(str(item.text))
        return " ".join(texts)
    if hasattr(contents, "text"):
        return str(contents.text)
    return str(contents)


def _extract_response_text(response: Any) -> str:
    """Extract text from a GenAI response."""
    try:
        if hasattr(response, "text"):
            return response.text or ""
        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, "content") and candidate.content:
                parts = candidate.content.parts
                if parts:
                    return parts[0].text or ""
    except (IndexError, AttributeError):
        pass
    return ""


class GovernedModels:
    """Governed wrapper around client.models."""

    def __init__(
        self,
        client: Any,
        engine: GovernanceEngine,
        agent_id: str,
    ) -> None:
        self._client = client
        self._engine = engine
        self._agent_id = agent_id

    def generate_content(self, *, model: str, contents: Any, **kwargs: Any) -> Any:
        """Generate content with governance."""
        text = _extract_content_text(contents)
        if text:
            self._engine.validate(text, agent_id=self._agent_id)

        response = self._client.models.generate_content(model=model, contents=contents, **kwargs)

        resp_text = _extract_response_text(response)
        if resp_text:
            old_strict = self._engine.strict
            self._engine.strict = False
            result = self._engine.validate(resp_text, agent_id=f"{self._agent_id}:output")
            self._engine.strict = old_strict
            if not result.valid:
                logger.warning(
                    "Gemini response governance violations: %s",
                    [v.rule_id for v in result.violations],
                )

        return response

    def generate_content_stream(self, *, model: str, contents: Any, **kwargs: Any) -> Any:
        """Stream content with governance (validates input only)."""
        text = _extract_content_text(contents)
        if text:
            self._engine.validate(text, agent_id=self._agent_id)

        return self._client.models.generate_content_stream(model=model, contents=contents, **kwargs)

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attributes to the underlying client.models."""
        return getattr(self._client.models, name)


class GovernedAsyncModels:
    """Governed wrapper around client.aio.models."""

    def __init__(
        self,
        client: Any,
        engine: GovernanceEngine,
        agent_id: str,
    ) -> None:
        self._client = client
        self._engine = engine
        self._agent_id = agent_id

    async def generate_content(self, *, model: str, contents: Any, **kwargs: Any) -> Any:
        """Async generate content with governance."""
        text = _extract_content_text(contents)
        if text:
            self._engine.validate(text, agent_id=self._agent_id)

        response = await self._client.aio.models.generate_content(
            model=model, contents=contents, **kwargs
        )

        resp_text = _extract_response_text(response)
        if resp_text:
            old_strict = self._engine.strict
            self._engine.strict = False
            result = self._engine.validate(resp_text, agent_id=f"{self._agent_id}:output")
            self._engine.strict = old_strict
            if not result.valid:
                logger.warning(
                    "Gemini async response governance violations: %s",
                    [v.rule_id for v in result.violations],
                )

        return response


class GovernedAsyncClient:
    """Governed wrapper around client.aio."""

    def __init__(self, models: GovernedAsyncModels) -> None:
        self.models = models


class GovernedGenAI:
    """Drop-in governed wrapper for Google GenAI Client.

    Usage::

        from acgs_lite.integrations.google_genai import GovernedGenAI

        client = GovernedGenAI(api_key="...")
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents="Hello!",
        )

        # Convenience method:
        response = client.generate_content(
            model="gemini-2.0-flash",
            contents="Hello!",
        )
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        constitution: Constitution | None = None,
        agent_id: str = "gemini-agent",
        strict: bool = True,
        **genai_kwargs: Any,
    ) -> None:
        if not GENAI_AVAILABLE:
            raise ImportError("google-genai is required. Install with: pip install acgs[google]")

        self._client = GenAIClient(api_key=api_key, **genai_kwargs)
        self.constitution = constitution or Constitution.default()
        self.audit_log = AuditLog()
        self.engine = GovernanceEngine(
            self.constitution,
            audit_log=self.audit_log,
            strict=strict,
        )
        self.agent_id = agent_id

        self.models = GovernedModels(self._client, self.engine, agent_id)
        self.aio = GovernedAsyncClient(GovernedAsyncModels(self._client, self.engine, agent_id))

    def generate_content(self, *, model: str, contents: Any, **kwargs: Any) -> Any:
        """Convenience: governed client.models.generate_content()."""
        return self.models.generate_content(model=model, contents=contents, **kwargs)

    @property
    def stats(self) -> dict[str, Any]:
        """Return governance statistics."""
        return {
            **self.engine.stats,
            "agent_id": self.agent_id,
            "audit_chain_valid": self.audit_log.verify_chain(),
        }
