"""
ACGS-2 Enhanced Agent Bus - PQC Audit Event Writers
Constitutional Hash: 608508a9bd224290

Writes enriched audit events for PQC governance verifications and enforcement
mode changes. Increments Redis HINCRBY counters for rolling adoption metrics.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Literal

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

# Redis key patterns for rolling adoption counters
_METRICS_KEY_PREFIX = "pqc:metrics"
_WINDOWS: list[tuple[Literal["1h", "24h", "7d"], int]] = [
    ("1h", 7200),  # TTL: 2x window for overlap safety
    ("24h", 172800),  # TTL: 2x window
    ("7d", 1209600),  # TTL: 2x window
]


def _bucket_id(window: str) -> str:
    """Compute the current time-bucket identifier for a window."""
    now = int(time.time())
    if window == "1h":
        return str(now // 3600)
    if window == "24h":
        return str(now // 86400)
    # 7d
    return str(now // 604800)


async def write_verification_audit_event(
    *,
    key_type: Literal["pqc", "classical"],
    key_algorithm: str | None,
    enforcement_mode: Literal["strict", "permissive"],
    constitutional_hash_valid: bool,
    redis_client: Any | None = None,
    audit_writer: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Emit a governance verification audit event enriched with PQC fields.

    Also increments Redis HINCRBY counters for 1h/24h/7d adoption windows.

    Returns the event dict for testing convenience.
    """
    event = {
        "event_type": "governance_verification",
        "key_type": key_type,
        "key_algorithm": key_algorithm,
        "enforcement_mode_at_verification": enforcement_mode,
        "constitutional_hash_valid": constitutional_hash_valid,
        "timestamp": time.time(),
    }

    # Write to blockchain audit log if writer provided
    if audit_writer is not None:
        try:
            result = audit_writer(event)
            if hasattr(result, "__await__"):
                await result
        except Exception as exc:
            logger.error("Failed to write verification audit event", error=str(exc))

    # Increment Redis adoption counters
    if redis_client is not None:
        counter_field = f"{key_type}_verified_count"
        for window, ttl in _WINDOWS:
            bucket = _bucket_id(window)
            redis_key = f"{_METRICS_KEY_PREFIX}:{window}:{bucket}"
            try:
                await redis_client.hincrby(redis_key, counter_field, 1)
                await redis_client.expire(redis_key, ttl)
            except (ConnectionError, TimeoutError, OSError, RuntimeError, ValueError) as exc:
                logger.warning(
                    "Failed to increment PQC adoption counter",
                    window=window,
                    key_type=key_type,
                    error=str(exc),
                )

    logger.info(
        "PQC verification audit event emitted",
        key_type=key_type,
        enforcement_mode=enforcement_mode,
        constitutional_hash_valid=constitutional_hash_valid,
    )
    return event


async def write_mode_change_audit_event(
    *,
    from_mode: Literal["strict", "permissive"],
    to_mode: Literal["strict", "permissive"],
    operator_id: str,
    audit_writer: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Emit an enforcement_mode_changed audit event.

    Emits a WARNING-level log when downgrading from strict to permissive.

    Returns the event dict for testing convenience.
    """
    event = {
        "event_type": "enforcement_mode_changed",
        "from_mode": from_mode,
        "to_mode": to_mode,
        "operator_id": operator_id,
        "timestamp": time.time(),
    }

    # Write to blockchain audit log if writer provided
    if audit_writer is not None:
        try:
            result = audit_writer(event)
            if hasattr(result, "__await__"):
                await result
        except Exception as exc:
            logger.error("Failed to write mode change audit event", error=str(exc))

    # Downgrade warning
    if from_mode == "strict" and to_mode == "permissive":
        logger.warning(
            "PQC enforcement downgraded from strict to permissive",
            operator_id=operator_id,
        )
    else:
        logger.info(
            "PQC enforcement mode changed",
            from_mode=from_mode,
            to_mode=to_mode,
            operator_id=operator_id,
        )

    return event


__all__ = [
    "write_mode_change_audit_event",
    "write_verification_audit_event",
]
