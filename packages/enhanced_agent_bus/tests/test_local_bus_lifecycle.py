from __future__ import annotations

import asyncio

import pytest

from enhanced_agent_bus.local_bus import LocalEventBus
from enhanced_agent_bus.models import AgentMessage, MessageType


@pytest.mark.asyncio
async def test_subscribe_before_start_receives_after_start() -> None:
    bus = LocalEventBus()
    received: list[dict[str, object]] = []

    async def handler(message: dict[str, object]) -> None:
        received.append(message)

    await bus.subscribe("tenant-a", [MessageType.COMMAND], handler)
    await bus.start()
    await bus.send_message(
        AgentMessage(
            from_agent="agent-a",
            to_agent="agent-b",
            tenant_id="tenant-a",
            message_type=MessageType.COMMAND,
            content={"step": "sync"},
        )
    )
    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0]["content"] == {"step": "sync"}

    await bus.stop()


@pytest.mark.asyncio
async def test_stop_cancels_background_consumer_tasks() -> None:
    bus = LocalEventBus()

    async def handler(_: dict[str, object]) -> None:
        await asyncio.sleep(0)

    await bus.start()
    await bus.subscribe("tenant-a", [MessageType.COMMAND], handler)
    tasks = list(bus._background_tasks)

    assert tasks

    await bus.stop()

    assert all(task.done() for task in tasks)
