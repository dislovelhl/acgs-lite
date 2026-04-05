"""
ACGS-2 Enhanced Agent Bus - Compliance Layer Models Coverage Tests
Constitutional Hash: 608508a9bd224290

Covers: enhanced_agent_bus/compliance_layer/models.py (390 stmts, 0% -> target 80%+)
Tests Pydantic model construction, enum values, and calculation methods:
  - ComplianceFramework, ComplianceStatus, RiskSeverity, ThreatCategory enums
  - ThreatModel.calculate_risk_score()
  - RiskRegisterEntry.calculate_overall_risk()
  - HighRiskClassification.determine_risk_level()
  - ComplianceAssessment.calculate_score()
  - ComplianceReport.calculate_overall_score()
  - AuditEvidencePackage.calculate_completeness()
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


# ---------------------------------------------------------------------------
# Enum value coverage
# ---------------------------------------------------------------------------


class TestEnums:
    def test_compliance_framework_values(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import ComplianceFramework

        assert ComplianceFramework.NIST_AI_RMF.value == "nist_ai_rmf"
        assert ComplianceFramework.SOC2_TYPE_II.value == "soc2_type_ii"
        assert ComplianceFramework.EU_AI_ACT.value == "eu_ai_act"
        assert ComplianceFramework.ISO_27001.value == "iso_27001"
        assert ComplianceFramework.GDPR.value == "gdpr"

    def test_compliance_status_values(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import ComplianceStatus

        assert ComplianceStatus.COMPLIANT.value == "compliant"
        assert ComplianceStatus.NON_COMPLIANT.value == "non_compliant"
        assert ComplianceStatus.PARTIAL.value == "partial"
        assert ComplianceStatus.NOT_ASSESSED.value == "not_assessed"
        assert ComplianceStatus.IN_PROGRESS.value == "in_progress"
        assert ComplianceStatus.EXEMPT.value == "exempt"

    def test_risk_severity_values(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import RiskSeverity

        assert RiskSeverity.CRITICAL.value == "critical"
        assert RiskSeverity.HIGH.value == "high"
        assert RiskSeverity.MEDIUM.value == "medium"
        assert RiskSeverity.LOW.value == "low"
        assert RiskSeverity.INFORMATIONAL.value == "informational"

    def test_threat_category_values(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import ThreatCategory

        assert ThreatCategory.DATA_POISONING.value == "data_poisoning"
        assert ThreatCategory.PROMPT_INJECTION.value == "prompt_injection"
        assert ThreatCategory.CONSTITUTIONAL_BYPASS.value == "constitutional_bypass"
        assert ThreatCategory.GOVERNANCE_EVASION.value == "governance_evasion"

    def test_data_classification_values(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import DataClassification

        assert DataClassification.PUBLIC.value == "public"
        assert DataClassification.PII.value == "pii"
        assert DataClassification.PHI.value == "phi"
        assert DataClassification.RESTRICTED.value == "restricted"

    def test_human_oversight_level_values(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import HumanOversightLevel

        assert HumanOversightLevel.HUMAN_IN_THE_LOOP.value == "human_in_the_loop"
        assert HumanOversightLevel.FULLY_AUTOMATED.value == "fully_automated"


# ---------------------------------------------------------------------------
# Model construction
# ---------------------------------------------------------------------------


class TestModelConstruction:
    def test_risk_context(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import RiskContext

        ctx = RiskContext(
            context_id="ctx-001",
            system_name="TestSystem",
            intended_purpose="Testing",
        )
        assert ctx.context_id == "ctx-001"
        assert ctx.system_version == "1.0.0"
        assert ctx.deployment_environment == "production"

    def test_threat_model(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ThreatCategory,
            ThreatModel,
        )

        threat = ThreatModel(
            threat_id="t-001",
            category=ThreatCategory.PROMPT_INJECTION,
            name="Prompt Injection",
            description="Malicious prompt injection",
            attack_vector="User input",
        )
        assert threat.threat_id == "t-001"
        assert threat.risk_score == 0.5

    def test_risk_mitigation(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import RiskMitigation

        mit = RiskMitigation(
            mitigation_id="m-001",
            threat_id="t-001",
            name="Input validation",
            description="Validate all inputs",
        )
        assert mit.control_type == "preventive"
        assert mit.effectiveness == 0.0

    def test_processing_integrity_control(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import ProcessingIntegrityControl

        ctrl = ProcessingIntegrityControl(
            control_id="pi-001",
            control_name="Data validation",
            description="Validate data integrity",
            criteria="PI1.1",
        )
        assert ctrl.testing_frequency == "quarterly"

    def test_confidentiality_control(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ConfidentialityControl,
            DataClassification,
        )

        ctrl = ConfidentialityControl(
            control_id="c-001",
            control_name="Encryption",
            description="Encrypt data",
            criteria="C1.1",
        )
        assert ctrl.data_classification == DataClassification.CONFIDENTIAL

    def test_availability_control(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import AvailabilityControl

        ctrl = AvailabilityControl(
            control_id="a-001",
            control_name="Redundancy",
            description="Multi-region failover",
            criteria="A1.1",
        )
        assert ctrl.uptime_target == 99.9
        assert ctrl.recovery_time_objective == 60

    def test_audit_evidence_item(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import AuditEvidenceItem

        item = AuditEvidenceItem(
            evidence_id="ev-001",
            control_id="pi-001",
            evidence_type="log",
            description="System logs",
            source="CloudWatch",
        )
        assert item.validity_period_days == 90
        assert item.is_valid is True

    def test_data_classification_entry(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            DataClassification,
            DataClassificationEntry,
        )

        entry = DataClassificationEntry(
            entry_id="dc-001",
            data_type="user_email",
            classification=DataClassification.PII,
        )
        assert entry.encryption_required is True
        assert entry.retention_days == 90

    def test_compliance_violation(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceFramework,
            ComplianceViolation,
        )

        violation = ComplianceViolation(
            violation_id="v-001",
            framework=ComplianceFramework.SOC2_TYPE_II,
            control_id="pi-001",
            description="Missing encryption at rest",
        )
        assert violation.remediation_actions == []

    def test_human_oversight_mechanism(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import HumanOversightMechanism

        mech = HumanOversightMechanism(
            mechanism_id="ho-001",
            name="HITL Review",
            description="Human review before execution",
        )
        assert mech.is_compliant is False

    def test_transparency_requirement(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import TransparencyRequirement

        req = TransparencyRequirement(
            requirement_id="tr-001",
            description="Disclose AI limitations",
        )
        assert req.article_reference == "Article 13"

    def test_technical_documentation(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import TechnicalDocumentation

        doc = TechnicalDocumentation(
            doc_id="td-001",
            system_name="ACGS-2",
        )
        assert doc.version == "1.0.0"


# ---------------------------------------------------------------------------
# Calculation methods
# ---------------------------------------------------------------------------


class TestThreatModelCalculation:
    def test_calculate_risk_score_default(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ThreatCategory,
            ThreatModel,
        )

        threat = ThreatModel(
            threat_id="t-001",
            category=ThreatCategory.DATA_POISONING,
            name="Poisoning",
            description="Data poisoning attack",
            attack_vector="Training data",
        )
        score = threat.calculate_risk_score()
        # Default likelihood=MEDIUM(0.5), impact=MEDIUM(0.5) -> (0.5+0.5)/2 = 0.5
        assert score == pytest.approx(0.5)

    def test_calculate_risk_score_critical(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            RiskSeverity,
            ThreatCategory,
            ThreatModel,
        )

        threat = ThreatModel(
            threat_id="t-002",
            category=ThreatCategory.CONSTITUTIONAL_BYPASS,
            name="Bypass",
            description="Constitutional bypass",
            attack_vector="API",
            likelihood=RiskSeverity.CRITICAL,
            impact=RiskSeverity.CRITICAL,
        )
        score = threat.calculate_risk_score()
        assert score == pytest.approx(1.0)

    def test_calculate_risk_score_low(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            RiskSeverity,
            ThreatCategory,
            ThreatModel,
        )

        threat = ThreatModel(
            threat_id="t-003",
            category=ThreatCategory.INSIDER_THREAT,
            name="Insider",
            description="Insider threat",
            attack_vector="Internal",
            likelihood=RiskSeverity.LOW,
            impact=RiskSeverity.INFORMATIONAL,
        )
        score = threat.calculate_risk_score()
        assert score == pytest.approx((0.3 + 0.1) / 2)


class TestRiskRegisterEntry:
    def _make_threat(self, risk_score: float = 0.5):
        from enhanced_agent_bus.compliance_layer.models import (
            ThreatCategory,
            ThreatModel,
        )

        return ThreatModel(
            threat_id="t-001",
            category=ThreatCategory.DATA_POISONING,
            name="Test",
            description="Test",
            attack_vector="Test",
            risk_score=risk_score,
        )

    def _make_mitigation(self, effectiveness: float = 0.8, compliant: bool = True):
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceStatus,
            RiskMitigation,
        )

        return RiskMitigation(
            mitigation_id="m-001",
            threat_id="t-001",
            name="Mitigation",
            description="Test",
            effectiveness=effectiveness,
            implementation_status=(
                ComplianceStatus.COMPLIANT if compliant else ComplianceStatus.NOT_ASSESSED
            ),
        )

    def test_no_threats(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            RiskContext,
            RiskRegisterEntry,
            RiskSeverity,
        )

        entry = RiskRegisterEntry(
            entry_id="rr-001",
            risk_context=RiskContext(
                context_id="ctx-001",
                system_name="Test",
                intended_purpose="Testing",
            ),
        )
        level = entry.calculate_overall_risk()
        assert level == RiskSeverity.LOW

    def test_high_risk_no_mitigations(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            RiskContext,
            RiskRegisterEntry,
            RiskSeverity,
        )

        threat = self._make_threat(risk_score=0.9)
        entry = RiskRegisterEntry(
            entry_id="rr-002",
            risk_context=RiskContext(
                context_id="ctx-002",
                system_name="Test",
                intended_purpose="Testing",
            ),
            threats=[threat],
        )
        level = entry.calculate_overall_risk()
        assert level == RiskSeverity.CRITICAL

    def test_high_risk_with_effective_mitigation(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            RiskContext,
            RiskRegisterEntry,
            RiskSeverity,
        )

        threat = self._make_threat(risk_score=0.9)
        mitigation = self._make_mitigation(effectiveness=0.9, compliant=True)
        entry = RiskRegisterEntry(
            entry_id="rr-003",
            risk_context=RiskContext(
                context_id="ctx-003",
                system_name="Test",
                intended_purpose="Testing",
            ),
            threats=[threat],
            mitigations=[mitigation],
        )
        level = entry.calculate_overall_risk()
        # 0.9 * (1 - 0.9) = 0.09 -> INFORMATIONAL
        assert level == RiskSeverity.INFORMATIONAL

    def test_medium_risk(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            RiskContext,
            RiskRegisterEntry,
            RiskSeverity,
        )

        threat = self._make_threat(risk_score=0.5)
        entry = RiskRegisterEntry(
            entry_id="rr-004",
            risk_context=RiskContext(
                context_id="ctx-004",
                system_name="Test",
                intended_purpose="Testing",
            ),
            threats=[threat],
        )
        level = entry.calculate_overall_risk()
        assert level == RiskSeverity.MEDIUM

    def test_low_risk(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            RiskContext,
            RiskRegisterEntry,
            RiskSeverity,
        )

        threat = self._make_threat(risk_score=0.25)
        entry = RiskRegisterEntry(
            entry_id="rr-005",
            risk_context=RiskContext(
                context_id="ctx-005",
                system_name="Test",
                intended_purpose="Testing",
            ),
            threats=[threat],
        )
        level = entry.calculate_overall_risk()
        assert level == RiskSeverity.LOW

    def test_non_compliant_mitigations_ignored(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            RiskContext,
            RiskRegisterEntry,
            RiskSeverity,
        )

        threat = self._make_threat(risk_score=0.7)
        mitigation = self._make_mitigation(effectiveness=0.9, compliant=False)
        entry = RiskRegisterEntry(
            entry_id="rr-006",
            risk_context=RiskContext(
                context_id="ctx-006",
                system_name="Test",
                intended_purpose="Testing",
            ),
            threats=[threat],
            mitigations=[mitigation],
        )
        level = entry.calculate_overall_risk()
        # Non-compliant mitigation is ignored -> 0.7 -> HIGH
        assert level == RiskSeverity.HIGH


class TestHighRiskClassification:
    def test_biometric_categorization(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import HighRiskClassification

        hrc = HighRiskClassification(
            classification_id="hrc-001",
            system_name="BiometricSystem",
            biometric_categorization=True,
        )
        level = hrc.determine_risk_level()
        assert level == "high"
        assert hrc.is_high_risk is True

    def test_critical_infrastructure(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import HighRiskClassification

        hrc = HighRiskClassification(
            classification_id="hrc-002",
            system_name="InfraSystem",
            critical_infrastructure=True,
        )
        level = hrc.determine_risk_level()
        assert level == "high"

    def test_significant_decisions_with_safety(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import HighRiskClassification

        hrc = HighRiskClassification(
            classification_id="hrc-003",
            system_name="SafetySystem",
            significant_decisions=True,
            safety_component=True,
        )
        level = hrc.determine_risk_level()
        assert level == "high"

    def test_annex_iii_category(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import HighRiskClassification

        hrc = HighRiskClassification(
            classification_id="hrc-004",
            system_name="AnnexSystem",
            annex_iii_category="education",
        )
        level = hrc.determine_risk_level()
        assert level == "high"

    def test_limited_risk(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import HighRiskClassification

        hrc = HighRiskClassification(
            classification_id="hrc-005",
            system_name="SimpleSystem",
        )
        level = hrc.determine_risk_level()
        assert level == "limited"
        assert hrc.is_high_risk is False


class TestComplianceAssessment:
    def test_calculate_score_zero_controls(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceAssessment,
            ComplianceFramework,
        )

        ca = ComplianceAssessment(
            assessment_id="ca-001",
            framework=ComplianceFramework.SOC2_TYPE_II,
            system_name="Test",
        )
        score = ca.calculate_score()
        assert score == 0.0

    def test_calculate_score_all_compliant(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceAssessment,
            ComplianceFramework,
            ComplianceStatus,
        )

        ca = ComplianceAssessment(
            assessment_id="ca-002",
            framework=ComplianceFramework.SOC2_TYPE_II,
            system_name="Test",
            controls_assessed=10,
            controls_compliant=10,
            controls_non_compliant=0,
            controls_partial=0,
        )
        score = ca.calculate_score()
        assert score == 100.0
        assert ca.overall_status == ComplianceStatus.COMPLIANT

    def test_calculate_score_partial(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceAssessment,
            ComplianceFramework,
            ComplianceStatus,
        )

        ca = ComplianceAssessment(
            assessment_id="ca-003",
            framework=ComplianceFramework.NIST_AI_RMF,
            system_name="Test",
            controls_assessed=10,
            controls_compliant=5,
            controls_partial=4,
            controls_non_compliant=1,
        )
        score = ca.calculate_score()
        # (5*1.0 + 4*0.5) / 10 * 100 = 70.0
        assert score == pytest.approx(70.0)
        assert ca.overall_status == ComplianceStatus.PARTIAL

    def test_calculate_score_non_compliant(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceAssessment,
            ComplianceFramework,
            ComplianceStatus,
        )

        ca = ComplianceAssessment(
            assessment_id="ca-004",
            framework=ComplianceFramework.EU_AI_ACT,
            system_name="Test",
            controls_assessed=10,
            controls_compliant=2,
            controls_non_compliant=8,
        )
        score = ca.calculate_score()
        assert score == 20.0
        assert ca.overall_status == ComplianceStatus.NON_COMPLIANT


class TestComplianceReport:
    def test_calculate_overall_score_empty(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import ComplianceReport

        report = ComplianceReport(report_id="r-001")
        score = report.calculate_overall_score()
        assert score == 0.0

    def test_calculate_overall_score_compliant(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceAssessment,
            ComplianceFramework,
            ComplianceReport,
            ComplianceStatus,
        )

        a1 = ComplianceAssessment(
            assessment_id="a-001",
            framework=ComplianceFramework.SOC2_TYPE_II,
            system_name="Test",
            compliance_score=96.0,
        )
        a2 = ComplianceAssessment(
            assessment_id="a-002",
            framework=ComplianceFramework.NIST_AI_RMF,
            system_name="Test",
            compliance_score=98.0,
        )
        report = ComplianceReport(report_id="r-002", assessments=[a1, a2])
        score = report.calculate_overall_score()
        assert score == pytest.approx(97.0)
        assert report.overall_status == ComplianceStatus.COMPLIANT

    def test_calculate_overall_score_partial(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceAssessment,
            ComplianceFramework,
            ComplianceReport,
            ComplianceStatus,
        )

        a1 = ComplianceAssessment(
            assessment_id="a-003",
            framework=ComplianceFramework.SOC2_TYPE_II,
            system_name="Test",
            compliance_score=70.0,
        )
        a2 = ComplianceAssessment(
            assessment_id="a-004",
            framework=ComplianceFramework.GDPR,
            system_name="Test",
            compliance_score=80.0,
        )
        report = ComplianceReport(report_id="r-003", assessments=[a1, a2])
        score = report.calculate_overall_score()
        assert score == pytest.approx(75.0)
        assert report.overall_status == ComplianceStatus.PARTIAL

    def test_calculate_overall_score_non_compliant(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceAssessment,
            ComplianceFramework,
            ComplianceReport,
            ComplianceStatus,
        )

        a1 = ComplianceAssessment(
            assessment_id="a-005",
            framework=ComplianceFramework.ISO_27001,
            system_name="Test",
            compliance_score=30.0,
        )
        report = ComplianceReport(report_id="r-004", assessments=[a1])
        score = report.calculate_overall_score()
        assert score == pytest.approx(30.0)
        assert report.overall_status == ComplianceStatus.NON_COMPLIANT


class TestAuditEvidencePackage:
    def test_calculate_completeness_empty(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import AuditEvidencePackage

        pkg = AuditEvidencePackage(
            package_id="pkg-001",
            period_start=datetime.now(UTC),
            period_end=datetime.now(UTC),
        )
        score = pkg.calculate_completeness()
        assert score == 0.0

    def test_calculate_completeness_full(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import AuditEvidencePackage

        pkg = AuditEvidencePackage(
            package_id="pkg-002",
            period_start=datetime.now(UTC),
            period_end=datetime.now(UTC),
            uptime_metrics={"api": 99.9},
            incident_log=[{"id": "inc-1"}],
            change_log=[{"id": "chg-1"}],
            access_reviews=[{"id": "ar-1"}],
            vulnerability_scans=[{"id": "vs-1"}],
            backup_test_results=[{"id": "bt-1"}],
            pi_controls_evidence={"pi-001": []},
            c_controls_evidence={"c-001": []},
            a_controls_evidence={"a-001": []},
        )
        score = pkg.calculate_completeness()
        assert score == 100.0

    def test_calculate_completeness_partial(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import AuditEvidencePackage

        pkg = AuditEvidencePackage(
            package_id="pkg-003",
            period_start=datetime.now(UTC),
            period_end=datetime.now(UTC),
            uptime_metrics={"api": 99.9},
            incident_log=[{"id": "inc-1"}],
        )
        score = pkg.calculate_completeness()
        # 2/6 * 50 = ~16.67
        assert 15.0 < score < 20.0
