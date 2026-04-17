"""Real-time governance event streaming primitives.

Constitutional Hash: 608508a9bd224290
ADR: docs/wiki/architecture/adr/020-governance-stream-reactive-state.md
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

T = TypeVar("T")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class GovernanceEvent:
    """Single governance event for dashboards and SSE subscribers."""

    event_type: str
    system_id: str
    payload: dict[str, Any]
    timestamp: str = ""
    scope_id: str = "default"

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = _utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "system_id": self.system_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "scope_id": self.scope_id,
        }

    def to_sse(self) -> str:
        return f"data: {json.dumps(self.to_dict(), sort_keys=True)}\n\n"


class EventBus:
    """In-process pub/sub for governance events.

    Subscriber queues are stored as plain list entries; the async generator
    in ``subscribe()`` removes its own queue on exit (including cancellation),
    so there is no permanent leak.  The queue reference is strong while the
    generator is alive and disappears when it exits.
    """

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[GovernanceEvent]] = []

    def publish(self, event: GovernanceEvent) -> None:
        for subscriber in list(self._subscribers):
            try:
                subscriber.put_nowait(event)
            except asyncio.QueueFull:
                continue

    async def subscribe(
        self,
        maxsize: int = 100,
        scope_id: str | None = None,
    ) -> AsyncIterator[GovernanceEvent]:
        """Yield events, optionally filtered to *scope_id*."""
        queue: asyncio.Queue[GovernanceEvent] = asyncio.Queue(maxsize=maxsize)
        self._subscribers.append(queue)
        try:
            while True:
                event = await queue.get()
                if scope_id is None or event.scope_id in (scope_id, "default"):
                    yield event
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)


class GovernanceStream(Generic[T]):
    """Typed reactive wrapper over EventBus.

    Provides ``.derive(fn)`` to project raw ``GovernanceEvent`` streams into
    domain-typed values without coupling call sites to the bus internals.

    Constitutional Hash: 608508a9bd224290

    Usage::

        stream: GovernanceStream[list[str]] = GovernanceStream(
            bus=get_event_bus(),
            transform=lambda e: e.payload.get("violation_ids", []),
            scope_id="session-42",
        )
        async for violations in stream.subscribe():
            ...
    """

    def __init__(
        self,
        bus: EventBus,
        transform: Callable[[GovernanceEvent], T],
        scope_id: str | None = None,
        maxsize: int = 100,
    ) -> None:
        self._bus = bus
        self._transform = transform
        self._scope_id = scope_id
        self._maxsize = maxsize

    def derive(self, fn: Callable[[T], GovernanceStream[Any]]) -> GovernanceStream[Any]:
        """Return a new stream whose values are produced by composing *fn* over this stream.

        This is intentionally simple: ``fn`` receives the transformed value and
        returns a new ``GovernanceStream``.  For most ACGS use cases a flat map
        is not needed; this provides the composability hook.
        """
        outer_transform = self._transform

        def composed(event: GovernanceEvent) -> Any:
            intermediate = outer_transform(event)
            inner_stream = fn(intermediate)
            return inner_stream._transform(event)

        return GovernanceStream(
            bus=self._bus,
            transform=composed,
            scope_id=self._scope_id,
            maxsize=self._maxsize,
        )

    async def subscribe(self) -> AsyncIterator[T]:
        """Yield transformed values from the bus."""
        async for event in self._bus.subscribe(
            maxsize=self._maxsize,
            scope_id=self._scope_id,
        ):
            yield self._transform(event)


_bus = EventBus()


def get_event_bus() -> EventBus:
    return _bus
