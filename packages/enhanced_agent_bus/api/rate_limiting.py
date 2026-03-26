"""
ACGS-2 Enhanced Agent Bus Rate Limiting
Constitutional Hash: 608508a9bd224290

This module provides rate limiting functionality for the API,
including batch-specific rate limiting based on batch size.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Protocol

try:
    from src.core.shared.types import (
        JSONDict,
        JSONList,
    )
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    JSONList = list  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .config import (
    BATCH_RATE_LIMIT_BASE,
    BYTES_PER_MB,
    MAX_ITEM_CONTENT_SIZE,
    MAX_VIOLATIONS_TO_DISPLAY,
    MS_PER_SECOND,
    RATE_LIMIT_COST_DIVISOR,
    RATE_LIMIT_WINDOW_CLEANUP_MINUTES,
    RATE_LIMIT_WINDOW_DURATION_MINUTES,
)
from .runtime_guards import is_sandbox_environment

logger = get_logger(__name__)


def _estimate_payload_size_bytes(value: object, seen: set[int] | None = None) -> int:
    """Estimate payload size without JSON serialization in hot paths."""
    if seen is None:
        seen = set()

    obj_id = id(value)
    if obj_id in seen:
        return 0
    seen.add(obj_id)

    total_size = sys.getsizeof(value)

    if isinstance(value, dict):
        for key, nested_value in value.items():
            total_size += _estimate_payload_size_bytes(key, seen)
            total_size += _estimate_payload_size_bytes(nested_value, seen)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            total_size += _estimate_payload_size_bytes(item, seen)

    return total_size


class RateLimitExceededWrapper(Exception):
    """Exception raised when a rate limit is exceeded."""

    def __init__(self, agent_id: str, message: str, retry_after_ms: int):
        self.agent_id = agent_id
        self.message = message
        self.retry_after_ms = retry_after_ms
        super().__init__(message)


# Initialize Redis client for rate limiting
_redis_client: object | None = None
try:
    import redis.asyncio as aioredis

    _redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    _redis_client = aioredis.from_url(_redis_url, decode_responses=True)
except Exception as e:
    logger.warning("Redis not available for rate limiting — falling back to in-memory: %s", e)


class BatchRequestProtocol(Protocol):
    """Protocol for batch request objects."""

    items: JSONList
    batch_id: str


# Rate limiting availability
RATE_LIMITING_AVAILABLE = False
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address

    RATE_LIMITING_AVAILABLE = True
except ImportError:
    from ..fallback_stubs import (
        Limiter,
        RateLimitExceeded,
        _rate_limit_exceeded_handler,
        get_remote_address,
    )

    logger.warning("slowapi not installed; API rate limiting is disabled and using fallback stubs")

# Batch rate limit state
_batch_rate_limit_state: dict[str, JSONDict] = {}
_batch_rate_limit_lock = asyncio.Lock()


async def check_batch_rate_limit(client_id: str, batch_size: int) -> None:
    """
    Check batch-specific rate limit based on batch size.

    Rate limiting strategy:
    - Base limit: 100 requests/minute
    - Cost per batch: batch_size / 10 tokens
    - Example: batch of 100 items consumes 10 tokens

    Args:
        client_id: Client identifier (IP address or API key)
        batch_size: Number of items in the batch

    Raises:
        RateLimitExceeded: If rate limit is exceeded
    """
    if not RATE_LIMITING_AVAILABLE:
        if not is_sandbox_environment():
            raise RuntimeError(
                "slowapi rate limiting is unavailable outside sandbox/development environments"
            )
        return

    rate_limit_cost = max(1, int(batch_size / RATE_LIMIT_COST_DIVISOR))

    # Try Redis-backed rate limiting first
    if _redis_client:
        try:
            await _check_rate_limit_redis(client_id, rate_limit_cost, batch_size)
            return
        except (ConnectionError, TimeoutError, OSError, RateLimitExceededWrapper) as e:
            if not is_sandbox_environment():
                logger.error("Redis rate limit backend unavailable: %s", e)
                raise RuntimeError(
                    "Redis-backed rate limiting unavailable outside sandbox/development "
                    "environments"
                ) from e
            logger.warning("Redis rate limit check failed, falling back to in-memory: %s", e)

    if not is_sandbox_environment():
        raise RuntimeError(
            "Redis-backed rate limiting unavailable outside sandbox/development environments"
        )

    # Fallback to in-memory rate limiting
    await _check_rate_limit_memory(client_id, rate_limit_cost, batch_size)


async def _check_rate_limit_redis(client_id: str, rate_limit_cost: int, batch_size: int) -> None:
    """
    Check rate limit using Redis backend.

    Args:
        client_id: Client identifier
        rate_limit_cost: Token cost for this request
        batch_size: Number of items in the batch

    Raises:
        RateLimitExceeded: If rate limit is exceeded
    """
    now = datetime.now(UTC)
    window_key = f"rate_limit:{client_id}:{now.strftime('%Y%m%dT%H%M')}"

    # Atomic increment and get new count
    new_count = await _redis_client.incrby(window_key, rate_limit_cost)

    # Set expiry on first request in window (TTL = window duration + 60s buffer)
    if new_count == rate_limit_cost:
        await _redis_client.expire(window_key, RATE_LIMIT_WINDOW_DURATION_MINUTES * 60 + 60)

    # Check if limit exceeded
    if new_count > BATCH_RATE_LIMIT_BASE:
        window_start = now.replace(second=0, microsecond=0)
        next_window = window_start + timedelta(minutes=RATE_LIMIT_WINDOW_DURATION_MINUTES)
        retry_after_ms = int((next_window - now).total_seconds() * MS_PER_SECOND)

        raise RateLimitExceededWrapper(
            agent_id=client_id,
            message=f"Batch rate limit exceeded: {new_count}/{BATCH_RATE_LIMIT_BASE} "
            f"tokens (batch of {batch_size} items consumes {rate_limit_cost} tokens). "
            f"Rate limit resets at {next_window.strftime('%H:%M:%S')} timezone.utc",
            retry_after_ms=retry_after_ms,
        )


async def _check_rate_limit_memory(client_id: str, rate_limit_cost: int, batch_size: int) -> None:
    """
    Check rate limit using in-memory backend (fallback).

    Args:
        client_id: Client identifier
        rate_limit_cost: Token cost for this request
        batch_size: Number of items in the batch

    Raises:
        RateLimitExceeded: If rate limit is exceeded
    """
    now = datetime.now(UTC)
    window_start = now.replace(second=0, microsecond=0)

    async with _batch_rate_limit_lock:
        # Cleanup old windows
        cutoff_time = now - timedelta(minutes=RATE_LIMIT_WINDOW_CLEANUP_MINUTES)
        keys_to_delete = [
            key
            for key, data in _batch_rate_limit_state.items()
            if data.get("window_start", now) < cutoff_time
        ]
        for key in keys_to_delete:
            _batch_rate_limit_state.pop(key, None)

        # Get or create state for current window
        state_key = f"{client_id}:{window_start.isoformat()}"
        state = _batch_rate_limit_state.setdefault(
            state_key,
            {
                "tokens_consumed": 0,
                "window_start": window_start,
                "requests": 0,
            },
        )

        # Check if limit would be exceeded
        new_token_count = state["tokens_consumed"] + rate_limit_cost
        if new_token_count > BATCH_RATE_LIMIT_BASE:
            next_window = window_start + timedelta(minutes=RATE_LIMIT_WINDOW_DURATION_MINUTES)
            retry_after_ms = int((next_window - now).total_seconds() * MS_PER_SECOND)

            raise RateLimitExceededWrapper(
                agent_id=client_id,
                message=f"Batch rate limit exceeded: {new_token_count}/{BATCH_RATE_LIMIT_BASE} "
                f"tokens (batch of {batch_size} items consumes {rate_limit_cost} tokens). "
                f"Rate limit resets at {next_window.strftime('%H:%M:%S')} timezone.utc",
                retry_after_ms=retry_after_ms,
            )

        # Update state
        state["tokens_consumed"] = new_token_count
        state["requests"] += 1


def validate_item_sizes(batch_request: BatchRequestProtocol) -> JSONDict | None:
    """
    Validate that all batch items are within size limits.

    Checks each item's content size against MAX_ITEM_CONTENT_SIZE (1MB).
    Returns error details if any items exceed the limit.

    Args:
        batch_request: The BatchRequest to validate

    Returns:
        None if all items are valid, otherwise dict with error details including:
        - oversized_items: List of item indices that exceed size limit
        - total_oversized: Count of oversized items
        - max_size_mb: Maximum allowed size in MB
        - details: Per-item size information (limited to first 5 violations)
    """
    oversized_items: list[JSONDict] = []

    for idx, item in enumerate(batch_request.items):
        try:
            content_size = _estimate_payload_size_bytes(item.content)
        except (TypeError, ValueError) as e:
            oversized_items.append(
                {
                    "item_index": idx,
                    "request_id": item.request_id,
                    "error": f"Content serialization failed: {e!s}",
                    "content_size_bytes": None,
                }
            )
            continue

        if content_size <= MAX_ITEM_CONTENT_SIZE:
            continue

        oversized_items.append(
            {
                "item_index": idx,
                "request_id": item.request_id,
                "content_size_bytes": content_size,
                "content_size_mb": round(content_size / BYTES_PER_MB, 2),
                "max_size_mb": round(MAX_ITEM_CONTENT_SIZE / BYTES_PER_MB, 2),
            }
        )

    if not oversized_items:
        return None

    total_oversized = len(oversized_items)
    return {
        "oversized_items": oversized_items[:MAX_VIOLATIONS_TO_DISPLAY],
        "total_oversized": total_oversized,
        "max_size_bytes": MAX_ITEM_CONTENT_SIZE,
        "max_size_mb": round(MAX_ITEM_CONTENT_SIZE / BYTES_PER_MB, 2),
        "message": f"{total_oversized} item(s) exceed maximum content size of "
        f"{MAX_ITEM_CONTENT_SIZE} bytes (1 MB). "
        f"Showing first {min(MAX_VIOLATIONS_TO_DISPLAY, total_oversized)} violation(s).",
    }


def require_rate_limiting_dependencies() -> None:
    """Refuse production startup when rate limiting would degrade to stubs or memory only."""
    if is_sandbox_environment():
        return
    if not RATE_LIMITING_AVAILABLE:
        raise RuntimeError(
            "slowapi rate limiting is required outside sandbox/development environments"
        )
    if _redis_client is None:
        raise RuntimeError(
            "Redis-backed rate limiting is required outside sandbox/development environments"
        )


# Create the global limiter instance
_limiter_kwargs = {"key_func": get_remote_address}
if storage_uri := os.environ.get("RATE_LIMIT_STORAGE_URI") or os.environ.get("REDIS_URL"):
    _limiter_kwargs["storage_uri"] = storage_uri
limiter = Limiter(**_limiter_kwargs)

__all__ = [
    "RATE_LIMITING_AVAILABLE",
    "RateLimitExceeded",
    "_rate_limit_exceeded_handler",
    "check_batch_rate_limit",
    "get_remote_address",
    "limiter",
    "require_rate_limiting_dependencies",
    "validate_item_sizes",
]
