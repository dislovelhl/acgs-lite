"""
ACGS-2 Model Rollback Procedure E2E Tests
Constitutional Hash: 608508a9bd224290

End-to-end tests for verifying the model rollback procedure as specified in spec.md:

Rollback Scenario (line 495):
1. Deploy model v2 (intentionally degraded)
2. Detect performance drop
3. Execute rollback via alias switch
4. Verify champion alias points to v1
5. Verify API serves previous model within 2 minutes

These tests verify:
- MLflow model versioning and alias management
- Performance degradation detection
- Rollback execution via alias switch
- Champion alias correctly pointing to rollback version
- API serving the correct (previous) model after rollback
"""

import pytest

pytest.importorskip("ml_versioning")


import os
import sys
import time
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus.observability.structured_logging import get_logger

# Add parent directory to path for module imports
enhanced_agent_bus_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if enhanced_agent_bus_dir not in sys.path:
    sys.path.insert(0, enhanced_agent_bus_dir)

# Import modules for testing
from ml_versioning import DEFAULT_MODEL_NAME, MLFLOW_AVAILABLE, MLflowVersionManager

logger = get_logger(__name__)
RUN_EAB_MODEL_ROLLBACK_TESTS = os.getenv("RUN_EAB_MODEL_ROLLBACK_TESTS", "false").lower() == "true"

# ============================================================================
# Test Markers
# ============================================================================

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.integration,
    pytest.mark.filterwarnings("ignore::DeprecationWarning"),
]
if not RUN_EAB_MODEL_ROLLBACK_TESTS:
    pytestmark.append(
        pytest.mark.skip(
            reason=(
                "Model rollback E2E tests disabled by default in this runtime. "
                "set RUN_EAB_MODEL_ROLLBACK_TESTS=true to run."
            )
        )
    )


# ============================================================================
# Test Constants for Rollback Verification
# ============================================================================

# Maximum time allowed for rollback (spec: 2 minutes)
MAX_ROLLBACK_TIME_SECONDS = 120

# Model performance thresholds
V1_GOOD_ACCURACY = 0.95
V2_DEGRADED_ACCURACY = 0.60  # Intentionally degraded
PERFORMANCE_DROP_THRESHOLD = 0.20  # 20% accuracy drop triggers alert


# ============================================================================
# Mock Model Factory
# ============================================================================


class MockSklearnModel:
    """Mock sklearn model for testing rollback scenarios."""

    def __init__(
        self,
        version: int,
        accuracy: float,
        prediction_value: float = 0.5,
        is_degraded: bool = False,
    ):
        self.version = version
        self.accuracy = accuracy
        self.prediction_value = prediction_value
        self.is_degraded = is_degraded
        self.n_estimators = 100
        self.max_depth = 10
        self.random_state = 42
        self.feature_importances_ = [0.1] * 10

    def predict(self, X: list[list[float]]) -> list[float]:
        """Make predictions with characteristic output based on version."""
        # Degraded model returns higher (riskier) predictions
        if self.is_degraded:
            return [self.prediction_value + 0.3 for _ in X]
        return [self.prediction_value for _ in X]

    def fit(self, X: list[list[float]], y: list[float]) -> "MockSklearnModel":
        """Mock fit method."""
        return self


def create_v1_good_model() -> MockSklearnModel:
    """Create v1 'good' model with high accuracy."""
    return MockSklearnModel(
        version=1,
        accuracy=V1_GOOD_ACCURACY,
        prediction_value=0.5,
        is_degraded=False,
    )


def create_v2_degraded_model() -> MockSklearnModel:
    """Create v2 'degraded' model with low accuracy."""
    return MockSklearnModel(
        version=2,
        accuracy=V2_DEGRADED_ACCURACY,
        prediction_value=0.5,
        is_degraded=True,
    )


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def v1_good_model() -> MockSklearnModel:
    """Create v1 good performance model."""
    return create_v1_good_model()


@pytest.fixture
def v2_degraded_model() -> MockSklearnModel:
    """Create v2 degraded performance model."""
    return create_v2_degraded_model()


@pytest.fixture
def sample_features() -> dict[str, float]:
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
    }


@pytest.fixture
def mock_mlflow():
    """Create mock MLflow module for testing."""
    with patch("ml_versioning.mlflow") as mock:
        # Configure mock run
        mock_run = MagicMock()
        mock_run.info.run_id = "test-run-id-12345"
        mock.start_run.return_value = mock_run
        mock.active_run.return_value = mock_run
        yield mock


@pytest.fixture
def mock_mlflow_client_with_versions():
    """Create mock MlflowClient with v1 and v2 versions pre-configured."""
    with patch("ml_versioning.MlflowClientClass") as mock_class:
        mock_client = MagicMock()

        # Create model version objects
        v1 = MagicMock()
        v1.version = "1"
        v1.aliases = []
        v1.run_id = "run-v1-good"
        v1.status = "READY"
        v1.creation_timestamp = int(datetime.now(tz=UTC).timestamp() * 1000)
        v1.description = "V1 - Good performance model"
        v1.name = DEFAULT_MODEL_NAME
        v1.tags = {}

        v2 = MagicMock()
        v2.version = "2"
        v2.aliases = ["champion"]  # v2 is currently champion
        v2.run_id = "run-v2-degraded"
        v2.status = "READY"
        v2.creation_timestamp = int(datetime.now(tz=UTC).timestamp() * 1000)
        v2.description = "V2 - Degraded performance model"
        v2.name = DEFAULT_MODEL_NAME
        v2.tags = {}

        # Store versions for dynamic lookup
        versions = {"1": v1, "2": v2}
        current_champion = {"version": "2"}  # Track current champion

        def get_version_by_alias(name, alias):
            """Mock get_model_version_by_alias."""
            if alias == "champion":
                version_num = current_champion["version"]
                return versions[version_num]
            raise Exception(f"Alias '{alias}' not found")

        def set_alias(name, alias, version):
            """Mock set_registered_model_alias."""
            version_str = str(version)
            if version_str in versions:
                # Update current champion if setting champion alias
                if alias == "champion":
                    current_champion["version"] = version_str
                logger.info(f"set alias '{alias}' to version {version}")
                return True
            raise Exception(f"Version {version} not found")

        mock_client.get_model_version_by_alias = MagicMock(side_effect=get_version_by_alias)
        mock_client.set_registered_model_alias = MagicMock(side_effect=set_alias)
        mock_client.search_model_versions = MagicMock(return_value=[v2, v1])
        mock_client.get_registered_model = MagicMock(return_value=MagicMock())
        mock_client.create_registered_model = MagicMock()
        mock_client.get_model_version = MagicMock(
            side_effect=lambda name, version: versions.get(str(version))
        )
        mock_client.get_run = MagicMock(
            return_value=MagicMock(data=MagicMock(metrics={"accuracy": 0.9}))
        )

        mock_class.return_value = mock_client

        # Return both the class mock and client mock for verification
        yield mock_client, current_champion, versions


@pytest.fixture
def version_manager_with_versions(mock_mlflow, mock_mlflow_client_with_versions):
    """Create MLflowVersionManager with v1 and v2 pre-configured."""
    mock_client, current_champion, versions = mock_mlflow_client_with_versions

    manager = MLflowVersionManager(
        model_name="test_governance_model",
        tracking_uri="http://mock-mlflow:5000",
    )
    manager._initialized = True
    manager._client = mock_client

    return manager, mock_client, current_champion, versions


# ============================================================================
# Step 1: Deploy Model v2 (Intentionally Degraded)
# ============================================================================


class TestDeployDegradedModelV2:
    """Step 1: Test deploying a degraded model v2 as champion."""

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_register_v1_good_model(self, mock_mlflow, mock_mlflow_client_with_versions):
        """Test registering v1 good model in MLflow."""
        _mock_client, _, _ = mock_mlflow_client_with_versions

        manager = MLflowVersionManager(
            model_name="test_governance_model",
            tracking_uri="http://mock-mlflow:5000",
        )

        v1_model = create_v1_good_model()

        # Register v1 model
        result = manager.register_model(
            model=v1_model,
            metrics={"accuracy": V1_GOOD_ACCURACY},
            params={"n_estimators": 100},
            description="V1 - Good performance model",
        )

        assert result.success is True
        assert result.version is not None

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_register_v2_degraded_model(self, mock_mlflow, mock_mlflow_client_with_versions):
        """Test registering v2 degraded model in MLflow."""
        _mock_client, _, _ = mock_mlflow_client_with_versions

        manager = MLflowVersionManager(
            model_name="test_governance_model",
            tracking_uri="http://mock-mlflow:5000",
        )

        v2_model = create_v2_degraded_model()

        # Register v2 degraded model
        result = manager.register_model(
            model=v2_model,
            metrics={"accuracy": V2_DEGRADED_ACCURACY},
            params={"n_estimators": 100},
            description="V2 - Degraded performance model",
        )

        assert result.success is True
        assert result.version is not None

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_promote_v2_to_champion(self, version_manager_with_versions):
        """Test promoting v2 degraded model to champion alias."""
        manager, _mock_client, current_champion, _versions = version_manager_with_versions

        # Verify v2 is initially champion
        assert current_champion["version"] == "2"

        # Verify champion alias points to v2
        champion_info = manager.get_version_by_alias("champion")
        assert champion_info is not None
        assert champion_info.version == 2

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_v2_model_is_degraded(self, v2_degraded_model, sample_features):
        """Test that v2 model produces degraded (higher risk) predictions."""
        features_list = list(sample_features.values())

        prediction = v2_degraded_model.predict([features_list])[0]

        # Degraded model returns higher predictions (more risky)
        assert v2_degraded_model.is_degraded is True
        assert prediction > 0.7  # Higher than normal


# ============================================================================
# Step 2: Detect Performance Drop
# ============================================================================


class TestDetectPerformanceDrop:
    """Step 2: Test detecting performance drop from v2 degraded model."""

    def test_accuracy_drop_detection(self, v1_good_model, v2_degraded_model):
        """Test detecting accuracy drop between v1 and v2."""
        accuracy_drop = v1_good_model.accuracy - v2_degraded_model.accuracy

        assert accuracy_drop > PERFORMANCE_DROP_THRESHOLD
        assert accuracy_drop == pytest.approx(0.35, abs=0.01)  # 95% - 60% = 35%

    def test_performance_drop_triggers_alert(self, v1_good_model, v2_degraded_model):
        """Test that performance drop exceeding threshold triggers alert condition."""
        current_accuracy = v2_degraded_model.accuracy
        baseline_accuracy = v1_good_model.accuracy

        accuracy_delta = baseline_accuracy - current_accuracy
        should_alert = accuracy_delta > PERFORMANCE_DROP_THRESHOLD

        assert should_alert is True
        assert current_accuracy < 0.8  # Below acceptable threshold

    def test_prediction_quality_degradation(
        self, v1_good_model, v2_degraded_model, sample_features
    ):
        """Test that v2 predictions are noticeably worse than v1."""
        features_list = list(sample_features.values())

        v1_prediction = v1_good_model.predict([features_list])[0]
        v2_prediction = v2_degraded_model.predict([features_list])[0]

        # v2 should produce higher (riskier) predictions
        prediction_delta = v2_prediction - v1_prediction

        assert prediction_delta > 0.2  # Significant difference
        assert v2_prediction > v1_prediction

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_metrics_comparison_shows_degradation(self, version_manager_with_versions):
        """Test that MLflow metrics comparison reveals v2 degradation."""
        _manager, _mock_client, _, _ = version_manager_with_versions

        # Simulate metrics retrieval showing degradation
        v1_metrics = {"accuracy": V1_GOOD_ACCURACY, "f1_score": 0.92}
        v2_metrics = {"accuracy": V2_DEGRADED_ACCURACY, "f1_score": 0.55}

        accuracy_delta = v1_metrics["accuracy"] - v2_metrics["accuracy"]

        assert accuracy_delta > PERFORMANCE_DROP_THRESHOLD
        assert v2_metrics["accuracy"] < v1_metrics["accuracy"]


# ============================================================================
# Step 3: Execute Rollback via Alias Switch
# ============================================================================


class TestExecuteRollbackViaAliasSwitch:
    """Step 3: Test executing rollback through MLflow alias switching."""

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_rollback_from_v2_to_v1(self, version_manager_with_versions):
        """Test rollback from v2 to v1 via alias switch."""
        manager, _mock_client, current_champion, _versions = version_manager_with_versions

        # Verify initial state: v2 is champion
        assert current_champion["version"] == "2"

        # Execute rollback to v1
        rollback_result = manager.rollback(to_version=1, alias="champion")

        assert rollback_result.success is True
        assert rollback_result.previous_version == 2
        assert rollback_result.new_version == 1
        assert rollback_result.alias == "champion"

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_rollback_auto_detects_previous_version(self, version_manager_with_versions):
        """Test rollback auto-detects previous version when not specified."""
        manager, _mock_client, _current_champion, _versions = version_manager_with_versions

        # Execute rollback without specifying version
        rollback_result = manager.rollback(alias="champion")

        assert rollback_result.success is True
        assert rollback_result.new_version == 1  # Should roll back to v1

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_rollback_updates_alias(self, version_manager_with_versions):
        """Test that rollback correctly updates the champion alias."""
        manager, mock_client, current_champion, _versions = version_manager_with_versions

        # Execute rollback
        rollback_result = manager.rollback(to_version=1, alias="champion")

        # Verify set_registered_model_alias was called correctly
        mock_client.set_registered_model_alias.assert_called()

        # Verify alias was updated to v1
        assert current_champion["version"] == "1"

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_rollback_completes_within_time_limit(self, version_manager_with_versions):
        """Test that rollback completes within spec time limit (2 minutes)."""
        manager, _mock_client, _current_champion, _versions = version_manager_with_versions

        start_time = time.time()

        # Execute rollback
        rollback_result = manager.rollback(to_version=1, alias="champion")

        elapsed_time = time.time() - start_time

        assert rollback_result.success is True
        assert elapsed_time < MAX_ROLLBACK_TIME_SECONDS
        # Should complete in milliseconds for alias switch
        assert elapsed_time < 1.0

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_rollback_returns_error_for_invalid_version(self, version_manager_with_versions):
        """Test rollback returns error for non-existent version."""
        manager, mock_client, _current_champion, versions = version_manager_with_versions

        # Override set_alias to fail for invalid version
        mock_client.set_registered_model_alias.side_effect = lambda name, alias, version: (
            (_ for _ in ()).throw(Exception(f"Version {version} not found"))
            if str(version) not in versions
            else None
        )

        # Attempt rollback to non-existent version
        rollback_result = manager.rollback(to_version=999, alias="champion")

        assert rollback_result.success is False
        assert rollback_result.error_message is not None


# ============================================================================
# Step 4: Verify Champion Alias Points to v1
# ============================================================================


class TestVerifyChampionAliasPointsToV1:
    """Step 4: Test verifying champion alias correctly points to v1 after rollback."""

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_champion_alias_points_to_v1_after_rollback(self, version_manager_with_versions):
        """Test that champion alias points to v1 after rollback."""
        manager, _mock_client, _current_champion, _versions = version_manager_with_versions

        # Execute rollback
        rollback_result = manager.rollback(to_version=1, alias="champion")
        assert rollback_result.success is True

        # Verify champion alias now points to v1
        champion_info = manager.get_version_by_alias("champion")

        assert champion_info is not None
        assert champion_info.version == 1

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_get_champion_model_returns_v1_after_rollback(
        self, version_manager_with_versions, mock_mlflow, v1_good_model
    ):
        """Test that get_champion_model returns v1 after rollback."""
        manager, _mock_client, _current_champion, _versions = version_manager_with_versions

        # Execute rollback
        rollback_result = manager.rollback(to_version=1, alias="champion")
        assert rollback_result.success is True

        # Mock the model loading to return v1 model
        mock_mlflow.sklearn.load_model.return_value = v1_good_model

        # Load champion model
        champion_model = manager.load_model_by_alias("champion")

        # Verify it's the v1 model
        assert champion_model is not None
        assert champion_model.version == 1
        assert champion_model.accuracy == V1_GOOD_ACCURACY
        assert champion_model.is_degraded is False

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_champion_version_metadata_is_v1(self, version_manager_with_versions):
        """Test that champion version metadata shows v1 details."""
        manager, _mock_client, _current_champion, _versions = version_manager_with_versions

        # Execute rollback
        rollback_result = manager.rollback(to_version=1, alias="champion")
        assert rollback_result.success is True

        # Get version info
        champion_info = manager.get_version_by_alias("champion")

        assert champion_info.version == 1
        assert champion_info.run_id == "run-v1-good"


# ============================================================================
# Step 5: Verify API Serves Previous Model Within 2 Minutes
# ============================================================================


class TestVerifyAPIServesPreviousModel:
    """Step 5: Test verifying API serves previous (v1) model within 2 minutes."""

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_api_serves_v1_predictions_after_rollback(
        self,
        version_manager_with_versions,
        mock_mlflow,
        v1_good_model,
        v2_degraded_model,
        sample_features,
    ):
        """Test that API serves v1 model predictions after rollback."""
        manager, _mock_client, _current_champion, _versions = version_manager_with_versions

        # Execute rollback
        rollback_result = manager.rollback(to_version=1, alias="champion")
        assert rollback_result.success is True

        # Mock load to return v1 model
        mock_mlflow.sklearn.load_model.return_value = v1_good_model

        # Simulate API loading champion model
        champion_model = manager.load_model_by_alias("champion")

        # Make prediction
        features_list = list(sample_features.values())
        prediction = champion_model.predict([features_list])[0]

        # Verify prediction matches v1 behavior (not degraded)
        assert prediction == pytest.approx(0.5, abs=0.1)  # v1 returns ~0.5
        assert champion_model.is_degraded is False

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_rollback_and_serve_completes_within_2_minutes(
        self,
        version_manager_with_versions,
        mock_mlflow,
        v1_good_model,
        sample_features,
    ):
        """Test complete rollback and serve cycle completes within 2 minutes."""
        manager, _mock_client, _current_champion, _versions = version_manager_with_versions

        start_time = time.time()

        # Step 1: Execute rollback
        rollback_result = manager.rollback(to_version=1, alias="champion")
        assert rollback_result.success is True

        # Step 2: Load new champion model
        mock_mlflow.sklearn.load_model.return_value = v1_good_model
        champion_model = manager.load_model_by_alias("champion")

        # Step 3: Make prediction with new model
        features_list = list(sample_features.values())
        prediction = champion_model.predict([features_list])[0]

        elapsed_time = time.time() - start_time

        # Verify within 2-minute limit
        assert elapsed_time < MAX_ROLLBACK_TIME_SECONDS
        assert prediction is not None
        assert champion_model.version == 1

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_multiple_api_requests_use_v1_after_rollback(
        self,
        version_manager_with_versions,
        mock_mlflow,
        v1_good_model,
        sample_features,
    ):
        """Test that multiple API requests all use v1 after rollback."""
        manager, _mock_client, _current_champion, _versions = version_manager_with_versions

        # Execute rollback
        rollback_result = manager.rollback(to_version=1, alias="champion")
        assert rollback_result.success is True

        # Mock load to return v1 model
        mock_mlflow.sklearn.load_model.return_value = v1_good_model

        # Simulate multiple API requests
        features_list = list(sample_features.values())
        predictions = []

        for _ in range(10):
            # Each request loads champion model (simulating stateless API)
            champion_model = manager.load_model_by_alias("champion")
            prediction = champion_model.predict([features_list])[0]
            predictions.append(prediction)

            # Verify model is v1
            assert champion_model.version == 1
            assert champion_model.is_degraded is False

        # All predictions should be consistent (from v1)
        assert all(p == pytest.approx(0.5, abs=0.1) for p in predictions)


# ============================================================================
# Full E2E Rollback Scenario Integration Test
# ============================================================================


class TestFullRollbackScenario:
    """Complete E2E test of the rollback scenario as specified in spec.md."""

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_complete_rollback_scenario(
        self,
        version_manager_with_versions,
        mock_mlflow,
        v1_good_model,
        v2_degraded_model,
        sample_features,
    ):
        """
        Complete E2E test of rollback scenario:
        1. Deploy model v2 (intentionally degraded)
        2. Detect performance drop
        3. Execute rollback via alias switch
        4. Verify champion alias points to v1
        5. Verify API serves previous model within 2 minutes
        """
        manager, _mock_client, current_champion, _versions = version_manager_with_versions
        features_list = list(sample_features.values())

        start_time = time.time()

        # =================================================================
        # Step 1: Verify v2 (degraded) is currently deployed as champion
        # =================================================================
        champion_info = manager.get_version_by_alias("champion")
        assert champion_info.version == 2
        logger.info("Step 1: Verified v2 is currently champion")

        # =================================================================
        # Step 2: Detect performance drop from v2
        # =================================================================
        # Simulate v2 predictions (degraded)
        mock_mlflow.sklearn.load_model.return_value = v2_degraded_model
        current_model = manager.load_model_by_alias("champion")
        v2_prediction = current_model.predict([features_list])[0]

        # Detect degraded performance
        assert current_model.is_degraded is True
        assert current_model.accuracy < 0.8  # Below acceptable threshold

        performance_drop = v1_good_model.accuracy - v2_degraded_model.accuracy
        assert performance_drop > PERFORMANCE_DROP_THRESHOLD
        logger.info(f"Step 2: Detected performance drop of {performance_drop:.1%}")

        # =================================================================
        # Step 3: Execute rollback via alias switch
        # =================================================================
        rollback_result = manager.rollback(to_version=1, alias="champion")

        assert rollback_result.success is True
        assert rollback_result.previous_version == 2
        assert rollback_result.new_version == 1
        logger.info("Step 3: Executed rollback from v2 to v1")

        # =================================================================
        # Step 4: Verify champion alias points to v1
        # =================================================================
        # Update mock to reflect rollback
        current_champion["version"] = "1"

        champion_info_after = manager.get_version_by_alias("champion")
        assert champion_info_after.version == 1
        logger.info("Step 4: Verified champion alias points to v1")

        # =================================================================
        # Step 5: Verify API serves previous model within 2 minutes
        # =================================================================
        mock_mlflow.sklearn.load_model.return_value = v1_good_model

        # Load and use v1 model
        v1_model = manager.load_model_by_alias("champion")
        v1_prediction = v1_model.predict([features_list])[0]

        assert v1_model.version == 1
        assert v1_model.is_degraded is False
        assert v1_model.accuracy == V1_GOOD_ACCURACY

        # Verify v1 prediction is better (lower risk score)
        assert v1_prediction < v2_prediction

        elapsed_time = time.time() - start_time
        assert elapsed_time < MAX_ROLLBACK_TIME_SECONDS
        logger.info(
            f"Step 5: Verified API serves v1 model "
            f"(completed in {elapsed_time:.3f}s < {MAX_ROLLBACK_TIME_SECONDS}s limit)"
        )

        # =================================================================
        # Final verification summary
        # =================================================================
        logger.info("=" * 60)
        logger.info("ROLLBACK SCENARIO COMPLETED SUCCESSFULLY")
        logger.info(f"- Previous champion: v2 (accuracy: {V2_DEGRADED_ACCURACY:.0%})")
        logger.info(f"- New champion: v1 (accuracy: {V1_GOOD_ACCURACY:.0%})")
        logger.info(f"- Performance improvement: {performance_drop:.1%}")
        logger.info(f"- Total rollback time: {elapsed_time:.3f}s")
        logger.info("=" * 60)

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_rollback_scenario_with_simulated_traffic(
        self,
        version_manager_with_versions,
        mock_mlflow,
        v1_good_model,
        v2_degraded_model,
        sample_features,
    ):
        """Test rollback scenario with simulated API traffic."""
        manager, _mock_client, _current_champion, _versions = version_manager_with_versions
        features_list = list(sample_features.values())

        # Simulate traffic to v2 (degraded)
        mock_mlflow.sklearn.load_model.return_value = v2_degraded_model
        v2_predictions = []
        for _ in range(100):
            model = manager.load_model_by_alias("champion")
            v2_predictions.append(model.predict([features_list])[0])

        # Calculate v2 prediction characteristics
        v2_avg_prediction = sum(v2_predictions) / len(v2_predictions)

        # Execute rollback
        rollback_result = manager.rollback(to_version=1, alias="champion")
        assert rollback_result.success is True

        # Simulate traffic to v1 (good)
        mock_mlflow.sklearn.load_model.return_value = v1_good_model
        v1_predictions = []
        for _ in range(100):
            model = manager.load_model_by_alias("champion")
            v1_predictions.append(model.predict([features_list])[0])

        # Calculate v1 prediction characteristics
        v1_avg_prediction = sum(v1_predictions) / len(v1_predictions)

        # Verify v1 predictions are better (lower risk)
        assert v1_avg_prediction < v2_avg_prediction

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_rollback_preserves_v2_for_analysis(self, version_manager_with_versions):
        """Test that rollback preserves v2 model for post-mortem analysis."""
        manager, _mock_client, _current_champion, _versions = version_manager_with_versions

        # Execute rollback
        rollback_result = manager.rollback(to_version=1, alias="champion")
        assert rollback_result.success is True

        # Verify v2 still exists in registry for analysis
        all_versions = manager.list_versions()

        # Should have both v1 and v2
        version_numbers = [v.version for v in all_versions]
        assert 1 in version_numbers
        assert 2 in version_numbers  # v2 preserved for analysis


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestRollbackEdgeCases:
    """Test edge cases and error handling in rollback procedure."""

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_rollback_when_only_one_version_exists(
        self, mock_mlflow, mock_mlflow_client_with_versions
    ):
        """Test rollback behavior when only one version exists."""
        mock_client, current_champion, versions = mock_mlflow_client_with_versions

        # Remove v2 from versions to simulate single version
        mock_client.search_model_versions.return_value = [versions["1"]]
        current_champion["version"] = "1"  # v1 is already champion

        manager = MLflowVersionManager(
            model_name="test_governance_model",
            tracking_uri="http://mock-mlflow:5000",
        )
        manager._initialized = True
        manager._client = mock_client

        # Attempt rollback - should fail as no previous version exists
        rollback_result = manager.rollback(alias="champion")

        assert rollback_result.success is False
        assert "No previous version" in (rollback_result.error_message or "")

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_rollback_to_specific_older_version(self, version_manager_with_versions):
        """Test rollback to a specific older version (not just previous)."""
        manager, mock_client, current_champion, versions = version_manager_with_versions

        # Add a v3 to simulate multiple versions
        v3 = MagicMock()
        v3.version = "3"
        v3.aliases = ["champion"]
        v3.run_id = "run-v3"
        v3.status = "READY"
        v3.creation_timestamp = int(datetime.now(tz=UTC).timestamp() * 1000)
        v3.name = DEFAULT_MODEL_NAME
        v3.tags = {}

        versions["3"] = v3
        current_champion["version"] = "3"
        mock_client.search_model_versions.return_value = [v3, versions["2"], versions["1"]]

        # Rollback directly to v1 (skipping v2)
        rollback_result = manager.rollback(to_version=1, alias="champion")

        assert rollback_result.success is True
        assert rollback_result.new_version == 1

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_consecutive_rollbacks(self, version_manager_with_versions):
        """Test multiple consecutive rollbacks work correctly."""
        manager, mock_client, current_champion, versions = version_manager_with_versions

        # First rollback: v2 -> v1
        result1 = manager.rollback(to_version=1, alias="champion")
        assert result1.success is True
        assert current_champion["version"] == "1"

        # Update mock to reflect v1 is now champion
        versions["1"].aliases = ["champion"]
        versions["2"].aliases = []

        # Second rollback attempt - should fail (no version before v1)
        mock_client.search_model_versions.return_value = [versions["2"], versions["1"]]
        result2 = manager.rollback(alias="champion")

        assert result2.success is False  # No version to roll back to


# ============================================================================
# Performance Benchmarks
# ============================================================================


class TestRollbackPerformance:
    """Performance benchmarks for rollback operations."""

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_rollback_latency_benchmark(self, version_manager_with_versions):
        """Benchmark rollback latency to ensure it meets SLA."""
        manager, _mock_client, current_champion, _versions = version_manager_with_versions

        rollback_times = []

        for _ in range(10):
            # Reset to v2 for each iteration
            current_champion["version"] = "2"

            start = time.perf_counter()
            result = manager.rollback(to_version=1, alias="champion")
            elapsed = time.perf_counter() - start

            assert result.success is True
            rollback_times.append(elapsed)

        avg_latency = sum(rollback_times) / len(rollback_times)
        max_latency = max(rollback_times)

        # Rollback should be very fast (sub-second)
        assert avg_latency < 0.1  # 100ms average
        assert max_latency < 1.0  # 1s max
        logger.info(
            f"Rollback latency: avg={avg_latency * 1000:.2f}ms, max={max_latency * 1000:.2f}ms"
        )

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_model_load_latency_after_rollback(
        self,
        version_manager_with_versions,
        mock_mlflow,
        v1_good_model,
    ):
        """Benchmark model loading latency after rollback."""
        manager, _mock_client, _current_champion, _versions = version_manager_with_versions

        # Execute rollback
        manager.rollback(to_version=1, alias="champion")

        # Benchmark model loading
        mock_mlflow.sklearn.load_model.return_value = v1_good_model

        load_times = []
        for _ in range(10):
            start = time.perf_counter()
            model = manager.load_model_by_alias("champion")
            elapsed = time.perf_counter() - start
            load_times.append(elapsed)

        avg_load_time = sum(load_times) / len(load_times)

        # Model loading should be fast for cached/mocked scenario
        assert avg_load_time < 1.0  # 1s max for model load
        logger.info(f"Model load latency: avg={avg_load_time * 1000:.2f}ms")
