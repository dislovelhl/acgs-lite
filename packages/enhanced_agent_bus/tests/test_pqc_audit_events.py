"""
ACGS-2 Enhanced Agent Bus - PQC Audit Event Tests
Constitutional Hash: 608508a9bd224290

Tests for write_verification_audit_event() and write_mode_change_audit_event().
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

try:
    from enhanced_agent_bus.pqc_audit import (
        write_mode_change_audit_event,
        write_verification_audit_event,
    )
except ImportError:
    from pqc_audit import (  # type: ignore[no-redef]
        write_mode_change_audit_event,
        write_verification_audit_event,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _redis_mock() -> AsyncMock:
    """Build an async Redis mock for counter operations."""
    redis = AsyncMock()
    redis.hincrby = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    return redis


# ---------------------------------------------------------------------------
# write_verification_audit_event() tests
# ---------------------------------------------------------------------------


async def test_verification_event_includes_required_fields():
    """Event payload contains key_type, key_algorithm, enforcement_mode, hash_valid."""
    event = await write_verification_audit_event(
        key_type="pqc",
        key_algorithm="ML-DSA-65",
        enforcement_mode="strict",
        constitutional_hash_valid=True,
    )
    assert event["event_type"] == "governance_verification"
    assert event["key_type"] == "pqc"
    assert event["key_algorithm"] == "ML-DSA-65"
    assert event["enforcement_mode_at_verification"] == "strict"
    assert event["constitutional_hash_valid"] is True
    assert "timestamp" in event


async def test_verification_pqc_increments_redis_counters():
    """PQC verification increments pqc_verified_count for all three windows."""
    redis = _redis_mock()
    await write_verification_audit_event(
        key_type="pqc",
        key_algorithm="ML-DSA-65",
        enforcement_mode="strict",
        constitutional_hash_valid=True,
        redis_client=redis,
    )
    # 3 windows x (hincrby + expire) = 6 calls
    assert redis.hincrby.await_count == 3
    assert redis.expire.await_count == 3
    # All hincrby calls use pqc_verified_count field
    for call in redis.hincrby.await_args_list:
        assert call.args[1] == "pqc_verified_count"
        assert call.args[2] == 1


async def test_verification_classical_increments_redis_counters():
    """Classical verification increments classical_verified_count for all three windows."""
    redis = _redis_mock()
    await write_verification_audit_event(
        key_type="classical",
        key_algorithm="RSA-2048",
        enforcement_mode="permissive",
        constitutional_hash_valid=True,
        redis_client=redis,
    )
    assert redis.hincrby.await_count == 3
    for call in redis.hincrby.await_args_list:
        assert call.args[1] == "classical_verified_count"


async def test_verification_calls_audit_writer():
    """Audit writer callable is invoked with the event payload."""
    writer = MagicMock()
    event = await write_verification_audit_event(
        key_type="pqc",
        key_algorithm="ML-KEM-768",
        enforcement_mode="strict",
        constitutional_hash_valid=True,
        audit_writer=writer,
    )
    writer.assert_called_once_with(event)


# ---------------------------------------------------------------------------
# write_mode_change_audit_event() tests
# ---------------------------------------------------------------------------


async def test_mode_change_event_fields():
    """Mode change event includes event_type, from_mode, to_mode, operator_id."""
    event = await write_mode_change_audit_event(
        from_mode="permissive",
        to_mode="strict",
        operator_id="operator-1",
    )
    assert event["event_type"] == "enforcement_mode_changed"
    assert event["from_mode"] == "permissive"
    assert event["to_mode"] == "strict"
    assert event["operator_id"] == "operator-1"
    assert "timestamp" in event


async def test_downgrade_emits_warning(caplog):
    """Downgrade from strict to permissive emits a WARNING log."""
    import logging

    with caplog.at_level(logging.WARNING):
        await write_mode_change_audit_event(
            from_mode="strict",
            to_mode="permissive",
            operator_id="admin-2",
        )
    assert any(
        "downgraded" in r.message.lower() or "permissive" in r.message.lower()
        for r in caplog.records
        if r.levelno >= logging.WARNING
    )
