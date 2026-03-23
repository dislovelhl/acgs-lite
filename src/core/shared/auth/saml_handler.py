"""
ACGS-2 SAML 2.0 Handler Service
Constitutional Hash: cdd01ef066bc6cf2

Provides enterprise-grade SAML 2.0 Service Provider (SP) implementation using
PySAML2. Supports multiple Identity Providers including Okta, Azure AD, and
custom SAML IdPs.

Features:
    - SP-initiated and IdP-initiated SSO flows
    - Assertion Consumer Service (ACS) with signature validation
    - Single Logout Service (SLS) support
    - SP metadata generation
    - Outstanding request tracking for replay attack prevention
    - Clock skew tolerance handling
    - Multiple IdP configuration

Usage:
    from src.core.shared.auth.saml_handler import SAMLHandler
    from src.core.shared.auth.saml_config import SAMLSPConfig, SAMLIdPConfig

    # Create handler with default configuration
    handler = SAMLHandler()

    # Or with custom configuration
    sp_config = SAMLSPConfig(
        entity_id="https://acgs2.example.com/saml/metadata",
        acs_url="https://acgs2.example.com/saml/acs",
    )
    handler = SAMLHandler(sp_config=sp_config)

    # Register an IdP
    handler.register_idp(
        name="okta",
        metadata_url="https://dev-123.okta.com/app/exk123/sso/saml/metadata",
    )

    # Initiate login
    redirect_url, request_id = await handler.initiate_login("okta")

    # Handle ACS callback
    user_info = await handler.process_acs_response(saml_response, request_id)
"""

# Standard library
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.parse import urlencode

from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

# Third-party
try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False
    httpx = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from src.core.shared.models.sso_provider import SSOProvider

# Local package imports
import contextlib

from .saml_config import (
    CONSTITUTIONAL_HASH,
    SAMLConfig,
    SAMLConfigurationError,
    SAMLIdPConfig,
    SAMLSPConfig,
)
from .saml_request_tracker import SAMLRequestTracker
from .saml_types import (
    NAMEID_FORMAT_EMAILADDRESS,
    SAMLError,
    SAMLAuthenticationError,
    SAMLProviderError,
    SAMLReplayError,
    SAMLUserInfo,
    SAMLValidationError,
)

# Optional PySAML2 imports (wrap in try/except)
try:
    from saml2 import BINDING_HTTP_POST, BINDING_HTTP_REDIRECT
    from saml2.client import Saml2Client
    from saml2.config import Config as Saml2Config
    from saml2.metadata import create_metadata_string
    from saml2.s_utils import UnknownPrincipal, UnsupportedBinding

    HAS_PYSAML2 = True
except ImportError:
    HAS_PYSAML2 = False
    BINDING_HTTP_POST = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
    BINDING_HTTP_REDIRECT = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
    Saml2Client = None  # type: ignore[misc, assignment]
    Saml2Config = None  # type: ignore[misc, assignment]
    UnknownPrincipal = Exception  # type: ignore[misc, assignment]
    UnsupportedBinding = Exception  # type: ignore[misc, assignment]

# Production-ready timeouts
DEFAULT_TIMEOUT = 10.0
METADATA_FETCH_TIMEOUT = 30.0

# Enterprise-grade User-Agent
HTTP_USER_AGENT = "ACGS-2-SAML-Handler/1.0 (Enterprise SSO Service)"

logger = get_logger(__name__)
_HTTPX_SAML_ERRORS = (httpx.HTTPError,) if HAS_HTTPX else (RuntimeError,)
_SAML_HANDLER_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    PermissionError,
    TimeoutError,
    ConnectionError,
    *_HTTPX_SAML_ERRORS,
)

# Exceptions and SAMLUserInfo moved to saml_types.py


class SAMLHandler:
    """SAML 2.0 Service Provider handler for enterprise SSO authentication.

    This handler manages SAML authentication flows for multiple identity
    providers. It supports:
    - SP-initiated SSO (redirect to IdP)
    - IdP-initiated SSO (unsolicited responses)
    - Single Logout (SLO)
    - SP metadata generation
    - Outstanding request tracking for replay prevention

    Example:
        handler = SAMLHandler()

        # Register an IdP
        handler.register_idp(
            name="okta",
            metadata_url="https://dev-123.okta.com/app/exk123/sso/saml/metadata"
        )

        # Start login
        redirect_url, request_id = await handler.initiate_login("okta")

        # Store request_id in session for replay prevention

        # After IdP redirects back with SAML response:
        user_info = await handler.process_acs_response(saml_response, request_id)
    """

    def __init__(
        self,
        sp_config: SAMLSPConfig | None = None,
        config: SAMLConfig | None = None,
    ) -> None:
        """Initialize SAML handler.

        Args:
            sp_config: Service Provider configuration (creates default if not provided)
            config: Full SAML configuration (overrides sp_config if provided)
        """
        if config:
            self._config = config
        elif sp_config:
            self._config = SAMLConfig(sp=sp_config)
        else:
            # Create minimal default configuration for testing
            self._config = SAMLConfig(
                sp=SAMLSPConfig(
                    entity_id="urn:acgs2:saml:sp",
                    acs_url="/sso/saml/acs",
                )
            )

        self._idp_configs: dict[str, SAMLIdPConfig] = {}
        self._saml_clients: dict[str, Saml2Client] = {}  # Cached Saml2Client per IdP
        self._metadata_cache: dict[str, tuple[str, datetime]] = {}
        self._tracker = SAMLRequestTracker()
        self._http_client: httpx.AsyncClient | None = None

        logger.info(
            "SAML handler initialized",
            extra={
                "entity_id": self._config.sp.entity_id,
                "has_signing_creds": self._config.sp.has_signing_credentials(),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

    @property
    def sp_config(self) -> SAMLSPConfig:
        """Get SP configuration."""
        return self._config.sp

    def register_idp(
        self,
        name: str,
        metadata_url: str | None = None,
        metadata_xml: str | None = None,
        entity_id: str | None = None,
        sso_url: str | None = None,
        slo_url: str | None = None,
        certificate: str | None = None,
        want_assertions_signed: bool = True,
    ) -> None:
        """Register an Identity Provider.

        Args:
            name: Unique IdP name
            metadata_url: URL to fetch IdP metadata
            metadata_xml: Inline IdP metadata XML
            entity_id: IdP entity ID (required if not using metadata)
            sso_url: IdP SSO endpoint URL
            slo_url: IdP SLO endpoint URL
            certificate: IdP signing certificate (PEM format)
            want_assertions_signed: Require signed assertions

        Raises:
            SAMLConfigurationError: If configuration is invalid
        """
        idp = SAMLIdPConfig(
            name=name,
            metadata_url=metadata_url,
            metadata_xml=metadata_xml,
            entity_id=entity_id,
            sso_url=sso_url,
            slo_url=slo_url,
            certificate=certificate,
            want_assertions_signed=want_assertions_signed,
        )

        errors = idp.validate()
        if errors:
            raise SAMLConfigurationError(f"Invalid IdP configuration: {'; '.join(errors)}")

        self._idp_configs[name] = idp
        self._config.add_idp(idp)

        # Clear cached client to force rebuild
        if name in self._saml_clients:
            del self._saml_clients[name]

        logger.info(
            "SAML IdP registered",
            extra={
                "idp_name": name,
                "has_metadata_url": bool(metadata_url),
                "has_metadata_xml": bool(metadata_xml),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

    def register_idp_from_model(self, provider: "SSOProvider") -> None:
        """Register an IdP from database model.

        Args:
            provider: SSOProvider model instance

        Raises:
            SAMLConfigurationError: If provider is not SAML or config invalid
        """
        if not provider.is_saml:
            raise SAMLConfigurationError(f"Provider '{provider.name}' is not a SAML provider")

        errors = provider.validate_saml_config()
        if errors:
            raise SAMLConfigurationError(
                f"Invalid SAML configuration for '{provider.name}': {'; '.join(errors)}"
            )

        self.register_idp(
            name=provider.name,
            metadata_url=provider.saml_metadata_url,
            metadata_xml=provider.saml_metadata_xml,
            entity_id=provider.saml_entity_id,
            certificate=provider.saml_sp_cert,  # IdP cert for validation
            want_assertions_signed=provider.saml_sign_assertions,
        )

    def get_idp(self, name: str) -> SAMLIdPConfig:
        """Get registered IdP configuration.

        Args:
            name: IdP name

        Returns:
            IdP configuration

        Raises:
            SAMLConfigurationError: If IdP not found
        """
        if name not in self._idp_configs:
            raise SAMLConfigurationError(f"SAML IdP '{name}' not registered")
        return self._idp_configs[name]

    def list_idps(self) -> list[str]:
        """List all registered IdP names.

        Returns:
            List of IdP names
        """
        return list(self._idp_configs.keys())

    async def _get_http_client(self) -> "httpx.AsyncClient":
        """Get or create HTTP client with production settings.

        Returns:
            httpx AsyncClient instance
        """
        if self._http_client is None:
            if not HAS_HTTPX:
                raise SAMLError("httpx library is required for SAML metadata fetching")

            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(DEFAULT_TIMEOUT, connect=5.0, read=METADATA_FETCH_TIMEOUT),
                headers={"User-Agent": HTTP_USER_AGENT},
                follow_redirects=True,
            )
        return self._http_client

    async def _fetch_metadata(self, idp: SAMLIdPConfig, force_refresh: bool = False) -> str | None:
        """Fetch IdP metadata from URL.

        Args:
            idp: IdP configuration
            force_refresh: Force metadata refresh even if cached

        Returns:
            Metadata XML string or None
        """
        if not idp.metadata_url:
            return idp.metadata_xml

        cache_key = idp.name
        if not force_refresh and cache_key in self._metadata_cache:
            xml, cached_at = self._metadata_cache[cache_key]
            age = datetime.now(UTC) - cached_at
            if age.total_seconds() < self._config.metadata_cache_duration:
                return xml

        try:
            client = await self._get_http_client()
            response = await client.get(idp.metadata_url)
            response.raise_for_status()
            xml = response.text

            self._metadata_cache[cache_key] = (xml, datetime.now(UTC))

            logger.info(
                "SAML IdP metadata fetched",
                extra={
                    "idp_name": idp.name,
                    "metadata_url": idp.metadata_url,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

            return xml

        except _SAML_HANDLER_OPERATION_ERRORS as e:
            # Try to use cached metadata on error
            if cache_key in self._metadata_cache:
                logger.warning(
                    "Failed to refresh SAML metadata, using cached version",
                    extra={
                        "idp_name": idp.name,
                        "error": str(e),
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                    },
                )
                return self._metadata_cache[cache_key][0]

            raise SAMLProviderError(f"Failed to fetch metadata for IdP '{idp.name}': {e}") from e

    def _build_pysaml2_config(self, idp: SAMLIdPConfig, metadata_xml: str | None) -> dict:
        """Build PySAML2 configuration dictionary.

        Args:
            idp: IdP configuration
            metadata_xml: IdP metadata XML content

        Returns:
            PySAML2 configuration dictionary
        """
        sp = self._config.sp

        config: JSONDict = {
            "entityid": sp.entity_id,
            "xmlsec_binary": sp.xmlsec_binary,
            "allow_unsolicited": sp.allow_unsolicited,
            "accepted_time_diff": sp.clock_skew_tolerance,
            "service": {
                "sp": {
                    "name": sp.name,
                    "description": sp.description,
                    "endpoints": {
                        "assertion_consumer_service": [
                            (sp.acs_url, BINDING_HTTP_POST),
                        ],
                    },
                    "want_assertions_signed": sp.want_assertions_signed,
                    "want_response_signed": idp.want_response_signed,
                    "authn_requests_signed": sp.sign_authn_requests,
                },
            },
            "debug": self._config.debug,
        }

        # Add SLS endpoint if configured
        if sp.sls_url:
            config["service"]["sp"]["endpoints"]["single_logout_service"] = [
                (sp.sls_url, BINDING_HTTP_REDIRECT),
                (sp.sls_url, BINDING_HTTP_POST),
            ]

        # Add SP certificate and key
        cert_content = sp.get_cert_content()
        key_content = sp.get_key_content()

        if cert_content and key_content:
            # Clean up old temp files if they exist
            for attr in ["_temp_cert_file", "_temp_key_file"]:
                if hasattr(self, attr):
                    old_file = getattr(self, attr)
                    if old_file:
                        with contextlib.suppress(OSError, PermissionError, RuntimeError):
                            Path(old_file.name).unlink(missing_ok=True)

            # Write to temporary files for PySAML2
            self._temp_cert_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".crt", delete=False
            )
            self._temp_cert_file.write(cert_content)
            self._temp_cert_file.flush()

            self._temp_key_file = tempfile.NamedTemporaryFile(mode="w", suffix=".key", delete=False)
            self._temp_key_file.write(key_content)
            self._temp_key_file.flush()

            config["cert_file"] = self._temp_cert_file.name
            config["key_file"] = self._temp_key_file.name

        # Add IdP metadata
        if metadata_xml:
            # Clean up old metadata file
            if hasattr(self, "_temp_metadata_file"):
                old_file = self._temp_metadata_file
                if old_file:
                    with contextlib.suppress(OSError, PermissionError, RuntimeError):
                        Path(old_file.name).unlink(missing_ok=True)

            # Write metadata to temp file
            self._temp_metadata_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".xml", delete=False
            )
            self._temp_metadata_file.write(metadata_xml)
            self._temp_metadata_file.flush()

            config["metadata"] = {
                "local": [self._temp_metadata_file.name],
            }
        elif idp.entity_id and idp.sso_url:
            # Manual IdP configuration
            config["metadata"] = {
                "inline": [
                    {
                        "entity_id": idp.entity_id,
                        "sso_url": idp.sso_url,
                        "slo_url": idp.slo_url,
                        "cert": idp.certificate,
                    }
                ]
            }

        return config

    async def _get_saml_client(self, idp_name: str) -> "Saml2Client":
        """Get or create SAML client for an IdP.

        Args:
            idp_name: IdP name

        Returns:
            PySAML2 Saml2Client instance

        Raises:
            SAMLError: If PySAML2 is not available
            SAMLConfigurationError: If IdP not found
        """
        if not HAS_PYSAML2:
            raise SAMLError(
                "PySAML2 is required for SAML operations. Install with: pip install pysaml2"
            )

        idp = self.get_idp(idp_name)

        # Return cached client if available
        if idp_name in self._saml_clients:
            return self._saml_clients[idp_name]

        # Fetch metadata
        metadata_xml = await self._fetch_metadata(idp)

        # Build configuration
        config_dict = self._build_pysaml2_config(idp, metadata_xml)

        # Create PySAML2 config
        saml_config = Saml2Config()
        saml_config.load(config_dict)

        # Create client
        client = Saml2Client(config=saml_config)

        self._saml_clients[idp_name] = client
        return client

    def _generate_request_id(self) -> str:
        """Generate a unique SAML request ID."""
        return self._tracker._generate_request_id()

    def store_outstanding_request(
        self,
        request_id: str | None = None,
        idp_name: str | None = None,
        relay_state: str | None = None,
        expiry_minutes: int = 5,
    ) -> str:
        """Store an outstanding SAML request for replay prevention."""
        return self._tracker.store_request(
            request_id=request_id,
            idp_name=idp_name,
            relay_state=relay_state,
            expiry_minutes=expiry_minutes,
        )

    def verify_and_remove_request(self, request_id: str) -> bool:
        """Verify an outstanding request exists and remove it."""
        return self._tracker.verify_and_remove(request_id)

    def get_outstanding_requests(self) -> dict[str, str]:
        """Get all outstanding requests in PySAML2 format."""
        return self._tracker.get_requests_as_dict()

    def clear_expired_requests(self) -> int:
        """Clear expired outstanding requests."""
        return self._tracker.clear_expired()

    async def initiate_login(
        self,
        idp_name: str,
        relay_state: str | None = None,
        force_authn: bool = False,
    ) -> tuple[str, str]:
        """Initiate SP-initiated SAML login.

        Args:
            idp_name: Name of the IdP to use
            relay_state: URL to redirect to after authentication
            force_authn: Force re-authentication even if user has session

        Returns:
            Tuple of (redirect_url, request_id)

        Raises:
            SAMLError: If PySAML2 is not available
            SAMLConfigurationError: If IdP not found
        """
        client = await self._get_saml_client(idp_name)
        idp = self.get_idp(idp_name)

        # Get IdP entity ID from metadata
        idp_entity_id = idp.entity_id
        if not idp_entity_id:
            # Try to get from client metadata
            try:
                idps = client.metadata.identity_providers()
                if idps:
                    idp_entity_id = idps[0]
            except (OSError, PermissionError, RuntimeError):
                pass

        if not idp_entity_id:
            raise SAMLConfigurationError(f"Cannot determine entity ID for IdP '{idp_name}'")

        try:
            # Prepare authentication request
            req_id, info = client.prepare_for_authenticate(
                entityid=idp_entity_id,
                relay_state=relay_state or "",
                force_authn=force_authn,
            )

            # Store outstanding request
            self.store_outstanding_request(
                request_id=req_id,
                idp_name=idp_name,
                relay_state=relay_state,
            )

            # Extract redirect URL from headers
            headers_dict = dict(info["headers"])
            redirect_url = headers_dict.get("Location", "")

            if not redirect_url:
                raise SAMLError("Failed to get redirect URL from SAML request")

            logger.info(
                "SAML login initiated",
                extra={
                    "idp_name": idp_name,
                    "request_id": req_id[:16] + "...",
                    "force_authn": force_authn,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

            return redirect_url, req_id

        except (UnknownPrincipal, UnsupportedBinding) as e:
            raise SAMLConfigurationError(
                f"SAML configuration error for IdP '{idp_name}': {e}"
            ) from e
        except _SAML_HANDLER_OPERATION_ERRORS as e:
            raise SAMLError(f"Failed to initiate SAML login: {e}") from e

    async def process_acs_response(
        self,
        saml_response: str,
        request_id: str | None = None,
        idp_name: str | None = None,
    ) -> SAMLUserInfo:
        """Process SAML response at Assertion Consumer Service."""
        if not HAS_PYSAML2:
            raise SAMLError("PySAML2 is required for SAML operations")

        # Determine which IdP to use
        if not idp_name:
            idp_name = self._detect_idp_name(request_id)

        client = await self._get_saml_client(idp_name)

        try:
            # Parse and validate response
            outstanding = self.get_outstanding_requests()
            response = client.parse_authn_request_response(
                saml_response,
                BINDING_HTTP_POST,
                outstanding=outstanding if outstanding else None,
            )

            if response is None:
                raise SAMLValidationError("Failed to parse SAML response")

            # Replay prevention
            self._handle_replay_prevention(request_id)

            # Extract user information
            user_info = SAMLUserInfo.from_response(response, HAS_PYSAML2)

            logger.info(
                "SAML authentication successful",
                extra={
                    "idp_name": idp_name,
                    "name_id": user_info.name_id[:16] + "..." if user_info.name_id else "N/A",
                    "email": user_info.email,
                    "groups_count": len(user_info.groups),
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

            return user_info

        except (SAMLReplayError, SAMLValidationError):
            raise
        except _SAML_HANDLER_OPERATION_ERRORS as e:
            logger.error(
                "SAML validation failed",
                extra={
                    "error": str(e),
                    "idp_name": idp_name,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )
            raise SAMLValidationError(f"SAML response validation failed: {e}") from e

    def _detect_idp_name(self, request_id: str | None) -> str:
        """Detect IdP name from request ID or configuration."""
        if request_id:
            req_info = self._tracker.get_request(request_id)
            if req_info and req_info.get("idp_name"):
                return cast(str, req_info["idp_name"])

        idp_list = self.list_idps()
        if not idp_list:
            raise SAMLConfigurationError("No IdPs registered")
        return idp_list[0]

    def _handle_replay_prevention(self, request_id: str | None) -> None:
        """Handle replay prevention for a request ID."""
        if request_id and not self.verify_and_remove_request(request_id):
            logger.warning(
                "SAML replay attack detected or request expired",
                extra={
                    "request_id": request_id[:16] + "...",
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )
            raise SAMLReplayError("SAML response replay detected or request expired")

    async def initiate_logout(
        self,
        idp_name: str,
        name_id: str,
        session_index: str | None = None,
        relay_state: str | None = None,
    ) -> str | None:
        """Initiate SAML Single Logout (SLO).

        Args:
            idp_name: IdP name
            name_id: User's SAML NameID
            session_index: Session index from login
            relay_state: URL to redirect after logout

        Returns:
            Logout redirect URL, or None if IdP doesn't support SLO
        """
        if not HAS_PYSAML2:
            return None

        idp = self.get_idp(idp_name)
        if not idp.slo_url:
            logger.info(
                "IdP does not support SLO",
                extra={
                    "idp_name": idp_name,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )
            return None

        try:
            client = await self._get_saml_client(idp_name)

            # Get IdP entity ID
            idp_entity_id = idp.entity_id
            if not idp_entity_id:
                idps = client.metadata.identity_providers()
                if idps:
                    idp_entity_id = idps[0]

            if not idp_entity_id:
                return None

            # Create logout request
            _req_id, info = client.do_logout(
                name_id,
                entity_ids=[idp_entity_id],
                session_indexes=[session_index] if session_index else None,
                sign=self._config.sp.sign_authn_requests,
            )

            headers_dict = dict(info.get("headers", []))
            logout_url = headers_dict.get("Location")

            if logout_url and relay_state:
                # Add relay state to logout URL
                separator = "&" if "?" in logout_url else "?"
                logout_url = f"{logout_url}{separator}{urlencode({'RelayState': relay_state})}"

            logger.info(
                "SAML logout initiated",
                extra={
                    "idp_name": idp_name,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

            return logout_url

        except _SAML_HANDLER_OPERATION_ERRORS as e:
            logger.warning(
                "Failed to initiate SAML logout",
                extra={
                    "idp_name": idp_name,
                    "error": str(e),
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )
            return None

    async def process_sls_response(
        self,
        saml_response: str,
        idp_name: str,
    ) -> bool:
        """Process SAML logout response.

        Args:
            saml_response: Base64-encoded SAML logout response
            idp_name: IdP name

        Returns:
            True if logout was successful
        """
        if not HAS_PYSAML2:
            return True

        try:
            client = await self._get_saml_client(idp_name)

            # Parse logout response
            response = client.parse_logout_request_response(
                saml_response,
                BINDING_HTTP_REDIRECT,
            )

            success = response.status_ok()

            logger.info(
                "SAML logout response processed",
                extra={
                    "idp_name": idp_name,
                    "success": success,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

            return success

        except _SAML_HANDLER_OPERATION_ERRORS as e:
            logger.warning(
                "Failed to process SAML logout response",
                extra={
                    "idp_name": idp_name,
                    "error": str(e),
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )
            return False

    async def generate_metadata(self) -> str:
        """Generate SP metadata XML.

        Returns:
            SP metadata XML string

        Raises:
            SAMLError: If metadata generation fails
        """
        if not HAS_PYSAML2:
            # Return minimal metadata without PySAML2
            sp = self._config.sp
            cert_content = sp.get_cert_content() or ""

            # Strip PEM headers for metadata
            cert_for_xml = (
                cert_content.replace("-----BEGIN CERTIFICATE-----", "")
                .replace("-----END CERTIFICATE-----", "")
                .replace("\n", "")
                .strip()
            )

            return f"""<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
                     entityID="{sp.entity_id}">
  <md:SPSSODescriptor
      AuthnRequestsSigned="{str(sp.sign_authn_requests).lower()}"
      WantAssertionsSigned="{str(sp.want_assertions_signed).lower()}"
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing">
      <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
        <ds:X509Data>
          <ds:X509Certificate>{cert_for_xml}</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>
    <md:NameIDFormat>{NAMEID_FORMAT_EMAILADDRESS}</md:NameIDFormat>
    <md:AssertionConsumerService
        Binding="{BINDING_HTTP_POST}"
        Location="{sp.acs_url}"
        index="0"
        isDefault="true"/>
  </md:SPSSODescriptor>
  <md:Organization>
    <md:OrganizationName xml:lang="en">{sp.org_name}</md:OrganizationName>
    <md:OrganizationDisplayName xml:lang="en">{sp.org_display_name}</md:OrganizationDisplayName>
    <md:OrganizationURL xml:lang="en">{sp.org_url}</md:OrganizationURL>
  </md:Organization>
  <md:ContactPerson contactType="technical">
    <md:GivenName>{sp.contact_name}</md:GivenName>
    <md:EmailAddress>{sp.contact_email}</md:EmailAddress>
  </md:ContactPerson>
</md:EntityDescriptor>"""

        try:
            # Use a dummy IdP just to generate SP metadata
            idps = self.list_idps()
            if idps:
                client = await self._get_saml_client(idps[0])
            else:
                # Create minimal client just for metadata
                config_dict = self._build_pysaml2_config(
                    SAMLIdPConfig(name="dummy"),
                    None,
                )
                saml_config = Saml2Config()
                saml_config.load(config_dict)
                client = Saml2Client(config=saml_config)

            # Generate metadata
            metadata = create_metadata_string(
                None,
                config=client.config,
                sign=False,  # Don't sign metadata
            )

            return metadata.decode("utf-8") if isinstance(metadata, bytes) else str(metadata)

        except _SAML_HANDLER_OPERATION_ERRORS as e:
            raise SAMLError(f"Failed to generate SP metadata: {e}") from e

    async def close(self) -> None:
        """Close HTTP client and clean up resources."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

        # Clean up temporary files
        for attr in ["_temp_cert_file", "_temp_key_file", "_temp_metadata_file"]:
            if hasattr(self, attr):
                temp_file = getattr(self, attr)
                if temp_file:
                    with contextlib.suppress(OSError, PermissionError, RuntimeError):
                        Path(temp_file.name).unlink(missing_ok=True)

        logger.info(
            "SAML handler closed",
            extra={"constitutional_hash": CONSTITUTIONAL_HASH},
        )
