"""
MACI Validation Strategy for AgentMessage processing.

Maps message types to MACI actions and validates through the enforcer.
Supports session context from messages for session-aware validation.

Constitutional Hash: 608508a9bd224290
"""

from collections.abc import Callable

from src.core.shared.type_guards import is_json_dict

from ..maci_imports import (
    CONSTITUTIONAL_HASH,
    MACIError,
    MACIRoleViolationError,
)
from ..observability.structured_logging import get_logger
from .enforcer import MACIEnforcer
from .models import MACIAction
from .utils import AgentMessage, MessageType

logger = get_logger(__name__)


class MACIValidationStrategy:
    """MACI validation strategy for AgentMessage processing.

    Maps message types to MACI actions and validates through the enforcer.
    Supports session context from messages for session-aware validation.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, enforcer: MACIEnforcer | None = None):
        """Initialize the validation strategy.

        Args:
            enforcer: Optional MACIEnforcer instance (creates new if None)
        """
        self.enforcer = enforcer or MACIEnforcer()
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def validate(
        self, msg: AgentMessage, session_id: str | None = None
    ) -> tuple[bool, str | None]:
        """Validate a message against MACI constraints.

        Args:
            msg: AgentMessage to validate
            session_id: Optional session ID (extracted from message if None)

        Returns:
            tuple of (is_valid, error_message)
        """
        # Use enum values for mapping to avoid identity issues with multiple imports
        mtype = (
            msg.message_type.value if hasattr(msg.message_type, "value") else str(msg.message_type)
        )

        try:
            message_type_enum = MessageType()
        except (TypeError, AttributeError):  # Dependency loading errors should not block validation
            message_type_enum = None
        if message_type_enum is not None:
            mapping: dict[str, MACIAction] = {
                message_type_enum.GOVERNANCE_REQUEST.value: MACIAction.PROPOSE,
                message_type_enum.CONSTITUTIONAL_VALIDATION.value: MACIAction.VALIDATE,
                message_type_enum.TASK_REQUEST.value: MACIAction.SYNTHESIZE,
                message_type_enum.QUERY.value: MACIAction.QUERY,
                message_type_enum.AUDIT_LOG.value: MACIAction.AUDIT,
            }
        else:
            mapping = {
                "governance_request": MACIAction.PROPOSE,
                "constitutional_validation": MACIAction.VALIDATE,
                "task_request": MACIAction.SYNTHESIZE,
                "query": MACIAction.QUERY,
                "audit_log": MACIAction.AUDIT,
            }
        act = mapping.get(mtype)
        if not act:
            return not self.enforcer.strict_mode, "Unknown type"

        try:
            # type-safe extraction of target_output_id from message content
            toid: str | None = None
            if is_json_dict(msg.content):
                toid_raw = msg.content.get("target_output_id")
                if isinstance(toid_raw, str):
                    toid = toid_raw

            # Extract session_id from message if not provided
            msg_session_id = session_id
            if msg_session_id is None:
                # Try to get session_id from message attributes
                msg_session_id = getattr(msg, "session_id", None)
                # Or from session_context if available
                if (
                    msg_session_id is None
                    and hasattr(msg, "session_context")
                    and msg.session_context is not None
                ):
                    ctx_session_id = getattr(msg.session_context, "session_id", None)
                    if isinstance(ctx_session_id, str):
                        msg_session_id = ctx_session_id

            await self.enforcer.validate_action(
                msg.from_agent, act, toid, msg.to_agent, session_id=msg_session_id
            )
            return True, None
        except MACIError as e:
            return False, str(e)


def create_maci_enforcement_middleware(
    enforcer: MACIEnforcer | None = None,
    extract_session: bool = True,
) -> Callable:
    """Create MACI enforcement middleware for message processing.

    The middleware validates all messages against MACI constraints before
    passing them to the next handler. Supports session-aware validation.

    Args:
        enforcer: Optional MACIEnforcer instance
        extract_session: If True, extract session_id from messages

    Returns:
        Async middleware function

    Constitutional Hash: 608508a9bd224290
    """
    enf = enforcer or MACIEnforcer()

    async def middleware(msg: AgentMessage, next_handler: Callable) -> AgentMessage:
        """Middleware function that validates messages against MACI constraints.

        Args:
            msg: AgentMessage to validate
            next_handler: Next handler in the middleware chain

        Returns:
            AgentMessage if validation passes

        Raises:
            MACIRoleViolationError: If MACI validation fails
        """
        strategy = MACIValidationStrategy(enf)

        # Extract session_id from message if enabled
        session_id = None
        if extract_session:
            session_id = getattr(msg, "session_id", None)
            if session_id is None and hasattr(msg, "session_context") and msg.session_context:
                session_id = msg.session_context.session_id

        is_valid, error = await strategy.validate(msg, session_id=session_id)
        if not is_valid:
            mtype = (
                msg.message_type.value
                if hasattr(msg.message_type, "value")
                else str(msg.message_type)
            )
            # Log the MACI violation with session context
            logger.warning(
                f"MACI violation: agent={msg.from_agent}, session={session_id}, "
                f"type={mtype}, error={error}"
            )
            raise MACIRoleViolationError(msg.from_agent, "unknown", f"{mtype}: {error}")
        return await next_handler(msg)  # type: ignore[no-any-return]

    return middleware
