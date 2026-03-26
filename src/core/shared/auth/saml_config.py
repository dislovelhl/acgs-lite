"""
ACGS-2 SAML 2.0 Configuration Module
Constitutional Hash: 608508a9bd224290

Provides configuration dataclasses for SAML 2.0 Service Provider (SP) setup
with PySAML2. Supports multiple Identity Providers (IdPs) including Okta,
Azure AD, and custom SAML IdPs.

Features:
    - SP configuration with entity ID and endpoints
    - IdP metadata handling (URL or inline XML)
    - Certificate and key management
    - Signature and encryption settings
    - Clock skew tolerance configuration

Usage:
    from src.core.shared.auth.saml_config import SAMLSPConfig, SAMLIdPConfig

    # Create SP configuration
    sp_config = SAMLSPConfig(
        entity_id="https://acgs2.example.com/saml/metadata",
        acs_url="https://acgs2.example.com/saml/acs",
        sls_url="https://acgs2.example.com/saml/sls",
        cert_file="/path/to/sp.crt",
        key_file="/path/to/sp.key",
    )

    # Create IdP configuration
    idp_config = SAMLIdPConfig(
        name="okta",
        entity_id="http://www.okta.com/exk123",
        metadata_url="https://dev-123.okta.com/app/exk123/sso/saml/metadata",
    )
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.errors.exceptions import ACGSBaseError
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONValue

logger = get_logger(__name__)

# Default paths relative to this module
DEFAULT_CERT_DIR = Path(__file__).parent / "certs"
DEFAULT_SP_CERT = DEFAULT_CERT_DIR / "sp.crt"
DEFAULT_SP_KEY = DEFAULT_CERT_DIR / "sp.key"

# Default clock skew tolerance (in seconds)
DEFAULT_CLOCK_SKEW_TOLERANCE = 120


class SAMLConfigurationError(ACGSBaseError):
    """Configuration error for SAML provider (Q-H4 migration)."""

    http_status_code = 400
    error_code = "SAML_CONFIGURATION_ERROR"


@dataclass
class SAMLSPConfig:
    """Service Provider (SP) configuration for SAML 2.0.

    Configures the SAML 2.0 Service Provider endpoints and security settings.
    The SP is the relying party that receives SAML assertions from IdPs.

    Attributes:
        entity_id: Unique identifier for this SP (typically the metadata URL)
        acs_url: Assertion Consumer Service URL for POST binding
        sls_url: Single Logout Service URL for redirect binding
        metadata_url: URL where SP metadata is served
        cert_file: Path to SP certificate file (PEM format)
        key_file: Path to SP private key file (PEM format)
        cert_content: SP certificate content (alternative to file)
        key_content: SP private key content (alternative to file)
        sign_authn_requests: Whether to sign AuthnRequests
        want_assertions_signed: Whether to require signed assertions
        want_assertions_encrypted: Whether to require encrypted assertions
        allow_unsolicited: Whether to accept IdP-initiated SSO
        clock_skew_tolerance: Allowed clock skew in seconds
        name: Human-readable name for this SP
        description: Description of this SP
        org_name: Organization name
        org_display_name: Organization display name
        org_url: Organization URL
        contact_name: Technical contact name
        contact_email: Technical contact email
        xmlsec_binary: Path to xmlsec1 binary (auto-detected if not set)
    """

    # Required fields
    entity_id: str
    acs_url: str

    # Optional endpoint URLs
    sls_url: str | None = None
    metadata_url: str | None = None

    # Certificate configuration (file paths or content)
    cert_file: str | None = None
    key_file: str | None = None
    cert_content: str | None = None
    key_content: str | None = None

    # Security settings
    sign_authn_requests: bool = True
    want_assertions_signed: bool = True
    want_assertions_encrypted: bool = False
    allow_unsolicited: bool = True

    # Timing settings
    clock_skew_tolerance: int = DEFAULT_CLOCK_SKEW_TOLERANCE

    # SP identity
    name: str = "ACGS-2 SAML SP"
    description: str = "ACGS-2 Constitutional AI Governance System"
    org_name: str = "ACGS-2"
    org_display_name: str = "ACGS-2 Platform"
    org_url: str = "https://acgs2.example.com"

    # Contact information
    contact_name: str = "ACGS-2 Admin"
    contact_email: str = "admin@example.com"

    # xmlsec1 binary path (auto-detected if None)
    xmlsec_binary: str | None = None

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if not self.entity_id:
            raise SAMLConfigurationError("SP entity ID is required")
        if not self.acs_url:
            raise SAMLConfigurationError("ACS URL is required")

        # Auto-detect xmlsec1 if not specified
        if not self.xmlsec_binary:
            self.xmlsec_binary = self._find_xmlsec_binary()

        # Use default certificate paths if not specified and no content provided
        if not self.cert_file and not self.cert_content and DEFAULT_SP_CERT.exists():
            self.cert_file = str(DEFAULT_SP_CERT)
        if not self.key_file and not self.key_content and DEFAULT_SP_KEY.exists():
            self.key_file = str(DEFAULT_SP_KEY)

    def _find_xmlsec_binary(self) -> str | None:
        """Find xmlsec1 binary in common locations.

        Returns:
            Path to xmlsec1 binary.

        Raises:
            SAMLConfigurationError: If xmlsec1 is not found.
        """
        # Check environment variable first
        env_path = os.environ.get("SAML_XMLSEC_BINARY")
        if env_path and os.path.isfile(env_path):
            return env_path

        # Common locations
        common_paths = [
            "/usr/bin/xmlsec1",
            "/usr/local/bin/xmlsec1",
            "/opt/homebrew/bin/xmlsec1",  # macOS Homebrew ARM
            "/opt/local/bin/xmlsec1",  # macOS MacPorts
        ]

        for path in common_paths:
            if os.path.isfile(path):
                return path

        # Check PATH
        import shutil

        path = shutil.which("xmlsec1")
        if path:
            return path

        logger.warning(
            "xmlsec1 binary not found. SAML signature validation will fail closed. "
            "Install with: apt-get install xmlsec1 (Debian/Ubuntu) or "
            "brew install libxmlsec1 (macOS)"
        )
        return None

    def get_cert_content(self) -> str | None:
        """Get SP certificate content.

        Returns:
            Certificate content string, or None if not configured.
        """
        if self.cert_content:
            return self.cert_content
        if self.cert_file and os.path.isfile(self.cert_file):
            with open(self.cert_file) as f:
                return f.read()
        return None

    def get_key_content(self) -> str | None:
        """Get SP private key content.

        Returns:
            Private key content string, or None if not configured.
        """
        if self.key_content:
            return self.key_content
        if self.key_file and os.path.isfile(self.key_file):
            with open(self.key_file) as f:
                return f.read()
        return None

    def has_signing_credentials(self) -> bool:
        """Check if signing credentials are available.

        Returns:
            True if both certificate and key are available.
        """
        cert = self.get_cert_content()
        key = self.get_key_content()
        return bool(cert and key)

    def validate(self) -> list[str]:
        """Validate SP configuration.

        Returns:
            List of validation errors, empty if valid.
        """
        errors = []

        if not self.entity_id:
            errors.append("SP entity ID is required")
        if not self.acs_url:
            errors.append("ACS URL is required")

        if self.sign_authn_requests and not self.has_signing_credentials():
            errors.append("SP certificate and key are required when sign_authn_requests is enabled")

        if self.sign_authn_requests:
            if not self.xmlsec_binary:
                errors.append("xmlsec1 binary is required when sign_authn_requests is enabled")
            elif not os.path.isfile(self.xmlsec_binary):
                errors.append(f"xmlsec1 binary not found at {self.xmlsec_binary}")

        return errors


@dataclass
class SAMLIdPConfig:
    """Identity Provider (IdP) configuration for SAML 2.0.

    Configures a SAML 2.0 Identity Provider for SSO authentication.
    Supports metadata URL, inline XML, or manual endpoint configuration.

    Attributes:
        name: Unique name for this IdP (e.g., 'okta', 'azure')
        entity_id: IdP entity ID (from metadata or manually configured)
        metadata_url: URL to fetch IdP metadata XML
        metadata_xml: Inline IdP metadata XML content
        sso_url: IdP SSO endpoint URL (if not using metadata)
        sso_binding: SSO binding type (redirect or post)
        slo_url: IdP SLO endpoint URL
        slo_binding: SLO binding type (redirect or post)
        certificate: IdP signing certificate (PEM format)
        want_response_signed: Whether to require signed SAML responses
        want_assertions_signed: Whether to require signed assertions
        enabled: Whether this IdP is enabled
    """

    # Required fields
    name: str

    # IdP identity (one of entity_id or metadata_url/xml required)
    entity_id: str | None = None
    metadata_url: str | None = None
    metadata_xml: str | None = None

    # Manual endpoint configuration (used if no metadata)
    sso_url: str | None = None
    sso_binding: str = "redirect"  # redirect or post
    slo_url: str | None = None
    slo_binding: str = "redirect"  # redirect or post

    # IdP certificate for signature validation
    certificate: str | None = None

    # Security requirements
    want_response_signed: bool = True
    want_assertions_signed: bool = True

    # Status
    enabled: bool = True

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if not self.name:
            raise SAMLConfigurationError("IdP name is required")

        # Normalize binding types
        self.sso_binding = self.sso_binding.lower()
        self.slo_binding = self.slo_binding.lower()

        if self.sso_binding not in ("redirect", "post"):
            raise SAMLConfigurationError(
                f"Invalid SSO binding '{self.sso_binding}'. Must be 'redirect' or 'post'"
            )
        if self.slo_binding not in ("redirect", "post"):
            raise SAMLConfigurationError(
                f"Invalid SLO binding '{self.slo_binding}'. Must be 'redirect' or 'post'"
            )

    def has_metadata(self) -> bool:
        """Check if IdP metadata is available.

        Returns:
            True if metadata URL or XML is configured.
        """
        return bool(self.metadata_url or self.metadata_xml)

    def has_manual_config(self) -> bool:
        """Check if manual endpoint configuration is available.

        Returns:
            True if SSO URL and certificate are configured.
        """
        return bool(self.sso_url and self.certificate)

    def is_configured(self) -> bool:
        """Check if IdP is properly configured.

        Returns:
            True if IdP can be used for authentication.
        """
        return self.has_metadata() or self.has_manual_config()

    def validate(self) -> list[str]:
        """Validate IdP configuration.

        Returns:
            List of validation errors, empty if valid.
        """
        errors = []

        if not self.name:
            errors.append("IdP name is required")

        if not self.has_metadata() and not self.has_manual_config():
            errors.append(
                "Either metadata (URL or XML) or manual configuration "
                "(SSO URL + certificate) is required"
            )

        if not self.has_metadata() and self.has_manual_config() and not self.entity_id:
            errors.append("IdP entity ID is required when using manual configuration")

        return errors


@dataclass
class SAMLConfig:
    """Complete SAML configuration combining SP and IdP settings.

    Provides a unified configuration object for the SAML handler,
    combining SP settings with multiple IdP configurations.

    Attributes:
        sp: Service Provider configuration
        idps: Dictionary of IdP configurations keyed by name
        debug: Enable debug logging
        strict: Enable strict mode (reject invalid responses)
        metadata_cache_duration: How long to cache IdP metadata (seconds)
    """

    sp: SAMLSPConfig
    idps: dict[str, SAMLIdPConfig] = field(default_factory=dict)
    debug: bool = False
    strict: bool = True
    metadata_cache_duration: int = 86400  # 24 hours

    def add_idp(self, idp: SAMLIdPConfig) -> None:
        """Add an IdP configuration.

        Args:
            idp: IdP configuration to add.
        """
        self.idps[idp.name] = idp
        logger.info(
            "SAML IdP added",
            extra={
                "idp_name": idp.name,
                "has_metadata": idp.has_metadata(),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

    def get_idp(self, name: str) -> SAMLIdPConfig | None:
        """Get an IdP configuration by name.

        Args:
            name: IdP name.

        Returns:
            IdP configuration or None if not found.
        """
        return self.idps.get(name)

    def list_enabled_idps(self) -> list[str]:
        """List names of all enabled IdPs.

        Returns:
            List of enabled IdP names.
        """
        return [name for name, idp in self.idps.items() if idp.enabled]

    def validate(self) -> list[str]:
        """Validate complete SAML configuration.

        Returns:
            List of validation errors, empty if valid.
        """
        errors = self.sp.validate()

        for name, idp in self.idps.items():
            idp_errors = idp.validate()
            for error in idp_errors:
                errors.append(f"IdP '{name}': {error}")

        return errors

    @classmethod
    def from_settings(cls, settings: JSONValue) -> "SAMLConfig":
        """Create SAMLConfig from application settings.

        Args:
            settings: Application settings object with sso attribute.

        Returns:
            SAMLConfig instance.
        """
        sso = getattr(settings, "sso", None)
        if not sso:
            raise SAMLConfigurationError("SSO settings not found")

        sp_config = SAMLSPConfig(
            entity_id=getattr(sso, "saml_entity_id", "urn:acgs2:sp"),
            acs_url="/sso/saml/acs",  # Default relative URL
            sls_url="/sso/saml/sls",
            metadata_url="/sso/saml/metadata",
            sign_authn_requests=getattr(sso, "saml_sign_requests", True),
            want_assertions_signed=getattr(sso, "saml_want_assertions_signed", True),
            want_assertions_encrypted=getattr(sso, "saml_want_assertions_encrypted", False),
        )

        # Handle SP certificate
        sp_cert = getattr(sso, "saml_sp_certificate", None)
        if sp_cert:
            sp_config.cert_content = sp_cert

        sp_key = getattr(sso, "saml_sp_private_key", None)
        if sp_key:
            if hasattr(sp_key, "get_secret_value"):
                sp_config.key_content = sp_key.get_secret_value()
            else:
                sp_config.key_content = str(sp_key)

        config = cls(sp=sp_config)

        # Add IdP from settings if configured
        idp_metadata_url = getattr(sso, "saml_idp_metadata_url", None)
        if idp_metadata_url:
            idp_config = SAMLIdPConfig(
                name="default",
                metadata_url=idp_metadata_url,
                entity_id=getattr(sso, "saml_entity_id", None),
                sso_url=getattr(sso, "saml_idp_sso_url", None),
                slo_url=getattr(sso, "saml_idp_slo_url", None),
                certificate=getattr(sso, "saml_idp_certificate", None),
            )
            config.add_idp(idp_config)

        return config
