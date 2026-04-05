"""
ACGS-2 LangGraph Orchestration - HITL Integration
Constitutional Hash: 608508a9bd224290

Human-in-the-loop (HITL) integration for workflow interrupts:
- Configurable interrupt points
- Timeout handling with escalation
- State modification support
- Audit trail for all HITL interactions
"""

import asyncio
import builtins
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .exceptions import InterruptError, TimeoutError
from .models import (
    ExecutionContext,
    GraphState,
    InterruptType,
)

logger = get_logger(__name__)


class HITLAction(str, Enum):
    """Actions that can be taken in response to HITL interrupt.

    Constitutional Hash: 608508a9bd224290
    """

    CONTINUE = "continue"  # Continue execution with current state
    ABORT = "abort"  # Abort workflow execution
    MODIFY = "modify"  # Continue with modified state
    RETRY = "retry"  # Retry current node
    SKIP = "skip"  # Skip current node
    ESCALATE = "escalate"  # Escalate to higher authority


@dataclass
class HITLConfig:
    """Configuration for HITL interrupt handling.

    Constitutional Hash: 608508a9bd224290
    """

    enabled: bool = True
    default_timeout_ms: float = 300000.0  # 5 minutes
    max_timeout_ms: float = 3600000.0  # 1 hour
    auto_continue_on_timeout: bool = False
    auto_abort_on_timeout: bool = False
    escalation_enabled: bool = True
    escalation_timeout_ms: float = 600000.0  # 10 minutes

    # Audit settings
    audit_all_requests: bool = True
    audit_all_responses: bool = True

    # Rate limiting
    max_requests_per_workflow: int = 100
    cooldown_ms: float = 1000.0  # 1 second between requests

    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class HITLRequest:
    """Request for human-in-the-loop interaction.

    Constitutional Hash: 608508a9bd224290
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = ""
    run_id: str = ""
    node_id: str = ""
    interrupt_type: InterruptType = InterruptType.HITL

    # Context
    current_state: GraphState | None = None
    reason: str = ""
    details: JSONDict = field(default_factory=dict)

    # Timing
    timeout_ms: float = 300000.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None

    # Checkpoint reference
    checkpoint_id: str | None = None

    # Metadata
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __post_init__(self):
        if self.expires_at is None and self.timeout_ms > 0:
            from datetime import timedelta

            self.expires_at = self.created_at + timedelta(milliseconds=self.timeout_ms)

    def is_expired(self) -> bool:
        """Check if request has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "interrupt_type": self.interrupt_type.value,
            "reason": self.reason,
            "details": self.details,
            "current_state": self.current_state.to_dict() if self.current_state else None,
            "timeout_ms": self.timeout_ms,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "checkpoint_id": self.checkpoint_id,
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class HITLResponse:
    """Response to a HITL request.

    Constitutional Hash: 608508a9bd224290
    """

    request_id: str
    action: HITLAction
    modified_state: GraphState | None = None
    user_input: JSONDict = field(default_factory=dict)
    responded_by: str = ""
    responded_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    reason: str = ""
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for serialization."""
        return {
            "request_id": self.request_id,
            "action": self.action.value,
            "modified_state": self.modified_state.to_dict() if self.modified_state else None,
            "user_input": self.user_input,
            "responded_by": self.responded_by,
            "responded_at": self.responded_at.isoformat(),
            "reason": self.reason,
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
        }


class InMemoryHITLHandler:
    """In-memory HITL handler for testing.

    Stores requests and allows programmatic responses.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, auto_response: HITLAction | None = None):
        self.pending_requests: dict[str, HITLRequest] = {}
        self.responses: dict[str, HITLResponse] = {}
        self._response_events: dict[str, asyncio.Event] = {}
        self.auto_response = auto_response
        self.request_history: list[HITLRequest] = []
        self.response_history: list[HITLResponse] = []

    async def request_human_input(
        self,
        request: HITLRequest,
    ) -> HITLResponse:
        """Wait for human input."""
        self.pending_requests[request.id] = request
        self.request_history.append(request)

        # Auto-respond if configured
        if self.auto_response:
            response = HITLResponse(
                request_id=request.id,
                action=self.auto_response,
                responded_by="auto_responder",
                reason="Auto-response",
            )
            self.response_history.append(response)
            del self.pending_requests[request.id]
            return response

        # Wait for response
        event = asyncio.Event()
        self._response_events[request.id] = event

        try:
            await asyncio.wait_for(
                event.wait(),
                timeout=request.timeout_ms / 1000.0,
            )
        except builtins.TimeoutError:
            raise TimeoutError(
                operation="hitl_request",
                timeout_ms=request.timeout_ms,
                context=f"Request {request.id} for workflow {request.workflow_id}",
            ) from None
        finally:
            self._response_events.pop(request.id, None)

        response = self.responses.get(request.id)
        if not response:
            raise InterruptError(
                interrupt_type=request.interrupt_type.value,
                reason="No response received",
                node_id=request.node_id,
                workflow_id=request.workflow_id,
            )

        self.pending_requests.pop(request.id, None)
        self.response_history.append(response)
        return response

    async def notify_timeout(self, request: HITLRequest) -> None:
        """Handle timeout notification."""
        logger.warning(f"HITL request {request.id} timed out")
        self.pending_requests.pop(request.id, None)

    def respond(self, request_id: str, response: HITLResponse) -> None:
        """Provide response to a pending request (for testing)."""
        self.responses[request_id] = response
        event = self._response_events.get(request_id)
        if event:
            event.set()


class HITLInterruptHandler:
    """Main HITL interrupt handler with full functionality.

    Manages HITL requests, timeouts, escalations, and audit logging.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        handler: InMemoryHITLHandler | None = None,
        config: HITLConfig | None = None,
        checkpoint_manager: object | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.handler = handler or InMemoryHITLHandler()
        self.config = config or HITLConfig()
        self.checkpoint_manager = checkpoint_manager
        self.constitutional_hash = constitutional_hash

        # Request tracking
        self._active_requests: dict[str, HITLRequest] = {}
        self._request_counts: dict[str, int] = {}  # workflow_id -> count
        self._last_request_time: dict[str, datetime] = {}

        # Audit log
        self._audit_log: list[JSONDict] = []

    async def create_interrupt(
        self,
        context: ExecutionContext,
        node_id: str,
        interrupt_type: InterruptType,
        reason: str,
        state: GraphState,
        details: JSONDict | None = None,
        timeout_ms: float | None = None,
    ) -> HITLRequest:
        """Create an interrupt request.

        Args:
            context: Execution context
            node_id: Node requesting interrupt
            interrupt_type: Type of interrupt
            reason: Reason for interrupt
            state: Current graph state
            details: Optional additional details
            timeout_ms: Optional timeout override

        Returns:
            Created HITL request

        Raises:
            InterruptError: If rate limit exceeded or HITL disabled
        """
        if not self.config.enabled:
            raise InterruptError(
                interrupt_type=interrupt_type.value,
                reason="HITL is disabled",
                node_id=node_id,
                workflow_id=context.workflow_id,
            )

        # Check rate limits
        workflow_count = self._request_counts.get(context.workflow_id, 0)
        if workflow_count >= self.config.max_requests_per_workflow:
            raise InterruptError(
                interrupt_type=interrupt_type.value,
                reason=f"Rate limit exceeded ({workflow_count} requests)",
                node_id=node_id,
                workflow_id=context.workflow_id,
            )

        # Check cooldown
        last_time = self._last_request_time.get(context.workflow_id)
        if last_time:
            elapsed = (datetime.now(UTC) - last_time).total_seconds() * 1000
            if elapsed < self.config.cooldown_ms:
                await asyncio.sleep((self.config.cooldown_ms - elapsed) / 1000)

        # Create checkpoint if manager available
        checkpoint_id = None
        if self.checkpoint_manager:
            checkpoint = await self.checkpoint_manager.create_checkpoint(
                context=context,
                node_id=node_id,
                state=state,
                metadata={"interrupt_type": interrupt_type.value, "reason": reason},
            )
            checkpoint_id = checkpoint.id

        # Create request
        request = HITLRequest(
            workflow_id=context.workflow_id,
            run_id=context.run_id,
            node_id=node_id,
            interrupt_type=interrupt_type,
            current_state=state,
            reason=reason,
            details=details or {},
            timeout_ms=timeout_ms or self.config.default_timeout_ms,
            checkpoint_id=checkpoint_id,
            constitutional_hash=self.constitutional_hash,
        )

        # Track request
        self._active_requests[request.id] = request
        self._request_counts[context.workflow_id] = workflow_count + 1
        self._last_request_time[context.workflow_id] = datetime.now(UTC)

        # Audit log
        if self.config.audit_all_requests:
            self._audit_log.append(
                {
                    "event": "hitl_request_created",
                    "request": request.to_dict(),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )

        logger.info(
            f"[{self.constitutional_hash}] Created HITL request {request.id} "
            f"for workflow {context.workflow_id} at node {node_id}"
        )

        return request

    async def handle_interrupt(
        self,
        request: HITLRequest,
    ) -> HITLResponse:
        """Handle an interrupt request and get response.

        Args:
            request: HITL request to handle

        Returns:
            Response from human or timeout handler

        Raises:
            InterruptError: If handling fails
            TimeoutError: If request times out
        """
        try:
            response = await self.handler.request_human_input(request)

            # Validate response
            if response.constitutional_hash != self.constitutional_hash:
                logger.warning(f"Response hash mismatch for request {request.id}, correcting")
                response.constitutional_hash = self.constitutional_hash

            # Audit log
            if self.config.audit_all_responses:
                self._audit_log.append(
                    {
                        "event": "hitl_response_received",
                        "response": response.to_dict(),
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )

            return response

        except TimeoutError:
            await self.handler.notify_timeout(request)

            # Handle timeout based on config
            if self.config.auto_continue_on_timeout:
                return HITLResponse(
                    request_id=request.id,
                    action=HITLAction.CONTINUE,
                    responded_by="timeout_handler",
                    reason="Auto-continue on timeout",
                )
            elif self.config.auto_abort_on_timeout:
                return HITLResponse(
                    request_id=request.id,
                    action=HITLAction.ABORT,
                    responded_by="timeout_handler",
                    reason="Auto-abort on timeout",
                )
            elif self.config.escalation_enabled:
                # Try escalation
                return await self._handle_escalation(request)
            else:
                raise

        finally:
            self._active_requests.pop(request.id, None)

    async def _handle_escalation(self, request: HITLRequest) -> HITLResponse:
        """Handle escalation when request times out.

        Args:
            request: Original request that timed out

        Returns:
            Response from escalation handler

        Raises:
            TimeoutError: If escalation also times out
        """
        escalation_request = HITLRequest(
            workflow_id=request.workflow_id,
            run_id=request.run_id,
            node_id=request.node_id,
            interrupt_type=InterruptType.HITL,
            current_state=request.current_state,
            reason=f"ESCALATION: {request.reason}",
            details={**request.details, "escalated_from": request.id},
            timeout_ms=self.config.escalation_timeout_ms,
            checkpoint_id=request.checkpoint_id,
            constitutional_hash=self.constitutional_hash,
        )

        self._audit_log.append(
            {
                "event": "hitl_escalation",
                "original_request_id": request.id,
                "escalation_request_id": escalation_request.id,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        try:
            return await self.handler.request_human_input(escalation_request)
        except TimeoutError:
            # Escalation also timed out
            raise TimeoutError(
                operation="hitl_escalation",
                timeout_ms=self.config.escalation_timeout_ms,
                context=f"Escalation for request {request.id}",
            ) from None

    def get_active_requests(
        self,
        workflow_id: str | None = None,
    ) -> list[HITLRequest]:
        """Get active HITL requests.

        Args:
            workflow_id: Optional filter by workflow

        Returns:
            List of active requests
        """
        requests = list(self._active_requests.values())
        if workflow_id:
            requests = [r for r in requests if r.workflow_id == workflow_id]
        return requests

    def get_audit_log(
        self,
        workflow_id: str | None = None,
        limit: int = 100,
    ) -> list[JSONDict]:
        """Get audit log entries.

        Args:
            workflow_id: Optional filter by workflow
            limit: Maximum entries to return

        Returns:
            List of audit log entries
        """
        log = self._audit_log
        if workflow_id:
            log = [
                e
                for e in log
                if e.get("request", {}).get("workflow_id") == workflow_id
                or e.get("response", {}).get("workflow_id") == workflow_id
            ]
        return log[-limit:]

    def clear_audit_log(self) -> int:
        """Clear audit log.

        Returns:
            Number of entries cleared
        """
        count = len(self._audit_log)
        self._audit_log = []
        return count


def create_hitl_handler(
    handler: InMemoryHITLHandler | None = None,
    config: HITLConfig | None = None,
    checkpoint_manager: object | None = None,
    auto_response: HITLAction | None = None,
    constitutional_hash: str = CONSTITUTIONAL_HASH,
) -> HITLInterruptHandler:
    """Factory function to create HITL handler.

    Args:
        handler: Optional custom HITL handler
        config: Optional HITL configuration
        checkpoint_manager: Optional checkpoint manager
        auto_response: Auto-response action for testing
        constitutional_hash: Constitutional hash to enforce

    Returns:
        Configured HITL interrupt handler

    Constitutional Hash: 608508a9bd224290
    """
    if auto_response and not handler:
        handler = InMemoryHITLHandler(auto_response=auto_response)

    return HITLInterruptHandler(
        handler=handler,
        config=config,
        checkpoint_manager=checkpoint_manager,
        constitutional_hash=constitutional_hash,
    )


# Backward-compatible alias
HITLHandler = HITLInterruptHandler

__all__ = [
    "HITLAction",
    "HITLConfig",
    "HITLHandler",
    "HITLInterruptHandler",
    "HITLRequest",
    "HITLResponse",
    "InMemoryHITLHandler",
    "create_hitl_handler",
]
