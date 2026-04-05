"""
ACGS-2 Governance Fixtures
Constitutional Hash: 608508a9bd224290

Fixtures for consensus checking, policy verification, and governance testing.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

import pytest

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]


class VoteType(Enum):
    """Types of votes in consensus."""

    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"


class ConsensusType(Enum):
    """Types of consensus mechanisms."""

    MAJORITY = "majority"  # > 50%
    SUPERMAJORITY = "supermajority"  # >= 2/3
    UNANIMOUS = "unanimous"  # 100%
    QUORUM = "quorum"  # Minimum threshold met


@dataclass
class Vote:
    """A vote cast in a consensus process."""

    voter_id: str
    vote_type: VoteType
    weight: float = 1.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    rationale: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class ConsensusResult:
    """Result of a consensus check."""

    reached: bool
    consensus_type: ConsensusType
    approve_weight: float
    reject_weight: float
    abstain_weight: float
    total_weight: float
    quorum_met: bool
    message: str = ""
    constitutional_hash: str = CONSTITUTIONAL_HASH

    @property
    def approval_ratio(self) -> float:
        """Calculate approval ratio excluding abstentions."""
        participating = self.approve_weight + self.reject_weight
        if participating == 0:
            return 0.0
        return self.approve_weight / participating

    def to_dict(self) -> JSONDict:
        return {
            "reached": self.reached,
            "consensus_type": self.consensus_type.value,
            "approve_weight": self.approve_weight,
            "reject_weight": self.reject_weight,
            "abstain_weight": self.abstain_weight,
            "total_weight": self.total_weight,
            "approval_ratio": self.approval_ratio,
            "quorum_met": self.quorum_met,
            "message": self.message,
            "constitutional_hash": self.constitutional_hash,
        }


class SpecConsensusChecker:
    """
    Consensus checker for specification testing.

    Implements multiple consensus mechanisms for governance decisions.
    """

    def __init__(
        self,
        consensus_type: ConsensusType = ConsensusType.MAJORITY,
        quorum_threshold: float = 0.5,
    ):
        self.consensus_type = consensus_type
        self.quorum_threshold = quorum_threshold
        self.votes: dict[str, Vote] = {}
        self.registered_voters: dict[str, float] = {}  # voter_id -> weight
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def register_voter(self, voter_id: str, weight: float = 1.0) -> None:
        """Register a voter with optional weight."""
        self.registered_voters[voter_id] = weight

    def cast_vote(
        self,
        voter_id: str,
        vote_type: VoteType,
        rationale: str | None = None,
    ) -> Vote:
        """
        Cast a vote.

        Args:
            voter_id: ID of the voter
            vote_type: Type of vote
            rationale: Optional explanation

        Returns:
            The cast Vote
        """
        weight = self.registered_voters.get(voter_id, 1.0)
        vote = Vote(
            voter_id=voter_id,
            vote_type=vote_type,
            weight=weight,
            rationale=rationale,
        )
        self.votes[voter_id] = vote
        return vote

    def check_consensus(self) -> ConsensusResult:
        """
        Check if consensus is reached.

        Returns:
            ConsensusResult with decision and metrics
        """
        approve_weight = sum(
            v.weight for v in self.votes.values() if v.vote_type == VoteType.APPROVE
        )
        reject_weight = sum(v.weight for v in self.votes.values() if v.vote_type == VoteType.REJECT)
        abstain_weight = sum(
            v.weight for v in self.votes.values() if v.vote_type == VoteType.ABSTAIN
        )

        total_registered = sum(self.registered_voters.values()) or 1.0
        total_voted = approve_weight + reject_weight + abstain_weight

        # Check quorum
        quorum_met = (total_voted / total_registered) >= self.quorum_threshold

        if not quorum_met:
            return ConsensusResult(
                reached=False,
                consensus_type=self.consensus_type,
                approve_weight=approve_weight,
                reject_weight=reject_weight,
                abstain_weight=abstain_weight,
                total_weight=total_voted,
                quorum_met=False,
                message="Quorum not met",
            )

        # Calculate consensus based on type
        participating = approve_weight + reject_weight
        if participating == 0:
            approval_ratio = 0.0
        else:
            approval_ratio = approve_weight / participating

        reached = False
        if self.consensus_type == ConsensusType.MAJORITY:
            reached = approval_ratio > 0.5
        elif self.consensus_type == ConsensusType.SUPERMAJORITY:
            reached = approval_ratio >= (2.0 / 3.0)
        elif self.consensus_type == ConsensusType.UNANIMOUS:
            reached = reject_weight == 0 and approve_weight > 0
        elif self.consensus_type == ConsensusType.QUORUM:
            reached = quorum_met

        return ConsensusResult(
            reached=reached,
            consensus_type=self.consensus_type,
            approve_weight=approve_weight,
            reject_weight=reject_weight,
            abstain_weight=abstain_weight,
            total_weight=total_voted,
            quorum_met=quorum_met,
            message="Consensus reached" if reached else "Consensus not reached",
        )

    def reset(self) -> None:
        """Reset all votes."""
        self.votes.clear()


class PolicyScope(Enum):
    """Scope of policy application."""

    GLOBAL = "global"
    SERVICE = "service"
    AGENT = "agent"
    MESSAGE = "message"


class PolicyEnforcement(Enum):
    """Enforcement level for policies."""

    STRICT = "strict"  # Must pass, no exceptions
    ADVISORY = "advisory"  # Log warning, allow through
    AUDIT_ONLY = "audit_only"  # Only log, no enforcement


@dataclass
class PolicyRule:
    """A policy rule for verification."""

    rule_id: str
    name: str
    condition: Callable[..., bool]
    scope: PolicyScope = PolicyScope.MESSAGE
    enforcement: PolicyEnforcement = PolicyEnforcement.STRICT
    description: str = ""
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class PolicyViolation:
    """Record of a policy violation."""

    rule_id: str
    rule_name: str
    scope: PolicyScope
    enforcement: PolicyEnforcement
    context: JSONDict
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    message: str = ""
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class PolicyVerificationResult:
    """Result of policy verification."""

    passed: bool
    rule_id: str
    rule_name: str
    enforcement: PolicyEnforcement
    violations: list[PolicyViolation] = field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        return {
            "passed": self.passed,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "enforcement": self.enforcement.value,
            "violation_count": len(self.violations),
            "constitutional_hash": self.constitutional_hash,
        }


class SpecPolicyVerifier:
    """
    Policy verifier for specification testing.

    Implements policy rule verification with multiple enforcement levels.
    """

    def __init__(self):
        self.rules: dict[str, PolicyRule] = {}
        self.violations: list[PolicyViolation] = []
        self.verification_log: list[PolicyVerificationResult] = []
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def register_rule(self, rule: PolicyRule) -> None:
        """Register a policy rule."""
        self.rules[rule.rule_id] = rule

    def create_rule(
        self,
        rule_id: str,
        name: str,
        condition: Callable[..., bool],
        scope: PolicyScope = PolicyScope.MESSAGE,
        enforcement: PolicyEnforcement = PolicyEnforcement.STRICT,
        description: str = "",
    ) -> PolicyRule:
        """Create and register a policy rule."""
        rule = PolicyRule(
            rule_id=rule_id,
            name=name,
            condition=condition,
            scope=scope,
            enforcement=enforcement,
            description=description,
        )
        self.register_rule(rule)
        return rule

    def verify(
        self,
        rule_id: str,
        context: JSONDict | None = None,
    ) -> PolicyVerificationResult:
        """
        Verify a specific policy rule.

        Args:
            rule_id: ID of the rule to verify
            context: Context for rule evaluation

        Returns:
            PolicyVerificationResult with pass/fail status
        """
        rule = self.rules.get(rule_id)
        if not rule:
            return PolicyVerificationResult(
                passed=False,
                rule_id=rule_id,
                rule_name="unknown",
                enforcement=PolicyEnforcement.STRICT,
            )

        context = context or {}

        try:
            passed = rule.condition(**context)
        except (TypeError, KeyError, ValueError, AttributeError):
            passed = False

        result = PolicyVerificationResult(
            passed=passed,
            rule_id=rule.rule_id,
            rule_name=rule.name,
            enforcement=rule.enforcement,
        )

        if not passed:
            violation = PolicyViolation(
                rule_id=rule.rule_id,
                rule_name=rule.name,
                scope=rule.scope,
                enforcement=rule.enforcement,
                context=context,
                message=f"Rule '{rule.name}' failed verification",
            )
            result.violations.append(violation)
            self.violations.append(violation)

        self.verification_log.append(result)
        return result

    def verify_all(
        self,
        context: JSONDict | None = None,
        scope: PolicyScope | None = None,
    ) -> list[PolicyVerificationResult]:
        """
        Verify all registered rules.

        Args:
            context: Context for rule evaluation
            scope: Optional scope filter

        Returns:
            List of verification results
        """
        results = []
        for rule_id, rule in self.rules.items():
            if scope and rule.scope != scope:
                continue
            results.append(self.verify(rule_id, context))
        return results

    def is_compliant(
        self,
        scope: PolicyScope | None = None,
    ) -> bool:
        """
        Check if all STRICT policies pass.

        Args:
            scope: Optional scope filter

        Returns:
            True if all strict policies pass
        """
        for result in self.verification_log:
            if result.enforcement == PolicyEnforcement.STRICT and not result.passed:
                if (
                    scope is None
                    or scope
                    == self.rules.get(result.rule_id, PolicyRule("", "", lambda: True)).scope
                ):
                    return False
        return True

    def get_violations(
        self,
        enforcement: PolicyEnforcement | None = None,
    ) -> list[PolicyViolation]:
        """Get violations filtered by enforcement level."""
        if enforcement:
            return [v for v in self.violations if v.enforcement == enforcement]
        return self.violations.copy()

    def reset(self) -> None:
        """Reset verification state."""
        self.violations.clear()
        self.verification_log.clear()


@pytest.fixture
def consensus_checker() -> SpecConsensusChecker:
    """
    Fixture providing a consensus checker for spec testing.

    Use in tests verifying consensus mechanisms:
        def test_majority_consensus(consensus_checker):
            consensus_checker.register_voter("A")
            consensus_checker.register_voter("B")
            consensus_checker.register_voter("C")
            consensus_checker.cast_vote("A", VoteType.APPROVE)
            consensus_checker.cast_vote("B", VoteType.APPROVE)
            consensus_checker.cast_vote("C", VoteType.REJECT)
            result = consensus_checker.check_consensus()
            assert result.reached
    """
    return SpecConsensusChecker()


@pytest.fixture
def policy_verifier() -> SpecPolicyVerifier:
    """
    Fixture providing a policy verifier for spec testing.

    Use in tests verifying policy compliance:
        def test_policy_compliance(policy_verifier):
            policy_verifier.create_rule(
                "hash_check",
                "Constitutional Hash Check",
                lambda hash: hash == CONSTITUTIONAL_HASH
            )
            result = policy_verifier.verify("hash_check", {"hash": CONSTITUTIONAL_HASH})
            assert result.passed
    """
    return SpecPolicyVerifier()
