"""
OAuth2 Provider for MCP Authentication.

Constitutional Hash: 608508a9bd224290
MACI Role: JUDICIAL

Provides OAuth2 token management:
- Multiple grant types (client_credentials, authorization_code, refresh_token)
- Token acquisition and caching
- Token introspection
- Token revocation
"""

import asyncio
import base64
import hashlib
import secrets
import urllib.parse
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum

# Import centralized constitutional hash
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

# Optional httpx for HTTP requests
HTTPX_AVAILABLE = False
try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    httpx = None

logger = get_logger(__name__)
_OAUTH2_PROVIDER_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class OAuth2GrantType(str, Enum):
    """OAuth2 grant types."""

    CLIENT_CREDENTIALS = "client_credentials"
    AUTHORIZATION_CODE = "authorization_code"
    REFRESH_TOKEN = "refresh_token"
    PASSWORD = "password"
    DEVICE_CODE = "device_code"


class TokenStatus(str, Enum):
    """Token status."""

    VALID = "valid"
    EXPIRED = "expired"
    REVOKED = "revoked"
    INVALID = "invalid"
    UNKNOWN = "unknown"


@dataclass
class OAuth2Config:
    """Configuration for OAuth2 provider."""

    # Endpoints
    token_endpoint: str
    authorization_endpoint: str | None = None
    revocation_endpoint: str | None = None
    introspection_endpoint: str | None = None
    device_authorization_endpoint: str | None = None

    # Client credentials
    client_id: str = ""
    client_secret: str = ""

    # Options
    default_scopes: list[str] = field(default_factory=list)
    timeout_seconds: int = 30
    verify_ssl: bool = True

    # Token handling
    token_cache_enabled: bool = True
    token_refresh_threshold_seconds: int = 300  # Refresh 5 min before expiry

    # PKCE
    use_pkce: bool = True
    pkce_method: str = "S256"  # S256 or plain


@dataclass
class OAuth2Token:
    """OAuth2 token."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    refresh_token: str | None = None
    scope: str | None = None
    id_token: str | None = None  # For OIDC
    issued_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    status: TokenStatus = TokenStatus.VALID
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __post_init__(self) -> None:
        """Calculate expiry time."""
        if self.expires_in and self.expires_at is None:
            self.expires_at = self.issued_at + timedelta(seconds=self.expires_in)

    def is_expired(self) -> bool:
        """Check if token is expired."""
        if self.expires_at is None:
            return False
        return datetime.now(UTC) >= self.expires_at

    def needs_refresh(self, threshold_seconds: int = 300) -> bool:
        """Check if token needs refresh."""
        if self.expires_at is None:
            return False
        refresh_at = self.expires_at - timedelta(seconds=threshold_seconds)
        return datetime.now(UTC) >= refresh_at

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "access_token": (
                self.access_token[:20] + "..." if len(self.access_token) > 20 else self.access_token
            ),
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            "has_refresh_token": self.refresh_token is not None,
            "scope": self.scope,
            "has_id_token": self.id_token is not None,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "status": self.status.value,
            "is_expired": self.is_expired(),
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class TokenIntrospectionResult:
    """Result of token introspection."""

    active: bool
    scope: str | None = None
    client_id: str | None = None
    username: str | None = None
    token_type: str | None = None
    exp: int | None = None
    iat: int | None = None
    sub: str | None = None
    aud: str | list[str] | None = None
    iss: str | None = None
    jti: str | None = None
    extra: JSONDict = field(default_factory=dict)


@dataclass
class PKCEChallenge:
    """PKCE challenge for authorization code flow."""

    code_verifier: str
    code_challenge: str
    code_challenge_method: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class OAuth2Provider:
    """
    OAuth2 authentication provider.

    Features:
    - Multiple grant type support
    - Token caching and refresh
    - PKCE for authorization code flow
    - Token introspection and revocation

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, config: OAuth2Config):
        self.config = config
        self._token_cache: dict[str, OAuth2Token] = {}
        self._pkce_challenges: dict[str, PKCEChallenge] = {}
        self._lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "tokens_acquired": 0,
            "tokens_refreshed": 0,
            "tokens_revoked": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "introspections": 0,
        }

    async def acquire_token(
        self,
        grant_type: OAuth2GrantType = OAuth2GrantType.CLIENT_CREDENTIALS,
        scopes: list[str] | None = None,
        code: str | None = None,
        redirect_uri: str | None = None,
        refresh_token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        code_verifier: str | None = None,
        cache_key: str | None = None,
    ) -> OAuth2Token | None:
        """
        Acquire an OAuth2 token.

        Args:
            grant_type: OAuth2 grant type
            scopes: Requested scopes
            code: Authorization code (for auth code flow)
            redirect_uri: Redirect URI (for auth code flow)
            refresh_token: Refresh token (for refresh flow)
            username: Username (for password flow)
            password: Password (for password flow)
            code_verifier: PKCE code verifier
            cache_key: Key for token caching

        Returns:
            OAuth2Token or None if acquisition failed
        """
        if not HTTPX_AVAILABLE:
            logger.error("httpx not available for OAuth2")
            return None

        # Check cache first
        cached_token = await self._check_token_cache(cache_key)
        if cached_token:
            return cached_token

        # Build request data
        request_data = self._build_token_request_data(
            grant_type, scopes, code, redirect_uri, refresh_token, username, password, code_verifier
        )
        if not request_data:
            return None

        # Execute token request
        token_data = await self._execute_token_request(request_data)
        if not token_data:
            return None

        # Parse and store token
        token = self._parse_token_response(token_data)
        if token:
            await self._store_token_in_cache(token, cache_key)
            self._stats["tokens_acquired"] += 1
            logger.info(f"Token acquired via {grant_type.value}")

        return token

    async def _check_token_cache(self, cache_key: str | None) -> OAuth2Token | None:
        """Check and return cached token if valid."""
        if not cache_key or not self.config.token_cache_enabled:
            return None

        async with self._lock:
            if cache_key in self._token_cache:
                cached = self._token_cache[cache_key]
                if not cached.is_expired():
                    self._stats["cache_hits"] += 1
                    return cached
                # Token expired, remove from cache
                del self._token_cache[cache_key]

        self._stats["cache_misses"] += 1
        return None

    def _build_token_request_data(
        self,
        grant_type: OAuth2GrantType,
        scopes: list[str] | None,
        code: str | None,
        redirect_uri: str | None,
        refresh_token: str | None,
        username: str | None,
        password: str | None,
        code_verifier: str | None,
    ) -> dict[str, str] | None:
        """Build token request data with validation."""
        scopes = scopes or self.config.default_scopes

        # Build base request data
        data = self._build_base_request_data(scopes)

        # Add grant-specific parameters
        grant_data = self._build_grant_specific_data(
            grant_type, code, redirect_uri, refresh_token, username, password, code_verifier
        )

        if grant_data is None:
            return None

        data.update(grant_data)
        return data

    def _build_base_request_data(self, scopes: list[str] | None) -> dict[str, str]:
        """Build base request data common to all grant types.

        Note: grant_type is intentionally NOT set here - it is owned by
        _build_grant_specific_data() to avoid placeholder/sentinel values.
        """
        data: dict[str, str] = {
            "client_id": self.config.client_id,
        }

        # Add client secret if available
        if self.config.client_secret:
            data["client_secret"] = self.config.client_secret

        # Add scopes
        if scopes:
            data["scope"] = " ".join(scopes)

        return data

    def _build_grant_specific_data(
        self,
        grant_type: OAuth2GrantType,
        code: str | None,
        redirect_uri: str | None,
        refresh_token: str | None,
        username: str | None,
        password: str | None,
        code_verifier: str | None,
    ) -> dict[str, str] | None:
        """Build grant-specific request data with validation."""
        data = {"grant_type": grant_type.value}

        try:
            if grant_type == OAuth2GrantType.AUTHORIZATION_CODE:
                self._add_auth_code_params(data, code, redirect_uri, code_verifier)
            elif grant_type == OAuth2GrantType.REFRESH_TOKEN:
                self._add_refresh_token_params(data, refresh_token)
            elif grant_type == OAuth2GrantType.PASSWORD:
                self._add_password_params(data, username, password)

        except ValueError as e:
            logger.error(f"Invalid token request parameters: {e}")
            return None

        return data

    @staticmethod
    def _add_auth_code_params(
        data: dict[str, str], code: str | None, redirect_uri: str | None, code_verifier: str | None
    ) -> None:
        """Add authorization code grant parameters."""
        if not code:
            raise ValueError("Authorization code required for auth code flow")
        data["code"] = code
        if redirect_uri:
            data["redirect_uri"] = redirect_uri
        if code_verifier:
            data["code_verifier"] = code_verifier

    @staticmethod
    def _add_refresh_token_params(data: dict[str, str], refresh_token: str | None) -> None:
        """Add refresh token grant parameters."""
        if not refresh_token:
            raise ValueError("Refresh token required for refresh flow")
        data["refresh_token"] = refresh_token

    @staticmethod
    def _add_password_params(
        data: dict[str, str], username: str | None, password: str | None
    ) -> None:
        """Add password grant parameters."""
        if not username or not password:
            raise ValueError("Username and password required for password flow")
        data["username"] = username
        data["password"] = password

    async def _execute_token_request(self, data: dict[str, str]) -> dict | None:
        """Execute the token request with proper error handling."""
        try:
            async with httpx.AsyncClient(
                timeout=self.config.timeout_seconds,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
                verify=self.config.verify_ssl,
            ) as client:
                response = await client.post(
                    self.config.token_endpoint,
                    data=data,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json",
                    },
                )

                if response.status_code != 200:
                    # Truncate response body to avoid logging sensitive data
                    body_preview = response.text[:200] if response.text else ""
                    logger.error(
                        "Token acquisition failed: HTTP %s - %s",
                        response.status_code,
                        body_preview,
                    )
                    return None

                return response.json()  # type: ignore[no-any-return]

        except _OAUTH2_PROVIDER_OPERATION_ERRORS as e:
            logger.error(f"Token acquisition error: {e}")
            return None

    def _parse_token_response(self, token_data: dict) -> OAuth2Token | None:
        """Parse token response data into OAuth2Token."""
        try:
            return OAuth2Token(
                access_token=token_data["access_token"],
                token_type=token_data.get("token_type", "Bearer"),
                expires_in=token_data.get("expires_in"),
                refresh_token=token_data.get("refresh_token"),
                scope=token_data.get("scope"),
                id_token=token_data.get("id_token"),
            )
        except KeyError as e:
            logger.error(f"Missing required token field: {e}")
            return None

    async def _store_token_in_cache(self, token: OAuth2Token, cache_key: str | None) -> None:
        """Store token in cache if enabled."""
        if cache_key and self.config.token_cache_enabled:
            async with self._lock:
                self._token_cache[cache_key] = token

    async def refresh_token(
        self,
        token: OAuth2Token,
        cache_key: str | None = None,
    ) -> OAuth2Token | None:
        """
        Refresh an OAuth2 token.

        Args:
            token: Token to refresh
            cache_key: Key for token caching

        Returns:
            New OAuth2Token or None if refresh failed
        """
        if not token.refresh_token:
            logger.error("No refresh token available")
            return None

        new_token = await self.acquire_token(
            grant_type=OAuth2GrantType.REFRESH_TOKEN,
            refresh_token=token.refresh_token,
            scopes=token.scope.split() if token.scope else None,
            cache_key=cache_key,
        )

        if new_token:
            self._stats["tokens_refreshed"] += 1
            logger.info("Token refreshed successfully")

        return new_token

    async def revoke_token(
        self,
        token: str,
        token_type_hint: str = "access_token",
    ) -> bool:
        """
        Revoke an OAuth2 token.

        Args:
            token: Token to revoke
            token_type_hint: Type hint (access_token or refresh_token)

        Returns:
            True if revocation successful
        """
        if not self.config.revocation_endpoint:
            logger.warning("No revocation endpoint configured")
            return False

        if not HTTPX_AVAILABLE:
            logger.error("httpx not available")
            return False

        try:
            async with httpx.AsyncClient(
                timeout=self.config.timeout_seconds,
                verify=self.config.verify_ssl,
            ) as client:
                response = await client.post(
                    self.config.revocation_endpoint,
                    data={
                        "token": token,
                        "token_type_hint": token_type_hint,
                        "client_id": self.config.client_id,
                        "client_secret": self.config.client_secret,
                    },
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )

                if response.status_code in (200, 204):
                    self._stats["tokens_revoked"] += 1
                    logger.info("Token revoked successfully")
                    return True

                logger.error(f"Token revocation failed: HTTP {response.status_code}")
                return False

        except _OAUTH2_PROVIDER_OPERATION_ERRORS as e:
            logger.error(f"Token revocation error: {e}")
            return False

    async def introspect_token(
        self,
        token: str,
        token_type_hint: str = "access_token",
    ) -> TokenIntrospectionResult | None:
        """
        Introspect an OAuth2 token.

        Args:
            token: Token to introspect
            token_type_hint: Type hint

        Returns:
            TokenIntrospectionResult or None if introspection failed
        """
        if not self.config.introspection_endpoint:
            logger.warning("No introspection endpoint configured")
            return None

        if not HTTPX_AVAILABLE:
            logger.error("httpx not available")
            return None

        try:
            # Build basic auth header
            auth = base64.b64encode(
                f"{self.config.client_id}:{self.config.client_secret}".encode()
            ).decode()

            async with httpx.AsyncClient(
                timeout=self.config.timeout_seconds,
                verify=self.config.verify_ssl,
            ) as client:
                response = await client.post(
                    self.config.introspection_endpoint,
                    data={
                        "token": token,
                        "token_type_hint": token_type_hint,
                    },
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Authorization": f"Basic {auth}",
                    },
                )

                if response.status_code != 200:
                    logger.error(f"Token introspection failed: HTTP {response.status_code}")
                    return None

                data = response.json()

        except _OAUTH2_PROVIDER_OPERATION_ERRORS as e:
            logger.error(f"Token introspection error: {e}")
            return None

        self._stats["introspections"] += 1

        return TokenIntrospectionResult(
            active=data.get("active", False),
            scope=data.get("scope"),
            client_id=data.get("client_id"),
            username=data.get("username"),
            token_type=data.get("token_type"),
            exp=data.get("exp"),
            iat=data.get("iat"),
            sub=data.get("sub"),
            aud=data.get("aud"),
            iss=data.get("iss"),
            jti=data.get("jti"),
            extra={
                k: v
                for k, v in data.items()
                if k
                not in [
                    "active",
                    "scope",
                    "client_id",
                    "username",
                    "token_type",
                    "exp",
                    "iat",
                    "sub",
                    "aud",
                    "iss",
                    "jti",
                ]
            },
        )

    def generate_pkce_challenge(self, state: str | None = None) -> PKCEChallenge:
        """
        Generate PKCE challenge for authorization code flow.

        Args:
            state: Optional state to associate with challenge

        Returns:
            PKCEChallenge
        """
        # Generate code verifier (43-128 characters)
        code_verifier = secrets.token_urlsafe(64)[:96]

        # Generate code challenge
        if self.config.pkce_method == "S256":
            code_challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
                .decode()
                .rstrip("=")
            )
        else:
            code_challenge = code_verifier

        challenge = PKCEChallenge(
            code_verifier=code_verifier,
            code_challenge=code_challenge,
            code_challenge_method=self.config.pkce_method,
        )

        # Store challenge
        if state:
            self._pkce_challenges[state] = challenge

        return challenge

    def get_pkce_verifier(self, state: str) -> str | None:
        """Get PKCE verifier for state."""
        challenge = self._pkce_challenges.get(state)
        if challenge:
            del self._pkce_challenges[state]
            return challenge.code_verifier
        return None

    def build_authorization_url(
        self,
        redirect_uri: str,
        scopes: list[str] | None = None,
        state: str | None = None,
        nonce: str | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> tuple[str, str, PKCEChallenge | None]:
        """
        Build authorization URL for auth code flow.

        Args:
            redirect_uri: Redirect URI
            scopes: Requested scopes
            state: State parameter (generated if not provided)
            nonce: Nonce for OIDC (generated if not provided)
            extra_params: Extra query parameters

        Returns:
            Tuple of (authorization_url, state, pkce_challenge)
        """
        if not self.config.authorization_endpoint:
            raise ValueError("Authorization endpoint not configured")

        state = state or secrets.token_urlsafe(32)
        scopes = scopes or self.config.default_scopes

        params = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
        }

        if nonce:
            params["nonce"] = nonce

        # Add PKCE
        pkce_challenge = None
        if self.config.use_pkce:
            pkce_challenge = self.generate_pkce_challenge(state)
            params["code_challenge"] = pkce_challenge.code_challenge
            params["code_challenge_method"] = pkce_challenge.code_challenge_method

        # Add extra params
        if extra_params:
            params.update(extra_params)

        # Build URL with proper encoding to prevent parameter injection
        query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        url = f"{self.config.authorization_endpoint}?{query}"

        return url, state, pkce_challenge

    def clear_cache(self) -> None:
        """Clear token cache."""
        self._token_cache.clear()
        self._pkce_challenges.clear()

    def get_stats(self) -> JSONDict:
        """Get provider statistics."""
        return {
            **self._stats,
            "cached_tokens": len(self._token_cache),
            "pending_pkce_challenges": len(self._pkce_challenges),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
