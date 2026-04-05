"""
ACGS-2 MACI Verifier - Role-Based Verification Pipeline
Constitutional Hash: 608508a9bd224290

Implements Multi-Agent Collaborative Intelligence (MACI) verification to bypass
Godel's incompleteness limitations through strict role separation:

- Executive agents: Propose actions (cannot validate own proposals)
- Legislative agents: Define and extract policies (cannot propose or validate)
- Judicial agents: Validate compliance (cannot propose or define policies)

Key Security Feature: No agent can validate its own outputs, preventing
self-referential paradoxes that could compromise constitutional integrity.

Performance Targets:
- P99 latency < 3ms for role validation
- 100% separation of concerns enforcement
- Audit trail for all verification decisions
"""

import asyncio
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from importlib import import_module

# Constitutional hash for immutable validation
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus._compat.constants import MACIRole
from enhanced_agent_bus.interfaces import RecommendationPlannerProtocol
from enhanced_agent_bus.maci_role_projection import project_to_verification_role
from enhanced_agent_bus.observability.structured_logging import get_logger

from ..governance_constants import (
    VERIFIER_BASE_RISK_SCORE,
    VERIFIER_JUDICIAL_CONFIDENCE_THRESHOLD,
    VERIFIER_LEGISLATIVE_CONFIDENCE_BASE,
    VERIFIER_LEGISLATIVE_CONFIDENCE_CAP,
    VERIFIER_LEGISLATIVE_CONFIDENCE_PER_RULE,
    VERIFIER_RISK_CROSS_JURISDICTION,
    VERIFIER_RISK_HIGH_IMPACT,
    VERIFIER_RISK_HUMAN_APPROVAL,
    VERIFIER_RISK_SENSITIVE_DATA,
)

logger = get_logger(__name__)
try:
    from acgs2_perf import fast_hash

    FAST_HASH_AVAILABLE = True
except ImportError:
    FAST_HASH_AVAILABLE = False

MACI_VERIFICATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)


class MACIAgentRole(Enum):
    """MACI Agent Roles with strict separation of concerns."""

    EXECUTIVE = "executive"
    LEGISLATIVE = "legislative"
    JUDICIAL = "judicial"
    MONITOR = "monitor"
    AUDITOR = "auditor"

    @classmethod
    def parse(cls, value: "MACIAgentRole | MACIRole | str") -> "MACIAgentRole":
        """Parse verifier roles from verifier-native or canonical MACI roles."""
        if isinstance(value, cls):
            return value

        projected_role = project_to_verification_role(value)
        if projected_role is not None:
            return cls(projected_role)

        if isinstance(value, str):
            return cls(value.strip().lower())

        raise ValueError(f"Unsupported MACI verifier role: {value!r}")


class VerificationPhase(Enum):
    """Phases in the MACI verification pipeline."""

    PROPOSAL = "proposal"
    POLICY_EXTRACTION = "policy_extraction"
    COMPLIANCE_CHECK = "compliance_check"
    JUDGMENT = "judgment"
    EXECUTION = "execution"
    AUDIT = "audit"


class VerificationStatus(Enum):
    """Status of verification operations."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"


@dataclass
class MACIVerificationContext:
    """Context for MACI verification operations."""

    verification_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str | None = None
    tenant_id: str = "default"
    initiator_agent_id: str = ""
    target_output_id: str | None = None
    decision_context: JSONDict = field(default_factory=dict)
    policy_context: JSONDict = field(default_factory=dict)
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    timeout_ms: int = 5000

    def to_dict(self) -> JSONDict:
        """Convert context to dictionary for serialization."""
        return {
            "verification_id": self.verification_id,
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "initiator_agent_id": self.initiator_agent_id,
            "target_output_id": self.target_output_id,
            "decision_context": self.decision_context,
            "policy_context": self.policy_context,
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
            "created_at": self.created_at.isoformat(),
            "timeout_ms": self.timeout_ms,
        }

    def generate_context_hash(self) -> str:
        """Generate hash for context integrity verification."""
        content = f"{self.verification_id}:{self.session_id}:{self.tenant_id}"
        content += f":{self.constitutional_hash}:{self.created_at.isoformat()}"
        if FAST_HASH_AVAILABLE:
            return f"{fast_hash(content):016x}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class AgentVerificationRecord:
    """Record of agent participation in verification."""

    agent_id: str
    role: MACIAgentRole
    phase: VerificationPhase
    action: str
    input_hash: str
    output_hash: str
    confidence: float
    reasoning: str
    evidence: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    duration_ms: float = 0.0
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert record to dictionary."""
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "phase": self.phase.value,
            "action": self.action,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "evidence": self.evidence,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class MACIVerificationResult:
    """Result of MACI verification pipeline execution."""

    verification_id: str
    is_compliant: bool
    confidence: float
    status: VerificationStatus
    violations: list[JSONDict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    agent_records: list[AgentVerificationRecord] = field(default_factory=list)
    executive_decision: JSONDict | None = None
    legislative_rules: JSONDict | None = None
    judicial_judgment: JSONDict | None = None
    total_duration_ms: float = 0.0
    constitutional_hash: str = CONSTITUTIONAL_HASH
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    audit_trail: list[JSONDict] = field(default_factory=list)

    def to_dict(self) -> JSONDict:
        """Convert result to dictionary."""
        return {
            "verification_id": self.verification_id,
            "is_compliant": self.is_compliant,
            "confidence": self.confidence,
            "status": self.status.value,
            "violations": self.violations,
            "recommendations": self.recommendations,
            "agent_records": [r.to_dict() for r in self.agent_records],
            "executive_decision": self.executive_decision,
            "legislative_rules": self.legislative_rules,
            "judicial_judgment": self.judicial_judgment,
            "total_duration_ms": self.total_duration_ms,
            "constitutional_hash": self.constitutional_hash,
            "timestamp": self.timestamp.isoformat(),
            "audit_trail": self.audit_trail,
        }

    def add_audit_entry(self, entry: JSONDict) -> None:
        """Add entry to audit trail."""
        entry["timestamp"] = datetime.now(UTC).isoformat()
        entry["constitutional_hash"] = self.constitutional_hash
        self.audit_trail.append(entry)


# Role permission matrix - defines what each role can do
ROLE_PERMISSIONS: dict[MACIAgentRole, set[VerificationPhase]] = {
    MACIAgentRole.EXECUTIVE: {VerificationPhase.PROPOSAL, VerificationPhase.EXECUTION},
    MACIAgentRole.LEGISLATIVE: {VerificationPhase.POLICY_EXTRACTION},
    MACIAgentRole.JUDICIAL: {VerificationPhase.COMPLIANCE_CHECK, VerificationPhase.JUDGMENT},
    MACIAgentRole.MONITOR: {VerificationPhase.AUDIT},
    MACIAgentRole.AUDITOR: {VerificationPhase.AUDIT},
}

# Cross-role validation constraints - who can validate whom
VALIDATION_CONSTRAINTS: dict[MACIAgentRole, set[MACIAgentRole]] = {
    MACIAgentRole.JUDICIAL: {MACIAgentRole.EXECUTIVE, MACIAgentRole.LEGISLATIVE},
    MACIAgentRole.AUDITOR: {MACIAgentRole.MONITOR, MACIAgentRole.JUDICIAL},
}


class MACIAgentBase:
    """Base class for MACI agents with common functionality."""

    def __init__(self, agent_id: str, role: MACIAgentRole | MACIRole | str):
        self.agent_id = agent_id
        self.role = MACIAgentRole.parse(role)
        self.output_registry: dict[str, str] = {}  # output_id -> hash
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def register_output(self, output_id: str, output_data: object) -> str:
        """Register an output and return its hash."""
        content = f"{self.agent_id}:{output_id}:{output_data!s}"
        if FAST_HASH_AVAILABLE:
            output_hash = f"{fast_hash(content):016x}"
        else:
            output_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        self.output_registry[output_id] = output_hash
        return output_hash

    def owns_output(self, output_id: str) -> bool:
        """Check if this agent produced the given output."""
        return output_id in self.output_registry

    def can_perform_phase(self, phase: VerificationPhase) -> bool:
        """Check if agent can perform the given verification phase."""
        return phase in ROLE_PERMISSIONS.get(self.role, set())

    def can_validate_role(self, target_role: MACIAgentRole) -> bool:
        """Check if this agent can validate outputs from target role."""
        return target_role in VALIDATION_CONSTRAINTS.get(self.role, set())


class ExecutiveAgent(MACIAgentBase):
    """
    Executive Agent: Proposes actions without self-validation capability.

    Focuses on:
    - Proposing governance decisions
    - Risk assessment and impact evaluation
    - Implementation planning
    - Cannot validate its own proposals (Godel bypass prevention)
    """

    def __init__(self, agent_id: str = "executive-001"):
        super().__init__(agent_id, MACIAgentRole.EXECUTIVE)

    async def propose_decision(
        self,
        action: str,
        context: JSONDict,
        impact_assessment: JSONDict | None = None,
    ) -> tuple[JSONDict, str]:
        """
        Propose a governance decision.

        Returns:
            Tuple of (decision_data, output_id)
        """
        output_id = f"exec-{str(uuid.uuid4())[:8]}"

        # Assess risks and impacts
        risk_score = await self._assess_risks(context)
        impact = impact_assessment or await self._evaluate_impact(context)

        decision = {
            "output_id": output_id,
            "agent_id": self.agent_id,
            "role": self.role.value,
            "action": action,
            "context": context,
            "risk_assessment": {
                "score": risk_score,
                "factors": self._extract_risk_factors(context),
            },
            "impact_evaluation": impact,
            "implementation_plan": self._create_implementation_plan(action),
            "proposed_at": datetime.now(UTC).isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }

        # Register output
        self.register_output(output_id, decision)

        logger.info(f"Executive agent {self.agent_id} proposed decision: {output_id}")
        return decision, output_id

    async def _assess_risks(self, context: JSONDict) -> float:
        """Assess risks in the decision context."""
        risk_score = VERIFIER_BASE_RISK_SCORE

        if context.get("involves_sensitive_data"):
            risk_score += VERIFIER_RISK_SENSITIVE_DATA
        if context.get("crosses_jurisdictions"):
            risk_score += VERIFIER_RISK_CROSS_JURISDICTION
        if context.get("high_impact"):
            risk_score += VERIFIER_RISK_HIGH_IMPACT
        if context.get("requires_human_approval"):
            risk_score += VERIFIER_RISK_HUMAN_APPROVAL

        return min(1.0, risk_score)

    async def _evaluate_impact(self, context: JSONDict) -> JSONDict:
        """Evaluate the impact of the decision."""
        return {
            "scope": context.get("scope", "local"),
            "stakeholders": context.get("stakeholders", []),
            "reversibility": context.get("reversibility", "reversible"),
            "estimated_duration": context.get("duration", "immediate"),
        }

    def _extract_risk_factors(self, context: JSONDict) -> list[str]:
        """Extract risk factors from context."""
        factors = []
        if context.get("involves_sensitive_data"):
            factors.append("sensitive_data_involved")
        if context.get("high_impact"):
            factors.append("high_impact_action")
        if context.get("emergency"):
            factors.append("emergency_condition")
        return factors

    def _create_implementation_plan(self, action: str) -> JSONDict:
        """Create an implementation plan for the action."""
        return {
            "steps": ["validate", "execute", "monitor", "audit"],
            "rollback_available": True,
            "monitoring_required": True,
        }


class LegislativeAgent(MACIAgentBase):
    """
    Legislative Agent: Extracts and defines policies.

    Focuses on:
    - Extracting relevant constitutional rules
    - Defining policy constraints
    - Establishing precedence order
    - Cannot propose or validate (Godel bypass prevention)
    """

    def __init__(self, agent_id: str = "legislative-001"):
        super().__init__(agent_id, MACIAgentRole.LEGISLATIVE)
        self.policy_registry: dict[str, JSONDict] = {}
        self.core_principles = [
            "Maximize beneficial impact while minimizing harm",
            "Ensure transparency and accountability",
            "Maintain constitutional integrity",
            "Respect stakeholder rights and interests",
            "Enable adaptive governance within bounds",
        ]

    async def extract_rules(
        self,
        decision: JSONDict,
        context: MACIVerificationContext,
    ) -> tuple[JSONDict, str]:
        """
        Extract relevant constitutional rules for a decision.

        Returns:
            Tuple of (rules_data, output_id)
        """
        output_id = f"legis-{str(uuid.uuid4())[:8]}"

        # Extract relevant rules based on decision action
        action = decision.get("action", "")
        relevant_rules = await self._extract_relevant_rules(action, context)
        principles = await self._identify_principles(decision)
        constraints = await self._establish_constraints(decision, context)
        precedence = self._determine_precedence(relevant_rules)

        rules_data = {
            "output_id": output_id,
            "agent_id": self.agent_id,
            "role": self.role.value,
            "decision_id": decision.get("output_id"),
            "rules": relevant_rules,
            "principles": principles,
            "constraints": constraints,
            "precedence_order": precedence,
            "extracted_at": datetime.now(UTC).isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }

        # Register output
        self.register_output(output_id, rules_data)

        logger.info(f"Legislative agent {self.agent_id} extracted {len(relevant_rules)} rules")
        return rules_data, output_id

    async def _extract_relevant_rules(
        self,
        action: str,
        context: MACIVerificationContext,
    ) -> list[JSONDict]:
        """Extract rules relevant to the action."""
        rules = []
        action_lower = action.lower()

        # Policy enforcement rules
        if "policy" in action_lower or "enforce" in action_lower:
            rules.extend(
                [
                    {
                        "rule_id": "policy_integrity",
                        "description": "Policies must maintain constitutional compliance",
                        "severity": "critical",
                        "scope": "all_policies",
                    },
                    {
                        "rule_id": "impact_assessment_required",
                        "description": "All policy changes require impact assessment",
                        "severity": "high",
                        "scope": "policy_changes",
                    },
                ]
            )

        # Access control rules
        if "access" in action_lower or "permission" in action_lower:
            rules.extend(
                [
                    {
                        "rule_id": "least_privilege",
                        "description": "Access must follow principle of least privilege",
                        "severity": "critical",
                        "scope": "access_grants",
                    },
                    {
                        "rule_id": "audit_trail_required",
                        "description": "All access changes must be auditable",
                        "severity": "high",
                        "scope": "access_operations",
                    },
                ]
            )

        # Data protection rules
        if context.decision_context.get("involves_sensitive_data"):
            rules.append(
                {
                    "rule_id": "data_protection",
                    "description": "Sensitive data must be protected according to classification",
                    "severity": "critical",
                    "scope": "data_operations",
                }
            )

        return rules

    async def _identify_principles(self, decision: JSONDict) -> list[str]:
        """Identify applicable constitutional principles."""
        principles = list(self.core_principles)

        # Add action-specific principles
        action = decision.get("action", "").lower()
        if "amendment" in action:
            principles.extend(
                [
                    "Constitutional amendments require broad consensus",
                    "Changes must preserve system stability",
                ]
            )

        return principles

    async def _establish_constraints(
        self,
        decision: JSONDict,
        context: MACIVerificationContext,
    ) -> list[str]:
        """Establish constraints for the decision."""
        constraints = [
            "Decision must not violate constitutional principles",
            "Implementation must be technically feasible",
            "Decision must be auditable and transparent",
        ]

        if context.decision_context.get("requires_human_approval"):
            constraints.append("Human approval required before execution")

        return constraints

    def _determine_precedence(self, rules: list[JSONDict]) -> list[str]:
        """Determine rule precedence order."""
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_rules = sorted(rules, key=lambda r: severity_order.get(r.get("severity", "low"), 3))
        return [r["rule_id"] for r in sorted_rules]


class JudicialAgent(MACIAgentBase):
    """
    Judicial Agent: Validates compliance and renders judgment.

    Focuses on:
    - Validating decisions against extracted rules
    - Rendering compliance judgments
    - Identifying violations
    - Cannot propose or extract rules (Godel bypass prevention)
    """

    def __init__(self, agent_id: str = "judicial-001"):
        super().__init__(agent_id, MACIAgentRole.JUDICIAL)
        self.confidence_threshold = VERIFIER_JUDICIAL_CONFIDENCE_THRESHOLD

    async def validate_compliance(
        self,
        decision: JSONDict,
        rules: JSONDict,
        context: MACIVerificationContext,
    ) -> tuple[JSONDict, str]:
        """
        Validate a decision against extracted rules.

        CRITICAL: Cannot validate outputs from same agent (Godel bypass prevention)

        Returns:
            Tuple of (judgment_data, output_id)
        """
        output_id = f"jud-{str(uuid.uuid4())[:8]}"

        # GODEL BYPASS PREVENTION: Check for self-validation attempt
        decision_agent = decision.get("agent_id")
        if decision_agent == self.agent_id:
            raise ValueError(
                f"Godel bypass prevention: Judicial agent {self.agent_id} "
                f"cannot validate its own output"
            )

        # Validate against rules in precedence order
        violations = []
        justifications = []
        confidence = 1.0

        for rule_id in rules.get("precedence_order", []):
            rule = next((r for r in rules.get("rules", []) if r["rule_id"] == rule_id), None)
            if rule:
                rule_result = await self._validate_against_rule(decision, rule, context)
                violations.extend(rule_result.get("violations", []))
                justifications.extend(rule_result.get("justifications", []))
                confidence = min(confidence, rule_result.get("confidence", 1.0))

        # Validate against principles
        principle_result = await self._validate_against_principles(
            decision, rules.get("principles", [])
        )
        violations.extend(principle_result.get("violations", []))
        justifications.extend(principle_result.get("justifications", []))

        # Check constraints
        constraint_violations = await self._check_constraints(
            decision, rules.get("constraints", [])
        )
        violations.extend(constraint_violations)

        # Determine compliance
        is_compliant = len(violations) == 0 and confidence >= self.confidence_threshold

        judgment = {
            "output_id": output_id,
            "agent_id": self.agent_id,
            "role": self.role.value,
            "decision_id": decision.get("output_id"),
            "rules_id": rules.get("output_id"),
            "is_compliant": is_compliant,
            "confidence": confidence,
            "violations": violations,
            "justifications": justifications,
            "judgment_reasoning": self._generate_reasoning(is_compliant, confidence, violations),
            "judged_at": datetime.now(UTC).isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }

        # Register output
        self.register_output(output_id, judgment)

        logger.info(
            f"Judicial agent {self.agent_id} rendered judgment: "
            f"{'COMPLIANT' if is_compliant else 'NON-COMPLIANT'} (confidence: {confidence:.2f})"
        )
        return judgment, output_id

    async def _validate_against_rule(
        self,
        decision: JSONDict,
        rule: JSONDict,
        context: MACIVerificationContext,
    ) -> JSONDict:
        """Validate decision against a specific rule."""
        violations = []
        justifications = []
        confidence = 1.0

        rule_id = rule["rule_id"]
        decision_context = decision.get("context", {})

        if rule_id == "policy_integrity":
            if not decision_context.get("policy_compliant", True):
                violations.append(
                    {
                        "rule_id": rule_id,
                        "severity": rule["severity"],
                        "description": "Decision violates policy integrity",
                    }
                )
                confidence = 0.3

        elif rule_id == "impact_assessment_required":
            if not decision.get("impact_evaluation"):
                violations.append(
                    {
                        "rule_id": rule_id,
                        "severity": rule["severity"],
                        "description": "Impact assessment missing",
                    }
                )
                confidence = 0.7

        elif rule_id == "least_privilege":
            if decision_context.get("excessive_permissions"):
                violations.append(
                    {
                        "rule_id": rule_id,
                        "severity": rule["severity"],
                        "description": "Violates principle of least privilege",
                    }
                )
                confidence = 0.4

        elif rule_id == "audit_trail_required":
            if not decision_context.get("auditable", True):
                violations.append(
                    {
                        "rule_id": rule_id,
                        "severity": rule["severity"],
                        "description": "Decision must be auditable",
                    }
                )
                confidence = 0.6

        elif rule_id == "data_protection":
            if decision_context.get("data_unprotected"):
                violations.append(
                    {
                        "rule_id": rule_id,
                        "severity": rule["severity"],
                        "description": "Sensitive data not properly protected",
                    }
                )
                confidence = 0.2

        if not violations:
            justifications.append(f"Decision complies with rule: {rule['description']}")

        return {
            "violations": violations,
            "justifications": justifications,
            "confidence": confidence,
        }

    async def _validate_against_principles(
        self,
        decision: JSONDict,
        principles: list[str],
    ) -> JSONDict:
        """Validate decision against constitutional principles."""
        violations = []
        justifications = []

        context = decision.get("context", {})

        for principle in principles:
            principle_lower = principle.lower()

            if "harm" in principle_lower:
                if context.get("potential_harm"):
                    violations.append(
                        {
                            "principle": principle,
                            "severity": "high",
                            "description": f"May violate: {principle}",
                        }
                    )

            if not violations:
                justifications.append(f"Aligned with: {principle[:50]}...")

        return {
            "violations": violations,
            "justifications": justifications,
        }

    async def _check_constraints(
        self,
        decision: JSONDict,
        constraints: list[str],
    ) -> list[JSONDict]:
        """Check decision against constraints."""
        violations = []
        context = decision.get("context", {})

        for constraint in constraints:
            constraint_lower = constraint.lower()

            if "technically feasible" in constraint_lower:
                if not context.get("technically_feasible", True):
                    violations.append(
                        {
                            "constraint": constraint,
                            "severity": "high",
                            "description": "Technical feasibility not confirmed",
                        }
                    )

            if "human approval" in constraint_lower:
                if context.get("requires_human_approval") and not context.get("human_approved"):
                    violations.append(
                        {
                            "constraint": constraint,
                            "severity": "critical",
                            "description": "Required human approval not obtained",
                        }
                    )

        return violations

    def _generate_reasoning(
        self,
        is_compliant: bool,
        confidence: float,
        violations: list[JSONDict],
    ) -> str:
        """Generate reasoning for the judgment."""
        if is_compliant:
            return f"Decision is COMPLIANT with confidence {confidence:.2f}"
        else:
            violation_count = len(violations)
            return (
                f"Decision is NON-COMPLIANT: {violation_count} violation(s) found, "
                f"confidence {confidence:.2f}"
            )


class MACIVerifier:
    """
    MACI Verification Pipeline: Complete role-based verification system.

    Implements the full MACI workflow:
    1. Executive proposes decisions
    2. Legislative extracts relevant rules
    3. Judicial validates compliance

    No agent validates its own output, bypassing Godel limitations.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        executive_agent: ExecutiveAgent | None = None,
        legislative_agent: LegislativeAgent | None = None,
        judicial_agent: JudicialAgent | None = None,
        recommendation_planner: RecommendationPlannerProtocol | None = None,
    ):
        self.executive = executive_agent or ExecutiveAgent()
        self.legislative = legislative_agent or LegislativeAgent()
        self.judicial = judicial_agent or JudicialAgent()
        if recommendation_planner is None:
            planner_module = import_module(
                "enhanced_agent_bus.verification_layer.recommendation_planner"
            )
            recommendation_planner = planner_module.MACIRemediationPlanner()
        self._recommendation_planner = recommendation_planner
        self.constitutional_hash = CONSTITUTIONAL_HASH
        self.verification_history: list[MACIVerificationResult] = []

        logger.info("Initialized MACI Verifier")
        logger.info(f"Constitutional Hash: {self.constitutional_hash}")

    async def verify(
        self,
        action: str,
        context: JSONDict,
        verification_context: MACIVerificationContext | None = None,
    ) -> MACIVerificationResult:
        """
        Execute full MACI verification pipeline.

        Args:
            action: The governance action to verify
            context: Decision context
            verification_context: Optional verification context

        Returns:
            Complete verification result with all agent records
        """
        start_time = datetime.now(UTC)

        ctx = verification_context or MACIVerificationContext(decision_context=context)

        result = MACIVerificationResult(
            verification_id=ctx.verification_id,
            is_compliant=False,
            confidence=0.0,
            status=VerificationStatus.IN_PROGRESS,
        )

        try:
            # Phase 1: Executive proposes decision
            decision, decision_id = await self._run_proposal_phase(action, context, ctx, result)

            # Phase 2: Legislative extracts rules
            rules, rules_id = await self._run_extraction_phase(decision, decision_id, ctx, result)

            # Phase 3: Judicial validates compliance
            judgment = await self._run_judgment_phase(
                decision, decision_id, rules, rules_id, ctx, result
            )

            # Finalize result
            result.is_compliant = judgment.get("is_compliant", False)
            result.confidence = judgment.get("confidence", 0.0)
            result.violations = judgment.get("violations", [])
            result.recommendations = self._recommendation_planner.generate_recommendations(
                judgment=judgment,
                decision=decision,
            )
            result.status = VerificationStatus.COMPLETED

        except MACI_VERIFICATION_ERRORS as e:
            logger.error(f"MACI verification failed: {e}")
            result.status = VerificationStatus.FAILED
            result.violations.append(
                {
                    "type": "verification_error",
                    "description": str(e),
                    "severity": "critical",
                }
            )
            result.add_audit_entry(
                {
                    "phase": "error",
                    "error": str(e),
                }
            )

        finally:
            end_time = datetime.now(UTC)
            result.total_duration_ms = (end_time - start_time).total_seconds() * 1000

            # Store in history
            self.verification_history.append(result)

            logger.info(
                f"MACI verification {result.verification_id}: "
                f"{'COMPLIANT' if result.is_compliant else 'NON-COMPLIANT'} "
                f"in {result.total_duration_ms:.2f}ms"
            )

        return result

    async def _run_proposal_phase(
        self,
        action: str,
        context: JSONDict,
        ctx: MACIVerificationContext,
        result: MACIVerificationResult,
    ) -> tuple[JSONDict, str]:
        """Execute Phase 1: Executive proposes decision."""
        result.add_audit_entry(
            {
                "phase": VerificationPhase.PROPOSAL.value,
                "agent": self.executive.agent_id,
                "action": "start_proposal",
            }
        )

        decision, decision_id = await self.executive.propose_decision(
            action=action,
            context=context,
        )
        result.executive_decision = decision

        exec_record = AgentVerificationRecord(
            agent_id=self.executive.agent_id,
            role=MACIAgentRole.EXECUTIVE,
            phase=VerificationPhase.PROPOSAL,
            action="propose_decision",
            input_hash=ctx.generate_context_hash(),
            output_hash=self.executive.output_registry.get(decision_id, ""),
            confidence=1.0 - decision.get("risk_assessment", {}).get("score", 0.5),
            reasoning=f"Proposed action: {action}",
            evidence=[f"Decision ID: {decision_id}"],
        )
        result.agent_records.append(exec_record)

        result.add_audit_entry(
            {
                "phase": VerificationPhase.PROPOSAL.value,
                "agent": self.executive.agent_id,
                "action": "complete_proposal",
                "output_id": decision_id,
            }
        )

        return decision, decision_id

    async def _run_extraction_phase(
        self,
        decision: JSONDict,
        decision_id: str,
        ctx: MACIVerificationContext,
        result: MACIVerificationResult,
    ) -> tuple[JSONDict, str]:
        """Execute Phase 2: Legislative extracts rules."""
        result.add_audit_entry(
            {
                "phase": VerificationPhase.POLICY_EXTRACTION.value,
                "agent": self.legislative.agent_id,
                "action": "start_extraction",
            }
        )

        rules, rules_id = await self.legislative.extract_rules(
            decision=decision,
            context=ctx,
        )
        result.legislative_rules = rules

        legis_record = AgentVerificationRecord(
            agent_id=self.legislative.agent_id,
            role=MACIAgentRole.LEGISLATIVE,
            phase=VerificationPhase.POLICY_EXTRACTION,
            action="extract_rules",
            input_hash=self.executive.output_registry.get(decision_id, ""),
            output_hash=self.legislative.output_registry.get(rules_id, ""),
            confidence=min(
                VERIFIER_LEGISLATIVE_CONFIDENCE_CAP,
                VERIFIER_LEGISLATIVE_CONFIDENCE_BASE
                + len(rules.get("rules", [])) * VERIFIER_LEGISLATIVE_CONFIDENCE_PER_RULE,
            ),
            reasoning=f"Extracted {len(rules.get('rules', []))} rules",
            evidence=[f"Rules ID: {rules_id}"],
        )
        result.agent_records.append(legis_record)

        result.add_audit_entry(
            {
                "phase": VerificationPhase.POLICY_EXTRACTION.value,
                "agent": self.legislative.agent_id,
                "action": "complete_extraction",
                "output_id": rules_id,
                "rule_count": len(rules.get("rules", [])),
            }
        )

        return rules, rules_id

    async def _run_judgment_phase(
        self,
        decision: JSONDict,
        decision_id: str,
        rules: JSONDict,
        rules_id: str,
        ctx: MACIVerificationContext,
        result: MACIVerificationResult,
    ) -> JSONDict:
        """Execute Phase 3: Judicial validates compliance."""
        result.add_audit_entry(
            {
                "phase": VerificationPhase.JUDGMENT.value,
                "agent": self.judicial.agent_id,
                "action": "start_judgment",
            }
        )

        judgment, judgment_id = await self.judicial.validate_compliance(
            decision=decision,
            rules=rules,
            context=ctx,
        )
        result.judicial_judgment = judgment

        jud_record = AgentVerificationRecord(
            agent_id=self.judicial.agent_id,
            role=MACIAgentRole.JUDICIAL,
            phase=VerificationPhase.JUDGMENT,
            action="validate_compliance",
            input_hash=f"{self.executive.output_registry.get(decision_id, '')}:{self.legislative.output_registry.get(rules_id, '')}",
            output_hash=self.judicial.output_registry.get(judgment_id, ""),
            confidence=judgment.get("confidence", 0.5),
            reasoning=judgment.get("judgment_reasoning", ""),
            evidence=judgment.get("justifications", []),
        )
        result.agent_records.append(jud_record)

        result.add_audit_entry(
            {
                "phase": VerificationPhase.JUDGMENT.value,
                "agent": self.judicial.agent_id,
                "action": "complete_judgment",
                "output_id": judgment_id,
                "is_compliant": judgment.get("is_compliant"),
            }
        )

        return judgment

    async def verify_cross_role_action(
        self,
        validator_agent_id: str,
        validator_role: MACIAgentRole | MACIRole | str,
        target_agent_id: str,
        target_role: MACIAgentRole | MACIRole | str,
        target_output_id: str,
    ) -> bool:
        """
        Verify if a cross-role validation is permitted.

        Implements Godel bypass prevention by ensuring:
        1. No agent validates its own output
        2. Only permitted roles can validate other roles

        Returns:
            True if validation is permitted, False otherwise
        """
        try:
            resolved_validator_role = MACIAgentRole.parse(validator_role)
            resolved_target_role = MACIAgentRole.parse(target_role)
        except ValueError as exc:
            logger.warning(f"Unsupported verifier role mapping: {exc}")
            return False

        # Self-validation check (Godel bypass prevention)
        if validator_agent_id == target_agent_id:
            logger.warning(
                f"Godel bypass prevention: Agent {validator_agent_id} "
                f"cannot validate its own output"
            )
            return False

        # Check role permissions
        permitted_targets = VALIDATION_CONSTRAINTS.get(resolved_validator_role, set())
        if resolved_target_role not in permitted_targets:
            logger.warning(
                f"Role constraint violation: {resolved_validator_role.value} "
                f"cannot validate {resolved_target_role.value}"
            )
            return False

        return True

    def get_verification_stats(self) -> JSONDict:
        """Get statistics about verification operations."""
        if not self.verification_history:
            return {"total_verifications": 0}

        total = len(self.verification_history)
        compliant = sum(1 for v in self.verification_history if v.is_compliant)
        avg_confidence = sum(v.confidence for v in self.verification_history) / total
        avg_duration = sum(v.total_duration_ms for v in self.verification_history) / total

        return {
            "total_verifications": total,
            "compliant_count": compliant,
            "compliance_rate": compliant / total,
            "average_confidence": avg_confidence,
            "average_duration_ms": avg_duration,
            "total_violations": sum(len(v.violations) for v in self.verification_history),
            "constitutional_hash": self.constitutional_hash,
        }

    def get_constitutional_hash(self) -> str:
        """Return the constitutional hash for validation."""
        return self.constitutional_hash  # type: ignore[no-any-return]


def create_maci_verifier(
    executive_id: str = "executive-001",
    legislative_id: str = "legislative-001",
    judicial_id: str = "judicial-001",
) -> MACIVerifier:
    """
    Factory function to create a configured MACI verifier.

    Args:
        executive_id: ID for executive agent
        legislative_id: ID for legislative agent
        judicial_id: ID for judicial agent

    Returns:
        Configured MACIVerifier instance
    """
    return MACIVerifier(
        executive_agent=ExecutiveAgent(executive_id),
        legislative_agent=LegislativeAgent(legislative_id),
        judicial_agent=JudicialAgent(judicial_id),
    )


__all__ = [
    "CONSTITUTIONAL_HASH",
    "ROLE_PERMISSIONS",
    "VALIDATION_CONSTRAINTS",
    "AgentVerificationRecord",
    "ExecutiveAgent",
    "JudicialAgent",
    "LegislativeAgent",
    "MACIAgentRole",
    "MACIVerificationContext",
    "MACIVerificationResult",
    "MACIVerifier",
    "VerificationPhase",
    "VerificationStatus",
    "create_maci_verifier",
]
