"""
FR-12 Explanation API Unit Tests
Constitutional Hash: 608508a9bd224290

Tests for ExplanationService, CounterfactualEngine, and factor attribution.
"""

import pytest

pytest.importorskip("src.core.shared.schema_registry")


import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.event_schemas.decision_explanation import (
    CounterfactualHint,
    ExplanationFactor,
    GovernanceDimension,
    PredictedOutcome,
)
from enhanced_agent_bus.explanation_service import (
    DEFAULT_GOVERNANCE_VECTOR,
    FACTOR_TO_GOVERNANCE_MAPPING,
    FACTOR_WEIGHTS,
    CounterfactualEngine,
    ExplanationService,
    get_explanation_service,
    reset_explanation_service,
)


class TestCounterfactualEngine:
    """Tests for CounterfactualEngine class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = CounterfactualEngine()

    def test_constitutional_hash_is_set(self):
        """Verify constitutional hash is properly set."""
        assert self.engine.constitutional_hash == CONSTITUTIONAL_HASH

    def test_generate_counterfactuals_empty_factors(self):
        """Test counterfactual generation with empty factors list."""
        hints = self.engine.generate_counterfactuals(
            factors=[],
            current_verdict="ALLOW",
            impact_score=0.5,
        )
        assert hints == []

    def test_generate_counterfactuals_single_factor_high_score(self):
        """Test counterfactual for high-scoring factor."""
        factor = ExplanationFactor(
            factor_id="f-test",
            factor_name="Test Factor",
            factor_value=0.9,
            factor_weight=0.6,
            explanation="High score factor",
            evidence=["Evidence 1"],
            governance_dimension=GovernanceDimension.SAFETY,
        )

        hints = self.engine.generate_counterfactuals(
            factors=[factor],
            current_verdict="ESCALATE",
            impact_score=0.85,
            max_hints=1,
        )

        assert len(hints) == 1
        hint = hints[0]
        assert hint.scenario_id == "cf-f-test"
        assert hint.modified_factor == "Test Factor"
        assert hint.original_value == 0.9
        assert hint.modified_value == 0.3  # High score -> low
        assert "lower" in hint.scenario_description.lower()

    def test_generate_counterfactuals_single_factor_low_score(self):
        """Test counterfactual for low-scoring factor."""
        factor = ExplanationFactor(
            factor_id="f-test",
            factor_name="Test Factor",
            factor_value=0.2,
            factor_weight=0.6,
            explanation="Low score factor",
            evidence=["Evidence 1"],
            governance_dimension=GovernanceDimension.SECURITY,
        )

        hints = self.engine.generate_counterfactuals(
            factors=[factor],
            current_verdict="ALLOW",
            impact_score=0.3,
        )

        assert len(hints) == 1
        hint = hints[0]
        assert hint.modified_value == 0.8  # Low score -> high
        assert "higher" in hint.scenario_description.lower()

    def test_generate_counterfactuals_medium_score(self):
        """Test counterfactual for medium-scoring factor (threshold crossing)."""
        factor = ExplanationFactor(
            factor_id="f-test",
            factor_name="Test Factor",
            factor_value=0.45,
            factor_weight=0.5,
            explanation="Medium score factor",
            evidence=[],
            governance_dimension=GovernanceDimension.PRIVACY,
        )

        hints = self.engine.generate_counterfactuals(
            factors=[factor],
            current_verdict="CONDITIONAL",
            impact_score=0.5,
        )

        assert len(hints) == 1
        hint = hints[0]
        assert "threshold" in hint.scenario_description.lower()

    def test_generate_counterfactuals_respects_max_hints(self):
        """Test that max_hints parameter limits output."""
        factors = [
            ExplanationFactor(
                factor_id=f"f-{i}",
                factor_name=f"Factor {i}",
                factor_value=0.5 + (i * 0.1),
                factor_weight=0.3,
                explanation=f"Factor {i} explanation",
                evidence=[],
                governance_dimension=GovernanceDimension.FAIRNESS,
            )
            for i in range(5)
        ]

        hints = self.engine.generate_counterfactuals(
            factors=factors,
            current_verdict="ALLOW",
            impact_score=0.5,
            max_hints=2,
        )

        assert len(hints) == 2

    def test_predict_outcome_change_high_impact(self):
        """Test outcome prediction for high impact changes."""
        outcome = self.engine._predict_outcome_change(
            current_verdict="ALLOW",
            impact_score=0.6,  # Start with higher base score
            factor_weight=0.8,
            value_delta=0.5,  # Large positive delta
        )
        # With large positive delta and high base score, should predict escalation
        assert outcome in [
            PredictedOutcome.ESCALATE,
            PredictedOutcome.CONDITIONAL,
            PredictedOutcome.ALLOW,
        ]

    def test_predict_outcome_change_low_impact(self):
        """Test outcome prediction for low impact changes."""
        outcome = self.engine._predict_outcome_change(
            current_verdict="ESCALATE",
            impact_score=0.9,
            factor_weight=0.6,
            value_delta=-0.5,  # Large negative delta
        )
        # With large negative delta, should predict allow
        assert outcome in [PredictedOutcome.ALLOW, PredictedOutcome.CONDITIONAL]

    def test_check_threshold_crossing_escalation(self):
        """Test threshold crossing detection for escalation threshold."""
        # Crossing 0.8 threshold upward
        result = self.engine._check_threshold_crossing(0.7, 0.85)
        assert result == "escalation_threshold"

    def test_check_threshold_crossing_review(self):
        """Test threshold crossing detection for review threshold."""
        # Crossing 0.5 threshold downward
        result = self.engine._check_threshold_crossing(0.6, 0.4)
        assert result == "review_threshold"

    def test_check_threshold_crossing_attention(self):
        """Test threshold crossing detection for attention threshold."""
        # Crossing 0.3 threshold upward
        result = self.engine._check_threshold_crossing(0.25, 0.35)
        assert result == "attention_threshold"

    def test_check_threshold_crossing_none(self):
        """Test no threshold crossing detected."""
        result = self.engine._check_threshold_crossing(0.6, 0.65)
        assert result is None


class TestExplanationService:
    """Tests for ExplanationService class."""

    def setup_method(self):
        """Set up test fixtures."""
        reset_explanation_service()  # Clear singleton
        self.service = ExplanationService(enable_counterfactuals=True)

    def teardown_method(self):
        """Clean up after tests."""
        reset_explanation_service()

    def test_constitutional_hash_is_set(self):
        """Verify constitutional hash is properly set."""
        assert self.service.constitutional_hash == CONSTITUTIONAL_HASH

    def test_service_initialization_defaults(self):
        """Test service initializes with correct defaults."""
        assert self.service.impact_scorer is None
        assert self.service.decision_store is None
        assert self.service.enable_counterfactuals is True
        assert self.service.counterfactual_engine is not None

    def test_service_initialization_disabled_counterfactuals(self):
        """Test service with counterfactuals disabled."""
        service = ExplanationService(enable_counterfactuals=False)
        assert service.enable_counterfactuals is False

    async def test_generate_explanation_basic(self):
        """Test basic explanation generation."""
        message = {
            "content": "Test message content",
            "from_agent": "test-agent",
            "message_type": "COMMAND",
            "priority": "HIGH",
        }

        explanation = await self.service.generate_explanation(
            message=message,
            verdict="ALLOW",
            context={"matched_rules": ["rule-1"]},
            store_explanation=False,
        )

        assert explanation.decision_id is not None
        assert explanation.verdict == "ALLOW"
        assert explanation.constitutional_hash == CONSTITUTIONAL_HASH
        assert len(explanation.factors) > 0
        assert explanation.governance_vector is not None

    async def test_generate_explanation_with_decision_id(self):
        """Test explanation generation with provided decision ID."""
        decision_id = str(uuid.uuid4())

        explanation = await self.service.generate_explanation(
            message={"content": "test"},
            verdict="DENY",
            decision_id=decision_id,
            store_explanation=False,
        )

        assert explanation.decision_id == decision_id

    async def test_generate_explanation_with_tenant_id(self):
        """Test explanation generation with tenant ID."""
        explanation = await self.service.generate_explanation(
            message={"content": "test"},
            verdict="CONDITIONAL",
            tenant_id="tenant-123",
            store_explanation=False,
        )

        assert explanation.tenant_id == "tenant-123"

    async def test_generate_explanation_includes_counterfactuals(self):
        """Test that counterfactuals are generated when enabled."""
        explanation = await self.service.generate_explanation(
            message={"content": "high impact content", "priority": "CRITICAL"},
            verdict="ESCALATE",
            store_explanation=False,
        )

        assert explanation.counterfactuals_generated is True
        assert len(explanation.counterfactual_hints) > 0

    async def test_generate_explanation_no_counterfactuals_when_disabled(self):
        """Test no counterfactuals when feature is disabled."""
        service = ExplanationService(enable_counterfactuals=False)

        explanation = await service.generate_explanation(
            message={"content": "test"},
            verdict="ALLOW",
            store_explanation=False,
        )

        assert explanation.counterfactuals_generated is False
        assert len(explanation.counterfactual_hints) == 0

    async def test_generate_explanation_governance_vector_completeness(self):
        """Test governance vector has all 7 dimensions."""
        explanation = await self.service.generate_explanation(
            message={"content": "test"},
            verdict="ALLOW",
            store_explanation=False,
        )

        governance_vector = explanation.governance_vector
        expected_dimensions = [
            "safety",
            "security",
            "privacy",
            "fairness",
            "reliability",
            "transparency",
            "efficiency",
        ]

        for dim in expected_dimensions:
            assert dim in governance_vector
            assert 0.0 <= governance_vector[dim] <= 1.0

    async def test_generate_explanation_primary_factors(self):
        """Test primary factors are identified."""
        explanation = await self.service.generate_explanation(
            message={"content": "test"},
            verdict="ALLOW",
            store_explanation=False,
        )

        assert len(explanation.primary_factors) <= 3
        # Primary factors should be valid factor IDs
        factor_ids = [f.factor_id for f in explanation.factors]
        for pf in explanation.primary_factors:
            assert pf in factor_ids

    async def test_generate_explanation_euaiact_compliance(self):
        """Test EU AI Act Article 13 compliance info is populated."""
        explanation = await self.service.generate_explanation(
            message={"content": "test"},
            verdict="ALLOW",
            context={"human_oversight_level": "human-in-the-loop"},
            store_explanation=False,
        )

        euaiact = explanation.euaiact_article13_info
        assert euaiact.article_13_compliant is True
        assert euaiact.human_oversight_level == "human-in-the-loop"
        assert len(euaiact.transparency_measures) > 0
        assert euaiact.data_governance_info.get("constitutional_hash") == CONSTITUTIONAL_HASH

    async def test_generate_explanation_summary_format(self):
        """Test summary generation for different verdicts."""
        for verdict in ["ALLOW", "DENY", "CONDITIONAL", "ESCALATE"]:
            explanation = await self.service.generate_explanation(
                message={"content": "test"},
                verdict=verdict,
                store_explanation=False,
            )

            assert verdict in explanation.summary
            assert "Decision:" in explanation.summary
            assert "Impact score" in explanation.summary

    async def test_generate_explanation_detailed_reasoning(self):
        """Test detailed reasoning is generated."""
        explanation = await self.service.generate_explanation(
            message={"content": "test"},
            verdict="ALLOW",
            store_explanation=False,
        )

        reasoning = explanation.detailed_reasoning
        assert CONSTITUTIONAL_HASH in reasoning
        assert "Factor Attribution:" in reasoning
        assert "7-Dimensional Governance Vector:" in reasoning

    async def test_generate_explanation_with_context_rules(self):
        """Test matched/violated rules from context are included."""
        context = {
            "matched_rules": ["rule-001", "rule-002"],
            "violated_rules": ["rule-003"],
            "applicable_policies": ["policy-A"],
        }

        explanation = await self.service.generate_explanation(
            message={"content": "test"},
            verdict="DENY",
            context=context,
            store_explanation=False,
        )

        assert explanation.matched_rules == ["rule-001", "rule-002"]
        assert explanation.violated_rules == ["rule-003"]
        assert explanation.applicable_policies == ["policy-A"]

    async def test_generate_explanation_processing_time_tracked(self):
        """Test processing time is tracked."""
        explanation = await self.service.generate_explanation(
            message={"content": "test"},
            verdict="ALLOW",
            store_explanation=False,
        )

        assert explanation.processing_time_ms >= 0

    def test_calculate_factor_scores_fallback(self):
        """Test factor score calculation with fallback (no ImpactScorer)."""
        impact_score, factor_scores = self.service._calculate_factor_scores(
            message={"content": "test"},
            context={},
        )

        assert 0.0 <= impact_score <= 1.0
        assert "semantic_score" in factor_scores
        assert "permission_score" in factor_scores
        assert "volume_score" in factor_scores
        assert "context_score" in factor_scores
        assert "drift_score" in factor_scores

    def test_get_governance_vector_from_factors(self):
        """Test governance vector derivation from factor scores."""
        factor_scores = {
            "semantic_score": 0.8,
            "permission_score": 0.5,
            "volume_score": 0.3,
            "context_score": 0.6,
            "drift_score": 0.2,
        }

        governance_vector = self.service._get_governance_vector(
            message={},
            context={},
            factor_scores=factor_scores,
        )

        # Check vector is populated
        assert governance_vector["safety"] == 0.8  # From semantic_score
        assert governance_vector["security"] == 0.5  # From permission_score

    def test_create_explanation_factors(self):
        """Test creation of explanation factor objects."""
        factor_scores = {
            "semantic_score": 0.7,
            "permission_score": 0.4,
        }

        factors = self.service._create_explanation_factors(
            factor_scores=factor_scores,
            message={"content": "test"},
            context={},
        )

        assert len(factors) == 2
        for factor in factors:
            assert factor.factor_id.startswith("f-")
            assert factor.factor_name != ""
            assert 0.0 <= factor.factor_value <= 1.0
            assert factor.explanation != ""
            assert CONSTITUTIONAL_HASH in factor.evidence[-1]

    def test_generate_factor_evidence(self):
        """Test evidence generation for factors."""
        evidence = self.service._generate_factor_evidence(
            factor_name="semantic_score",
            score=0.95,
            message={},
            context={},
        )

        assert len(evidence) > 0
        assert any("high-impact" in e.lower() for e in evidence)
        assert any(CONSTITUTIONAL_HASH in e for e in evidence)

    def test_calculate_confidence(self):
        """Test confidence calculation."""
        factors = [
            ExplanationFactor(
                factor_id="f-1",
                factor_name="Factor 1",
                factor_value=0.8,
                factor_weight=0.5,
                explanation="",
                evidence=[],
                governance_dimension=GovernanceDimension.SAFETY,
            ),
            ExplanationFactor(
                factor_id="f-2",
                factor_name="Factor 2",
                factor_value=0.85,
                factor_weight=0.5,
                explanation="",
                evidence=[],
                governance_dimension=GovernanceDimension.SECURITY,
            ),
        ]

        # Low variance factors should give high confidence
        confidence = self.service._calculate_confidence(factors, 0.8)
        assert 0.7 <= confidence <= 1.0

    def test_calculate_variance(self):
        """Test variance calculation helper."""
        # Same values = 0 variance
        assert self.service._calculate_variance([0.5, 0.5, 0.5]) == 0.0

        # Empty list = 0 variance
        assert self.service._calculate_variance([]) == 0.0

        # Different values = non-zero variance
        variance = self.service._calculate_variance([0.1, 0.9])
        assert variance > 0

    def test_extract_message_id_from_dict(self):
        """Test message ID extraction from dict."""
        msg_id = self.service._extract_message_id({"message_id": "msg-123"})
        assert msg_id == "msg-123"

        msg_id = self.service._extract_message_id({"id": "id-456"})
        assert msg_id == "id-456"

    def test_extract_message_id_from_object(self):
        """Test message ID extraction from object with attributes."""

        class MockMessage:
            message_id = "msg-789"

        msg_id = self.service._extract_message_id(MockMessage())
        assert msg_id == "msg-789"


class TestExplanationServiceSingleton:
    """Tests for singleton pattern."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_explanation_service()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_explanation_service()

    def test_get_explanation_service_returns_singleton(self):
        """Test that get_explanation_service returns same instance."""
        service1 = get_explanation_service()
        service2 = get_explanation_service()
        assert service1 is service2

    def test_reset_explanation_service(self):
        """Test that reset creates new instance."""
        service1 = get_explanation_service()
        reset_explanation_service()
        service2 = get_explanation_service()
        assert service1 is not service2


class TestConstants:
    """Tests for module constants."""

    def test_default_governance_vector_has_all_dimensions(self):
        """Test default governance vector has all 7 dimensions."""
        expected = [
            "safety",
            "security",
            "privacy",
            "fairness",
            "reliability",
            "transparency",
            "efficiency",
        ]
        assert set(DEFAULT_GOVERNANCE_VECTOR.keys()) == set(expected)

    def test_default_governance_vector_values_are_zero(self):
        """Test default governance vector values are 0.0."""
        for value in DEFAULT_GOVERNANCE_VECTOR.values():
            assert value == 0.0

    def test_factor_to_governance_mapping_covers_all_factors(self):
        """Test mapping includes all expected factors."""
        expected_factors = [
            "semantic_score",
            "permission_score",
            "volume_score",
            "context_score",
            "drift_score",
            "priority_factor",
            "type_factor",
        ]
        for factor in expected_factors:
            assert factor in FACTOR_TO_GOVERNANCE_MAPPING

    def test_factor_weights_sum_reasonable(self):
        """Test factor weights are reasonable."""
        additive_weights = sum(
            v for k, v in FACTOR_WEIGHTS.items() if k not in ["priority_factor", "type_factor"]
        )
        # Additive weights should sum to approximately 1.0
        assert 0.9 <= additive_weights <= 1.1


class TestExplanationServiceWithMockedStore:
    """Tests for ExplanationService with mocked decision store."""

    def setup_method(self):
        """Set up test fixtures with mocked store."""
        reset_explanation_service()
        self.mock_store = MagicMock()
        self.mock_store.store = AsyncMock()
        self.mock_store.get = AsyncMock(return_value=None)

        self.service = ExplanationService(
            decision_store=self.mock_store,
            enable_counterfactuals=True,
        )

    def teardown_method(self):
        """Clean up after tests."""
        reset_explanation_service()

    async def test_generate_explanation_stores_when_enabled(self):
        """Test explanation is stored when store_explanation=True."""
        await self.service.generate_explanation(
            message={"content": "test"},
            verdict="ALLOW",
            store_explanation=True,
        )

        self.mock_store.store.assert_called_once()

    async def test_generate_explanation_skips_store_when_disabled(self):
        """Test explanation is not stored when store_explanation=False."""
        await self.service.generate_explanation(
            message={"content": "test"},
            verdict="ALLOW",
            store_explanation=False,
        )

        self.mock_store.store.assert_not_called()

    async def test_get_explanation_calls_store(self):
        """Test get_explanation delegates to decision store."""
        await self.service.get_explanation("decision-123", "tenant-1")

        self.mock_store.get.assert_called_once_with("decision-123", "tenant-1")
