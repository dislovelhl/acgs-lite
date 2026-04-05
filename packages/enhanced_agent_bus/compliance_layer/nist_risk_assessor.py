"""
ACGS-2 NIST AI RMF Risk Assessor
Constitutional Hash: 608508a9bd224290

Implements NIST AI Risk Management Framework alignment for Layer 4.
Provides risk context identification, threat modeling, and risk register management.
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
    DataClassification,
    RiskContext,
    RiskMitigation,
    RiskRegisterEntry,
    RiskSeverity,
    ThreatCategory,
    ThreatModel,
)

logger = get_logger(__name__)


class NISTMAPFunction:
    """NIST AI RMF MAP function implementation.

    Manages AI system context and risk mapping.
    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self):
        self.constitutional_hash = CONSTITUTIONAL_HASH
        self._contexts: dict[str, RiskContext] = {}

    def establish_context(
        self,
        system_name: str,
        intended_purpose: str,
        data_types: list[DataClassification] | None = None,
        risk_tolerance: RiskSeverity = RiskSeverity.MEDIUM,
        regulatory_requirements: list[ComplianceFramework] | None = None,
    ) -> RiskContext:
        """Establish risk context for an AI system (MAP 1.1)."""
        context = RiskContext(
            context_id=f"ctx-{uuid.uuid4().hex[:8]}",
            system_name=system_name,
            intended_purpose=intended_purpose,
            data_types=data_types or [],
            risk_tolerance=risk_tolerance,
            regulatory_requirements=regulatory_requirements or [],
            constitutional_hash=self.constitutional_hash,
        )
        self._contexts[context.context_id] = context
        logger.info(f"[{self.constitutional_hash}] Established risk context: {context.context_id}")
        return context

    def get_context(self, context_id: str) -> RiskContext | None:
        """Retrieve risk context by ID."""
        return self._contexts.get(context_id)

    def list_contexts(self) -> list[RiskContext]:
        """List all established contexts."""
        return list(self._contexts.values())


class NISTGovernFunction:
    """NIST AI RMF GOVERN function implementation.

    Manages governance policies and accountability structures.
    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self):
        self.constitutional_hash = CONSTITUTIONAL_HASH
        self._policies: dict[str, JSONDict] = {}
        self._accountability: dict[str, str] = {}

    def register_policy(self, policy_id: str, policy_name: str, content: str) -> JSONDict:
        """Register a governance policy (GOVERN 1.1)."""
        policy = {
            "policy_id": policy_id,
            "policy_name": policy_name,
            "content": content,
            "created_at": datetime.now(UTC).isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }
        self._policies[policy_id] = policy
        return policy

    def assign_accountability(self, role: str, owner: str) -> None:
        """Assign accountability for a role (GOVERN 2.1)."""
        self._accountability[role] = owner
        logger.info(f"[{self.constitutional_hash}] Assigned {role} to {owner}")

    def get_accountability(self, role: str) -> str | None:
        """Get owner for a role."""
        return self._accountability.get(role)


class NISTRiskAssessor:
    """NIST AI RMF Risk Assessor - Main implementation.

    Provides comprehensive NIST AI RMF alignment including:
    - Risk context identification and assessment
    - Threat modeling integration
    - MAP function alignment
    - Risk register with mitigation tracking

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self):
        self.constitutional_hash = CONSTITUTIONAL_HASH
        self.map_function = NISTMAPFunction()
        self.govern_function = NISTGovernFunction()
        self._risk_register: dict[str, RiskRegisterEntry] = {}
        self._threats: dict[str, ThreatModel] = {}
        self._mitigations: dict[str, RiskMitigation] = {}
        self._initialized = False
        logger.info(f"[{self.constitutional_hash}] NISTRiskAssessor initialized")

    async def initialize(self) -> bool:
        """Initialize the risk assessor."""
        if self._initialized:
            return True
        self._initialize_default_threats()
        self._initialized = True
        return True

    def _initialize_default_threats(self) -> None:
        """Initialize default AI threat models."""
        default_threats = [
            ThreatModel(
                threat_id="THREAT-001",
                category=ThreatCategory.PROMPT_INJECTION,
                name="Prompt Injection Attack",
                description="Attacker injects malicious prompts to manipulate AI behavior",
                attack_vector="User input, API requests",
                likelihood=RiskSeverity.HIGH,
                impact=RiskSeverity.HIGH,
                affected_components=["API Gateway", "Agent Bus"],
                mitigations=["Input validation", "Constitutional constraints"],
                detection_methods=["Anomaly detection", "Pattern matching"],
            ),
            ThreatModel(
                threat_id="THREAT-002",
                category=ThreatCategory.CONSTITUTIONAL_BYPASS,
                name="Constitutional Bypass Attempt",
                description="Attempt to bypass constitutional governance controls",
                attack_vector="Malformed requests, timing attacks",
                likelihood=RiskSeverity.MEDIUM,
                impact=RiskSeverity.CRITICAL,
                affected_components=["Constitutional Engine", "MACI Enforcer"],
                mitigations=["Hash validation", "Multi-layer checks"],
                detection_methods=["Hash verification", "Audit logging"],
            ),
            ThreatModel(
                threat_id="THREAT-003",
                category=ThreatCategory.PRIVACY_LEAKAGE,
                name="PII Leakage",
                description="Unauthorized disclosure of personal information",
                attack_vector="Model outputs, logging",
                likelihood=RiskSeverity.MEDIUM,
                impact=RiskSeverity.HIGH,
                affected_components=["All services"],
                mitigations=["PII detection", "Data classification"],
                detection_methods=["PII scanning", "Audit review"],
            ),
        ]
        for threat in default_threats:
            threat.calculate_risk_score()
            self._threats[threat.threat_id] = threat

    async def assess_risk(
        self,
        system_name: str,
        context: RiskContext | None = None,
    ) -> ComplianceAssessment:
        """Perform NIST AI RMF risk assessment."""
        await self.initialize()
        start_time = time.perf_counter()

        if context is None:
            context = self.map_function.establish_context(
                system_name=system_name,
                intended_purpose="AI governance and compliance",
            )

        # Collect threats for this context
        relevant_threats = list(self._threats.values())

        # Create assessment
        assessment = ComplianceAssessment(
            assessment_id=f"nist-{uuid.uuid4().hex[:8]}",
            framework=ComplianceFramework.NIST_AI_RMF,
            system_name=system_name,
            assessor="acgs2-nist-risk-assessor",
            constitutional_hash=self.constitutional_hash,
        )

        # Assess controls based on threats
        assessment.controls_assessed = len(relevant_threats)
        for threat in relevant_threats:
            if threat.risk_score <= 0.4:
                assessment.controls_compliant += 1
            elif threat.risk_score <= 0.7:
                assessment.controls_partial += 1
            else:
                assessment.controls_non_compliant += 1

        assessment.calculate_score()

        # Add findings
        for threat in relevant_threats:
            if threat.risk_score > 0.5:
                assessment.findings.append(
                    f"{threat.name}: Risk score {threat.risk_score:.2f} requires attention"
                )

        # Add recommendations
        if assessment.controls_non_compliant > 0:
            assessment.recommendations.append(
                "Implement additional mitigations for high-risk threats"
            )

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"[{self.constitutional_hash}] NIST assessment completed: "
            f"score={assessment.compliance_score}%, latency={elapsed_ms:.2f}ms"
        )

        return assessment

    def add_threat(self, threat: ThreatModel) -> None:
        """Add a threat to the threat catalog."""
        threat.calculate_risk_score()
        self._threats[threat.threat_id] = threat
        logger.info(f"[{self.constitutional_hash}] Added threat: {threat.threat_id}")

    def add_mitigation(self, mitigation: RiskMitigation) -> None:
        """Add a mitigation strategy."""
        self._mitigations[mitigation.mitigation_id] = mitigation
        logger.info(f"[{self.constitutional_hash}] Added mitigation: {mitigation.mitigation_id}")

    def create_risk_register_entry(
        self,
        context: RiskContext,
        threats: list[ThreatModel] | None = None,
        mitigations: list[RiskMitigation] | None = None,
    ) -> RiskRegisterEntry:
        """Create a risk register entry."""
        entry = RiskRegisterEntry(
            entry_id=f"rre-{uuid.uuid4().hex[:8]}",
            risk_context=context,
            threats=threats or list(self._threats.values()),
            mitigations=mitigations or list(self._mitigations.values()),
            constitutional_hash=self.constitutional_hash,
        )
        entry.calculate_overall_risk()
        self._risk_register[entry.entry_id] = entry
        return entry

    def get_risk_register(self) -> dict[str, RiskRegisterEntry]:
        """Get the complete risk register."""
        return self._risk_register

    def get_threats(self) -> list[ThreatModel]:
        """Get all registered threats."""
        return list(self._threats.values())


# Singleton instance
_nist_risk_assessor: NISTRiskAssessor | None = None


def get_nist_risk_assessor() -> NISTRiskAssessor:
    """Get or create the singleton NISTRiskAssessor instance."""
    global _nist_risk_assessor
    if _nist_risk_assessor is None:
        _nist_risk_assessor = NISTRiskAssessor()
    return _nist_risk_assessor


def reset_nist_risk_assessor() -> None:
    """Reset the singleton instance (for testing)."""
    global _nist_risk_assessor
    _nist_risk_assessor = None


__all__ = [
    "NISTGovernFunction",
    "NISTMAPFunction",
    "NISTRiskAssessor",
    "get_nist_risk_assessor",
    "reset_nist_risk_assessor",
]
