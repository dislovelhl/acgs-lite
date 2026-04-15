"""Real-time governance event streaming primitives."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class GovernanceEvent:
    """Single governance event for dashboards and SSE subscribers."""

    event_type: str
    system_id: str
    payload: dict[str, Any]
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = _utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "system_id": self.system_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }

    def to_sse(self) -> str:
        return f"data: {json.dumps(self.to_dict(), sort_keys=True)}\n\n"


class EventBus:
    """In-process pub/sub for governance events."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[GovernanceEvent]] = []

    def publish(self, event: GovernanceEvent) -> None:
        for subscriber in list(self._subscribers):
            try:
                subscriber.put_nowait(event)
            except asyncio.QueueFull:
                continue

    async def subscribe(self, maxsize: int = 100) -> AsyncGenerator[GovernanceEvent, None]:
        queue: asyncio.Queue[GovernanceEvent] = asyncio.Queue(maxsize=maxsize)
        self._subscribers.append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)


_bus = EventBus()


def get_event_bus() -> EventBus:
    return _bus
