"""
ACGS-2 MLflow Integration Tests
Constitutional Hash: cdd01ef066bc6cf2

Unit tests for MLflow model versioning, registration, and alias management.
Tests the ml_versioning module functionality with comprehensive mocking.
"""

import os
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from packages.enhanced_agent_bus.ml_versioning import (
    DEFAULT_CANDIDATE_ALIAS,
    DEFAULT_CHAMPION_ALIAS,
    DEFAULT_MODEL_NAME,
    MLFLOW_AVAILABLE,
    MLflowVersionManager,
    ModelVersionInfo,
    RegistrationResult,
    RollbackResult,
    get_version_manager,
    load_candidate_model,
    load_champion_model,
    register_model,
    rollback_champion,
)

from enhanced_agent_bus.observability.structured_logging import get_logger

_ML_VERSIONING_MODULE = "packages.enhanced_agent_bus.ml_versioning"

logger = get_logger(__name__)
RUN_EAB_MLFLOW_INTEGRATION_TESTS = (
    os.getenv("RUN_EAB_MLFLOW_INTEGRATION_TESTS", "false").lower() == "true"
)
if not RUN_EAB_MLFLOW_INTEGRATION_TESTS:
    pytestmark = pytest.mark.skip(
        reason=(
            "MLflow integration tests disabled by default in this runtime. "
            "Set RUN_EAB_MLFLOW_INTEGRATION_TESTS=true to run."
        )
    )


class TestModelVersionInfo:
    """Tests for ModelVersionInfo dataclass."""

    def test_model_version_info_creation(self):
        """Test creating ModelVersionInfo with required fields."""
        creation_time = datetime.now(tz=UTC)
        info = ModelVersionInfo(
            name="test_model",
            version=1,
            aliases=["champion"],
            run_id="run-123",
            status="READY",
            creation_timestamp=creation_time,
        )

        assert info.name == "test_model"
        assert info.version == 1
        assert info.aliases == ["champion"]
        assert info.run_id == "run-123"
        assert info.status == "READY"
        assert info.creation_timestamp == creation_time
        assert info.description is None
        assert info.metrics is None
        assert info.tags is None

    def test_model_version_info_with_optional_fields(self):
        """Test ModelVersionInfo with all optional fields."""
        creation_time = datetime.now(tz=UTC)
        metrics = {"accuracy": 0.95, "f1_score": 0.92}
        tags = {"environment": "production", "version": "v1.0"}

        info = ModelVersionInfo(
            name="test_model",
            version=2,
            aliases=["champion", "candidate"],
            run_id="run-456",
            status="READY",
            creation_timestamp=creation_time,
            description="Production model for governance",
            metrics=metrics,
            tags=tags,
        )

        assert info.description == "Production model for governance"
        assert info.metrics == metrics
        assert info.tags == tags

    def test_model_version_info_empty_aliases(self):
        """Test ModelVersionInfo with empty aliases list."""
        info = ModelVersionInfo(
            name="test_model",
            version=3,
            aliases=[],
            run_id="run-789",
            status="PENDING_REGISTRATION",
            creation_timestamp=datetime.now(tz=UTC),
        )

        assert info.aliases == []


class TestRegistrationResult:
    """Tests for RegistrationResult dataclass."""

    def test_registration_result_success(self):
        """Test successful registration result."""
        result = RegistrationResult(
            success=True,
            model_name="governance_impact_scorer",
            version=5,
            run_id="run-abc",
        )

        assert result.success is True
        assert result.model_name == "governance_impact_scorer"
        assert result.version == 5
        assert result.run_id == "run-abc"
        assert result.error_message is None

    def test_registration_result_failure(self):
        """Test failed registration result."""
        result = RegistrationResult(
            success=False,
            model_name="governance_impact_scorer",
            error_message="MLflow server unavailable",
        )

        assert result.success is False
        assert result.model_name == "governance_impact_scorer"
        assert result.version is None
        assert result.run_id is None
        assert result.error_message == "MLflow server unavailable"


class TestRollbackResult:
    """Tests for RollbackResult dataclass."""

    def test_rollback_result_success(self):
        """Test successful rollback result."""
        result = RollbackResult(
            success=True,
            previous_version=3,
            new_version=2,
            alias="champion",
        )

        assert result.success is True
        assert result.previous_version == 3
        assert result.new_version == 2
        assert result.alias == "champion"
        assert result.error_message is None

    def test_rollback_result_failure(self):
        """Test failed rollback result."""
        result = RollbackResult(
            success=False,
            alias="champion",
            error_message="No previous version available for rollback",
        )

        assert result.success is False
        assert result.error_message == "No previous version available for rollback"

    def test_rollback_result_default_alias(self):
        """Test rollback result uses default champion alias."""
        result = RollbackResult(success=True)
        assert result.alias == DEFAULT_CHAMPION_ALIAS


class TestMLflowVersionManager:
    """Tests for MLflowVersionManager class."""

    @pytest.fixture
    def mock_mlflow_client(self):
        """Create a mock MlflowClient."""
        client = MagicMock()
        return client

    @pytest.fixture
    def mock_mlflow(self):
        """Create mock mlflow module."""
        with patch(f"{_ML_VERSIONING_MODULE}.mlflow") as mock:
            yield mock

    @pytest.fixture
    def manager(self):
        """Create a version manager instance for testing."""
        return MLflowVersionManager(
            model_name="test_model",
            tracking_uri="http://test-mlflow:5000",
            champion_alias="champion",
            candidate_alias="candidate",
        )

    def test_manager_initialization(self):
        """Test MLflowVersionManager initialization."""
        manager = MLflowVersionManager(
            model_name="my_model",
            tracking_uri="http://mlflow:5000",
            champion_alias="production",
            candidate_alias="staging",
        )

        assert manager.model_name == "my_model"
        assert manager.tracking_uri == "http://mlflow:5000"
        assert manager.champion_alias == "production"
        assert manager.candidate_alias == "staging"
        assert manager._client is None
        assert manager._initialized is False

    def test_manager_default_values(self):
        """Test MLflowVersionManager uses default values."""
        manager = MLflowVersionManager()

        assert manager.model_name == DEFAULT_MODEL_NAME
        assert manager.champion_alias == DEFAULT_CHAMPION_ALIAS
        assert manager.candidate_alias == DEFAULT_CANDIDATE_ALIAS

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_ensure_initialized(self, manager, mock_mlflow):
        """Test _ensure_initialized creates client."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            manager._ensure_initialized()

            assert manager._initialized is True
            mock_client_class.assert_called_once_with(manager.tracking_uri)

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_client_property(self, manager, mock_mlflow):
        """Test client property initializes on access."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            client = manager.client

            assert client is mock_client
            assert manager._initialized is True

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_register_model_success(self, manager, mock_mlflow):
        """Test successful model registration."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Mock run
            mock_run = MagicMock()
            mock_run.info.run_id = "test-run-id"
            mock_mlflow.start_run.return_value = mock_run

            # Mock model version
            mock_version = MagicMock()
            mock_version.version = "1"
            mock_client.create_model_version.return_value = mock_version

            # Create mock model
            mock_model = MagicMock()

            result = manager.register_model(
                model=mock_model,
                metrics={"accuracy": 0.95},
                params={"n_estimators": 100},
                description="Test model",
            )

            assert result.success is True
            assert result.version == 1
            assert result.run_id == "test-run-id"
            mock_mlflow.log_metrics.assert_called_once_with({"accuracy": 0.95})
            mock_mlflow.log_params.assert_called_once_with({"n_estimators": 100})

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_register_model_with_existing_run(self, manager, mock_mlflow):
        """Test model registration with existing run_id."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Mock model version
            mock_version = MagicMock()
            mock_version.version = "2"
            mock_client.create_model_version.return_value = mock_version

            mock_model = MagicMock()

            result = manager.register_model(
                model=mock_model,
                run_id="existing-run-id",
            )

            assert result.success is True
            assert result.run_id == "existing-run-id"
            # Should not start a new run
            mock_mlflow.start_run.assert_not_called()

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_set_alias_success(self, manager, mock_mlflow):
        """Test setting an alias successfully."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            result = manager.set_alias(version=1, alias="champion")

            assert result is True
            mock_client.set_registered_model_alias.assert_called_once_with(
                name="test_model",
                alias="champion",
                version="1",
            )

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_promote_to_champion(self, manager, mock_mlflow):
        """Test promoting a version to champion."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            result = manager.promote_to_champion(version=3)

            assert result is True
            mock_client.set_registered_model_alias.assert_called_once_with(
                name="test_model",
                alias="champion",
                version="3",
            )

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_promote_to_candidate(self, manager, mock_mlflow):
        """Test promoting a version to candidate."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            result = manager.promote_to_candidate(version=4)

            assert result is True
            mock_client.set_registered_model_alias.assert_called_once_with(
                name="test_model",
                alias="candidate",
                version="4",
            )

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_get_version_by_alias_found(self, manager, mock_mlflow):
        """Test getting version by alias when found."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Mock version
            mock_version = MagicMock()
            mock_version.name = "test_model"
            mock_version.version = "1"
            mock_version.run_id = "run-123"
            mock_version.status = "READY"
            mock_version.creation_timestamp = 1700000000000
            mock_version.description = "Test version"
            mock_version.tags = {}
            mock_client.get_model_version_by_alias.return_value = mock_version

            # Mock run for metrics
            mock_run = MagicMock()
            mock_run.data.metrics = {"accuracy": 0.95}
            mock_client.get_run.return_value = mock_run

            info = manager.get_version_by_alias("champion")

            assert info is not None
            assert info.name == "test_model"
            assert info.version == 1

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_load_model_by_alias_success(self, manager, mock_mlflow):
        """Test loading model by alias successfully."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_model = MagicMock()
            mock_mlflow.sklearn.load_model.return_value = mock_model

            model = manager.load_model_by_alias("champion")

            assert model is mock_model
            mock_mlflow.sklearn.load_model.assert_called_once_with("models:/test_model@champion")

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_load_model_by_version_success(self, manager, mock_mlflow):
        """Test loading model by version number."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_model = MagicMock()
            mock_mlflow.sklearn.load_model.return_value = mock_model

            model = manager.load_model_by_version(3)

            assert model is mock_model
            mock_mlflow.sklearn.load_model.assert_called_once_with("models:/test_model/3")

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_get_champion_model(self, manager, mock_mlflow):
        """Test getting champion model convenience method."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_model = MagicMock()
            mock_mlflow.sklearn.load_model.return_value = mock_model

            model = manager.get_champion_model()

            assert model is mock_model
            mock_mlflow.sklearn.load_model.assert_called_with("models:/test_model@champion")

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_get_candidate_model(self, manager, mock_mlflow):
        """Test getting candidate model convenience method."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_model = MagicMock()
            mock_mlflow.sklearn.load_model.return_value = mock_model

            model = manager.get_candidate_model()

            assert model is mock_model
            mock_mlflow.sklearn.load_model.assert_called_with("models:/test_model@candidate")

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_rollback_to_specific_version(self, manager, mock_mlflow):
        """Test rollback to a specific version."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Mock current version
            mock_version = MagicMock()
            mock_version.name = "test_model"
            mock_version.version = "3"
            mock_version.run_id = "run-123"
            mock_version.status = "READY"
            mock_version.creation_timestamp = 1700000000000
            mock_version.description = None
            mock_version.tags = {}
            mock_client.get_model_version_by_alias.return_value = mock_version

            result = manager.rollback(to_version=2, alias="champion")

            assert result.success is True
            assert result.previous_version == 3
            assert result.new_version == 2
            assert result.alias == "champion"

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_rollback_auto_detect_previous(self, manager, mock_mlflow):
        """Test rollback with auto-detection of previous version."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Mock current version
            current_version = MagicMock()
            current_version.name = "test_model"
            current_version.version = "3"
            current_version.run_id = "run-123"
            current_version.status = "READY"
            current_version.creation_timestamp = 1700000000000
            current_version.description = None
            current_version.tags = {}
            mock_client.get_model_version_by_alias.return_value = current_version

            # Mock version list for auto-detection
            v1 = MagicMock()
            v1.version = "1"
            v1.name = "test_model"
            v1.run_id = "run-1"
            v1.status = "READY"
            v1.creation_timestamp = 1699000000000
            v1.description = None
            v1.tags = {}

            v2 = MagicMock()
            v2.version = "2"
            v2.name = "test_model"
            v2.run_id = "run-2"
            v2.status = "READY"
            v2.creation_timestamp = 1699500000000
            v2.description = None
            v2.tags = {}

            mock_client.search_model_versions.return_value = [v1, v2, current_version]

            result = manager.rollback(alias="champion")

            assert result.success is True
            assert result.new_version == 2  # Should pick version 2 (max version < 3)

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_rollback_no_previous_version(self, manager, mock_mlflow):
        """Test rollback when no previous version exists."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Mock current version as version 1 (no previous)
            current_version = MagicMock()
            current_version.name = "test_model"
            current_version.version = "1"
            current_version.run_id = "run-1"
            current_version.status = "READY"
            current_version.creation_timestamp = 1700000000000
            current_version.description = None
            current_version.tags = {}
            mock_client.get_model_version_by_alias.return_value = current_version

            # Mock version list with only version 1
            mock_client.search_model_versions.return_value = [current_version]

            result = manager.rollback(alias="champion")

            assert result.success is False
            assert "No previous version available" in result.error_message

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_list_versions(self, manager, mock_mlflow):
        """Test listing all model versions."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Mock versions
            v1 = MagicMock()
            v1.name = "test_model"
            v1.version = "1"
            v1.run_id = "run-1"
            v1.status = "READY"
            v1.creation_timestamp = 1699000000000
            v1.description = "Version 1"
            v1.tags = {}

            v2 = MagicMock()
            v2.name = "test_model"
            v2.version = "2"
            v2.run_id = "run-2"
            v2.status = "READY"
            v2.creation_timestamp = 1699500000000
            v2.description = "Version 2"
            v2.tags = {"env": "prod"}

            mock_client.search_model_versions.return_value = [v1, v2]
            mock_client.get_model_version_by_alias.side_effect = Exception("No alias")

            versions = manager.list_versions()

            assert len(versions) == 2
            mock_client.search_model_versions.assert_called_once_with(
                filter_string="name='test_model'"
            )

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_delete_alias_success(self, manager, mock_mlflow):
        """Test deleting an alias successfully."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            result = manager.delete_alias("old_alias")

            assert result is True
            mock_client.delete_registered_model_alias.assert_called_once_with(
                name="test_model",
                alias="old_alias",
            )

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_get_model_metrics(self, manager, mock_mlflow):
        """Test getting metrics for a model version."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Mock model version
            mock_version = MagicMock()
            mock_version.run_id = "run-123"
            mock_client.get_model_version.return_value = mock_version

            # Mock run with metrics
            mock_run = MagicMock()
            mock_run.data.metrics = {"accuracy": 0.95, "f1_score": 0.92}
            mock_client.get_run.return_value = mock_run

            metrics = manager.get_model_metrics(version=1)

            assert metrics == {"accuracy": 0.95, "f1_score": 0.92}

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_promote_candidate_to_champion(self, manager, mock_mlflow):
        """Test promoting current candidate to champion."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Mock candidate version
            mock_version = MagicMock()
            mock_version.name = "test_model"
            mock_version.version = "2"
            mock_version.run_id = "run-2"
            mock_version.status = "READY"
            mock_version.creation_timestamp = 1700000000000
            mock_version.description = None
            mock_version.tags = {}
            mock_client.get_model_version_by_alias.return_value = mock_version

            result = manager.promote_candidate_to_champion()

            assert result is True
            # Should have called set_alias with candidate's version
            mock_client.set_registered_model_alias.assert_called()


class TestModuleLevelFunctions:
    """Tests for module-level convenience functions."""

    @pytest.fixture(autouse=True)
    def reset_global_manager(self):
        """Reset the global version manager before each test."""
        import ml_versioning

        ml_versioning._version_manager = None
        yield
        ml_versioning._version_manager = None

    def test_get_version_manager_creates_singleton(self):
        """Test get_version_manager creates a singleton."""
        manager1 = get_version_manager()
        manager2 = get_version_manager()

        assert manager1 is manager2

    def test_get_version_manager_with_custom_params(self):
        """Test get_version_manager with custom parameters."""
        manager = get_version_manager(
            model_name="custom_model",
            tracking_uri="http://custom-mlflow:5000",
        )

        assert manager.model_name == "custom_model"
        assert manager.tracking_uri == "http://custom-mlflow:5000"

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_register_model_function(self):
        """Test module-level register_model function."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            with patch(f"{_ML_VERSIONING_MODULE}.mlflow") as mock_mlflow:
                # Mock run
                mock_run = MagicMock()
                mock_run.info.run_id = "global-run-id"
                mock_mlflow.start_run.return_value = mock_run

                # Mock model version
                mock_version = MagicMock()
                mock_version.version = "1"
                mock_client.create_model_version.return_value = mock_version

                mock_model = MagicMock()

                result = register_model(
                    model=mock_model,
                    metrics={"accuracy": 0.9},
                    params={"trees": 50},
                    description="Test model",
                )

                assert result.success is True

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_load_champion_model_function(self):
        """Test module-level load_champion_model function."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            with patch(f"{_ML_VERSIONING_MODULE}.mlflow") as mock_mlflow:
                mock_model = MagicMock()
                mock_mlflow.sklearn.load_model.return_value = mock_model

                model = load_champion_model()

                assert model is mock_model

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_load_candidate_model_function(self):
        """Test module-level load_candidate_model function."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            with patch(f"{_ML_VERSIONING_MODULE}.mlflow") as mock_mlflow:
                mock_model = MagicMock()
                mock_mlflow.sklearn.load_model.return_value = mock_model

                model = load_candidate_model()

                assert model is mock_model

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_rollback_champion_function(self):
        """Test module-level rollback_champion function."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            with patch(f"{_ML_VERSIONING_MODULE}.mlflow"):
                # Mock current version
                mock_version = MagicMock()
                mock_version.name = DEFAULT_MODEL_NAME
                mock_version.version = "2"
                mock_version.run_id = "run-2"
                mock_version.status = "READY"
                mock_version.creation_timestamp = 1700000000000
                mock_version.description = None
                mock_version.tags = {}
                mock_client.get_model_version_by_alias.return_value = mock_version

                result = rollback_champion(to_version=1)

                assert result.success is True
                assert result.new_version == 1


class TestMLflowUnavailable:
    """Tests for when MLflow is not available."""

    def test_mlflow_available_flag(self):
        """Test MLFLOW_AVAILABLE flag is exported."""
        # This import should succeed regardless of MLflow availability
        from ml_versioning import MLFLOW_AVAILABLE

        assert isinstance(MLFLOW_AVAILABLE, bool)

    def test_manager_without_mlflow(self):
        """Test manager gracefully handles missing MLflow."""
        # Temporarily patch MLFLOW_AVAILABLE to False
        with patch(f"{_ML_VERSIONING_MODULE}.MLFLOW_AVAILABLE", False):
            manager = MLflowVersionManager()

            # Should raise ImportError when trying to initialize
            with pytest.raises(ImportError):
                manager._ensure_initialized()


class TestErrorHandling:
    """Tests for error handling scenarios."""

    @pytest.fixture
    def manager(self):
        """Create a version manager for error testing."""
        return MLflowVersionManager(
            model_name="error_test_model",
            tracking_uri="http://test:5000",
        )

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_set_alias_mlflow_exception(self, manager):
        """Test set_alias handles MLflow exceptions."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            with patch(f"{_ML_VERSIONING_MODULE}.mlflow"):
                from ml_versioning import MlflowException

                mock_client.set_registered_model_alias.side_effect = MlflowException(
                    "Version not found"
                )

                result = manager.set_alias(version=999, alias="champion")

                assert result is False

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_load_model_not_found(self, manager):
        """Test load_model_by_alias handles not found."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            with patch(f"{_ML_VERSIONING_MODULE}.mlflow") as mock_mlflow:
                from ml_versioning import MlflowException

                mock_mlflow.sklearn.load_model.side_effect = MlflowException("Model not found")

                model = manager.load_model_by_alias("nonexistent")

                assert model is None

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_list_versions_error(self, manager):
        """Test list_versions handles errors gracefully."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            with patch(f"{_ML_VERSIONING_MODULE}.mlflow"):
                from ml_versioning import MlflowException

                mock_client.search_model_versions.side_effect = MlflowException("Search failed")

                versions = manager.list_versions()

                assert versions == []

    @pytest.mark.skipif(not MLFLOW_AVAILABLE, reason="MLflow not installed")
    def test_rollback_exception_handling(self, manager):
        """Test rollback handles exceptions gracefully."""
        with patch(f"{_ML_VERSIONING_MODULE}.MlflowClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            with patch(f"{_ML_VERSIONING_MODULE}.mlflow"):
                mock_client.get_model_version_by_alias.side_effect = Exception("Unexpected error")

                result = manager.rollback(alias="champion")

                assert result.success is False
                assert "Unexpected error" in result.error_message


class TestDefaultConstants:
    """Tests for default constant values."""

    def test_default_model_name(self):
        """Test DEFAULT_MODEL_NAME constant."""
        assert DEFAULT_MODEL_NAME == os.getenv("MODEL_REGISTRY_NAME", "governance_impact_scorer")

    def test_default_champion_alias(self):
        """Test DEFAULT_CHAMPION_ALIAS constant."""
        assert DEFAULT_CHAMPION_ALIAS == os.getenv("CHAMPION_ALIAS", "champion")

    def test_default_candidate_alias(self):
        """Test DEFAULT_CANDIDATE_ALIAS constant."""
        assert DEFAULT_CANDIDATE_ALIAS == os.getenv("CANDIDATE_ALIAS", "candidate")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
