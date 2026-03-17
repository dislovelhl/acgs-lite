"""
ACGS-2 Constitutional Validation Event Schemas
Constitutional Hash: cdd01ef066bc6cf2

Versioned schemas for constitutional compliance validation events.
Records the outcomes of constitutional AI governance checks.

Version History:
- V1 (1.0.0): Constitutional validation with principles and compliance tracking
"""

from enum import StrEnum
from typing import Any, ClassVar

from pydantic import Field

from src.core.shared.schema_registry import (
    EventSchemaBase,
    SchemaCompatibility,
    SchemaStatus,
    SchemaVersion,
    get_schema_registry,
)
from src.core.shared.types import JSONDict

# =============================================================================
# Enums
# =============================================================================


class ValidationOutcome(StrEnum):
    """Outcome of constitutional validation."""

    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    CONDITIONALLY_COMPLIANT = "conditionally_compliant"
    REQUIRES_REVIEW = "requires_review"
    ERROR = "error"
    SKIPPED = "skipped"


class ValidationMode(StrEnum):
    """Mode of validation."""

    STRICT = "strict"  # All principles must pass
    LENIENT = "lenient"  # Warnings allowed
    ADVISORY = "advisory"  # Non-blocking validation
    AUDIT = "audit"  # Record-only mode


class PrincipleCategory(StrEnum):
    """Categories of constitutional principles."""

    SAFETY = "safety"
    ETHICS = "ethics"
    PRIVACY = "privacy"
    FAIRNESS = "fairness"
    TRANSPARENCY = "transparency"
    ACCOUNTABILITY = "accountability"
    SECURITY = "security"
    GOVERNANCE = "governance"


class ValidationTrigger(StrEnum):
    """What triggered the validation."""

    MESSAGE_RECEIVED = "message_received"
    ACTION_PROPOSED = "action_proposed"
    POLICY_CHANGE = "policy_change"
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    ESCALATION = "escalation"
    CONSENSUS = "consensus"


# =============================================================================
# Supporting Models
# =============================================================================


class PrincipleViolation(EventSchemaBase):
    """Details of a constitutional principle violation."""

    SCHEMA_NAME: ClassVar[str] = "PrincipleViolation"
    SCHEMA_VERSION: ClassVar[SchemaVersion] = SchemaVersion(1, 0, 0)

    principle_id: str = Field(..., description="Identifier of the violated principle")
    principle_name: str = Field(..., description="Human-readable principle name")
    category: PrincipleCategory = Field(..., description="Category of the principle")
    severity: str = Field(
        default="high",
        description="Severity of the violation (low, medium, high, critical)",
    )
    description: str = Field(
        default="",
        description="Description of how the principle was violated",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Evidence supporting the violation finding",
    )
    remediation_suggestions: list[str] = Field(
        default_factory=list,
        description="Suggested actions to remediate the violation",
    )

    model_config: ClassVar[dict[str, Any]] = {"from_attributes": True}


# =============================================================================
# V1: Constitutional Validation (1.0.0)
# =============================================================================


class ConstitutionalValidationV1(EventSchemaBase):
    """
    Constitutional Validation Schema V1 - Records constitutional compliance checks.

    Constitutional Hash: cdd01ef066bc6cf2

    Captures the full context of a constitutional validation including:
    - Validation outcome and mode
    - Principles evaluated and violations found
    - Deliberation and consensus information
    - Remediation actions taken
    """

    SCHEMA_NAME: ClassVar[str] = "ConstitutionalValidation"
    SCHEMA_VERSION: ClassVar[SchemaVersion] = SchemaVersion(1, 0, 0)

    # Validation identification
    validation_id: str | None = Field(
        default=None,
        description="Unique identifier for this validation",
    )

    # Subject being validated
    subject_type: str = Field(
        ...,
        description="Type of subject being validated (message, action, policy, agent)",
    )
    subject_id: str = Field(..., description="Identifier of the subject")
    subject_content: JSONDict = Field(
        default_factory=dict,
        description="Content/data being validated",
    )

    # Validation configuration
    validation_mode: ValidationMode = Field(
        default=ValidationMode.STRICT,
        description="Mode of validation",
    )
    trigger: ValidationTrigger = Field(
        default=ValidationTrigger.MESSAGE_RECEIVED,
        description="What triggered this validation",
    )

    # Outcome
    outcome: ValidationOutcome = Field(..., description="Validation outcome")
    overall_compliance_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Overall compliance score (0.0-1.0)",
    )
    is_compliant: bool = Field(
        default=True,
        description="Simple boolean compliance flag",
    )

    # Principles evaluated
    principles_evaluated: list[str] = Field(
        default_factory=list,
        description="List of principle IDs that were evaluated",
    )
    principles_passed: list[str] = Field(
        default_factory=list,
        description="List of principle IDs that passed",
    )
    principles_failed: list[str] = Field(
        default_factory=list,
        description="List of principle IDs that failed",
    )
    principles_warned: list[str] = Field(
        default_factory=list,
        description="List of principle IDs with warnings",
    )

    # Detailed violations
    violations: list[JSONDict] = Field(
        default_factory=list,
        description="Detailed violation information",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Warning messages",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Error messages during validation",
    )

    # Deliberation (for high-impact validations)
    required_deliberation: bool = Field(
        default=False,
        description="Whether deliberation was required",
    )
    deliberation_id: str | None = Field(
        default=None,
        description="Deliberation session ID if applicable",
    )
    deliberation_outcome: str | None = Field(
        default=None,
        description="Outcome of deliberation",
    )
    consensus_reached: bool | None = Field(
        default=None,
        description="Whether consensus was reached",
    )
    participating_agents: list[str] = Field(
        default_factory=list,
        description="Agents that participated in deliberation",
    )

    # Human-in-the-loop
    requires_human_review: bool = Field(
        default=False,
        description="Whether human review is required",
    )
    human_reviewer_id: str | None = Field(
        default=None,
        description="ID of human reviewer if assigned",
    )
    human_decision: str | None = Field(
        default=None,
        description="Human override decision",
    )
    human_decision_reason: str | None = Field(
        default=None,
        description="Reason for human decision",
    )

    # Impact assessment
    impact_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Impact score that triggered validation (0.0-1.0)",
    )
    risk_assessment: JSONDict = Field(
        default_factory=dict,
        description="Risk assessment details",
    )

    # Remediation
    remediation_actions: list[JSONDict] = Field(
        default_factory=list,
        description="Remediation actions taken or recommended",
    )
    is_remediated: bool = Field(
        default=False,
        description="Whether issues have been remediated",
    )

    # Context
    tenant_id: str = Field(
        default="default",
        description="Tenant identifier",
    )
    session_id: str | None = Field(
        default=None,
        description="Session identifier",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Correlation ID for tracing",
    )
    evaluation_context: JSONDict = Field(
        default_factory=dict,
        description="Additional context for evaluation",
    )

    # Performance
    validation_duration_ms: float | None = Field(
        default=None,
        description="Time taken to complete validation in milliseconds",
    )
    deliberation_duration_ms: float | None = Field(
        default=None,
        description="Time spent in deliberation in milliseconds",
    )

    # Chain of custody
    validator_id: str = Field(
        default="constitutional-validator",
        description="ID of the validating component",
    )
    validator_version: str = Field(
        default="1.0.0",
        description="Version of the validator",
    )

    model_config: ClassVar[dict[str, Any]] = {"from_attributes": True}


# =============================================================================
# Registration
# =============================================================================


def register_constitutional_validation_schemas() -> None:
    """Register all ConstitutionalValidation schema versions with the registry."""
    registry = get_schema_registry()

    # Register V1
    registry.register(
        ConstitutionalValidationV1,
        status=SchemaStatus.ACTIVE,
        compatibility_mode=SchemaCompatibility.BACKWARD,
        description="Constitutional compliance validation with deliberation support",
    )


__all__ = [
    "ConstitutionalValidationV1",
    "PrincipleCategory",
    "PrincipleViolation",
    "ValidationMode",
    "ValidationOutcome",
    "ValidationTrigger",
    "register_constitutional_validation_schemas",
]
