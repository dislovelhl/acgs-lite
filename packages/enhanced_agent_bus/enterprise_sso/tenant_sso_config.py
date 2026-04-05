"""
Tenant SSO Configuration
Constitutional Hash: 608508a9bd224290

Per-tenant SSO configuration management for multi-tenant enterprise deployments.
Each tenant can configure their own identity providers and role mappings.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from uuid import uuid4

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.errors import (
    ConstitutionalViolationError,
)
from enhanced_agent_bus._compat.errors import (
    ValidationError as ACGSValidationError,
)

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)


class IdPProviderType(str, Enum):
    """Supported Identity Provider types."""

    OKTA = "okta"
    AZURE_AD = "azure_ad"
    GOOGLE_WORKSPACE = "google_workspace"
    AUTH0 = "auth0"
    ONELOGIN = "onelogin"
    PING_IDENTITY = "ping_identity"
    KEYCLOAK = "keycloak"
    CUSTOM_SAML = "custom_saml"
    CUSTOM_OIDC = "custom_oidc"


class SSOProtocolType(str, Enum):
    """SSO protocol types."""

    SAML_2_0 = "saml"
    OIDC = "oidc"


@dataclass
class SAMLConfig:
    """SAML 2.0 specific configuration.

    Constitutional Hash: 608508a9bd224290
    """

    entity_id: str
    sso_url: str
    slo_url: str | None = None
    x509_certificate: str | None = None
    x509_certificate_fingerprint: str | None = None
    name_id_format: str = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
    authn_request_signed: bool = True
    want_assertions_signed: bool = True
    want_response_signed: bool = True
    binding: str = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
    metadata_url: str | None = None

    def to_dict(self) -> JSONDict:
        """Serialize to dictionary."""
        return {
            "entity_id": self.entity_id,
            "sso_url": self.sso_url,
            "slo_url": self.slo_url,
            "x509_certificate": self.x509_certificate,
            "x509_certificate_fingerprint": self.x509_certificate_fingerprint,
            "name_id_format": self.name_id_format,
            "authn_request_signed": self.authn_request_signed,
            "want_assertions_signed": self.want_assertions_signed,
            "want_response_signed": self.want_response_signed,
            "binding": self.binding,
            "metadata_url": self.metadata_url,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "SAMLConfig":
        """Deserialize from dictionary."""
        return cls(
            entity_id=data["entity_id"],
            sso_url=data["sso_url"],
            slo_url=data.get("slo_url"),
            x509_certificate=data.get("x509_certificate"),
            x509_certificate_fingerprint=data.get("x509_certificate_fingerprint"),
            name_id_format=data.get(
                "name_id_format",
                "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
            ),
            authn_request_signed=data.get("authn_request_signed", True),
            want_assertions_signed=data.get("want_assertions_signed", True),
            want_response_signed=data.get("want_response_signed", True),
            binding=data.get(
                "binding",
                "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            ),
            metadata_url=data.get("metadata_url"),
        )


@dataclass
class OIDCConfig:
    """OIDC/OAuth 2.0 specific configuration.

    Constitutional Hash: 608508a9bd224290
    """

    issuer: str
    client_id: str
    client_secret: str | None = None  # None for PKCE flow
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    userinfo_endpoint: str | None = None
    jwks_uri: str | None = None
    end_session_endpoint: str | None = None
    scopes: list[str] = field(default_factory=lambda: ["openid", "profile", "email"])
    response_type: str = "code"
    use_pkce: bool = True
    token_endpoint_auth_method: str = "client_secret_post"

    def to_dict(self) -> JSONDict:
        """Serialize to dictionary (excludes secrets)."""
        return {
            "issuer": self.issuer,
            "client_id": self.client_id,
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": self.token_endpoint,
            "userinfo_endpoint": self.userinfo_endpoint,
            "jwks_uri": self.jwks_uri,
            "end_session_endpoint": self.end_session_endpoint,
            "scopes": self.scopes,
            "response_type": self.response_type,
            "use_pkce": self.use_pkce,
            "token_endpoint_auth_method": self.token_endpoint_auth_method,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "OIDCConfig":
        """Deserialize from dictionary."""
        return cls(
            issuer=data["issuer"],
            client_id=data["client_id"],
            client_secret=data.get("client_secret"),
            authorization_endpoint=data.get("authorization_endpoint"),
            token_endpoint=data.get("token_endpoint"),
            userinfo_endpoint=data.get("userinfo_endpoint"),
            jwks_uri=data.get("jwks_uri"),
            end_session_endpoint=data.get("end_session_endpoint"),
            scopes=data.get("scopes", ["openid", "profile", "email"]),
            response_type=data.get("response_type", "code"),
            use_pkce=data.get("use_pkce", True),
            token_endpoint_auth_method=data.get("token_endpoint_auth_method", "client_secret_post"),
        )


@dataclass
class RoleMappingRule:
    """Rule for mapping IdP group to MACI role.

    Constitutional Hash: 608508a9bd224290
    """

    idp_group: str
    maci_role: str
    priority: int = 0
    conditions: JSONDict = field(default_factory=dict)

    def matches(self, groups: list[str], attributes: dict | None = None) -> bool:
        """Check if this rule matches the provided groups and attributes."""
        if self.idp_group not in groups:
            return False

        # Check additional conditions if specified
        if self.conditions and attributes:
            for key, expected_value in self.conditions.items():
                if attributes.get(key) != expected_value:
                    return False

        return True

    def to_dict(self) -> JSONDict:
        """Serialize to dictionary."""
        return {
            "idp_group": self.idp_group,
            "maci_role": self.maci_role,
            "priority": self.priority,
            "conditions": self.conditions,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "RoleMappingRule":
        """Deserialize from dictionary."""
        return cls(
            idp_group=data["idp_group"],
            maci_role=data["maci_role"],
            priority=data.get("priority", 0),
            conditions=data.get("conditions", {}),
        )


@dataclass
class AttributeMapping:
    """Mapping of IdP attributes to user profile fields.

    Constitutional Hash: 608508a9bd224290
    """

    email: str = "email"
    display_name: str = "name"
    first_name: str = "given_name"
    last_name: str = "family_name"
    groups: str = "groups"
    external_id: str | None = None  # If None, use NameID/sub
    custom_attributes: dict[str, str] = field(default_factory=dict)

    def extract(self, raw_attributes: JSONDict) -> JSONDict:
        """Extract mapped attributes from raw IdP attributes."""

        def get_value(key: str) -> object:
            value = raw_attributes.get(key)
            if isinstance(value, list) and len(value) > 0:
                return value[0]
            return value

        result = {
            "email": get_value(self.email),
            "display_name": get_value(self.display_name),
            "first_name": get_value(self.first_name),
            "last_name": get_value(self.last_name),
            "groups": raw_attributes.get(self.groups, []),
        }

        if self.external_id:
            result["external_id"] = get_value(self.external_id)

        for field_name, attr_name in self.custom_attributes.items():
            result[field_name] = get_value(attr_name)

        return result

    def to_dict(self) -> JSONDict:
        """Serialize to dictionary."""
        return {
            "email": self.email,
            "display_name": self.display_name,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "groups": self.groups,
            "external_id": self.external_id,
            "custom_attributes": self.custom_attributes,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "AttributeMapping":
        """Deserialize from dictionary."""
        return cls(
            email=data.get("email", "email"),
            display_name=data.get("display_name", "name"),
            first_name=data.get("first_name", "given_name"),
            last_name=data.get("last_name", "family_name"),
            groups=data.get("groups", "groups"),
            external_id=data.get("external_id"),
            custom_attributes=data.get("custom_attributes", {}),
        )


@dataclass
class TenantIdPConfig:
    """Identity Provider configuration for a specific tenant.

    Constitutional Hash: 608508a9bd224290
    """

    idp_id: str
    tenant_id: str
    provider_type: IdPProviderType
    protocol: SSOProtocolType
    display_name: str
    enabled: bool = True

    # Protocol-specific config (one of these will be set)
    saml_config: SAMLConfig | None = None
    oidc_config: OIDCConfig | None = None

    # Attribute and role mapping
    attribute_mapping: AttributeMapping = field(default_factory=AttributeMapping)
    role_mappings: list[RoleMappingRule] = field(default_factory=list)
    default_maci_role: str = "MONITOR"

    # JIT provisioning settings
    jit_enabled: bool = True
    jit_update_on_login: bool = True
    jit_deactivate_on_remove: bool = False

    # Security settings
    allowed_domains: list[str] = field(default_factory=list)
    mfa_required: bool = False

    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            raise ConstitutionalViolationError(
                f"Invalid constitutional hash. Expected {CONSTITUTIONAL_HASH}, "
                f"got {self.constitutional_hash}",
                error_code="SSO_IDP_HASH_MISMATCH",
            )

        if self.protocol == SSOProtocolType.SAML_2_0 and not self.saml_config:
            raise ACGSValidationError(
                "SAML configuration required for SAML protocol",
                error_code="SSO_SAML_CONFIG_MISSING",
            )

        if self.protocol == SSOProtocolType.OIDC and not self.oidc_config:
            raise ACGSValidationError(
                "OIDC configuration required for OIDC protocol",
                error_code="SSO_OIDC_CONFIG_MISSING",
            )

    def get_maci_roles(self, groups: list[str], attributes: dict | None = None) -> list[str]:
        """Get MACI roles for the given IdP groups and attributes.

        Args:
            groups: List of IdP groups from the user's assertion/token.
            attributes: Optional additional attributes for conditional matching.

        Returns:
            List of MACI roles (sorted by priority, highest first).
        """
        matching_roles: list[tuple[int, str]] = []

        for rule in self.role_mappings:
            if rule.matches(groups, attributes):
                matching_roles.append((rule.priority, rule.maci_role))

        if not matching_roles:
            return [self.default_maci_role]

        # Sort by priority (descending) and return unique roles
        matching_roles.sort(key=lambda x: x[0], reverse=True)
        seen = set()
        result = []
        for _, role in matching_roles:
            if role not in seen:
                seen.add(role)
                result.append(role)

        return result

    def is_domain_allowed(self, email: str) -> bool:
        """Check if the email domain is allowed.

        Args:
            email: User's email address.

        Returns:
            True if domain is allowed or no domain restrictions.
        """
        if not self.allowed_domains:
            return True

        domain = email.split("@")[-1].lower()
        return domain in [d.lower() for d in self.allowed_domains]

    def to_dict(self) -> JSONDict:
        """Serialize to dictionary."""
        return {
            "idp_id": self.idp_id,
            "tenant_id": self.tenant_id,
            "provider_type": self.provider_type.value,
            "protocol": self.protocol.value,
            "display_name": self.display_name,
            "enabled": self.enabled,
            "saml_config": self.saml_config.to_dict() if self.saml_config else None,
            "oidc_config": self.oidc_config.to_dict() if self.oidc_config else None,
            "attribute_mapping": self.attribute_mapping.to_dict(),
            "role_mappings": [r.to_dict() for r in self.role_mappings],
            "default_maci_role": self.default_maci_role,
            "jit_enabled": self.jit_enabled,
            "jit_update_on_login": self.jit_update_on_login,
            "jit_deactivate_on_remove": self.jit_deactivate_on_remove,
            "allowed_domains": self.allowed_domains,
            "mfa_required": self.mfa_required,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class TenantSSOConfig:
    """SSO configuration for a tenant.

    Constitutional Hash: 608508a9bd224290
    """

    tenant_id: str
    sso_enabled: bool = False
    sso_enforced: bool = False  # If True, local auth is disabled
    identity_providers: list[TenantIdPConfig] = field(default_factory=list)
    default_idp_id: str | None = None
    session_timeout_hours: int = 24
    allow_multiple_sessions: bool = True
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            raise ConstitutionalViolationError(
                f"Invalid constitutional hash. Expected {CONSTITUTIONAL_HASH}, "
                f"got {self.constitutional_hash}",
                error_code="SSO_TENANT_HASH_MISMATCH",
            )

    def get_enabled_idps(self) -> list[TenantIdPConfig]:
        """Get list of enabled identity providers."""
        return [idp for idp in self.identity_providers if idp.enabled]

    def get_idp(self, idp_id: str) -> TenantIdPConfig | None:
        """Get identity provider by ID."""
        for idp in self.identity_providers:
            if idp.idp_id == idp_id:
                return idp
        return None

    def get_default_idp(self) -> TenantIdPConfig | None:
        """Get default identity provider."""
        if self.default_idp_id:
            return self.get_idp(self.default_idp_id)
        enabled = self.get_enabled_idps()
        return enabled[0] if enabled else None

    def to_dict(self) -> JSONDict:
        """Serialize to dictionary."""
        return {
            "tenant_id": self.tenant_id,
            "sso_enabled": self.sso_enabled,
            "sso_enforced": self.sso_enforced,
            "identity_providers": [idp.to_dict() for idp in self.identity_providers],
            "default_idp_id": self.default_idp_id,
            "session_timeout_hours": self.session_timeout_hours,
            "allow_multiple_sessions": self.allow_multiple_sessions,
            "constitutional_hash": self.constitutional_hash,
        }


class TenantSSOConfigManager:
    """Manager for tenant SSO configurations.

    Constitutional Hash: 608508a9bd224290

    Provides CRUD operations for tenant SSO configurations with
    in-memory storage (suitable for extension to database storage).
    """

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH) -> None:
        """Initialize the manager."""
        if constitutional_hash != CONSTITUTIONAL_HASH:
            raise ConstitutionalViolationError(
                f"Invalid constitutional hash. Expected {CONSTITUTIONAL_HASH}, "
                f"got {constitutional_hash}",
                error_code="SSO_MANAGER_HASH_MISMATCH",
            )
        self.constitutional_hash = constitutional_hash
        self._configs: dict[str, TenantSSOConfig] = {}

    def create_config(
        self,
        tenant_id: str,
        sso_enabled: bool = False,
        sso_enforced: bool = False,
    ) -> TenantSSOConfig:
        """Create a new tenant SSO configuration.

        Args:
            tenant_id: Tenant identifier.
            sso_enabled: Whether SSO is enabled.
            sso_enforced: Whether SSO is required (no local auth).

        Returns:
            Created TenantSSOConfig.

        Raises:
            ValueError: If config already exists.
        """
        if tenant_id in self._configs:
            raise ACGSValidationError(
                f"SSO config already exists for tenant: {tenant_id}",
                error_code="SSO_CONFIG_DUPLICATE",
            )

        config = TenantSSOConfig(
            tenant_id=tenant_id,
            sso_enabled=sso_enabled,
            sso_enforced=sso_enforced,
        )

        self._configs[tenant_id] = config
        logger.info(f"[{CONSTITUTIONAL_HASH}] Created SSO config for tenant: {tenant_id}")

        return config

    def get_config(self, tenant_id: str) -> TenantSSOConfig | None:
        """Get tenant SSO configuration.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            TenantSSOConfig if exists, None otherwise.
        """
        return self._configs.get(tenant_id)

    def update_config(
        self,
        tenant_id: str,
        sso_enabled: bool | None = None,
        sso_enforced: bool | None = None,
        session_timeout_hours: int | None = None,
    ) -> TenantSSOConfig | None:
        """Update tenant SSO configuration.

        Args:
            tenant_id: Tenant identifier.
            sso_enabled: New SSO enabled state.
            sso_enforced: New SSO enforced state.
            session_timeout_hours: New session timeout.

        Returns:
            Updated TenantSSOConfig or None if not found.
        """
        config = self._configs.get(tenant_id)
        if not config:
            return None

        if sso_enabled is not None:
            config.sso_enabled = sso_enabled
        if sso_enforced is not None:
            config.sso_enforced = sso_enforced
        if session_timeout_hours is not None:
            config.session_timeout_hours = session_timeout_hours

        logger.info(f"[{CONSTITUTIONAL_HASH}] Updated SSO config for tenant: {tenant_id}")

        return config

    def add_identity_provider(
        self,
        tenant_id: str,
        idp_config: TenantIdPConfig,
        set_as_default: bool = False,
    ) -> TenantSSOConfig | None:
        """Add an identity provider to a tenant.

        Args:
            tenant_id: Tenant identifier.
            idp_config: Identity provider configuration.
            set_as_default: Whether to set as default IdP.

        Returns:
            Updated TenantSSOConfig or None if tenant not found.
        """
        config = self._configs.get(tenant_id)
        if not config:
            return None

        # Ensure idp_id is unique
        existing_ids = {idp.idp_id for idp in config.identity_providers}
        if idp_config.idp_id in existing_ids:
            raise ACGSValidationError(
                f"IdP ID already exists: {idp_config.idp_id}",
                error_code="SSO_IDP_DUPLICATE",
            )

        config.identity_providers.append(idp_config)

        if set_as_default or config.default_idp_id is None:
            config.default_idp_id = idp_config.idp_id

        logger.info(f"[{CONSTITUTIONAL_HASH}] Added IdP {idp_config.idp_id} to tenant: {tenant_id}")

        return config

    def remove_identity_provider(self, tenant_id: str, idp_id: str) -> TenantSSOConfig | None:
        """Remove an identity provider from a tenant.

        Args:
            tenant_id: Tenant identifier.
            idp_id: Identity provider ID to remove.

        Returns:
            Updated TenantSSOConfig or None if tenant not found.
        """
        config = self._configs.get(tenant_id)
        if not config:
            return None

        config.identity_providers = [
            idp for idp in config.identity_providers if idp.idp_id != idp_id
        ]

        # Clear default if removed
        if config.default_idp_id == idp_id:
            enabled = config.get_enabled_idps()
            config.default_idp_id = enabled[0].idp_id if enabled else None

        logger.info(f"[{CONSTITUTIONAL_HASH}] Removed IdP {idp_id} from tenant: {tenant_id}")

        return config

    def delete_config(self, tenant_id: str) -> bool:
        """Delete tenant SSO configuration.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            True if deleted, False if not found.
        """
        if tenant_id not in self._configs:
            return False

        del self._configs[tenant_id]
        logger.warning(f"[{CONSTITUTIONAL_HASH}] Deleted SSO config for tenant: {tenant_id}")

        return True

    def list_configs(self) -> list[TenantSSOConfig]:
        """List all tenant SSO configurations."""
        return list(self._configs.values())

    def get_sso_enabled_tenants(self) -> list[str]:
        """Get list of tenant IDs with SSO enabled."""
        return [config.tenant_id for config in self._configs.values() if config.sso_enabled]


def create_okta_idp_config(
    tenant_id: str,
    okta_domain: str,
    client_id: str,
    client_secret: str | None = None,
    role_mappings: list[RoleMappingRule] | None = None,
) -> TenantIdPConfig:
    """Factory function to create Okta OIDC configuration.

    Args:
        tenant_id: Tenant identifier.
        okta_domain: Okta organization domain (e.g., 'company.okta.com').
        client_id: Okta application client ID.
        client_secret: Okta application client secret (optional for PKCE).
        role_mappings: Optional role mapping rules.

    Returns:
        Configured TenantIdPConfig for Okta.
    """
    return TenantIdPConfig(
        idp_id=f"okta-{tenant_id}-{str(uuid4())[:8]}",
        tenant_id=tenant_id,
        provider_type=IdPProviderType.OKTA,
        protocol=SSOProtocolType.OIDC,
        display_name="Okta",
        oidc_config=OIDCConfig(
            issuer=f"https://{okta_domain}",
            client_id=client_id,
            client_secret=client_secret,
            authorization_endpoint=f"https://{okta_domain}/oauth2/v1/authorize",
            token_endpoint=f"https://{okta_domain}/oauth2/v1/token",
            userinfo_endpoint=f"https://{okta_domain}/oauth2/v1/userinfo",
            jwks_uri=f"https://{okta_domain}/oauth2/v1/keys",
            end_session_endpoint=f"https://{okta_domain}/oauth2/v1/logout",
            scopes=["openid", "profile", "email", "groups"],
        ),
        attribute_mapping=AttributeMapping(
            email="email",
            display_name="name",
            first_name="given_name",
            last_name="family_name",
            groups="groups",
        ),
        role_mappings=role_mappings or [],
    )


def create_azure_ad_idp_config(
    tenant_id: str,
    azure_tenant_id: str,
    client_id: str,
    client_secret: str | None = None,
    role_mappings: list[RoleMappingRule] | None = None,
) -> TenantIdPConfig:
    """Factory function to create Azure AD OIDC configuration.

    Args:
        tenant_id: ACGS-2 tenant identifier.
        azure_tenant_id: Azure AD tenant ID.
        client_id: Azure AD application client ID.
        client_secret: Azure AD application client secret.
        role_mappings: Optional role mapping rules.

    Returns:
        Configured TenantIdPConfig for Azure AD.
    """
    base_url = f"https://login.microsoftonline.com/{azure_tenant_id}"

    return TenantIdPConfig(
        idp_id=f"azure-ad-{tenant_id}-{str(uuid4())[:8]}",
        tenant_id=tenant_id,
        provider_type=IdPProviderType.AZURE_AD,
        protocol=SSOProtocolType.OIDC,
        display_name="Microsoft Azure AD",
        oidc_config=OIDCConfig(
            issuer=f"{base_url}/v2.0",
            client_id=client_id,
            client_secret=client_secret,
            authorization_endpoint=f"{base_url}/oauth2/v2.0/authorize",
            token_endpoint=f"{base_url}/oauth2/v2.0/token",
            jwks_uri=f"{base_url}/discovery/v2.0/keys",
            end_session_endpoint=f"{base_url}/oauth2/v2.0/logout",
            scopes=["openid", "profile", "email"],
        ),
        attribute_mapping=AttributeMapping(
            email="email",
            display_name="name",
            first_name="given_name",
            last_name="family_name",
            groups="groups",
        ),
        role_mappings=role_mappings or [],
    )


def create_google_workspace_idp_config(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    hosted_domain: str | None = None,
    role_mappings: list[RoleMappingRule] | None = None,
) -> TenantIdPConfig:
    """Factory function to create Google Workspace OIDC configuration.

    Args:
        tenant_id: ACGS-2 tenant identifier.
        client_id: Google OAuth client ID.
        client_secret: Google OAuth client secret.
        hosted_domain: Optional G Suite domain restriction.
        role_mappings: Optional role mapping rules.

    Returns:
        Configured TenantIdPConfig for Google Workspace.
    """
    config = TenantIdPConfig(
        idp_id=f"google-{tenant_id}-{str(uuid4())[:8]}",
        tenant_id=tenant_id,
        provider_type=IdPProviderType.GOOGLE_WORKSPACE,
        protocol=SSOProtocolType.OIDC,
        display_name="Google Workspace",
        oidc_config=OIDCConfig(
            issuer="https://accounts.google.com",
            client_id=client_id,
            client_secret=client_secret,
            authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
            token_endpoint="https://oauth2.googleapis.com/token",
            userinfo_endpoint="https://openidconnect.googleapis.com/v1/userinfo",
            jwks_uri="https://www.googleapis.com/oauth2/v3/certs",
            scopes=["openid", "profile", "email"],
        ),
        attribute_mapping=AttributeMapping(
            email="email",
            display_name="name",
            first_name="given_name",
            last_name="family_name",
            external_id="sub",
        ),
        role_mappings=role_mappings or [],
    )

    if hosted_domain:
        config.allowed_domains = [hosted_domain]

    return config
