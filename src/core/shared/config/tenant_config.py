"""
ACGS-2 Tenant Configuration Models
Constitutional Hash: 608508a9bd224290

Pydantic configuration models for multi-tenant quota management.
Supports namespace-based tenant isolation with configurable resource quotas.
"""

import re
from functools import lru_cache

from pydantic import Field, field_validator

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    HAS_PYDANTIC_SETTINGS = True
except ImportError:
    HAS_PYDANTIC_SETTINGS = False
    from pydantic import BaseModel as BaseSettings

    class SettingsConfigDict(dict):
        """Fallback stub for pydantic_settings.SettingsConfigDict when pydantic-settings is unavailable."""


# Tenant ID validation constants
TENANT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-_]{0,62}[a-zA-Z0-9]$|^[a-zA-Z0-9]$")
TENANT_ID_MAX_LENGTH = 64


class TenantQuotaConfig(BaseSettings):
    """Resource quota configuration for a single tenant.

    Defines CPU, memory, storage limits and rate limiting settings
    for Kubernetes namespace-based tenant isolation.

    Example usage:
        # Default configuration
        config = TenantQuotaConfig(cpu='2', memory='4Gi')

        # Custom configuration with rate limits
        config = TenantQuotaConfig(
            cpu='4',
            memory='8Gi',
            storage='50Gi',
            rate_limit_requests=5000,
            rate_limit_window_seconds=60,
        )

        # From environment variables
        config = TenantQuotaConfig()  # Reads TENANT_DEFAULT_* env vars
    """

    if HAS_PYDANTIC_SETTINGS:
        model_config = SettingsConfigDict(
            env_prefix="TENANT_DEFAULT_",
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
            populate_by_name=True,
        )

    # Resource quotas (Kubernetes-compatible format)
    cpu: str = Field(
        default="2",
        description="CPU quota (e.g., '2' for 2 cores or '2000m' for 2000 millicores)",
        validation_alias="TENANT_DEFAULT_CPU_QUOTA",
    )
    memory: str = Field(
        default="4Gi",
        description="Memory quota (e.g., '4Gi', '4096Mi')",
        validation_alias="TENANT_DEFAULT_MEMORY_QUOTA",
    )
    storage: str = Field(
        default="20Gi",
        description="Storage quota (e.g., '20Gi')",
        validation_alias="TENANT_DEFAULT_STORAGE_QUOTA",
    )

    # Rate limiting settings
    rate_limit_requests: int = Field(
        default=1000,
        ge=1,
        le=1000000,
        description="Maximum requests allowed per rate limit window",
        validation_alias="TENANT_DEFAULT_RATE_LIMIT_REQUESTS",
    )
    rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        le=86400,
        description="Rate limit window duration in seconds",
        validation_alias="TENANT_DEFAULT_RATE_LIMIT_WINDOW",
    )

    # PersistentVolumeClaims limit
    max_pvcs: int = Field(
        default=10,
        ge=0,
        le=1000,
        description="Maximum number of PersistentVolumeClaims allowed",
        validation_alias="TENANT_DEFAULT_MAX_PVCS",
    )

    # Pod limits
    max_pods: int = Field(
        default=50,
        ge=1,
        le=10000,
        description="Maximum number of pods allowed in tenant namespace",
        validation_alias="TENANT_DEFAULT_MAX_PODS",
    )

    @field_validator("cpu")
    @classmethod
    def validate_cpu_format(cls, v: str) -> str:
        """Validate CPU quota format (e.g., '2', '2000m', '0.5')."""
        # Kubernetes CPU format: integer, float, or millicores (e.g., 100m)
        cpu_pattern = re.compile(r"^(\d+\.?\d*|\d*\.?\d+)(m)?$")
        if not cpu_pattern.match(v):
            raise ValueError(
                f"Invalid CPU quota format '{v}'. "
                "Expected format: integer (e.g., '2'), float (e.g., '0.5'), "
                "or millicores (e.g., '2000m')"
            )
        return v

    @field_validator("memory", "storage")
    @classmethod
    def validate_memory_storage_format(cls, v: str) -> str:
        """Validate memory/storage quota format (e.g., '4Gi', '4096Mi')."""
        # Kubernetes memory/storage format: number with optional suffix
        # Suffixes: Ki, Mi, Gi, Ti, Pi, Ei (binary) or k, M, G, T, P, E (decimal)
        memory_pattern = re.compile(r"^(\d+)(Ki|Mi|Gi|Ti|Pi|Ei|k|M|G|T|P|E)?$")
        if not memory_pattern.match(v):
            raise ValueError(
                f"Invalid memory/storage quota format '{v}'. "
                "Expected format: number with optional suffix "
                "(e.g., '4Gi', '4096Mi', '4096')"
            )
        return v


class TenantConfig(BaseSettings):
    """Configuration for a specific tenant including identity and quotas.

    Combines tenant identification with resource quota configuration.
    Used for tenant-specific settings in multi-tenant deployments.

    Example usage:
        config = TenantConfig(
            tenant_id='acme-corp',
            namespace_prefix='tenant-',
            quotas=TenantQuotaConfig(cpu='4', memory='8Gi'),
        )
    """

    if HAS_PYDANTIC_SETTINGS:
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
            populate_by_name=True,
        )

    tenant_id: str = Field(
        default="acgs-dev",
        min_length=1,
        max_length=TENANT_ID_MAX_LENGTH,
        description="Unique tenant identifier (alphanumeric with hyphens/underscores)",
        validation_alias="TENANT_ID",
    )

    namespace_prefix: str = Field(
        default="tenant-",
        description="Prefix for Kubernetes namespace names",
        validation_alias="K8S_NAMESPACE_PREFIX",
    )

    quotas: TenantQuotaConfig = Field(
        default_factory=TenantQuotaConfig,
        description="Resource quota configuration for this tenant",
    )

    # Tenant status
    enabled: bool = Field(
        default=True,
        description="Whether the tenant is active and can make requests",
        validation_alias="TENANT_ENABLED",
    )

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant_id(cls, v: str) -> str:
        """Validate tenant ID format for security and Kubernetes compatibility.

        Tenant IDs must:
        - Be 1-64 characters long
        - Start and end with alphanumeric characters
        - Contain only alphanumeric characters, hyphens, or underscores
        - Not contain special characters that could cause injection attacks
        """
        if not v:
            raise ValueError("Tenant ID cannot be empty")

        if len(v) > TENANT_ID_MAX_LENGTH:
            raise ValueError(f"Tenant ID exceeds maximum length of {TENANT_ID_MAX_LENGTH}")

        if not TENANT_ID_PATTERN.match(v):
            raise ValueError(
                f"Invalid tenant ID format '{v}'. "
                "Tenant ID must start and end with alphanumeric characters, "
                "and contain only alphanumeric characters, hyphens, or underscores."
            )

        # Additional security check: prevent path traversal attempts
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("Tenant ID contains invalid path characters")

        return v

    @property
    def namespace_name(self) -> str:
        """Generate the Kubernetes namespace name for this tenant."""
        return f"{self.namespace_prefix}{self.tenant_id}"


class TenantQuotaRegistry(BaseSettings):
    """Registry of tenant-specific quota overrides.

    Allows per-tenant quota configuration beyond the default settings.
    Quota overrides are loaded from environment or configuration files.

    Example usage:
        registry = TenantQuotaRegistry()
        tenant_quotas = registry.get_quota_for_tenant('premium-tenant')
    """

    if HAS_PYDANTIC_SETTINGS:
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
            populate_by_name=True,
        )

    # Default quota configuration applied to all tenants
    default_quotas: TenantQuotaConfig = Field(
        default_factory=TenantQuotaConfig,
        description="Default quotas applied to tenants without specific overrides",
    )

    # Tenant-specific quota overrides (loaded from config)
    tenant_overrides: dict[str, TenantQuotaConfig] = Field(
        default_factory=dict,
        description="Per-tenant quota overrides keyed by tenant_id",
    )

    def get_quota_for_tenant(self, tenant_id: str) -> TenantQuotaConfig:
        """Get quota configuration for a specific tenant.

        Returns tenant-specific overrides if configured,
        otherwise returns default quotas.

        Args:
            tenant_id: The tenant identifier to look up

        Returns:
            TenantQuotaConfig for the specified tenant
        """
        return self.tenant_overrides.get(tenant_id, self.default_quotas)

    def register_tenant_quota(self, tenant_id: str, quotas: TenantQuotaConfig) -> None:
        """Register quota overrides for a specific tenant.

        Args:
            tenant_id: The tenant identifier
            quotas: The quota configuration to apply
        """
        # Validate tenant_id format before registering
        TenantConfig.validate_tenant_id(tenant_id)
        self.tenant_overrides[tenant_id] = quotas


# Global instances and factory functions


@lru_cache
def get_default_tenant_quotas() -> TenantQuotaConfig:
    """Get the default tenant quota configuration.

    Uses lru_cache for consistency with FastAPI dependency injection patterns.
    """
    return TenantQuotaConfig()


@lru_cache
def get_tenant_quota_registry() -> TenantQuotaRegistry:
    """Get the global tenant quota registry.

    Uses lru_cache for consistency with FastAPI dependency injection patterns.
    """
    return TenantQuotaRegistry()


def create_tenant_config(
    tenant_id: str,
    cpu: str | None = None,
    memory: str | None = None,
    storage: str | None = None,
    rate_limit_requests: int | None = None,
    rate_limit_window_seconds: int | None = None,
    namespace_prefix: str = "tenant-",
) -> TenantConfig:
    """Factory function to create a TenantConfig with optional overrides.

    Args:
        tenant_id: Unique tenant identifier
        cpu: CPU quota override (default: from TenantQuotaConfig)
        memory: Memory quota override (default: from TenantQuotaConfig)
        storage: Storage quota override (default: from TenantQuotaConfig)
        rate_limit_requests: Rate limit requests override
        rate_limit_window_seconds: Rate limit window override
        namespace_prefix: Kubernetes namespace prefix

    Returns:
        Configured TenantConfig instance
    """
    quota_kwargs = {}
    if cpu is not None:
        quota_kwargs["cpu"] = cpu
    if memory is not None:
        quota_kwargs["memory"] = memory
    if storage is not None:
        quota_kwargs["storage"] = storage
    if rate_limit_requests is not None:
        quota_kwargs["rate_limit_requests"] = rate_limit_requests
    if rate_limit_window_seconds is not None:
        quota_kwargs["rate_limit_window_seconds"] = rate_limit_window_seconds

    quotas = TenantQuotaConfig(**quota_kwargs)

    return TenantConfig(
        tenant_id=tenant_id,
        namespace_prefix=namespace_prefix,
        quotas=quotas,
    )
