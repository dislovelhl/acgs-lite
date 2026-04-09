"""Tests for the real-time governance event bus."""

from __future__ import annotations

import asyncio
import json

import pytest

from acgs_lite.events import EventBus, GovernanceEvent


@pytest.mark.asyncio
async def test_event_bus_publish_delivers_event_to_subscriber() -> None:
    bus = EventBus()
    queue: asyncio.Queue[GovernanceEvent] = asyncio.Queue(maxsize=1)
    bus._subscribers.append(queue)
    event = GovernanceEvent(event_type="validation", system_id="sys-1", payload={"ok": True})

    bus.publish(event)

    assert await queue.get() == event


def test_governance_event_to_sse_has_expected_shape() -> None:
    event = GovernanceEvent(event_type="validation", system_id="sys-1", payload={"ok": True})

    sse = event.to_sse()

    assert sse.startswith("data: ")
    assert sse.endswith("\n\n")


def test_governance_event_to_sse_payload_is_json_parseable() -> None:
    event = GovernanceEvent(event_type="validation", system_id="sys-1", payload={"ok": True})

    payload = json.loads(event.to_sse().removeprefix("data: ").strip())

    assert payload["event_type"] == "validation"
    assert payload["system_id"] == "sys-1"
    assert payload["payload"] == {"ok": True}


@pytest.mark.asyncio
async def test_multiple_subscribers_receive_same_event() -> None:
    bus = EventBus()
    first: asyncio.Queue[GovernanceEvent] = asyncio.Queue(maxsize=1)
    second: asyncio.Queue[GovernanceEvent] = asyncio.Queue(maxsize=1)
    bus._subscribers.extend([first, second])
    event = GovernanceEvent(event_type="validation", system_id="sys-1", payload={"ok": True})

    bus.publish(event)

    assert await first.get() == event
    assert await second.get() == event
