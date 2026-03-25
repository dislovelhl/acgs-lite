# mypy: disable-error-code="no-redef"
"""Global settings aggregation and factory.

Constitutional Hash: 608508a9bd224290
"""

import os
from functools import lru_cache
from typing import Final

from pydantic import Field, model_validator

from src.core.shared.types import JSONDict

from .communication import SMTPSettings
from .governance import CircuitBreakerSettings, MACISettings, VotingSettings
from .infrastructure import AISettings, BlockchainSettings, DatabaseSettings, RedisSettings
from .integrations import BundleSettings, OpenCodeSettings, SearchPlatformSettings, ServiceSettings
from .operations import AWSSettings, QualitySettings, TelemetrySettings
from .security import AuditSettings, OPASettings, SecuritySettings, SSOSettings, VaultSettings

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    HAS_PYDANTIC_SETTINGS: Final[bool] = True
except ImportError:
    HAS_PYDANTIC_SETTINGS: Final[bool] = False  # type: ignore[misc]
    from pydantic import BaseModel as BaseSettings  # type: ignore[assignment]

    class SettingsConfigDict(dict):  # type: ignore[no-redef]
        """Fallback stub for pydantic_settings.SettingsConfigDict when pydantic-settings is unavailable."""


if HAS_PYDANTIC_SETTINGS:

    class Settings(BaseSettings):
        """Global Application Settings."""

        model_config = SettingsConfigDict(
            env_file=".env", env_file_encoding="utf-8", extra="ignore"
        )

        env: str = Field("development", validation_alias="APP_ENV")
        debug: bool = Field(False, validation_alias="APP_DEBUG")

        redis: RedisSettings = RedisSettings()
        database: DatabaseSettings = DatabaseSettings()
        ai: AISettings = AISettings()
        blockchain: BlockchainSettings = BlockchainSettings()
        security: SecuritySettings = SecuritySettings()
        sso: SSOSettings = SSOSettings()
        smtp: SMTPSettings = SMTPSettings()
        opa: OPASettings = OPASettings()
        audit: AuditSettings = AuditSettings()
        bundle: BundleSettings = BundleSettings()
        services: ServiceSettings = ServiceSettings()
        telemetry: TelemetrySettings = TelemetrySettings()
        aws: AWSSettings = AWSSettings()
        search_platform: SearchPlatformSettings = SearchPlatformSettings()
        opencode: OpenCodeSettings = OpenCodeSettings()
        quality: QualitySettings = QualitySettings()
        maci: MACISettings = MACISettings()
        vault: VaultSettings = VaultSettings()
        voting: VotingSettings = VotingSettings()
        circuit_breaker: CircuitBreakerSettings = CircuitBreakerSettings()
        kafka: JSONDict = Field(
            default_factory=lambda: {
                "bootstrap_servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
                "security_protocol": os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"),
                "ssl_ca_location": os.getenv("KAFKA_SSL_CA_LOCATION"),
                "ssl_certificate_location": os.getenv("KAFKA_SSL_CERTIFICATE_LOCATION"),
                "ssl_key_location": os.getenv("KAFKA_SSL_KEY_LOCATION"),
                "ssl_password": os.getenv("KAFKA_SSL_PASSWORD"),
            },
            validation_alias="KAFKA_CONFIG",
        )

        @model_validator(mode="before")
        @classmethod
        def _coerce_opencode_env(cls, data: dict) -> dict:
            """Handle OPENCODE env var collision with OpenCodeSettings field.

            The OpenCode CLI sets OPENCODE=1 as a flag. Pydantic auto-maps
            field names to env vars, causing a type mismatch. When the value
            is not a dict, replace with empty dict to use defaults.
            """
            if isinstance(data, dict):
                val = data.get("opencode")
                if val is not None and not isinstance(val, dict):
                    data["opencode"] = {}
            return data

        @model_validator(mode="after")
        def validate_production_security(self) -> "Settings":
            """Ensure strict security when running in production."""
            if self.env == "production":
                if not self.security.jwt_secret:
                    raise ValueError("JWT_SECRET is mandatory in production environment")

                jwt_val = self.security.jwt_secret.get_secret_value()
                if jwt_val == "dev-secret":
                    raise ValueError("Insecure JWT_SECRET 'dev-secret' is forbidden in production")
                if len(jwt_val) < 32:
                    raise ValueError("JWT_SECRET must be at least 32 characters in production")

                if not self.security.api_key_internal:
                    raise ValueError("API_KEY_INTERNAL is mandatory in production environment")
                if self.security.jwt_public_key == "SYSTEM_PUBLIC_KEY_PLACEHOLDER":
                    raise ValueError("JWT_PUBLIC_KEY must be configured in production environment")

                # NOTE: Redis TLS enforcement — warns in production, does not block.
                # Upgrade to hard-fail once all Redis deployments support TLS.
                if not self.redis.ssl and not self.redis.url.startswith("rediss://"):
                    import warnings

                    warnings.warn(
                        "Redis connection does not use TLS in production environment. "
                        "Consider setting REDIS_SSL=true or using rediss:// URL for secure "
                        "communication.",
                        UserWarning,
                        stacklevel=2,
                    )
            return self

else:
    from dataclasses import dataclass, field

    @dataclass
    class Settings:  # type: ignore[no-redef]
        """Root application settings aggregating all subsystem configurations (dataclass fallback)."""

        env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
        debug: bool = field(
            default_factory=lambda: os.getenv("APP_DEBUG", "false").lower() == "true"
        )

        redis: RedisSettings = field(default_factory=RedisSettings)
        database: DatabaseSettings = field(default_factory=DatabaseSettings)
        ai: AISettings = field(default_factory=AISettings)
        blockchain: BlockchainSettings = field(default_factory=BlockchainSettings)
        security: SecuritySettings = field(default_factory=SecuritySettings)
        sso: SSOSettings = field(default_factory=SSOSettings)
        smtp: SMTPSettings = field(default_factory=SMTPSettings)
        opa: OPASettings = field(default_factory=OPASettings)
        audit: AuditSettings = field(default_factory=AuditSettings)
        bundle: BundleSettings = field(default_factory=BundleSettings)
        services: ServiceSettings = field(default_factory=ServiceSettings)
        telemetry: TelemetrySettings = field(default_factory=TelemetrySettings)
        aws: AWSSettings = field(default_factory=AWSSettings)
        search_platform: SearchPlatformSettings = field(default_factory=SearchPlatformSettings)
        opencode: OpenCodeSettings = field(default_factory=OpenCodeSettings)
        quality: QualitySettings = field(default_factory=QualitySettings)
        maci: MACISettings = field(default_factory=MACISettings)
        vault: VaultSettings = field(default_factory=VaultSettings)
        voting: VotingSettings = field(default_factory=VotingSettings)
        circuit_breaker: CircuitBreakerSettings = field(default_factory=CircuitBreakerSettings)
        kafka: JSONDict = field(
            default_factory=lambda: {
                "bootstrap_servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
                "security_protocol": os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"),
                "ssl_ca_location": os.getenv("KAFKA_SSL_CA_LOCATION"),
                "ssl_certificate_location": os.getenv("KAFKA_SSL_CERTIFICATE_LOCATION"),
                "ssl_key_location": os.getenv("KAFKA_SSL_KEY_LOCATION"),
                "ssl_password": os.getenv("KAFKA_SSL_PASSWORD"),
            }
        )

        def __post_init__(self):
            """Validate production security requirements."""
            if self.env in {"production", "prod", "staging"}:
                # NOTE: Redis TLS enforcement — warns in production, does not block.
                if not self.redis.ssl and not self.redis.url.startswith("rediss://"):
                    import warnings

                    warnings.warn(
                        "Redis connection does not use TLS in production environment. "
                        "Consider setting REDIS_SSL=true or using rediss:// URL for secure "
                        "communication.",
                        UserWarning,
                        stacklevel=2,
                    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached application settings singleton."""
    return Settings()


# Singleton instance for backwards compatibility
# Use get_settings() for dependency injection patterns
settings = get_settings()
