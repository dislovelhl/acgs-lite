"""
ACGS-2 Compliance Layer - Layer 4: Compliance & Transparency
Constitutional Hash: 608508a9bd224290

Implements institutional-grade regulatory alignment for:
- NIST AI RMF (Risk Management Framework)
- SOC 2 Type II Compliance
- EU AI Act High-Risk Compliance

Phase 2.1 Layer 4 Requirements from docs/ROADMAP_2025.md
"""

__version__ = "1.0.0"

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

__constitutional_hash__ = CONSTITUTIONAL_HASH

from .compliance_reporter import (
    ComplianceDashboard,
    ComplianceMetrics,
    ComplianceReporter,
    UnifiedComplianceReport,
    get_compliance_reporter,
    reset_compliance_reporter,
)
from .decision_explainer import (
    DecisionExplainer,
    ExplanationContext,
    ExplanationResult,
    FactorContribution,
    get_decision_explainer,
    reset_decision_explainer,
)
from .euaiact_compliance import (
    Article13Transparency,
    Article14HumanOversight,
    EUAIActCompliance,
    HighRiskSystemValidator,
    get_euaiact_compliance,
    reset_euaiact_compliance,
)
from .models import (
    AuditEvidenceItem,
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
from .nist_risk_assessor import (
    NISTGovernFunction,
    NISTMAPFunction,
    NISTRiskAssessor,
    get_nist_risk_assessor,
    reset_nist_risk_assessor,
)
from .soc2_auditor import (
    SOC2Auditor,
    SOC2ControlValidator,
    SOC2EvidenceCollector,
    get_soc2_auditor,
    reset_soc2_auditor,
)

COMPLIANCE_LAYER_AVAILABLE = True
NIST_RMF_ENABLED = True
SOC2_ENABLED = True
EUAIACT_ENABLED = True

__all__ = [
    "COMPLIANCE_LAYER_AVAILABLE",
    "CONSTITUTIONAL_HASH",
    "EUAIACT_ENABLED",
    "NIST_RMF_ENABLED",
    "SOC2_ENABLED",
    "Article13Transparency",
    "Article14HumanOversight",
    "AuditEvidenceItem",
    "ComplianceAssessment",
    "ComplianceDashboard",
    "ComplianceFramework",
    "ComplianceMetrics",
    "ComplianceReport",
    "ComplianceReporter",
    "ComplianceStatus",
    "ComplianceViolation",
    "ConfidentialityControl",
    "DataClassification",
    "DataClassificationEntry",
    "DecisionExplainer",
    "EUAIActCompliance",
    "ExplanationContext",
    "ExplanationResult",
    "FactorContribution",
    "HighRiskClassification",
    "HighRiskSystemValidator",
    "HumanOversightLevel",
    "HumanOversightMechanism",
    "NISTGovernFunction",
    "NISTMAPFunction",
    "NISTRiskAssessor",
    "ProcessingIntegrityControl",
    "RiskContext",
    "RiskMitigation",
    "RiskRegisterEntry",
    "RiskSeverity",
    "SOC2Auditor",
    "SOC2ControlValidator",
    "SOC2EvidenceCollector",
    "TechnicalDocumentation",
    "ThreatCategory",
    "ThreatModel",
    "TransparencyRequirement",
    "UnifiedComplianceReport",
    "get_compliance_reporter",
    "get_decision_explainer",
    "get_euaiact_compliance",
    "get_nist_risk_assessor",
    "get_soc2_auditor",
    "reset_compliance_reporter",
    "reset_decision_explainer",
    "reset_euaiact_compliance",
    "reset_nist_risk_assessor",
    "reset_soc2_auditor",
]
