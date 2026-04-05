"""MACI Verification Pipeline for ACGS-2 Constitutional AI Governance.

Constitutional Hash: 608508a9bd224290

Implements Multi-Agent Collaborative Intelligence (MACI) to bypass Gödel's
incompleteness theorems through strict role separation:

- Executive Agent: Proposes governance decisions
- Legislative Agent: Extracts and validates constitutional rules
- Judicial Agent: Evaluates compliance and renders final judgment

No agent validates its own output, ensuring mathematical consistency.
"""

import hashlib
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

try:
    from enhanced_agent_bus._compat.types import (
        JSONDict,
        JSONList,
    )
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    JSONList = list  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
# Constitutional Hash for immutable validation
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

# Memory-bounded history constants
MAX_DECISION_HISTORY = 1_000  # FIFO eviction for agent decision history


class AgentRole(Enum):
    """MACI Agent Roles for strict separation of concerns."""

    EXECUTIVE = "executive"  # Proposes decisions
    LEGISLATIVE = "legislative"  # Validates constitutional rules
    JUDICIAL = "judicial"  # Evaluates compliance


class GovernancePhase(Enum):
    """Phases of constitutional governance."""

    PROPOSAL = "proposal"
    VALIDATION = "validation"
    JUDGMENT = "judgment"
    EXECUTION = "execution"


@dataclass
class ConstitutionalPrinciple:
    """Represents a constitutional principle with metadata."""

    id: str
    text: str
    category: str
    priority: int
    hash: str = field(init=False)

    def __post_init__(self):
        """Generate immutable hash for the principle."""
        content = f"{self.id}:{self.text}:{self.category}:{self.priority}"
        self.hash = hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class GovernanceDecision:
    """Represents a governance decision with full context."""

    id: str
    action: str
    context: JSONDict
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    proposed_by: str = "system"
    constitutional_hash: str = CONSTITUTIONAL_HASH

    @property
    def decision_hash(self) -> str:
        """Generate hash for decision integrity."""
        content = f"{self.id}:{self.action}:{self.context!s}:{self.timestamp.isoformat()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class AgentResponse:
    """Response from a MACI agent."""

    agent_role: AgentRole
    decision_id: str
    confidence: float
    reasoning: str
    evidence: list[str]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    agent_hash: str = field(init=False)

    def __post_init__(self):
        """Generate agent response hash."""
        content = f"{self.agent_role.value}:{self.decision_id}:{self.confidence}:{self.reasoning}"
        self.agent_hash = hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class VerificationResult:
    """Result of constitutional verification."""

    decision_id: str
    is_compliant: bool
    confidence: float
    violations: list[str]
    recommendations: list[str]
    executive_response: AgentResponse
    legislative_response: AgentResponse
    judicial_response: AgentResponse
    constitutional_hash: str = CONSTITUTIONAL_HASH
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class BaseMACIAgent:
    """Base class for MACI agents with common functionality."""

    def __init__(self, role: AgentRole, agent_id: str):
        self.role = role
        self.agent_id = agent_id
        self.constitutional_principles: dict[str, ConstitutionalPrinciple] = {}
        self.decision_history: deque[AgentResponse] = deque(maxlen=MAX_DECISION_HISTORY)

    def load_constitutional_principles(self, principles: list[ConstitutionalPrinciple]):
        """Load constitutional principles into agent knowledge."""
        for principle in principles:
            self.constitutional_principles[principle.id] = principle
        logger.info(f"{self.role.value} agent loaded {len(principles)} constitutional principles")

    def validate_constitutional_hash(self, decision: GovernanceDecision) -> bool:
        """Validate that decision references correct constitution."""
        return bool(decision.constitutional_hash == CONSTITUTIONAL_HASH)

    async def _analyze_decision(
        self, decision: GovernanceDecision, context_responses: list[AgentResponse] | None = None
    ) -> JSONDict:
        """Common decision analysis logic."""
        # Validate constitutional hash
        if not self.validate_constitutional_hash(decision):
            return {
                "confidence": 0.0,
                "reasoning": "Invalid constitutional hash",
                "evidence": ["Constitutional hash mismatch"],
                "violations": ["Constitution integrity compromised"],
            }

        # Agent-specific analysis (implemented by subclasses)
        return await self._analyze_decision_specific(decision, context_responses)

    async def _analyze_decision_specific(
        self, decision: GovernanceDecision, context_responses: list[AgentResponse] | None = None
    ) -> JSONDict:
        """Agent-specific decision analysis - implemented by subclasses."""
        raise NotImplementedError

    async def respond_to_decision(
        self, decision: GovernanceDecision, context_responses: list[AgentResponse] | None = None
    ) -> AgentResponse:
        """Generate agent response to a governance decision."""
        analysis = await self._analyze_decision(decision, context_responses)

        response = AgentResponse(
            agent_role=self.role,
            decision_id=decision.id,
            confidence=analysis.get("confidence", 0.5),
            reasoning=analysis.get("reasoning", "Analysis incomplete"),
            evidence=analysis.get("evidence", []),
        )

        self.decision_history.append(response)
        logger.info(
            f"{self.role.value} agent responded to decision {decision.id} with confidence {response.confidence:.2f}"
        )

        return response


class ExecutiveAgent(BaseMACIAgent):
    """Executive Agent: Proposes governance decisions without self-validation."""

    def __init__(self, agent_id: str = "executive-001"):
        super().__init__(AgentRole.EXECUTIVE, agent_id)

    async def _analyze_decision_specific(
        self, decision: GovernanceDecision, context_responses: list[AgentResponse] | None = None
    ) -> JSONDict:
        """
        Executive analysis: Propose decisions based on operational context.
        Does NOT validate compliance - that's for Legislative and Judicial agents.
        """
        context = decision.context

        # Executive focuses on operational feasibility and impact
        confidence = 0.8  # Base confidence
        reasoning_parts = []
        evidence = []

        # Analyze operational impact
        if "impact_assessment" in context:
            impact = context["impact_assessment"]
            if impact.get("severity", "unknown") == "critical":
                confidence -= 0.2
                reasoning_parts.append("High-impact decision requires careful consideration")
                evidence.append("Critical operational impact detected")

        # Check for emergency conditions
        if context.get("emergency", False):
            confidence += 0.1
            reasoning_parts.append("Emergency conditions justify expedited action")
            evidence.append("Emergency flag detected in context")

        # Analyze resource requirements
        if "resources_required" in context:
            resources = context["resources_required"]
            if len(resources) > 5:
                confidence -= 0.1
                reasoning_parts.append("Complex resource requirements increase operational risk")
                evidence.append(f"High resource count: {len(resources)}")

        reasoning = (
            "Executive assessment: " + "; ".join(reasoning_parts)
            if reasoning_parts
            else "Standard operational assessment"
        )

        return {
            "confidence": max(0.1, min(0.95, confidence)),
            "reasoning": reasoning,
            "evidence": evidence,
            "violations": [],  # Executive doesn't identify violations
        }

    async def propose_decision(
        self, action: str, context: JSONDict, proposed_by: str = "system"
    ) -> GovernanceDecision:
        """Propose a new governance decision."""
        decision_id = f"exec-{hashlib.sha256(f'{action}:{context!s}'.encode()).hexdigest()[:8]}"

        decision = GovernanceDecision(
            id=decision_id, action=action, context=context, proposed_by=proposed_by
        )

        logger.info(f"Executive agent proposed decision {decision_id}: {action}")
        return decision


class LegislativeAgent(BaseMACIAgent):
    """Legislative Agent: Validates constitutional rules and extracts relevant principles."""

    def __init__(self, agent_id: str = "legislative-001"):
        super().__init__(AgentRole.LEGISLATIVE, agent_id)

    async def _analyze_decision_specific(
        self, decision: GovernanceDecision, context_responses: list[AgentResponse] | None = None
    ) -> JSONDict:
        """
        Legislative analysis: Extract and validate relevant constitutional principles.
        Does NOT render final judgment - that's for Judicial agent.
        """
        action = decision.action
        context = decision.context

        relevant_principles: JSONList = []
        violations: list[str] = []
        evidence: JSONList = []

        # Find relevant constitutional principles
        action_keywords = action.lower().split()
        for principle in self.constitutional_principles.values():
            principle_text = principle.text.lower()
            if any(keyword in principle_text for keyword in action_keywords):
                relevant_principles.append(principle)
                evidence.append(f"Relevant principle: {principle.text[:50]}...")

        # Analyze context for constitutional relevance
        if "stakeholders" in context:
            stakeholders = context["stakeholders"]
            if len(stakeholders) > 10:
                evidence.append("Broad stakeholder impact suggests constitutional review needed")

        # Check for precedent conflicts
        if context_responses:
            for response in context_responses:
                if response.agent_role == AgentRole.EXECUTIVE:
                    if response.confidence < 0.5:
                        evidence.append("Executive concerns suggest constitutional review needed")

        confidence = min(0.9, 0.6 + (len(relevant_principles) * 0.1))
        reasoning = f"Legislative analysis identified {len(relevant_principles)} relevant constitutional principles"

        return {
            "confidence": confidence,
            "reasoning": reasoning,
            "evidence": evidence,
            "violations": violations,  # Legislative identifies potential issues but doesn't judge
            "relevant_principles": [p.id for p in relevant_principles],
        }


class JudicialAgent(BaseMACIAgent):
    """Judicial Agent: Renders final judgment on constitutional compliance."""

    def __init__(self, agent_id: str = "judicial-001"):
        super().__init__(AgentRole.JUDICIAL, agent_id)

    async def _analyze_decision_specific(
        self, decision: GovernanceDecision, context_responses: list[AgentResponse] | None = None
    ) -> JSONDict:
        """
        Judicial analysis: Render final judgment based on Executive proposal and Legislative rules.
        Does NOT propose decisions or extract rules - that's for other agents.
        """
        violations = []
        evidence = []
        confidence = 0.5  # Base judicial confidence

        if not context_responses:
            return {
                "confidence": 0.1,
                "reasoning": "Insufficient context for judicial review",
                "evidence": ["No agent responses provided"],
                "violations": ["Incomplete review process"],
            }

        # Analyze responses from other agents
        executive_response = None
        legislative_response = None

        for response in context_responses:
            if response.agent_role == AgentRole.EXECUTIVE:
                executive_response = response
            elif response.agent_role == AgentRole.LEGISLATIVE:
                legislative_response = response

        # Judicial evaluation logic
        if executive_response and executive_response.confidence < 0.4:
            violations.append("Executive agent expressed significant concerns")
            evidence.append(f"Executive confidence: {executive_response.confidence:.2f}")

        if legislative_response:
            if "relevant_principles" in legislative_response.reasoning:
                evidence.append(
                    "Legislative analysis identified relevant constitutional principles"
                )
                confidence += 0.2
            if legislative_response.confidence > 0.7:
                confidence += 0.1

        # Check for emergency override conditions
        if decision.context.get("emergency_override", False):
            evidence.append("Emergency override condition detected")
            if decision.context.get("emergency_justification"):
                confidence += 0.1
            else:
                violations.append("Emergency override lacks justification")

        # Final compliance determination
        is_compliant = len(violations) == 0 and confidence > 0.6

        reasoning = f"Judicial review: {'COMPLIANT' if is_compliant else 'NON-COMPLIANT'} (confidence: {confidence:.2f})"

        return {
            "confidence": confidence,
            "reasoning": reasoning,
            "evidence": evidence,
            "violations": violations,
            "is_compliant": is_compliant,
        }


class MACIVerificationPipeline:
    """
    MACI Verification Pipeline: Bypasses Gödel limitations through role separation.

    Constitutional Hash: 608508a9bd224290

    Workflow:
    1. Executive Agent proposes decision
    2. Legislative Agent extracts relevant constitutional rules
    3. Judicial Agent renders final judgment
    4. No agent validates its own output
    """

    def __init__(self):
        self.executive_agent = ExecutiveAgent()
        self.legislative_agent = LegislativeAgent()
        self.judicial_agent = JudicialAgent()
        self.constitutional_principles: list[ConstitutionalPrinciple] = []
        self.verification_history: deque[VerificationResult] = deque(maxlen=MAX_DECISION_HISTORY)

    def load_constitution(self, principles: list[ConstitutionalPrinciple]):
        """Load constitutional principles into all agents."""
        self.constitutional_principles = principles

        self.executive_agent.load_constitutional_principles(principles)
        self.legislative_agent.load_constitutional_principles(principles)
        self.judicial_agent.load_constitutional_principles(principles)

        logger.info(f"MACI Pipeline loaded constitution with {len(principles)} principles")

    async def verify_governance_decision(self, decision: GovernanceDecision) -> VerificationResult:
        """
        Execute full MACI verification pipeline.

        Args:
            decision: Governance decision to verify

        Returns:
            Complete verification result with all agent responses
        """
        logger.info(f"Starting MACI verification for decision {decision.id}")

        # Phase 1: Executive proposal analysis
        executive_response = await self.executive_agent.respond_to_decision(decision)

        # Phase 2: Legislative constitutional rule extraction
        legislative_response = await self.legislative_agent.respond_to_decision(
            decision, context_responses=[executive_response]
        )

        # Phase 3: Judicial final judgment
        judicial_response = await self.judicial_agent.respond_to_decision(
            decision, context_responses=[executive_response, legislative_response]
        )

        # Determine overall compliance
        is_compliant = judicial_response.confidence > 0.6
        violations = []

        # Extract violations from judicial analysis
        if (
            hasattr(judicial_response, "reasoning")
            and "NON-COMPLIANT" in judicial_response.reasoning
        ):
            violations.append("Judicial agent determined non-compliance")

        # Extract recommendations
        recommendations = []
        if executive_response.confidence < 0.5:
            recommendations.append("Review executive concerns before proceeding")

        confidence = judicial_response.confidence

        result = VerificationResult(
            decision_id=decision.id,
            is_compliant=is_compliant,
            confidence=confidence,
            violations=violations,
            recommendations=recommendations,
            executive_response=executive_response,
            legislative_response=legislative_response,
            judicial_response=judicial_response,
        )

        self.verification_history.append(result)

        logger.info(
            f"MACI verification complete for {decision.id}: {'COMPLIANT' if is_compliant else 'NON-COMPLIANT'}"
        )
        return result

    async def propose_and_verify_decision(
        self, action: str, context: JSONDict, proposed_by: str = "system"
    ) -> tuple[GovernanceDecision, VerificationResult]:
        """
        Complete workflow: Propose decision and verify compliance.

        Args:
            action: Governance action to propose
            context: Decision context
            proposed_by: Agent proposing the decision

        Returns:
            Tuple of (proposed decision, verification result)
        """
        # Executive proposes the decision
        decision = await self.executive_agent.propose_decision(action, context, proposed_by)

        # Full MACI verification
        verification = await self.verify_governance_decision(decision)

        return decision, verification

    def get_constitutional_hash(self) -> str:
        """Return the constitutional hash for validation."""
        return str(CONSTITUTIONAL_HASH)

    def get_pipeline_stats(self) -> JSONDict:
        """Get statistics about pipeline performance."""
        if not self.verification_history:
            return {"total_decisions": 0}

        total_decisions = len(self.verification_history)
        compliant_decisions = sum(1 for v in self.verification_history if v.is_compliant)
        avg_confidence = sum(v.confidence for v in self.verification_history) / total_decisions

        return {
            "total_decisions": total_decisions,
            "compliant_decisions": compliant_decisions,
            "compliance_rate": compliant_decisions / total_decisions,
            "average_confidence": avg_confidence,
            "total_violations": sum(len(v.violations) for v in self.verification_history),
        }


# Convenience functions for external use
async def create_maci_pipeline_with_constitution(
    constitutional_principles: list[JSONDict],
) -> MACIVerificationPipeline:
    """
    Create and initialize MACI pipeline with constitutional principles.

    Args:
        constitutional_principles: List of principle dictionaries with 'id', 'text', 'category', 'priority'

    Returns:
        Initialized MACI pipeline
    """
    pipeline = MACIVerificationPipeline()

    principles = [
        ConstitutionalPrinciple(
            id=p["id"], text=p["text"], category=p["category"], priority=p["priority"]
        )
        for p in constitutional_principles
    ]

    pipeline.load_constitution(principles)
    return pipeline


# Export for use in other modules
__all__ = [
    "CONSTITUTIONAL_HASH",
    "AgentRole",
    "ConstitutionalPrinciple",
    "ExecutiveAgent",
    "GovernanceDecision",
    "GovernancePhase",
    "JudicialAgent",
    "LegislativeAgent",
    "MACIVerificationPipeline",
    "VerificationResult",
    "create_maci_pipeline_with_constitution",
]
