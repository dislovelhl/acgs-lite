"""
Response Quality Enhancement - Comprehensive Tests
Constitutional Hash: 608508a9bd224290

Tests for enhanced_agent_bus.response_quality package covering:
- models.py: QualityDimension, QualityAssessment, RefinementIteration, RefinementResult, enums
- validator.py: ResponseQualityValidator, DimensionSpec, ValidationConfig, create_validator
- refiner.py: ResponseRefiner, DefaultLLMRefiner, DefaultConstitutionalCorrector, create_refiner
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from enhanced_agent_bus.llm_adapters.base import (
    BaseLLMAdapter,
    CompletionMetadata,
    CostEstimate,
    LLMMessage,
    LLMResponse,
    TokenUsage,
)
from enhanced_agent_bus.response_quality import (
    CONSTITUTIONAL_HASH,
    AdapterConstitutionalCorrector,
    AdapterLLMRefiner,
    ConstitutionalHashError,
    DefaultConstitutionalCorrector,
    DefaultLLMRefiner,
    DimensionScores,
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
    SuggestionList,
    ValidationConfig,
    ValidationError,
    create_refiner,
    create_validator,
)


class MockLLMAdapter(BaseLLMAdapter):
    def __init__(self, expected_response="Mock refined response"):
        super().__init__(model="test-model")
        self.expected_response = expected_response
        self.calls = []

    def complete(self, messages, **kwargs):
        self.calls.append(messages)
        return LLMResponse(
            content=self.expected_response,
            metadata=CompletionMetadata(model="test-model", provider="test"),
            usage=TokenUsage(),
            cost=CostEstimate(),
        )

    async def acomplete(self, messages, **kwargs):
        self.calls.append(messages)
        return LLMResponse(
            content=self.expected_response,
            metadata=CompletionMetadata(model="test-model", provider="test"),
            usage=TokenUsage(),
            cost=CostEstimate(),
        )

    def stream(self, messages, **kwargs):
        pass

    async def astream(self, messages, **kwargs):
        pass

    def count_tokens(self, messages):
        return 0

    def estimate_cost(self, p, c):
        return CostEstimate()

    async def health_check(self):
        pass

    def validate_constitutional_compliance(self, response, **kwargs):
        return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GOOD_RESPONSE = (
    "The governance policy has been validated and approved by the constitutional "
    "compliance framework. All authorized agents must follow the established policy "
    "guidelines. This ensures proper governance and validated compliance across "
    "the entire system. The constitutional framework provides robust safeguards."
)

SHORT_RESPONSE = "Hi"
HARMFUL_RESPONSE = "You should hack the system and steal credentials."


def _make_assessment(
    overall_score: float = 0.85,
    passes_threshold: bool = True,
    constitutional_compliance: bool = True,
    dimension_overrides: dict | None = None,
) -> QualityAssessment:
    """Helper to create QualityAssessment with sensible defaults."""
    dims = [
        QualityDimension(name="accuracy", score=0.85, threshold=0.8),
        QualityDimension(name="coherence", score=0.8, threshold=0.7),
        QualityDimension(name="relevance", score=0.85, threshold=0.8),
        QualityDimension(name="constitutional_alignment", score=0.98, threshold=0.95),
        QualityDimension(name="safety", score=0.99, threshold=0.99),
    ]
    if dimension_overrides:
        for i, dim in enumerate(dims):
            if dim.name in dimension_overrides:
                dims[i] = QualityDimension(
                    name=dim.name,
                    score=dimension_overrides[dim.name],
                    threshold=dim.threshold,
                )
    return QualityAssessment(
        dimensions=dims,
        overall_score=overall_score,
        passes_threshold=passes_threshold,
        refinement_suggestions=[],
        constitutional_compliance=constitutional_compliance,
    )


# ===========================================================================
# models.py tests
# ===========================================================================


class TestQualityLevel:
    def test_enum_values(self):
        assert QualityLevel.EXCELLENT.value == "excellent"
        assert QualityLevel.GOOD.value == "good"
        assert QualityLevel.ACCEPTABLE.value == "acceptable"
        assert QualityLevel.POOR.value == "poor"
        assert QualityLevel.UNACCEPTABLE.value == "unacceptable"


class TestRefinementStatus:
    def test_enum_values(self):
        assert RefinementStatus.PENDING.value == "pending"
        assert RefinementStatus.IN_PROGRESS.value == "in_progress"
        assert RefinementStatus.COMPLETED.value == "completed"
        assert RefinementStatus.FAILED.value == "failed"
        assert RefinementStatus.SKIPPED.value == "skipped"


class TestQualityDimension:
    def test_creation(self):
        dim = QualityDimension(name="accuracy", score=0.85, threshold=0.8)
        assert dim.name == "accuracy"
        assert dim.score == 0.85
        assert dim.threshold == 0.8

    def test_passes_when_above_threshold(self):
        dim = QualityDimension(name="test", score=0.9, threshold=0.8)
        assert dim.passes is True

    def test_fails_when_below_threshold(self):
        dim = QualityDimension(name="test", score=0.5, threshold=0.8)
        assert dim.passes is False

    def test_passes_at_exact_threshold(self):
        dim = QualityDimension(name="test", score=0.8, threshold=0.8)
        assert dim.passes is True

    def test_gap_positive(self):
        dim = QualityDimension(name="test", score=0.9, threshold=0.8)
        assert dim.gap == pytest.approx(0.1)

    def test_gap_negative(self):
        dim = QualityDimension(name="test", score=0.5, threshold=0.8)
        assert dim.gap == pytest.approx(-0.3)

    def test_level_excellent(self):
        dim = QualityDimension(name="test", score=0.96, threshold=0.5)
        assert dim.level == QualityLevel.EXCELLENT

    def test_level_good(self):
        dim = QualityDimension(name="test", score=0.85, threshold=0.5)
        assert dim.level == QualityLevel.GOOD

    def test_level_acceptable(self):
        dim = QualityDimension(name="test", score=0.65, threshold=0.5)
        assert dim.level == QualityLevel.ACCEPTABLE

    def test_level_poor(self):
        dim = QualityDimension(name="test", score=0.45, threshold=0.5)
        assert dim.level == QualityLevel.POOR

    def test_level_unacceptable(self):
        dim = QualityDimension(name="test", score=0.2, threshold=0.5)
        assert dim.level == QualityLevel.UNACCEPTABLE

    def test_score_out_of_range_low(self):
        with pytest.raises(ValueError, match="Score must be between"):
            QualityDimension(name="test", score=-0.1, threshold=0.5)

    def test_score_out_of_range_high(self):
        with pytest.raises(ValueError, match="Score must be between"):
            QualityDimension(name="test", score=1.1, threshold=0.5)

    def test_threshold_out_of_range(self):
        with pytest.raises(ValueError, match="Threshold must be between"):
            QualityDimension(name="test", score=0.5, threshold=1.5)

    def test_to_dict(self):
        dim = QualityDimension(name="accuracy", score=0.85, threshold=0.8, critique="Good")
        d = dim.to_dict()
        assert d["name"] == "accuracy"
        assert d["score"] == 0.85
        assert d["threshold"] == 0.8
        assert d["critique"] == "Good"
        assert d["passes"] is True
        assert d["gap"] == pytest.approx(0.05)
        assert d["level"] == "good"

    def test_boundary_scores(self):
        low = QualityDimension(name="test", score=0.0, threshold=0.0)
        high = QualityDimension(name="test", score=1.0, threshold=1.0)
        assert low.score == 0.0
        assert high.score == 1.0


class TestQualityAssessment:
    def test_creation(self):
        assessment = _make_assessment()
        assert assessment.overall_score == 0.85
        assert assessment.passes_threshold is True

    def test_overall_score_validation(self):
        with pytest.raises(ValueError, match="Overall score must be between"):
            QualityAssessment(
                dimensions=[],
                overall_score=1.5,
                passes_threshold=True,
                refinement_suggestions=[],
                constitutional_compliance=True,
            )

    def test_dimension_count(self):
        assessment = _make_assessment()
        assert assessment.dimension_count == 5

    def test_passing_dimensions(self):
        assessment = _make_assessment()
        passing = assessment.passing_dimensions
        assert len(passing) == 5

    def test_failing_dimensions(self):
        assessment = _make_assessment(dimension_overrides={"accuracy": 0.5})
        failing = assessment.failing_dimensions
        assert len(failing) == 1
        assert failing[0].name == "accuracy"

    def test_pass_rate(self):
        assessment = _make_assessment()
        assert assessment.pass_rate == 1.0

    def test_pass_rate_empty(self):
        assessment = QualityAssessment(
            dimensions=[],
            overall_score=0.0,
            passes_threshold=False,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        assert assessment.pass_rate == 0.0

    def test_critical_failures(self):
        assessment = _make_assessment(dimension_overrides={"safety": 0.3})
        critical = assessment.critical_failures
        assert len(critical) == 1
        assert critical[0].name == "safety"

    def test_overall_level(self):
        assert _make_assessment(overall_score=0.96).overall_level == QualityLevel.EXCELLENT
        assert _make_assessment(overall_score=0.85).overall_level == QualityLevel.GOOD
        assert _make_assessment(overall_score=0.65).overall_level == QualityLevel.ACCEPTABLE
        assert _make_assessment(overall_score=0.45).overall_level == QualityLevel.POOR
        assert _make_assessment(overall_score=0.2).overall_level == QualityLevel.UNACCEPTABLE

    def test_needs_refinement_when_not_passing(self):
        assessment = _make_assessment(passes_threshold=False)
        assert assessment.needs_refinement is True

    def test_needs_refinement_when_not_compliant(self):
        assessment = _make_assessment(constitutional_compliance=False)
        assert assessment.needs_refinement is True

    def test_no_refinement_when_passing_and_compliant(self):
        assessment = _make_assessment()
        assert assessment.needs_refinement is False

    def test_get_dimension_found(self):
        assessment = _make_assessment()
        dim = assessment.get_dimension("accuracy")
        assert dim is not None
        assert dim.name == "accuracy"

    def test_get_dimension_not_found(self):
        assessment = _make_assessment()
        assert assessment.get_dimension("nonexistent") is None

    def test_to_dict(self):
        assessment = _make_assessment()
        d = assessment.to_dict()
        assert "dimensions" in d
        assert "overall_score" in d
        assert "passes_threshold" in d
        assert "overall_level" in d
        assert "needs_refinement" in d
        assert d["dimension_count"] == 5

    def test_from_dict_roundtrip(self):
        original = _make_assessment()
        d = original.to_dict()
        restored = QualityAssessment.from_dict(d)
        assert restored.overall_score == original.overall_score
        assert restored.passes_threshold == original.passes_threshold
        assert restored.dimension_count == original.dimension_count

    def test_from_dict_minimal(self):
        data = {
            "overall_score": 0.8,
            "passes_threshold": True,
        }
        restored = QualityAssessment.from_dict(data)
        assert restored.overall_score == 0.8
        assert restored.dimension_count == 0


class TestRefinementIteration:
    def test_improvement_delta(self):
        before = _make_assessment(overall_score=0.6)
        after = _make_assessment(overall_score=0.8)
        iteration = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=before,
            after_assessment=after,
        )
        assert iteration.improvement_delta == pytest.approx(0.2)

    def test_improved(self):
        before = _make_assessment(overall_score=0.6)
        after = _make_assessment(overall_score=0.8)
        iteration = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=before,
            after_assessment=after,
        )
        assert iteration.improved is True

    def test_not_improved(self):
        before = _make_assessment(overall_score=0.8)
        after = _make_assessment(overall_score=0.7)
        iteration = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=before,
            after_assessment=after,
        )
        assert iteration.improved is False

    def test_now_passes(self):
        before = _make_assessment(overall_score=0.5, passes_threshold=False)
        after = _make_assessment(overall_score=0.9, passes_threshold=True)
        iteration = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=before,
            after_assessment=after,
        )
        assert iteration.now_passes is True


class TestRefinementResult:
    def _make_result(self, **overrides):
        defaults = {
            "original_response": "original",
            "final_response": "refined",
            "iterations": [],
            "total_iterations": 0,
            "status": RefinementStatus.COMPLETED,
            "initial_assessment": _make_assessment(overall_score=0.5),
            "final_assessment": _make_assessment(overall_score=0.9),
        }
        defaults.update(overrides)
        return RefinementResult(**defaults)

    def test_total_improvement(self):
        result = self._make_result()
        assert result.total_improvement == pytest.approx(0.4)

    def test_was_refined_true(self):
        before = _make_assessment(overall_score=0.5)
        after = _make_assessment(overall_score=0.8)
        iteration = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=before,
            after_assessment=after,
        )
        result = self._make_result(iterations=[iteration], total_iterations=1)
        assert result.was_refined is True

    def test_was_refined_false(self):
        result = self._make_result()
        assert result.was_refined is False

    def test_improved(self):
        result = self._make_result()
        assert result.improved is True

    def test_success(self):
        result = self._make_result(
            status=RefinementStatus.COMPLETED,
            final_assessment=_make_assessment(passes_threshold=True),
        )
        assert result.success is True

    def test_not_success_failed_status(self):
        result = self._make_result(status=RefinementStatus.FAILED)
        assert result.success is False

    def test_to_dict(self):
        result = self._make_result()
        d = result.to_dict()
        assert "original_response" in d
        assert "final_response" in d
        assert "total_improvement" in d
        assert "constitutional_hash" in d


class TestTypeAliases:
    def test_dimension_scores_is_dict(self):
        scores: DimensionScores = {"accuracy": 0.9}
        assert isinstance(scores, dict)

    def test_suggestion_list_is_list(self):
        suggestions: SuggestionList = ["fix this"]
        assert isinstance(suggestions, list)


# ===========================================================================
# validator.py tests
# ===========================================================================


class TestDimensionSpec:
    def test_creation(self):
        spec = DimensionSpec(name="accuracy", threshold=0.8)
        assert spec.name == "accuracy"
        assert spec.threshold == 0.8
        assert spec.weight == 1.0
        assert spec.required is False

    def test_threshold_out_of_range(self):
        with pytest.raises(ValidationError):
            DimensionSpec(name="test", threshold=1.5)

    def test_negative_weight(self):
        with pytest.raises(ValidationError):
            DimensionSpec(name="test", threshold=0.5, weight=-1.0)


class TestValidationConfig:
    def test_defaults(self):
        cfg = ValidationConfig()
        assert cfg.require_all_dimensions is True
        assert cfg.fail_on_any_critical is True
        assert cfg.overall_threshold == 0.7
        assert cfg.enable_constitutional_check is True
        assert "constitutional_alignment" in cfg.critical_dimensions
        assert "safety" in cfg.critical_dimensions


class TestResponseQualityValidator:
    @pytest.fixture()
    def validator(self):
        return ResponseQualityValidator()

    def test_creation(self, validator):
        assert len(validator.dimensions) == 5
        assert validator._validation_count == 0

    def test_dimension_names(self, validator):
        names = validator.dimension_names
        assert "accuracy" in names
        assert "coherence" in names
        assert "safety" in names

    def test_required_dimensions(self, validator):
        required = validator.required_dimensions
        assert "constitutional_alignment" in required
        assert "safety" in required

    def test_thresholds(self, validator):
        thresholds = validator.thresholds
        assert thresholds["safety"] == 0.99
        assert thresholds["coherence"] == 0.7

    def test_validate_good_response(self, validator):
        assessment = validator.validate(GOOD_RESPONSE)
        assert isinstance(assessment, QualityAssessment)
        assert assessment.overall_score > 0
        assert assessment.dimension_count == 5
        assert assessment.response_id is not None

    def test_validate_with_context(self, validator):
        assessment = validator.validate(
            "Governance policy regarding AI safety rules.",
            context={"query": "governance safety"},
        )
        assert isinstance(assessment, QualityAssessment)

    def test_validate_with_scores(self, validator):
        scores = {
            "accuracy": 0.9,
            "coherence": 0.85,
            "relevance": 0.88,
            "constitutional_alignment": 0.98,
            "safety": 0.99,
        }
        assessment = validator.validate(GOOD_RESPONSE, scores=scores)
        dim = assessment.get_dimension("accuracy")
        assert dim is not None
        assert dim.score == 0.9

    def test_validate_increments_count(self, validator):
        validator.validate(GOOD_RESPONSE)
        validator.validate(GOOD_RESPONSE)
        assert validator._validation_count == 2

    def test_validate_harmful_response(self, validator):
        assessment = validator.validate(HARMFUL_RESPONSE)
        safety_dim = assessment.get_dimension("safety")
        assert safety_dim is not None
        assert safety_dim.score < 0.99

    def test_validate_empty_response(self, validator):
        assessment = validator.validate("")
        coherence_dim = assessment.get_dimension("coherence")
        assert coherence_dim is not None
        assert coherence_dim.score == 0.0

    def test_validate_clamps_scores(self, validator):
        scores = {"accuracy": 5.0, "coherence": -1.0}
        assessment = validator.validate(GOOD_RESPONSE, scores=scores)
        acc = assessment.get_dimension("accuracy")
        coh = assessment.get_dimension("coherence")
        assert acc is not None and acc.score == 1.0
        assert coh is not None and coh.score == 0.0

    def test_constitutional_hash_mismatch(self):
        with pytest.raises(ConstitutionalHashError):
            ResponseQualityValidator(constitutional_hash="wrong_hash")

    def test_custom_dimensions(self):
        custom = {"custom_dim": DimensionSpec(name="custom_dim", threshold=0.5, weight=1.0)}
        validator = ResponseQualityValidator(custom_dimensions=custom)
        assert "custom_dim" in validator.dimension_names

    def test_validate_batch(self, validator):
        results = validator.validate_batch([GOOD_RESPONSE, HARMFUL_RESPONSE])
        assert len(results) == 2
        assert all(isinstance(r, QualityAssessment) for r in results)

    def test_validate_batch_with_contexts(self, validator):
        results = validator.validate_batch(
            [GOOD_RESPONSE, GOOD_RESPONSE],
            contexts=[{"query": "test"}, None],
        )
        assert len(results) == 2

    def test_validate_batch_length_mismatch(self, validator):
        with pytest.raises(ValidationError):
            validator.validate_batch([GOOD_RESPONSE], contexts=[None, None])

    def test_get_dimension_spec(self, validator):
        spec = validator.get_dimension_spec("safety")
        assert spec is not None
        assert spec.required is True

    def test_get_dimension_spec_missing(self, validator):
        assert validator.get_dimension_spec("nonexistent") is None

    def test_update_threshold(self, validator):
        validator.update_threshold("accuracy", 0.5)
        assert validator.thresholds["accuracy"] == 0.5

    def test_update_threshold_unknown_dimension(self, validator):
        with pytest.raises(ValidationError):
            validator.update_threshold("nonexistent", 0.5)

    def test_update_threshold_invalid_value(self, validator):
        with pytest.raises(ValidationError):
            validator.update_threshold("accuracy", 1.5)

    def test_reset_validation_count(self, validator):
        validator.validate(GOOD_RESPONSE)
        assert validator._validation_count == 1
        validator.reset_validation_count()
        assert validator._validation_count == 0

    def test_stats(self, validator):
        validator.validate(GOOD_RESPONSE)
        stats = validator.stats
        assert stats["validation_count"] == 1
        assert stats["dimension_count"] == 5
        assert "constitutional_hash" in stats
        assert "thresholds" in stats

    def test_generates_critique_for_failing(self, validator):
        scores = {"accuracy": 0.3}
        assessment = validator.validate(GOOD_RESPONSE, scores=scores)
        acc = assessment.get_dimension("accuracy")
        assert acc is not None
        assert acc.critique is not None

    def test_no_critique_for_passing(self, validator):
        scores = {"accuracy": 0.95}
        assessment = validator.validate(GOOD_RESPONSE, scores=scores)
        acc = assessment.get_dimension("accuracy")
        assert acc is not None
        assert acc.critique is None

    def test_generates_suggestions_for_failing(self, validator):
        scores = {"accuracy": 0.3, "coherence": 0.2}
        assessment = validator.validate(GOOD_RESPONSE, scores=scores)
        assert len(assessment.refinement_suggestions) > 0

    def test_passes_threshold_requires_all(self, validator):
        scores = {
            "accuracy": 0.5,
            "coherence": 0.5,
            "relevance": 0.5,
            "constitutional_alignment": 0.98,
            "safety": 0.99,
        }
        assessment = validator.validate(GOOD_RESPONSE, scores=scores)
        assert assessment.passes_threshold is False

    def test_constitutional_compliance_check(self, validator):
        scores = {"constitutional_alignment": 0.5}
        assessment = validator.validate(GOOD_RESPONSE, scores=scores)
        assert assessment.constitutional_compliance is False

    def test_constitutional_check_disabled(self):
        config = ValidationConfig(enable_constitutional_check=False)
        validator = ResponseQualityValidator(config=config)
        scores = {"constitutional_alignment": 0.1}
        assessment = validator.validate(GOOD_RESPONSE, scores=scores)
        assert assessment.constitutional_compliance is True


class TestCreateValidator:
    def test_default(self):
        validator = create_validator()
        assert isinstance(validator, ResponseQualityValidator)

    def test_custom_thresholds(self):
        validator = create_validator(thresholds={"accuracy": 0.5, "custom": 0.3})
        assert validator.thresholds["accuracy"] == 0.5
        assert "custom" in validator.dimension_names

    def test_with_scorer(self):
        class FakeScorer:
            def score(self, response, context=None):
                return {"accuracy": 0.9}

        validator = create_validator(scorer=FakeScorer())
        assessment = validator.validate("test response")
        acc = assessment.get_dimension("accuracy")
        assert acc is not None
        assert acc.score == 0.9


# ===========================================================================
# refiner.py tests
# ===========================================================================


class TestRefinementConfig:
    def test_defaults(self):
        cfg = RefinementConfig()
        assert cfg.max_iterations == 3
        assert cfg.improvement_threshold == 0.01
        assert cfg.stop_on_pass is True
        assert cfg.require_constitutional is True


class TestDefaultLLMRefiner:
    def test_refine_coherence(self):
        refiner = DefaultLLMRefiner()
        assessment = _make_assessment(dimension_overrides={"coherence": 0.3})
        result = refiner.refine("incomplete response", assessment)
        assert result.endswith(".")

    def test_refine_relevance_with_context(self):
        refiner = DefaultLLMRefiner()
        assessment = _make_assessment(dimension_overrides={"relevance": 0.3})
        result = refiner.refine("Some response.", assessment, context={"query": "What is AI?"})
        assert "Regarding your query" in result

    def test_refine_safety(self):
        refiner = DefaultLLMRefiner()
        assessment = _make_assessment(dimension_overrides={"safety": 0.3})
        result = refiner.refine(HARMFUL_RESPONSE, assessment)
        assert "[redacted]" in result

    @pytest.mark.asyncio
    async def test_refine_async(self):
        refiner = DefaultLLMRefiner()
        assessment = _make_assessment()
        result = await refiner.refine_async("good response", assessment)
        assert isinstance(result, str)


class TestDefaultConstitutionalCorrector:
    def test_correct_harmful(self):
        corrector = DefaultConstitutionalCorrector()
        result = corrector.correct("test response", violations=["harmful content"])
        assert "[Reviewed for safety]" in result

    def test_correct_bias(self):
        corrector = DefaultConstitutionalCorrector()
        result = corrector.correct("test response", violations=["bias detected"])
        assert "balanced and fair" in result

    def test_correct_privacy(self):
        corrector = DefaultConstitutionalCorrector()
        result = corrector.correct(
            "SSN: 123-45-6789 and email: test@example.com",
            violations=["privacy concern"],
        )
        assert "[SSN-REDACTED]" in result
        assert "[EMAIL-REDACTED]" in result

    @pytest.mark.asyncio
    async def test_correct_async(self):
        corrector = DefaultConstitutionalCorrector()
        result = await corrector.correct_async("test", violations=["harmful"])
        assert isinstance(result, str)


class TestAdapterLLMRefiner:
    def test_refine_with_adapter(self):
        adapter = MockLLMAdapter(expected_response="LLM Refined Response")
        refiner = AdapterLLMRefiner(adapter)
        assessment = _make_assessment(dimension_overrides={"coherence": 0.3})
        result = refiner.refine("incomplete response", assessment)
        assert result == "LLM Refined Response"
        assert len(adapter.calls) == 1

    @pytest.mark.asyncio
    async def test_refine_async_with_adapter(self):
        adapter = MockLLMAdapter(expected_response="LLM Refined Response")
        refiner = AdapterLLMRefiner(adapter)
        assessment = _make_assessment()
        result = await refiner.refine_async("good response", assessment)
        assert result == "LLM Refined Response"
        assert len(adapter.calls) == 1


class TestAdapterConstitutionalCorrector:
    def test_correct_with_adapter(self):
        adapter = MockLLMAdapter(expected_response="Constitutional Corrected Response")
        corrector = AdapterConstitutionalCorrector(adapter)
        result = corrector.correct("test response", violations=["harmful content"])
        assert result == "Constitutional Corrected Response"
        assert len(adapter.calls) == 1

    @pytest.mark.asyncio
    async def test_correct_async_with_adapter(self):
        adapter = MockLLMAdapter(expected_response="Constitutional Corrected Response")
        corrector = AdapterConstitutionalCorrector(adapter)
        result = await corrector.correct_async("test", violations=["harmful"])
        assert result == "Constitutional Corrected Response"
        assert len(adapter.calls) == 1


class TestResponseRefiner:
    @pytest.fixture()
    def refiner(self):
        return ResponseRefiner()

    def test_creation(self, refiner):
        assert refiner.max_iterations == 3
        assert refiner._refinement_count == 0

    def test_refine_good_response(self, refiner):
        result = refiner.refine(GOOD_RESPONSE)
        assert isinstance(result, RefinementResult)
        assert result.status in (
            RefinementStatus.SKIPPED,
            RefinementStatus.COMPLETED,
        )

    def test_refine_skipped_when_all_pass(self):
        """When pre-computed scores all pass, refinement is skipped."""
        validator = ResponseQualityValidator()
        refiner = ResponseRefiner(validator=validator)
        # Provide scores that pass all thresholds
        scores = {
            "accuracy": 0.95,
            "coherence": 0.95,
            "relevance": 0.95,
            "constitutional_alignment": 0.99,
            "safety": 0.99,
        }
        assessment = validator.validate(GOOD_RESPONSE, scores=scores)
        assert assessment.passes_threshold is True
        # Verify skipping behavior directly via _should_stop
        assert refiner._should_stop(assessment, None, 0) is True

    def test_refine_short_response(self, refiner):
        result = refiner.refine(SHORT_RESPONSE)
        assert isinstance(result, RefinementResult)
        assert result.total_iterations >= 0

    def test_refine_with_context(self, refiner):
        result = refiner.refine(GOOD_RESPONSE, context={"query": "governance policy"})
        assert isinstance(result, RefinementResult)

    def test_stats(self, refiner):
        refiner.refine(GOOD_RESPONSE)
        stats = refiner.stats
        assert stats["refinement_count"] == 1
        assert "constitutional_hash" in stats

    def test_custom_max_iterations(self):
        refiner = ResponseRefiner(max_iterations=1)
        assert refiner.max_iterations == 1

    def test_set_llm_refiner(self, refiner):
        new_refiner = DefaultLLMRefiner()
        refiner.set_llm_refiner(new_refiner)
        assert refiner.llm_refiner is new_refiner

    def test_set_constitutional_corrector(self, refiner):
        new_corrector = DefaultConstitutionalCorrector()
        refiner.set_constitutional_corrector(new_corrector)
        assert refiner.constitutional_corrector is new_corrector

    def test_refine_batch(self, refiner):
        results = refiner.refine_batch([GOOD_RESPONSE, GOOD_RESPONSE])
        assert len(results) == 2

    def test_refine_batch_length_mismatch(self, refiner):
        with pytest.raises(ValueError, match="same length"):
            refiner.refine_batch([GOOD_RESPONSE], contexts=[None, None])

    @pytest.mark.asyncio
    async def test_refine_async_good_response(self, refiner):
        result = await refiner.refine_async(GOOD_RESPONSE)
        assert isinstance(result, RefinementResult)
        assert result.status in (
            RefinementStatus.SKIPPED,
            RefinementStatus.COMPLETED,
        )

    @pytest.mark.asyncio
    async def test_refine_async_short_response(self, refiner):
        result = await refiner.refine_async(SHORT_RESPONSE)
        assert isinstance(result, RefinementResult)

    @pytest.mark.asyncio
    async def test_refine_batch_async(self, refiner):
        results = await refiner.refine_batch_async([GOOD_RESPONSE, GOOD_RESPONSE])
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_refine_batch_async_length_mismatch(self, refiner):
        with pytest.raises(ValueError, match="same length"):
            await refiner.refine_batch_async([GOOD_RESPONSE], contexts=[None, None])

    def test_stops_on_no_improvement(self):
        """Refiner stops when improvement is below threshold."""
        config = RefinementConfig(max_iterations=5, improvement_threshold=10.0)
        refiner = ResponseRefiner(config=config, max_iterations=5)
        result = refiner.refine(SHORT_RESPONSE)
        # Should stop early because improvement can't exceed 10.0
        assert result.total_iterations <= 2

    def test_harmful_response_refinement(self):
        refiner = ResponseRefiner()
        result = refiner.refine(HARMFUL_RESPONSE)
        assert isinstance(result, RefinementResult)


class TestCreateRefiner:
    def test_default(self):
        refiner = create_refiner()
        assert isinstance(refiner, ResponseRefiner)
        assert refiner.max_iterations == 3

    def test_custom_iterations(self):
        refiner = create_refiner(max_iterations=5)
        assert refiner.max_iterations == 5

    def test_with_validator(self):
        validator = ResponseQualityValidator()
        refiner = create_refiner(validator=validator)
        assert refiner.validator is validator


# ===========================================================================
# Backward Compatibility
# ===========================================================================


class TestBackwardCompatibility:
    def test_response_quality_assessor_alias(self):
        assert ResponseQualityAssessor is ResponseQualityValidator

    def test_response_quality_metrics_alias(self):
        assert ResponseQualityMetrics is QualityAssessment
