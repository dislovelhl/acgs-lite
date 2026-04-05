from __future__ import annotations

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .config import BusConfiguration
from .message_processor_components import (
    apply_session_governance_metrics,
    calculate_session_resolution_rate,
    extract_session_id_for_pacar,
)
from .models import AgentMessage
from .processing_context import MessageProcessingContext
from .session_context import SessionContext, SessionContextManager
from .session_context_resolver import SessionContextResolver

logger = get_logger(__name__)


class SessionCoordinator:
    """Encapsulates session-governance setup, attachment, and metrics.

    MessageProcessor keeps the public/private helper surface for compatibility, while this
    coordinator owns the actual session-resolution flow and session-metrics enrichment.
    """

    def __init__(
        self,
        *,
        enable_session_governance: bool,
        session_context_manager: SessionContextManager | None,
        session_resolver: SessionContextResolver,
        session_resolved_count: int = 0,
        session_not_found_count: int = 0,
        session_error_count: int = 0,
    ) -> None:
        self._enable_session_governance = enable_session_governance
        self._session_context_manager = session_context_manager
        self._session_resolver = session_resolver
        self._session_resolved_count = session_resolved_count
        self._session_not_found_count = session_not_found_count
        self._session_error_count = session_error_count

    @staticmethod
    def initialize_runtime(
        config: BusConfiguration,
        *,
        enable_session_governance: bool,
    ) -> tuple[bool, SessionContextManager | None]:
        if not enable_session_governance:
            return False, None
        try:
            manager = SessionContextManager(
                cache_size=1000,
                cache_ttl=config.session_policy_cache_ttl,
            )
            logger.info("Session governance enabled for message processor")
            return True, manager
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
            logger.warning(f"Failed to initialize session context manager: {exc}")
            return False, None

    @staticmethod
    def build_session_resolver(
        config: BusConfiguration,
        manager: SessionContextManager | None,
    ) -> SessionContextResolver:
        return SessionContextResolver(
            config=config,
            manager=manager,
        )

    def sync_runtime(
        self,
        *,
        enable_session_governance: bool,
        session_context_manager: SessionContextManager | None,
        session_resolver: SessionContextResolver,
        session_resolved_count: int,
        session_not_found_count: int,
        session_error_count: int,
    ) -> None:
        self._enable_session_governance = enable_session_governance
        self._session_context_manager = session_context_manager
        self._session_resolver = session_resolver
        self._session_resolved_count = session_resolved_count
        self._session_not_found_count = session_not_found_count
        self._session_error_count = session_error_count

    def export_runtime_state(self) -> tuple[bool, SessionContextManager | None, SessionContextResolver, int, int, int]:
        return (
            self._enable_session_governance,
            self._session_context_manager,
            self._session_resolver,
            self._session_resolved_count,
            self._session_not_found_count,
            self._session_error_count,
        )

    async def extract_session_context(self, msg: AgentMessage) -> SessionContext | None:
        if not self._enable_session_governance:
            return None

        session_context = await self._session_resolver.resolve(msg)
        resolver_metrics = self._session_resolver.get_metrics()
        self._session_resolved_count = int(resolver_metrics.get("resolved_count", 0))
        self._session_not_found_count = int(resolver_metrics.get("not_found_count", 0))
        self._session_error_count = int(resolver_metrics.get("error_count", 0))
        return session_context  # type: ignore[no-any-return]

    def extract_message_session_id(self, msg: AgentMessage) -> str | None:
        return extract_session_id_for_pacar(msg)  # type: ignore[no-any-return]

    async def attach_session_context(
        self,
        target: MessageProcessingContext | AgentMessage,
    ) -> None:
        if hasattr(target, "message") and hasattr(target, "start_time"):
            context = target
            msg = target.message
        else:
            context = None
            msg = target

        session_context = await self.extract_session_context(msg)
        if session_context is None:
            return

        if context is not None:
            context.session_context = session_context
        if hasattr(msg, "session_context"):
            msg.session_context = session_context  # type: ignore[assignment]
        if hasattr(msg, "session_id") and not msg.session_id:
            msg.session_id = session_context.session_id
        logger.debug(
            f"Attached session context to message {msg.message_id}: "
            f"session_id={session_context.session_id}"
        )

    def apply_metrics(self, metrics: JSONDict) -> None:
        session_resolution_rate = calculate_session_resolution_rate(
            self._session_resolved_count,
            self._session_not_found_count,
            self._session_error_count,
        )
        apply_session_governance_metrics(
            metrics,
            enabled=self._enable_session_governance,
            resolved_count=self._session_resolved_count,
            not_found_count=self._session_not_found_count,
            error_count=self._session_error_count,
            resolution_rate=session_resolution_rate,
        )
