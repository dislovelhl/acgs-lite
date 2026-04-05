"""
Unit tests for TierAssignmentRepository.
Constitutional Hash: 608508a9bd224290

All external dependencies (Redis, SQLAlchemy async session) are mocked.
No real database or cache connections are made.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.services.api_gateway.models.tier_assignment import AgentTierAssignment, AutonomyTier
from src.core.services.api_gateway.repositories.tier_assignment import (
    NotFoundError,
    TierAssignmentRepository,
    _cache_key,
    _serialize,
)
from src.core.services.api_gateway.schemas.tier_assignment import (
    AgentTierAssignmentCreate,
    AgentTierAssignmentUpdate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AGENT_ID = "agent-abc-123"
_TENANT_ID = "tenant-xyz-456"
_ASSIGNED_BY = "admin@example.com"


def _make_assignment(
    agent_id: str = _AGENT_ID,
    tenant_id: str = _TENANT_ID,
    tier: AutonomyTier = AutonomyTier.BOUNDED,
    action_boundaries: list[str] | None = None,
) -> AgentTierAssignment:
    now = datetime.now(UTC)
    return AgentTierAssignment(
        id=uuid.uuid4(),
        agent_id=agent_id,
        tenant_id=tenant_id,
        tier=tier,
        action_boundaries=action_boundaries,
        assigned_by=_ASSIGNED_BY,
        assigned_at=now,
        created_at=now,
    )


def _make_redis() -> AsyncMock:
    redis = AsyncMock()
    return redis


def _make_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    return session


def _make_repo(
    session: AsyncMock | None = None, redis: AsyncMock | None = None
) -> tuple[TierAssignmentRepository, AsyncMock, AsyncMock]:
    s = session or _make_session()
    r = redis or _make_redis()
    repo = TierAssignmentRepository(session=s, redis=r)
    return repo, s, r


# ---------------------------------------------------------------------------
# get_by_agent — cache hit
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_get_by_agent_cache_hit() -> None:
    """Redis returns a serialized assignment; DB must NOT be called."""
    assignment = _make_assignment()
    serialized = _serialize(assignment)

    repo, session, redis = _make_repo()
    redis.get.return_value = serialized

    result = await repo.get_by_agent(_AGENT_ID, _TENANT_ID)

    assert result is not None
    assert result.agent_id == _AGENT_ID
    assert result.tenant_id == _TENANT_ID
    assert result.tier == AutonomyTier.BOUNDED

    redis.get.assert_called_once_with(_cache_key(_TENANT_ID, _AGENT_ID))
    session.execute.assert_not_called()


# ---------------------------------------------------------------------------
# get_by_agent — cache miss, DB hit
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_get_by_agent_cache_miss_db_hit() -> None:
    """Redis returns None; DB is queried and cache repopulated with TTL=60s."""
    assignment = _make_assignment()

    repo, session, redis = _make_repo()
    redis.get.return_value = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = assignment
    session.execute.return_value = mock_result

    result = await repo.get_by_agent(_AGENT_ID, _TENANT_ID)

    assert result is assignment
    redis.get.assert_called_once_with(_cache_key(_TENANT_ID, _AGENT_ID))
    session.execute.assert_called_once()
    redis.set.assert_called_once_with(
        _cache_key(_TENANT_ID, _AGENT_ID),
        _serialize(assignment),
        ex=60,
    )


# ---------------------------------------------------------------------------
# get_by_agent — not found
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_get_by_agent_not_found() -> None:
    """Cache miss AND DB returns no row → returns None (does not raise)."""
    repo, session, redis = _make_repo()
    redis.get.return_value = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    result = await repo.get_by_agent(_AGENT_ID, _TENANT_ID)

    assert result is None
    redis.set.assert_not_called()


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_create_persists_and_invalidates_cache() -> None:
    """create() adds row to DB and deletes the Redis cache key."""
    data = AgentTierAssignmentCreate(
        agent_id=_AGENT_ID,
        tier=AutonomyTier.ADVISORY,
        action_boundaries=None,
    )
    repo, session, redis = _make_repo()

    result = await repo.create(data, assigned_by=_ASSIGNED_BY, tenant_id=_TENANT_ID)

    session.add.assert_called_once()
    session.flush.assert_called_once()
    redis.delete.assert_called_once_with(_cache_key(_TENANT_ID, _AGENT_ID))

    assert result.agent_id == _AGENT_ID
    assert result.tenant_id == _TENANT_ID
    assert result.tier == AutonomyTier.ADVISORY
    assert result.assigned_by == _ASSIGNED_BY


# ---------------------------------------------------------------------------
# update — success
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_update_modifies_db_and_invalidates_cache() -> None:
    """update() updates the DB row and deletes the Redis cache key."""
    existing = _make_assignment(tier=AutonomyTier.ADVISORY)
    data = AgentTierAssignmentUpdate(tier=AutonomyTier.BOUNDED, action_boundaries=["read:*"])

    repo, session, redis = _make_repo()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    session.execute.return_value = mock_result

    result = await repo.update(_AGENT_ID, _TENANT_ID, data, assigned_by=_ASSIGNED_BY)

    session.flush.assert_called_once()
    redis.delete.assert_called_once_with(_cache_key(_TENANT_ID, _AGENT_ID))
    assert result.tier == AutonomyTier.BOUNDED
    assert result.action_boundaries == ["read:*"]


# ---------------------------------------------------------------------------
# update — not found
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_update_raises_not_found_for_unknown_agent() -> None:
    """update() raises NotFoundError when the agent has no existing assignment."""
    data = AgentTierAssignmentUpdate(tier=AutonomyTier.HUMAN_APPROVED)

    repo, session, redis = _make_repo()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    with pytest.raises(NotFoundError):
        await repo.update(_AGENT_ID, _TENANT_ID, data, assigned_by=_ASSIGNED_BY)

    session.flush.assert_not_called()
    redis.delete.assert_not_called()


# ---------------------------------------------------------------------------
# delete — success
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_delete_removes_db_row_and_cache_key() -> None:
    """delete() removes the DB row and deletes the Redis cache key."""
    existing = _make_assignment()

    repo, session, redis = _make_repo()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    session.execute.return_value = mock_result

    await repo.delete(_AGENT_ID, _TENANT_ID)

    session.delete.assert_called_once_with(existing)
    session.flush.assert_called_once()
    redis.delete.assert_called_once_with(_cache_key(_TENANT_ID, _AGENT_ID))


# ---------------------------------------------------------------------------
# delete — not found
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_delete_raises_not_found_for_unknown_agent() -> None:
    """delete() raises NotFoundError when the agent has no existing assignment."""
    repo, session, redis = _make_repo()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    with pytest.raises(NotFoundError):
        await repo.delete(_AGENT_ID, _TENANT_ID)

    session.delete.assert_not_called()
    session.flush.assert_not_called()
    redis.delete.assert_not_called()
