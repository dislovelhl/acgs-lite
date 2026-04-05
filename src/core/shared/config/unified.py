"""ACGS-2 Unified Configuration System — backward-compatibility shim.

Constitutional Hash: 608508a9bd224290

This module re-exports all configuration classes from their domain-specific
modules so that existing ``from src.core.shared.config.unified import ...``
statements continue to work without modification.

New code should import directly from the domain modules:
  - infrastructure: RedisSettings, DatabaseSettings, AISettings, BlockchainSettings
  - security: SecuritySettings, OPASettings, AuditSettings, VaultSettings, SSOSettings
  - integrations: ServiceSettings, BundleSettings, OpenCodeSettings, SearchPlatformSettings
  - operations: TelemetrySettings, AWSSettings, QualitySettings
  - governance: MACISettings, VotingSettings, CircuitBreakerSettings
  - communication: SMTPSettings
  - factory: Settings, get_settings, settings
"""

# Infrastructure
# Communication
from src.core.shared.config.communication import SMTPSettings

# Factory — Settings aggregator + singleton
from src.core.shared.config.factory import Settings, get_settings, settings

# Governance
from src.core.shared.config.governance import (
    CircuitBreakerSettings,
    MACISettings,
    VotingSettings,
)

# Re-export HAS_PYDANTIC_SETTINGS for tests that inspect it
from src.core.shared.config.infrastructure import (
    HAS_PYDANTIC_SETTINGS,
    AISettings,
    BlockchainSettings,
    DatabaseSettings,
    RedisSettings,
)

# Integrations
from src.core.shared.config.integrations import (
    BundleSettings,
    OpenCodeSettings,
    SearchPlatformSettings,
    ServiceSettings,
)

# Operations
from src.core.shared.config.operations import (
    AWSSettings,
    QualitySettings,
    TelemetrySettings,
)

# Security
from src.core.shared.config.security import (
    AuditSettings,
    OPASettings,
    SecuritySettings,
    SSOSettings,
    VaultSettings,
)

__all__ = [
    "HAS_PYDANTIC_SETTINGS",
    "AISettings",
    "AWSSettings",
    "AuditSettings",
    "BlockchainSettings",
    "BundleSettings",
    "CircuitBreakerSettings",
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
    "Settings",
    "TelemetrySettings",
    "VaultSettings",
    "VotingSettings",
    "get_settings",
    "settings",
]
