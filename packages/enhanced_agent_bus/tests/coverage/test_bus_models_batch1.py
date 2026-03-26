"""
Tests for under-covered enhanced_agent_bus pure-Python models and exceptions.
Constitutional Hash: 608508a9bd224290

Covers:
- compliance_layer/models.py (enums, Pydantic models, computed properties)
- api_models.py (request/response models, validators)
- api_exceptions.py (create_error_response utility)
- visual_studio/models.py (workflow models, validators)
- policy_copilot/models.py (copilot models, validators)
- routes/sessions/models.py (session models, validators)
- enterprise_sso/enterprise_sso_infra/models.py (SSO dataclasses)
- exceptions/ hierarchy (all exception submodules)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

# ============================================================================
# compliance_layer/models.py
# ============================================================================


class TestComplianceEnums:
    """Verify all compliance enums have expected members and string values."""

    def test_compliance_framework_values(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import ComplianceFramework

        assert ComplianceFramework.NIST_AI_RMF == "nist_ai_rmf"
        assert ComplianceFramework.SOC2_TYPE_II == "soc2_type_ii"
        assert ComplianceFramework.EU_AI_ACT == "eu_ai_act"
        assert ComplianceFramework.ISO_27001 == "iso_27001"
        assert ComplianceFramework.GDPR == "gdpr"
        assert len(ComplianceFramework) == 5

    def test_compliance_status_values(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import ComplianceStatus

        assert ComplianceStatus.COMPLIANT == "compliant"
        assert ComplianceStatus.NON_COMPLIANT == "non_compliant"
        assert ComplianceStatus.PARTIAL == "partial"
        assert ComplianceStatus.NOT_ASSESSED == "not_assessed"
        assert ComplianceStatus.IN_PROGRESS == "in_progress"
        assert ComplianceStatus.EXEMPT == "exempt"

    def test_risk_severity_values(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import RiskSeverity

        assert RiskSeverity.CRITICAL == "critical"
        assert RiskSeverity.HIGH == "high"
        assert RiskSeverity.MEDIUM == "medium"
        assert RiskSeverity.LOW == "low"
        assert RiskSeverity.INFORMATIONAL == "informational"

    def test_threat_category_values(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import ThreatCategory

        assert ThreatCategory.DATA_POISONING == "data_poisoning"
        assert ThreatCategory.PROMPT_INJECTION == "prompt_injection"
        assert ThreatCategory.CONSTITUTIONAL_BYPASS == "constitutional_bypass"
        assert ThreatCategory.GOVERNANCE_EVASION == "governance_evasion"
        assert len(ThreatCategory) == 9

    def test_data_classification_values(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import DataClassification

        expected = {"public", "internal", "confidential", "restricted", "pii", "phi"}
        actual = {m.value for m in DataClassification}
        assert actual == expected

    def test_human_oversight_level_values(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import HumanOversightLevel

        assert HumanOversightLevel.HUMAN_IN_THE_LOOP == "human_in_the_loop"
        assert HumanOversightLevel.FULLY_AUTOMATED == "fully_automated"
        assert len(HumanOversightLevel) == 4


class TestRiskContext:
    def test_construction_with_required_fields(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import RiskContext

        ctx = RiskContext(
            context_id="ctx-1",
            system_name="test-system",
            intended_purpose="testing",
        )
        assert ctx.context_id == "ctx-1"
        assert ctx.system_version == "1.0.0"
        assert ctx.deployment_environment == "production"
        assert ctx.user_population == "enterprise"
        assert ctx.data_types == []
        assert ctx.regulatory_requirements == []
        assert isinstance(ctx.created_at, datetime)

    def test_serialization_roundtrip(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            DataClassification,
            RiskContext,
            RiskSeverity,
        )

        ctx = RiskContext(
            context_id="ctx-2",
            system_name="sys",
            intended_purpose="test",
            data_types=[DataClassification.PII],
            risk_tolerance=RiskSeverity.HIGH,
        )
        data = ctx.model_dump()
        assert data["context_id"] == "ctx-2"
        assert data["data_types"] == ["pii"]
        assert data["risk_tolerance"] == "high"


class TestThreatModel:
    def test_calculate_risk_score_critical_critical(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            RiskSeverity,
            ThreatCategory,
            ThreatModel,
        )

        t = ThreatModel(
            threat_id="t-1",
            category=ThreatCategory.PROMPT_INJECTION,
            name="Injection",
            description="desc",
            attack_vector="input",
            likelihood=RiskSeverity.CRITICAL,
            impact=RiskSeverity.CRITICAL,
        )
        score = t.calculate_risk_score()
        assert score == 1.0
        assert t.risk_score == 1.0

    def test_calculate_risk_score_low_low(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            RiskSeverity,
            ThreatCategory,
            ThreatModel,
        )

        t = ThreatModel(
            threat_id="t-2",
            category=ThreatCategory.DATA_POISONING,
            name="Poison",
            description="desc",
            attack_vector="data",
            likelihood=RiskSeverity.LOW,
            impact=RiskSeverity.LOW,
        )
        score = t.calculate_risk_score()
        assert score == pytest.approx(0.3)

    def test_calculate_risk_score_mixed(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            RiskSeverity,
            ThreatCategory,
            ThreatModel,
        )

        t = ThreatModel(
            threat_id="t-3",
            category=ThreatCategory.SUPPLY_CHAIN,
            name="Supply",
            description="desc",
            attack_vector="dependency",
            likelihood=RiskSeverity.HIGH,
            impact=RiskSeverity.INFORMATIONAL,
        )
        score = t.calculate_risk_score()
        # (0.8 + 0.1) / 2 = 0.45
        assert score == pytest.approx(0.45)

    def test_risk_score_field_bounds(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import ThreatCategory, ThreatModel

        with pytest.raises(ValidationError):
            ThreatModel(
                threat_id="t-x",
                category=ThreatCategory.INSIDER_THREAT,
                name="x",
                description="x",
                attack_vector="x",
                risk_score=1.5,
            )

    def test_model_dump(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import ThreatCategory, ThreatModel

        t = ThreatModel(
            threat_id="t-dump",
            category=ThreatCategory.MODEL_EXTRACTION,
            name="Extract",
            description="d",
            attack_vector="api",
        )
        d = t.model_dump()
        assert d["threat_id"] == "t-dump"
        assert d["category"] == "model_extraction"
        assert "constitutional_hash" in d


class TestRiskMitigation:
    def test_defaults(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceStatus,
            RiskMitigation,
            RiskSeverity,
        )

        m = RiskMitigation(
            mitigation_id="m-1",
            threat_id="t-1",
            name="Firewall",
            description="desc",
        )
        assert m.control_type == "preventive"
        assert m.implementation_status == ComplianceStatus.NOT_ASSESSED
        assert m.effectiveness == 0.0
        assert m.residual_risk == RiskSeverity.LOW
        assert m.evidence == []

    def test_effectiveness_bounds(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import RiskMitigation

        with pytest.raises(ValidationError):
            RiskMitigation(
                mitigation_id="m-x",
                threat_id="t-x",
                name="x",
                description="x",
                effectiveness=1.5,
            )


class TestRiskRegisterEntry:
    def test_calculate_overall_risk_no_threats(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            RiskContext,
            RiskRegisterEntry,
            RiskSeverity,
        )

        ctx = RiskContext(context_id="c", system_name="s", intended_purpose="p")
        entry = RiskRegisterEntry(entry_id="e-1", risk_context=ctx)
        result = entry.calculate_overall_risk()
        assert result == RiskSeverity.LOW

    def test_calculate_overall_risk_with_threats_no_mitigations(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            RiskContext,
            RiskRegisterEntry,
            RiskSeverity,
            ThreatCategory,
            ThreatModel,
        )

        ctx = RiskContext(context_id="c", system_name="s", intended_purpose="p")
        threat = ThreatModel(
            threat_id="t",
            category=ThreatCategory.PROMPT_INJECTION,
            name="n",
            description="d",
            attack_vector="a",
            risk_score=0.9,
        )
        entry = RiskRegisterEntry(entry_id="e-2", risk_context=ctx, threats=[threat])
        result = entry.calculate_overall_risk()
        assert result == RiskSeverity.CRITICAL

    def test_calculate_overall_risk_with_effective_mitigations(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceStatus,
            RiskContext,
            RiskMitigation,
            RiskRegisterEntry,
            RiskSeverity,
            ThreatCategory,
            ThreatModel,
        )

        ctx = RiskContext(context_id="c", system_name="s", intended_purpose="p")
        threat = ThreatModel(
            threat_id="t",
            category=ThreatCategory.DATA_POISONING,
            name="n",
            description="d",
            attack_vector="a",
            risk_score=0.9,
        )
        mitigation = RiskMitigation(
            mitigation_id="m",
            threat_id="t",
            name="fix",
            description="d",
            implementation_status=ComplianceStatus.COMPLIANT,
            effectiveness=0.8,
        )
        entry = RiskRegisterEntry(
            entry_id="e-3",
            risk_context=ctx,
            threats=[threat],
            mitigations=[mitigation],
        )
        result = entry.calculate_overall_risk()
        # 0.9 * (1 - 0.8) = 0.18 -> LOW
        assert result == RiskSeverity.INFORMATIONAL

    def test_calculate_overall_risk_medium_threshold(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            RiskContext,
            RiskRegisterEntry,
            RiskSeverity,
            ThreatCategory,
            ThreatModel,
        )

        ctx = RiskContext(context_id="c", system_name="s", intended_purpose="p")
        threat = ThreatModel(
            threat_id="t",
            category=ThreatCategory.ADVERSARIAL_INPUT,
            name="n",
            description="d",
            attack_vector="a",
            risk_score=0.5,
        )
        entry = RiskRegisterEntry(entry_id="e-4", risk_context=ctx, threats=[threat])
        result = entry.calculate_overall_risk()
        assert result == RiskSeverity.MEDIUM

    def test_calculate_overall_risk_high_threshold(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            RiskContext,
            RiskRegisterEntry,
            RiskSeverity,
            ThreatCategory,
            ThreatModel,
        )

        ctx = RiskContext(context_id="c", system_name="s", intended_purpose="p")
        threat = ThreatModel(
            threat_id="t",
            category=ThreatCategory.PRIVACY_LEAKAGE,
            name="n",
            description="d",
            attack_vector="a",
            risk_score=0.7,
        )
        entry = RiskRegisterEntry(entry_id="e-5", risk_context=ctx, threats=[threat])
        result = entry.calculate_overall_risk()
        assert result == RiskSeverity.HIGH

    def test_calculate_overall_risk_low_threshold(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            RiskContext,
            RiskRegisterEntry,
            RiskSeverity,
            ThreatCategory,
            ThreatModel,
        )

        ctx = RiskContext(context_id="c", system_name="s", intended_purpose="p")
        threat = ThreatModel(
            threat_id="t",
            category=ThreatCategory.INSIDER_THREAT,
            name="n",
            description="d",
            attack_vector="a",
            risk_score=0.25,
        )
        entry = RiskRegisterEntry(entry_id="e-6", risk_context=ctx, threats=[threat])
        result = entry.calculate_overall_risk()
        assert result == RiskSeverity.LOW


class TestProcessingIntegrityControl:
    def test_construction_defaults(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import ProcessingIntegrityControl

        ctrl = ProcessingIntegrityControl(
            control_id="pi-1",
            control_name="Input Validation",
            description="d",
            criteria="PI1.1",
        )
        assert ctrl.testing_frequency == "quarterly"
        assert ctrl.completeness_check is False
        assert ctrl.accuracy_check is False
        assert ctrl.acgs2_components == []


class TestConfidentialityControl:
    def test_construction_defaults(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ConfidentialityControl,
            DataClassification,
        )

        ctrl = ConfidentialityControl(
            control_id="c-1",
            control_name="Encryption",
            description="d",
            criteria="C1.1",
        )
        assert ctrl.data_classification == DataClassification.CONFIDENTIAL
        assert ctrl.encryption_at_rest is False
        assert ctrl.encryption_in_transit is False


class TestAvailabilityControl:
    def test_construction_defaults(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import AvailabilityControl

        ctrl = AvailabilityControl(
            control_id="a-1",
            control_name="Uptime",
            description="d",
            criteria="A1.1",
        )
        assert ctrl.uptime_target == 99.9
        assert ctrl.recovery_time_objective == 60
        assert ctrl.recovery_point_objective == 15
        assert ctrl.disaster_recovery_plan is False

    def test_uptime_target_bounds(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import AvailabilityControl

        with pytest.raises(ValidationError):
            AvailabilityControl(
                control_id="a-x",
                control_name="x",
                description="x",
                criteria="x",
                uptime_target=101.0,
            )


class TestAuditEvidencePackage:
    def test_calculate_completeness_empty(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import AuditEvidencePackage

        pkg = AuditEvidencePackage(
            package_id="p-1",
            period_start=datetime.now(UTC),
            period_end=datetime.now(UTC),
        )
        score = pkg.calculate_completeness()
        assert score == 0.0

    def test_calculate_completeness_full(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            AuditEvidenceItem,
            AuditEvidencePackage,
        )

        pkg = AuditEvidencePackage(
            package_id="p-2",
            period_start=datetime.now(UTC),
            period_end=datetime.now(UTC),
            uptime_metrics={"api": 99.9},
            incident_log=[{"id": "i1"}],
            change_log=[{"id": "c1"}],
            access_reviews=[{"id": "a1"}],
            vulnerability_scans=[{"id": "v1"}],
            backup_test_results=[{"id": "b1"}],
            pi_controls_evidence={"pi1": []},
            c_controls_evidence={"c1": []},
            a_controls_evidence={"a1": []},
        )
        score = pkg.calculate_completeness()
        # base_score = (6/6)*50 = 50, pi=15, c=15, a=20 -> 100
        assert score == 100.0

    def test_calculate_completeness_partial(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import AuditEvidencePackage

        pkg = AuditEvidencePackage(
            package_id="p-3",
            period_start=datetime.now(UTC),
            period_end=datetime.now(UTC),
            uptime_metrics={"api": 99.5},
            incident_log=[{"id": "i1"}],
        )
        score = pkg.calculate_completeness()
        # base_score = (2/6)*50 ~ 16.67
        assert score == pytest.approx(16.67, abs=0.1)


class TestHighRiskClassification:
    def test_determine_risk_level_biometric(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import HighRiskClassification

        hrc = HighRiskClassification(
            classification_id="hrc-1",
            system_name="bio-sys",
            biometric_categorization=True,
        )
        level = hrc.determine_risk_level()
        assert level == "high"
        assert hrc.is_high_risk is True

    def test_determine_risk_level_critical_infra(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import HighRiskClassification

        hrc = HighRiskClassification(
            classification_id="hrc-2",
            system_name="infra-sys",
            critical_infrastructure=True,
        )
        level = hrc.determine_risk_level()
        assert level == "high"

    def test_determine_risk_level_significant_and_safety(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import HighRiskClassification

        hrc = HighRiskClassification(
            classification_id="hrc-3",
            system_name="safe-sys",
            significant_decisions=True,
            safety_component=True,
        )
        level = hrc.determine_risk_level()
        assert level == "high"

    def test_determine_risk_level_annex_iii(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import HighRiskClassification

        hrc = HighRiskClassification(
            classification_id="hrc-4",
            system_name="annex-sys",
            annex_iii_category="category-1",
        )
        level = hrc.determine_risk_level()
        assert level == "high"

    def test_determine_risk_level_limited(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import HighRiskClassification

        hrc = HighRiskClassification(
            classification_id="hrc-5",
            system_name="basic-sys",
        )
        level = hrc.determine_risk_level()
        assert level == "limited"
        assert hrc.is_high_risk is False

    def test_significant_decisions_without_safety_is_limited(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import HighRiskClassification

        hrc = HighRiskClassification(
            classification_id="hrc-6",
            system_name="decide-sys",
            significant_decisions=True,
            safety_component=False,
        )
        level = hrc.determine_risk_level()
        assert level == "limited"


class TestHumanOversightMechanism:
    def test_construction(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            HumanOversightLevel,
            HumanOversightMechanism,
        )

        m = HumanOversightMechanism(
            mechanism_id="ho-1",
            name="HITL Review",
            description="desc",
            oversight_level=HumanOversightLevel.HUMAN_IN_THE_LOOP,
        )
        assert m.is_compliant is False
        assert m.stop_mechanisms == []
        d = m.model_dump()
        assert d["oversight_level"] == "human_in_the_loop"


class TestTransparencyRequirement:
    def test_defaults(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import TransparencyRequirement

        tr = TransparencyRequirement(
            requirement_id="tr-1",
            description="Explain AI decisions",
        )
        assert tr.article_reference == "Article 13"
        assert tr.user_instructions_available is False
        assert tr.explanation_api_available is False


class TestTechnicalDocumentation:
    def test_model_dump_schema(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import TechnicalDocumentation

        doc = TechnicalDocumentation(
            doc_id="td-1",
            system_name="sys",
        )
        d = doc.model_dump()
        assert "doc_id" in d
        assert "system_name" in d
        assert "development_methods" in d
        schema = TechnicalDocumentation.model_json_schema()
        assert "properties" in schema


class TestComplianceViolation:
    def test_construction(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceFramework,
            ComplianceViolation,
            RiskSeverity,
        )

        v = ComplianceViolation(
            violation_id="v-1",
            framework=ComplianceFramework.GDPR,
            control_id="ctrl-1",
            severity=RiskSeverity.CRITICAL,
            description="Data breach",
        )
        assert v.framework == ComplianceFramework.GDPR
        assert v.remediation_actions == []


class TestComplianceAssessment:
    def test_calculate_score_zero_controls(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceAssessment,
            ComplianceFramework,
        )

        a = ComplianceAssessment(
            assessment_id="a-1",
            framework=ComplianceFramework.NIST_AI_RMF,
            system_name="sys",
        )
        assert a.calculate_score() == 0.0

    def test_calculate_score_all_compliant(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceAssessment,
            ComplianceFramework,
            ComplianceStatus,
        )

        a = ComplianceAssessment(
            assessment_id="a-2",
            framework=ComplianceFramework.SOC2_TYPE_II,
            system_name="sys",
            controls_assessed=10,
            controls_compliant=10,
        )
        score = a.calculate_score()
        assert score == 100.0
        assert a.overall_status == ComplianceStatus.COMPLIANT

    def test_calculate_score_partial(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceAssessment,
            ComplianceFramework,
            ComplianceStatus,
        )

        a = ComplianceAssessment(
            assessment_id="a-3",
            framework=ComplianceFramework.EU_AI_ACT,
            system_name="sys",
            controls_assessed=10,
            controls_compliant=5,
            controls_partial=4,
        )
        score = a.calculate_score()
        # (5*1.0 + 4*0.5) / 10 * 100 = 70
        assert score == 70.0
        assert a.overall_status == ComplianceStatus.PARTIAL

    def test_calculate_score_non_compliant(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceAssessment,
            ComplianceFramework,
            ComplianceStatus,
        )

        a = ComplianceAssessment(
            assessment_id="a-4",
            framework=ComplianceFramework.ISO_27001,
            system_name="sys",
            controls_assessed=10,
            controls_compliant=2,
            controls_non_compliant=8,
        )
        score = a.calculate_score()
        assert score == 20.0
        assert a.overall_status == ComplianceStatus.NON_COMPLIANT


class TestComplianceReport:
    def test_calculate_overall_score_no_assessments(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import ComplianceReport

        r = ComplianceReport(report_id="r-1")
        assert r.calculate_overall_score() == 0.0

    def test_calculate_overall_score_compliant(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceAssessment,
            ComplianceFramework,
            ComplianceReport,
            ComplianceStatus,
        )

        a1 = ComplianceAssessment(
            assessment_id="a1",
            framework=ComplianceFramework.GDPR,
            system_name="s",
            compliance_score=96.0,
        )
        a2 = ComplianceAssessment(
            assessment_id="a2",
            framework=ComplianceFramework.ISO_27001,
            system_name="s",
            compliance_score=98.0,
        )
        r = ComplianceReport(report_id="r-2", assessments=[a1, a2])
        score = r.calculate_overall_score()
        assert score == 97.0
        assert r.overall_status == ComplianceStatus.COMPLIANT

    def test_calculate_overall_score_non_compliant(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceAssessment,
            ComplianceFramework,
            ComplianceReport,
            ComplianceStatus,
        )

        a1 = ComplianceAssessment(
            assessment_id="a1",
            framework=ComplianceFramework.GDPR,
            system_name="s",
            compliance_score=30.0,
        )
        r = ComplianceReport(report_id="r-3", assessments=[a1])
        score = r.calculate_overall_score()
        assert score == 30.0
        assert r.overall_status == ComplianceStatus.NON_COMPLIANT


class TestDataClassificationEntry:
    def test_defaults(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import (
            DataClassification,
            DataClassificationEntry,
        )

        e = DataClassificationEntry(
            entry_id="dce-1",
            data_type="user_email",
            classification=DataClassification.PII,
        )
        assert e.encryption_required is True
        assert e.retention_days == 90
        assert e.audit_logging_required is True


class TestAuditEvidenceItem:
    def test_construction(self) -> None:
        from enhanced_agent_bus.compliance_layer.models import AuditEvidenceItem

        item = AuditEvidenceItem(
            evidence_id="ei-1",
            control_id="ctrl-1",
            evidence_type="log",
            description="system logs",
            source="splunk",
        )
        assert item.is_valid is True
        assert item.validity_period_days == 90
        assert item.reviewer is None


# ============================================================================
# api_models.py
# ============================================================================


class TestMessageTypeEnum:
    def test_all_values_exist(self) -> None:
        from enhanced_agent_bus.api_models import MessageTypeEnum

        assert MessageTypeEnum.COMMAND == "command"
        assert MessageTypeEnum.GOVERNANCE_REQUEST == "governance_request"
        assert MessageTypeEnum.CONSTITUTIONAL_VALIDATION == "constitutional_validation"
        assert MessageTypeEnum.SECURITY_ALERT == "security_alert"


class TestPriorityEnum:
    def test_values(self) -> None:
        from enhanced_agent_bus.api_models import PriorityEnum

        assert PriorityEnum.LOW == "low"
        assert PriorityEnum.NORMAL == "normal"
        assert PriorityEnum.CRITICAL == "critical"


class TestMessageStatusEnum:
    def test_values(self) -> None:
        from enhanced_agent_bus.api_models import MessageStatusEnum

        assert MessageStatusEnum.PENDING == "pending"
        assert MessageStatusEnum.COMPLETED == "completed"
        assert MessageStatusEnum.REJECTED == "rejected"


class TestMessageRequest:
    def test_valid_construction(self) -> None:
        from enhanced_agent_bus.api_models import MessageRequest

        req = MessageRequest(content="Hello", sender="agent-1")
        assert req.content == "Hello"
        assert req.message_type.value == "command"
        assert req.priority.value == "normal"

    def test_empty_content_rejected(self) -> None:
        from enhanced_agent_bus.api_models import MessageRequest

        with pytest.raises(ValidationError):
            MessageRequest(content="", sender="agent-1")

    def test_whitespace_only_content_rejected(self) -> None:
        from enhanced_agent_bus.api_models import MessageRequest

        with pytest.raises(ValidationError):
            MessageRequest(content="   ", sender="agent-1")

    def test_empty_sender_rejected(self) -> None:
        from enhanced_agent_bus.api_models import MessageRequest

        with pytest.raises(ValidationError):
            MessageRequest(content="hello", sender="")

    def test_model_dump(self) -> None:
        from enhanced_agent_bus.api_models import MessageRequest

        req = MessageRequest(
            content="test",
            sender="s1",
            recipient="r1",
            tenant_id="t1",
            session_id="sess-1",
        )
        d = req.model_dump()
        assert d["recipient"] == "r1"
        assert d["tenant_id"] == "t1"

    def test_json_schema(self) -> None:
        from enhanced_agent_bus.api_models import MessageRequest

        schema = MessageRequest.model_json_schema()
        assert "properties" in schema
        assert "content" in schema["properties"]


class TestMessageResponse:
    def test_construction(self) -> None:
        from enhanced_agent_bus.api_models import MessageResponse, MessageStatusEnum

        resp = MessageResponse(
            message_id="msg-1",
            status=MessageStatusEnum.ACCEPTED,
            timestamp="2024-01-01T00:00:00Z",
        )
        assert resp.message_id == "msg-1"
        assert resp.correlation_id is None


class TestValidationFinding:
    def test_construction(self) -> None:
        from enhanced_agent_bus.api_models import ValidationFinding

        f = ValidationFinding(
            severity="critical",
            code="MISSING_FIELD",
            message="Field X is required",
            field="x",
        )
        assert f.severity == "critical"
        assert f.field == "x"


class TestValidationResponse:
    def test_default_findings(self) -> None:
        from enhanced_agent_bus.api_models import ValidationResponse

        vr = ValidationResponse(valid=True)
        assert vr.valid is True
        assert "critical" in vr.findings
        assert "warnings" in vr.findings


class TestPolicyOverrideRequest:
    def test_construction(self) -> None:
        from enhanced_agent_bus.api_models import PolicyOverrideRequest

        por = PolicyOverrideRequest(
            policy_id="p-1",
            variables={"x": "int", "y": "string"},
            constraints=["x > 0"],
        )
        assert por.policy_id == "p-1"
        assert por.name is None


class TestSessionOverridesRequest:
    def test_construction(self) -> None:
        from enhanced_agent_bus.api_models import PolicyOverrideRequest, SessionOverridesRequest

        sor = SessionOverridesRequest(
            overrides=[
                PolicyOverrideRequest(
                    policy_id="p-1", variables={"x": "int"}, constraints=["x > 0"]
                )
            ]
        )
        assert len(sor.overrides) == 1


class TestHealthResponse:
    def test_construction(self) -> None:
        from enhanced_agent_bus.api_models import HealthResponse

        hr = HealthResponse(
            status="healthy",
            service="agent-bus",
            version="1.0.0",
            agent_bus_status="running",
        )
        assert hr.rate_limiting_enabled is False
        assert hr.circuit_breaker_enabled is False


class TestErrorResponse:
    def test_construction(self) -> None:
        from enhanced_agent_bus.api_models import ErrorResponse

        er = ErrorResponse(
            error="not_found",
            message="Resource not found",
            timestamp="2024-01-01T00:00:00Z",
        )
        assert er.details is None
        assert er.correlation_id is None


class TestStabilityMetricsResponse:
    def test_construction(self) -> None:
        from enhanced_agent_bus.api_models import StabilityMetricsResponse

        smr = StabilityMetricsResponse(
            spectral_radius_bound=0.95,
            divergence=0.01,
            max_weight=0.3,
            stability_hash="abc123",
            input_norm=1.0,
            output_norm=0.95,
        )
        assert smr.spectral_radius_bound == 0.95
        assert smr.timestamp  # auto-generated


class TestLatencyMetrics:
    def test_defaults(self) -> None:
        from enhanced_agent_bus.api_models import LatencyMetrics

        lm = LatencyMetrics()
        assert lm.p50_ms == 0.0
        assert lm.sample_count == 0
        assert lm.window_size == 1000


class TestLatencyTracker:
    @pytest.mark.asyncio
    async def test_get_metrics(self) -> None:
        from enhanced_agent_bus.api_models import LatencyTracker

        tracker = LatencyTracker()
        metrics = await tracker.get_metrics()
        assert metrics.p50_ms == 0.0

    @pytest.mark.asyncio
    async def test_get_total_messages(self) -> None:
        from enhanced_agent_bus.api_models import LatencyTracker

        tracker = LatencyTracker()
        total = await tracker.get_total_messages()
        assert total == 0


class TestServiceUnavailableResponse:
    def test_construction(self) -> None:
        from enhanced_agent_bus.api_models import ServiceUnavailableResponse

        sur = ServiceUnavailableResponse(
            status="unavailable",
            message="Maintenance in progress",
        )
        assert sur.status == "unavailable"


class TestValidationErrorResponse:
    def test_construction(self) -> None:
        from enhanced_agent_bus.api_models import ValidationErrorResponse

        ver = ValidationErrorResponse(
            message="Validation failed",
            findings={"errors": [{"code": "E1"}]},
        )
        assert ver.valid is False


# ============================================================================
# api_exceptions.py
# ============================================================================


class TestCreateErrorResponse:
    def test_basic_exception(self) -> None:
        from enhanced_agent_bus.api_exceptions import create_error_response

        exc = RuntimeError("something went wrong")
        result = create_error_response(exc, 500, request_id="req-123")
        assert result["status"] == "error"
        assert result["code"] == "INTERNAL_ERROR"
        assert result["message"] == "something went wrong"
        assert result["request_id"] == "req-123"
        assert "timestamp" in result

    def test_exception_with_code_attribute(self) -> None:
        from enhanced_agent_bus.api_exceptions import create_error_response

        exc = RuntimeError("oops")
        exc.code = "CUSTOM_CODE"  # type: ignore[attr-defined]
        exc.details = {"key": "val"}  # type: ignore[attr-defined]
        result = create_error_response(exc, 400)
        assert result["code"] == "CUSTOM_CODE"
        assert result["details"] == {"key": "val"}

    def test_no_request_id(self) -> None:
        from enhanced_agent_bus.api_exceptions import create_error_response

        result = create_error_response(ValueError("bad"), 400)
        assert result["request_id"] is None


class TestCorrelationIdVar:
    def test_default_value(self) -> None:
        from enhanced_agent_bus.api_exceptions import correlation_id_var

        assert correlation_id_var.get() == "unknown"

    def test_set_and_get(self) -> None:
        from enhanced_agent_bus.api_exceptions import correlation_id_var

        token = correlation_id_var.set("test-corr-id")
        try:
            assert correlation_id_var.get() == "test-corr-id"
        finally:
            correlation_id_var.reset(token)


# ============================================================================
# visual_studio/models.py
# ============================================================================


class TestNodeType:
    def test_values(self) -> None:
        from enhanced_agent_bus.visual_studio.models import NodeType

        assert NodeType.START == "start"
        assert NodeType.END == "end"
        assert NodeType.POLICY == "policy"
        assert NodeType.CONDITION == "condition"
        assert NodeType.ACTION == "action"


class TestExportFormat:
    def test_values(self) -> None:
        from enhanced_agent_bus.visual_studio.models import ExportFormat

        assert ExportFormat.JSON == "json"
        assert ExportFormat.REGO == "rego"
        assert ExportFormat.YAML == "yaml"


class TestWorkflowNode:
    def test_valid_construction(self) -> None:
        from enhanced_agent_bus.visual_studio.models import NodeType, WorkflowNode

        node = WorkflowNode(id="n1", type=NodeType.START)
        assert node.position == {"x": 0.0, "y": 0.0}
        assert node.selected is False
        assert node.dragging is False
        assert node.width is None

    def test_invalid_position_missing_x(self) -> None:
        from enhanced_agent_bus.visual_studio.models import NodeType, WorkflowNode

        with pytest.raises(ValidationError):
            WorkflowNode(id="n1", type=NodeType.START, position={"y": 0.0})

    def test_invalid_position_missing_y(self) -> None:
        from enhanced_agent_bus.visual_studio.models import NodeType, WorkflowNode

        with pytest.raises(ValidationError):
            WorkflowNode(id="n1", type=NodeType.START, position={"x": 0.0})

    def test_empty_id_rejected(self) -> None:
        from enhanced_agent_bus.visual_studio.models import NodeType, WorkflowNode

        with pytest.raises(ValidationError):
            WorkflowNode(id="", type=NodeType.START)

    def test_model_dump(self) -> None:
        from enhanced_agent_bus.visual_studio.models import NodeType, WorkflowNode

        node = WorkflowNode(id="n2", type=NodeType.POLICY, position={"x": 10.0, "y": 20.0})
        d = node.model_dump()
        assert d["type"] == "policy"
        assert d["position"]["x"] == 10.0


class TestWorkflowEdge:
    def test_construction(self) -> None:
        from enhanced_agent_bus.visual_studio.models import WorkflowEdge

        edge = WorkflowEdge(id="e1", source="n1", target="n2")
        assert edge.type == "smoothstep"
        assert edge.animated is False
        assert edge.label is None

    def test_empty_source_rejected(self) -> None:
        from enhanced_agent_bus.visual_studio.models import WorkflowEdge

        with pytest.raises(ValidationError):
            WorkflowEdge(id="e1", source="", target="n2")


class TestWorkflowDefinition:
    def test_construction(self) -> None:
        from enhanced_agent_bus.visual_studio.models import WorkflowDefinition

        wd = WorkflowDefinition(id="wf-1", name="Test Workflow")
        assert wd.version == "1.0.0"
        assert wd.is_active is True
        assert wd.nodes == []
        assert wd.edges == []
        assert wd.tags == []

    def test_empty_name_rejected(self) -> None:
        from enhanced_agent_bus.visual_studio.models import WorkflowDefinition

        with pytest.raises(ValidationError):
            WorkflowDefinition(id="wf-1", name="")


class TestWorkflowValidationResult:
    def test_construction(self) -> None:
        from enhanced_agent_bus.visual_studio.models import WorkflowValidationResult

        vr = WorkflowValidationResult(is_valid=True)
        assert vr.errors == []
        assert vr.warnings == []


class TestVisualStudioValidationResult:
    def test_defaults(self) -> None:
        from enhanced_agent_bus.visual_studio.models import VisualStudioValidationResult

        vr = VisualStudioValidationResult(message="Missing start node")
        assert vr.severity == "error"
        assert vr.field is None
        assert vr.node_id is None


class TestSimulationStep:
    def test_construction(self) -> None:
        from enhanced_agent_bus.visual_studio.models import NodeType, SimulationStep

        step = SimulationStep(
            step_number=1, node_id="n1", node_type=NodeType.START, status="completed"
        )
        assert step.input_data == {}
        assert step.execution_time_ms is None


class TestWorkflowSimulationResult:
    def test_construction(self) -> None:
        from enhanced_agent_bus.visual_studio.models import WorkflowSimulationResult

        wsr = WorkflowSimulationResult(workflow_id="wf-1", success=True)
        assert wsr.steps == []
        assert wsr.error_message is None


class TestWorkflowSummary:
    def test_construction(self) -> None:
        from enhanced_agent_bus.visual_studio.models import WorkflowSummary

        ws = WorkflowSummary(
            id="wf-1",
            name="Test",
            node_count=3,
            edge_count=2,
            updated_at=datetime.now(UTC),
            version="1.0.0",
            is_active=True,
        )
        assert ws.description is None


class TestWorkflowListResponse:
    def test_defaults(self) -> None:
        from enhanced_agent_bus.visual_studio.models import WorkflowListResponse

        wlr = WorkflowListResponse(workflows=[], total=0)
        assert wlr.page == 1
        assert wlr.page_size == 20


class TestWorkflowExportRequest:
    def test_defaults(self) -> None:
        from enhanced_agent_bus.visual_studio.models import ExportFormat, WorkflowExportRequest

        wer = WorkflowExportRequest()
        assert wer.format == ExportFormat.JSON
        assert wer.include_metadata is True


class TestWorkflowExportResult:
    def test_construction(self) -> None:
        from enhanced_agent_bus.visual_studio.models import WorkflowExportResult

        wer = WorkflowExportResult(
            workflow_id="wf-1",
            format="json",
            content='{"nodes":[]}',
            filename="wf-1.json",
        )
        assert wer.timestamp is not None


# ============================================================================
# policy_copilot/models.py
# ============================================================================


class TestPolicyEntityType:
    def test_values(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import PolicyEntityType

        assert PolicyEntityType.SUBJECT == "subject"
        assert PolicyEntityType.TIME == "time"
        assert PolicyEntityType.LOCATION == "location"
        assert len(PolicyEntityType) == 7


class TestLogicalOperator:
    def test_values(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import LogicalOperator

        assert LogicalOperator.AND == "and"
        assert LogicalOperator.OR == "or"
        assert LogicalOperator.NOT == "not"


class TestPolicyTemplateCategory:
    def test_values(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import PolicyTemplateCategory

        expected = {"compliance", "security", "access_control", "data_protection", "custom"}
        actual = {m.value for m in PolicyTemplateCategory}
        assert actual == expected


class TestPolicyEntity:
    def test_construction(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import PolicyEntity, PolicyEntityType

        pe = PolicyEntity(type=PolicyEntityType.ROLE, value="admin")
        assert pe.confidence == 1.0
        assert pe.modifiers == []

    def test_confidence_bounds(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import PolicyEntity, PolicyEntityType

        with pytest.raises(ValidationError):
            PolicyEntity(type=PolicyEntityType.SUBJECT, value="x", confidence=1.5)

    def test_empty_value_rejected(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import PolicyEntity, PolicyEntityType

        with pytest.raises(ValidationError):
            PolicyEntity(type=PolicyEntityType.ACTION, value="")


class TestPolicyCopilotTestCase:
    def test_construction(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import TestCase

        tc = TestCase(
            name="allow admin",
            input_data={"role": "admin"},
            expected_result=True,
        )
        assert tc.description is None


class TestPolicyResult:
    def test_construction(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import PolicyResult

        pr = PolicyResult(
            rego_code="package test\ndefault allow = false",
            explanation="A test policy",
        )
        assert pr.confidence == 0.0
        assert pr.policy_id  # auto-generated uuid
        assert pr.entities == []


class TestPolicyTemplate:
    def test_construction(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import (
            PolicyTemplate,
            PolicyTemplateCategory,
        )

        pt = PolicyTemplate(
            id="pt-1",
            name="RBAC Template",
            description="Role-based access control",
            category=PolicyTemplateCategory.ACCESS_CONTROL,
            rego_template="package rbac",
            example_usage="Use for RBAC",
        )
        assert pt.placeholders == []
        assert pt.tags == []


class TestCopilotRequest:
    def test_valid(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import CopilotRequest

        cr = CopilotRequest(description="Allow admin access to all resources")
        assert cr.template_id is None
        assert cr.tenant_id is None

    def test_short_description_rejected(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import CopilotRequest

        with pytest.raises(ValidationError):
            CopilotRequest(description="ab")

    def test_whitespace_description_normalized(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import CopilotRequest

        cr = CopilotRequest(description="   Allow admin access   ")
        assert cr.description == "Allow admin access"

    def test_whitespace_only_description_rejected(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import CopilotRequest

        with pytest.raises(ValidationError):
            CopilotRequest(description="   ")


class TestCopilotResponse:
    def test_defaults(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import CopilotResponse

        cr = CopilotResponse()
        assert cr.policy == ""
        assert cr.explanation == ""
        assert cr.confidence == 0.0
        assert cr.policy_id  # auto-generated


class TestExplainRequest:
    def test_valid(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import ExplainRequest

        er = ExplainRequest(policy="package test")
        assert er.detail_level == "detailed"

    def test_invalid_detail_level(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import ExplainRequest

        with pytest.raises(ValidationError):
            ExplainRequest(policy="package test", detail_level="verbose")

    def test_all_valid_detail_levels(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import ExplainRequest

        for level in ("simple", "detailed", "technical"):
            er = ExplainRequest(policy="pkg", detail_level=level)
            assert er.detail_level == level


class TestRiskAssessment:
    def test_valid(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import RiskAssessment

        ra = RiskAssessment(
            severity="high",
            category="access_control",
            description="Overly permissive",
        )
        assert ra.mitigation is None

    def test_invalid_severity(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import RiskAssessment

        with pytest.raises(ValidationError):
            RiskAssessment(severity="extreme", category="c", description="d")


class TestExplainResponse:
    def test_defaults(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import ExplainResponse

        er = ExplainResponse(explanation="This policy does X")
        assert er.risks == []
        assert er.complexity_score == 0.0


class TestImproveRequest:
    def test_valid(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import ImproveRequest

        ir = ImproveRequest(policy="package test", feedback="Make stricter")
        assert ir.instruction == "custom"

    def test_invalid_instruction(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import ImproveRequest

        with pytest.raises(ValidationError):
            ImproveRequest(policy="pkg", feedback="f", instruction="invalid")

    def test_valid_instructions(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import ImproveRequest

        for instr in ("stricter", "permissive", "custom"):
            ir = ImproveRequest(policy="pkg", feedback="f", instruction=instr)
            assert ir.instruction == instr


class TestImproveResponse:
    def test_defaults(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import ImproveResponse

        ir = ImproveResponse(improved_policy="package improved")
        assert ir.explanation == ""
        assert ir.changes_made == []


class TestTestRequest:
    def test_construction(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import TestRequest

        tr = TestRequest(policy="package test", test_input={"role": "admin"})
        assert tr.tenant_id is None


class TestTestResult:
    def test_defaults(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import TestResult

        tr = TestResult(allowed=True)
        assert tr.decision_path == []
        assert tr.execution_time_ms == 0.0


class TestPolicyCopilotValidationResult:
    def test_defaults(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import ValidationResult

        vr = ValidationResult(valid=True)
        assert vr.errors == []
        assert vr.warnings == []
        assert vr.syntax_check is False
        assert vr.best_practices == []


class TestChatMessage:
    def test_valid_roles(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import ChatMessage

        for role in ("user", "assistant", "system"):
            cm = ChatMessage(role=role, content="hello")
            assert cm.role == role

    def test_invalid_role(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import ChatMessage

        with pytest.raises(ValidationError):
            ChatMessage(role="admin", content="hello")


class TestChatHistory:
    def test_add_message(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import ChatHistory

        ch = ChatHistory()
        assert ch.messages == []
        ch.add_message("user", "Hello")
        assert len(ch.messages) == 1
        assert ch.messages[0].role == "user"
        assert ch.messages[0].content == "Hello"

    def test_add_message_with_metadata(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import ChatHistory

        ch = ChatHistory()
        ch.add_message("assistant", "Hi", metadata={"source": "copilot"})
        assert ch.messages[0].metadata == {"source": "copilot"}

    def test_updated_at_changes(self) -> None:
        from enhanced_agent_bus.policy_copilot.models import ChatHistory

        ch = ChatHistory()
        original = ch.updated_at
        ch.add_message("user", "test")
        assert ch.updated_at >= original


# ============================================================================
# routes/sessions/models.py
# ============================================================================


class TestCreateSessionRequest:
    def test_defaults(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import CreateSessionRequest

        req = CreateSessionRequest()
        assert req.risk_level == "medium"
        assert req.require_human_approval is False
        assert req.enabled_policies == []
        assert req.disabled_policies == []

    def test_valid_risk_levels(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import CreateSessionRequest

        for level in ("low", "medium", "high", "critical"):
            req = CreateSessionRequest(risk_level=level)
            assert req.risk_level == level

    def test_invalid_risk_level(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import CreateSessionRequest

        with pytest.raises(ValidationError):
            CreateSessionRequest(risk_level="extreme")

    def test_risk_level_case_insensitive(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import CreateSessionRequest

        req = CreateSessionRequest(risk_level="HIGH")
        assert req.risk_level == "high"

    def test_valid_automation_levels(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import CreateSessionRequest

        for level in ("full", "partial", "none"):
            req = CreateSessionRequest(max_automation_level=level)
            assert req.max_automation_level == level

    def test_invalid_automation_level(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import CreateSessionRequest

        with pytest.raises(ValidationError):
            CreateSessionRequest(max_automation_level="auto")

    def test_none_automation_level(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import CreateSessionRequest

        req = CreateSessionRequest()
        assert req.max_automation_level is None

    def test_ttl_bounds(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import CreateSessionRequest

        with pytest.raises(ValidationError):
            CreateSessionRequest(ttl_seconds=10)  # below 60

        with pytest.raises(ValidationError):
            CreateSessionRequest(ttl_seconds=100000)  # above 86400


class TestUpdateGovernanceRequest:
    def test_all_none_defaults(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import UpdateGovernanceRequest

        req = UpdateGovernanceRequest()
        assert req.risk_level is None
        assert req.policy_id is None
        assert req.require_human_approval is None

    def test_valid_risk_level(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import UpdateGovernanceRequest

        req = UpdateGovernanceRequest(risk_level="high")
        assert req.risk_level == "high"

    def test_invalid_risk_level(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import UpdateGovernanceRequest

        with pytest.raises(ValidationError):
            UpdateGovernanceRequest(risk_level="extreme")

    def test_none_risk_level_passes(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import UpdateGovernanceRequest

        req = UpdateGovernanceRequest(risk_level=None)
        assert req.risk_level is None

    def test_extend_ttl_bounds(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import UpdateGovernanceRequest

        with pytest.raises(ValidationError):
            UpdateGovernanceRequest(extend_ttl_seconds=10)


class TestPolicySelectionRequest:
    def test_defaults(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import PolicySelectionRequest

        req = PolicySelectionRequest()
        assert req.include_disabled is False
        assert req.include_all_candidates is False
        assert req.risk_level_override is None

    def test_valid_risk_override(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import PolicySelectionRequest

        req = PolicySelectionRequest(risk_level_override="critical")
        assert req.risk_level_override == "critical"

    def test_invalid_risk_override(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import PolicySelectionRequest

        with pytest.raises(ValidationError):
            PolicySelectionRequest(risk_level_override="extreme")


class TestSessionResponse:
    def test_construction(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import SessionResponse

        resp = SessionResponse(
            session_id="s-1",
            tenant_id="t-1",
            risk_level="medium",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        assert resp.require_human_approval is False
        assert resp.ttl_remaining_seconds is None


class TestSessionListResponse:
    def test_defaults(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import SessionListResponse

        slr = SessionListResponse()
        assert slr.total_count == 0
        assert slr.page == 1
        assert slr.page_size == 20


class TestSessionMetricsResponse:
    def test_defaults(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import SessionMetricsResponse

        smr = SessionMetricsResponse()
        assert smr.cache_hits == 0
        assert smr.cache_hit_rate == 0.0
        assert smr.creates == 0


class TestSelectedPolicy:
    def test_construction(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import SelectedPolicy

        sp = SelectedPolicy(
            policy_id="p-1",
            name="Strict Policy",
            source="session",
            reasoning="Explicit override",
        )
        assert sp.priority == 0
        assert sp.version is None


class TestPolicySelectionResponse:
    def test_construction(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import PolicySelectionResponse

        psr = PolicySelectionResponse(
            session_id="s-1",
            tenant_id="t-1",
            risk_level="high",
            timestamp="2024-01-01T00:00:00Z",
        )
        assert psr.selected_policy is None
        assert psr.candidate_policies == []


class TestSessionErrorResponse:
    def test_construction(self) -> None:
        from enhanced_agent_bus.routes.sessions.models import ErrorResponse

        er = ErrorResponse(
            error="not_found",
            message="Session not found",
            timestamp="2024-01-01T00:00:00Z",
        )
        assert er.details is None


# ============================================================================
# enterprise_sso/enterprise_sso_infra/models.py
# ============================================================================


class TestProtocolValidationResult:
    def test_success(self) -> None:
        from enhanced_agent_bus.enterprise_sso.enterprise_sso_infra.models import (
            ProtocolValidationResult,
        )

        pvr = ProtocolValidationResult(
            success=True,
            user_id="u-1",
            email="user@example.com",
            display_name="Test User",
            groups=["admin"],
        )
        assert pvr.success is True
        assert pvr.error is None

    def test_failure(self) -> None:
        from enhanced_agent_bus.enterprise_sso.enterprise_sso_infra.models import (
            ProtocolValidationResult,
        )

        pvr = ProtocolValidationResult(
            success=False,
            error="Invalid SAML response",
            error_code="SAML_INVALID",
        )
        assert pvr.success is False
        assert pvr.user_id is None

    def test_to_dict(self) -> None:
        from enhanced_agent_bus.enterprise_sso.enterprise_sso_infra.models import (
            ProtocolValidationResult,
        )

        pvr = ProtocolValidationResult(
            success=True,
            user_id="u-1",
            email="u@e.com",
            display_name="U",
            groups=["g1"],
        )
        d = pvr.to_dict()
        assert d["success"] is True
        assert d["user_id"] == "u-1"
        assert d["groups"] == ["g1"]
        assert "error" in d
        assert "error_code" in d

    def test_defaults(self) -> None:
        from enhanced_agent_bus.enterprise_sso.enterprise_sso_infra.models import (
            ProtocolValidationResult,
        )

        pvr = ProtocolValidationResult(success=True)
        assert pvr.groups == []
        assert pvr.attributes == {}
        assert pvr.raw_response is None


class TestAuthorizationRequest:
    def test_construction(self) -> None:
        from enhanced_agent_bus.enterprise_sso.enterprise_sso_infra.models import (
            AuthorizationRequest,
        )

        ar = AuthorizationRequest(
            authorization_url="https://idp.example.com/authorize",
            state="random-state",
            nonce="random-nonce",
        )
        assert ar.code_verifier is None
        assert ar.code_challenge is None
        assert isinstance(ar.expires_at, datetime)

    def test_is_expired_false(self) -> None:
        from enhanced_agent_bus.enterprise_sso.enterprise_sso_infra.models import (
            AuthorizationRequest,
        )

        ar = AuthorizationRequest(
            authorization_url="https://idp.example.com/authorize",
            state="s",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        assert ar.is_expired() is False

    def test_is_expired_true(self) -> None:
        from enhanced_agent_bus.enterprise_sso.enterprise_sso_infra.models import (
            AuthorizationRequest,
        )

        ar = AuthorizationRequest(
            authorization_url="https://idp.example.com/authorize",
            state="s",
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        assert ar.is_expired() is True


class TestLogoutRequest:
    def test_construction(self) -> None:
        from enhanced_agent_bus.enterprise_sso.enterprise_sso_infra.models import LogoutRequest

        lr = LogoutRequest(
            logout_url="https://idp.example.com/logout",
            request_id="req-1",
            name_id="user@example.com",
        )
        assert lr.session_index is None

    def test_is_expired(self) -> None:
        from enhanced_agent_bus.enterprise_sso.enterprise_sso_infra.models import LogoutRequest

        lr = LogoutRequest(
            logout_url="u",
            request_id="r",
            name_id="n",
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        assert lr.is_expired() is True


class TestLogoutRequestResult:
    def test_construction(self) -> None:
        from enhanced_agent_bus.enterprise_sso.enterprise_sso_infra.models import (
            LogoutRequestResult,
        )

        lrr = LogoutRequestResult(success=True, name_id="user@example.com")
        assert lrr.session_index is None
        assert lrr.error is None


class TestLogoutResult:
    def test_construction(self) -> None:
        from enhanced_agent_bus.enterprise_sso.enterprise_sso_infra.models import LogoutResult

        lr = LogoutResult(success=False, error="Timeout", error_code="TIMEOUT")
        assert lr.success is False


# ============================================================================
# exceptions/ hierarchy
# ============================================================================


class TestExceptionBase:
    def test_agent_bus_error_basic(self) -> None:
        from enhanced_agent_bus.exceptions import AgentBusError

        exc = AgentBusError("test error")
        assert "test error" in str(exc)
        assert exc.message == "test error"

    def test_agent_bus_error_to_dict(self) -> None:
        from enhanced_agent_bus.exceptions import AgentBusError

        exc = AgentBusError("oops", details={"key": "val"})
        d = exc.to_dict()
        assert d["error_type"] == "AgentBusError"
        assert d["message"] == "oops"
        assert "key" in d.get("details", {})

    def test_inheritance_chain(self) -> None:
        from enhanced_agent_bus.exceptions import (
            AgentBusError,
            AgentError,
            BusOperationError,
            ConstitutionalError,
            MACIError,
            MessageError,
            PolicyError,
        )

        for cls in (
            ConstitutionalError,
            MessageError,
            AgentError,
            PolicyError,
            MACIError,
            BusOperationError,
        ):
            exc = cls("test")
            assert isinstance(exc, AgentBusError)


class TestAgentExceptions:
    def test_agent_not_registered(self) -> None:
        from enhanced_agent_bus.exceptions import AgentNotRegisteredError

        exc = AgentNotRegisteredError("agent-1", operation="send_message")
        assert "agent-1" in str(exc)
        assert "send_message" in str(exc)
        assert exc.agent_id == "agent-1"

    def test_agent_not_registered_no_operation(self) -> None:
        from enhanced_agent_bus.exceptions import AgentNotRegisteredError

        exc = AgentNotRegisteredError("agent-2")
        assert "agent-2" in str(exc)
        assert exc.operation is None

    def test_agent_already_registered(self) -> None:
        from enhanced_agent_bus.exceptions import AgentAlreadyRegisteredError

        exc = AgentAlreadyRegisteredError("agent-1")
        assert exc.agent_id == "agent-1"

    def test_agent_capability_error(self) -> None:
        from enhanced_agent_bus.exceptions import AgentCapabilityError

        exc = AgentCapabilityError(
            "agent-1",
            required_capabilities=["governance", "audit"],
            available_capabilities=["audit"],
        )
        assert "governance" in str(exc)
        d = exc.to_dict()
        details = d.get("details", {})
        assert "governance" in details.get("missing_capabilities", [])


class TestConstitutionalExceptions:
    def test_hash_mismatch(self) -> None:
        from enhanced_agent_bus.exceptions import ConstitutionalHashMismatchError

        exc = ConstitutionalHashMismatchError(
            expected_hash="608508a9bd224290",
            actual_hash="0000000000000000",
            context="startup",
        )
        assert exc.expected_hash == "608508a9bd224290"
        assert exc.actual_hash == "0000000000000000"
        assert "startup" in str(exc)

    def test_hash_mismatch_sanitization(self) -> None:
        from enhanced_agent_bus.exceptions import ConstitutionalHashMismatchError

        exc = ConstitutionalHashMismatchError(
            expected_hash="abcdefghijklmnop",
            actual_hash="1234567890abcdef",
        )
        d = exc.to_dict()
        details = d.get("details", {})
        # Sanitized: only first 8 chars visible
        assert details["expected_hash_prefix"] == "abcdefgh..."
        assert details["actual_hash_prefix"] == "12345678..."

    def test_constitutional_validation_error(self) -> None:
        from enhanced_agent_bus.exceptions import ConstitutionalValidationError

        exc = ConstitutionalValidationError(
            validation_errors=["rule_1 violated", "rule_2 violated"],
            agent_id="agent-1",
            action_type="send",
        )
        assert exc.validation_errors == ["rule_1 violated", "rule_2 violated"]
        assert "rule_1 violated" in str(exc)


class TestMACIExceptions:
    def test_role_violation(self) -> None:
        from enhanced_agent_bus.exceptions import MACIRoleViolationError

        exc = MACIRoleViolationError(
            agent_id="agent-1",
            role="proposer",
            action="validate",
            allowed_roles=["validator"],
        )
        assert exc.agent_id == "agent-1"
        assert "validator" in str(exc)

    def test_role_violation_no_allowed(self) -> None:
        from enhanced_agent_bus.exceptions import MACIRoleViolationError

        exc = MACIRoleViolationError(agent_id="a", role="r", action="act")
        assert exc.allowed_roles == []

    def test_self_validation_error(self) -> None:
        from enhanced_agent_bus.exceptions import MACISelfValidationError

        exc = MACISelfValidationError("agent-1", "validate", "output-123")
        assert "Gödel" in str(exc) or "Godel" in str(exc) or "godel" in str(exc).lower()
        assert exc.output_id == "output-123"

    def test_self_validation_no_output(self) -> None:
        from enhanced_agent_bus.exceptions import MACISelfValidationError

        exc = MACISelfValidationError("a", "validate")
        assert exc.output_id is None

    def test_cross_role_validation(self) -> None:
        from enhanced_agent_bus.exceptions import MACICrossRoleValidationError

        exc = MACICrossRoleValidationError(
            validator_agent="v1",
            validator_role="proposer",
            target_agent="t1",
            target_role="proposer",
            reason="same role",
        )
        assert exc.validator_agent == "v1"
        assert exc.reason == "same role"

    def test_role_not_assigned(self) -> None:
        from enhanced_agent_bus.exceptions import MACIRoleNotAssignedError

        exc = MACIRoleNotAssignedError("agent-1", "validate")
        assert exc.agent_id == "agent-1"
        assert exc.operation == "validate"


class TestMessagingExceptions:
    def test_message_validation_error(self) -> None:
        from enhanced_agent_bus.exceptions import MessageValidationError

        exc = MessageValidationError(
            message_id="msg-1",
            errors=["field_x missing", "field_y invalid"],
            warnings=["deprecated field used"],
        )
        assert exc.message_id == "msg-1"
        assert len(exc.errors) == 2
        assert len(exc.warnings) == 1

    def test_message_validation_no_warnings(self) -> None:
        from enhanced_agent_bus.exceptions import MessageValidationError

        exc = MessageValidationError("msg-2", errors=["e1"])
        assert exc.warnings == []

    def test_message_delivery_error(self) -> None:
        from enhanced_agent_bus.exceptions import MessageDeliveryError

        exc = MessageDeliveryError("msg-1", "agent-2", "agent offline")
        assert exc.target_agent == "agent-2"

    def test_message_timeout(self) -> None:
        from enhanced_agent_bus.exceptions import MessageTimeoutError

        exc = MessageTimeoutError("msg-1", 5000, operation="governance_check")
        assert exc.message_id == "msg-1"
        assert exc.timeout_ms == 5000
        assert "governance_check" in str(exc)

    def test_message_timeout_no_operation(self) -> None:
        from enhanced_agent_bus.exceptions import MessageTimeoutError

        exc = MessageTimeoutError("msg-2", 3000)
        assert exc.operation is None
        assert "3000ms" in str(exc)

    def test_message_routing_error(self) -> None:
        from enhanced_agent_bus.exceptions import MessageRoutingError

        exc = MessageRoutingError("msg-1", "a1", "a2", "no route")
        assert exc.source_agent == "a1"
        assert exc.target_agent == "a2"

    def test_rate_limit_exceeded(self) -> None:
        from enhanced_agent_bus.exceptions import RateLimitExceeded

        exc = RateLimitExceeded("agent-1", limit=100, window_seconds=60, retry_after_ms=5000)
        assert exc.agent_id == "agent-1"
        assert exc.retry_after_ms == 5000
        assert "retry after" in str(exc).lower()

    def test_rate_limit_exceeded_no_retry(self) -> None:
        from enhanced_agent_bus.exceptions import RateLimitExceeded

        exc = RateLimitExceeded("agent-2", limit=50, window_seconds=30)
        assert exc.retry_after_ms is None


class TestOperationsExceptions:
    def test_bus_not_started(self) -> None:
        from enhanced_agent_bus.exceptions import BusNotStartedError

        exc = BusNotStartedError("send_message")
        assert exc.operation == "send_message"

    def test_bus_already_started(self) -> None:
        from enhanced_agent_bus.exceptions import BusAlreadyStartedError

        exc = BusAlreadyStartedError()
        assert "already running" in str(exc)

    def test_handler_execution_error(self) -> None:
        from enhanced_agent_bus.exceptions import HandlerExecutionError

        original = ValueError("bad value")
        exc = HandlerExecutionError("my_handler", "msg-1", original)
        assert exc.handler_name == "my_handler"
        assert exc.original_error is original

    def test_configuration_error(self) -> None:
        from enhanced_agent_bus.exceptions import ConfigurationError

        exc = ConfigurationError("REDIS_URL", "not set")
        assert exc.config_key == "REDIS_URL"
        assert exc.reason == "not set"

    def test_alignment_violation_with_score(self) -> None:
        from enhanced_agent_bus.exceptions import AlignmentViolationError

        exc = AlignmentViolationError("prompt injection", alignment_score=0.2, agent_id="a1")
        assert exc.alignment_score == 0.2
        assert "0.2" in str(exc)

    def test_alignment_violation_without_score(self) -> None:
        from enhanced_agent_bus.exceptions import AlignmentViolationError

        exc = AlignmentViolationError("bad content")
        assert exc.alignment_score is None

    def test_authentication_error(self) -> None:
        from enhanced_agent_bus.exceptions import AuthenticationError

        exc = AuthenticationError("agent-1", "invalid token")
        assert exc.agent_id == "agent-1"

    def test_authorization_error(self) -> None:
        from enhanced_agent_bus.exceptions import AuthorizationError

        exc = AuthorizationError("agent-1", "delete", "insufficient permissions")
        assert exc.action == "delete"

    def test_dependency_error(self) -> None:
        from enhanced_agent_bus.exceptions import DependencyError

        exc = DependencyError("redis", "connection refused")
        assert exc.dependency_name == "redis"

    def test_deliberation_timeout(self) -> None:
        from enhanced_agent_bus.exceptions import DeliberationTimeoutError

        exc = DeliberationTimeoutError(
            "dec-1", timeout_seconds=30, pending_reviews=2, pending_signatures=1
        )
        assert exc.decision_id == "dec-1"
        assert exc.pending_reviews == 2

    def test_signature_collection_error(self) -> None:
        from enhanced_agent_bus.exceptions import SignatureCollectionError

        exc = SignatureCollectionError(
            "dec-1",
            required_signers=["a", "b", "c"],
            collected_signers=["a"],
            reason="timeout",
        )
        assert exc.decision_id == "dec-1"
        d = exc.to_dict()
        details = d.get("details", {})
        assert set(details.get("missing_signers", [])) == {"b", "c"}

    def test_review_consensus_error(self) -> None:
        from enhanced_agent_bus.exceptions import ReviewConsensusError

        exc = ReviewConsensusError("dec-1", approval_count=1, rejection_count=2, escalation_count=0)
        assert exc.rejection_count == 2

    def test_governance_error(self) -> None:
        from enhanced_agent_bus.exceptions import GovernanceError

        exc = GovernanceError("governance failed", details={"policy": "p1"})
        assert "governance failed" in str(exc)

    def test_impact_assessment_error(self) -> None:
        from enhanced_agent_bus.exceptions import ImpactAssessmentError

        exc = ImpactAssessmentError("security", "insufficient data")
        assert exc.assessment_type == "security"

    def test_checkpoint_error(self) -> None:
        from enhanced_agent_bus.exceptions import CheckpointError

        exc = CheckpointError("checkpoint failed")
        assert "checkpoint failed" in str(exc)

    def test_interrupt_error(self) -> None:
        from enhanced_agent_bus.exceptions import InterruptError

        exc = InterruptError("user intervention")
        assert "user intervention" in str(exc)

    def test_timeout_error(self) -> None:
        from enhanced_agent_bus.exceptions import TimeoutError

        exc = TimeoutError("operation timed out")
        assert "timed out" in str(exc)


class TestPolicyExceptions:
    def test_policy_evaluation_error(self) -> None:
        from enhanced_agent_bus.exceptions import PolicyEvaluationError

        exc = PolicyEvaluationError("data.policy.allow", "syntax error")
        assert exc.policy_path == "data.policy.allow"
        assert exc.reason == "syntax error"

    def test_policy_evaluation_with_input(self) -> None:
        from enhanced_agent_bus.exceptions import PolicyEvaluationError

        exc = PolicyEvaluationError("path", "err", input_data={"role": "admin"})
        assert exc.input_data == {"role": "admin"}

    def test_policy_not_found(self) -> None:
        from enhanced_agent_bus.exceptions import PolicyNotFoundError

        exc = PolicyNotFoundError("data.missing.policy")
        assert exc.policy_path == "data.missing.policy"

    def test_opa_connection_error(self) -> None:
        from enhanced_agent_bus.exceptions import OPAConnectionError

        exc = OPAConnectionError("http://localhost:8181", "connection refused")
        assert exc.opa_url == "http://localhost:8181"
        assert exc.reason == "connection refused"

    def test_opa_not_initialized(self) -> None:
        from enhanced_agent_bus.exceptions import OPANotInitializedError

        exc = OPANotInitializedError("evaluate")
        assert exc.operation == "evaluate"


class TestExceptionBackwardCompat:
    def test_constitutional_violation_alias(self) -> None:
        from enhanced_agent_bus.exceptions import (
            ConstitutionalValidationError,
            ConstitutionalViolationError,
        )

        assert ConstitutionalViolationError is ConstitutionalValidationError
