"""
ACGS-2 Enhanced Agent Bus - PQC Enforcement Mode Config Service
Constitutional Hash: 608508a9bd224290

Manages the PQC enforcement mode (strict | permissive) with:
- Redis as primary durable store (hash key pqc:enforcement_config)
- PostgreSQL as fallback durable store
- Local in-process cache with 30-second TTL
- Redis pub/sub on pqc:enforcement_mode for cross-instance cache invalidation
- Fail-safe: returns 'strict' when both backends are unavailable
"""

from __future__ import annotations

import time
from typing import Any, Literal

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REDIS_CONFIG_KEY = "pqc:enforcement_config"
REDIS_CHANNEL = "pqc:enforcement_mode"
DEFAULT_MODE: Literal["strict", "permissive"] = "permissive"
FAILSAFE_MODE: Literal["strict", "permissive"] = "strict"
DEFAULT_CACHE_TTL_SECONDS = 30

_VALID_MODES = frozenset({"strict", "permissive"})


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class StorageUnavailableError(Exception):
    """Raised when enforcement mode cannot be persisted (both Redis and PG down)."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class EnforcementModeConfigService:
    """
    Manages the global (and optionally per-tenant) PQC enforcement mode.

    get_mode() priority:
      1. Local in-process cache (TTL = cache_ttl_seconds)
      2. Redis hash pqc:enforcement_config (hget field=scope)
      3. PostgreSQL table config row (scope column)
      4. Fail-safe: return 'strict'

    set_mode() writes to Redis, PostgreSQL, and publishes to the pub/sub channel.

    Cache invalidation via _invalidate_cache(scope) — call this when the
    pub/sub subscription delivers a message on REDIS_CHANNEL.
    """

    def __init__(
        self,
        redis_client: Any,
        pg_conn: Any | None = None,
        cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        self._redis = redis_client
        self._pg = pg_conn
        self._cache: dict[str, tuple[Literal["strict", "permissive"], float]] = {}
        self._cache_ttl = cache_ttl_seconds

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_mode(self, scope: str = "global") -> Literal["strict", "permissive"]:
        """Return the current enforcement mode for the given scope.

        Uses a local cache with TTL; falls back through Redis → PostgreSQL → 'strict'.
        """
        # 1. Local cache
        cached = self._cache.get(scope)
        if cached is not None:
            mode, ts = cached
            if time.monotonic() - ts < self._cache_ttl:
                logger.debug(
                    "PQC enforcement mode served from local cache",
                    scope=scope,
                    mode=mode,
                )
                return mode

        # 2. Redis
        try:
            raw = await self._redis.hget(REDIS_CONFIG_KEY, scope)
            if raw is not None:
                decoded = raw if isinstance(raw, str) else raw.decode()
                if decoded in _VALID_MODES:
                    mode_val: Literal["strict", "permissive"] = decoded  # type: ignore[assignment]
                    self._cache[scope] = (mode_val, time.monotonic())
                    logger.info(
                        "PQC enforcement mode read from Redis",
                        scope=scope,
                        mode=mode_val,
                    )
                    return mode_val
            # Key exists but value missing or invalid → treat as default
            logger.debug(
                "No PQC enforcement config in Redis; returning default",
                scope=scope,
                default=DEFAULT_MODE,
            )
            self._cache[scope] = (DEFAULT_MODE, time.monotonic())
            return DEFAULT_MODE

        except ConnectionError as redis_err:
            logger.warning(
                "Redis unavailable for PQC enforcement config read; trying PostgreSQL",
                scope=scope,
                error=str(redis_err),
            )

        # 3. PostgreSQL fallback
        if self._pg is not None:
            try:
                row = await self._pg.fetchrow(
                    "SELECT mode FROM pqc_enforcement_config WHERE scope = $1 LIMIT 1",
                    scope,
                )
                if row is not None and row["mode"] in _VALID_MODES:
                    pg_mode: Literal["strict", "permissive"] = row["mode"]  # type: ignore[assignment]
                    logger.info(
                        "PQC enforcement mode read from PostgreSQL fallback",
                        scope=scope,
                        mode=pg_mode,
                    )
                    return pg_mode
            except (ConnectionError, TimeoutError, OSError, ValueError) as pg_err:
                logger.error(
                    "PostgreSQL fallback also failed for PQC enforcement config",
                    scope=scope,
                    error=str(pg_err),
                )

        # 4. Fail-safe
        logger.error(
            "Both Redis and PostgreSQL unavailable; returning fail-safe strict mode",
            scope=scope,
        )
        return FAILSAFE_MODE

    async def set_mode(
        self,
        mode: Literal["strict", "permissive"],
        scope: str = "global",
        activated_by: str = "unknown",
    ) -> None:
        """Persist the enforcement mode to Redis and PostgreSQL and publish a change event.

        Raises:
            StorageUnavailableError: If neither Redis nor PostgreSQL can be written.
        """
        if mode not in _VALID_MODES:
            raise ValueError(f"Invalid enforcement mode: {mode!r}")

        redis_ok = False
        pg_ok = False

        # Write to Redis
        try:
            await self._redis.hset(REDIS_CONFIG_KEY, scope, mode)
            redis_ok = True
            logger.info(
                "PQC enforcement mode persisted to Redis",
                scope=scope,
                mode=mode,
                activated_by=activated_by,
            )
        except (ConnectionError, TimeoutError, OSError, ValueError) as redis_err:
            logger.error(
                "Failed to persist PQC enforcement mode to Redis",
                scope=scope,
                mode=mode,
                error=str(redis_err),
            )

        # Write to PostgreSQL
        if self._pg is not None:
            try:
                await self._pg.execute(
                    """
                    INSERT INTO pqc_enforcement_config (scope, mode, activated_by)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (scope) DO UPDATE
                        SET mode = EXCLUDED.mode,
                            activated_by = EXCLUDED.activated_by,
                            updated_at = NOW()
                    """,
                    scope,
                    mode,
                    activated_by,
                )
                pg_ok = True
                logger.info(
                    "PQC enforcement mode persisted to PostgreSQL",
                    scope=scope,
                    mode=mode,
                    activated_by=activated_by,
                )
            except (ConnectionError, TimeoutError, OSError, ValueError) as pg_err:
                logger.error(
                    "Failed to persist PQC enforcement mode to PostgreSQL",
                    scope=scope,
                    mode=mode,
                    error=str(pg_err),
                )
        else:
            # No PG configured — count Redis success as sufficient
            pg_ok = True

        if not redis_ok and not pg_ok:
            raise StorageUnavailableError(
                "Cannot persist enforcement mode: both Redis and PostgreSQL unavailable"
            )

        # Update local cache
        self._cache[scope] = (mode, time.monotonic())

        # Publish invalidation to all other instances
        if redis_ok:
            try:
                await self._redis.publish(REDIS_CHANNEL, f"{scope}:{mode}")
            except (ConnectionError, TimeoutError, OSError, ValueError) as pub_err:
                # Non-fatal: other instances will re-read from Redis on next access
                logger.warning(
                    "Failed to publish PQC enforcement mode change on pub/sub",
                    scope=scope,
                    mode=mode,
                    error=str(pub_err),
                )

    def _invalidate_cache(self, scope: str = "global") -> None:
        """Remove a scope's entry from the local in-process cache.

        Called when a pub/sub message is received on REDIS_CHANNEL to ensure
        fresh reads from Redis on the next get_mode() call.
        """
        self._cache.pop(scope, None)
        logger.debug("PQC enforcement cache invalidated via pub/sub", scope=scope)


__all__ = [
    "DEFAULT_CACHE_TTL_SECONDS",
    "DEFAULT_MODE",
    "FAILSAFE_MODE",
    "REDIS_CHANNEL",
    "REDIS_CONFIG_KEY",
    "EnforcementModeConfigService",
    "StorageUnavailableError",
]
