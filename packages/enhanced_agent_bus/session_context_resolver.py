"""
ACGS-2 Enhanced Agent Bus - Session Context Resolver
Constitutional Hash: 608508a9bd224290

Unified session context extraction from messages with cross-tenant
security validation and metrics tracking.

Consolidates the duplicated logic from MessageProcessor's
_extract_session_context() and _extract_message_session_id() into
a single class with a consistent priority chain.
"""

import asyncio

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .config import BusConfiguration
from .models import AgentMessage
from .performance_monitor import timed
from .session_context import SessionContext, SessionContextManager

logger = get_logger(__name__)
SESSION_CONTEXT_LOAD_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)


class SessionContextResolver:
    """Unified session context resolution with cross-tenant protection.

    Extracts session_id from messages using a consistent priority chain:
    1. ``session_id`` field on the message
    2. Already-attached ``session_context``
    3. ``X-Session-ID`` / ``x-session-id`` header
    4. ``session_id`` key in ``metadata`` dict
    5. ``session_id`` key in ``content`` dict (if dict)

    The extended extraction for PACAR multi-turn context also checks:
    - ``conversation_id`` field
    - ``session_id`` in ``payload`` dict

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        config: BusConfiguration,
        manager: SessionContextManager | None = None,
    ) -> None:
        self._config = config
        self._enable = config.enable_session_governance and manager is not None
        self._manager = manager

        # Metrics counters
        self._resolved_count: int = 0
        self._not_found_count: int = 0
        self._error_count: int = 0

    @property
    def enabled(self) -> bool:
        """Whether session governance resolution is active."""
        return self._enable

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @timed("session_context_resolve")
    async def resolve(self, msg: AgentMessage) -> SessionContext | None:
        """Resolve and validate session context for *msg*.

        Args:
            msg: The agent message to resolve session context for.

        Returns:
            A ``SessionContext`` if found and valid, ``None`` otherwise.
            Returns ``None`` gracefully on errors, missing tenant, and
            cross-tenant access attempts.
        """
        if not self._enable or self._manager is None:
            return None

        # Fast-path: context already attached
        if hasattr(msg, "session_context") and msg.session_context:
            self._resolved_count += 1
            return msg.session_context  # type: ignore[return-value]

        session_id = self.extract_governance_session_id(msg)
        if not session_id:
            return None

        tenant_id = getattr(msg, "tenant_id", None)
        if not tenant_id:
            logger.warning(
                "No tenant_id in message, cannot load session %s",
                session_id,
            )
            return None

        try:
            ctx = await self._manager.get(session_id, tenant_id)
        except SESSION_CONTEXT_LOAD_ERRORS as exc:
            self._error_count += 1
            logger.warning(
                "Error loading session context for session_id=%s: %s",
                session_id,
                exc,
                exc_info=True,
            )
            return None

        if ctx is None:
            self._not_found_count += 1
            logger.debug(
                "Session context not found for session_id=%s",
                session_id,
            )
            return None

        # VULN-002: Cross-tenant session hijacking prevention
        if ctx.governance_config.tenant_id != tenant_id:
            logger.warning(
                "Cross-tenant session access denied: session_id=%s "
                "belongs to tenant=%s, but request is from tenant=%s",
                session_id,
                ctx.governance_config.tenant_id,
                tenant_id,
            )
            return None

        self._resolved_count += 1
        logger.debug(
            "Resolved session context for session_id=%s, tenant=%s, risk_level=%s",
            session_id,
            ctx.governance_config.tenant_id,
            ctx.governance_config.risk_level.value,
        )
        return ctx

    def extract_session_id(self, msg: AgentMessage) -> str | None:
        """Extract session_id from *msg* without loading context.

        Priority chain:
            session_id field → headers → conversation_id → content →
            payload

        Args:
            msg: The agent message.

        Returns:
            The session ID string or ``None``.
        """
        if hasattr(msg, "session_id") and msg.session_id:
            return str(msg.session_id)

        if hasattr(msg, "headers") and msg.headers:
            hdr = msg.headers.get("X-Session-ID") or msg.headers.get("x-session-id")
            if hdr:
                return str(hdr)

        if hasattr(msg, "conversation_id") and msg.conversation_id:
            return str(msg.conversation_id)

        if hasattr(msg, "metadata") and isinstance(msg.metadata, dict):
            sid = msg.metadata.get("session_id")
            if sid:
                return str(sid)

        if hasattr(msg, "content") and isinstance(msg.content, dict):
            sid = msg.content.get("session_id")
            if sid:
                return str(sid)

        if hasattr(msg, "payload") and isinstance(msg.payload, dict):
            sid = msg.payload.get("session_id")
            if sid:
                return str(sid)

        return None

    def extract_governance_session_id(self, msg: AgentMessage) -> str | None:
        """Extract session_id for session-governance lookup only.

        Priority chain:
            session_id field → headers → metadata → content
        """
        if hasattr(msg, "session_id") and msg.session_id:
            return str(msg.session_id)

        if hasattr(msg, "headers") and msg.headers:
            hdr = msg.headers.get("X-Session-ID") or msg.headers.get("x-session-id")
            if hdr:
                return str(hdr)

        if hasattr(msg, "metadata") and isinstance(msg.metadata, dict):
            sid = msg.metadata.get("session_id")
            if sid:
                return str(sid)

        if hasattr(msg, "content") and isinstance(msg.content, dict):
            sid = msg.content.get("session_id")
            if sid:
                return str(sid)

        return None

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def get_metrics(self) -> JSONDict:
        """Get session resolution metrics.

        Returns:
            Dict with resolved_count, not_found_count, error_count,
            and resolution_rate.
        """
        total = self._resolved_count + self._not_found_count + self._error_count
        rate = self._resolved_count / total if total > 0 else 0.0
        return {
            "resolved_count": self._resolved_count,
            "not_found_count": self._not_found_count,
            "error_count": self._error_count,
            "resolution_rate": rate,
        }
