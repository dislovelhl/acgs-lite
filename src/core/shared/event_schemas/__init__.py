"""
ACGS-2 Versioned Event Schemas
Constitutional Hash: cdd01ef066bc6cf2

This package contains versioned event schemas for the ACGS-2 system.
Each schema type has multiple versions to support schema evolution
and backward/forward compatibility.

Event Types:
- AgentMessage: Messages exchanged between agents
- PolicyDecision: Policy evaluation decisions
- AuditEvent: Audit trail events
- ConstitutionalValidation: Constitutional compliance checks
- CircuitBreakerState: Circuit breaker state changes
- DecisionExplanation: FR-12 Decision explanation with factor attribution

Usage:
    from src.core.shared.event_schemas import (
        AgentMessageV1,
        AgentMessageV2,
        PolicyDecisionV1,
        AuditEventV1,
        ConstitutionalValidationV1,
        CircuitBreakerStateV1,
        DecisionExplanationV1,
        ExplanationFactor,
        CounterfactualHint,
    )

    # Create event
    event = AgentMessageV2(
        event_id="msg-123",
        event_type="agent_message",
        from_agent="agent-a",
        to_agent="agent-b",
        content={"action": "process"},
    )

    # Register all schemas
    from src.core.shared.event_schemas import register_all_schemas
    register_all_schemas()
"""

from src.core.shared.constants import CONSTITUTIONAL_HASH

# Import all schema versions
from .agent_message import (
    AgentMessageV1,
    AgentMessageV2,
    register_agent_message_schemas,
)
from .audit_event import (
    AuditEventV1,
    register_audit_event_schemas,
)
from .circuit_breaker_state import (
    CircuitBreakerStateV1,
    register_circuit_breaker_state_schemas,
)
from .constitutional_validation import (
    ConstitutionalValidationV1,
    register_constitutional_validation_schemas,
)
from .decision_explanation import (
    CounterfactualHint,
    DecisionExplanationV1,
    EUAIActTransparencyInfo,
    ExplanationFactor,
    GovernanceDimension,
    PredictedOutcome,
    create_decision_explanation,
)
from .policy_decision import (
    PolicyDecisionV1,
    register_policy_decision_schemas,
)


def register_decision_explanation_schemas() -> None:
    """Register decision explanation schemas with the global registry.

    Only DecisionExplanationV1 is registered as it extends EventSchemaBase.
    Nested models (ExplanationFactor, CounterfactualHint, EUAIActTransparencyInfo)
    are plain Pydantic BaseModels and don't require registry registration.
    """
    from ..schema_registry import SchemaRegistry

    registry = SchemaRegistry()
    registry.register(DecisionExplanationV1)


def register_all_schemas() -> None:
    """Register all event schemas with the global registry."""
    register_agent_message_schemas()
    register_policy_decision_schemas()
    register_audit_event_schemas()
    register_constitutional_validation_schemas()
    register_circuit_breaker_state_schemas()
    register_decision_explanation_schemas()


__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    # Agent Message
    "AgentMessageV1",
    "AgentMessageV2",
    # Audit Event
    "AuditEventV1",
    # Circuit Breaker State
    "CircuitBreakerStateV1",
    # Constitutional Validation
    "ConstitutionalValidationV1",
    "CounterfactualHint",
    # Decision Explanation (FR-12)
    "DecisionExplanationV1",
    "EUAIActTransparencyInfo",
    "ExplanationFactor",
    "GovernanceDimension",
    # Policy Decision
    "PolicyDecisionV1",
    "PredictedOutcome",
    "create_decision_explanation",
    "register_agent_message_schemas",
    # Registration
    "register_all_schemas",
    "register_audit_event_schemas",
    "register_circuit_breaker_state_schemas",
    "register_constitutional_validation_schemas",
    "register_decision_explanation_schemas",
    "register_policy_decision_schemas",
]
