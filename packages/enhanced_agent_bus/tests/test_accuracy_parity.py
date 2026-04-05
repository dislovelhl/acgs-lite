"""
Accuracy parity tests for ONNX vs keyword-based impact scoring.
Constitutional Hash: 608508a9bd224290

This module validates that the ONNX-based scoring path produces results
that are consistent with the keyword-based baseline, ensuring:
1. Agreement threshold >= 99% on validation dataset
2. Score tolerance within acceptable bounds (default 0.15)
3. BERT semantic improvements are correctly identified

The validation dataset covers:
- High-risk security scenarios
- Financial transactions
- Governance policy violations
- Emergency situations
- Edge cases (empty, whitespace, unicode)
- Context-based scoring (priority, tools)
- Semantic advantage cases (where BERT outperforms keywords)
"""

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from enhanced_agent_bus._compat.types import JSONDict

# Import the module under test
from enhanced_agent_bus.deliberation_layer.impact_scorer import (
    ONNX_AVAILABLE,
    TRANSFORMERS_AVAILABLE,
    ImpactScorer,
    reset_impact_scorer,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
# --- Fixtures ---


@pytest.fixture(scope="module")
def validation_dataset() -> JSONDict:
    """Load the validation dataset from JSON file."""
    fixtures_dir = Path(__file__).parent / "fixtures"
    dataset_path = fixtures_dir / "validation_dataset.json"

    if not dataset_path.exists():
        pytest.fail(f"Validation dataset not found at {dataset_path}")

    with open(dataset_path) as f:
        return json.load(f)


@pytest.fixture
def keyword_scorer():
    """Create a scorer that uses only keyword-based scoring (no ONNX/BERT)."""
    reset_impact_scorer()
    with patch("enhanced_agent_bus.deliberation_layer.impact_scorer.TRANSFORMERS_AVAILABLE", False):
        scorer = ImpactScorer(use_onnx=False)
        scorer._bert_enabled = False
        scorer._onnx_enabled = False
        yield scorer
    reset_impact_scorer()


@pytest.fixture
def onnx_scorer():
    """Create a scorer that uses ONNX/BERT if available."""
    reset_impact_scorer()
    scorer = ImpactScorer(use_onnx=True)
    yield scorer
    reset_impact_scorer()


@pytest.fixture
def bert_scorer():
    """Create a scorer using BERT (PyTorch) without ONNX."""
    reset_impact_scorer()
    scorer = ImpactScorer(use_onnx=False)
    yield scorer
    reset_impact_scorer()


# --- Test Classes ---


class TestValidationDatasetIntegrity:
    """Tests to ensure the validation dataset is properly structured."""

    def test_dataset_has_required_fields(self, validation_dataset):
        """Verify the dataset has all required top-level fields."""
        required_fields = ["version", "test_cases", "agreement_threshold", "score_tolerance"]
        for field in required_fields:
            assert field in validation_dataset, f"Missing required field: {field}"

    def test_dataset_has_test_cases(self, validation_dataset):
        """Verify the dataset has test cases."""
        assert len(validation_dataset["test_cases"]) > 0, "Dataset has no test cases"

    def test_each_test_case_has_required_fields(self, validation_dataset):
        """Verify each test case has required fields."""
        required_fields = ["id", "category", "message", "expected_risk_level"]
        for case in validation_dataset["test_cases"]:
            for field in required_fields:
                assert field in case, (
                    f"Test case {case.get('id', 'unknown')} missing field: {field}"
                )

    def test_test_case_categories_are_valid(self, validation_dataset):
        """Verify test cases have valid categories."""
        valid_categories = {
            "security",
            "financial",
            "governance",
            "emergency",
            "mixed",
            "benign",
            "priority",
            "tools",
            "semantic",
            "edge_case",
            "combined",
            "message_type",
            "length",
            "blockchain",
            "alerts",
        }
        for case in validation_dataset["test_cases"]:
            assert case["category"] in valid_categories, (
                f"Test case {case['id']} has invalid category: {case['category']}"
            )

    def test_expected_risk_levels_are_valid(self, validation_dataset):
        """Verify expected risk levels are valid."""
        valid_levels = {"low", "medium", "high"}
        for case in validation_dataset["test_cases"]:
            assert case["expected_risk_level"] in valid_levels, (
                f"Test case {case['id']} has invalid risk level: {case['expected_risk_level']}"
            )


class TestKeywordBasedScoring:
    """Tests for keyword-based scoring accuracy on the validation dataset."""

    def test_high_risk_cases_score_high(self, validation_dataset, keyword_scorer):
        """Verify high-risk cases receive high scores."""
        high_risk_cases = [
            c for c in validation_dataset["test_cases"] if c["expected_risk_level"] == "high"
        ]

        for case in high_risk_cases:
            score = keyword_scorer.calculate_impact_score(case["message"], case.get("context", {}))
            min_expected = case.get("expected_min_score", 0.5)
            assert score >= min_expected - 0.1, (
                f"Case {case['id']}: Expected score >= {min_expected - 0.1}, got {score}"
            )

    def test_low_risk_cases_score_low(self, validation_dataset, keyword_scorer):
        """Verify low-risk cases receive low scores."""
        low_risk_cases = [
            c for c in validation_dataset["test_cases"] if c["expected_risk_level"] == "low"
        ]

        for case in low_risk_cases:
            score = keyword_scorer.calculate_impact_score(case["message"], case.get("context", {}))
            max_expected = case.get("expected_max_score", 0.5)
            assert score <= max_expected + 0.1, (
                f"Case {case['id']}: Expected score <= {max_expected + 0.1}, got {score}"
            )

    def test_critical_priority_boosts_score(self, validation_dataset, keyword_scorer):
        """Verify critical priority correctly boosts the score."""
        priority_cases = [
            c
            for c in validation_dataset["test_cases"]
            if c["category"] == "priority" and c.get("context", {}).get("priority") == "critical"
        ]

        for case in priority_cases:
            score = keyword_scorer.calculate_impact_score(case["message"], case.get("context", {}))
            assert score >= 0.9, (
                f"Case {case['id']}: Critical priority should boost to >= 0.9, got {score}"
            )


class TestONNXVsKeywordParity:
    """Tests for accuracy parity between ONNX and keyword-based scoring."""

    def _calculate_agreement_rate(
        self, onnx_scores: list[float], keyword_scores: list[float], tolerance: float
    ) -> tuple[float, list[int]]:
        """
        Calculate agreement rate between two score lists.

        Returns:
            tuple of (agreement_rate, list of disagreeing indices)
        """
        if len(onnx_scores) != len(keyword_scores):
            raise ValueError("Score lists must have the same length")

        agreements = 0
        disagreements = []

        for i, (onnx, keyword) in enumerate(zip(onnx_scores, keyword_scores, strict=False)):
            if abs(onnx - keyword) <= tolerance:
                agreements += 1
            else:
                disagreements.append(i)

        rate = agreements / len(onnx_scores) if onnx_scores else 0.0
        return rate, disagreements

    def test_scoring_agreement_threshold(self, validation_dataset, onnx_scorer, keyword_scorer):
        """
        Verify ONNX and keyword scoring agree within threshold.

        This is the primary accuracy parity test. It allows for:
        1. Cases where scores agree within tolerance
        2. Cases where ONNX (BERT) scores higher due to semantic understanding
        """
        test_cases = validation_dataset["test_cases"]
        tolerance = validation_dataset["score_tolerance"]
        threshold = validation_dataset["agreement_threshold"]
        semantic_cases = set(validation_dataset.get("semantic_improvement_cases", []))

        onnx_scores = []
        keyword_scores = []
        case_ids = []

        for case in test_cases:
            message = case["message"]
            context = case.get("context", {})

            onnx_score = onnx_scorer.calculate_impact_score(message, context)
            keyword_score = keyword_scorer.calculate_impact_score(message, context)

            onnx_scores.append(onnx_score)
            keyword_scores.append(keyword_score)
            case_ids.append(case["id"])

        # Calculate agreement, excluding semantic advantage cases
        agreements = 0
        total_non_semantic = 0

        for i, case_id in enumerate(case_ids):
            if case_id in semantic_cases:
                # For semantic cases, ONNX should score >= keyword
                # (or at least close to it)
                if onnx_scores[i] >= keyword_scores[i] - tolerance:
                    agreements += 1
                    total_non_semantic += 1
                else:
                    total_non_semantic += 1
            else:
                total_non_semantic += 1
                if abs(onnx_scores[i] - keyword_scores[i]) <= tolerance:
                    agreements += 1

        agreement_rate = agreements / total_non_semantic if total_non_semantic > 0 else 1.0

        assert agreement_rate >= threshold, (
            f"Agreement rate {agreement_rate:.2%} below threshold {threshold:.2%}. "
            f"Tolerance: {tolerance}"
        )

    def test_both_scorers_produce_valid_scores(
        self, validation_dataset, onnx_scorer, keyword_scorer
    ):
        """Verify both scorers produce scores in valid range [0.0, 1.0]."""
        for case in validation_dataset["test_cases"]:
            message = case["message"]
            context = case.get("context", {})

            onnx_score = onnx_scorer.calculate_impact_score(message, context)
            keyword_score = keyword_scorer.calculate_impact_score(message, context)

            assert 0.0 <= onnx_score <= 1.0, (
                f"ONNX score {onnx_score} out of range for case {case['id']}"
            )
            assert 0.0 <= keyword_score <= 1.0, (
                f"Keyword score {keyword_score} out of range for case {case['id']}"
            )

    def test_score_consistency_same_input(self, onnx_scorer, keyword_scorer):
        """Verify both scorers produce consistent scores for same input."""
        test_message = {"content": "critical security breach emergency alert"}
        context = {}

        # Score multiple times
        onnx_scores = [onnx_scorer.calculate_impact_score(test_message, context) for _ in range(5)]
        keyword_scores = [
            keyword_scorer.calculate_impact_score(test_message, context) for _ in range(5)
        ]

        # All scores should be identical for deterministic scoring
        assert len(set(onnx_scores)) == 1, "ONNX scorer produces inconsistent scores"
        assert len(set(keyword_scores)) == 1, "Keyword scorer produces inconsistent scores"


class TestSemanticImprovement:
    """Tests for cases where BERT should provide semantic improvement."""

    def test_semantic_cases_not_worse_than_keywords(
        self, validation_dataset, onnx_scorer, keyword_scorer
    ):
        """Verify ONNX/BERT doesn't score significantly worse than keywords."""
        semantic_cases = validation_dataset.get("semantic_improvement_cases", [])
        tolerance = validation_dataset["score_tolerance"]

        for case in validation_dataset["test_cases"]:
            if case["id"] in semantic_cases:
                message = case["message"]
                context = case.get("context", {})

                onnx_score = onnx_scorer.calculate_impact_score(message, context)
                keyword_score = keyword_scorer.calculate_impact_score(message, context)

                # ONNX should not be significantly worse than keywords
                assert onnx_score >= keyword_score - tolerance, (
                    f"Case {case['id']}: ONNX score {onnx_score} significantly "
                    f"worse than keyword score {keyword_score}"
                )

    @pytest.mark.skipif(
        not TRANSFORMERS_AVAILABLE, reason="Transformers not available for semantic testing"
    )
    def test_semantic_understanding_cases(self, validation_dataset, bert_scorer):
        """Test that BERT understands semantic meaning in advantage cases."""
        semantic_case_ids = set(validation_dataset.get("semantic_improvement_cases", []))
        semantic_cases = [
            c for c in validation_dataset["test_cases"] if c["id"] in semantic_case_ids
        ]

        for case in semantic_cases:
            score = bert_scorer.calculate_impact_score(case["message"], case.get("context", {}))
            min_expected = case.get("expected_min_score", 0.3)

            # BERT should recognize security-related semantic content
            assert score >= min_expected - 0.1, (
                f"Case {case['id']}: BERT score {score} below expected {min_expected - 0.1}. "
                f"Notes: {case.get('notes', 'N/A')}"
            )


class TestBatchScoringParity:
    """Tests for batch scoring accuracy parity."""

    def test_batch_matches_sequential_onnx(self, validation_dataset, onnx_scorer):
        """Verify batch scoring matches sequential scoring for ONNX."""
        messages = [c["message"] for c in validation_dataset["test_cases"][:10]]
        contexts = [c.get("context", {}) for c in validation_dataset["test_cases"][:10]]

        # Batch scoring
        batch_scores = onnx_scorer.batch_score_impact(messages, contexts)

        # Sequential scoring
        sequential_scores = [
            onnx_scorer.calculate_impact_score(msg, ctx)
            for msg, ctx in zip(messages, contexts, strict=False)
        ]

        # Compare
        for i, (batch, seq) in enumerate(zip(batch_scores, sequential_scores, strict=False)):
            assert batch == pytest.approx(seq, abs=0.01), (
                f"Batch score {batch} != sequential score {seq} at index {i}"
            )

    def test_batch_matches_sequential_keyword(self, validation_dataset, keyword_scorer):
        """Verify batch scoring matches sequential scoring for keywords."""
        messages = [c["message"] for c in validation_dataset["test_cases"][:10]]
        contexts = [c.get("context", {}) for c in validation_dataset["test_cases"][:10]]

        # Batch scoring
        batch_scores = keyword_scorer.batch_score_impact(messages, contexts)

        # Sequential scoring
        sequential_scores = [
            keyword_scorer.calculate_impact_score(msg, ctx)
            for msg, ctx in zip(messages, contexts, strict=False)
        ]

        # Compare
        for i, (batch, seq) in enumerate(zip(batch_scores, sequential_scores, strict=False)):
            assert batch == pytest.approx(seq, abs=0.01), (
                f"Batch score {batch} != sequential score {seq} at index {i}"
            )


class TestEdgeCaseScoring:
    """Tests for edge case handling in scoring."""

    @pytest.fixture
    def edge_cases(self, validation_dataset):
        """Extract edge case test cases."""
        return [c for c in validation_dataset["test_cases"] if c["category"] == "edge_case"]

    def test_empty_content_handling(self, edge_cases, onnx_scorer, keyword_scorer):
        """Verify empty content is handled gracefully."""
        empty_cases = [c for c in edge_cases if "empty" in c["id"]]

        for case in empty_cases:
            onnx_score = onnx_scorer.calculate_impact_score(
                case["message"], case.get("context", {})
            )
            keyword_score = keyword_scorer.calculate_impact_score(
                case["message"], case.get("context", {})
            )

            # Both should return low scores for empty content
            assert onnx_score <= 0.3, f"ONNX score {onnx_score} too high for empty content"
            assert keyword_score <= 0.3, f"Keyword score {keyword_score} too high for empty content"

    def test_whitespace_content_handling(self, edge_cases, onnx_scorer, keyword_scorer):
        """Verify whitespace-only content is handled gracefully."""
        whitespace_cases = [c for c in edge_cases if "whitespace" in c["id"]]

        for case in whitespace_cases:
            onnx_score = onnx_scorer.calculate_impact_score(
                case["message"], case.get("context", {})
            )
            keyword_score = keyword_scorer.calculate_impact_score(
                case["message"], case.get("context", {})
            )

            # Both should return low scores for whitespace content
            assert onnx_score <= 0.3, f"ONNX score {onnx_score} too high for whitespace"
            assert keyword_score <= 0.3, f"Keyword score {keyword_score} too high for whitespace"

    def test_unicode_content_handling(self, edge_cases, onnx_scorer, keyword_scorer):
        """Verify unicode content is handled correctly."""
        unicode_cases = [c for c in edge_cases if "unicode" in c["id"]]

        for case in unicode_cases:
            onnx_score = onnx_scorer.calculate_impact_score(
                case["message"], case.get("context", {})
            )
            keyword_score = keyword_scorer.calculate_impact_score(
                case["message"], case.get("context", {})
            )

            # Both should successfully score unicode content
            assert 0.0 <= onnx_score <= 1.0, f"ONNX score {onnx_score} invalid"
            assert 0.0 <= keyword_score <= 1.0, f"Keyword score {keyword_score} invalid"


class TestCategoryScoring:
    """Tests for scoring accuracy by category."""

    @pytest.fixture
    def cases_by_category(self, validation_dataset):
        """Group test cases by category."""
        result = {}
        for case in validation_dataset["test_cases"]:
            category = case["category"]
            if category not in result:
                result[category] = []
            result[category].append(case)
        return result

    def test_security_category_high_scores(self, cases_by_category, keyword_scorer):
        """Verify security-related cases score appropriately high."""
        security_cases = cases_by_category.get("security", [])

        for case in security_cases:
            score = keyword_scorer.calculate_impact_score(case["message"], case.get("context", {}))
            min_expected = case.get("expected_min_score", 0.5)
            assert score >= min_expected - 0.15, (
                f"Security case {case['id']}: score {score} below expected {min_expected - 0.15}"
            )

    def test_benign_category_low_scores(self, cases_by_category, keyword_scorer):
        """Verify benign cases score appropriately low."""
        benign_cases = cases_by_category.get("benign", [])

        for case in benign_cases:
            score = keyword_scorer.calculate_impact_score(case["message"], case.get("context", {}))
            max_expected = case.get("expected_max_score", 0.4)
            assert score <= max_expected + 0.1, (
                f"Benign case {case['id']}: score {score} above expected {max_expected + 0.1}"
            )

    def test_financial_category_scores(self, cases_by_category, keyword_scorer):
        """Verify financial cases score based on risk level."""
        financial_cases = cases_by_category.get("financial", [])

        for case in financial_cases:
            score = keyword_scorer.calculate_impact_score(case["message"], case.get("context", {}))
            min_expected = case.get("expected_min_score", 0.5)
            assert score >= min_expected - 0.15, (
                f"Financial case {case['id']}: score {score} below expected {min_expected - 0.15}"
            )


class TestAccuracyMetrics:
    """Tests for overall accuracy metrics across the dataset."""

    def test_overall_high_risk_detection_rate(self, validation_dataset, keyword_scorer):
        """Verify high-risk cases are detected with acceptable rate."""
        high_risk_cases = [
            c for c in validation_dataset["test_cases"] if c["expected_risk_level"] == "high"
        ]

        detected = 0
        for case in high_risk_cases:
            score = keyword_scorer.calculate_impact_score(case["message"], case.get("context", {}))
            if score >= 0.5:  # Threshold for high-risk detection
                detected += 1

        detection_rate = detected / len(high_risk_cases) if high_risk_cases else 0.0
        # Note: Keyword-based fallback achieves ~75% detection rate; ML models achieve 85%+
        assert detection_rate >= 0.70, (
            f"High-risk detection rate {detection_rate:.2%} below 70% threshold"
        )

    def test_overall_low_risk_classification_rate(self, validation_dataset, keyword_scorer):
        """Verify low-risk cases are correctly classified."""
        low_risk_cases = [
            c for c in validation_dataset["test_cases"] if c["expected_risk_level"] == "low"
        ]

        correct = 0
        for case in low_risk_cases:
            score = keyword_scorer.calculate_impact_score(case["message"], case.get("context", {}))
            if score < 0.5:  # Threshold for low-risk classification
                correct += 1

        classification_rate = correct / len(low_risk_cases) if low_risk_cases else 0.0
        assert classification_rate >= 0.9, (
            f"Low-risk classification rate {classification_rate:.2%} below 90% threshold"
        )

    def test_average_score_by_risk_level(self, validation_dataset, keyword_scorer):
        """Verify average scores follow expected risk level ordering."""
        scores_by_level = {"low": [], "medium": [], "high": []}

        for case in validation_dataset["test_cases"]:
            score = keyword_scorer.calculate_impact_score(case["message"], case.get("context", {}))
            scores_by_level[case["expected_risk_level"]].append(score)

        avg_low = np.mean(scores_by_level["low"]) if scores_by_level["low"] else 0.0
        avg_medium = np.mean(scores_by_level["medium"]) if scores_by_level["medium"] else 0.5
        avg_high = np.mean(scores_by_level["high"]) if scores_by_level["high"] else 1.0

        # Average scores should follow ordering: low < medium < high
        assert avg_low < avg_medium, (
            f"Average low ({avg_low:.2f}) should be less than medium ({avg_medium:.2f})"
        )
        assert avg_medium <= avg_high, (
            f"Average medium ({avg_medium:.2f}) should be less than or equal to "
            f"high ({avg_high:.2f})"
        )


class TestScorerFlags:
    """Tests for scorer feature flags and configuration."""

    def test_onnx_available_flag_is_boolean(self):
        """Verify ONNX_AVAILABLE flag is a boolean."""
        assert isinstance(ONNX_AVAILABLE, bool)

    def test_transformers_available_flag_is_boolean(self):
        """Verify TRANSFORMERS_AVAILABLE flag is a boolean."""
        assert isinstance(TRANSFORMERS_AVAILABLE, bool)

    def test_scorer_flags_match_availability(self, onnx_scorer):
        """Verify scorer instance flags reflect availability."""
        # _onnx_enabled should only be True if ONNX_AVAILABLE is True
        if not ONNX_AVAILABLE or not TRANSFORMERS_AVAILABLE:
            assert not onnx_scorer._onnx_enabled

    def test_keyword_scorer_has_correct_flags(self, keyword_scorer):
        """Verify keyword scorer has correct disabled flags."""
        assert not keyword_scorer._bert_enabled
        assert not keyword_scorer._onnx_enabled
