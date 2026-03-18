from __future__ import annotations

import sys
from datetime import UTC, datetime

from enhanced_agent_bus.config import BusConfiguration
from enhanced_agent_bus.observability.structured_logging import get_logger

from .conversation import ConversationMessage, ConversationState, MessageRole

logger = get_logger(__name__)
sys.modules.setdefault("enhanced_agent_bus.sdpc.pacar_manager", sys.modules[__name__])

try:
    import redis.asyncio as redis
except ImportError:  # pragma: no cover
    class _RedisStub:
        @staticmethod
        def from_url(*args: object, **kwargs: object) -> object:
            raise ImportError("redis is not installed")

    redis = _RedisStub()  # type: ignore[assignment]

_PACAR_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class PACARManager:
    def __init__(self, config: BusConfiguration | None = None) -> None:
        self.config = config or BusConfiguration.from_environment()
        self._redis = None
        self._local_history: dict[str, ConversationState] = {}

    async def _get_redis(self):
        if self._redis is None:
            self._redis = redis.from_url(self.config.redis_url, decode_responses=True)
        return self._redis

    async def get_state(self, session_id: str) -> ConversationState:
        if session_id in self._local_history:
            return self._local_history[session_id]
        try:
            client = await self._get_redis()
            payload = await client.get(f"pacar:session:{session_id}")
            if payload:
                state = ConversationState.model_validate_json(payload)
            else:
                state = ConversationState(session_id=session_id)
        except _PACAR_OPERATION_ERRORS as exc:
            logger.error(f"PACAR get_state failed for {session_id}: {exc}")
            state = ConversationState(session_id=session_id)
        self._local_history[session_id] = state
        return state

    async def save_state(self, state: ConversationState) -> None:
        state.updated_at = datetime.now(UTC).isoformat()
        self._local_history[state.session_id] = state
        try:
            client = await self._get_redis()
            await client.setex(f"pacar:session:{state.session_id}", 3600, state.model_dump_json())
        except _PACAR_OPERATION_ERRORS as exc:
            logger.error(f"PACAR save_state failed for {state.session_id}: {exc}")

    async def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> ConversationState:
        state = await self.get_state(session_id)
        state.messages.append(
            ConversationMessage(role=role, content=content, metadata=metadata or {})
        )
        state.updated_at = datetime.now(UTC).isoformat()
        await self.save_state(state)
        return state

    async def clear_session(self, session_id: str) -> None:
        self._local_history.pop(session_id, None)
        try:
            client = await self._get_redis()
            await client.delete(f"pacar:session:{session_id}")
        except _PACAR_OPERATION_ERRORS as exc:
            logger.error(f"PACAR clear_session failed for {session_id}: {exc}")
