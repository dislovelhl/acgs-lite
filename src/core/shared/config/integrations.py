# mypy: disable-error-code="no-redef"
"""Service integration configuration: Service, Bundle, OpenCode, SearchPlatform.

Constitutional Hash: cdd01ef066bc6cf2
"""

import os
from typing import Final

from pydantic import Field, SecretStr

try:
    from pydantic_settings import BaseSettings

    HAS_PYDANTIC_SETTINGS: Final[bool] = True
except ImportError:
    HAS_PYDANTIC_SETTINGS: Final[bool] = False  # type: ignore[misc]
    from pydantic import BaseModel as BaseSettings  # type: ignore[assignment]


if HAS_PYDANTIC_SETTINGS:

    class ServiceSettings(BaseSettings):
        """Service URL settings for inter-service communication."""

        agent_bus_url: str = Field("http://localhost:8000", validation_alias="AGENT_BUS_URL")
        policy_registry_url: str = Field(
            "http://localhost:8000", validation_alias="POLICY_REGISTRY_URL"
        )
        api_gateway_url: str = Field("http://localhost:8080", validation_alias="API_GATEWAY_URL")
        tenant_management_url: str = Field(
            "http://localhost:8500", validation_alias="TENANT_MANAGEMENT_URL"
        )
        hitl_approvals_url: str = Field(
            "http://localhost:8200", validation_alias="HITL_APPROVALS_URL"
        )
        ml_governance_url: str = Field(
            "http://localhost:8400", validation_alias="ML_GOVERNANCE_URL"
        )
        compliance_docs_url: str = Field(
            "http://localhost:8100", validation_alias="COMPLIANCE_DOCS_URL"
        )
        audit_service_url: str = Field(
            "http://localhost:8300", validation_alias="AUDIT_SERVICE_URL"
        )

    class BundleSettings(BaseSettings):
        """Policy Bundle settings."""

        registry_url: str = Field("http://localhost:5000", validation_alias="BUNDLE_REGISTRY_URL")
        storage_path: str = Field("./storage/bundles", validation_alias="BUNDLE_STORAGE_PATH")
        s3_bucket: str | None = Field(None, validation_alias="BUNDLE_S3_BUCKET")
        policy_public_key: str | None = Field(None, validation_alias="POLICY_PUBLIC_KEY")
        github_webhook_secret: SecretStr | None = Field(
            None, validation_alias="GITHUB_WEBHOOK_SECRET"
        )

    class OpenCodeSettings(BaseSettings):
        """OpenCode Server integration settings."""

        url: str = Field("http://localhost:4096", validation_alias="OPENCODE_URL")
        username: str = Field("opencode", validation_alias="OPENCODE_USERNAME")
        password: SecretStr | None = Field(None, validation_alias="OPENCODE_PASSWORD")
        timeout_seconds: float = Field(30.0, validation_alias="OPENCODE_TIMEOUT")
        max_connections: int = Field(50, validation_alias="OPENCODE_MAX_CONNECTIONS")
        max_retries: int = Field(3, validation_alias="OPENCODE_MAX_RETRIES")
        circuit_breaker_threshold: int = Field(5, validation_alias="OPENCODE_CIRCUIT_THRESHOLD")
        circuit_breaker_timeout: float = Field(60.0, validation_alias="OPENCODE_CIRCUIT_TIMEOUT")

    class SearchPlatformSettings(BaseSettings):
        """Search Platform integration settings."""

        url: str = Field("http://localhost:9080", validation_alias="SEARCH_PLATFORM_URL")
        timeout_seconds: float = Field(30.0, validation_alias="SEARCH_PLATFORM_TIMEOUT")
        max_connections: int = Field(100, validation_alias="SEARCH_PLATFORM_MAX_CONNECTIONS")
        max_retries: int = Field(3, validation_alias="SEARCH_PLATFORM_MAX_RETRIES")
        retry_delay_seconds: float = Field(1.0, validation_alias="SEARCH_PLATFORM_RETRY_DELAY")
        circuit_breaker_threshold: int = Field(
            5, validation_alias="SEARCH_PLATFORM_CIRCUIT_THRESHOLD"
        )
        circuit_breaker_timeout: float = Field(
            30.0, validation_alias="SEARCH_PLATFORM_CIRCUIT_TIMEOUT"
        )
        enable_compliance: bool = Field(True, validation_alias="SEARCH_PLATFORM_ENABLE_COMPLIANCE")

else:
    from dataclasses import dataclass, field

    @dataclass
    class ServiceSettings:  # type: ignore[no-redef]
        """Internal service URL settings for inter-service communication (dataclass fallback)."""

        agent_bus_url: str = field(
            default_factory=lambda: os.getenv("AGENT_BUS_URL", "http://localhost:8000")
        )
        policy_registry_url: str = field(
            default_factory=lambda: os.getenv("POLICY_REGISTRY_URL", "http://localhost:8000")
        )
        api_gateway_url: str = field(
            default_factory=lambda: os.getenv("API_GATEWAY_URL", "http://localhost:8080")
        )
        tenant_management_url: str = field(
            default_factory=lambda: os.getenv("TENANT_MANAGEMENT_URL", "http://localhost:8500")
        )
        hitl_approvals_url: str = field(
            default_factory=lambda: os.getenv("HITL_APPROVALS_URL", "http://localhost:8200")
        )
        ml_governance_url: str = field(
            default_factory=lambda: os.getenv("ML_GOVERNANCE_URL", "http://localhost:8400")
        )
        compliance_docs_url: str = field(
            default_factory=lambda: os.getenv("COMPLIANCE_DOCS_URL", "http://localhost:8100")
        )
        audit_service_url: str = field(
            default_factory=lambda: os.getenv("AUDIT_SERVICE_URL", "http://localhost:8300")
        )

    @dataclass
    class BundleSettings:  # type: ignore[no-redef]
        """Policy bundle registry and storage settings (dataclass fallback)."""

        registry_url: str = field(
            default_factory=lambda: os.getenv("BUNDLE_REGISTRY_URL", "http://localhost:5000")
        )
        storage_path: str = field(
            default_factory=lambda: os.getenv("BUNDLE_STORAGE_PATH", "./storage/bundles")
        )
        s3_bucket: str | None = field(default_factory=lambda: os.getenv("BUNDLE_S3_BUCKET"))
        policy_public_key: str | None = field(
            default_factory=lambda: os.getenv("POLICY_PUBLIC_KEY")
        )
        github_webhook_secret: SecretStr | None = field(
            default_factory=lambda: (
                SecretStr(os.getenv("GITHUB_WEBHOOK_SECRET", ""))
                if os.getenv("GITHUB_WEBHOOK_SECRET")
                else None
            )
        )

    @dataclass
    class OpenCodeSettings:  # type: ignore[no-redef]
        """OpenCode Server integration settings (dataclass fallback)."""

        url: str = field(default_factory=lambda: os.getenv("OPENCODE_URL", "http://localhost:4096"))
        username: str = field(default_factory=lambda: os.getenv("OPENCODE_USERNAME", "opencode"))
        password: SecretStr | None = field(
            default_factory=lambda: (
                SecretStr(os.getenv("OPENCODE_PASSWORD", ""))
                if os.getenv("OPENCODE_PASSWORD")
                else None
            )
        )
        timeout_seconds: float = field(
            default_factory=lambda: float(os.getenv("OPENCODE_TIMEOUT", "30.0"))
        )
        max_connections: int = field(
            default_factory=lambda: int(os.getenv("OPENCODE_MAX_CONNECTIONS", "50"))
        )
        max_retries: int = field(
            default_factory=lambda: int(os.getenv("OPENCODE_MAX_RETRIES", "3"))
        )
        circuit_breaker_threshold: int = field(
            default_factory=lambda: int(os.getenv("OPENCODE_CIRCUIT_THRESHOLD", "5"))
        )
        circuit_breaker_timeout: float = field(
            default_factory=lambda: float(os.getenv("OPENCODE_CIRCUIT_TIMEOUT", "60.0"))
        )

    @dataclass
    class SearchPlatformSettings:  # type: ignore[no-redef]
        """Search platform connection and circuit breaker settings (dataclass fallback)."""

        url: str = field(
            default_factory=lambda: os.getenv("SEARCH_PLATFORM_URL", "http://localhost:9080")
        )
        timeout_seconds: float = field(
            default_factory=lambda: float(os.getenv("SEARCH_PLATFORM_TIMEOUT", "30.0"))
        )
        max_connections: int = field(
            default_factory=lambda: int(os.getenv("SEARCH_PLATFORM_MAX_CONNECTIONS", "100"))
        )
        max_retries: int = field(
            default_factory=lambda: int(os.getenv("SEARCH_PLATFORM_MAX_RETRIES", "3"))
        )
        retry_delay_seconds: float = field(
            default_factory=lambda: float(os.getenv("SEARCH_PLATFORM_RETRY_DELAY", "1.0"))
        )
        circuit_breaker_threshold: int = field(
            default_factory=lambda: int(os.getenv("SEARCH_PLATFORM_CIRCUIT_THRESHOLD", "5"))
        )
        circuit_breaker_timeout: float = field(
            default_factory=lambda: float(os.getenv("SEARCH_PLATFORM_CIRCUIT_TIMEOUT", "30.0"))
        )
        enable_compliance: bool = field(
            default_factory=lambda: (
                os.getenv("SEARCH_PLATFORM_ENABLE_COMPLIANCE", "true").lower() == "true"
            )
        )
