"""
ACGS-2 Session Governance - Request/Response Models
Constitutional Hash: 608508a9bd224290

Pydantic models for session governance API endpoints.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

if TYPE_CHECKING:
    from ..session_context import SessionContext
    from .models import SessionGovernanceConfig


# =============================================================================
# Request Models
# =============================================================================


class CreateSessionRequest(BaseModel):
    """Request model for creating a new session with governance configuration."""

    session_id: str | None = Field(
        default=None,
        description="Optional session ID (generated if not provided)",
        max_length=128,
    )
    tenant_id: str | None = Field(
        default=None,
        description="Tenant ID (extracted from header if not provided)",
        max_length=100,
    )
    user_id: str | None = Field(
        default=None,
        description="User identifier for user-specific policies",
        max_length=255,
    )
    risk_level: str = Field(
        default="medium",
        description="Session risk level: low, medium, high, critical",
    )
    policy_id: str | None = Field(
        default=None,
        description="Primary governance policy ID to apply",
        max_length=100,
    )
    policy_overrides: JSONDict = Field(
        default_factory=dict,
        description="Policy-specific overrides for this session",
    )
    enabled_policies: list[str] = Field(
        default_factory=list,
        description="list of additional policy IDs to evaluate",
    )
    disabled_policies: list[str] = Field(
        default_factory=list,
        description="list of policy IDs to skip for this session",
    )
    require_human_approval: bool = Field(
        default=False,
        description="Override to always require HITL for this session",
    )
    max_automation_level: str | None = Field(
        default=None,
        description="Maximum automation level allowed (full, partial, none)",
    )
    metadata: JSONDict = Field(
        default_factory=dict,
        description="Additional session metadata",
    )
    ttl_seconds: int | None = Field(
        default=None,
        description="Session time-to-live in seconds (default: 3600)",
        ge=60,
        le=86400,  # Max 24 hours
    )

    @field_validator("risk_level")
    @classmethod
    def validate_risk_level(cls, v: str) -> str:
        valid_levels = {"low", "medium", "high", "critical"}
        if v.lower() not in valid_levels:
            raise ValueError(f"risk_level must be one of: {', '.join(valid_levels)}")
        return v.lower()

    @field_validator("max_automation_level")
    @classmethod
    def validate_automation_level(cls, v: str | None) -> str | None:
        if v is None:
            return None
        valid_levels = {"full", "partial", "none"}
        if v.lower() not in valid_levels:
            raise ValueError(f"max_automation_level must be one of: {', '.join(valid_levels)}")
        return v.lower()

    model_config = {
        "json_schema_extra": {
            "example": {
                "user_id": "user-12345",
                "risk_level": "medium",
                "policy_id": "policy-default-v1",
                "require_human_approval": False,
                "metadata": {"source": "web-app", "user_agent": "Mozilla/5.0"},
                "ttl_seconds": 3600,
            }
        }
    }


class UpdateGovernanceRequest(BaseModel):
    """Request model for updating session governance configuration."""

    risk_level: str | None = Field(
        default=None,
        description="New session risk level",
    )
    policy_id: str | None = Field(
        default=None,
        description="New primary governance policy ID",
    )
    policy_overrides: JSONDict | None = Field(
        default=None,
        description="New policy overrides (replaces existing)",
    )
    enabled_policies: list[str] | None = Field(
        default=None,
        description="New list of enabled policies",
    )
    disabled_policies: list[str] | None = Field(
        default=None,
        description="New list of disabled policies",
    )
    require_human_approval: bool | None = Field(
        default=None,
        description="New HITL requirement setting",
    )
    max_automation_level: str | None = Field(
        default=None,
        description="New maximum automation level",
    )
    metadata: JSONDict | None = Field(
        default=None,
        description="Metadata to merge with existing",
    )
    extend_ttl_seconds: int | None = Field(
        default=None,
        description="Extend session TTL by this many seconds",
        ge=60,
        le=86400,
    )

    @field_validator("risk_level")
    @classmethod
    def validate_risk_level(cls, v: str | None) -> str | None:
        if v is None:
            return None
        valid_levels = {"low", "medium", "high", "critical"}
        if v.lower() not in valid_levels:
            raise ValueError(f"risk_level must be one of: {', '.join(valid_levels)}")
        return v.lower()

    model_config = {
        "json_schema_extra": {
            "example": {
                "risk_level": "high",
                "require_human_approval": True,
                "extend_ttl_seconds": 1800,
            }
        }
    }


class PolicySelectionRequest(BaseModel):
    """Request model for context-driven policy selection."""

    policy_name_filter: str | None = Field(
        default=None,
        description="Filter policies by name (exact match)",
        max_length=100,
    )
    include_disabled: bool = Field(
        default=False,
        description="Include policies from disabled_policies list",
    )
    include_all_candidates: bool = Field(
        default=False,
        description="Include all candidate policies, not just the selected one",
    )
    risk_level_override: str | None = Field(
        default=None,
        description="Override session risk level for this selection",
    )

    @field_validator("risk_level_override")
    @classmethod
    def validate_risk_level_override(cls, v: str | None) -> str | None:
        if v is None:
            return None
        valid_levels = {"low", "medium", "high", "critical"}
        if v.lower() not in valid_levels:
            raise ValueError(f"risk_level_override must be one of: {', '.join(valid_levels)}")
        return v.lower()


# =============================================================================
# Response Models
# =============================================================================


class SessionResponse(BaseModel):
    """Response model for session operations."""

    session_id: str = Field(..., description="Unique session identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: str | None = Field(default=None, description="User identifier")
    risk_level: str = Field(..., description="Current risk level")
    policy_id: str | None = Field(default=None, description="Active policy ID")
    policy_overrides: JSONDict = Field(default_factory=dict, description="Policy overrides")
    enabled_policies: list[str] = Field(default_factory=list, description="Enabled policies")
    disabled_policies: list[str] = Field(default_factory=list, description="Disabled policies")
    require_human_approval: bool = Field(default=False, description="HITL requirement")
    max_automation_level: str | None = Field(default=None, description="Max automation level")
    metadata: JSONDict = Field(default_factory=dict, description="Session metadata")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    updated_at: str = Field(..., description="ISO 8601 last update timestamp")
    expires_at: str | None = Field(default=None, description="ISO 8601 expiration timestamp")
    ttl_remaining_seconds: int | None = Field(default=None, description="Remaining TTL in seconds")
    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH, description="Constitutional hash for verification"
    )

    @classmethod
    def from_session_context(
        cls, context: SessionContext, ttl_remaining: int | None = None
    ) -> SessionResponse:
        """Create response from SessionContext."""
        config = context.governance_config
        return cls(
            session_id=context.session_id,
            tenant_id=config.tenant_id,
            user_id=config.user_id,
            risk_level=(
                config.risk_level.value
                if hasattr(config.risk_level, "value")
                else str(config.risk_level)
            ),
            policy_id=config.policy_id,
            policy_overrides=config.policy_overrides,
            enabled_policies=config.enabled_policies,
            disabled_policies=config.disabled_policies,
            require_human_approval=config.require_human_approval,
            max_automation_level=config.max_automation_level,
            metadata=context.metadata,
            created_at=context.created_at.isoformat(),
            updated_at=context.updated_at.isoformat(),
            expires_at=context.expires_at.isoformat() if context.expires_at else None,
            ttl_remaining_seconds=ttl_remaining,
            constitutional_hash=context.constitutional_hash,
        )


class SessionListResponse(BaseModel):
    """Response model for listing sessions (admin use)."""

    sessions: list[SessionResponse] = Field(default_factory=list, description="list of sessions")
    total_count: int = Field(default=0, description="Total number of sessions")
    page: int = Field(default=1, description="Current page number")
    page_size: int = Field(default=20, description="Number of items per page")


class SessionMetricsResponse(BaseModel):
    """Response model for session manager metrics."""

    cache_hits: int = Field(default=0, description="Cache hit count")
    cache_misses: int = Field(default=0, description="Cache miss count")
    cache_hit_rate: float = Field(default=0.0, description="Cache hit rate (0-1)")
    cache_size: int = Field(default=0, description="Current cache size")
    cache_capacity: int = Field(default=0, description="Maximum cache capacity")
    creates: int = Field(default=0, description="Total sessions created")
    reads: int = Field(default=0, description="Total session reads")
    updates: int = Field(default=0, description="Total session updates")
    deletes: int = Field(default=0, description="Total session deletions")
    errors: int = Field(default=0, description="Total errors")
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH, description="Constitutional hash")


class SelectedPolicy(BaseModel):
    """Model for a selected policy in policy selection response."""

    policy_id: str = Field(..., description="Policy identifier")
    name: str = Field(..., description="Policy name")
    version: str | None = Field(default=None, description="Policy version")
    source: str = Field(..., description="Selection source: session, tenant, or global")
    priority: int = Field(default=0, description="Policy priority (higher = more important)")
    reasoning: str = Field(..., description="Explanation for why this policy was selected")
    metadata: JSONDict = Field(default_factory=dict, description="Additional policy metadata")

    model_config = {
        "json_schema_extra": {
            "example": {
                "policy_id": "policy-strict-governance-v1",
                "name": "Strict Governance Policy",
                "version": "1.0.0",
                "source": "session",
                "priority": 100,
                "reasoning": "Session override with policy_id=policy-strict-governance-v1",
                "metadata": {"risk_levels": ["high", "critical"]},
            }
        }
    }


class PolicySelectionResponse(BaseModel):
    """Response model for context-driven policy selection."""

    session_id: str = Field(..., description="Session identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    risk_level: str = Field(..., description="Risk level used for selection")
    selected_policy: SelectedPolicy | None = Field(
        default=None, description="Primary selected policy"
    )
    candidate_policies: list[SelectedPolicy] = Field(
        default_factory=list,
        description="All candidate policies (if include_all_candidates=true)",
    )
    enabled_policies: list[str] = Field(
        default_factory=list, description="Session's enabled policy IDs"
    )
    disabled_policies: list[str] = Field(
        default_factory=list, description="Session's disabled policy IDs"
    )
    selection_metadata: JSONDict = Field(
        default_factory=dict,
        description="Selection process metadata (timing, cache hit, etc.)",
    )
    timestamp: str = Field(..., description="Selection timestamp (ISO 8601)")
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH, description="Constitutional hash")

    model_config = {
        "json_schema_extra": {
            "example": {
                "session_id": "session-12345",
                "tenant_id": "tenant-abc",
                "risk_level": "high",
                "selected_policy": {
                    "policy_id": "policy-strict-v1",
                    "name": "Strict Policy",
                    "version": "1.0.0",
                    "source": "tenant",
                    "priority": 90,
                    "reasoning": "Tenant policy for risk_level=high",
                    "metadata": {},
                },
                "candidate_policies": [],
                "enabled_policies": ["policy-audit-v1"],
                "disabled_policies": ["policy-lenient-v1"],
                "selection_metadata": {
                    "cache_hit": True,
                    "elapsed_ms": 0.42,
                },
                "timestamp": "2026-01-12T00:00:00Z",
                "constitutional_hash": CONSTITUTIONAL_HASH,  # pragma: allowlist secret
            }
        }
    }


class ErrorResponse(BaseModel):
    """Standard error response format."""

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: JSONDict | None = Field(default=None, description="Additional error details")
    timestamp: str = Field(..., description="Error timestamp")
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH, description="Constitutional hash")


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Request models
    "CreateSessionRequest",
    "ErrorResponse",
    "PolicySelectionRequest",
    "PolicySelectionResponse",
    "SelectedPolicy",
    "SessionListResponse",
    "SessionMetricsResponse",
    # Response models
    "SessionResponse",
    "UpdateGovernanceRequest",
]
