"""Operator control plane for bounded self-evolution.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from src.core.self_evolution.models import (
    ResearchOperatorControlSnapshot,
    ResearchRuntimeState,
)

DEFAULT_RESEARCH_OPERATOR_CONTROL_KEY_PREFIX = "acgs:research:operator_control"
_RUNTIME_HEARTBEAT_TTL_SECONDS = 120


class ResearchOperatorControlPlane(Protocol):
    async def snapshot(self) -> dict[str, object]: ...

    async def request_pause(self, user_id: str, reason: str | None) -> dict[str, object]: ...

    async def request_resume(self, user_id: str, reason: str | None) -> dict[str, object]: ...

    async def request_stop(self, user_id: str, reason: str | None) -> dict[str, object]: ...

    async def record_runtime_heartbeat(
        self,
        *,
        instance_id: str,
        runtime_state: ResearchRuntimeState,
        run_id: str | None = None,
        generation_index: int | None = None,
        pid: int | None = None,
    ) -> None: ...

    async def aclose(self) -> None: ...


class InMemoryResearchOperatorControlPlane:
    """Simple in-memory operator control plane used by tests and dev setups."""

    def __init__(self) -> None:
        self._snapshot = ResearchOperatorControlSnapshot()
        self._last_runtime_heartbeat_at: datetime | None = None

    async def snapshot(self) -> dict[str, object]:
        payload = self._snapshot.model_dump(mode="json")
        payload["runtime_online"] = self._runtime_online()
        return payload

    async def request_pause(self, user_id: str, reason: str | None) -> dict[str, object]:
        self._snapshot.paused = True
        self._snapshot.stop_requested = False
        self._snapshot.status = "paused"
        self._snapshot.mode = "pause_requested"
        self._snapshot.updated_by = user_id
        self._snapshot.requested_by = user_id
        self._snapshot.reason = reason
        self._snapshot.updated_at = datetime.now(UTC)
        return await self.snapshot()

    async def request_resume(self, user_id: str, reason: str | None) -> dict[str, object]:
        self._snapshot.paused = False
        self._snapshot.stop_requested = False
        self._snapshot.status = "running"
        self._snapshot.mode = "running"
        self._snapshot.updated_by = user_id
        self._snapshot.requested_by = user_id
        self._snapshot.reason = reason
        self._snapshot.updated_at = datetime.now(UTC)
        return await self.snapshot()

    async def request_stop(self, user_id: str, reason: str | None) -> dict[str, object]:
        self._snapshot.paused = False
        self._snapshot.stop_requested = True
        self._snapshot.status = "stopped"
        self._snapshot.mode = "stop_requested"
        self._snapshot.updated_by = user_id
        self._snapshot.requested_by = user_id
        self._snapshot.reason = reason
        self._snapshot.updated_at = datetime.now(UTC)
        return await self.snapshot()

    async def record_runtime_heartbeat(
        self,
        *,
        instance_id: str,
        runtime_state: ResearchRuntimeState,
        run_id: str | None = None,
        generation_index: int | None = None,
        pid: int | None = None,
    ) -> None:
        self._snapshot.runtime_instance_id = instance_id
        self._snapshot.runtime_state = runtime_state.value
        self._snapshot.runtime_last_run_id = run_id
        self._snapshot.runtime_generation_index = generation_index
        self._snapshot.runtime_pid = pid
        self._last_runtime_heartbeat_at = datetime.now(UTC)
        self._snapshot.updated_at = self._last_runtime_heartbeat_at

    def _runtime_online(self) -> bool:
        if self._last_runtime_heartbeat_at is None:
            return False
        return datetime.now(UTC) - self._last_runtime_heartbeat_at <= timedelta(
            seconds=_RUNTIME_HEARTBEAT_TTL_SECONDS
        )

    async def aclose(self) -> None:
        return None


def create_research_operator_control_plane(
    *,
    backend: str = "memory",
    redis_url: str | None = None,
    key_prefix: str = DEFAULT_RESEARCH_OPERATOR_CONTROL_KEY_PREFIX,
) -> ResearchOperatorControlPlane:
    """Create an operator control plane.

    Redis-backed persistence is intentionally deferred; until then the control plane
    returns the in-memory implementation for all backends.
    """
    _ = (backend, redis_url, key_prefix)
    return InMemoryResearchOperatorControlPlane()


__all__ = [
    "DEFAULT_RESEARCH_OPERATOR_CONTROL_KEY_PREFIX",
    "InMemoryResearchOperatorControlPlane",
    "ResearchOperatorControlPlane",
    "ResearchRuntimeState",
    "create_research_operator_control_plane",
]

