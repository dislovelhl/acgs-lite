"""
Async repository for AgentTierAssignment with Redis TTL cache.
Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.services.api_gateway.models.tier_assignment import AgentTierAssignment, AutonomyTier
from src.core.services.api_gateway.schemas.tier_assignment import (
    AgentTierAssignmentCreate,
    AgentTierAssignmentUpdate,
)
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)

_CACHE_TTL = 60  # seconds


def _cache_key(tenant_id: str, agent_id: str) -> str:
    return f"tier:v1:{tenant_id}:{agent_id}"


def _serialize(assignment: AgentTierAssignment) -> str:
    return json.dumps(
        {
            "id": str(assignment.id),
            "agent_id": assignment.agent_id,
            "tenant_id": assignment.tenant_id,
            "tier": str(assignment.tier),
            "action_boundaries": assignment.action_boundaries,
            "assigned_by": assignment.assigned_by,
            "assigned_at": assignment.assigned_at.isoformat(),
            "created_at": assignment.created_at.isoformat(),
        }
    )


def _deserialize(raw: str) -> AgentTierAssignment:
    data = json.loads(raw)
    return AgentTierAssignment(
        id=uuid.UUID(data["id"]),
        agent_id=data["agent_id"],
        tenant_id=data["tenant_id"],
        tier=AutonomyTier(data["tier"]),
        action_boundaries=data["action_boundaries"],
        assigned_by=data["assigned_by"],
        assigned_at=datetime.fromisoformat(data["assigned_at"]),
        created_at=datetime.fromisoformat(data["created_at"]),
    )


class NotFoundError(Exception):
    """Raised when the requested tier assignment does not exist."""


class TierAssignmentRepository:
    """Async repository for agent tier assignments backed by PostgreSQL + Redis cache."""

    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self._session = session
        self._redis = redis

    async def get_by_agent(self, agent_id: str, tenant_id: str) -> AgentTierAssignment | None:
        """Return the tier assignment for the given agent, or None if not found.

        Checks Redis cache first; on miss, queries PostgreSQL and repopulates cache.
        """
        key = _cache_key(tenant_id, agent_id)

        cached = await self._redis.get(key)
        if cached is not None:
            logger.info("tier_assignment.cache_hit", agent_id=agent_id, tenant_id=tenant_id)
            return _deserialize(cached)

        logger.info("tier_assignment.cache_miss", agent_id=agent_id, tenant_id=tenant_id)
        result = await self._session.execute(
            select(AgentTierAssignment).where(
                AgentTierAssignment.agent_id == agent_id,
                AgentTierAssignment.tenant_id == tenant_id,
            )
        )
        assignment = result.scalar_one_or_none()

        if assignment is None:
            return None

        await self._redis.set(key, _serialize(assignment), ex=_CACHE_TTL)
        return assignment

    async def create(
        self,
        data: AgentTierAssignmentCreate,
        assigned_by: str,
        tenant_id: str,
    ) -> AgentTierAssignment:
        """Persist a new tier assignment and invalidate any stale cache entry."""
        now = datetime.now(UTC)
        assignment = AgentTierAssignment(
            id=uuid.uuid4(),
            agent_id=data.agent_id,
            tenant_id=tenant_id,
            tier=data.tier,
            action_boundaries=data.action_boundaries,
            assigned_by=assigned_by,
            assigned_at=now,
            created_at=now,
        )
        self._session.add(assignment)
        await self._session.flush()

        key = _cache_key(tenant_id, data.agent_id)
        await self._redis.delete(key)

        logger.info(
            "tier_assignment.created",
            agent_id=data.agent_id,
            tenant_id=tenant_id,
            tier=str(data.tier),
        )
        return assignment

    async def update(
        self,
        agent_id: str,
        tenant_id: str,
        data: AgentTierAssignmentUpdate,
        assigned_by: str,
    ) -> AgentTierAssignment:
        """Update an existing tier assignment and invalidate cache.

        Raises NotFoundError if no assignment exists for the given agent/tenant.
        """
        result = await self._session.execute(
            select(AgentTierAssignment).where(
                AgentTierAssignment.agent_id == agent_id,
                AgentTierAssignment.tenant_id == tenant_id,
            )
        )
        assignment = result.scalar_one_or_none()
        if assignment is None:
            raise NotFoundError(f"No tier assignment for agent={agent_id!r} tenant={tenant_id!r}")

        assignment.tier = data.tier
        assignment.action_boundaries = data.action_boundaries
        assignment.assigned_by = assigned_by
        assignment.assigned_at = datetime.now(UTC)
        await self._session.flush()

        key = _cache_key(tenant_id, agent_id)
        await self._redis.delete(key)

        logger.info(
            "tier_assignment.updated",
            agent_id=agent_id,
            tenant_id=tenant_id,
            tier=str(data.tier),
        )
        return assignment

    async def delete(self, agent_id: str, tenant_id: str) -> None:
        """Delete a tier assignment and remove it from cache.

        Raises NotFoundError if no assignment exists for the given agent/tenant.
        """
        result = await self._session.execute(
            select(AgentTierAssignment).where(
                AgentTierAssignment.agent_id == agent_id,
                AgentTierAssignment.tenant_id == tenant_id,
            )
        )
        assignment = result.scalar_one_or_none()
        if assignment is None:
            raise NotFoundError(f"No tier assignment for agent={agent_id!r} tenant={tenant_id!r}")

        await self._session.delete(assignment)
        await self._session.flush()

        key = _cache_key(tenant_id, agent_id)
        await self._redis.delete(key)

        logger.info(
            "tier_assignment.deleted",
            agent_id=agent_id,
            tenant_id=tenant_id,
        )

    async def list_by_tenant(self, tenant_id: str) -> list[AgentTierAssignment]:
        """Return all tier assignments scoped to the given tenant."""
        result = await self._session.execute(
            select(AgentTierAssignment).where(AgentTierAssignment.tenant_id == tenant_id)
        )
        return list(result.scalars().all())
