"""
Redis Backend for Distributed Rate Limiting.

Constitutional Hash: cdd01ef066bc6cf2

Provides Redis-based rate limiting for multi-instance deployments.
Falls back to in-memory when Redis is unavailable.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

logger = get_logger(__name__)

REDIS_RATE_LIMIT_MAX_CONNECTIONS = 20


@dataclass
class RedisConfig:
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    key_prefix: str = "acgs:ratelimit:"
    socket_timeout: float = 1.0
    socket_connect_timeout: float = 1.0

    @classmethod
    def from_env(cls) -> RedisConfig:
        return cls(
            host=os.environ.get("REDIS_HOST", "localhost"),
            port=int(os.environ.get("REDIS_PORT", "6379")),
            db=int(os.environ.get("REDIS_DB", "0")),
            password=os.environ.get("REDIS_PASSWORD"),
            key_prefix=os.environ.get("REDIS_RATE_LIMIT_PREFIX", "acgs:ratelimit:"),
        )


class RedisRateLimitBackend:
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __init__(self, config: RedisConfig | None = None):
        self._config = config or RedisConfig.from_env()
        self._redis = None
        self._connection_pool = None
        self._available = False
        self._last_check = 0.0
        self._check_interval = 30.0

    async def connect(self) -> bool:
        try:
            import redis.asyncio as aioredis

            if self._connection_pool is None:
                redis_url = f"redis://{self._config.host}:{self._config.port}/{self._config.db}"
                self._connection_pool = aioredis.ConnectionPool.from_url(
                    redis_url,
                    password=self._config.password,
                    socket_timeout=self._config.socket_timeout,
                    socket_connect_timeout=self._config.socket_connect_timeout,
                    decode_responses=True,
                    max_connections=REDIS_RATE_LIMIT_MAX_CONNECTIONS,
                )

            self._redis = aioredis.Redis(connection_pool=self._connection_pool)
            await self._redis.ping()
            self._available = True
            logger.info(f"[{CONSTITUTIONAL_HASH}] Redis rate limit backend connected")
            return True
        except ImportError:
            logger.warning("redis package not installed, using in-memory rate limiting")
            return False
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, using in-memory fallback")
            return False

    @property
    def is_available(self) -> bool:
        return self._available and self._redis is not None

    async def check_and_consume(
        self,
        key: str,
        max_tokens: float,
        refill_rate: float,
        window_seconds: int = 60,
    ) -> tuple[bool, float, float]:
        if not self.is_available:
            return True, max_tokens, 0.0

        full_key = f"{self._config.key_prefix}{key}"
        now = time.time()

        try:
            lua_script = """
            local key = KEYS[1]
            local max_tokens = tonumber(ARGV[1])
            local refill_rate = tonumber(ARGV[2])
            local now = tonumber(ARGV[3])
            local window = tonumber(ARGV[4])

            local bucket = redis.call('HMGET', key, 'tokens', 'last_update')
            local tokens = tonumber(bucket[1]) or max_tokens
            local last_update = tonumber(bucket[2]) or now

            local elapsed = now - last_update
            tokens = math.min(max_tokens, tokens + (elapsed * refill_rate))

            local allowed = 0
            if tokens >= 1 then
                tokens = tokens - 1
                allowed = 1
            end

            redis.call('HMSET', key, 'tokens', tokens, 'last_update', now)
            redis.call('EXPIRE', key, window * 2)

            local reset_seconds = (max_tokens - tokens) / refill_rate

            return {allowed, tokens, reset_seconds}
            """

            result = await self._redis.eval(
                lua_script,
                1,
                full_key,
                str(max_tokens),
                str(refill_rate),
                str(now),
                str(window_seconds),
            )

            allowed = bool(int(result[0]))
            remaining = float(result[1])
            reset_seconds = float(result[2])

            return allowed, remaining, reset_seconds

        except Exception as e:
            logger.warning(f"Redis rate limit check failed: {e}")
            await self._check_connection()
            return True, max_tokens, 0.0

    async def _check_connection(self) -> None:
        now = time.time()
        if now - self._last_check < self._check_interval:
            return

        self._last_check = now
        try:
            if self._redis:
                await self._redis.ping()
                self._available = True
        except (RuntimeError, ConnectionError, OSError):
            self._available = False

    async def get_stats(self) -> JSONDict:
        stats: JSONDict = {
            "constitutional_hash": self.constitutional_hash,
            "backend": "redis" if self.is_available else "in-memory",
            "available": self.is_available,
            "config": {
                "host": self._config.host,
                "port": self._config.port,
                "db": self._config.db,
                "key_prefix": self._config.key_prefix,
            },
        }

        if self.is_available and self._redis:
            try:
                info = await self._redis.info("memory")
                stats["memory_used"] = info.get("used_memory_human", "unknown")
            except (RuntimeError, ConnectionError, OSError):
                pass

        return stats

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
            self._redis = None
            self._available = False
        if self._connection_pool is not None:
            await self._connection_pool.disconnect()
            self._connection_pool = None


_redis_backend: RedisRateLimitBackend | None = None


async def get_redis_backend() -> RedisRateLimitBackend:
    global _redis_backend
    if _redis_backend is None:
        _redis_backend = RedisRateLimitBackend()
        await _redis_backend.connect()
    return _redis_backend
