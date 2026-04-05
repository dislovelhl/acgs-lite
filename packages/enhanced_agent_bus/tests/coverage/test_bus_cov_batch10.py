"""
Comprehensive coverage tests for enhanced_agent_bus modules (batch 10).

Targets:
- enhanced_agent_bus.response_quality (models, validator, refiner submodules)
- enhanced_agent_bus.deliberation_layer.integration (194 missing, 59.8%)
- enhanced_agent_bus.constitutional.review_api (150 missing, 49.8%)
- enhanced_agent_bus.deliberation_layer.timeout_checker (118 missing, 0%)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError

# =============================================================================
# Module 1: response_quality.models
# =============================================================================


class TestQualityLevel:
    def test_all_values(self):
        from enhanced_agent_bus.response_quality.models import QualityLevel

        assert QualityLevel.EXCELLENT.value == "excellent"
        assert QualityLevel.GOOD.value == "good"
        assert QualityLevel.ACCEPTABLE.value == "acceptable"
        assert QualityLevel.POOR.value == "poor"
        assert QualityLevel.UNACCEPTABLE.value == "unacceptable"


class TestRefinementStatus:
    def test_all_values(self):
        from enhanced_agent_bus.response_quality.models import RefinementStatus

        assert RefinementStatus.PENDING.value == "pending"
        assert RefinementStatus.IN_PROGRESS.value == "in_progress"
        assert RefinementStatus.COMPLETED.value == "completed"
        assert RefinementStatus.FAILED.value == "failed"
        assert RefinementStatus.SKIPPED.value == "skipped"


class TestQualityDimension:
    def test_basic_creation(self):
        from enhanced_agent_bus.response_quality.models import QualityDimension

        dim = QualityDimension(name="accuracy", score=0.9, threshold=0.8)
        assert dim.name == "accuracy"
        assert dim.score == 0.9
        assert dim.threshold == 0.8

    def test_passes_true(self):
        from enhanced_agent_bus.response_quality.models import QualityDimension

        dim = QualityDimension(name="test", score=0.9, threshold=0.8)
        assert dim.passes is True

    def test_passes_false(self):
        from enhanced_agent_bus.response_quality.models import QualityDimension

        dim = QualityDimension(name="test", score=0.5, threshold=0.8)
        assert dim.passes is False

    def test_passes_equal(self):
        from enhanced_agent_bus.response_quality.models import QualityDimension

        dim = QualityDimension(name="test", score=0.8, threshold=0.8)
        assert dim.passes is True

    def test_gap_positive(self):
        from enhanced_agent_bus.response_quality.models import QualityDimension

        dim = QualityDimension(name="test", score=0.9, threshold=0.7)
        assert dim.gap == pytest.approx(0.2)

    def test_gap_negative(self):
        from enhanced_agent_bus.response_quality.models import QualityDimension

        dim = QualityDimension(name="test", score=0.5, threshold=0.8)
        assert dim.gap == pytest.approx(-0.3)

    def test_level_excellent(self):
        from enhanced_agent_bus.response_quality.models import QualityDimension, QualityLevel

        dim = QualityDimension(name="test", score=0.96, threshold=0.5)
        assert dim.level == QualityLevel.EXCELLENT

    def test_level_good(self):
        from enhanced_agent_bus.response_quality.models import QualityDimension, QualityLevel

        dim = QualityDimension(name="test", score=0.85, threshold=0.5)
        assert dim.level == QualityLevel.GOOD

    def test_level_acceptable(self):
        from enhanced_agent_bus.response_quality.models import QualityDimension, QualityLevel

        dim = QualityDimension(name="test", score=0.65, threshold=0.5)
        assert dim.level == QualityLevel.ACCEPTABLE

    def test_level_poor(self):
        from enhanced_agent_bus.response_quality.models import QualityDimension, QualityLevel

        dim = QualityDimension(name="test", score=0.45, threshold=0.5)
        assert dim.level == QualityLevel.POOR

    def test_level_unacceptable(self):
        from enhanced_agent_bus.response_quality.models import QualityDimension, QualityLevel

        dim = QualityDimension(name="test", score=0.2, threshold=0.5)
        assert dim.level == QualityLevel.UNACCEPTABLE

    def test_invalid_score_too_high(self):
        from enhanced_agent_bus.response_quality.models import QualityDimension

        with pytest.raises(ValueError, match="Score must be between"):
            QualityDimension(name="test", score=1.5, threshold=0.5)

    def test_invalid_score_negative(self):
        from enhanced_agent_bus.response_quality.models import QualityDimension

        with pytest.raises(ValueError, match="Score must be between"):
            QualityDimension(name="test", score=-0.1, threshold=0.5)

    def test_invalid_threshold(self):
        from enhanced_agent_bus.response_quality.models import QualityDimension

        with pytest.raises(ValueError, match="Threshold must be between"):
            QualityDimension(name="test", score=0.5, threshold=1.5)

    def test_to_dict(self):
        from enhanced_agent_bus.response_quality.models import QualityDimension

        dim = QualityDimension(name="accuracy", score=0.9, threshold=0.8, critique="Good")
        d = dim.to_dict()
        assert d["name"] == "accuracy"
        assert d["score"] == 0.9
        assert d["threshold"] == 0.8
        assert d["critique"] == "Good"
        assert d["passes"] is True
        assert "gap" in d
        assert "level" in d

    def test_critique_optional(self):
        from enhanced_agent_bus.response_quality.models import QualityDimension

        dim = QualityDimension(name="test", score=0.5, threshold=0.5)
        assert dim.critique is None


class TestQualityAssessment:
    def _make_assessment(self, **kwargs):
        from enhanced_agent_bus.response_quality.models import QualityAssessment, QualityDimension

        defaults = {
            "dimensions": [
                QualityDimension(name="accuracy", score=0.9, threshold=0.8),
                QualityDimension(name="coherence", score=0.7, threshold=0.7),
                QualityDimension(name="safety", score=0.99, threshold=0.99),
            ],
            "overall_score": 0.85,
            "passes_threshold": True,
            "refinement_suggestions": [],
            "constitutional_compliance": True,
        }
        defaults.update(kwargs)
        return QualityAssessment(**defaults)

    def test_dimension_count(self):
        a = self._make_assessment()
        assert a.dimension_count == 3

    def test_passing_dimensions(self):
        a = self._make_assessment()
        passing = a.passing_dimensions
        assert len(passing) == 3

    def test_failing_dimensions(self):
        from enhanced_agent_bus.response_quality.models import QualityDimension

        a = self._make_assessment(
            dimensions=[
                QualityDimension(name="accuracy", score=0.5, threshold=0.8),
                QualityDimension(name="coherence", score=0.9, threshold=0.7),
            ],
            overall_score=0.7,
            passes_threshold=False,
        )
        failing = a.failing_dimensions
        assert len(failing) == 1
        assert failing[0].name == "accuracy"

    def test_pass_rate(self):
        from enhanced_agent_bus.response_quality.models import QualityDimension

        a = self._make_assessment(
            dimensions=[
                QualityDimension(name="a", score=0.9, threshold=0.8),
                QualityDimension(name="b", score=0.5, threshold=0.8),
            ],
            overall_score=0.7,
        )
        assert a.pass_rate == pytest.approx(0.5)

    def test_pass_rate_empty(self):
        a = self._make_assessment(dimensions=[], overall_score=0.0, passes_threshold=False)
        assert a.pass_rate == 0.0

    def test_critical_failures(self):
        from enhanced_agent_bus.response_quality.models import QualityDimension

        a = self._make_assessment(
            dimensions=[
                QualityDimension(name="safety", score=0.5, threshold=0.99),
                QualityDimension(name="constitutional_alignment", score=0.3, threshold=0.95),
                QualityDimension(name="accuracy", score=0.5, threshold=0.8),
            ],
            overall_score=0.4,
            passes_threshold=False,
        )
        critical = a.critical_failures
        assert len(critical) == 2
        names = {c.name for c in critical}
        assert "safety" in names
        assert "constitutional_alignment" in names

    def test_overall_level_excellent(self):
        from enhanced_agent_bus.response_quality.models import QualityLevel

        a = self._make_assessment(overall_score=0.96)
        assert a.overall_level == QualityLevel.EXCELLENT

    def test_overall_level_good(self):
        from enhanced_agent_bus.response_quality.models import QualityLevel

        a = self._make_assessment(overall_score=0.85)
        assert a.overall_level == QualityLevel.GOOD

    def test_overall_level_acceptable(self):
        from enhanced_agent_bus.response_quality.models import QualityLevel

        a = self._make_assessment(overall_score=0.65)
        assert a.overall_level == QualityLevel.ACCEPTABLE

    def test_overall_level_poor(self):
        from enhanced_agent_bus.response_quality.models import QualityLevel

        a = self._make_assessment(overall_score=0.45)
        assert a.overall_level == QualityLevel.POOR

    def test_overall_level_unacceptable(self):
        from enhanced_agent_bus.response_quality.models import QualityLevel

        a = self._make_assessment(overall_score=0.2)
        assert a.overall_level == QualityLevel.UNACCEPTABLE

    def test_needs_refinement_fails_threshold(self):
        a = self._make_assessment(passes_threshold=False)
        assert a.needs_refinement is True

    def test_needs_refinement_no_compliance(self):
        a = self._make_assessment(constitutional_compliance=False)
        assert a.needs_refinement is True

    def test_needs_refinement_false(self):
        a = self._make_assessment(passes_threshold=True, constitutional_compliance=True)
        assert a.needs_refinement is False

    def test_get_dimension_found(self):
        a = self._make_assessment()
        dim = a.get_dimension("accuracy")
        assert dim is not None
        assert dim.name == "accuracy"

    def test_get_dimension_not_found(self):
        a = self._make_assessment()
        dim = a.get_dimension("nonexistent")
        assert dim is None

    def test_invalid_overall_score(self):
        with pytest.raises(ValueError, match="Overall score"):
            self._make_assessment(overall_score=1.5)

    def test_to_dict(self):
        a = self._make_assessment()
        d = a.to_dict()
        assert "dimensions" in d
        assert "overall_score" in d
        assert "passes_threshold" in d
        assert "dimension_count" in d
        assert "pass_rate" in d
        assert "overall_level" in d
        assert "needs_refinement" in d
        assert "timestamp" in d

    def test_from_dict(self):
        from enhanced_agent_bus.response_quality.models import QualityAssessment

        data = {
            "dimensions": [{"name": "accuracy", "score": 0.9, "threshold": 0.8, "critique": None}],
            "overall_score": 0.9,
            "passes_threshold": True,
            "refinement_suggestions": ["improve"],
            "constitutional_compliance": True,
            "response_id": "r-1",
            "timestamp": "2025-01-01T00:00:00",
            "metadata": {"key": "val"},
        }
        a = QualityAssessment.from_dict(data)
        assert a.overall_score == 0.9
        assert a.response_id == "r-1"
        assert a.dimension_count == 1

    def test_from_dict_no_timestamp(self):
        from enhanced_agent_bus.response_quality.models import QualityAssessment

        data = {
            "dimensions": [],
            "overall_score": 0.5,
            "passes_threshold": False,
        }
        a = QualityAssessment.from_dict(data)
        assert a.timestamp is not None


class TestRefinementIteration:
    def _make_assessment(self, score=0.7, passes=True):
        from enhanced_agent_bus.response_quality.models import QualityAssessment, QualityDimension

        return QualityAssessment(
            dimensions=[QualityDimension(name="test", score=score, threshold=0.6)],
            overall_score=score,
            passes_threshold=passes,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )

    def test_improvement_delta(self):
        from enhanced_agent_bus.response_quality.models import RefinementIteration

        it = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=self._make_assessment(0.5, False),
            after_assessment=self._make_assessment(0.8, True),
        )
        assert it.improvement_delta == pytest.approx(0.3)

    def test_improved_true(self):
        from enhanced_agent_bus.response_quality.models import RefinementIteration

        it = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=self._make_assessment(0.5),
            after_assessment=self._make_assessment(0.8),
        )
        assert it.improved is True

    def test_improved_false(self):
        from enhanced_agent_bus.response_quality.models import RefinementIteration

        it = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=self._make_assessment(0.8),
            after_assessment=self._make_assessment(0.8),
        )
        assert it.improved is False

    def test_now_passes(self):
        from enhanced_agent_bus.response_quality.models import RefinementIteration

        it = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=self._make_assessment(0.5, False),
            after_assessment=self._make_assessment(0.8, True),
        )
        assert it.now_passes is True


class TestRefinementResult:
    def _make_assessment(self, score=0.7, passes=True):
        from enhanced_agent_bus.response_quality.models import QualityAssessment, QualityDimension

        return QualityAssessment(
            dimensions=[QualityDimension(name="test", score=score, threshold=0.6)],
            overall_score=score,
            passes_threshold=passes,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )

    def test_total_improvement(self):
        from enhanced_agent_bus.response_quality.models import RefinementResult, RefinementStatus

        result = RefinementResult(
            original_response="old",
            final_response="new",
            iterations=[],
            total_iterations=0,
            status=RefinementStatus.COMPLETED,
            initial_assessment=self._make_assessment(0.5),
            final_assessment=self._make_assessment(0.8),
        )
        assert result.total_improvement == pytest.approx(0.3)

    def test_was_refined_true(self):
        from enhanced_agent_bus.response_quality.models import (
            RefinementIteration,
            RefinementResult,
            RefinementStatus,
        )

        a1 = self._make_assessment(0.5)
        a2 = self._make_assessment(0.8)
        it = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=a1,
            after_assessment=a2,
        )
        result = RefinementResult(
            original_response="old",
            final_response="new",
            iterations=[it],
            total_iterations=1,
            status=RefinementStatus.COMPLETED,
            initial_assessment=a1,
            final_assessment=a2,
        )
        assert result.was_refined is True

    def test_was_refined_false(self):
        from enhanced_agent_bus.response_quality.models import RefinementResult, RefinementStatus

        a = self._make_assessment(0.9)
        result = RefinementResult(
            original_response="ok",
            final_response="ok",
            iterations=[],
            total_iterations=0,
            status=RefinementStatus.SKIPPED,
            initial_assessment=a,
            final_assessment=a,
        )
        assert result.was_refined is False

    def test_success_true(self):
        from enhanced_agent_bus.response_quality.models import RefinementResult, RefinementStatus

        result = RefinementResult(
            original_response="old",
            final_response="new",
            iterations=[],
            total_iterations=0,
            status=RefinementStatus.COMPLETED,
            initial_assessment=self._make_assessment(0.5),
            final_assessment=self._make_assessment(0.8, True),
        )
        assert result.success is True

    def test_success_false_status(self):
        from enhanced_agent_bus.response_quality.models import RefinementResult, RefinementStatus

        result = RefinementResult(
            original_response="old",
            final_response="old",
            iterations=[],
            total_iterations=0,
            status=RefinementStatus.FAILED,
            initial_assessment=self._make_assessment(0.5, False),
            final_assessment=self._make_assessment(0.5, False),
        )
        assert result.success is False

    def test_to_dict(self):
        from enhanced_agent_bus.response_quality.models import RefinementResult, RefinementStatus

        result = RefinementResult(
            original_response="old",
            final_response="new",
            iterations=[],
            total_iterations=0,
            status=RefinementStatus.COMPLETED,
            initial_assessment=self._make_assessment(0.5),
            final_assessment=self._make_assessment(0.8),
        )
        d = result.to_dict()
        assert d["original_response"] == "old"
        assert d["final_response"] == "new"
        assert d["status"] == "completed"
        assert "total_improvement" in d
        assert "was_refined" in d
        assert "improved" in d
        assert "success" in d


# =============================================================================
# Module 1: response_quality.validator
# =============================================================================


class TestDimensionSpec:
    def test_basic_creation(self):
        from enhanced_agent_bus.response_quality.validator import DimensionSpec

        spec = DimensionSpec(name="accuracy", threshold=0.8, weight=1.2)
        assert spec.name == "accuracy"
        assert spec.threshold == 0.8
        assert spec.weight == 1.2

    def test_invalid_threshold(self):
        from enhanced_agent_bus.response_quality.validator import DimensionSpec

        with pytest.raises(ACGSValidationError):
            DimensionSpec(name="test", threshold=1.5)

    def test_negative_weight(self):
        from enhanced_agent_bus.response_quality.validator import DimensionSpec

        with pytest.raises(ACGSValidationError):
            DimensionSpec(name="test", threshold=0.5, weight=-1.0)

    def test_defaults(self):
        from enhanced_agent_bus.response_quality.validator import DimensionSpec

        spec = DimensionSpec(name="test", threshold=0.5)
        assert spec.weight == 1.0
        assert spec.required is False
        assert spec.description == ""


class TestValidationConfig:
    def test_defaults(self):
        from enhanced_agent_bus.response_quality.validator import ValidationConfig

        config = ValidationConfig()
        assert config.require_all_dimensions is True
        assert config.fail_on_any_critical is True
        assert config.overall_threshold == 0.7
        assert config.enable_constitutional_check is True


class TestResponseQualityValidator:
    def test_creation(self):
        from enhanced_agent_bus.response_quality import ResponseQualityValidator

        v = ResponseQualityValidator()
        assert v is not None

    def test_validate_returns_assessment(self):
        from enhanced_agent_bus.response_quality import ResponseQualityValidator

        v = ResponseQualityValidator()
        assessment = v.validate("This is a test response for validation.")
        assert assessment is not None
        assert 0.0 <= assessment.overall_score <= 1.0
        assert isinstance(assessment.passes_threshold, bool)

    def test_validate_with_context(self):
        from enhanced_agent_bus.response_quality import ResponseQualityValidator

        v = ResponseQualityValidator()
        assessment = v.validate("Test response.", context={"query": "What is AI?"})
        assert assessment is not None

    def test_validate_with_response_id(self):
        from enhanced_agent_bus.response_quality import ResponseQualityValidator

        v = ResponseQualityValidator()
        assessment = v.validate("Test response.", response_id="r-1")
        assert assessment.response_id == "r-1"

    def test_quality_dimensions_class_var(self):
        from enhanced_agent_bus.response_quality import ResponseQualityValidator

        dims = ResponseQualityValidator.QUALITY_DIMENSIONS
        assert "accuracy" in dims
        assert "coherence" in dims
        assert "safety" in dims
        assert "constitutional_alignment" in dims


# =============================================================================
# Module 1: response_quality.refiner
# =============================================================================


class TestRefinementConfigRefiner:
    def test_defaults(self):
        from enhanced_agent_bus.response_quality.refiner import RefinementConfig

        config = RefinementConfig()
        assert config.max_iterations == 3
        assert config.improvement_threshold == 0.01
        assert config.stop_on_pass is True
        assert config.require_constitutional is True
        assert config.timeout_per_iteration_ms == 5000.0


class TestDefaultLLMRefiner:
    def test_refine_adds_period(self):
        from enhanced_agent_bus.response_quality.models import QualityAssessment, QualityDimension
        from enhanced_agent_bus.response_quality.refiner import DefaultLLMRefiner

        refiner = DefaultLLMRefiner()
        assessment = QualityAssessment(
            dimensions=[QualityDimension(name="coherence", score=0.3, threshold=0.7)],
            overall_score=0.3,
            passes_threshold=False,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        result = refiner.refine("incomplete text", assessment)
        assert result.endswith(".")

    def test_refine_safety_redaction(self):
        from enhanced_agent_bus.response_quality.models import QualityAssessment, QualityDimension
        from enhanced_agent_bus.response_quality.refiner import DefaultLLMRefiner

        refiner = DefaultLLMRefiner()
        assessment = QualityAssessment(
            dimensions=[QualityDimension(name="safety", score=0.3, threshold=0.99)],
            overall_score=0.3,
            passes_threshold=False,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        result = refiner.refine("You should hack the system and steal data", assessment)
        assert "[redacted]" in result

    async def test_refine_async(self):
        from enhanced_agent_bus.response_quality.models import QualityAssessment, QualityDimension
        from enhanced_agent_bus.response_quality.refiner import DefaultLLMRefiner

        refiner = DefaultLLMRefiner()
        assessment = QualityAssessment(
            dimensions=[],
            overall_score=0.8,
            passes_threshold=True,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        result = await refiner.refine_async("test response", assessment)
        assert isinstance(result, str)


class TestDefaultConstitutionalCorrector:
    def test_correct_harmful(self):
        from enhanced_agent_bus.response_quality.refiner import DefaultConstitutionalCorrector

        corrector = DefaultConstitutionalCorrector()
        result = corrector.correct("Bad content", ["harmful content detected"])
        assert "[Reviewed for safety]" in result

    def test_correct_bias(self):
        from enhanced_agent_bus.response_quality.refiner import DefaultConstitutionalCorrector

        corrector = DefaultConstitutionalCorrector()
        result = corrector.correct("Biased statement", ["bias detected in response"])
        assert "balanced and fair" in result

    def test_correct_privacy(self):
        from enhanced_agent_bus.response_quality.refiner import DefaultConstitutionalCorrector

        corrector = DefaultConstitutionalCorrector()
        result = corrector.correct(
            "Contact john@example.com or SSN 123-45-6789",
            ["privacy violation"],
        )
        assert "[EMAIL-REDACTED]" in result
        assert "[SSN-REDACTED]" in result

    async def test_correct_async(self):
        from enhanced_agent_bus.response_quality.refiner import DefaultConstitutionalCorrector

        corrector = DefaultConstitutionalCorrector()
        result = await corrector.correct_async("test", ["harmful content"])
        assert "[Reviewed for safety]" in result


class TestResponseRefiner:
    def test_creation(self):
        from enhanced_agent_bus.response_quality import ResponseRefiner

        refiner = ResponseRefiner()
        assert refiner.max_iterations == 3

    def test_custom_max_iterations(self):
        from enhanced_agent_bus.response_quality import ResponseRefiner

        refiner = ResponseRefiner(max_iterations=5)
        assert refiner.max_iterations == 5

    def test_stats_property(self):
        from enhanced_agent_bus.response_quality import ResponseRefiner

        refiner = ResponseRefiner()
        stats = refiner.stats
        assert "refinement_count" in stats
        assert "total_iterations" in stats
        assert "constitutional_hash" in stats

    def test_refine_basic(self):
        from enhanced_agent_bus.response_quality import ResponseRefiner

        refiner = ResponseRefiner(max_iterations=1)
        result = refiner.refine("This is a test response for the refiner.")
        assert result.original_response == "This is a test response for the refiner."
        assert result.final_response is not None
        assert result.total_iterations >= 0

    def test_refine_batch(self):
        from enhanced_agent_bus.response_quality import ResponseRefiner

        refiner = ResponseRefiner(max_iterations=1)
        results = refiner.refine_batch(["Response one.", "Response two."])
        assert len(results) == 2

    def test_refine_batch_with_contexts(self):
        from enhanced_agent_bus.response_quality import ResponseRefiner

        refiner = ResponseRefiner(max_iterations=1)
        results = refiner.refine_batch(
            ["Response one.", "Response two."],
            contexts=[{"query": "q1"}, {"query": "q2"}],
        )
        assert len(results) == 2

    def test_refine_batch_mismatched_lengths(self):
        from enhanced_agent_bus.response_quality import ResponseRefiner

        refiner = ResponseRefiner()
        with pytest.raises(ValueError, match="same length"):
            refiner.refine_batch(["one", "two"], contexts=[{"a": 1}])

    async def test_refine_async(self):
        from enhanced_agent_bus.response_quality import ResponseRefiner

        refiner = ResponseRefiner(max_iterations=1)
        result = await refiner.refine_async("This is a test response.")
        assert result.original_response == "This is a test response."

    async def test_refine_batch_async(self):
        from enhanced_agent_bus.response_quality import ResponseRefiner

        refiner = ResponseRefiner(max_iterations=1)
        results = await refiner.refine_batch_async(["Response one.", "Response two."])
        assert len(results) == 2

    async def test_refine_batch_async_mismatched(self):
        from enhanced_agent_bus.response_quality import ResponseRefiner

        refiner = ResponseRefiner()
        with pytest.raises(ValueError, match="same length"):
            await refiner.refine_batch_async(["one"], contexts=[{}, {}])

    def test_set_constitutional_corrector(self):
        from enhanced_agent_bus.response_quality import ResponseRefiner

        refiner = ResponseRefiner()
        mock_corrector = MagicMock()
        refiner.set_constitutional_corrector(mock_corrector)
        assert refiner.constitutional_corrector is mock_corrector

    def test_set_llm_refiner(self):
        from enhanced_agent_bus.response_quality import ResponseRefiner

        refiner = ResponseRefiner()
        mock_llm = MagicMock()
        refiner.set_llm_refiner(mock_llm)
        assert refiner.llm_refiner is mock_llm


class TestCreateRefiner:
    def test_create_refiner_defaults(self):
        from enhanced_agent_bus.response_quality import create_refiner

        refiner = create_refiner()
        assert refiner.max_iterations == 3

    def test_create_refiner_custom(self):
        from enhanced_agent_bus.response_quality import create_refiner

        refiner = create_refiner(max_iterations=5)
        assert refiner.max_iterations == 5


class TestCreateValidator:
    def test_create_validator(self):
        from enhanced_agent_bus.response_quality import create_validator

        v = create_validator()
        assert v is not None


# =============================================================================
# Module 2: deliberation_layer.timeout_checker
# =============================================================================


class TestTimeoutChecker:
    @pytest.fixture
    def mock_settings(self):
        with patch("enhanced_agent_bus.deliberation_layer.timeout_checker.settings") as mock_s:
            mock_s.voting.timeout_check_interval_seconds = 1
            mock_s.voting.default_timeout_seconds = 300
            mock_s.voting.audit_signature_key = None
            yield mock_s

    def test_init(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        checker = TimeoutChecker()
        assert checker._running is False
        assert checker._task is None
        assert checker.kafka_bus is None

    def test_init_with_kafka(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        mock_kafka = MagicMock()
        checker = TimeoutChecker(kafka_bus=mock_kafka)
        assert checker.kafka_bus is mock_kafka

    async def test_start(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        checker = TimeoutChecker()
        checker._check_loop = AsyncMock()
        await checker.start()
        assert checker._running is True
        assert checker._task is not None
        await checker.stop()

    async def test_start_already_running(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        checker = TimeoutChecker()
        checker._running = True
        await checker.start()
        assert checker._task is None

    async def test_stop(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        checker = TimeoutChecker()
        checker._check_loop = AsyncMock()
        await checker.start()
        await checker.stop()
        assert checker._running is False

    async def test_stop_no_task(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        checker = TimeoutChecker()
        await checker.stop()
        assert checker._running is False

    async def test_check_expired_elections_no_store(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        with patch(
            "enhanced_agent_bus.deliberation_layer.timeout_checker.get_election_store",
            new_callable=AsyncMock,
            return_value=None,
        ):
            checker = TimeoutChecker()
            await checker._check_expired_elections()

    async def test_check_expired_elections_with_expired(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        expired_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        mock_store = AsyncMock()
        mock_store.scan_elections.return_value = ["election-1"]
        mock_store.get_election.return_value = {
            "status": "OPEN",
            "expires_at": expired_time,
        }

        with patch(
            "enhanced_agent_bus.deliberation_layer.timeout_checker.get_election_store",
            new_callable=AsyncMock,
            return_value=mock_store,
        ):
            checker = TimeoutChecker()
            checker._handle_expired_election = AsyncMock()
            await checker._check_expired_elections()
            checker._handle_expired_election.assert_called_once()

    async def test_check_expired_elections_not_expired(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        future_time = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        mock_store = AsyncMock()
        mock_store.scan_elections.return_value = ["election-1"]
        mock_store.get_election.return_value = {
            "status": "OPEN",
            "expires_at": future_time,
        }

        with patch(
            "enhanced_agent_bus.deliberation_layer.timeout_checker.get_election_store",
            new_callable=AsyncMock,
            return_value=mock_store,
        ):
            checker = TimeoutChecker()
            checker._handle_expired_election = AsyncMock()
            await checker._check_expired_elections()
            checker._handle_expired_election.assert_not_called()

    async def test_check_expired_elections_already_resolved(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        mock_store = AsyncMock()
        mock_store.scan_elections.return_value = ["election-1"]
        mock_store.get_election.return_value = {"status": "RESOLVED"}

        with patch(
            "enhanced_agent_bus.deliberation_layer.timeout_checker.get_election_store",
            new_callable=AsyncMock,
            return_value=mock_store,
        ):
            checker = TimeoutChecker()
            checker._handle_expired_election = AsyncMock()
            await checker._check_expired_elections()
            checker._handle_expired_election.assert_not_called()

    async def test_check_expired_elections_no_expires_at(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        mock_store = AsyncMock()
        mock_store.scan_elections.return_value = ["election-1"]
        mock_store.get_election.return_value = {"status": "OPEN"}

        with patch(
            "enhanced_agent_bus.deliberation_layer.timeout_checker.get_election_store",
            new_callable=AsyncMock,
            return_value=mock_store,
        ):
            checker = TimeoutChecker()
            checker._handle_expired_election = AsyncMock()
            await checker._check_expired_elections()
            checker._handle_expired_election.assert_not_called()

    async def test_check_expired_elections_null_election(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        mock_store = AsyncMock()
        mock_store.scan_elections.return_value = ["election-1"]
        mock_store.get_election.return_value = None

        with patch(
            "enhanced_agent_bus.deliberation_layer.timeout_checker.get_election_store",
            new_callable=AsyncMock,
            return_value=mock_store,
        ):
            checker = TimeoutChecker()
            checker._handle_expired_election = AsyncMock()
            await checker._check_expired_elections()
            checker._handle_expired_election.assert_not_called()

    async def test_handle_expired_election(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        mock_store = AsyncMock()
        with patch(
            "enhanced_agent_bus.deliberation_layer.timeout_checker.get_election_store",
            new_callable=AsyncMock,
            return_value=mock_store,
        ):
            checker = TimeoutChecker()
            election_data = {"status": "OPEN", "tenant_id": "test"}
            await checker._handle_expired_election("election-1", election_data)

            mock_store.update_election_status.assert_called_once_with("election-1", "EXPIRED")
            mock_store.save_election.assert_called_once()
            assert election_data["status"] == "EXPIRED"
            assert election_data["result"] == "DENY"

    async def test_handle_expired_election_no_store(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        with patch(
            "enhanced_agent_bus.deliberation_layer.timeout_checker.get_election_store",
            new_callable=AsyncMock,
            return_value=None,
        ):
            checker = TimeoutChecker()
            await checker._handle_expired_election("election-1", {})

    async def test_handle_expired_election_with_kafka(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        mock_store = AsyncMock()
        mock_kafka = AsyncMock()

        with patch(
            "enhanced_agent_bus.deliberation_layer.timeout_checker.get_election_store",
            new_callable=AsyncMock,
            return_value=mock_store,
        ):
            checker = TimeoutChecker(kafka_bus=mock_kafka)
            checker._publish_escalation_event = AsyncMock()
            election_data = {"status": "OPEN", "tenant_id": "test"}
            await checker._handle_expired_election("election-1", election_data)
            checker._publish_escalation_event.assert_called_once()

    async def test_publish_escalation_event(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        mock_kafka = AsyncMock()
        checker = TimeoutChecker(kafka_bus=mock_kafka)

        election_data = {
            "tenant_id": "test-tenant",
            "message_id": "msg-1",
            "expires_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            "created_at": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
        }

        with patch(
            "enhanced_agent_bus.deliberation_layer.timeout_checker.TimeoutChecker._publish_escalation_event",
            wraps=checker._publish_escalation_event,
        ):
            with patch(
                "enhanced_agent_bus.deliberation_layer.audit_signature.sign_audit_record",
                return_value="mock-signature",
            ):
                await checker._publish_escalation_event("election-1", election_data)

        mock_kafka.publish_audit_record.assert_called_once()
        call_args = mock_kafka.publish_audit_record.call_args
        assert call_args[0][0] == "test-tenant"

    async def test_publish_escalation_event_default_tenant(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        mock_kafka = AsyncMock()
        checker = TimeoutChecker(kafka_bus=mock_kafka)

        with patch(
            "enhanced_agent_bus.deliberation_layer.audit_signature.sign_audit_record",
            return_value="sig",
        ):
            await checker._publish_escalation_event("election-1", {})

        call_args = mock_kafka.publish_audit_record.call_args
        assert call_args[0][0] == "default"

    async def test_publish_escalation_event_with_signature_key(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        mock_kafka = AsyncMock()
        mock_secret = MagicMock()
        mock_secret.get_secret_value.return_value = "test-key"
        mock_settings.voting.audit_signature_key = mock_secret

        checker = TimeoutChecker(kafka_bus=mock_kafka)

        with patch(
            "enhanced_agent_bus.deliberation_layer.audit_signature.sign_audit_record",
            return_value="signed",
        ) as mock_sign:
            await checker._publish_escalation_event("election-1", {"tenant_id": "t1"})
            mock_sign.assert_called_once()

    async def test_check_expired_elections_scan_error(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        mock_store = AsyncMock()
        mock_store.scan_elections.side_effect = RuntimeError("Redis error")

        with patch(
            "enhanced_agent_bus.deliberation_layer.timeout_checker.get_election_store",
            new_callable=AsyncMock,
            return_value=mock_store,
        ):
            checker = TimeoutChecker()
            await checker._check_expired_elections()

    async def test_check_expired_datetime_object(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        expired_dt = datetime.now(UTC) - timedelta(hours=1)
        mock_store = AsyncMock()
        mock_store.scan_elections.return_value = ["election-1"]
        mock_store.get_election.return_value = {
            "status": "OPEN",
            "expires_at": expired_dt,
        }

        with patch(
            "enhanced_agent_bus.deliberation_layer.timeout_checker.get_election_store",
            new_callable=AsyncMock,
            return_value=mock_store,
        ):
            checker = TimeoutChecker()
            checker._handle_expired_election = AsyncMock()
            await checker._check_expired_elections()
            checker._handle_expired_election.assert_called_once()

    async def test_handle_expired_election_store_error(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        mock_store = AsyncMock()
        mock_store.update_election_status.side_effect = RuntimeError("Store error")

        with patch(
            "enhanced_agent_bus.deliberation_layer.timeout_checker.get_election_store",
            new_callable=AsyncMock,
            return_value=mock_store,
        ):
            checker = TimeoutChecker()
            await checker._handle_expired_election("e1", {"status": "OPEN"})

    async def test_check_loop_runs_and_stops(self, mock_settings):
        from enhanced_agent_bus.deliberation_layer.timeout_checker import TimeoutChecker

        mock_settings.voting.timeout_check_interval_seconds = 0.01
        checker = TimeoutChecker()
        checker._check_expired_elections = AsyncMock()

        checker._running = True
        task = asyncio.create_task(checker._check_loop())
        await asyncio.sleep(0.05)
        checker._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert checker._check_expired_elections.call_count >= 1


# =============================================================================
# Module 3: constitutional.review_api
# =============================================================================


class TestReviewAPIModels:
    def test_amendment_list_query_defaults(self):
        from enhanced_agent_bus.constitutional.review_api import AmendmentListQuery

        q = AmendmentListQuery()
        assert q.limit == 50
        assert q.offset == 0
        assert q.order_by == "created_at"
        assert q.order == "desc"

    def test_approval_request(self):
        from enhanced_agent_bus.constitutional.review_api import ApprovalRequest

        req = ApprovalRequest(approver_agent_id="agent-1", comments="Looks good")
        assert req.approver_agent_id == "agent-1"
        assert req.metadata == {}

    def test_rejection_request(self):
        from enhanced_agent_bus.constitutional.review_api import RejectionRequest

        req = RejectionRequest(
            rejector_agent_id="agent-2",
            reason="This violates policy section 3.2 on data retention",
        )
        assert req.rejector_agent_id == "agent-2"

    def test_rollback_request(self):
        from enhanced_agent_bus.constitutional.review_api import RollbackRequest

        req = RollbackRequest(
            requester_agent_id="agent-3",
            justification="Critical governance degradation detected in recent metrics.",
        )
        assert len(req.justification) >= 20

    def test_rollback_response(self):
        from enhanced_agent_bus.constitutional.review_api import RollbackResponse

        resp = RollbackResponse(
            success=True,
            rollback_id="rollback-123",
            previous_version="v2.0",
            restored_version="v1.9",
            message="Rolled back",
            justification="Governance degradation in v2.0.",
        )
        assert resp.rollback_id == "rollback-123"


class TestReviewAPIHealthCheck:
    async def test_health_check(self):
        from enhanced_agent_bus.constitutional.review_api import health_check

        result = await health_check()
        assert result["status"] == "healthy"
        assert result["service"] == "constitutional-review-api"
        assert "constitutional_hash" in result
        assert "timestamp" in result


class TestReviewAPIRouter:
    def test_router_prefix(self):
        from enhanced_agent_bus.constitutional.review_api import router

        assert router.prefix == "/api/v1/constitutional"

    def test_router_tags(self):
        from enhanced_agent_bus.constitutional.review_api import router

        assert "constitutional-amendments" in router.tags


class TestReviewAPIRollback:
    async def test_rollback_unavailable(self):
        from enhanced_agent_bus.constitutional.review_api import (
            RollbackRequest,
            rollback_to_version,
        )

        with patch(
            "enhanced_agent_bus.constitutional.review_api.ROLLBACK_AVAILABLE",
            False,
        ):
            req = RollbackRequest(
                requester_agent_id="agent-1",
                justification="Critical governance degradation detected in recent metrics.",
            )
            with pytest.raises(Exception) as exc_info:
                await rollback_to_version("v1.0", req)
            assert exc_info.value.status_code == 501


class TestReviewAPIEndpointsViaTestClient:
    """Test review_api endpoints via FastAPI TestClient for proper parameter handling."""

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from enhanced_agent_bus.constitutional.review_api import router

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_health_check_via_client(self, client):
        resp = client.get("/api/v1/constitutional/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    def test_list_amendments_success(self, client):
        mock_storage = AsyncMock()
        mock_storage.list_amendments.return_value = ([], 0)

        with patch(
            "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
            return_value=mock_storage,
        ):
            resp = client.get("/api/v1/constitutional/amendments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    def test_list_amendments_invalid_status(self, client):
        mock_storage = AsyncMock()
        with patch(
            "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
            return_value=mock_storage,
        ):
            resp = client.get("/api/v1/constitutional/amendments?status=bogus")
        assert resp.status_code == 400

    def test_list_amendments_invalid_order_by(self, client):
        mock_storage = AsyncMock()
        with patch(
            "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
            return_value=mock_storage,
        ):
            resp = client.get("/api/v1/constitutional/amendments?order_by=nonexistent")
        assert resp.status_code == 400

    def test_list_amendments_invalid_order(self, client):
        mock_storage = AsyncMock()
        with patch(
            "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
            return_value=mock_storage,
        ):
            resp = client.get("/api/v1/constitutional/amendments?order=sideways")
        assert resp.status_code == 400

    def test_list_amendments_storage_error(self, client):
        mock_storage = AsyncMock()
        mock_storage.list_amendments.side_effect = RuntimeError("DB down")
        with patch(
            "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
            return_value=mock_storage,
        ):
            resp = client.get("/api/v1/constitutional/amendments")
        assert resp.status_code == 500

    def test_list_amendments_with_filters(self, client):
        mock_storage = AsyncMock()
        mock_storage.list_amendments.return_value = ([], 0)
        with patch(
            "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
            return_value=mock_storage,
        ):
            resp = client.get(
                "/api/v1/constitutional/amendments"
                "?status=proposed&proposer_agent_id=agent-42&limit=10&offset=5"
            )
        assert resp.status_code == 200

    def test_get_amendment_not_found(self, client):
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = None
        with patch(
            "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
            return_value=mock_storage,
        ):
            resp = client.get("/api/v1/constitutional/amendments/nonexistent-id")
        assert resp.status_code == 404

    def test_get_amendment_storage_error(self, client):
        mock_storage = AsyncMock()
        mock_storage.get_amendment.side_effect = RuntimeError("DB error")
        with patch(
            "enhanced_agent_bus.constitutional.review_api.ConstitutionalStorageService",
            return_value=mock_storage,
        ):
            resp = client.get("/api/v1/constitutional/amendments/amend-1")
        assert resp.status_code == 500


# =============================================================================
# Module 4: deliberation_layer.integration
# =============================================================================


class TestDeliberationLayerIntegrationHelpers:
    def test_truncate_content_for_hotl_string(self):
        from enhanced_agent_bus.deliberation_layer.integration import _truncate_content_for_hotl

        result = _truncate_content_for_hotl("Hello world", limit=5)
        assert result == "Hello"

    def test_truncate_content_for_hotl_none(self):
        from enhanced_agent_bus.deliberation_layer.integration import _truncate_content_for_hotl

        result = _truncate_content_for_hotl(None)
        assert result == ""

    def test_truncate_content_for_hotl_object(self):
        from enhanced_agent_bus.deliberation_layer.integration import _truncate_content_for_hotl

        result = _truncate_content_for_hotl(12345, limit=3)
        assert result == "123"

    def test_truncate_content_for_hotl_default_limit(self):
        from enhanced_agent_bus.deliberation_layer.integration import _truncate_content_for_hotl

        long_str = "x" * 1000
        result = _truncate_content_for_hotl(long_str)
        assert len(result) == 500


class TestDeliberationLayerInit:
    def _make_layer(self, **kwargs):
        defaults = {
            "enable_redis": False,
            "enable_llm": False,
            "enable_opa_guard": False,
            "enable_learning": False,
            "impact_scorer": MagicMock(),
            "adaptive_router": MagicMock(),
            "deliberation_queue": MagicMock(),
        }
        defaults.update(kwargs)
        from enhanced_agent_bus.deliberation_layer.integration import DeliberationLayer

        return DeliberationLayer(**defaults)

    def test_basic_init(self):
        layer = self._make_layer()
        assert layer.impact_threshold == 0.8
        assert layer.enable_redis is False

    def test_custom_thresholds(self):
        layer = self._make_layer(
            impact_threshold=0.5,
            high_risk_threshold=0.7,
            critical_risk_threshold=0.9,
        )
        assert layer.impact_threshold == 0.5
        assert layer.high_risk_threshold == 0.7

    def test_injected_impact_scorer_property(self):
        mock_scorer = MagicMock()
        layer = self._make_layer(impact_scorer=mock_scorer)
        assert layer.injected_impact_scorer is mock_scorer

    def test_injected_router_property(self):
        mock_router = MagicMock()
        layer = self._make_layer(adaptive_router=mock_router)
        assert layer.injected_router is mock_router

    def test_injected_queue_property(self):
        mock_queue = MagicMock()
        layer = self._make_layer(deliberation_queue=mock_queue)
        assert layer.injected_queue is mock_queue

    def test_callbacks_initialized(self):
        layer = self._make_layer()
        assert layer.fast_lane_callback is None
        assert layer.deliberation_callback is None
        assert layer.guard_callback is None

    def test_llm_assistant_injected(self):
        mock_llm = MagicMock()
        layer = self._make_layer(llm_assistant=mock_llm, enable_llm=True)
        assert layer.llm_assistant is mock_llm

    def test_opa_guard_injected(self):
        mock_guard = MagicMock()
        layer = self._make_layer(opa_guard=mock_guard, enable_opa_guard=True)
        assert layer.opa_guard is mock_guard

    def test_redis_disabled_ignores_injected_redis(self):
        layer = self._make_layer(
            enable_redis=False,
            redis_queue=MagicMock(),
            redis_voting=MagicMock(),
        )
        assert layer.redis_queue is None
        assert layer.redis_voting is None

    def test_graphrag_enricher_stored(self):
        mock_enricher = MagicMock()
        layer = self._make_layer(graphrag_enricher=mock_enricher)
        assert layer._graphrag_enricher is mock_enricher

    async def test_initialize_no_redis(self):
        layer = self._make_layer()
        layer.opa_guard = None
        await layer.initialize()

    async def test_initialize_with_opa_guard(self):
        mock_guard = AsyncMock()
        layer = self._make_layer(opa_guard=mock_guard, enable_opa_guard=True)
        await layer.initialize()
        mock_guard.initialize.assert_called_once()

    async def test_initialize_with_redis(self):
        mock_redis_q = AsyncMock()
        mock_redis_v = AsyncMock()
        layer = self._make_layer(
            enable_redis=True,
            redis_queue=mock_redis_q,
            redis_voting=mock_redis_v,
        )
        layer.opa_guard = None
        await layer.initialize()
        mock_redis_q.connect.assert_called_once()
        mock_redis_v.connect.assert_called_once()
