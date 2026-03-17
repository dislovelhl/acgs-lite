"""
ACGS-2 Enhanced Agent Bus - Amendment Proposal Model
Constitutional Hash: cdd01ef066bc6cf2

Data model for constitutional amendment proposals with justification,
impact analysis, and governance metrics tracking.
"""

from datetime import UTC, datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_serializer, field_validator
from src.core.shared.errors.exceptions import ValidationError as ACGSValidationError
from src.core.shared.types import JSONDict

# Import centralized constitutional hash
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    # Fallback for standalone usage
    from src.core.shared.constants import CONSTITUTIONAL_HASH


class AmendmentStatus(str, Enum):  # noqa: UP042
    """Amendment proposal status enumeration.

    Constitutional Hash: cdd01ef066bc6cf2

    Tracks the lifecycle of a constitutional amendment from proposal
    through approval, activation, and potential rollback.
    """

    PROPOSED = "proposed"  # Initial proposal submitted
    UNDER_REVIEW = "under_review"  # In HITL approval process
    APPROVED = "approved"  # Approved but not yet activated
    REJECTED = "rejected"  # Rejected during review
    ACTIVE = "active"  # Currently active and applied to constitution
    ROLLED_BACK = "rolled_back"  # Rolled back due to degradation
    WITHDRAWN = "withdrawn"  # Withdrawn by proposer before approval


class AmendmentProposal(BaseModel):
    """Constitutional amendment proposal model.

    This model tracks proposed constitutional changes with justification,
    impact analysis, and governance metrics for before/after comparison.

    Constitutional Hash: cdd01ef066bc6cf2

    Attributes:
        proposal_id: Unique identifier for this amendment proposal
        proposed_changes: dict containing the proposed constitutional changes
        justification: Human-readable explanation for why this amendment is needed
        proposer_agent_id: ID of the agent/user proposing the amendment
        target_version: Target constitutional version this amendment applies to
        new_version: New constitutional version if amendment is approved
        status: Current status of this amendment proposal
        impact_score: ML-computed impact score (0.0-1.0, from ImpactScorer)
        impact_factors: Detailed impact analysis factors
        impact_recommendation: Textual recommendation from impact analysis
        requires_deliberation: Whether this amendment requires HITL deliberation
        governance_metrics_before: Governance metrics snapshot before amendment
        governance_metrics_after: Governance metrics snapshot after activation
        approval_chain: list of approver IDs and timestamps
        rejection_reason: Reason for rejection (if rejected)
        rollback_reason: Reason for rollback (if rolled back)
        metadata: Additional metadata (MACI role enforcement, audit trail)
        created_at: Timestamp when proposal was created
        reviewed_at: Timestamp when proposal was reviewed
        activated_at: Timestamp when amendment was activated
        rolled_back_at: Timestamp when amendment was rolled back
    """

    # Core identification
    proposal_id: str = Field(default_factory=lambda: str(uuid4()))

    # Amendment content
    proposed_changes: JSONDict = Field(
        ..., description="Proposed constitutional changes (diff format or full content)"
    )
    justification: str = Field(
        ..., min_length=10, description="Human-readable justification for this amendment"
    )

    # Proposer and version tracking
    proposer_agent_id: str = Field(..., description="ID of the agent/user proposing the amendment")
    target_version: str = Field(
        ...,
        pattern=r"^\d+\.\d+\.\d+$",
        description="Target constitutional version this amendment applies to",
    )
    new_version: str | None = Field(
        None,
        pattern=r"^\d+\.\d+\.\d+$",
        description="New constitutional version if amendment is approved",
    )

    # Status tracking
    status: AmendmentStatus = Field(default=AmendmentStatus.PROPOSED)

    # Impact analysis (from ImpactScorer)
    impact_score: float | None = Field(
        None, ge=0.0, le=1.0, description="ML-computed impact score from DistilBERT impact scorer"
    )
    impact_factors: dict[str, float] = Field(
        default_factory=dict,
        description="Detailed impact analysis factors (semantic, permission, etc.)",
    )
    impact_recommendation: str | None = Field(
        None, description="Textual recommendation from impact analysis"
    )
    requires_deliberation: bool = Field(
        default=False, description="Whether this amendment requires HITL deliberation"
    )

    # Governance metrics tracking (before/after comparison)
    governance_metrics_before: dict[str, float] = Field(
        default_factory=dict, description="Governance metrics snapshot before amendment activation"
    )
    governance_metrics_after: dict[str, float] = Field(
        default_factory=dict, description="Governance metrics snapshot after amendment activation"
    )

    # Approval workflow
    approval_chain: list[JSONDict] = Field(
        default_factory=list, description="list of approvers with IDs, timestamps, and decisions"
    )
    rejection_reason: str | None = Field(None, description="Reason for rejection (if rejected)")
    rollback_reason: str | None = Field(None, description="Reason for rollback (if rolled back)")

    # Metadata and audit trail
    metadata: JSONDict = Field(
        default_factory=lambda: {"constitutional_hash": CONSTITUTIONAL_HASH},
        description="Additional metadata: MACI role enforcement, audit trail, etc.",
    )

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reviewed_at: datetime | None = Field(
        None, description="Timestamp when proposal was reviewed (approved/rejected)"
    )
    activated_at: datetime | None = Field(
        None, description="Timestamp when amendment was activated"
    )
    rolled_back_at: datetime | None = Field(
        None, description="Timestamp when amendment was rolled back"
    )

    @field_serializer("created_at", "reviewed_at", "activated_at", "rolled_back_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        """Serialize datetime fields to ISO format."""
        if value is None:
            return None
        return value.isoformat()

    @field_validator("justification")
    @classmethod
    def validate_justification(cls, v: str) -> str:
        """Validate justification is meaningful."""
        if len(v.strip()) < 10:
            raise ValueError("Justification must be at least 10 characters")
        return v.strip()

    @field_validator("proposed_changes")
    @classmethod
    def validate_proposed_changes(cls, v: JSONDict) -> JSONDict:
        """Validate proposed changes are not empty."""
        if not v:
            raise ValueError("Proposed changes cannot be empty")
        return v

    @field_validator("target_version", "new_version")
    @classmethod
    def validate_semantic_version(cls, v: str | None) -> str | None:
        """Validate semantic versioning format (major.minor.patch)."""
        if v is None:
            return None

        parts = v.split(".")
        if len(parts) != 3:
            raise ValueError("Version must follow semantic versioning: major.minor.patch")

        try:
            major, minor, patch = map(int, parts)
            if major < 0 or minor < 0 or patch < 0:
                raise ValueError("Version numbers must be non-negative")
        except ValueError as e:
            raise ValueError(f"Invalid semantic version format: {e}") from e

        return v

    def __init__(self, **data):
        """Initialize amendment proposal with defaults."""
        super().__init__(**data)
        if not self.proposal_id:
            self.proposal_id = str(uuid4())

        # Ensure constitutional hash is always present in metadata
        if "constitutional_hash" not in self.metadata:
            self.metadata["constitutional_hash"] = CONSTITUTIONAL_HASH

    # Status check properties
    @property
    def is_proposed(self) -> bool:
        """Check if this proposal is in proposed status."""
        return self.status == AmendmentStatus.PROPOSED

    @property
    def is_under_review(self) -> bool:
        """Check if this proposal is under review."""
        return self.status == AmendmentStatus.UNDER_REVIEW

    @property
    def is_approved(self) -> bool:
        """Check if this proposal is approved but not yet active."""
        return self.status == AmendmentStatus.APPROVED

    @property
    def is_rejected(self) -> bool:
        """Check if this proposal was rejected."""
        return self.status == AmendmentStatus.REJECTED

    @property
    def is_active(self) -> bool:
        """Check if this amendment is currently active."""
        return self.status == AmendmentStatus.ACTIVE

    @property
    def is_rolled_back(self) -> bool:
        """Check if this amendment was rolled back."""
        return self.status == AmendmentStatus.ROLLED_BACK

    @property
    def is_withdrawn(self) -> bool:
        """Check if this proposal was withdrawn."""
        return self.status == AmendmentStatus.WITHDRAWN

    @property
    def is_pending(self) -> bool:
        """Check if this proposal is pending (proposed or under review)."""
        return self.status in (AmendmentStatus.PROPOSED, AmendmentStatus.UNDER_REVIEW)

    @property
    def is_final(self) -> bool:
        """Check if this proposal has reached a final state."""
        return self.status in (
            AmendmentStatus.REJECTED,
            AmendmentStatus.ROLLED_BACK,
            AmendmentStatus.WITHDRAWN,
        )

    @property
    def high_impact(self) -> bool:
        """Check if this amendment has high impact (>= 0.8)."""
        return self.impact_score is not None and self.impact_score >= 0.8

    @property
    def medium_impact(self) -> bool:
        """Check if this amendment has medium impact (0.5-0.8)."""
        return self.impact_score is not None and 0.5 <= self.impact_score < 0.8

    @property
    def low_impact(self) -> bool:
        """Check if this amendment has low impact (< 0.5)."""
        return self.impact_score is not None and self.impact_score < 0.5

    # State transition methods
    def submit_for_review(self) -> None:
        """Submit proposal for review.

        Transitions status from PROPOSED to UNDER_REVIEW.
        """
        if not self.is_proposed:
            raise ACGSValidationError(
                f"Can only submit proposals in PROPOSED status (current: {self.status})",
                error_code="AMENDMENT_NOT_PROPOSED",
            )
        self.status = AmendmentStatus.UNDER_REVIEW

    def approve(self, approver_id: str, approver_role: str = "unknown") -> None:
        """Approve this amendment proposal.

        Args:
            approver_id: ID of the approver
            approver_role: MACI role of the approver (e.g., "judicial")

        Transitions status to APPROVED and records approval in chain.
        """
        if not self.is_under_review:
            raise ACGSValidationError(
                f"Can only approve proposals in UNDER_REVIEW status (current: {self.status})",
                error_code="AMENDMENT_NOT_UNDER_REVIEW",
            )

        self.status = AmendmentStatus.APPROVED
        self.reviewed_at = datetime.now(UTC)

        # Record approval in chain
        self.approval_chain.append(
            {
                "approver_id": approver_id,
                "approver_role": approver_role,
                "decision": "approved",
                "timestamp": self.reviewed_at.isoformat(),
            }
        )

    def reject(self, reviewer_id: str, reason: str, reviewer_role: str = "unknown") -> None:
        """Reject this amendment proposal.

        Args:
            reviewer_id: ID of the reviewer
            reason: Reason for rejection
            reviewer_role: MACI role of the reviewer

        Transitions status to REJECTED and records reason.
        """
        if not self.is_under_review:
            raise ACGSValidationError(
                f"Can only reject proposals in UNDER_REVIEW status (current: {self.status})",
                error_code="AMENDMENT_NOT_UNDER_REVIEW",
            )

        self.status = AmendmentStatus.REJECTED
        self.reviewed_at = datetime.now(UTC)
        self.rejection_reason = reason

        # Record rejection in chain
        self.approval_chain.append(
            {
                "reviewer_id": reviewer_id,
                "reviewer_role": reviewer_role,
                "decision": "rejected",
                "reason": reason,
                "timestamp": self.reviewed_at.isoformat(),
            }
        )

    def activate(self, governance_metrics_before: dict[str, float] | None = None) -> None:
        """Activate this amendment.

        Args:
            governance_metrics_before: Optional governance metrics snapshot

        Transitions status to ACTIVE and records activation timestamp.
        """
        if not self.is_approved:
            raise ACGSValidationError(
                f"Can only activate proposals in APPROVED status (current: {self.status})",
                error_code="AMENDMENT_NOT_APPROVED",
            )

        self.status = AmendmentStatus.ACTIVE
        self.activated_at = datetime.now(UTC)

        if governance_metrics_before:
            self.governance_metrics_before = governance_metrics_before

    def rollback(
        self, reason: str, governance_metrics_after: dict[str, float] | None = None
    ) -> None:
        """Rollback this amendment due to degradation.

        Args:
            reason: Reason for rollback (e.g., "governance degradation detected")
            governance_metrics_after: Optional governance metrics snapshot

        Transitions status to ROLLED_BACK and records reason.
        """
        if not self.is_active:
            raise ACGSValidationError(
                f"Can only rollback amendments in ACTIVE status (current: {self.status})",
                error_code="AMENDMENT_NOT_ACTIVE",
            )

        self.status = AmendmentStatus.ROLLED_BACK
        self.rolled_back_at = datetime.now(UTC)
        self.rollback_reason = reason

        if governance_metrics_after:
            self.governance_metrics_after = governance_metrics_after

    def withdraw(self) -> None:
        """Withdraw this proposal before approval.

        Transitions status to WITHDRAWN.
        """
        if not self.is_pending:
            raise ACGSValidationError(
                f"Can only withdraw pending proposals (current: {self.status})",
                error_code="AMENDMENT_NOT_PENDING",
            )

        self.status = AmendmentStatus.WITHDRAWN

    def calculate_metrics_delta(self) -> dict[str, float]:
        """Calculate the delta between before and after governance metrics.

        Returns:
            dict mapping metric names to delta values (after - before)
        """
        if not self.governance_metrics_before or not self.governance_metrics_after:
            return {}

        delta: dict[str, float] = {}
        for metric_name in self.governance_metrics_before:
            if metric_name in self.governance_metrics_after:
                before = self.governance_metrics_before[metric_name]
                after = self.governance_metrics_after[metric_name]
                delta[metric_name] = after - before

        return delta

    def to_dict(self) -> JSONDict:
        """Convert model to dictionary with serialized datetimes."""
        return self.model_dump()

    def __repr__(self) -> str:
        """String representation of amendment proposal."""
        return (
            f"AmendmentProposal(proposal_id={self.proposal_id}, "
            f"target_version={self.target_version}, "
            f"status={self.status.value}, "
            f"impact_score={self.impact_score})"
        )
