from __future__ import annotations

from dataclasses import dataclass

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .governance_core import GovernanceDecision, GovernanceInput, GovernanceReceipt
from .models import AgentMessage
from .session_context import SessionContext
from .validators import ValidationResult


@dataclass(slots=True)
class MessageProcessingContext:
    """Explicit runtime state for a single MessageProcessor invocation.

    Keeps governance and verification artifacts off the mutable ``AgentMessage`` instance so
    processing stages can pass state explicitly and finalizers can behave consistently.
    """

    message: AgentMessage
    start_time: float
    session_context: SessionContext | None = None
    governance_input: GovernanceInput | None = None
    governance_decision: GovernanceDecision | None = None
    governance_receipt: GovernanceReceipt | None = None
    governance_shadow_metadata: JSONDict | None = None
    cache_key: str | None = None
    cached_result: ValidationResult | None = None
