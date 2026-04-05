"""Tests for feedback_handler.handler module."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus.feedback_handler.enums import FeedbackType, OutcomeStatus
from enhanced_agent_bus.feedback_handler.handler import (
    FeedbackHandler,
    get_feedback_for_decision,
    get_feedback_handler,
    submit_feedback,
)
from enhanced_agent_bus.feedback_handler.models import (
    FeedbackBatchRequest,
    FeedbackEvent,
    FeedbackStats,
    StoredFeedbackEvent,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_event(**overrides) -> FeedbackEvent:
    defaults = {
        "decision_id": "dec-001",
        "feedback_type": FeedbackType.POSITIVE,
        "outcome": OutcomeStatus.SUCCESS,
        "user_id": "user-1",
        "tenant_id": "tenant-a",
    }
    defaults.update(overrides)
    return FeedbackEvent(**defaults)


@pytest.fixture()
def handler() -> FeedbackHandler:
    """Return a handler using in-memory storage (no DB)."""
    return FeedbackHandler(db_connection=None, auto_publish_kafka=False)


# ---------------------------------------------------------------------------
# store_feedback — in-memory path
# ---------------------------------------------------------------------------


class TestStoreFeedback:
    def test_store_returns_accepted_response(self, handler: FeedbackHandler):
        event = _make_event()
        resp = handler.store_feedback(event)

        assert resp.status == "accepted"
        assert resp.decision_id == "dec-001"
        assert resp.feedback_id  # non-empty UUID
        assert resp.timestamp  # ISO timestamp string

    def test_stored_event_lands_in_memory(self, handler: FeedbackHandler):
        handler.store_feedback(_make_event())
        assert len(handler._memory_store) == 1

    def test_response_details_contain_type_and_outcome(self, handler: FeedbackHandler):
        resp = handler.store_feedback(_make_event())
        assert resp.details["feedback_type"] == "positive"
        assert resp.details["outcome"] == "success"


# ---------------------------------------------------------------------------
# store_feedback — DB path
# ---------------------------------------------------------------------------


class TestStoreFeedbackWithDB:
    def test_store_to_database_called(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        h = FeedbackHandler(db_connection=mock_conn)
        h.store_feedback(_make_event())

        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    def test_db_failure_falls_back_to_memory(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = RuntimeError("db down")
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        h = FeedbackHandler(db_connection=mock_conn)
        resp = h.store_feedback(_make_event())

        assert resp.status == "accepted"
        assert len(h._memory_store) == 1


# ---------------------------------------------------------------------------
# Kafka auto-publish
# ---------------------------------------------------------------------------


class TestKafkaPublish:
    def test_auto_publish_invokes_publisher(self):
        publisher = MagicMock()
        h = FeedbackHandler(auto_publish_kafka=True)
        h.set_kafka_publisher(publisher)

        h.store_feedback(_make_event())
        publisher.publish.assert_called_once()

    def test_kafka_failure_does_not_break_store(self):
        publisher = MagicMock()
        publisher.publish.side_effect = RuntimeError("kafka down")
        h = FeedbackHandler(auto_publish_kafka=True)
        h.set_kafka_publisher(publisher)

        resp = h.store_feedback(_make_event())
        assert resp.status == "accepted"


# ---------------------------------------------------------------------------
# store_batch
# ---------------------------------------------------------------------------


class TestStoreBatch:
    def test_batch_all_accepted(self, handler: FeedbackHandler):
        events = [_make_event(decision_id=f"dec-{i}") for i in range(3)]
        batch = FeedbackBatchRequest(events=events)
        resp = handler.store_batch(batch)

        assert resp.total == 3
        assert resp.accepted == 3
        assert resp.rejected == 0
        assert len(resp.feedback_ids) == 3


# ---------------------------------------------------------------------------
# get_feedback — in-memory
# ---------------------------------------------------------------------------


class TestGetFeedback:
    def test_returns_all_when_no_filter(self, handler: FeedbackHandler):
        handler.store_feedback(_make_event(decision_id="d1"))
        handler.store_feedback(_make_event(decision_id="d2"))

        results = handler.get_feedback()
        assert len(results) == 2

    def test_filter_by_decision_id(self, handler: FeedbackHandler):
        handler.store_feedback(_make_event(decision_id="d1"))
        handler.store_feedback(_make_event(decision_id="d2"))

        results = handler.get_feedback(decision_id="d1")
        assert len(results) == 1
        assert results[0].decision_id == "d1"

    def test_limit_and_offset(self, handler: FeedbackHandler):
        for i in range(5):
            handler.store_feedback(_make_event(decision_id=f"d{i}"))

        results = handler.get_feedback(limit=2, offset=1)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# get_feedback_stats — in-memory
# ---------------------------------------------------------------------------


class TestGetFeedbackStats:
    def test_empty_stats(self, handler: FeedbackHandler):
        stats = handler.get_feedback_stats()
        assert stats.total_count == 0

    def test_counts_by_type(self, handler: FeedbackHandler):
        handler.store_feedback(_make_event(feedback_type=FeedbackType.POSITIVE))
        handler.store_feedback(_make_event(feedback_type=FeedbackType.NEGATIVE))
        handler.store_feedback(_make_event(feedback_type=FeedbackType.NEUTRAL))
        handler.store_feedback(
            _make_event(
                feedback_type=FeedbackType.CORRECTION,
                correction_data={"key": "val"},
            )
        )

        stats = handler.get_feedback_stats()
        assert stats.total_count == 4
        assert stats.positive_count == 1
        assert stats.negative_count == 1
        assert stats.neutral_count == 1
        assert stats.correction_count == 1

    def test_success_rate(self, handler: FeedbackHandler):
        handler.store_feedback(_make_event(outcome=OutcomeStatus.SUCCESS))
        handler.store_feedback(_make_event(outcome=OutcomeStatus.FAILURE))

        stats = handler.get_feedback_stats()
        assert stats.success_rate == pytest.approx(0.5)

    def test_average_impact(self, handler: FeedbackHandler):
        handler.store_feedback(_make_event(actual_impact=0.8))
        handler.store_feedback(_make_event(actual_impact=0.4))

        stats = handler.get_feedback_stats()
        assert stats.average_impact == pytest.approx(0.6)

    def test_filter_by_tenant(self, handler: FeedbackHandler):
        handler.store_feedback(_make_event(tenant_id="t1"))
        handler.store_feedback(_make_event(tenant_id="t2"))

        stats = handler.get_feedback_stats(tenant_id="t1")
        assert stats.total_count == 1


# ---------------------------------------------------------------------------
# mark_as_processed — in-memory
# ---------------------------------------------------------------------------


class TestMarkAsProcessed:
    def test_marks_matching_events(self, handler: FeedbackHandler):
        resp = handler.store_feedback(_make_event())
        count = handler.mark_as_processed([resp.feedback_id])
        assert count == 1
        assert handler._memory_store[0].processed is True

    def test_empty_ids_returns_zero(self, handler: FeedbackHandler):
        assert handler.mark_as_processed([]) == 0


# ---------------------------------------------------------------------------
# get_unprocessed_feedback
# ---------------------------------------------------------------------------


class TestGetUnprocessed:
    def test_returns_only_unprocessed(self, handler: FeedbackHandler):
        r1 = handler.store_feedback(_make_event(decision_id="d1"))
        handler.store_feedback(_make_event(decision_id="d2"))
        handler.mark_as_processed([r1.feedback_id])

        unprocessed = handler.get_unprocessed_feedback()
        assert len(unprocessed) == 1
        assert unprocessed[0].decision_id == "d2"


# ---------------------------------------------------------------------------
# initialize_schema
# ---------------------------------------------------------------------------


class TestInitializeSchema:
    def test_no_db_returns_false(self, handler: FeedbackHandler):
        result = handler.initialize_schema()
        assert result is False
        assert handler._initialized is True

    def test_with_db_executes_schema(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        h = FeedbackHandler(db_connection=mock_conn)
        result = h.initialize_schema()

        assert result is True
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


class TestClose:
    def test_close_with_connection(self):
        mock_conn = MagicMock()
        h = FeedbackHandler(db_connection=mock_conn)
        h.close()
        mock_conn.close.assert_called_once()
        assert h._db_connection is None

    def test_close_without_connection(self, handler: FeedbackHandler):
        handler.close()  # should not raise


# ---------------------------------------------------------------------------
# publisher property
# ---------------------------------------------------------------------------


class TestPublisherProperty:
    def test_publisher_getter_setter(self, handler: FeedbackHandler):
        pub = MagicMock()
        handler._publisher = pub
        assert handler._publisher is pub

    def test_publisher_deleter(self, handler: FeedbackHandler):
        handler._publisher = MagicMock()
        del handler._publisher
        assert handler._publisher is None


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------


class TestModuleFunctions:
    def test_get_feedback_handler_singleton(self):
        import enhanced_agent_bus.feedback_handler.handler as mod

        mod._feedback_handler = None
        h1 = get_feedback_handler()
        h2 = get_feedback_handler()
        assert h1 is h2
        mod._feedback_handler = None  # cleanup

    def test_submit_feedback_with_dict(self):
        import enhanced_agent_bus.feedback_handler.handler as mod

        mod._feedback_handler = None
        resp = submit_feedback(
            {
                "decision_id": "d-dict",
                "feedback_type": "positive",
            }
        )
        assert resp.status == "accepted"
        mod._feedback_handler = None

    def test_get_feedback_for_decision(self):
        import enhanced_agent_bus.feedback_handler.handler as mod

        mod._feedback_handler = None
        submit_feedback(_make_event(decision_id="lookup-me"))
        results = get_feedback_for_decision("lookup-me")
        assert len(results) == 1
        mod._feedback_handler = None
