"""
ACGS-2 Enhanced Agent Bus - Response Quality Extension Exports
Constitutional Hash: 608508a9bd224290

Extension module for Phase 5: Response Quality Enhancement.
Provides graceful-fallback import interface for response quality components,
following the established _ext_*.py pattern in this package.
"""

try:
    from .response_quality import (
        RESPONSE_QUALITY_AVAILABLE,
        AlignmentScorer,
        CoherenceScorer,
        CompletenessScorer,
        ConstitutionalValidator,
        PipelineConfig,
        PipelineRunResult,
        PipelineStageConfig,
        QualityDimension,
        QualityScore,
        QualityScorer,
        RefinementConfig,
        RefinementResult,
        RefinementStep,
        ResponseRefiner,
        ResponseValidationPipeline,
        ScorerThresholds,
        SemanticValidator,
        SyntaxValidator,
        ValidationStage,
        create_quality_scorer,
        create_response_refiner,
        create_validation_pipeline,
    )
    from .response_quality import (
        # Alias RefinementCallback for stable external reference
        RefinementCallback as ResponseRefinementCallback,
    )
    from .response_quality import (
        # Alias ValidationResult to avoid collision with bus-level validators.ValidationResult
        ValidationResult as ResponseValidationResult,
    )

except ImportError:
    RESPONSE_QUALITY_AVAILABLE = False

    # Task 5.1 stubs
    ValidationStage = object  # type: ignore[assignment, misc]
    ResponseValidationResult = object  # type: ignore[assignment, misc]
    PipelineStageConfig = object  # type: ignore[assignment, misc]
    PipelineConfig = object  # type: ignore[assignment, misc]
    PipelineRunResult = object  # type: ignore[assignment, misc]
    SyntaxValidator = object  # type: ignore[assignment, misc]
    SemanticValidator = object  # type: ignore[assignment, misc]
    ConstitutionalValidator = object  # type: ignore[assignment, misc]
    ResponseValidationPipeline = object  # type: ignore[assignment, misc]
    create_validation_pipeline = None  # type: ignore[assignment]

    # Task 5.2 stubs
    QualityDimension = object  # type: ignore[assignment, misc]
    QualityScore = object  # type: ignore[assignment, misc]
    ScorerThresholds = object  # type: ignore[assignment, misc]
    CoherenceScorer = object  # type: ignore[assignment, misc]
    CompletenessScorer = object  # type: ignore[assignment, misc]
    AlignmentScorer = object  # type: ignore[assignment, misc]
    QualityScorer = object  # type: ignore[assignment, misc]
    create_quality_scorer = None  # type: ignore[assignment]

    # Task 5.3 stubs
    RefinementConfig = object  # type: ignore[assignment, misc]
    RefinementStep = object  # type: ignore[assignment, misc]
    RefinementResult = object  # type: ignore[assignment, misc]
    ResponseRefinementCallback = object  # type: ignore[assignment, misc]
    ResponseRefiner = object  # type: ignore[assignment, misc]
    create_response_refiner = None  # type: ignore[assignment]

__all__ = [
    "RESPONSE_QUALITY_AVAILABLE",
    "AlignmentScorer",
    "CoherenceScorer",
    "CompletenessScorer",
    "ConstitutionalValidator",
    "PipelineConfig",
    "PipelineRunResult",
    "PipelineStageConfig",
    # Task 5.2: Quality scoring
    "QualityDimension",
    "QualityScore",
    "QualityScorer",
    # Task 5.3: Response refinement
    "RefinementConfig",
    "RefinementResult",
    "RefinementStep",
    "ResponseRefinementCallback",
    "ResponseRefiner",
    "ResponseValidationPipeline",
    "ResponseValidationResult",
    "ScorerThresholds",
    "SemanticValidator",
    "SyntaxValidator",
    # Task 5.1: Validation pipeline
    "ValidationStage",
    "create_quality_scorer",
    "create_response_refiner",
    "create_validation_pipeline",
]

_EXT_ALL = __all__
