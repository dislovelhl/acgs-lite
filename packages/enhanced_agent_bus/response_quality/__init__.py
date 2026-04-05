"""
ACGS-2 Response Quality Enhancement Module
Constitutional Hash: 608508a9bd224290

This module provides response quality validation and iterative refinement
capabilities for LLM-generated responses, ensuring constitutional compliance
and high-quality outputs.

Key Components:
    - QualityDimension: Individual quality dimension assessment
    - QualityAssessment: Complete quality evaluation
    - ResponseQualityValidator: Multi-dimensional quality validation
    - ResponseRefiner: Iterative response improvement

Usage:
    >>> from packages.enhanced_agent_bus.response_quality import (
    ...     ResponseQualityValidator,
    ...     ResponseRefiner,
    ... )
    >>>
    >>> validator = ResponseQualityValidator()
    >>> assessment = validator.validate("Hello, world!")
    >>>
    >>> refiner = ResponseRefiner(validator=validator)
    >>> result = refiner.refine("incomplete response")
"""

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

# Models
from .models import (
    CONSTITUTIONAL_HASH as MODELS_HASH,
)
from .models import (
    DimensionScores,
    QualityAssessment,
    QualityDimension,
    QualityLevel,
    RefinementIteration,
    RefinementResult,
    RefinementStatus,
    SuggestionList,
)

# Refiner
from .refiner import (
    CONSTITUTIONAL_HASH as REFINER_HASH,
)
from .refiner import (
    AdapterConstitutionalCorrector,
    AdapterLLMRefiner,
    ConstitutionalSelfCorrector,
    ConstitutionalViolationError,
    DefaultConstitutionalCorrector,
    DefaultLLMRefiner,
    LLMRefiner,
    RefinementConfig,
    RefinementError,
    ResponseRefiner,
    create_refiner,
)

# Validator
from .validator import (
    CONSTITUTIONAL_HASH as VALIDATOR_HASH,
)
from .validator import (
    ConstitutionalHashError,
    DimensionSpec,
    ResponseQualityValidator,
    ResponseScorer,
    ValidationConfig,
    ValidationError,
    create_validator,
)


# Verify constitutional hash consistency across modules
def _verify_constitutional_hashes() -> None:
    """Verify all module hashes match."""
    hashes = [CONSTITUTIONAL_HASH, MODELS_HASH, VALIDATOR_HASH, REFINER_HASH]
    if not all(h == CONSTITUTIONAL_HASH for h in hashes):
        raise RuntimeError(
            f"Constitutional hash mismatch across modules. Expected: {CONSTITUTIONAL_HASH}"
        )


# Run verification on import
_verify_constitutional_hashes()


# Backward compatibility type aliases
# ResponseQualityAssessor is an alias for ResponseQualityValidator
ResponseQualityAssessor = ResponseQualityValidator
# ResponseQualityMetrics is an alias for QualityAssessment
ResponseQualityMetrics = QualityAssessment

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    # Validator - Exceptions
    "ConstitutionalHashError",
    # Refiner - Protocols
    "ConstitutionalSelfCorrector",
    "ConstitutionalViolationError",
    "DefaultConstitutionalCorrector",
    "AdapterConstitutionalCorrector",
    # Refiner - Default implementations
    "DefaultLLMRefiner",
    "AdapterLLMRefiner",
    # Models - Type aliases
    "DimensionScores",
    # Validator - Classes
    "DimensionSpec",
    "LLMRefiner",
    "QualityAssessment",
    # Models - Dataclasses
    "QualityDimension",
    # Models - Enums
    "QualityLevel",
    # Refiner - Config
    "RefinementConfig",
    # Refiner - Exceptions
    "RefinementError",
    "RefinementIteration",
    "RefinementResult",
    "RefinementStatus",
    # Backward compatibility aliases
    "ResponseQualityAssessor",
    "ResponseQualityMetrics",
    "ResponseQualityValidator",
    # Refiner - Main class
    "ResponseRefiner",
    "ResponseScorer",
    "SuggestionList",
    "ValidationConfig",
    "ValidationError",
    # Refiner - Factory
    "create_refiner",
    # Validator - Factory
    "create_validator",
]
