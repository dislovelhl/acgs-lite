"""
ACGS-2 Enhanced Agent Bus - Governance Degradation Detection Engine
Constitutional Hash: cdd01ef066bc6cf2

Statistical analysis engine to detect significant governance degradation after
constitutional amendments using statistical significance testing and configurable
thresholds.
"""

from datetime import UTC, datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

# Import centralized constitutional hash
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger

# Import statistical libraries
try:
    import numpy as np
    from scipy import stats

    SCIPY_AVAILABLE = True
except ImportError:
    stats = None
    np = None
    SCIPY_AVAILABLE = False

from .metrics_collector import GovernanceMetricsCollector, GovernanceMetricsSnapshot

logger = get_logger(__name__)
CHI_SQUARE_TEST_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)


class TimeWindow(str, Enum):
    """Time windows for degradation analysis.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    ONE_HOUR = "1h"
    SIX_HOURS = "6h"
    TWELVE_HOURS = "12h"
    TWENTY_FOUR_HOURS = "24h"

    def to_seconds(self) -> int:
        """Convert time window to seconds."""
        mapping = {
            TimeWindow.ONE_HOUR: 3600,
            TimeWindow.SIX_HOURS: 21600,
            TimeWindow.TWELVE_HOURS: 43200,
            TimeWindow.TWENTY_FOUR_HOURS: 86400,
        }
        return mapping[self]


class SignificanceLevel(str, Enum):
    """Statistical significance levels.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    VERY_HIGH = "very_high"  # p < 0.001
    HIGH = "high"  # p < 0.01
    MODERATE = "moderate"  # p < 0.05
    LOW = "low"  # p < 0.1
    NONE = "none"  # p >= 0.1

    @classmethod
    def from_p_value(cls, p_value: float) -> "SignificanceLevel":
        """Determine significance level from p-value."""
        if p_value < 0.001:
            return cls.VERY_HIGH
        elif p_value < 0.01:
            return cls.HIGH
        elif p_value < 0.05:
            return cls.MODERATE
        elif p_value < 0.1:
            return cls.LOW
        else:
            return cls.NONE


class DegradationSeverity(str, Enum):
    """Severity levels for degradation detection.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    CRITICAL = "critical"  # Immediate rollback recommended
    HIGH = "high"  # Rollback strongly recommended
    MODERATE = "moderate"  # Monitor closely, consider rollback
    LOW = "low"  # Minor degradation, continue monitoring
    NONE = "none"  # No degradation detected


class StatisticalTest(BaseModel):
    """Results from a statistical significance test.

    Constitutional Hash: cdd01ef066bc6cf2

    Attributes:
        test_name: Name of the statistical test (t-test, chi-square, etc.)
        statistic: Test statistic value
        p_value: P-value for significance
        significance_level: Interpreted significance level
        degrees_of_freedom: Degrees of freedom (if applicable)
        baseline_mean: Mean value from baseline
        current_mean: Mean value from current
        is_significant: Whether the result is statistically significant (p < 0.05)
    """

    test_name: str
    statistic: float
    p_value: float
    significance_level: SignificanceLevel
    degrees_of_freedom: int | None = None
    baseline_mean: float | None = None
    current_mean: float | None = None

    @property
    def is_significant(self) -> bool:
        """Check if result is statistically significant (p < 0.05)."""
        return self.p_value < 0.05

    @property
    def is_highly_significant(self) -> bool:
        """Check if result is highly significant (p < 0.01)."""
        return self.p_value < 0.01


class MetricDegradationAnalysis(BaseModel):
    """Degradation analysis for a single metric.

    Constitutional Hash: cdd01ef066bc6cf2

    Attributes:
        metric_name: Name of the metric being analyzed
        baseline_value: Baseline value (before amendment)
        current_value: Current value (after amendment)
        delta: Change in value (current - baseline)
        percent_change: Percent change from baseline
        threshold_exceeded: Whether degradation threshold was exceeded
        configured_threshold: Configured threshold for this metric
        statistical_test: Statistical test result (if performed)
        severity: Degradation severity level
    """

    metric_name: str
    baseline_value: float
    current_value: float
    delta: float
    percent_change: float
    threshold_exceeded: bool
    configured_threshold: float
    statistical_test: StatisticalTest | None = None
    severity: DegradationSeverity = DegradationSeverity.NONE


class DegradationReport(BaseModel):
    """Comprehensive degradation detection report.

    Constitutional Hash: cdd01ef066bc6cf2

    Attributes:
        report_id: Unique identifier for this report
        timestamp: When this report was generated
        constitutional_hash: Hash of constitutional version being analyzed
        constitutional_version: Semantic version of constitution
        amendment_id: ID of amendment being analyzed (if applicable)
        time_window: Time window used for analysis
        baseline_snapshot: Baseline metrics snapshot
        current_snapshot: Current metrics snapshot
        metric_analyses: Degradation analysis per metric
        overall_severity: Overall degradation severity
        confidence_score: Confidence in degradation detection (0.0-1.0)
        rollback_recommended: Whether automatic rollback is recommended
        degradation_summary: Human-readable summary of degradation
        statistical_significance: Overall statistical significance
    """

    report_id: str = Field(default_factory=lambda: f"degradation-{datetime.now(UTC).timestamp()}")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    constitutional_version: str | None = None
    amendment_id: str | None = None
    time_window: TimeWindow

    baseline_snapshot: GovernanceMetricsSnapshot
    current_snapshot: GovernanceMetricsSnapshot

    metric_analyses: list[MetricDegradationAnalysis] = Field(default_factory=list)
    overall_severity: DegradationSeverity = DegradationSeverity.NONE
    confidence_score: float = Field(0.0, ge=0.0, le=1.0)
    rollback_recommended: bool = False
    degradation_summary: str = ""
    statistical_significance: SignificanceLevel = SignificanceLevel.NONE

    @property
    def has_degradation(self) -> bool:
        """Check if any degradation was detected."""
        return self.overall_severity != DegradationSeverity.NONE

    @property
    def critical_metrics(self) -> list[MetricDegradationAnalysis]:
        """Get metrics with critical degradation."""
        return [m for m in self.metric_analyses if m.severity == DegradationSeverity.CRITICAL]

    @property
    def high_severity_metrics(self) -> list[MetricDegradationAnalysis]:
        """Get metrics with high or critical degradation."""
        return [
            m
            for m in self.metric_analyses
            if m.severity in (DegradationSeverity.CRITICAL, DegradationSeverity.HIGH)
        ]


class DegradationThresholds(BaseModel):
    """Configurable thresholds for degradation detection.

    Constitutional Hash: cdd01ef066bc6cf2

    Attributes:
        violations_rate_threshold: Max acceptable increase in violation rate (default: 0.01 = 1%)
        latency_p99_threshold_ms: Max acceptable increase in P99 latency (default: 2.0ms)
        latency_p99_percent_threshold: Max acceptable percent increase in P99 latency (default: 0.5 = 50%)
        deliberation_success_rate_threshold: Max acceptable decrease in success rate (default: 0.05 = 5%)
        maci_violations_threshold: Max acceptable increase in MACI violations (default: 1)
        error_rate_threshold: Max acceptable increase in error rate (default: 0.1 = 10%)
        health_score_threshold: Min acceptable decrease in health score (default: 0.15 = 15%)
        min_sample_size: Minimum sample size for statistical tests (default: 30)
        significance_level: P-value threshold for statistical significance (default: 0.05)
    """

    violations_rate_threshold: float = Field(0.01, ge=0.0, le=1.0)
    latency_p99_threshold_ms: float = Field(2.0, ge=0.0)
    latency_p99_percent_threshold: float = Field(0.5, ge=0.0)
    deliberation_success_rate_threshold: float = Field(0.05, ge=0.0, le=1.0)
    maci_violations_threshold: int = Field(1, ge=0)
    error_rate_threshold: float = Field(0.1, ge=0.0, le=1.0)
    health_score_threshold: float = Field(0.15, ge=0.0, le=1.0)
    min_sample_size: int = Field(30, ge=1)
    significance_level: float = Field(0.05, ge=0.0, le=1.0)


class DegradationDetector:
    """Statistical analysis engine to detect governance degradation.

    Constitutional Hash: cdd01ef066bc6cf2

    This engine performs statistical analysis to detect significant governance
    degradation after constitutional amendments. It uses multiple time windows,
    statistical significance testing, and configurable thresholds.

    Args:
        metrics_collector: Metrics collector for gathering snapshots
        thresholds: Configurable thresholds for degradation detection
    """

    def __init__(
        self,
        metrics_collector: GovernanceMetricsCollector,
        thresholds: DegradationThresholds | None = None,
    ):
        """Initialize the degradation detector."""
        self.metrics_collector = metrics_collector
        self.thresholds = thresholds or DegradationThresholds(
            violations_rate_threshold=0.01,
            latency_p99_threshold_ms=2.0,
            latency_p99_percent_threshold=0.5,
            deliberation_success_rate_threshold=0.05,
            maci_violations_threshold=1,
            error_rate_threshold=0.1,
            health_score_threshold=0.15,
            min_sample_size=30,
            significance_level=0.05,
        )

        if not SCIPY_AVAILABLE:
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] scipy not available, "
                "statistical significance testing will be limited"
            )

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Initialized DegradationDetector with "
            f"thresholds: violations={self.thresholds.violations_rate_threshold:.2%}, "
            f"latency={self.thresholds.latency_p99_threshold_ms}ms, "
            f"health_score={self.thresholds.health_score_threshold:.2%}"
        )

    async def analyze_degradation(
        self,
        baseline: GovernanceMetricsSnapshot,
        current: GovernanceMetricsSnapshot | None = None,
        time_window: TimeWindow = TimeWindow.ONE_HOUR,
        amendment_id: str | None = None,
    ) -> DegradationReport:
        """Analyze governance degradation by comparing baseline to current metrics.

        Args:
            baseline: Baseline metrics snapshot (before amendment)
            current: Current metrics snapshot (if None, collects new snapshot)
            time_window: Time window for analysis
            amendment_id: ID of amendment being analyzed

        Returns:
            DegradationReport with comprehensive analysis
        """
        # Collect current snapshot if not provided
        if current is None:
            current = await self.metrics_collector.collect_snapshot(
                constitutional_version=baseline.constitutional_version,
                window_seconds=time_window.to_seconds(),
            )

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Analyzing degradation for window={time_window.value}, "
            f"amendment={amendment_id}"
        )

        # Analyze each metric
        metric_analyses = []

        # Violations rate
        metric_analyses.append(self._analyze_violations_rate(baseline, current))

        # Latency P99
        metric_analyses.append(self._analyze_latency_p99(baseline, current))

        # Deliberation success rate
        metric_analyses.append(self._analyze_deliberation_success_rate(baseline, current))

        # MACI violations
        metric_analyses.append(self._analyze_maci_violations(baseline, current))

        # Error rate
        metric_analyses.append(self._analyze_error_rate(baseline, current))

        # Health score
        metric_analyses.append(self._analyze_health_score(baseline, current))

        # Determine overall severity
        overall_severity = self._determine_overall_severity(metric_analyses)

        # Compute confidence score
        confidence_score = self._compute_confidence_score(metric_analyses, baseline, current)

        # Determine statistical significance
        statistical_significance = self._determine_statistical_significance(metric_analyses)

        # Generate summary
        degradation_summary = self._generate_summary(metric_analyses, overall_severity)

        # Determine rollback recommendation
        rollback_recommended = self._should_recommend_rollback(
            overall_severity, confidence_score, statistical_significance
        )

        report = DegradationReport(
            constitutional_version=baseline.constitutional_version,
            amendment_id=amendment_id,
            time_window=time_window,
            baseline_snapshot=baseline,
            current_snapshot=current,
            metric_analyses=metric_analyses,
            overall_severity=overall_severity,
            confidence_score=confidence_score,
            rollback_recommended=rollback_recommended,
            degradation_summary=degradation_summary,
            statistical_significance=statistical_significance,
        )

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Degradation analysis complete: "
            f"severity={overall_severity.value}, confidence={confidence_score:.2%}, "
            f"rollback_recommended={rollback_recommended}"
        )

        return report

    async def analyze_multi_window(
        self,
        baseline: GovernanceMetricsSnapshot,
        amendment_id: str | None = None,
        windows: list[TimeWindow] | None = None,
    ) -> list[DegradationReport]:
        """Analyze degradation across multiple time windows.

        Args:
            baseline: Baseline metrics snapshot
            amendment_id: ID of amendment being analyzed
            windows: list of time windows to analyze (default: 1h, 6h, 24h)

        Returns:
            list of degradation reports, one per time window
        """
        if windows is None:
            windows = [TimeWindow.ONE_HOUR, TimeWindow.SIX_HOURS, TimeWindow.TWENTY_FOUR_HOURS]

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Starting multi-window degradation analysis "
            f"with {len(windows)} windows"
        )

        reports = []
        for window in windows:
            report = await self.analyze_degradation(
                baseline=baseline,
                time_window=window,
                amendment_id=amendment_id,
            )
            reports.append(report)

        return reports

    def _analyze_violations_rate(
        self,
        baseline: GovernanceMetricsSnapshot,
        current: GovernanceMetricsSnapshot,
    ) -> MetricDegradationAnalysis:
        """Analyze violations rate degradation."""
        delta = current.violations_rate - baseline.violations_rate
        percent_change = (
            (delta / max(0.001, baseline.violations_rate)) if baseline.violations_rate > 0 else 0.0
        )
        threshold_exceeded = delta > self.thresholds.violations_rate_threshold

        # Determine severity
        severity = DegradationSeverity.NONE
        if threshold_exceeded:
            if delta > self.thresholds.violations_rate_threshold * 5:  # 5x threshold
                severity = DegradationSeverity.CRITICAL
            elif delta > self.thresholds.violations_rate_threshold * 3:  # 3x threshold
                severity = DegradationSeverity.HIGH
            elif delta > self.thresholds.violations_rate_threshold * 2:  # 2x threshold
                severity = DegradationSeverity.MODERATE
            else:
                severity = DegradationSeverity.LOW

        # Perform chi-square test if scipy available
        statistical_test = None
        if SCIPY_AVAILABLE and (baseline.total_requests >= self.thresholds.min_sample_size):
            statistical_test = self._chi_square_test(
                baseline_successes=baseline.total_requests
                - int(baseline.violations_rate * baseline.total_requests),
                baseline_total=baseline.total_requests,
                current_successes=current.total_requests
                - int(current.violations_rate * current.total_requests),
                current_total=current.total_requests,
                test_name="chi_square_violations_rate",
            )

        return MetricDegradationAnalysis(
            metric_name="violations_rate",
            baseline_value=baseline.violations_rate,
            current_value=current.violations_rate,
            delta=delta,
            percent_change=percent_change,
            threshold_exceeded=threshold_exceeded,
            configured_threshold=self.thresholds.violations_rate_threshold,
            statistical_test=statistical_test,
            severity=severity,
        )

    def _analyze_latency_p99(
        self,
        baseline: GovernanceMetricsSnapshot,
        current: GovernanceMetricsSnapshot,
    ) -> MetricDegradationAnalysis:
        """Analyze P99 latency degradation."""
        delta = current.governance_latency_p99 - baseline.governance_latency_p99
        percent_change = (
            (delta / max(0.001, baseline.governance_latency_p99))
            if baseline.governance_latency_p99 > 0
            else 0.0
        )

        # Check both absolute and percent thresholds
        threshold_exceeded = (
            delta > self.thresholds.latency_p99_threshold_ms
            or percent_change > self.thresholds.latency_p99_percent_threshold
        )

        # Determine severity
        severity = DegradationSeverity.NONE
        if threshold_exceeded:
            if current.governance_latency_p99 > 10.0:  # Above 10ms is critical
                severity = DegradationSeverity.CRITICAL
            elif delta > self.thresholds.latency_p99_threshold_ms * 3:  # 3x threshold
                severity = DegradationSeverity.HIGH
            elif delta > self.thresholds.latency_p99_threshold_ms * 2:  # 2x threshold
                severity = DegradationSeverity.MODERATE
            else:
                severity = DegradationSeverity.LOW

        # We can't perform t-test without raw data, just note the change
        statistical_test = None

        return MetricDegradationAnalysis(
            metric_name="latency_p99",
            baseline_value=baseline.governance_latency_p99,
            current_value=current.governance_latency_p99,
            delta=delta,
            percent_change=percent_change,
            threshold_exceeded=threshold_exceeded,
            configured_threshold=self.thresholds.latency_p99_threshold_ms,
            statistical_test=statistical_test,
            severity=severity,
        )

    def _analyze_deliberation_success_rate(
        self,
        baseline: GovernanceMetricsSnapshot,
        current: GovernanceMetricsSnapshot,
    ) -> MetricDegradationAnalysis:
        """Analyze deliberation success rate degradation."""
        delta = current.deliberation_success_rate - baseline.deliberation_success_rate
        percent_change = (
            (delta / max(0.001, baseline.deliberation_success_rate))
            if baseline.deliberation_success_rate > 0
            else 0.0
        )
        threshold_exceeded = (
            delta < -self.thresholds.deliberation_success_rate_threshold
        )  # Negative delta is bad

        # Determine severity
        severity = DegradationSeverity.NONE
        if threshold_exceeded:
            if current.deliberation_success_rate < 0.85:  # Below 85% is critical
                severity = DegradationSeverity.CRITICAL
            elif abs(delta) > self.thresholds.deliberation_success_rate_threshold * 3:
                severity = DegradationSeverity.HIGH
            elif abs(delta) > self.thresholds.deliberation_success_rate_threshold * 2:
                severity = DegradationSeverity.MODERATE
            else:
                severity = DegradationSeverity.LOW

        # Perform chi-square test if scipy available
        statistical_test = None
        if SCIPY_AVAILABLE:
            # Estimate total deliberations (we don't have exact counts in snapshot)
            # Use escalated_requests as proxy for deliberation count
            baseline_total = max(baseline.escalated_requests, 1)
            current_total = max(current.escalated_requests, 1)

            if baseline_total >= self.thresholds.min_sample_size:
                statistical_test = self._chi_square_test(
                    baseline_successes=int(baseline.deliberation_success_rate * baseline_total),
                    baseline_total=baseline_total,
                    current_successes=int(current.deliberation_success_rate * current_total),
                    current_total=current_total,
                    test_name="chi_square_deliberation_success",
                )

        return MetricDegradationAnalysis(
            metric_name="deliberation_success_rate",
            baseline_value=baseline.deliberation_success_rate,
            current_value=current.deliberation_success_rate,
            delta=delta,
            percent_change=percent_change,
            threshold_exceeded=threshold_exceeded,
            configured_threshold=self.thresholds.deliberation_success_rate_threshold,
            statistical_test=statistical_test,
            severity=severity,
        )

    def _analyze_maci_violations(
        self,
        baseline: GovernanceMetricsSnapshot,
        current: GovernanceMetricsSnapshot,
    ) -> MetricDegradationAnalysis:
        """Analyze MACI violations degradation."""
        delta = current.maci_violations_count - baseline.maci_violations_count
        percent_change = (
            (delta / max(1, baseline.maci_violations_count))
            if baseline.maci_violations_count > 0
            else 0.0
        )
        threshold_exceeded = delta > self.thresholds.maci_violations_threshold

        # Determine severity
        severity = DegradationSeverity.NONE
        if threshold_exceeded:
            if delta > 10:  # More than 10 new MACI violations is critical
                severity = DegradationSeverity.CRITICAL
            elif delta > 5:
                severity = DegradationSeverity.HIGH
            elif delta > 2:
                severity = DegradationSeverity.MODERATE
            else:
                severity = DegradationSeverity.LOW

        return MetricDegradationAnalysis(
            metric_name="maci_violations_count",
            baseline_value=float(baseline.maci_violations_count),
            current_value=float(current.maci_violations_count),
            delta=float(delta),
            percent_change=percent_change,
            threshold_exceeded=threshold_exceeded,
            configured_threshold=float(self.thresholds.maci_violations_threshold),
            statistical_test=None,
            severity=severity,
        )

    def _analyze_error_rate(
        self,
        baseline: GovernanceMetricsSnapshot,
        current: GovernanceMetricsSnapshot,
    ) -> MetricDegradationAnalysis:
        """Analyze error rate degradation."""
        delta = current.error_rate - baseline.error_rate
        percent_change = (
            (delta / max(0.001, baseline.error_rate)) if baseline.error_rate > 0 else 0.0
        )
        threshold_exceeded = delta > self.thresholds.error_rate_threshold

        # Determine severity
        severity = DegradationSeverity.NONE
        if threshold_exceeded:
            if current.error_rate > 0.3:  # Above 30% error rate is critical
                severity = DegradationSeverity.CRITICAL
            elif delta > self.thresholds.error_rate_threshold * 3:
                severity = DegradationSeverity.HIGH
            elif delta > self.thresholds.error_rate_threshold * 2:
                severity = DegradationSeverity.MODERATE
            else:
                severity = DegradationSeverity.LOW

        return MetricDegradationAnalysis(
            metric_name="error_rate",
            baseline_value=baseline.error_rate,
            current_value=current.error_rate,
            delta=delta,
            percent_change=percent_change,
            threshold_exceeded=threshold_exceeded,
            configured_threshold=self.thresholds.error_rate_threshold,
            statistical_test=None,
            severity=severity,
        )

    def _analyze_health_score(
        self,
        baseline: GovernanceMetricsSnapshot,
        current: GovernanceMetricsSnapshot,
    ) -> MetricDegradationAnalysis:
        """Analyze overall health score degradation."""
        delta = current.health_score - baseline.health_score
        percent_change = (
            (delta / max(0.001, baseline.health_score)) if baseline.health_score > 0 else 0.0
        )
        threshold_exceeded = (
            delta < -self.thresholds.health_score_threshold
        )  # Negative delta is bad

        # Determine severity
        severity = DegradationSeverity.NONE
        if threshold_exceeded:
            if current.health_score < 0.6:  # Below 60% health is critical
                severity = DegradationSeverity.CRITICAL
            elif abs(delta) > self.thresholds.health_score_threshold * 3:
                severity = DegradationSeverity.HIGH
            elif abs(delta) > self.thresholds.health_score_threshold * 2:
                severity = DegradationSeverity.MODERATE
            else:
                severity = DegradationSeverity.LOW

        return MetricDegradationAnalysis(
            metric_name="health_score",
            baseline_value=baseline.health_score,
            current_value=current.health_score,
            delta=delta,
            percent_change=percent_change,
            threshold_exceeded=threshold_exceeded,
            configured_threshold=self.thresholds.health_score_threshold,
            statistical_test=None,
            severity=severity,
        )

    def _chi_square_test(
        self,
        baseline_successes: int,
        baseline_total: int,
        current_successes: int,
        current_total: int,
        test_name: str,
    ) -> StatisticalTest | None:
        """Perform chi-square test for proportions.

        Args:
            baseline_successes: Number of successes in baseline
            baseline_total: Total observations in baseline
            current_successes: Number of successes in current
            current_total: Total observations in current
            test_name: Name of the test

        Returns:
            StatisticalTest result or None if test cannot be performed
        """
        if not SCIPY_AVAILABLE:
            return None

        try:
            # Create contingency table
            observed = np.array(
                [
                    [baseline_successes, baseline_total - baseline_successes],
                    [current_successes, current_total - current_successes],
                ]
            )

            # Perform chi-square test
            chi2, p_value, dof, _expected = stats.chi2_contingency(observed)

            baseline_mean = baseline_successes / max(1, baseline_total)
            current_mean = current_successes / max(1, current_total)

            return StatisticalTest(
                test_name=test_name,
                statistic=float(chi2),
                p_value=float(p_value),
                significance_level=SignificanceLevel.from_p_value(p_value),
                degrees_of_freedom=int(dof),
                baseline_mean=float(baseline_mean),
                current_mean=float(current_mean),
            )
        except CHI_SQUARE_TEST_ERRORS as e:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Chi-square test failed: {e}")
            return None

    def _determine_overall_severity(
        self,
        metric_analyses: list[MetricDegradationAnalysis],
    ) -> DegradationSeverity:
        """Determine overall severity from individual metric analyses."""
        # If any metric is critical, overall is critical
        if any(m.severity == DegradationSeverity.CRITICAL for m in metric_analyses):
            return DegradationSeverity.CRITICAL

        # If multiple high severity metrics, escalate to critical
        high_count = sum(1 for m in metric_analyses if m.severity == DegradationSeverity.HIGH)
        if high_count >= 2:
            return DegradationSeverity.CRITICAL

        # If any metric is high, overall is high
        if any(m.severity == DegradationSeverity.HIGH for m in metric_analyses):
            return DegradationSeverity.HIGH

        # If multiple moderate metrics, escalate to high
        moderate_count = sum(
            1 for m in metric_analyses if m.severity == DegradationSeverity.MODERATE
        )
        if moderate_count >= 3:
            return DegradationSeverity.HIGH
        elif moderate_count >= 2:
            return DegradationSeverity.MODERATE

        # If any metric is moderate, overall is moderate
        if any(m.severity == DegradationSeverity.MODERATE for m in metric_analyses):
            return DegradationSeverity.MODERATE

        # If any metric is low, overall is low
        if any(m.severity == DegradationSeverity.LOW for m in metric_analyses):
            return DegradationSeverity.LOW

        return DegradationSeverity.NONE

    def _compute_confidence_score(
        self,
        metric_analyses: list[MetricDegradationAnalysis],
        baseline: GovernanceMetricsSnapshot,
        current: GovernanceMetricsSnapshot,
    ) -> float:
        """Compute confidence score for degradation detection (0.0-1.0).

        Confidence is based on:
        - Sample size (more data = higher confidence)
        - Statistical significance (significant results = higher confidence)
        - Consistency across metrics (more degraded metrics = higher confidence)
        """
        # Sample size factor (0.0-0.4)
        sample_size_factor = min(0.4, baseline.total_requests / 1000.0 * 0.4)

        # Statistical significance factor (0.0-0.3)
        significant_tests = sum(
            1 for m in metric_analyses if m.statistical_test and m.statistical_test.is_significant
        )
        total_tests = sum(1 for m in metric_analyses if m.statistical_test is not None)
        significance_factor = (
            (significant_tests / max(1, total_tests)) * 0.3 if total_tests > 0 else 0.0
        )

        # Consistency factor (0.0-0.3)
        degraded_metrics = sum(1 for m in metric_analyses if m.threshold_exceeded)
        consistency_factor = (degraded_metrics / len(metric_analyses)) * 0.3

        confidence = sample_size_factor + significance_factor + consistency_factor

        return min(1.0, confidence)

    def _determine_statistical_significance(
        self,
        metric_analyses: list[MetricDegradationAnalysis],
    ) -> SignificanceLevel:
        """Determine overall statistical significance from metric analyses."""
        # Collect all p-values from statistical tests
        p_values = [
            m.statistical_test.p_value for m in metric_analyses if m.statistical_test is not None
        ]

        if not p_values:
            return SignificanceLevel.NONE

        # Use the minimum p-value (most significant)
        min_p_value = min(p_values)
        return SignificanceLevel.from_p_value(min_p_value)

    def _generate_summary(
        self,
        metric_analyses: list[MetricDegradationAnalysis],
        overall_severity: DegradationSeverity,
    ) -> str:
        """Generate human-readable summary of degradation analysis."""
        if overall_severity == DegradationSeverity.NONE:
            return "No significant governance degradation detected. All metrics within acceptable thresholds."

        degraded_metrics = [m for m in metric_analyses if m.threshold_exceeded]

        summary_parts = [
            f"Governance degradation detected (severity: {overall_severity.value}).",
            f"{len(degraded_metrics)} metric(s) exceeded thresholds:",
        ]

        for metric in degraded_metrics:
            summary_parts.append(
                f"- {metric.metric_name}: {metric.baseline_value:.4f} → {metric.current_value:.4f} "
                f"(Δ {metric.delta:+.4f}, {metric.percent_change:+.1%}, severity: {metric.severity.value})"
            )

        return " ".join(summary_parts)

    def _should_recommend_rollback(
        self,
        overall_severity: DegradationSeverity,
        confidence_score: float,
        statistical_significance: SignificanceLevel,
    ) -> bool:
        """Determine whether to recommend automatic rollback.

        Rollback is recommended when:
        - Severity is CRITICAL, OR
        - Severity is HIGH with high confidence (>0.7) and statistical significance
        """
        if overall_severity == DegradationSeverity.CRITICAL:
            return True

        if overall_severity == DegradationSeverity.HIGH:
            if confidence_score > 0.7 and statistical_significance in (
                SignificanceLevel.VERY_HIGH,
                SignificanceLevel.HIGH,
            ):
                return True

        return False


__all__ = [
    "DegradationDetector",
    "DegradationReport",
    "DegradationSeverity",
    "DegradationThresholds",
    "MetricDegradationAnalysis",
    "SignificanceLevel",
    "StatisticalTest",
    "TimeWindow",
]
