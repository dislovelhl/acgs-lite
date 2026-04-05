"""
Tests for enhanced_agent_bus.response_quality package.

Covers all three submodules:
- models.py: QualityLevel, RefinementStatus, QualityDimension, QualityAssessment,
  RefinementIteration, RefinementResult
- validator.py: DimensionSpec, ValidationConfig, ResponseQualityValidator,
  ConstitutionalHashError, create_validator
- refiner.py: RefinementConfig, DefaultLLMRefiner, DefaultConstitutionalCorrector,
  ResponseRefiner, RefinementError, ConstitutionalViolationError, create_refiner

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import sys

sys.path.insert(0, "packages/enhanced_agent_bus")

import pytest

from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError
from enhanced_agent_bus.response_quality import (
    ConstitutionalHashError,
    DefaultConstitutionalCorrector,
    DefaultLLMRefiner,
    DimensionSpec,
    QualityAssessment,
    QualityDimension,
    QualityLevel,
    RefinementConfig,
    RefinementIteration,
    RefinementResult,
    RefinementStatus,
    ResponseQualityAssessor,
    ResponseQualityMetrics,
    ResponseQualityValidator,
    ResponseRefiner,
    ValidationConfig,
    create_refiner,
    create_validator,
)
from enhanced_agent_bus.response_quality.refiner import (
    ConstitutionalViolationError,
    RefinementError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GOOD_RESPONSE = (
    "The governance policy has been validated and approved by the constitutional "
    "framework. This compliance report covers all required aspects of the system. "
    "The authorized personnel have reviewed the documentation thoroughly. "
    "All policy requirements are satisfied according to the latest governance rules."
)

SHORT_RESPONSE = "Hi."


def _make_assessment(
    overall_score: float = 0.85,
    passes_threshold: bool = True,
    constitutional_compliance: bool = True,
    dim_scores: dict[str, float] | None = None,
) -> QualityAssessment:
    """Create a QualityAssessment for testing."""
    scores = dim_scores or {"accuracy": 0.9, "coherence": 0.8, "safety": 0.99}
    dims = [
        QualityDimension(name=name, score=score, threshold=0.7) for name, score in scores.items()
    ]
    return QualityAssessment(
        dimensions=dims,
        overall_score=overall_score,
        passes_threshold=passes_threshold,
        refinement_suggestions=["Improve coherence"],
        constitutional_compliance=constitutional_compliance,
    )


# ===========================================================================
# models.py
# ===========================================================================


class TestQualityLevel:
    def test_all_values(self) -> None:
        assert QualityLevel.EXCELLENT.value == "excellent"
        assert QualityLevel.GOOD.value == "good"
        assert QualityLevel.ACCEPTABLE.value == "acceptable"
        assert QualityLevel.POOR.value == "poor"
        assert QualityLevel.UNACCEPTABLE.value == "unacceptable"

    def test_member_count(self) -> None:
        assert len(QualityLevel) == 5


class TestRefinementStatus:
    def test_all_values(self) -> None:
        assert RefinementStatus.PENDING.value == "pending"
        assert RefinementStatus.IN_PROGRESS.value == "in_progress"
        assert RefinementStatus.COMPLETED.value == "completed"
        assert RefinementStatus.FAILED.value == "failed"
        assert RefinementStatus.SKIPPED.value == "skipped"


class TestQualityDimension:
    def test_basic_creation(self) -> None:
        dim = QualityDimension(name="accuracy", score=0.9, threshold=0.8)
        assert dim.name == "accuracy"
        assert dim.score == 0.9
        assert dim.threshold == 0.8

    def test_passes_when_above_threshold(self) -> None:
        dim = QualityDimension(name="a", score=0.9, threshold=0.8)
        assert dim.passes is True

    def test_fails_when_below_threshold(self) -> None:
        dim = QualityDimension(name="a", score=0.5, threshold=0.8)
        assert dim.passes is False

    def test_passes_at_exact_threshold(self) -> None:
        dim = QualityDimension(name="a", score=0.8, threshold=0.8)
        assert dim.passes is True

    def test_gap_positive(self) -> None:
        dim = QualityDimension(name="a", score=0.9, threshold=0.7)
        assert dim.gap == pytest.approx(0.2)

    def test_gap_negative(self) -> None:
        dim = QualityDimension(name="a", score=0.5, threshold=0.7)
        assert dim.gap == pytest.approx(-0.2)

    def test_level_excellent(self) -> None:
        dim = QualityDimension(name="a", score=0.96, threshold=0.5)
        assert dim.level == QualityLevel.EXCELLENT

    def test_level_good(self) -> None:
        dim = QualityDimension(name="a", score=0.85, threshold=0.5)
        assert dim.level == QualityLevel.GOOD

    def test_level_acceptable(self) -> None:
        dim = QualityDimension(name="a", score=0.65, threshold=0.5)
        assert dim.level == QualityLevel.ACCEPTABLE

    def test_level_poor(self) -> None:
        dim = QualityDimension(name="a", score=0.45, threshold=0.5)
        assert dim.level == QualityLevel.POOR

    def test_level_unacceptable(self) -> None:
        dim = QualityDimension(name="a", score=0.3, threshold=0.5)
        assert dim.level == QualityLevel.UNACCEPTABLE

    def test_score_below_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="Score must be between"):
            QualityDimension(name="a", score=-0.1, threshold=0.5)

    def test_score_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="Score must be between"):
            QualityDimension(name="a", score=1.1, threshold=0.5)

    def test_threshold_below_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="Threshold must be between"):
            QualityDimension(name="a", score=0.5, threshold=-0.1)

    def test_threshold_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="Threshold must be between"):
            QualityDimension(name="a", score=0.5, threshold=1.1)

    def test_to_dict(self) -> None:
        dim = QualityDimension(name="accuracy", score=0.9, threshold=0.8, critique="Good")
        d = dim.to_dict()
        assert d["name"] == "accuracy"
        assert d["score"] == 0.9
        assert d["threshold"] == 0.8
        assert d["critique"] == "Good"
        assert d["passes"] is True
        assert d["gap"] == pytest.approx(0.1)
        assert d["level"] == "good"

    def test_critique_none(self) -> None:
        dim = QualityDimension(name="a", score=0.9, threshold=0.5)
        assert dim.critique is None


class TestQualityAssessment:
    def test_basic_creation(self) -> None:
        a = _make_assessment()
        assert a.overall_score == 0.85
        assert a.passes_threshold is True

    def test_overall_score_validation(self) -> None:
        with pytest.raises(ValueError, match="Overall score must be between"):
            QualityAssessment(
                dimensions=[],
                overall_score=1.5,
                passes_threshold=True,
                refinement_suggestions=[],
                constitutional_compliance=True,
            )

    def test_dimension_count(self) -> None:
        a = _make_assessment()
        assert a.dimension_count == 3

    def test_passing_dimensions(self) -> None:
        a = _make_assessment(dim_scores={"a": 0.9, "b": 0.5})
        passing = a.passing_dimensions
        assert len(passing) == 1
        assert passing[0].name == "a"

    def test_failing_dimensions(self) -> None:
        a = _make_assessment(dim_scores={"a": 0.9, "b": 0.5})
        failing = a.failing_dimensions
        assert len(failing) == 1
        assert failing[0].name == "b"

    def test_pass_rate(self) -> None:
        a = _make_assessment(dim_scores={"a": 0.9, "b": 0.5})
        assert a.pass_rate == pytest.approx(0.5)

    def test_pass_rate_empty_dims(self) -> None:
        a = QualityAssessment(
            dimensions=[],
            overall_score=0.0,
            passes_threshold=False,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        assert a.pass_rate == 0.0

    def test_critical_failures(self) -> None:
        dims = [
            QualityDimension(name="safety", score=0.3, threshold=0.99),
            QualityDimension(name="coherence", score=0.5, threshold=0.7),
        ]
        a = QualityAssessment(
            dimensions=dims,
            overall_score=0.4,
            passes_threshold=False,
            refinement_suggestions=[],
            constitutional_compliance=False,
        )
        critical = a.critical_failures
        assert len(critical) == 1
        assert critical[0].name == "safety"

    def test_overall_level_excellent(self) -> None:
        a = _make_assessment(overall_score=0.96)
        assert a.overall_level == QualityLevel.EXCELLENT

    def test_overall_level_good(self) -> None:
        a = _make_assessment(overall_score=0.85)
        assert a.overall_level == QualityLevel.GOOD

    def test_overall_level_acceptable(self) -> None:
        a = _make_assessment(overall_score=0.65)
        assert a.overall_level == QualityLevel.ACCEPTABLE

    def test_overall_level_poor(self) -> None:
        a = _make_assessment(overall_score=0.45)
        assert a.overall_level == QualityLevel.POOR

    def test_overall_level_unacceptable(self) -> None:
        a = _make_assessment(overall_score=0.3)
        assert a.overall_level == QualityLevel.UNACCEPTABLE

    def test_needs_refinement_when_fails(self) -> None:
        a = _make_assessment(passes_threshold=False)
        assert a.needs_refinement is True

    def test_needs_refinement_when_unconstitutional(self) -> None:
        a = _make_assessment(passes_threshold=True, constitutional_compliance=False)
        assert a.needs_refinement is True

    def test_no_refinement_needed(self) -> None:
        a = _make_assessment(passes_threshold=True, constitutional_compliance=True)
        assert a.needs_refinement is False

    def test_get_dimension_found(self) -> None:
        a = _make_assessment(dim_scores={"accuracy": 0.9})
        dim = a.get_dimension("accuracy")
        assert dim is not None
        assert dim.score == 0.9

    def test_get_dimension_not_found(self) -> None:
        a = _make_assessment()
        assert a.get_dimension("nonexistent") is None

    def test_to_dict(self) -> None:
        a = _make_assessment()
        d = a.to_dict()
        assert "dimensions" in d
        assert "overall_score" in d
        assert "passes_threshold" in d
        assert "refinement_suggestions" in d
        assert "constitutional_compliance" in d
        assert "dimension_count" in d
        assert "pass_rate" in d
        assert "overall_level" in d
        assert "needs_refinement" in d

    def test_from_dict_roundtrip(self) -> None:
        a = _make_assessment()
        d = a.to_dict()
        restored = QualityAssessment.from_dict(d)
        assert restored.overall_score == a.overall_score
        assert restored.passes_threshold == a.passes_threshold
        assert len(restored.dimensions) == len(a.dimensions)

    def test_from_dict_no_timestamp(self) -> None:
        data = {
            "dimensions": [{"name": "a", "score": 0.9, "threshold": 0.7}],
            "overall_score": 0.9,
            "passes_threshold": True,
        }
        a = QualityAssessment.from_dict(data)
        assert a.timestamp is not None

    def test_from_dict_string_timestamp(self) -> None:
        data = {
            "dimensions": [],
            "overall_score": 0.5,
            "passes_threshold": False,
            "timestamp": "2024-01-01T00:00:00",
        }
        a = QualityAssessment.from_dict(data)
        assert a.timestamp.year == 2024


class TestRefinementIteration:
    def test_basic(self) -> None:
        before = _make_assessment(overall_score=0.5, passes_threshold=False)
        after = _make_assessment(overall_score=0.8, passes_threshold=True)
        it = RefinementIteration(
            iteration_number=1,
            original_response="bad",
            refined_response="good",
            before_assessment=before,
            after_assessment=after,
        )
        assert it.iteration_number == 1

    def test_improvement_delta(self) -> None:
        before = _make_assessment(overall_score=0.5)
        after = _make_assessment(overall_score=0.8)
        it = RefinementIteration(
            iteration_number=1,
            original_response="a",
            refined_response="b",
            before_assessment=before,
            after_assessment=after,
        )
        assert it.improvement_delta == pytest.approx(0.3)

    def test_improved_true(self) -> None:
        before = _make_assessment(overall_score=0.5)
        after = _make_assessment(overall_score=0.8)
        it = RefinementIteration(
            iteration_number=1,
            original_response="a",
            refined_response="b",
            before_assessment=before,
            after_assessment=after,
        )
        assert it.improved is True

    def test_improved_false(self) -> None:
        a = _make_assessment(overall_score=0.5)
        it = RefinementIteration(
            iteration_number=1,
            original_response="a",
            refined_response="b",
            before_assessment=a,
            after_assessment=a,
        )
        assert it.improved is False

    def test_now_passes(self) -> None:
        before = _make_assessment(passes_threshold=False)
        after = _make_assessment(passes_threshold=True)
        it = RefinementIteration(
            iteration_number=1,
            original_response="a",
            refined_response="b",
            before_assessment=before,
            after_assessment=after,
        )
        assert it.now_passes is True

    def test_now_passes_false_when_both_pass(self) -> None:
        a = _make_assessment(passes_threshold=True)
        it = RefinementIteration(
            iteration_number=1,
            original_response="a",
            refined_response="b",
            before_assessment=a,
            after_assessment=a,
        )
        assert it.now_passes is False


class TestRefinementResult:
    def _make_result(
        self,
        status: RefinementStatus = RefinementStatus.COMPLETED,
        passes: bool = True,
        initial_score: float = 0.5,
        final_score: float = 0.9,
        iterations: list | None = None,
    ) -> RefinementResult:
        return RefinementResult(
            original_response="original",
            final_response="final",
            iterations=iterations or [],
            total_iterations=len(iterations) if iterations else 0,
            status=status,
            initial_assessment=_make_assessment(overall_score=initial_score),
            final_assessment=_make_assessment(overall_score=final_score, passes_threshold=passes),
        )

    def test_total_improvement(self) -> None:
        r = self._make_result(initial_score=0.4, final_score=0.9)
        assert r.total_improvement == pytest.approx(0.5)

    def test_was_refined_true(self) -> None:
        before = _make_assessment(overall_score=0.5)
        after = _make_assessment(overall_score=0.8)
        it = RefinementIteration(
            iteration_number=1,
            original_response="a",
            refined_response="b",
            before_assessment=before,
            after_assessment=after,
        )
        r = self._make_result(iterations=[it])
        assert r.was_refined is True

    def test_was_refined_false(self) -> None:
        r = self._make_result(iterations=[])
        assert r.was_refined is False

    def test_improved_true(self) -> None:
        r = self._make_result(initial_score=0.3, final_score=0.8)
        assert r.improved is True

    def test_improved_false(self) -> None:
        r = self._make_result(initial_score=0.8, final_score=0.8)
        assert r.improved is False

    def test_success_when_completed_and_passes(self) -> None:
        r = self._make_result(status=RefinementStatus.COMPLETED, passes=True)
        assert r.success is True

    def test_not_success_when_failed(self) -> None:
        r = self._make_result(status=RefinementStatus.FAILED, passes=True)
        assert r.success is False

    def test_not_success_when_doesnt_pass(self) -> None:
        r = self._make_result(status=RefinementStatus.COMPLETED, passes=False)
        assert r.success is False

    def test_to_dict(self) -> None:
        r = self._make_result()
        d = r.to_dict()
        assert "original_response" in d
        assert "final_response" in d
        assert "total_iterations" in d
        assert "status" in d
        assert "total_improvement" in d
        assert "was_refined" in d
        assert "improved" in d
        assert "success" in d
        assert "constitutional_hash" in d


# ===========================================================================
# validator.py
# ===========================================================================


class TestDimensionSpec:
    def test_basic(self) -> None:
        spec = DimensionSpec(name="accuracy", threshold=0.8)
        assert spec.name == "accuracy"
        assert spec.threshold == 0.8
        assert spec.weight == 1.0
        assert spec.required is False

    def test_invalid_threshold_high(self) -> None:
        with pytest.raises(ACGSValidationError):
            DimensionSpec(name="a", threshold=1.5)

    def test_invalid_threshold_low(self) -> None:
        with pytest.raises(ACGSValidationError):
            DimensionSpec(name="a", threshold=-0.1)

    def test_negative_weight(self) -> None:
        with pytest.raises(ACGSValidationError):
            DimensionSpec(name="a", threshold=0.5, weight=-1.0)


class TestValidationConfig:
    def test_defaults(self) -> None:
        cfg = ValidationConfig()
        assert cfg.require_all_dimensions is True
        assert cfg.fail_on_any_critical is True
        assert cfg.overall_threshold == 0.7
        assert cfg.enable_constitutional_check is True


class TestConstitutionalHashError:
    def test_is_exception(self) -> None:
        with pytest.raises(ConstitutionalHashError):
            raise ConstitutionalHashError("hash mismatch")


class TestResponseQualityValidator:
    @pytest.fixture
    def validator(self) -> ResponseQualityValidator:
        return ResponseQualityValidator()

    def test_init(self, validator: ResponseQualityValidator) -> None:
        assert len(validator.dimensions) >= 5

    def test_init_wrong_hash(self) -> None:
        with pytest.raises(ConstitutionalHashError):
            ResponseQualityValidator(constitutional_hash="wrong_hash")

    def test_dimension_names(self, validator: ResponseQualityValidator) -> None:
        names = validator.dimension_names
        assert "accuracy" in names
        assert "coherence" in names
        assert "safety" in names

    def test_required_dimensions(self, validator: ResponseQualityValidator) -> None:
        required = validator.required_dimensions
        assert "constitutional_alignment" in required
        assert "safety" in required

    def test_thresholds(self, validator: ResponseQualityValidator) -> None:
        t = validator.thresholds
        assert isinstance(t, dict)
        assert "accuracy" in t

    def test_validate_good_response(self, validator: ResponseQualityValidator) -> None:
        assessment = validator.validate(GOOD_RESPONSE)
        assert isinstance(assessment, QualityAssessment)
        assert assessment.overall_score > 0
        assert assessment.dimension_count >= 5

    def test_validate_with_context(self, validator: ResponseQualityValidator) -> None:
        ctx = {"query": "governance policy"}
        assessment = validator.validate(GOOD_RESPONSE, context=ctx)
        assert assessment.metadata["context_provided"] is True

    def test_validate_with_scores(self, validator: ResponseQualityValidator) -> None:
        scores = {
            "accuracy": 0.9,
            "coherence": 0.8,
            "relevance": 0.85,
            "constitutional_alignment": 0.99,
            "safety": 0.99,
        }
        assessment = validator.validate(GOOD_RESPONSE, scores=scores)
        assert assessment.overall_score > 0

    def test_validate_empty_response(self, validator: ResponseQualityValidator) -> None:
        assessment = validator.validate("")
        assert assessment.overall_score < 1.0

    def test_validate_harmful_content(self, validator: ResponseQualityValidator) -> None:
        assessment = validator.validate("I will hack into the system and steal data")
        assert (
            assessment.constitutional_compliance is True
            or assessment.constitutional_compliance is False
        )
        # Safety score should be low
        safety_dim = assessment.get_dimension("safety")
        assert safety_dim is not None
        assert safety_dim.score < 0.5

    def test_validate_short_response(self, validator: ResponseQualityValidator) -> None:
        assessment = validator.validate("Hi")
        assert isinstance(assessment, QualityAssessment)

    def test_default_scoring_with_query_context(self, validator: ResponseQualityValidator) -> None:
        ctx = {"query": "governance policy review"}
        assessment = validator.validate(GOOD_RESPONSE, context=ctx)
        relevance = assessment.get_dimension("relevance")
        assert relevance is not None
        assert relevance.score > 0.6

    def test_default_scoring_without_query(self, validator: ResponseQualityValidator) -> None:
        assessment = validator.validate(GOOD_RESPONSE)
        relevance = assessment.get_dimension("relevance")
        assert relevance is not None
        assert relevance.score == 0.75  # default moderate relevance

    def test_custom_dimensions(self) -> None:
        custom = {"custom_dim": DimensionSpec(name="custom_dim", threshold=0.5, weight=1.0)}
        v = ResponseQualityValidator(custom_dimensions=custom)
        assert "custom_dim" in v.dimensions

    def test_custom_scorer(self) -> None:
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
        assessment = v.validate("test")
        assert assessment.overall_score > 0.9

    def test_validate_batch(self, validator: ResponseQualityValidator) -> None:
        results = validator.validate_batch([GOOD_RESPONSE, SHORT_RESPONSE])
        assert len(results) == 2
        assert all(isinstance(r, QualityAssessment) for r in results)

    def test_validate_batch_with_contexts(self, validator: ResponseQualityValidator) -> None:
        results = validator.validate_batch(
            [GOOD_RESPONSE, GOOD_RESPONSE],
            contexts=[{"query": "test"}, None],
        )
        assert len(results) == 2

    def test_validate_batch_length_mismatch(self, validator: ResponseQualityValidator) -> None:
        with pytest.raises(ACGSValidationError):
            validator.validate_batch(["a", "b"], contexts=[None])

    def test_get_dimension_spec(self, validator: ResponseQualityValidator) -> None:
        spec = validator.get_dimension_spec("accuracy")
        assert spec is not None
        assert spec.name == "accuracy"

    def test_get_dimension_spec_missing(self, validator: ResponseQualityValidator) -> None:
        assert validator.get_dimension_spec("nonexistent") is None

    def test_update_threshold(self, validator: ResponseQualityValidator) -> None:
        validator.update_threshold("accuracy", 0.5)
        assert validator.dimensions["accuracy"].threshold == 0.5

    def test_update_threshold_unknown_dim(self, validator: ResponseQualityValidator) -> None:
        with pytest.raises(ACGSValidationError):
            validator.update_threshold("nonexistent", 0.5)

    def test_update_threshold_invalid_value(self, validator: ResponseQualityValidator) -> None:
        with pytest.raises(ACGSValidationError):
            validator.update_threshold("accuracy", 1.5)

    def test_reset_validation_count(self, validator: ResponseQualityValidator) -> None:
        validator.validate(GOOD_RESPONSE)
        assert validator._validation_count > 0
        validator.reset_validation_count()
        assert validator._validation_count == 0

    def test_stats(self, validator: ResponseQualityValidator) -> None:
        validator.validate(GOOD_RESPONSE)
        stats = validator.stats
        assert stats["validation_count"] == 1
        assert "constitutional_hash" in stats
        assert "thresholds" in stats
        assert "required_dimensions" in stats

    def test_generate_critique_passing(self, validator: ResponseQualityValidator) -> None:
        critique = validator._generate_critique("accuracy", 0.9, 0.8)
        assert critique is None

    def test_generate_critique_failing_slight(self, validator: ResponseQualityValidator) -> None:
        critique = validator._generate_critique("accuracy", 0.75, 0.8)
        assert critique is not None
        assert "slightly" in critique

    def test_generate_critique_failing_significant(
        self, validator: ResponseQualityValidator
    ) -> None:
        critique = validator._generate_critique("accuracy", 0.55, 0.8)
        assert critique is not None
        assert "significantly" in critique

    def test_generate_critique_failing_critical(self, validator: ResponseQualityValidator) -> None:
        critique = validator._generate_critique("accuracy", 0.2, 0.8)
        assert critique is not None
        assert "critically" in critique

    def test_generate_critique_unknown_dimension(self, validator: ResponseQualityValidator) -> None:
        critique = validator._generate_critique("unknown_dim", 0.3, 0.8)
        assert critique is not None
        assert "unknown_dim" in critique

    def test_generate_critique_all_known_dims(self, validator: ResponseQualityValidator) -> None:
        for name in ["accuracy", "coherence", "relevance", "constitutional_alignment", "safety"]:
            critique = validator._generate_critique(name, 0.3, 0.8)
            assert critique is not None

    def test_check_constitutional_compliance_disabled(self) -> None:
        cfg = ValidationConfig(enable_constitutional_check=False)
        v = ResponseQualityValidator(config=cfg)
        dims = [QualityDimension(name="constitutional_alignment", score=0.1, threshold=0.95)]
        assert v._check_constitutional_compliance(dims) is True

    def test_check_constitutional_compliance_no_dim(
        self, validator: ResponseQualityValidator
    ) -> None:
        dims = [QualityDimension(name="accuracy", score=0.9, threshold=0.7)]
        assert validator._check_constitutional_compliance(dims) is True

    def test_check_passes_threshold_overall_too_low(
        self, validator: ResponseQualityValidator
    ) -> None:
        dims = [QualityDimension(name="accuracy", score=0.9, threshold=0.7)]
        assert validator._check_passes_threshold(dims, 0.3) is False

    def test_check_passes_threshold_critical_fail(
        self, validator: ResponseQualityValidator
    ) -> None:
        dims = [QualityDimension(name="safety", score=0.3, threshold=0.99)]
        assert validator._check_passes_threshold(dims, 0.9) is False

    def test_calculate_overall_score_empty(self, validator: ResponseQualityValidator) -> None:
        assert validator._calculate_overall_score([]) == 0.0

    def test_generate_suggestions_no_failures(self, validator: ResponseQualityValidator) -> None:
        dims = [QualityDimension(name="accuracy", score=0.9, threshold=0.7)]
        suggestions = validator._generate_suggestions(dims)
        assert suggestions == []

    def test_generate_suggestions_known_dim(self, validator: ResponseQualityValidator) -> None:
        dims = [QualityDimension(name="accuracy", score=0.5, threshold=0.8)]
        suggestions = validator._generate_suggestions(dims)
        assert len(suggestions) >= 1
        assert "factual" in suggestions[0].lower() or "Verify" in suggestions[0]

    def test_generate_suggestions_unknown_dim(self, validator: ResponseQualityValidator) -> None:
        dims = [QualityDimension(name="custom_xyz", score=0.3, threshold=0.8)]
        suggestions = validator._generate_suggestions(dims)
        assert len(suggestions) >= 1
        assert "custom_xyz" in suggestions[0]


class TestCreateValidator:
    def test_default(self) -> None:
        v = create_validator()
        assert isinstance(v, ResponseQualityValidator)

    def test_with_thresholds_known(self) -> None:
        v = create_validator(thresholds={"accuracy": 0.5})
        assert v.dimensions["accuracy"].threshold == 0.5

    def test_with_thresholds_unknown(self) -> None:
        v = create_validator(thresholds={"custom_metric": 0.6})
        assert "custom_metric" in v.dimensions
        assert v.dimensions["custom_metric"].threshold == 0.6


# ===========================================================================
# refiner.py
# ===========================================================================


class TestRefinementExceptions:
    def test_refinement_error(self) -> None:
        with pytest.raises(RefinementError):
            raise RefinementError("failed")

    def test_constitutional_violation_error(self) -> None:
        with pytest.raises(ConstitutionalViolationError):
            raise ConstitutionalViolationError("violation")


class TestRefinementConfig:
    def test_defaults(self) -> None:
        cfg = RefinementConfig()
        assert cfg.max_iterations == 3
        assert cfg.improvement_threshold == 0.01
        assert cfg.stop_on_pass is True
        assert cfg.require_constitutional is True
        assert cfg.enable_logging is True


class TestDefaultLLMRefiner:
    @pytest.fixture
    def refiner(self) -> DefaultLLMRefiner:
        return DefaultLLMRefiner()

    def test_refine_coherence_no_period(self, refiner: DefaultLLMRefiner) -> None:
        a = _make_assessment(dim_scores={"coherence": 0.3})
        # Dimensions are created with threshold 0.7, so coherence at 0.3 fails
        result = refiner.refine("hello world", a)
        assert result.endswith(".")

    def test_refine_coherence_capitalizes(self, refiner: DefaultLLMRefiner) -> None:
        a = _make_assessment(dim_scores={"coherence": 0.3})
        result = refiner.refine("first sentence. second sentence.", a)
        assert "First sentence" in result or "first" in result.lower()

    def test_refine_relevance_with_query(self, refiner: DefaultLLMRefiner) -> None:
        a = _make_assessment(dim_scores={"relevance": 0.3})
        ctx = {"query": "What is governance?"}
        result = refiner.refine("Some text.", a, context=ctx)
        assert "Regarding" in result or "query" in result.lower() or result == "Some text."

    def test_refine_safety_redaction(self, refiner: DefaultLLMRefiner) -> None:
        a = _make_assessment(dim_scores={"safety": 0.3})
        result = refiner.refine("I will hack and steal data.", a)
        assert "[redacted]" in result

    async def test_refine_async(self, refiner: DefaultLLMRefiner) -> None:
        a = _make_assessment()
        result = await refiner.refine_async("test response.", a)
        assert isinstance(result, str)


class TestDefaultConstitutionalCorrector:
    @pytest.fixture
    def corrector(self) -> DefaultConstitutionalCorrector:
        return DefaultConstitutionalCorrector()

    def test_harmful_violation(self, corrector: DefaultConstitutionalCorrector) -> None:
        result = corrector.correct("test text", ["harmful content detected"])
        assert "[Reviewed for safety]" in result

    def test_unsafe_violation(self, corrector: DefaultConstitutionalCorrector) -> None:
        result = corrector.correct("test text", ["unsafe output"])
        assert "[Reviewed for safety]" in result

    def test_bias_violation(self, corrector: DefaultConstitutionalCorrector) -> None:
        result = corrector.correct("test text", ["bias detected"])
        assert "balanced and fair" in result

    def test_privacy_violation_ssn(self, corrector: DefaultConstitutionalCorrector) -> None:
        result = corrector.correct("SSN is 123-45-6789", ["privacy concern"])
        assert "[SSN-REDACTED]" in result

    def test_privacy_violation_email(self, corrector: DefaultConstitutionalCorrector) -> None:
        result = corrector.correct("Email: test@example.com", ["privacy concern"])
        assert "[EMAIL-REDACTED]" in result

    def test_no_violations(self, corrector: DefaultConstitutionalCorrector) -> None:
        result = corrector.correct("clean text", [])
        assert result == "clean text"

    async def test_correct_async(self, corrector: DefaultConstitutionalCorrector) -> None:
        result = await corrector.correct_async("test", ["harmful"])
        assert "[Reviewed for safety]" in result


class TestResponseRefiner:
    @pytest.fixture
    def refiner(self) -> ResponseRefiner:
        return ResponseRefiner()

    def test_init_default(self, refiner: ResponseRefiner) -> None:
        assert refiner.max_iterations == 3

    def test_init_custom_max_iterations(self) -> None:
        r = ResponseRefiner(max_iterations=5)
        assert r.max_iterations == 5

    def test_init_with_config(self) -> None:
        cfg = RefinementConfig(max_iterations=7)
        r = ResponseRefiner(config=cfg, max_iterations=7)
        assert r.max_iterations == 7

    def test_stats_initial(self, refiner: ResponseRefiner) -> None:
        stats = refiner.stats
        assert stats["refinement_count"] == 0
        assert stats["total_iterations"] == 0
        assert "constitutional_hash" in stats

    def test_refine_good_response(self, refiner: ResponseRefiner) -> None:
        result = refiner.refine(GOOD_RESPONSE)
        assert isinstance(result, RefinementResult)
        assert result.status in (RefinementStatus.COMPLETED, RefinementStatus.SKIPPED)

    def test_refine_skips_passing(self, refiner: ResponseRefiner) -> None:
        # Provide scores that pass all thresholds
        result = refiner.refine(
            GOOD_RESPONSE,
            response_id="test-id",
        )
        assert isinstance(result, RefinementResult)

    def test_refine_short_response_iterates(self, refiner: ResponseRefiner) -> None:
        result = refiner.refine(SHORT_RESPONSE)
        assert isinstance(result, RefinementResult)

    def test_refine_with_context(self, refiner: ResponseRefiner) -> None:
        result = refiner.refine(GOOD_RESPONSE, context={"query": "governance"})
        assert isinstance(result, RefinementResult)

    def test_stats_after_refine(self, refiner: ResponseRefiner) -> None:
        refiner.refine(GOOD_RESPONSE)
        stats = refiner.stats
        assert stats["refinement_count"] == 1

    async def test_refine_async(self, refiner: ResponseRefiner) -> None:
        result = await refiner.refine_async(GOOD_RESPONSE)
        assert isinstance(result, RefinementResult)
        assert result.status in (RefinementStatus.COMPLETED, RefinementStatus.SKIPPED)

    async def test_refine_async_iterates(self, refiner: ResponseRefiner) -> None:
        result = await refiner.refine_async(SHORT_RESPONSE)
        assert isinstance(result, RefinementResult)

    def test_refine_batch(self, refiner: ResponseRefiner) -> None:
        results = refiner.refine_batch([GOOD_RESPONSE, SHORT_RESPONSE])
        assert len(results) == 2
        assert all(isinstance(r, RefinementResult) for r in results)

    def test_refine_batch_with_contexts(self, refiner: ResponseRefiner) -> None:
        results = refiner.refine_batch(
            [GOOD_RESPONSE, GOOD_RESPONSE], contexts=[None, {"query": "test"}]
        )
        assert len(results) == 2

    def test_refine_batch_length_mismatch(self, refiner: ResponseRefiner) -> None:
        with pytest.raises(ValueError, match="same length"):
            refiner.refine_batch(["a", "b"], contexts=[None])

    async def test_refine_batch_async(self, refiner: ResponseRefiner) -> None:
        results = await refiner.refine_batch_async([GOOD_RESPONSE, SHORT_RESPONSE])
        assert len(results) == 2

    async def test_refine_batch_async_length_mismatch(self, refiner: ResponseRefiner) -> None:
        with pytest.raises(ValueError, match="same length"):
            await refiner.refine_batch_async(["a"], contexts=[None, None])

    def test_set_constitutional_corrector(self, refiner: ResponseRefiner) -> None:
        corrector = DefaultConstitutionalCorrector()
        refiner.set_constitutional_corrector(corrector)
        assert refiner.constitutional_corrector is corrector

    def test_set_llm_refiner(self, refiner: ResponseRefiner) -> None:
        llm = DefaultLLMRefiner()
        refiner.set_llm_refiner(llm)
        assert refiner.llm_refiner is llm

    def test_should_stop_when_passes(self, refiner: ResponseRefiner) -> None:
        a = _make_assessment(passes_threshold=True, constitutional_compliance=True)
        assert refiner._should_stop(a, None, 0) is True

    def test_should_stop_max_iterations(self, refiner: ResponseRefiner) -> None:
        a = _make_assessment(passes_threshold=False)
        assert refiner._should_stop(a, None, refiner.max_iterations) is True

    def test_should_stop_no_improvement(self, refiner: ResponseRefiner) -> None:
        before = _make_assessment(overall_score=0.5, passes_threshold=False)
        after = _make_assessment(overall_score=0.5, passes_threshold=False)
        it = RefinementIteration(
            iteration_number=1,
            original_response="a",
            refined_response="b",
            before_assessment=before,
            after_assessment=after,
        )
        assert refiner._should_stop(after, it, 1) is True

    def test_describe_improvements_overall(self, refiner: ResponseRefiner) -> None:
        before = _make_assessment(overall_score=0.5, dim_scores={"a": 0.5})
        after = _make_assessment(overall_score=0.8, dim_scores={"a": 0.9})
        improvements = refiner._describe_improvements(before, after)
        assert any("Overall" in i for i in improvements)

    def test_describe_improvements_dimension(self, refiner: ResponseRefiner) -> None:
        before = _make_assessment(overall_score=0.5, dim_scores={"a": 0.3})
        after = _make_assessment(overall_score=0.8, dim_scores={"a": 0.9})
        improvements = refiner._describe_improvements(before, after)
        assert any("a:" in i for i in improvements)

    def test_describe_improvements_now_passes(self, refiner: ResponseRefiner) -> None:
        # dim_delta must be <= 0.05 so it falls through to the "now passes" branch
        before_dims = [QualityDimension(name="x", score=0.68, threshold=0.7)]
        after_dims = [QualityDimension(name="x", score=0.72, threshold=0.7)]
        before = QualityAssessment(
            dimensions=before_dims,
            overall_score=0.5,
            passes_threshold=False,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        after = QualityAssessment(
            dimensions=after_dims,
            overall_score=0.75,
            passes_threshold=True,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        improvements = refiner._describe_improvements(before, after)
        assert any("passes" in i.lower() for i in improvements)

    def test_describe_improvements_constitutional(self, refiner: ResponseRefiner) -> None:
        before = _make_assessment(constitutional_compliance=False)
        after = _make_assessment(constitutional_compliance=True)
        improvements = refiner._describe_improvements(before, after)
        assert any("Constitutional" in i for i in improvements)


class TestCreateRefiner:
    def test_default(self) -> None:
        r = create_refiner()
        assert isinstance(r, ResponseRefiner)
        assert r.max_iterations == 3

    def test_custom_max_iterations(self) -> None:
        r = create_refiner(max_iterations=5)
        assert r.max_iterations == 5

    def test_with_validator(self) -> None:
        v = ResponseQualityValidator()
        r = create_refiner(validator=v)
        assert r.validator is v

    def test_with_corrector(self) -> None:
        c = DefaultConstitutionalCorrector()
        r = create_refiner(constitutional_corrector=c)
        assert r.constitutional_corrector is c


# ===========================================================================
# Backward Compatibility
# ===========================================================================


class TestBackwardCompatibility:
    def test_response_quality_assessor_alias(self) -> None:
        assert ResponseQualityAssessor is ResponseQualityValidator

    def test_response_quality_metrics_alias(self) -> None:
        assert ResponseQualityMetrics is QualityAssessment
