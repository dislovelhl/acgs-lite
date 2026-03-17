"""
ACGS-2 Drift Detection Tests
Constitutional Hash: cdd01ef066bc6cf2

Unit tests for Evidently-based drift detection module.
Tests drift monitoring, severity calculation, alerting, and baseline management.
"""

import os
import sys
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest

from enhanced_agent_bus.observability.structured_logging import get_logger

# Add parent directory to path for module imports
enhanced_agent_bus_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if enhanced_agent_bus_dir not in sys.path:
    sys.path.insert(0, enhanced_agent_bus_dir)

from drift_monitoring import (  # noqa: E402
    DRIFT_CHECK_INTERVAL_HOURS,
    DRIFT_PSI_THRESHOLD,
    DRIFT_SHARE_THRESHOLD,
    EVIDENTLY_AVAILABLE,
    MIN_SAMPLES_FOR_DRIFT,
    PANDAS_AVAILABLE,
    REFERENCE_DATA_PATH,
    DriftAlertConfig,
    DriftDetector,
    DriftReport,
    DriftSeverity,
    DriftStatus,
    FeatureDriftResult,
    check_drift_and_alert,
    detect_drift,
    get_drift_detector,
)

logger = get_logger(__name__)


class TestDriftSeverity:
    """Tests for DriftSeverity enum."""

    def test_drift_severity_values(self):
        """Test all DriftSeverity enum values."""
        assert DriftSeverity.NONE.value == "none"
        assert DriftSeverity.LOW.value == "low"
        assert DriftSeverity.MODERATE.value == "moderate"
        assert DriftSeverity.HIGH.value == "high"
        assert DriftSeverity.CRITICAL.value == "critical"

    def test_drift_severity_is_string_enum(self):
        """Test that DriftSeverity inherits from str."""
        assert isinstance(DriftSeverity.NONE, str)
        assert DriftSeverity.HIGH == "high"

    def test_drift_severity_count(self):
        """Test all expected severity levels exist."""
        severity_values = [s.value for s in DriftSeverity]
        assert len(severity_values) == 5
        assert "none" in severity_values
        assert "critical" in severity_values


class TestDriftStatus:
    """Tests for DriftStatus enum."""

    def test_drift_status_values(self):
        """Test all DriftStatus enum values."""
        assert DriftStatus.SUCCESS.value == "success"
        assert DriftStatus.INSUFFICIENT_DATA.value == "insufficient_data"
        assert DriftStatus.NO_REFERENCE.value == "no_reference"
        assert DriftStatus.ERROR.value == "error"

    def test_drift_status_is_string_enum(self):
        """Test that DriftStatus inherits from str."""
        assert isinstance(DriftStatus.SUCCESS, str)
        assert DriftStatus.ERROR == "error"


class TestFeatureDriftResult:
    """Tests for FeatureDriftResult dataclass."""

    def test_feature_drift_result_creation(self):
        """Test creating FeatureDriftResult with required fields."""
        result = FeatureDriftResult(
            feature_name="age",
            drift_detected=True,
            drift_score=0.35,
        )

        assert result.feature_name == "age"
        assert result.drift_detected is True
        assert result.drift_score == 0.35
        assert result.stattest == "psi"
        assert result.threshold == DRIFT_PSI_THRESHOLD
        assert result.psi_value is None

    def test_feature_drift_result_with_optional_fields(self):
        """Test FeatureDriftResult with all optional fields."""
        result = FeatureDriftResult(
            feature_name="income",
            drift_detected=False,
            drift_score=0.15,
            stattest="ks",
            threshold=0.1,
            psi_value=0.15,
            reference_distribution={"mean": 50000, "std": 10000},
            current_distribution={"mean": 52000, "std": 11000},
        )

        assert result.stattest == "ks"
        assert result.threshold == 0.1
        assert result.psi_value == 0.15
        assert result.reference_distribution is not None
        assert result.current_distribution is not None


class TestDriftReport:
    """Tests for DriftReport dataclass."""

    def test_drift_report_creation_minimal(self):
        """Test creating DriftReport with minimal fields."""
        timestamp = datetime.now(tz=UTC)
        report = DriftReport(
            timestamp=timestamp,
            status=DriftStatus.SUCCESS,
        )

        assert report.timestamp == timestamp
        assert report.status == DriftStatus.SUCCESS
        assert report.dataset_drift is False
        assert report.drift_severity == DriftSeverity.NONE
        assert report.drift_share == 0.0
        assert report.total_features == 0
        assert report.drifted_features == 0
        assert report.feature_results == []
        assert report.recommendations == []
        assert report.error_message is None

    def test_drift_report_creation_full(self):
        """Test creating DriftReport with all fields."""
        timestamp = datetime.now(tz=UTC)
        feature_results = [
            FeatureDriftResult(feature_name="age", drift_detected=True, drift_score=0.3),
            FeatureDriftResult(feature_name="income", drift_detected=False, drift_score=0.1),
        ]

        report = DriftReport(
            timestamp=timestamp,
            status=DriftStatus.SUCCESS,
            dataset_drift=True,
            drift_severity=DriftSeverity.HIGH,
            drift_share=0.5,
            total_features=2,
            drifted_features=1,
            feature_results=feature_results,
            reference_samples=1000,
            current_samples=500,
            error_message=None,
            raw_results={"metrics": []},
            recommendations=["Schedule model retraining"],
        )

        assert report.dataset_drift is True
        assert report.drift_severity == DriftSeverity.HIGH
        assert report.drift_share == 0.5
        assert len(report.feature_results) == 2
        assert report.reference_samples == 1000
        assert len(report.recommendations) == 1

    def test_drift_report_to_dict(self):
        """Test DriftReport serialization to dictionary."""
        timestamp = datetime.now(tz=UTC)
        feature_result = FeatureDriftResult(
            feature_name="age",
            drift_detected=True,
            drift_score=0.35,
            psi_value=0.35,
        )

        report = DriftReport(
            timestamp=timestamp,
            status=DriftStatus.SUCCESS,
            dataset_drift=True,
            drift_severity=DriftSeverity.MODERATE,
            drift_share=0.25,
            total_features=4,
            drifted_features=1,
            feature_results=[feature_result],
            reference_samples=500,
            current_samples=200,
            recommendations=["Monitor trends"],
        )

        result_dict = report.to_dict()

        assert result_dict["timestamp"] == timestamp.isoformat()
        assert result_dict["status"] == "success"
        assert result_dict["dataset_drift"] is True
        assert result_dict["drift_severity"] == "moderate"
        assert result_dict["drift_share"] == 0.25
        assert result_dict["total_features"] == 4
        assert result_dict["drifted_features"] == 1
        assert len(result_dict["feature_results"]) == 1
        assert result_dict["feature_results"][0]["feature_name"] == "age"
        assert result_dict["feature_results"][0]["psi_value"] == 0.35
        assert result_dict["reference_samples"] == 500
        assert result_dict["current_samples"] == 200
        assert result_dict["recommendations"] == ["Monitor trends"]

    def test_drift_report_error_state(self):
        """Test DriftReport with error status."""
        report = DriftReport(
            timestamp=datetime.now(tz=UTC),
            status=DriftStatus.ERROR,
            error_message="Failed to load data",
            recommendations=["Check file path"],
        )

        assert report.status == DriftStatus.ERROR
        assert report.error_message == "Failed to load data"
        assert "Check file path" in report.recommendations


class TestDriftAlertConfig:
    """Tests for DriftAlertConfig dataclass."""

    def test_drift_alert_config_defaults(self):
        """Test DriftAlertConfig default values."""
        config = DriftAlertConfig()

        assert config.enabled is True
        assert config.low_threshold == 0.1
        assert config.moderate_threshold == 0.25
        assert config.high_threshold == 0.5
        assert config.critical_threshold == 0.75
        assert DriftSeverity.HIGH in config.alert_on_severity
        assert DriftSeverity.CRITICAL in config.alert_on_severity
        assert config.webhook_url is None
        assert config.email_recipients == []

    def test_drift_alert_config_custom(self):
        """Test DriftAlertConfig with custom values."""
        config = DriftAlertConfig(
            enabled=False,
            low_threshold=0.05,
            moderate_threshold=0.15,
            high_threshold=0.3,
            critical_threshold=0.6,
            alert_on_severity=[DriftSeverity.CRITICAL],
            webhook_url="https://hooks.slack.com/services/xxx",
            email_recipients=["admin@example.com", "ml-team@example.com"],
        )

        assert config.enabled is False
        assert config.low_threshold == 0.05
        assert config.high_threshold == 0.3
        assert len(config.alert_on_severity) == 1
        assert config.webhook_url is not None
        assert len(config.email_recipients) == 2


class TestDriftDetector:
    """Tests for DriftDetector class."""

    @pytest.fixture
    def detector(self):
        """Create a DriftDetector instance for testing."""
        return DriftDetector(
            reference_data_path="test/reference.parquet",
            psi_threshold=0.2,
            drift_share_threshold=0.5,
            min_samples=100,
        )

    @pytest.fixture
    def mock_pandas(self):
        """Create mock pandas module."""
        with patch("drift_monitoring.pd_module") as mock_pd:
            mock_pd.DataFrame = MagicMock
            mock_pd.read_parquet = MagicMock()
            mock_pd.read_csv = MagicMock()
            mock_pd.concat = MagicMock()
            yield mock_pd

    @pytest.fixture
    def mock_evidently(self):
        """Create mock Evidently module."""
        with patch("drift_monitoring.EvidentlyReport") as mock_report:
            yield mock_report

    def test_detector_initialization(self):
        """Test DriftDetector initialization with default values."""
        detector = DriftDetector()

        assert detector.reference_data_path == REFERENCE_DATA_PATH
        assert detector.psi_threshold == DRIFT_PSI_THRESHOLD
        assert detector.drift_share_threshold == DRIFT_SHARE_THRESHOLD
        assert detector.min_samples == MIN_SAMPLES_FOR_DRIFT
        assert detector.alert_config is not None
        assert detector._reference_data is None
        assert detector._last_report is None
        assert detector._drift_history == []

    def test_detector_initialization_custom(self, detector):
        """Test DriftDetector initialization with custom values."""
        assert detector.reference_data_path == "test/reference.parquet"
        assert detector.psi_threshold == 0.2
        assert detector.drift_share_threshold == 0.5
        assert detector.min_samples == 100

    def test_detector_with_custom_alert_config(self):
        """Test DriftDetector with custom alert configuration."""
        alert_config = DriftAlertConfig(
            enabled=True,
            critical_threshold=0.8,
            alert_on_severity=[DriftSeverity.CRITICAL],
        )

        detector = DriftDetector(alert_config=alert_config)

        assert detector.alert_config.critical_threshold == 0.8
        assert DriftSeverity.CRITICAL in detector.alert_config.alert_on_severity

    def test_has_reference_data_false(self, detector):
        """Test has_reference_data returns False when no data loaded."""
        assert detector.has_reference_data is False

    def test_reference_data_property(self, detector):
        """Test reference_data property returns None initially."""
        assert detector.reference_data is None

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="Pandas not installed")
    def test_check_dependencies_pandas_available(self, detector):
        """Test _check_dependencies passes when pandas available."""
        # Should not raise when pandas is available
        with patch("drift_monitoring.EVIDENTLY_AVAILABLE", True):
            with patch("drift_monitoring.PANDAS_AVAILABLE", True):
                detector._check_dependencies()

    def test_check_dependencies_pandas_missing(self, detector):
        """Test _check_dependencies raises when pandas missing."""
        with patch("drift_monitoring.PANDAS_AVAILABLE", False):
            with pytest.raises(ImportError) as exc_info:
                detector._check_dependencies()
            assert "pandas is required" in str(exc_info.value)

    def test_check_dependencies_evidently_missing(self, detector):
        """Test _check_dependencies raises when evidently missing."""
        with patch("drift_monitoring.PANDAS_AVAILABLE", True):
            with patch("drift_monitoring.EVIDENTLY_AVAILABLE", False):
                with pytest.raises(ImportError) as exc_info:
                    detector._check_dependencies()
                assert "evidently is required" in str(exc_info.value)

    @pytest.mark.skipif(
        not PANDAS_AVAILABLE or not EVIDENTLY_AVAILABLE,
        reason="Pandas or Evidently not installed",
    )
    def test_load_reference_data_from_dataframe(self, detector):
        """Test loading reference data from DataFrame."""
        import pandas as pd

        df = pd.DataFrame(
            {
                "feature1": range(150),
                "feature2": range(150),
                "target": [0, 1] * 75,
            }
        )

        result = detector.load_reference_data(df)

        assert result is True
        assert detector.has_reference_data is True
        assert len(detector._feature_columns) == 2
        assert "feature1" in detector._feature_columns
        assert "target" not in detector._feature_columns  # Excluded

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="Pandas not installed")
    def test_load_reference_data_file_not_found(self, detector):
        """Test loading reference data from non-existent file."""
        with patch("drift_monitoring.EVIDENTLY_AVAILABLE", True):
            result = detector.load_reference_data("nonexistent/file.parquet")
            assert result is False

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="Pandas not installed")
    def test_set_reference_data(self, detector):
        """Test set_reference_data convenience method."""
        import pandas as pd

        with patch("drift_monitoring.EVIDENTLY_AVAILABLE", True):
            df = pd.DataFrame({"col1": range(100), "col2": range(100)})
            result = detector.set_reference_data(df)
            assert result is True

    def test_calculate_severity_none(self, detector):
        """Test severity calculation for no drift."""
        severity = detector._calculate_severity(0.05)
        assert severity == DriftSeverity.NONE

    def test_calculate_severity_low(self, detector):
        """Test severity calculation for low drift."""
        severity = detector._calculate_severity(0.15)
        assert severity == DriftSeverity.LOW

    def test_calculate_severity_moderate(self, detector):
        """Test severity calculation for moderate drift."""
        severity = detector._calculate_severity(0.35)
        assert severity == DriftSeverity.MODERATE

    def test_calculate_severity_high(self, detector):
        """Test severity calculation for high drift."""
        severity = detector._calculate_severity(0.55)
        assert severity == DriftSeverity.HIGH

    def test_calculate_severity_critical(self, detector):
        """Test severity calculation for critical drift."""
        severity = detector._calculate_severity(0.80)
        assert severity == DriftSeverity.CRITICAL

    def test_generate_recommendations_no_drift(self, detector):
        """Test recommendations when no drift detected."""
        recommendations = detector._generate_recommendations(
            dataset_drift=False,
            severity=DriftSeverity.NONE,
            drift_share=0.0,
            drifted_columns=0,
            feature_results=[],
        )

        assert len(recommendations) == 1
        assert "No action required" in recommendations[0]

    def test_generate_recommendations_critical(self, detector):
        """Test recommendations for critical drift."""
        feature_result = FeatureDriftResult(
            feature_name="age",
            drift_detected=True,
            drift_score=0.5,
        )

        recommendations = detector._generate_recommendations(
            dataset_drift=True,
            severity=DriftSeverity.CRITICAL,
            drift_share=0.8,
            drifted_columns=4,
            feature_results=[feature_result],
        )

        assert len(recommendations) >= 3
        assert any("IMMEDIATE ACTION" in r for r in recommendations)
        assert any("emergency" in r.lower() for r in recommendations)

    def test_generate_recommendations_high(self, detector):
        """Test recommendations for high drift."""
        recommendations = detector._generate_recommendations(
            dataset_drift=True,
            severity=DriftSeverity.HIGH,
            drift_share=0.55,
            drifted_columns=3,
            feature_results=[],
        )

        assert len(recommendations) >= 3
        assert any("24-48 hours" in r for r in recommendations)

    def test_generate_recommendations_moderate(self, detector):
        """Test recommendations for moderate drift."""
        recommendations = detector._generate_recommendations(
            dataset_drift=True,
            severity=DriftSeverity.MODERATE,
            drift_share=0.35,
            drifted_columns=2,
            feature_results=[],
        )

        assert any("maintenance window" in r for r in recommendations)

    def test_generate_recommendations_low(self, detector):
        """Test recommendations for low drift."""
        recommendations = detector._generate_recommendations(
            dataset_drift=True,
            severity=DriftSeverity.LOW,
            drift_share=0.15,
            drifted_columns=1,
            feature_results=[],
        )

        assert any("Monitor" in r for r in recommendations)

    def test_generate_recommendations_high_drift_features(self, detector):
        """Test recommendations include high drift features."""
        feature_results = [
            FeatureDriftResult(feature_name="age", drift_detected=True, drift_score=0.5),
            FeatureDriftResult(feature_name="income", drift_detected=True, drift_score=0.6),
        ]

        recommendations = detector._generate_recommendations(
            dataset_drift=True,
            severity=DriftSeverity.HIGH,
            drift_share=0.6,
            drifted_columns=2,
            feature_results=feature_results,
        )

        assert any("age" in r or "income" in r for r in recommendations)

    def test_get_last_report_none(self, detector):
        """Test get_last_report returns None initially."""
        assert detector.get_last_report() is None

    def test_get_drift_history_empty(self, detector):
        """Test get_drift_history returns empty list initially."""
        assert detector.get_drift_history() == []

    def test_get_drift_history_with_limit(self, detector):
        """Test get_drift_history respects limit parameter."""
        # Add some reports to history
        for i in range(5):
            report = DriftReport(
                timestamp=datetime.now(tz=UTC) - timedelta(hours=i),
                status=DriftStatus.SUCCESS,
            )
            detector._drift_history.append(report)

        history = detector.get_drift_history(limit=3)
        assert len(history) == 3

    def test_get_drift_history_since_filter(self, detector):
        """Test get_drift_history filters by timestamp."""
        now = datetime.now(tz=UTC)

        # Add old report
        old_report = DriftReport(
            timestamp=now - timedelta(days=7),
            status=DriftStatus.SUCCESS,
        )
        detector._drift_history.append(old_report)

        # Add recent report
        recent_report = DriftReport(
            timestamp=now - timedelta(hours=1),
            status=DriftStatus.SUCCESS,
        )
        detector._drift_history.append(recent_report)

        # Filter to last 2 days
        since = now - timedelta(days=2)
        history = detector.get_drift_history(since=since)

        assert len(history) == 1
        assert history[0].timestamp > since

    def test_should_trigger_retraining_no_report(self, detector):
        """Test should_trigger_retraining returns False when no report."""
        assert detector.should_trigger_retraining() is False

    def test_should_trigger_retraining_no_drift(self, detector):
        """Test should_trigger_retraining returns False when no drift."""
        report = DriftReport(
            timestamp=datetime.now(tz=UTC),
            status=DriftStatus.SUCCESS,
            dataset_drift=False,
        )
        assert detector.should_trigger_retraining(report) is False

    def test_should_trigger_retraining_high_severity(self, detector):
        """Test should_trigger_retraining returns True for high severity."""
        report = DriftReport(
            timestamp=datetime.now(tz=UTC),
            status=DriftStatus.SUCCESS,
            dataset_drift=True,
            drift_severity=DriftSeverity.HIGH,
        )
        assert detector.should_trigger_retraining(report) is True

    def test_should_trigger_retraining_critical_severity(self, detector):
        """Test should_trigger_retraining returns True for critical severity."""
        report = DriftReport(
            timestamp=datetime.now(tz=UTC),
            status=DriftStatus.SUCCESS,
            dataset_drift=True,
            drift_severity=DriftSeverity.CRITICAL,
        )
        assert detector.should_trigger_retraining(report) is True

    def test_should_trigger_retraining_moderate_severity(self, detector):
        """Test should_trigger_retraining returns False for moderate severity."""
        report = DriftReport(
            timestamp=datetime.now(tz=UTC),
            status=DriftStatus.SUCCESS,
            dataset_drift=True,
            drift_severity=DriftSeverity.MODERATE,
        )
        assert detector.should_trigger_retraining(report) is False

    def test_should_send_alert_disabled(self, detector):
        """Test should_send_alert returns False when alerts disabled."""
        detector.alert_config.enabled = False

        report = DriftReport(
            timestamp=datetime.now(tz=UTC),
            status=DriftStatus.SUCCESS,
            dataset_drift=True,
            drift_severity=DriftSeverity.CRITICAL,
        )

        assert detector.should_send_alert(report) is False

    def test_should_send_alert_no_report(self, detector):
        """Test should_send_alert returns False when no report."""
        assert detector.should_send_alert() is False

    def test_should_send_alert_high_severity(self, detector):
        """Test should_send_alert returns True for high severity."""
        report = DriftReport(
            timestamp=datetime.now(tz=UTC),
            status=DriftStatus.SUCCESS,
            dataset_drift=True,
            drift_severity=DriftSeverity.HIGH,
        )

        assert detector.should_send_alert(report) is True

    def test_should_send_alert_low_severity(self, detector):
        """Test should_send_alert returns False for low severity."""
        report = DriftReport(
            timestamp=datetime.now(tz=UTC),
            status=DriftStatus.SUCCESS,
            dataset_drift=True,
            drift_severity=DriftSeverity.LOW,
        )

        assert detector.should_send_alert(report) is False

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="Pandas not installed")
    def test_update_reference_baseline_replace(self, detector):
        """Test update_reference_baseline with replace strategy."""
        import pandas as pd

        with patch("drift_monitoring.EVIDENTLY_AVAILABLE", True):
            new_data = pd.DataFrame({"col1": range(100), "col2": range(100)})
            result = detector.update_reference_baseline(new_data, strategy="replace")

            assert result is True
            assert detector.has_reference_data is True

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="Pandas not installed")
    def test_update_reference_baseline_append(self, detector):
        """Test update_reference_baseline with append strategy."""
        import pandas as pd

        with patch("drift_monitoring.EVIDENTLY_AVAILABLE", True):
            # Set initial data
            initial_data = pd.DataFrame({"col1": range(50), "col2": range(50)})
            detector._reference_data = initial_data

            # Append new data
            new_data = pd.DataFrame({"col1": range(50, 100), "col2": range(50, 100)})
            result = detector.update_reference_baseline(new_data, strategy="append")

            assert result is True

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="Pandas not installed")
    def test_update_reference_baseline_rolling(self, detector):
        """Test update_reference_baseline with rolling strategy."""
        import pandas as pd

        with patch("drift_monitoring.EVIDENTLY_AVAILABLE", True):
            # Set initial data
            initial_data = pd.DataFrame({"col1": range(100), "col2": range(100)})
            detector._reference_data = initial_data

            # Add rolling data
            new_data = pd.DataFrame({"col1": range(50), "col2": range(50)})
            result = detector.update_reference_baseline(new_data, strategy="rolling")

            assert result is True

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="Pandas not installed")
    def test_update_reference_baseline_unknown_strategy(self, detector):
        """Test update_reference_baseline with unknown strategy."""
        import pandas as pd

        with patch("drift_monitoring.EVIDENTLY_AVAILABLE", True):
            new_data = pd.DataFrame({"col1": range(100)})
            result = detector.update_reference_baseline(new_data, strategy="unknown")

            assert result is False

    def test_save_reference_baseline_no_data(self, detector):
        """Test save_reference_baseline returns False when no data."""
        result = detector.save_reference_baseline()
        assert result is False

    def test_parse_evidently_results(self, detector):
        """Test _parse_evidently_results parses correctly."""
        drift_results = {
            "metrics": [
                {
                    "result": {
                        "dataset_drift": True,
                        "share_of_drifted_columns": 0.5,
                        "number_of_drifted_columns": 2,
                        "number_of_columns": 4,
                        "drift_by_columns": {
                            "age": {
                                "drift_detected": True,
                                "drift_score": 0.35,
                                "stattest_name": "psi",
                                "stattest_threshold": 0.2,
                            },
                            "income": {
                                "drift_detected": False,
                                "drift_score": 0.1,
                                "stattest_name": "psi",
                                "stattest_threshold": 0.2,
                            },
                        },
                    }
                }
            ]
        }

        timestamp = datetime.now(tz=UTC)
        report = detector._parse_evidently_results(
            drift_results=drift_results,
            timestamp=timestamp,
            reference_samples=1000,
            current_samples=500,
            columns=["age", "income"],
        )

        assert report.status == DriftStatus.SUCCESS
        assert report.dataset_drift is True
        assert report.drift_share == 0.5
        assert report.drifted_features == 2
        assert report.total_features == 4
        assert len(report.feature_results) == 2
        assert report.reference_samples == 1000
        assert report.current_samples == 500


class TestDriftDetectorIntegration:
    """Integration tests for DriftDetector with mock Evidently."""

    @pytest.fixture
    def detector_with_mocks(self):
        """Create detector with mocked dependencies."""
        detector = DriftDetector(
            psi_threshold=0.2,
            drift_share_threshold=0.5,
            min_samples=10,  # Lower for testing
        )
        return detector

    def test_detect_drift_dependencies_unavailable(self, detector_with_mocks):
        """Test detect_drift handles missing dependencies gracefully."""
        with patch("drift_monitoring.PANDAS_AVAILABLE", False):
            report = detector_with_mocks.detect_drift(MagicMock())

            assert report.status == DriftStatus.ERROR
            assert "pandas is required" in report.error_message

    def test_detect_drift_no_reference_data(self, detector_with_mocks):
        """Test detect_drift handles missing reference data."""
        with patch("drift_monitoring.PANDAS_AVAILABLE", True):
            with patch("drift_monitoring.EVIDENTLY_AVAILABLE", True):
                with patch.object(detector_with_mocks, "load_reference_data", return_value=False):
                    # Mock current data
                    mock_df = MagicMock()
                    mock_df.__len__ = Mock(return_value=100)

                    report = detector_with_mocks.detect_drift(mock_df)

                    assert report.status == DriftStatus.NO_REFERENCE

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="Pandas not installed")
    def test_detect_drift_insufficient_current_samples(self, detector_with_mocks):
        """Test detect_drift handles insufficient current data."""
        import pandas as pd

        with patch("drift_monitoring.PANDAS_AVAILABLE", True):
            with patch("drift_monitoring.EVIDENTLY_AVAILABLE", True):
                # Set reference data
                detector_with_mocks._reference_data = pd.DataFrame(
                    {"col1": range(100), "col2": range(100)}
                )
                detector_with_mocks._feature_columns = ["col1", "col2"]
                detector_with_mocks.min_samples = 100

                # Create small current dataset
                current_data = pd.DataFrame({"col1": range(10), "col2": range(10)})

                report = detector_with_mocks.detect_drift(current_data)

                assert report.status == DriftStatus.INSUFFICIENT_DATA
                assert "Insufficient current data" in report.error_message

    @pytest.mark.skipif(
        not PANDAS_AVAILABLE or not EVIDENTLY_AVAILABLE,
        reason="Pandas or Evidently not installed",
    )
    def test_detect_drift_success(self, detector_with_mocks):
        """Test detect_drift with valid data."""
        import pandas as pd

        # Create reference data
        reference_data = pd.DataFrame(
            {
                "feature1": list(range(100)),
                "feature2": [x * 2 for x in range(100)],
            }
        )

        # Create current data with slight drift
        current_data = pd.DataFrame(
            {
                "feature1": [x + 5 for x in range(100)],
                "feature2": [x * 2 + 10 for x in range(100)],
            }
        )

        # Set min_samples lower for test
        detector_with_mocks.min_samples = 50

        # Load reference data
        detector_with_mocks.load_reference_data(reference_data)

        # Run drift detection
        report = detector_with_mocks.detect_drift(current_data)

        assert report.status == DriftStatus.SUCCESS
        assert report.reference_samples == 100
        assert report.current_samples == 100
        assert len(report.feature_results) == 2


class TestModuleLevelFunctions:
    """Tests for module-level convenience functions."""

    @pytest.fixture(autouse=True)
    def reset_global_detector(self):
        """Reset the global drift detector before each test."""
        import drift_monitoring

        drift_monitoring._drift_detector = None
        yield
        drift_monitoring._drift_detector = None

    def test_get_drift_detector_creates_singleton(self):
        """Test get_drift_detector creates a singleton."""
        detector1 = get_drift_detector()
        detector2 = get_drift_detector()

        assert detector1 is detector2

    def test_get_drift_detector_with_custom_params(self):
        """Test get_drift_detector with custom parameters."""
        detector = get_drift_detector(
            reference_data_path="custom/path.parquet",
            psi_threshold=0.15,
        )

        assert detector.reference_data_path == "custom/path.parquet"
        assert detector.psi_threshold == 0.15

    def test_detect_drift_function(self):
        """Test module-level detect_drift function."""
        with patch("drift_monitoring.get_drift_detector") as mock_get:
            mock_detector = MagicMock()
            mock_report = DriftReport(
                timestamp=datetime.now(tz=UTC),
                status=DriftStatus.SUCCESS,
            )
            mock_detector.detect_drift.return_value = mock_report
            mock_get.return_value = mock_detector

            result = detect_drift(MagicMock())

            assert result.status == DriftStatus.SUCCESS

    def test_detect_drift_function_with_reference(self):
        """Test module-level detect_drift with reference data."""
        with patch("drift_monitoring.get_drift_detector") as mock_get:
            mock_detector = MagicMock()
            mock_report = DriftReport(
                timestamp=datetime.now(tz=UTC),
                status=DriftStatus.SUCCESS,
            )
            mock_detector.detect_drift.return_value = mock_report
            mock_get.return_value = mock_detector

            result = detect_drift(MagicMock(), reference_data=MagicMock())

            mock_detector.load_reference_data.assert_called_once()
            assert result.status == DriftStatus.SUCCESS

    def test_check_drift_and_alert_function(self):
        """Test module-level check_drift_and_alert function."""
        with patch("drift_monitoring.get_drift_detector") as mock_get:
            mock_detector = MagicMock()
            mock_report = DriftReport(
                timestamp=datetime.now(tz=UTC),
                status=DriftStatus.SUCCESS,
                dataset_drift=True,
                drift_severity=DriftSeverity.HIGH,
            )
            mock_detector.detect_drift.return_value = mock_report
            mock_detector.should_send_alert.return_value = True
            mock_detector.should_trigger_retraining.return_value = True
            mock_get.return_value = mock_detector

            result = check_drift_and_alert(MagicMock())

            assert result["drift_detected"] is True
            assert result["severity"] == "high"
            assert result["should_alert"] is True
            assert result["should_retrain"] is True
            assert "report" in result


class TestConfigurationConstants:
    """Tests for configuration constants."""

    def test_reference_data_path_from_env(self):
        """Test REFERENCE_DATA_PATH is a non-empty path string."""
        # REFERENCE_DATA_PATH is a module-level constant set at import time.
        # We verify it is a non-empty string ending in .parquet.
        assert isinstance(REFERENCE_DATA_PATH, str) and REFERENCE_DATA_PATH
        assert REFERENCE_DATA_PATH.endswith(".parquet")

    def test_drift_check_interval_from_env(self):
        """Test DRIFT_CHECK_INTERVAL_HOURS uses environment variable."""
        expected = int(os.getenv("DRIFT_CHECK_INTERVAL_HOURS", "6"))
        assert DRIFT_CHECK_INTERVAL_HOURS == expected

    def test_drift_psi_threshold_from_env(self):
        """Test DRIFT_PSI_THRESHOLD uses environment variable."""
        expected = float(os.getenv("DRIFT_PSI_THRESHOLD", "0.2"))
        assert DRIFT_PSI_THRESHOLD == expected

    def test_drift_share_threshold_from_env(self):
        """Test DRIFT_SHARE_THRESHOLD uses environment variable."""
        expected = float(os.getenv("DRIFT_SHARE_THRESHOLD", "0.5"))
        assert DRIFT_SHARE_THRESHOLD == expected

    def test_min_samples_from_env(self):
        """Test MIN_SAMPLES_FOR_DRIFT uses environment variable."""
        expected = int(os.getenv("MIN_SAMPLES_FOR_DRIFT", "100"))
        assert MIN_SAMPLES_FOR_DRIFT == expected


class TestAvailabilityFlags:
    """Tests for availability flag exports."""

    def test_pandas_available_flag(self):
        """Test PANDAS_AVAILABLE flag is exported."""
        assert isinstance(PANDAS_AVAILABLE, bool)

    def test_evidently_available_flag(self):
        """Test EVIDENTLY_AVAILABLE flag is exported."""
        assert isinstance(EVIDENTLY_AVAILABLE, bool)


class TestErrorHandling:
    """Tests for error handling scenarios."""

    @pytest.fixture
    def detector(self):
        """Create detector for error testing."""
        return DriftDetector(min_samples=10)

    @pytest.mark.skipif(not PANDAS_AVAILABLE, reason="Pandas not installed")
    def test_load_reference_data_exception_handling(self, detector):
        """Test load_reference_data handles exceptions."""
        with patch("drift_monitoring.PANDAS_AVAILABLE", True):
            with patch("drift_monitoring.EVIDENTLY_AVAILABLE", True):
                with patch("drift_monitoring.pd_module.read_parquet") as mock_read:
                    mock_read.side_effect = RuntimeError("Read error")

                    # Create a temp file path
                    result = detector.load_reference_data("test.parquet")

                    # Should return False due to file not existing
                    assert result is False

    def test_update_baseline_exception_handling(self, detector):
        """Test update_reference_baseline handles exceptions."""
        with patch("drift_monitoring.PANDAS_AVAILABLE", True):
            with patch("drift_monitoring.EVIDENTLY_AVAILABLE", True):
                # Mock DataFrame that raises on copy
                mock_df = MagicMock()
                mock_df.copy.side_effect = RuntimeError("Copy failed")

                result = detector.update_reference_baseline(mock_df, strategy="replace")

                assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
