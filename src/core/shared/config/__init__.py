"""
ACGS-2 Configuration Package
Constitutional Hash: 608508a9bd224290

Configuration models and utilities for multi-tenant isolation.
"""

from .communication import SMTPSettings
from .factory import Settings, get_settings, settings
from .governance import CircuitBreakerSettings, MACISettings, VotingSettings
from .infrastructure import AISettings, BlockchainSettings, DatabaseSettings, RedisSettings
from .integrations import BundleSettings, OpenCodeSettings, SearchPlatformSettings, ServiceSettings
from .operations import AWSSettings, QualitySettings, TelemetrySettings
from .overrides import (
    ConfigOverride,
    clear_overrides,
    get_all_overrides,
    get_override,
    override_config,
    set_override,
)
from .security import AuditSettings, OPASettings, SecuritySettings, SSOSettings, VaultSettings
from .tenant_config import (
    TenantConfig,
    TenantQuotaConfig,
    TenantQuotaRegistry,
    create_tenant_config,
    get_default_tenant_quotas,
    get_tenant_quota_registry,
)

__all__ = [
    "AISettings",
    "AWSSettings",
    "AuditSettings",
    "BlockchainSettings",
    "BundleSettings",
    "CircuitBreakerSettings",
    "ConfigOverride",
    "DatabaseSettings",
    "MACISettings",
    "OPASettings",
    "OpenCodeSettings",
    "QualitySettings",
    "RedisSettings",
    "SMTPSettings",
    "SSOSettings",
    "SearchPlatformSettings",
    "SecuritySettings",
    "ServiceSettings",
    # Settings
    "Settings",
    "TelemetrySettings",
    # Tenant config
    "TenantConfig",
    "TenantQuotaConfig",
    "TenantQuotaRegistry",
    "VaultSettings",
    "VotingSettings",
    "clear_overrides",
    "create_tenant_config",
    "get_all_overrides",
    "get_default_tenant_quotas",
    "get_override",
    "get_settings",
    "get_tenant_quota_registry",
    "override_config",
    "set_override",
    "settings",
]
