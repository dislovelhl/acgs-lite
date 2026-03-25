"""
AgentHealthStore — async Redis-backed CRUD for agent health state.
Constitutional Hash: 608508a9bd224290

Key schema:
  agent_health:{agent_id}              → AgentHealthRecord (Redis hash)
  agent_healing_override:{agent_id}    → HealingOverride (Redis hash)

Health records expire after HEALTH_RECORD_TTL_SECONDS to auto-remove stale agents.
"""

from __future__ import annotations

from datetime import datetime

from redis.asyncio import Redis
from src.core.shared.types import AgentID

from enhanced_agent_bus.agent_health.models import (
    AgentHealthRecord,
    HealingAction,
    HealingOverride,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

HEALTH_RECORD_TTL_SECONDS: int = 3600
_HEALTH_KEY_PREFIX = "agent_health:"
_OVERRIDE_KEY_PREFIX = "agent_healing_override:"


def _health_key(agent_id: AgentID) -> str:
    return f"{_HEALTH_KEY_PREFIX}{agent_id}"


def _override_key(agent_id: AgentID) -> str:
    return f"{_OVERRIDE_KEY_PREFIX}{agent_id}"


def _record_to_hash(record: AgentHealthRecord) -> dict[str, str]:
    """Serialize AgentHealthRecord to a flat Redis-hash-compatible dict."""
    return {
        "agent_id": record.agent_id,
        "health_state": record.health_state.value,
        "consecutive_failure_count": str(record.consecutive_failure_count),
        "memory_usage_pct": str(record.memory_usage_pct),
        "last_error_type": record.last_error_type or "",
        "last_event_at": record.last_event_at.isoformat(),
        "autonomy_tier": record.autonomy_tier.value,
        "healing_override_id": record.healing_override_id or "",
    }


def _hash_to_record(data: dict[str, str]) -> AgentHealthRecord:
    """Deserialize a Redis hash into an AgentHealthRecord."""
    return AgentHealthRecord(
        agent_id=data["agent_id"],
        health_state=data["health_state"],  # StrEnum coercion
        consecutive_failure_count=int(data["consecutive_failure_count"]),
        memory_usage_pct=float(data["memory_usage_pct"]),
        last_error_type=data["last_error_type"] or None,
        last_event_at=datetime.fromisoformat(data["last_event_at"]),
        autonomy_tier=data["autonomy_tier"],  # StrEnum coercion
        healing_override_id=data["healing_override_id"] or None,
    )


def _override_to_hash(override: HealingOverride) -> dict[str, str]:
    """Serialize HealingOverride to a flat Redis-hash-compatible dict."""
    return {
        "override_id": override.override_id,
        "agent_id": override.agent_id,
        "mode": override.mode.value,
        "reason": override.reason,
        "issued_by": override.issued_by,
        "issued_at": override.issued_at.isoformat(),
        "expires_at": override.expires_at.isoformat() if override.expires_at else "",
    }


def _hash_to_override(data: dict[str, str]) -> HealingOverride:
    """Deserialize a Redis hash into a HealingOverride."""
    expires_at = datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None
    return HealingOverride(
        override_id=data["override_id"],
        agent_id=data["agent_id"],
        mode=data["mode"],  # StrEnum coercion
        reason=data["reason"],
        issued_by=data["issued_by"],
        issued_at=datetime.fromisoformat(data["issued_at"]),
        expires_at=expires_at,
    )


class AgentHealthStore:
    """Async Redis-backed store for AgentHealthRecord and HealingOverride objects.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    # ------------------------------------------------------------------
    # AgentHealthRecord
    # ------------------------------------------------------------------

    async def get_health_record(self, agent_id: AgentID) -> AgentHealthRecord | None:
        """Retrieve the current health record for an agent, or None if absent."""
        try:
            data: dict[str, str] = await self._redis.hgetall(_health_key(agent_id))
            if not data:
                return None
            return _hash_to_record(data)
        except Exception as exc:
            logger.error(
                "Failed to get health record",
                agent_id=agent_id,
                error=str(exc),
            )
            raise

    async def upsert_health_record(self, record: AgentHealthRecord) -> None:
        """Write (create or overwrite) a health record and set TTL."""
        try:
            key = _health_key(record.agent_id)
            mapping = _record_to_hash(record)
            await self._redis.hset(key, mapping=mapping)  # type: ignore[arg-type]
            await self._redis.expire(key, HEALTH_RECORD_TTL_SECONDS)
            logger.info(
                "Upserted health record",
                agent_id=record.agent_id,
                health_state=record.health_state.value,
            )
        except Exception as exc:
            logger.error(
                "Failed to upsert health record",
                agent_id=record.agent_id,
                error=str(exc),
            )
            raise

    # ------------------------------------------------------------------
    # HealingOverride
    # ------------------------------------------------------------------

    async def get_override(self, agent_id: AgentID) -> HealingOverride | None:
        """Retrieve the active healing override for an agent, or None if absent."""
        try:
            data: dict[str, str] = await self._redis.hgetall(_override_key(agent_id))
            if not data:
                return None
            return _hash_to_override(data)
        except Exception as exc:
            logger.error(
                "Failed to get override",
                agent_id=agent_id,
                error=str(exc),
            )
            raise

    async def set_override(self, override: HealingOverride) -> None:
        """Write (create or overwrite) a healing override for an agent."""
        try:
            key = _override_key(override.agent_id)
            mapping = _override_to_hash(override)
            await self._redis.hset(key, mapping=mapping)  # type: ignore[arg-type]
            logger.info(
                "Set healing override",
                agent_id=override.agent_id,
                mode=override.mode.value,
                issued_by=override.issued_by,
            )
        except Exception as exc:
            logger.error(
                "Failed to set override",
                agent_id=override.agent_id,
                error=str(exc),
            )
            raise

    async def save_healing_action(self, action: HealingAction) -> None:
        """Persist a HealingAction to the audit trail in Redis.

        Key: agent_healing_action:{agent_id}:{action_id}
        TTL: same as health records (1 hour).
        """
        key = f"agent_healing_action:{action.agent_id}:{action.action_id}"
        mapping = {
            "action_id": action.action_id,
            "agent_id": action.agent_id,
            "trigger": action.trigger.value,
            "action_type": action.action_type.value,
            "initiated_at": action.initiated_at.isoformat(),
            "completed_at": action.completed_at.isoformat() if action.completed_at else "",
            "audit_event_id": action.audit_event_id or "",
            "constitutional_hash": action.constitutional_hash,
        }
        try:
            await self._redis.hset(key, mapping=mapping)  # type: ignore[arg-type]
            await self._redis.expire(key, HEALTH_RECORD_TTL_SECONDS)
            logger.info(
                "Saved healing action",
                agent_id=action.agent_id,
                action_id=action.action_id,
                action_type=action.action_type.value,
            )
        except Exception as exc:
            logger.error(
                "Failed to save healing action",
                agent_id=action.agent_id,
                action_id=action.action_id,
                error=str(exc),
            )
            raise

    async def delete_override(self, agent_id: AgentID) -> bool:
        """Remove the active healing override for an agent.

        Returns:
            True if an override existed and was deleted; False if no override was found.
        """
        try:
            deleted: int = await self._redis.delete(_override_key(agent_id))
            existed = deleted > 0
            if existed:
                logger.info("Deleted healing override", agent_id=agent_id)
            return existed
        except Exception as exc:
            logger.error(
                "Failed to delete override",
                agent_id=agent_id,
                error=str(exc),
            )
            raise


__all__ = ["HEALTH_RECORD_TTL_SECONDS", "AgentHealthStore", "HealingAction"]
