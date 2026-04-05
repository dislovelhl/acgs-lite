"""
ACGS-2 Compliance Layer Models
Constitutional Hash: 608508a9bd224290
"""

from datetime import UTC, datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]


class ComplianceFramework(str, Enum):
    NIST_AI_RMF = "nist_ai_rmf"
    SOC2_TYPE_II = "soc2_type_ii"
    EU_AI_ACT = "eu_ai_act"
    ISO_27001 = "iso_27001"
    GDPR = "gdpr"


class ComplianceStatus(str, Enum):
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PARTIAL = "partial"
    NOT_ASSESSED = "not_assessed"
    IN_PROGRESS = "in_progress"
    EXEMPT = "exempt"


class RiskSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class ThreatCategory(str, Enum):
    DATA_POISONING = "data_poisoning"
    MODEL_EXTRACTION = "model_extraction"
    ADVERSARIAL_INPUT = "adversarial_input"
    PROMPT_INJECTION = "prompt_injection"
    PRIVACY_LEAKAGE = "privacy_leakage"
    SUPPLY_CHAIN = "supply_chain"
    INSIDER_THREAT = "insider_threat"
    CONSTITUTIONAL_BYPASS = "constitutional_bypass"
    GOVERNANCE_EVASION = "governance_evasion"


class DataClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    PII = "pii"
    PHI = "phi"


class HumanOversightLevel(str, Enum):
    HUMAN_IN_THE_LOOP = "human_in_the_loop"
    HUMAN_ON_THE_LOOP = "human_on_the_loop"
    HUMAN_IN_COMMAND = "human_in_command"
    FULLY_AUTOMATED = "fully_automated"


class RiskContext(BaseModel):
    context_id: str = Field(..., description="Unique context identifier")
    system_name: str = Field(..., description="AI system name")
    system_version: str = Field(default="1.0.0")
    deployment_environment: str = Field(default="production")
    intended_purpose: str = Field(...)
    user_population: str = Field(default="enterprise")
    data_types: list[DataClassification] = Field(default_factory=list)
    risk_tolerance: RiskSeverity = Field(default=RiskSeverity.MEDIUM)
    regulatory_requirements: list[ComplianceFramework] = Field(default_factory=list)
    stakeholders: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    model_config = {"from_attributes": True}


class ThreatModel(BaseModel):
    threat_id: str = Field(...)
    category: ThreatCategory = Field(...)
    name: str = Field(...)
    description: str = Field(...)
    attack_vector: str = Field(...)
    likelihood: RiskSeverity = Field(default=RiskSeverity.MEDIUM)
    impact: RiskSeverity = Field(default=RiskSeverity.MEDIUM)
    risk_score: float = Field(default=0.5, ge=0.0, le=1.0)
    affected_components: list[str] = Field(default_factory=list)
    mitigations: list[str] = Field(default_factory=list)
    detection_methods: list[str] = Field(default_factory=list)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)

    def calculate_risk_score(self) -> float:
        severity_values = {
            RiskSeverity.CRITICAL: 1.0,
            RiskSeverity.HIGH: 0.8,
            RiskSeverity.MEDIUM: 0.5,
            RiskSeverity.LOW: 0.3,
            RiskSeverity.INFORMATIONAL: 0.1,
        }
        self.risk_score = (
            severity_values.get(self.likelihood, 0.5) + severity_values.get(self.impact, 0.5)
        ) / 2
        return self.risk_score


class RiskMitigation(BaseModel):
    mitigation_id: str = Field(...)
    threat_id: str = Field(...)
    name: str = Field(...)
    description: str = Field(...)
    control_type: str = Field(default="preventive")
    implementation_status: ComplianceStatus = Field(default=ComplianceStatus.NOT_ASSESSED)
    effectiveness: float = Field(default=0.0, ge=0.0, le=1.0)
    responsible_party: str = Field(default="")
    due_date: datetime | None = Field(default=None)
    evidence: list[str] = Field(default_factory=list)
    residual_risk: RiskSeverity = Field(default=RiskSeverity.LOW)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    model_config = {"from_attributes": True}


class RiskRegisterEntry(BaseModel):
    entry_id: str = Field(...)
    risk_context: RiskContext = Field(...)
    threats: list[ThreatModel] = Field(default_factory=list)
    mitigations: list[RiskMitigation] = Field(default_factory=list)
    overall_risk_level: RiskSeverity = Field(default=RiskSeverity.MEDIUM)
    risk_owner: str = Field(default="")
    review_date: datetime | None = Field(default=None)
    notes: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)

    def calculate_overall_risk(self) -> RiskSeverity:
        if not self.threats:
            return RiskSeverity.LOW
        max_risk = max(t.risk_score for t in self.threats)
        effective = [
            m for m in self.mitigations if m.implementation_status == ComplianceStatus.COMPLIANT
        ]
        if effective:
            max_risk *= 1 - sum(m.effectiveness for m in effective) / len(effective)
        if max_risk >= 0.8:
            self.overall_risk_level = RiskSeverity.CRITICAL
        elif max_risk >= 0.6:
            self.overall_risk_level = RiskSeverity.HIGH
        elif max_risk >= 0.4:
            self.overall_risk_level = RiskSeverity.MEDIUM
        elif max_risk >= 0.2:
            self.overall_risk_level = RiskSeverity.LOW
        else:
            self.overall_risk_level = RiskSeverity.INFORMATIONAL
        return self.overall_risk_level


class ProcessingIntegrityControl(BaseModel):
    control_id: str = Field(...)
    control_name: str = Field(...)
    description: str = Field(...)
    criteria: str = Field(...)
    implementation_status: ComplianceStatus = Field(default=ComplianceStatus.NOT_ASSESSED)
    testing_frequency: str = Field(default="quarterly")
    last_tested: datetime | None = Field(default=None)
    test_results: str = Field(default="")
    acgs2_components: list[str] = Field(default_factory=list)
    evidence_artifacts: list[str] = Field(default_factory=list)
    completeness_check: bool = Field(default=False)
    accuracy_check: bool = Field(default=False)
    timeliness_check: bool = Field(default=False)
    authorization_check: bool = Field(default=False)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    model_config = {"from_attributes": True}


class ConfidentialityControl(BaseModel):
    control_id: str = Field(...)
    control_name: str = Field(...)
    description: str = Field(...)
    criteria: str = Field(...)
    implementation_status: ComplianceStatus = Field(default=ComplianceStatus.NOT_ASSESSED)
    data_classification: DataClassification = Field(default=DataClassification.CONFIDENTIAL)
    encryption_at_rest: bool = Field(default=False)
    encryption_in_transit: bool = Field(default=False)
    access_controls: list[str] = Field(default_factory=list)
    retention_policy: str = Field(default="")
    disposal_procedures: str = Field(default="")
    acgs2_components: list[str] = Field(default_factory=list)
    evidence_artifacts: list[str] = Field(default_factory=list)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    model_config = {"from_attributes": True}


class AvailabilityControl(BaseModel):
    """SOC 2 Availability Trust Service Criteria control.

    Constitutional Hash: 608508a9bd224290
    """

    control_id: str = Field(...)
    control_name: str = Field(...)
    description: str = Field(...)
    criteria: str = Field(...)  # A1.1, A1.2, A1.3
    implementation_status: ComplianceStatus = Field(default=ComplianceStatus.NOT_ASSESSED)
    uptime_target: float = Field(default=99.9, ge=0.0, le=100.0)
    current_uptime: float = Field(default=0.0, ge=0.0, le=100.0)
    recovery_time_objective: int = Field(default=60)  # Minutes
    recovery_point_objective: int = Field(default=15)  # Minutes
    redundancy_mechanisms: list[str] = Field(default_factory=list)
    backup_procedures: list[str] = Field(default_factory=list)
    disaster_recovery_plan: bool = Field(default=False)
    monitoring_enabled: bool = Field(default=False)
    incident_response_plan: bool = Field(default=False)
    capacity_planning: bool = Field(default=False)
    acgs2_components: list[str] = Field(default_factory=list)
    evidence_artifacts: list[str] = Field(default_factory=list)
    last_tested: datetime | None = Field(default=None)
    testing_frequency: str = Field(default="monthly")
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    model_config = {"from_attributes": True}


class AuditEvidencePackage(BaseModel):
    """60-day audit evidence package for SOC 2 type II.

    Constitutional Hash: 608508a9bd224290
    """

    package_id: str = Field(...)
    package_name: str = Field(default="SOC 2 type II Audit Evidence Package")
    organization: str = Field(default="ACGS-2 Platform")
    period_start: datetime = Field(...)
    period_end: datetime = Field(...)
    evidence_items: list["AuditEvidenceItem"] = Field(default_factory=list)
    pi_controls_evidence: dict[str, list["AuditEvidenceItem"]] = Field(default_factory=dict)
    c_controls_evidence: dict[str, list["AuditEvidenceItem"]] = Field(default_factory=dict)
    a_controls_evidence: dict[str, list["AuditEvidenceItem"]] = Field(default_factory=dict)
    uptime_metrics: dict[str, float] = Field(default_factory=dict)
    incident_log: list[JSONDict] = Field(default_factory=list)
    change_log: list[JSONDict] = Field(default_factory=list)
    access_reviews: list[JSONDict] = Field(default_factory=list)
    vulnerability_scans: list[JSONDict] = Field(default_factory=list)
    backup_test_results: list[JSONDict] = Field(default_factory=list)
    total_evidence_count: int = Field(default=0)
    completeness_score: float = Field(default=0.0, ge=0.0, le=100.0)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    generated_by: str = Field(default="acgs2-soc2-auditor")
    auditor_notes: str = Field(default="")
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    model_config = {"from_attributes": True}

    def calculate_completeness(self) -> float:
        """Calculate evidence package completeness score."""
        required_evidence_types = [
            "uptime_metrics",
            "incident_log",
            "change_log",
            "access_reviews",
            "vulnerability_scans",
            "backup_test_results",
        ]
        has_count = sum(
            [
                bool(self.uptime_metrics),
                bool(self.incident_log),
                bool(self.change_log),
                bool(self.access_reviews),
                bool(self.vulnerability_scans),
                bool(self.backup_test_results),
            ]
        )
        base_score = (has_count / len(required_evidence_types)) * 50

        # Add points for control evidence
        pi_score = 15 if self.pi_controls_evidence else 0
        c_score = 15 if self.c_controls_evidence else 0
        a_score = 20 if self.a_controls_evidence else 0

        self.completeness_score = min(100, base_score + pi_score + c_score + a_score)
        return self.completeness_score


class DataClassificationEntry(BaseModel):
    entry_id: str = Field(...)
    data_type: str = Field(...)
    classification: DataClassification = Field(...)
    description: str = Field(default="")
    pii_indicators: list[str] = Field(default_factory=list)
    handling_requirements: list[str] = Field(default_factory=list)
    encryption_required: bool = Field(default=True)
    retention_days: int = Field(default=90, ge=0)
    access_roles: list[str] = Field(default_factory=list)
    audit_logging_required: bool = Field(default=True)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    model_config = {"from_attributes": True}


class AuditEvidenceItem(BaseModel):
    evidence_id: str = Field(...)
    control_id: str = Field(...)
    evidence_type: str = Field(...)
    description: str = Field(...)
    source: str = Field(...)
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    collected_by: str = Field(default="")
    artifact_path: str = Field(default="")
    hash_value: str = Field(default="")
    validity_period_days: int = Field(default=90)
    is_valid: bool = Field(default=True)
    reviewer: str | None = Field(default=None)
    review_date: datetime | None = Field(default=None)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    model_config = {"from_attributes": True}


class HighRiskClassification(BaseModel):
    classification_id: str = Field(...)
    system_name: str = Field(...)
    annex_iii_category: str | None = Field(default=None)
    is_high_risk: bool = Field(default=False)
    risk_level: str = Field(default="limited")
    classification_rationale: str = Field(default="")
    safety_component: bool = Field(default=False)
    product_requiring_conformity: bool = Field(default=False)
    significant_decisions: bool = Field(default=False)
    biometric_categorization: bool = Field(default=False)
    critical_infrastructure: bool = Field(default=False)
    assessed_by: str = Field(default="")
    assessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    model_config = {"from_attributes": True}

    def determine_risk_level(self) -> str:
        if any(
            [
                self.biometric_categorization,
                self.critical_infrastructure,
                self.significant_decisions and self.safety_component,
            ]
        ):
            self.is_high_risk = True
            self.risk_level = "high"
        elif self.annex_iii_category:
            self.is_high_risk = True
            self.risk_level = "high"
        else:
            self.is_high_risk = False
            self.risk_level = "limited"
        return self.risk_level


class HumanOversightMechanism(BaseModel):
    mechanism_id: str = Field(...)
    name: str = Field(...)
    description: str = Field(...)
    oversight_level: HumanOversightLevel = Field(default=HumanOversightLevel.HUMAN_ON_THE_LOOP)
    capabilities_enabled: list[str] = Field(default_factory=list)
    intervention_points: list[str] = Field(default_factory=list)
    stop_mechanisms: list[str] = Field(default_factory=list)
    understanding_capabilities: list[str] = Field(default_factory=list)
    training_requirements: list[str] = Field(default_factory=list)
    escalation_procedures: list[str] = Field(default_factory=list)
    is_compliant: bool = Field(default=False)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    model_config = {"from_attributes": True}


class TransparencyRequirement(BaseModel):
    requirement_id: str = Field(...)
    article_reference: str = Field(default="Article 13")
    description: str = Field(...)
    implementation_status: ComplianceStatus = Field(default=ComplianceStatus.NOT_ASSESSED)
    transparency_measures: list[str] = Field(default_factory=list)
    user_instructions_available: bool = Field(default=False)
    capabilities_disclosed: bool = Field(default=False)
    limitations_disclosed: bool = Field(default=False)
    accuracy_metrics_available: bool = Field(default=False)
    explanation_api_available: bool = Field(default=False)
    evidence: list[str] = Field(default_factory=list)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    model_config = {"from_attributes": True}


class TechnicalDocumentation(BaseModel):
    doc_id: str = Field(...)
    system_name: str = Field(...)
    version: str = Field(default="1.0.0")
    general_description: str = Field(default="")
    intended_purpose: str = Field(default="")
    development_methods: list[str] = Field(default_factory=list)
    data_requirements: JSONDict = Field(default_factory=dict)
    testing_procedures: list[str] = Field(default_factory=list)
    validation_results: JSONDict = Field(default_factory=dict)
    risk_management_system: str = Field(default="")
    monitoring_capabilities: list[str] = Field(default_factory=list)
    changes_log: list[JSONDict] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    model_config = {"from_attributes": True}


class ComplianceViolation(BaseModel):
    violation_id: str = Field(...)
    framework: ComplianceFramework = Field(...)
    control_id: str = Field(...)
    severity: RiskSeverity = Field(default=RiskSeverity.MEDIUM)
    description: str = Field(...)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    detected_by: str = Field(default="")
    affected_systems: list[str] = Field(default_factory=list)
    remediation_status: ComplianceStatus = Field(default=ComplianceStatus.NOT_ASSESSED)
    remediation_actions: list[str] = Field(default_factory=list)
    remediation_deadline: datetime | None = Field(default=None)
    resolved_at: datetime | None = Field(default=None)
    root_cause: str = Field(default="")
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    model_config = {"from_attributes": True}


class ComplianceAssessment(BaseModel):
    assessment_id: str = Field(...)
    framework: ComplianceFramework = Field(...)
    system_name: str = Field(...)
    assessment_date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    assessor: str = Field(default="acgs2-compliance-engine")
    overall_status: ComplianceStatus = Field(default=ComplianceStatus.NOT_ASSESSED)
    compliance_score: float = Field(default=0.0, ge=0.0, le=100.0)
    controls_assessed: int = Field(default=0)
    controls_compliant: int = Field(default=0)
    controls_non_compliant: int = Field(default=0)
    controls_partial: int = Field(default=0)
    violations: list[ComplianceViolation] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    evidence_collected: list[AuditEvidenceItem] = Field(default_factory=list)
    next_assessment_date: datetime | None = Field(default=None)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    model_config = {"from_attributes": True}

    def calculate_score(self) -> float:
        total = self.controls_assessed
        if total == 0:
            return 0.0
        score = ((self.controls_compliant * 1.0) + (self.controls_partial * 0.5)) / total * 100
        self.compliance_score = round(score, 2)
        if self.compliance_score >= 95:
            self.overall_status = ComplianceStatus.COMPLIANT
        elif self.compliance_score >= 70:
            self.overall_status = ComplianceStatus.PARTIAL
        else:
            self.overall_status = ComplianceStatus.NON_COMPLIANT
        return self.compliance_score


class ComplianceReport(BaseModel):
    report_id: str = Field(...)
    report_title: str = Field(default="ACGS-2 Compliance Report")
    organization: str = Field(default="ACGS-2 Platform")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    generated_by: str = Field(default="acgs2-compliance-engine")
    report_period_start: datetime = Field(default_factory=lambda: datetime.now(UTC))
    report_period_end: datetime = Field(default_factory=lambda: datetime.now(UTC))
    assessments: list[ComplianceAssessment] = Field(default_factory=list)
    overall_compliance_score: float = Field(default=0.0, ge=0.0, le=100.0)
    overall_status: ComplianceStatus = Field(default=ComplianceStatus.NOT_ASSESSED)
    executive_summary: str = Field(default="")
    key_findings: list[str] = Field(default_factory=list)
    critical_violations: list[ComplianceViolation] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    model_config = {"from_attributes": True}

    def calculate_overall_score(self) -> float:
        if not self.assessments:
            return 0.0
        total_score = sum(a.compliance_score for a in self.assessments)
        self.overall_compliance_score = round(total_score / len(self.assessments), 2)
        if self.overall_compliance_score >= 95:
            self.overall_status = ComplianceStatus.COMPLIANT
        elif self.overall_compliance_score >= 70:
            self.overall_status = ComplianceStatus.PARTIAL
        else:
            self.overall_status = ComplianceStatus.NON_COMPLIANT
        return self.overall_compliance_score


__all__ = [
    "AuditEvidenceItem",
    "AuditEvidencePackage",
    "AvailabilityControl",
    "ComplianceAssessment",
    "ComplianceFramework",
    "ComplianceReport",
    "ComplianceStatus",
    "ComplianceViolation",
    "ConfidentialityControl",
    "DataClassification",
    "DataClassificationEntry",
    "HighRiskClassification",
    "HumanOversightLevel",
    "HumanOversightMechanism",
    "ProcessingIntegrityControl",
    "RiskContext",
    "RiskMitigation",
    "RiskRegisterEntry",
    "RiskSeverity",
    "TechnicalDocumentation",
    "ThreatCategory",
    "ThreatModel",
    "TransparencyRequirement",
]
