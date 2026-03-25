"""
SQLAlchemy and Pydantic models for ACGS-2 Constitutional Storage.

Constitutional Hash: 608508a9bd224290
"""

from datetime import UTC, datetime, timezone

from sqlalchemy import JSON, Column, DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase


# SQLAlchemy Base for ORM models
class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    pass


class ConstitutionalVersionDB(Base):
    """SQLAlchemy model for constitutional versions in PostgreSQL.

    Constitutional Hash: 608508a9bd224290
    Multi-Tenant Support: Phase 10 Task 1
    """

    __tablename__ = "constitutional_versions"

    version_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True, default="system")
    version = Column(String, nullable=False, index=True)
    constitutional_hash = Column(String, nullable=False)
    content = Column(JSON, nullable=False)
    predecessor_version = Column(String, nullable=True)
    status = Column(String, nullable=False, index=True)
    extra_metadata = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    activated_at = Column(DateTime, nullable=True)
    deactivated_at = Column(DateTime, nullable=True)


class AmendmentProposalDB(Base):
    """SQLAlchemy model for amendment proposals in PostgreSQL.

    Constitutional Hash: 608508a9bd224290
    Multi-Tenant Support: Phase 10 Task 1
    """

    __tablename__ = "amendment_proposals"

    proposal_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True, default="system")
    proposed_changes = Column(JSON, nullable=False)
    justification = Column(Text, nullable=False)
    proposer_agent_id = Column(String, nullable=False, index=True)
    target_version = Column(String, nullable=False)
    new_version = Column(String, nullable=True)
    status = Column(String, nullable=False, index=True)
    impact_score = Column(String, nullable=True)  # Stored as string for precision
    impact_factors = Column(JSON, nullable=False, default=dict)
    impact_recommendation = Column(Text, nullable=True)
    requires_deliberation = Column(String, nullable=False, default="false")
    governance_metrics_before = Column(JSON, nullable=False, default=dict)
    governance_metrics_after = Column(JSON, nullable=False, default=dict)
    approval_chain = Column(JSON, nullable=False, default=list)
    rejection_reason = Column(Text, nullable=True)
    rollback_reason = Column(Text, nullable=True)
    extra_metadata = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    reviewed_at = Column(DateTime, nullable=True)
    activated_at = Column(DateTime, nullable=True)
    rolled_back_at = Column(DateTime, nullable=True)
