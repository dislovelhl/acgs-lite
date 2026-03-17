"""
ACGS-2 Enhanced Agent Bus - Constitutional Version Model
Constitutional Hash: cdd01ef066bc6cf2

Data model for constitutional versions with semantic versioning,
hash tracking, and metadata. Extends existing PolicyVersion pattern.
"""

from datetime import UTC, datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_serializer, field_validator
from src.core.shared.types import JSONDict

# Import centralized constitutional hash
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    # Fallback for standalone usage
    from src.core.shared.constants import CONSTITUTIONAL_HASH


class ConstitutionalStatus(str, Enum):  # noqa: UP042
    """Constitutional version status enumeration.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    DRAFT = "draft"  # Initial draft, not yet activated
    PROPOSED = "proposed"  # Proposed for review
    UNDER_REVIEW = "under_review"  # In HITL approval process
    APPROVED = "approved"  # Approved but not yet active
    ACTIVE = "active"  # Currently active constitutional version
    SUPERSEDED = "superseded"  # Replaced by newer version
    ROLLED_BACK = "rolled_back"  # Rolled back due to degradation
    REJECTED = "rejected"  # Rejected during review


class ConstitutionalVersion(BaseModel):
    """Constitutional version model with semantic versioning and hash tracking.

    This model tracks versions of the constitutional framework, enabling
    evolution, rollback, and audit trails for governance changes.

    Constitutional Hash: cdd01ef066bc6cf2

    Attributes:
        version_id: Unique identifier for this version
        version: Semantic version string (major.minor.patch)
        constitutional_hash: SHA256 hash of constitutional content
        content: Full constitutional content (OPA policies, rules, principles)
        predecessor_version: Previous version ID for rollback capability
        status: Current status of this version
        metadata: Additional metadata (author, justification, metrics)
        created_at: Timestamp when version was created
        activated_at: Timestamp when version became active (if applicable)
        deactivated_at: Timestamp when version was superseded/rolled back
    """

    # Core identification
    version_id: str = Field(default_factory=lambda: str(uuid4()))
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")  # Semantic versioning

    # Constitutional content and validation
    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH,
        description="SHA256 hash of constitutional content for integrity validation",
    )
    content: JSONDict = Field(
        ..., description="Full constitutional content including OPA policies, rules, and principles"
    )

    # Version lineage for rollback
    predecessor_version: str | None = Field(
        None, description="Previous version ID for rollback capability"
    )

    # Status tracking
    status: ConstitutionalStatus = Field(default=ConstitutionalStatus.DRAFT)

    # Metadata and audit trail
    metadata: JSONDict = Field(
        default_factory=dict,
        description="Additional metadata: author, justification, governance metrics, impact score",
    )

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    activated_at: datetime | None = Field(
        None, description="Timestamp when this version became active"
    )
    deactivated_at: datetime | None = Field(
        None, description="Timestamp when this version was superseded or rolled back"
    )

    @field_serializer("created_at", "activated_at", "deactivated_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        """Serialize datetime fields to ISO format."""
        if value is None:
            return None
        return value.isoformat()

    @field_validator("version")
    @classmethod
    def validate_semantic_version(cls, v: str) -> str:
        """Validate semantic versioning format (major.minor.patch)."""
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

    @field_validator("constitutional_hash")
    @classmethod
    def validate_hash_format(cls, v: str) -> str:
        """Validate constitutional hash format (16-character hex)."""
        if not v:
            raise ValueError("Constitutional hash cannot be empty")

        # Current format is 16 hex characters
        if len(v) != 16 or not all(c in "0123456789abcdef" for c in v):
            raise ValueError(f"Constitutional hash must be 16 hexadecimal characters (got: {v})")

        return v

    def __init__(self, **data):
        """Initialize constitutional version with defaults."""
        super().__init__(**data)
        if not self.version_id:
            self.version_id = str(uuid4())

    @property
    def is_active(self) -> bool:
        """Check if this version is currently active."""
        return self.status == ConstitutionalStatus.ACTIVE

    @property
    def is_draft(self) -> bool:
        """Check if this version is in draft status."""
        return self.status == ConstitutionalStatus.DRAFT

    @property
    def is_proposed(self) -> bool:
        """Check if this version is proposed for review."""
        return self.status == ConstitutionalStatus.PROPOSED

    @property
    def is_under_review(self) -> bool:
        """Check if this version is under review."""
        return self.status == ConstitutionalStatus.UNDER_REVIEW

    @property
    def is_approved(self) -> bool:
        """Check if this version is approved but not yet active."""
        return self.status == ConstitutionalStatus.APPROVED

    @property
    def is_superseded(self) -> bool:
        """Check if this version has been superseded by a newer version."""
        return self.status == ConstitutionalStatus.SUPERSEDED

    @property
    def is_rolled_back(self) -> bool:
        """Check if this version was rolled back due to degradation."""
        return self.status == ConstitutionalStatus.ROLLED_BACK

    @property
    def is_rejected(self) -> bool:
        """Check if this version was rejected during review."""
        return self.status == ConstitutionalStatus.REJECTED

    @property
    def semantic_version_tuple(self) -> tuple[int, int, int]:
        """Get semantic version as tuple (major, minor, patch)."""
        parts = self.version.split(".")
        return (int(parts[0]), int(parts[1]), int(parts[2]))

    @property
    def major_version(self) -> int:
        """Get major version number."""
        return self.semantic_version_tuple[0]

    @property
    def minor_version(self) -> int:
        """Get minor version number."""
        return self.semantic_version_tuple[1]

    @property
    def patch_version(self) -> int:
        """Get patch version number."""
        return self.semantic_version_tuple[2]

    def activate(self) -> None:
        """Activate this constitutional version.

        Sets status to ACTIVE and records activation timestamp.
        """
        self.status = ConstitutionalStatus.ACTIVE
        if not self.activated_at:
            self.activated_at = datetime.now(UTC)

    def deactivate(self, reason: str = "superseded") -> None:
        """Deactivate this constitutional version.

        Args:
            reason: Reason for deactivation ('superseded' or 'rolled_back')

        Sets status to SUPERSEDED or ROLLED_BACK and records deactivation timestamp.
        """
        if reason == "rolled_back":
            self.status = ConstitutionalStatus.ROLLED_BACK
        else:
            self.status = ConstitutionalStatus.SUPERSEDED

        if not self.deactivated_at:
            self.deactivated_at = datetime.now(UTC)

    def to_dict(self) -> JSONDict:
        """Convert model to dictionary with serialized datetimes."""
        return self.model_dump()

    def __repr__(self) -> str:
        """String representation of constitutional version."""
        return (
            f"ConstitutionalVersion(version_id={self.version_id}, "
            f"version={self.version}, "
            f"hash={self.constitutional_hash}, "
            f"status={self.status.value})"
        )
