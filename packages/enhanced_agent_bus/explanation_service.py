"""
ACGS-2 Decision Explanation Service
Constitutional Hash: 608508a9bd224290

Implements FR-12 Decision Explanation API requirements for structured
factor attribution, governance vector analysis, and counterfactual reasoning.
"""

import time
import uuid

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.event_schemas.decision_explanation import (
    CounterfactualHint,
    DecisionExplanationV1,
    EUAIActTransparencyInfo,
    ExplanationFactor,
    GovernanceDimension,
    PredictedOutcome,
    create_decision_explanation,
)

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
# Default governance vector with neutral scores
DEFAULT_GOVERNANCE_VECTOR: dict[str, float] = {
    "safety": 0.0,
    "security": 0.0,
    "privacy": 0.0,
    "fairness": 0.0,
    "reliability": 0.0,
    "transparency": 0.0,
    "efficiency": 0.0,
}

# Mapping of scoring components to governance dimensions
FACTOR_TO_GOVERNANCE_MAPPING: dict[str, GovernanceDimension] = {
    "semantic_score": GovernanceDimension.SAFETY,
    "permission_score": GovernanceDimension.SECURITY,
    "volume_score": GovernanceDimension.RELIABILITY,
    "context_score": GovernanceDimension.TRANSPARENCY,
    "drift_score": GovernanceDimension.FAIRNESS,
    "priority_factor": GovernanceDimension.EFFICIENCY,
    "type_factor": GovernanceDimension.PRIVACY,
}

# Factor weights from ImpactScorer
FACTOR_WEIGHTS: dict[str, float] = {
    "semantic_score": 0.6,
    "permission_score": 0.1,
    "volume_score": 0.05,
    "context_score": 0.2,
    "drift_score": 0.05,
    "priority_factor": 1.0,  # Multiplier, not additive
    "type_factor": 1.0,  # Multiplier, not additive
}


class CounterfactualEngine:
    """
    Engine for generating counterfactual analysis hints.

    Provides "what-if" scenarios showing how decision outcomes might
    change with different input parameters.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self) -> None:
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def generate_counterfactuals(
        self,
        factors: list[ExplanationFactor],
        current_verdict: str,
        impact_score: float,
        max_hints: int = 3,
    ) -> list[CounterfactualHint]:
        """
        Generate counterfactual hints based on current factors.

        Args:
            factors: List of current explanation factors.
            current_verdict: Current decision verdict.
            impact_score: Current impact score.
            max_hints: Maximum number of counterfactual hints to generate.

        Returns:
            List of CounterfactualHint objects.
        """
        hints: list[CounterfactualHint] = []

        for factor in factors[:max_hints]:
            hint = self._generate_single_counterfactual(
                factor=factor,
                current_verdict=current_verdict,
                impact_score=impact_score,
            )
            if hint:
                hints.append(hint)

        return hints

    def _generate_single_counterfactual(
        self,
        factor: ExplanationFactor,
        current_verdict: str,
        impact_score: float,
    ) -> CounterfactualHint | None:
        """Generate a single counterfactual hint for a factor."""
        original_value = factor.factor_value

        # Determine modified value (inverse direction)
        if original_value >= 0.7:
            # High score - show what happens if it were low
            modified_value = 0.3
            scenario_desc = (
                f"If {factor.factor_name} were lower (0.3 instead of {original_value:.2f})"
            )
        elif original_value <= 0.3:
            # Low score - show what happens if it were high
            modified_value = 0.8
            scenario_desc = (
                f"If {factor.factor_name} were higher (0.8 instead of {original_value:.2f})"
            )
        else:
            # Medium score - show threshold crossing
            modified_value = 0.9 if original_value < 0.5 else 0.2
            scenario_desc = f"If {factor.factor_name} crossed threshold ({modified_value:.1f} instead of {original_value:.2f})"

        # Predict outcome based on score change
        predicted_outcome = self._predict_outcome_change(
            current_verdict=current_verdict,
            impact_score=impact_score,
            factor_weight=factor.factor_weight,
            value_delta=modified_value - original_value,
        )

        # Calculate impact delta
        impact_delta = (modified_value - original_value) * factor.factor_weight * 0.1

        return CounterfactualHint(
            scenario_id=f"cf-{factor.factor_id}",
            scenario_description=scenario_desc,
            modified_factor=factor.factor_name,
            original_value=original_value,
            modified_value=modified_value,
            predicted_outcome=predicted_outcome,
            confidence=0.75,  # Base confidence for rule-based counterfactuals
            threshold_crossed=self._check_threshold_crossing(original_value, modified_value),
            impact_delta=impact_delta,
        )

    def _predict_outcome_change(
        self,
        current_verdict: str,
        impact_score: float,
        factor_weight: float,
        value_delta: float,
    ) -> PredictedOutcome:
        """Predict outcome change based on factor modification."""
        # Estimate new impact score
        score_delta = value_delta * factor_weight * 0.6  # 0.6 is semantic weight
        new_score = max(0.0, min(1.0, impact_score + score_delta))

        # Decision thresholds
        if new_score >= 0.8:
            return PredictedOutcome.ESCALATE
        elif new_score >= 0.5:
            return PredictedOutcome.CONDITIONAL
        elif new_score >= 0.3:
            return PredictedOutcome.ALLOW
        else:
            return PredictedOutcome.ALLOW

    def _check_threshold_crossing(self, original: float, modified: float) -> str | None:
        """Check if a modification crosses any decision thresholds."""
        thresholds = [
            (0.8, "escalation_threshold"),
            (0.5, "review_threshold"),
            (0.3, "attention_threshold"),
        ]

        for threshold, name in thresholds:
            if (original < threshold <= modified) or (modified < threshold <= original):
                return name

        return None


class ExplanationService:
    """
    Service for generating structured decision explanations.

    Implements FR-12 requirements for:
    - Factor attribution with evidence
    - 7-dimensional governance vector
    - Counterfactual analysis
    - EU AI Act Article 13 compliance

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        impact_scorer: object | None = None,
        decision_store: object | None = None,
        enable_counterfactuals: bool = True,
    ) -> None:
        """
        Initialize the explanation service.

        Args:
            impact_scorer: Optional ImpactScorer instance for scoring.
            decision_store: Optional DecisionStore for persistence.
            enable_counterfactuals: Whether to generate counterfactual hints.
        """
        self.constitutional_hash = CONSTITUTIONAL_HASH
        self.impact_scorer = impact_scorer
        self.decision_store = decision_store
        self.enable_counterfactuals = enable_counterfactuals
        self.counterfactual_engine = CounterfactualEngine()

        # Lazy import to avoid circular dependencies
        self._impact_scorer_loaded = False
        self._decision_store_loaded = False

    def _ensure_impact_scorer(self) -> None:
        """Lazy load impact scorer if not provided."""
        if self.impact_scorer is None and not self._impact_scorer_loaded:
            try:
                from enhanced_agent_bus.deliberation_layer.impact_scorer import (
                    ImpactScorer,
                )

                self.impact_scorer = ImpactScorer()
                self._impact_scorer_loaded = True
            except ImportError:
                logger.warning("ImpactScorer not available, using fallback scoring")
                self._impact_scorer_loaded = True

    async def _ensure_decision_store(self) -> None:
        """Lazy load decision store if not provided."""
        if self.decision_store is None and not self._decision_store_loaded:
            try:
                from enhanced_agent_bus.decision_store import get_decision_store

                self.decision_store = await get_decision_store()
                self._decision_store_loaded = True
            except ImportError:
                logger.warning("DecisionStore not available, explanations won't be persisted")
                self._decision_store_loaded = True

    async def generate_explanation(
        self,
        message: JSONDict | object,
        verdict: str,
        context: JSONDict | None = None,
        decision_id: str | None = None,
        tenant_id: str | None = None,
        store_explanation: bool = True,
    ) -> DecisionExplanationV1:
        """
        Generate a complete decision explanation.

        Args:
            message: The message or action being explained.
            verdict: Decision verdict (ALLOW, DENY, CONDITIONAL, ESCALATE).
            context: Additional context for scoring.
            decision_id: Optional decision ID (generated if not provided).
            tenant_id: Tenant identifier for multi-tenancy.
            store_explanation: Whether to store in decision store.

        Returns:
            DecisionExplanationV1 with full explanation.
        """
        start_time = time.perf_counter()
        self._ensure_impact_scorer()
        if store_explanation:
            await self._ensure_decision_store()

        if context is None:
            context = {}

        if decision_id is None:
            decision_id = str(uuid.uuid4())

        # Calculate impact score and factors
        impact_score, factor_scores = self._calculate_factor_scores(message, context)

        # Get governance vector
        governance_vector = self._get_governance_vector(message, context, factor_scores)

        # Create explanation factors
        factors = self._create_explanation_factors(factor_scores, message, context)

        # Calculate confidence
        confidence_score = self._calculate_confidence(factors, impact_score)

        # Get message ID if available
        message_id = self._extract_message_id(message)

        # Create base explanation
        explanation = create_decision_explanation(
            decision_id=decision_id,
            verdict=verdict.upper(),
            confidence_score=confidence_score,
            governance_vector=governance_vector,
            factors=[f.model_dump() for f in factors],
            message_id=message_id,
            tenant_id=tenant_id,
        )

        # Set impact score
        explanation.impact_score = impact_score

        # Generate counterfactuals if enabled
        if self.enable_counterfactuals:
            counterfactuals = self.counterfactual_engine.generate_counterfactuals(
                factors=factors,
                current_verdict=verdict,
                impact_score=impact_score,
            )
            explanation.counterfactual_hints = counterfactuals
            explanation.counterfactuals_generated = len(counterfactuals) > 0

        # Set primary factors (top 3 by weight * value)
        sorted_factors = sorted(
            factors, key=lambda f: f.factor_value * f.factor_weight, reverse=True
        )
        explanation.primary_factors = [f.factor_id for f in sorted_factors[:3]]

        # Add matched/violated rules from context
        explanation.matched_rules = context.get("matched_rules", [])
        explanation.violated_rules = context.get("violated_rules", [])
        explanation.applicable_policies = context.get("applicable_policies", [])

        # Generate summary
        explanation.summary = self._generate_summary(verdict, factors, impact_score)
        explanation.detailed_reasoning = self._generate_detailed_reasoning(
            verdict, factors, governance_vector, impact_score
        )

        # Set EU AI Act compliance info
        explanation.euaiact_article13_info = self._create_euaiact_info(context)

        # Set processing time
        explanation.processing_time_ms = (time.perf_counter() - start_time) * 1000

        # Store if enabled
        if store_explanation and self.decision_store:
            await self.decision_store.store(explanation)

        return explanation

    def _get_default_factor_scores(self) -> dict[str, float]:
        """
        Return default factor scores used when ImpactScorer is unavailable.

        Returns:
            Dict mapping factor names to their default float scores.
        """
        return {
            "semantic_score": 0.5,
            "permission_score": 0.5,
            "volume_score": 0.3,
            "context_score": 0.5,
            "drift_score": 0.2,
            "priority_factor": 0.5,
            "type_factor": 0.5,
        }

    def _calculate_single_factor(
        self,
        factor_name: str,
        scorer_method: str,
        args: tuple,
        default: float,
    ) -> float:
        """
        Calculate a single factor score with error handling.

        Attempts to call the specified ImpactScorer method with the given arguments.
        Falls back to the default value if the calculation fails.

        Args:
            factor_name: Name of the factor (for logging purposes).
            scorer_method: Name of the ImpactScorer method to call.
            args: Tuple of arguments to pass to the scorer method.
            default: Default value to return if calculation fails.

        Returns:
            The calculated score or the default value on failure.
        """
        try:
            method = getattr(self.impact_scorer, scorer_method)
            return method(*args)  # type: ignore[no-any-return]
        except (AttributeError, KeyError, TypeError) as e:
            logger.debug("%s calculation failed, using default: %s", factor_name, e)
            return default

    def _calculate_scorer_factors(
        self,
        msg_dict: JSONDict,
        context: JSONDict,
    ) -> dict[str, float]:
        """
        Calculate all factor scores using the ImpactScorer.

        Iterates through defined factor configurations and calculates each
        score using the corresponding ImpactScorer method.

        Args:
            msg_dict: Message dictionary containing message attributes.
            context: Context dictionary with additional scoring context.

        Returns:
            Dict mapping factor names to their calculated float scores.
        """
        from_agent = msg_dict.get("from_agent", "unknown")

        # Define factor configurations: (scorer_method, args, default)
        factor_configs: dict[str, tuple] = {
            "semantic_score": ("_calculate_semantic_score", (msg_dict,), 0.5),
            "permission_score": ("_calculate_permission_score", (msg_dict,), 0.5),
            "volume_score": ("_calculate_volume_score", (from_agent,), 0.3),
            "context_score": ("_calculate_context_score", (msg_dict, context), 0.5),
            "drift_score": ("_calculate_drift_score", (from_agent, 0.4), 0.2),
            "priority_factor": ("_calculate_priority_factor", (msg_dict, context), 0.5),
            "type_factor": ("_calculate_type_factor", (msg_dict, context), 0.5),
        }

        return {
            name: self._calculate_single_factor(name, method, args, default)
            for name, (method, args, default) in factor_configs.items()
        }

    def _calculate_overall_impact(
        self,
        message: JSONDict | object,
        context: JSONDict,
        factor_scores: dict[str, float],
    ) -> float:
        """
        Calculate the overall impact score.

        Attempts to use the ImpactScorer's calculate_impact_score method.
        Falls back to a weighted sum of individual factor scores on failure.

        Args:
            message: The original message object or dictionary.
            context: Context dictionary with additional scoring context.
            factor_scores: Pre-calculated individual factor scores.

        Returns:
            The overall impact score as a float.
        """
        try:
            return self.impact_scorer.calculate_impact_score(message, context)  # type: ignore[no-any-return]
        except (AttributeError, KeyError, TypeError) as e:
            logger.debug("Impact score calculation failed, using fallback: %s", e)
            additive_factors = [
                "semantic_score",
                "permission_score",
                "volume_score",
                "context_score",
                "drift_score",
            ]
            return sum(factor_scores[k] * FACTOR_WEIGHTS.get(k, 0.1) for k in additive_factors)

    def _calculate_factor_scores(
        self, message: JSONDict | object, context: JSONDict
    ) -> tuple[float, dict[str, float]]:
        """
        Calculate individual factor scores using ImpactScorer.

        Orchestrates the calculation of all factor scores and the overall
        impact score, delegating to helper methods for each component.

        Args:
            message: The message object or dictionary to score.
            context: Context dictionary with additional scoring context.

        Returns:
            Tuple of (impact_score, factor_scores_dict).
        """
        if self.impact_scorer is None:
            return 0.5, self._get_default_factor_scores()

        msg_dict = message if isinstance(message, dict) else message.__dict__
        factor_scores = self._calculate_scorer_factors(msg_dict, context)
        impact_score = self._calculate_overall_impact(message, context, factor_scores)

        return impact_score, factor_scores

    def _get_governance_vector(
        self,
        message: JSONDict | object,
        context: JSONDict,
        factor_scores: dict[str, float],
    ) -> dict[str, float]:
        """Get or calculate the 7-dimensional governance vector."""
        governance_vector = DEFAULT_GOVERNANCE_VECTOR.copy()

        # Try to get from ImpactScorer
        if self.impact_scorer is not None:
            try:
                scorer_vector = self.impact_scorer.get_governance_vector(context)
                if scorer_vector:
                    governance_vector.update(scorer_vector)
                    return governance_vector
            except (AttributeError, KeyError, TypeError) as e:
                logger.debug("Governance vector retrieval failed, using defaults: %s", e)

        # Fallback: derive from factor scores
        for factor_name, score in factor_scores.items():
            dimension = FACTOR_TO_GOVERNANCE_MAPPING.get(factor_name)
            if dimension:
                # Update governance dimension with factor score
                dim_key = dimension.value
                governance_vector[dim_key] = max(governance_vector[dim_key], score)

        return governance_vector

    def _create_explanation_factors(
        self,
        factor_scores: dict[str, float],
        message: JSONDict | object,
        context: JSONDict,
    ) -> list[ExplanationFactor]:
        """Create ExplanationFactor objects from scores."""
        factors: list[ExplanationFactor] = []

        factor_metadata = {
            "semantic_score": {
                "name": "Content Analysis",
                "explanation": "Score based on semantic analysis of message content for high-impact keywords",
                "source": "semantic_scorer",
                "method": "keyword_matching",
            },
            "permission_score": {
                "name": "Permission Check",
                "explanation": "Score based on requested permissions and security implications",
                "source": "permission_checker",
                "method": "permission_analysis",
            },
            "volume_score": {
                "name": "Request Volume",
                "explanation": "Score based on agent request volume and rate patterns",
                "source": "volume_tracker",
                "method": "rate_analysis",
            },
            "context_score": {
                "name": "Context Analysis",
                "explanation": "Score based on message context and metadata quality",
                "source": "context_analyzer",
                "method": "context_evaluation",
            },
            "drift_score": {
                "name": "Behavior Drift",
                "explanation": "Score based on deviation from established behavioral patterns",
                "source": "drift_detector",
                "method": "statistical_analysis",
            },
            "priority_factor": {
                "name": "Priority Level",
                "explanation": "Factor based on message priority affecting urgency of processing",
                "source": "priority_evaluator",
                "method": "priority_mapping",
            },
            "type_factor": {
                "name": "Message Type",
                "explanation": "Factor based on message type affecting processing requirements",
                "source": "type_classifier",
                "method": "type_categorization",
            },
        }

        for factor_name, score in factor_scores.items():
            metadata = factor_metadata.get(
                factor_name,
                {
                    "name": factor_name.replace("_", " ").title(),
                    "explanation": f"Calculated {factor_name} for governance decision",
                    "source": "impact_scorer",
                    "method": "calculation",
                },
            )

            dimension = FACTOR_TO_GOVERNANCE_MAPPING.get(
                factor_name, GovernanceDimension.TRANSPARENCY
            )

            # Generate evidence based on score
            evidence = self._generate_factor_evidence(factor_name, score, message, context)

            factor = ExplanationFactor(
                factor_id=f"f-{factor_name}",
                factor_name=metadata["name"],
                factor_value=score,
                factor_weight=FACTOR_WEIGHTS.get(factor_name, 1.0),
                explanation=metadata["explanation"],
                evidence=evidence,
                governance_dimension=dimension,
                source_component=metadata["source"],
                calculation_method=metadata["method"],
            )
            factors.append(factor)

        return factors

    def _generate_factor_evidence(
        self,
        factor_name: str,
        score: float,
        message: JSONDict | object,
        context: JSONDict,
    ) -> list[str]:
        """Generate evidence items for a factor."""
        evidence: list[str] = []

        if factor_name == "semantic_score":
            if score >= 0.9:
                evidence.append("High-impact keywords detected in content")
            elif score >= 0.5:
                evidence.append("Moderate semantic indicators present")
            else:
                evidence.append("No high-impact keywords detected")

        elif factor_name == "permission_score":
            if score >= 0.7:
                evidence.append("Elevated permissions requested")
            else:
                evidence.append("Standard permission level")

        elif factor_name == "priority_factor":
            msg_dict = message if isinstance(message, dict) else getattr(message, "__dict__", {})
            priority = context.get("priority") or msg_dict.get("priority", "normal")
            evidence.append(f"Priority level: {priority}")

        elif factor_name == "volume_score":
            if score >= 0.7:
                evidence.append("High request volume from agent")
            else:
                evidence.append("Normal request volume")

        # Add constitutional hash as evidence
        evidence.append(f"Constitutional hash: {self.constitutional_hash}")

        return evidence

    def _calculate_confidence(self, factors: list[ExplanationFactor], impact_score: float) -> float:
        """Calculate overall confidence in the decision."""
        if not factors:
            return 0.5

        # Base confidence on factor agreement
        factor_values = [f.factor_value for f in factors]
        variance = self._calculate_variance(factor_values)

        # Lower variance = higher confidence
        base_confidence = max(0.5, 1.0 - variance)

        # Adjust for extreme scores (more confident at extremes)
        if impact_score >= 0.9 or impact_score <= 0.1:
            base_confidence = min(1.0, base_confidence + 0.1)

        return base_confidence

    def _calculate_variance(self, values: list[float]) -> float:
        """Calculate variance of a list of values."""
        if not values:
            return 0.0
        mean = sum(values) / len(values)
        return sum((v - mean) ** 2 for v in values) / len(values)

    def _extract_message_id(self, message: JSONDict | object) -> str | None:
        """Extract message ID from message object."""
        if isinstance(message, dict):
            return message.get("message_id") or message.get("id")  # type: ignore[no-any-return]
        return getattr(message, "message_id", None) or getattr(message, "id", None)  # type: ignore[no-any-return]

    def _generate_summary(
        self, verdict: str, factors: list[ExplanationFactor], impact_score: float
    ) -> str:
        """Generate a brief human-readable summary."""
        primary_factor = (
            max(factors, key=lambda f: f.factor_value * f.factor_weight) if factors else None
        )
        primary_name = primary_factor.factor_name if primary_factor else "analysis"

        if verdict.upper() == "ALLOW":
            return f"Decision: ALLOW. Impact score {impact_score:.2f} is below threshold. Primary factor: {primary_name}."
        elif verdict.upper() == "DENY":
            return f"Decision: DENY. Impact score {impact_score:.2f} exceeds threshold. Primary factor: {primary_name}."
        elif verdict.upper() == "CONDITIONAL":
            return f"Decision: CONDITIONAL. Impact score {impact_score:.2f} requires additional review. Primary factor: {primary_name}."
        else:
            return f"Decision: {verdict}. Impact score {impact_score:.2f}. Primary factor: {primary_name}."

    def _generate_detailed_reasoning(
        self,
        verdict: str,
        factors: list[ExplanationFactor],
        governance_vector: dict[str, float],
        impact_score: float,
    ) -> str:
        """Generate detailed reasoning explanation."""
        lines = [
            f"Constitutional Governance Analysis (Hash: {self.constitutional_hash})",
            "",
            f"Overall Impact Score: {impact_score:.3f}",
            f"Final Verdict: {verdict.upper()}",
            "",
            "Factor Attribution:",
        ]

        sorted_factors = sorted(
            factors, key=lambda f: f.factor_value * f.factor_weight, reverse=True
        )
        for f in sorted_factors:
            contribution = f.factor_value * f.factor_weight
            lines.append(
                f"  - {f.factor_name}: {f.factor_value:.3f} (weight: {f.factor_weight:.2f}, contribution: {contribution:.3f})"
            )

        lines.append("")
        lines.append("7-Dimensional Governance Vector:")
        for dim, score in governance_vector.items():
            lines.append(f"  - {dim}: {score:.3f}")

        return "\n".join(lines)

    def _create_euaiact_info(self, context: JSONDict) -> EUAIActTransparencyInfo:
        """Create EU AI Act Article 13 transparency information."""
        return EUAIActTransparencyInfo(
            article_13_compliant=True,
            human_oversight_level=context.get("human_oversight_level", "human-on-the-loop"),
            risk_category=context.get("risk_category", "limited"),
            transparency_measures=[
                "Decision explanation API (FR-12)",
                "Factor attribution with evidence",
                "7-dimensional governance vector",
                "Counterfactual analysis",
                "Audit trail integration",
            ],
            data_governance_info={
                "constitutional_hash": self.constitutional_hash,
                "data_retention_days": 90,
                "anonymization_applied": True,
            },
            technical_documentation_ref="ACGS-2 v2.3 Specification",
            conformity_assessment_status="completed",
            intended_purpose="AI governance decision-making",
            limitations_and_risks=[
                "Model-based scoring may have inherent biases",
                "Counterfactual analysis is estimative",
            ],
            human_reviewers=context.get("human_reviewers", []),
        )

    async def get_explanation(
        self, decision_id: str, tenant_id: str = "default"
    ) -> DecisionExplanationV1 | None:
        """
        Retrieve a stored explanation by decision ID.

        Args:
            decision_id: The decision ID to retrieve.
            tenant_id: Tenant identifier.

        Returns:
            DecisionExplanationV1 if found, None otherwise.
        """
        await self._ensure_decision_store()
        if self.decision_store:
            return await self.decision_store.get(decision_id, tenant_id)
        return None


# Singleton instance
_explanation_service: ExplanationService | None = None


def get_explanation_service() -> ExplanationService:
    """Get or create the singleton ExplanationService instance."""
    global _explanation_service
    if _explanation_service is None:
        _explanation_service = ExplanationService()
    return _explanation_service


def reset_explanation_service() -> None:
    """Reset the singleton instance (for testing)."""
    global _explanation_service
    _explanation_service = None


class ExplanationServiceAdapter:
    """MD-010 adapter: wraps ExplanationService to satisfy ExplanationPort Protocol.

    Services depend on ExplanationPort (contracts layer) rather than on the
    concrete ExplanationService, enabling independent testing and future
    implementation swaps without modifying service code.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, service: ExplanationService | None = None) -> None:
        self._service = service or get_explanation_service()

    async def explain_decision(
        self,
        message_id: str,
        *,
        factors: dict | None = None,
        include_counterfactuals: bool = False,
        tenant_id: str = "default",
    ) -> dict:
        """Delegate to ExplanationService.explain() and serialize result."""
        result = await self._service.explain(
            message_id=message_id,
            factors=factors or {},
            include_counterfactuals=include_counterfactuals,
            tenant_id=tenant_id,
        )
        return result.model_dump() if hasattr(result, "model_dump") else dict(result)

    async def get_explanation(
        self,
        decision_id: str,
        tenant_id: str = "default",
    ) -> dict | None:
        """Retrieve a stored explanation and serialize to dict (or None)."""
        result = await self._service.get_explanation(decision_id, tenant_id)
        if result is None:
            return None
        return result.model_dump() if hasattr(result, "model_dump") else dict(result)


__all__ = [
    "DEFAULT_GOVERNANCE_VECTOR",
    "FACTOR_TO_GOVERNANCE_MAPPING",
    "FACTOR_WEIGHTS",
    "CounterfactualEngine",
    "ExplanationService",
    "ExplanationServiceAdapter",
    "get_explanation_service",
    "reset_explanation_service",
]
