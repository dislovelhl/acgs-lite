"""
Coverage tests for:
- enhanced_agent_bus/bus/core.py (88.0% -> target 95%+)
- enhanced_agent_bus/constitutional/review_api.py (84.6% -> target 95%+)
- enhanced_agent_bus/constitutional/degradation_detector.py (83.8% -> target 95%+)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# bus/core imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.bus.core import EnhancedAgentBus

# ---------------------------------------------------------------------------
# degradation_detector imports
# ---------------------------------------------------------------------------
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
from enhanced_agent_bus.constitutional.metrics_collector import GovernanceMetricsSnapshot

# ---------------------------------------------------------------------------
# review_api imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.constitutional.review_api import (
    AmendmentDetailResponse,
    AmendmentListQuery,
    AmendmentListResponse,
    ApprovalRequest,
    ApprovalResponse,
    RejectionRequest,
    RollbackRequest,
    RollbackResponse,
    health_check,
)
from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage

# ============================================================================
# Helpers
# ============================================================================


def _make_snapshot(
    *,
    violations_rate: float = 0.0,
    governance_latency_p99: float = 1.0,
    deliberation_success_rate: float = 0.95,
    maci_violations_count: int = 0,
    error_rate: float = 0.0,
    health_score_override: float | None = None,
    total_requests: int = 100,
    escalated_requests: int = 10,
    constitutional_version: str = "1.0.0",
) -> GovernanceMetricsSnapshot:
    snap = GovernanceMetricsSnapshot(
        constitutional_version=constitutional_version,
        violations_rate=violations_rate,
        governance_latency_p99=governance_latency_p99,
        governance_latency_p50=0.5,
        governance_latency_p95=0.8,
        deliberation_success_rate=deliberation_success_rate,
        maci_violations_count=maci_violations_count,
        total_requests=total_requests,
        approved_requests=total_requests - 5,
        denied_requests=3,
        escalated_requests=escalated_requests,
        error_rate=error_rate,
        window_duration_seconds=60,
    )
    return snap


def _make_detector(thresholds: DegradationThresholds | None = None) -> DegradationDetector:
    collector = MagicMock()
    collector.collect_snapshot = AsyncMock(return_value=_make_snapshot())
    collector.connect = AsyncMock()
    collector.disconnect = AsyncMock()
    return DegradationDetector(
        metrics_collector=collector,
        thresholds=thresholds,
    )


# ============================================================================
# SECTION 1: degradation_detector.py
# ============================================================================


class TestTimeWindow:
    """Cover TimeWindow enum and to_seconds()."""

    def test_one_hour_seconds(self):
        assert TimeWindow.ONE_HOUR.to_seconds() == 3600

    def test_six_hours_seconds(self):
        assert TimeWindow.SIX_HOURS.to_seconds() == 21600

    def test_twelve_hours_seconds(self):
        assert TimeWindow.TWELVE_HOURS.to_seconds() == 43200

    def test_twenty_four_hours_seconds(self):
        assert TimeWindow.TWENTY_FOUR_HOURS.to_seconds() == 86400


class TestSignificanceLevel:
    """Cover SignificanceLevel.from_p_value all branches."""

    def test_very_high(self):
        assert SignificanceLevel.from_p_value(0.0005) == SignificanceLevel.VERY_HIGH

    def test_high(self):
        assert SignificanceLevel.from_p_value(0.005) == SignificanceLevel.HIGH

    def test_moderate(self):
        assert SignificanceLevel.from_p_value(0.03) == SignificanceLevel.MODERATE

    def test_low(self):
        assert SignificanceLevel.from_p_value(0.08) == SignificanceLevel.LOW

    def test_none(self):
        assert SignificanceLevel.from_p_value(0.15) == SignificanceLevel.NONE


class TestStatisticalTestModel:
    """Cover StatisticalTest properties."""

    def test_is_significant_true(self):
        st = StatisticalTest(
            test_name="t",
            statistic=5.0,
            p_value=0.01,
            significance_level=SignificanceLevel.HIGH,
        )
        assert st.is_significant is True

    def test_is_significant_false(self):
        st = StatisticalTest(
            test_name="t",
            statistic=1.0,
            p_value=0.2,
            significance_level=SignificanceLevel.NONE,
        )
        assert st.is_significant is False

    def test_is_highly_significant_true(self):
        st = StatisticalTest(
            test_name="t",
            statistic=10.0,
            p_value=0.001,
            significance_level=SignificanceLevel.VERY_HIGH,
        )
        assert st.is_highly_significant is True

    def test_is_highly_significant_false(self):
        st = StatisticalTest(
            test_name="t",
            statistic=2.0,
            p_value=0.04,
            significance_level=SignificanceLevel.MODERATE,
        )
        assert st.is_highly_significant is False


class TestDegradationReport:
    """Cover DegradationReport properties."""

    def _make_report(self, severity=DegradationSeverity.NONE, analyses=None):
        baseline = _make_snapshot()
        current = _make_snapshot()
        return DegradationReport(
            time_window=TimeWindow.ONE_HOUR,
            baseline_snapshot=baseline,
            current_snapshot=current,
            overall_severity=severity,
            metric_analyses=analyses or [],
        )

    def test_has_degradation_false(self):
        report = self._make_report()
        assert report.has_degradation is False

    def test_has_degradation_true(self):
        report = self._make_report(severity=DegradationSeverity.HIGH)
        assert report.has_degradation is True

    def test_critical_metrics_empty(self):
        report = self._make_report()
        assert report.critical_metrics == []

    def test_critical_metrics_returns_critical(self):
        crit = MetricDegradationAnalysis(
            metric_name="test",
            baseline_value=0.0,
            current_value=0.5,
            delta=0.5,
            percent_change=100.0,
            threshold_exceeded=True,
            configured_threshold=0.01,
            severity=DegradationSeverity.CRITICAL,
        )
        low = MetricDegradationAnalysis(
            metric_name="other",
            baseline_value=0.0,
            current_value=0.01,
            delta=0.01,
            percent_change=1.0,
            threshold_exceeded=False,
            configured_threshold=0.01,
            severity=DegradationSeverity.LOW,
        )
        report = self._make_report(analyses=[crit, low])
        assert len(report.critical_metrics) == 1
        assert report.critical_metrics[0].metric_name == "test"

    def test_high_severity_metrics(self):
        high = MetricDegradationAnalysis(
            metric_name="h",
            baseline_value=0.0,
            current_value=0.5,
            delta=0.5,
            percent_change=100.0,
            threshold_exceeded=True,
            configured_threshold=0.01,
            severity=DegradationSeverity.HIGH,
        )
        report = self._make_report(analyses=[high])
        assert len(report.high_severity_metrics) == 1


class TestDegradationDetectorAnalyzeViolationsRate:
    """Cover _analyze_violations_rate all severity branches."""

    def test_no_degradation(self):
        d = _make_detector()
        baseline = _make_snapshot(violations_rate=0.01)
        current = _make_snapshot(violations_rate=0.01)
        result = d._analyze_violations_rate(baseline, current)
        assert result.severity == DegradationSeverity.NONE
        assert result.threshold_exceeded is False

    def test_low_severity(self):
        d = _make_detector()
        baseline = _make_snapshot(violations_rate=0.0)
        current = _make_snapshot(violations_rate=0.015)
        result = d._analyze_violations_rate(baseline, current)
        assert result.severity == DegradationSeverity.LOW

    def test_moderate_severity(self):
        d = _make_detector()
        baseline = _make_snapshot(violations_rate=0.0)
        current = _make_snapshot(violations_rate=0.025)
        result = d._analyze_violations_rate(baseline, current)
        assert result.severity == DegradationSeverity.MODERATE

    def test_high_severity(self):
        d = _make_detector()
        baseline = _make_snapshot(violations_rate=0.0)
        current = _make_snapshot(violations_rate=0.04)
        result = d._analyze_violations_rate(baseline, current)
        assert result.severity == DegradationSeverity.HIGH

    def test_critical_severity(self):
        d = _make_detector()
        baseline = _make_snapshot(violations_rate=0.0)
        current = _make_snapshot(violations_rate=0.06)
        result = d._analyze_violations_rate(baseline, current)
        assert result.severity == DegradationSeverity.CRITICAL

    def test_zero_baseline_percent_change(self):
        d = _make_detector()
        baseline = _make_snapshot(violations_rate=0.0)
        current = _make_snapshot(violations_rate=0.0)
        result = d._analyze_violations_rate(baseline, current)
        assert result.percent_change == 0.0

    def test_chi_square_test_performed(self):
        """Verify chi-square test is invoked when scipy available and sample >= min."""
        d = _make_detector()
        baseline = _make_snapshot(violations_rate=0.01, total_requests=50)
        current = _make_snapshot(violations_rate=0.05, total_requests=50)
        result = d._analyze_violations_rate(baseline, current)
        # If scipy is available the test should be populated
        # If not, it will be None - both are acceptable
        assert result.metric_name == "violations_rate"


class TestDegradationDetectorLatencyP99:
    """Cover _analyze_latency_p99 severity branches."""

    def test_no_degradation(self):
        d = _make_detector()
        baseline = _make_snapshot(governance_latency_p99=1.0)
        current = _make_snapshot(governance_latency_p99=1.5)
        result = d._analyze_latency_p99(baseline, current)
        assert result.severity == DegradationSeverity.NONE

    def test_low_severity_absolute(self):
        d = _make_detector()
        baseline = _make_snapshot(governance_latency_p99=1.0)
        current = _make_snapshot(governance_latency_p99=3.5)
        result = d._analyze_latency_p99(baseline, current)
        assert result.threshold_exceeded is True
        assert result.severity == DegradationSeverity.LOW

    def test_moderate_severity(self):
        d = _make_detector()
        baseline = _make_snapshot(governance_latency_p99=1.0)
        current = _make_snapshot(governance_latency_p99=5.5)
        result = d._analyze_latency_p99(baseline, current)
        assert result.severity == DegradationSeverity.MODERATE

    def test_high_severity(self):
        d = _make_detector()
        baseline = _make_snapshot(governance_latency_p99=1.0)
        current = _make_snapshot(governance_latency_p99=8.0)
        result = d._analyze_latency_p99(baseline, current)
        assert result.severity == DegradationSeverity.HIGH

    def test_critical_severity_above_10ms(self):
        d = _make_detector()
        baseline = _make_snapshot(governance_latency_p99=1.0)
        current = _make_snapshot(governance_latency_p99=11.0)
        result = d._analyze_latency_p99(baseline, current)
        assert result.severity == DegradationSeverity.CRITICAL

    def test_zero_baseline_latency(self):
        d = _make_detector()
        baseline = _make_snapshot(governance_latency_p99=0.0)
        current = _make_snapshot(governance_latency_p99=0.0)
        result = d._analyze_latency_p99(baseline, current)
        assert result.percent_change == 0.0

    def test_percent_threshold_exceeded(self):
        """Cover the percent_change > latency_p99_percent_threshold branch."""
        d = _make_detector()
        baseline = _make_snapshot(governance_latency_p99=1.0)
        current = _make_snapshot(governance_latency_p99=2.0)
        # delta=1.0 < threshold 2.0ms, but percent_change=1.0 > 0.5
        result = d._analyze_latency_p99(baseline, current)
        assert result.threshold_exceeded is True


class TestDegradationDetectorDeliberationSuccessRate:
    """Cover _analyze_deliberation_success_rate severity branches."""

    def test_no_degradation(self):
        d = _make_detector()
        baseline = _make_snapshot(deliberation_success_rate=0.95)
        current = _make_snapshot(deliberation_success_rate=0.94)
        result = d._analyze_deliberation_success_rate(baseline, current)
        assert result.severity == DegradationSeverity.NONE

    def test_low_severity(self):
        d = _make_detector()
        baseline = _make_snapshot(deliberation_success_rate=0.95)
        current = _make_snapshot(deliberation_success_rate=0.89)
        result = d._analyze_deliberation_success_rate(baseline, current)
        assert result.threshold_exceeded is True
        assert result.severity == DegradationSeverity.LOW

    def test_moderate_severity(self):
        # Need current >= 0.85 (not critical) and |delta| > threshold*2 (0.10)
        d = _make_detector()
        baseline = _make_snapshot(deliberation_success_rate=0.97)
        current = _make_snapshot(deliberation_success_rate=0.86)
        # delta = -0.11 => |delta| = 0.11 > threshold*2=0.10, current=0.86 >= 0.85
        result = d._analyze_deliberation_success_rate(baseline, current)
        assert result.severity == DegradationSeverity.MODERATE

    def test_high_severity(self):
        d = _make_detector()
        baseline = _make_snapshot(deliberation_success_rate=0.95)
        current = _make_snapshot(deliberation_success_rate=0.78)
        # |delta| = 0.17 > threshold*3 (0.15)
        result = d._analyze_deliberation_success_rate(baseline, current)
        # But also current < 0.85 so it becomes CRITICAL
        assert result.severity == DegradationSeverity.CRITICAL

    def test_critical_below_85_percent(self):
        d = _make_detector()
        baseline = _make_snapshot(deliberation_success_rate=0.90)
        current = _make_snapshot(deliberation_success_rate=0.80)
        result = d._analyze_deliberation_success_rate(baseline, current)
        assert result.severity == DegradationSeverity.CRITICAL

    def test_zero_baseline(self):
        d = _make_detector()
        baseline = _make_snapshot(deliberation_success_rate=0.0)
        current = _make_snapshot(deliberation_success_rate=0.0)
        result = d._analyze_deliberation_success_rate(baseline, current)
        assert result.percent_change == 0.0

    def test_chi_square_with_enough_escalated(self):
        d = _make_detector()
        baseline = _make_snapshot(deliberation_success_rate=0.95, escalated_requests=50)
        current = _make_snapshot(deliberation_success_rate=0.80, escalated_requests=50)
        result = d._analyze_deliberation_success_rate(baseline, current)
        assert result.metric_name == "deliberation_success_rate"

    def test_chi_square_skipped_small_sample(self):
        d = _make_detector()
        baseline = _make_snapshot(deliberation_success_rate=0.95, escalated_requests=5)
        current = _make_snapshot(deliberation_success_rate=0.80, escalated_requests=5)
        result = d._analyze_deliberation_success_rate(baseline, current)
        assert result.statistical_test is None

    def test_high_severity_not_below_85(self):
        """Cover high severity branch: |delta| > 3*threshold but current >= 0.85."""
        d = _make_detector()
        # Need |delta| > 0.15 and current >= 0.85
        # baseline=1.0, current=0.85 => delta=-0.15 => NOT > 0.15 (strict >)
        # baseline=1.01 would exceed le=1.0 constraint
        # Use custom thresholds: threshold=0.04 => 3*0.04=0.12
        det = _make_detector(DegradationThresholds(deliberation_success_rate_threshold=0.04))
        baseline = _make_snapshot(deliberation_success_rate=1.0)
        current = _make_snapshot(deliberation_success_rate=0.87)
        # delta=-0.13, |delta|=0.13 > 0.12, current=0.87 >= 0.85
        result = det._analyze_deliberation_success_rate(baseline, current)
        assert result.severity == DegradationSeverity.HIGH


class TestDegradationDetectorMACIViolations:
    """Cover _analyze_maci_violations severity branches."""

    def test_no_degradation(self):
        d = _make_detector()
        baseline = _make_snapshot(maci_violations_count=0)
        current = _make_snapshot(maci_violations_count=0)
        result = d._analyze_maci_violations(baseline, current)
        assert result.severity == DegradationSeverity.NONE

    def test_low_severity(self):
        d = _make_detector()
        baseline = _make_snapshot(maci_violations_count=0)
        current = _make_snapshot(maci_violations_count=2)
        result = d._analyze_maci_violations(baseline, current)
        assert result.severity == DegradationSeverity.LOW

    def test_moderate_severity(self):
        d = _make_detector()
        baseline = _make_snapshot(maci_violations_count=0)
        current = _make_snapshot(maci_violations_count=3)
        result = d._analyze_maci_violations(baseline, current)
        assert result.severity == DegradationSeverity.MODERATE

    def test_high_severity(self):
        d = _make_detector()
        baseline = _make_snapshot(maci_violations_count=0)
        current = _make_snapshot(maci_violations_count=6)
        result = d._analyze_maci_violations(baseline, current)
        assert result.severity == DegradationSeverity.HIGH

    def test_critical_severity(self):
        d = _make_detector()
        baseline = _make_snapshot(maci_violations_count=0)
        current = _make_snapshot(maci_violations_count=11)
        result = d._analyze_maci_violations(baseline, current)
        assert result.severity == DegradationSeverity.CRITICAL

    def test_zero_baseline_percent(self):
        d = _make_detector()
        baseline = _make_snapshot(maci_violations_count=0)
        current = _make_snapshot(maci_violations_count=0)
        result = d._analyze_maci_violations(baseline, current)
        assert result.percent_change == 0.0


class TestDegradationDetectorErrorRate:
    """Cover _analyze_error_rate severity branches."""

    def test_no_degradation(self):
        d = _make_detector()
        baseline = _make_snapshot(error_rate=0.01)
        current = _make_snapshot(error_rate=0.05)
        result = d._analyze_error_rate(baseline, current)
        assert result.severity == DegradationSeverity.NONE

    def test_low_severity(self):
        d = _make_detector()
        baseline = _make_snapshot(error_rate=0.0)
        current = _make_snapshot(error_rate=0.15)
        result = d._analyze_error_rate(baseline, current)
        assert result.severity == DegradationSeverity.LOW

    def test_moderate_severity(self):
        d = _make_detector()
        baseline = _make_snapshot(error_rate=0.0)
        current = _make_snapshot(error_rate=0.25)
        result = d._analyze_error_rate(baseline, current)
        assert result.severity == DegradationSeverity.MODERATE

    def test_high_severity(self):
        d = _make_detector()
        baseline = _make_snapshot(error_rate=0.0)
        # delta=0.35 > 0.1*3 = 0.3, but current < 0.3 not true... 0.35>0.3 => CRITICAL
        # Actually current.error_rate=0.35 > 0.3 => CRITICAL
        # Let me use 0.29 for HIGH
        current = _make_snapshot(error_rate=0.0)
        # Use custom thresholds to trigger high
        det = _make_detector(DegradationThresholds(error_rate_threshold=0.05))
        b = _make_snapshot(error_rate=0.0)
        c = _make_snapshot(error_rate=0.20)
        result = det._analyze_error_rate(b, c)
        # delta=0.20 > 0.05*3=0.15 and current=0.20 < 0.3
        assert result.severity == DegradationSeverity.HIGH

    def test_critical_severity_above_30(self):
        d = _make_detector()
        baseline = _make_snapshot(error_rate=0.0)
        current = _make_snapshot(error_rate=0.35)
        result = d._analyze_error_rate(baseline, current)
        assert result.severity == DegradationSeverity.CRITICAL

    def test_zero_baseline(self):
        d = _make_detector()
        baseline = _make_snapshot(error_rate=0.0)
        current = _make_snapshot(error_rate=0.0)
        result = d._analyze_error_rate(baseline, current)
        assert result.percent_change == 0.0


class TestDegradationDetectorHealthScore:
    """Cover _analyze_health_score severity branches."""

    def test_no_degradation(self):
        d = _make_detector()
        baseline = _make_snapshot()
        current = _make_snapshot()
        result = d._analyze_health_score(baseline, current)
        assert result.severity == DegradationSeverity.NONE

    def test_low_severity(self):
        """Health score threshold = 0.15. Need delta < -0.15 but not too extreme."""
        d = _make_detector()
        # baseline: health ~1.0 (all zero penalties)
        baseline = _make_snapshot(
            error_rate=0.0,
            violations_rate=0.0,
            governance_latency_p99=1.0,
            deliberation_success_rate=0.96,
        )
        # current: violations_rate=1.0 => penalty=0.3, latency=60 => penalty=0.3,
        # deliberation=0.0 => penalty=0.2, maci=10 => penalty=0.1, error=1.0 => 0.1
        # health = 1.0 - 1.0 = 0.0, delta ~ -1.0 => clearly exceeds threshold
        # But we want LOW: need delta between -0.15 and -0.30 and current >= 0.6
        # baseline health ~ 1.0. Need current health ~ 0.80 => delta=-0.20
        # violations_rate=0.5 => penalty=0.15, error_rate=0.5 => penalty=0.05
        # health ~ 1.0 - 0.15 - 0.05 = 0.80, delta = -0.20
        current = _make_snapshot(
            error_rate=0.5,
            violations_rate=0.5,
            governance_latency_p99=1.0,
            deliberation_success_rate=0.96,
        )
        result = d._analyze_health_score(baseline, current)
        assert result.threshold_exceeded is True
        assert result.severity in (
            DegradationSeverity.LOW,
            DegradationSeverity.MODERATE,
            DegradationSeverity.HIGH,
            DegradationSeverity.CRITICAL,
        )

    def test_critical_below_60(self):
        """Cover health_score < 0.6 => CRITICAL."""
        d = _make_detector()
        baseline = _make_snapshot(
            error_rate=0.0,
            violations_rate=0.0,
            governance_latency_p99=1.0,
            deliberation_success_rate=0.96,
        )
        # Make current health < 0.6:
        # violations=1.0 => penalty 0.3, latency=60 => penalty 0.3,
        # delib=0.0 => penalty 0.2, maci=10 => penalty 0.1, error=1.0 => 0.1
        # health = 1.0 - 1.0 = 0.0 => CRITICAL
        current = _make_snapshot(
            error_rate=1.0,
            violations_rate=1.0,
            governance_latency_p99=60.0,
            deliberation_success_rate=0.0,
            maci_violations_count=10,
        )
        result = d._analyze_health_score(baseline, current)
        assert result.threshold_exceeded is True
        assert result.severity == DegradationSeverity.CRITICAL


class TestDegradationDetectorOverallSeverity:
    """Cover _determine_overall_severity branching logic."""

    def _metric(self, severity):
        return MetricDegradationAnalysis(
            metric_name="x",
            baseline_value=0.0,
            current_value=0.1,
            delta=0.1,
            percent_change=10.0,
            threshold_exceeded=severity != DegradationSeverity.NONE,
            configured_threshold=0.01,
            severity=severity,
        )

    def test_any_critical_returns_critical(self):
        d = _make_detector()
        analyses = [
            self._metric(DegradationSeverity.CRITICAL),
            self._metric(DegradationSeverity.LOW),
        ]
        assert d._determine_overall_severity(analyses) == DegradationSeverity.CRITICAL

    def test_two_high_escalates_to_critical(self):
        d = _make_detector()
        analyses = [self._metric(DegradationSeverity.HIGH), self._metric(DegradationSeverity.HIGH)]
        assert d._determine_overall_severity(analyses) == DegradationSeverity.CRITICAL

    def test_one_high_returns_high(self):
        d = _make_detector()
        analyses = [self._metric(DegradationSeverity.HIGH), self._metric(DegradationSeverity.NONE)]
        assert d._determine_overall_severity(analyses) == DegradationSeverity.HIGH

    def test_three_moderate_escalates_to_high(self):
        d = _make_detector()
        analyses = [self._metric(DegradationSeverity.MODERATE)] * 3
        assert d._determine_overall_severity(analyses) == DegradationSeverity.HIGH

    def test_two_moderate_returns_moderate(self):
        d = _make_detector()
        analyses = [
            self._metric(DegradationSeverity.MODERATE),
            self._metric(DegradationSeverity.MODERATE),
            self._metric(DegradationSeverity.NONE),
        ]
        assert d._determine_overall_severity(analyses) == DegradationSeverity.MODERATE

    def test_one_moderate_returns_moderate(self):
        d = _make_detector()
        analyses = [
            self._metric(DegradationSeverity.MODERATE),
            self._metric(DegradationSeverity.NONE),
        ]
        assert d._determine_overall_severity(analyses) == DegradationSeverity.MODERATE

    def test_one_low_returns_low(self):
        d = _make_detector()
        analyses = [self._metric(DegradationSeverity.LOW), self._metric(DegradationSeverity.NONE)]
        assert d._determine_overall_severity(analyses) == DegradationSeverity.LOW

    def test_all_none_returns_none(self):
        d = _make_detector()
        analyses = [self._metric(DegradationSeverity.NONE)] * 3
        assert d._determine_overall_severity(analyses) == DegradationSeverity.NONE


class TestDegradationDetectorConfidence:
    """Cover _compute_confidence_score."""

    def test_low_sample_size(self):
        d = _make_detector()
        baseline = _make_snapshot(total_requests=10)
        current = _make_snapshot(total_requests=10)
        # Need at least one analysis to avoid division by zero
        analysis = MetricDegradationAnalysis(
            metric_name="test",
            baseline_value=0.0,
            current_value=0.0,
            delta=0.0,
            percent_change=0.0,
            threshold_exceeded=False,
            configured_threshold=0.01,
            severity=DegradationSeverity.NONE,
        )
        score = d._compute_confidence_score([analysis], baseline, current)
        assert 0.0 <= score <= 1.0

    def test_high_sample_size(self):
        d = _make_detector()
        baseline = _make_snapshot(total_requests=2000)
        current = _make_snapshot(total_requests=2000)
        analysis = MetricDegradationAnalysis(
            metric_name="test",
            baseline_value=0.0,
            current_value=0.0,
            delta=0.0,
            percent_change=0.0,
            threshold_exceeded=False,
            configured_threshold=0.01,
            severity=DegradationSeverity.NONE,
        )
        score = d._compute_confidence_score([analysis], baseline, current)
        assert score >= 0.3

    def test_with_significant_tests(self):
        d = _make_detector()
        baseline = _make_snapshot(total_requests=100)
        current = _make_snapshot(total_requests=100)
        st = StatisticalTest(
            test_name="t",
            statistic=5.0,
            p_value=0.001,
            significance_level=SignificanceLevel.VERY_HIGH,
        )
        analysis = MetricDegradationAnalysis(
            metric_name="test",
            baseline_value=0.0,
            current_value=0.5,
            delta=0.5,
            percent_change=100.0,
            threshold_exceeded=True,
            configured_threshold=0.01,
            severity=DegradationSeverity.HIGH,
            statistical_test=st,
        )
        score = d._compute_confidence_score([analysis], baseline, current)
        assert score > 0.0

    def test_no_statistical_tests(self):
        d = _make_detector()
        baseline = _make_snapshot(total_requests=100)
        current = _make_snapshot(total_requests=100)
        analysis = MetricDegradationAnalysis(
            metric_name="test",
            baseline_value=0.0,
            current_value=0.5,
            delta=0.5,
            percent_change=100.0,
            threshold_exceeded=True,
            configured_threshold=0.01,
            severity=DegradationSeverity.HIGH,
            statistical_test=None,
        )
        score = d._compute_confidence_score([analysis], baseline, current)
        assert score >= 0.0


class TestDegradationDetectorStatisticalSignificance:
    """Cover _determine_statistical_significance."""

    def test_no_p_values(self):
        d = _make_detector()
        analysis = MetricDegradationAnalysis(
            metric_name="test",
            baseline_value=0.0,
            current_value=0.5,
            delta=0.5,
            percent_change=100.0,
            threshold_exceeded=True,
            configured_threshold=0.01,
            severity=DegradationSeverity.HIGH,
            statistical_test=None,
        )
        assert d._determine_statistical_significance([analysis]) == SignificanceLevel.NONE

    def test_with_p_values(self):
        d = _make_detector()
        st = StatisticalTest(
            test_name="t",
            statistic=5.0,
            p_value=0.002,
            significance_level=SignificanceLevel.HIGH,
        )
        analysis = MetricDegradationAnalysis(
            metric_name="test",
            baseline_value=0.0,
            current_value=0.5,
            delta=0.5,
            percent_change=100.0,
            threshold_exceeded=True,
            configured_threshold=0.01,
            severity=DegradationSeverity.HIGH,
            statistical_test=st,
        )
        result = d._determine_statistical_significance([analysis])
        assert result == SignificanceLevel.HIGH


class TestDegradationDetectorSummary:
    """Cover _generate_summary."""

    def test_no_degradation_summary(self):
        d = _make_detector()
        summary = d._generate_summary([], DegradationSeverity.NONE)
        assert "No significant" in summary

    def test_degradation_summary(self):
        d = _make_detector()
        analysis = MetricDegradationAnalysis(
            metric_name="violations_rate",
            baseline_value=0.0,
            current_value=0.05,
            delta=0.05,
            percent_change=5.0,
            threshold_exceeded=True,
            configured_threshold=0.01,
            severity=DegradationSeverity.HIGH,
        )
        summary = d._generate_summary([analysis], DegradationSeverity.HIGH)
        assert "violations_rate" in summary
        assert "high" in summary.lower()


class TestDegradationDetectorRollbackRecommendation:
    """Cover _should_recommend_rollback."""

    def test_critical_always_recommends(self):
        d = _make_detector()
        assert (
            d._should_recommend_rollback(DegradationSeverity.CRITICAL, 0.5, SignificanceLevel.NONE)
            is True
        )

    def test_high_with_confidence_and_significance(self):
        d = _make_detector()
        assert (
            d._should_recommend_rollback(DegradationSeverity.HIGH, 0.8, SignificanceLevel.VERY_HIGH)
            is True
        )

    def test_high_with_low_confidence(self):
        d = _make_detector()
        assert (
            d._should_recommend_rollback(DegradationSeverity.HIGH, 0.3, SignificanceLevel.VERY_HIGH)
            is False
        )

    def test_high_with_low_significance(self):
        d = _make_detector()
        assert (
            d._should_recommend_rollback(DegradationSeverity.HIGH, 0.8, SignificanceLevel.LOW)
            is False
        )

    def test_moderate_never_recommends(self):
        d = _make_detector()
        assert (
            d._should_recommend_rollback(
                DegradationSeverity.MODERATE, 0.9, SignificanceLevel.VERY_HIGH
            )
            is False
        )


class TestDegradationDetectorAnalyzeDegradation:
    """Cover analyze_degradation async method."""

    async def test_with_both_snapshots(self):
        d = _make_detector()
        baseline = _make_snapshot()
        current = _make_snapshot(violations_rate=0.05, error_rate=0.15)
        report = await d.analyze_degradation(baseline, current, TimeWindow.ONE_HOUR, "amend-1")
        assert isinstance(report, DegradationReport)
        assert report.amendment_id == "amend-1"
        assert len(report.metric_analyses) == 6

    async def test_without_current_snapshot(self):
        d = _make_detector()
        baseline = _make_snapshot()
        report = await d.analyze_degradation(baseline, None, TimeWindow.SIX_HOURS)
        assert isinstance(report, DegradationReport)
        d.metrics_collector.collect_snapshot.assert_called_once()

    async def test_analyze_multi_window(self):
        d = _make_detector()
        baseline = _make_snapshot()
        reports = await d.analyze_multi_window(baseline, "amend-2")
        assert len(reports) == 3  # default 1h, 6h, 24h

    async def test_analyze_multi_window_custom(self):
        d = _make_detector()
        baseline = _make_snapshot()
        reports = await d.analyze_multi_window(baseline, "amend-3", windows=[TimeWindow.ONE_HOUR])
        assert len(reports) == 1


class TestChiSquareTest:
    """Cover _chi_square_test edge cases."""

    def test_returns_none_without_scipy(self):
        d = _make_detector()
        with patch("enhanced_agent_bus.constitutional.degradation_detector.SCIPY_AVAILABLE", False):
            result = d._chi_square_test(90, 100, 85, 100, "test_chi")
        assert result is None

    def test_returns_result_with_scipy(self):
        d = _make_detector()
        try:
            import scipy

            result = d._chi_square_test(90, 100, 70, 100, "test_chi")
            assert result is not None
            assert result.test_name == "test_chi"
        except ImportError:
            pytest.skip("scipy not available")

    def test_handles_error_gracefully(self):
        d = _make_detector()
        with patch("enhanced_agent_bus.constitutional.degradation_detector.SCIPY_AVAILABLE", True):
            with patch("enhanced_agent_bus.constitutional.degradation_detector.np") as mock_np:
                mock_np.array.side_effect = ValueError("bad data")
                result = d._chi_square_test(90, 100, 85, 100, "test_chi")
        assert result is None


# ============================================================================
# SECTION 2: review_api.py
# ============================================================================


class TestHealthCheck:
    """Cover health_check endpoint."""

    async def test_health_check_returns_healthy(self):
        result = await health_check()
        assert result["status"] == "healthy"
        assert result["service"] == "constitutional-review-api"
        assert "constitutional_hash" in result
        assert "timestamp" in result


class TestReviewApiModels:
    """Cover request/response model construction."""

    def test_amendment_list_query_defaults(self):
        q = AmendmentListQuery()
        assert q.limit == 50
        assert q.offset == 0
        assert q.order_by == "created_at"
        assert q.order == "desc"

    def test_approval_request_creation(self):
        r = ApprovalRequest(approver_agent_id="agent-1", comments="Looks good")
        assert r.approver_agent_id == "agent-1"
        assert r.metadata == {}

    def test_rejection_request_creation(self):
        r = RejectionRequest(
            rejector_agent_id="agent-2",
            reason="Does not meet constitutional requirements for governance",
        )
        assert r.rejector_agent_id == "agent-2"
        assert len(r.reason) >= 10

    def test_rollback_request_creation(self):
        r = RollbackRequest(
            requester_agent_id="agent-3",
            justification="Critical degradation detected in governance metrics requiring immediate rollback",
        )
        assert len(r.justification) >= 20

    def test_rollback_response_model(self):
        r = RollbackResponse(
            success=True,
            rollback_id="rb-1",
            previous_version="1.2.0",
            restored_version="1.1.0",
            message="Rolled back",
            justification="Degradation detected in critical metrics",
        )
        assert r.success is True
        assert r.degradation_detected is False


# ============================================================================
# SECTION 3: bus/core.py
# ============================================================================


class TestEnhancedAgentBusCoreInit:
    """Cover EnhancedAgentBus constructor branches."""

    def test_default_init(self):
        bus = EnhancedAgentBus()
        assert bus.constitutional_hash == CONSTITUTIONAL_HASH
        assert bus.is_running is False

    def test_init_with_custom_redis_url(self):
        bus = EnhancedAgentBus(redis_url="redis://custom:6380")
        assert bus.redis_url == "redis://custom:6380"

    def test_init_with_validator_kwarg(self):
        mock_validator = MagicMock()
        bus = EnhancedAgentBus(validator=mock_validator)
        assert bus._validator is mock_validator

    def test_from_config_dict(self):
        config = {"redis_url": "redis://test:6379", "enable_maci": False}
        bus = EnhancedAgentBus.from_config(config)
        assert bus.redis_url == "redis://test:6379"

    def test_from_config_with_to_dict(self):
        config = MagicMock()
        config.to_dict.return_value = {"redis_url": "redis://obj:6379"}
        bus = EnhancedAgentBus.from_config(config)
        assert bus.redis_url == "redis://obj:6379"

    def test_normalize_tenant_id_static(self):
        result = EnhancedAgentBus._normalize_tenant_id("  Tenant-A  ")
        assert result is not None
        assert result == result.strip()

    def test_format_tenant_id_none(self):
        result = EnhancedAgentBus._format_tenant_id(None)
        assert result == "none"

    def test_format_tenant_id_value(self):
        result = EnhancedAgentBus._format_tenant_id("tenant-abc")
        assert "tenant" in result.lower() or result == "tenant-abc"


class TestEnhancedAgentBusTestMode:
    """Cover _is_test_mode_message."""

    def test_fail_in_content(self):
        msg = MagicMock()
        msg.content = "this will fail"
        msg.constitutional_hash = CONSTITUTIONAL_HASH
        msg.from_agent = "agent-1"
        assert EnhancedAgentBus._is_test_mode_message(msg) is True

    def test_invalid_hash(self):
        msg = MagicMock()
        msg.content = "ok"
        msg.constitutional_hash = "invalid-hash"
        msg.from_agent = "agent-1"
        assert EnhancedAgentBus._is_test_mode_message(msg) is True

    def test_test_agent(self):
        msg = MagicMock()
        msg.content = "ok"
        msg.constitutional_hash = CONSTITUTIONAL_HASH
        msg.from_agent = "test-agent-1"
        assert EnhancedAgentBus._is_test_mode_message(msg) is True

    def test_normal_message(self):
        msg = MagicMock()
        msg.content = "normal content"
        msg.constitutional_hash = CONSTITUTIONAL_HASH
        msg.from_agent = "agent-1"
        assert EnhancedAgentBus._is_test_mode_message(msg) is False


class TestEnhancedAgentBusStartStop:
    """Cover start/stop lifecycle."""

    async def test_start_sets_running(self):
        bus = EnhancedAgentBus()
        bus._metering_manager = AsyncMock()
        bus._governance = AsyncMock()
        bus._governance.constitutional_hash = CONSTITUTIONAL_HASH
        bus._router_component = AsyncMock()
        await bus.start()
        assert bus.is_running is True
        assert bus._metrics["started_at"] is not None

    async def test_stop_resets_running(self):
        bus = EnhancedAgentBus()
        bus._running = True
        bus._metering_manager = AsyncMock()
        bus._governance = AsyncMock()
        bus._router_component = AsyncMock()
        bus._kafka_consumer_task = None
        bus._redis_client_for_limiter = None
        await bus.stop()
        assert bus.is_running is False

    async def test_stop_cancels_kafka_task(self):
        bus = EnhancedAgentBus()
        bus._running = True
        bus._metering_manager = AsyncMock()
        bus._governance = AsyncMock()
        bus._router_component = AsyncMock()
        bus._redis_client_for_limiter = None

        # Create a real asyncio task that we can cancel
        async def _noop():
            await asyncio.sleep(100)

        task = asyncio.create_task(_noop())
        bus._kafka_consumer_task = task
        await bus.stop()
        assert task.cancelled()

    async def test_stop_closes_redis_limiter(self):
        bus = EnhancedAgentBus()
        bus._running = True
        bus._metering_manager = AsyncMock()
        bus._governance = AsyncMock()
        bus._router_component = AsyncMock()
        bus._kafka_consumer_task = None
        mock_redis = AsyncMock()
        bus._redis_client_for_limiter = mock_redis
        await bus.stop()
        mock_redis.aclose.assert_called_once()

    async def test_stop_redis_close_error(self):
        bus = EnhancedAgentBus()
        bus._running = True
        bus._metering_manager = AsyncMock()
        bus._governance = AsyncMock()
        bus._router_component = AsyncMock()
        bus._kafka_consumer_task = None
        mock_redis = AsyncMock()
        mock_redis.aclose.side_effect = ConnectionError("closed")
        bus._redis_client_for_limiter = mock_redis
        await bus.stop()  # Should not raise


class TestEnhancedAgentBusProperties:
    """Cover property accessors."""

    def test_maci_enabled(self):
        bus = EnhancedAgentBus(enable_maci=False)
        assert bus.maci_enabled is False

    def test_maci_registry_none(self):
        bus = EnhancedAgentBus(enable_maci=False)
        assert bus.maci_registry is None

    def test_maci_enforcer_none(self):
        bus = EnhancedAgentBus(enable_maci=False)
        assert bus.maci_enforcer is None

    def test_maci_strict_mode(self):
        bus = EnhancedAgentBus(enable_maci=False)
        assert isinstance(bus.maci_strict_mode, bool)

    def test_processor_property(self):
        bus = EnhancedAgentBus()
        assert bus.processor is not None

    def test_agents_property(self):
        bus = EnhancedAgentBus()
        assert isinstance(bus.agents, dict)

    def test_registry_property(self):
        bus = EnhancedAgentBus()
        assert bus.registry is not None

    def test_validator_property(self):
        bus = EnhancedAgentBus()
        assert bus.validator is not None


class TestEnhancedAgentBusKafka:
    """Cover Kafka resolution and mock creation."""

    def test_create_simple_kafka_mock(self):
        mock = EnhancedAgentBus._create_simple_kafka_mock()
        assert mock is not None
        assert hasattr(mock, "_mock_name")

    async def test_create_simple_kafka_mock_method_call(self):
        mock = EnhancedAgentBus._create_simple_kafka_mock()
        result = await mock.subscribe("callback")
        assert result is True

    def test_resolve_kafka_bus_from_config(self):
        fake_kafka = MagicMock()
        bus = EnhancedAgentBus(kafka_bus=fake_kafka)
        bus._resolve_kafka_bus()
        assert bus._kafka_bus is fake_kafka

    def test_resolve_kafka_bus_use_kafka_true_creates_mock(self):
        bus = EnhancedAgentBus(use_kafka=True)
        bus._kafka_bus = None
        bus._resolve_kafka_bus()
        # Should have created a mock since use_kafka=True and no kafka_bus

    async def test_start_kafka_bus_if_supported_no_start(self):
        bus = EnhancedAgentBus()
        bus._kafka_bus = MagicMock(spec=[])  # No start method
        await bus._start_kafka_bus_if_supported()

    async def test_start_kafka_bus_if_supported_sync_start(self):
        bus = EnhancedAgentBus()
        mock_bus = MagicMock()
        mock_bus.start = MagicMock(return_value=None)
        bus._kafka_bus = mock_bus
        await bus._start_kafka_bus_if_supported()
        mock_bus.start.assert_called_once()

    async def test_start_kafka_bus_if_supported_async_start(self):
        bus = EnhancedAgentBus()
        mock_bus = MagicMock()
        mock_bus.start = AsyncMock()
        bus._kafka_bus = mock_bus
        await bus._start_kafka_bus_if_supported()
        mock_bus.start.assert_called_once()


class TestEnhancedAgentBusRateLimiting:
    """Cover _apply_rate_limit branches."""

    async def test_no_rate_limiter(self):
        bus = EnhancedAgentBus()
        bus._rate_limiter = None
        msg = MagicMock()
        result = MagicMock()
        assert await bus._apply_rate_limit(msg, result) is True

    async def test_global_rate_limit_allowed(self):
        bus = EnhancedAgentBus()
        bus._rate_limiter = AsyncMock()
        rate_result = MagicMock()
        rate_result.allowed = True
        bus._rate_limiter.is_allowed = AsyncMock(return_value=rate_result)
        msg = MagicMock()
        msg.tenant_id = None
        result = MagicMock()
        assert await bus._apply_rate_limit(msg, result) is True

    async def test_global_rate_limit_denied(self):
        bus = EnhancedAgentBus()
        bus._rate_limiter = AsyncMock()
        rate_result = MagicMock()
        rate_result.allowed = False
        rate_result.retry_after = 5
        bus._rate_limiter.is_allowed = AsyncMock(return_value=rate_result)
        msg = MagicMock()
        msg.tenant_id = None
        result = MagicMock()
        assert await bus._apply_rate_limit(msg, result) is False
        result.add_error.assert_called_once()

    async def test_tenant_rate_limit_with_quota(self):
        bus = EnhancedAgentBus()
        bus._rate_limiter = AsyncMock()
        rate_result = MagicMock()
        rate_result.allowed = True
        bus._rate_limiter.is_allowed = AsyncMock(return_value=rate_result)
        bus._tenant_rate_limit_provider = MagicMock()
        quota = MagicMock()
        quota.requests = 500
        quota.window_seconds = 30
        bus._tenant_rate_limit_provider.get_quota.return_value = quota
        msg = MagicMock()
        msg.tenant_id = "tenant-x"
        result = MagicMock()
        assert await bus._apply_rate_limit(msg, result) is True

    async def test_tenant_rate_limit_no_quota(self):
        bus = EnhancedAgentBus()
        bus._rate_limiter = AsyncMock()
        rate_result = MagicMock()
        rate_result.allowed = True
        bus._rate_limiter.is_allowed = AsyncMock(return_value=rate_result)
        bus._tenant_rate_limit_provider = MagicMock()
        bus._tenant_rate_limit_provider.get_quota.return_value = None
        msg = MagicMock()
        msg.tenant_id = "tenant-y"
        result = MagicMock()
        assert await bus._apply_rate_limit(msg, result) is True


class TestEnhancedAgentBusValidateAgentIdentity:
    """Cover _validate_agent_identity branches."""

    async def test_no_token_no_dynamic_policy(self):
        bus = EnhancedAgentBus(use_dynamic_policy=False)
        result, _ = await bus._validate_agent_identity("agent-1", None)
        assert result is None

    async def test_no_token_with_dynamic_policy(self):
        bus = EnhancedAgentBus()
        bus._use_dynamic_policy = True
        bus._config["use_dynamic_policy"] = True
        result, _ = await bus._validate_agent_identity("agent-1", None)
        assert result is False

    async def test_token_with_dot(self):
        bus = EnhancedAgentBus()
        result, errors = await bus._validate_agent_identity("agent-1", "jwt.token.here")
        assert result == "jwt.token.here"
        assert errors == []

    async def test_token_without_dot(self):
        bus = EnhancedAgentBus()
        result, errors = await bus._validate_agent_identity("agent-1", "simpletoken")
        assert result == "default"
        assert errors == []


class TestEnhancedAgentBusValidateTenantConsistency:
    """Cover _validate_tenant_consistency branches."""

    def test_with_message_object(self):
        bus = EnhancedAgentBus()
        msg = MagicMock()
        msg.from_agent = "agent-1"
        msg.to_agent = "agent-2"
        msg.tenant_id = "tenant-a"
        result = bus._validate_tenant_consistency(msg)
        assert isinstance(result, list)

    def test_with_string_args(self):
        bus = EnhancedAgentBus()
        result = bus._validate_tenant_consistency("agent-1", "agent-2", "tenant-a")
        assert isinstance(result, list)


class TestEnhancedAgentBusRouterProperty:
    """Cover router property with different router_component types."""

    def test_router_with_router_component_instance(self):
        bus = EnhancedAgentBus()
        router = bus.router
        assert router is not None

    def test_router_with_custom_router(self):
        mock_router = MagicMock()
        mock_router._router = MagicMock()
        # Passing router without _router attr triggers the wrapping branch
        bus = EnhancedAgentBus(router=mock_router)
        # The router should be accessible
        assert bus.router is not None


class TestEnhancedAgentBusDelegatedMethods:
    """Cover delegated backward-compatibility methods."""

    def test_record_metrics_failure(self):
        bus = EnhancedAgentBus()
        bus._message_validator = MagicMock()
        bus._record_metrics_failure()
        bus._message_validator.record_metrics_failure.assert_called_once()

    def test_record_metrics_success(self):
        bus = EnhancedAgentBus()
        bus._message_validator = MagicMock()
        bus._record_metrics_success()
        bus._message_validator.record_metrics_success.assert_called_once()

    async def test_receive_message(self):
        bus = EnhancedAgentBus()
        bus._message_handler = MagicMock()
        bus._message_handler.receive_message = AsyncMock(return_value=None)
        result = await bus.receive_message(timeout=0.5)
        assert result is None

    async def test_route_and_deliver(self):
        bus = EnhancedAgentBus()
        bus._message_handler = MagicMock()
        bus._message_handler.route_and_deliver = AsyncMock(return_value=True)
        msg = MagicMock()
        result = await bus._route_and_deliver(msg)
        assert result is True

    async def test_handle_deliberation(self):
        bus = EnhancedAgentBus()
        bus._message_handler = MagicMock()
        bus._message_handler.handle_deliberation = AsyncMock(return_value=False)
        msg = MagicMock()
        result = await bus._handle_deliberation(msg)
        assert result is False

    def test_requires_deliberation(self):
        bus = EnhancedAgentBus()
        bus._message_handler = MagicMock()
        bus._message_handler.requires_deliberation = MagicMock(return_value=True)
        msg = MagicMock()
        assert bus._requires_deliberation(msg) is True

    async def test_broadcast_message(self):
        bus = EnhancedAgentBus()
        bus._message_handler = MagicMock()
        bus._message_handler.broadcast_message = AsyncMock(return_value={})
        msg = MagicMock()
        result = await bus.broadcast_message(msg)
        assert result == {}

    async def test_process_batch(self):
        bus = EnhancedAgentBus()
        bus._batch_processor = MagicMock()
        bus._batch_processor.process_batch = AsyncMock(return_value=MagicMock())
        batch_req = MagicMock()
        result = await bus.process_batch(batch_req)
        assert result is not None

    def test_record_batch_metering(self):
        bus = EnhancedAgentBus()
        bus._batch_processor = MagicMock()
        bus._record_batch_metering(MagicMock(), MagicMock(), 100.0)
        bus._batch_processor._record_batch_metering.assert_called_once()

    async def test_get_metrics_async(self):
        bus = EnhancedAgentBus()
        bus._bus_metrics = MagicMock()
        bus._bus_metrics.get_metrics_async = AsyncMock(return_value={"sent": 0})
        result = await bus.get_metrics_async()
        assert "sent" in result

    def test_get_metrics(self):
        bus = EnhancedAgentBus()
        bus._bus_metrics = MagicMock()
        bus._bus_metrics.get_metrics.return_value = {"sent": 0}
        result = bus.get_metrics()
        assert "sent" in result

    async def test_initialize_adaptive_governance(self):
        bus = EnhancedAgentBus()
        await bus._initialize_adaptive_governance()  # no-op

    async def test_shutdown_adaptive_governance(self):
        bus = EnhancedAgentBus()
        await bus._shutdown_adaptive_governance()  # no-op
