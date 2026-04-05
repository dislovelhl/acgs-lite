"""
Tests for Constitutional Degradation Detector
Constitutional Hash: 608508a9bd224290

Tests for governance degradation detection, severity analysis,
and rollback recommendations.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

from ..degradation_detector import (
    DegradationDetector,
    DegradationReport,
    DegradationSeverity,
    DegradationThresholds,
    MetricDegradationAnalysis,
    SignificanceLevel,
    StatisticalTest,
    TimeWindow,
)
from ..metrics_collector import GovernanceMetricsSnapshot

# Constitutional validation markers
pytestmark = [
    pytest.mark.constitutional,
    pytest.mark.unit,
]


class TestTimeWindow:
    """Test TimeWindow enum functionality."""

    def test_time_window_to_seconds(self):
        """Test converting time windows to seconds."""
        assert TimeWindow.ONE_HOUR.to_seconds() == 3600
        assert TimeWindow.SIX_HOURS.to_seconds() == 21600
        assert TimeWindow.TWELVE_HOURS.to_seconds() == 43200
        assert TimeWindow.TWENTY_FOUR_HOURS.to_seconds() == 86400


class TestSignificanceLevel:
    """Test SignificanceLevel enum functionality."""

    def test_from_p_value_very_high(self):
        """Test very high significance (p < 0.001)."""
        assert SignificanceLevel.from_p_value(0.0005) == SignificanceLevel.VERY_HIGH

    def test_from_p_value_high(self):
        """Test high significance (p < 0.01)."""
        assert SignificanceLevel.from_p_value(0.005) == SignificanceLevel.HIGH

    def test_from_p_value_moderate(self):
        """Test moderate significance (p < 0.05)."""
        assert SignificanceLevel.from_p_value(0.03) == SignificanceLevel.MODERATE

    def test_from_p_value_low(self):
        """Test low significance (p < 0.1)."""
        assert SignificanceLevel.from_p_value(0.07) == SignificanceLevel.LOW

    def test_from_p_value_none(self):
        """Test no significance (p >= 0.1)."""
        assert SignificanceLevel.from_p_value(0.15) == SignificanceLevel.NONE


class TestStatisticalTest:
    """Test StatisticalTest model."""

    def test_is_significant(self):
        """Test significance detection (p < 0.05)."""
        test = StatisticalTest(
            test_name="chi_square",
            statistic=5.5,
            p_value=0.03,
            significance_level=SignificanceLevel.MODERATE,
        )
        assert test.is_significant is True

    def test_is_not_significant(self):
        """Test non-significance (p >= 0.05)."""
        test = StatisticalTest(
            test_name="chi_square",
            statistic=1.2,
            p_value=0.25,
            significance_level=SignificanceLevel.NONE,
        )
        assert test.is_significant is False

    def test_is_highly_significant(self):
        """Test high significance (p < 0.01)."""
        test = StatisticalTest(
            test_name="chi_square",
            statistic=12.5,
            p_value=0.005,
            significance_level=SignificanceLevel.HIGH,
        )
        assert test.is_highly_significant is True


class TestDegradationThresholds:
    """Test DegradationThresholds configuration."""

    def test_default_thresholds(self):
        """Test default threshold values."""
        thresholds = DegradationThresholds()

        assert thresholds.violations_rate_threshold == 0.01
        assert thresholds.latency_p99_threshold_ms == 2.0
        assert thresholds.latency_p99_percent_threshold == 0.5
        assert thresholds.deliberation_success_rate_threshold == 0.05
        assert thresholds.maci_violations_threshold == 1
        assert thresholds.error_rate_threshold == 0.1
        assert thresholds.health_score_threshold == 0.15
        assert thresholds.min_sample_size == 30
        assert thresholds.significance_level == 0.05

    def test_custom_thresholds(self):
        """Test custom threshold configuration."""
        thresholds = DegradationThresholds(
            violations_rate_threshold=0.02,
            latency_p99_threshold_ms=5.0,
            min_sample_size=50,
        )

        assert thresholds.violations_rate_threshold == 0.02
        assert thresholds.latency_p99_threshold_ms == 5.0
        assert thresholds.min_sample_size == 50

    def test_threshold_validation(self):
        """Test threshold validation."""
        with pytest.raises(ValueError):
            DegradationThresholds(violations_rate_threshold=1.5)  # > 1.0


class TestDegradationReport:
    """Test DegradationReport model."""

    @pytest.fixture
    def mock_baseline_snapshot(self):
        """Create mock baseline metrics snapshot."""
        return GovernanceMetricsSnapshot(
            snapshot_id="baseline-001",
            constitutional_version="1.0.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            total_requests=1000,
            violations_count=10,
            violations_rate=0.01,
            governance_latency_p99=2.0,
            deliberation_success_rate=0.95,
            maci_violations_count=0,
            error_rate=0.02,
            health_score=0.95,
            escalated_requests=100,
        )

    @pytest.fixture
    def mock_current_snapshot(self):
        """Create mock current metrics snapshot with degradation."""
        return GovernanceMetricsSnapshot(
            snapshot_id="current-001",
            constitutional_version="1.0.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            total_requests=1000,
            violations_count=50,
            violations_rate=0.05,
            governance_latency_p99=5.0,
            deliberation_success_rate=0.85,
            maci_violations_count=3,
            error_rate=0.15,
            health_score=0.75,
            escalated_requests=100,
        )

    def test_has_degradation_property(self, mock_baseline_snapshot, mock_current_snapshot):
        """Test has_degradation property."""
        report = DegradationReport(
            time_window=TimeWindow.ONE_HOUR,
            baseline_snapshot=mock_baseline_snapshot,
            current_snapshot=mock_current_snapshot,
            overall_severity=DegradationSeverity.HIGH,
        )
        assert report.has_degradation is True

        report_no_degradation = DegradationReport(
            time_window=TimeWindow.ONE_HOUR,
            baseline_snapshot=mock_baseline_snapshot,
            current_snapshot=mock_baseline_snapshot,
            overall_severity=DegradationSeverity.NONE,
        )
        assert report_no_degradation.has_degradation is False

    def test_critical_metrics_property(self, mock_baseline_snapshot, mock_current_snapshot):
        """Test critical_metrics property."""
        critical_analysis = MetricDegradationAnalysis(
            metric_name="violations_rate",
            baseline_value=0.01,
            current_value=0.05,
            delta=0.04,
            percent_change=4.0,
            threshold_exceeded=True,
            configured_threshold=0.01,
            severity=DegradationSeverity.CRITICAL,
        )

        high_analysis = MetricDegradationAnalysis(
            metric_name="latency_p99",
            baseline_value=2.0,
            current_value=5.0,
            delta=3.0,
            percent_change=1.5,
            threshold_exceeded=True,
            configured_threshold=2.0,
            severity=DegradationSeverity.HIGH,
        )

        report = DegradationReport(
            time_window=TimeWindow.ONE_HOUR,
            baseline_snapshot=mock_baseline_snapshot,
            current_snapshot=mock_current_snapshot,
            metric_analyses=[critical_analysis, high_analysis],
            overall_severity=DegradationSeverity.CRITICAL,
        )

        assert len(report.critical_metrics) == 1
        assert report.critical_metrics[0].metric_name == "violations_rate"

    def test_high_severity_metrics_property(self, mock_baseline_snapshot, mock_current_snapshot):
        """Test high_severity_metrics property."""
        critical_analysis = MetricDegradationAnalysis(
            metric_name="violations_rate",
            baseline_value=0.01,
            current_value=0.05,
            delta=0.04,
            percent_change=4.0,
            threshold_exceeded=True,
            configured_threshold=0.01,
            severity=DegradationSeverity.CRITICAL,
        )

        high_analysis = MetricDegradationAnalysis(
            metric_name="latency_p99",
            baseline_value=2.0,
            current_value=5.0,
            delta=3.0,
            percent_change=1.5,
            threshold_exceeded=True,
            configured_threshold=2.0,
            severity=DegradationSeverity.HIGH,
        )

        moderate_analysis = MetricDegradationAnalysis(
            metric_name="health_score",
            baseline_value=0.95,
            current_value=0.80,
            delta=-0.15,
            percent_change=-0.16,
            threshold_exceeded=True,
            configured_threshold=0.15,
            severity=DegradationSeverity.MODERATE,
        )

        report = DegradationReport(
            time_window=TimeWindow.ONE_HOUR,
            baseline_snapshot=mock_baseline_snapshot,
            current_snapshot=mock_current_snapshot,
            metric_analyses=[critical_analysis, high_analysis, moderate_analysis],
            overall_severity=DegradationSeverity.CRITICAL,
        )

        # high_severity_metrics includes both CRITICAL and HIGH
        assert len(report.high_severity_metrics) == 2

    def test_constitutional_hash_in_report(self, mock_baseline_snapshot, mock_current_snapshot):
        """Test constitutional hash is included in report."""
        report = DegradationReport(
            time_window=TimeWindow.ONE_HOUR,
            baseline_snapshot=mock_baseline_snapshot,
            current_snapshot=mock_current_snapshot,
        )

        assert report.constitutional_hash == CONSTITUTIONAL_HASH


class TestDegradationDetector:
    """Test DegradationDetector functionality."""

    @pytest.fixture
    def mock_metrics_collector(self):
        """Create mock metrics collector."""
        collector = AsyncMock()
        collector.get_baseline_snapshot = AsyncMock(return_value=None)
        collector.collect_snapshot = AsyncMock()
        return collector

    @pytest.fixture
    def mock_baseline_snapshot(self):
        """Create mock baseline metrics snapshot."""
        return GovernanceMetricsSnapshot(
            snapshot_id="baseline-001",
            constitutional_version="1.0.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            total_requests=1000,
            violations_count=10,
            violations_rate=0.01,
            governance_latency_p99=2.0,
            deliberation_success_rate=0.95,
            maci_violations_count=0,
            error_rate=0.02,
            health_score=0.95,
            escalated_requests=100,
        )

    @pytest.fixture
    def mock_current_snapshot_degraded(self):
        """Create mock current metrics with degradation."""
        return GovernanceMetricsSnapshot(
            snapshot_id="current-001",
            constitutional_version="1.0.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            total_requests=1000,
            violations_count=50,
            violations_rate=0.05,
            governance_latency_p99=5.0,
            deliberation_success_rate=0.80,
            maci_violations_count=5,
            error_rate=0.20,
            health_score=0.70,
            escalated_requests=100,
        )

    @pytest.fixture
    def mock_current_snapshot_healthy(self):
        """Create mock current metrics without degradation."""
        return GovernanceMetricsSnapshot(
            snapshot_id="current-002",
            constitutional_version="1.0.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            total_requests=1000,
            violations_count=12,
            violations_rate=0.012,
            governance_latency_p99=2.1,
            deliberation_success_rate=0.94,
            maci_violations_count=0,
            error_rate=0.025,
            health_score=0.93,
            escalated_requests=100,
        )

    async def test_analyze_degradation_detects_issues(
        self, mock_metrics_collector, mock_baseline_snapshot, mock_current_snapshot_degraded
    ):
        """Test degradation detection with degraded metrics."""
        detector = DegradationDetector(
            metrics_collector=mock_metrics_collector,
            thresholds=DegradationThresholds(),
        )

        report = await detector.analyze_degradation(
            baseline=mock_baseline_snapshot,
            current=mock_current_snapshot_degraded,
            time_window=TimeWindow.ONE_HOUR,
            amendment_id="amendment-001",
        )

        assert report.has_degradation is True
        assert report.overall_severity in (
            DegradationSeverity.HIGH,
            DegradationSeverity.CRITICAL,
        )
        assert report.rollback_recommended is True
        assert len(report.metric_analyses) > 0
        assert report.amendment_id == "amendment-001"

    async def test_analyze_degradation_healthy_system(
        self, mock_metrics_collector, mock_baseline_snapshot, mock_current_snapshot_healthy
    ):
        """Test degradation detection with healthy metrics."""
        detector = DegradationDetector(
            metrics_collector=mock_metrics_collector,
            thresholds=DegradationThresholds(),
        )

        report = await detector.analyze_degradation(
            baseline=mock_baseline_snapshot,
            current=mock_current_snapshot_healthy,
            time_window=TimeWindow.ONE_HOUR,
        )

        assert report.has_degradation is False
        assert report.overall_severity == DegradationSeverity.NONE
        assert report.rollback_recommended is False

    async def test_analyze_degradation_collects_current_if_not_provided(
        self, mock_metrics_collector, mock_baseline_snapshot
    ):
        """Test that detector collects current snapshot if not provided."""
        mock_current = GovernanceMetricsSnapshot(
            snapshot_id="current-auto",
            constitutional_version="1.0.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            total_requests=1000,
            violations_count=10,
            violations_rate=0.01,
            governance_latency_p99=2.0,
            deliberation_success_rate=0.95,
            maci_violations_count=0,
            error_rate=0.02,
            health_score=0.95,
            escalated_requests=100,
        )
        mock_metrics_collector.collect_snapshot.return_value = mock_current

        detector = DegradationDetector(
            metrics_collector=mock_metrics_collector,
            thresholds=DegradationThresholds(),
        )

        report = await detector.analyze_degradation(
            baseline=mock_baseline_snapshot,
            time_window=TimeWindow.ONE_HOUR,
        )

        mock_metrics_collector.collect_snapshot.assert_called_once()
        assert report.current_snapshot == mock_current

    async def test_analyze_multi_window(
        self, mock_metrics_collector, mock_baseline_snapshot, mock_current_snapshot_degraded
    ):
        """Test multi-window degradation analysis."""
        mock_metrics_collector.collect_snapshot.return_value = mock_current_snapshot_degraded

        detector = DegradationDetector(
            metrics_collector=mock_metrics_collector,
            thresholds=DegradationThresholds(),
        )

        reports = await detector.analyze_multi_window(
            baseline=mock_baseline_snapshot,
            amendment_id="amendment-001",
            windows=[TimeWindow.ONE_HOUR, TimeWindow.SIX_HOURS],
        )

        assert len(reports) == 2
        assert all(isinstance(r, DegradationReport) for r in reports)

    def test_determine_overall_severity_critical(self, mock_metrics_collector):
        """Test critical severity determination."""
        detector = DegradationDetector(
            metrics_collector=mock_metrics_collector,
            thresholds=DegradationThresholds(),
        )

        analyses = [
            MetricDegradationAnalysis(
                metric_name="violations_rate",
                baseline_value=0.01,
                current_value=0.10,
                delta=0.09,
                percent_change=9.0,
                threshold_exceeded=True,
                configured_threshold=0.01,
                severity=DegradationSeverity.CRITICAL,
            ),
        ]

        severity = detector._determine_overall_severity(analyses)
        assert severity == DegradationSeverity.CRITICAL

    def test_determine_overall_severity_escalates_multiple_high(self, mock_metrics_collector):
        """Test that multiple HIGH severities escalate to CRITICAL."""
        detector = DegradationDetector(
            metrics_collector=mock_metrics_collector,
            thresholds=DegradationThresholds(),
        )

        analyses = [
            MetricDegradationAnalysis(
                metric_name="violations_rate",
                baseline_value=0.01,
                current_value=0.04,
                delta=0.03,
                percent_change=3.0,
                threshold_exceeded=True,
                configured_threshold=0.01,
                severity=DegradationSeverity.HIGH,
            ),
            MetricDegradationAnalysis(
                metric_name="latency_p99",
                baseline_value=2.0,
                current_value=8.0,
                delta=6.0,
                percent_change=3.0,
                threshold_exceeded=True,
                configured_threshold=2.0,
                severity=DegradationSeverity.HIGH,
            ),
        ]

        severity = detector._determine_overall_severity(analyses)
        assert severity == DegradationSeverity.CRITICAL

    def test_should_recommend_rollback_critical(self, mock_metrics_collector):
        """Test rollback recommendation for critical severity."""
        detector = DegradationDetector(
            metrics_collector=mock_metrics_collector,
            thresholds=DegradationThresholds(),
        )

        should_rollback = detector._should_recommend_rollback(
            overall_severity=DegradationSeverity.CRITICAL,
            confidence_score=0.5,
            statistical_significance=SignificanceLevel.NONE,
        )

        assert should_rollback is True

    def test_should_recommend_rollback_high_with_confidence(self, mock_metrics_collector):
        """Test rollback recommendation for high severity with confidence."""
        detector = DegradationDetector(
            metrics_collector=mock_metrics_collector,
            thresholds=DegradationThresholds(),
        )

        # High severity + high confidence + high significance = rollback
        should_rollback = detector._should_recommend_rollback(
            overall_severity=DegradationSeverity.HIGH,
            confidence_score=0.8,
            statistical_significance=SignificanceLevel.HIGH,
        )
        assert should_rollback is True

        # High severity + low confidence = no rollback
        should_not_rollback = detector._should_recommend_rollback(
            overall_severity=DegradationSeverity.HIGH,
            confidence_score=0.4,
            statistical_significance=SignificanceLevel.LOW,
        )
        assert should_not_rollback is False

    def test_generate_summary_no_degradation(self, mock_metrics_collector):
        """Test summary generation when no degradation."""
        detector = DegradationDetector(
            metrics_collector=mock_metrics_collector,
            thresholds=DegradationThresholds(),
        )

        analyses = [
            MetricDegradationAnalysis(
                metric_name="violations_rate",
                baseline_value=0.01,
                current_value=0.011,
                delta=0.001,
                percent_change=0.1,
                threshold_exceeded=False,
                configured_threshold=0.01,
                severity=DegradationSeverity.NONE,
            ),
        ]

        summary = detector._generate_summary(analyses, DegradationSeverity.NONE)

        assert "No significant governance degradation" in summary

    def test_generate_summary_with_degradation(self, mock_metrics_collector):
        """Test summary generation with degradation."""
        detector = DegradationDetector(
            metrics_collector=mock_metrics_collector,
            thresholds=DegradationThresholds(),
        )

        analyses = [
            MetricDegradationAnalysis(
                metric_name="violations_rate",
                baseline_value=0.01,
                current_value=0.05,
                delta=0.04,
                percent_change=4.0,
                threshold_exceeded=True,
                configured_threshold=0.01,
                severity=DegradationSeverity.HIGH,
            ),
        ]

        summary = detector._generate_summary(analyses, DegradationSeverity.HIGH)

        assert "degradation detected" in summary.lower()
        assert "violations_rate" in summary


class TestDegradationDetectorMetricAnalysis:
    """Test individual metric analysis methods."""

    @pytest.fixture
    def detector(self):
        """Create detector for testing."""
        mock_collector = MagicMock()
        return DegradationDetector(
            metrics_collector=mock_collector,
            thresholds=DegradationThresholds(),
        )

    @pytest.fixture
    def baseline(self):
        """Create baseline snapshot."""
        return GovernanceMetricsSnapshot(
            snapshot_id="baseline",
            constitutional_version="1.0.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            total_requests=1000,
            violations_count=10,
            violations_rate=0.01,
            governance_latency_p99=2.0,
            deliberation_success_rate=0.95,
            maci_violations_count=0,
            error_rate=0.02,
            health_score=0.95,
            escalated_requests=100,
        )

    def test_analyze_violations_rate_critical(self, detector, baseline):
        """Test violations rate analysis with critical degradation."""
        current = GovernanceMetricsSnapshot(
            snapshot_id="current",
            constitutional_version="1.0.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            total_requests=1000,
            violations_count=100,
            violations_rate=0.10,  # 10x increase
            governance_latency_p99=2.0,
            deliberation_success_rate=0.95,
            maci_violations_count=0,
            error_rate=0.02,
            health_score=0.95,
            escalated_requests=100,
        )

        analysis = detector._analyze_violations_rate(baseline, current)

        assert analysis.metric_name == "violations_rate"
        assert analysis.threshold_exceeded is True
        assert analysis.severity == DegradationSeverity.CRITICAL

    def test_analyze_latency_p99_high(self, detector, baseline):
        """Test P99 latency analysis with high degradation."""
        current = GovernanceMetricsSnapshot(
            snapshot_id="current",
            constitutional_version="1.0.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            total_requests=1000,
            violations_count=10,
            violations_rate=0.01,
            governance_latency_p99=8.0,  # 4x increase
            deliberation_success_rate=0.95,
            maci_violations_count=0,
            error_rate=0.02,
            health_score=0.95,
            escalated_requests=100,
        )

        analysis = detector._analyze_latency_p99(baseline, current)

        assert analysis.metric_name == "latency_p99"
        assert analysis.threshold_exceeded is True
        assert analysis.severity in (DegradationSeverity.HIGH, DegradationSeverity.MODERATE)

    def test_analyze_deliberation_success_rate_critical(self, detector, baseline):
        """Test deliberation success rate with critical degradation."""
        current = GovernanceMetricsSnapshot(
            snapshot_id="current",
            constitutional_version="1.0.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            total_requests=1000,
            violations_count=10,
            violations_rate=0.01,
            governance_latency_p99=2.0,
            deliberation_success_rate=0.70,  # Below 85% threshold
            maci_violations_count=0,
            error_rate=0.02,
            health_score=0.95,
            escalated_requests=100,
        )

        analysis = detector._analyze_deliberation_success_rate(baseline, current)

        assert analysis.metric_name == "deliberation_success_rate"
        assert analysis.threshold_exceeded is True
        assert analysis.severity == DegradationSeverity.CRITICAL

    def test_analyze_maci_violations_high(self, detector, baseline):
        """Test MACI violations with high degradation."""
        current = GovernanceMetricsSnapshot(
            snapshot_id="current",
            constitutional_version="1.0.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            total_requests=1000,
            violations_count=10,
            violations_rate=0.01,
            governance_latency_p99=2.0,
            deliberation_success_rate=0.95,
            maci_violations_count=7,  # Significant increase
            error_rate=0.02,
            health_score=0.95,
            escalated_requests=100,
        )

        analysis = detector._analyze_maci_violations(baseline, current)

        assert analysis.metric_name == "maci_violations_count"
        assert analysis.threshold_exceeded is True
        assert analysis.severity in (DegradationSeverity.HIGH, DegradationSeverity.MODERATE)

    def test_analyze_health_score_critical(self, detector, baseline):
        """Test health score with critical degradation.

        Note: health_score is a computed property in GovernanceMetricsSnapshot.
        To test critical degradation, we create mock snapshots with controlled
        health_score values.
        """
        # Create mock snapshots with controlled health_score values
        # since health_score is a computed property
        mock_baseline = MagicMock()
        mock_baseline.health_score = 0.95

        mock_current = MagicMock()
        mock_current.health_score = 0.50  # Below 60% critical threshold

        analysis = detector._analyze_health_score(mock_baseline, mock_current)

        assert analysis.metric_name == "health_score"
        assert analysis.threshold_exceeded is True
        assert analysis.severity == DegradationSeverity.CRITICAL


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
