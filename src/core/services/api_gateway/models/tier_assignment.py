"""
SQLAlchemy ORM model for agent tier assignments.
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class AutonomyTier(StrEnum):
    """Autonomy tier enumeration defining an AI agent's authority level."""

    ADVISORY = "ADVISORY"
    BOUNDED = "BOUNDED"
    HUMAN_APPROVED = "HUMAN_APPROVED"


class Base(DeclarativeBase):
    pass


class AgentTierAssignment(Base):
    """
    Binding between an agent identity and its current autonomy tier.

    Owned by Tenant Admin; enforced by the API Gateway middleware.
    """

    __tablename__ = "agent_tier_assignments"

    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_id", name="uq_agent_tier_assignments_tenant_agent"),
        Index("ix_agent_tier_assignments_agent_id", "agent_id"),
        Index("ix_agent_tier_assignments_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    agent_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    tenant_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    tier: Mapped[AutonomyTier] = mapped_column(
        String,
        nullable=False,
    )
    action_boundaries: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    assigned_by: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
