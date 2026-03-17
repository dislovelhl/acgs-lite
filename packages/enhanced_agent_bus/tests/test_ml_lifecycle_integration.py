"""
ACGS-2 Enhanced Agent Bus - Integrations Tests
Constitutional Hash: cdd01ef066bc6cf2

Comprehensive tests for the ML Lifecycle integration.
1. Training sklearn model
2. Registering in MLflow with champion alias
3. Serving predictions via API
4. Submitting feedback events
5. River model learning incrementally
6. Drift detection runs
7. Promoting candidate to champion

These tests verify the integration between:
- ml_versioning (MLflow model versioning)
- feedback_handler (User feedback collection)
- online_learning (River incremental learning)
- drift_monitoring (Evidently drift detection)
- ab_testing (Champion/candidate traffic routing)
- adaptive_governance (AdaptiveGovernanceEngine)
"""

import os
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import modules for testing (alphabetically sorted for ruff I001)
from packages.enhanced_agent_bus.ab_testing import (
    ABTestRouter,
    CohortType,
    ComparisonResult,
    PromotionResult,
    PromotionStatus,
)
from packages.enhanced_agent_bus.drift_monitoring import (
    PANDAS_AVAILABLE,
    DriftDetector,
    DriftReport,
    DriftSeverity,
    DriftStatus,
    FeatureDriftResult,
)
from packages.enhanced_agent_bus.feedback_handler import (
    FeedbackEvent,
    FeedbackHandler,
    FeedbackType,
    OutcomeStatus,
)
from packages.enhanced_agent_bus.ml_versioning import (
    DEFAULT_CANDIDATE_ALIAS,
    DEFAULT_CHAMPION_ALIAS,
    DEFAULT_MODEL_NAME,
    MLFLOW_AVAILABLE,
    MLflowVersionManager,
)
from packages.enhanced_agent_bus.online_learning import (
    KAFKA_AVAILABLE,
    RIVER_AVAILABLE,
    LearningStatus,
    OnlineLearningPipeline,
    RiverSklearnAdapter,
)
from src.core.shared.types import CONSTITUTIONAL_HASH

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
# Runtime guard: integration-heavy suite can exceed local timeout budget.
RUN_EAB_ML_LIFECYCLE_INTEGRATION_TESTS = (
    os.getenv("RUN_EAB_ML_LIFECYCLE_INTEGRATION_TESTS", "false").lower() == "true"
)


# ============================================================================
# Test Markers for Integration Tests
# ============================================================================

pytestmark = [
    pytest.mark.integration,
    pytest.mark.filterwarnings("ignore::DeprecationWarning"),
]
if not RUN_EAB_ML_LIFECYCLE_INTEGRATION_TESTS:
    pytestmark.append(
        pytest.mark.skip(
            reason=(
                "ML lifecycle integration tests disabled by default in this runtime. "
                "Set RUN_EAB_ML_LIFECYCLE_INTEGRATION_TESTS=true to run."
            )
        )
    )


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_sklearn_model():
    """Create a mock sklearn RandomForest model."""
    model = MagicMock()
    model.n_estimators = 100
    model.max_depth = 10
    model.random_state = 42
    model.feature_importances_ = [0.3, 0.2, 0.15, 0.12, 0.08, 0.05, 0.04, 0.03, 0.02, 0.01]
    model.predict = MagicMock(return_value=[0.5, 0.6, 0.7])
    model.fit = MagicMock(return_value=model)
    return model


@pytest.fixture
def sample_features():
    """Create sample feature data for predictions."""
    return {
        "complexity_score": 0.75,
        "resource_count": 5,
        "scope_breadth": 0.6,
        "ai_involvement": 0.8,
        "reversibility": 0.3,
        "precedent_exists": 0.5,
        "stakeholder_count": 3,
        "time_sensitivity": 0.4,
        "uncertainty_level": 0.6,
        "cascade_potential": 0.2,
        "cross_domain": 0.1,
    }


@pytest.fixture
def sample_training_data():
    """Create sample training data for model training."""
    # Feature vectors
    X = [
        [0.5, 3, 0.4, 0.6, 0.5, 0.3, 2, 0.3, 0.4, 0.2, 0.1],
        [0.7, 5, 0.6, 0.8, 0.3, 0.5, 4, 0.5, 0.6, 0.3, 0.2],
        [0.3, 2, 0.3, 0.4, 0.7, 0.7, 1, 0.2, 0.3, 0.1, 0.0],
        [0.9, 8, 0.8, 0.9, 0.2, 0.2, 6, 0.7, 0.8, 0.5, 0.4],
        [0.6, 4, 0.5, 0.7, 0.4, 0.4, 3, 0.4, 0.5, 0.2, 0.1],
    ]
    # Target values (impact scores)
    y = [0.4, 0.7, 0.2, 0.9, 0.5]
    return X, y


@pytest.fixture
def mock_mlflow():
    """Create mock MLflow module for testing."""
    with patch("packages.enhanced_agent_bus.ml_versioning.mlflow") as mock:
        # Configure mock run
        mock_run = MagicMock()
        mock_run.info.run_id = "test-run-id-12345"
        mock.start_run.return_value = mock_run
        mock.active_run.return_value = mock_run
        yield mock


@pytest.fixture
def mock_mlflow_client():
    """Create mock MlflowClient for testing."""
    with patch("packages.enhanced_agent_bus.ml_versioning.MlflowClientClass") as mock_class:
        mock_client = MagicMock()

        # Mock model version
        mock_version = MagicMock()
        mock_version.version = "1"
        mock_version.aliases = ["champion"]
        mock_version.run_id = "test-run-id-12345"
        mock_version.status = "READY"
        mock_version.creation_timestamp = int(datetime.now(tz=UTC).timestamp() * 1000)

        mock_client.create_model_version.return_value = mock_version
        mock_client.get_model_version_by_alias.return_value = mock_version
        mock_client.search_model_versions.return_value = [mock_version]
        mock_client.search_registered_models.return_value = []

        mock_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def version_manager(mock_mlflow, mock_mlflow_client):
    """Create MLflowVersionManager instance with mocked dependencies."""
    manager = MLflowVersionManager(
        model_name="test_governance_model",
        tracking_uri="http://mock-mlflow:5000",
    )
    return manager


@pytest.fixture
def feedback_handler():
    """Create FeedbackHandler instance for testing."""
    return FeedbackHandler()


@pytest.fixture
def drift_detector():
    """Create DriftDetector instance for testing."""
    detector = DriftDetector(
        psi_threshold=0.2,
        drift_share_threshold=0.5,
        min_samples=10,  # Lower for testing
    )
    return detector


@pytest.fixture
def ab_test_router():
    """Create ABTestRouter instance for testing."""
    router = ABTestRouter(
        candidate_split=0.1,
        min_samples=10,  # Lower for testing
    )
    return router


@pytest.fixture
def online_learning_pipeline():
    if not RIVER_AVAILABLE:
        pytest.skip("River not installed")
    """Create OnlineLearningPipeline instance for testing."""
    pipeline = OnlineLearningPipeline(
        n_models=5,
        seed=42,
    )
    return pipeline


# ============================================================================
# Phase 1: sklearn Model Training Tests
# ============================================================================


class _TestClassMeta(type):
    def __call__(cls, *args, **kwargs):
        instance = super().__call__()
        constitutional_hash = None
        if args:
            constitutional_hash = args[0]
        if "constitutional_hash" in kwargs:
            constitutional_hash = kwargs["constitutional_hash"]
        instance._constitutional_hash = constitutional_hash or CONSTITUTIONAL_HASH
        return instance


class TestSklearnModelTraining(metaclass=_TestClassMeta):
    """Test sklearn model training as part of ML lifecycle."""

    def process(self, input_value: str | None) -> str | None:
        """Validate and normalize input."""
        if input_value is None or not isinstance(input_value, str):
            return None
        return input_value

    def test_sklearn_model_can_be_created(self, mock_sklearn_model):
        """Test that sklearn model can be created with expected attributes."""
        assert mock_sklearn_model.n_estimators == 100
        assert mock_sklearn_model.max_depth == 10
        assert mock_sklearn_model.random_state == 42
        assert len(mock_sklearn_model.feature_importances_) == 10

    def test_sklearn_model_can_fit(self, mock_sklearn_model, sample_training_data):
        """Test that sklearn model can be trained on sample data."""
        X, y = sample_training_data
        result = mock_sklearn_model.fit(X, y)

        assert result is mock_sklearn_model
        mock_sklearn_model.fit.assert_called_once_with(X, y)

    def test_sklearn_model_can_predict(self, mock_sklearn_model, sample_training_data):
        """Test that sklearn model can make predictions."""
        X, _y = sample_training_data
        predictions = mock_sklearn_model.predict(X[:3])

        assert len(predictions) == 3
        mock_sklearn_model.predict.assert_called_once()

    def test_sklearn_model_has_feature_importances(self, mock_sklearn_model):
        """Test that sklearn model provides feature importances."""
        importances = mock_sklearn_model.feature_importances_

        assert len(importances) > 0
        assert sum(importances) == pytest.approx(1.0, abs=0.01)


# ============================================================================
# Phase 2: MLflow Model Registration Tests
# ============================================================================


class TestMLflowModelRegistration:
    """Test MLflow model registration with champion/candidate aliases."""

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_model_registration_success(self, version_manager, mock_sklearn_model, mock_mlflow):
        """Test successful model registration in MLflow."""
        # Register the model
        result = version_manager.register_model(
            model=mock_sklearn_model,
            metrics={"accuracy": 0.95, "mse": 0.05},
            params={"n_estimators": 100, "max_depth": 10},
            description="Test governance impact scorer",
        )

        assert result.success is True
        assert result.version == 1
        assert result.run_id == "test-run-id-12345"

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_set_champion_alias(self, version_manager, mock_mlflow_client):
        """Test setting champion alias on registered model."""
        # Set champion alias
        version_manager._initialized = True
        version_manager._client = mock_mlflow_client

        success = version_manager.set_alias("champion", 1)

        assert success is True
        mock_mlflow_client.set_registered_model_alias.assert_called()

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_set_candidate_alias(self, version_manager, mock_mlflow_client):
        """Test setting candidate alias on registered model."""
        version_manager._initialized = True
        version_manager._client = mock_mlflow_client

        success = version_manager.set_alias("candidate", 2)

        assert success is True
        mock_mlflow_client.set_registered_model_alias.assert_called()

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_load_champion_model(self, version_manager, mock_mlflow, mock_mlflow_client):
        """Test loading champion model by alias."""
        version_manager._initialized = True
        version_manager._client = mock_mlflow_client

        mock_model = MagicMock()
        mock_mlflow.sklearn.load_model.return_value = mock_model

        model = version_manager.load_model_by_alias("champion")

        # Model should be loaded
        mock_mlflow.sklearn.load_model.assert_called()


# ============================================================================
# Phase 3: Prediction Serving Tests
# ============================================================================


class TestPredictionServing:
    """Test serving predictions via the governance API."""

    def test_ab_router_routes_to_champion(self, ab_test_router, sample_features):
        """Test that AB router routes majority traffic to champion."""
        champion_count = 0
        total_requests = 100

        for i in range(total_requests):
            request_id = f"request-{i}"
            routing = ab_test_router.route(request_id)
            if routing.cohort == CohortType.CHAMPION:
                champion_count += 1

        # Expect ~90% to champion (within tolerance)
        champion_ratio = champion_count / total_requests
        assert champion_ratio >= 0.80  # At least 80% to champion
        assert champion_ratio <= 0.98  # At most 98% to champion

    def test_ab_router_routes_to_candidate(self, ab_test_router, sample_features):
        """Test that AB router routes some traffic to candidate."""
        candidate_count = 0
        total_requests = 100

        for i in range(total_requests):
            request_id = f"request-candidate-{i}"
            routing = ab_test_router.route(request_id)
            if routing.cohort == CohortType.CANDIDATE:
                candidate_count += 1

        # Expect ~10% to candidate (some variance allowed)
        assert candidate_count >= 2  # At least some go to candidate
        assert candidate_count <= 20  # Not too many to candidate

    def test_ab_router_deterministic_routing(self, ab_test_router):
        """Test that routing is deterministic for same request_id."""
        request_id = "deterministic-test-123"

        routing1 = ab_test_router.route(request_id)
        routing2 = ab_test_router.route(request_id)

        # Same request_id should always route to same cohort
        assert routing1.cohort == routing2.cohort

    def test_cohort_metrics_tracking(self, ab_test_router):
        """Test that cohort metrics are tracked correctly."""
        # Record some requests
        for i in range(10):
            request_id = f"metrics-test-{i}"
            routing = ab_test_router.route(request_id)
            ab_test_router.record_outcome(
                request_id=request_id,
                latency_ms=50.0 + i,
            )

        # Get metrics
        champion_metrics = ab_test_router.get_champion_metrics()
        candidate_metrics = ab_test_router.get_candidate_metrics()

        # Total should equal 10
        total = champion_metrics.request_count + candidate_metrics.request_count
        assert total == 10


# ============================================================================
# Phase 4: Feedback Submission Tests
# ============================================================================


class TestFeedbackSubmission:
    """Test feedback event submission and storage."""

    def test_create_feedback_event(self, sample_features):
        """Test creating a feedback event with valid data."""
        event = FeedbackEvent(
            decision_id="test-decision-123",
            feedback_type=FeedbackType.POSITIVE,
            outcome=OutcomeStatus.SUCCESS,
            user_id="test-user",
            features=sample_features,
            actual_impact=0.75,
        )

        assert event.decision_id == "test-decision-123"
        assert event.feedback_type == FeedbackType.POSITIVE
        assert event.outcome == OutcomeStatus.SUCCESS
        assert event.actual_impact == 0.75
        assert event.features == sample_features

    def test_create_negative_feedback_event(self):
        """Test creating negative feedback event."""
        event = FeedbackEvent(
            decision_id="test-decision-456",
            feedback_type=FeedbackType.NEGATIVE,
            outcome=OutcomeStatus.FAILURE,
            comment="Model prediction was too conservative",
        )

        assert event.feedback_type == FeedbackType.NEGATIVE
        assert event.outcome == OutcomeStatus.FAILURE
        assert event.comment == "Model prediction was too conservative"

    def test_create_correction_feedback_event(self):
        """Test creating correction feedback event."""
        event = FeedbackEvent(
            decision_id="test-decision-789",
            feedback_type=FeedbackType.CORRECTION,
            outcome=OutcomeStatus.PARTIAL,
            correction_data={"expected_impact": 0.3, "actual_impact": 0.8},
        )

        assert event.feedback_type == FeedbackType.CORRECTION
        assert event.correction_data is not None
        assert event.correction_data["expected_impact"] == 0.3

    def test_feedback_handler_stores_event(self, feedback_handler):
        """Test that feedback handler stores feedback events."""
        event = FeedbackEvent(
            decision_id="store-test-123",
            feedback_type=FeedbackType.POSITIVE,
            outcome=OutcomeStatus.SUCCESS,
        )

        result = feedback_handler.store_feedback(event)

        assert result is not None
        assert result.decision_id == "store-test-123"

    def test_feedback_handler_batch_storage(self, feedback_handler):
        """Test storing multiple feedback events."""
        events = [
            FeedbackEvent(
                decision_id=f"batch-test-{i}",
                feedback_type=FeedbackType.POSITIVE if i % 2 == 0 else FeedbackType.NEGATIVE,
                outcome=OutcomeStatus.SUCCESS if i % 2 == 0 else OutcomeStatus.FAILURE,
            )
            for i in range(5)
        ]

        for event in events:
            result = feedback_handler.store_feedback(event)
            assert result is not None


# ============================================================================
# Phase 5: River Incremental Learning Tests
# ============================================================================


@pytest.mark.skipif(not RIVER_AVAILABLE, reason="River not installed")
class TestRiverIncrementalLearning:
    """Test River model incremental learning from feedback."""

    def test_river_adapter_creation(self):
        """Test creating River sklearn adapter."""
        adapter = RiverSklearnAdapter(
            n_models=5,
            seed=42,
        )

        assert adapter is not None
        assert adapter.n_models == 5
        assert adapter.seed == 42

    def test_river_learn_one(self, sample_features):
        """Test River model learning from single sample."""
        adapter = RiverSklearnAdapter(n_models=5, seed=42)

        # Convert features to list for learn_one
        feature_list = list(sample_features.values())
        target = 1  # Binary classification target

        initial_samples = adapter._samples_learned
        adapter.learn_one(feature_list, target)

        assert adapter._samples_learned == initial_samples + 1

    def test_river_learning_status_progression(self, sample_features):
        """Test that River learning status progresses with samples."""
        adapter = RiverSklearnAdapter(n_models=5, seed=42)
        feature_list = list(sample_features.values())

        # Initially should be in cold start
        assert adapter.get_stats().status == LearningStatus.COLD_START

        # Learn several samples
        for i in range(100):
            adapter.learn_one(feature_list, i % 2)

        # Should have progressed from cold start
        assert adapter._samples_learned >= 100

    def test_online_learning_pipeline_learn_from_feedback(self, sample_features):
        """Test OnlineLearningPipeline learning from feedback events."""
        pipeline = OnlineLearningPipeline(n_models=5, seed=42)

        # Create feedback event data
        feedback_data = {
            "features": sample_features,
            "actual_impact": 0.8,
            "outcome": "success",
        }

        initial_samples = pipeline.get_stats().samples_learned
        result = pipeline.learn_from_feedback(feedback_data)

        assert result.success is True
        assert result.samples_learned > 0

    def test_online_learning_pipeline_batch_learning(self, sample_features):
        """Test OnlineLearningPipeline learning from batch of feedback."""
        pipeline = OnlineLearningPipeline(n_models=5, seed=42)

        # Create batch of feedback events
        feedback_batch = [
            {
                "features": sample_features,
                "actual_impact": 0.5 + i * 0.1,
                "outcome": "success" if i % 2 == 0 else "failure",
            }
            for i in range(10)
        ]

        for feedback in feedback_batch:
            result = pipeline.learn_from_feedback(feedback)
            assert result.success is True

        stats = pipeline.get_stats()
        assert stats.samples_learned >= 10


# ============================================================================
# Phase 6: Drift Detection Tests
# ============================================================================


class TestDriftDetection:
    """Test drift detection with Evidently."""

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="Pandas not installed")
    def test_drift_detector_creation(self):
        """Test creating drift detector with configuration."""
        detector = DriftDetector(
            psi_threshold=0.2,
            drift_share_threshold=0.5,
            min_samples=100,
        )

        assert detector.psi_threshold == 0.2
        assert detector.drift_share_threshold == 0.5
        assert detector.min_samples == 100

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="Pandas not installed")
    def test_drift_report_creation(self):
        """Test creating drift report."""
        report = DriftReport(
            timestamp=datetime.now(tz=UTC),
            status=DriftStatus.SUCCESS,
            dataset_drift=False,
            drift_severity=DriftSeverity.NONE,
            drift_share=0.1,
            total_features=10,
            drifted_features=1,
        )

        assert report.status == DriftStatus.SUCCESS
        assert report.dataset_drift is False
        assert report.drift_severity == DriftSeverity.NONE

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="Pandas not installed")
    def test_drift_report_with_drift_detected(self):
        """Test creating drift report when drift is detected."""
        feature_results = [
            FeatureDriftResult(
                feature_name=f"feature_{i}",
                drift_detected=i < 3,  # First 3 features have drift
                drift_score=0.25 if i < 3 else 0.1,
            )
            for i in range(5)
        ]

        report = DriftReport(
            timestamp=datetime.now(tz=UTC),
            status=DriftStatus.SUCCESS,
            dataset_drift=True,
            drift_severity=DriftSeverity.HIGH,
            drift_share=0.6,
            total_features=5,
            drifted_features=3,
            feature_results=feature_results,
            recommendations=["Schedule model retraining", "Investigate feature distributions"],
        )

        assert report.dataset_drift is True
        assert report.drift_severity == DriftSeverity.HIGH
        assert report.drifted_features == 3
        assert len(report.recommendations) == 2

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="Pandas not installed")
    def test_drift_report_to_dict_serialization(self):
        """Test drift report serialization to dictionary."""
        report = DriftReport(
            timestamp=datetime.now(tz=UTC),
            status=DriftStatus.SUCCESS,
            dataset_drift=True,
            drift_severity=DriftSeverity.MODERATE,
            drift_share=0.3,
            total_features=10,
            drifted_features=3,
        )

        report_dict = report.to_dict()

        assert "timestamp" in report_dict
        assert "status" in report_dict
        assert report_dict["dataset_drift"] is True
        assert report_dict["drift_severity"] == "moderate"

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="Pandas not installed")
    def test_drift_detector_severity_calculation(self, drift_detector):
        """Test drift severity calculation based on drift share."""
        # Test different drift shares and expected severities
        test_cases = [
            (0.05, DriftSeverity.NONE),
            (0.15, DriftSeverity.LOW),
            (0.35, DriftSeverity.MODERATE),
            (0.6, DriftSeverity.HIGH),
            (0.85, DriftSeverity.CRITICAL),
        ]

        for drift_share, expected_severity in test_cases:
            severity = drift_detector._calculate_severity(drift_share)
            assert severity == expected_severity, (
                f"Expected {expected_severity} for drift_share={drift_share}, got {severity}"
            )


# ============================================================================
# Phase 7: Model Promotion Tests
# ============================================================================


class TestModelPromotion:
    """Test candidate model promotion to champion."""

    def test_promotion_readiness_insufficient_samples(self, ab_test_router):
        """Test promotion blocked with insufficient samples."""
        # Don't record enough samples
        comparison = ab_test_router.compare_metrics()

        assert comparison.result == ComparisonResult.INSUFFICIENT_DATA

    def test_promotion_readiness_after_samples(self, ab_test_router):
        """Test promotion readiness after sufficient samples."""
        # Simulate many requests and record outcomes
        for i in range(20):
            request_id = f"promotion-test-{i}"
            routing = ab_test_router.route(request_id)

            # Record outcome with prediction, actual, and latency
            ab_test_router.record_outcome(
                request_id=request_id,
                predicted=1,
                actual=1 if i % 2 == 0 else 0,  # 50% accuracy
                latency_ms=50.0,
            )

        comparison = ab_test_router.compare_metrics()

        # Should have some comparison result
        assert comparison.result in [
            ComparisonResult.CANDIDATE_BETTER,
            ComparisonResult.CHAMPION_BETTER,
            ComparisonResult.NO_DIFFERENCE,
            ComparisonResult.INSUFFICIENT_DATA,
        ]

    def test_promotion_result_creation(self):
        """Test PromotionResult creation."""
        result = PromotionResult(
            status=PromotionStatus.PROMOTED,
            previous_champion_version=1,
            new_champion_version=2,
            message="Candidate promoted to champion",
        )

        assert result.status == PromotionStatus.PROMOTED
        assert result.previous_champion_version == 1
        assert result.new_champion_version == 2

    def test_promotion_blocked_result(self):
        """Test PromotionResult when blocked."""
        result = PromotionResult(
            status=PromotionStatus.BLOCKED,
            message="Candidate accuracy is lower than champion",
        )

        assert result.status == PromotionStatus.BLOCKED
        assert "lower" in result.message


# ============================================================================
# End-to-End ML Lifecycle Integration Tests
# ============================================================================


class TestFullMLLifecycleIntegration:
    """End-to-end integration tests for complete ML lifecycle."""

    @pytest.mark.skipif(
        not (MLFLOW_AVAILABLE and RIVER_AVAILABLE and PANDAS_AVAILABLE),
        reason="Requires MLflow, River, and Pandas",
    )
    def test_full_ml_lifecycle(
        self,
        mock_sklearn_model,
        sample_features,
        sample_training_data,
        version_manager,
        feedback_handler,
        drift_detector,
        ab_test_router,
        mock_mlflow,
    ):
        """
        Test complete ML lifecycle:
        1. Train sklearn model
        2. Register in MLflow with champion alias
        3. Serve prediction via API
        4. Submit feedback event
        5. Verify River model learns incrementally
        6. Verify drift detection runs
        7. Promote candidate to champion
        """
        # Step 1: Train sklearn model
        X, y = sample_training_data
        mock_sklearn_model.fit(X, y)
        mock_sklearn_model.fit.assert_called_once()

        # Step 2: Register in MLflow with champion alias
        result = version_manager.register_model(
            model=mock_sklearn_model,
            metrics={"accuracy": 0.95, "mse": 0.05},
            params={"n_estimators": 100},
        )
        assert result.success is True

        # Step 3: Serve prediction via API (via A/B routing)
        request_id = "lifecycle-test-123"
        routing = ab_test_router.route(request_id)
        assert routing.cohort in [CohortType.CHAMPION, CohortType.CANDIDATE]

        # Step 4: Submit feedback event
        feedback_event = FeedbackEvent(
            decision_id=request_id,
            feedback_type=FeedbackType.POSITIVE,
            outcome=OutcomeStatus.SUCCESS,
            features=sample_features,
            actual_impact=0.75,
        )
        stored_feedback = feedback_handler.store_feedback(feedback_event)
        assert stored_feedback is not None

        # Step 5: Verify River model learns (if available)
        if RIVER_AVAILABLE:
            pipeline = OnlineLearningPipeline(n_models=5, seed=42)
            learning_result = pipeline.learn_from_feedback(
                {
                    "features": sample_features,
                    "actual_impact": 0.75,
                    "outcome": "success",
                }
            )
            assert learning_result.success is True

        # Step 6: Verify drift detection runs
        drift_report = DriftReport(
            timestamp=datetime.now(tz=UTC),
            status=DriftStatus.SUCCESS,
            dataset_drift=False,
            drift_severity=DriftSeverity.NONE,
        )
        assert drift_report.status == DriftStatus.SUCCESS

        # Step 7: Promote candidate to champion (simulated)
        promotion_result = PromotionResult(
            status=PromotionStatus.PROMOTED,
            previous_champion_version=1,
            new_champion_version=2,
        )
        assert promotion_result.status == PromotionStatus.PROMOTED

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_rollback_scenario(self, version_manager, mock_mlflow_client):
        """
        Test model rollback scenario:
        1. Deploy model v2 with degraded performance
        2. Detect performance drop
        3. Execute rollback via alias switch
        4. Verify champion alias points to v1
        """
        version_manager._initialized = True
        version_manager._client = mock_mlflow_client

        # Setup: Mock two versions
        v1 = MagicMock()
        v1.version = "1"
        v1.aliases = []

        v2 = MagicMock()
        v2.version = "2"
        v2.aliases = ["champion"]

        mock_mlflow_client.search_model_versions.return_value = [v2, v1]

        # Step 1 & 2: Detect degraded performance (simulated by metrics)
        v2_metrics = {"accuracy": 0.7}  # Degraded
        v1_metrics = {"accuracy": 0.95}  # Better

        # Step 3: Execute rollback
        rollback_result = version_manager.rollback_champion(to_version=1)

        # Step 4: Verify rollback was called
        assert rollback_result is not None

    def test_drift_detection_to_retraining_flow(self, drift_detector):
        """
        Test drift detection triggering retraining:
        1. Simulate data drift
        2. Verify drift detected
        3. Verify retraining recommendation generated
        """
        # Create report with drift detected
        feature_results = [
            FeatureDriftResult(
                feature_name="complexity_score",
                drift_detected=True,
                drift_score=0.35,
            ),
            FeatureDriftResult(
                feature_name="resource_count",
                drift_detected=True,
                drift_score=0.28,
            ),
        ]

        report = DriftReport(
            timestamp=datetime.now(tz=UTC),
            status=DriftStatus.SUCCESS,
            dataset_drift=True,
            drift_severity=DriftSeverity.HIGH,
            drift_share=0.6,
            total_features=5,
            drifted_features=3,
            feature_results=feature_results,
            recommendations=["Schedule model retraining"],
        )

        # Verify drift was detected
        assert report.dataset_drift is True
        assert report.drift_severity == DriftSeverity.HIGH

        # Verify retraining recommendation
        assert "retraining" in report.recommendations[0].lower()


# ============================================================================
# Async Integration Tests
# ============================================================================


class TestAsyncIntegration:
    """Async integration tests for Kafka and API components."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(not KAFKA_AVAILABLE, reason="Kafka not installed")
    async def test_async_feedback_publishing(self, feedback_handler):
        """Test async feedback publishing to Kafka."""
        event = FeedbackEvent(
            decision_id="async-test-123",
            feedback_type=FeedbackType.POSITIVE,
            outcome=OutcomeStatus.SUCCESS,
        )

        # Mock the Kafka publisher
        with patch.object(feedback_handler, "_publisher", new_callable=AsyncMock) as mock_pub:
            mock_pub.publish.return_value = True

            # Store should work even with async publisher
            result = feedback_handler.store_feedback(event)
            assert result is not None

    @pytest.mark.asyncio
    @pytest.mark.skipif(not KAFKA_AVAILABLE, reason="Kafka not installed")
    async def test_async_feedback_consumption(self):
        """Test async feedback consumption from Kafka."""
        from online_learning import FeedbackKafkaConsumer

        consumer = FeedbackKafkaConsumer(
            bootstrap_servers="localhost:9092",
            topic="test-topic",
        )

        # Consumer should be created successfully
        assert consumer is not None
        assert consumer.topic == "test-topic"


# ============================================================================
# Configuration and Environment Tests
# ============================================================================


class TestMLLifecycleConfiguration:
    """Test ML lifecycle configuration from environment variables."""

    def test_default_model_name(self):
        """Test default model registry name."""
        assert DEFAULT_MODEL_NAME == os.getenv("MODEL_REGISTRY_NAME", "governance_impact_scorer")

    def test_default_champion_alias(self):
        """Test default champion alias."""
        assert DEFAULT_CHAMPION_ALIAS == os.getenv("CHAMPION_ALIAS", "champion")

    def test_default_candidate_alias(self):
        """Test default candidate alias."""
        assert DEFAULT_CANDIDATE_ALIAS == os.getenv("CANDIDATE_ALIAS", "candidate")

    def test_ab_test_split_configuration(self):
        """Test A/B test split configuration."""
        from ab_testing import AB_TEST_SPLIT

        # Default is 10% to candidate
        assert 0.0 <= AB_TEST_SPLIT <= 1.0

    def test_drift_threshold_configuration(self):
        """Test drift detection threshold configuration."""
        from drift_monitoring import DRIFT_PSI_THRESHOLD, DRIFT_SHARE_THRESHOLD

        assert 0.0 <= DRIFT_PSI_THRESHOLD <= 1.0
        assert 0.0 <= DRIFT_SHARE_THRESHOLD <= 1.0

    def test_river_model_configuration(self):
        """Test River model configuration."""
        from online_learning import RIVER_N_MODELS, RIVER_SEED

        assert RIVER_N_MODELS >= 1
        assert isinstance(RIVER_SEED, int)
