"""
OAuth2 State Manager Service
Constitutional Hash: 608508a9bd224290

Redis-backed OAuth2 state parameter management with enhanced security:
- High-entropy state generation (256-bit)
- Client IP and user agent binding (prevents CSRF token theft)
- 5-minute TTL with automatic cleanup
- One-time use enforcement
- Graceful degradation without Redis

MACI Compliance:
- Executive role: Proposes state creation/validation
- Judicial role: Validates OAuth flows (external)
- No self-validation (separation of powers)

Security Features:
- Prevents CSRF attacks via state parameter
- Prevents replay attacks via one-time use
- Prevents session hijacking via client binding
- Constitutional hash validation

Usage:
    from src.core.shared.security.oauth_state_manager import OAuth2StateManager

    # Initialize with async Redis client
    manager = OAuth2StateManager(redis_client=redis)

    # Create state before OAuth redirect
    state = await manager.create_state(
        client_ip=request.client.host,
        user_agent=request.headers.get("user-agent"),
        provider="okta",
        callback_url="/sso/oidc/callback"
    )

    # Validate state in callback
    stored_data = await manager.validate_state(
        state=state,
        client_ip=request.client.host,
        user_agent=request.headers.get("user-agent")
    )
"""

import json
import os
import secrets
from datetime import UTC, datetime, timedelta

from src.core.shared.config import settings
from src.core.shared.config.runtime_environment import resolve_runtime_environment
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.errors.exceptions import ACGSBaseError
from src.core.shared.errors.exceptions import ValidationError as ACGSValidationError
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)
_NON_PRODUCTION_ENVS = frozenset({"development", "dev", "test", "testing", "local", "ci"})


def _runtime_environment() -> str:
    configured_env = getattr(settings, "env", None)
    if configured_env and configured_env not in ("development",):
        return configured_env
    return resolve_runtime_environment(configured_env)


def _parse_bool_env(value: str | None) -> bool:
    return (value or "").strip().lower() in {"true", "1", "yes", "on"}


def _allow_degraded_mode_without_redis() -> bool:
    if _parse_bool_env(os.getenv("OAUTH_STATE_ALLOW_DEGRADED_MODE")):
        return True
    return _runtime_environment() in _NON_PRODUCTION_ENVS


class OAuth2StateError(ACGSBaseError):
    """Base exception for OAuth2 state errors (Q-H4 migration)."""

    http_status_code = 400
    error_code = "OAUTH2_STATE_ERROR"


class OAuth2StateNotFoundError(OAuth2StateError):
    """Raised when state is not found in Redis."""

    pass


class OAuth2StateExpiredError(OAuth2StateError):
    """Raised when state has expired (> 5 minutes)."""

    pass


class OAuth2StateValidationError(OAuth2StateError):
    """Raised when state validation fails (IP/UA mismatch, hash mismatch)."""

    pass


class OAuth2StateManager:
    """
    OAuth2 State Manager with Redis-backed storage.

    Implements secure OAuth2 state parameter management with:
    - High-entropy generation (256-bit via secrets.token_urlsafe)
    - Client binding (IP + user agent) to prevent CSRF token theft
    - TTL-based expiry (5 minutes)
    - One-time use enforcement (state invalidated after validation)
    - Constitutional hash validation
    - Graceful degradation without Redis

    Constitutional Hash: 608508a9bd224290
    """

    # State TTL in seconds (5 minutes)
    STATE_TTL_SECONDS = 300

    # Minimum entropy check (256 bits = 32 bytes)
    MIN_ENTROPY_BYTES = 32

    def __init__(self, redis_client: object | None = None):
        """
        Initialize OAuth2StateManager.

        Args:
            redis_client: Optional async Redis client for state storage.
                         If None, service operates in degraded mode (logs only).
        """
        self._redis_client = redis_client
        self._use_redis = redis_client is not None

        if not self._use_redis:
            if not _allow_degraded_mode_without_redis():
                raise OSError(
                    "Redis is required for OAuth2StateManager in production-like environments. "
                    f"Current environment: {_runtime_environment()!r}"
                )
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] OAuth2StateManager initialized without Redis - "
                "state validation will fail (degraded mode)"
            )

    async def create_state(
        self,
        client_ip: str,
        user_agent: str,
        provider: str,
        callback_url: str,
    ) -> str:
        """
        Generate and store OAuth2 state parameter with client binding.

        The state is stored in Redis with:
        - Key: oauth:state:{state_value}
        - Value: JSON with {provider, callback_url, client_ip, user_agent, created_at, constitutional_hash}
        - TTL: 5 minutes

        Args:
            client_ip: Client IP address for binding
            user_agent: Client user agent for binding
            provider: OAuth provider name (e.g., "okta", "auth0")
            callback_url: OAuth callback URL

        Returns:
            URL-safe base64 encoded state string (256-bit entropy)

        Raises:
            ValueError: If any parameter is empty
            ConnectionError: If Redis is unavailable (not in degraded mode)

        Example:
            state = await manager.create_state(
                client_ip="192.168.1.100",
                user_agent="Mozilla/5.0 Chrome/120.0",
                provider="okta",
                callback_url="/sso/oidc/callback"
            )
        """
        # Input validation
        if not client_ip or not client_ip.strip():
            raise ACGSValidationError(
                message="client_ip cannot be empty", error_code="OAUTH_CLIENT_IP_EMPTY"
            )
        if not user_agent or not user_agent.strip():
            raise ACGSValidationError(
                message="user_agent cannot be empty", error_code="OAUTH_USER_AGENT_EMPTY"
            )
        if not provider or not provider.strip():
            raise ACGSValidationError(
                message="provider cannot be empty", error_code="OAUTH_PROVIDER_EMPTY"
            )
        if not callback_url or not callback_url.strip():
            raise ACGSValidationError(
                message="callback_url cannot be empty", error_code="OAUTH_CALLBACK_URL_EMPTY"
            )

        # Generate high-entropy state (256 bits)
        # secrets.token_urlsafe(32) generates 32 bytes = 256 bits
        # Base64 encoding: 32 bytes -> ~43 characters
        state = secrets.token_urlsafe(self.MIN_ENTROPY_BYTES)

        # Create state metadata
        state_data = {
            "provider": provider,
            "callback_url": callback_url,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "created_at": datetime.now(UTC).isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        # Store in Redis with TTL
        if self._use_redis:
            try:
                redis_key = f"oauth:state:{state}"
                await self._redis_client.set(
                    redis_key,
                    json.dumps(state_data),
                    ex=self.STATE_TTL_SECONDS,
                )

                logger.info(
                    f"[{CONSTITUTIONAL_HASH}] OAuth2 state created: "
                    f"provider={provider}, ip={client_ip}"
                )
            except (ConnectionError, OSError) as e:
                logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to store OAuth2 state in Redis: {e}")
                raise ConnectionError(f"Redis unavailable: {e}") from e
        else:
            # Degraded mode: log only
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] OAuth2 state created in degraded mode "
                f"(not stored): provider={provider}"
            )

        return state

    async def validate_state(
        self,
        state: str,
        client_ip: str,
        user_agent: str,
    ) -> dict:
        """
        Validate OAuth2 state and return stored metadata.

        This method:
        1. Retrieves state from Redis
        2. Validates client IP matches (prevents CSRF token theft)
        3. Validates user agent matches (prevents session hijacking)
        4. Validates state hasn't expired (< 5 minutes)
        5. Validates constitutional hash
        6. Invalidates state (one-time use)

        Args:
            state: OAuth2 state parameter from callback
            client_ip: Current client IP address
            user_agent: Current client user agent

        Returns:
            Dictionary with stored metadata (provider, callback_url, etc.)

        Raises:
            ValueError: If state is empty
            OAuth2StateNotFoundError: If state not found in Redis or expired by TTL
            OAuth2StateExpiredError: If state created > 5 minutes ago
            OAuth2StateValidationError: If IP/UA mismatch or hash mismatch
            ConnectionError: If Redis connection fails

        Example:
            try:
                data = await manager.validate_state(
                    state=state_from_callback,
                    client_ip=request.client.host,
                    user_agent=request.headers.get("user-agent")
                )
                provider = data["provider"]
                callback_url = data["callback_url"]
            except OAuth2StateValidationError as e:
                logger.warning(f"OAuth2 state validation failed: {e}")
                raise HTTPException(status_code=401, detail="Invalid state")
        """
        self._validate_state_input(state)
        redis_key = self._build_state_redis_key(state)
        stored_json = await self._load_state_json(redis_key, state)
        stored_data = self._parse_state_json(stored_json)

        self._validate_constitutional_hash(stored_data)
        self._validate_state_expiry(stored_data)
        self._validate_client_binding(stored_data, client_ip, user_agent)

        await self._invalidate_after_validation(redis_key, stored_data, client_ip)
        return stored_data

    def _validate_state_input(self, state: str) -> None:
        """Validate state token input before Redis lookup."""
        if not state or not state.strip():
            raise ACGSValidationError(
                message="state cannot be empty", error_code="OAUTH_STATE_EMPTY"
            )

    def _build_state_redis_key(self, state: str) -> str:
        """Build Redis key for OAuth state payload."""
        if not self._use_redis:
            logger.error(
                f"[{CONSTITUTIONAL_HASH}] OAuth2 state validation failed: Redis unavailable"
            )
            raise OAuth2StateNotFoundError("Redis unavailable")
        return f"oauth:state:{state}"

    async def _load_state_json(self, redis_key: str, state: str) -> str:
        """Load state payload JSON from Redis."""
        try:
            stored_json = await self._redis_client.get(redis_key)
        except (ConnectionError, OSError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Redis connection error during validation: {e}")
            raise ConnectionError(f"Redis unavailable: {e}") from e

        if not stored_json:
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] OAuth2 state not found or expired: {state[:16]}..."
            )
            raise OAuth2StateNotFoundError("State not found or expired")

        if isinstance(stored_json, bytes):
            return stored_json.decode("utf-8")
        return stored_json

    def _parse_state_json(self, stored_json: str) -> dict:
        """Parse stored JSON payload for OAuth state."""
        try:
            return json.loads(stored_json)
        except json.JSONDecodeError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Invalid JSON in Redis state: {e}")
            raise OAuth2StateValidationError("Invalid state data") from e

    def _validate_constitutional_hash(self, stored_data: dict) -> None:
        """Validate constitutional hash integrity for stored state."""
        stored_hash = stored_data.get("constitutional_hash")
        if not stored_hash:
            logger.error(f"[{CONSTITUTIONAL_HASH}] State missing constitutional hash")
            raise OAuth2StateValidationError("Constitutional hash missing")

        if stored_hash != CONSTITUTIONAL_HASH:
            logger.error(
                f"[{CONSTITUTIONAL_HASH}] State hash mismatch: "
                f"expected={CONSTITUTIONAL_HASH}, got={stored_hash}"
            )
            raise OAuth2StateValidationError("Constitutional hash mismatch")

    def _validate_state_expiry(self, stored_data: dict) -> None:
        """Validate state TTL in case Redis expiration has not yet fired."""
        created_at_str = stored_data.get("created_at")
        if not created_at_str:
            return

        created_at = datetime.fromisoformat(created_at_str)
        age = datetime.now(UTC) - created_at
        if age > timedelta(seconds=self.STATE_TTL_SECONDS):
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] OAuth2 state expired: age={age.total_seconds():.1f}s"
            )
            raise OAuth2StateExpiredError("State has expired")

    def _validate_client_binding(self, stored_data: dict, client_ip: str, user_agent: str) -> None:
        """Validate IP and user-agent bindings to prevent token theft and replay."""
        stored_ip = stored_data.get("client_ip")
        if stored_ip != client_ip:
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] OAuth2 state IP mismatch: "
                f"stored={stored_ip}, current={client_ip}"
            )
            raise OAuth2StateValidationError("Client IP mismatch")

        stored_ua = stored_data.get("user_agent")
        if stored_ua != user_agent:
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] OAuth2 state user agent mismatch: "
                f"stored={stored_ua[:50]}, current={user_agent[:50]}"
            )
            raise OAuth2StateValidationError("User agent mismatch")

    async def _invalidate_after_validation(
        self,
        redis_key: str,
        stored_data: dict,
        client_ip: str,
    ) -> None:
        """Invalidate state after successful validation (one-time use)."""
        try:
            await self._redis_client.delete(redis_key)
            logger.info(
                f"[{CONSTITUTIONAL_HASH}] OAuth2 state validated and invalidated: "
                f"provider={stored_data.get('provider')}, ip={client_ip}"
            )
        except (ConnectionError, OSError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to delete state after validation: {e}")

    async def invalidate_state(self, state: str) -> bool:
        """
        Manually invalidate a state parameter.

        This is useful for:
        - Manual cleanup on errors
        - Administrative invalidation

        Args:
            state: State parameter to invalidate

        Returns:
            True if state was found and deleted, False if not found

        Example:
            success = await manager.invalidate_state("stale_state_12345")
        """
        if not self._use_redis:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Cannot invalidate state: Redis unavailable")
            return False

        redis_key = f"oauth:state:{state}"
        try:
            deleted_count = await self._redis_client.delete(redis_key)
            success = deleted_count > 0

            if success:
                logger.info(
                    f"[{CONSTITUTIONAL_HASH}] OAuth2 state manually invalidated: {state[:16]}..."
                )
            else:
                logger.debug(
                    f"[{CONSTITUTIONAL_HASH}] OAuth2 state not found for invalidation: {state[:16]}..."
                )

            return success
        except (ConnectionError, OSError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to invalidate state: {e}")
            return False
