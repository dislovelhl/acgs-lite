"""
ACGS-2 Decision Explanation API Routes
Constitutional Hash: cdd01ef066bc6cf2

Implements FR-12 Decision Explanation API endpoints for structured
factor attribution, governance vector analysis, and counterfactual reasoning.
"""

import uuid
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.core.shared.api_versioning import create_versioned_router
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.metrics import track_request_metrics
from src.core.shared.security.auth import UserClaims, get_current_user
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

logger = get_logger(__name__)


# ============================================================================
# Response Models
# ============================================================================


class ExplanationFactorResponse(BaseModel):
    """Individual factor in a decision explanation."""

    factor_id: str = Field(..., description="Unique factor identifier")
    factor_name: str = Field(..., description="Human-readable factor name")
    factor_value: float = Field(..., ge=0.0, le=1.0, description="Factor score (0-1)")
    factor_weight: float = Field(..., ge=0.0, description="Factor weight in decision")
    explanation: str = Field(..., description="Explanation of factor calculation")
    evidence: list[str] = Field(default_factory=list, description="Supporting evidence")
    governance_dimension: str = Field(..., description="Governance dimension")
    source_component: str = Field(default="", description="Source component")
    calculation_method: str = Field(default="", description="Calculation method")


class CounterfactualHintResponse(BaseModel):
    """Counterfactual analysis hint."""

    scenario_id: str = Field(..., description="Unique scenario identifier")
    scenario_description: str = Field(default="", description="Scenario description")
    modified_factor: str = Field(..., description="Modified factor name")
    original_value: float = Field(..., ge=0.0, le=1.0)
    modified_value: float = Field(..., ge=0.0, le=1.0)
    predicted_outcome: str = Field(..., description="Predicted outcome")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    threshold_crossed: str | None = Field(default=None)
    impact_delta: float = Field(default=0.0)


class EUAIActInfoResponse(BaseModel):
    """EU AI Act Article 13 transparency information."""

    article_13_compliant: bool = Field(default=True)
    human_oversight_level: str = Field(default="human-on-the-loop")
    risk_category: str = Field(default="limited")
    transparency_measures: list[str] = Field(default_factory=list)
    data_governance_info: JSONDict = Field(default_factory=dict)
    technical_documentation_ref: str = Field(default="")
    conformity_assessment_status: str = Field(default="pending")
    intended_purpose: str = Field(default="")
    limitations_and_risks: list[str] = Field(default_factory=list)
    human_reviewers: list[str] = Field(default_factory=list)


class DecisionExplanationResponse(BaseModel):
    """Complete decision explanation response."""

    # Core identification
    decision_id: str = Field(..., description="Unique decision identifier")
    message_id: str | None = Field(default=None, description="Related message ID")
    request_id: str | None = Field(default=None, description="Correlation ID")

    # Decision outcome
    verdict: str = Field(..., description="Decision verdict (ALLOW, DENY, CONDITIONAL, ESCALATE)")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    impact_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Impact score")

    # 7-dimensional governance vector
    governance_vector: dict[str, float] = Field(
        ...,
        description="7-dimensional governance vector (safety, security, privacy, fairness, reliability, transparency, efficiency)",
    )

    # Factor attribution
    factors: list[ExplanationFactorResponse] = Field(
        default_factory=list, description="Contributing factors"
    )
    primary_factors: list[str] = Field(default_factory=list, description="IDs of primary factors")

    # Counterfactual analysis
    counterfactual_hints: list[CounterfactualHintResponse] = Field(
        default_factory=list, description="Counterfactual hints"
    )
    counterfactuals_generated: bool = Field(default=False)

    # Rules and policies
    matched_rules: list[str] = Field(default_factory=list)
    violated_rules: list[str] = Field(default_factory=list)
    applicable_policies: list[str] = Field(default_factory=list)

    # Human-readable explanation
    summary: str = Field(default="", description="Brief summary")
    detailed_reasoning: str = Field(default="", description="Detailed reasoning")

    # EU AI Act compliance
    euaiact_article13_info: EUAIActInfoResponse = Field(default_factory=EUAIActInfoResponse)

    # Metadata
    processing_time_ms: float = Field(default=0.0, ge=0.0)
    explanation_generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    explanation_version: str = Field(default="v1.0.0")
    tenant_id: str | None = Field(default=None)
    scope: str = Field(default="decision")
    audit_references: list[str] = Field(default_factory=list)

    # Constitutional compliance
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)


class ExplainDecisionRequest(BaseModel):
    """Request to generate explanation for a message/action."""

    message: JSONDict = Field(..., description="Message or action to explain")
    verdict: str = Field(..., description="Decision verdict")
    context: JSONDict = Field(default_factory=dict, description="Additional context")
    include_counterfactuals: bool = Field(
        default=True, description="Include counterfactual analysis"
    )


class ExplainDecisionResponse(BaseModel):
    """Response for generate explanation request."""

    explanation: DecisionExplanationResponse
    stored: bool = Field(default=False, description="Whether explanation was persisted")


# ============================================================================
# Router Configuration
# ============================================================================

decisions_v1_router = create_versioned_router(
    prefix="/decisions",
    version="v1",
    tags=["Decisions (v1)"],
)


# ============================================================================
# Endpoints
# ============================================================================


@decisions_v1_router.get(
    "/{decision_id}/explain",
    response_model=DecisionExplanationResponse,
    summary="Get Decision Explanation",
    description="""
    Retrieve structured explanation for a governance decision.

    Implements FR-12 Decision Explanation API requirements including:
    - Factor attribution with evidence
    - 7-dimensional governance vector
    - Counterfactual analysis hints
    - EU AI Act Article 13 transparency compliance

    Constitutional Hash: cdd01ef066bc6cf2
    """,
)
@track_request_metrics("api-gateway", "/api/v1/decisions/{decision_id}/explain")
async def get_decision_explanation(
    decision_id: str,
    include_counterfactuals: bool = Query(
        default=True, description="Include counterfactual analysis"
    ),
    user: UserClaims = Depends(get_current_user),
) -> DecisionExplanationResponse:
    """
    Get structured explanation for a governance decision.

    Args:
        decision_id: Unique decision identifier.
        include_counterfactuals: Whether to include counterfactual hints.
        user: Authenticated user claims.

    Returns:
        DecisionExplanationResponse with full explanation data.

    Raises:
        HTTPException 404: If decision not found.
        HTTPException 403: If user doesn't have access to the decision.
    """
    try:
        # MD-010: use ExplanationServiceAdapter (satisfies ExplanationPort)
        from packages.enhanced_agent_bus.facades.agent_bus_facade import ExplanationServiceAdapter

        service: ExplanationServiceAdapter = ExplanationServiceAdapter()

        # Try to retrieve stored explanation
        explanation = await service.get_explanation(
            decision_id=decision_id,
            tenant_id=user.tenant_id or "default",
        )

        if explanation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "decision_not_found",
                    "message": f"No explanation found for decision {decision_id}",
                    "decision_id": decision_id,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

        # Convert to response model
        response = _convert_to_response(explanation, include_counterfactuals)

        logger.info(
            "Decision explanation retrieved",
            decision_id=decision_id,
            user_id=user.sub,
            tenant_id=user.tenant_id,
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error retrieving decision explanation",
            decision_id=decision_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "explanation_retrieval_failed",
                "message": "An internal error occurred while retrieving the explanation.",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        ) from e


@decisions_v1_router.post(
    "/explain",
    response_model=ExplainDecisionResponse,
    summary="Generate Decision Explanation",
    description="""
    Generate a structured explanation for a governance decision.

    Use this endpoint to create explanations for new decisions that
    haven't been stored yet, or to get explanations without persistence.

    Constitutional Hash: cdd01ef066bc6cf2
    """,
)
@track_request_metrics("api-gateway", "/api/v1/decisions/explain")
async def generate_decision_explanation(
    request: ExplainDecisionRequest,
    user: UserClaims = Depends(get_current_user),
) -> ExplainDecisionResponse:
    """
    Generate a structured explanation for a decision.

    Args:
        request: Explanation request with message, verdict, and context.
        user: Authenticated user claims.

    Returns:
        ExplainDecisionResponse with generated explanation.
    """
    try:
        # MD-010: use ExplanationServiceAdapter (satisfies ExplanationPort)
        from packages.enhanced_agent_bus.facades.agent_bus_facade import (
            ExplanationService,
            ExplanationServiceAdapter,
        )

        service: ExplanationServiceAdapter = ExplanationServiceAdapter(
            ExplanationService(enable_counterfactuals=request.include_counterfactuals)
        )

        # Generate explanation
        decision_id = str(uuid.uuid4())
        explanation = await service.generate_explanation(
            message=request.message,
            verdict=request.verdict,
            context=request.context,
            decision_id=decision_id,
            tenant_id=user.tenant_id,
            store_explanation=True,  # Persist for later retrieval
        )

        # Convert to response
        response = _convert_to_response(explanation, request.include_counterfactuals)

        logger.info(
            "Decision explanation generated",
            decision_id=decision_id,
            user_id=user.sub,
            tenant_id=user.tenant_id,
            verdict=request.verdict,
        )

        return ExplainDecisionResponse(
            explanation=response,
            stored=True,
        )

    except Exception as e:
        logger.error(
            "Error generating decision explanation",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "explanation_generation_failed",
                "message": "An internal error occurred while generating the explanation.",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        ) from e


@decisions_v1_router.get(
    "/governance-vector/schema",
    response_model=JSONDict,
    summary="Get Governance Vector Schema",
    description="Returns the schema for the 7-dimensional governance vector.",
)
async def get_governance_vector_schema(
    user: UserClaims = Depends(get_current_user),
) -> JSONDict:
    """
    Get the schema for the 7-dimensional governance vector.

    Returns:
        Schema describing each governance dimension.
    """
    return {
        "constitutional_hash": CONSTITUTIONAL_HASH,
        "version": "v1.0.0",
        "dimensions": {
            "safety": {
                "description": "Physical and operational safety impact",
                "range": [0.0, 1.0],
                "high_score_meaning": "High potential safety impact",
            },
            "security": {
                "description": "Information and system security impact",
                "range": [0.0, 1.0],
                "high_score_meaning": "High security sensitivity",
            },
            "privacy": {
                "description": "Personal data and confidentiality impact",
                "range": [0.0, 1.0],
                "high_score_meaning": "High privacy implications",
            },
            "fairness": {
                "description": "Equity and bias considerations",
                "range": [0.0, 1.0],
                "high_score_meaning": "Significant fairness concerns",
            },
            "reliability": {
                "description": "System dependability impact",
                "range": [0.0, 1.0],
                "high_score_meaning": "High reliability requirements",
            },
            "transparency": {
                "description": "Explainability and auditability",
                "range": [0.0, 1.0],
                "high_score_meaning": "High transparency requirements",
            },
            "efficiency": {
                "description": "Resource and performance impact",
                "range": [0.0, 1.0],
                "high_score_meaning": "High resource utilization",
            },
        },
        "thresholds": {
            "escalation": 0.8,
            "review": 0.5,
            "attention": 0.3,
        },
    }


# ============================================================================
# Helper Functions
# ============================================================================


def _convert_to_response(
    explanation: object,
    include_counterfactuals: bool = True,
) -> DecisionExplanationResponse:
    """Convert DecisionExplanationV1 to API response model."""
    # Convert factors
    factors = []
    for f in explanation.factors:
        factors.append(
            ExplanationFactorResponse(
                factor_id=f.factor_id,
                factor_name=f.factor_name,
                factor_value=f.factor_value,
                factor_weight=f.factor_weight,
                explanation=f.explanation,
                evidence=f.evidence,
                governance_dimension=(
                    f.governance_dimension.value
                    if hasattr(f.governance_dimension, "value")
                    else str(f.governance_dimension)
                ),
                source_component=f.source_component,
                calculation_method=f.calculation_method,
            )
        )

    # Convert counterfactuals
    counterfactuals = []
    if include_counterfactuals:
        for cf in explanation.counterfactual_hints:
            counterfactuals.append(
                CounterfactualHintResponse(
                    scenario_id=cf.scenario_id,
                    scenario_description=cf.scenario_description,
                    modified_factor=cf.modified_factor,
                    original_value=cf.original_value,
                    modified_value=cf.modified_value,
                    predicted_outcome=(
                        cf.predicted_outcome.value
                        if hasattr(cf.predicted_outcome, "value")
                        else str(cf.predicted_outcome)
                    ),
                    confidence=cf.confidence,
                    threshold_crossed=cf.threshold_crossed,
                    impact_delta=cf.impact_delta,
                )
            )

    # Convert EU AI Act info
    euaiact_info = EUAIActInfoResponse(
        article_13_compliant=explanation.euaiact_article13_info.article_13_compliant,
        human_oversight_level=explanation.euaiact_article13_info.human_oversight_level,
        risk_category=explanation.euaiact_article13_info.risk_category,
        transparency_measures=explanation.euaiact_article13_info.transparency_measures,
        data_governance_info=explanation.euaiact_article13_info.data_governance_info,
        technical_documentation_ref=explanation.euaiact_article13_info.technical_documentation_ref,
        conformity_assessment_status=explanation.euaiact_article13_info.conformity_assessment_status,
        intended_purpose=explanation.euaiact_article13_info.intended_purpose,
        limitations_and_risks=explanation.euaiact_article13_info.limitations_and_risks,
        human_reviewers=explanation.euaiact_article13_info.human_reviewers,
    )

    return DecisionExplanationResponse(
        decision_id=explanation.decision_id,
        message_id=explanation.message_id,
        request_id=explanation.request_id,
        verdict=explanation.verdict,
        confidence_score=explanation.confidence_score,
        impact_score=explanation.impact_score,
        governance_vector=explanation.governance_vector,
        factors=factors,
        primary_factors=explanation.primary_factors,
        counterfactual_hints=counterfactuals,
        counterfactuals_generated=explanation.counterfactuals_generated,
        matched_rules=explanation.matched_rules,
        violated_rules=explanation.violated_rules,
        applicable_policies=explanation.applicable_policies,
        summary=explanation.summary,
        detailed_reasoning=explanation.detailed_reasoning,
        euaiact_article13_info=euaiact_info,
        processing_time_ms=explanation.processing_time_ms,
        explanation_generated_at=explanation.explanation_generated_at,
        explanation_version=explanation.explanation_version,
        tenant_id=explanation.tenant_id,
        scope=explanation.scope,
        audit_references=explanation.audit_references,
        constitutional_hash=explanation.constitutional_hash,
    )


__all__ = [
    "CounterfactualHintResponse",
    "DecisionExplanationResponse",
    "EUAIActInfoResponse",
    "ExplainDecisionRequest",
    "ExplainDecisionResponse",
    "ExplanationFactorResponse",
    "decisions_v1_router",
]
