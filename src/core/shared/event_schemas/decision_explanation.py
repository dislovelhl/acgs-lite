"""
ACGS-2 Decision Explanation Event Schema
Constitutional Hash: cdd01ef066bc6cf2

Implements FR-12 Decision Explanation API requirements from v2.3 specification.
Provides structured factor attribution, 7-dimensional governance vector,
counterfactual analysis hints, and EU AI Act Article 13 transparency compliance.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator

from ..schema_registry import CONSTITUTIONAL_HASH, EventSchemaBase, SchemaVersion

# Type alias for JSON-compatible dictionaries
JSONDict = dict[str, object]


class GovernanceDimension(StrEnum):
    """7-dimensional governance vector dimensions."""

    SAFETY = "safety"
    SECURITY = "security"
    PRIVACY = "privacy"
    FAIRNESS = "fairness"
    RELIABILITY = "reliability"
    TRANSPARENCY = "transparency"
    EFFICIENCY = "efficiency"


class PredictedOutcome(StrEnum):
    """Predicted outcomes for counterfactual analysis."""

    ALLOW = "allow"
    DENY = "deny"
    CONDITIONAL = "conditional"
    ESCALATE = "escalate"


class ExplanationFactor(BaseModel):
    """
    Individual factor contributing to a governance decision.

    Each factor represents a scored dimension of the decision-making process,
    with supporting evidence and explanation for transparency.
    """

    factor_id: str = Field(..., description="Unique identifier for this factor")
    factor_name: str = Field(
        ..., description="Human-readable name of the factor (e.g., 'safety_score')"
    )
    factor_value: float = Field(
        ..., ge=0.0, le=1.0, description="Normalized score for this factor (0.0-1.0)"
    )
    factor_weight: float = Field(
        default=1.0,
        ge=0.0,
        le=10.0,
        description="Weight applied to this factor in final decision",
    )
    explanation: str = Field(
        ..., description="Human-readable explanation of how this factor was calculated"
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Supporting evidence items for this factor's score",
    )
    governance_dimension: GovernanceDimension = Field(
        ..., description="Which of the 7 governance dimensions this factor maps to"
    )
    source_component: str = Field(
        default="impact_scorer",
        description="Component that calculated this factor (e.g., 'semantic_scorer', 'permission_checker')",
    )
    calculation_method: str = Field(
        default="",
        description="Method used to calculate factor (e.g., 'cosine_similarity', 'rule_matching')",
    )

    model_config = {"frozen": False, "extra": "allow"}


class CounterfactualHint(BaseModel):
    """
    Counterfactual analysis hint showing alternative decision paths.

    Provides "what-if" scenarios to help users understand how modifying
    input factors would affect the governance decision outcome.
    """

    scenario_id: str = Field(..., description="Unique identifier for this scenario")
    scenario_description: str = Field(
        default="",
        description="Human-readable description of the counterfactual scenario",
    )
    modified_factor: str = Field(
        ..., description="Name of the factor that was modified in this scenario"
    )
    original_value: float = Field(..., ge=0.0, le=1.0, description="Original value of the factor")
    modified_value: float = Field(
        ..., ge=0.0, le=1.0, description="Hypothetical modified value of the factor"
    )
    predicted_outcome: PredictedOutcome = Field(
        ..., description="Predicted decision outcome with the modified factor"
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence level in the predicted outcome",
    )
    threshold_crossed: str | None = Field(
        default=None,
        description="Name of threshold that would be crossed with modification",
    )
    impact_delta: float = Field(
        default=0.0,
        description="Change in overall impact score with this modification",
    )

    model_config = {"frozen": False, "extra": "allow"}


class EUAIActTransparencyInfo(BaseModel):
    """
    EU AI Act Article 13 transparency compliance information.

    Provides required transparency data for AI systems operating
    under EU AI Act regulations.
    """

    article_13_compliant: bool = Field(
        default=True, description="Whether this decision meets Article 13 requirements"
    )
    human_oversight_level: str = Field(
        default="human-in-the-loop",
        description="Level of human oversight applied (human-in-the-loop, human-on-the-loop, human-in-command)",
    )
    risk_category: str = Field(
        default="limited",
        description="EU AI Act risk category (minimal, limited, high, unacceptable)",
    )
    transparency_measures: list[str] = Field(
        default_factory=list,
        description="List of transparency measures implemented",
    )
    data_governance_info: JSONDict = Field(
        default_factory=dict,
        description="Information about data governance practices",
    )
    technical_documentation_ref: str = Field(
        default="",
        description="Reference to technical documentation for the AI system",
    )
    conformity_assessment_status: str = Field(
        default="pending",
        description="Status of conformity assessment (pending, in_progress, completed, not_required)",
    )
    intended_purpose: str = Field(
        default="",
        description="Intended purpose of the AI system making the decision",
    )
    limitations_and_risks: list[str] = Field(
        default_factory=list,
        description="Known limitations and residual risks of the AI system",
    )
    human_reviewers: list[str] = Field(
        default_factory=list,
        description="List of human reviewers involved in oversight",
    )

    model_config = {"frozen": False, "extra": "allow"}


class DecisionExplanationV1(EventSchemaBase):
    """
    Complete decision explanation with factor attribution and counterfactual analysis.

    This schema implements FR-12 Decision Explanation API requirements,
    providing structured explanations for governance decisions including:
    - 7-dimensional governance vector scores
    - Individual factor attributions with evidence
    - Counterfactual "what-if" analysis hints
    - EU AI Act Article 13 transparency compliance

    Constitutional Hash: cdd01ef066bc6cf2
    """

    SCHEMA_NAME: ClassVar[str] = "DecisionExplanation"
    SCHEMA_VERSION: ClassVar[SchemaVersion] = SchemaVersion(1, 0, 0)

    # Core decision identification
    decision_id: str = Field(..., description="Unique identifier of the decision being explained")
    message_id: str | None = Field(
        default=None, description="ID of the message that triggered this decision"
    )
    request_id: str | None = Field(default=None, description="Correlation ID for request tracing")

    # Decision outcome
    verdict: str = Field(
        ..., description="Final decision verdict (ALLOW, DENY, CONDITIONAL, ESCALATE)"
    )
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Overall confidence in the decision"
    )
    impact_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Overall impact score for the decision"
    )

    # 7-dimensional governance vector
    governance_vector: dict[str, float] = Field(
        default_factory=lambda: {
            "safety": 0.0,
            "security": 0.0,
            "privacy": 0.0,
            "fairness": 0.0,
            "reliability": 0.0,
            "transparency": 0.0,
            "efficiency": 0.0,
        },
        description="7-dimensional governance impact vector with scores 0.0-1.0",
    )

    # Factor attribution
    factors: list[ExplanationFactor] = Field(
        default_factory=list,
        description="List of factors contributing to the decision with attributions",
    )
    primary_factors: list[str] = Field(
        default_factory=list,
        description="IDs of the top factors that most influenced the decision",
    )

    # Counterfactual analysis
    counterfactual_hints: list[CounterfactualHint] = Field(
        default_factory=list,
        description="What-if scenarios showing how decision might change",
    )
    counterfactuals_generated: bool = Field(
        default=False, description="Whether counterfactual analysis was performed"
    )

    # Rules and policies
    matched_rules: list[str] = Field(
        default_factory=list, description="Policy rules that matched this decision"
    )
    violated_rules: list[str] = Field(
        default_factory=list, description="Policy rules that were violated"
    )
    applicable_policies: list[str] = Field(
        default_factory=list, description="Policies applicable to this decision"
    )

    # Human-readable explanation
    summary: str = Field(default="", description="Brief human-readable summary of the decision")
    detailed_reasoning: str = Field(
        default="", description="Detailed explanation of the decision reasoning"
    )

    # EU AI Act compliance
    euaiact_article13_info: EUAIActTransparencyInfo = Field(
        default_factory=EUAIActTransparencyInfo,
        description="EU AI Act Article 13 transparency information",
    )

    # Processing metadata
    processing_time_ms: float = Field(
        default=0.0, ge=0.0, description="Time taken to generate explanation in milliseconds"
    )
    explanation_generated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when explanation was generated",
    )
    explanation_version: str = Field(
        default="v1.0.0", description="Version of the explanation format"
    )

    # Tenant and scope
    tenant_id: str | None = Field(default=None, description="Tenant identifier for multi-tenancy")
    scope: str = Field(
        default="decision", description="Scope of the explanation (decision, batch, aggregate)"
    )

    # Audit trail
    audit_references: list[str] = Field(
        default_factory=list,
        description="References to related audit trail entries",
    )

    @field_validator("governance_vector")
    @classmethod
    def validate_governance_vector(cls, v: dict[str, float]) -> dict[str, float]:
        """Ensure all 7 governance dimensions are present and valid."""
        required_dims = {
            "safety",
            "security",
            "privacy",
            "fairness",
            "reliability",
            "transparency",
            "efficiency",
        }
        missing = required_dims - set(v.keys())
        if missing:
            # Add missing dimensions with default 0.0
            for dim in missing:
                v[dim] = 0.0
        # Validate all values are in range
        for dim, score in v.items():
            if not 0.0 <= score <= 1.0:
                raise ValueError(
                    f"Governance vector dimension '{dim}' score must be between 0.0 and 1.0"
                )
        return v

    @field_validator("verdict")
    @classmethod
    def validate_verdict(cls, v: str) -> str:
        """Validate verdict is one of the allowed values."""
        allowed = {
            "ALLOW",
            "DENY",
            "CONDITIONAL",
            "ESCALATE",
            "allow",
            "deny",
            "conditional",
            "escalate",
        }
        if v not in allowed:
            raise ValueError("Verdict must be one of: ALLOW, DENY, CONDITIONAL, ESCALATE")
        return v.upper()

    def get_primary_governance_concerns(self, threshold: float = 0.7) -> list[str]:
        """Get governance dimensions that exceed the concern threshold."""
        return [dim for dim, score in self.governance_vector.items() if score >= threshold]

    def get_factor_by_dimension(self, dimension: GovernanceDimension) -> list[ExplanationFactor]:
        """Get all factors for a specific governance dimension."""
        return [f for f in self.factors if f.governance_dimension == dimension]

    def calculate_weighted_score(self) -> float:
        """Calculate weighted average of all factor scores."""
        if not self.factors:
            return self.confidence_score
        total_weight = sum(f.factor_weight for f in self.factors)
        if total_weight == 0:
            return self.confidence_score
        weighted_sum = sum(f.factor_value * f.factor_weight for f in self.factors)
        return weighted_sum / total_weight


# Factory function for creating explanation from decision components
def create_decision_explanation(
    decision_id: str,
    verdict: str,
    confidence_score: float,
    governance_vector: dict[str, float],
    factors: list[JSONDict] | None = None,
    counterfactuals: list[JSONDict] | None = None,
    message_id: str | None = None,
    tenant_id: str | None = None,
) -> DecisionExplanationV1:
    """
    Factory function to create a DecisionExplanationV1 from components.

    Args:
        decision_id: Unique decision identifier
        verdict: Decision outcome (ALLOW, DENY, CONDITIONAL, ESCALATE)
        confidence_score: Overall confidence (0.0-1.0)
        governance_vector: 7-dimensional governance scores
        factors: Optional list of factor dictionaries
        counterfactuals: Optional list of counterfactual dictionaries
        message_id: Optional related message ID
        tenant_id: Optional tenant identifier

    Returns:
        Fully populated DecisionExplanationV1 instance
    """
    import uuid

    explanation = DecisionExplanationV1(
        event_id=str(uuid.uuid4()),
        event_type="decision_explanation",
        decision_id=decision_id,
        message_id=message_id,
        verdict=verdict,
        confidence_score=confidence_score,
        governance_vector=governance_vector,
        tenant_id=tenant_id,
        constitutional_hash=CONSTITUTIONAL_HASH,
    )

    # Add factors if provided
    if factors:
        for factor_data in factors:
            factor = ExplanationFactor(**factor_data)
            explanation.factors.append(factor)

    # Add counterfactuals if provided
    if counterfactuals:
        for cf_data in counterfactuals:
            cf = CounterfactualHint(**cf_data)
            explanation.counterfactual_hints.append(cf)
        explanation.counterfactuals_generated = True

    return explanation
