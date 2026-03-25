"""
ACGS-2 Centralized Redis Configuration
Constitutional Hash: 608508a9bd224290

Provides centralized Redis configuration for all services with health check
callbacks for graceful degradation when Redis is unavailable.
"""

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from src.core.shared.structured_logging import get_logger

try:
    import redis
except ImportError:
    redis = None

# Constitutional Hash for governance validation
from src.core.shared.constants import CONSTITUTIONAL_HASH

logger = get_logger(__name__)


def _get_settings() -> object:
    """
    Resolve canonical unified settings at call time.

    Tests and services expect Redis defaults from `config.unified`.
    """
    from src.core.shared.config.unified import settings

    return settings


class RedisHealthState(Enum):
    """Redis health states for tracking availability."""

    HEALTHY = "healthy"  # Redis is available and responding
    UNHEALTHY = "unhealthy"  # Redis is unavailable or timing out
    RECOVERING = "recovering"  # Redis was down, attempting recovery
    UNKNOWN = "unknown"  # Initial state before first check


@dataclass
class RedisHealthCheckConfig:
    """Configuration for Redis health checks."""

    check_interval: float = 30.0  # Seconds between health checks
    timeout: float = 5.0  # Seconds before health check times out
    unhealthy_threshold: int = 3  # Failures before marking unhealthy
    healthy_threshold: int = 1  # Successes before marking healthy again


class RedisHealthListener:
    """
    Redis Health Listener with constitutional compliance logging.

    Following pattern from circuit_breaker.ACGSCircuitBreakerListener.
    """

    def __init__(self, name: str = "redis"):
        self.name = name
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def on_state_change(self, old_state: RedisHealthState, new_state: RedisHealthState) -> None:
        """Log state changes with constitutional context."""
        logger.warning(
            f"[{self.constitutional_hash}] Redis health '{self.name}' "
            f"state change: {old_state.value} -> {new_state.value}"
        )

    def on_health_check_success(self, latency_ms: float) -> None:
        """Log successful health checks."""
        logger.debug(
            f"[{self.constitutional_hash}] Redis health '{self.name}' "
            f"check succeeded (latency: {latency_ms:.2f}ms)"
        )

    def on_health_check_failure(self, error: Exception) -> None:
        """Log failed health checks."""
        logger.warning(
            f"[{self.constitutional_hash}] Redis health '{self.name}' "
            f"check failed: {type(error).__name__}: {error}"
        )


# Type alias for health change callbacks
HealthChangeCallback = Callable[[RedisHealthState, RedisHealthState], None]


@dataclass
class RedisConfig:
    """
    Centralized Redis configuration with health check support.

    This class provides:
    - Redis URL and connection parameter configuration
    - Health check callbacks for graceful degradation
    - State tracking for Redis availability

    Usage:
        config = RedisConfig()
        config.register_health_callback(my_callback)
        is_healthy, latency = config.health_check()
    """

    # Default URL for legacy compatibility
    DEFAULT_URL: str = field(default="redis://localhost:6379", init=False, repr=False)

    # Health check configuration
    health_config: RedisHealthCheckConfig = field(default_factory=RedisHealthCheckConfig)

    # Instance state (not passed via __init__)
    _state: RedisHealthState = field(default=RedisHealthState.UNKNOWN, init=False, repr=False)
    _consecutive_failures: int = field(default=0, init=False, repr=False)
    _consecutive_successes: int = field(default=0, init=False, repr=False)
    _last_check_time: float | None = field(default=None, init=False, repr=False)
    _last_latency_ms: float | None = field(default=None, init=False, repr=False)
    _callbacks: list[HealthChangeCallback] = field(default_factory=list, init=False, repr=False)
    _listeners: list[RedisHealthListener] = field(default_factory=list, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _redis_client: object | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        """Initialize with default listener."""
        self._listeners.append(RedisHealthListener())

    @classmethod
    def get_url(cls, db: int = 0, env_var: str = "REDIS_URL") -> str:
        """
        Get Redis URL from settings or default.

        Args:
            db: Database number (0-15)
            env_var: Environment variable name for URL override

        Returns:
            Redis URL string
        """
        # Check environment variable for URL override first
        env_url = os.getenv(env_var)
        if env_url:
            base_url = env_url
        else:
            # Construct base URL from settings, supporting rediss scheme
            settings = _get_settings()
            scheme = "rediss" if settings.redis.ssl else "redis"
            base_url = f"{scheme}://{settings.redis.host}:{settings.redis.port}"

        # Normalize URL by stripping trailing slash first
        base_url = base_url.rstrip("/")

        # Check if URL already has a database number (path segment with content)
        # redis://localhost:6379/5 has 3 slashes after rstrip
        if base_url.count("/") > 2:
            # URL already has a path segment (likely db), return as-is
            return base_url

        # Use db from settings if not explicitly provided as non-zero
        settings = _get_settings()
        effective_db = db if db > 0 else settings.redis.db

        if effective_db > 0:
            return f"{base_url}/{effective_db}"

        return base_url

    @classmethod
    def get_connection_params(cls) -> dict:
        """
        Get Redis connection parameters from settings.

        Returns:
            Dictionary of connection parameters
        """
        settings = _get_settings()
        return {
            "url": cls.get_url(),
            "max_connections": settings.redis.max_connections,
            "socket_timeout": settings.redis.socket_timeout,
            "socket_connect_timeout": settings.redis.socket_timeout,
            "retry_on_timeout": settings.redis.retry_on_timeout,
            "ssl": settings.redis.ssl,
            "ssl_cert_reqs": settings.redis.ssl_cert_reqs,
            "ssl_ca_certs": settings.redis.ssl_ca_certs,
            "socket_keepalive": settings.redis.socket_keepalive,
            "health_check_interval": settings.redis.health_check_interval,
        }

    def register_health_callback(self, callback: HealthChangeCallback) -> None:
        """
        Register a callback to be invoked on health state changes.

        Args:
            callback: Function(old_state, new_state) to call on state change

        Example:
            def on_redis_health_change(old, new):
                if new == RedisHealthState.UNHEALTHY:
                    enable_l1_only_mode()

            config.register_health_callback(on_redis_health_change)
        """
        with self._lock:
            self._callbacks.append(callback)
            logger.info(f"[{CONSTITUTIONAL_HASH}] Registered health callback: {callback.__name__}")

    def unregister_health_callback(self, callback: HealthChangeCallback) -> bool:
        """
        Unregister a previously registered callback.

        Args:
            callback: The callback to remove

        Returns:
            True if callback was removed, False if not found
        """
        with self._lock:
            try:
                self._callbacks.remove(callback)
                logger.info(
                    f"[{CONSTITUTIONAL_HASH}] Unregistered health callback: {callback.__name__}"
                )
                return True
            except ValueError:
                return False

    def add_listener(self, listener: RedisHealthListener) -> None:
        """
        Add a health listener for logging and monitoring.

        Args:
            listener: RedisHealthListener instance
        """
        with self._lock:
            self._listeners.append(listener)

    def health_check(self, redis_client: object | None = None) -> tuple:
        """
        Perform a health check against Redis.

        This method attempts to ping Redis and tracks success/failure counts
        to determine the overall health state. State transitions trigger
        registered callbacks.

        Args:
            redis_client: Optional Redis client to use. If not provided,
                         attempts to create one from settings.

        Returns:
            Tuple of (is_healthy: bool, latency_ms: Optional[float])

        Example:
            config = RedisConfig()
            is_healthy, latency = config.health_check()
            if not is_healthy:
                logger.warning("Redis unavailable, using L1 cache only")
        """
        start_time = time.perf_counter()
        is_healthy = False
        latency_ms = None

        try:
            client = redis_client or self._get_or_create_client()
            if client is None:
                raise ConnectionError("Unable to create Redis client")

            # Attempt ping - works for both sync and async clients
            # For sync clients, ping() returns True/string
            # We handle the case where the client might be async
            client.ping()

            # Calculate latency
            latency_ms = (time.perf_counter() - start_time) * 1000
            self._last_latency_ms = latency_ms
            is_healthy = True

            # Notify listeners of success
            for listener in self._listeners:
                try:
                    listener.on_health_check_success(latency_ms)
                except (ValueError, TypeError, AttributeError, RuntimeError) as e:
                    logger.error(f"Listener error on success: {e}")

        except (ConnectionError, TimeoutError, OSError) as e:
            latency_ms = (time.perf_counter() - start_time) * 1000

            # Notify listeners of failure
            for listener in self._listeners:
                try:
                    listener.on_health_check_failure(e)
                except (ValueError, TypeError, AttributeError, RuntimeError) as le:
                    logger.error(f"Listener error on failure: {le}")

        # Update state based on result
        self._update_health_state(is_healthy)
        self._last_check_time = time.time()

        return (is_healthy, latency_ms)

    async def health_check_async(self, redis_client: object | None = None) -> tuple:
        """
        Perform an async health check against Redis.

        Args:
            redis_client: Optional async Redis client

        Returns:
            Tuple of (is_healthy: bool, latency_ms: Optional[float])
        """
        start_time = time.perf_counter()
        is_healthy = False
        latency_ms = None

        try:
            client = redis_client or self._redis_client
            if client is None:
                raise ConnectionError("No async Redis client available")

            # Await the async ping
            await client.ping()

            latency_ms = (time.perf_counter() - start_time) * 1000
            self._last_latency_ms = latency_ms
            is_healthy = True

            for listener in self._listeners:
                try:
                    listener.on_health_check_success(latency_ms)
                except (ValueError, TypeError, AttributeError, RuntimeError) as e:
                    logger.error(f"Listener error on success: {e}")

        except (ConnectionError, TimeoutError, OSError) as e:
            latency_ms = (time.perf_counter() - start_time) * 1000

            for listener in self._listeners:
                try:
                    listener.on_health_check_failure(e)
                except (ValueError, TypeError, AttributeError, RuntimeError) as le:
                    logger.error(f"Listener error on failure: {le}")

        self._update_health_state(is_healthy)
        self._last_check_time = time.time()

        return (is_healthy, latency_ms)

    def _get_or_create_client(self) -> object | None:
        """
        Get or create a Redis client for health checks.

        Returns:
            Redis client or None if unavailable
        """
        if self._redis_client is not None:
            return self._redis_client

        try:
            import redis

            params = self.get_connection_params()
            self._redis_client = redis.Redis.from_url(
                params["url"],
                socket_timeout=self.health_config.timeout,
                socket_connect_timeout=self.health_config.timeout,
            )
            return self._redis_client
        except ImportError:
            logger.warning("redis-py not installed, health checks disabled")
            return None
        except (ConnectionError, OSError, ValueError) as e:
            logger.error(f"Failed to create Redis client: {e}")
            return None

    def _update_health_state(self, check_passed: bool) -> None:
        """
        Update health state based on check result.

        Args:
            check_passed: Whether the health check succeeded
        """
        with self._lock:
            old_state = self._state

            if check_passed:
                self._consecutive_failures = 0
                self._consecutive_successes += 1

                if self._consecutive_successes >= self.health_config.healthy_threshold:
                    if old_state == RedisHealthState.RECOVERING:
                        self._state = RedisHealthState.HEALTHY
                    elif old_state in (
                        RedisHealthState.UNKNOWN,
                        RedisHealthState.UNHEALTHY,
                    ):
                        self._state = RedisHealthState.HEALTHY
            else:
                self._consecutive_successes = 0
                self._consecutive_failures += 1

                if self._consecutive_failures >= self.health_config.unhealthy_threshold:
                    self._state = RedisHealthState.UNHEALTHY

            # Trigger callbacks if state changed
            if old_state != self._state:
                self._notify_state_change(old_state, self._state)

    def _notify_state_change(
        self, old_state: RedisHealthState, new_state: RedisHealthState
    ) -> None:
        """
        Notify listeners and callbacks of state change.

        Args:
            old_state: Previous health state
            new_state: New health state
        """
        # Notify listeners
        for listener in self._listeners:
            try:
                listener.on_state_change(old_state, new_state)
            except (ValueError, TypeError, AttributeError, RuntimeError) as e:
                logger.error(f"Listener state change error: {e}")

        # Invoke callbacks
        for callback in self._callbacks:
            try:
                callback(old_state, new_state)
            except (ValueError, TypeError, AttributeError, RuntimeError) as e:
                logger.error(
                    f"[{CONSTITUTIONAL_HASH}] Health callback error in {callback.__name__}: {e}"
                )

    @property
    def current_state(self) -> RedisHealthState:
        """Get current health state."""
        return self._state

    @property
    def is_healthy(self) -> bool:
        """Check if Redis is currently considered healthy."""
        return self._state == RedisHealthState.HEALTHY

    @property
    def last_latency_ms(self) -> float | None:
        """Get latency of last health check in milliseconds."""
        return self._last_latency_ms

    @property
    def last_check_time(self) -> float | None:
        """Get timestamp of last health check."""
        return self._last_check_time

    def get_health_stats(self) -> dict:
        """
        Get comprehensive health statistics.

        Returns:
            Dictionary containing health state and metrics
        """
        return {
            "state": self._state.value,
            "is_healthy": self.is_healthy,
            "consecutive_failures": self._consecutive_failures,
            "consecutive_successes": self._consecutive_successes,
            "last_latency_ms": self._last_latency_ms,
            "last_check_time": (
                datetime.fromtimestamp(self._last_check_time, tz=UTC).isoformat()
                if self._last_check_time
                else None
            ),
            "config": {
                "check_interval": self.health_config.check_interval,
                "timeout": self.health_config.timeout,
                "unhealthy_threshold": self.health_config.unhealthy_threshold,
                "healthy_threshold": self.health_config.healthy_threshold,
            },
        }

    def reset(self) -> None:
        """Reset health state to unknown (for testing or reconnection)."""
        with self._lock:
            old_state = self._state
            self._state = RedisHealthState.UNKNOWN
            self._consecutive_failures = 0
            self._consecutive_successes = 0
            self._last_check_time = None
            self._last_latency_ms = None

            if old_state != RedisHealthState.UNKNOWN:
                self._notify_state_change(old_state, RedisHealthState.UNKNOWN)

            logger.info(f"[{CONSTITUTIONAL_HASH}] Redis health state reset")


# Singleton instance for easy import
REDIS_URL = RedisConfig.get_url()
REDIS_URL_WITH_DB = RedisConfig.get_url(db=0)

# Global health-aware config instance
_global_redis_config: RedisConfig | None = None
_global_config_lock = threading.Lock()


def get_redis_config() -> RedisConfig:
    """
    Get or create the global Redis configuration with health checking.

    Returns:
        RedisConfig singleton instance
    """
    global _global_redis_config
    with _global_config_lock:
        if _global_redis_config is None:
            _global_redis_config = RedisConfig()
        return _global_redis_config


def get_redis_url(db: int = 0) -> str:
    """
    Convenience function to get Redis URL.

    Args:
        db: Database number

    Returns:
        Redis URL string
    """
    return RedisConfig.get_url(db=db)
