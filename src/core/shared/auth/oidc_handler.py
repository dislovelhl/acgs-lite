"""
ACGS-2 OpenID Connect (OIDC) Handler Service
Constitutional Hash: cdd01ef066bc6cf2

Provides enterprise-grade OIDC Relying Party (RP) implementation using Authlib.
Supports multiple identity providers including Google Workspace, Azure AD, and Okta.

Features:
    - Auto-discovery via .well-known/openid-configuration
    - PKCE (Proof Key for Code Exchange) support
    - Token exchange and validation
    - User info retrieval
    - Session management support
    - Multiple provider configuration

Usage:
    from src.core.shared.auth.oidc_handler import OIDCHandler

    # Create handler
    handler = OIDCHandler()

    # Register a provider
    handler.register_provider(
        name="google",
        client_id="your-client-id",
        client_secret="REPLACE_ME",  # pragma: allowlist secret
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration"
    )

    # Initiate login
    auth_url, state = await handler.initiate_login("google", "https://app/callback")

    # Handle callback
    user_info = await handler.handle_callback("google", code, state)
"""

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.core.shared.errors.exceptions import ACGSBaseError
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

if TYPE_CHECKING:
    from src.core.shared.models.sso_provider import SSOProvider

try:
    from authlib.jose import jwt

    HAS_AUTHLIB = True
except ImportError:
    HAS_AUTHLIB = False
    jwt = None  # type: ignore[assignment]

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False
    httpx = None  # type: ignore[assignment]

# Default timeouts for OIDC operations
DEFAULT_TIMEOUT = 10.0
AUTH_FETCH_TIMEOUT = 5.0

logger = get_logger(__name__)
# Constitutional hash constant
from src.core.shared.constants import CONSTITUTIONAL_HASH

# Default OIDC scopes
DEFAULT_SCOPES = ["openid", "profile", "email"]
_DISALLOWED_SECRET_SENTINELS = frozenset({"your-secret", "replace_me"})
_HTTPX_OIDC_ERRORS = (httpx.HTTPError,) if HAS_HTTPX else (RuntimeError,)
_OIDC_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
    *_HTTPX_OIDC_ERRORS,
)


def _normalize_secret_sentinel(secret: str) -> str:
    return "".join(ch for ch in secret.strip().lower() if ch.isalnum())


class OIDCError(ACGSBaseError):
    """Base exception for OIDC-related errors.

    Inherits from ACGSBaseError to gain constitutional hash tracking,
    correlation IDs, and structured error logging.
    """

    http_status_code = 500
    error_code = "OIDC_ERROR"


class OIDCConfigurationError(OIDCError):
    """Configuration error for OIDC provider."""

    http_status_code = 500
    error_code = "OIDC_CONFIGURATION_ERROR"


class OIDCAuthenticationError(OIDCError):
    """Authentication failed during OIDC flow."""

    http_status_code = 401
    error_code = "OIDC_AUTHENTICATION_ERROR"


class OIDCTokenError(OIDCError):
    """Token exchange or validation failed."""

    http_status_code = 401
    error_code = "OIDC_TOKEN_ERROR"


class OIDCProviderError(OIDCError):
    """Error communicating with OIDC provider."""

    http_status_code = 502  # Bad Gateway
    error_code = "OIDC_PROVIDER_ERROR"


@dataclass
class OIDCProviderConfig:
    """Configuration for an OIDC identity provider.

    Attributes:
        name: Unique provider name (e.g., 'google', 'azure', 'okta')
        client_id: OAuth 2.0 client ID from the IdP
        client_secret: OAuth 2.0 client secret
        server_metadata_url: OpenID Connect discovery URL
        scopes: OAuth scopes to request
        use_pkce: Whether to use PKCE for enhanced security
        extra_params: Additional parameters for authorization requests
    """

    name: str
    client_id: str
    client_secret: str
    server_metadata_url: str
    scopes: list[str] = field(default_factory=lambda: list(DEFAULT_SCOPES))
    use_pkce: bool = True
    extra_params: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if not self.name:
            raise OIDCConfigurationError("Provider name is required")
        if not self.client_id:
            raise OIDCConfigurationError("Client ID is required")
        if not self.client_secret:
            raise OIDCConfigurationError("Client secret is required")
        normalized_secret = _normalize_secret_sentinel(self.client_secret)
        normalized_disallowed = {
            _normalize_secret_sentinel(v) for v in _DISALLOWED_SECRET_SENTINELS
        }
        if normalized_secret in normalized_disallowed:
            raise OIDCConfigurationError(
                "Client secret uses placeholder value; configure a real secret"
            )
        if not self.server_metadata_url:
            raise OIDCConfigurationError("Server metadata URL is required")


@dataclass
class OIDCTokenResponse:
    """Token response from OIDC provider.

    Attributes:
        access_token: OAuth 2.0 access token
        token_type: Token type (typically 'Bearer')
        expires_in: Token expiration time in seconds
        refresh_token: Optional refresh token
        id_token: OIDC ID token (JWT)
        scope: Granted scopes
        raw_response: Full token response dict
    """

    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    refresh_token: str | None = None
    id_token: str | None = None
    scope: str | None = None
    raw_response: JSONDict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: JSONDict) -> "OIDCTokenResponse":
        """Create token response from dictionary.

        Args:
            data: Token response dictionary from IdP

        Returns:
            OIDCTokenResponse instance
        """
        return cls(
            access_token=str(data.get("access_token", "")),
            token_type=str(data.get("token_type", "Bearer")),
            expires_in=int(data["expires_in"]) if data.get("expires_in") is not None else None,
            refresh_token=str(data.get("refresh_token")) if data.get("refresh_token") else None,
            id_token=str(data.get("id_token")) if data.get("id_token") else None,
            scope=str(data.get("scope")) if data.get("scope") else None,
            raw_response=data,
        )


@dataclass
class OIDCUserInfo:
    """User information from OIDC provider.

    Attributes:
        sub: Subject identifier (unique user ID from IdP)
        email: User's email address
        email_verified: Whether email is verified
        name: Full name
        given_name: First name
        family_name: Last name
        picture: Profile picture URL
        locale: User's locale
        groups: Group memberships (if available)
        raw_claims: Full claims dict from IdP
    """

    sub: str
    email: str | None = None
    email_verified: bool = False
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    picture: str | None = None
    locale: str | None = None
    groups: list[str] = field(default_factory=list)
    raw_claims: JSONDict = field(default_factory=dict)

    @classmethod
    def from_claims(cls, claims: JSONDict) -> "OIDCUserInfo":
        """Create user info from OIDC claims.

        Args:
            claims: Claims dictionary from ID token or userinfo endpoint

        Returns:
            OIDCUserInfo instance
        """
        # Extract groups from various claim formats
        groups = []
        if "groups" in claims:
            groups = claims["groups"]
        elif "roles" in claims:
            groups = claims["roles"]
        elif "https://schemas.microsoft.com/claims/groups" in claims:
            # Azure AD group claims
            groups = claims["https://schemas.microsoft.com/claims/groups"]

        return cls(
            sub=claims.get("sub", ""),
            email=claims.get("email"),
            email_verified=claims.get("email_verified", False),
            name=claims.get("name"),
            given_name=claims.get("given_name"),
            family_name=claims.get("family_name"),
            picture=claims.get("picture"),
            locale=claims.get("locale"),
            groups=groups if isinstance(groups, list) else [],
            raw_claims=claims,
        )


class OIDCHandler:
    """OpenID Connect handler for enterprise SSO authentication.

    This handler manages OIDC authentication flows for multiple identity
    providers. It supports:
    - Auto-discovery via .well-known/openid-configuration
    - PKCE (Proof Key for Code Exchange)
    - Token exchange and validation
    - User info retrieval
    - Multiple simultaneous providers

    Example:
        handler = OIDCHandler()
        handler.register_provider(
            name="google",
            client_id="your-client-id",
            client_secret="REPLACE_ME",  # pragma: allowlist secret
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration"
        )

        # Start login
        auth_url, state = await handler.initiate_login("google", "https://app/callback")

        # After user authenticates, handle callback
        user_info = await handler.handle_callback("google", code, state)
    """

    def __init__(self) -> None:
        """Initialize OIDC handler."""
        self._providers: dict[str, OIDCProviderConfig] = {}
        self._metadata_cache: dict[str, JSONDict] = {}
        self._metadata_timestamps: dict[str, datetime] = {}
        self._pending_states: dict[str, JSONDict] = {}
        # H-4 fix: Bound pending states to prevent DoS via login flow flooding.
        self._max_pending_states: int = 10_000
        self._pending_state_ttl_seconds: int = 600  # 10 minutes
        self._http_client: httpx.AsyncClient | None = None

        logger.info(
            "OIDC handler initialized",
            extra={"constitutional_hash": CONSTITUTIONAL_HASH},
        )

    def _evict_stale_pending_states(self) -> None:
        """H-4 fix: Remove expired pending OIDC states to bound memory usage."""
        now = datetime.now(UTC)
        expired = [
            state
            for state, data in self._pending_states.items()
            if (now - datetime.fromisoformat(data["created_at"])).total_seconds()
            > self._pending_state_ttl_seconds
        ]
        for state in expired:
            del self._pending_states[state]
        if expired:
            logger.info("Evicted %d expired OIDC pending states", len(expired))

    def register_provider(
        self,
        name: str,
        client_id: str,
        client_secret: str,
        server_metadata_url: str,
        scopes: list[str] | None = None,
        use_pkce: bool = True,
        extra_params: dict[str, str] | None = None,
    ) -> None:
        """Register an OIDC provider.

        Args:
            name: Unique provider name (e.g., 'google', 'azure', 'okta')
            client_id: OAuth 2.0 client ID
            client_secret: OAuth 2.0 client secret
            server_metadata_url: OpenID Connect discovery URL
            scopes: OAuth scopes to request (default: openid, profile, email)
            use_pkce: Whether to use PKCE (default: True)
            extra_params: Additional authorization request parameters

        Raises:
            OIDCConfigurationError: If configuration is invalid
        """
        config = OIDCProviderConfig(
            name=name,
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url=server_metadata_url,
            scopes=scopes or list(DEFAULT_SCOPES),
            use_pkce=use_pkce,
            extra_params=extra_params or {},
        )

        self._providers[name] = config
        logger.info(
            "OIDC provider registered",
            extra={
                "provider": name,
                "metadata_url": server_metadata_url,
                "use_pkce": use_pkce,
                "scopes": config.scopes,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

    def register_provider_from_model(
        self,
        provider: "SSOProvider",  # SSOProvider model
    ) -> None:
        """Register an OIDC provider from database model.

        Args:
            provider: SSOProvider model instance

        Raises:
            OIDCConfigurationError: If provider is not OIDC or config is invalid
        """
        if not provider.is_oidc:
            raise OIDCConfigurationError(f"Provider '{provider.name}' is not an OIDC provider")

        # Validate required fields
        errors = provider.validate_oidc_config()
        if errors:
            raise OIDCConfigurationError(
                f"Invalid OIDC configuration for '{provider.name}': {'; '.join(errors)}"
            )

        self.register_provider(
            name=provider.name,
            client_id=provider.oidc_client_id,
            client_secret=provider.oidc_client_secret,
            server_metadata_url=provider.oidc_metadata_url,
            scopes=provider.oidc_scope_list,
            use_pkce=True,
            extra_params=provider.get_config(),
        )

    def get_provider(self, name: str) -> OIDCProviderConfig:
        """Get a registered provider configuration.

        Args:
            name: Provider name

        Returns:
            Provider configuration

        Raises:
            OIDCConfigurationError: If provider not found
        """
        if name not in self._providers:
            raise OIDCConfigurationError(f"OIDC provider '{name}' not registered")
        return self._providers[name]

    def list_providers(self) -> list[str]:
        """List all registered provider names.

        Returns:
            List of provider names
        """
        return list(self._providers.keys())

    async def _get_http_client(self) -> "httpx.AsyncClient":
        """Get or create HTTP client.

        Returns:
            httpx AsyncClient instance
        """
        if self._http_client is None:
            if not HAS_HTTPX:
                raise OIDCError("httpx library is required for OIDC operations")
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(DEFAULT_TIMEOUT, connect=AUTH_FETCH_TIMEOUT),
                headers={"User-Agent": "ACGS-2/OIDC-Handler/1.0"},
            )
        return self._http_client

    async def _fetch_metadata(
        self, provider: OIDCProviderConfig, force_refresh: bool = False
    ) -> JSONDict:
        """Fetch OpenID Connect metadata from discovery endpoint.

        Args:
            provider: Provider configuration
            force_refresh: Force metadata refresh even if cached

        Returns:
            Provider metadata dictionary

        Raises:
            OIDCProviderError: If metadata fetch fails
        """
        cache_key = provider.name

        # Check cache validity (24 hours)
        if not force_refresh and cache_key in self._metadata_cache:
            cached_at = self._metadata_timestamps.get(cache_key)
            if cached_at:
                age = datetime.now(UTC) - cached_at
                if age.total_seconds() < 86400:  # 24 hours
                    return self._metadata_cache[cache_key]

        try:
            client = await self._get_http_client()
            response = await client.get(provider.server_metadata_url)
            response.raise_for_status()
            metadata = response.json()

            # Cache the metadata
            self._metadata_cache[cache_key] = metadata
            self._metadata_timestamps[cache_key] = datetime.now(UTC)

            logger.info(
                "OIDC metadata fetched",
                extra={
                    "provider": provider.name,
                    "issuer": metadata.get("issuer"),
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

            return metadata

        except _OIDC_OPERATION_ERRORS as e:
            # Try to use cached metadata on error
            if cache_key in self._metadata_cache:
                logger.warning(
                    "Failed to refresh OIDC metadata, using cached version",
                    extra={
                        "provider": provider.name,
                        "error": str(e),
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                    },
                )
                return self._metadata_cache[cache_key]

            raise OIDCProviderError(
                f"Failed to fetch OIDC metadata for '{provider.name}': {e}"
            ) from e

    def _generate_state(self) -> str:
        """Generate a cryptographically secure state parameter.

        Returns:
            Random state string
        """
        return secrets.token_urlsafe(32)

    def _generate_code_verifier(self) -> str:
        """Generate PKCE code verifier.

        Returns:
            Random code verifier string
        """
        return secrets.token_urlsafe(64)

    def _generate_code_challenge(self, verifier: str) -> str:
        """Generate PKCE code challenge from verifier.

        Args:
            verifier: Code verifier string

        Returns:
            Base64url-encoded SHA256 hash of verifier
        """
        digest = hashlib.sha256(verifier.encode()).digest()
        # Convert to base64url without padding
        import base64

        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    async def initiate_login(
        self,
        provider_name: str,
        redirect_uri: str,
        nonce: str | None = None,
    ) -> tuple[str, str]:
        """Initiate OIDC login flow.

        This generates the authorization URL that the user should be
        redirected to for authentication.

        Args:
            provider_name: Name of the registered provider
            redirect_uri: Callback URL after authentication
            nonce: Optional nonce for replay attack prevention

        Returns:
            Tuple of (authorization_url, state)

        Raises:
            OIDCConfigurationError: If provider not found
            OIDCProviderError: If metadata fetch fails
        """
        provider = self.get_provider(provider_name)
        metadata = await self._fetch_metadata(provider)

        authorization_endpoint = metadata.get("authorization_endpoint")
        if not authorization_endpoint:
            raise OIDCProviderError(
                f"Authorization endpoint not found in metadata for '{provider_name}'"
            )

        # Generate state and PKCE values
        state = self._generate_state()
        code_verifier = self._generate_code_verifier() if provider.use_pkce else None
        code_challenge = self._generate_code_challenge(code_verifier) if code_verifier else None

        # H-4 fix: Evict expired/oldest states before adding new ones to prevent OOM.
        self._evict_stale_pending_states()
        if len(self._pending_states) >= self._max_pending_states:
            logger.warning(
                "Pending OIDC states at capacity (%d), evicting oldest",
                self._max_pending_states,
            )
            oldest_key = next(iter(self._pending_states))
            del self._pending_states[oldest_key]

        # Store pending state for callback verification
        self._pending_states[state] = {
            "provider": provider_name,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
            "nonce": nonce or secrets.token_urlsafe(16),
            "created_at": datetime.now(UTC).isoformat(),
        }

        # Build authorization URL
        params = {
            "client_id": provider.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(provider.scopes),
            "state": state,
            "nonce": self._pending_states[state]["nonce"],
        }

        # Add PKCE parameters
        if provider.use_pkce and code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"

        # Add extra provider-specific parameters
        params.update(provider.extra_params)

        # Construct URL
        from urllib.parse import urlencode

        auth_url = f"{authorization_endpoint}?{urlencode(params)}"

        logger.info(
            "OIDC login initiated",
            extra={
                "provider": provider_name,
                "state": state[:8] + "...",  # Log partial state for security
                "use_pkce": provider.use_pkce,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

        return auth_url, state

    async def handle_callback(
        self,
        provider_name: str,
        code: str,
        state: str,
        redirect_uri: str | None = None,
    ) -> OIDCUserInfo:
        """Handle OIDC callback after IdP authentication.

        This exchanges the authorization code for tokens and retrieves
        user information.

        Args:
            provider_name: Name of the registered provider
            code: Authorization code from callback
            state: State parameter from callback
            redirect_uri: Optional redirect URI (uses stored value if not provided)

        Returns:
            User information from IdP

        Raises:
            OIDCAuthenticationError: If state validation fails
            OIDCTokenError: If token exchange fails
            OIDCProviderError: If user info retrieval fails
        """
        # Validate state
        if state not in self._pending_states:
            raise OIDCAuthenticationError(
                "Invalid or expired state parameter. Possible CSRF attack."
            )

        stored = self._pending_states.pop(state)

        # Verify provider matches
        if stored["provider"] != provider_name:
            raise OIDCAuthenticationError(
                f"Provider mismatch: expected '{stored['provider']}', got '{provider_name}'"
            )

        provider = self.get_provider(provider_name)
        callback_redirect_uri = redirect_uri or stored["redirect_uri"]

        # Exchange code for tokens
        tokens = await self._exchange_code(
            provider=provider,
            code=code,
            redirect_uri=callback_redirect_uri,
            code_verifier=stored.get("code_verifier"),
        )

        # Get user info (prefer ID token claims, fallback to userinfo endpoint)
        user_info = await self._get_user_info(provider, tokens)

        logger.info(
            "OIDC authentication successful",
            extra={
                "provider": provider_name,
                "user_sub": user_info.sub[:8] + "..." if user_info.sub else "N/A",
                "email": user_info.email,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

        return user_info

    async def _exchange_code(
        self,
        provider: OIDCProviderConfig,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> OIDCTokenResponse:
        """Exchange authorization code for tokens.

        Args:
            provider: Provider configuration
            code: Authorization code
            redirect_uri: Callback URI used in authorization request
            code_verifier: PKCE code verifier (if used)

        Returns:
            Token response from IdP

        Raises:
            OIDCTokenError: If token exchange fails
        """
        metadata = await self._fetch_metadata(provider)
        token_endpoint = metadata.get("token_endpoint")

        if not token_endpoint:
            raise OIDCTokenError(f"Token endpoint not found in metadata for '{provider.name}'")

        try:
            client = await self._get_http_client()

            data = {
                "grant_type": "authorization_code",
                "client_id": provider.client_id,
                "client_secret": provider.client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            }

            if code_verifier:
                data["code_verifier"] = code_verifier

            response = await client.post(
                token_endpoint,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get(
                    "error_description", error_data.get("error", "Unknown error")
                )
                raise OIDCTokenError(f"Token exchange failed for '{provider.name}': {error_msg}")

            token_data = response.json()
            return OIDCTokenResponse.from_dict(token_data)

        except OIDCTokenError:
            raise
        except _OIDC_OPERATION_ERRORS as e:
            raise OIDCTokenError(f"Token exchange failed for '{provider.name}': {e}") from e

    async def _get_user_info(
        self,
        provider: OIDCProviderConfig,
        tokens: OIDCTokenResponse,
    ) -> OIDCUserInfo:
        """Get user information from tokens or userinfo endpoint.

        Args:
            provider: Provider configuration
            tokens: Token response from exchange

        Returns:
            User information
        """
        # First, try to extract claims from ID token
        if tokens.id_token:
            try:
                claims = await self._decode_id_token(tokens.id_token, provider)
                if claims.get("sub"):
                    return OIDCUserInfo.from_claims(claims)
            except (OIDCTokenError, *_OIDC_OPERATION_ERRORS) as e:
                logger.warning(
                    "Failed to validate ID token, falling back to userinfo endpoint",
                    extra={
                        "provider": provider.name,
                        "error": str(e),
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                    },
                )

        # Fallback to userinfo endpoint
        return await self._fetch_userinfo(provider, tokens.access_token)

    async def _decode_id_token(self, id_token: str, provider: OIDCProviderConfig) -> JSONDict:
        """Decode and validate ID token signature against provider JWKS.

        Args:
            id_token: JWT ID token
            provider: OIDC provider configuration

        Returns:
            Validated token claims dictionary

        Raises:
            OIDCTokenError: If validation fails
        """
        try:
            if not HAS_AUTHLIB:
                raise OIDCTokenError("authlib library is required for ID token validation")

            # Fetch JWKS from provider metadata
            metadata = await self._fetch_metadata(provider)
            jwks_uri = metadata.get("jwks_uri")
            if not jwks_uri:
                raise OIDCTokenError(f"JWKS URI not found for provider '{provider.name}'")

            client = await self._get_http_client()
            resp = await client.get(jwks_uri)
            resp.raise_for_status()
            jwks_data = resp.json()

            # Load JWKS
            from authlib.jose import JsonWebKey, JWTClaims

            jwk_set = JsonWebKey.import_key_set(jwks_data)

            issuer = metadata.get("issuer")
            if not issuer:
                raise OIDCTokenError(f"Issuer not found for provider '{provider.name}'")

            # Decode and validate token
            claims = jwt.decode(
                id_token,
                jwk_set,
                claims_cls=JWTClaims,
                claims_options={
                    "iss": {"essential": True, "values": [issuer]},
                    "aud": {"essential": True, "values": [provider.client_id]},
                    "exp": {"essential": True},
                    "iat": {"essential": True},
                    "nonce": {"essential": False},
                },
            )
            claims.validate()

            return dict(claims)
        except OIDCTokenError:
            raise
        except _OIDC_OPERATION_ERRORS as e:
            raise OIDCTokenError(f"Failed to validate ID token: {e}") from e
        except Exception as e:
            raise OIDCTokenError(f"Failed to validate ID token: {e}") from e

    async def _fetch_userinfo(
        self,
        provider: OIDCProviderConfig,
        access_token: str,
    ) -> OIDCUserInfo:
        """Fetch user info from userinfo endpoint.

        Args:
            provider: Provider configuration
            access_token: Access token for API call

        Returns:
            User information

        Raises:
            OIDCProviderError: If userinfo request fails
        """
        metadata = await self._fetch_metadata(provider)
        userinfo_endpoint = metadata.get("userinfo_endpoint")

        if not userinfo_endpoint:
            raise OIDCProviderError(
                f"Userinfo endpoint not found in metadata for '{provider.name}'"
            )

        try:
            client = await self._get_http_client()
            response = await client.get(
                userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code != 200:
                raise OIDCProviderError(
                    f"Userinfo request failed for '{provider.name}': {response.status_code}"
                )

            claims = response.json()
            return OIDCUserInfo.from_claims(claims)

        except OIDCProviderError:
            raise
        except _OIDC_OPERATION_ERRORS as e:
            raise OIDCProviderError(f"Userinfo request failed for '{provider.name}': {e}") from e

    async def refresh_token(
        self,
        provider_name: str,
        refresh_token: str,
    ) -> OIDCTokenResponse:
        """Refresh an access token using a refresh token.

        Args:
            provider_name: Name of the registered provider
            refresh_token: Refresh token from initial token exchange

        Returns:
            New token response

        Raises:
            OIDCTokenError: If refresh fails
        """
        provider = self.get_provider(provider_name)
        metadata = await self._fetch_metadata(provider)
        token_endpoint = metadata.get("token_endpoint")

        if not token_endpoint:
            raise OIDCTokenError(f"Token endpoint not found in metadata for '{provider_name}'")

        try:
            client = await self._get_http_client()

            response = await client.post(
                token_endpoint,
                data={
                    "grant_type": "refresh_token",
                    "client_id": provider.client_id,
                    "client_secret": provider.client_secret,
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get(
                    "error_description", error_data.get("error", "Unknown error")
                )
                raise OIDCTokenError(f"Token refresh failed for '{provider_name}': {error_msg}")

            token_data = response.json()

            logger.info(
                "OIDC token refreshed",
                extra={
                    "provider": provider_name,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

            return OIDCTokenResponse.from_dict(token_data)

        except OIDCTokenError:
            raise
        except _OIDC_OPERATION_ERRORS as e:
            raise OIDCTokenError(f"Token refresh failed for '{provider_name}': {e}") from e

    async def logout(
        self,
        provider_name: str,
        id_token_hint: str | None = None,
        post_logout_redirect_uri: str | None = None,
    ) -> str | None:
        """Get logout URL for OIDC RP-initiated logout.

        Args:
            provider_name: Name of the registered provider
            id_token_hint: ID token for logout hint
            post_logout_redirect_uri: Where to redirect after logout

        Returns:
            Logout URL (or None if provider doesn't support RP-initiated logout)
        """
        provider = self.get_provider(provider_name)
        metadata = await self._fetch_metadata(provider)

        logout_endpoint = metadata.get("end_session_endpoint")
        if not logout_endpoint:
            logger.info(
                "Provider does not support RP-initiated logout",
                extra={
                    "provider": provider_name,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )
            return None

        from urllib.parse import urlencode

        params = {"client_id": provider.client_id}

        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        if post_logout_redirect_uri:
            params["post_logout_redirect_uri"] = post_logout_redirect_uri

        logout_url = f"{logout_endpoint}?{urlencode(params)}"

        logger.info(
            "OIDC logout URL generated",
            extra={
                "provider": provider_name,
                "has_id_token_hint": bool(id_token_hint),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

        return logout_url

    def validate_state(self, state: str) -> bool:
        """Validate a pending state parameter.

        Args:
            state: State to validate

        Returns:
            True if state is valid and pending
        """
        return state in self._pending_states

    def clear_expired_states(self, max_age_seconds: int = 600) -> int:
        """Clear expired pending states.

        Args:
            max_age_seconds: Maximum age of pending states (default: 10 minutes)

        Returns:
            Number of states cleared
        """
        now = datetime.now(UTC)
        expired = []

        for state, data in self._pending_states.items():
            created = datetime.fromisoformat(data["created_at"])
            if (now - created).total_seconds() > max_age_seconds:
                expired.append(state)

        for state in expired:
            del self._pending_states[state]

        if expired:
            logger.info(
                "Cleared expired OIDC states",
                extra={
                    "count": len(expired),
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

        return len(expired)

    async def close(self) -> None:
        """Close HTTP client and clean up resources."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

        logger.info(
            "OIDC handler closed",
            extra={"constitutional_hash": CONSTITUTIONAL_HASH},
        )
