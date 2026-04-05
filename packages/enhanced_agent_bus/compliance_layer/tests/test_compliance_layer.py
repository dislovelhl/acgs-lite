"""
ACGS-2 Compliance Layer Tests
Constitutional Hash: 608508a9bd224290

Comprehensive test suite for Layer 4: Compliance & Transparency
Testing NIST AI RMF, SOC 2, and EU AI Act compliance components.
"""

from datetime import datetime, timezone

import pytest

# Constitutional hash for validation
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# ============================================================================
# Models Tests
# ============================================================================


class TestComplianceModels:
    """Tests for compliance layer data models."""

    def test_compliance_framework_enum(self):
        """Test ComplianceFramework enum values."""
        from enhanced_agent_bus.compliance_layer.models import ComplianceFramework

        assert ComplianceFramework.NIST_AI_RMF.value == "nist_ai_rmf"
        assert ComplianceFramework.SOC2_TYPE_II.value == "soc2_type_ii"
        assert ComplianceFramework.EU_AI_ACT.value == "eu_ai_act"

    def test_compliance_status_enum(self):
        """Test ComplianceStatus enum values."""
        from enhanced_agent_bus.compliance_layer.models import ComplianceStatus

        assert ComplianceStatus.COMPLIANT.value == "compliant"
        assert ComplianceStatus.NON_COMPLIANT.value == "non_compliant"
        assert ComplianceStatus.PARTIAL.value == "partial"

    def test_risk_severity_enum(self):
        """Test RiskSeverity enum values."""
        from enhanced_agent_bus.compliance_layer.models import RiskSeverity

        assert RiskSeverity.CRITICAL.value == "critical"
        assert RiskSeverity.HIGH.value == "high"
        assert RiskSeverity.MEDIUM.value == "medium"
        assert RiskSeverity.LOW.value == "low"

    def test_threat_category_enum(self):
        """Test ThreatCategory enum values."""
        from enhanced_agent_bus.compliance_layer.models import ThreatCategory

        assert ThreatCategory.PROMPT_INJECTION.value == "prompt_injection"
        assert ThreatCategory.CONSTITUTIONAL_BYPASS.value == "constitutional_bypass"

    def test_data_classification_enum(self):
        """Test DataClassification enum values."""
        from enhanced_agent_bus.compliance_layer.models import DataClassification

        assert DataClassification.PUBLIC.value == "public"
        assert DataClassification.PII.value == "pii"
        assert DataClassification.CONFIDENTIAL.value == "confidential"

    def test_human_oversight_level_enum(self):
        """Test HumanOversightLevel enum values."""
        from enhanced_agent_bus.compliance_layer.models import HumanOversightLevel

        assert HumanOversightLevel.HUMAN_IN_THE_LOOP.value == "human_in_the_loop"
        assert HumanOversightLevel.HUMAN_ON_THE_LOOP.value == "human_on_the_loop"

    def test_risk_context_creation(self):
        """Test RiskContext model creation."""
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceFramework,
            DataClassification,
            RiskContext,
            RiskSeverity,
        )

        context = RiskContext(
            context_id="ctx-001",
            system_name="ACGS-2",
            intended_purpose="AI governance",
            data_types=[DataClassification.CONFIDENTIAL],
            risk_tolerance=RiskSeverity.MEDIUM,
        )

        assert context.context_id == "ctx-001"
        assert context.system_name == "ACGS-2"
        assert context.constitutional_hash == CONSTITUTIONAL_HASH

    def test_threat_model_risk_calculation(self):
        """Test ThreatModel risk score calculation."""
        from enhanced_agent_bus.compliance_layer.models import (
            RiskSeverity,
            ThreatCategory,
            ThreatModel,
        )

        threat = ThreatModel(
            threat_id="T-001",
            category=ThreatCategory.PROMPT_INJECTION,
            name="Test Threat",
            description="Test description",
            attack_vector="API",
            likelihood=RiskSeverity.HIGH,
            impact=RiskSeverity.CRITICAL,
        )

        score = threat.calculate_risk_score()
        assert 0.8 <= score <= 1.0

    def test_compliance_assessment_score_calculation(self):
        """Test ComplianceAssessment score calculation."""
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceAssessment,
            ComplianceFramework,
            ComplianceStatus,
        )

        assessment = ComplianceAssessment(
            assessment_id="ca-001",
            framework=ComplianceFramework.NIST_AI_RMF,
            system_name="ACGS-2",
            controls_assessed=10,
            controls_compliant=8,
            controls_partial=1,
            controls_non_compliant=1,
        )

        score = assessment.calculate_score()
        assert score == 85.0  # (8*1 + 1*0.5) / 10 * 100
        assert assessment.overall_status == ComplianceStatus.PARTIAL

    def test_compliance_report_overall_score(self):
        """Test ComplianceReport overall score calculation."""
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceAssessment,
            ComplianceFramework,
            ComplianceReport,
        )

        report = ComplianceReport(report_id="rep-001")

        assessment1 = ComplianceAssessment(
            assessment_id="ca-001",
            framework=ComplianceFramework.NIST_AI_RMF,
            system_name="ACGS-2",
            compliance_score=90.0,
        )
        assessment2 = ComplianceAssessment(
            assessment_id="ca-002",
            framework=ComplianceFramework.SOC2_TYPE_II,
            system_name="ACGS-2",
            compliance_score=80.0,
        )

        report.assessments = [assessment1, assessment2]
        score = report.calculate_overall_score()

        assert score == 85.0


# ============================================================================
# NIST Risk Assessor Tests
# ============================================================================


class TestNISTRiskAssessor:
    """Tests for NIST AI RMF Risk Assessor."""

    @pytest.fixture
    def assessor(self):
        from enhanced_agent_bus.compliance_layer.nist_risk_assessor import (
            NISTRiskAssessor,
            reset_nist_risk_assessor,
        )

        reset_nist_risk_assessor()
        return NISTRiskAssessor()

    def test_assessor_initialization(self, assessor):
        """Test NISTRiskAssessor initialization."""
        assert assessor.constitutional_hash == CONSTITUTIONAL_HASH
        assert assessor.map_function is not None
        assert assessor.govern_function is not None

    async def test_assessor_initialize(self, assessor):
        """Test async initialization."""
        result = await assessor.initialize()
        assert result is True
        assert len(assessor.get_threats()) > 0

    def test_map_function_establish_context(self, assessor):
        """Test MAP function context establishment."""
        context = assessor.map_function.establish_context(
            system_name="ACGS-2",
            intended_purpose="AI governance",
        )

        assert context.system_name == "ACGS-2"
        assert context.context_id.startswith("ctx-")
        assert context.constitutional_hash == CONSTITUTIONAL_HASH

    def test_govern_function_register_policy(self, assessor):
        """Test GOVERN function policy registration."""
        policy = assessor.govern_function.register_policy(
            policy_id="POL-001",
            policy_name="Test Policy",
            content="Policy content",
        )

        assert policy["policy_id"] == "POL-001"
        assert policy["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_risk_assessment(self, assessor):
        """Test full risk assessment."""
        assessment = await assessor.assess_risk(system_name="ACGS-2")

        assert assessment.framework.value == "nist_ai_rmf"
        assert assessment.system_name == "ACGS-2"
        assert assessment.controls_assessed > 0
        assert 0 <= assessment.compliance_score <= 100

    def test_add_threat(self, assessor):
        """Test adding custom threat."""
        from enhanced_agent_bus.compliance_layer.models import (
            RiskSeverity,
            ThreatCategory,
            ThreatModel,
        )

        threat = ThreatModel(
            threat_id="CUSTOM-001",
            category=ThreatCategory.GOVERNANCE_EVASION,
            name="Custom Threat",
            description="Test threat",
            attack_vector="Custom",
        )

        assessor.add_threat(threat)
        threats = assessor.get_threats()

        assert any(t.threat_id == "CUSTOM-001" for t in threats)


# ============================================================================
# SOC 2 Auditor Tests
# ============================================================================


class TestSOC2Auditor:
    """Tests for SOC 2 type II Auditor."""

    @pytest.fixture
    def auditor(self):
        from enhanced_agent_bus.compliance_layer.soc2_auditor import (
            SOC2Auditor,
            reset_soc2_auditor,
        )

        reset_soc2_auditor()
        return SOC2Auditor()

    def test_auditor_initialization(self, auditor):
        """Test SOC2Auditor initialization."""
        assert auditor.constitutional_hash == CONSTITUTIONAL_HASH
        assert auditor.control_validator is not None
        assert auditor.evidence_collector is not None

    async def test_auditor_initialize(self, auditor):
        """Test async initialization."""
        result = await auditor.initialize()
        assert result is True
        assert len(auditor.get_pi_controls()) > 0
        assert len(auditor.get_c_controls()) > 0

    async def test_soc2_audit(self, auditor):
        """Test SOC 2 audit."""
        assessment = await auditor.audit(system_name="ACGS-2")

        assert assessment.framework.value == "soc2_type_ii"
        assert assessment.system_name == "ACGS-2"
        assert assessment.controls_assessed > 0
        assert 0 <= assessment.compliance_score <= 100

    def test_control_validator_pi(self, auditor):
        """Test Processing Integrity control validation."""
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceStatus,
            ProcessingIntegrityControl,
        )

        control = ProcessingIntegrityControl(
            control_id="PI-TEST",
            control_name="Test Control",
            description="Test",
            criteria="CC7.1",
            completeness_check=True,
            accuracy_check=True,
            timeliness_check=True,
            authorization_check=True,
        )

        result = auditor.control_validator.validate_processing_integrity(control)
        assert result is True
        assert control.implementation_status == ComplianceStatus.COMPLIANT

    def test_control_validator_confidentiality(self, auditor):
        """Test Confidentiality control validation."""
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceStatus,
            ConfidentialityControl,
        )

        control = ConfidentialityControl(
            control_id="C-TEST",
            control_name="Test Control",
            description="Test",
            criteria="C1.1",
            encryption_at_rest=True,
            encryption_in_transit=True,
            access_controls=["RBAC"],
            retention_policy="90 days",
        )

        result = auditor.control_validator.validate_confidentiality(control)
        assert result is True
        assert control.implementation_status == ComplianceStatus.COMPLIANT

    def test_evidence_collection(self, auditor):
        """Test evidence collection."""
        evidence = auditor.evidence_collector.collect_evidence(
            control_id="PI1.1",
            evidence_type="log",
            description="Test evidence",
            source="test",
        )

        assert evidence.evidence_id.startswith("ev-")
        assert evidence.control_id == "PI1.1"
        assert evidence.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_data_classification_matrix(self, auditor):
        """Test data classification matrix."""
        await auditor.initialize()
        matrix = auditor.get_data_classification_matrix()

        assert len(matrix) > 0
        assert any(e.data_type == "User PII" for e in matrix)

    async def test_availability_controls_initialized(self, auditor):
        """Test that Availability controls (A1.x) are initialized."""
        await auditor.initialize()
        a_controls = auditor.get_a_controls()

        assert len(a_controls) >= 3
        control_ids = [c.control_id for c in a_controls]
        assert "A1.1" in control_ids
        assert "A1.2" in control_ids
        assert "A1.3" in control_ids

    def test_control_validator_availability(self, auditor):
        """Test Availability control validation."""
        from enhanced_agent_bus.compliance_layer.models import (
            AvailabilityControl,
            ComplianceStatus,
        )

        control = AvailabilityControl(
            control_id="A-TEST",
            control_name="Test Availability Control",
            description="Test",
            criteria="A1.1",
            uptime_target=99.9,
            current_uptime=99.95,
            disaster_recovery_plan=True,
            monitoring_enabled=True,
            incident_response_plan=True,
            capacity_planning=True,
            backup_procedures=["Daily backups"],
        )

        result = auditor.control_validator.validate_availability(control)
        assert result is True
        assert control.implementation_status == ComplianceStatus.COMPLIANT

    def test_control_validator_availability_partial(self, auditor):
        """Test Availability control validation with partial compliance."""
        from enhanced_agent_bus.compliance_layer.models import (
            AvailabilityControl,
            ComplianceStatus,
        )

        # Partial compliance: 3-4 checks pass (uptime below target but other controls in place)
        control = AvailabilityControl(
            control_id="A-TEST-PARTIAL",
            control_name="Test Partial Control",
            description="Test",
            criteria="A1.1",
            uptime_target=99.9,
            current_uptime=99.0,  # Below target - FAIL
            disaster_recovery_plan=True,  # PASS
            monitoring_enabled=True,  # PASS
            incident_response_plan=True,  # PASS
            capacity_planning=False,  # FAIL
            backup_procedures=[],  # FAIL
        )

        result = auditor.control_validator.validate_availability(control)
        assert result is False
        assert control.implementation_status == ComplianceStatus.PARTIAL

    async def test_validate_uptime_sla(self, auditor):
        """Test 99.9% uptime SLA validation."""
        await auditor.initialize()
        report = auditor.validate_uptime_sla(target_uptime=99.9)

        assert report["target_uptime"] == 99.9
        assert report["controls_validated"] >= 3
        assert report["sla_compliant"] is True
        assert report["average_uptime"] >= 99.9
        assert report["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert len(report["control_details"]) >= 3

    async def test_generate_evidence_package(self, auditor):
        """Test 60-day audit evidence package generation."""
        await auditor.initialize()
        package = auditor.generate_evidence_package(period_days=60)

        assert package.package_id.startswith("evpkg-")
        assert "60-day" in package.package_name
        assert len(package.evidence_items) > 0
        assert len(package.pi_controls_evidence) > 0
        assert len(package.c_controls_evidence) > 0
        assert len(package.a_controls_evidence) > 0
        assert len(package.uptime_metrics) > 0
        assert package.constitutional_hash == CONSTITUTIONAL_HASH

        # Verify completeness calculation
        completeness = package.calculate_completeness()
        assert completeness > 0

    async def test_audit_includes_availability_controls(self, auditor):
        """Test that SOC 2 audit includes Availability controls."""
        assessment = await auditor.audit(system_name="ACGS-2")

        # Should assess PI (3) + C (3) + A (3) = 9 controls
        assert assessment.controls_assessed >= 9
        assert assessment.compliance_score >= 90.0

    async def test_evidence_package_period(self, auditor):
        """Test evidence package covers correct period."""
        from datetime import timedelta

        await auditor.initialize()
        package = auditor.generate_evidence_package(period_days=60)

        period_duration = package.period_end - package.period_start
        assert period_duration >= timedelta(days=59)
        assert period_duration <= timedelta(days=61)


# ============================================================================
# EU AI Act Compliance Tests
# ============================================================================


class TestEUAIActCompliance:
    """Tests for EU AI Act Compliance."""

    @pytest.fixture
    def compliance(self):
        from enhanced_agent_bus.compliance_layer.euaiact_compliance import (
            EUAIActCompliance,
            reset_euaiact_compliance,
        )

        reset_euaiact_compliance()
        return EUAIActCompliance()

    def test_compliance_initialization(self, compliance):
        """Test EUAIActCompliance initialization."""
        assert compliance.constitutional_hash == CONSTITUTIONAL_HASH
        assert compliance.article13 is not None
        assert compliance.article14 is not None

    async def test_compliance_initialize(self, compliance):
        """Test async initialization."""
        result = await compliance.initialize()
        assert result is True
        assert len(compliance.get_documentation()) > 0

    async def test_euaiact_assessment(self, compliance):
        """Test EU AI Act assessment."""
        assessment = await compliance.assess(system_name="ACGS-2")

        assert assessment.framework.value == "eu_ai_act"
        assert assessment.system_name == "ACGS-2"
        assert assessment.controls_assessed > 0
        assert 0 <= assessment.compliance_score <= 100

    def test_article13_transparency(self, compliance):
        """Test Article 13 transparency compliance."""
        result = compliance.article13.check_compliance()

        assert result["article"] == "Article 13"
        assert "compliant_requirements" in result
        assert "is_compliant" in result
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_article14_human_oversight(self, compliance):
        """Test Article 14 human oversight compliance."""
        result = compliance.article14.check_compliance()

        assert result["article"] == "Article 14"
        assert "compliant_mechanisms" in result
        assert "oversight_levels" in result
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_high_risk_classification(self, compliance):
        """Test high-risk system classification."""
        classification = compliance.high_risk_validator.classify_system(
            system_name="Test System",
            critical_infrastructure=True,
        )

        assert classification.is_high_risk is True
        assert classification.risk_level == "high"

    def test_transparency_requirements(self, compliance):
        """Test transparency requirements."""
        requirements = compliance.article13.get_requirements()

        assert len(requirements) > 0
        assert any(r.explanation_api_available for r in requirements)

    def test_human_oversight_mechanisms(self, compliance):
        """Test human oversight mechanisms."""
        mechanisms = compliance.article14.get_mechanisms()

        assert len(mechanisms) > 0
        assert any(m.oversight_level.value == "human_in_the_loop" for m in mechanisms)


# ============================================================================
# Decision Explainer Tests
# ============================================================================


class TestDecisionExplainer:
    """Tests for Decision Explainer."""

    @pytest.fixture
    def explainer(self):
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
            reset_decision_explainer,
        )

        reset_decision_explainer()
        return DecisionExplainer()

    def test_explainer_initialization(self, explainer):
        """Test DecisionExplainer initialization."""
        assert explainer.constitutional_hash == CONSTITUTIONAL_HASH
        assert explainer.enable_counterfactuals is True

    async def test_generate_explanation(self, explainer):
        """Test explanation generation."""
        result = await explainer.explain(
            verdict="ALLOW",
            impact_score=0.3,
        )

        assert result.verdict == "ALLOW"
        assert result.impact_score == 0.3
        assert len(result.factors) > 0
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_explanation_with_context(self, explainer):
        """Test explanation with custom context."""
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            ExplanationContext,
        )

        context = ExplanationContext(
            decision_id="dec-test",
            tenant_id="test-tenant",
            human_oversight_level="human_in_the_loop",
        )

        result = await explainer.explain(
            verdict="DENY",
            impact_score=0.9,
            context=context,
        )

        assert result.decision_id == "dec-test"
        assert result.human_oversight_level == "human_in_the_loop"

    async def test_counterfactual_generation(self, explainer):
        """Test counterfactual analysis."""
        result = await explainer.explain(
            verdict="CONDITIONAL",
            impact_score=0.6,
        )

        assert len(result.counterfactual_hints) > 0
        hint = result.counterfactual_hints[0]
        assert "modified_factor" in hint
        assert "original_value" in hint
        assert "modified_value" in hint

    async def test_governance_vector(self, explainer):
        """Test governance vector generation."""
        result = await explainer.explain(
            verdict="ALLOW",
            impact_score=0.4,
        )

        assert len(result.governance_vector) == 7
        assert "safety" in result.governance_vector
        assert "transparency" in result.governance_vector

    async def test_factor_attribution(self, explainer):
        """Test factor attribution."""
        result = await explainer.explain(
            verdict="ALLOW",
            impact_score=0.5,
            factor_scores={
                "semantic_score": 0.8,
                "permission_score": 0.3,
            },
        )

        assert len(result.factors) >= 2
        assert any(f.factor_name == "Content Analysis" for f in result.factors)


# ============================================================================
# Compliance Reporter Tests
# ============================================================================


class TestComplianceReporter:
    """Tests for Compliance Reporter."""

    @pytest.fixture
    def reporter(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceReporter,
            reset_compliance_reporter,
        )

        reset_compliance_reporter()
        return ComplianceReporter()

    def test_reporter_initialization(self, reporter):
        """Test ComplianceReporter initialization."""
        assert reporter.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_reporter_initialize(self, reporter):
        """Test async initialization."""
        result = await reporter.initialize()
        assert result is True

    async def test_unified_report_generation(self, reporter):
        """Test unified compliance report generation."""
        report = await reporter.generate_unified_report(system_name="ACGS-2")

        assert report.report_id.startswith("ucr-")
        assert report.nist_assessment is not None
        assert report.soc2_assessment is not None
        assert report.euaiact_assessment is not None
        assert report.metrics is not None

    async def test_compliance_metrics(self, reporter):
        """Test compliance metrics calculation."""
        report = await reporter.generate_unified_report(system_name="ACGS-2")

        assert report.metrics.total_controls > 0
        assert 0 <= report.metrics.overall_score <= 100
        assert report.metrics.nist_score >= 0
        assert report.metrics.soc2_score >= 0
        assert report.metrics.euaiact_score >= 0

    async def test_dashboard_generation(self, reporter):
        """Test dashboard data generation."""
        dashboard = await reporter.generate_dashboard(system_name="ACGS-2")

        assert dashboard.metrics is not None
        assert "nist_ai_rmf" in dashboard.framework_status
        assert len(dashboard.recent_assessments) > 0
        assert len(dashboard.recommendations) > 0

    async def test_executive_summary(self, reporter):
        """Test executive summary generation."""
        report = await reporter.generate_unified_report(system_name="ACGS-2")

        assert len(report.executive_summary) > 0
        assert "Overall Compliance" in report.executive_summary
        assert CONSTITUTIONAL_HASH in report.executive_summary


# ============================================================================
# Integration Tests
# ============================================================================


class TestComplianceLayerIntegration:
    """Integration tests for compliance layer."""

    async def test_full_compliance_assessment(self):
        """Test full compliance assessment across all frameworks."""
        from enhanced_agent_bus.compliance_layer import (
            get_compliance_reporter,
            reset_compliance_reporter,
        )

        reset_compliance_reporter()
        reporter = get_compliance_reporter()

        report = await reporter.generate_unified_report(
            system_name="ACGS-2",
            organization="ACGS-2 Platform",
        )

        # Verify all frameworks assessed
        assert report.nist_assessment is not None
        assert report.soc2_assessment is not None
        assert report.euaiact_assessment is not None

        # Verify constitutional hash consistency
        assert report.constitutional_hash == CONSTITUTIONAL_HASH
        assert report.nist_assessment.constitutional_hash == CONSTITUTIONAL_HASH
        assert report.soc2_assessment.constitutional_hash == CONSTITUTIONAL_HASH
        assert report.euaiact_assessment.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_constitutional_hash_enforcement(self):
        """Test constitutional hash is enforced across all components."""
        from enhanced_agent_bus.compliance_layer import (
            get_decision_explainer,
            get_euaiact_compliance,
            get_nist_risk_assessor,
            get_soc2_auditor,
            reset_decision_explainer,
            reset_euaiact_compliance,
            reset_nist_risk_assessor,
            reset_soc2_auditor,
        )

        # Reset all singletons
        reset_nist_risk_assessor()
        reset_soc2_auditor()
        reset_euaiact_compliance()
        reset_decision_explainer()

        # Get fresh instances
        nist = get_nist_risk_assessor()
        soc2 = get_soc2_auditor()
        euaiact = get_euaiact_compliance()
        explainer = get_decision_explainer()

        # Verify all have constitutional hash
        assert nist.constitutional_hash == CONSTITUTIONAL_HASH
        assert soc2.constitutional_hash == CONSTITUTIONAL_HASH
        assert euaiact.constitutional_hash == CONSTITUTIONAL_HASH
        assert explainer.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_explanation_with_compliance(self):
        """Test decision explanation integrates with compliance."""
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
            ExplanationContext,
        )

        explainer = DecisionExplainer()

        context = ExplanationContext(
            decision_id="int-test-001",
            matched_rules=["RULE-001", "RULE-002"],
            applicable_policies=["POL-001"],
        )

        result = await explainer.explain(
            verdict="CONDITIONAL",
            impact_score=0.7,
            context=context,
        )

        assert result.article_13_compliant is True
        assert len(result.transparency_measures) > 0


# ============================================================================
# Constitutional Compliance Tests
# ============================================================================


@pytest.mark.constitutional
class TestConstitutionalCompliance:
    """Tests for constitutional compliance validation."""

    def test_constitutional_hash_in_models(self):
        """Test constitutional hash is in all models."""
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceAssessment,
            ComplianceFramework,
            ComplianceReport,
            ConfidentialityControl,
            HighRiskClassification,
            ProcessingIntegrityControl,
            RiskContext,
            ThreatCategory,
            ThreatModel,
        )

        context = RiskContext(
            context_id="test",
            system_name="test",
            intended_purpose="test",
        )
        assert context.constitutional_hash == CONSTITUTIONAL_HASH

        threat = ThreatModel(
            threat_id="test",
            category=ThreatCategory.PROMPT_INJECTION,
            name="test",
            description="test",
            attack_vector="test",
        )
        assert threat.constitutional_hash == CONSTITUTIONAL_HASH

        assessment = ComplianceAssessment(
            assessment_id="test",
            framework=ComplianceFramework.NIST_AI_RMF,
            system_name="test",
        )
        assert assessment.constitutional_hash == CONSTITUTIONAL_HASH

    def test_module_constitutional_hash(self):
        """Test module exports constitutional hash."""
        from enhanced_agent_bus.compliance_layer import CONSTITUTIONAL_HASH as MODULE_HASH

        assert MODULE_HASH == CONSTITUTIONAL_HASH


# ============================================================================
# Performance Tests
# ============================================================================


class TestPerformance:
    """Performance tests for compliance layer."""

    async def test_assessment_latency(self):
        """Test assessment completes within performance target."""
        import time

        from enhanced_agent_bus.compliance_layer import (
            get_compliance_reporter,
            reset_compliance_reporter,
        )

        reset_compliance_reporter()
        reporter = get_compliance_reporter()

        start = time.perf_counter()
        report = await reporter.generate_unified_report(system_name="ACGS-2")
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Performance target: P99 < 5000ms for full assessment
        assert elapsed_ms < 5000, f"Assessment took {elapsed_ms:.2f}ms, target <5000ms"

    async def test_explanation_latency(self):
        """Test explanation generation latency."""
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
        )

        explainer = DecisionExplainer()
        result = await explainer.explain(
            verdict="ALLOW",
            impact_score=0.5,
        )

        # Performance target: < 5ms for explanation
        assert result.processing_time_ms < 5.0, (
            f"Explanation took {result.processing_time_ms:.2f}ms, target <5ms"
        )
