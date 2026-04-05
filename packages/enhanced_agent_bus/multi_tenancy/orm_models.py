"""
ACGS-2 Multi-Tenancy SQLAlchemy ORM Models
Constitutional Hash: 608508a9bd224290

SQLAlchemy ORM models for persistent multi-tenant database storage.
These models correspond to the Pydantic models in models.py and provide
database persistence via PostgreSQL with Row-Level Security support.
"""

import sys
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

# Cross-database compatible JSON type
# Uses JSONB on PostgreSQL for performance, falls back to JSON on SQLite
JSONType = JSON().with_variant(JSONB(), "postgresql")

# Constitutional hash constant
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.database.session import Base

# Ensure module aliasing across package import paths to avoid duplicate ORM definitions
_module = sys.modules.get(__name__)
if _module is not None:
    sys.modules.setdefault("enhanced_agent_bus.multi_tenancy.orm_models", _module)
    sys.modules.setdefault("enhanced_agent_bus.multi_tenancy.orm_models", _module)
    sys.modules.setdefault("core.enhanced_agent_bus.multi_tenancy.orm_models", _module)


class TenantStatusEnum:
    """Tenant lifecycle status values."""

    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"
    MIGRATING = "migrating"


class TenantORM(Base):
    """
    SQLAlchemy ORM model for enterprise tenants.

    Constitutional Hash: 608508a9bd224290

    Represents an isolated tenant in the multi-tenant ACGS-2 system.
    Each tenant has its own data isolation via PostgreSQL RLS policies.

    Attributes:
        tenant_id: Unique tenant identifier (UUID).
        name: Human-readable tenant name.
        slug: URL-safe tenant slug for routing.
        status: Current lifecycle status.
        config: JSON configuration settings.
        quota: Resource quota limits.
        metadata: Additional tenant metadata.
        parent_tenant_id: Parent tenant for hierarchical organizations.
        constitutional_hash: Hash for compliance verification.
    """

    __tablename__ = "tenants"

    # Primary key
    tenant_id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        comment="Unique tenant identifier (UUID)",
    )

    # Basic info
    name = Column(
        String(255),
        nullable=False,
        comment="Human-readable tenant name",
    )
    slug = Column(
        String(63),
        nullable=False,
        unique=True,
        index=True,
        comment="URL-safe tenant slug for routing",
    )

    # Status
    status = Column(
        String(20),
        nullable=False,
        default=TenantStatusEnum.PENDING,
        index=True,
        comment="Current tenant lifecycle status",
    )

    # Configuration (stored as JSON)
    config = Column(
        JSONType,
        nullable=False,
        default=dict,
        comment="Tenant configuration settings",
    )

    # Quota limits (stored as JSON)
    quota = Column(
        JSONType,
        nullable=False,
        default=dict,
        comment="Resource quota limits",
    )

    # Metadata (stored as JSON)
    metadata_ = Column(
        "metadata",
        JSONType,
        nullable=False,
        default=dict,
        comment="Additional tenant metadata",
    )

    # Hierarchical tenancy
    parent_tenant_id = Column(
        String(36),
        ForeignKey("tenants.tenant_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Parent tenant ID for hierarchical organizations",
    )

    # Constitutional compliance
    constitutional_hash = Column(
        String(16),
        nullable=False,
        default=CONSTITUTIONAL_HASH,
        comment="Constitutional hash for compliance verification",
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Tenant creation timestamp",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        comment="Last update timestamp",
    )
    activated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Activation timestamp",
    )
    suspended_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Suspension timestamp",
    )

    # Relationships - self-referential for tenant hierarchy
    # Use string-based foreign_keys and primaryjoin for robust resolution
    # under importlib mode + xdist parallel workers.
    children = relationship(
        "TenantORM",
        primaryjoin="TenantORM.tenant_id == foreign(TenantORM.parent_tenant_id)",
        lazy="selectin",
        passive_deletes=True,
    )
    parent = relationship(
        "TenantORM",
        primaryjoin="TenantORM.parent_tenant_id == foreign(TenantORM.tenant_id)",
        remote_side="TenantORM.tenant_id",
        lazy="selectin",
        viewonly=True,
    )

    # Reverse relationships — standalone (no back_populates/backref) to avoid
    # mapper cross-reference failures under importlib + xdist parallel workers.
    integrations = relationship(
        "EnterpriseIntegrationORM",
        foreign_keys="EnterpriseIntegrationORM.tenant_id",
        viewonly=True,
    )
    role_mappings = relationship(
        "TenantRoleMappingORM",
        foreign_keys="TenantRoleMappingORM.tenant_id",
        viewonly=True,
    )
    migration_jobs = relationship(
        "MigrationJobORM",
        foreign_keys="MigrationJobORM.tenant_id",
        viewonly=True,
    )
    audit_logs = relationship(
        "TenantAuditLogORM",
        foreign_keys="TenantAuditLogORM.tenant_id",
        viewonly=True,
    )

    # Table constraints and indexes
    __table_args__ = (
        Index("ix_tenants_status_created", "status", "created_at"),
        Index("ix_tenants_parent_status", "parent_tenant_id", "status"),
        {
            "comment": "ACGS-2 enterprise tenants with hierarchical support",
            "extend_existing": True,
        },
    )

    def __repr__(self) -> str:
        return f"<TenantORM(tenant_id={self.tenant_id}, slug={self.slug}, status={self.status})>"

    def is_active(self) -> bool:
        """Check if tenant is active."""
        return bool(self.status == TenantStatusEnum.ACTIVE)

    def validate_constitutional_compliance(self) -> bool:
        """Validate constitutional hash compliance."""
        return bool(self.constitutional_hash == CONSTITUTIONAL_HASH)


def _dedupe_indexes() -> None:
    """Remove duplicate index objects by name from metadata tables."""
    for table in Base.metadata.tables.values():
        seen = set()
        for idx in list(table.indexes):
            if idx.name in seen:
                table.indexes.remove(idx)
            else:
                seen.add(idx.name)


class EnterpriseIntegrationORM(Base):
    """
    SQLAlchemy ORM model for enterprise integrations.

    Constitutional Hash: 608508a9bd224290

    Stores SSO, LDAP, and other enterprise integration configurations
    per tenant.

    Attributes:
        integration_id: Unique integration identifier.
        tenant_id: Owning tenant.
        integration_type: Type of integration (sso, ldap, scim, etc.).
        provider: Integration provider (okta, azure_ad, etc.).
        config: Provider-specific configuration.
        enabled: Whether integration is active.
    """

    __tablename__ = "enterprise_integrations"

    # Primary key
    integration_id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        comment="Unique integration identifier (UUID)",
    )

    # Tenant reference
    tenant_id = Column(
        String(36),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning tenant ID",
    )

    # Integration type and provider
    integration_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Integration type (sso, ldap, scim, saml, oidc)",
    )
    provider = Column(
        String(100),
        nullable=False,
        comment="Integration provider (okta, azure_ad, google, etc.)",
    )
    name = Column(
        String(255),
        nullable=False,
        comment="Human-readable integration name",
    )

    # Configuration (stored as JSON, encrypted at rest)
    config = Column(
        JSONType,
        nullable=False,
        default=dict,
        comment="Provider-specific configuration (sensitive fields encrypted)",
    )

    # Status
    enabled = Column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether integration is active",
    )

    # Constitutional compliance
    constitutional_hash = Column(
        String(16),
        nullable=False,
        default=CONSTITUTIONAL_HASH,
        comment="Constitutional hash for compliance verification",
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Integration creation timestamp",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        comment="Last update timestamp",
    )
    last_sync_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last successful sync timestamp",
    )

    # Relationships
    # Standalone relationship (no back_populates/backref) for xdist + importlib compat
    tenant = relationship("TenantORM", viewonly=True)
    role_mappings = relationship(
        "TenantRoleMappingORM",
        foreign_keys="TenantRoleMappingORM.integration_id",
        viewonly=True,
    )

    # Table constraints
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "integration_type",
            "provider",
            name="uq_enterprise_integrations_tenant_type_provider",
        ),
        Index("ix_enterprise_integrations_tenant_type", "tenant_id", "integration_type"),
        {
            "comment": "ACGS-2 enterprise integration configurations",
            "extend_existing": True,
        },
    )

    def __repr__(self) -> str:
        return f"<EnterpriseIntegrationORM(integration_id={self.integration_id}, type={self.integration_type})>"


class TenantRoleMappingORM(Base):
    """
    SQLAlchemy ORM model for tenant role mappings.

    Constitutional Hash: 608508a9bd224290

    Maps external identity provider groups/roles to internal ACGS-2 roles.
    Supports SSO group-to-role translation and MACI role assignment.

    Attributes:
        mapping_id: Unique mapping identifier.
        tenant_id: Owning tenant.
        integration_id: Associated enterprise integration.
        external_role: External group/role name from IdP.
        internal_role: ACGS-2 internal role (MACI role or custom).
        priority: Mapping priority for conflict resolution.
    """

    __tablename__ = "tenant_role_mappings"

    # Primary key
    mapping_id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        comment="Unique mapping identifier (UUID)",
    )

    # References
    tenant_id = Column(
        String(36),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning tenant ID",
    )
    integration_id = Column(
        String(36),
        ForeignKey("enterprise_integrations.integration_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Associated integration ID (null for manual mappings)",
    )

    # Role mapping
    external_role = Column(
        String(255),
        nullable=False,
        comment="External group/role name from identity provider",
    )
    internal_role = Column(
        String(100),
        nullable=False,
        comment="ACGS-2 internal role (MACI role or custom role)",
    )

    # Priority for conflict resolution
    priority = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Mapping priority (higher = applied first for conflicts)",
    )

    # Description
    description = Column(
        Text,
        nullable=True,
        comment="Optional description of this role mapping",
    )

    # Constitutional compliance
    constitutional_hash = Column(
        String(16),
        nullable=False,
        default=CONSTITUTIONAL_HASH,
        comment="Constitutional hash for compliance verification",
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Mapping creation timestamp",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        comment="Last update timestamp",
    )

    # Relationships — standalone for xdist + importlib compatibility
    tenant = relationship("TenantORM", viewonly=True)
    integration = relationship("EnterpriseIntegrationORM", viewonly=True)

    # Table constraints
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "integration_id",
            "external_role",
            name="uq_tenant_role_mappings_tenant_integration_external",
        ),
        Index("ix_tenant_role_mappings_tenant_internal", "tenant_id", "internal_role"),
        {
            "comment": "ACGS-2 tenant role mappings for SSO integration",
            "extend_existing": True,
        },
    )

    def __repr__(self) -> str:
        return f"<TenantRoleMappingORM(mapping_id={self.mapping_id}, external={self.external_role}, internal={self.internal_role})>"


class MigrationJobORM(Base):
    """
    SQLAlchemy ORM model for tenant migration jobs.

    Constitutional Hash: 608508a9bd224290

    Tracks tenant data migration operations for cross-region moves,
    schema upgrades, and data transformations.

    Attributes:
        job_id: Unique job identifier.
        tenant_id: Tenant being migrated.
        job_type: Type of migration (region, schema, data).
        status: Current job status.
        progress: Completion percentage.
        source_region: Source region/database.
        target_region: Target region/database.
    """

    __tablename__ = "migration_jobs"

    # Primary key
    job_id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        comment="Unique job identifier (UUID)",
    )

    # Tenant reference
    tenant_id = Column(
        String(36),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Tenant being migrated",
    )

    # Job details
    job_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Migration type (region, schema, data, upgrade)",
    )
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
        comment="Job status (pending, running, completed, failed, cancelled)",
    )
    progress = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Completion percentage (0.0 - 100.0)",
    )

    # Migration source/target
    source_region = Column(
        String(100),
        nullable=True,
        comment="Source region or database identifier",
    )
    target_region = Column(
        String(100),
        nullable=True,
        comment="Target region or database identifier",
    )

    # Job configuration and results
    config = Column(
        JSONType,
        nullable=False,
        default=dict,
        comment="Job configuration parameters",
    )
    result = Column(
        JSONType,
        nullable=True,
        comment="Job result data and statistics",
    )
    error_message = Column(
        Text,
        nullable=True,
        comment="Error message if job failed",
    )

    # Constitutional compliance
    constitutional_hash = Column(
        String(16),
        nullable=False,
        default=CONSTITUTIONAL_HASH,
        comment="Constitutional hash for compliance verification",
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Job creation timestamp",
    )
    started_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Job start timestamp",
    )
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Job completion timestamp",
    )

    # Relationships
    # Standalone relationship for xdist + importlib compatibility
    tenant = relationship("TenantORM", viewonly=True)

    # Table constraints
    __table_args__ = (
        Index("ix_migration_jobs_tenant_status", "tenant_id", "status"),
        Index("ix_migration_jobs_status_created", "status", "created_at"),
        {
            "comment": "ACGS-2 tenant migration job tracking",
            "extend_existing": True,
        },
    )

    def __repr__(self) -> str:
        return (
            f"<MigrationJobORM(job_id={self.job_id}, type={self.job_type}, status={self.status})>"
        )


class TenantAuditLogORM(Base):
    """
    SQLAlchemy ORM model for tenant audit logs.

    Constitutional Hash: 608508a9bd224290

    Immutable audit trail for tenant operations, configuration changes,
    and security events. Critical for compliance and forensics.

    Attributes:
        log_id: Unique log entry identifier.
        tenant_id: Affected tenant.
        action: Action performed.
        actor_id: User/system that performed action.
        actor_type: Type of actor (user, system, integration).
        details: Action details and before/after state.
    """

    __tablename__ = "tenant_audit_log"

    # Primary key
    log_id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        comment="Unique log entry identifier (UUID)",
    )

    # Tenant reference
    tenant_id = Column(
        String(36),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Affected tenant ID",
    )

    # Action details
    action = Column(
        String(100),
        nullable=False,
        index=True,
        comment="Action performed (create, update, delete, activate, suspend, etc.)",
    )
    resource_type = Column(
        String(100),
        nullable=False,
        default="tenant",
        index=True,
        comment="Type of resource affected",
    )
    resource_id = Column(
        String(36),
        nullable=True,
        index=True,
        comment="ID of specific resource affected (if not tenant itself)",
    )

    # Actor information
    actor_id = Column(
        String(255),
        nullable=False,
        index=True,
        comment="ID of user/system that performed action",
    )
    actor_type = Column(
        String(50),
        nullable=False,
        default="user",
        comment="Type of actor (user, system, integration, api_key)",
    )
    actor_ip = Column(
        String(45),
        nullable=True,
        comment="IP address of actor (IPv4 or IPv6)",
    )

    # Details (stored as JSON)
    details = Column(
        JSONType,
        nullable=False,
        default=dict,
        comment="Action details including before/after state",
    )

    # Constitutional compliance
    constitutional_hash = Column(
        String(16),
        nullable=False,
        default=CONSTITUTIONAL_HASH,
        comment="Constitutional hash for compliance verification",
    )

    # Timestamp (immutable)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
        comment="Log entry timestamp (immutable)",
    )

    # Relationships
    # Standalone relationship for xdist + importlib compatibility
    tenant = relationship("TenantORM", viewonly=True)

    # Table constraints
    __table_args__ = (
        Index("ix_tenant_audit_log_tenant_created", "tenant_id", "created_at"),
        Index("ix_tenant_audit_log_action_created", "action", "created_at"),
        Index("ix_tenant_audit_log_actor_created", "actor_id", "created_at"),
        {
            "comment": "ACGS-2 tenant audit log for compliance and forensics",
            "extend_existing": True,
        },
    )

    def __repr__(self) -> str:
        return f"<TenantAuditLogORM(log_id={self.log_id}, action={self.action}, tenant_id={self.tenant_id})>"


def _dedupe_class_registry() -> None:
    """Ensure class registry resolves ORM names to this module's classes.

    Test suites import ORM modules via multiple package paths. When the same
    declarative base sees classes with identical names, SQLAlchemy stores a
    "multiple classes" marker and string-based relationships fail to resolve.
    This normalizes the registry to the classes defined here.
    """

    registry = Base.registry._class_registry
    for class_name in (
        "TenantORM",
        "EnterpriseIntegrationORM",
        "TenantRoleMappingORM",
        "MigrationJobORM",
        "TenantAuditLogORM",
    ):
        current = registry.get(class_name)
        desired = globals().get(class_name)
        if desired is None or current is desired:
            continue
        if not isinstance(current, type):
            registry[class_name] = desired
            continue
        registry[class_name] = desired


_dedupe_class_registry()
_dedupe_indexes()

# Force early mapper configuration to avoid lazy-init failures under xdist.
# If configuration fails (due to cross-worker import races), clear the failure
# flag so subsequent attempts can succeed.
MAPPER_CONFIGURATION_ERRORS = (Exception,)

try:
    from sqlalchemy.orm import configure_mappers

    configure_mappers()
except MAPPER_CONFIGURATION_ERRORS:
    # Clear _configure_failed on all mappers so they retry on next access
    for _mapper in Base.registry.mappers:
        if hasattr(_mapper, "_configure_failed"):
            _mapper._configure_failed = False
