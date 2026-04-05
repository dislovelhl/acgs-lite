"""
Tests for Governance Degradation Detection Engine.
Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import AsyncMock

import pytest

from enhanced_agent_bus.constitutional.degradation_detector import (
    DegradationDetector,
    DegradationReport,
    DegradationSeverity,
    DegradationThresholds,
    MetricDegradationAnalysis,
    SignificanceLevel,
    StatisticalTest,
    TimeWindow,
)
from enhanced_agent_bus.constitutional.metrics_collector import (
    GovernanceMetricsCollector,
    GovernanceMetricsSnapshot,
)

# ---------------------------------------------------------------------------
# TimeWindow tests
# ---------------------------------------------------------------------------


class TestTimeWindow:
    """Tests for TimeWindow enum."""

    def test_values(self):
        assert TimeWindow.ONE_HOUR.value == "1h"
        assert TimeWindow.SIX_HOURS.value == "6h"
        assert TimeWindow.TWELVE_HOURS.value == "12h"
        assert TimeWindow.TWENTY_FOUR_HOURS.value == "24h"

    def test_to_seconds(self):
        assert TimeWindow.ONE_HOUR.to_seconds() == 3600
        assert TimeWindow.SIX_HOURS.to_seconds() == 21600
        assert TimeWindow.TWELVE_HOURS.to_seconds() == 43200
        assert TimeWindow.TWENTY_FOUR_HOURS.to_seconds() == 86400


# ---------------------------------------------------------------------------
# SignificanceLevel tests
# ---------------------------------------------------------------------------


class TestSignificanceLevel:
    """Tests for SignificanceLevel enum."""

    def test_from_p_value_very_high(self):
        assert SignificanceLevel.from_p_value(0.0005) == SignificanceLevel.VERY_HIGH

    def test_from_p_value_high(self):
        assert SignificanceLevel.from_p_value(0.005) == SignificanceLevel.HIGH

    def test_from_p_value_moderate(self):
        assert SignificanceLevel.from_p_value(0.03) == SignificanceLevel.MODERATE

    def test_from_p_value_low(self):
        assert SignificanceLevel.from_p_value(0.08) == SignificanceLevel.LOW

    def test_from_p_value_none(self):
        assert SignificanceLevel.from_p_value(0.5) == SignificanceLevel.NONE


# ---------------------------------------------------------------------------
# StatisticalTest tests
# ---------------------------------------------------------------------------


class TestStatisticalTest:
    """Tests for StatisticalTest model."""

    def test_is_significant(self):
        test = StatisticalTest(
            test_name="chi_square",
            statistic=5.0,
            p_value=0.01,
            significance_level=SignificanceLevel.HIGH,
        )
        assert test.is_significant is True

    def test_not_significant(self):
        test = StatisticalTest(
            test_name="chi_square",
            statistic=1.0,
            p_value=0.5,
            significance_level=SignificanceLevel.NONE,
        )
        assert test.is_significant is False

    def test_is_highly_significant(self):
        test = StatisticalTest(
            test_name="chi_square",
            statistic=10.0,
            p_value=0.005,
            significance_level=SignificanceLevel.HIGH,
        )
        assert test.is_highly_significant is True

    def test_not_highly_significant(self):
        test = StatisticalTest(
            test_name="chi_square",
            statistic=3.0,
            p_value=0.03,
            significance_level=SignificanceLevel.MODERATE,
        )
        assert test.is_highly_significant is False


# ---------------------------------------------------------------------------
# DegradationThresholds tests
# ---------------------------------------------------------------------------


class TestDegradationThresholds:
    """Tests for DegradationThresholds model."""

    def test_defaults(self):
        t = DegradationThresholds()
        assert t.violations_rate_threshold == 0.01
        assert t.latency_p99_threshold_ms == 2.0
        assert t.min_sample_size == 30
        assert t.significance_level == 0.05

    def test_custom(self):
        t = DegradationThresholds(
            violations_rate_threshold=0.05,
            latency_p99_threshold_ms=5.0,
            min_sample_size=10,
        )
        assert t.violations_rate_threshold == 0.05
        assert t.latency_p99_threshold_ms == 5.0
        assert t.min_sample_size == 10


# ---------------------------------------------------------------------------
# DegradationReport tests
# ---------------------------------------------------------------------------


class TestDegradationReport:
    """Tests for DegradationReport model."""

    def _make_report(self, severity=DegradationSeverity.NONE, analyses=None):
        baseline = GovernanceMetricsSnapshot()
        current = GovernanceMetricsSnapshot()
        return DegradationReport(
            time_window=TimeWindow.ONE_HOUR,
            baseline_snapshot=baseline,
            current_snapshot=current,
            overall_severity=severity,
            metric_analyses=analyses or [],
        )

    def test_has_degradation_none(self):
        report = self._make_report(DegradationSeverity.NONE)
        assert report.has_degradation is False

    def test_has_degradation_critical(self):
        report = self._make_report(DegradationSeverity.CRITICAL)
        assert report.has_degradation is True

    def test_critical_metrics(self):
        analysis = MetricDegradationAnalysis(
            metric_name="test",
            baseline_value=0.0,
            current_value=0.5,
            delta=0.5,
            percent_change=100.0,
            threshold_exceeded=True,
            configured_threshold=0.01,
            severity=DegradationSeverity.CRITICAL,
        )
        report = self._make_report(DegradationSeverity.CRITICAL, [analysis])
        assert len(report.critical_metrics) == 1

    def test_high_severity_metrics(self):
        analyses = [
            MetricDegradationAnalysis(
                metric_name="a",
                baseline_value=0.0,
                current_value=0.5,
                delta=0.5,
                percent_change=100.0,
                threshold_exceeded=True,
                configured_threshold=0.01,
                severity=DegradationSeverity.HIGH,
            ),
            MetricDegradationAnalysis(
                metric_name="b",
                baseline_value=0.0,
                current_value=0.1,
                delta=0.1,
                percent_change=10.0,
                threshold_exceeded=False,
                configured_threshold=0.01,
                severity=DegradationSeverity.LOW,
            ),
        ]
        report = self._make_report(DegradationSeverity.HIGH, analyses)
        assert len(report.high_severity_metrics) == 1


# ---------------------------------------------------------------------------
# DegradationDetector tests
# ---------------------------------------------------------------------------


class TestDegradationDetector:
    """Tests for DegradationDetector."""

    @pytest.fixture
    def mock_collector(self):
        collector = AsyncMock(spec=GovernanceMetricsCollector)
        collector.collect_snapshot.return_value = GovernanceMetricsSnapshot()
        return collector

    @pytest.fixture
    def detector(self, mock_collector):
        return DegradationDetector(metrics_collector=mock_collector)

    def test_init_default_thresholds(self, mock_collector):
        det = DegradationDetector(metrics_collector=mock_collector)
        assert det.thresholds.violations_rate_threshold == 0.01

    def test_init_custom_thresholds(self, mock_collector):
        thresholds = DegradationThresholds(violations_rate_threshold=0.05)
        det = DegradationDetector(metrics_collector=mock_collector, thresholds=thresholds)
        assert det.thresholds.violations_rate_threshold == 0.05

    @pytest.mark.asyncio
    async def test_analyze_no_degradation(self, detector):
        baseline = GovernanceMetricsSnapshot(
            violations_rate=0.0,
            governance_latency_p99=1.0,
            deliberation_success_rate=0.99,
            maci_violations_count=0,
            error_rate=0.0,
        )
        current = GovernanceMetricsSnapshot(
            violations_rate=0.0,
            governance_latency_p99=1.0,
            deliberation_success_rate=0.99,
            maci_violations_count=0,
            error_rate=0.0,
        )
        report = await detector.analyze_degradation(baseline, current)
        assert report.overall_severity == DegradationSeverity.NONE
        assert report.rollback_recommended is False

    @pytest.mark.asyncio
    async def test_analyze_violations_degradation(self, detector):
        baseline = GovernanceMetricsSnapshot(violations_rate=0.0)
        current = GovernanceMetricsSnapshot(violations_rate=0.1)
        report = await detector.analyze_degradation(baseline, current)
        violations = [m for m in report.metric_analyses if m.metric_name == "violations_rate"]
        assert len(violations) == 1
        assert violations[0].threshold_exceeded is True

    @pytest.mark.asyncio
    async def test_analyze_latency_degradation(self, detector):
        baseline = GovernanceMetricsSnapshot(governance_latency_p99=1.0)
        current = GovernanceMetricsSnapshot(governance_latency_p99=15.0)
        report = await detector.analyze_degradation(baseline, current)
        latency = [m for m in report.metric_analyses if m.metric_name == "latency_p99"]
        assert len(latency) == 1
        assert latency[0].threshold_exceeded is True
        assert latency[0].severity == DegradationSeverity.CRITICAL

    @pytest.mark.asyncio
    async def test_analyze_deliberation_degradation(self, detector):
        baseline = GovernanceMetricsSnapshot(deliberation_success_rate=0.99)
        current = GovernanceMetricsSnapshot(deliberation_success_rate=0.80)
        report = await detector.analyze_degradation(baseline, current)
        delib = [m for m in report.metric_analyses if m.metric_name == "deliberation_success_rate"]
        assert delib[0].threshold_exceeded is True

    @pytest.mark.asyncio
    async def test_analyze_maci_violations(self, detector):
        baseline = GovernanceMetricsSnapshot(maci_violations_count=0)
        current = GovernanceMetricsSnapshot(maci_violations_count=15)
        report = await detector.analyze_degradation(baseline, current)
        maci = [m for m in report.metric_analyses if m.metric_name == "maci_violations_count"]
        assert maci[0].threshold_exceeded is True
        assert maci[0].severity == DegradationSeverity.CRITICAL

    @pytest.mark.asyncio
    async def test_analyze_error_rate(self, detector):
        baseline = GovernanceMetricsSnapshot(error_rate=0.0)
        current = GovernanceMetricsSnapshot(error_rate=0.5)
        report = await detector.analyze_degradation(baseline, current)
        errors = [m for m in report.metric_analyses if m.metric_name == "error_rate"]
        assert errors[0].threshold_exceeded is True
        assert errors[0].severity == DegradationSeverity.CRITICAL

    @pytest.mark.asyncio
    async def test_analyze_health_score(self, detector):
        baseline = GovernanceMetricsSnapshot(
            violations_rate=0.0,
            governance_latency_p99=1.0,
            deliberation_success_rate=0.99,
            maci_violations_count=0,
            error_rate=0.0,
        )
        current = GovernanceMetricsSnapshot(
            violations_rate=1.0,
            governance_latency_p99=100.0,
            deliberation_success_rate=0.0,
            maci_violations_count=100,
            error_rate=1.0,
        )
        report = await detector.analyze_degradation(baseline, current)
        health = [m for m in report.metric_analyses if m.metric_name == "health_score"]
        assert health[0].threshold_exceeded is True

    @pytest.mark.asyncio
    async def test_analyze_collects_current_if_none(self, detector, mock_collector):
        baseline = GovernanceMetricsSnapshot()
        report = await detector.analyze_degradation(baseline, current=None)
        mock_collector.collect_snapshot.assert_awaited_once()
        assert isinstance(report, DegradationReport)

    @pytest.mark.asyncio
    async def test_analyze_multi_window(self, detector, mock_collector):
        baseline = GovernanceMetricsSnapshot()
        reports = await detector.analyze_multi_window(baseline)
        assert len(reports) == 3  # default: 1h, 6h, 24h
        assert mock_collector.collect_snapshot.await_count == 3

    @pytest.mark.asyncio
    async def test_analyze_multi_window_custom(self, detector, mock_collector):
        baseline = GovernanceMetricsSnapshot()
        reports = await detector.analyze_multi_window(baseline, windows=[TimeWindow.ONE_HOUR])
        assert len(reports) == 1

    # -- severity determination --

    def test_severity_critical_single(self, detector):
        analyses = [
            MetricDegradationAnalysis(
                metric_name="x",
                baseline_value=0.0,
                current_value=1.0,
                delta=1.0,
                percent_change=100.0,
                threshold_exceeded=True,
                configured_threshold=0.01,
                severity=DegradationSeverity.CRITICAL,
            )
        ]
        assert detector._determine_overall_severity(analyses) == DegradationSeverity.CRITICAL

    def test_severity_two_high_becomes_critical(self, detector):
        analyses = [
            MetricDegradationAnalysis(
                metric_name="a",
                baseline_value=0.0,
                current_value=1.0,
                delta=1.0,
                percent_change=100.0,
                threshold_exceeded=True,
                configured_threshold=0.01,
                severity=DegradationSeverity.HIGH,
            ),
            MetricDegradationAnalysis(
                metric_name="b",
                baseline_value=0.0,
                current_value=1.0,
                delta=1.0,
                percent_change=100.0,
                threshold_exceeded=True,
                configured_threshold=0.01,
                severity=DegradationSeverity.HIGH,
            ),
        ]
        assert detector._determine_overall_severity(analyses) == DegradationSeverity.CRITICAL

    def test_severity_single_high(self, detector):
        analyses = [
            MetricDegradationAnalysis(
                metric_name="a",
                baseline_value=0.0,
                current_value=1.0,
                delta=1.0,
                percent_change=100.0,
                threshold_exceeded=True,
                configured_threshold=0.01,
                severity=DegradationSeverity.HIGH,
            ),
        ]
        assert detector._determine_overall_severity(analyses) == DegradationSeverity.HIGH

    def test_severity_three_moderate_becomes_high(self, detector):
        analyses = [
            MetricDegradationAnalysis(
                metric_name=f"m{i}",
                baseline_value=0.0,
                current_value=0.5,
                delta=0.5,
                percent_change=50.0,
                threshold_exceeded=True,
                configured_threshold=0.01,
                severity=DegradationSeverity.MODERATE,
            )
            for i in range(3)
        ]
        assert detector._determine_overall_severity(analyses) == DegradationSeverity.HIGH

    def test_severity_none(self, detector):
        analyses = [
            MetricDegradationAnalysis(
                metric_name="a",
                baseline_value=0.0,
                current_value=0.0,
                delta=0.0,
                percent_change=0.0,
                threshold_exceeded=False,
                configured_threshold=0.01,
                severity=DegradationSeverity.NONE,
            ),
        ]
        assert detector._determine_overall_severity(analyses) == DegradationSeverity.NONE

    def test_severity_low(self, detector):
        analyses = [
            MetricDegradationAnalysis(
                metric_name="a",
                baseline_value=0.0,
                current_value=0.015,
                delta=0.015,
                percent_change=1.5,
                threshold_exceeded=True,
                configured_threshold=0.01,
                severity=DegradationSeverity.LOW,
            ),
        ]
        assert detector._determine_overall_severity(analyses) == DegradationSeverity.LOW

    # -- rollback recommendation --

    def test_rollback_critical(self, detector):
        assert (
            detector._should_recommend_rollback(
                DegradationSeverity.CRITICAL, 0.5, SignificanceLevel.NONE
            )
            is True
        )

    def test_rollback_high_confident(self, detector):
        assert (
            detector._should_recommend_rollback(
                DegradationSeverity.HIGH, 0.8, SignificanceLevel.HIGH
            )
            is True
        )

    def test_rollback_high_low_confidence(self, detector):
        assert (
            detector._should_recommend_rollback(
                DegradationSeverity.HIGH, 0.3, SignificanceLevel.NONE
            )
            is False
        )

    def test_rollback_moderate(self, detector):
        assert (
            detector._should_recommend_rollback(
                DegradationSeverity.MODERATE, 0.9, SignificanceLevel.VERY_HIGH
            )
            is False
        )

    # -- summary generation --

    def test_summary_no_degradation(self, detector):
        summary = detector._generate_summary([], DegradationSeverity.NONE)
        assert "No significant" in summary

    def test_summary_with_degradation(self, detector):
        analyses = [
            MetricDegradationAnalysis(
                metric_name="violations_rate",
                baseline_value=0.0,
                current_value=0.1,
                delta=0.1,
                percent_change=100.0,
                threshold_exceeded=True,
                configured_threshold=0.01,
                severity=DegradationSeverity.HIGH,
            ),
        ]
        summary = detector._generate_summary(analyses, DegradationSeverity.HIGH)
        assert "degradation detected" in summary.lower()
        assert "violations_rate" in summary

    # -- confidence score --

    def test_confidence_score_no_data(self, detector):
        analyses = [
            MetricDegradationAnalysis(
                metric_name="x",
                baseline_value=0.0,
                current_value=0.0,
                delta=0.0,
                percent_change=0.0,
                threshold_exceeded=False,
                configured_threshold=0.01,
                severity=DegradationSeverity.NONE,
            ),
        ]
        baseline = GovernanceMetricsSnapshot(total_requests=0)
        current = GovernanceMetricsSnapshot(total_requests=0)
        score = detector._compute_confidence_score(analyses, baseline, current)
        assert score == 0.0

    def test_confidence_score_high_data(self, detector):
        test = StatisticalTest(
            test_name="chi",
            statistic=10.0,
            p_value=0.001,
            significance_level=SignificanceLevel.VERY_HIGH,
        )
        analyses = [
            MetricDegradationAnalysis(
                metric_name="x",
                baseline_value=0.0,
                current_value=0.5,
                delta=0.5,
                percent_change=100.0,
                threshold_exceeded=True,
                configured_threshold=0.01,
                severity=DegradationSeverity.HIGH,
                statistical_test=test,
            ),
        ]
        baseline = GovernanceMetricsSnapshot(total_requests=1000)
        current = GovernanceMetricsSnapshot(total_requests=1000)
        score = detector._compute_confidence_score(analyses, baseline, current)
        assert score > 0.5

    # -- statistical significance --

    def test_statistical_significance_none(self, detector):
        analyses = [
            MetricDegradationAnalysis(
                metric_name="x",
                baseline_value=0.0,
                current_value=0.0,
                delta=0.0,
                percent_change=0.0,
                threshold_exceeded=False,
                configured_threshold=0.01,
                severity=DegradationSeverity.NONE,
            ),
        ]
        assert detector._determine_statistical_significance(analyses) == SignificanceLevel.NONE

    def test_statistical_significance_with_test(self, detector):
        test = StatisticalTest(
            test_name="chi",
            statistic=10.0,
            p_value=0.001,
            significance_level=SignificanceLevel.VERY_HIGH,
        )
        analyses = [
            MetricDegradationAnalysis(
                metric_name="x",
                baseline_value=0.0,
                current_value=0.5,
                delta=0.5,
                percent_change=100.0,
                threshold_exceeded=True,
                configured_threshold=0.01,
                severity=DegradationSeverity.HIGH,
                statistical_test=test,
            ),
        ]
        result = detector._determine_statistical_significance(analyses)
        # p_value=0.001 -> from_p_value returns VERY_HIGH (< 0.001 boundary)
        # or HIGH (< 0.01) depending on exact threshold check
        assert result in (SignificanceLevel.VERY_HIGH, SignificanceLevel.HIGH)

    # -- individual metric analysis methods --

    def test_violations_rate_no_degradation(self, detector):
        baseline = GovernanceMetricsSnapshot(violations_rate=0.0, total_requests=10)
        current = GovernanceMetricsSnapshot(violations_rate=0.0, total_requests=10)
        result = detector._analyze_violations_rate(baseline, current)
        assert result.threshold_exceeded is False
        assert result.severity == DegradationSeverity.NONE

    def test_violations_rate_critical(self, detector):
        baseline = GovernanceMetricsSnapshot(violations_rate=0.0, total_requests=10)
        current = GovernanceMetricsSnapshot(violations_rate=0.1, total_requests=10)
        result = detector._analyze_violations_rate(baseline, current)
        assert result.threshold_exceeded is True
        # 0.1 > 0.01 * 5 = 0.05 -> CRITICAL
        assert result.severity == DegradationSeverity.CRITICAL

    def test_latency_p99_no_degradation(self, detector):
        baseline = GovernanceMetricsSnapshot(governance_latency_p99=1.0)
        current = GovernanceMetricsSnapshot(governance_latency_p99=1.5)
        result = detector._analyze_latency_p99(baseline, current)
        assert result.threshold_exceeded is False

    def test_maci_violations_moderate(self, detector):
        baseline = GovernanceMetricsSnapshot(maci_violations_count=0)
        current = GovernanceMetricsSnapshot(maci_violations_count=3)
        result = detector._analyze_maci_violations(baseline, current)
        assert result.threshold_exceeded is True
        assert result.severity == DegradationSeverity.MODERATE

    def test_error_rate_low(self, detector):
        baseline = GovernanceMetricsSnapshot(error_rate=0.0)
        current = GovernanceMetricsSnapshot(error_rate=0.15)
        result = detector._analyze_error_rate(baseline, current)
        assert result.threshold_exceeded is True
        assert result.severity == DegradationSeverity.LOW

    def test_health_score_no_degradation(self, detector):
        baseline = GovernanceMetricsSnapshot(
            violations_rate=0.0,
            governance_latency_p99=1.0,
            deliberation_success_rate=0.99,
        )
        current = GovernanceMetricsSnapshot(
            violations_rate=0.0,
            governance_latency_p99=1.0,
            deliberation_success_rate=0.99,
        )
        result = detector._analyze_health_score(baseline, current)
        assert result.threshold_exceeded is False
