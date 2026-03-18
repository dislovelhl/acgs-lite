"""
ACGS-2 Multi-Tenancy Models
Constitutional Hash: cdd01ef066bc6cf2

Data models for multi-tenant enterprise governance.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]


class TenantStatus(str, Enum):  # noqa: UP042
    """Tenant lifecycle status."""

    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"
    MIGRATING = "migrating"


@dataclass
class TenantQuota:
    """Resource quotas for a tenant.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    max_agents: int = 100
    max_policies: int = 1000
    max_messages_per_minute: int = 10000
    max_batch_size: int = 1000
    max_storage_mb: int = 10240  # 10 GB
    max_concurrent_sessions: int = 100

    def to_dict(self) -> dict[str, int]:
        """Convert to dictionary."""
        return {
            "max_agents": self.max_agents,
            "max_policies": self.max_policies,
            "max_messages_per_minute": self.max_messages_per_minute,
            "max_batch_size": self.max_batch_size,
            "max_storage_mb": self.max_storage_mb,
            "max_concurrent_sessions": self.max_concurrent_sessions,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "TenantQuota":
        """Create from dictionary."""
        return cls(
            max_agents=data.get("max_agents", 100),
            max_policies=data.get("max_policies", 1000),
            max_messages_per_minute=data.get("max_messages_per_minute", 10000),
            max_batch_size=data.get("max_batch_size", 1000),
            max_storage_mb=data.get("max_storage_mb", 10240),
            max_concurrent_sessions=data.get("max_concurrent_sessions", 100),
        )


@dataclass
class TenantUsage:
    """Current resource usage for a tenant.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    agent_count: int = 0
    policy_count: int = 0
    message_count_minute: int = 0
    storage_used_mb: float = 0.0
    concurrent_sessions: int = 0
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "agent_count": self.agent_count,
            "policy_count": self.policy_count,
            "message_count_minute": self.message_count_minute,
            "storage_used_mb": self.storage_used_mb,
            "concurrent_sessions": self.concurrent_sessions,
            "last_updated": self.last_updated.isoformat(),
        }

    def is_within_quota(self, quota: TenantQuota) -> bool:
        """Check if current usage is within quota limits."""
        return (
            self.agent_count <= quota.max_agents
            and self.policy_count <= quota.max_policies
            and self.message_count_minute <= quota.max_messages_per_minute
            and self.storage_used_mb <= quota.max_storage_mb
            and self.concurrent_sessions <= quota.max_concurrent_sessions
        )


class TenantConfig(BaseModel):
    """Tenant configuration settings.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH,
        description="Constitutional hash for compliance verification",
    )

    # Feature flags
    enable_batch_processing: bool = Field(
        default=True,
        description="Enable batch processing API",
    )
    enable_deliberation: bool = Field(
        default=True,
        description="Enable deliberation layer for high-impact decisions",
    )
    enable_blockchain_anchoring: bool = Field(
        default=False,
        description="Enable blockchain anchoring for audit trails",
    )
    enable_maci_enforcement: bool = Field(
        default=True,
        description="Enable MACI role-based enforcement",
    )

    # MCP tool allowlist overrides (AA03: tenant-scoped privilege restriction).
    # Maps MACIRole value → list of permitted MCP tool names.
    # Merged via INTERSECTION with system defaults (consensus C-6):
    # tenants can only RESTRICT, never EXPAND beyond system policy.
    tool_allowlist_overrides: dict[str, list[str]] | None = Field(
        default=None,
        description=(
            "Per-role MCP tool allowlist overrides. "
            "Keys are MACIRole values, values are lists of tool names. "
            "INTERSECTION-merged with system defaults."
        ),
    )

    # Performance settings
    default_timeout_ms: int = Field(
        default=5000,
        description="Default request timeout in milliseconds",
    )
    cache_ttl_seconds: int = Field(
        default=300,
        description="Cache TTL in seconds",
    )

    # Security settings
    require_jwt_auth: bool = Field(
        default=True,
        description="Require JWT authentication",
    )
    allowed_ip_ranges: list[str] = Field(
        default_factory=list,
        description="Allowed IP CIDR ranges (empty = allow all)",
    )

    # Integration settings
    sso_provider: str | None = Field(
        default=None,
        description="SSO provider (saml, oidc, ldap)",
    )
    sso_config: JSONDict = Field(
        default_factory=dict,
        description="SSO configuration details",
    )

    model_config = {"extra": "allow"}


class Tenant(BaseModel):
    """Enterprise tenant model.

    Constitutional Hash: cdd01ef066bc6cf2

    Represents an isolated tenant in the multi-tenant ACGS-2 system.
    Each tenant has its own data isolation via PostgreSQL RLS policies.
    """

    tenant_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique tenant identifier",
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable tenant name",
    )
    slug: str = Field(
        ...,
        min_length=1,
        max_length=63,
        pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$",
        description="URL-safe tenant slug (used in routing)",
    )

    status: TenantStatus = Field(
        default=TenantStatus.PENDING,
        description="Current tenant status",
    )

    config: TenantConfig = Field(
        default_factory=TenantConfig,
        description="Tenant configuration",
    )

    quota: dict[str, int] = Field(
        default_factory=lambda: TenantQuota().to_dict(),
        description="Resource quotas",
    )

    metadata: JSONDict = Field(
        default_factory=dict,
        description="Additional tenant metadata",
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Tenant creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Last update timestamp",
    )
    activated_at: datetime | None = Field(
        default=None,
        description="Activation timestamp",
    )
    suspended_at: datetime | None = Field(
        default=None,
        description="Suspension timestamp",
    )

    # Parent tenant for hierarchical tenancy
    parent_tenant_id: str | None = Field(
        default=None,
        description="Parent tenant ID for hierarchical organizations",
    )

    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH,
        description="Constitutional hash for compliance",
    )

    model_config = {"extra": "allow"}

    def is_active(self) -> bool:
        """Check if tenant is active."""
        return self.status == TenantStatus.ACTIVE

    def get_quota(self) -> TenantQuota:
        """Get tenant quota as TenantQuota object."""
        return TenantQuota.from_dict(self.quota)

    def validate_constitutional_compliance(self) -> bool:
        """Validate constitutional hash compliance."""
        return bool(
            self.constitutional_hash == CONSTITUTIONAL_HASH
            and self.config.constitutional_hash == CONSTITUTIONAL_HASH
        )

    def to_rls_context(self) -> dict[str, str]:
        """Get RLS context for database queries."""
        return {
            "tenant_id": self.tenant_id,
            "constitutional_hash": self.constitutional_hash,
        }
