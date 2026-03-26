"""
JWT Token Revocation Service
Constitutional Hash: 608508a9bd224290

Provides JWT token revocation using Redis blacklist with graceful degradation.
Follows session_manager.py pattern for blacklist implementation.

MACI Compliance:
- Executive role: Proposes token revocations
- Judicial role: Validates revocations (external)
- No self-validation (separation of powers)

Features:
- Token blacklisting with automatic TTL expiry
- User-level token revocation (logout all devices)
- Graceful degradation when Redis unavailable
- Comprehensive audit logging
- Constitutional hash validation

Usage:
    from src.core.shared.security.token_revocation import TokenRevocationService

    # Initialize with async Redis client
    service = TokenRevocationService(redis_client=redis)

    # Revoke single token
    await service.revoke_token(jti="token-uuid", expires_at=datetime_obj)

    # Check if token is revoked
    is_revoked = await service.is_token_revoked(jti="token-uuid")

    # Revoke all user tokens (logout all devices)
    count = await service.revoke_all_user_tokens(user_id="user123", expires_at=datetime_obj)
"""

import inspect
import os
from datetime import UTC, datetime

from src.core.shared.config import settings
from src.core.shared.config.runtime_environment import resolve_runtime_environment
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.errors.exceptions import ValidationError as ACGSValidationError
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

logger = get_logger(__name__)


def _runtime_environment() -> str:
    configured_env = getattr(settings, "env", None)
    # Trust an explicitly configured non-default env (e.g. "production") over
    # raw ENVIRONMENT env vars so that tests patching settings.env work correctly
    # even when the EAB test conftest sets ENVIRONMENT=test in os.environ.
    if configured_env and configured_env not in ("development",):
        return configured_env
    return resolve_runtime_environment(configured_env)


def _parse_bool_env(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    return None


class TokenRevocationService:
    """
    JWT Token Revocation Service with Redis blacklist.

    Implements token revocation using Redis with TTL-based expiry to prevent
    unbounded blacklist growth. Follows MACI separation of powers - this service
    proposes revocations but does not validate its own operations.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, redis_client: object | None = None):
        """
        Initialize token revocation service.

        Args:
            redis_client: Optional async Redis client for blacklist storage.
                         If None, service operates in degraded mode (logs only).
        """
        self._redis_client = redis_client
        self._use_redis = redis_client is not None

        if not self._use_redis:
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] TokenRevocationService initialized without Redis - "
                "revocations will be logged but not enforced"
            )

    async def close(self) -> None:
        """Close the underlying Redis client if one was initialized."""
        if self._redis_client is None:
            return

        try:
            close_method = getattr(self._redis_client, "aclose", None)
            if callable(close_method):
                await close_method()
            else:
                close_method = getattr(self._redis_client, "close", None)
                if callable(close_method):
                    result = close_method()
                    if inspect.isawaitable(result):
                        await result
        except Exception as e:
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] Failed to close token revocation Redis client: {e}"
            )
        finally:
            self._redis_client = None
            self._use_redis = False

    @staticmethod
    def _should_fail_open() -> bool:
        configured = _parse_bool_env(os.getenv("TOKEN_REVOCATION_FAIL_OPEN"))
        if configured is not None:
            return configured

        environment = _runtime_environment()
        return environment in {"development", "dev", "test", "testing", "local", "ci"}

    async def revoke_token(self, jti: str, expires_at: datetime) -> bool:
        """
        Revoke a JWT token by adding it to the Redis blacklist.

        The token is blacklisted with a TTL matching its expiration time,
        ensuring the blacklist doesn't grow unbounded as expired tokens
        are automatically removed by Redis.

        Args:
            jti: JWT ID (unique token identifier)
            expires_at: Token expiration timestamp (for TTL calculation)

        Returns:
            True if revocation succeeded, False if Redis unavailable or error

        Raises:
            ValueError: If jti is empty or invalid

        Example:
            success = await service.revoke_token(
                jti="550e8400-e29b-41d4-a716-446655440000",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
            )
        """
        # Input validation
        if not jti or not jti.strip():
            raise ACGSValidationError(message="JTI cannot be empty", error_code="TOKEN_JTI_EMPTY")

        if not self._use_redis:
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] Token revocation requested but Redis not configured: {jti[:8]}..."
            )
            return False

        try:
            # Calculate TTL from expires_at
            ttl = self._calculate_ttl(expires_at)

            # Add to blacklist with TTL
            blacklist_key = f"token_blacklist:{jti}"
            await self._redis_client.setex(blacklist_key, ttl, "revoked")

            logger.info(
                f"[{CONSTITUTIONAL_HASH}] Token revoked successfully: {jti[:8]}... (TTL: {ttl}s)"
            )
            return True

        except (ConnectionError, TimeoutError, OSError) as e:
            logger.error(
                f"[{CONSTITUTIONAL_HASH}] Failed to revoke token in Redis: {jti[:8]}... - {e}"
            )
            return False

        except Exception as e:
            logger.error(
                f"[{CONSTITUTIONAL_HASH}] Unexpected error revoking token: {jti[:8]}... - {e}"
            )
            return False

    async def is_token_revoked(self, jti: str) -> bool:
        """
        Check if a JWT token is in the revocation blacklist.

        This method fails open - if Redis is unavailable, it returns False
        to prevent blocking all requests. Monitoring should alert on Redis
        unavailability.

        Args:
            jti: JWT ID to check

        Returns:
            True if token is revoked, False if valid or Redis unavailable

        Raises:
            ValueError: If jti is empty or invalid

        Example:
            if await service.is_token_revoked(jti):
                raise UnauthorizedError("Token has been revoked")
        """
        # Input validation
        if not jti or not jti.strip():
            raise ACGSValidationError(message="JTI cannot be empty", error_code="TOKEN_JTI_EMPTY")

        if not self._use_redis:
            if self._should_fail_open():
                return False
            logger.error(
                f"[{CONSTITUTIONAL_HASH}] Redis unavailable for token revocation checks in strict mode; "
                "treating token as revoked"
            )
            return True

        try:
            blacklist_key = f"token_blacklist:{jti}"
            exists = await self._redis_client.exists(blacklist_key)
            return bool(exists)

        except (ConnectionError, TimeoutError, OSError) as e:
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] Failed to check token blacklist: {jti[:8]}... - {e}"
            )
            if self._should_fail_open():
                return False
            logger.error(
                f"[{CONSTITUTIONAL_HASH}] Token revocation backend unavailable in strict mode; "
                "treating token as revoked"
            )
            return True

        except Exception as e:
            logger.error(
                f"[{CONSTITUTIONAL_HASH}] Unexpected error checking token revocation: {jti[:8]}... - {e}"
            )
            return not self._should_fail_open()

    async def revoke_all_user_tokens(self, user_id: str, expires_at: datetime) -> int:
        """
        Revoke all tokens for a user by setting a user revocation timestamp.

        This is used for "logout all devices" functionality. object token issued
        before this timestamp will be considered revoked.

        Args:
            user_id: User identifier
            expires_at: Maximum expiration time for user's tokens (for TTL)

        Returns:
            Number of tokens revoked (1 = user revocation record set)

        Raises:
            ValueError: If user_id is empty or invalid

        Example:
            # User clicks "Logout all devices"
            count = await service.revoke_all_user_tokens(
                user_id="user_12345",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
            )
        """
        # Input validation
        if not user_id or not user_id.strip():
            raise ACGSValidationError(
                message="User ID cannot be empty", error_code="TOKEN_USER_ID_EMPTY"
            )

        if not self._use_redis:
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] User token revocation requested but Redis not configured: {user_id}"
            )
            return 0

        try:
            # Calculate TTL from expires_at
            ttl = self._calculate_ttl(expires_at)

            # Set user revocation timestamp
            user_revoked_key = f"user_revoked:{user_id}"
            revocation_timestamp = datetime.now(UTC).isoformat()

            await self._redis_client.setex(user_revoked_key, ttl, revocation_timestamp)

            logger.info(
                f"[{CONSTITUTIONAL_HASH}] All tokens revoked for user: {user_id} "
                f"(timestamp: {revocation_timestamp})"
            )

            # Return 1 to indicate the user revocation record was set
            return 1

        except (ConnectionError, TimeoutError, OSError) as e:
            logger.error(
                f"[{CONSTITUTIONAL_HASH}] Failed to revoke user tokens in Redis: {user_id} - {e}"
            )
            return 0

        except Exception as e:
            logger.error(
                f"[{CONSTITUTIONAL_HASH}] Unexpected error revoking user tokens: {user_id} - {e}"
            )
            return 0

    def _calculate_ttl(self, expires_at: datetime) -> int:
        """
        Calculate TTL in seconds from expiration timestamp.

        Args:
            expires_at: Token expiration timestamp

        Returns:
            TTL in seconds (minimum 1, maximum matches token expiry)
        """
        now = datetime.now(UTC)

        # Handle timezone-naive datetimes by assuming timezone.utc
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        # Calculate difference in seconds
        delta = (expires_at - now).total_seconds()

        # Ensure minimum TTL of 1 second (even for expired tokens)
        # This allows brief blacklisting of already-expired tokens
        ttl = max(1, int(delta))

        return ttl

    async def is_user_revoked(self, user_id: str, token_issued_at: datetime) -> bool:
        """
        Check if a user's tokens have been revoked after a specific time.

        This checks if the user clicked "logout all devices" after the token
        was issued, which would invalidate the token.

        Args:
            user_id: User identifier
            token_issued_at: When the token was issued (from JWT 'iat' claim)

        Returns:
            True if user tokens were revoked after token issuance, False otherwise

        Example:
            # In token validation middleware
            if await service.is_user_revoked(user_id, token_iat):
                raise UnauthorizedError("User has logged out from all devices")
        """
        if not self._use_redis:
            return self._strict_mode_default_on_missing_redis()

        try:
            revocation_timestamp_str = await self._get_user_revocation_timestamp(user_id)
            if not revocation_timestamp_str:
                return False

            revocation_timestamp = self._parse_revocation_timestamp(revocation_timestamp_str)
            normalized_token_iat = self._ensure_utc_datetime(token_issued_at)
            normalized_revoked_at = self._ensure_utc_datetime(revocation_timestamp)
            return normalized_token_iat < normalized_revoked_at

        except (ConnectionError, TimeoutError, OSError) as e:
            return self._handle_revocation_backend_error(user_id, e)
        except (ValueError, TypeError) as e:
            logger.error(
                f"[{CONSTITUTIONAL_HASH}] Invalid revocation timestamp for user: {user_id} - {e}"
            )
            return False
        except Exception as e:
            logger.error(
                f"[{CONSTITUTIONAL_HASH}] Unexpected error checking user revocation: {user_id} - {e}"
            )
            return not self._should_fail_open()

    def _strict_mode_default_on_missing_redis(self) -> bool:
        """Return revocation decision when Redis is unavailable."""
        if self._should_fail_open():
            return False
        logger.error(
            f"[{CONSTITUTIONAL_HASH}] Redis unavailable for user revocation checks in strict mode; "
            "treating user as revoked"
        )
        return True

    async def _get_user_revocation_timestamp(self, user_id: str) -> str | bytes | None:
        """Fetch user-level revocation timestamp from Redis."""
        user_revoked_key = f"user_revoked:{user_id}"
        return await self._redis_client.get(user_revoked_key)

    def _parse_revocation_timestamp(self, revocation_timestamp: str | bytes) -> datetime:
        """Parse stored revocation timestamp payload into datetime."""
        if isinstance(revocation_timestamp, bytes):
            revocation_timestamp = revocation_timestamp.decode("utf-8")
        return datetime.fromisoformat(revocation_timestamp)

    def _ensure_utc_datetime(self, value: datetime) -> datetime:
        """Normalize datetimes to UTC for safe comparisons."""
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    def _handle_revocation_backend_error(
        self,
        user_id: str,
        error: ConnectionError | TimeoutError | OSError,
    ) -> bool:
        """Handle Redis availability errors for user revocation checks."""
        logger.warning(
            f"[{CONSTITUTIONAL_HASH}] Failed to check user revocation: {user_id} - {error}"
        )
        if self._should_fail_open():
            return False
        logger.error(
            f"[{CONSTITUTIONAL_HASH}] User revocation backend unavailable in strict mode; "
            "treating user as revoked"
        )
        return True

    async def get_revocation_stats(self) -> JSONDict:
        """
        Get statistics about token revocations.

        Returns:
            Dictionary containing revocation metrics

        Example:
            stats = await service.get_revocation_stats()
            logger.info("Active blacklist entries: %d", stats['blacklist_count'])
        """
        if not self._use_redis:
            return {
                "redis_available": False,
                "blacklist_count": 0,
                "user_revocations": 0,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }

        try:
            # Count blacklisted tokens via non-blocking SCAN
            blacklist_count = 0
            async for _ in self._redis_client.scan_iter("token_blacklist:*", count=100):
                blacklist_count += 1

            # Count user revocations via non-blocking SCAN
            user_revocations = 0
            async for _ in self._redis_client.scan_iter("user_revoked:*", count=100):
                user_revocations += 1

            return {
                "redis_available": True,
                "blacklist_count": blacklist_count,
                "user_revocations": user_revocations,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }

        except (ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to get revocation stats: {e}")
            return {
                "redis_available": False,
                "blacklist_count": 0,
                "user_revocations": 0,
                "error": str(e),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }


# Convenience function for service initialization
async def create_token_revocation_service(redis_url: str | None = None) -> TokenRevocationService:
    """
    Create a TokenRevocationService with Redis client.

    Args:
        redis_url: Optional Redis connection URL. If None, uses environment variable.

    Returns:
        Configured TokenRevocationService instance

    Example:
        service = await create_token_revocation_service("redis://localhost:6379")
    """
    if not redis_url:
        import os

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")

    try:
        # Try to import async Redis
        try:
            import redis.asyncio as redis_async

            redis_client = await redis_async.from_url(redis_url)
        except ImportError:
            # Fallback to sync Redis (for compatibility)
            import redis

            redis_client = redis.from_url(redis_url)

        # Test connection
        await redis_client.ping()

        try:
            from urllib.parse import urlparse

            parsed = urlparse(redis_url)
            safe_url = f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 6379}"
        except Exception:
            safe_url = "<redis>"
        logger.info(
            "[%s] TokenRevocationService initialized with Redis: %s",
            CONSTITUTIONAL_HASH,
            safe_url,
        )
        return TokenRevocationService(redis_client=redis_client)

    except Exception as e:
        logger.error(
            f"[{CONSTITUTIONAL_HASH}] Failed to connect to Redis: {e} - "
            "TokenRevocationService will operate in degraded mode"
        )
        return TokenRevocationService(redis_client=None)
