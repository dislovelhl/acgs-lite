# Constitutional Hash: 608508a9bd224290
"""
Comprehensive test suite for compliance_layer/models.py.

Targets ≥90% coverage of all classes, enums, Pydantic models,
validators, and methods defined in the module.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone

import pytest

from compliance_layer.models import (
    AuditEvidenceItem,
    AuditEvidencePackage,
    AvailabilityControl,
    ComplianceAssessment,
    ComplianceFramework,
    ComplianceReport,
    ComplianceStatus,
    ComplianceViolation,
    ConfidentialityControl,
    DataClassification,
    DataClassificationEntry,
    HighRiskClassification,
    HumanOversightLevel,
    HumanOversightMechanism,
    ProcessingIntegrityControl,
    RiskContext,
    RiskMitigation,
    RiskRegisterEntry,
    RiskSeverity,
    TechnicalDocumentation,
    ThreatCategory,
    ThreatModel,
    TransparencyRequirement,
)
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestComplianceFramework:
    def test_all_values(self):
        assert ComplianceFramework.NIST_AI_RMF == "nist_ai_rmf"
        assert ComplianceFramework.SOC2_TYPE_II == "soc2_type_ii"
        assert ComplianceFramework.EU_AI_ACT == "eu_ai_act"
        assert ComplianceFramework.ISO_27001 == "iso_27001"
        assert ComplianceFramework.GDPR == "gdpr"

    def test_str_subclass(self):
        assert isinstance(ComplianceFramework.GDPR, str)

    def test_membership(self):
        assert "gdpr" in [f.value for f in ComplianceFramework]

    def test_count(self):
        assert len(ComplianceFramework) == 5


class TestComplianceStatus:
    def test_all_values(self):
        assert ComplianceStatus.COMPLIANT == "compliant"
        assert ComplianceStatus.NON_COMPLIANT == "non_compliant"
        assert ComplianceStatus.PARTIAL == "partial"
        assert ComplianceStatus.NOT_ASSESSED == "not_assessed"
        assert ComplianceStatus.IN_PROGRESS == "in_progress"
        assert ComplianceStatus.EXEMPT == "exempt"

    def test_str_subclass(self):
        assert isinstance(ComplianceStatus.COMPLIANT, str)

    def test_count(self):
        assert len(ComplianceStatus) == 6


class TestRiskSeverity:
    def test_all_values(self):
        assert RiskSeverity.CRITICAL == "critical"
        assert RiskSeverity.HIGH == "high"
        assert RiskSeverity.MEDIUM == "medium"
        assert RiskSeverity.LOW == "low"
        assert RiskSeverity.INFORMATIONAL == "informational"

    def test_str_subclass(self):
        assert isinstance(RiskSeverity.HIGH, str)

    def test_count(self):
        assert len(RiskSeverity) == 5


class TestThreatCategory:
    def test_all_values(self):
        assert ThreatCategory.DATA_POISONING == "data_poisoning"
        assert ThreatCategory.MODEL_EXTRACTION == "model_extraction"
        assert ThreatCategory.ADVERSARIAL_INPUT == "adversarial_input"
        assert ThreatCategory.PROMPT_INJECTION == "prompt_injection"
        assert ThreatCategory.PRIVACY_LEAKAGE == "privacy_leakage"
        assert ThreatCategory.SUPPLY_CHAIN == "supply_chain"
        assert ThreatCategory.INSIDER_THREAT == "insider_threat"
        assert ThreatCategory.CONSTITUTIONAL_BYPASS == "constitutional_bypass"
        assert ThreatCategory.GOVERNANCE_EVASION == "governance_evasion"

    def test_count(self):
        assert len(ThreatCategory) == 9


class TestDataClassification:
    def test_all_values(self):
        assert DataClassification.PUBLIC == "public"
        assert DataClassification.INTERNAL == "internal"
        assert DataClassification.CONFIDENTIAL == "confidential"
        assert DataClassification.RESTRICTED == "restricted"
        assert DataClassification.PII == "pii"
        assert DataClassification.PHI == "phi"

    def test_count(self):
        assert len(DataClassification) == 6


class TestHumanOversightLevel:
    def test_all_values(self):
        assert HumanOversightLevel.HUMAN_IN_THE_LOOP == "human_in_the_loop"
        assert HumanOversightLevel.HUMAN_ON_THE_LOOP == "human_on_the_loop"
        assert HumanOversightLevel.HUMAN_IN_COMMAND == "human_in_command"
        assert HumanOversightLevel.FULLY_AUTOMATED == "fully_automated"

    def test_count(self):
        assert len(HumanOversightLevel) == 4


# ---------------------------------------------------------------------------
# RiskContext
# ---------------------------------------------------------------------------


class TestRiskContext:
    def _make(self, **kwargs):
        defaults = dict(
            context_id="ctx-001",
            system_name="ACGS-2",
            intended_purpose="AI governance",
        )
        defaults.update(kwargs)
        return RiskContext(**defaults)

    def test_minimal_creation(self):
        ctx = self._make()
        assert ctx.context_id == "ctx-001"
        assert ctx.system_name == "ACGS-2"
        assert ctx.intended_purpose == "AI governance"

    def test_defaults(self):
        ctx = self._make()
        assert ctx.system_version == "1.0.0"
        assert ctx.deployment_environment == "production"
        assert ctx.user_population == "enterprise"
        assert ctx.data_types == []
        assert ctx.risk_tolerance == RiskSeverity.MEDIUM
        assert ctx.regulatory_requirements == []
        assert ctx.stakeholders == []
        assert ctx.constitutional_hash == CONSTITUTIONAL_HASH

    def test_created_at_is_timezone_aware(self):
        ctx = self._make()
        assert ctx.created_at.tzinfo is not None

    def test_override_defaults(self):
        ctx = self._make(
            system_version="2.0.0",
            deployment_environment="staging",
            user_population="consumer",
            data_types=[DataClassification.PII],
            risk_tolerance=RiskSeverity.HIGH,
            regulatory_requirements=[ComplianceFramework.GDPR],
            stakeholders=["alice", "bob"],
        )
        assert ctx.system_version == "2.0.0"
        assert ctx.deployment_environment == "staging"
        assert DataClassification.PII in ctx.data_types
        assert ctx.risk_tolerance == RiskSeverity.HIGH
        assert ComplianceFramework.GDPR in ctx.regulatory_requirements
        assert "alice" in ctx.stakeholders


# ---------------------------------------------------------------------------
# ThreatModel
# ---------------------------------------------------------------------------


class TestThreatModel:
    def _make(self, **kwargs):
        defaults = dict(
            threat_id="threat-001",
            category=ThreatCategory.PROMPT_INJECTION,
            name="Prompt Injection Attack",
            description="Attacker injects malicious instructions",
            attack_vector="user input",
        )
        defaults.update(kwargs)
        return ThreatModel(**defaults)

    def test_minimal_creation(self):
        t = self._make()
        assert t.threat_id == "threat-001"
        assert t.category == ThreatCategory.PROMPT_INJECTION

    def test_defaults(self):
        t = self._make()
        assert t.likelihood == RiskSeverity.MEDIUM
        assert t.impact == RiskSeverity.MEDIUM
        assert t.risk_score == 0.5
        assert t.affected_components == []
        assert t.mitigations == []
        assert t.detection_methods == []
        assert t.constitutional_hash == CONSTITUTIONAL_HASH

    def test_risk_score_bounds(self):
        t = self._make(risk_score=0.0)
        assert t.risk_score == 0.0
        t2 = self._make(risk_score=1.0)
        assert t2.risk_score == 1.0

    def test_calculate_risk_score_critical_critical(self):
        t = self._make(likelihood=RiskSeverity.CRITICAL, impact=RiskSeverity.CRITICAL)
        score = t.calculate_risk_score()
        assert score == pytest.approx(1.0)
        assert t.risk_score == pytest.approx(1.0)

    def test_calculate_risk_score_low_low(self):
        t = self._make(likelihood=RiskSeverity.LOW, impact=RiskSeverity.LOW)
        score = t.calculate_risk_score()
        assert score == pytest.approx(0.3)

    def test_calculate_risk_score_high_medium(self):
        t = self._make(likelihood=RiskSeverity.HIGH, impact=RiskSeverity.MEDIUM)
        score = t.calculate_risk_score()
        assert score == pytest.approx((0.8 + 0.5) / 2)

    def test_calculate_risk_score_informational(self):
        t = self._make(likelihood=RiskSeverity.INFORMATIONAL, impact=RiskSeverity.INFORMATIONAL)
        score = t.calculate_risk_score()
        assert score == pytest.approx(0.1)

    def test_calculate_risk_score_mixed(self):
        t = self._make(likelihood=RiskSeverity.CRITICAL, impact=RiskSeverity.LOW)
        score = t.calculate_risk_score()
        assert score == pytest.approx((1.0 + 0.3) / 2)

    def test_with_lists_populated(self):
        t = self._make(
            affected_components=["agent-bus", "policy-engine"],
            mitigations=["input filtering"],
            detection_methods=["anomaly detection"],
        )
        assert len(t.affected_components) == 2
        assert len(t.mitigations) == 1
        assert len(t.detection_methods) == 1


# ---------------------------------------------------------------------------
# RiskMitigation
# ---------------------------------------------------------------------------


class TestRiskMitigation:
    def _make(self, **kwargs):
        defaults = dict(
            mitigation_id="mit-001",
            threat_id="threat-001",
            name="Input Sanitization",
            description="Sanitize all user inputs",
        )
        defaults.update(kwargs)
        return RiskMitigation(**defaults)

    def test_minimal_creation(self):
        m = self._make()
        assert m.mitigation_id == "mit-001"
        assert m.threat_id == "threat-001"

    def test_defaults(self):
        m = self._make()
        assert m.control_type == "preventive"
        assert m.implementation_status == ComplianceStatus.NOT_ASSESSED
        assert m.effectiveness == 0.0
        assert m.responsible_party == ""
        assert m.due_date is None
        assert m.evidence == []
        assert m.residual_risk == RiskSeverity.LOW
        assert m.constitutional_hash == CONSTITUTIONAL_HASH

    def test_with_due_date(self):
        dt = datetime(2026, 12, 31, tzinfo=UTC)
        m = self._make(due_date=dt)
        assert m.due_date == dt

    def test_effectiveness_bounds(self):
        m = self._make(effectiveness=0.0)
        assert m.effectiveness == 0.0
        m2 = self._make(effectiveness=1.0)
        assert m2.effectiveness == 1.0

    def test_override_status(self):
        m = self._make(implementation_status=ComplianceStatus.COMPLIANT, effectiveness=0.9)
        assert m.implementation_status == ComplianceStatus.COMPLIANT
        assert m.effectiveness == 0.9


# ---------------------------------------------------------------------------
# RiskRegisterEntry
# ---------------------------------------------------------------------------


class TestRiskRegisterEntry:
    def _make_context(self):
        return RiskContext(
            context_id="ctx-001",
            system_name="ACGS-2",
            intended_purpose="governance",
        )

    def _make_threat(self, risk_score: float = 0.5) -> ThreatModel:
        t = ThreatModel(
            threat_id="t-001",
            category=ThreatCategory.ADVERSARIAL_INPUT,
            name="Adversarial Input",
            description="Adversarial input attack",
            attack_vector="API",
            risk_score=risk_score,
        )
        return t

    def _make_mitigation(
        self,
        effectiveness: float = 0.5,
        status: ComplianceStatus = ComplianceStatus.COMPLIANT,
    ) -> RiskMitigation:
        return RiskMitigation(
            mitigation_id="m-001",
            threat_id="t-001",
            name="Defence",
            description="desc",
            implementation_status=status,
            effectiveness=effectiveness,
        )

    def _make(self, **kwargs):
        defaults = dict(entry_id="entry-001", risk_context=self._make_context())
        defaults.update(kwargs)
        return RiskRegisterEntry(**defaults)

    def test_minimal_creation(self):
        e = self._make()
        assert e.entry_id == "entry-001"
        assert e.overall_risk_level == RiskSeverity.MEDIUM

    def test_defaults(self):
        e = self._make()
        assert e.threats == []
        assert e.mitigations == []
        assert e.risk_owner == ""
        assert e.review_date is None
        assert e.notes == ""
        assert e.constitutional_hash == CONSTITUTIONAL_HASH

    def test_calculate_overall_risk_no_threats(self):
        e = self._make()
        result = e.calculate_overall_risk()
        assert result == RiskSeverity.LOW

    def test_calculate_overall_risk_critical(self):
        t = self._make_threat(risk_score=0.9)
        e = self._make(threats=[t])
        result = e.calculate_overall_risk()
        assert result == RiskSeverity.CRITICAL
        assert e.overall_risk_level == RiskSeverity.CRITICAL

    def test_calculate_overall_risk_high(self):
        t = self._make_threat(risk_score=0.7)
        e = self._make(threats=[t])
        result = e.calculate_overall_risk()
        assert result == RiskSeverity.HIGH

    def test_calculate_overall_risk_medium(self):
        t = self._make_threat(risk_score=0.5)
        e = self._make(threats=[t])
        result = e.calculate_overall_risk()
        assert result == RiskSeverity.MEDIUM

    def test_calculate_overall_risk_low(self):
        t = self._make_threat(risk_score=0.3)
        e = self._make(threats=[t])
        result = e.calculate_overall_risk()
        assert result == RiskSeverity.LOW

    def test_calculate_overall_risk_informational(self):
        t = self._make_threat(risk_score=0.1)
        e = self._make(threats=[t])
        result = e.calculate_overall_risk()
        assert result == RiskSeverity.INFORMATIONAL

    def test_calculate_overall_risk_with_effective_mitigation(self):
        # risk_score=0.9 reduced by mitigation effectiveness=0.9 → ~0.09 → INFORMATIONAL
        t = self._make_threat(risk_score=0.9)
        m = self._make_mitigation(effectiveness=0.9, status=ComplianceStatus.COMPLIANT)
        e = self._make(threats=[t], mitigations=[m])
        result = e.calculate_overall_risk()
        assert result == RiskSeverity.INFORMATIONAL

    def test_calculate_overall_risk_non_compliant_mitigation_ignored(self):
        # Non-compliant mitigation should NOT reduce risk
        t = self._make_threat(risk_score=0.9)
        m = self._make_mitigation(effectiveness=0.9, status=ComplianceStatus.NON_COMPLIANT)
        e = self._make(threats=[t], mitigations=[m])
        result = e.calculate_overall_risk()
        assert result == RiskSeverity.CRITICAL

    def test_calculate_overall_risk_multiple_mitigations(self):
        t = self._make_threat(risk_score=0.85)
        m1 = self._make_mitigation(effectiveness=0.5, status=ComplianceStatus.COMPLIANT)
        m2 = RiskMitigation(
            mitigation_id="m-002",
            threat_id="t-001",
            name="Defence 2",
            description="desc2",
            implementation_status=ComplianceStatus.COMPLIANT,
            effectiveness=0.5,
        )
        e = self._make(threats=[t], mitigations=[m1, m2])
        # avg effectiveness = 0.5 → max_risk = 0.85 * (1-0.5) = 0.425 → MEDIUM
        result = e.calculate_overall_risk()
        assert result == RiskSeverity.MEDIUM


# ---------------------------------------------------------------------------
# ProcessingIntegrityControl
# ---------------------------------------------------------------------------


class TestProcessingIntegrityControl:
    def _make(self, **kwargs):
        defaults = dict(
            control_id="PI-1.1",
            control_name="Completeness Check",
            description="Ensures data completeness",
            criteria="PI1.1",
        )
        defaults.update(kwargs)
        return ProcessingIntegrityControl(**defaults)

    def test_minimal_creation(self):
        c = self._make()
        assert c.control_id == "PI-1.1"
        assert c.control_name == "Completeness Check"

    def test_defaults(self):
        c = self._make()
        assert c.implementation_status == ComplianceStatus.NOT_ASSESSED
        assert c.testing_frequency == "quarterly"
        assert c.last_tested is None
        assert c.test_results == ""
        assert c.acgs2_components == []
        assert c.evidence_artifacts == []
        assert c.completeness_check is False
        assert c.accuracy_check is False
        assert c.timeliness_check is False
        assert c.authorization_check is False
        assert c.constitutional_hash == CONSTITUTIONAL_HASH

    def test_override_booleans(self):
        c = self._make(
            completeness_check=True,
            accuracy_check=True,
            timeliness_check=True,
            authorization_check=True,
        )
        assert c.completeness_check is True
        assert c.accuracy_check is True
        assert c.timeliness_check is True
        assert c.authorization_check is True

    def test_with_last_tested(self):
        dt = datetime(2026, 1, 1, tzinfo=UTC)
        c = self._make(last_tested=dt)
        assert c.last_tested == dt


# ---------------------------------------------------------------------------
# ConfidentialityControl
# ---------------------------------------------------------------------------


class TestConfidentialityControl:
    def _make(self, **kwargs):
        defaults = dict(
            control_id="C-1.1",
            control_name="Encryption",
            description="Encryption at rest and transit",
            criteria="C1.1",
        )
        defaults.update(kwargs)
        return ConfidentialityControl(**defaults)

    def test_minimal_creation(self):
        c = self._make()
        assert c.control_id == "C-1.1"

    def test_defaults(self):
        c = self._make()
        assert c.implementation_status == ComplianceStatus.NOT_ASSESSED
        assert c.data_classification == DataClassification.CONFIDENTIAL
        assert c.encryption_at_rest is False
        assert c.encryption_in_transit is False
        assert c.access_controls == []
        assert c.retention_policy == ""
        assert c.disposal_procedures == ""
        assert c.acgs2_components == []
        assert c.evidence_artifacts == []
        assert c.constitutional_hash == CONSTITUTIONAL_HASH

    def test_override_encryption_flags(self):
        c = self._make(encryption_at_rest=True, encryption_in_transit=True)
        assert c.encryption_at_rest is True
        assert c.encryption_in_transit is True

    def test_override_classification(self):
        c = self._make(data_classification=DataClassification.PII)
        assert c.data_classification == DataClassification.PII


# ---------------------------------------------------------------------------
# AvailabilityControl
# ---------------------------------------------------------------------------


class TestAvailabilityControl:
    def _make(self, **kwargs):
        defaults = dict(
            control_id="A-1.1",
            control_name="Uptime Monitoring",
            description="99.9% uptime",
            criteria="A1.1",
        )
        defaults.update(kwargs)
        return AvailabilityControl(**defaults)

    def test_minimal_creation(self):
        a = self._make()
        assert a.control_id == "A-1.1"

    def test_defaults(self):
        a = self._make()
        assert a.implementation_status == ComplianceStatus.NOT_ASSESSED
        assert a.uptime_target == pytest.approx(99.9)
        assert a.current_uptime == pytest.approx(0.0)
        assert a.recovery_time_objective == 60
        assert a.recovery_point_objective == 15
        assert a.redundancy_mechanisms == []
        assert a.backup_procedures == []
        assert a.disaster_recovery_plan is False
        assert a.monitoring_enabled is False
        assert a.incident_response_plan is False
        assert a.capacity_planning is False
        assert a.acgs2_components == []
        assert a.evidence_artifacts == []
        assert a.last_tested is None
        assert a.testing_frequency == "monthly"
        assert a.constitutional_hash == CONSTITUTIONAL_HASH

    def test_override_flags(self):
        a = self._make(
            disaster_recovery_plan=True,
            monitoring_enabled=True,
            incident_response_plan=True,
            capacity_planning=True,
        )
        assert a.disaster_recovery_plan is True
        assert a.monitoring_enabled is True
        assert a.incident_response_plan is True
        assert a.capacity_planning is True

    def test_uptime_bounds(self):
        a = self._make(uptime_target=100.0, current_uptime=99.5)
        assert a.uptime_target == pytest.approx(100.0)
        assert a.current_uptime == pytest.approx(99.5)


# ---------------------------------------------------------------------------
# AuditEvidenceItem
# ---------------------------------------------------------------------------


class TestAuditEvidenceItem:
    def _make(self, **kwargs):
        defaults = dict(
            evidence_id="ev-001",
            control_id="PI-1.1",
            evidence_type="log_export",
            description="System log export",
            source="ACGS-2 Agent Bus",
        )
        defaults.update(kwargs)
        return AuditEvidenceItem(**defaults)

    def test_minimal_creation(self):
        item = self._make()
        assert item.evidence_id == "ev-001"
        assert item.source == "ACGS-2 Agent Bus"

    def test_defaults(self):
        item = self._make()
        assert item.collected_by == ""
        assert item.artifact_path == ""
        assert item.hash_value == ""
        assert item.validity_period_days == 90
        assert item.is_valid is True
        assert item.reviewer is None
        assert item.review_date is None
        assert item.constitutional_hash == CONSTITUTIONAL_HASH

    def test_collected_at_is_timezone_aware(self):
        item = self._make()
        assert item.collected_at.tzinfo is not None

    def test_with_reviewer(self):
        item = self._make(reviewer="alice", review_date=datetime(2026, 1, 1, tzinfo=UTC))
        assert item.reviewer == "alice"
        assert item.review_date is not None


# ---------------------------------------------------------------------------
# AuditEvidencePackage
# ---------------------------------------------------------------------------


class TestAuditEvidencePackage:
    _NOW = datetime(2026, 1, 1, tzinfo=UTC)
    _THEN = datetime(2026, 3, 1, tzinfo=UTC)

    def _make(self, **kwargs):
        defaults = dict(
            package_id="pkg-001",
            period_start=self._NOW,
            period_end=self._THEN,
        )
        defaults.update(kwargs)
        return AuditEvidencePackage(**defaults)

    def test_minimal_creation(self):
        pkg = self._make()
        assert pkg.package_id == "pkg-001"

    def test_defaults(self):
        pkg = self._make()
        assert pkg.package_name == "SOC 2 type II Audit Evidence Package"
        assert pkg.organization == "ACGS-2 Platform"
        assert pkg.evidence_items == []
        assert pkg.pi_controls_evidence == {}
        assert pkg.c_controls_evidence == {}
        assert pkg.a_controls_evidence == {}
        assert pkg.uptime_metrics == {}
        assert pkg.incident_log == []
        assert pkg.change_log == []
        assert pkg.access_reviews == []
        assert pkg.vulnerability_scans == []
        assert pkg.backup_test_results == []
        assert pkg.total_evidence_count == 0
        assert pkg.completeness_score == pytest.approx(0.0)
        assert pkg.generated_by == "acgs2-soc2-auditor"
        assert pkg.auditor_notes == ""
        assert pkg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_calculate_completeness_empty(self):
        pkg = self._make()
        score = pkg.calculate_completeness()
        # 0/6 base (0) + 0 pi + 0 c + 0 a = 0
        assert score == pytest.approx(0.0)
        assert pkg.completeness_score == pytest.approx(0.0)

    def test_calculate_completeness_all_base_present(self):
        pkg = self._make(
            uptime_metrics={"agent-bus": 99.9},
            incident_log=[{"id": "inc-001"}],
            change_log=[{"id": "chg-001"}],
            access_reviews=[{"id": "rev-001"}],
            vulnerability_scans=[{"id": "vscan-001"}],
            backup_test_results=[{"id": "bkp-001"}],
        )
        score = pkg.calculate_completeness()
        # 6/6 * 50 = 50, no control evidence
        assert score == pytest.approx(50.0)

    def test_calculate_completeness_all_present(self):
        item = AuditEvidenceItem(
            evidence_id="ev-001",
            control_id="PI-1.1",
            evidence_type="log",
            description="desc",
            source="src",
        )
        pkg = self._make(
            uptime_metrics={"agent-bus": 99.9},
            incident_log=[{"id": "inc-001"}],
            change_log=[{"id": "chg-001"}],
            access_reviews=[{"id": "rev-001"}],
            vulnerability_scans=[{"id": "vscan-001"}],
            backup_test_results=[{"id": "bkp-001"}],
            pi_controls_evidence={"PI-1.1": [item]},
            c_controls_evidence={"C-1.1": [item]},
            a_controls_evidence={"A-1.1": [item]},
        )
        score = pkg.calculate_completeness()
        # 50 + 15 + 15 + 20 = 100
        assert score == pytest.approx(100.0)

    def test_calculate_completeness_partial(self):
        pkg = self._make(
            uptime_metrics={"agent-bus": 99.9},
            incident_log=[{"id": "inc-001"}],
        )
        score = pkg.calculate_completeness()
        # 2/6 * 50 ≈ 16.67
        assert score == pytest.approx(2 / 6 * 50)

    def test_calculate_completeness_pi_only(self):
        item = AuditEvidenceItem(
            evidence_id="ev-001",
            control_id="PI-1.1",
            evidence_type="log",
            description="desc",
            source="src",
        )
        pkg = self._make(pi_controls_evidence={"PI-1.1": [item]})
        score = pkg.calculate_completeness()
        # 0 base + 15 pi + 0 c + 0 a = 15
        assert score == pytest.approx(15.0)

    def test_calculate_completeness_c_only(self):
        item = AuditEvidenceItem(
            evidence_id="ev-001",
            control_id="C-1.1",
            evidence_type="log",
            description="desc",
            source="src",
        )
        pkg = self._make(c_controls_evidence={"C-1.1": [item]})
        score = pkg.calculate_completeness()
        assert score == pytest.approx(15.0)

    def test_calculate_completeness_a_only(self):
        item = AuditEvidenceItem(
            evidence_id="ev-001",
            control_id="A-1.1",
            evidence_type="log",
            description="desc",
            source="src",
        )
        pkg = self._make(a_controls_evidence={"A-1.1": [item]})
        score = pkg.calculate_completeness()
        assert score == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# DataClassificationEntry
# ---------------------------------------------------------------------------


class TestDataClassificationEntry:
    def _make(self, **kwargs):
        defaults = dict(
            entry_id="dce-001",
            data_type="user_email",
            classification=DataClassification.PII,
        )
        defaults.update(kwargs)
        return DataClassificationEntry(**defaults)

    def test_minimal_creation(self):
        e = self._make()
        assert e.entry_id == "dce-001"
        assert e.classification == DataClassification.PII

    def test_defaults(self):
        e = self._make()
        assert e.description == ""
        assert e.pii_indicators == []
        assert e.handling_requirements == []
        assert e.encryption_required is True
        assert e.retention_days == 90
        assert e.access_roles == []
        assert e.audit_logging_required is True
        assert e.constitutional_hash == CONSTITUTIONAL_HASH

    def test_override_retention(self):
        e = self._make(retention_days=365)
        assert e.retention_days == 365

    def test_retention_zero(self):
        e = self._make(retention_days=0)
        assert e.retention_days == 0

    def test_override_flags(self):
        e = self._make(encryption_required=False, audit_logging_required=False)
        assert e.encryption_required is False
        assert e.audit_logging_required is False


# ---------------------------------------------------------------------------
# HighRiskClassification
# ---------------------------------------------------------------------------


class TestHighRiskClassification:
    def _make(self, **kwargs):
        defaults = dict(
            classification_id="hrc-001",
            system_name="ACGS-2",
        )
        defaults.update(kwargs)
        return HighRiskClassification(**defaults)

    def test_minimal_creation(self):
        h = self._make()
        assert h.classification_id == "hrc-001"
        assert h.is_high_risk is False
        assert h.risk_level == "limited"

    def test_defaults(self):
        h = self._make()
        assert h.annex_iii_category is None
        assert h.safety_component is False
        assert h.product_requiring_conformity is False
        assert h.significant_decisions is False
        assert h.biometric_categorization is False
        assert h.critical_infrastructure is False
        assert h.assessed_by == ""
        assert h.constitutional_hash == CONSTITUTIONAL_HASH

    def test_determine_risk_level_no_flags(self):
        h = self._make()
        result = h.determine_risk_level()
        assert result == "limited"
        assert h.is_high_risk is False

    def test_determine_risk_level_biometric(self):
        h = self._make(biometric_categorization=True)
        result = h.determine_risk_level()
        assert result == "high"
        assert h.is_high_risk is True

    def test_determine_risk_level_critical_infrastructure(self):
        h = self._make(critical_infrastructure=True)
        result = h.determine_risk_level()
        assert result == "high"
        assert h.is_high_risk is True

    def test_determine_risk_level_significant_and_safety(self):
        h = self._make(significant_decisions=True, safety_component=True)
        result = h.determine_risk_level()
        assert result == "high"
        assert h.is_high_risk is True

    def test_determine_risk_level_significant_without_safety(self):
        h = self._make(significant_decisions=True, safety_component=False)
        result = h.determine_risk_level()
        # significant_decisions alone (without safety_component) = False
        assert result == "limited"
        assert h.is_high_risk is False

    def test_determine_risk_level_annex_iii(self):
        h = self._make(annex_iii_category="Annex III Category 1")
        result = h.determine_risk_level()
        assert result == "high"
        assert h.is_high_risk is True

    def test_determine_risk_level_annex_iii_override_other_flags(self):
        # annex_iii takes second branch even if other flags are False
        h = self._make(annex_iii_category="Cat-X", biometric_categorization=False)
        result = h.determine_risk_level()
        assert result == "high"


# ---------------------------------------------------------------------------
# HumanOversightMechanism
# ---------------------------------------------------------------------------


class TestHumanOversightMechanism:
    def _make(self, **kwargs):
        defaults = dict(
            mechanism_id="hom-001",
            name="HITL Approval",
            description="Human reviews high-impact decisions",
        )
        defaults.update(kwargs)
        return HumanOversightMechanism(**defaults)

    def test_minimal_creation(self):
        h = self._make()
        assert h.mechanism_id == "hom-001"

    def test_defaults(self):
        h = self._make()
        assert h.oversight_level == HumanOversightLevel.HUMAN_ON_THE_LOOP
        assert h.capabilities_enabled == []
        assert h.intervention_points == []
        assert h.stop_mechanisms == []
        assert h.understanding_capabilities == []
        assert h.training_requirements == []
        assert h.escalation_procedures == []
        assert h.is_compliant is False
        assert h.constitutional_hash == CONSTITUTIONAL_HASH

    def test_override_oversight_level(self):
        h = self._make(oversight_level=HumanOversightLevel.HUMAN_IN_THE_LOOP)
        assert h.oversight_level == HumanOversightLevel.HUMAN_IN_THE_LOOP

    def test_fully_automated(self):
        h = self._make(oversight_level=HumanOversightLevel.FULLY_AUTOMATED, is_compliant=True)
        assert h.oversight_level == HumanOversightLevel.FULLY_AUTOMATED
        assert h.is_compliant is True


# ---------------------------------------------------------------------------
# TransparencyRequirement
# ---------------------------------------------------------------------------


class TestTransparencyRequirement:
    def _make(self, **kwargs):
        defaults = dict(
            requirement_id="tr-001",
            description="AI system must disclose its nature",
        )
        defaults.update(kwargs)
        return TransparencyRequirement(**defaults)

    def test_minimal_creation(self):
        t = self._make()
        assert t.requirement_id == "tr-001"

    def test_defaults(self):
        t = self._make()
        assert t.article_reference == "Article 13"
        assert t.implementation_status == ComplianceStatus.NOT_ASSESSED
        assert t.transparency_measures == []
        assert t.user_instructions_available is False
        assert t.capabilities_disclosed is False
        assert t.limitations_disclosed is False
        assert t.accuracy_metrics_available is False
        assert t.explanation_api_available is False
        assert t.evidence == []
        assert t.constitutional_hash == CONSTITUTIONAL_HASH

    def test_override_flags(self):
        t = self._make(
            user_instructions_available=True,
            capabilities_disclosed=True,
            limitations_disclosed=True,
            accuracy_metrics_available=True,
            explanation_api_available=True,
        )
        assert t.user_instructions_available is True
        assert t.explanation_api_available is True


# ---------------------------------------------------------------------------
# TechnicalDocumentation
# ---------------------------------------------------------------------------


class TestTechnicalDocumentation:
    def _make(self, **kwargs):
        defaults = dict(
            doc_id="doc-001",
            system_name="ACGS-2",
        )
        defaults.update(kwargs)
        return TechnicalDocumentation(**defaults)

    def test_minimal_creation(self):
        d = self._make()
        assert d.doc_id == "doc-001"
        assert d.system_name == "ACGS-2"

    def test_defaults(self):
        d = self._make()
        assert d.version == "1.0.0"
        assert d.general_description == ""
        assert d.intended_purpose == ""
        assert d.development_methods == []
        assert d.data_requirements == {}
        assert d.testing_procedures == []
        assert d.validation_results == {}
        assert d.risk_management_system == ""
        assert d.monitoring_capabilities == []
        assert d.changes_log == []
        assert d.constitutional_hash == CONSTITUTIONAL_HASH

    def test_timestamps_are_timezone_aware(self):
        d = self._make()
        assert d.created_at.tzinfo is not None
        assert d.updated_at.tzinfo is not None

    def test_with_populated_lists(self):
        d = self._make(
            development_methods=["agile", "scrum"],
            testing_procedures=["unit", "integration"],
            monitoring_capabilities=["prometheus"],
        )
        assert len(d.development_methods) == 2
        assert len(d.testing_procedures) == 2
        assert len(d.monitoring_capabilities) == 1


# ---------------------------------------------------------------------------
# ComplianceViolation
# ---------------------------------------------------------------------------


class TestComplianceViolation:
    def _make(self, **kwargs):
        defaults = dict(
            violation_id="viol-001",
            framework=ComplianceFramework.SOC2_TYPE_II,
            control_id="PI-1.1",
            description="Missing audit logs for 3 days",
        )
        defaults.update(kwargs)
        return ComplianceViolation(**defaults)

    def test_minimal_creation(self):
        v = self._make()
        assert v.violation_id == "viol-001"
        assert v.framework == ComplianceFramework.SOC2_TYPE_II

    def test_defaults(self):
        v = self._make()
        assert v.severity == RiskSeverity.MEDIUM
        assert v.detected_by == ""
        assert v.affected_systems == []
        assert v.remediation_status == ComplianceStatus.NOT_ASSESSED
        assert v.remediation_actions == []
        assert v.remediation_deadline is None
        assert v.resolved_at is None
        assert v.root_cause == ""
        assert v.constitutional_hash == CONSTITUTIONAL_HASH

    def test_detected_at_is_timezone_aware(self):
        v = self._make()
        assert v.detected_at.tzinfo is not None

    def test_with_resolution(self):
        dt = datetime(2026, 2, 1, tzinfo=UTC)
        v = self._make(resolved_at=dt, remediation_status=ComplianceStatus.COMPLIANT)
        assert v.resolved_at == dt
        assert v.remediation_status == ComplianceStatus.COMPLIANT

    def test_severity_override(self):
        v = self._make(severity=RiskSeverity.CRITICAL)
        assert v.severity == RiskSeverity.CRITICAL


# ---------------------------------------------------------------------------
# ComplianceAssessment
# ---------------------------------------------------------------------------


class TestComplianceAssessment:
    def _make(self, **kwargs):
        defaults = dict(
            assessment_id="assess-001",
            framework=ComplianceFramework.NIST_AI_RMF,
            system_name="ACGS-2",
        )
        defaults.update(kwargs)
        return ComplianceAssessment(**defaults)

    def test_minimal_creation(self):
        a = self._make()
        assert a.assessment_id == "assess-001"
        assert a.framework == ComplianceFramework.NIST_AI_RMF

    def test_defaults(self):
        a = self._make()
        assert a.assessor == "acgs2-compliance-engine"
        assert a.overall_status == ComplianceStatus.NOT_ASSESSED
        assert a.compliance_score == pytest.approx(0.0)
        assert a.controls_assessed == 0
        assert a.controls_compliant == 0
        assert a.controls_non_compliant == 0
        assert a.controls_partial == 0
        assert a.violations == []
        assert a.findings == []
        assert a.recommendations == []
        assert a.evidence_collected == []
        assert a.next_assessment_date is None
        assert a.constitutional_hash == CONSTITUTIONAL_HASH

    def test_calculate_score_zero_assessed(self):
        a = self._make()
        score = a.calculate_score()
        assert score == pytest.approx(0.0)

    def test_calculate_score_fully_compliant(self):
        a = self._make(controls_assessed=10, controls_compliant=10)
        score = a.calculate_score()
        assert score == pytest.approx(100.0)
        assert a.overall_status == ComplianceStatus.COMPLIANT

    def test_calculate_score_compliant_threshold(self):
        # 95% = COMPLIANT
        a = self._make(controls_assessed=20, controls_compliant=19)
        score = a.calculate_score()
        assert score == pytest.approx(95.0)
        assert a.overall_status == ComplianceStatus.COMPLIANT

    def test_calculate_score_partial(self):
        # 70%-94% = PARTIAL
        a = self._make(controls_assessed=10, controls_compliant=7)
        score = a.calculate_score()
        assert score == pytest.approx(70.0)
        assert a.overall_status == ComplianceStatus.PARTIAL

    def test_calculate_score_partial_with_partials(self):
        # 5 compliant (5.0) + 4 partial (2.0) = 7.0/10 = 70%
        a = self._make(controls_assessed=10, controls_compliant=5, controls_partial=4)
        score = a.calculate_score()
        assert score == pytest.approx(70.0)

    def test_calculate_score_non_compliant(self):
        # Below 70% = NON_COMPLIANT
        a = self._make(controls_assessed=10, controls_compliant=5)
        score = a.calculate_score()
        assert score == pytest.approx(50.0)
        assert a.overall_status == ComplianceStatus.NON_COMPLIANT

    def test_calculate_score_rounds(self):
        # 1/3 * 100 = 33.33... → rounds to 33.33
        a = self._make(controls_assessed=3, controls_compliant=1)
        score = a.calculate_score()
        assert score == pytest.approx(33.33, abs=0.01)

    def test_calculate_score_partial_above_95(self):
        # 10 compliant + 0 partial = 100%, status COMPLIANT
        a = self._make(controls_assessed=20, controls_compliant=20)
        score = a.calculate_score()
        assert a.overall_status == ComplianceStatus.COMPLIANT


# ---------------------------------------------------------------------------
# ComplianceReport
# ---------------------------------------------------------------------------


class TestComplianceReport:
    def _make_assessment(self, score: float = 80.0) -> ComplianceAssessment:
        a = ComplianceAssessment(
            assessment_id="a-001",
            framework=ComplianceFramework.GDPR,
            system_name="ACGS-2",
            compliance_score=score,
        )
        return a

    def _make(self, **kwargs):
        defaults = dict(report_id="rep-001")
        defaults.update(kwargs)
        return ComplianceReport(**defaults)

    def test_minimal_creation(self):
        r = self._make()
        assert r.report_id == "rep-001"

    def test_defaults(self):
        r = self._make()
        assert r.report_title == "ACGS-2 Compliance Report"
        assert r.organization == "ACGS-2 Platform"
        assert r.generated_by == "acgs2-compliance-engine"
        assert r.assessments == []
        assert r.overall_compliance_score == pytest.approx(0.0)
        assert r.overall_status == ComplianceStatus.NOT_ASSESSED
        assert r.executive_summary == ""
        assert r.key_findings == []
        assert r.critical_violations == []
        assert r.recommendations == []
        assert r.next_steps == []
        assert r.constitutional_hash == CONSTITUTIONAL_HASH

    def test_calculate_overall_score_no_assessments(self):
        r = self._make()
        score = r.calculate_overall_score()
        assert score == pytest.approx(0.0)

    def test_calculate_overall_score_compliant(self):
        a = self._make_assessment(score=100.0)
        r = self._make(assessments=[a])
        score = r.calculate_overall_score()
        assert score == pytest.approx(100.0)
        assert r.overall_status == ComplianceStatus.COMPLIANT

    def test_calculate_overall_score_compliant_boundary(self):
        a = self._make_assessment(score=95.0)
        r = self._make(assessments=[a])
        score = r.calculate_overall_score()
        assert score == pytest.approx(95.0)
        assert r.overall_status == ComplianceStatus.COMPLIANT

    def test_calculate_overall_score_partial(self):
        a = self._make_assessment(score=80.0)
        r = self._make(assessments=[a])
        score = r.calculate_overall_score()
        assert score == pytest.approx(80.0)
        assert r.overall_status == ComplianceStatus.PARTIAL

    def test_calculate_overall_score_partial_boundary(self):
        a = self._make_assessment(score=70.0)
        r = self._make(assessments=[a])
        score = r.calculate_overall_score()
        assert r.overall_status == ComplianceStatus.PARTIAL

    def test_calculate_overall_score_non_compliant(self):
        a = self._make_assessment(score=50.0)
        r = self._make(assessments=[a])
        score = r.calculate_overall_score()
        assert score == pytest.approx(50.0)
        assert r.overall_status == ComplianceStatus.NON_COMPLIANT

    def test_calculate_overall_score_multiple_assessments(self):
        a1 = self._make_assessment(score=80.0)
        a2 = self._make_assessment(score=100.0)
        a3 = self._make_assessment(score=60.0)
        r = self._make(assessments=[a1, a2, a3])
        score = r.calculate_overall_score()
        # (80 + 100 + 60) / 3 = 80
        assert score == pytest.approx(80.0)
        assert r.overall_status == ComplianceStatus.PARTIAL

    def test_calculate_overall_score_rounds(self):
        a1 = self._make_assessment(score=100.0)
        a2 = self._make_assessment(score=0.0)
        a3 = self._make_assessment(score=0.0)
        r = self._make(assessments=[a1, a2, a3])
        score = r.calculate_overall_score()
        # 100/3 = 33.33
        assert score == pytest.approx(33.33, abs=0.01)
        assert r.overall_status == ComplianceStatus.NON_COMPLIANT


# ---------------------------------------------------------------------------
# __all__ completeness check
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_all_exports_importable(self):
        from compliance_layer import models

        expected = [
            "ComplianceFramework",
            "ComplianceStatus",
            "RiskSeverity",
            "ThreatCategory",
            "DataClassification",
            "HumanOversightLevel",
            "RiskContext",
            "ThreatModel",
            "RiskMitigation",
            "RiskRegisterEntry",
            "ProcessingIntegrityControl",
            "ConfidentialityControl",
            "AvailabilityControl",
            "DataClassificationEntry",
            "AuditEvidenceItem",
            "AuditEvidencePackage",
            "HighRiskClassification",
            "HumanOversightMechanism",
            "TransparencyRequirement",
            "TechnicalDocumentation",
            "ComplianceAssessment",
            "ComplianceViolation",
            "ComplianceReport",
        ]
        for name in expected:
            assert hasattr(models, name), f"Missing export: {name}"

    def test_constitutional_hash_present_in_models(self):
        # Every model must default to the correct constitutional hash
        ctx = RiskContext(context_id="x", system_name="y", intended_purpose="z")
        assert ctx.constitutional_hash == CONSTITUTIONAL_HASH
