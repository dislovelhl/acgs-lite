"""
ACGS-2 Deliberation Layer - OPA Guard Models
Constitutional Hash: 608508a9bd224290

Data models and enums for the OPA Policy Guard.
Separates data structures from business logic for better maintainability.
"""

import hashlib
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import TypeAlias

from enhanced_agent_bus.bus_types import JSONDict, JSONValue

# Ensure module aliasing across package import paths
_module = sys.modules.get(__name__)
if _module is not None:
    sys.modules.setdefault("enhanced_agent_bus.deliberation_layer.opa_guard_models", _module)
    sys.modules.setdefault(
        "enhanced_agent_bus.deliberation_layer.opa_guard_models", _module
    )
    sys.modules.setdefault("core.enhanced_agent_bus.deliberation_layer.opa_guard_models", _module)

# Import centralized constitutional hash from shared module
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
        from src.core.shared.constants import CONSTITUTIONAL_HASH
# Alias for backward compatibility
GUARD_CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH


class GuardDecision(Enum):
    """Guard decision outcomes."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_REVIEW = "require_review"
    REQUIRE_SIGNATURES = "require_signatures"
    PENDING = "pending"


class SignatureStatus(Enum):
    """Status of signature collection."""

    PENDING = "pending"
    COLLECTED = "collected"
    EXPIRED = "expired"
    REJECTED = "rejected"


class ReviewStatus(Enum):
    """Status of critic review."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"


@dataclass
class GuardResult:
    """
    Result of OPA guard pre-action validation.

    Implements VERIFY-BEFORE-ACT pattern by providing comprehensive
    validation results before any action is executed.
    """

    decision: GuardDecision = GuardDecision.PENDING
    is_allowed: bool = False
    agent_id: str = ""
    action_type: str = ""

    # Policy evaluation details
    policy_path: str = ""
    policy_result: JSONDict = field(default_factory=dict)

    # Validation details
    constitutional_valid: bool = False
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)

    # Risk assessment
    risk_level: str = "unknown"  # low, medium, high, critical
    risk_score: float = 0.0
    risk_factors: list[str] = field(default_factory=list)

    # Required actions
    requires_signatures: bool = False
    required_signers: list[str] = field(default_factory=list)
    requires_review: bool = False
    required_reviewers: list[str] = field(default_factory=list)

    # Metadata
    guard_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = GUARD_CONSTITUTIONAL_HASH
    metadata: JSONDict = field(default_factory=dict)

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for serialization."""
        return {
            "guard_id": self.guard_id,
            "decision": self.decision.value,
            "is_allowed": self.is_allowed,
            "agent_id": self.agent_id,
            "action_type": self.action_type,
            "policy_path": self.policy_path,
            "policy_result": self.policy_result,
            "constitutional_valid": self.constitutional_valid,
            "validation_errors": self.validation_errors,
            "validation_warnings": self.validation_warnings,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score,
            "risk_factors": self.risk_factors,
            "requires_signatures": self.requires_signatures,
            "required_signers": self.required_signers,
            "requires_review": self.requires_review,
            "required_reviewers": self.required_reviewers,
            "timestamp": self.timestamp.isoformat(),
            "constitutional_hash": self.constitutional_hash,
            "metadata": self.metadata,
        }


@dataclass
class Signature:
    """Individual signature from an authorized signer."""

    signer_id: str
    signature_hash: str = ""
    signed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    reasoning: str = ""
    confidence: float = 1.0
    metadata: JSONDict = field(default_factory=dict)

    def __post_init__(self):
        """Generate signature hash if not provided."""
        if not self.signature_hash:
            sig_data = f"{self.signer_id}:{self.signed_at.isoformat()}:{GUARD_CONSTITUTIONAL_HASH}"
            self.signature_hash = hashlib.sha256(sig_data.encode()).hexdigest()[:32]


@dataclass
class SignatureResult:
    """
    Result of multi-signature collection for high-risk decisions.

    Ensures that high-impact actions require approval from multiple
    authorized entities before execution.
    """

    decision_id: str = ""
    status: SignatureStatus = SignatureStatus.PENDING

    # Signature requirements
    required_signers: list[str] = field(default_factory=list)
    required_count: int = 0
    threshold: float = 1.0  # Percentage of required signatures (1.0 = all)

    # Collected signatures
    signatures: list[Signature] = field(default_factory=list)
    collected_count: int = 0

    # Missing and rejected
    missing_signers: list[str] = field(default_factory=list)
    rejected_by: list[str] = field(default_factory=list)

    # Timing
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    completed_at: datetime | None = None

    # Validation
    is_complete: bool = False
    is_valid: bool = False
    constitutional_hash: str = GUARD_CONSTITUTIONAL_HASH

    # Metadata
    metadata: JSONDict = field(default_factory=dict)

    def __post_init__(self):
        """Calculate missing signers and update counts."""
        signed_ids = {sig.signer_id for sig in self.signatures}
        self.missing_signers = [s for s in self.required_signers if s not in signed_ids]
        self.collected_count = len(self.signatures)

        # Check if threshold is met
        if self.required_count > 0:
            ratio = self.collected_count / self.required_count
            self.is_complete = ratio >= self.threshold
            self.is_valid = self.is_complete and len(self.rejected_by) == 0

    def add_signature(self, signature: Signature) -> bool:
        """Add a signature and update status."""
        if signature.signer_id not in self.required_signers:
            return False

        # Check if already signed
        existing = next((s for s in self.signatures if s.signer_id == signature.signer_id), None)
        if existing:
            # Update existing signature
            self.signatures.remove(existing)

        self.signatures.append(signature)
        self.__post_init__()

        if self.is_complete:
            self.status = SignatureStatus.COLLECTED
            self.completed_at = datetime.now(UTC)

        return True

    def reject(self, signer_id: str, reason: str = "") -> bool:
        """Record a rejection from a signer."""
        if signer_id not in self.required_signers:
            return False

        self.rejected_by.append(signer_id)
        self.status = SignatureStatus.REJECTED
        self.is_valid = False
        self.metadata[f"rejection_{signer_id}"] = {
            "reason": reason,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        return True

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for serialization."""
        return {
            "decision_id": self.decision_id,
            "status": self.status.value,
            "required_signers": self.required_signers,
            "required_count": self.required_count,
            "threshold": self.threshold,
            "signatures": [
                {
                    "signer_id": sig.signer_id,
                    "signature_hash": sig.signature_hash,
                    "signed_at": sig.signed_at.isoformat(),
                    "reasoning": sig.reasoning,
                    "confidence": sig.confidence,
                }
                for sig in self.signatures
            ],
            "collected_count": self.collected_count,
            "missing_signers": self.missing_signers,
            "rejected_by": self.rejected_by,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "is_complete": self.is_complete,
            "is_valid": self.is_valid,
            "constitutional_hash": self.constitutional_hash,
            "metadata": self.metadata,
        }


@dataclass
class CriticReview:
    """Review from a critic agent."""

    critic_id: str
    review_type: str = "general"  # general, safety, ethics, performance
    verdict: str = ""  # approve, reject, escalate
    reasoning: str = ""
    confidence: float = 1.0
    concerns: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    reviewed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: JSONDict = field(default_factory=dict)


@dataclass
class ReviewResult:
    """
    Result of critic agent review process.

    Aggregates reviews from multiple critic agents to provide
    comprehensive decision analysis for high-risk actions.
    """

    decision_id: str = ""
    status: ReviewStatus = ReviewStatus.PENDING

    # Review requirements
    required_critics: list[str] = field(default_factory=list)
    review_types: list[str] = field(default_factory=list)

    # Collected reviews
    reviews: list[CriticReview] = field(default_factory=list)

    # Aggregated results
    approval_count: int = 0
    rejection_count: int = 0
    escalation_count: int = 0

    # Consensus
    consensus_reached: bool = False
    consensus_verdict: str = ""  # approve, reject, escalate
    consensus_confidence: float = 0.0

    # Timing
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    timeout_seconds: int = 300

    # Constitutional validation
    constitutional_hash: str = GUARD_CONSTITUTIONAL_HASH

    # Aggregated concerns and recommendations
    all_concerns: list[str] = field(default_factory=list)
    all_recommendations: list[str] = field(default_factory=list)

    # Metadata
    metadata: JSONDict = field(default_factory=dict)

    def add_review(self, review: CriticReview) -> bool:
        """Add a critic review and update aggregations."""
        self.reviews.append(review)

        # Update counts
        if review.verdict == "approve":
            self.approval_count += 1
        elif review.verdict == "reject":
            self.rejection_count += 1
        elif review.verdict == "escalate":
            self.escalation_count += 1

        # Aggregate concerns and recommendations
        self.all_concerns.extend(review.concerns)
        self.all_recommendations.extend(review.recommendations)

        # Check consensus
        self._check_consensus()

        return True

    def _check_consensus(self):
        """Check if consensus has been reached."""
        total_reviews = len(self.reviews)
        if total_reviews == 0:
            return

        # Need at least half of required critics
        if self.required_critics:
            if total_reviews < len(self.required_critics) // 2 + 1:
                return

        # Calculate majority
        if self.rejection_count > total_reviews // 2:
            self.consensus_verdict = "reject"
            self.consensus_reached = True
            self.status = ReviewStatus.REJECTED
        elif self.escalation_count > total_reviews // 2:
            self.consensus_verdict = "escalate"
            self.consensus_reached = True
            self.status = ReviewStatus.ESCALATED
        elif self.approval_count > total_reviews // 2:
            self.consensus_verdict = "approve"
            self.consensus_reached = True
            self.status = ReviewStatus.APPROVED

        if self.consensus_reached:
            self.completed_at = datetime.now(UTC)
            # Calculate confidence as weighted average
            if total_reviews > 0:
                self.consensus_confidence = (
                    sum(r.confidence for r in self.reviews if r.verdict == self.consensus_verdict)
                    / total_reviews
                )

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for serialization."""
        return {
            "decision_id": self.decision_id,
            "status": self.status.value,
            "required_critics": self.required_critics,
            "review_types": self.review_types,
            "reviews": [
                {
                    "critic_id": r.critic_id,
                    "review_type": r.review_type,
                    "verdict": r.verdict,
                    "reasoning": r.reasoning,
                    "confidence": r.confidence,
                    "concerns": r.concerns,
                    "recommendations": r.recommendations,
                    "reviewed_at": r.reviewed_at.isoformat(),
                }
                for r in self.reviews
            ],
            "approval_count": self.approval_count,
            "rejection_count": self.rejection_count,
            "escalation_count": self.escalation_count,
            "consensus_reached": self.consensus_reached,
            "consensus_verdict": self.consensus_verdict,
            "consensus_confidence": self.consensus_confidence,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "timeout_seconds": self.timeout_seconds,
            "all_concerns": self.all_concerns,
            "all_recommendations": self.all_recommendations,
            "constitutional_hash": self.constitutional_hash,
            "metadata": self.metadata,
        }


__all__ = [
    "GUARD_CONSTITUTIONAL_HASH",
    "CriticReview",
    "GuardDecision",
    "GuardResult",
    "ReviewResult",
    "ReviewStatus",
    "Signature",
    "SignatureResult",
    "SignatureStatus",
]
