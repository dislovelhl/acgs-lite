"""
ACGS-2 Response Quality Enhancement - Validator
Constitutional Hash: cdd01ef066bc6cf2

Response quality validation with constitutional compliance checking.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar, Protocol

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from src.core.shared.errors.exceptions import (
    ACGSBaseError,
    ValidationError,  # canonical; re-exported for backward compatibility
)

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .models import (
    DimensionScores,
    QualityAssessment,
    QualityDimension,
)

logger = get_logger(__name__)


class ConstitutionalHashError(ACGSBaseError):
    """Raised when constitutional hash validation fails."""

    http_status_code = 400
    error_code = "CONSTITUTIONAL_HASH_ERROR"


@dataclass
class DimensionSpec:
    """Specification for a quality dimension."""

    name: str
    threshold: float
    weight: float = 1.0
    required: bool = False
    description: str = ""

    def __post_init__(self):
        if not 0.0 <= self.threshold <= 1.0:
            raise ValidationError(
                f"Threshold must be between 0.0 and 1.0, got {self.threshold}",
                error_code="QUALITY_THRESHOLD_INVALID",
            )
        if self.weight < 0:
            raise ValidationError(
                f"Weight must be non-negative, got {self.weight}",
                error_code="QUALITY_WEIGHT_NEGATIVE",
            )


class ResponseScorer(Protocol):
    """Protocol for response scoring implementations."""

    def score(self, response: str, context: JSONDict | None = None) -> DimensionScores:
        """Score a response across quality dimensions."""
        ...


@dataclass
class ValidationConfig:
    """Configuration for response quality validation."""

    require_all_dimensions: bool = True
    fail_on_any_critical: bool = True
    critical_dimensions: list[str] = field(
        default_factory=lambda: ["constitutional_alignment", "safety"]
    )
    overall_threshold: float = 0.7
    enable_constitutional_check: bool = True
    constitutional_hash: str = CONSTITUTIONAL_HASH


class ResponseQualityValidator:
    """
    Validates response quality across multiple dimensions.

    This validator assesses LLM responses for quality, safety, and
    constitutional compliance. It supports configurable quality dimensions
    with individual thresholds.

    Constitutional Hash Validation:
        The validator verifies constitutional hash at initialization to ensure
        it is operating under the correct governance framework.

    Attributes:
        QUALITY_DIMENSIONS: Default quality dimension specifications
        config: Validation configuration
        scorer: Optional custom response scorer

    Example:
        >>> validator = ResponseQualityValidator()
        >>> assessment = validator.validate("Hello, world!", context={"intent": "greeting"})
        >>> print(f"Passes: {assessment.passes_threshold}, Score: {assessment.overall_score}")
    """

    # Default quality dimensions with thresholds
    QUALITY_DIMENSIONS: ClassVar[dict[str, DimensionSpec]] = {
        "accuracy": DimensionSpec(
            name="accuracy",
            threshold=0.8,
            weight=1.2,
            required=False,
            description="Factual correctness and precision of information",
        ),
        "coherence": DimensionSpec(
            name="coherence",
            threshold=0.7,
            weight=1.0,
            required=False,
            description="Logical flow and internal consistency",
        ),
        "relevance": DimensionSpec(
            name="relevance",
            threshold=0.8,
            weight=1.1,
            required=False,
            description="Appropriateness to the query context",
        ),
        "constitutional_alignment": DimensionSpec(
            name="constitutional_alignment",
            threshold=0.95,
            weight=1.5,
            required=True,
            description="Alignment with constitutional principles",
        ),
        "safety": DimensionSpec(
            name="safety",
            threshold=0.99,
            weight=2.0,
            required=True,
            description="Absence of harmful or unsafe content",
        ),
    }

    def __init__(
        self,
        config: ValidationConfig | None = None,
        scorer: ResponseScorer | None = None,
        custom_dimensions: dict[str, DimensionSpec] | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        """
        Initialize the validator with constitutional hash verification.

        Args:
            config: Optional validation configuration
            scorer: Optional custom response scorer
            custom_dimensions: Optional custom dimension specifications
            constitutional_hash: Expected constitutional hash for verification

        Raises:
            ConstitutionalHashError: If constitutional hash validation fails
        """
        # Validate constitutional hash at initialization
        self._validate_constitutional_hash(constitutional_hash)

        self.config = config or ValidationConfig()
        self.scorer = scorer

        # Merge custom dimensions with defaults
        self.dimensions = dict(self.QUALITY_DIMENSIONS)
        if custom_dimensions:
            self.dimensions.update(custom_dimensions)

        self._validation_count = 0
        self._created_at = datetime.now()

        logger.info(
            f"ResponseQualityValidator initialized with {len(self.dimensions)} dimensions, "
            f"constitutional_hash={constitutional_hash[:8]}..."
        )

    def _validate_constitutional_hash(self, provided_hash: str) -> None:
        """
        Validate the constitutional hash.

        Args:
            provided_hash: The hash to validate

        Raises:
            ConstitutionalHashError: If hash doesn't match expected value
        """
        if provided_hash != CONSTITUTIONAL_HASH:
            raise ConstitutionalHashError(
                f"Constitutional hash mismatch. "
                f"Expected: {CONSTITUTIONAL_HASH}, Got: {provided_hash}"
            )

    @property
    def dimension_names(self) -> list[str]:
        """Get list of all dimension names."""
        return list(self.dimensions.keys())

    @property
    def required_dimensions(self) -> list[str]:
        """Get list of required (critical) dimension names."""
        return [name for name, spec in self.dimensions.items() if spec.required]

    @property
    def thresholds(self) -> dict[str, float]:
        """Get mapping of dimension names to thresholds."""
        return {name: spec.threshold for name, spec in self.dimensions.items()}

    def validate(
        self,
        response: str,
        context: JSONDict | None = None,
        scores: DimensionScores | None = None,
        response_id: str | None = None,
    ) -> QualityAssessment:
        """
        Validate a response for quality across all dimensions.

        Args:
            response: The response text to validate
            context: Optional context for scoring
            scores: Optional pre-computed dimension scores
            response_id: Optional identifier for the response

        Returns:
            QualityAssessment with complete evaluation results

        Raises:
            ValidationError: If validation fails critically
        """
        self._validation_count += 1
        response_id = response_id or str(uuid.uuid4())

        # Get scores from scorer or use provided scores
        if scores is None:
            if self.scorer:
                scores = self.scorer.score(response, context)
            else:
                scores = self._default_scoring(response, context)

        # Build quality dimensions from scores
        dimensions = []
        for name, spec in self.dimensions.items():
            score = scores.get(name, 0.0)
            # Clamp score to valid range
            score = max(0.0, min(1.0, score))

            dim = QualityDimension(
                name=name,
                score=score,
                threshold=spec.threshold,
                critique=self._generate_critique(name, score, spec.threshold),
            )
            dimensions.append(dim)

        # Calculate overall score (weighted average)
        overall_score = self._calculate_overall_score(dimensions)

        # Determine if passes threshold
        passes_threshold = self._check_passes_threshold(dimensions, overall_score)

        # Check constitutional compliance
        constitutional_compliance = self._check_constitutional_compliance(dimensions)

        # Generate refinement suggestions
        refinement_suggestions = self._generate_suggestions(dimensions)

        # Build metadata
        metadata = {
            "validation_count": self._validation_count,
            "validator_created_at": self._created_at.isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "context_provided": context is not None,
        }

        assessment = QualityAssessment(
            dimensions=dimensions,
            overall_score=overall_score,
            passes_threshold=passes_threshold,
            refinement_suggestions=refinement_suggestions,
            constitutional_compliance=constitutional_compliance,
            response_id=response_id,
            timestamp=datetime.now(),
            metadata=metadata,
        )

        logger.debug(
            f"Validated response {response_id[:8]}...: "
            f"score={overall_score:.3f}, passes={passes_threshold}, "
            f"constitutional={constitutional_compliance}"
        )

        return assessment

    def _default_scoring(self, response: str, context: JSONDict | None = None) -> DimensionScores:
        """
        Default scoring implementation when no scorer is provided.

        Uses heuristics to provide baseline scores. Production usage
        should provide a proper LLM-based scorer.

        Args:
            response: The response to score
            context: Optional context

        Returns:
            Dictionary of dimension scores
        """
        scores: DimensionScores = {}

        # Basic heuristic scoring
        response_len = len(response)
        word_count = len(response.split())

        # Coherence: based on structure
        if response_len > 0 and word_count > 0:
            avg_word_len = response_len / word_count
            coherence = min(1.0, 0.5 + (0.1 * min(word_count, 50) / 50))
            # Bonus for reasonable word length
            if 3 <= avg_word_len <= 8:
                coherence = min(1.0, coherence + 0.2)
            scores["coherence"] = coherence
        else:
            scores["coherence"] = 0.0

        # Relevance: if context provided, check for keyword overlap
        if context and "query" in context:
            query_words = set(context["query"].lower().split())
            response_words = set(response.lower().split())
            overlap = len(query_words & response_words)
            scores["relevance"] = min(1.0, 0.6 + (overlap * 0.1))
        else:
            scores["relevance"] = 0.75  # Default moderate relevance

        # Accuracy: heuristic baseline
        scores["accuracy"] = 0.8 if response_len > 10 else 0.5

        # Constitutional alignment: default high unless flagged
        scores["constitutional_alignment"] = 0.98

        # Safety: default very high unless harmful patterns detected
        harmful_patterns = ["hack", "steal", "kill", "illegal"]
        response_lower = response.lower()
        if any(pattern in response_lower for pattern in harmful_patterns):
            scores["safety"] = 0.3
        else:
            scores["safety"] = 0.99

        return scores

    def _calculate_overall_score(self, dimensions: list[QualityDimension]) -> float:
        """
        Calculate weighted overall score from dimensions.

        Args:
            dimensions: List of quality dimensions

        Returns:
            Weighted average score between 0.0 and 1.0
        """
        if not dimensions:
            return 0.0

        total_weighted = 0.0
        total_weight = 0.0

        for dim in dimensions:
            spec = self.dimensions.get(dim.name)
            weight = spec.weight if spec else 1.0
            total_weighted += dim.score * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0

        return round(total_weighted / total_weight, 4)

    def _check_passes_threshold(
        self, dimensions: list[QualityDimension], overall_score: float
    ) -> bool:
        """
        Check if assessment passes all thresholds.

        Args:
            dimensions: List of quality dimensions
            overall_score: Calculated overall score

        Returns:
            True if all thresholds are met
        """
        if overall_score < self.config.overall_threshold:
            return False

        critical_fails = self.config.fail_on_any_critical and any(
            dim.name in self.config.critical_dimensions and not dim.passes for dim in dimensions
        )
        if critical_fails:
            return False

        required_fails = any(
            (spec := self.dimensions.get(dim.name)) and spec.required and not dim.passes
            for dim in dimensions
        )
        if required_fails:
            return False

        return not (
            self.config.require_all_dimensions and any(not dim.passes for dim in dimensions)
        )

    def _check_constitutional_compliance(self, dimensions: list[QualityDimension]) -> bool:
        """
        Check constitutional compliance from dimensions.

        Args:
            dimensions: List of quality dimensions

        Returns:
            True if constitutionally compliant
        """
        if not self.config.enable_constitutional_check:
            return True

        for dim in dimensions:
            if dim.name == "constitutional_alignment":
                return dim.passes

        # If no constitutional dimension, assume compliant
        return True

    def _generate_critique(self, name: str, score: float, threshold: float) -> str | None:
        """
        Generate a critique for a dimension score.

        Args:
            name: Dimension name
            score: Achieved score
            threshold: Required threshold

        Returns:
            Critique string or None if passing
        """
        if score >= threshold:
            return None

        gap = threshold - score
        severity = "slightly" if gap < 0.1 else "significantly" if gap < 0.3 else "critically"

        critiques = {
            "accuracy": f"Response is {severity} below accuracy threshold ({score:.2f} < {threshold:.2f}). "
            "Consider verifying facts and sources.",
            "coherence": f"Response lacks coherence ({score:.2f} < {threshold:.2f}). "
            "Improve logical flow and structure.",
            "relevance": f"Response is {severity} off-topic ({score:.2f} < {threshold:.2f}). "
            "Better align with the query intent.",
            "constitutional_alignment": f"Constitutional alignment insufficient ({score:.2f} < {threshold:.2f}). "
            "Review against constitutional principles.",
            "safety": f"Safety concerns detected ({score:.2f} < {threshold:.2f}). "
            "Remove or rephrase potentially harmful content.",
        }

        return critiques.get(name, f"{name} score below threshold ({score:.2f} < {threshold:.2f})")

    def _generate_suggestions(self, dimensions: list[QualityDimension]) -> list[str]:
        """
        Generate refinement suggestions for failing dimensions.

        Args:
            dimensions: List of quality dimensions

        Returns:
            List of improvement suggestions
        """
        suggestions = []

        # Sort by gap (most problematic first)
        failing = sorted([d for d in dimensions if not d.passes], key=lambda d: d.gap)

        suggestion_templates = {
            "accuracy": "Verify factual claims and cite sources where possible",
            "coherence": "Restructure response with clear logical progression",
            "relevance": "Focus more directly on the original query",
            "constitutional_alignment": "Review and align with constitutional AI principles",
            "safety": "Remove any potentially harmful or unsafe content",
        }

        for dim in failing:
            if dim.name in suggestion_templates:
                suggestions.append(suggestion_templates[dim.name])
            else:
                suggestions.append(f"Improve {dim.name} to meet threshold of {dim.threshold:.2f}")

        return suggestions

    def validate_batch(
        self, responses: list[str], contexts: list[JSONDict | None] | None = None
    ) -> list[QualityAssessment]:
        """
        Validate multiple responses.

        Args:
            responses: List of responses to validate
            contexts: Optional list of contexts (parallel to responses)

        Returns:
            List of QualityAssessment objects
        """
        if contexts is None:
            contexts = [None] * len(responses)

        if len(responses) != len(contexts):
            raise ValidationError(
                "responses and contexts must have the same length",
                error_code="QUALITY_LENGTH_MISMATCH",
            )

        return [
            self.validate(response, context)
            for response, context in zip(responses, contexts, strict=False)
        ]

    def get_dimension_spec(self, name: str) -> DimensionSpec | None:
        """Get specification for a dimension by name."""
        return self.dimensions.get(name)

    def update_threshold(self, dimension_name: str, new_threshold: float) -> None:
        """
        Update threshold for a dimension.

        Args:
            dimension_name: Name of dimension to update
            new_threshold: New threshold value (0.0 to 1.0)

        Raises:
            ValueError: If dimension doesn't exist or threshold invalid
        """
        if dimension_name not in self.dimensions:
            raise ValidationError(
                f"Unknown dimension: {dimension_name}",
                error_code="QUALITY_UNKNOWN_DIMENSION",
            )
        if not 0.0 <= new_threshold <= 1.0:
            raise ValidationError(
                f"Threshold must be between 0.0 and 1.0, got {new_threshold}",
                error_code="QUALITY_THRESHOLD_INVALID",
            )

        spec = self.dimensions[dimension_name]
        self.dimensions[dimension_name] = DimensionSpec(
            name=spec.name,
            threshold=new_threshold,
            weight=spec.weight,
            required=spec.required,
            description=spec.description,
        )

        logger.info(f"Updated threshold for {dimension_name} to {new_threshold}")

    def reset_validation_count(self) -> None:
        """Reset the validation counter."""
        self._validation_count = 0

    @property
    def stats(self) -> JSONDict:
        """Get validator statistics."""
        return {
            "validation_count": self._validation_count,
            "dimension_count": len(self.dimensions),
            "created_at": self._created_at.isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "thresholds": self.thresholds,
            "required_dimensions": self.required_dimensions,
        }


def create_validator(
    thresholds: dict[str, float] | None = None, scorer: ResponseScorer | None = None
) -> ResponseQualityValidator:
    """
    Factory function to create a configured validator.

    Args:
        thresholds: Optional custom thresholds for dimensions
        scorer: Optional custom scorer

    Returns:
        Configured ResponseQualityValidator
    """
    custom_dimensions = None

    if thresholds:
        custom_dimensions = {}
        for name, threshold in thresholds.items():
            default_spec = ResponseQualityValidator.QUALITY_DIMENSIONS.get(name)
            if default_spec:
                custom_dimensions[name] = DimensionSpec(
                    name=name,
                    threshold=threshold,
                    weight=default_spec.weight,
                    required=default_spec.required,
                    description=default_spec.description,
                )
            else:
                custom_dimensions[name] = DimensionSpec(
                    name=name, threshold=threshold, weight=1.0, required=False
                )

    return ResponseQualityValidator(scorer=scorer, custom_dimensions=custom_dimensions)


__all__ = [
    "CONSTITUTIONAL_HASH",
    "ConstitutionalHashError",
    "DimensionSpec",
    "ResponseQualityValidator",
    "ResponseScorer",
    "ValidationConfig",
    "ValidationError",
    "create_validator",
]
