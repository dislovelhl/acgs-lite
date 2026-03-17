"""
ACGS-2 Response Quality Enhancement - Tests
Constitutional Hash: cdd01ef066bc6cf2

Comprehensive test suite for response quality validation and refinement.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from packages.enhanced_agent_bus.response_quality import (
    # Constants
    CONSTITUTIONAL_HASH,
    # Validator
    ConstitutionalHashError,
    ConstitutionalViolationError,
    DefaultConstitutionalCorrector,
    DefaultLLMRefiner,
    DimensionSpec,
    QualityAssessment,
    # Models - Dataclasses
    QualityDimension,
    # Models - Enums
    QualityLevel,
    RefinementConfig,
    # Refiner
    RefinementError,
    RefinementIteration,
    RefinementResult,
    RefinementStatus,
    ResponseQualityValidator,
    ResponseRefiner,
    ValidationConfig,
    ValidationError,
    create_refiner,
    create_validator,
)
from src.core.shared.errors.exceptions import ValidationError as ACGSValidationError

# ============================================================================
# Test Constants
# ============================================================================


class TestConstitutionalHash:
    """Tests for constitutional hash consistency."""

    def test_hash_value(self):
        """Test constitutional hash has expected value."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_hash_length(self):
        """Test constitutional hash has expected length."""
        assert len(CONSTITUTIONAL_HASH) == 16

    def test_hash_is_hex(self):
        """Test constitutional hash is valid hex."""
        int(CONSTITUTIONAL_HASH, 16)  # Should not raise


# ============================================================================
# Test QualityDimension
# ============================================================================


class TestQualityDimension:
    """Tests for QualityDimension dataclass."""

    def test_basic_creation(self):
        """Test basic dimension creation."""
        dim = QualityDimension(name="accuracy", score=0.85, threshold=0.8)
        assert dim.name == "accuracy"
        assert dim.score == 0.85
        assert dim.threshold == 0.8

    def test_with_critique(self):
        """Test dimension with critique."""
        dim = QualityDimension(
            name="coherence", score=0.6, threshold=0.7, critique="Response lacks logical flow"
        )
        assert dim.critique == "Response lacks logical flow"

    def test_passes_property_true(self):
        """Test passes property when score meets threshold."""
        dim = QualityDimension(name="test", score=0.9, threshold=0.8)
        assert dim.passes is True

    def test_passes_property_false(self):
        """Test passes property when score below threshold."""
        dim = QualityDimension(name="test", score=0.7, threshold=0.8)
        assert dim.passes is False

    def test_passes_property_equal(self):
        """Test passes property when score equals threshold."""
        dim = QualityDimension(name="test", score=0.8, threshold=0.8)
        assert dim.passes is True

    def test_gap_positive(self):
        """Test gap when passing."""
        dim = QualityDimension(name="test", score=0.9, threshold=0.8)
        assert dim.gap == pytest.approx(0.1)

    def test_gap_negative(self):
        """Test gap when failing."""
        dim = QualityDimension(name="test", score=0.6, threshold=0.8)
        assert dim.gap == pytest.approx(-0.2)

    def test_level_excellent(self):
        """Test excellent quality level."""
        dim = QualityDimension(name="test", score=0.98, threshold=0.8)
        assert dim.level == QualityLevel.EXCELLENT

    def test_level_good(self):
        """Test good quality level."""
        dim = QualityDimension(name="test", score=0.85, threshold=0.8)
        assert dim.level == QualityLevel.GOOD

    def test_level_acceptable(self):
        """Test acceptable quality level."""
        dim = QualityDimension(name="test", score=0.65, threshold=0.5)
        assert dim.level == QualityLevel.ACCEPTABLE

    def test_level_poor(self):
        """Test poor quality level."""
        dim = QualityDimension(name="test", score=0.45, threshold=0.5)
        assert dim.level == QualityLevel.POOR

    def test_level_unacceptable(self):
        """Test unacceptable quality level."""
        dim = QualityDimension(name="test", score=0.2, threshold=0.5)
        assert dim.level == QualityLevel.UNACCEPTABLE

    def test_score_validation_too_high(self):
        """Test score validation for values > 1.0."""
        with pytest.raises((ValueError, ACGSValidationError), match="Score must be between"):
            QualityDimension(name="test", score=1.5, threshold=0.8)

    def test_score_validation_too_low(self):
        """Test score validation for values < 0.0."""
        with pytest.raises((ValueError, ACGSValidationError), match="Score must be between"):
            QualityDimension(name="test", score=-0.1, threshold=0.8)

    def test_threshold_validation_too_high(self):
        """Test threshold validation for values > 1.0."""
        with pytest.raises((ValueError, ACGSValidationError), match="Threshold must be between"):
            QualityDimension(name="test", score=0.8, threshold=1.5)

    def test_to_dict(self):
        """Test dictionary conversion."""
        dim = QualityDimension(name="accuracy", score=0.85, threshold=0.8)
        d = dim.to_dict()
        assert d["name"] == "accuracy"
        assert d["score"] == 0.85
        assert d["threshold"] == 0.8
        assert d["passes"] is True
        assert "gap" in d
        assert "level" in d


# ============================================================================
# Test QualityAssessment
# ============================================================================


class TestQualityAssessment:
    """Tests for QualityAssessment dataclass."""

    @pytest.fixture
    def sample_dimensions(self) -> list[QualityDimension]:
        """Create sample dimensions for testing."""
        return [
            QualityDimension(name="accuracy", score=0.9, threshold=0.8),
            QualityDimension(name="coherence", score=0.8, threshold=0.7),
            QualityDimension(name="safety", score=0.99, threshold=0.99),
        ]

    def test_basic_creation(self, sample_dimensions):
        """Test basic assessment creation."""
        assessment = QualityAssessment(
            dimensions=sample_dimensions,
            overall_score=0.89,
            passes_threshold=True,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        assert assessment.overall_score == 0.89
        assert assessment.passes_threshold is True

    def test_dimension_count(self, sample_dimensions):
        """Test dimension count property."""
        assessment = QualityAssessment(
            dimensions=sample_dimensions,
            overall_score=0.89,
            passes_threshold=True,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        assert assessment.dimension_count == 3

    def test_passing_dimensions(self, sample_dimensions):
        """Test passing dimensions property."""
        assessment = QualityAssessment(
            dimensions=sample_dimensions,
            overall_score=0.89,
            passes_threshold=True,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        passing = assessment.passing_dimensions
        assert len(passing) == 3

    def test_failing_dimensions(self):
        """Test failing dimensions property."""
        dims = [
            QualityDimension(name="accuracy", score=0.7, threshold=0.8),  # Fails
            QualityDimension(name="coherence", score=0.8, threshold=0.7),  # Passes
        ]
        assessment = QualityAssessment(
            dimensions=dims,
            overall_score=0.75,
            passes_threshold=False,
            refinement_suggestions=["Improve accuracy"],
            constitutional_compliance=True,
        )
        failing = assessment.failing_dimensions
        assert len(failing) == 1
        assert failing[0].name == "accuracy"

    def test_pass_rate(self, sample_dimensions):
        """Test pass rate calculation."""
        assessment = QualityAssessment(
            dimensions=sample_dimensions,
            overall_score=0.89,
            passes_threshold=True,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        assert assessment.pass_rate == 1.0

    def test_pass_rate_partial(self):
        """Test pass rate with some failures."""
        dims = [
            QualityDimension(name="a", score=0.9, threshold=0.8),
            QualityDimension(name="b", score=0.5, threshold=0.8),
        ]
        assessment = QualityAssessment(
            dimensions=dims,
            overall_score=0.7,
            passes_threshold=False,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        assert assessment.pass_rate == 0.5

    def test_critical_failures(self):
        """Test critical failures detection."""
        dims = [
            QualityDimension(name="safety", score=0.5, threshold=0.99),
            QualityDimension(name="accuracy", score=0.7, threshold=0.8),
        ]
        assessment = QualityAssessment(
            dimensions=dims,
            overall_score=0.6,
            passes_threshold=False,
            refinement_suggestions=[],
            constitutional_compliance=False,
        )
        critical = assessment.critical_failures
        assert len(critical) == 1
        assert critical[0].name == "safety"

    def test_needs_refinement_false(self, sample_dimensions):
        """Test needs_refinement when passing."""
        assessment = QualityAssessment(
            dimensions=sample_dimensions,
            overall_score=0.89,
            passes_threshold=True,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        assert assessment.needs_refinement is False

    def test_needs_refinement_true(self):
        """Test needs_refinement when failing."""
        dims = [QualityDimension(name="a", score=0.5, threshold=0.8)]
        assessment = QualityAssessment(
            dimensions=dims,
            overall_score=0.5,
            passes_threshold=False,
            refinement_suggestions=["Improve"],
            constitutional_compliance=True,
        )
        assert assessment.needs_refinement is True

    def test_get_dimension(self, sample_dimensions):
        """Test get_dimension by name."""
        assessment = QualityAssessment(
            dimensions=sample_dimensions,
            overall_score=0.89,
            passes_threshold=True,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        dim = assessment.get_dimension("accuracy")
        assert dim is not None
        assert dim.score == 0.9

    def test_get_dimension_not_found(self, sample_dimensions):
        """Test get_dimension for non-existent dimension."""
        assessment = QualityAssessment(
            dimensions=sample_dimensions,
            overall_score=0.89,
            passes_threshold=True,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        dim = assessment.get_dimension("nonexistent")
        assert dim is None

    def test_to_dict(self, sample_dimensions):
        """Test dictionary conversion."""
        assessment = QualityAssessment(
            dimensions=sample_dimensions,
            overall_score=0.89,
            passes_threshold=True,
            refinement_suggestions=["suggestion1"],
            constitutional_compliance=True,
            response_id="test-123",
        )
        d = assessment.to_dict()
        assert d["overall_score"] == 0.89
        assert d["passes_threshold"] is True
        assert d["response_id"] == "test-123"
        assert len(d["dimensions"]) == 3

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "dimensions": [{"name": "accuracy", "score": 0.9, "threshold": 0.8}],
            "overall_score": 0.9,
            "passes_threshold": True,
            "refinement_suggestions": [],
            "constitutional_compliance": True,
        }
        assessment = QualityAssessment.from_dict(data)
        assert assessment.overall_score == 0.9
        assert len(assessment.dimensions) == 1

    def test_overall_score_validation(self, sample_dimensions):
        """Test overall score validation."""
        with pytest.raises(
            (ValueError, ACGSValidationError), match="Overall score must be between"
        ):
            QualityAssessment(
                dimensions=sample_dimensions,
                overall_score=1.5,
                passes_threshold=True,
                refinement_suggestions=[],
                constitutional_compliance=True,
            )


# ============================================================================
# Test DimensionSpec
# ============================================================================


class TestDimensionSpec:
    """Tests for DimensionSpec dataclass."""

    def test_basic_creation(self):
        """Test basic spec creation."""
        spec = DimensionSpec(name="accuracy", threshold=0.8)
        assert spec.name == "accuracy"
        assert spec.threshold == 0.8
        assert spec.weight == 1.0
        assert spec.required is False

    def test_with_all_fields(self):
        """Test spec with all fields."""
        spec = DimensionSpec(
            name="safety", threshold=0.99, weight=2.0, required=True, description="Safety check"
        )
        assert spec.weight == 2.0
        assert spec.required is True
        assert spec.description == "Safety check"

    def test_threshold_validation(self):
        """Test threshold validation."""
        with pytest.raises((ValueError, ACGSValidationError)):
            DimensionSpec(name="test", threshold=1.5)

    def test_weight_validation(self):
        """Test weight validation."""
        with pytest.raises((ValueError, ACGSValidationError)):
            DimensionSpec(name="test", threshold=0.8, weight=-1.0)


# ============================================================================
# Test ResponseQualityValidator
# ============================================================================


class TestResponseQualityValidator:
    """Tests for ResponseQualityValidator."""

    def test_default_creation(self):
        """Test default validator creation."""
        validator = ResponseQualityValidator()
        assert len(validator.dimensions) == 5
        assert "accuracy" in validator.dimensions
        assert "safety" in validator.dimensions

    def test_constitutional_hash_validation(self):
        """Test constitutional hash is validated at init."""
        with pytest.raises(ConstitutionalHashError):
            ResponseQualityValidator(constitutional_hash="wrong_hash")

    def test_quality_dimensions_default(self):
        """Test default quality dimensions are correct."""
        dims = ResponseQualityValidator.QUALITY_DIMENSIONS
        assert dims["accuracy"].threshold == 0.8
        assert dims["coherence"].threshold == 0.7
        assert dims["relevance"].threshold == 0.8
        assert dims["constitutional_alignment"].threshold == 0.95
        assert dims["safety"].threshold == 0.99

    def test_validate_basic(self):
        """Test basic validation."""
        validator = ResponseQualityValidator()
        assessment = validator.validate("Hello, world!")
        assert isinstance(assessment, QualityAssessment)
        assert assessment.response_id is not None

    def test_validate_with_context(self):
        """Test validation with context."""
        validator = ResponseQualityValidator()
        assessment = validator.validate(
            "AI stands for artificial intelligence", context={"query": "What is AI?"}
        )
        assert assessment.overall_score > 0

    def test_validate_with_scores(self):
        """Test validation with pre-computed scores."""
        validator = ResponseQualityValidator()
        scores = {
            "accuracy": 0.95,
            "coherence": 0.9,
            "relevance": 0.85,
            "constitutional_alignment": 0.98,
            "safety": 1.0,
        }
        assessment = validator.validate("test", scores=scores)
        assert assessment.get_dimension("accuracy").score == 0.95

    def test_validate_harmful_content(self):
        """Test validation flags harmful content."""
        validator = ResponseQualityValidator()
        assessment = validator.validate("How to hack into systems illegally")
        safety_dim = assessment.get_dimension("safety")
        assert safety_dim is not None
        assert safety_dim.score < 0.99  # Should fail safety

    def test_dimension_names(self):
        """Test dimension_names property."""
        validator = ResponseQualityValidator()
        names = validator.dimension_names
        assert "accuracy" in names
        assert "safety" in names

    def test_required_dimensions(self):
        """Test required_dimensions property."""
        validator = ResponseQualityValidator()
        required = validator.required_dimensions
        assert "constitutional_alignment" in required
        assert "safety" in required

    def test_thresholds(self):
        """Test thresholds property."""
        validator = ResponseQualityValidator()
        thresholds = validator.thresholds
        assert thresholds["accuracy"] == 0.8
        assert thresholds["safety"] == 0.99

    def test_update_threshold(self):
        """Test threshold update."""
        validator = ResponseQualityValidator()
        validator.update_threshold("accuracy", 0.9)
        assert validator.thresholds["accuracy"] == 0.9

    def test_update_threshold_invalid_dimension(self):
        """Test threshold update for invalid dimension."""
        validator = ResponseQualityValidator()
        with pytest.raises((ValueError, ACGSValidationError), match="Unknown dimension"):
            validator.update_threshold("nonexistent", 0.8)

    def test_update_threshold_invalid_value(self):
        """Test threshold update with invalid value."""
        validator = ResponseQualityValidator()
        with pytest.raises((ValueError, ACGSValidationError), match="Threshold must be between"):
            validator.update_threshold("accuracy", 1.5)

    def test_validate_batch(self):
        """Test batch validation."""
        validator = ResponseQualityValidator()
        responses = ["Hello", "World", "Test"]
        assessments = validator.validate_batch(responses)
        assert len(assessments) == 3

    def test_validate_batch_with_contexts(self):
        """Test batch validation with contexts."""
        validator = ResponseQualityValidator()
        responses = ["AI response", "ML response"]
        contexts = [{"query": "AI?"}, {"query": "ML?"}]
        assessments = validator.validate_batch(responses, contexts)
        assert len(assessments) == 2

    def test_validate_batch_mismatched_lengths(self):
        """Test batch validation with mismatched lengths."""
        validator = ResponseQualityValidator()
        with pytest.raises((ValueError, ACGSValidationError)):
            validator.validate_batch(["a", "b"], [{"query": "a"}])

    def test_stats(self):
        """Test stats property."""
        validator = ResponseQualityValidator()
        validator.validate("test")
        stats = validator.stats
        assert stats["validation_count"] == 1
        assert "constitutional_hash" in stats

    def test_reset_validation_count(self):
        """Test validation count reset."""
        validator = ResponseQualityValidator()
        validator.validate("test")
        validator.validate("test2")
        validator.reset_validation_count()
        assert validator.stats["validation_count"] == 0


class TestCreateValidator:
    """Tests for create_validator factory function."""

    def test_default_creation(self):
        """Test default factory creation."""
        validator = create_validator()
        assert isinstance(validator, ResponseQualityValidator)

    def test_with_custom_thresholds(self):
        """Test factory with custom thresholds."""
        validator = create_validator(thresholds={"accuracy": 0.9})
        assert validator.thresholds["accuracy"] == 0.9

    def test_with_new_dimension(self):
        """Test factory with new dimension."""
        validator = create_validator(thresholds={"custom_dim": 0.75})
        assert "custom_dim" in validator.dimensions


# ============================================================================
# Test RefinementIteration
# ============================================================================


class TestRefinementIteration:
    """Tests for RefinementIteration dataclass."""

    @pytest.fixture
    def sample_assessments(self):
        """Create sample assessments."""
        dim1 = [QualityDimension(name="a", score=0.7, threshold=0.8)]
        dim2 = [QualityDimension(name="a", score=0.85, threshold=0.8)]
        before = QualityAssessment(
            dimensions=dim1,
            overall_score=0.7,
            passes_threshold=False,
            refinement_suggestions=["Improve"],
            constitutional_compliance=True,
        )
        after = QualityAssessment(
            dimensions=dim2,
            overall_score=0.85,
            passes_threshold=True,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        return before, after

    def test_basic_creation(self, sample_assessments):
        """Test basic iteration creation."""
        before, after = sample_assessments
        iteration = RefinementIteration(
            iteration_number=1,
            original_response="original",
            refined_response="refined",
            before_assessment=before,
            after_assessment=after,
        )
        assert iteration.iteration_number == 1

    def test_improvement_delta(self, sample_assessments):
        """Test improvement delta calculation."""
        before, after = sample_assessments
        iteration = RefinementIteration(
            iteration_number=1,
            original_response="original",
            refined_response="refined",
            before_assessment=before,
            after_assessment=after,
        )
        assert iteration.improvement_delta == pytest.approx(0.15)

    def test_improved_property(self, sample_assessments):
        """Test improved property."""
        before, after = sample_assessments
        iteration = RefinementIteration(
            iteration_number=1,
            original_response="original",
            refined_response="refined",
            before_assessment=before,
            after_assessment=after,
        )
        assert iteration.improved is True

    def test_now_passes(self, sample_assessments):
        """Test now_passes property."""
        before, after = sample_assessments
        iteration = RefinementIteration(
            iteration_number=1,
            original_response="original",
            refined_response="refined",
            before_assessment=before,
            after_assessment=after,
        )
        assert iteration.now_passes is True


# ============================================================================
# Test RefinementResult
# ============================================================================


class TestRefinementResult:
    """Tests for RefinementResult dataclass."""

    @pytest.fixture
    def sample_result(self):
        """Create sample refinement result."""
        dim = [QualityDimension(name="a", score=0.9, threshold=0.8)]
        assessment = QualityAssessment(
            dimensions=dim,
            overall_score=0.9,
            passes_threshold=True,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        return RefinementResult(
            original_response="original",
            final_response="refined",
            iterations=[],
            total_iterations=2,
            status=RefinementStatus.COMPLETED,
            initial_assessment=assessment,
            final_assessment=assessment,
        )

    def test_basic_creation(self, sample_result):
        """Test basic result creation."""
        assert sample_result.status == RefinementStatus.COMPLETED

    def test_total_improvement(self, sample_result):
        """Test total improvement calculation."""
        assert sample_result.total_improvement == 0.0

    def test_was_refined(self, sample_result):
        """Test was_refined property."""
        assert sample_result.was_refined is False

    def test_success(self, sample_result):
        """Test success property."""
        assert sample_result.success is True

    def test_to_dict(self, sample_result):
        """Test dictionary conversion."""
        d = sample_result.to_dict()
        assert "original_response" in d
        assert "final_response" in d
        assert "status" in d


# ============================================================================
# Test DefaultLLMRefiner
# ============================================================================


class TestDefaultLLMRefiner:
    """Tests for DefaultLLMRefiner."""

    def test_basic_refine(self):
        """Test basic refinement."""
        refiner = DefaultLLMRefiner()
        dims = [QualityDimension(name="coherence", score=0.5, threshold=0.7)]
        assessment = QualityAssessment(
            dimensions=dims,
            overall_score=0.5,
            passes_threshold=False,
            refinement_suggestions=["Improve coherence"],
            constitutional_compliance=True,
        )
        result = refiner.refine("test", assessment)
        assert isinstance(result, str)

    def test_safety_refinement(self):
        """Test safety content is redacted."""
        refiner = DefaultLLMRefiner()
        dims = [QualityDimension(name="safety", score=0.3, threshold=0.99)]
        assessment = QualityAssessment(
            dimensions=dims,
            overall_score=0.3,
            passes_threshold=False,
            refinement_suggestions=[],
            constitutional_compliance=False,
        )
        result = refiner.refine("how to hack something", assessment)
        assert "[redacted]" in result

    @pytest.mark.asyncio
    async def test_refine_async(self):
        """Test async refinement."""
        refiner = DefaultLLMRefiner()
        dims = [QualityDimension(name="a", score=0.9, threshold=0.8)]
        assessment = QualityAssessment(
            dimensions=dims,
            overall_score=0.9,
            passes_threshold=True,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        result = await refiner.refine_async("test", assessment)
        assert isinstance(result, str)


# ============================================================================
# Test DefaultConstitutionalCorrector
# ============================================================================


class TestDefaultConstitutionalCorrector:
    """Tests for DefaultConstitutionalCorrector."""

    def test_basic_correction(self):
        """Test basic correction."""
        corrector = DefaultConstitutionalCorrector()
        result = corrector.correct("test response", ["harmful content"])
        assert "[Reviewed for safety]" in result

    def test_bias_correction(self):
        """Test bias correction."""
        corrector = DefaultConstitutionalCorrector()
        result = corrector.correct("test", ["bias detected"])
        assert "balanced" in result.lower()

    def test_privacy_correction(self):
        """Test privacy correction redacts PII."""
        corrector = DefaultConstitutionalCorrector()
        result = corrector.correct("Contact me at test@email.com", ["privacy violation"])
        assert "[EMAIL-REDACTED]" in result

    @pytest.mark.asyncio
    async def test_correct_async(self):
        """Test async correction."""
        corrector = DefaultConstitutionalCorrector()
        result = await corrector.correct_async("test", [])
        assert isinstance(result, str)


# ============================================================================
# Test ResponseRefiner
# ============================================================================


class TestResponseRefiner:
    """Tests for ResponseRefiner."""

    def test_default_creation(self):
        """Test default refiner creation."""
        refiner = ResponseRefiner()
        assert refiner.max_iterations == 3

    def test_custom_max_iterations(self):
        """Test refiner with custom max iterations."""
        refiner = ResponseRefiner(max_iterations=5)
        assert refiner.max_iterations == 5

    def test_refine_already_passing(self):
        """Test refine skips when already passing."""
        validator = ResponseQualityValidator()
        refiner = ResponseRefiner(validator=validator)

        # Mock high scores
        with patch.object(validator, "_default_scoring") as mock_scoring:
            mock_scoring.return_value = {
                "accuracy": 0.95,
                "coherence": 0.9,
                "relevance": 0.9,
                "constitutional_alignment": 0.98,
                "safety": 1.0,
            }
            result = refiner.refine("Good response")

        assert result.status == RefinementStatus.SKIPPED
        assert result.total_iterations == 0

    def test_refine_basic(self):
        """Test basic refinement."""
        refiner = ResponseRefiner(max_iterations=1)
        result = refiner.refine("incomplete")
        assert isinstance(result, RefinementResult)

    def test_refine_with_context(self):
        """Test refinement with context."""
        refiner = ResponseRefiner(max_iterations=1)
        result = refiner.refine("AI answer", context={"query": "What is AI?"})
        assert result is not None

    def test_stats(self):
        """Test stats property."""
        refiner = ResponseRefiner()
        stats = refiner.stats
        assert "refinement_count" in stats
        assert "constitutional_hash" in stats
        assert stats["max_iterations"] == 3

    def test_set_constitutional_corrector(self):
        """Test setting custom corrector."""
        refiner = ResponseRefiner()
        mock_corrector = MagicMock()
        refiner.set_constitutional_corrector(mock_corrector)
        assert refiner.constitutional_corrector is mock_corrector

    def test_set_llm_refiner(self):
        """Test setting custom LLM refiner."""
        refiner = ResponseRefiner()
        mock_refiner = MagicMock()
        refiner.set_llm_refiner(mock_refiner)
        assert refiner.llm_refiner is mock_refiner

    def test_refine_batch(self):
        """Test batch refinement."""
        refiner = ResponseRefiner(max_iterations=1)
        results = refiner.refine_batch(["a", "b", "c"])
        assert len(results) == 3

    def test_refine_batch_with_contexts(self):
        """Test batch refinement with contexts."""
        refiner = ResponseRefiner(max_iterations=1)
        results = refiner.refine_batch(["a", "b"], contexts=[{"query": "A?"}, {"query": "B?"}])
        assert len(results) == 2

    def test_refine_batch_mismatched_lengths(self):
        """Test batch refinement with mismatched lengths."""
        refiner = ResponseRefiner()
        with pytest.raises((ValueError, ACGSValidationError)):
            refiner.refine_batch(["a", "b"], [{"query": "a"}])

    @pytest.mark.asyncio
    async def test_refine_async(self):
        """Test async refinement."""
        refiner = ResponseRefiner(max_iterations=1)
        result = await refiner.refine_async("test response")
        assert isinstance(result, RefinementResult)

    @pytest.mark.asyncio
    async def test_refine_batch_async(self):
        """Test async batch refinement."""
        refiner = ResponseRefiner(max_iterations=1)
        results = await refiner.refine_batch_async(["a", "b"])
        assert len(results) == 2


class TestCreateRefiner:
    """Tests for create_refiner factory function."""

    def test_default_creation(self):
        """Test default factory creation."""
        refiner = create_refiner()
        assert isinstance(refiner, ResponseRefiner)
        assert refiner.max_iterations == 3

    def test_custom_max_iterations(self):
        """Test factory with custom iterations."""
        refiner = create_refiner(max_iterations=5)
        assert refiner.max_iterations == 5

    def test_with_validator(self):
        """Test factory with custom validator."""
        validator = ResponseQualityValidator()
        refiner = create_refiner(validator=validator)
        assert refiner.validator is validator


# ============================================================================
# Test RefinementConfig
# ============================================================================


class TestRefinementConfig:
    """Tests for RefinementConfig."""

    def test_default_values(self):
        """Test default config values."""
        config = RefinementConfig()
        assert config.max_iterations == 3
        assert config.improvement_threshold == 0.01
        assert config.stop_on_pass is True
        assert config.require_constitutional is True

    def test_custom_values(self):
        """Test custom config values."""
        config = RefinementConfig(max_iterations=5, improvement_threshold=0.05, stop_on_pass=False)
        assert config.max_iterations == 5
        assert config.improvement_threshold == 0.05
        assert config.stop_on_pass is False


# ============================================================================
# Test ValidationConfig
# ============================================================================


class TestValidationConfig:
    """Tests for ValidationConfig."""

    def test_default_values(self):
        """Test default config values."""
        config = ValidationConfig()
        assert config.require_all_dimensions is True
        assert config.fail_on_any_critical is True
        assert config.overall_threshold == 0.7

    def test_constitutional_hash(self):
        """Test constitutional hash in config."""
        config = ValidationConfig()
        assert config.constitutional_hash == CONSTITUTIONAL_HASH


# ============================================================================
# Test Enums
# ============================================================================


class TestEnums:
    """Tests for enum classes."""

    def test_quality_level_values(self):
        """Test QualityLevel enum values."""
        assert QualityLevel.EXCELLENT.value == "excellent"
        assert QualityLevel.GOOD.value == "good"
        assert QualityLevel.ACCEPTABLE.value == "acceptable"
        assert QualityLevel.POOR.value == "poor"
        assert QualityLevel.UNACCEPTABLE.value == "unacceptable"

    def test_refinement_status_values(self):
        """Test RefinementStatus enum values."""
        assert RefinementStatus.PENDING.value == "pending"
        assert RefinementStatus.IN_PROGRESS.value == "in_progress"
        assert RefinementStatus.COMPLETED.value == "completed"
        assert RefinementStatus.FAILED.value == "failed"
        assert RefinementStatus.SKIPPED.value == "skipped"


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for the response quality module."""

    def test_validator_refiner_integration(self):
        """Test validator and refiner work together."""
        validator = ResponseQualityValidator()
        refiner = ResponseRefiner(validator=validator, max_iterations=2)

        # Validate and refine
        result = refiner.refine("Short incomplete response")

        assert result.initial_assessment is not None
        assert result.final_assessment is not None
        assert isinstance(result.status, RefinementStatus)

    def test_full_pipeline(self):
        """Test full quality pipeline."""
        # Create components
        validator = ResponseQualityValidator()
        refiner = ResponseRefiner(validator=validator, max_iterations=2)

        # Process response
        response = "AI is artificial intelligence used in many applications"
        result = refiner.refine(response, context={"query": "What is AI?"})

        # Verify result structure
        assert result.original_response == response
        assert result.final_response is not None
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    @pytest.mark.asyncio
    async def test_async_pipeline(self):
        """Test async quality pipeline."""
        validator = ResponseQualityValidator()
        refiner = ResponseRefiner(validator=validator, max_iterations=1)

        result = await refiner.refine_async("Test async response")

        assert isinstance(result, RefinementResult)
        assert result.final_response is not None
