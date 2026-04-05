"""
Unit tests for AgentHealthStore using fakeredis.
Constitutional Hash: 608508a9bd224290

Tests are written RED-first (before store.py is implemented).
All tests use FakeAsyncRedis — no real Redis connection required.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fakeredis")

from datetime import UTC, datetime, timedelta

import fakeredis.aioredis as fake_aioredis
import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.agent_health.models import (
    AgentHealthRecord,
    AgentHealthThresholds,
    AutonomyTier,
    HealingAction,
    HealingActionType,
    HealingOverride,
    HealingTrigger,
    HealthState,
    OverrideMode,
)
from enhanced_agent_bus.agent_health.store import AgentHealthStore


def _make_record(agent_id: str = "agent-001", **kwargs: object) -> AgentHealthRecord:
    defaults: dict = {
        "agent_id": agent_id,
        "health_state": HealthState.HEALTHY,
        "consecutive_failure_count": 0,
        "memory_usage_pct": 50.0,
        "last_event_at": datetime.now(UTC),
        "autonomy_tier": AutonomyTier.ADVISORY,
    }
    defaults.update(kwargs)
    return AgentHealthRecord(**defaults)


def _make_override(agent_id: str = "agent-001", **kwargs: object) -> HealingOverride:
    now = datetime.now(UTC)
    defaults: dict = {
        "agent_id": agent_id,
        "mode": OverrideMode.SUPPRESS_HEALING,
        "reason": "Test override",
        "issued_by": "operator@example.com",
        "issued_at": now,
        "expires_at": now + timedelta(hours=1),
    }
    defaults.update(kwargs)
    return HealingOverride(**defaults)


@pytest.fixture
def fake_redis() -> fake_aioredis.FakeRedis:
    return fake_aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def store(fake_redis: fake_aioredis.FakeRedis) -> AgentHealthStore:
    return AgentHealthStore(redis=fake_redis)


# ---------------------------------------------------------------------------
# AgentHealthRecord CRUD
# ---------------------------------------------------------------------------


class TestGetHealthRecord:
    async def test_returns_none_for_missing_agent(self, store: AgentHealthStore) -> None:
        result = await store.get_health_record("unknown-agent")
        assert result is None

    async def test_returns_record_after_upsert(self, store: AgentHealthStore) -> None:
        record = _make_record("agent-001")
        await store.upsert_health_record(record)
        fetched = await store.get_health_record("agent-001")
        assert fetched is not None
        assert fetched.agent_id == "agent-001"
        assert fetched.health_state == HealthState.HEALTHY

    async def test_key_schema(
        self, store: AgentHealthStore, fake_redis: fake_aioredis.FakeRedis
    ) -> None:
        record = _make_record("agent-abc")
        await store.upsert_health_record(record)
        keys = await fake_redis.keys("agent_health:*")
        assert "agent_health:agent-abc" in keys


class TestUpsertHealthRecord:
    async def test_upsert_overwrites_existing(self, store: AgentHealthStore) -> None:
        record1 = _make_record("agent-001", consecutive_failure_count=0)
        record2 = _make_record("agent-001", consecutive_failure_count=5)
        await store.upsert_health_record(record1)
        await store.upsert_health_record(record2)
        fetched = await store.get_health_record("agent-001")
        assert fetched is not None
        assert fetched.consecutive_failure_count == 5

    async def test_upsert_sets_ttl(
        self, store: AgentHealthStore, fake_redis: fake_aioredis.FakeRedis
    ) -> None:
        record = _make_record("agent-001")
        await store.upsert_health_record(record)
        ttl = await fake_redis.ttl("agent_health:agent-001")
        assert ttl > 0

    async def test_ttl_is_3600_seconds(
        self, store: AgentHealthStore, fake_redis: fake_aioredis.FakeRedis
    ) -> None:
        record = _make_record("agent-001")
        await store.upsert_health_record(record)
        ttl = await fake_redis.ttl("agent_health:agent-001")
        # Allow small tolerance for test execution time
        assert 3595 <= ttl <= 3600

    async def test_all_fields_persisted(self, store: AgentHealthStore) -> None:
        now = datetime.now(UTC)
        record = _make_record(
            "agent-001",
            health_state=HealthState.DEGRADED,
            consecutive_failure_count=3,
            memory_usage_pct=72.5,
            last_error_type="TimeoutError",
            last_event_at=now,
            autonomy_tier=AutonomyTier.BOUNDED,
            healing_override_id="override-99",
        )
        await store.upsert_health_record(record)
        fetched = await store.get_health_record("agent-001")
        assert fetched is not None
        assert fetched.health_state == HealthState.DEGRADED
        assert fetched.consecutive_failure_count == 3
        assert fetched.memory_usage_pct == 72.5
        assert fetched.last_error_type == "TimeoutError"
        assert fetched.autonomy_tier == AutonomyTier.BOUNDED
        assert fetched.healing_override_id == "override-99"


# ---------------------------------------------------------------------------
# HealingOverride CRUD
# ---------------------------------------------------------------------------


class TestGetOverride:
    async def test_returns_none_for_missing_agent(self, store: AgentHealthStore) -> None:
        result = await store.get_override("unknown-agent")
        assert result is None

    async def test_returns_override_after_set(self, store: AgentHealthStore) -> None:
        override = _make_override("agent-001")
        await store.set_override(override)
        fetched = await store.get_override("agent-001")
        assert fetched is not None
        assert fetched.agent_id == "agent-001"
        assert fetched.mode == OverrideMode.SUPPRESS_HEALING

    async def test_key_schema(
        self, store: AgentHealthStore, fake_redis: fake_aioredis.FakeRedis
    ) -> None:
        override = _make_override("agent-xyz")
        await store.set_override(override)
        keys = await fake_redis.keys("agent_healing_override:*")
        assert "agent_healing_override:agent-xyz" in keys


class TestSetOverride:
    async def test_overwrites_existing_override(self, store: AgentHealthStore) -> None:
        now = datetime.now(UTC)
        override1 = _make_override("agent-001", mode=OverrideMode.SUPPRESS_HEALING)
        override2 = _make_override("agent-001", mode=OverrideMode.FORCE_QUARANTINE)
        await store.set_override(override1)
        await store.set_override(override2)
        fetched = await store.get_override("agent-001")
        assert fetched is not None
        assert fetched.mode == OverrideMode.FORCE_QUARANTINE

    async def test_all_fields_persisted(self, store: AgentHealthStore) -> None:
        now = datetime.now(UTC)
        expiry = now + timedelta(hours=2)
        override = _make_override(
            "agent-001",
            mode=OverrideMode.FORCE_RESTART,
            reason="Force restart for testing",
            issued_by="admin@example.com",
            issued_at=now,
            expires_at=expiry,
        )
        await store.set_override(override)
        fetched = await store.get_override("agent-001")
        assert fetched is not None
        assert fetched.mode == OverrideMode.FORCE_RESTART
        assert fetched.reason == "Force restart for testing"
        assert fetched.issued_by == "admin@example.com"
        assert fetched.expires_at is not None


def _make_action(agent_id: str = "agent-001", **kwargs: object) -> HealingAction:
    now = datetime.now(UTC)
    defaults: dict = {
        "agent_id": agent_id,
        "trigger": HealingTrigger.FAILURE_LOOP,
        "action_type": HealingActionType.GRACEFUL_RESTART,
        "tier_determined_by": AutonomyTier.HUMAN_APPROVED,
        "initiated_at": now,
        "audit_event_id": "audit-xyz",
        "constitutional_hash": "608508a9bd224290",  # pragma: allowlist secret
    }
    defaults.update(kwargs)
    return HealingAction(**defaults)


class TestDeleteOverride:
    async def test_delete_existing_override_returns_true(self, store: AgentHealthStore) -> None:
        override = _make_override("agent-001")
        await store.set_override(override)
        result = await store.delete_override("agent-001")
        assert result is True

    async def test_delete_removes_override(self, store: AgentHealthStore) -> None:
        override = _make_override("agent-001")
        await store.set_override(override)
        await store.delete_override("agent-001")
        fetched = await store.get_override("agent-001")
        assert fetched is None

    async def test_delete_missing_override_returns_false(self, store: AgentHealthStore) -> None:
        result = await store.delete_override("unknown-agent")
        assert result is False


# ---------------------------------------------------------------------------
# HealingAction persistence
# ---------------------------------------------------------------------------


class TestSaveHealingAction:
    async def test_saves_action_with_correct_key_schema(
        self, store: AgentHealthStore, fake_redis: fake_aioredis.FakeRedis
    ) -> None:
        action = _make_action("agent-001")
        await store.save_healing_action(action)
        keys = await fake_redis.keys("agent_healing_action:agent-001:*")
        assert len(keys) == 1
        assert keys[0].startswith("agent_healing_action:agent-001:")

    async def test_saves_all_required_fields(
        self, store: AgentHealthStore, fake_redis: fake_aioredis.FakeRedis
    ) -> None:
        action = _make_action("agent-002")
        await store.save_healing_action(action)
        key = f"agent_healing_action:agent-002:{action.action_id}"
        data = await fake_redis.hgetall(key)
        assert data["agent_id"] == "agent-002"
        assert data["trigger"] == HealingTrigger.FAILURE_LOOP.value
        assert data["action_type"] == HealingActionType.GRACEFUL_RESTART.value
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_sets_ttl_on_action_key(
        self, store: AgentHealthStore, fake_redis: fake_aioredis.FakeRedis
    ) -> None:
        action = _make_action("agent-003")
        await store.save_healing_action(action)
        key = f"agent_healing_action:agent-003:{action.action_id}"
        ttl = await fake_redis.ttl(key)
        assert ttl > 0

    async def test_action_with_completed_at(
        self, store: AgentHealthStore, fake_redis: fake_aioredis.FakeRedis
    ) -> None:
        now = datetime.now(UTC)
        action = _make_action("agent-004", completed_at=now + timedelta(seconds=5))
        await store.save_healing_action(action)
        key = f"agent_healing_action:agent-004:{action.action_id}"
        data = await fake_redis.hgetall(key)
        assert data["completed_at"] != ""

    async def test_action_without_completed_at(
        self, store: AgentHealthStore, fake_redis: fake_aioredis.FakeRedis
    ) -> None:
        action = _make_action("agent-005", completed_at=None)
        await store.save_healing_action(action)
        key = f"agent_healing_action:agent-005:{action.action_id}"
        data = await fake_redis.hgetall(key)
        assert data["completed_at"] == ""
