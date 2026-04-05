"""
Module.

Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import AsyncMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.observability.structured_logging import get_logger

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


from ab_testing import ABTestRouter
from enhanced_agent_bus.adaptive_governance import (
    AdaptiveGovernanceEngine,
    AdaptiveThresholds,
    GovernanceDecision,
    GovernanceMetrics,
    GovernanceMode,
    ImpactFeatures,
    ImpactLevel,
    ImpactScorer,
    evaluate_message_governance,
    get_adaptive_governance,
    initialize_adaptive_governance,
    provide_governance_feedback,
)

logger = get_logger(__name__)


class TestAdaptiveGovernance:
    """Test suite for adaptive governance system."""

    @pytest.fixture(autouse=True)
    def _mock_mlflow(self):
        """Prevent MLflow and Postgres connection attempts during tests."""
        from enhanced_agent_bus.feedback_handler.handler import FeedbackHandler

        with (
            patch.object(ImpactScorer, "_initialize_mlflow"),
            patch.object(AdaptiveThresholds, "_initialize_mlflow"),
            patch.object(ABTestRouter, "_ensure_initialized"),
            patch.object(FeedbackHandler, "_get_db_connection"),
            patch.object(FeedbackHandler, "initialize_schema"),
        ):
            yield

    @pytest.fixture
    def constitutional_hash(self):
        return CONSTITUTIONAL_HASH

    @pytest.fixture
    def sample_features(self):
        return ImpactFeatures(
            message_length=100,
            agent_count=3,
            tenant_complexity=0.5,
            temporal_patterns=[0.1, 0.2, 0.15],
            semantic_similarity=0.3,
            historical_precedence=2,
            resource_utilization=0.2,
            network_isolation=0.9,
        )

    @pytest.fixture
    def sample_message(self):
        return {
            "from_agent": "test-agent",
            "to_agent": "target-agent",
            "content": "Test message content",
            "tenant_id": "test-tenant",
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "metadata": {"test": True},
        }

    @pytest.fixture
    def sample_context(self):
        return {
            "active_agents": ["agent1", "agent2", "agent3"],
            "tenant_id": "test-tenant",
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    def test_impact_features_creation(self, sample_features):
        """Test ImpactFeatures dataclass creation."""
        assert sample_features.message_length == 100
        assert sample_features.agent_count == 3
        assert sample_features.risk_score == 0.0  # Default
        assert sample_features.confidence_level == 0.0  # Default

    def test_governance_metrics_creation(self):
        """Test GovernanceMetrics dataclass creation."""
        metrics = GovernanceMetrics()
        assert metrics.constitutional_compliance_rate == 0.0
        assert isinstance(metrics.compliance_trend, list)
        assert isinstance(metrics.accuracy_trend, list)

    def test_impact_level_enum(self):
        """Test ImpactLevel enum values."""
        assert ImpactLevel.NEGLIGIBLE.value == "negligible"
        assert ImpactLevel.CRITICAL.value == "critical"

    def test_governance_mode_enum(self):
        """Test GovernanceMode enum values."""
        assert GovernanceMode.STRICT.value == "strict"
        assert GovernanceMode.ADAPTIVE.value == "adaptive"
        assert GovernanceMode.EVOLVING.value == "evolving"

    async def test_adaptive_thresholds_initialization(self, constitutional_hash):
        """Test AdaptiveThresholds initialization."""
        thresholds = AdaptiveThresholds(constitutional_hash)

        assert thresholds.constitutional_hash == constitutional_hash
        assert not thresholds.model_trained
        assert thresholds.base_thresholds[ImpactLevel.CRITICAL] == 0.95

    def test_adaptive_thresholds_base_values(self, constitutional_hash):
        """Test base threshold values."""
        thresholds = AdaptiveThresholds(constitutional_hash)

        assert thresholds.base_thresholds[ImpactLevel.NEGLIGIBLE] == 0.1
        assert thresholds.base_thresholds[ImpactLevel.LOW] == 0.3
        assert thresholds.base_thresholds[ImpactLevel.MEDIUM] == 0.6
        assert thresholds.base_thresholds[ImpactLevel.HIGH] == 0.8
        assert thresholds.base_thresholds[ImpactLevel.CRITICAL] == 0.95

    async def test_impact_scorer_initialization(self, constitutional_hash):
        """Test ImpactScorer initialization."""
        scorer = ImpactScorer(constitutional_hash)

        assert scorer.constitutional_hash == constitutional_hash
        assert not scorer.model_trained
        assert len(scorer.training_samples) == 0

    async def test_impact_scorer_rule_based_scoring(self, constitutional_hash, sample_features):
        """Test rule-based impact scoring."""
        scorer = ImpactScorer(constitutional_hash)

        risk_score = scorer._rule_based_risk_score(sample_features)
        assert 0.0 <= risk_score <= 1.0

        # Higher message length should increase risk
        high_risk_features = sample_features
        high_risk_features.message_length = 10000
        high_risk_score = scorer._rule_based_risk_score(high_risk_features)
        assert high_risk_score > risk_score

    async def test_governance_engine_initialization(self, constitutional_hash):
        """Test AdaptiveGovernanceEngine initialization."""
        engine = AdaptiveGovernanceEngine(constitutional_hash)

        assert engine.constitutional_hash == constitutional_hash
        assert engine.mode == GovernanceMode.ADAPTIVE
        assert len(engine.decision_history) == 0

    async def test_governance_engine_evaluate_decision(
        self, constitutional_hash, sample_message, sample_context
    ):
        """Test governance decision evaluation."""
        engine = AdaptiveGovernanceEngine(constitutional_hash)

        # Mock the impact scorer to return known features
        mock_features = ImpactFeatures(
            message_length=50,
            agent_count=2,
            tenant_complexity=0.3,
            temporal_patterns=[0.1],
            semantic_similarity=0.2,
            historical_precedence=1,
            resource_utilization=0.1,
            network_isolation=0.8,
            risk_score=0.3,
            confidence_level=0.8,
        )

        engine.impact_scorer.assess_impact = AsyncMock(return_value=mock_features)

        decision = await engine.evaluate_governance_decision(sample_message, sample_context)

        assert isinstance(decision, GovernanceDecision)
        assert decision.action_allowed is True  # Low risk should be allowed
        assert decision.impact_level == ImpactLevel.LOW
        assert 0.0 <= decision.confidence_score <= 1.0
        assert isinstance(decision.reasoning, str)
        assert len(decision.reasoning) > 0

    def test_governance_decision_creation(self, sample_features):
        """Test GovernanceDecision creation."""
        decision = GovernanceDecision(
            action_allowed=True,
            impact_level=ImpactLevel.LOW,
            confidence_score=0.85,
            reasoning="Test reasoning",
            recommended_threshold=0.4,
            features_used=sample_features,
        )

        assert decision.action_allowed is True
        assert decision.impact_level == ImpactLevel.LOW
        assert decision.confidence_score == 0.85
        assert decision.reasoning == "Test reasoning"
        assert decision.recommended_threshold == 0.4
        assert decision.features_used == sample_features

    async def test_global_governance_functions(
        self, constitutional_hash, sample_message, sample_context
    ):
        """Test global governance functions."""
        # Initialize governance
        governance = await initialize_adaptive_governance(constitutional_hash)
        assert governance is not None

        # Get governance instance
        retrieved = get_adaptive_governance()
        assert retrieved == governance

        # Test evaluation
        decision = await evaluate_message_governance(sample_message, sample_context)
        assert isinstance(decision, GovernanceDecision)

        # Test feedback
        provide_governance_feedback(decision, outcome_success=True)

    def test_impact_level_classification(self, constitutional_hash):
        """Test impact level classification from risk scores."""
        engine = AdaptiveGovernanceEngine(constitutional_hash)

        assert engine._classify_impact_level(0.05) == ImpactLevel.NEGLIGIBLE
        assert engine._classify_impact_level(0.2) == ImpactLevel.LOW
        assert engine._classify_impact_level(0.4) == ImpactLevel.MEDIUM
        assert engine._classify_impact_level(0.7) == ImpactLevel.HIGH
        assert engine._classify_impact_level(0.9) == ImpactLevel.CRITICAL

    async def test_governance_engine_feedback(self, constitutional_hash):
        """Test feedback mechanism in governance engine."""
        engine = AdaptiveGovernanceEngine(constitutional_hash)

        # Create a mock decision
        features = ImpactFeatures(
            message_length=100,
            agent_count=1,
            tenant_complexity=0.1,
            temporal_patterns=[],
            semantic_similarity=0.1,
            historical_precedence=0,
            resource_utilization=0.1,
            network_isolation=0.9,
        )

        decision = GovernanceDecision(
            action_allowed=True,
            impact_level=ImpactLevel.LOW,
            confidence_score=0.8,
            reasoning="Test decision",
            recommended_threshold=0.3,
            features_used=features,
        )

        # Populate decision history first
        await engine.evaluate_governance_decision({"content": "test"}, {"active_agents": []})

        # Provide feedback
        engine.provide_feedback(decision, outcome_success=True)

        # Check that feedback was recorded (implementation would update models)
        assert len(engine.decision_history) >= 1

    async def test_adaptive_thresholds_learning(self, constitutional_hash, sample_features):
        """Test adaptive thresholds learning capability."""
        thresholds = AdaptiveThresholds(constitutional_hash)

        # Create mock decision
        decision = GovernanceDecision(
            action_allowed=True,
            impact_level=ImpactLevel.MEDIUM,
            confidence_score=0.8,
            reasoning="Learning test",
            recommended_threshold=0.7,
            features_used=sample_features,
        )

        # Update model
        thresholds.update_model(decision, outcome_success=True)

        # Check that training data was stored
        assert len(thresholds.training_data) == 1
        assert thresholds.training_data[0]["target"] != 0  # Should have learning signal

    def test_threshold_bounds_checking(self, constitutional_hash, sample_features):
        """Test that adaptive thresholds stay within bounds."""
        thresholds = AdaptiveThresholds(constitutional_hash)

        # Test with extreme values
        extreme_features = ImpactFeatures(
            message_length=1000000,  # Very high
            agent_count=1000,  # Very high
            tenant_complexity=1.0,  # Maximum
            temporal_patterns=[1.0, 1.0, 1.0],  # All high
            semantic_similarity=1.0,  # Maximum
            historical_precedence=1000,  # Very high
            resource_utilization=1.0,  # Maximum
            network_isolation=0.0,  # Minimum
        )

        threshold = thresholds.get_adaptive_threshold(ImpactLevel.CRITICAL, extreme_features)

        # Should be clamped to valid range
        assert 0.0 <= threshold <= 1.0

    async def test_governance_engine_shutdown(self, constitutional_hash):
        """Test governance engine shutdown."""
        engine = AdaptiveGovernanceEngine(constitutional_hash)

        # Should not raise exceptions
        await engine.shutdown()

        # Should be able to shutdown multiple times safely
        await engine.shutdown()

    async def test_metrics_update(self, constitutional_hash, sample_features):
        """Test metrics update functionality."""
        engine = AdaptiveGovernanceEngine(constitutional_hash)

        # Create mock decision
        decision = GovernanceDecision(
            action_allowed=True,
            impact_level=ImpactLevel.MEDIUM,
            confidence_score=0.9,
            reasoning="Metrics test",
            recommended_threshold=0.6,
            features_used=sample_features,
        )

        # Populate decision history first
        await engine.evaluate_governance_decision({"content": "test"}, {"active_agents": []})

        # Update metrics
        engine._update_metrics(decision, response_time=0.005)

        # Check metrics were updated
        assert engine.metrics.average_response_time > 0
        assert len(engine.decision_history) == 1

    async def test_reasoning_generation(self, constitutional_hash, sample_features):
        """Test reasoning generation for decisions."""
        engine = AdaptiveGovernanceEngine(constitutional_hash)

        reasoning = engine._generate_reasoning(
            action_allowed=True,
            features=ImpactFeatures(
                message_length=100,
                agent_count=1,
                tenant_complexity=0.1,
                temporal_patterns=[],
                semantic_similarity=0.1,
                historical_precedence=0,
                resource_utilization=0.1,
                network_isolation=0.9,
                risk_score=0.2,
                confidence_level=0.8,
            ),
            threshold=0.3,
        )

        assert isinstance(reasoning, str)
        assert len(reasoning) > 0
        assert "ALLOWED" in reasoning.upper()
        assert "risk score" in reasoning.lower()

    @pytest.mark.integration
    async def test_full_governance_workflow(
        self, constitutional_hash, sample_message, sample_context
    ):
        """Integration test for full governance workflow."""
        # Initialize governance
        governance = await initialize_adaptive_governance(constitutional_hash)

        try:
            # Make decision
            decision = await governance.evaluate_governance_decision(sample_message, sample_context)
            assert isinstance(decision, GovernanceDecision)

            # Provide feedback
            governance.provide_feedback(decision, outcome_success=True)

            # Check metrics updated
            assert governance.metrics.constitutional_compliance_rate >= 0

        finally:
            # Cleanup
            await governance.shutdown()


if __name__ == "__main__":
    # Run basic smoke tests
    logger.info("Running Adaptive Governance smoke tests...")

    # Test basic imports
    try:
        from enhanced_agent_bus.adaptive_governance import (
            AdaptiveGovernanceEngine,
        )

        logger.info("✅ Imports successful")
    except ImportError as e:
        logger.error(f"❌ Import failed: {e}")
        exit(1)

    # Test basic instantiation
    try:
        engine = AdaptiveGovernanceEngine("test-hash")
        logger.info("✅ Engine instantiation successful")
    except (RuntimeError, ValueError, TypeError, AssertionError) as e:
        logger.error(f"❌ Engine instantiation failed: {e}")
        exit(1)

    logger.info("✅ All smoke tests passed!")
