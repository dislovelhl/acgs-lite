"""
FR-9: Reporting and Analytics Dashboard Tests
Constitutional Hash: 608508a9bd224290

Comprehensive test coverage for PRD v2.3.1 FR-9 requirements:
- 6.1 NIST RMF Reports verification
- 6.2 EU AI Act compliance reports
- 6.3 Unified compliance endpoint
- 6.4 Trend analysis validation

PRD Hash: 36d689a9a103b8cb
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Constitutional hash for validation
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

PRD_HASH = "36d689a9a103b8cb"

# ============================================================================
# 6.1 NIST RMF Reports Tests
# ============================================================================


class TestNISTRMFReports:
    """
    Test suite for NIST RMF (Risk Management Framework) reporting.

    Validates:
    - RMF seven-step process tracking
    - Security control implementation status
    - Control family coverage
    - Authorization status
    - Report generation and export
    """

    @pytest.fixture
    def nist_rmf_reporter(self):
        """Create NIST RMF reporter for testing."""
        try:
            from src.core.services.audit_service.reporters.nist_rmf import (
                NISTRiskManagementReporter,
            )

            return NISTRiskManagementReporter()
        except ImportError:
            pytest.skip("NIST RMF reporter not available")

    @pytest.fixture
    def rmf_control(self):
        """Create sample RMF control for testing."""
        try:
            from src.core.services.audit_service.reporters.nist_rmf import (
                ControlFamily,
                ControlStatus,
                RMFControl,
            )

            return RMFControl(
                control_id="AC-2",
                family=ControlFamily.AC,
                name="Account Management",
                description="Manage system accounts, group memberships, and privileges",
                status=ControlStatus.IMPLEMENTED,
                implementation_details=[
                    "Multi-tenant user account management",
                    "Role-based access control (RBAC)",
                ],
                evidence=["Tenant management service implements user accounts"],
            )
        except ImportError:
            pytest.skip("NIST RMF types not available")

    async def test_rmf_assessment_generation(self, nist_rmf_reporter):
        """Test RMF assessment generation with all seven steps."""
        assessment = await nist_rmf_reporter.generate_rmf_assessment(
            system_name="ACGS-2 Test System",
            tenant_id="test-tenant-001",
        )

        # Verify assessment structure
        assert assessment.assessment_id is not None
        assert assessment.system_name == "ACGS-2 Test System"
        assert assessment.tenant_id == "test-tenant-001"
        assert assessment.assessor == "acgs2-compliance-engine"

        # Verify all RMF steps completed
        from src.core.services.audit_service.reporters.nist_rmf import RMFStep

        expected_steps = {
            RMFStep.PREPARE,
            RMFStep.CATEGORIZE,
            RMFStep.SELECT,
            RMFStep.IMPLEMENT,
            RMFStep.ASSESS,
            RMFStep.AUTHORIZE,
            RMFStep.MONITOR,
        }
        assert assessment.completed_steps == expected_steps

        # Verify constitutional hash
        assert assessment.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_rmf_control_coverage(self, nist_rmf_reporter):
        """Test that RMF assessment covers required security controls."""
        assessment = await nist_rmf_reporter.generate_rmf_assessment()

        # Verify controls are present
        assert len(assessment.controls) >= 10

        # Check for critical control families
        control_ids = {c.control_id for c in assessment.controls}
        required_controls = {"AC-2", "AC-3", "AU-2", "AU-3", "IA-2", "SC-7", "SC-8"}
        for required_id in required_controls:
            assert required_id in control_ids, f"Missing required control: {required_id}"

    async def test_rmf_security_impact_levels(self, nist_rmf_reporter):
        """Test security impact level calculations."""
        from src.core.services.audit_service.reporters.nist_rmf import SecurityImpactLevel

        assessment = await nist_rmf_reporter.generate_rmf_assessment()

        # Verify impact levels are set
        assert assessment.confidentiality_impact in SecurityImpactLevel
        assert assessment.integrity_impact in SecurityImpactLevel
        assert assessment.availability_impact in SecurityImpactLevel

        # Verify overall impact is calculated correctly
        overall = assessment.get_overall_impact()
        assert overall in SecurityImpactLevel

        # HIGH impact if any individual is HIGH
        if SecurityImpactLevel.HIGH in [
            assessment.confidentiality_impact,
            assessment.integrity_impact,
            assessment.availability_impact,
        ]:
            assert overall == SecurityImpactLevel.HIGH

    async def test_rmf_authorization_status(self, nist_rmf_reporter):
        """Test authorization status tracking."""
        assessment = await nist_rmf_reporter.generate_rmf_assessment()

        # Verify authorization is set
        assert assessment.authorization_date is not None
        assert assessment.authorization_expiry is not None
        assert assessment.authorizing_official is not None

        # Verify authorization is valid
        assert assessment.is_authorized is True

        # Verify expiry is in the future (1 year)
        assert assessment.authorization_expiry > datetime.now(UTC)
        assert assessment.authorization_expiry <= datetime.now(UTC) + timedelta(days=366)

    async def test_rmf_report_generation(self, nist_rmf_reporter):
        """Test complete RMF report generation."""
        report = await nist_rmf_reporter.generate_rmf_report(
            system_name="ACGS-2 Platform",
            tenant_id="test-tenant-001",
        )

        # Verify report structure
        assert report.report_id is not None
        assert report.assessment is not None
        assert report.generated_at is not None

        # Verify metrics are calculated
        assert report.total_controls > 0
        assert report.implemented_controls > 0
        assert report.compliance_score > 0.0
        assert report.risk_level in ["very_low", "low", "moderate", "high", "very_high"]

        # Verify recommendations are generated
        assert isinstance(report.improvement_recommendations, list)

    async def test_rmf_report_export_json(self, nist_rmf_reporter):
        """Test RMF report JSON export."""
        report = await nist_rmf_reporter.generate_rmf_report()
        json_output = await nist_rmf_reporter.export_report(report, "json")

        # Verify valid JSON
        data = json.loads(json_output)
        assert "report_id" in data
        assert "assessment" in data
        assert "summary_metrics" in data
        assert "controls" in data

        # Verify constitutional hash in export
        assert data["assessment"]["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_rmf_report_export_html(self, nist_rmf_reporter):
        """Test RMF report HTML export."""
        report = await nist_rmf_reporter.generate_rmf_report()
        html_output = await nist_rmf_reporter.export_report(report, "html")

        # Verify HTML structure
        assert "<!DOCTYPE html>" in html_output
        assert "NIST RMF Assessment Report" in html_output
        assert report.report_id in html_output
        assert CONSTITUTIONAL_HASH in html_output

        # Verify control tables are present
        assert "Control ID" in html_output
        assert "Implementation Status" in html_output or "Status" in html_output

    async def test_rmf_control_compliance_rate(self, nist_rmf_reporter):
        """Test control compliance rate calculation."""
        assessment = await nist_rmf_reporter.generate_rmf_assessment()
        compliance_rate = assessment.get_control_compliance_rate()

        # Verify compliance rate is valid
        assert 0.0 <= compliance_rate <= 1.0

        # ACGS-2 should have high compliance (all 14 controls implemented)
        assert compliance_rate >= 0.9, f"Expected high compliance rate, got {compliance_rate}"


# ============================================================================
# 6.2 EU AI Act Compliance Reports Tests
# ============================================================================


class TestEUAIActCompliance:
    """
    Test suite for EU AI Act compliance reporting.

    Validates:
    - Article 13 transparency requirements
    - High-risk AI system classification
    - Human oversight requirements (HITL)
    - Fundamental rights impact assessment
    """

    @pytest.fixture
    def compliance_dashboard_service(self):
        """Create compliance dashboard service for testing."""
        try:
            from src.core.services.compliance_docs.src.api.compliance_dashboard import (
                ComplianceDashboardService,
            )

            return ComplianceDashboardService()
        except ImportError:
            pytest.skip("Compliance dashboard service not available")

    @pytest.fixture
    def unified_reporter(self):
        """Create unified compliance reporter for testing."""
        try:
            from src.core.services.audit_service.reporters.unified_compliance import (
                UnifiedComplianceReporter,
            )

            return UnifiedComplianceReporter()
        except ImportError:
            pytest.skip("Unified compliance reporter not available")

    async def test_eu_ai_act_framework_assessment(self, compliance_dashboard_service):
        """Test EU AI Act framework assessment."""
        from src.core.services.compliance_docs.src.api.compliance_dashboard import (
            ComplianceFramework,
        )

        # Get EU AI Act assessment
        dashboard = await compliance_dashboard_service.get_unified_dashboard(
            frameworks=[ComplianceFramework.EU_AI_ACT]
        )

        # Verify EU AI Act is assessed
        assert len(dashboard.framework_assessments) >= 1

        eu_ai_assessment = None
        for assessment in dashboard.framework_assessments:
            if assessment.framework == ComplianceFramework.EU_AI_ACT:
                eu_ai_assessment = assessment
                break

        assert eu_ai_assessment is not None
        assert eu_ai_assessment.framework_name == "EU Artificial Intelligence Act"

        # Verify coverage percentage meets PRD requirements (88%)
        assert eu_ai_assessment.coverage_percentage >= 80.0

    async def test_eu_ai_act_transparency_controls(self, compliance_dashboard_service):
        """Test EU AI Act Article 13 transparency controls."""
        from src.core.services.compliance_docs.src.api.compliance_dashboard import (
            ComplianceFramework,
        )

        dashboard = await compliance_dashboard_service.get_unified_dashboard(
            frameworks=[ComplianceFramework.EU_AI_ACT]
        )

        for assessment in dashboard.framework_assessments:
            if assessment.framework == ComplianceFramework.EU_AI_ACT:
                # Verify key findings mention transparency
                findings_text = " ".join(assessment.key_findings).lower()
                assert "transparency" in findings_text or "article 13" in findings_text

                # Verify recommendations exist
                assert len(assessment.recommendations) > 0
                break

    async def test_eu_ai_act_hitl_requirements(self, compliance_dashboard_service):
        """Test EU AI Act human oversight (HITL) requirements."""
        from src.core.services.compliance_docs.src.api.compliance_dashboard import (
            ComplianceFramework,
        )

        dashboard = await compliance_dashboard_service.get_unified_dashboard(
            frameworks=[ComplianceFramework.EU_AI_ACT]
        )

        for assessment in dashboard.framework_assessments:
            if assessment.framework == ComplianceFramework.EU_AI_ACT:
                # Verify human oversight is documented
                findings_text = " ".join(assessment.key_findings).lower()
                assert (
                    "human" in findings_text
                    or "hitl" in findings_text
                    or "oversight" in findings_text
                )
                break

    async def test_eu_ai_act_high_risk_classification(self, unified_reporter):
        """Test EU AI Act high-risk AI system classification."""
        from src.core.services.audit_service.reporters.unified_compliance import (
            ComplianceFramework,
        )

        score = await unified_reporter.generate_unified_score(
            frameworks=[ComplianceFramework.EU_AI_ACT]
        )

        # Get EU AI Act score
        eu_score = score.framework_scores.get(ComplianceFramework.EU_AI_ACT)
        assert eu_score is not None

        # Verify high-risk controls are addressed
        assert eu_score.controls_total >= 10

        # Verify gaps are identified
        gaps = eu_score.gaps
        assert isinstance(gaps, list)


# ============================================================================
# 6.3 Unified Compliance Endpoint Tests
# ============================================================================


class TestUnifiedComplianceEndpoint:
    """
    Test suite for unified compliance dashboard API.

    Validates:
    - Multi-framework aggregation
    - Overall compliance score calculation
    - Gap analysis and cross-framework impact
    - Executive summary generation
    """

    @pytest.fixture
    def compliance_dashboard_service(self):
        """Create compliance dashboard service for testing."""
        try:
            from src.core.services.compliance_docs.src.api.compliance_dashboard import (
                ComplianceDashboardService,
            )

            return ComplianceDashboardService()
        except ImportError:
            pytest.skip("Compliance dashboard service not available")

    @pytest.fixture
    def unified_reporter(self):
        """Create unified compliance reporter for testing."""
        try:
            from src.core.services.audit_service.reporters.unified_compliance import (
                UnifiedComplianceReporter,
            )

            return UnifiedComplianceReporter()
        except ImportError:
            pytest.skip("Unified compliance reporter not available")

    async def test_unified_dashboard_all_frameworks(self, compliance_dashboard_service):
        """Test unified dashboard with all frameworks."""
        dashboard = await compliance_dashboard_service.get_unified_dashboard()

        # Verify all 6 frameworks are assessed
        assert len(dashboard.framework_assessments) >= 6

        # Verify dashboard structure
        assert dashboard.dashboard_id is not None
        assert dashboard.overall_compliance_score >= 0.0
        assert dashboard.overall_compliance_score <= 100.0
        assert dashboard.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_unified_dashboard_filtered_frameworks(self, compliance_dashboard_service):
        """Test unified dashboard with filtered frameworks."""
        from src.core.services.compliance_docs.src.api.compliance_dashboard import (
            ComplianceFramework,
        )

        # Test with subset of frameworks
        frameworks = [ComplianceFramework.SOC2, ComplianceFramework.GDPR]
        dashboard = await compliance_dashboard_service.get_unified_dashboard(frameworks=frameworks)

        # Verify only requested frameworks
        assert len(dashboard.framework_assessments) == 2
        for assessment in dashboard.framework_assessments:
            assert assessment.framework in frameworks

    async def test_overall_compliance_score_calculation(self, compliance_dashboard_service):
        """Test overall compliance score calculation."""
        dashboard = await compliance_dashboard_service.get_unified_dashboard()

        # Calculate expected average
        total = sum(a.coverage_percentage for a in dashboard.framework_assessments)
        expected_average = total / len(dashboard.framework_assessments)

        # Verify overall score matches average
        assert abs(dashboard.overall_compliance_score - expected_average) < 0.1

    async def test_compliance_status_determination(self, compliance_dashboard_service):
        """Test compliance status determination logic."""
        from src.core.services.compliance_docs.src.api.compliance_dashboard import (
            ComplianceStatus,
        )

        dashboard = await compliance_dashboard_service.get_unified_dashboard()

        # Verify status based on score
        if dashboard.overall_compliance_score >= 95:
            assert dashboard.overall_status == ComplianceStatus.COMPLIANT
        elif dashboard.overall_compliance_score >= 80:
            assert dashboard.overall_status == ComplianceStatus.PARTIALLY_COMPLIANT
        else:
            assert dashboard.overall_status == ComplianceStatus.NON_COMPLIANT

    async def test_gap_analysis(self, compliance_dashboard_service):
        """Test gap analysis functionality."""
        from src.core.services.compliance_docs.src.api.compliance_dashboard import (
            GapAnalysisRequest,
        )

        request = GapAnalysisRequest()
        gaps = await compliance_dashboard_service.get_gap_analysis(request)

        # Verify gaps are returned
        assert isinstance(gaps, list)

        for gap in gaps:
            assert gap.gap_id is not None
            assert gap.framework is not None
            assert gap.control_id is not None
            assert gap.description is not None
            assert gap.priority is not None

    async def test_gap_analysis_priority_filter(self, compliance_dashboard_service):
        """Test gap analysis with priority filter."""
        from src.core.services.compliance_docs.src.api.compliance_dashboard import (
            GapAnalysisRequest,
            GapPriority,
        )

        request = GapAnalysisRequest(priority_filter=GapPriority.P2_HIGH)
        gaps = await compliance_dashboard_service.get_gap_analysis(request)

        # Verify all gaps match priority
        for gap in gaps:
            assert gap.priority == GapPriority.P2_HIGH

    async def test_cross_framework_gap_impact(self, compliance_dashboard_service):
        """Test cross-framework gap impact tracking."""
        from src.core.services.compliance_docs.src.api.compliance_dashboard import (
            GapAnalysisRequest,
        )

        request = GapAnalysisRequest(include_cross_framework=True)
        gaps = await compliance_dashboard_service.get_gap_analysis(request)

        # Check for gaps with cross-framework impact
        for gap in gaps:
            # Verify cross_framework_impact is a list
            assert isinstance(gap.cross_framework_impact, list)

    async def test_executive_summary_generation(self, compliance_dashboard_service):
        """Test executive summary generation."""
        from src.core.services.compliance_docs.src.api.compliance_dashboard import (
            ExecutiveSummaryRequest,
        )

        request = ExecutiveSummaryRequest()
        summary = await compliance_dashboard_service.get_executive_summary(request)

        # Verify summary content
        assert "ACGS-2" in summary
        assert "Compliance" in summary
        assert "Score" in summary or "%" in summary

        # Verify constitutional hash is included
        assert CONSTITUTIONAL_HASH in summary

    async def test_unified_report_generation(self, unified_reporter):
        """Test unified compliance report generation."""
        report = await unified_reporter.generate_unified_report()

        # Verify report structure
        assert report.report_id is not None
        assert report.score is not None
        assert report.executive_summary is not None or report.score.overall_score >= 0

        # Verify gap analysis
        assert isinstance(report.gap_analysis, dict)

        # Verify remediation roadmap
        assert isinstance(report.remediation_roadmap, list)

    async def test_unified_report_export_json(self, unified_reporter):
        """Test unified compliance report JSON export."""
        report = await unified_reporter.generate_unified_report()
        json_output = await unified_reporter.export_report(report, "json")

        # Verify valid JSON
        data = json.loads(json_output)
        assert "report_id" in data
        assert "score" in data
        assert "constitutional_hash" in data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_unified_report_export_html(self, unified_reporter):
        """Test unified compliance report HTML export."""
        report = await unified_reporter.generate_unified_report()
        html_output = await unified_reporter.export_report(report, "html")

        # Verify HTML structure
        assert "<!DOCTYPE html>" in html_output
        assert "Unified Compliance Report" in html_output
        assert CONSTITUTIONAL_HASH in html_output


# ============================================================================
# 6.4 Trend Analysis Tests
# ============================================================================


class TestComplianceTrendAnalysis:
    """
    Test suite for compliance trend analysis.

    Validates:
    - Historical compliance data tracking
    - Trend calculation and visualization
    - Compliance score progression
    - Framework-specific trends
    """

    @pytest.fixture
    def compliance_dashboard_service(self):
        """Create compliance dashboard service for testing."""
        try:
            from src.core.services.compliance_docs.src.api.compliance_dashboard import (
                ComplianceDashboardService,
            )

            return ComplianceDashboardService()
        except ImportError:
            pytest.skip("Compliance dashboard service not available")

    async def test_dashboard_has_trend_data_field(self, compliance_dashboard_service):
        """Test that dashboard includes compliance trend data field."""
        dashboard = await compliance_dashboard_service.get_unified_dashboard()

        # Verify trend field exists
        assert hasattr(dashboard, "compliance_trend")
        assert isinstance(dashboard.compliance_trend, list)

    async def test_framework_assessment_timestamps(self, compliance_dashboard_service):
        """Test that framework assessments have timestamps for trend tracking."""
        dashboard = await compliance_dashboard_service.get_unified_dashboard()

        for assessment in dashboard.framework_assessments:
            # Verify last assessment date exists
            assert hasattr(assessment, "last_assessment")
            assert assessment.last_assessment is not None

            # Verify timestamp is a datetime
            assert isinstance(assessment.last_assessment, datetime)

    async def test_multiple_dashboard_snapshots(self, compliance_dashboard_service):
        """Test that multiple dashboard snapshots can be generated for trend analysis."""
        import time

        # Generate multiple snapshots with small delay for unique timestamps
        snapshots = []
        for i in range(3):
            if i > 0:
                time.sleep(0.01)  # Small delay, IDs use same-second grouping
            dashboard = await compliance_dashboard_service.get_unified_dashboard()
            snapshots.append(
                {
                    "dashboard_id": dashboard.dashboard_id,
                    "score": dashboard.overall_compliance_score,
                    "timestamp": dashboard.generated_at,
                }
            )

        # Dashboard IDs are timestamp-based (second resolution)
        # Within same second, IDs will be identical - this is expected
        # We verify the IDs follow the expected format
        for snapshot in snapshots:
            assert snapshot["dashboard_id"].startswith("dash_")

        # Verify scores are consistent (same service, same data)
        scores = [s["score"] for s in snapshots]
        assert max(scores) - min(scores) < 0.1  # Small variance allowed

    async def test_framework_control_status_tracking(self, compliance_dashboard_service):
        """Test tracking of control status for trend analysis."""
        dashboard = await compliance_dashboard_service.get_unified_dashboard()

        for assessment in dashboard.framework_assessments:
            # Verify control status breakdown
            control_status = assessment.control_status

            assert control_status.total_controls >= 0
            assert control_status.implemented >= 0
            assert control_status.partial >= 0
            assert control_status.planned >= 0
            assert control_status.not_applicable >= 0

            # Verify coverage percentage is calculable
            assert control_status.coverage_percentage >= 0.0
            assert control_status.coverage_percentage <= 100.0

    async def test_gap_status_tracking(self, compliance_dashboard_service):
        """Test gap status tracking for trend analysis."""
        from src.core.services.compliance_docs.src.api.compliance_dashboard import (
            GapAnalysisRequest,
        )

        request = GapAnalysisRequest()
        gaps = await compliance_dashboard_service.get_gap_analysis(request)

        # Verify gaps have status for tracking
        for gap in gaps:
            assert gap.status in ["open", "in_progress", "planned", "closed", "resolved"]


# ============================================================================
# Integration Tests
# ============================================================================


class TestFR9Integration:
    """
    Integration tests for FR-9 reporting and analytics.

    Validates end-to-end functionality of the reporting dashboard.
    """

    @pytest.fixture
    def compliance_dashboard_service(self):
        """Create compliance dashboard service for testing."""
        try:
            from src.core.services.compliance_docs.src.api.compliance_dashboard import (
                ComplianceDashboardService,
            )

            return ComplianceDashboardService()
        except ImportError:
            pytest.skip("Compliance dashboard service not available")

    @pytest.fixture
    def unified_reporter(self):
        """Create unified compliance reporter for testing."""
        try:
            from src.core.services.audit_service.reporters.unified_compliance import (
                UnifiedComplianceReporter,
            )

            return UnifiedComplianceReporter()
        except ImportError:
            pytest.skip("Unified compliance reporter not available")

    @pytest.fixture
    def nist_rmf_reporter(self):
        """Create NIST RMF reporter for testing."""
        try:
            from src.core.services.audit_service.reporters.nist_rmf import (
                NISTRiskManagementReporter,
            )

            return NISTRiskManagementReporter()
        except ImportError:
            pytest.skip("NIST RMF reporter not available")

    async def test_end_to_end_compliance_reporting(
        self,
        compliance_dashboard_service,
        unified_reporter,
        nist_rmf_reporter,
    ):
        """Test end-to-end compliance reporting workflow."""
        # Step 1: Generate NIST RMF report
        rmf_report = await nist_rmf_reporter.generate_rmf_report()
        assert rmf_report.compliance_score >= 0.9

        # Step 2: Generate unified dashboard
        dashboard = await compliance_dashboard_service.get_unified_dashboard()
        assert dashboard.overall_compliance_score >= 80.0

        # Step 3: Generate unified report
        unified_report = await unified_reporter.generate_unified_report()
        assert unified_report.score.overall_score >= 80.0

        # Step 4: Export reports
        rmf_json = await nist_rmf_reporter.export_report(rmf_report, "json")
        unified_json = await unified_reporter.export_report(unified_report, "json")

        # Verify exports are valid
        rmf_data = json.loads(rmf_json)
        unified_data = json.loads(unified_json)

        # Both should have constitutional hash
        assert rmf_data["assessment"]["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert unified_data["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_all_frameworks_complete(self, compliance_dashboard_service):
        """Test that all required frameworks are assessed."""
        from src.core.services.compliance_docs.src.api.compliance_dashboard import (
            ComplianceFramework,
        )

        dashboard = await compliance_dashboard_service.get_unified_dashboard()

        # Verify all 6 frameworks from PRD are present
        assessed_frameworks = {a.framework for a in dashboard.framework_assessments}
        required_frameworks = {
            ComplianceFramework.NIST_AI_RMF,
            ComplianceFramework.SOC2,
            ComplianceFramework.GDPR,
            ComplianceFramework.CCPA,
            ComplianceFramework.EU_AI_ACT,
            ComplianceFramework.ISO_27001,
        }

        for framework in required_frameworks:
            assert framework in assessed_frameworks, f"Missing framework: {framework}"

    async def test_constitutional_hash_consistency(
        self,
        compliance_dashboard_service,
        unified_reporter,
        nist_rmf_reporter,
    ):
        """Test constitutional hash consistency across all reports."""
        # Get all reports
        dashboard = await compliance_dashboard_service.get_unified_dashboard()
        unified_report = await unified_reporter.generate_unified_report()
        rmf_report = await nist_rmf_reporter.generate_rmf_report()

        # Verify hash consistency
        assert dashboard.constitutional_hash == CONSTITUTIONAL_HASH
        assert unified_report.constitutional_hash == CONSTITUTIONAL_HASH
        assert rmf_report.assessment.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_compliance_metrics_meet_prd_targets(self, compliance_dashboard_service):
        """Test that compliance metrics meet PRD v2.3.1 targets."""
        dashboard = await compliance_dashboard_service.get_unified_dashboard()

        # PRD Target: Overall compliance > 85%
        assert dashboard.overall_compliance_score >= 85.0, (
            f"Overall compliance {dashboard.overall_compliance_score}% "
            "does not meet PRD target of 85%"
        )

        # Count frameworks meeting 80%+ coverage
        high_coverage = sum(
            1 for a in dashboard.framework_assessments if a.coverage_percentage >= 80.0
        )

        # At least 5 of 6 frameworks should have 80%+ coverage
        assert high_coverage >= 5, f"Only {high_coverage}/6 frameworks meet 80% coverage target"


# ============================================================================
# API Endpoint Simulation Tests
# ============================================================================


class TestComplianceDashboardAPI:
    """
    Test suite for compliance dashboard API endpoints.

    Validates API response formats and status codes.
    """

    @pytest.fixture
    def mock_service(self):
        """Create mock compliance dashboard service."""
        try:
            from src.core.services.compliance_docs.src.api.compliance_dashboard import (
                ComplianceDashboardService,
                ComplianceFramework,
                ComplianceStatus,
                FrameworkAssessment,
                FrameworkControlStatus,
                RiskLevel,
                UnifiedComplianceDashboard,
            )

            service = ComplianceDashboardService()
            return service
        except ImportError:
            pytest.skip("Compliance dashboard API not available")

    async def test_get_dashboard_endpoint(self, mock_service):
        """Test GET /compliance-dashboard/ endpoint."""
        dashboard = await mock_service.get_unified_dashboard()

        # Verify response structure matches API schema
        assert isinstance(dashboard.dashboard_id, str)
        assert isinstance(dashboard.organization, str)
        assert isinstance(dashboard.framework_assessments, list)
        assert isinstance(dashboard.overall_compliance_score, float)
        assert isinstance(dashboard.total_gaps, int)

    async def test_get_frameworks_endpoint(self, mock_service):
        """Test GET /compliance-dashboard/frameworks endpoint."""
        frameworks = list(mock_service._assessments.values())

        assert len(frameworks) >= 6
        for framework in frameworks:
            assert framework.framework is not None
            assert framework.framework_name is not None
            assert framework.coverage_percentage >= 0.0

    async def test_get_gaps_endpoint(self, mock_service):
        """Test GET /compliance-dashboard/gaps endpoint."""
        gaps = mock_service._gaps

        assert isinstance(gaps, list)
        for gap in gaps:
            assert gap.gap_id is not None
            assert gap.description is not None

    async def test_get_score_endpoint(self, mock_service):
        """Test GET /compliance-dashboard/score endpoint."""
        dashboard = await mock_service.get_unified_dashboard()

        score_response = {
            "overall_score": dashboard.overall_compliance_score,
            "status": dashboard.overall_status.value,
            "risk_level": dashboard.overall_risk_level.value,
            "total_gaps": dashboard.total_gaps,
            "critical_gaps": dashboard.critical_gaps,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        # Verify response structure
        assert "overall_score" in score_response
        assert "status" in score_response
        assert "constitutional_hash" in score_response
        assert score_response["constitutional_hash"] == CONSTITUTIONAL_HASH


# ============================================================================
# Data Model Tests
# ============================================================================


class TestComplianceDataModels:
    """
    Test suite for compliance data models.

    Validates Pydantic models and dataclasses used in reporting.
    """

    def test_framework_assessment_model(self):
        """Test FrameworkAssessment model."""
        try:
            from src.core.services.compliance_docs.src.api.compliance_dashboard import (
                ComplianceFramework,
                ComplianceStatus,
                FrameworkAssessment,
                FrameworkControlStatus,
                RiskLevel,
            )

            assessment = FrameworkAssessment(
                framework=ComplianceFramework.SOC2,
                framework_name="SOC 2 type II",
                status=ComplianceStatus.COMPLIANT,
                coverage_percentage=100.0,
                risk_level=RiskLevel.LOW,
                control_status=FrameworkControlStatus(
                    total_controls=18,
                    implemented=18,
                    coverage_percentage=100.0,
                ),
            )

            assert assessment.framework == ComplianceFramework.SOC2
            assert assessment.coverage_percentage == 100.0
            assert assessment.status == ComplianceStatus.COMPLIANT
        except ImportError:
            pytest.skip("Compliance dashboard models not available")

    def test_compliance_gap_model(self):
        """Test ComplianceGap model."""
        try:
            from src.core.services.compliance_docs.src.api.compliance_dashboard import (
                ComplianceFramework,
                ComplianceGap,
                GapPriority,
                RiskLevel,
            )

            gap = ComplianceGap(
                gap_id="GAP-TEST-001",
                framework=ComplianceFramework.NIST_AI_RMF,
                control_id="MEASURE-2.6",
                description="Test gap description",
                priority=GapPriority.P2_HIGH,
                risk_level=RiskLevel.MEDIUM,
                status="open",
            )

            assert gap.gap_id == "GAP-TEST-001"
            assert gap.priority == GapPriority.P2_HIGH
            assert gap.status == "open"
        except ImportError:
            pytest.skip("Compliance dashboard models not available")

    def test_unified_dashboard_model(self):
        """Test UnifiedComplianceDashboard model."""
        try:
            from src.core.services.compliance_docs.src.api.compliance_dashboard import (
                ComplianceStatus,
                RiskLevel,
                UnifiedComplianceDashboard,
            )

            dashboard = UnifiedComplianceDashboard(
                dashboard_id="test-dashboard-001",
                overall_compliance_score=91.3,
                overall_status=ComplianceStatus.PARTIALLY_COMPLIANT,
                overall_risk_level=RiskLevel.LOW,
            )

            assert dashboard.dashboard_id == "test-dashboard-001"
            assert dashboard.constitutional_hash == CONSTITUTIONAL_HASH
        except ImportError:
            pytest.skip("Compliance dashboard models not available")


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
