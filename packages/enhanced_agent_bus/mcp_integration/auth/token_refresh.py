"""
Token Refresh Manager for MCP Authentication.

Constitutional Hash: 608508a9bd224290
MACI Role: JUDICIAL

Provides automatic token refresh:
- Background refresh before expiration
- Refresh retry with backoff
- Token rotation coordination
- Refresh failure handling
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
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

from .oauth2_provider import OAuth2Provider, OAuth2Token

logger = get_logger(__name__)
_TOKEN_REFRESH_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class RefreshStatus(str, Enum):
    """Status of a refresh operation."""

    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    SKIPPED = "skipped"
    NOT_NEEDED = "not_needed"
    NO_REFRESH_TOKEN = "no_refresh_token"


@dataclass
class RefreshConfig:
    """Configuration for token refresh."""

    # Timing
    refresh_threshold_seconds: int = 300  # Refresh 5 min before expiry
    check_interval_seconds: int = 60  # Check every minute

    # Retry
    max_retries: int = 3
    initial_retry_delay_seconds: float = 1.0
    max_retry_delay_seconds: float = 30.0
    retry_backoff_multiplier: float = 2.0

    # Behavior
    refresh_on_error: bool = True
    synchronous_refresh_enabled: bool = True
    background_refresh_enabled: bool = True

    # Limits
    max_concurrent_refreshes: int = 10


@dataclass
class RefreshResult:
    """Result of a token refresh operation."""

    token_id: str
    status: RefreshStatus
    old_token: OAuth2Token | None = None
    new_token: OAuth2Token | None = None
    error: str | None = None
    retry_count: int = 0
    duration_ms: float = 0.0
    refreshed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "token_id": self.token_id,
            "status": self.status.value,
            "error": self.error,
            "retry_count": self.retry_count,
            "duration_ms": self.duration_ms,
            "refreshed_at": self.refreshed_at.isoformat(),
            "has_new_token": self.new_token is not None,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class ManagedToken:
    """A token managed for automatic refresh."""

    token_id: str
    token: OAuth2Token
    provider: OAuth2Provider
    cache_key: str | None = None
    on_refresh: Callable[[OAuth2Token, OAuth2Token], Awaitable[None]] | None = None
    on_error: Callable[[str, Exception], Awaitable[None]] | None = None
    last_refresh_attempt: datetime | None = None
    refresh_count: int = 0
    error_count: int = 0
    metadata: JSONDict = field(default_factory=dict)


class TokenRefresher:
    """
    Automatic token refresh manager.

    Features:
    - Background refresh before expiration
    - Configurable retry with exponential backoff
    - Callback hooks for refresh events
    - Concurrent refresh limiting

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, config: RefreshConfig | None = None):
        self.config = config or RefreshConfig()

        # Managed tokens
        self._managed_tokens: dict[str, ManagedToken] = {}

        # Background task
        self._refresh_task: asyncio.Task | None = None
        self._running = False
        self._refresh_semaphore = asyncio.Semaphore(self.config.max_concurrent_refreshes)

        # Lock
        self._lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "tokens_registered": 0,
            "refreshes_attempted": 0,
            "refreshes_successful": 0,
            "refreshes_failed": 0,
            "background_checks": 0,
        }

    async def start(self) -> None:
        """Start background refresh monitoring."""
        if self._running:
            return

        self._running = True

        if self.config.background_refresh_enabled:
            self._refresh_task = asyncio.create_task(
                self._background_refresh_loop(),
                name="token_refresh_background",
            )
            logger.info("Token refresh background monitoring started")

    async def stop(self) -> None:
        """Stop background refresh monitoring."""
        self._running = False

        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None

        logger.info("Token refresh background monitoring stopped")

    async def register_token(
        self,
        token_id: str,
        token: OAuth2Token,
        provider: OAuth2Provider,
        cache_key: str | None = None,
        on_refresh: Callable[[OAuth2Token, OAuth2Token], Awaitable[None]] | None = None,
        on_error: Callable[[str, Exception], Awaitable[None]] | None = None,
        metadata: JSONDict | None = None,
    ) -> None:
        """
        Register a token for automatic refresh.

        Args:
            token_id: Unique identifier for the token
            token: The OAuth2 token
            provider: OAuth2 provider for refresh
            cache_key: Optional cache key
            on_refresh: Callback when token is refreshed
            on_error: Callback on refresh error
            metadata: Additional metadata
        """
        async with self._lock:
            self._managed_tokens[token_id] = ManagedToken(
                token_id=token_id,
                token=token,
                provider=provider,
                cache_key=cache_key,
                on_refresh=on_refresh,
                on_error=on_error,
                metadata=metadata or {},
            )

        self._stats["tokens_registered"] += 1
        logger.debug(f"Registered token for refresh: {token_id}")

    async def unregister_token(self, token_id: str) -> bool:
        """Unregister a token from automatic refresh."""
        async with self._lock:
            if token_id in self._managed_tokens:
                del self._managed_tokens[token_id]
                logger.debug(f"Unregistered token: {token_id}")
                return True
        return False

    async def refresh_token(
        self,
        token_id: str,
        force: bool = False,
    ) -> RefreshResult:
        """
        Refresh a specific token.

        Args:
            token_id: Token to refresh
            force: Force refresh even if not needed

        Returns:
            RefreshResult
        """
        start_time = datetime.now(UTC)
        self._stats["refreshes_attempted"] += 1

        async with self._lock:
            managed = self._managed_tokens.get(token_id)

        if not managed:
            return RefreshResult(
                token_id=token_id,
                status=RefreshStatus.FAILED,
                error="Token not registered",
            )

        token = managed.token

        # Check if refresh needed
        if not force:
            if not token.refresh_token:
                return RefreshResult(
                    token_id=token_id,
                    status=RefreshStatus.NO_REFRESH_TOKEN,
                )

            if not token.needs_refresh(self.config.refresh_threshold_seconds):
                return RefreshResult(
                    token_id=token_id,
                    status=RefreshStatus.NOT_NEEDED,
                )

        # Acquire semaphore for concurrent limiting
        async with self._refresh_semaphore:
            result = await self._do_refresh(managed)

        # Calculate duration
        end_time = datetime.now(UTC)
        result.duration_ms = (end_time - start_time).total_seconds() * 1000

        return result

    async def _do_refresh(self, managed: ManagedToken) -> RefreshResult:
        """Perform the actual refresh with retries."""
        result = RefreshResult(
            token_id=managed.token_id,
            status=RefreshStatus.PENDING,
            old_token=managed.token,
        )

        delay = self.config.initial_retry_delay_seconds

        for attempt in range(self.config.max_retries + 1):
            result.retry_count = attempt

            try:
                new_token = await managed.provider.refresh_token(
                    managed.token,
                    cache_key=managed.cache_key,
                )

                if new_token:
                    # Success
                    result.status = RefreshStatus.SUCCESS
                    result.new_token = new_token

                    # Update managed token
                    async with self._lock:
                        managed.token = new_token
                        managed.refresh_count += 1
                        managed.last_refresh_attempt = datetime.now(UTC)

                    self._stats["refreshes_successful"] += 1

                    # Call callback
                    if managed.on_refresh:
                        try:
                            await managed.on_refresh(managed.token, new_token)
                        except _TOKEN_REFRESH_OPERATION_ERRORS as e:
                            logger.warning(f"Refresh callback error: {e}")

                    logger.info(f"Token refreshed: {managed.token_id}")
                    return result

                else:
                    result.error = "Refresh returned no token"

            except _TOKEN_REFRESH_OPERATION_ERRORS as e:
                result.error = str(e)
                logger.warning(f"Token refresh attempt {attempt + 1} failed: {e}")

            # Retry delay
            if attempt < self.config.max_retries:
                await asyncio.sleep(delay)
                delay = min(
                    delay * self.config.retry_backoff_multiplier,
                    self.config.max_retry_delay_seconds,
                )

        # All retries exhausted
        result.status = RefreshStatus.FAILED
        self._stats["refreshes_failed"] += 1

        # Update error count
        async with self._lock:
            managed.error_count += 1
            managed.last_refresh_attempt = datetime.now(UTC)

        # Call error callback
        if managed.on_error:
            try:
                await managed.on_error(managed.token_id, Exception(result.error))
            except _TOKEN_REFRESH_OPERATION_ERRORS as e:
                logger.warning(f"Error callback failed: {e}")

        logger.error(
            f"Token refresh failed after {result.retry_count + 1} attempts: {managed.token_id}"
        )

        return result

    async def _background_refresh_loop(self) -> None:
        """Background loop to check and refresh tokens."""
        while self._running:
            try:
                self._stats["background_checks"] += 1
                await self._check_all_tokens()
            except asyncio.CancelledError:
                break
            except _TOKEN_REFRESH_OPERATION_ERRORS as e:
                logger.error(f"Background refresh error: {e}")

            await asyncio.sleep(self.config.check_interval_seconds)

    async def _check_all_tokens(self) -> None:
        """Check all tokens and refresh if needed."""
        async with self._lock:
            tokens_to_check = list(self._managed_tokens.items())

        refresh_tasks = []

        for token_id, managed in tokens_to_check:
            # Check if refresh needed
            if managed.token.needs_refresh(self.config.refresh_threshold_seconds):
                task = asyncio.create_task(
                    self.refresh_token(token_id),
                    name=f"refresh_{token_id}",
                )
                refresh_tasks.append(task)

        if refresh_tasks:
            await asyncio.gather(*refresh_tasks, return_exceptions=True)

    async def refresh_all(self, force: bool = False) -> list[RefreshResult]:
        """
        Refresh all managed tokens.

        Args:
            force: Force refresh even if not needed

        Returns:
            List of RefreshResults
        """
        async with self._lock:
            token_ids = list(self._managed_tokens.keys())

        tasks = [self.refresh_token(token_id, force=force) for token_id in token_ids]

        return await asyncio.gather(*tasks)

    def get_token(self, token_id: str) -> OAuth2Token | None:
        """Get the current token for a token ID."""
        managed = self._managed_tokens.get(token_id)
        return managed.token if managed else None

    def get_managed_token(self, token_id: str) -> ManagedToken | None:
        """Get managed token info."""
        return self._managed_tokens.get(token_id)

    def list_tokens(self) -> list[JSONDict]:
        """List all managed tokens."""
        result = []
        for token_id, managed in self._managed_tokens.items():
            result.append(
                {
                    "token_id": token_id,
                    "is_expired": managed.token.is_expired(),
                    "needs_refresh": managed.token.needs_refresh(
                        self.config.refresh_threshold_seconds
                    ),
                    "has_refresh_token": managed.token.refresh_token is not None,
                    "refresh_count": managed.refresh_count,
                    "error_count": managed.error_count,
                    "last_refresh_attempt": (
                        managed.last_refresh_attempt.isoformat()
                        if managed.last_refresh_attempt
                        else None
                    ),
                    "expires_at": (
                        managed.token.expires_at.isoformat() if managed.token.expires_at else None
                    ),
                }
            )
        return result

    def get_stats(self) -> JSONDict:
        """Get refresher statistics."""
        return {
            **self._stats,
            "managed_tokens": len(self._managed_tokens),
            "running": self._running,
            "config": {
                "refresh_threshold_seconds": self.config.refresh_threshold_seconds,
                "check_interval_seconds": self.config.check_interval_seconds,
                "max_retries": self.config.max_retries,
                "background_enabled": self.config.background_refresh_enabled,
            },
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
