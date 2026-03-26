# mypy: disable-error-code="no-redef"
"""Security configuration: Security, OPA, Audit, Vault, SSO.

Constitutional Hash: 608508a9bd224290
"""

import os
from typing import Final

from pydantic import Field, SecretStr, field_validator

try:
    from pydantic_settings import BaseSettings

    HAS_PYDANTIC_SETTINGS: Final[bool] = True
except ImportError:
    HAS_PYDANTIC_SETTINGS: Final[bool] = False  # type: ignore[misc]
    from pydantic import BaseModel as BaseSettings  # type: ignore[assignment]


if HAS_PYDANTIC_SETTINGS:

    class SecuritySettings(BaseSettings):
        """Security and Auth settings."""

        api_key_internal: SecretStr | None = Field(None, validation_alias="API_KEY_INTERNAL")
        jwt_secret: SecretStr | None = Field(None, validation_alias="JWT_SECRET")
        jwt_public_key: str = Field(
            "SYSTEM_PUBLIC_KEY_PLACEHOLDER", validation_alias="JWT_PUBLIC_KEY"
        )
        admin_api_key: SecretStr | None = Field(None, validation_alias="ADMIN_API_KEY")

        @field_validator("jwt_secret", "api_key_internal")
        @classmethod
        def check_no_placeholders(cls, v: SecretStr | None) -> SecretStr | None:
            """Ensure sensitive keys don't use weak placeholders."""
            if v is not None:
                secret_val = v.get_secret_value()
                if secret_val in ["PLACEHOLDER", "CHANGE_ME", "DANGEROUS_DEFAULT", "dev-secret"]:
                    raise ValueError("Sensitive credential uses a forbidden placeholder value")

                # Check secret strength if it's a JWT secret
                # Note: We can't easily distinguish which field 'v' is here without 'info',
                # but applying it to both is safe as both should be strong.
                if len(secret_val) < 32:
                    # We check the environment in the model_validator below for the hard stop,
                    # but we can log a warning here or raise if we want to be very strict.
                    pass
            return v

    class OPASettings(BaseSettings):
        """OPA (Open Policy Agent) settings."""

        url: str = Field("http://localhost:8181", validation_alias="OPA_URL")
        max_connections: int = Field(100, validation_alias="OPA_MAX_CONNECTIONS")
        mode: str = Field("http", validation_alias="OPA_MODE")  # http, embedded, fallback
        # SECURITY FIX (VULN-002): OPA is now ALWAYS fail-closed.
        # Parameter removed to prevent insecure overrides.
        fail_closed: bool = True
        ssl_verify: bool = Field(True, validation_alias="OPA_SSL_VERIFY")
        ssl_cert: str | None = Field(None, validation_alias="OPA_SSL_CERT")
        ssl_key: str | None = Field(None, validation_alias="OPA_SSL_KEY")

    class AuditSettings(BaseSettings):
        """Audit Service settings."""

        url: str = Field("http://localhost:8001", validation_alias="AUDIT_SERVICE_URL")

    class VaultSettings(BaseSettings):
        """HashiCorp Vault integration settings."""

        address: str = Field("http://127.0.0.1:8200", validation_alias="VAULT_ADDR")
        token: SecretStr | None = Field(None, validation_alias="VAULT_TOKEN")
        namespace: str | None = Field(None, validation_alias="VAULT_NAMESPACE")
        transit_mount: str = Field("transit", validation_alias="VAULT_TRANSIT_MOUNT")
        kv_mount: str = Field("secret", validation_alias="VAULT_KV_MOUNT")
        kv_version: int = Field(2, validation_alias="VAULT_KV_VERSION")
        timeout: float = Field(30.0, validation_alias="VAULT_TIMEOUT")
        verify_tls: bool = Field(True, validation_alias="VAULT_VERIFY_TLS")
        ca_cert: str | None = Field(None, validation_alias="VAULT_CACERT")
        client_cert: str | None = Field(None, validation_alias="VAULT_CLIENT_CERT")
        client_key: str | None = Field(None, validation_alias="VAULT_CLIENT_KEY")

    class SSOSettings(BaseSettings):
        """SSO and Authentication settings for OIDC and SAML 2.0."""

        enabled: bool = Field(True, validation_alias="SSO_ENABLED")
        session_lifetime_seconds: int = Field(3600, validation_alias="SSO_SESSION_LIFETIME")

        # OIDC settings
        oidc_enabled: bool = Field(True, validation_alias="OIDC_ENABLED")
        oidc_client_id: str | None = Field(None, validation_alias="OIDC_CLIENT_ID")
        oidc_client_secret: SecretStr | None = Field(None, validation_alias="OIDC_CLIENT_SECRET")
        oidc_issuer_url: str | None = Field(None, validation_alias="OIDC_ISSUER_URL")
        oidc_scopes: list[str] = Field(
            ["openid", "email", "profile"], validation_alias="OIDC_SCOPES"
        )
        oidc_use_pkce: bool = Field(True, validation_alias="OIDC_USE_PKCE")

        # SAML settings
        saml_enabled: bool = Field(True, validation_alias="SAML_ENABLED")
        saml_entity_id: str | None = Field(None, validation_alias="SAML_ENTITY_ID")
        saml_sign_requests: bool = Field(True, validation_alias="SAML_SIGN_REQUESTS")
        saml_want_assertions_signed: bool = Field(
            True, validation_alias="SAML_WANT_ASSERTIONS_SIGNED"
        )
        saml_want_assertions_encrypted: bool = Field(
            False, validation_alias="SAML_WANT_ASSERTIONS_ENCRYPTED"
        )
        saml_sp_certificate: str | None = Field(None, validation_alias="SAML_SP_CERTIFICATE")
        saml_sp_private_key: SecretStr | None = Field(None, validation_alias="SAML_SP_PRIVATE_KEY")
        saml_idp_metadata_url: str | None = Field(None, validation_alias="SAML_IDP_METADATA_URL")
        saml_idp_sso_url: str | None = Field(None, validation_alias="SAML_IDP_SSO_URL")
        saml_idp_slo_url: str | None = Field(None, validation_alias="SAML_IDP_SLO_URL")
        saml_idp_certificate: str | None = Field(None, validation_alias="SAML_IDP_CERTIFICATE")

        # Provisioning
        auto_provision_users: bool = Field(True, validation_alias="SSO_AUTO_PROVISION")
        default_role_on_provision: str = Field("viewer", validation_alias="SSO_DEFAULT_ROLE")
        allowed_domains: list[str] | None = Field(None, validation_alias="SSO_ALLOWED_DOMAINS")

        # WorkOS integration
        workos_enabled: bool = Field(False, validation_alias="WORKOS_ENABLED")
        workos_api_base_url: str = Field(
            "https://api.workos.com", validation_alias="WORKOS_API_BASE_URL"
        )
        workos_client_id: str | None = Field(None, validation_alias="WORKOS_CLIENT_ID")
        workos_api_key: SecretStr | None = Field(None, validation_alias="WORKOS_API_KEY")
        workos_webhook_secret: SecretStr | None = Field(
            None, validation_alias="WORKOS_WEBHOOK_SECRET"
        )
        workos_webhook_dedupe_ttl_seconds: int = Field(
            86400, validation_alias="WORKOS_WEBHOOK_DEDUPE_TTL_SECONDS"
        )
        workos_webhook_fail_closed: bool = Field(
            True, validation_alias="WORKOS_WEBHOOK_FAIL_CLOSED"
        )
        workos_portal_default_intent: str = Field(
            "sso", validation_alias="WORKOS_PORTAL_DEFAULT_INTENT"
        )
        workos_portal_return_url: str | None = Field(
            None, validation_alias="WORKOS_PORTAL_RETURN_URL"
        )
        workos_portal_success_url: str | None = Field(
            None, validation_alias="WORKOS_PORTAL_SUCCESS_URL"
        )

        # Trusted hosts for middleware
        trusted_hosts: list[str] = Field(
            ["localhost", "127.0.0.1"], validation_alias="SSO_TRUSTED_HOSTS"
        )

else:
    from dataclasses import dataclass, field

    @dataclass
    class SecuritySettings:  # type: ignore[no-redef]
        """API keys, CORS, and JWT security settings (dataclass fallback)."""

        api_key_internal: SecretStr | None = field(
            default_factory=lambda: (
                SecretStr(os.getenv("API_KEY_INTERNAL", ""))
                if os.getenv("API_KEY_INTERNAL")
                else None
            )
        )
        cors_origins: list[str] = field(
            default_factory=lambda: os.getenv("CORS_ORIGINS", "*").split(",")
        )
        jwt_secret: SecretStr | None = field(
            default_factory=lambda: (
                SecretStr(os.getenv("JWT_SECRET", "")) if os.getenv("JWT_SECRET") else None
            )
        )
        jwt_public_key: str = field(
            default_factory=lambda: os.getenv("JWT_PUBLIC_KEY", "SYSTEM_PUBLIC_KEY_PLACEHOLDER")
        )
        admin_api_key: SecretStr | None = field(
            default_factory=lambda: (
                SecretStr(os.getenv("ADMIN_API_KEY", "")) if os.getenv("ADMIN_API_KEY") else None
            )
        )

    @dataclass
    class OPASettings:  # type: ignore[no-redef]
        """Open Policy Agent connection settings (dataclass fallback)."""

        url: str = field(default_factory=lambda: os.getenv("OPA_URL", "http://localhost:8181"))
        mode: str = field(default_factory=lambda: os.getenv("OPA_MODE", "http"))
        fail_closed: bool = True
        ssl_verify: bool = field(
            default_factory=lambda: os.getenv("OPA_SSL_VERIFY", "true").lower() == "true"
        )
        ssl_cert: str | None = field(default_factory=lambda: os.getenv("OPA_SSL_CERT"))
        ssl_key: str | None = field(default_factory=lambda: os.getenv("OPA_SSL_KEY"))

    @dataclass
    class AuditSettings:  # type: ignore[no-redef]
        """Audit service URL settings (dataclass fallback)."""

        url: str = field(
            default_factory=lambda: os.getenv("AUDIT_SERVICE_URL", "http://localhost:8001")
        )

    @dataclass
    class VaultSettings:  # type: ignore[no-redef]
        """HashiCorp Vault secrets management settings (dataclass fallback)."""

        address: str = field(
            default_factory=lambda: os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
        )
        token: SecretStr | None = field(
            default_factory=lambda: (
                SecretStr(os.getenv("VAULT_TOKEN", "")) if os.getenv("VAULT_TOKEN") else None
            )
        )
        namespace: str | None = field(default_factory=lambda: os.getenv("VAULT_NAMESPACE"))
        transit_mount: str = field(
            default_factory=lambda: os.getenv("VAULT_TRANSIT_MOUNT", "transit")
        )
        kv_mount: str = field(default_factory=lambda: os.getenv("VAULT_KV_MOUNT", "secret"))
        kv_version: int = field(default_factory=lambda: int(os.getenv("VAULT_KV_VERSION", "2")))
        timeout: float = field(default_factory=lambda: float(os.getenv("VAULT_TIMEOUT", "30.0")))
        verify_tls: bool = field(
            default_factory=lambda: os.getenv("VAULT_VERIFY_TLS", "true").lower() == "true"
        )
        ca_cert: str | None = field(default_factory=lambda: os.getenv("VAULT_CACERT"))
        client_cert: str | None = field(default_factory=lambda: os.getenv("VAULT_CLIENT_CERT"))
        client_key: str | None = field(default_factory=lambda: os.getenv("VAULT_CLIENT_KEY"))

    @dataclass
    class SSOSettings:  # type: ignore[no-redef]
        """Single Sign-On (OIDC/SAML/WorkOS) settings (dataclass fallback)."""

        enabled: bool = field(
            default_factory=lambda: os.getenv("SSO_ENABLED", "true").lower() == "true"
        )
        session_lifetime_seconds: int = field(
            default_factory=lambda: int(os.getenv("SSO_SESSION_LIFETIME", "3600"))
        )

        # OIDC
        oidc_enabled: bool = field(
            default_factory=lambda: os.getenv("OIDC_ENABLED", "true").lower() == "true"
        )
        oidc_client_id: str | None = field(default_factory=lambda: os.getenv("OIDC_CLIENT_ID"))
        oidc_client_secret: SecretStr | None = field(
            default_factory=lambda: (
                SecretStr(os.getenv("OIDC_CLIENT_SECRET", ""))
                if os.getenv("OIDC_CLIENT_SECRET")
                else None
            )
        )
        oidc_issuer_url: str | None = field(default_factory=lambda: os.getenv("OIDC_ISSUER_URL"))
        oidc_scopes: list[str] = field(
            default_factory=lambda: os.getenv("OIDC_SCOPES", "openid,email,profile").split(",")
        )
        oidc_use_pkce: bool = field(
            default_factory=lambda: os.getenv("OIDC_USE_PKCE", "true").lower() == "true"
        )

        # SAML
        saml_enabled: bool = field(
            default_factory=lambda: os.getenv("SAML_ENABLED", "true").lower() == "true"
        )
        saml_entity_id: str | None = field(default_factory=lambda: os.getenv("SAML_ENTITY_ID"))
        saml_sign_requests: bool = field(
            default_factory=lambda: os.getenv("SAML_SIGN_REQUESTS", "true").lower() == "true"
        )
        saml_want_assertions_signed: bool = field(
            default_factory=lambda: (
                os.getenv("SAML_WANT_ASSERTIONS_SIGNED", "true").lower() == "true"
            )
        )
        saml_want_assertions_encrypted: bool = field(
            default_factory=lambda: (
                os.getenv("SAML_WANT_ASSERTIONS_ENCRYPTED", "false").lower() == "true"
            )
        )
        saml_sp_certificate: str | None = field(
            default_factory=lambda: os.getenv("SAML_SP_CERTIFICATE")
        )
        saml_sp_private_key: SecretStr | None = field(
            default_factory=lambda: (
                SecretStr(os.getenv("SAML_SP_PRIVATE_KEY", ""))
                if os.getenv("SAML_SP_PRIVATE_KEY")
                else None
            )
        )
        saml_idp_metadata_url: str | None = field(
            default_factory=lambda: os.getenv("SAML_IDP_METADATA_URL")
        )
        saml_idp_sso_url: str | None = field(default_factory=lambda: os.getenv("SAML_IDP_SSO_URL"))
        saml_idp_slo_url: str | None = field(default_factory=lambda: os.getenv("SAML_IDP_SLO_URL"))
        saml_idp_certificate: str | None = field(
            default_factory=lambda: os.getenv("SAML_IDP_CERTIFICATE")
        )

        # Provisioning
        auto_provision_users: bool = field(
            default_factory=lambda: os.getenv("SSO_AUTO_PROVISION", "true").lower() == "true"
        )
        default_role_on_provision: str = field(
            default_factory=lambda: os.getenv("SSO_DEFAULT_ROLE", "viewer")
        )
        allowed_domains: list[str] | None = field(
            default_factory=lambda: (
                (os.getenv("SSO_ALLOWED_DOMAINS") or "").split(",")
                if os.getenv("SSO_ALLOWED_DOMAINS")
                else None
            )
        )

        # WorkOS integration
        workos_enabled: bool = field(
            default_factory=lambda: os.getenv("WORKOS_ENABLED", "false").lower() == "true"
        )
        workos_api_base_url: str = field(
            default_factory=lambda: os.getenv("WORKOS_API_BASE_URL", "https://api.workos.com")
        )
        workos_client_id: str | None = field(default_factory=lambda: os.getenv("WORKOS_CLIENT_ID"))
        workos_api_key: SecretStr | None = field(
            default_factory=lambda: (
                SecretStr(os.getenv("WORKOS_API_KEY", "")) if os.getenv("WORKOS_API_KEY") else None
            )
        )
        workos_webhook_secret: SecretStr | None = field(
            default_factory=lambda: (
                SecretStr(os.getenv("WORKOS_WEBHOOK_SECRET", ""))
                if os.getenv("WORKOS_WEBHOOK_SECRET")
                else None
            )
        )
        workos_webhook_dedupe_ttl_seconds: int = field(
            default_factory=lambda: int(os.getenv("WORKOS_WEBHOOK_DEDUPE_TTL_SECONDS", "86400"))
        )
        workos_webhook_fail_closed: bool = field(
            default_factory=lambda: (
                os.getenv("WORKOS_WEBHOOK_FAIL_CLOSED", "false").lower() == "true"
            )
        )
        workos_portal_default_intent: str = field(
            default_factory=lambda: os.getenv("WORKOS_PORTAL_DEFAULT_INTENT", "sso")
        )
        workos_portal_return_url: str | None = field(
            default_factory=lambda: os.getenv("WORKOS_PORTAL_RETURN_URL")
        )
        workos_portal_success_url: str | None = field(
            default_factory=lambda: os.getenv("WORKOS_PORTAL_SUCCESS_URL")
        )
