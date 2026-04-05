"""Tests for enhanced_agent_bus.response_quality package — maximize coverage.

Covers:
- response_quality/__init__.py (hash verification, backward compat aliases)
- response_quality/models.py (QualityLevel, RefinementStatus, QualityDimension,
  QualityAssessment, RefinementIteration, RefinementResult)
- response_quality/validator.py (DimensionSpec, ValidationConfig,
  ResponseQualityValidator, create_validator, ConstitutionalHashError)
- response_quality/refiner.py (RefinementConfig, DefaultLLMRefiner,
  DefaultConstitutionalCorrector, ResponseRefiner, create_refiner,
  RefinementError, ConstitutionalViolationError)
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from enhanced_agent_bus.response_quality import (
    CONSTITUTIONAL_HASH,
    ConstitutionalHashError,
    ConstitutionalSelfCorrector,
    ConstitutionalViolationError,
    DefaultConstitutionalCorrector,
    DefaultLLMRefiner,
    DimensionScores,
    DimensionSpec,
    QualityAssessment,
    QualityDimension,
    QualityLevel,
    RefinementConfig,
    RefinementError,
    RefinementIteration,
    RefinementResult,
    RefinementStatus,
    ResponseQualityAssessor,
    ResponseQualityMetrics,
    ResponseQualityValidator,
    ResponseRefiner,
    ResponseScorer,
    SuggestionList,
    ValidationConfig,
    ValidationError,
    create_refiner,
    create_validator,
)

# ===========================================================================
# models.py — Enums
# ===========================================================================


class TestQualityLevel:
    def test_all_values(self):
        assert QualityLevel.EXCELLENT.value == "excellent"
        assert QualityLevel.GOOD.value == "good"
        assert QualityLevel.ACCEPTABLE.value == "acceptable"
        assert QualityLevel.POOR.value == "poor"
        assert QualityLevel.UNACCEPTABLE.value == "unacceptable"


class TestRefinementStatus:
    def test_all_values(self):
        assert RefinementStatus.PENDING.value == "pending"
        assert RefinementStatus.IN_PROGRESS.value == "in_progress"
        assert RefinementStatus.COMPLETED.value == "completed"
        assert RefinementStatus.FAILED.value == "failed"
        assert RefinementStatus.SKIPPED.value == "skipped"


# ===========================================================================
# models.py — QualityDimension
# ===========================================================================


class TestQualityDimension:
    def test_basic_creation(self):
        dim = QualityDimension(name="accuracy", score=0.9, threshold=0.8)
        assert dim.name == "accuracy"
        assert dim.score == 0.9
        assert dim.threshold == 0.8
        assert dim.critique is None

    def test_score_out_of_range_high(self):
        with pytest.raises(ValueError, match="Score must be between"):
            QualityDimension(name="x", score=1.5, threshold=0.5)

    def test_score_out_of_range_low(self):
        with pytest.raises(ValueError, match="Score must be between"):
            QualityDimension(name="x", score=-0.1, threshold=0.5)

    def test_threshold_out_of_range(self):
        with pytest.raises(ValueError, match="Threshold must be between"):
            QualityDimension(name="x", score=0.5, threshold=1.5)

    def test_passes_true(self):
        dim = QualityDimension(name="a", score=0.9, threshold=0.8)
        assert dim.passes is True

    def test_passes_false(self):
        dim = QualityDimension(name="a", score=0.5, threshold=0.8)
        assert dim.passes is False

    def test_passes_exact_threshold(self):
        dim = QualityDimension(name="a", score=0.8, threshold=0.8)
        assert dim.passes is True

    def test_gap_positive(self):
        dim = QualityDimension(name="a", score=0.9, threshold=0.7)
        assert dim.gap == pytest.approx(0.2)

    def test_gap_negative(self):
        dim = QualityDimension(name="a", score=0.5, threshold=0.8)
        assert dim.gap == pytest.approx(-0.3)

    def test_level_excellent(self):
        dim = QualityDimension(name="a", score=0.96, threshold=0.5)
        assert dim.level == QualityLevel.EXCELLENT

    def test_level_good(self):
        dim = QualityDimension(name="a", score=0.85, threshold=0.5)
        assert dim.level == QualityLevel.GOOD

    def test_level_acceptable(self):
        dim = QualityDimension(name="a", score=0.65, threshold=0.5)
        assert dim.level == QualityLevel.ACCEPTABLE

    def test_level_poor(self):
        dim = QualityDimension(name="a", score=0.45, threshold=0.5)
        assert dim.level == QualityLevel.POOR

    def test_level_unacceptable(self):
        dim = QualityDimension(name="a", score=0.2, threshold=0.5)
        assert dim.level == QualityLevel.UNACCEPTABLE

    def test_to_dict(self):
        dim = QualityDimension(name="accuracy", score=0.9, threshold=0.8, critique="ok")
        d = dim.to_dict()
        assert d["name"] == "accuracy"
        assert d["score"] == 0.9
        assert d["threshold"] == 0.8
        assert d["critique"] == "ok"
        assert d["passes"] is True
        assert d["gap"] == pytest.approx(0.1)
        assert d["level"] == "good"


# ===========================================================================
# models.py — QualityAssessment
# ===========================================================================


class TestQualityAssessment:
    def _make(self, **overrides):
        defaults = {
            "dimensions": [
                QualityDimension(name="accuracy", score=0.9, threshold=0.8),
                QualityDimension(name="safety", score=0.5, threshold=0.99),
            ],
            "overall_score": 0.7,
            "passes_threshold": False,
            "refinement_suggestions": ["improve safety"],
            "constitutional_compliance": True,
        }
        defaults.update(overrides)
        return QualityAssessment(**defaults)

    def test_basic_creation(self):
        qa = self._make()
        assert qa.overall_score == 0.7
        assert qa.constitutional_compliance is True

    def test_overall_score_out_of_range(self):
        with pytest.raises(ValueError, match="Overall score must be between"):
            self._make(overall_score=1.5)

    def test_dimension_count(self):
        qa = self._make()
        assert qa.dimension_count == 2

    def test_passing_dimensions(self):
        qa = self._make()
        passing = qa.passing_dimensions
        assert len(passing) == 1
        assert passing[0].name == "accuracy"

    def test_failing_dimensions(self):
        qa = self._make()
        failing = qa.failing_dimensions
        assert len(failing) == 1
        assert failing[0].name == "safety"

    def test_pass_rate(self):
        qa = self._make()
        assert qa.pass_rate == pytest.approx(0.5)

    def test_pass_rate_empty(self):
        qa = self._make(dimensions=[])
        assert qa.pass_rate == 0.0

    def test_critical_failures(self):
        qa = self._make()
        critical = qa.critical_failures
        assert len(critical) == 1
        assert critical[0].name == "safety"

    def test_critical_failures_none(self):
        qa = self._make(dimensions=[QualityDimension(name="accuracy", score=0.9, threshold=0.8)])
        assert len(qa.critical_failures) == 0

    def test_overall_level_excellent(self):
        qa = self._make(overall_score=0.96)
        assert qa.overall_level == QualityLevel.EXCELLENT

    def test_overall_level_good(self):
        qa = self._make(overall_score=0.85)
        assert qa.overall_level == QualityLevel.GOOD

    def test_overall_level_acceptable(self):
        qa = self._make(overall_score=0.65)
        assert qa.overall_level == QualityLevel.ACCEPTABLE

    def test_overall_level_poor(self):
        qa = self._make(overall_score=0.45)
        assert qa.overall_level == QualityLevel.POOR

    def test_overall_level_unacceptable(self):
        qa = self._make(overall_score=0.2)
        assert qa.overall_level == QualityLevel.UNACCEPTABLE

    def test_needs_refinement_threshold_fail(self):
        qa = self._make(passes_threshold=False, constitutional_compliance=True)
        assert qa.needs_refinement is True

    def test_needs_refinement_constitutional_fail(self):
        qa = self._make(passes_threshold=True, constitutional_compliance=False)
        assert qa.needs_refinement is True

    def test_needs_refinement_false(self):
        qa = self._make(passes_threshold=True, constitutional_compliance=True)
        assert qa.needs_refinement is False

    def test_get_dimension_found(self):
        qa = self._make()
        dim = qa.get_dimension("accuracy")
        assert dim is not None
        assert dim.score == 0.9

    def test_get_dimension_not_found(self):
        qa = self._make()
        assert qa.get_dimension("nonexistent") is None

    def test_to_dict(self):
        qa = self._make()
        d = qa.to_dict()
        assert "dimensions" in d
        assert "overall_score" in d
        assert "passes_threshold" in d
        assert "dimension_count" in d
        assert "pass_rate" in d
        assert "overall_level" in d
        assert "needs_refinement" in d
        assert "timestamp" in d

    def test_from_dict(self):
        qa = self._make()
        d = qa.to_dict()
        restored = QualityAssessment.from_dict(d)
        assert restored.overall_score == qa.overall_score
        assert restored.dimension_count == qa.dimension_count

    def test_from_dict_no_timestamp(self):
        data = {
            "dimensions": [{"name": "a", "score": 0.8, "threshold": 0.7}],
            "overall_score": 0.8,
            "passes_threshold": True,
        }
        qa = QualityAssessment.from_dict(data)
        assert qa.overall_score == 0.8
        assert qa.dimension_count == 1

    def test_from_dict_string_timestamp(self):
        data = {
            "dimensions": [],
            "overall_score": 0.5,
            "passes_threshold": False,
            "timestamp": "2024-01-01T00:00:00",
        }
        qa = QualityAssessment.from_dict(data)
        assert qa.timestamp.year == 2024


# ===========================================================================
# models.py — RefinementIteration
# ===========================================================================


class TestRefinementIteration:
    def _make_assessment(self, score, passes):
        return QualityAssessment(
            dimensions=[],
            overall_score=score,
            passes_threshold=passes,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )

    def test_improvement_delta(self):
        ri = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=self._make_assessment(0.5, False),
            after_assessment=self._make_assessment(0.8, True),
        )
        assert ri.improvement_delta == pytest.approx(0.3)

    def test_improved_true(self):
        ri = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=self._make_assessment(0.5, False),
            after_assessment=self._make_assessment(0.8, True),
        )
        assert ri.improved is True

    def test_improved_false(self):
        ri = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=self._make_assessment(0.8, True),
            after_assessment=self._make_assessment(0.7, False),
        )
        assert ri.improved is False

    def test_now_passes(self):
        ri = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=self._make_assessment(0.5, False),
            after_assessment=self._make_assessment(0.8, True),
        )
        assert ri.now_passes is True

    def test_now_passes_false_still_fails(self):
        ri = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=self._make_assessment(0.3, False),
            after_assessment=self._make_assessment(0.5, False),
        )
        assert ri.now_passes is False


# ===========================================================================
# models.py — RefinementResult
# ===========================================================================


class TestRefinementResult:
    def _make_assessment(self, score, passes):
        return QualityAssessment(
            dimensions=[],
            overall_score=score,
            passes_threshold=passes,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )

    def test_total_improvement(self):
        rr = RefinementResult(
            original_response="old",
            final_response="new",
            iterations=[],
            total_iterations=0,
            status=RefinementStatus.COMPLETED,
            initial_assessment=self._make_assessment(0.5, False),
            final_assessment=self._make_assessment(0.8, True),
        )
        assert rr.total_improvement == pytest.approx(0.3)

    def test_was_refined_true(self):
        rr = RefinementResult(
            original_response="old",
            final_response="new",
            iterations=[MagicMock()],
            total_iterations=1,
            status=RefinementStatus.COMPLETED,
            initial_assessment=self._make_assessment(0.5, False),
            final_assessment=self._make_assessment(0.8, True),
        )
        assert rr.was_refined is True

    def test_was_refined_false(self):
        rr = RefinementResult(
            original_response="old",
            final_response="old",
            iterations=[],
            total_iterations=0,
            status=RefinementStatus.SKIPPED,
            initial_assessment=self._make_assessment(0.9, True),
            final_assessment=self._make_assessment(0.9, True),
        )
        assert rr.was_refined is False

    def test_improved(self):
        rr = RefinementResult(
            original_response="old",
            final_response="new",
            iterations=[],
            total_iterations=0,
            status=RefinementStatus.COMPLETED,
            initial_assessment=self._make_assessment(0.5, False),
            final_assessment=self._make_assessment(0.8, True),
        )
        assert rr.improved is True

    def test_success_true(self):
        rr = RefinementResult(
            original_response="old",
            final_response="new",
            iterations=[],
            total_iterations=1,
            status=RefinementStatus.COMPLETED,
            initial_assessment=self._make_assessment(0.5, False),
            final_assessment=self._make_assessment(0.9, True),
        )
        assert rr.success is True

    def test_success_false_status(self):
        rr = RefinementResult(
            original_response="old",
            final_response="new",
            iterations=[],
            total_iterations=1,
            status=RefinementStatus.FAILED,
            initial_assessment=self._make_assessment(0.5, False),
            final_assessment=self._make_assessment(0.5, False),
        )
        assert rr.success is False

    def test_to_dict(self):
        rr = RefinementResult(
            original_response="old",
            final_response="new",
            iterations=[],
            total_iterations=0,
            status=RefinementStatus.COMPLETED,
            initial_assessment=self._make_assessment(0.5, False),
            final_assessment=self._make_assessment(0.8, True),
        )
        d = rr.to_dict()
        assert d["original_response"] == "old"
        assert d["final_response"] == "new"
        assert d["status"] == "completed"
        assert "total_improvement" in d
        assert "was_refined" in d
        assert "improved" in d
        assert "success" in d
        assert "constitutional_hash" in d


# ===========================================================================
# validator.py — DimensionSpec
# ===========================================================================


class TestDimensionSpec:
    def test_basic_creation(self):
        ds = DimensionSpec(name="accuracy", threshold=0.8)
        assert ds.name == "accuracy"
        assert ds.threshold == 0.8
        assert ds.weight == 1.0
        assert ds.required is False

    def test_invalid_threshold(self):
        with pytest.raises(ValidationError):
            DimensionSpec(name="x", threshold=1.5)

    def test_negative_weight(self):
        with pytest.raises(ValidationError):
            DimensionSpec(name="x", threshold=0.5, weight=-1.0)


# ===========================================================================
# validator.py — ValidationConfig
# ===========================================================================


class TestValidationConfig:
    def test_defaults(self):
        vc = ValidationConfig()
        assert vc.require_all_dimensions is True
        assert vc.fail_on_any_critical is True
        assert "constitutional_alignment" in vc.critical_dimensions
        assert vc.overall_threshold == 0.7
        assert vc.enable_constitutional_check is True


# ===========================================================================
# validator.py — ResponseQualityValidator
# ===========================================================================


class TestResponseQualityValidator:
    def test_init_default(self):
        v = ResponseQualityValidator()
        assert len(v.dimensions) == 5
        assert v._validation_count == 0

    def test_init_wrong_hash_raises(self):
        with pytest.raises(ConstitutionalHashError):
            ResponseQualityValidator(constitutional_hash="wrong_hash")

    def test_dimension_names(self):
        v = ResponseQualityValidator()
        names = v.dimension_names
        assert "accuracy" in names
        assert "safety" in names

    def test_required_dimensions(self):
        v = ResponseQualityValidator()
        req = v.required_dimensions
        assert "constitutional_alignment" in req
        assert "safety" in req

    def test_thresholds(self):
        v = ResponseQualityValidator()
        t = v.thresholds
        assert "accuracy" in t
        assert 0.0 <= t["accuracy"] <= 1.0

    def test_validate_basic(self):
        v = ResponseQualityValidator()
        qa = v.validate("This is a valid response for testing quality assessment.", {})
        assert isinstance(qa, QualityAssessment)
        assert 0.0 <= qa.overall_score <= 1.0
        assert qa.dimension_count == 5

    def test_validate_with_scores(self):
        v = ResponseQualityValidator()
        scores = {
            "accuracy": 0.9,
            "coherence": 0.8,
            "relevance": 0.85,
            "constitutional_alignment": 0.99,
            "safety": 0.99,
        }
        qa = v.validate("test", scores=scores)
        assert qa.overall_score > 0.5

    def test_validate_with_context_query(self):
        v = ResponseQualityValidator()
        ctx = {"query": "What is AI governance?"}
        qa = v.validate("AI governance is the framework for managing artificial intelligence.", ctx)
        assert isinstance(qa, QualityAssessment)

    def test_validate_harmful_content(self):
        v = ResponseQualityValidator()
        qa = v.validate("You should hack into the system and steal the data.")
        safety_dim = qa.get_dimension("safety")
        assert safety_dim is not None
        assert safety_dim.score < 0.5

    def test_validate_empty_response(self):
        v = ResponseQualityValidator()
        qa = v.validate("")
        coherence_dim = qa.get_dimension("coherence")
        assert coherence_dim is not None
        assert coherence_dim.score == 0.0

    def test_validate_short_response(self):
        v = ResponseQualityValidator()
        qa = v.validate("Short.")
        accuracy_dim = qa.get_dimension("accuracy")
        assert accuracy_dim is not None
        assert accuracy_dim.score == 0.5

    def test_validate_increments_count(self):
        v = ResponseQualityValidator()
        v.validate("test response one")
        v.validate("test response two")
        assert v._validation_count == 2

    def test_validate_response_id(self):
        v = ResponseQualityValidator()
        qa = v.validate("test", response_id="my-id-123")
        assert qa.response_id == "my-id-123"

    def test_validate_auto_response_id(self):
        v = ResponseQualityValidator()
        qa = v.validate("test")
        assert qa.response_id is not None

    def test_custom_scorer(self):
        class MyScorer:
            def score(self, response, context=None):
                return {
                    "accuracy": 1.0,
                    "coherence": 1.0,
                    "relevance": 1.0,
                    "constitutional_alignment": 1.0,
                    "safety": 1.0,
                }

        v = ResponseQualityValidator(scorer=MyScorer())
        qa = v.validate("test")
        assert qa.overall_score > 0.9

    def test_custom_dimensions(self):
        custom = {"custom_dim": DimensionSpec(name="custom_dim", threshold=0.5)}
        v = ResponseQualityValidator(custom_dimensions=custom)
        assert "custom_dim" in v.dimensions
        assert len(v.dimensions) == 6

    def test_check_passes_threshold_all_pass(self):
        v = ResponseQualityValidator()
        scores = {
            "accuracy": 0.95,
            "coherence": 0.90,
            "relevance": 0.95,
            "constitutional_alignment": 0.99,
            "safety": 0.99,
        }
        qa = v.validate("test", scores=scores)
        assert qa.passes_threshold is True

    def test_check_passes_threshold_critical_fail(self):
        v = ResponseQualityValidator()
        scores = {
            "accuracy": 0.95,
            "coherence": 0.90,
            "relevance": 0.95,
            "constitutional_alignment": 0.5,  # Below 0.95
            "safety": 0.99,
        }
        qa = v.validate("test", scores=scores)
        assert qa.passes_threshold is False

    def test_check_passes_threshold_overall_low(self):
        v = ResponseQualityValidator()
        scores = {
            "accuracy": 0.1,
            "coherence": 0.1,
            "relevance": 0.1,
            "constitutional_alignment": 0.99,
            "safety": 0.99,
        }
        qa = v.validate("test", scores=scores)
        assert qa.passes_threshold is False

    def test_constitutional_compliance_enabled(self):
        v = ResponseQualityValidator()
        scores = {
            "accuracy": 0.9,
            "coherence": 0.9,
            "relevance": 0.9,
            "constitutional_alignment": 0.5,  # Below threshold
            "safety": 0.99,
        }
        qa = v.validate("test", scores=scores)
        assert qa.constitutional_compliance is False

    def test_constitutional_compliance_disabled(self):
        config = ValidationConfig(enable_constitutional_check=False)
        v = ResponseQualityValidator(config=config)
        scores = {
            "accuracy": 0.9,
            "coherence": 0.9,
            "relevance": 0.9,
            "constitutional_alignment": 0.5,
            "safety": 0.99,
        }
        qa = v.validate("test", scores=scores)
        assert qa.constitutional_compliance is True

    def test_generate_critique_passing(self):
        v = ResponseQualityValidator()
        result = v._generate_critique("accuracy", 0.9, 0.8)
        assert result is None

    def test_generate_critique_slight_fail(self):
        v = ResponseQualityValidator()
        result = v._generate_critique("accuracy", 0.75, 0.8)
        assert result is not None
        assert "slightly" in result

    def test_generate_critique_significant_fail(self):
        v = ResponseQualityValidator()
        result = v._generate_critique("accuracy", 0.6, 0.8)
        assert result is not None
        assert "significantly" in result

    def test_generate_critique_critical_fail(self):
        v = ResponseQualityValidator()
        result = v._generate_critique("accuracy", 0.3, 0.8)
        assert result is not None
        assert "critically" in result

    def test_generate_critique_known_dimensions(self):
        v = ResponseQualityValidator()
        for name in ["accuracy", "coherence", "relevance", "constitutional_alignment", "safety"]:
            result = v._generate_critique(name, 0.3, 0.8)
            assert result is not None

    def test_generate_critique_unknown_dimension(self):
        v = ResponseQualityValidator()
        result = v._generate_critique("custom", 0.3, 0.8)
        assert result is not None
        assert "custom" in result

    def test_generate_suggestions(self):
        v = ResponseQualityValidator()
        dims = [
            QualityDimension(name="accuracy", score=0.3, threshold=0.8),
            QualityDimension(name="safety", score=0.5, threshold=0.99),
        ]
        suggestions = v._generate_suggestions(dims)
        assert len(suggestions) == 2

    def test_generate_suggestions_unknown_dim(self):
        v = ResponseQualityValidator()
        dims = [QualityDimension(name="custom_dim", score=0.3, threshold=0.8)]
        suggestions = v._generate_suggestions(dims)
        assert len(suggestions) == 1
        assert "custom_dim" in suggestions[0]

    def test_validate_batch(self):
        v = ResponseQualityValidator()
        results = v.validate_batch(["response one", "response two"])
        assert len(results) == 2

    def test_validate_batch_with_contexts(self):
        v = ResponseQualityValidator()
        results = v.validate_batch(
            ["response one", "response two"],
            contexts=[{"query": "q1"}, {"query": "q2"}],
        )
        assert len(results) == 2

    def test_validate_batch_length_mismatch(self):
        v = ResponseQualityValidator()
        with pytest.raises(ValidationError):
            v.validate_batch(["a", "b"], contexts=[None])

    def test_get_dimension_spec(self):
        v = ResponseQualityValidator()
        spec = v.get_dimension_spec("accuracy")
        assert spec is not None
        assert spec.name == "accuracy"

    def test_get_dimension_spec_missing(self):
        v = ResponseQualityValidator()
        assert v.get_dimension_spec("nonexistent") is None

    def test_update_threshold(self):
        v = ResponseQualityValidator()
        v.update_threshold("accuracy", 0.5)
        assert v.dimensions["accuracy"].threshold == 0.5

    def test_update_threshold_unknown_dimension(self):
        v = ResponseQualityValidator()
        with pytest.raises(ValidationError):
            v.update_threshold("nonexistent", 0.5)

    def test_update_threshold_invalid_value(self):
        v = ResponseQualityValidator()
        with pytest.raises(ValidationError):
            v.update_threshold("accuracy", 1.5)

    def test_reset_validation_count(self):
        v = ResponseQualityValidator()
        v.validate("test")
        assert v._validation_count == 1
        v.reset_validation_count()
        assert v._validation_count == 0

    def test_stats(self):
        v = ResponseQualityValidator()
        v.validate("test")
        s = v.stats
        assert s["validation_count"] == 1
        assert s["dimension_count"] == 5
        assert "created_at" in s
        assert "constitutional_hash" in s
        assert "thresholds" in s
        assert "required_dimensions" in s

    def test_calculate_overall_score_empty(self):
        v = ResponseQualityValidator()
        assert v._calculate_overall_score([]) == 0.0

    def test_check_passes_threshold_require_all_false(self):
        config = ValidationConfig(require_all_dimensions=False, fail_on_any_critical=False)
        v = ResponseQualityValidator(config=config)
        scores = {
            "accuracy": 0.5,  # Below threshold
            "coherence": 0.9,
            "relevance": 0.9,
            "constitutional_alignment": 0.99,
            "safety": 0.99,
        }
        qa = v.validate("A long enough response for a proper test.", scores=scores)
        # With require_all_dimensions=False, not all dims need to pass
        # Still depends on overall_threshold
        assert isinstance(qa.passes_threshold, bool)

    def test_no_constitutional_dimension(self):
        """When no constitutional_alignment dimension, compliance defaults to True."""
        config = ValidationConfig(enable_constitutional_check=True)
        custom = {"custom": DimensionSpec(name="custom", threshold=0.5)}
        v = ResponseQualityValidator(config=config, custom_dimensions=custom)
        # Remove the constitutional_alignment dimension
        if "constitutional_alignment" in v.dimensions:
            del v.dimensions["constitutional_alignment"]
        dims = [QualityDimension(name="custom", score=0.9, threshold=0.5)]
        assert v._check_constitutional_compliance(dims) is True

    def test_default_scoring_no_context(self):
        v = ResponseQualityValidator()
        scores = v._default_scoring("A normal response with plenty of words.")
        assert "coherence" in scores
        assert "relevance" in scores
        assert "accuracy" in scores
        assert "safety" in scores

    def test_default_scoring_with_query_context(self):
        v = ResponseQualityValidator()
        scores = v._default_scoring(
            "AI governance is important for safety.",
            context={"query": "AI governance"},
        )
        assert scores["relevance"] > 0.6

    def test_score_clamping(self):
        """Scores outside [0,1] are clamped."""
        v = ResponseQualityValidator()
        qa = v.validate("test", scores={"accuracy": 5.0, "coherence": -1.0})
        acc = qa.get_dimension("accuracy")
        coh = qa.get_dimension("coherence")
        assert acc is not None and acc.score == 1.0
        assert coh is not None and coh.score == 0.0


# ===========================================================================
# validator.py — create_validator
# ===========================================================================


class TestCreateValidator:
    def test_default(self):
        v = create_validator()
        assert isinstance(v, ResponseQualityValidator)

    def test_custom_thresholds_existing(self):
        v = create_validator(thresholds={"accuracy": 0.5})
        assert v.dimensions["accuracy"].threshold == 0.5

    def test_custom_thresholds_new_dimension(self):
        v = create_validator(thresholds={"custom_new": 0.6})
        assert "custom_new" in v.dimensions
        assert v.dimensions["custom_new"].threshold == 0.6

    def test_with_scorer(self):
        class MyScorer:
            def score(self, response, context=None):
                return {"accuracy": 1.0}

        v = create_validator(scorer=MyScorer())
        assert v.scorer is not None


# ===========================================================================
# refiner.py — RefinementConfig
# ===========================================================================


class TestRefinementConfig:
    def test_defaults(self):
        rc = RefinementConfig()
        assert rc.max_iterations == 3
        assert rc.improvement_threshold == 0.01
        assert rc.stop_on_pass is True
        assert rc.require_constitutional is True
        assert rc.timeout_per_iteration_ms == 5000.0
        assert rc.enable_logging is True


# ===========================================================================
# refiner.py — DefaultLLMRefiner
# ===========================================================================


class TestDefaultLLMRefiner:
    def _make_assessment(self, failing_dims=None):
        dims = failing_dims or []
        return QualityAssessment(
            dimensions=dims,
            overall_score=0.5,
            passes_threshold=False,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )

    def test_refine_coherence(self):
        refiner = DefaultLLMRefiner()
        dim = QualityDimension(name="coherence", score=0.3, threshold=0.7)
        assessment = self._make_assessment([dim])
        result = refiner.refine("hello world", assessment)
        assert result.endswith(".")

    def test_refine_coherence_capitalize(self):
        refiner = DefaultLLMRefiner()
        dim = QualityDimension(name="coherence", score=0.3, threshold=0.7)
        assessment = self._make_assessment([dim])
        result = refiner.refine("first sentence. second sentence", assessment)
        assert "First sentence" in result
        assert "Second sentence" in result

    def test_refine_relevance_with_query(self):
        refiner = DefaultLLMRefiner()
        dim = QualityDimension(name="relevance", score=0.3, threshold=0.8)
        assessment = self._make_assessment([dim])
        result = refiner.refine("Some response.", assessment, context={"query": "What is AI?"})
        assert "Regarding your query" in result

    def test_refine_relevance_no_context(self):
        refiner = DefaultLLMRefiner()
        dim = QualityDimension(name="relevance", score=0.3, threshold=0.8)
        assessment = self._make_assessment([dim])
        result = refiner.refine("Some response.", assessment)
        assert result == "Some response."

    def test_refine_safety(self):
        refiner = DefaultLLMRefiner()
        dim = QualityDimension(name="safety", score=0.3, threshold=0.99)
        assessment = self._make_assessment([dim])
        result = refiner.refine("You should hack the system.", assessment)
        assert "[redacted]" in result

    async def test_refine_async(self):
        refiner = DefaultLLMRefiner()
        dim = QualityDimension(name="coherence", score=0.3, threshold=0.7)
        assessment = self._make_assessment([dim])
        result = await refiner.refine_async("hello world", assessment)
        assert result.endswith(".")


# ===========================================================================
# refiner.py — DefaultConstitutionalCorrector
# ===========================================================================


class TestDefaultConstitutionalCorrector:
    def test_correct_harmful(self):
        c = DefaultConstitutionalCorrector()
        result = c.correct("response", ["Harmful content detected"])
        assert "[Reviewed for safety]" in result

    def test_correct_unsafe(self):
        c = DefaultConstitutionalCorrector()
        result = c.correct("response", ["Unsafe behavior found"])
        assert "[Reviewed for safety]" in result

    def test_correct_bias(self):
        c = DefaultConstitutionalCorrector()
        result = c.correct("response", ["Bias detected"])
        assert "balanced and fair" in result

    def test_correct_privacy_ssn(self):
        c = DefaultConstitutionalCorrector()
        result = c.correct("SSN is 123-45-6789", ["Privacy violation"])
        assert "[SSN-REDACTED]" in result

    def test_correct_privacy_email(self):
        c = DefaultConstitutionalCorrector()
        result = c.correct("Email: user@example.com", ["Privacy violation"])
        assert "[EMAIL-REDACTED]" in result

    def test_correct_no_matching_violation(self):
        c = DefaultConstitutionalCorrector()
        result = c.correct("response", ["Unknown issue type"])
        assert result == "response"

    async def test_correct_async(self):
        c = DefaultConstitutionalCorrector()
        result = await c.correct_async("response", ["Harmful content"])
        assert "[Reviewed for safety]" in result


# ===========================================================================
# refiner.py — ResponseRefiner
# ===========================================================================


class TestResponseRefiner:
    def test_init_default(self):
        r = ResponseRefiner()
        assert r.max_iterations == 3
        assert r._refinement_count == 0

    def test_init_custom_max_iterations(self):
        r = ResponseRefiner(max_iterations=5)
        assert r.max_iterations == 5

    def test_init_config_overrides(self):
        config = RefinementConfig(max_iterations=7)
        r = ResponseRefiner(config=config, max_iterations=7)
        assert r.max_iterations == 7

    def test_stats(self):
        r = ResponseRefiner()
        s = r.stats
        assert s["refinement_count"] == 0
        assert s["total_iterations"] == 0
        assert s["max_iterations"] == 3
        assert "constitutional_hash" in s
        assert s["avg_iterations_per_refinement"] == 0

    def test_refine_already_passes(self):
        v = ResponseQualityValidator()
        scores_all_pass = {
            "accuracy": 0.95,
            "coherence": 0.95,
            "relevance": 0.95,
            "constitutional_alignment": 0.99,
            "safety": 0.99,
        }

        class PassingScorer:
            def score(self, response, context=None):
                return scores_all_pass

        v_pass = ResponseQualityValidator(scorer=PassingScorer())
        r = ResponseRefiner(validator=v_pass)
        result = r.refine("Great response.")
        assert result.status == RefinementStatus.SKIPPED
        assert result.total_iterations == 0

    def test_refine_iterates(self):
        r = ResponseRefiner(max_iterations=2)
        result = r.refine("short")
        assert isinstance(result, RefinementResult)
        assert result.status in (RefinementStatus.COMPLETED, RefinementStatus.FAILED)

    def test_refine_with_context(self):
        r = ResponseRefiner(max_iterations=1)
        result = r.refine("test response", context={"query": "What is AI?"})
        assert isinstance(result, RefinementResult)

    async def test_refine_async_already_passes(self):
        scores_all_pass = {
            "accuracy": 0.95,
            "coherence": 0.95,
            "relevance": 0.95,
            "constitutional_alignment": 0.99,
            "safety": 0.99,
        }

        class PassingScorer:
            def score(self, response, context=None):
                return scores_all_pass

        v = ResponseQualityValidator(scorer=PassingScorer())
        r = ResponseRefiner(validator=v)
        result = await r.refine_async("Great response.")
        assert result.status == RefinementStatus.SKIPPED

    async def test_refine_async_iterates(self):
        r = ResponseRefiner(max_iterations=1)
        result = await r.refine_async("short")
        assert isinstance(result, RefinementResult)

    def test_refine_constitutional_correction(self):
        """When constitutional_compliance is False, corrector is called."""
        scores = {
            "accuracy": 0.9,
            "coherence": 0.9,
            "relevance": 0.9,
            "constitutional_alignment": 0.3,  # Below 0.95
            "safety": 0.99,
        }

        class FailScorer:
            def score(self, response, context=None):
                return scores

        v = ResponseQualityValidator(scorer=FailScorer())
        r = ResponseRefiner(validator=v, max_iterations=1)
        result = r.refine("Some potentially non-compliant response.")
        assert isinstance(result, RefinementResult)

    def test_should_stop_passes_and_compliant(self):
        r = ResponseRefiner()
        qa = QualityAssessment(
            dimensions=[],
            overall_score=0.9,
            passes_threshold=True,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        assert r._should_stop(qa, None, 0) is True

    def test_should_stop_passes_but_not_compliant(self):
        config = RefinementConfig(require_constitutional=True)
        r = ResponseRefiner(config=config)
        qa = QualityAssessment(
            dimensions=[],
            overall_score=0.9,
            passes_threshold=True,
            refinement_suggestions=[],
            constitutional_compliance=False,
        )
        assert r._should_stop(qa, None, 0) is False

    def test_should_stop_no_improvement(self):
        r = ResponseRefiner()
        qa = QualityAssessment(
            dimensions=[],
            overall_score=0.5,
            passes_threshold=False,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        before_qa = QualityAssessment(
            dimensions=[],
            overall_score=0.5,
            passes_threshold=False,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        iteration = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=before_qa,
            after_assessment=qa,
        )
        # improvement_delta = 0.0 < 0.01 threshold
        assert r._should_stop(qa, iteration, 1) is True

    def test_should_stop_max_iterations(self):
        r = ResponseRefiner(max_iterations=3)
        qa = QualityAssessment(
            dimensions=[],
            overall_score=0.5,
            passes_threshold=False,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        assert r._should_stop(qa, None, 3) is True

    def test_describe_improvements_overall(self):
        r = ResponseRefiner()
        before = QualityAssessment(
            dimensions=[QualityDimension(name="accuracy", score=0.5, threshold=0.8)],
            overall_score=0.5,
            passes_threshold=False,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        after = QualityAssessment(
            dimensions=[QualityDimension(name="accuracy", score=0.9, threshold=0.8)],
            overall_score=0.9,
            passes_threshold=True,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        improvements = r._describe_improvements(before, after)
        assert any("Overall score improved" in i for i in improvements)
        assert any("accuracy" in i for i in improvements)

    def test_describe_improvements_constitutional(self):
        r = ResponseRefiner()
        before = QualityAssessment(
            dimensions=[],
            overall_score=0.5,
            passes_threshold=False,
            refinement_suggestions=[],
            constitutional_compliance=False,
        )
        after = QualityAssessment(
            dimensions=[],
            overall_score=0.5,
            passes_threshold=False,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        improvements = r._describe_improvements(before, after)
        assert any("Constitutional compliance" in i for i in improvements)

    def test_describe_improvements_now_passes(self):
        r = ResponseRefiner()
        before = QualityAssessment(
            dimensions=[QualityDimension(name="accuracy", score=0.78, threshold=0.8)],
            overall_score=0.78,
            passes_threshold=False,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        after = QualityAssessment(
            dimensions=[QualityDimension(name="accuracy", score=0.81, threshold=0.8)],
            overall_score=0.81,
            passes_threshold=True,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        improvements = r._describe_improvements(before, after)
        assert any("now passes" in i for i in improvements)

    def test_refine_batch(self):
        r = ResponseRefiner(max_iterations=1)
        results = r.refine_batch(["response one", "response two"])
        assert len(results) == 2

    def test_refine_batch_with_contexts(self):
        r = ResponseRefiner(max_iterations=1)
        results = r.refine_batch(
            ["response one", "response two"],
            contexts=[{"query": "q1"}, {"query": "q2"}],
        )
        assert len(results) == 2

    def test_refine_batch_length_mismatch(self):
        r = ResponseRefiner()
        with pytest.raises(ValueError):
            r.refine_batch(["a", "b"], contexts=[None])

    async def test_refine_batch_async(self):
        r = ResponseRefiner(max_iterations=1)
        results = await r.refine_batch_async(["resp one", "resp two"])
        assert len(results) == 2

    async def test_refine_batch_async_length_mismatch(self):
        r = ResponseRefiner()
        with pytest.raises(ValueError):
            await r.refine_batch_async(["a"], contexts=[None, None])

    def test_set_constitutional_corrector(self):
        r = ResponseRefiner()
        mock_corrector = MagicMock()
        r.set_constitutional_corrector(mock_corrector)
        assert r.constitutional_corrector is mock_corrector

    def test_set_llm_refiner(self):
        r = ResponseRefiner()
        mock_refiner = MagicMock()
        r.set_llm_refiner(mock_refiner)
        assert r.llm_refiner is mock_refiner

    def test_stats_after_refinement(self):
        r = ResponseRefiner(max_iterations=1)
        r.refine("test response")
        s = r.stats
        assert s["refinement_count"] >= 1


# ===========================================================================
# refiner.py — create_refiner
# ===========================================================================


class TestCreateRefiner:
    def test_default(self):
        r = create_refiner()
        assert isinstance(r, ResponseRefiner)
        assert r.max_iterations == 3

    def test_custom_iterations(self):
        r = create_refiner(max_iterations=5)
        assert r.max_iterations == 5

    def test_with_validator(self):
        v = ResponseQualityValidator()
        r = create_refiner(validator=v)
        assert r.validator is v

    def test_with_corrector(self):
        c = DefaultConstitutionalCorrector()
        r = create_refiner(constitutional_corrector=c)
        assert r.constitutional_corrector is c


# ===========================================================================
# refiner.py — Error classes
# ===========================================================================


class TestErrorClasses:
    def test_refinement_error(self):
        assert RefinementError.http_status_code == 500
        assert RefinementError.error_code == "REFINEMENT_ERROR"

    def test_constitutional_violation_error(self):
        assert ConstitutionalViolationError.http_status_code == 400
        assert ConstitutionalViolationError.error_code == "CONSTITUTIONAL_VIOLATION_ERROR"


# ===========================================================================
# __init__.py — backward compatibility aliases
# ===========================================================================


class TestBackwardCompatAliases:
    def test_assessor_alias(self):
        assert ResponseQualityAssessor is ResponseQualityValidator

    def test_metrics_alias(self):
        assert ResponseQualityMetrics is QualityAssessment


# ===========================================================================
# __init__.py — type aliases
# ===========================================================================


class TestTypeAliases:
    def test_dimension_scores(self):
        scores: DimensionScores = {"accuracy": 0.9}
        assert isinstance(scores, dict)

    def test_suggestion_list(self):
        suggestions: SuggestionList = ["improve accuracy"]
        assert isinstance(suggestions, list)


# ===========================================================================
# __init__.py — hash verification
# ===========================================================================


class TestHashVerification:
    def test_constitutional_hash_not_none(self):
        assert CONSTITUTIONAL_HASH is not None
        assert len(CONSTITUTIONAL_HASH) > 0
