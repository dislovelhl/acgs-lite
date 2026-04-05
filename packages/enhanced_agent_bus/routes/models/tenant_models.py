"""Constitutional Hash: 608508a9bd224290
Tenant-related Pydantic models for the Enhanced Agent Bus API.
"""

from datetime import UTC, datetime
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
    from enhanced_agent_bus.multi_tenancy import Tenant


def _to_dict_safe(obj: object) -> dict:
    """Convert object to dict safely using Pydantic V2 model_dump().

    Constitutional Hash: 608508a9bd224290
    """
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return dict(obj.model_dump())  # type: ignore[union-attr]
    if hasattr(obj, "to_dict"):
        return dict(obj.to_dict())  # type: ignore[union-attr]
    return {}


class CreateTenantRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=2, max_length=63)
    parent_tenant_id: str | None = Field(default=None)
    config: JSONDict | None = Field(default_factory=dict)
    quota: dict[str, int] | None = Field(default=None)
    metadata: JSONDict | None = Field(default_factory=dict)
    auto_activate: bool = Field(default=False)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        import re

        if not re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", v):
            raise ValueError(
                "Slug must be lowercase alphanumeric with hyphens, "
                "start and end with alphanumeric characters"
            )
        return v.lower()

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Acme Corporation",
                "slug": "acme-corp",
                "config": {"theme": "dark", "timezone": "UTC"},
                "quota": {"max_agents": 50, "max_policies": 500},
                "auto_activate": True,
            }
        }
    }


class UpdateTenantRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    config: JSONDict | None = Field(default=None)
    metadata: JSONDict | None = Field(default=None)

    model_config = {
        "json_schema_extra": {
            "example": {"name": "Acme Corporation Ltd", "config": {"theme": "light"}}
        }
    }


class UpdateQuotaRequest(BaseModel):
    max_agents: int | None = Field(default=None, ge=1)
    max_policies: int | None = Field(default=None, ge=1)
    max_messages_per_minute: int | None = Field(default=None, ge=1)
    max_batch_size: int | None = Field(default=None, ge=1)
    max_storage_mb: int | None = Field(default=None, ge=1)
    max_concurrent_sessions: int | None = Field(default=None, ge=1)

    model_config = {"json_schema_extra": {"example": {"max_agents": 200, "max_policies": 2000}}}


class SuspendTenantRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    suspend_children: bool = Field(default=True)


class TenantResponse(BaseModel):
    tenant_id: str
    name: str
    slug: str
    status: str
    parent_tenant_id: str | None = None
    config: JSONDict = Field(default_factory=dict)
    quota: dict[str, int] = Field(default_factory=dict)
    usage: dict[str, int] = Field(default_factory=dict)
    metadata: JSONDict = Field(default_factory=dict)
    created_at: str
    updated_at: str
    activated_at: str | None = None
    suspended_at: str | None = None
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)

    @classmethod
    def from_tenant(cls, tenant: "Tenant") -> "TenantResponse":
        return cls(
            tenant_id=tenant.tenant_id,
            name=tenant.name,
            slug=tenant.slug,
            status=tenant.status.value if hasattr(tenant.status, "value") else str(tenant.status),
            parent_tenant_id=tenant.parent_tenant_id,
            config=_to_dict_safe(tenant.config),
            quota=_to_dict_safe(tenant.quota),
            usage=_to_dict_safe(tenant.usage),
            metadata=tenant.metadata or {},
            created_at=(
                tenant.created_at.isoformat()
                if tenant.created_at
                else datetime.now(UTC).isoformat()
            ),
            updated_at=(
                tenant.updated_at.isoformat()
                if tenant.updated_at
                else datetime.now(UTC).isoformat()
            ),
            activated_at=tenant.activated_at.isoformat() if tenant.activated_at else None,
            suspended_at=tenant.suspended_at.isoformat() if tenant.suspended_at else None,
            constitutional_hash=tenant.constitutional_hash or CONSTITUTIONAL_HASH,
        )


class TenantListResponse(BaseModel):
    tenants: list[TenantResponse] = Field(default_factory=list)
    total_count: int = Field(default=0)
    page: int = Field(default=0)
    page_size: int = Field(default=20)
    has_more: bool = Field(default=False)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)


class TenantHierarchyResponse(BaseModel):
    tenant_id: str
    ancestors: list[TenantResponse] = Field(default_factory=list)
    descendants: list[TenantResponse] = Field(default_factory=list)
    depth: int = Field(default=0)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)


class QuotaCheckRequest(BaseModel):
    resource: str
    requested_amount: int = Field(default=1, ge=1)


class QuotaCheckResponse(BaseModel):
    tenant_id: str
    resource: str
    available: bool
    current_usage: int = Field(default=0)
    quota_limit: int = Field(default=0)
    requested_amount: int = Field(default=1)
    remaining: int = Field(default=0)
    warning_threshold_reached: bool = Field(default=False)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)


class UsageIncrementRequest(BaseModel):
    resource: str
    amount: int = Field(default=1, ge=1)


class UsageResponse(BaseModel):
    tenant_id: str
    usage: dict[str, int] = Field(default_factory=dict)
    quota: dict[str, int] = Field(default_factory=dict)
    utilization: dict[str, float] = Field(default_factory=dict)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: JSONDict | None = None
    timestamp: str
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
