"""
Tests for Saga Event Publishing.
Constitutional Hash: 608508a9bd224290
"""

import uuid

import pytest

from enterprise_sso.saga_orchestration import (
    SagaEvent,
    SagaEventPublisher,
    SagaEventType,
)

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestSagaEventPublisher:
    """Tests for saga event publishing."""

    async def test_publish_event(self, event_publisher: SagaEventPublisher):
        """Test publishing an event."""
        event = SagaEvent(
            event_id=str(uuid.uuid4()),
            saga_id="saga-001",
            event_type=SagaEventType.SAGA_STARTED,
        )

        await event_publisher.publish(event)
        events = event_publisher.get_events(saga_id="saga-001")

        assert len(events) == 1
        assert events[0].event_type == SagaEventType.SAGA_STARTED

    async def test_subscribe_to_events(self, event_publisher: SagaEventPublisher):
        """Test subscribing to events."""
        received_events: list[SagaEvent] = []

        async def handler(event: SagaEvent):
            received_events.append(event)

        event_publisher.subscribe(handler)

        event = SagaEvent(
            event_id=str(uuid.uuid4()),
            saga_id="saga-001",
            event_type=SagaEventType.SAGA_STARTED,
        )
        await event_publisher.publish(event)

        assert len(received_events) == 1

    async def test_filter_events_by_type(self, event_publisher: SagaEventPublisher):
        """Test filtering events by type."""
        event1 = SagaEvent(
            event_id=str(uuid.uuid4()),
            saga_id="saga-001",
            event_type=SagaEventType.SAGA_STARTED,
        )
        event2 = SagaEvent(
            event_id=str(uuid.uuid4()),
            saga_id="saga-001",
            event_type=SagaEventType.SAGA_COMPLETED,
        )

        await event_publisher.publish(event1)
        await event_publisher.publish(event2)

        started_events = event_publisher.get_events(event_type=SagaEventType.SAGA_STARTED)
        assert len(started_events) == 1

    async def test_handler_exception_does_not_break_publishing(
        self, event_publisher: SagaEventPublisher
    ):
        """Test that handler exceptions don't break event publishing."""

        async def failing_handler(event: SagaEvent):
            raise ValueError("Handler failed")

        received_events: list[SagaEvent] = []

        async def good_handler(event: SagaEvent):
            received_events.append(event)

        event_publisher.subscribe(failing_handler)
        event_publisher.subscribe(good_handler)

        event = SagaEvent(
            event_id=str(uuid.uuid4()),
            saga_id="saga-001",
            event_type=SagaEventType.SAGA_STARTED,
        )
        await event_publisher.publish(event)

        # Good handler should still receive the event
        assert len(received_events) == 1
