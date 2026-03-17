"""
ACGS-2 Policy Decision Event Schemas
Constitutional Hash: cdd01ef066bc6cf2

Versioned schemas for policy evaluation decision events.
Records the outcome of policy evaluations for audit and compliance.

Version History:
- V1 (1.0.0): Policy decision with verdict, reasoning, and compliance info
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


class PolicyVerdict(StrEnum):
    """Outcome of a policy evaluation."""

    ALLOW = "allow"
    DENY = "deny"
    CONDITIONAL = "conditional"
    ABSTAIN = "abstain"
    ERROR = "error"


class PolicyDecisionSource(StrEnum):
    """Source of the policy decision."""

    OPA = "opa"  # Open Policy Agent
    REGO = "rego"  # Rego policy engine
    CONSTITUTIONAL = "constitutional"  # Constitutional AI rules
    MACI = "maci"  # Multi-Agent Constitutional Intelligence
    MANUAL = "manual"  # Human override
    CACHED = "cached"  # Cached decision


class ComplianceLevel(StrEnum):
    """Level of compliance for the decision."""

    FULL = "full"
    PARTIAL = "partial"
    NON_COMPLIANT = "non_compliant"
    UNKNOWN = "unknown"


# =============================================================================
# V1: Policy Decision (1.0.0)
# =============================================================================


class PolicyDecisionV1(EventSchemaBase):
    """
    Policy Decision Schema V1 - Records policy evaluation outcomes.

    Constitutional Hash: cdd01ef066bc6cf2

    Captures the full context of a policy decision including:
    - The verdict (allow/deny/conditional)
    - Reasoning and explanations
    - Compliance information
    - Audit trail data
    """

    SCHEMA_NAME: ClassVar[str] = "PolicyDecision"
    SCHEMA_VERSION: ClassVar[SchemaVersion] = SchemaVersion(1, 0, 0)

    # Decision identification
    decision_id: str | None = Field(
        default=None,
        description="Unique identifier for this decision",
    )
    policy_id: str = Field(..., description="Identifier of the evaluated policy")
    policy_version: str = Field(
        default="latest",
        description="Version of the policy used",
    )

    # Subject and context
    subject_id: str = Field(..., description="Identifier of the subject being evaluated")
    subject_type: str = Field(
        default="agent",
        description="Type of subject (agent, user, service)",
    )
    resource_id: str | None = Field(
        default=None,
        description="Resource being accessed",
    )
    action: str = Field(..., description="Action being evaluated")

    # Decision outcome
    verdict: PolicyVerdict = Field(..., description="Policy decision verdict")
    decision_source: PolicyDecisionSource = Field(
        default=PolicyDecisionSource.OPA,
        description="Source of the decision",
    )

    # Reasoning and explanation
    reasoning: str = Field(
        default="",
        description="Human-readable explanation of the decision",
    )
    matched_rules: list[str] = Field(
        default_factory=list,
        description="List of policy rules that matched",
    )
    violated_rules: list[str] = Field(
        default_factory=list,
        description="List of policy rules that were violated",
    )

    # Compliance
    compliance_level: ComplianceLevel = Field(
        default=ComplianceLevel.UNKNOWN,
        description="Level of compliance",
    )
    compliance_frameworks: list[str] = Field(
        default_factory=list,
        description="Applicable compliance frameworks (GDPR, SOC2, etc.)",
    )

    # Confidence and scoring
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence in the decision (0.0-1.0)",
    )
    risk_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Risk score for the action (0.0-1.0)",
    )

    # Context
    evaluation_context: JSONDict = Field(
        default_factory=dict,
        description="Context data used in evaluation",
    )
    tenant_id: str = Field(
        default="default",
        description="Tenant identifier",
    )

    # Performance
    evaluation_duration_ms: float | None = Field(
        default=None,
        description="Time taken to evaluate policy in milliseconds",
    )

    # Audit
    audit_trail: list[JSONDict] = Field(
        default_factory=list,
        description="Audit trail of evaluation steps",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Correlation ID for request tracing",
    )

    # Conditions (for conditional verdicts)
    conditions: list[JSONDict] = Field(
        default_factory=list,
        description="Conditions for conditional verdicts",
    )

    model_config: ClassVar[dict[str, Any]] = {"from_attributes": True}


# =============================================================================
# Registration
# =============================================================================


def register_policy_decision_schemas() -> None:
    """Register all PolicyDecision schema versions with the registry."""
    registry = get_schema_registry()

    # Register V1
    registry.register(
        PolicyDecisionV1,
        status=SchemaStatus.ACTIVE,
        compatibility_mode=SchemaCompatibility.BACKWARD,
        description="Policy evaluation decision with compliance tracking",
    )


__all__ = [
    "ComplianceLevel",
    "PolicyDecisionSource",
    "PolicyDecisionV1",
    "PolicyVerdict",
    "register_policy_decision_schemas",
]
