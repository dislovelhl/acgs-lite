"""
Pydantic v2 schemas for agent tier assignment API endpoints.
Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.core.services.api_gateway.models.tier_assignment import AutonomyTier


class AgentTierAssignmentCreate(BaseModel):
    """Schema for creating a new agent tier assignment."""

    model_config = ConfigDict(from_attributes=True)

    agent_id: str = Field(..., description="Unique identifier of the AI agent")
    tier: AutonomyTier = Field(..., description="Autonomy tier to assign")
    action_boundaries: list[str] | None = Field(
        default=None,
        description="Permitted action type patterns for BOUNDED tier (fnmatch glob patterns)",
    )


class AgentTierAssignmentUpdate(BaseModel):
    """Schema for updating an existing agent tier assignment."""

    model_config = ConfigDict(from_attributes=True)

    tier: AutonomyTier = Field(..., description="New autonomy tier value")
    action_boundaries: list[str] | None = Field(
        default=None,
        description="Updated action type patterns for BOUNDED tier",
    )


class AgentTierAssignmentResponse(BaseModel):
    """Schema for returning an agent tier assignment in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Primary key of the assignment record")
    agent_id: str = Field(..., description="Unique identifier of the AI agent")
    tenant_id: str = Field(..., description="Owning tenant identifier")
    tier: AutonomyTier = Field(..., description="Assigned autonomy tier")
    action_boundaries: list[str] | None = Field(
        default=None,
        description="Permitted action type patterns (only meaningful for BOUNDED tier)",
    )
    assigned_by: str = Field(
        ..., description="Identity of the admin who last modified the assignment"
    )
    assigned_at: datetime = Field(..., description="Timestamp of last modification (UTC)")


class TierEnforcementDecisionSchema(BaseModel):
    """Immutable audit record schema for a single tier enforcement evaluation."""

    model_config = ConfigDict(from_attributes=True)

    request_id: uuid.UUID = Field(
        ..., description="Unique request identifier (from X-Request-ID or generated)"
    )
    agent_id: str = Field(..., description="Agent that made the request")
    tenant_id: str = Field(..., description="Tenant scope of the request")
    tier_at_decision: AutonomyTier = Field(
        ..., description="Tier value used to evaluate this request"
    )
    action_type: str = Field(..., description="Type of action requested")
    outcome: str = Field(
        ...,
        description="Enforcement outcome: APPROVED | PENDING | BLOCKED | ERROR",
    )
    reason: str = Field(
        ...,
        description=(
            "Machine-readable reason: BOUNDARY_EXCEEDED | ADVISORY_QUEUED | "
            "HUMAN_APPROVAL_REQUIRED | NO_TIER_ASSIGNED | STORE_UNAVAILABLE"
        ),
    )
    constitutional_hash: str = Field(
        ...,
        description="Constitutional hash at time of decision (must equal cdd01ef066bc6cf2)",
    )
    timestamp: datetime = Field(..., description="Decision evaluation time (UTC)")
