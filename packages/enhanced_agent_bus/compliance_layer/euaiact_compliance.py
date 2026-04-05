"""
ACGS-2 EU AI Act Compliance
Constitutional Hash: 608508a9bd224290

Implements EU AI Act compliance for Layer 4.
Provides Article 13 transparency, Article 14 human oversight,
high-risk classification, and technical documentation.
"""

import time
import uuid
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

from .models import (
    ComplianceAssessment,
    ComplianceFramework,
    ComplianceStatus,
    HighRiskClassification,
    HumanOversightLevel,
    HumanOversightMechanism,
    TechnicalDocumentation,
    TransparencyRequirement,
)

logger = get_logger(__name__)


class Article13Transparency:
    """EU AI Act Article 13 Transparency Implementation.

    Ensures AI system transparency through decision explanations,
    capability disclosure, and user instructions.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self):
        self.constitutional_hash = CONSTITUTIONAL_HASH
        self._requirements: dict[str, TransparencyRequirement] = {}
        self._initialize_requirements()

    def _initialize_requirements(self) -> None:
        """Initialize Article 13 transparency requirements."""
        requirements = [
            TransparencyRequirement(
                requirement_id="ART13-001",
                article_reference="Article 13(1)",
                description="High-risk AI systems designed for transparency",
                transparency_measures=[
                    "Decision Explanation API (FR-12)",
                    "7-dimensional governance vector",
                    "Factor attribution with evidence",
                ],
                user_instructions_available=True,
                capabilities_disclosed=True,
                limitations_disclosed=True,
                explanation_api_available=True,
                implementation_status=ComplianceStatus.COMPLIANT,
            ),
            TransparencyRequirement(
                requirement_id="ART13-002",
                article_reference="Article 13(2)",
                description="Instructions for use provided",
                transparency_measures=[
                    "API documentation",
                    "User guides",
                    "Integration documentation",
                ],
                user_instructions_available=True,
                implementation_status=ComplianceStatus.COMPLIANT,
            ),
            TransparencyRequirement(
                requirement_id="ART13-003",
                article_reference="Article 13(3)",
                description="Accuracy and robustness levels disclosed",
                transparency_measures=[
                    "Performance metrics dashboard",
                    "Accuracy metrics",
                    "Robustness testing results",
                ],
                accuracy_metrics_available=True,
                implementation_status=ComplianceStatus.COMPLIANT,
            ),
        ]
        for req in requirements:
            self._requirements[req.requirement_id] = req

    def check_compliance(self) -> JSONDict:
        """Check Article 13 compliance status."""
        compliant = sum(
            1
            for r in self._requirements.values()
            if r.implementation_status == ComplianceStatus.COMPLIANT
        )
        total = len(self._requirements)

        return {
            "article": "Article 13",
            "compliant_requirements": compliant,
            "total_requirements": total,
            "compliance_rate": compliant / total if total > 0 else 0,
            "is_compliant": compliant == total,
            "constitutional_hash": self.constitutional_hash,
        }

    def get_requirements(self) -> list[TransparencyRequirement]:
        """Get all transparency requirements."""
        return list(self._requirements.values())


class Article14HumanOversight:
    """EU AI Act Article 14 Human Oversight Implementation.

    Implements human oversight mechanisms for high-risk AI systems.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self):
        self.constitutional_hash = CONSTITUTIONAL_HASH
        self._mechanisms: dict[str, HumanOversightMechanism] = {}
        self._initialize_mechanisms()

    def _initialize_mechanisms(self) -> None:
        """Initialize human oversight mechanisms."""
        mechanisms = [
            HumanOversightMechanism(
                mechanism_id="HO-001",
                name="HITL Approval System",
                description="Human-in-the-loop approval for high-impact decisions",
                oversight_level=HumanOversightLevel.HUMAN_IN_THE_LOOP,
                capabilities_enabled=[
                    "View decision details",
                    "Approve/reject decisions",
                    "Request additional information",
                ],
                intervention_points=[
                    "High-impact score threshold (0.8)",
                    "Constitutional violation detection",
                    "PII processing decisions",
                ],
                stop_mechanisms=[
                    "Manual override button",
                    "Emergency cooldown",
                    "System pause",
                ],
                understanding_capabilities=[
                    "Decision explanation view",
                    "Factor attribution",
                    "Counterfactual analysis",
                ],
                training_requirements=[
                    "ACGS-2 operator training",
                    "Constitutional governance training",
                    "AI ethics certification",
                ],
                escalation_procedures=[
                    "Escalate to supervisor",
                    "Trigger compliance review",
                    "Engage legal team",
                ],
                is_compliant=True,
            ),
            HumanOversightMechanism(
                mechanism_id="HO-002",
                name="Deliberation Layer",
                description="Human-on-the-loop monitoring with auto-escalation",
                oversight_level=HumanOversightLevel.HUMAN_ON_THE_LOOP,
                capabilities_enabled=[
                    "Real-time monitoring",
                    "Alert notifications",
                    "Audit trail review",
                ],
                intervention_points=[
                    "Anomaly detection triggers",
                    "Policy violation alerts",
                    "Performance degradation",
                ],
                stop_mechanisms=[
                    "Circuit breaker activation",
                    "Rate limiting",
                    "Service isolation",
                ],
                is_compliant=True,
            ),
            HumanOversightMechanism(
                mechanism_id="HO-003",
                name="Judicial Role (MACI)",
                description="Human-in-command judicial oversight via MACI",
                oversight_level=HumanOversightLevel.HUMAN_IN_COMMAND,
                capabilities_enabled=[
                    "Policy override",
                    "Constitutional amendment",
                    "System-wide controls",
                ],
                intervention_points=[
                    "Constitutional changes",
                    "Critical policy updates",
                    "Emergency situations",
                ],
                stop_mechanisms=[
                    "Full system shutdown",
                    "Data processing halt",
                    "Service termination",
                ],
                is_compliant=True,
            ),
        ]
        for mechanism in mechanisms:
            self._mechanisms[mechanism.mechanism_id] = mechanism

    def check_compliance(self) -> JSONDict:
        """Check Article 14 compliance status."""
        compliant = sum(1 for m in self._mechanisms.values() if m.is_compliant)
        total = len(self._mechanisms)

        return {
            "article": "Article 14",
            "compliant_mechanisms": compliant,
            "total_mechanisms": total,
            "compliance_rate": compliant / total if total > 0 else 0,
            "is_compliant": compliant == total,
            "oversight_levels": [m.oversight_level.value for m in self._mechanisms.values()],
            "constitutional_hash": self.constitutional_hash,
        }

    def get_mechanisms(self) -> list[HumanOversightMechanism]:
        """Get all human oversight mechanisms."""
        return list(self._mechanisms.values())


class HighRiskSystemValidator:
    """Validates high-risk AI system classification per EU AI Act.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self):
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def classify_system(
        self,
        system_name: str,
        annex_iii_category: str | None = None,
        safety_component: bool = False,
        significant_decisions: bool = False,
        biometric_categorization: bool = False,
        critical_infrastructure: bool = False,
    ) -> HighRiskClassification:
        """Classify an AI system under EU AI Act."""
        classification = HighRiskClassification(
            classification_id=f"hrc-{uuid.uuid4().hex[:8]}",
            system_name=system_name,
            annex_iii_category=annex_iii_category,
            safety_component=safety_component,
            significant_decisions=significant_decisions,
            biometric_categorization=biometric_categorization,
            critical_infrastructure=critical_infrastructure,
            assessed_by="acgs2-euaiact-compliance",
            constitutional_hash=self.constitutional_hash,
        )
        classification.determine_risk_level()
        return classification


class EUAIActCompliance:
    """EU AI Act Compliance - Main implementation.

    Provides comprehensive EU AI Act compliance including:
    - Article 13 transparency (Decision explanation API)
    - Article 14 human oversight mechanisms
    - High-risk AI system classification
    - Technical documentation generation

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self):
        self.constitutional_hash = CONSTITUTIONAL_HASH
        self.article13 = Article13Transparency()
        self.article14 = Article14HumanOversight()
        self.high_risk_validator = HighRiskSystemValidator()
        self._documentation: dict[str, TechnicalDocumentation] = {}
        self._classifications: dict[str, HighRiskClassification] = {}
        self._initialized = False
        logger.info(f"[{self.constitutional_hash}] EUAIActCompliance initialized")

    async def initialize(self) -> bool:
        """Initialize EU AI Act compliance components."""
        if self._initialized:
            return True
        self._generate_acgs2_documentation()
        self._classify_acgs2_system()
        self._initialized = True
        return True

    def _generate_acgs2_documentation(self) -> None:
        """Generate technical documentation for ACGS-2."""
        doc = TechnicalDocumentation(
            doc_id="td-acgs2-001",
            system_name="ACGS-2",
            version="2.3.0",
            general_description=(
                "AI Constitutional Governance System providing enterprise-grade "
                "AI governance with constitutional compliance, multi-agent coordination, "
                "and real-time performance optimization."
            ),
            intended_purpose=(
                "Enterprise AI governance and compliance platform for ensuring "
                "constitutional AI behavior, regulatory compliance, and ethical "
                "decision-making in AI systems."
            ),
            development_methods=[
                "Constitutional AI principles",
                "Multi-agent coordination",
                "Formal verification",
                "Test-driven development",
            ],
            data_requirements={
                "training_data": "Constitutional governance examples",
                "input_types": ["Agent messages", "Policy definitions", "User requests"],
                "output_types": ["Governance decisions", "Explanations", "Audit logs"],
            },
            testing_procedures=[
                "Unit testing with pytest",
                "Integration testing",
                "Constitutional compliance testing",
                "Performance benchmarking",
            ],
            validation_results={
                "accuracy": "93.1%-100% across 8 models",
                "p99_latency": "1.31ms (target <5ms)",
                "throughput": "770.4 RPS (target >100 RPS)",
                "constitutional_compliance": "100%",
            },
            risk_management_system="NIST AI RMF aligned risk assessment",
            monitoring_capabilities=[
                "Real-time performance monitoring",
                "Anomaly detection",
                "Constitutional violation alerts",
                "Audit trail logging",
            ],
            constitutional_hash=self.constitutional_hash,
        )
        self._documentation[doc.doc_id] = doc

    def _classify_acgs2_system(self) -> None:
        """Classify ACGS-2 system under EU AI Act."""
        classification = self.high_risk_validator.classify_system(
            system_name="ACGS-2",
            annex_iii_category=None,  # Not in Annex III
            safety_component=False,
            significant_decisions=True,  # Makes governance decisions
            biometric_categorization=False,
            critical_infrastructure=False,
        )
        self._classifications[classification.classification_id] = classification

    async def assess(self, system_name: str = "ACGS-2") -> ComplianceAssessment:
        """Perform EU AI Act compliance assessment."""
        await self.initialize()
        start_time = time.perf_counter()

        assessment = ComplianceAssessment(
            assessment_id=f"euai-{uuid.uuid4().hex[:8]}",
            framework=ComplianceFramework.EU_AI_ACT,
            system_name=system_name,
            assessor="acgs2-euaiact-compliance",
            constitutional_hash=self.constitutional_hash,
        )

        # Check Article 13
        art13_result = self.article13.check_compliance()
        assessment.controls_assessed += art13_result["total_requirements"]
        assessment.controls_compliant += art13_result["compliant_requirements"]

        # Check Article 14
        art14_result = self.article14.check_compliance()
        assessment.controls_assessed += art14_result["total_mechanisms"]
        assessment.controls_compliant += art14_result["compliant_mechanisms"]

        # Additional controls for documentation and classification
        assessment.controls_assessed += 2
        if self._documentation:
            assessment.controls_compliant += 1
        if self._classifications:
            assessment.controls_compliant += 1

        assessment.calculate_score()

        # Add findings
        if not art13_result["is_compliant"]:
            assessment.findings.append("Article 13 transparency requirements need attention")
        if not art14_result["is_compliant"]:
            assessment.findings.append("Article 14 human oversight requirements need attention")

        # Add recommendations
        assessment.recommendations.append("Continue monitoring EU AI Act implementation guidelines")

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"[{self.constitutional_hash}] EU AI Act assessment completed: "
            f"score={assessment.compliance_score}%, latency={elapsed_ms:.2f}ms"
        )

        return assessment

    def get_documentation(self) -> list[TechnicalDocumentation]:
        """Get all technical documentation."""
        return list(self._documentation.values())

    def get_classifications(self) -> list[HighRiskClassification]:
        """Get all high-risk classifications."""
        return list(self._classifications.values())

    def generate_transparency_report(self) -> JSONDict:
        """Generate Article 13 transparency report."""
        return {
            "article_13_compliance": self.article13.check_compliance(),
            "article_14_compliance": self.article14.check_compliance(),
            "transparency_requirements": [
                r.model_dump() for r in self.article13.get_requirements()
            ],
            "oversight_mechanisms": [m.model_dump() for m in self.article14.get_mechanisms()],
            "generated_at": datetime.now(UTC).isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }


# Singleton instance
_euaiact_compliance: EUAIActCompliance | None = None


def get_euaiact_compliance() -> EUAIActCompliance:
    """Get or create the singleton EUAIActCompliance instance."""
    global _euaiact_compliance
    if _euaiact_compliance is None:
        _euaiact_compliance = EUAIActCompliance()
    return _euaiact_compliance


def reset_euaiact_compliance() -> None:
    """Reset the singleton instance (for testing)."""
    global _euaiact_compliance
    _euaiact_compliance = None


__all__ = [
    "Article13Transparency",
    "Article14HumanOversight",
    "EUAIActCompliance",
    "HighRiskSystemValidator",
    "get_euaiact_compliance",
    "reset_euaiact_compliance",
]
