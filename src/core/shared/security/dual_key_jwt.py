"""
ACGS-2 Dual-Key JWT Validator for Zero-Downtime Rotation
Constitutional Hash: cdd01ef066bc6cf2

This module provides JWT validation that supports dual-key mode during secret
rotation, enabling zero-downtime key rotation by accepting tokens signed with
either the current or previous key.

Usage:
    validator = DualKeyJWTValidator()
    claims = await validator.validate_token(token)

Features:
    - Accepts tokens signed with current or previous key (during rotation)
    - Automatic key refresh from Vault or environment
    - Key ID (kid) based routing for efficient validation
    - Constitutional hash verification
    - Comprehensive audit logging
"""

import asyncio
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from pydantic import BaseModel, Field

from src.core.shared.structured_logging import get_logger

try:
    from src.core.shared.types import JSONDict, JSONValue
except ImportError:
    JSONDict = dict[str, object]  # type: ignore[misc, assignment]
    JSONValue = object

logger = get_logger(__name__)
# Constitutional compliance

from src.core.shared.constants import CONSTITUTIONAL_HASH


class KeyMetadata(BaseModel):
    """Metadata for a signing key."""

    kid: str = Field(..., description="Key ID (version identifier)")
    algorithm: str = Field(default="RS256", description="Signing algorithm")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    is_current: bool = Field(default=True, description="Whether this is the current key")
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)


class DualKeyConfig(BaseModel):
    """Configuration for dual-key JWT validation."""

    enabled: bool = Field(default=True, description="Enable dual-key validation")
    grace_period_hours: int = Field(
        default=4, description="Hours to accept previous key after rotation"
    )
    max_keys: int = Field(default=2, description="Maximum concurrent keys")
    refresh_interval_seconds: int = Field(
        default=60, description="Key refresh interval from secret store"
    )
    require_kid: bool = Field(default=False, description="Require kid header in tokens")


class JWTValidationResult(BaseModel):
    """Result of JWT validation."""

    valid: bool
    claims: JSONDict | None = None
    key_used: str | None = None  # kid of the key that validated the token
    error: str | None = None
    constitutional_compliant: bool = True


class DualKeyJWTValidator:
    """
    JWT validator supporting dual-key mode for zero-downtime rotation.

    During a key rotation, this validator will:
    1. Try the current key first (if kid matches or no kid specified)
    2. Fall back to previous key if current key fails
    3. Log which key successfully validated for monitoring

    Example:
        ```python
        validator = DualKeyJWTValidator()

        # Load keys from environment or Vault
        await validator.load_keys_from_env()

        # Validate a token
        result = validator.validate_token(token)
        if result.valid:
            logger.info(f"Token validated with key: {result.key_used}")
            logger.info(f"Claims: {result.claims}")
        else:
            logger.error(f"Validation failed: {result.error}")
        ```
    """

    def __init__(
        self,
        config: DualKeyConfig | None = None,
        vault_client: object | None = None,
    ):
        """
        Initialize the dual-key JWT validator.

        Args:
            config: Configuration for dual-key validation
            vault_client: Optional Vault client for key retrieval
        """
        self.config = config or DualKeyConfig()
        self._vault_client = vault_client

        # Key storage: {kid: (private_key_bytes, public_key_bytes, metadata)}
        self._keys: dict[str, tuple[bytes | None, bytes, KeyMetadata]] = {}
        self._current_kid: str | None = None
        self._previous_kid: str | None = None

        # Key refresh management
        self._last_refresh: datetime | None = None
        self._refresh_lock = asyncio.Lock()

        # Validation statistics
        self._validation_stats = {
            "total_validations": 0,
            "current_key_validations": 0,
            "previous_key_validations": 0,
            "failures": 0,
        }

        logger.info(
            f"DualKeyJWTValidator initialized. "
            f"Dual-key mode: {self.config.enabled}, "
            f"Grace period: {self.config.grace_period_hours}h"
        )

    async def load_keys_from_env(self) -> bool:
        """
        Load signing keys from environment variables.

        Expected environment variables:
            JWT_CURRENT_PRIVATE_KEY: Base64-encoded current private key
            JWT_CURRENT_PUBLIC_KEY: Base64-encoded current public key
            JWT_CURRENT_KID: Key ID for current key
            JWT_PREVIOUS_PRIVATE_KEY: Base64-encoded previous private key (optional)
            JWT_PREVIOUS_PUBLIC_KEY: Base64-encoded previous public key (optional)
            JWT_PREVIOUS_KID: Key ID for previous key (optional)

        Returns:
            True if at least the current key was loaded
        """
        import base64
        import os

        try:
            # Load current key
            current_private = os.getenv("JWT_CURRENT_PRIVATE_KEY", "")
            current_public = os.getenv("JWT_CURRENT_PUBLIC_KEY", "")
            current_kid = os.getenv("JWT_CURRENT_KID", "v1")

            if current_public:
                current_private_bytes = (
                    base64.b64decode(current_private) if current_private else None
                )
                current_public_bytes = base64.b64decode(current_public)

                self._keys[current_kid] = (
                    current_private_bytes,
                    current_public_bytes,
                    KeyMetadata(kid=current_kid, is_current=True),
                )
                self._current_kid = current_kid
                logger.info(f"Loaded current key: {current_kid}")

            # Load previous key if dual-key mode enabled
            if self.config.enabled:
                prev_private = os.getenv("JWT_PREVIOUS_PRIVATE_KEY", "")
                prev_public = os.getenv("JWT_PREVIOUS_PUBLIC_KEY", "")
                prev_kid = os.getenv("JWT_PREVIOUS_KID", "")

                if prev_public and prev_kid:
                    prev_private_bytes = base64.b64decode(prev_private) if prev_private else None
                    prev_public_bytes = base64.b64decode(prev_public)

                    # Calculate expiry based on grace period
                    expires_at = datetime.now(UTC) + timedelta(hours=self.config.grace_period_hours)

                    self._keys[prev_kid] = (
                        prev_private_bytes,
                        prev_public_bytes,
                        KeyMetadata(
                            kid=prev_kid,
                            is_current=False,
                            expires_at=expires_at,
                        ),
                    )
                    self._previous_kid = prev_kid
                    logger.info(f"Loaded previous key: {prev_kid}, expires: {expires_at}")

            self._last_refresh = datetime.now(UTC)
            return self._current_kid is not None

        except (ValueError, KeyError, OSError) as e:
            logger.error(f"Failed to load keys from environment: {e}")
            return False

    async def load_keys_from_vault(
        self,
        current_path: str = "secret/data/acgs2/jwt/signing/current",
        previous_path: str = "secret/data/acgs2/jwt/signing/previous",
    ) -> bool:
        """
        Load signing keys from HashiCorp Vault.

        Args:
            current_path: Vault path for current key
            previous_path: Vault path for previous key

        Returns:
            True if at least the current key was loaded
        """
        if not self._vault_client:
            logger.warning("No Vault client configured, falling back to env")
            return await self.load_keys_from_env()

        try:
            import base64

            # Load current key
            current_secret = self._vault_client.secrets.kv.v2.read_secret_version(
                path=current_path.replace("secret/data/", "")
            )
            current_data = current_secret["data"]["data"]

            current_kid = current_data.get("kid", f"v{current_data.get('version', 1)}")
            current_public = base64.b64decode(current_data["public_key"])
            current_private = (
                base64.b64decode(current_data.get("key", "")) if current_data.get("key") else None
            )

            self._keys[current_kid] = (
                current_private,
                current_public,
                KeyMetadata(
                    kid=current_kid,
                    is_current=True,
                    created_at=datetime.fromisoformat(
                        current_data.get("created_at", datetime.now(UTC).isoformat())
                    ),
                ),
            )
            self._current_kid = current_kid

            # Check if dual-key mode is enabled in Vault
            dual_key_enabled = current_data.get("dual_key_enabled", "false") == "true"

            if self.config.enabled and dual_key_enabled:
                try:
                    prev_secret = self._vault_client.secrets.kv.v2.read_secret_version(
                        path=previous_path.replace("secret/data/", "")
                    )
                    prev_data = prev_secret["data"]["data"]

                    prev_kid = prev_data.get("kid", f"v{prev_data.get('version', 0)}")
                    prev_public = base64.b64decode(prev_data["public_key"])

                    # Use expires_at from Vault if available
                    expires_at_str = prev_data.get("expires_at") or current_data.get(
                        "dual_key_expires"
                    )
                    if expires_at_str:
                        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                    else:
                        expires_at = datetime.now(UTC) + timedelta(
                            hours=self.config.grace_period_hours
                        )

                    self._keys[prev_kid] = (
                        None,  # Don't load previous private key
                        prev_public,
                        KeyMetadata(kid=prev_kid, is_current=False, expires_at=expires_at),
                    )
                    self._previous_kid = prev_kid
                    logger.info(f"Loaded previous key from Vault: {prev_kid}")
                except (ValueError, KeyError, RuntimeError) as e:
                    logger.debug(f"No previous key in Vault ({type(e).__name__}): {e}")

            self._last_refresh = datetime.now(UTC)
            logger.info(f"Loaded keys from Vault. Current: {current_kid}")
            return True

        except (RuntimeError, ValueError, KeyError) as e:
            logger.error(f"Failed to load keys from Vault ({type(e).__name__}): {e}")
            return await self.load_keys_from_env()

    async def refresh_keys_if_needed(self) -> None:
        """Refresh keys if the refresh interval has passed."""
        if not self._last_refresh:
            return

        time_since_refresh = (datetime.now(UTC) - self._last_refresh).total_seconds()

        if time_since_refresh < self.config.refresh_interval_seconds:
            return

        async with self._refresh_lock:
            # Double-check after acquiring lock
            time_since_refresh = (datetime.now(UTC) - self._last_refresh).total_seconds()
            if time_since_refresh >= self.config.refresh_interval_seconds:
                if self._vault_client:
                    await self.load_keys_from_vault()
                else:
                    await self.load_keys_from_env()

    def _cleanup_expired_keys(self) -> None:
        """Remove keys that have passed their expiration."""
        now = datetime.now(UTC)
        expired_kids = [
            kid
            for kid, (_, _, metadata) in self._keys.items()
            if metadata.expires_at and metadata.expires_at < now
        ]

        for kid in expired_kids:
            del self._keys[kid]
            if kid == self._previous_kid:
                self._previous_kid = None
            logger.info(f"Removed expired key: {kid}")

    def validate_token(
        self,
        token: str,
        verify_exp: bool = True,
        audience: str | None = None,
        issuer: str = "acgs2",
    ) -> JWTValidationResult:
        """
        Validate a JWT token using dual-key strategy.

        Args:
            token: JWT token string
            verify_exp: Whether to verify expiration
            audience: Expected audience (optional)
            issuer: Expected issuer

        Returns:
            JWTValidationResult with validation status and claims
        """
        self._validation_stats["total_validations"] += 1
        self._cleanup_expired_keys()

        if not self._keys:
            return JWTValidationResult(
                valid=False,
                error="No signing keys loaded",
                constitutional_compliant=False,
            )

        token_kid = self._extract_token_kid(token)
        keys_to_try, early_error = self._determine_keys_to_try(token_kid)
        if early_error is not None:
            return early_error

        last_error = ""
        for kid in keys_to_try:
            key_entry = self._keys.get(kid)
            if key_entry is None:
                continue

            _, public_key, metadata = key_entry
            if self._is_key_expired(metadata):
                continue

            try:
                claims = self._decode_token_claims(
                    token=token,
                    public_key=public_key,
                    verify_exp=verify_exp,
                    audience=audience,
                    issuer=issuer,
                )
            except JWTError as e:
                last_error = str(e)
                continue

            hash_error = self._validate_constitutional_hash_claim(claims)
            if hash_error is not None:
                return hash_error

            self._record_successful_validation(kid)
            logger.debug(f"Token validated with key: {kid}")
            return JWTValidationResult(
                valid=True,
                claims=claims,
                key_used=kid,
                constitutional_compliant=True,
            )

        self._validation_stats["failures"] += 1
        logger.warning(f"Token validation failed: {last_error}")
        return JWTValidationResult(
            valid=False,
            error=f"Token validation failed: {last_error}",
            constitutional_compliant=True,
        )

    def _extract_token_kid(self, token: str) -> str | None:
        """Extract key ID from JWT header without signature validation."""
        try:
            unverified_header = jwt.get_unverified_header(token)
            return unverified_header.get("kid")
        except JWTError:
            return None

    def _determine_keys_to_try(
        self,
        token_kid: str | None,
    ) -> tuple[list[str], JWTValidationResult | None]:
        """Determine key traversal order for token validation."""
        keys_to_try: list[str] = []

        if token_kid and token_kid in self._keys:
            keys_to_try.append(token_kid)
            keys_to_try.extend(kid for kid in self._keys if kid != token_kid)
            return keys_to_try, None

        if self.config.require_kid and token_kid is None:
            return [], JWTValidationResult(
                valid=False,
                error="Token missing required 'kid' header",
                constitutional_compliant=True,
            )

        if self._current_kid:
            keys_to_try.append(self._current_kid)
        if self._previous_kid and self.config.enabled:
            keys_to_try.append(self._previous_kid)
        return keys_to_try, None

    def _is_key_expired(self, metadata: KeyMetadata) -> bool:
        """Check whether a key is expired and should be skipped."""
        return bool(metadata.expires_at and metadata.expires_at < datetime.now(UTC))

    def _decode_token_claims(
        self,
        token: str,
        public_key: bytes,
        verify_exp: bool,
        audience: str | None,
        issuer: str,
    ) -> JSONDict:
        """Decode JWT claims with configured verification options."""
        options = {
            "verify_exp": verify_exp,
            "verify_aud": audience is not None,
        }
        return jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            options=options,
        )

    def _validate_constitutional_hash_claim(self, claims: JSONDict) -> JWTValidationResult | None:
        """Validate constitutional hash claim if present in token payload."""
        claim_hash = claims.get("constitutional_hash")
        if claim_hash and claim_hash != CONSTITUTIONAL_HASH:
            return JWTValidationResult(
                valid=False,
                error="Constitutional hash mismatch in token",
                constitutional_compliant=False,
            )
        return None

    def _record_successful_validation(self, kid: str) -> None:
        """Track successful validation stats by key role."""
        if kid == self._current_kid:
            self._validation_stats["current_key_validations"] += 1
        else:
            self._validation_stats["previous_key_validations"] += 1

    def create_token(
        self,
        claims: JSONDict,
        expires_delta: timedelta | None = None,
        include_kid: bool = True,
    ) -> str | None:
        """
        Create a JWT token signed with the current key.

        Args:
            claims: Token claims
            expires_delta: Token expiration time
            include_kid: Whether to include kid in header

        Returns:
            JWT token string or None if no private key available
        """
        if not self._current_kid:
            logger.error("No current key loaded")
            return None

        private_key, _, _metadata = self._keys.get(self._current_kid, (None, None, None))
        if not private_key:
            logger.error("No private key available for token creation")
            return None

        # Set expiration
        if expires_delta is None:
            expires_delta = timedelta(hours=1)

        expire = datetime.now(UTC) + expires_delta

        # Build claims
        token_claims = {
            **claims,
            "exp": expire,
            "iat": datetime.now(UTC),
            "iss": "acgs2",
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        # Build header
        headers = {"alg": "RS256"}
        if include_kid:
            headers["kid"] = self._current_kid

        try:
            return jwt.encode(token_claims, private_key, algorithm="RS256", headers=headers)
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to create token ({type(e).__name__}): {e}")
            return None

    def get_jwks(self) -> JSONDict:
        """
        Get the JSON Web Key Set (JWKS) for public key discovery.

        Returns:
            JWKS document with all active public keys
        """
        import base64

        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        keys = []

        for kid, (_, public_key_bytes, metadata) in self._keys.items():
            # Skip expired keys
            if metadata.expires_at and metadata.expires_at < datetime.now(UTC):
                continue

            try:
                # Parse public key
                public_key = serialization.load_pem_public_key(
                    public_key_bytes, backend=default_backend()
                )

                if isinstance(public_key, rsa.RSAPublicKey):
                    numbers = public_key.public_numbers()

                    # Convert to JWK format
                    keys.append(
                        {
                            "kty": "RSA",
                            "kid": kid,
                            "use": "sig",
                            "alg": "RS256",
                            "n": base64.urlsafe_b64encode(
                                numbers.n.to_bytes(
                                    (numbers.n.bit_length() + 7) // 8, byteorder="big"
                                )
                            )
                            .decode()
                            .rstrip("="),
                            "e": base64.urlsafe_b64encode(
                                numbers.e.to_bytes(
                                    (numbers.e.bit_length() + 7) // 8, byteorder="big"
                                )
                            )
                            .decode()
                            .rstrip("="),
                        }
                    )
            except (ValueError, TypeError, AttributeError) as e:
                logger.warning(f"Failed to convert key {kid} to JWK ({type(e).__name__}): {e}")

        return {
            "keys": keys,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    def get_stats(self) -> JSONDict:
        """Get validation statistics."""
        return {
            **self._validation_stats,
            "current_kid": self._current_kid,
            "previous_kid": self._previous_kid,
            "dual_key_enabled": self.config.enabled and self._previous_kid is not None,
            "loaded_keys": list(self._keys.keys()),
            "last_refresh": (self._last_refresh.isoformat() if self._last_refresh else None),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    def get_health(self) -> JSONDict:
        """Get health status for monitoring endpoints."""
        now = datetime.now(UTC)

        # Check if previous key is about to expire
        previous_expires_soon = False
        if self._previous_kid:
            _, _, metadata = self._keys.get(self._previous_kid, (None, None, None))
            if metadata and metadata.expires_at:
                time_to_expiry = (metadata.expires_at - now).total_seconds()
                previous_expires_soon = time_to_expiry < 3600  # Less than 1 hour

        return {
            "status": "healthy" if self._current_kid else "degraded",
            "current_key_loaded": self._current_kid is not None,
            "dual_key_active": self._previous_kid is not None,
            "previous_key_expires_soon": previous_expires_soon,
            "key_version": self._current_kid,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


# Singleton instance for convenience
_validator: DualKeyJWTValidator | None = None


async def get_dual_key_validator(
    config: DualKeyConfig | None = None,
) -> DualKeyJWTValidator:
    """Get or create the dual-key JWT validator singleton."""
    global _validator
    if _validator is None:
        _validator = DualKeyJWTValidator(config=config)
        await _validator.load_keys_from_env()
    return _validator


__all__ = [
    "CONSTITUTIONAL_HASH",
    "DualKeyConfig",
    "DualKeyJWTValidator",
    "JWTValidationResult",
    "KeyMetadata",
    "get_dual_key_validator",
]
