"""
OpenID Connect Provider for MCP Authentication.

Constitutional Hash: 608508a9bd224290
MACI Role: JUDICIAL

Provides OIDC discovery and authentication:
- Automatic discovery from .well-known endpoint
- ID token validation
- UserInfo endpoint support
- Session management
"""

import asyncio
import base64
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

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

from .oauth2_provider import OAuth2Config, OAuth2GrantType, OAuth2Provider, OAuth2Token

# Optional httpx
HTTPX_AVAILABLE = False
try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    httpx = None

# Optional PyJWT for token validation
JWT_AVAILABLE = False
try:
    import jwt

    JWT_AVAILABLE = True
except ImportError:
    jwt = None

logger = get_logger(__name__)

_OIDC_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
    json.JSONDecodeError,
)
if HTTPX_AVAILABLE and httpx is not None:
    _OIDC_OPERATION_ERRORS = (*_OIDC_OPERATION_ERRORS, httpx.HTTPError)


@dataclass
class OIDCProviderMetadata:
    """OIDC provider metadata from discovery."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str | None = None
    jwks_uri: str | None = None
    registration_endpoint: str | None = None
    revocation_endpoint: str | None = None
    introspection_endpoint: str | None = None
    end_session_endpoint: str | None = None
    device_authorization_endpoint: str | None = None

    # Supported features
    scopes_supported: list[str] = field(default_factory=list)
    response_types_supported: list[str] = field(default_factory=list)
    grant_types_supported: list[str] = field(default_factory=list)
    subject_types_supported: list[str] = field(default_factory=list)
    id_token_signing_alg_values_supported: list[str] = field(default_factory=list)
    token_endpoint_auth_methods_supported: list[str] = field(default_factory=list)
    claims_supported: list[str] = field(default_factory=list)
    code_challenge_methods_supported: list[str] = field(default_factory=list)

    # Discovery timestamp
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH

    @classmethod
    def from_dict(cls, data: JSONDict) -> "OIDCProviderMetadata":
        """Create from discovery response."""
        return cls(
            issuer=data["issuer"],
            authorization_endpoint=data["authorization_endpoint"],
            token_endpoint=data["token_endpoint"],
            userinfo_endpoint=data.get("userinfo_endpoint"),
            jwks_uri=data.get("jwks_uri"),
            registration_endpoint=data.get("registration_endpoint"),
            revocation_endpoint=data.get("revocation_endpoint"),
            introspection_endpoint=data.get("introspection_endpoint"),
            end_session_endpoint=data.get("end_session_endpoint"),
            device_authorization_endpoint=data.get("device_authorization_endpoint"),
            scopes_supported=data.get("scopes_supported", []),
            response_types_supported=data.get("response_types_supported", []),
            grant_types_supported=data.get("grant_types_supported", []),
            subject_types_supported=data.get("subject_types_supported", []),
            id_token_signing_alg_values_supported=data.get(
                "id_token_signing_alg_values_supported", []
            ),
            token_endpoint_auth_methods_supported=data.get(
                "token_endpoint_auth_methods_supported", []
            ),
            claims_supported=data.get("claims_supported", []),
            code_challenge_methods_supported=data.get("code_challenge_methods_supported", []),
        )

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "issuer": self.issuer,
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": self.token_endpoint,
            "userinfo_endpoint": self.userinfo_endpoint,
            "jwks_uri": self.jwks_uri,
            "registration_endpoint": self.registration_endpoint,
            "revocation_endpoint": self.revocation_endpoint,
            "introspection_endpoint": self.introspection_endpoint,
            "end_session_endpoint": self.end_session_endpoint,
            "scopes_supported": self.scopes_supported,
            "response_types_supported": self.response_types_supported,
            "grant_types_supported": self.grant_types_supported,
            "discovered_at": self.discovered_at.isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class OIDCConfig:
    """Configuration for OIDC provider."""

    # Discovery
    issuer_url: str  # Base URL for discovery
    discovery_path: str = "/.well-known/openid-configuration"

    # Client credentials
    client_id: str = ""
    client_secret: str = ""

    # Scopes (openid is always included)
    default_scopes: list[str] = field(default_factory=lambda: ["openid", "profile", "email"])

    # Options
    timeout_seconds: int = 30
    verify_ssl: bool = True
    use_pkce: bool = True

    # Token validation
    validate_id_token: bool = True
    validate_at_hash: bool = True
    clock_skew_seconds: int = 60

    # Caching
    cache_discovery: bool = True
    discovery_cache_ttl_seconds: int = 3600  # 1 hour
    cache_jwks: bool = True
    jwks_cache_ttl_seconds: int = 86400  # 24 hours


@dataclass
class OIDCTokens:
    """OIDC tokens with ID token claims."""

    oauth2_token: OAuth2Token
    id_token_claims: JSONDict = field(default_factory=dict)
    userinfo: JSONDict = field(default_factory=dict)
    nonce: str | None = None
    validated: bool = False
    validation_errors: list[str] = field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    @property
    def subject(self) -> str | None:
        """Get subject claim."""
        return self.id_token_claims.get("sub")  # type: ignore[no-any-return]

    @property
    def email(self) -> str | None:
        """Get email from claims or userinfo."""
        return self.id_token_claims.get("email") or self.userinfo.get("email")  # type: ignore[no-any-return]

    @property
    def name(self) -> str | None:
        """Get name from claims or userinfo."""
        return self.id_token_claims.get("name") or self.userinfo.get("name")  # type: ignore[no-any-return]

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "oauth2_token": self.oauth2_token.to_dict(),
            "id_token_claims": self.id_token_claims,
            "userinfo": self.userinfo,
            "subject": self.subject,
            "email": self.email,
            "name": self.name,
            "validated": self.validated,
            "validation_errors": self.validation_errors,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class JWKSCache:
    """Cache for JSON Web Key Set."""

    keys: list[JSONDict]
    fetched_at: datetime
    expires_at: datetime


class OIDCProvider:
    """
    OpenID Connect authentication provider.

    Features:
    - Automatic discovery from .well-known endpoint
    - ID token validation with JWKS
    - UserInfo endpoint support
    - Session management

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, config: OIDCConfig):
        self.config = config
        self._metadata: OIDCProviderMetadata | None = None
        self._oauth2_provider: OAuth2Provider | None = None
        self._jwks_cache: JWKSCache | None = None
        self._lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "discoveries": 0,
            "tokens_acquired": 0,
            "id_tokens_validated": 0,
            "userinfo_fetched": 0,
            "validation_failures": 0,
        }

    async def discover(self, force_refresh: bool = False) -> OIDCProviderMetadata | None:
        """
        Discover OIDC provider metadata.

        Args:
            force_refresh: Force refresh of cached metadata

        Returns:
            OIDCProviderMetadata or None if discovery failed
        """
        if not HTTPX_AVAILABLE:
            logger.error("httpx not available for OIDC discovery")
            return None

        # Check cache
        if self._metadata and self.config.cache_discovery and not force_refresh:
            cache_age = datetime.now(UTC) - self._metadata.discovered_at
            if cache_age.total_seconds() < self.config.discovery_cache_ttl_seconds:
                return self._metadata

        discovery_url = f"{self.config.issuer_url.rstrip('/')}{self.config.discovery_path}"

        try:
            async with httpx.AsyncClient(
                timeout=self.config.timeout_seconds,
                verify=self.config.verify_ssl,
            ) as client:
                response = await client.get(discovery_url)

                if response.status_code != 200:
                    logger.error(f"OIDC discovery failed: HTTP {response.status_code}")
                    return None

                data = response.json()

        except _OIDC_OPERATION_ERRORS as e:
            logger.error(f"OIDC discovery error: {e}")
            return None

        self._metadata = OIDCProviderMetadata.from_dict(data)
        self._stats["discoveries"] += 1

        # Initialize OAuth2 provider with discovered endpoints
        self._oauth2_provider = OAuth2Provider(
            OAuth2Config(
                token_endpoint=self._metadata.token_endpoint,
                authorization_endpoint=self._metadata.authorization_endpoint,
                revocation_endpoint=self._metadata.revocation_endpoint,
                introspection_endpoint=self._metadata.introspection_endpoint,
                device_authorization_endpoint=self._metadata.device_authorization_endpoint,
                client_id=self.config.client_id,
                client_secret=self.config.client_secret,
                default_scopes=self.config.default_scopes,
                timeout_seconds=self.config.timeout_seconds,
                verify_ssl=self.config.verify_ssl,
                use_pkce=self.config.use_pkce,
            )
        )

        logger.info(f"OIDC discovery completed for {self._metadata.issuer}")
        return self._metadata

    async def acquire_tokens(
        self,
        grant_type: OAuth2GrantType = OAuth2GrantType.CLIENT_CREDENTIALS,
        scopes: list[str] | None = None,
        code: str | None = None,
        redirect_uri: str | None = None,
        refresh_token: str | None = None,
        nonce: str | None = None,
        state: str | None = None,
        cache_key: str | None = None,
    ) -> OIDCTokens | None:
        """
        Acquire OIDC tokens.

        Args:
            grant_type: OAuth2 grant type
            scopes: Requested scopes (openid always included)
            code: Authorization code
            redirect_uri: Redirect URI
            refresh_token: Refresh token
            nonce: Nonce for ID token validation
            state: State for PKCE verifier lookup
            cache_key: Key for token caching

        Returns:
            OIDCTokens or None if acquisition failed
        """
        # Ensure discovery
        if not self._oauth2_provider:
            await self.discover()
            if not self._oauth2_provider:
                return None

        # Ensure openid scope
        scopes = scopes or self.config.default_scopes
        if "openid" not in scopes:
            scopes = ["openid"] + scopes

        # Get PKCE verifier if state provided
        code_verifier = None
        if state:
            code_verifier = self._oauth2_provider.get_pkce_verifier(state)

        # Acquire OAuth2 token
        oauth2_token = await self._oauth2_provider.acquire_token(
            grant_type=grant_type,
            scopes=scopes,
            code=code,
            redirect_uri=redirect_uri,
            refresh_token=refresh_token,
            code_verifier=code_verifier,
            cache_key=cache_key,
        )

        if not oauth2_token:
            return None

        self._stats["tokens_acquired"] += 1

        # Parse and validate ID token
        id_token_claims: JSONDict = {}
        validation_errors = []
        validated = False

        if oauth2_token.id_token:
            id_token_claims, errors = await self._validate_id_token(
                oauth2_token.id_token,
                oauth2_token.access_token,
                nonce,
            )
            validation_errors = errors
            validated = len(errors) == 0

            if validated:
                self._stats["id_tokens_validated"] += 1
            else:
                self._stats["validation_failures"] += 1
                logger.warning(f"ID token validation failed: {errors}")

        return OIDCTokens(
            oauth2_token=oauth2_token,
            id_token_claims=id_token_claims,
            nonce=nonce,
            validated=validated,
            validation_errors=validation_errors,
        )

    async def get_userinfo(
        self,
        access_token: str,
    ) -> JSONDict | None:
        """
        Get user info from userinfo endpoint.

        Args:
            access_token: Access token

        Returns:
            Userinfo dictionary or None
        """
        if not self._metadata or not self._metadata.userinfo_endpoint:
            logger.warning("UserInfo endpoint not available")
            return None

        if not HTTPX_AVAILABLE:
            return None

        try:
            async with httpx.AsyncClient(
                timeout=self.config.timeout_seconds,
                verify=self.config.verify_ssl,
            ) as client:
                response = await client.get(
                    self._metadata.userinfo_endpoint,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                    },
                )

                if response.status_code != 200:
                    logger.error(f"UserInfo request failed: HTTP {response.status_code}")
                    return None

                self._stats["userinfo_fetched"] += 1
                return response.json()

        except _OIDC_OPERATION_ERRORS as e:
            logger.error(f"UserInfo error: {e}")
            return None

    async def _validate_id_token(
        self,
        id_token: str,
        access_token: str,
        expected_nonce: str | None = None,
    ) -> tuple[JSONDict, list[str]]:
        """
        Validate ID token and extract claims.

        Performs JWKS-based signature verification when validate_id_token is True.

        Returns:
            Tuple of (claims, validation_errors)
        """
        errors: list[str] = []
        claims: JSONDict = {}

        if not self.config.validate_id_token:
            # Just decode without validation (payload extraction only)
            try:
                claims = self._decode_jwt_payload(id_token)
            except _OIDC_OPERATION_ERRORS as e:
                errors.append(f"Token decode error: {e}")
            return claims, errors

        # Full validation with signature verification
        try:
            # Fetch JWKS keys for signature verification
            jwks_keys = await self._fetch_jwks()
            if not jwks_keys:
                errors.append("No JWKS keys available for signature verification")
                return {}, errors

            # Verify signature using JWKS
            claims = self._verify_jwt_signature(id_token, jwks_keys)

            # Check issuer
            if self._metadata and claims.get("iss") != self._metadata.issuer:
                errors.append(f"Invalid issuer: {claims.get('iss')} != {self._metadata.issuer}")

            # Check audience
            aud = claims.get("aud")
            if isinstance(aud, list):
                if self.config.client_id not in aud:
                    errors.append(f"Invalid audience: {aud}")
            elif aud != self.config.client_id:
                errors.append(f"Invalid audience: {aud}")

            # Check expiration
            exp = claims.get("exp")
            if exp:
                exp_time = datetime.fromtimestamp(exp, tz=UTC)
                if datetime.now(UTC) > exp_time + timedelta(seconds=self.config.clock_skew_seconds):
                    errors.append("Token expired")

            # Check issued at
            iat = claims.get("iat")
            if iat:
                iat_time = datetime.fromtimestamp(iat, tz=UTC)
                if datetime.now(UTC) < iat_time - timedelta(seconds=self.config.clock_skew_seconds):
                    errors.append("Token issued in the future")

            # Check nonce
            if expected_nonce and claims.get("nonce") != expected_nonce:
                errors.append("Nonce mismatch")

            # Check at_hash if present
            if self.config.validate_at_hash and "at_hash" in claims:
                expected_at_hash = self._compute_at_hash(access_token, claims)
                if claims.get("at_hash") != expected_at_hash:
                    errors.append("at_hash mismatch")

        except _OIDC_OPERATION_ERRORS as e:
            errors.append(f"Validation error: {e}")
            return {}, errors
        except Exception as e:
            # Catch JWT-specific errors (InvalidSignatureError, DecodeError, etc.)
            if JWT_AVAILABLE and isinstance(e, jwt.exceptions.PyJWTError):
                errors.append(f"Validation error: {e}")
                return {}, errors
            raise

        return claims, errors

    def _verify_jwt_signature(
        self,
        token: str,
        jwks_keys: list[JSONDict],
    ) -> JSONDict:
        """Verify JWT signature against JWKS keys.

        Args:
            token: The JWT token string
            jwks_keys: List of JWK key dictionaries

        Returns:
            Decoded and verified claims

        Raises:
            ValueError: If signature verification fails
        """
        if not JWT_AVAILABLE:
            raise ValueError("PyJWT is required for signature verification")

        # Get the token header to find the key ID
        unverified_header = jwt.get_unverified_header(token)
        token_kid = unverified_header.get("kid")
        token_alg = unverified_header.get("alg", "RS256")

        # Find matching key
        matching_key = None
        for key in jwks_keys:
            if token_kid and key.get("kid") == token_kid:
                matching_key = key
                break

        if matching_key is None:
            raise ValueError(f"No matching JWKS key found for kid={token_kid!r}")

        # Convert JWK to public key
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(matching_key))

        # Decode with signature verification
        return jwt.decode(
            token,
            public_key,
            algorithms=[token_alg],
            options={
                "verify_signature": True,
                "verify_exp": False,  # We check expiry manually with clock skew
                "verify_aud": False,  # We check audience manually
                "verify_iss": False,  # We check issuer manually
            },
        )

    def _decode_jwt_payload(self, token: str) -> JSONDict:
        """Extract JWT payload without signature verification.

        Used only when validate_id_token=False (explicitly opted out).
        For production use, _verify_jwt_signature performs JWKS-based
        signature verification.
        """
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid JWT format")

        # Decode payload (add padding)
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding

        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)

    def _compute_at_hash(
        self,
        access_token: str,
        claims: JSONDict,
    ) -> str:
        """Compute at_hash for access token validation."""
        # Determine hash algorithm from ID token
        alg = claims.get("alg", "RS256")

        if alg.endswith("256"):
            hash_func = hashlib.sha256
        elif alg.endswith("384"):
            hash_func = hashlib.sha384
        elif alg.endswith("512"):
            hash_func = hashlib.sha512
        else:
            hash_func = hashlib.sha256

        # Hash access token
        token_hash = hash_func(access_token.encode()).digest()
        # Take left half
        left_half = token_hash[: len(token_hash) // 2]
        # Base64url encode
        return base64.urlsafe_b64encode(left_half).decode().rstrip("=")

    async def _fetch_jwks(self) -> list[JSONDict] | None:
        """Fetch JWKS from provider."""
        if not self._metadata or not self._metadata.jwks_uri:
            return None

        # Check cache
        if self._jwks_cache:
            if datetime.now(UTC) < self._jwks_cache.expires_at:
                return self._jwks_cache.keys

        if not HTTPX_AVAILABLE:
            return None

        try:
            async with httpx.AsyncClient(
                timeout=self.config.timeout_seconds,
                verify=self.config.verify_ssl,
            ) as client:
                response = await client.get(self._metadata.jwks_uri)

                if response.status_code != 200:
                    logger.error(f"JWKS fetch failed: HTTP {response.status_code}")
                    return None

                data = response.json()
                keys = data.get("keys", [])

                # Cache JWKS
                if self.config.cache_jwks:
                    self._jwks_cache = JWKSCache(
                        keys=keys,
                        fetched_at=datetime.now(UTC),
                        expires_at=datetime.now(UTC)
                        + timedelta(seconds=self.config.jwks_cache_ttl_seconds),
                    )

                return keys  # type: ignore[no-any-return]

        except _OIDC_OPERATION_ERRORS as e:
            logger.error(f"JWKS fetch error: {e}")
            return None

    def build_authorization_url(
        self,
        redirect_uri: str,
        scopes: list[str] | None = None,
        state: str | None = None,
        nonce: str | None = None,
        login_hint: str | None = None,
        prompt: str | None = None,
    ) -> tuple[str, str, str | None] | None:
        """
        Build authorization URL for OIDC auth code flow.

        Args:
            redirect_uri: Redirect URI
            scopes: Requested scopes
            state: State parameter
            nonce: Nonce for ID token
            login_hint: Email hint for login
            prompt: Prompt behavior (none, login, consent, select_account)

        Returns:
            Tuple of (url, state, nonce) or None
        """
        if not self._oauth2_provider:
            logger.error("OAuth2 provider not initialized. Call discover() first.")
            return None

        # Build extra params
        extra_params = {}
        if login_hint:
            extra_params["login_hint"] = login_hint
        if prompt:
            extra_params["prompt"] = prompt

        # Generate nonce if not provided
        import secrets

        nonce = nonce or secrets.token_urlsafe(32)
        extra_params["nonce"] = nonce

        url, state, _ = self._oauth2_provider.build_authorization_url(
            redirect_uri=redirect_uri,
            scopes=scopes,
            state=state,
            nonce=nonce,
            extra_params=extra_params,
        )

        return url, state, nonce

    def build_logout_url(
        self,
        id_token_hint: str | None = None,
        post_logout_redirect_uri: str | None = None,
        state: str | None = None,
    ) -> str | None:
        """
        Build logout URL for OIDC session end.

        Args:
            id_token_hint: ID token for logout
            post_logout_redirect_uri: Post-logout redirect
            state: State parameter

        Returns:
            Logout URL or None
        """
        if not self._metadata or not self._metadata.end_session_endpoint:
            return None

        params = {}
        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        if post_logout_redirect_uri:
            params["post_logout_redirect_uri"] = post_logout_redirect_uri
        if state:
            params["state"] = state

        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            return f"{self._metadata.end_session_endpoint}?{query}"

        return self._metadata.end_session_endpoint

    def get_metadata(self) -> OIDCProviderMetadata | None:
        """Get cached provider metadata."""
        return self._metadata

    def get_stats(self) -> JSONDict:
        """Get provider statistics."""
        return {
            **self._stats,
            "metadata_cached": self._metadata is not None,
            "jwks_cached": self._jwks_cache is not None,
            "issuer": self._metadata.issuer if self._metadata else None,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
