"""
Comprehensive coverage tests for enhanced_agent_bus modules:
- response_quality/ (models, validator, refiner)
- ai_assistant/retrieval.py (policy, semantic, hybrid retrieval)
- workflows/graph_workflow.py (state graph, governance graph)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# retrieval imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.ai_assistant.retrieval import (
    BaseRetriever,
    HybridRetriever,
    KnowledgeRetriever,
    RetrievalResult,
    SemanticRetriever,
    get_knowledge_retriever,
)

# ---------------------------------------------------------------------------
# response_quality imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.response_quality import (
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
    ResponseQualityValidator,
    ResponseRefiner,
    SuggestionList,
    ValidationConfig,
    create_refiner,
    create_validator,
)

# ---------------------------------------------------------------------------
# graph_workflow imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.workflows.graph_workflow import (
    GovernanceGraph,
    GraphEdge,
    GraphNode,
    NodeStatus,
    StateGraph,
)

# ============================================================================
# response_quality/models.py — QualityDimension
# ============================================================================


class TestQualityDimension:
    """Tests for QualityDimension dataclass."""

    def test_valid_construction(self):
        qd = QualityDimension(name="accuracy", score=0.9, threshold=0.8)
        assert qd.name == "accuracy"
        assert qd.score == 0.9
        assert qd.threshold == 0.8

    def test_score_below_zero_raises(self):
        with pytest.raises(ValueError, match="Score must be between"):
            QualityDimension(name="x", score=-0.1, threshold=0.5)

    def test_score_above_one_raises(self):
        with pytest.raises(ValueError, match="Score must be between"):
            QualityDimension(name="x", score=1.1, threshold=0.5)

    def test_threshold_below_zero_raises(self):
        with pytest.raises(ValueError, match="Threshold must be between"):
            QualityDimension(name="x", score=0.5, threshold=-0.1)

    def test_threshold_above_one_raises(self):
        with pytest.raises(ValueError, match="Threshold must be between"):
            QualityDimension(name="x", score=0.5, threshold=1.1)

    def test_passes_above_threshold(self):
        qd = QualityDimension(name="x", score=0.9, threshold=0.8)
        assert qd.passes is True

    def test_passes_at_threshold(self):
        qd = QualityDimension(name="x", score=0.8, threshold=0.8)
        assert qd.passes is True

    def test_fails_below_threshold(self):
        qd = QualityDimension(name="x", score=0.7, threshold=0.8)
        assert qd.passes is False

    def test_gap_positive(self):
        qd = QualityDimension(name="x", score=0.9, threshold=0.8)
        assert qd.gap == pytest.approx(0.1)

    def test_gap_negative(self):
        qd = QualityDimension(name="x", score=0.5, threshold=0.8)
        assert qd.gap == pytest.approx(-0.3)

    def test_level_excellent(self):
        qd = QualityDimension(name="x", score=0.96, threshold=0.5)
        assert qd.level == QualityLevel.EXCELLENT

    def test_level_good(self):
        qd = QualityDimension(name="x", score=0.85, threshold=0.5)
        assert qd.level == QualityLevel.GOOD

    def test_level_acceptable(self):
        qd = QualityDimension(name="x", score=0.65, threshold=0.5)
        assert qd.level == QualityLevel.ACCEPTABLE

    def test_level_poor(self):
        qd = QualityDimension(name="x", score=0.45, threshold=0.5)
        assert qd.level == QualityLevel.POOR

    def test_level_unacceptable(self):
        qd = QualityDimension(name="x", score=0.2, threshold=0.5)
        assert qd.level == QualityLevel.UNACCEPTABLE

    def test_to_dict(self):
        qd = QualityDimension(name="test", score=0.9, threshold=0.8, critique="good")
        d = qd.to_dict()
        assert d["name"] == "test"
        assert d["score"] == 0.9
        assert d["threshold"] == 0.8
        assert d["critique"] == "good"
        assert d["passes"] is True
        assert d["gap"] == pytest.approx(0.1)
        assert d["level"] == "good"

    def test_boundary_score_zero(self):
        qd = QualityDimension(name="x", score=0.0, threshold=0.5)
        assert qd.level == QualityLevel.UNACCEPTABLE

    def test_boundary_score_one(self):
        qd = QualityDimension(name="x", score=1.0, threshold=0.5)
        assert qd.level == QualityLevel.EXCELLENT


# ============================================================================
# response_quality/models.py — QualityAssessment
# ============================================================================


class TestQualityAssessment:
    """Tests for QualityAssessment dataclass."""

    def _make_assessment(self, **overrides):
        defaults = {
            "dimensions": [
                QualityDimension(name="accuracy", score=0.9, threshold=0.8),
                QualityDimension(name="safety", score=0.99, threshold=0.95),
            ],
            "overall_score": 0.9,
            "passes_threshold": True,
            "refinement_suggestions": [],
            "constitutional_compliance": True,
        }
        defaults.update(overrides)
        return QualityAssessment(**defaults)

    def test_valid_construction(self):
        qa = self._make_assessment()
        assert qa.overall_score == 0.9
        assert qa.passes_threshold is True

    def test_overall_score_below_zero_raises(self):
        with pytest.raises(ValueError, match="Overall score must be between"):
            self._make_assessment(overall_score=-0.1)

    def test_overall_score_above_one_raises(self):
        with pytest.raises(ValueError, match="Overall score must be between"):
            self._make_assessment(overall_score=1.1)

    def test_dimension_count(self):
        qa = self._make_assessment()
        assert qa.dimension_count == 2

    def test_passing_dimensions(self):
        qa = self._make_assessment()
        assert len(qa.passing_dimensions) == 2

    def test_failing_dimensions(self):
        dims = [
            QualityDimension(name="accuracy", score=0.5, threshold=0.8),
            QualityDimension(name="safety", score=0.99, threshold=0.95),
        ]
        qa = self._make_assessment(dimensions=dims)
        assert len(qa.failing_dimensions) == 1
        assert qa.failing_dimensions[0].name == "accuracy"

    def test_pass_rate_all_pass(self):
        qa = self._make_assessment()
        assert qa.pass_rate == 1.0

    def test_pass_rate_empty(self):
        qa = self._make_assessment(dimensions=[])
        assert qa.pass_rate == 0.0

    def test_pass_rate_partial(self):
        dims = [
            QualityDimension(name="a", score=0.9, threshold=0.8),
            QualityDimension(name="b", score=0.3, threshold=0.8),
        ]
        qa = self._make_assessment(dimensions=dims)
        assert qa.pass_rate == 0.5

    def test_critical_failures(self):
        dims = [
            QualityDimension(name="constitutional_alignment", score=0.5, threshold=0.95),
            QualityDimension(name="safety", score=0.3, threshold=0.99),
            QualityDimension(name="accuracy", score=0.5, threshold=0.8),
        ]
        qa = self._make_assessment(dimensions=dims, passes_threshold=False)
        critical = qa.critical_failures
        assert len(critical) == 2

    def test_overall_level_values(self):
        assert self._make_assessment(overall_score=0.96).overall_level == QualityLevel.EXCELLENT
        assert self._make_assessment(overall_score=0.85).overall_level == QualityLevel.GOOD
        assert self._make_assessment(overall_score=0.65).overall_level == QualityLevel.ACCEPTABLE
        assert self._make_assessment(overall_score=0.45).overall_level == QualityLevel.POOR
        assert self._make_assessment(overall_score=0.2).overall_level == QualityLevel.UNACCEPTABLE

    def test_needs_refinement_when_not_passing(self):
        qa = self._make_assessment(passes_threshold=False)
        assert qa.needs_refinement is True

    def test_needs_refinement_when_non_compliant(self):
        qa = self._make_assessment(constitutional_compliance=False)
        assert qa.needs_refinement is True

    def test_no_refinement_needed(self):
        qa = self._make_assessment()
        assert qa.needs_refinement is False

    def test_get_dimension_exists(self):
        qa = self._make_assessment()
        dim = qa.get_dimension("accuracy")
        assert dim is not None
        assert dim.score == 0.9

    def test_get_dimension_missing(self):
        qa = self._make_assessment()
        assert qa.get_dimension("nonexistent") is None

    def test_to_dict(self):
        qa = self._make_assessment(response_id="test-1")
        d = qa.to_dict()
        assert d["overall_score"] == 0.9
        assert d["passes_threshold"] is True
        assert d["dimension_count"] == 2
        assert d["response_id"] == "test-1"
        assert "timestamp" in d

    def test_from_dict(self):
        qa = self._make_assessment(response_id="test-2")
        d = qa.to_dict()
        restored = QualityAssessment.from_dict(d)
        assert restored.overall_score == 0.9
        assert restored.passes_threshold is True
        assert len(restored.dimensions) == 2

    def test_from_dict_no_timestamp(self):
        data = {
            "dimensions": [],
            "overall_score": 0.5,
            "passes_threshold": False,
        }
        restored = QualityAssessment.from_dict(data)
        assert restored.overall_score == 0.5


# ============================================================================
# response_quality/models.py — RefinementIteration & RefinementResult
# ============================================================================


class TestRefinementIteration:
    """Tests for RefinementIteration dataclass."""

    def _make_assessment(self, score, passes=True):
        return QualityAssessment(
            dimensions=[],
            overall_score=score,
            passes_threshold=passes,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )

    def test_improvement_delta_positive(self):
        ri = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=self._make_assessment(0.5),
            after_assessment=self._make_assessment(0.8),
        )
        assert ri.improvement_delta == pytest.approx(0.3)

    def test_improved_true(self):
        ri = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=self._make_assessment(0.5),
            after_assessment=self._make_assessment(0.8),
        )
        assert ri.improved is True

    def test_improved_false(self):
        ri = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=self._make_assessment(0.8),
            after_assessment=self._make_assessment(0.7),
        )
        assert ri.improved is False

    def test_now_passes(self):
        ri = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=self._make_assessment(0.5, passes=False),
            after_assessment=self._make_assessment(0.8, passes=True),
        )
        assert ri.now_passes is True

    def test_now_passes_false_when_both_pass(self):
        ri = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=self._make_assessment(0.8, passes=True),
            after_assessment=self._make_assessment(0.9, passes=True),
        )
        assert ri.now_passes is False


class TestRefinementResultModel:
    """Tests for RefinementResult dataclass."""

    def _make_assessment(self, score, passes=True):
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
            initial_assessment=self._make_assessment(0.5),
            final_assessment=self._make_assessment(0.8),
        )
        assert rr.total_improvement == pytest.approx(0.3)

    def test_was_refined_true(self):
        ri = RefinementIteration(
            iteration_number=1,
            original_response="old",
            refined_response="new",
            before_assessment=self._make_assessment(0.5),
            after_assessment=self._make_assessment(0.8),
        )
        rr = RefinementResult(
            original_response="old",
            final_response="new",
            iterations=[ri],
            total_iterations=1,
            status=RefinementStatus.COMPLETED,
            initial_assessment=self._make_assessment(0.5),
            final_assessment=self._make_assessment(0.8),
        )
        assert rr.was_refined is True

    def test_was_refined_false(self):
        rr = RefinementResult(
            original_response="old",
            final_response="old",
            iterations=[],
            total_iterations=0,
            status=RefinementStatus.SKIPPED,
            initial_assessment=self._make_assessment(0.9),
            final_assessment=self._make_assessment(0.9),
        )
        assert rr.was_refined is False

    def test_success_true(self):
        rr = RefinementResult(
            original_response="old",
            final_response="new",
            iterations=[],
            total_iterations=0,
            status=RefinementStatus.COMPLETED,
            initial_assessment=self._make_assessment(0.5),
            final_assessment=self._make_assessment(0.9, passes=True),
        )
        assert rr.success is True

    def test_success_false_on_failure_status(self):
        rr = RefinementResult(
            original_response="old",
            final_response="old",
            iterations=[],
            total_iterations=0,
            status=RefinementStatus.FAILED,
            initial_assessment=self._make_assessment(0.5),
            final_assessment=self._make_assessment(0.5),
        )
        assert rr.success is False

    def test_to_dict(self):
        rr = RefinementResult(
            original_response="old",
            final_response="new",
            iterations=[],
            total_iterations=0,
            status=RefinementStatus.COMPLETED,
            initial_assessment=self._make_assessment(0.5),
            final_assessment=self._make_assessment(0.9),
        )
        d = rr.to_dict()
        assert d["status"] == "completed"
        assert d["total_improvement"] == pytest.approx(0.4)
        assert "constitutional_hash" in d


# ============================================================================
# response_quality/validator.py
# ============================================================================


class TestDimensionSpec:
    """Tests for DimensionSpec."""

    def test_valid_spec(self):
        ds = DimensionSpec(name="test", threshold=0.8, weight=1.5)
        assert ds.name == "test"
        assert ds.weight == 1.5

    def test_invalid_threshold(self):
        from enhanced_agent_bus._compat.errors import ValidationError as VE

        with pytest.raises(VE):
            DimensionSpec(name="x", threshold=1.5)

    def test_negative_weight(self):
        from enhanced_agent_bus._compat.errors import ValidationError as VE

        with pytest.raises(VE):
            DimensionSpec(name="x", threshold=0.5, weight=-1.0)


class TestResponseQualityValidator:
    """Tests for ResponseQualityValidator."""

    @pytest.fixture()
    def validator(self):
        return ResponseQualityValidator()

    def test_construction(self, validator):
        assert len(validator.dimensions) >= 5

    def test_constitutional_hash_mismatch_raises(self):
        with pytest.raises(ConstitutionalHashError):
            ResponseQualityValidator(constitutional_hash="wrong_hash")

    def test_dimension_names(self, validator):
        names = validator.dimension_names
        assert "accuracy" in names
        assert "safety" in names

    def test_required_dimensions(self, validator):
        required = validator.required_dimensions
        assert "constitutional_alignment" in required
        assert "safety" in required

    def test_thresholds(self, validator):
        t = validator.thresholds
        assert t["safety"] == 0.99

    def test_validate_good_response(self, validator):
        assessment = validator.validate(
            "This is a well-formed, governance-compliant response with proper information."
        )
        assert isinstance(assessment, QualityAssessment)
        assert assessment.overall_score > 0.0
        assert assessment.dimension_count == len(validator.dimensions)

    def test_validate_with_context(self, validator):
        assessment = validator.validate(
            "AI governance requires transparent and fair processes.",
            context={"query": "What is AI governance?"},
        )
        assert assessment.overall_score > 0.0

    def test_validate_with_precomputed_scores(self, validator):
        scores = {
            "accuracy": 0.9,
            "coherence": 0.8,
            "relevance": 0.85,
            "constitutional_alignment": 0.98,
            "safety": 0.99,
        }
        assessment = validator.validate("test response", scores=scores)
        assert assessment.overall_score > 0.0

    def test_validate_empty_response(self, validator):
        assessment = validator.validate("")
        assert assessment.overall_score < 0.8

    def test_validate_harmful_content(self, validator):
        assessment = validator.validate("Here is how to hack into systems and steal data.")
        safety_dim = assessment.get_dimension("safety")
        assert safety_dim is not None
        assert safety_dim.score < 0.5

    def test_default_scoring_with_query_context(self, validator):
        scores = validator._default_scoring(
            "AI governance ensures safety.",
            context={"query": "AI governance"},
        )
        assert scores["relevance"] > 0.6

    def test_default_scoring_no_context(self, validator):
        scores = validator._default_scoring("A valid response here.")
        assert scores["relevance"] == 0.75

    def test_default_scoring_empty(self, validator):
        scores = validator._default_scoring("")
        assert scores["coherence"] == 0.0

    def test_calculate_overall_score_empty(self, validator):
        assert validator._calculate_overall_score([]) == 0.0

    def test_check_constitutional_compliance_disabled(self):
        config = ValidationConfig(enable_constitutional_check=False)
        v = ResponseQualityValidator(config=config)
        dims = [QualityDimension(name="constitutional_alignment", score=0.1, threshold=0.95)]
        assert v._check_constitutional_compliance(dims) is True

    def test_check_constitutional_no_dimension(self, validator):
        dims = [QualityDimension(name="accuracy", score=0.9, threshold=0.8)]
        assert validator._check_constitutional_compliance(dims) is True

    def test_generate_critique_passing(self, validator):
        assert validator._generate_critique("accuracy", 0.9, 0.8) is None

    def test_generate_critique_failing(self, validator):
        critique = validator._generate_critique("accuracy", 0.5, 0.8)
        assert critique is not None
        assert "accuracy" in critique.lower()

    def test_generate_critique_unknown_dimension(self, validator):
        critique = validator._generate_critique("custom_dim", 0.3, 0.8)
        assert "custom_dim" in critique

    def test_generate_suggestions(self, validator):
        dims = [
            QualityDimension(name="accuracy", score=0.5, threshold=0.8),
            QualityDimension(name="safety", score=0.3, threshold=0.99),
        ]
        suggestions = validator._generate_suggestions(dims)
        assert len(suggestions) == 2

    def test_generate_suggestions_custom_dimension(self, validator):
        dims = [QualityDimension(name="custom", score=0.3, threshold=0.8)]
        suggestions = validator._generate_suggestions(dims)
        assert len(suggestions) == 1
        assert "custom" in suggestions[0]

    def test_validate_batch(self, validator):
        results = validator.validate_batch(
            ["Response one is valid.", "Response two is also valid."]
        )
        assert len(results) == 2

    def test_validate_batch_with_contexts(self, validator):
        results = validator.validate_batch(
            ["Response one.", "Response two."],
            contexts=[{"query": "q1"}, {"query": "q2"}],
        )
        assert len(results) == 2

    def test_validate_batch_mismatched_lengths(self, validator):
        from enhanced_agent_bus._compat.errors import ValidationError as VE

        with pytest.raises(VE):
            validator.validate_batch(["r1", "r2"], contexts=[None])

    def test_get_dimension_spec(self, validator):
        spec = validator.get_dimension_spec("accuracy")
        assert spec is not None
        assert spec.name == "accuracy"

    def test_get_dimension_spec_missing(self, validator):
        assert validator.get_dimension_spec("nonexistent") is None

    def test_update_threshold(self, validator):
        validator.update_threshold("accuracy", 0.5)
        assert validator.thresholds["accuracy"] == 0.5

    def test_update_threshold_unknown_dimension(self, validator):
        from enhanced_agent_bus._compat.errors import ValidationError as VE

        with pytest.raises(VE):
            validator.update_threshold("nonexistent", 0.5)

    def test_update_threshold_invalid_value(self, validator):
        from enhanced_agent_bus._compat.errors import ValidationError as VE

        with pytest.raises(VE):
            validator.update_threshold("accuracy", 1.5)

    def test_reset_validation_count(self, validator):
        validator.validate("test response")
        validator.reset_validation_count()
        assert validator._validation_count == 0

    def test_stats(self, validator):
        validator.validate("test response")
        stats = validator.stats
        assert stats["validation_count"] == 1
        assert "constitutional_hash" in stats
        assert "thresholds" in stats

    def test_custom_dimensions(self):
        custom = {
            "custom_dim": DimensionSpec(name="custom_dim", threshold=0.5, weight=2.0),
        }
        v = ResponseQualityValidator(custom_dimensions=custom)
        assert "custom_dim" in v.dimensions

    def test_check_passes_threshold_below_overall(self, validator):
        dims = [QualityDimension(name="accuracy", score=0.9, threshold=0.8)]
        # overall_score below config threshold
        assert validator._check_passes_threshold(dims, 0.3) is False

    def test_check_passes_threshold_critical_fail(self, validator):
        dims = [
            QualityDimension(name="safety", score=0.5, threshold=0.99),
            QualityDimension(name="accuracy", score=0.9, threshold=0.8),
        ]
        assert validator._check_passes_threshold(dims, 0.9) is False

    def test_custom_scorer(self):
        class MockScorer:
            def score(self, response, context=None):
                return {
                    "accuracy": 0.95,
                    "coherence": 0.9,
                    "relevance": 0.85,
                    "constitutional_alignment": 0.99,
                    "safety": 1.0,
                }

        v = ResponseQualityValidator(scorer=MockScorer())
        assessment = v.validate("test")
        assert assessment.overall_score > 0.8


class TestCreateValidator:
    """Tests for create_validator factory."""

    def test_default(self):
        v = create_validator()
        assert isinstance(v, ResponseQualityValidator)

    def test_with_thresholds(self):
        v = create_validator(thresholds={"accuracy": 0.5, "custom": 0.6})
        assert v.dimensions["accuracy"].threshold == 0.5
        assert v.dimensions["custom"].threshold == 0.6


# ============================================================================
# response_quality/refiner.py
# ============================================================================


class TestDefaultLLMRefiner:
    """Tests for DefaultLLMRefiner."""

    def _make_assessment(self, failing_dims=None):
        dims = []
        if failing_dims:
            for name, score, threshold in failing_dims:
                dims.append(QualityDimension(name=name, score=score, threshold=threshold))
        return QualityAssessment(
            dimensions=dims,
            overall_score=0.5,
            passes_threshold=False,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )

    def test_refine_coherence(self):
        refiner = DefaultLLMRefiner()
        assessment = self._make_assessment([("coherence", 0.3, 0.7)])
        result = refiner.refine("this is a test", assessment)
        assert result.endswith(".")

    def test_refine_relevance_with_context(self):
        refiner = DefaultLLMRefiner()
        assessment = self._make_assessment([("relevance", 0.3, 0.8)])
        result = refiner.refine("answer here", assessment, context={"query": "What is AI?"})
        assert "Regarding" in result

    def test_refine_safety(self):
        refiner = DefaultLLMRefiner()
        assessment = self._make_assessment([("safety", 0.3, 0.99)])
        result = refiner.refine("hack the system and steal data", assessment)
        assert "[redacted]" in result

    async def test_refine_async(self):
        refiner = DefaultLLMRefiner()
        assessment = self._make_assessment([("coherence", 0.3, 0.7)])
        result = await refiner.refine_async("test text", assessment)
        assert isinstance(result, str)


class TestDefaultConstitutionalCorrector:
    """Tests for DefaultConstitutionalCorrector."""

    def test_correct_harmful(self):
        corrector = DefaultConstitutionalCorrector()
        result = corrector.correct("some response", ["harmful content detected"])
        assert "[Reviewed for safety]" in result

    def test_correct_bias(self):
        corrector = DefaultConstitutionalCorrector()
        result = corrector.correct("some response", ["bias detected"])
        assert "balanced and fair" in result

    def test_correct_privacy_ssn(self):
        corrector = DefaultConstitutionalCorrector()
        result = corrector.correct("SSN is 123-45-6789", ["privacy violation"])
        assert "[SSN-REDACTED]" in result

    def test_correct_privacy_email(self):
        corrector = DefaultConstitutionalCorrector()
        result = corrector.correct("Email: user@example.com", ["privacy concern"])
        assert "[EMAIL-REDACTED]" in result

    async def test_correct_async(self):
        corrector = DefaultConstitutionalCorrector()
        result = await corrector.correct_async("response", ["harmful"], None)
        assert "[Reviewed for safety]" in result

    def test_no_violations(self):
        corrector = DefaultConstitutionalCorrector()
        result = corrector.correct("clean response", [])
        assert result == "clean response"


class TestRefinementConfig:
    """Tests for RefinementConfig."""

    def test_defaults(self):
        config = RefinementConfig()
        assert config.max_iterations == 3
        assert config.stop_on_pass is True

    def test_custom_config(self):
        config = RefinementConfig(max_iterations=5, improvement_threshold=0.05)
        assert config.max_iterations == 5
        assert config.improvement_threshold == 0.05


class TestResponseRefiner:
    """Tests for ResponseRefiner."""

    @pytest.fixture()
    def refiner(self):
        return ResponseRefiner()

    def test_construction(self, refiner):
        assert refiner.max_iterations == 3
        assert isinstance(refiner.validator, ResponseQualityValidator)

    def test_refine_already_passes(self, refiner):
        result = refiner.refine(
            "A comprehensive, accurate response about AI governance and policy "
            "compliance that addresses safety concerns with authorized methods.",
            context={"query": "AI governance"},
        )
        assert isinstance(result, RefinementResult)
        assert result.status in (RefinementStatus.SKIPPED, RefinementStatus.COMPLETED)

    def test_refine_iterates(self):
        refiner = ResponseRefiner(max_iterations=2)
        result = refiner.refine("short")
        assert isinstance(result, RefinementResult)
        assert result.total_iterations >= 0

    def test_stats(self, refiner):
        refiner.refine("test response")
        stats = refiner.stats
        assert stats["refinement_count"] == 1
        assert "constitutional_hash" in stats

    def test_set_constitutional_corrector(self, refiner):
        mock_corrector = MagicMock()
        refiner.set_constitutional_corrector(mock_corrector)
        assert refiner.constitutional_corrector is mock_corrector

    def test_set_llm_refiner(self, refiner):
        mock_refiner = MagicMock()
        refiner.set_llm_refiner(mock_refiner)
        assert refiner.llm_refiner is mock_refiner

    def test_refine_batch(self, refiner):
        results = refiner.refine_batch(["response one.", "response two."])
        assert len(results) == 2

    def test_refine_batch_mismatched(self, refiner):
        with pytest.raises(ValueError, match="same length"):
            refiner.refine_batch(["r1"], contexts=[None, None])

    async def test_refine_async(self, refiner):
        result = await refiner.refine_async("A test response for governance review.")
        assert isinstance(result, RefinementResult)

    async def test_refine_batch_async(self, refiner):
        results = await refiner.refine_batch_async(["response one.", "response two."])
        assert len(results) == 2

    async def test_refine_batch_async_mismatched(self, refiner):
        with pytest.raises(ValueError, match="same length"):
            await refiner.refine_batch_async(["r1"], contexts=[None, None])

    def test_should_stop_on_pass(self, refiner):
        assessment = QualityAssessment(
            dimensions=[],
            overall_score=0.9,
            passes_threshold=True,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        assert refiner._should_stop(assessment, None, 0) is True

    def test_should_stop_max_iterations(self, refiner):
        assessment = QualityAssessment(
            dimensions=[],
            overall_score=0.3,
            passes_threshold=False,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        assert refiner._should_stop(assessment, None, 3) is True

    def test_describe_improvements(self, refiner):
        before = QualityAssessment(
            dimensions=[QualityDimension(name="accuracy", score=0.5, threshold=0.8)],
            overall_score=0.5,
            passes_threshold=False,
            refinement_suggestions=[],
            constitutional_compliance=False,
        )
        after = QualityAssessment(
            dimensions=[QualityDimension(name="accuracy", score=0.9, threshold=0.8)],
            overall_score=0.9,
            passes_threshold=True,
            refinement_suggestions=[],
            constitutional_compliance=True,
        )
        improvements = refiner._describe_improvements(before, after)
        assert len(improvements) >= 1
        assert any("improved" in i.lower() or "compliance" in i.lower() for i in improvements)


class TestCreateRefiner:
    """Tests for create_refiner factory."""

    def test_default(self):
        r = create_refiner()
        assert isinstance(r, ResponseRefiner)
        assert r.max_iterations == 3

    def test_custom_iterations(self):
        r = create_refiner(max_iterations=5)
        assert r.max_iterations == 5


# ============================================================================
# ai_assistant/retrieval.py
# ============================================================================


class TestRetrievalResult:
    """Tests for RetrievalResult dataclass."""

    def test_construction(self):
        rr = RetrievalResult(
            id="test-1",
            content="Some content",
            score=0.95,
            source="policy_index",
        )
        assert rr.id == "test-1"
        assert rr.score == 0.95
        assert rr.metadata == {}
        assert rr.timestamp is not None

    def test_with_metadata(self):
        rr = RetrievalResult(
            id="test-2",
            content="Content",
            score=0.8,
            source="vector_db",
            metadata={"domain": "security"},
        )
        assert rr.metadata["domain"] == "security"


class TestBaseRetriever:
    """Tests for BaseRetriever."""

    async def test_not_implemented(self):
        br = BaseRetriever()
        with pytest.raises(NotImplementedError):
            await br.retrieve("query")


class TestSemanticRetriever:
    """Tests for SemanticRetriever."""

    async def test_no_embeddings_returns_empty(self):
        with patch("enhanced_agent_bus.ai_assistant.retrieval.EMBEDDINGS_AVAILABLE", False):
            sr = SemanticRetriever()
            sr._initialized = False
            results = await sr.retrieve("test query")
            assert results == []

    async def test_retrieve_with_mock_providers(self):
        mock_provider = MagicMock()
        mock_provider.embed.return_value = [0.1, 0.2, 0.3]

        mock_result = MagicMock()
        mock_result.id = "doc-1"
        mock_result.payload = {"content": "test content"}
        mock_result.score = 0.95

        mock_store = MagicMock()
        mock_store.search.return_value = [mock_result]

        sr = SemanticRetriever(
            embedding_provider=mock_provider,
            vector_store=mock_store,
        )
        # Mark as initialized so _ensure_initialized returns True
        sr._initialized = True
        results = await sr.retrieve("test query", limit=5)
        assert len(results) == 1
        assert results[0].id == "doc-1"
        assert results[0].source == "vector_db"

    async def test_index_document_with_mock(self):
        mock_provider = MagicMock()
        mock_provider.embed.return_value = [0.1, 0.2]

        mock_store = MagicMock()
        mock_store.upsert.return_value = None

        sr = SemanticRetriever(
            embedding_provider=mock_provider,
            vector_store=mock_store,
        )
        sr._initialized = True

        # Mock the VectorDocument import inside index_document
        mock_vd = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "enhanced_agent_bus.embeddings": MagicMock(),
                "enhanced_agent_bus.embeddings.vector_store": MagicMock(VectorDocument=mock_vd),
            },
        ):
            success = await sr.index_document("doc-1", "content", {"tag": "test"})
            assert success is True
            mock_store.upsert.assert_called_once()

    async def test_index_document_not_initialized(self):
        with patch("enhanced_agent_bus.ai_assistant.retrieval.EMBEDDINGS_AVAILABLE", False):
            sr = SemanticRetriever()
            sr._initialized = False
            success = await sr.index_document("doc-1", "content")
            assert success is False

    async def test_index_documents_batch(self):
        mock_provider = MagicMock()
        mock_provider.embed_batch.return_value = [[0.1], [0.2]]

        mock_store = MagicMock()
        mock_store.upsert.return_value = 2

        sr = SemanticRetriever(
            embedding_provider=mock_provider,
            vector_store=mock_store,
        )
        sr._initialized = True

        mock_vd = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "enhanced_agent_bus.embeddings": MagicMock(),
                "enhanced_agent_bus.embeddings.vector_store": MagicMock(VectorDocument=mock_vd),
            },
        ):
            count = await sr.index_documents_batch(
                [
                    {"id": "d1", "content": "one", "metadata": {"k": "v"}},
                    {"content": "two"},
                ]
            )
            assert count == 2

    async def test_index_documents_batch_not_initialized(self):
        with patch("enhanced_agent_bus.ai_assistant.retrieval.EMBEDDINGS_AVAILABLE", False):
            sr = SemanticRetriever()
            sr._initialized = False
            count = await sr.index_documents_batch([{"content": "test"}])
            assert count == 0

    async def test_ensure_initialized_already_done(self):
        """When already initialized with providers, returns True immediately."""
        mock_provider = MagicMock()
        mock_store = MagicMock()
        sr = SemanticRetriever(embedding_provider=mock_provider, vector_store=mock_store)
        sr._initialized = True
        assert sr._ensure_initialized() is True

    async def test_ensure_initialized_no_embeddings(self):
        """When EMBEDDINGS_AVAILABLE is False, returns False."""
        with patch("enhanced_agent_bus.ai_assistant.retrieval.EMBEDDINGS_AVAILABLE", False):
            sr = SemanticRetriever()
            sr._initialized = False
            assert sr._ensure_initialized() is False

    async def test_ensure_initialized_already_done_no_provider(self):
        """When initialized=True but no providers, returns False."""
        sr = SemanticRetriever()
        sr._initialized = True
        sr._embedding_provider = None
        sr._vector_store = None
        assert sr._ensure_initialized() is False


class TestHybridRetriever:
    """Tests for HybridRetriever."""

    async def test_retrieve_combines_results(self):
        hr = HybridRetriever()
        mock_results_1 = [
            RetrievalResult(id="p1", content="policy", score=0.9, source="policy_index")
        ]
        mock_results_2 = [RetrievalResult(id="v1", content="vector", score=0.8, source="vector_db")]
        hr.retrievers[0] = MagicMock()
        hr.retrievers[0].retrieve = AsyncMock(return_value=mock_results_1)
        hr.retrievers[1] = MagicMock()
        hr.retrievers[1].retrieve = AsyncMock(return_value=mock_results_2)

        results = await hr.retrieve("test", limit=5)
        assert len(results) == 2
        assert results[0].score >= results[1].score

    async def test_retrieve_handles_retriever_error(self):
        hr = HybridRetriever()
        hr.retrievers[0] = MagicMock()
        hr.retrievers[0].retrieve = AsyncMock(side_effect=RuntimeError("broken"))
        hr.retrievers[0].__class__.__name__ = "PolicyRetriever"
        hr.retrievers[1] = MagicMock()
        hr.retrievers[1].retrieve = AsyncMock(return_value=[])

        results = await hr.retrieve("test")
        assert results == []

    async def test_retrieve_respects_limit(self):
        hr = HybridRetriever()
        many_results = [
            RetrievalResult(id=f"r{i}", content=f"content {i}", score=0.9 - i * 0.1, source="test")
            for i in range(10)
        ]
        hr.retrievers = [MagicMock()]
        hr.retrievers[0].retrieve = AsyncMock(return_value=many_results)

        results = await hr.retrieve("test", limit=3)
        assert len(results) == 3


class TestKnowledgeRetriever:
    """Tests for KnowledgeRetriever."""

    async def test_query_delegates_to_hybrid(self):
        kr = KnowledgeRetriever()
        mock_results = [RetrievalResult(id="r1", content="result", score=0.9, source="test")]
        kr.retriever = MagicMock()
        kr.retriever.retrieve = AsyncMock(return_value=mock_results)

        results = await kr.query("test query", limit=5)
        assert len(results) == 1
        kr.retriever.retrieve.assert_awaited_once_with("test query", limit=5)

    def test_constitutional_hash_stored(self):
        kr = KnowledgeRetriever(constitutional_hash="test_hash")
        assert kr.constitutional_hash == "test_hash"


class TestGetKnowledgeRetriever:
    """Tests for get_knowledge_retriever singleton."""

    def test_returns_instance(self):
        import enhanced_agent_bus.ai_assistant.retrieval as mod

        mod._retriever = None
        kr = get_knowledge_retriever()
        assert isinstance(kr, KnowledgeRetriever)

    def test_returns_same_instance(self):
        import enhanced_agent_bus.ai_assistant.retrieval as mod

        mod._retriever = None
        kr1 = get_knowledge_retriever()
        kr2 = get_knowledge_retriever()
        assert kr1 is kr2


# ============================================================================
# workflows/graph_workflow.py
# ============================================================================


class TestNodeStatus:
    """Tests for NodeStatus enum."""

    def test_values(self):
        assert NodeStatus.PENDING.value == "pending"
        assert NodeStatus.RUNNING.value == "running"
        assert NodeStatus.COMPLETED.value == "completed"
        assert NodeStatus.FAILED.value == "failed"


class TestGraphNodeAndEdge:
    """Tests for GraphNode and GraphEdge dataclasses."""

    def test_graph_node(self):
        async def dummy(state):
            return state

        node = GraphNode(name="test", func=dummy)
        assert node.name == "test"
        assert node.metadata == {}

    def test_graph_edge_no_condition(self):
        edge = GraphEdge(source="a", target="b")
        assert edge.condition is None

    def test_graph_edge_with_condition(self):
        edge = GraphEdge(source="a", target="b", condition=lambda s: True)
        assert edge.condition is not None


class TestStateGraph:
    """Tests for StateGraph."""

    @pytest.fixture()
    def graph(self):
        return StateGraph(state_schema=dict)

    async def test_add_node_and_execute(self, graph):
        async def node_a(state):
            return {**state, "visited_a": True}

        graph.add_node("a", node_a)
        graph.add_edge("a", "END")
        graph.set_entry_point("a")

        result = await graph.execute({"initial": True})
        assert result["visited_a"] is True
        assert result["initial"] is True

    async def test_linear_chain(self, graph):
        async def node_a(state):
            return {**state, "a": True}

        async def node_b(state):
            return {**state, "b": True}

        graph.add_node("a", node_a)
        graph.add_node("b", node_b)
        graph.add_edge("a", "b")
        graph.add_edge("b", "END")
        graph.set_entry_point("a")

        result = await graph.execute({})
        assert result["a"] is True
        assert result["b"] is True

    async def test_conditional_edge(self, graph):
        async def classify(state):
            return {**state, "type": "fast"}

        async def fast_path(state):
            return {**state, "path": "fast"}

        async def slow_path(state):
            return {**state, "path": "slow"}

        graph.add_node("classify", classify)
        graph.add_node("fast", fast_path)
        graph.add_node("slow", slow_path)
        graph.add_edge("classify", "fast", condition=lambda s: s.get("type") == "fast")
        graph.add_edge("classify", "slow", condition=lambda s: s.get("type") == "slow")
        graph.add_edge("fast", "END")
        graph.add_edge("slow", "END")
        graph.set_entry_point("classify")

        result = await graph.execute({})
        assert result["path"] == "fast"

    def test_add_edge_invalid_source(self, graph):
        async def node_a(state):
            return state

        graph.add_node("a", node_a)
        with pytest.raises(ValueError, match="Source node"):
            graph.add_edge("nonexistent", "a")

    def test_add_edge_invalid_target(self, graph):
        async def node_a(state):
            return state

        graph.add_node("a", node_a)
        with pytest.raises(ValueError, match="Target node"):
            graph.add_edge("a", "nonexistent")

    def test_add_edge_start_source_ok(self, graph):
        async def node_a(state):
            return state

        graph.add_node("a", node_a)
        graph.add_edge("START", "a")

    def test_add_edge_end_target_ok(self, graph):
        async def node_a(state):
            return state

        graph.add_node("a", node_a)
        graph.add_edge("a", "END")

    def test_set_entry_point_invalid(self, graph):
        with pytest.raises(ValueError, match="not found"):
            graph.set_entry_point("nonexistent")

    async def test_no_entry_point_raises(self, graph):
        with pytest.raises(ValueError, match="Entry point not set"):
            await graph.execute({})

    async def test_no_valid_edge_terminates(self, graph):
        async def node_a(state):
            return {**state, "done": True}

        graph.add_node("a", node_a)
        graph.set_entry_point("a")

        result = await graph.execute({})
        assert result["done"] is True

    async def test_node_execution_error_propagates(self, graph):
        async def failing_node(state):
            raise ValueError("node failed")

        graph.add_node("fail", failing_node)
        graph.add_edge("fail", "END")
        graph.set_entry_point("fail")

        with pytest.raises(ValueError, match="node failed"):
            await graph.execute({})

    async def test_get_history(self, graph):
        async def node_a(state):
            return {**state, "step": 1}

        graph.add_node("a", node_a)
        graph.add_edge("a", "END")
        graph.set_entry_point("a")

        await graph.execute({"step": 0})
        history = graph.get_history()
        assert len(history) >= 2
        assert history[0]["step"] == 0
        assert history[1]["step"] == 1

    async def test_interrupt_without_context(self, graph):
        async def node_a(state):
            return {**state, "done": True}

        graph.add_node("a", node_a)
        graph.add_edge("a", "END")
        graph.set_entry_point("a")
        graph.add_interrupt("a")

        result = await graph.execute({})
        assert result["done"] is True

    async def test_interrupt_with_context(self, graph):
        async def node_a(state):
            return {**state, "done": True}

        graph.add_node("a", node_a)
        graph.add_edge("a", "END")
        graph.set_entry_point("a")
        graph.add_interrupt("a")

        mock_context = MagicMock()
        mock_context.wait_for_signal = AsyncMock(return_value=None)

        result = await graph.execute({}, context=mock_context)
        assert result["done"] is True
        mock_context.wait_for_signal.assert_awaited_once_with("resume_a")

    def test_add_node_returns_self(self, graph):
        async def node_a(state):
            return state

        result = graph.add_node("a", node_a)
        assert result is graph

    def test_add_edge_returns_self(self, graph):
        async def node_a(state):
            return state

        graph.add_node("a", node_a)
        result = graph.add_edge("a", "END")
        assert result is graph

    def test_set_entry_point_returns_self(self, graph):
        async def node_a(state):
            return state

        graph.add_node("a", node_a)
        result = graph.set_entry_point("a")
        assert result is graph

    async def test_conditional_edge_false_skips_to_fallback(self, graph):
        async def node_a(state):
            return {**state, "type": "other"}

        async def node_b(state):
            return {**state, "b": True}

        async def node_c(state):
            return {**state, "c": True}

        graph.add_node("a", node_a)
        graph.add_node("b", node_b)
        graph.add_node("c", node_c)
        graph.add_edge("a", "b", condition=lambda s: s.get("type") == "fast")
        graph.add_edge("a", "c", condition=lambda s: True)
        graph.add_edge("b", "END")
        graph.add_edge("c", "END")
        graph.set_entry_point("a")

        result = await graph.execute({})
        assert result.get("c") is True
        assert result.get("b") is None


class TestGovernanceGraph:
    """Tests for GovernanceGraph."""

    @pytest.fixture()
    def gov_graph(self):
        return GovernanceGraph()

    async def test_simple_path(self, gov_graph):
        result = await gov_graph.execute({"content": "simple request"})
        assert result["complexity"] == "simple"
        assert result["executed"] is True
        assert result["audited"] is True
        assert result.get("validated") is None
        assert result.get("deliberated") is None

    async def test_validation_path(self, gov_graph):
        result = await gov_graph.execute({"content": "please validate this"})
        assert result["complexity"] == "requires_validation"
        assert result["validated"] is True
        assert result["deliberated"] is True
        assert result["executed"] is True
        assert result["audited"] is True

    async def test_complex_path(self, gov_graph):
        result = await gov_graph.execute({"content": "critical issue"})
        assert result["complexity"] == "complex"
        assert result["deliberated"] is True
        assert result["executed"] is True
        assert result["audited"] is True

    async def test_classify_node_directly(self, gov_graph):
        state = await gov_graph._classify_node({"content": "critical"})
        assert state["complexity"] == "complex"

    async def test_classify_node_validation(self, gov_graph):
        state = await gov_graph._classify_node({"content": "validate"})
        assert state["complexity"] == "requires_validation"

    async def test_classify_node_simple(self, gov_graph):
        state = await gov_graph._classify_node({"content": "hello"})
        assert state["complexity"] == "simple"

    async def test_classify_node_empty(self, gov_graph):
        state = await gov_graph._classify_node({})
        assert state["complexity"] == "simple"

    def test_has_standard_nodes(self, gov_graph):
        expected_nodes = {"classify", "validate", "deliberate", "execute", "audit"}
        assert set(gov_graph.nodes.keys()) == expected_nodes

    def test_entry_point_is_classify(self, gov_graph):
        assert gov_graph.entry_point == "classify"

    async def test_history_populated(self, gov_graph):
        await gov_graph.execute({"content": "simple"})
        history = gov_graph.get_history()
        assert len(history) >= 2
