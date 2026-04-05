"""
ACGS-2 Compliance Reporter
Constitutional Hash: 608508a9bd224290

Provides unified compliance reporting across all frameworks.
Generates consolidated reports for NIST AI RMF, SOC 2, and EU AI Act.
"""

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .euaiact_compliance import EUAIActCompliance, get_euaiact_compliance
from .models import (
    ComplianceAssessment,
    ComplianceFramework,
    ComplianceStatus,
    ComplianceViolation,
    RiskSeverity,
)
from .nist_risk_assessor import NISTRiskAssessor, get_nist_risk_assessor
from .soc2_auditor import SOC2Auditor, get_soc2_auditor

logger = get_logger(__name__)


@dataclass
class ComplianceMetrics:
    """Aggregated compliance metrics."""

    total_controls: int = 0
    compliant_controls: int = 0
    partial_controls: int = 0
    non_compliant_controls: int = 0
    compliance_rate: float = 0.0
    nist_score: float = 0.0
    soc2_score: float = 0.0
    euaiact_score: float = 0.0
    overall_score: float = 0.0
    critical_violations: int = 0
    high_violations: int = 0
    medium_violations: int = 0
    low_violations: int = 0
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class ComplianceDashboard:
    """Dashboard data for compliance visualization."""

    metrics: ComplianceMetrics
    framework_status: dict[str, ComplianceStatus]
    recent_assessments: list[JSONDict]
    trending_violations: list[JSONDict]
    recommendations: list[str]
    next_actions: list[str]
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class UnifiedComplianceReport:
    """Unified compliance report across all frameworks."""

    report_id: str
    organization: str
    generated_at: datetime
    report_period_start: datetime
    report_period_end: datetime
    metrics: ComplianceMetrics
    nist_assessment: ComplianceAssessment | None = None
    soc2_assessment: ComplianceAssessment | None = None
    euaiact_assessment: ComplianceAssessment | None = None
    all_violations: list[ComplianceViolation] = field(default_factory=list)
    executive_summary: str = ""
    key_findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH


class ComplianceReporter:
    """Compliance Reporter - Main implementation.

    Provides unified compliance reporting across:
    - NIST AI RMF
    - SOC 2 Type II
    - EU AI Act

    Generates consolidated reports, dashboards, and metrics.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        nist_assessor: NISTRiskAssessor | None = None,
        soc2_auditor: SOC2Auditor | None = None,
        euaiact_compliance: EUAIActCompliance | None = None,
    ):
        self.constitutional_hash = CONSTITUTIONAL_HASH
        self._nist = nist_assessor
        self._soc2 = soc2_auditor
        self._euaiact = euaiact_compliance
        self._reports: dict[str, UnifiedComplianceReport] = {}
        self._initialized = False
        logger.info(f"[{self.constitutional_hash}] ComplianceReporter initialized")

    async def initialize(self) -> bool:
        """Initialize compliance components."""
        if self._initialized:
            return True

        if self._nist is None:
            self._nist = get_nist_risk_assessor()
        if self._soc2 is None:
            self._soc2 = get_soc2_auditor()
        if self._euaiact is None:
            self._euaiact = get_euaiact_compliance()

        await self._nist.initialize()
        await self._soc2.initialize()
        await self._euaiact.initialize()

        self._initialized = True
        return True

    async def generate_unified_report(
        self,
        system_name: str = "ACGS-2",
        organization: str = "ACGS-2 Platform",
    ) -> UnifiedComplianceReport:
        """Generate unified compliance report across all frameworks."""
        await self.initialize()
        start_time = time.perf_counter()

        # Run all assessments
        nist_assessment = await self._nist.assess_risk(system_name)
        soc2_assessment = await self._soc2.audit(system_name)
        euaiact_assessment = await self._euaiact.assess(system_name)

        # Calculate metrics
        metrics = self._calculate_metrics(
            [
                nist_assessment,
                soc2_assessment,
                euaiact_assessment,
            ]
        )

        # Collect all violations
        all_violations = []
        for assessment in [nist_assessment, soc2_assessment, euaiact_assessment]:
            all_violations.extend(assessment.violations)

        # Generate summaries
        executive_summary = self._generate_executive_summary(metrics)
        key_findings = self._extract_key_findings(
            [
                nist_assessment,
                soc2_assessment,
                euaiact_assessment,
            ]
        )
        recommendations = self._generate_recommendations(metrics, all_violations)
        next_steps = self._generate_next_steps(metrics)

        report = UnifiedComplianceReport(
            report_id=f"ucr-{uuid.uuid4().hex[:8]}",
            organization=organization,
            generated_at=datetime.now(UTC),
            report_period_start=datetime.now(UTC),
            report_period_end=datetime.now(UTC),
            metrics=metrics,
            nist_assessment=nist_assessment,
            soc2_assessment=soc2_assessment,
            euaiact_assessment=euaiact_assessment,
            all_violations=all_violations,
            executive_summary=executive_summary,
            key_findings=key_findings,
            recommendations=recommendations,
            next_steps=next_steps,
        )

        self._reports[report.report_id] = report

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"[{self.constitutional_hash}] Generated unified report {report.report_id} "
            f"(overall_score={metrics.overall_score}%, latency={elapsed_ms:.2f}ms)"
        )

        return report

    def _calculate_metrics(
        self,
        assessments: list[ComplianceAssessment],
    ) -> ComplianceMetrics:
        """Calculate aggregated compliance metrics."""
        metrics = ComplianceMetrics()

        for assessment in assessments:
            self._accumulate_control_totals(metrics, assessment)
            self._set_framework_score(metrics, assessment)
            self._accumulate_violation_totals(metrics, assessment)

        self._finalize_compliance_rate(metrics)
        self._finalize_overall_score(metrics)
        return metrics

    @staticmethod
    def _accumulate_control_totals(
        metrics: ComplianceMetrics,
        assessment: ComplianceAssessment,
    ) -> None:
        """Accumulate assessed/compliant/partial/non-compliant control counts."""
        metrics.total_controls += assessment.controls_assessed
        metrics.compliant_controls += assessment.controls_compliant
        metrics.partial_controls += assessment.controls_partial
        metrics.non_compliant_controls += assessment.controls_non_compliant

    @staticmethod
    def _set_framework_score(
        metrics: ComplianceMetrics,
        assessment: ComplianceAssessment,
    ) -> None:
        """Map framework-specific compliance score into aggregate metrics."""
        framework_score_mapping: dict[ComplianceFramework, str] = {
            ComplianceFramework.NIST_AI_RMF: "nist_score",
            ComplianceFramework.SOC2_TYPE_II: "soc2_score",
            ComplianceFramework.EU_AI_ACT: "euaiact_score",
        }

        score_attr = framework_score_mapping.get(assessment.framework)
        if score_attr:
            setattr(metrics, score_attr, assessment.compliance_score)

    @staticmethod
    def _accumulate_violation_totals(
        metrics: ComplianceMetrics,
        assessment: ComplianceAssessment,
    ) -> None:
        """Accumulate violation counters by severity."""
        severity_attr_mapping: dict[RiskSeverity, str] = {
            RiskSeverity.CRITICAL: "critical_violations",
            RiskSeverity.HIGH: "high_violations",
            RiskSeverity.MEDIUM: "medium_violations",
        }

        for violation in assessment.violations:
            attr_name = severity_attr_mapping.get(violation.severity, "low_violations")
            setattr(metrics, attr_name, getattr(metrics, attr_name) + 1)

    @staticmethod
    def _finalize_compliance_rate(metrics: ComplianceMetrics) -> None:
        """Compute weighted compliance rate once control totals are aggregated."""
        if metrics.total_controls <= 0:
            return

        metrics.compliance_rate = (
            (metrics.compliant_controls + metrics.partial_controls * 0.5)
            / metrics.total_controls
            * 100
        )

    @staticmethod
    def _finalize_overall_score(metrics: ComplianceMetrics) -> None:
        """Compute overall score from non-zero framework scores."""
        scores = [metrics.nist_score, metrics.soc2_score, metrics.euaiact_score]
        valid_scores = [score for score in scores if score > 0]
        if valid_scores:
            metrics.overall_score = round(sum(valid_scores) / len(valid_scores), 2)

    def _generate_executive_summary(self, metrics: ComplianceMetrics) -> str:
        """Generate executive summary."""
        status = (
            "Strong"
            if metrics.overall_score >= 90
            else "Acceptable"
            if metrics.overall_score >= 70
            else "Needs Improvement"
        )

        return f"""ACGS-2 Compliance Executive Summary

Overall Compliance Status: {status}
Overall Compliance Score: {metrics.overall_score}%

Framework Scores:
- NIST AI RMF: {metrics.nist_score}%
- SOC 2 Type II: {metrics.soc2_score}%
- EU AI Act: {metrics.euaiact_score}%

Control Statistics:
- Total Controls: {metrics.total_controls}
- Compliant: {metrics.compliant_controls}
- Partial: {metrics.partial_controls}
- Non-Compliant: {metrics.non_compliant_controls}

Violations:
- Critical: {metrics.critical_violations}
- High: {metrics.high_violations}
- Medium: {metrics.medium_violations}
- Low: {metrics.low_violations}

Constitutional Hash: {self.constitutional_hash}
"""

    def _extract_key_findings(
        self,
        assessments: list[ComplianceAssessment],
    ) -> list[str]:
        """Extract key findings from assessments."""
        findings = []
        for assessment in assessments:
            for finding in assessment.findings[:3]:  # Top 3 per framework
                findings.append(f"[{assessment.framework.value}] {finding}")
        return findings

    def _generate_recommendations(
        self,
        metrics: ComplianceMetrics,
        violations: list[ComplianceViolation],
    ) -> list[str]:
        """Generate recommendations based on findings."""
        recommendations = []

        if metrics.critical_violations > 0:
            recommendations.append("PRIORITY: Address all critical violations immediately")

        if metrics.high_violations > 0:
            recommendations.append(
                "Schedule remediation for high-severity violations within 30 days"
            )

        if metrics.overall_score < 90:
            recommendations.append("Implement additional controls to achieve 90%+ compliance")

        recommendations.append("Continue constitutional hash validation across all operations")
        recommendations.append("Maintain audit trail for all governance decisions")

        return recommendations

    def _generate_next_steps(self, metrics: ComplianceMetrics) -> list[str]:
        """Generate next steps based on metrics."""
        next_steps = []

        if metrics.non_compliant_controls > 0:
            next_steps.append(f"Remediate {metrics.non_compliant_controls} non-compliant controls")

        if metrics.partial_controls > 0:
            next_steps.append(
                f"Complete implementation of {metrics.partial_controls} partial controls"
            )

        next_steps.append("Schedule next compliance assessment in 90 days")
        next_steps.append("Update technical documentation with latest changes")
        next_steps.append("Review and update risk register")

        return next_steps

    async def generate_dashboard(
        self,
        system_name: str = "ACGS-2",
    ) -> ComplianceDashboard:
        """Generate compliance dashboard data."""
        report = await self.generate_unified_report(system_name)

        framework_status = {
            "nist_ai_rmf": (
                report.nist_assessment.overall_status
                if report.nist_assessment
                else ComplianceStatus.NOT_ASSESSED
            ),
            "soc2_type_ii": (
                report.soc2_assessment.overall_status
                if report.soc2_assessment
                else ComplianceStatus.NOT_ASSESSED
            ),
            "eu_ai_act": (
                report.euaiact_assessment.overall_status
                if report.euaiact_assessment
                else ComplianceStatus.NOT_ASSESSED
            ),
        }

        recent_assessments = []
        for assessment in [
            report.nist_assessment,
            report.soc2_assessment,
            report.euaiact_assessment,
        ]:
            if assessment:
                recent_assessments.append(
                    {
                        "framework": assessment.framework.value,
                        "score": assessment.compliance_score,
                        "status": assessment.overall_status.value,
                        "date": assessment.assessment_date.isoformat(),
                    }
                )

        trending_violations = []
        for violation in report.all_violations[:5]:
            trending_violations.append(
                {
                    "id": violation.violation_id,
                    "framework": violation.framework.value,
                    "severity": violation.severity.value,
                    "description": violation.description[:100],
                }
            )

        return ComplianceDashboard(
            metrics=report.metrics,
            framework_status=framework_status,
            recent_assessments=recent_assessments,
            trending_violations=trending_violations,
            recommendations=report.recommendations,
            next_actions=report.next_steps,
        )

    def get_report(self, report_id: str) -> UnifiedComplianceReport | None:
        """Retrieve a stored report."""
        return self._reports.get(report_id)

    def list_reports(self, limit: int = 100) -> list[UnifiedComplianceReport]:
        """List stored reports."""
        return list(self._reports.values())[:limit]


# Singleton instance
_compliance_reporter: ComplianceReporter | None = None


def get_compliance_reporter() -> ComplianceReporter:
    """Get or create the singleton ComplianceReporter instance."""
    global _compliance_reporter
    if _compliance_reporter is None:
        _compliance_reporter = ComplianceReporter()
    return _compliance_reporter


def reset_compliance_reporter() -> None:
    """Reset the singleton instance (for testing)."""
    global _compliance_reporter
    _compliance_reporter = None


__all__ = [
    "ComplianceDashboard",
    "ComplianceMetrics",
    "ComplianceReporter",
    "UnifiedComplianceReport",
    "get_compliance_reporter",
    "reset_compliance_reporter",
]
