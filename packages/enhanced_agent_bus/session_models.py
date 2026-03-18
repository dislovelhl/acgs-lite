"""
ACGS-2 Enhanced Agent Bus - Session Models
Constitutional Hash: cdd01ef066bc6cf2

Session governance models for dynamic policy application.
Split from models.py for improved maintainability.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

# Import constitutional hash
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .enums import RiskLevel

# Type alias


class SessionGovernanceConfig(BaseModel):
    """Session-level governance configuration for dynamic policy application.

    Enables different governance policies per session or user context,
    allowing fine-grained control over AI behavior based on use case,
    risk level, or tenant requirements.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    session_id: str = Field(..., description="Unique session identifier")
    tenant_id: str = Field(..., description="Tenant identifier for multi-tenant isolation")
    user_id: str | None = Field(
        default=None, description="User identifier for user-specific policies"
    )
    risk_level: RiskLevel = Field(default=RiskLevel.MEDIUM, description="Session risk level")

    # Policy configuration
    policy_id: str | None = Field(default=None, description="Primary governance policy to apply")
    policy_overrides: JSONDict = Field(
        default_factory=dict,
        description="Policy-specific overrides for this session",
    )
    enabled_policies: list[str] = Field(
        default_factory=list,
        description="List of additional policy IDs to evaluate",
    )
    disabled_policies: list[str] = Field(
        default_factory=list,
        description="List of policy IDs to skip for this session",
    )

    # Governance controls
    require_human_approval: bool = Field(
        default=False,
        description="Override to always require HITL for this session",
    )
    max_automation_level: str | None = Field(
        default=None,
        description="Maximum automation level allowed (e.g., 'full', 'partial', 'none')",
    )
    constitutional_strictness: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="Multiplier for constitutional validation strictness (1.0 = default)",
    )

    # Context and metadata
    context_tags: list[str] = Field(
        default_factory=list,
        description="Tags for context-aware policy selection",
    )
    metadata: JSONDict = Field(
        default_factory=dict,
        description="Additional session metadata",
    )

    # Constitutional compliance
    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH,
        description="Constitutional hash for compliance verification",
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When session config was created",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="When session config expires (None = never)",
    )

    model_config = {"from_attributes": True}

    def model_post_init(self, __context: object) -> None:
        """Validate constitutional hash."""
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(
                f"Invalid constitutional hash: {self.constitutional_hash}. "
                f"Expected: {CONSTITUTIONAL_HASH}"
            )

    def is_expired(self) -> bool:
        """Check if session config has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at

    def get_effective_risk_level(self) -> RiskLevel:
        """Get effective risk level considering overrides."""
        if override := self.policy_overrides.get("risk_level"):
            try:
                return RiskLevel(override)
            except ValueError:
                pass
        return self.risk_level

    def should_require_human_approval(self, impact_score: float) -> bool:
        """Determine if human approval is required based on config and impact."""
        if self.require_human_approval:
            return True
        # Risk-based thresholds
        thresholds = {
            RiskLevel.LOW: 0.9,
            RiskLevel.MEDIUM: 0.7,
            RiskLevel.HIGH: 0.5,
            RiskLevel.CRITICAL: 0.3,
        }
        threshold = thresholds.get(self.risk_level, 0.7)
        return impact_score >= threshold


class SessionContext(BaseModel):
    """Active session context with governance state.

    Tracks the current state of a session including active policies,
    audit trail, and accumulated context for governance decisions.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    session_id: str = Field(..., description="Unique session identifier")
    config: SessionGovernanceConfig = Field(..., description="Session governance configuration")

    # Active state
    is_active: bool = Field(default=True, description="Whether session is currently active")
    current_policy_version: str | None = Field(
        default=None,
        description="Version of currently applied policy",
    )

    # Accumulated context
    request_count: int = Field(default=0, description="Number of requests in this session")
    violation_count: int = Field(default=0, description="Number of governance violations")
    escalation_count: int = Field(default=0, description="Number of HITL escalations")

    # Policy history for audit
    policy_changes: list[JSONDict] = Field(
        default_factory=list,
        description="History of policy changes during session",
    )

    # Constitutional compliance
    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH,
        description="Constitutional hash for compliance verification",
    )

    # Timestamps
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When session started",
    )
    last_activity_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Last activity timestamp",
    )

    model_config = {"from_attributes": True}

    def record_request(self) -> None:
        """Record a request in this session."""
        self.request_count += 1
        self.last_activity_at = datetime.now(UTC)

    def record_violation(self) -> None:
        """Record a governance violation."""
        self.violation_count += 1
        self.last_activity_at = datetime.now(UTC)

    def record_escalation(self) -> None:
        """Record an escalation to human approval."""
        self.escalation_count += 1
        self.last_activity_at = datetime.now(UTC)

    def record_policy_change(
        self,
        old_policy: str | None,
        new_policy: str,
        reason: str,
    ) -> None:
        """Record a policy change for audit trail."""
        self.policy_changes.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "old_policy": old_policy,
                "new_policy": new_policy,
                "reason": reason,
            }
        )
        self.current_policy_version = new_policy
        self.last_activity_at = datetime.now(UTC)

    def to_audit_dict(self) -> JSONDict:
        """Convert to dictionary for audit logging."""
        return {
            "session_id": self.session_id,
            "tenant_id": self.config.tenant_id,
            "user_id": self.config.user_id,
            "risk_level": self.config.risk_level.value,
            "request_count": self.request_count,
            "violation_count": self.violation_count,
            "escalation_count": self.escalation_count,
            "policy_changes": len(self.policy_changes),
            "started_at": self.started_at.isoformat(),
            "last_activity_at": self.last_activity_at.isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }


__all__ = [
    "SessionContext",
    "SessionGovernanceConfig",
]
