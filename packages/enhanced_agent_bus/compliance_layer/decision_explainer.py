"""
ACGS-2 Decision Explainer
Constitutional Hash: 608508a9bd224290

Implements explainable AI decisions for Layer 4 compliance.
"""

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)


@dataclass
class FactorContribution:
    factor_id: str
    factor_name: str
    factor_value: float
    factor_weight: float
    contribution: float
    explanation: str
    evidence: list[str] = field(default_factory=list)
    governance_dimension: str = "transparency"


@dataclass
class ExplanationContext:
    decision_id: str
    message_id: str | None = None
    tenant_id: str = "default"
    priority: str = "normal"
    human_oversight_level: str = "human_on_the_loop"
    matched_rules: list[str] = field(default_factory=list)
    violated_rules: list[str] = field(default_factory=list)
    applicable_policies: list[str] = field(default_factory=list)
    additional_context: JSONDict = field(default_factory=dict)


@dataclass
class ExplanationResult:
    explanation_id: str
    decision_id: str
    verdict: str
    impact_score: float
    confidence_score: float
    summary: str
    detailed_reasoning: str
    factors: list[FactorContribution]
    governance_vector: dict[str, float]
    counterfactual_hints: list[JSONDict]
    primary_factors: list[str]
    processing_time_ms: float
    generated_at: datetime
    constitutional_hash: str = CONSTITUTIONAL_HASH
    article_13_compliant: bool = True
    human_oversight_level: str = "human_on_the_loop"
    transparency_measures: list[str] = field(default_factory=list)


class DecisionExplainer:
    GOVERNANCE_DIMENSIONS: ClassVar[list[str]] = [
        "safety",
        "security",
        "privacy",
        "fairness",
        "reliability",
        "transparency",
        "efficiency",
    ]

    FACTOR_WEIGHTS: ClassVar[dict[str, float]] = {
        "semantic_score": 0.6,
        "permission_score": 0.1,
        "volume_score": 0.05,
        "context_score": 0.2,
        "drift_score": 0.05,
    }

    def __init__(self, enable_counterfactuals: bool = True, max_counterfactuals: int = 3):
        self.constitutional_hash = CONSTITUTIONAL_HASH
        self.enable_counterfactuals = enable_counterfactuals
        self.max_counterfactuals = max_counterfactuals
        self._explanations: dict[str, ExplanationResult] = {}
        logger.info(f"[{self.constitutional_hash}] DecisionExplainer initialized")

    async def explain(
        self,
        verdict: str,
        impact_score: float,
        context: ExplanationContext | None = None,
        factor_scores: dict[str, float] | None = None,
    ) -> ExplanationResult:
        start_time = time.perf_counter()

        if context is None:
            context = ExplanationContext(decision_id=f"dec-{uuid.uuid4().hex[:8]}")

        if factor_scores is None:
            factor_scores = {
                "semantic_score": 0.5,
                "permission_score": 0.5,
                "volume_score": 0.3,
                "context_score": 0.5,
                "drift_score": 0.2,
            }

        factors = self._calculate_factors(factor_scores)
        governance_vector = self._calculate_governance_vector(factors)
        confidence_score = self._calculate_confidence(factors, impact_score)

        counterfactuals = []
        if self.enable_counterfactuals:
            counterfactuals = self._generate_counterfactuals(factors, verdict, impact_score)

        summary = self._generate_summary(verdict, impact_score, factors)
        detailed_reasoning = self._generate_detailed_reasoning(
            verdict, factors, governance_vector, impact_score
        )

        primary_factors = sorted(factors, key=lambda f: f.contribution, reverse=True)[:3]
        processing_time_ms = (time.perf_counter() - start_time) * 1000

        result = ExplanationResult(
            explanation_id=f"exp-{uuid.uuid4().hex[:8]}",
            decision_id=context.decision_id,
            verdict=verdict.upper(),
            impact_score=impact_score,
            confidence_score=confidence_score,
            summary=summary,
            detailed_reasoning=detailed_reasoning,
            factors=factors,
            governance_vector=governance_vector,
            counterfactual_hints=counterfactuals,
            primary_factors=[f.factor_id for f in primary_factors],
            processing_time_ms=processing_time_ms,
            generated_at=datetime.now(UTC),
            human_oversight_level=context.human_oversight_level,
            transparency_measures=[
                "Factor attribution with evidence",
                "7-dimensional governance vector",
                "Counterfactual analysis",
                "Audit trail integration",
            ],
        )

        self._explanations[result.explanation_id] = result
        logger.info(
            f"[{self.constitutional_hash}] Generated explanation {result.explanation_id} "
            f"for {context.decision_id} (latency={processing_time_ms:.2f}ms)"
        )
        return result

    def _calculate_factors(self, factor_scores: dict[str, float]) -> list[FactorContribution]:
        factors = []
        factor_metadata = {
            "semantic_score": ("Content Analysis", "safety"),
            "permission_score": ("Permission Check", "security"),
            "volume_score": ("Request Volume", "reliability"),
            "context_score": ("Context Analysis", "transparency"),
            "drift_score": ("Behavior Drift", "fairness"),
        }

        for factor_name, score in factor_scores.items():
            weight = self.FACTOR_WEIGHTS.get(factor_name, 0.1)
            contribution = score * weight
            name, dimension = factor_metadata.get(
                factor_name, (factor_name.replace("_", " ").title(), "transparency")
            )
            factors.append(
                FactorContribution(
                    factor_id=f"f-{factor_name}",
                    factor_name=name,
                    factor_value=score,
                    factor_weight=weight,
                    contribution=contribution,
                    explanation=f"Score based on {name.lower()} evaluation",
                    evidence=[f"Constitutional hash: {self.constitutional_hash}"],
                    governance_dimension=dimension,
                )
            )
        return factors

    def _calculate_governance_vector(self, factors: list[FactorContribution]) -> dict[str, float]:
        vector = {dim: 0.0 for dim in self.GOVERNANCE_DIMENSIONS}
        for factor in factors:
            dim = factor.governance_dimension
            if dim in vector:
                vector[dim] = max(vector[dim], factor.factor_value)
        return vector

    def _calculate_confidence(
        self, factors: list[FactorContribution], impact_score: float
    ) -> float:
        if not factors:
            return 0.5
        values = [f.factor_value for f in factors]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        base_confidence = max(0.5, 1.0 - variance)
        if impact_score >= 0.9 or impact_score <= 0.1:
            base_confidence = min(1.0, base_confidence + 0.1)
        return round(base_confidence, 3)

    def _generate_counterfactuals(
        self,
        factors: list[FactorContribution],
        verdict: str,
        impact_score: float,
    ) -> list[JSONDict]:
        counterfactuals = []
        sorted_factors = sorted(factors, key=lambda f: f.contribution, reverse=True)

        for factor in sorted_factors[: self.max_counterfactuals]:
            original = factor.factor_value
            if original >= 0.7:
                modified = 0.3
                scenario = f"If {factor.factor_name} were lower"
            elif original <= 0.3:
                modified = 0.8
                scenario = f"If {factor.factor_name} were higher"
            else:
                modified = 0.9 if original < 0.5 else 0.2
                scenario = f"If {factor.factor_name} crossed threshold"

            impact_delta = (modified - original) * factor.factor_weight * 0.1
            counterfactuals.append(
                {
                    "scenario_id": f"cf-{factor.factor_id}",
                    "scenario_description": scenario,
                    "modified_factor": factor.factor_name,
                    "original_value": original,
                    "modified_value": modified,
                    "impact_delta": round(impact_delta, 4),
                    "confidence": 0.75,
                }
            )
        return counterfactuals

    def _generate_summary(
        self,
        verdict: str,
        impact_score: float,
        factors: list[FactorContribution],
    ) -> str:
        primary = max(factors, key=lambda f: f.contribution) if factors else None
        primary_name = primary.factor_name if primary else "analysis"

        if verdict.upper() == "ALLOW":
            return f"Decision: ALLOW. Impact score {impact_score:.2f} below threshold. Primary factor: {primary_name}."
        elif verdict.upper() == "DENY":
            return f"Decision: DENY. Impact score {impact_score:.2f} exceeds threshold. Primary factor: {primary_name}."
        elif verdict.upper() == "CONDITIONAL":
            return f"Decision: CONDITIONAL. Impact score {impact_score:.2f} requires review. Primary factor: {primary_name}."
        else:
            return f"Decision: {verdict}. Impact score {impact_score:.2f}. Primary factor: {primary_name}."

    def _generate_detailed_reasoning(
        self,
        verdict: str,
        factors: list[FactorContribution],
        governance_vector: dict[str, float],
        impact_score: float,
    ) -> str:
        lines = [
            f"Constitutional Governance Analysis (Hash: {self.constitutional_hash})",
            "",
            f"Overall Impact Score: {impact_score:.3f}",
            f"Final Verdict: {verdict.upper()}",
            "",
            "Factor Attribution:",
        ]
        sorted_factors = sorted(factors, key=lambda f: f.contribution, reverse=True)
        for f in sorted_factors:
            lines.append(
                f"  - {f.factor_name}: {f.factor_value:.3f} "
                f"(weight: {f.factor_weight:.2f}, contribution: {f.contribution:.3f})"
            )
        lines.extend(["", "7-Dimensional Governance Vector:"])
        for dim, score in governance_vector.items():
            lines.append(f"  - {dim}: {score:.3f}")
        return chr(10).join(lines)

    def get_explanation(self, explanation_id: str) -> ExplanationResult | None:
        return self._explanations.get(explanation_id)

    def list_explanations(self, limit: int = 100) -> list[ExplanationResult]:
        return list(self._explanations.values())[:limit]


_decision_explainer: DecisionExplainer | None = None


def get_decision_explainer() -> DecisionExplainer:
    global _decision_explainer
    if _decision_explainer is None:
        _decision_explainer = DecisionExplainer()
    return _decision_explainer


def reset_decision_explainer() -> None:
    global _decision_explainer
    _decision_explainer = None


__all__ = [
    "DecisionExplainer",
    "ExplanationContext",
    "ExplanationResult",
    "FactorContribution",
    "get_decision_explainer",
    "reset_decision_explainer",
]
