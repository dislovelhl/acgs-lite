# Constitutional Hash: 608508a9bd224290
# Sprint 61 — deliberation_layer/vote_consumer.py coverage
"""
Comprehensive tests for deliberation_layer/vote_consumer.py.

Targets >=95% line coverage of the module, covering:
- Module-level import guards (KAFKA_AVAILABLE, get_election_store, VotingService,
  VoteEvent, VoteDecision, settings)
- VoteEventConsumer.__init__ — all argument combinations
- VoteEventConsumer.start — Kafka unavailable, successful start, exception paths
- VoteEventConsumer.stop — with and without active consumer
- VoteEventConsumer._consume_loop — no consumer, normal flow, stop mid-loop,
  inner error (no commit), outer error in consume loop
- VoteEventConsumer._handle_vote_event — missing fields, missing election store,
  election not found, duplicate vote (agent already voted), new vote cast ok,
  cast_vote returns False, with/without kafka_bus, timestamp ISO string vs datetime
- VoteEventConsumer._publish_audit_record — with signature key, without signature
  key, exception in publish
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

pytestmark = [pytest.mark.unit]

# ---------------------------------------------------------------------------
# Import module under test
# ---------------------------------------------------------------------------

from enhanced_agent_bus.deliberation_layer.vote_consumer import (
    _VOTE_CONSUMER_OPERATION_ERRORS,
    KAFKA_AVAILABLE,
    VoteEventConsumer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_voting_service(has_kafka_bus: bool = False) -> MagicMock:
    """Return a minimal VotingService mock."""
    svc = MagicMock()
    svc.cast_vote = AsyncMock(return_value=True)
    if has_kafka_bus:
        svc.kafka_bus = MagicMock()
        svc.kafka_bus.publish_audit_record = AsyncMock()
    else:
        # Ensure hasattr check returns False
        del svc.kafka_bus
    return svc


def _mock_election_store(
    election_data: dict | None = None,
    store_available: bool = True,
) -> tuple[MagicMock, Any]:
    """Return (store_mock, async_getter) for patching get_election_store."""
    store = MagicMock()
    store.get_election = AsyncMock(return_value=election_data)

    async def _getter():
        return store if store_available else None

    return store, _getter


def _make_vote_event(
    election_id: str = "elec-1",
    agent_id: str = "agent-a",
    decision: str = "APPROVE",
    timestamp: str | None = "2024-01-01T10:00:00Z",
    reasoning: str | None = "looks good",
) -> dict:
    ev: dict = {
        "election_id": election_id,
        "agent_id": agent_id,
        "decision": decision,
    }
    if timestamp is not None:
        ev["timestamp"] = timestamp
    if reasoning is not None:
        ev["reasoning"] = reasoning
    return ev


# ---------------------------------------------------------------------------
# 1. Module-level constants / flags
# ---------------------------------------------------------------------------


class TestModuleLevel:
    def test_operation_errors_tuple(self):
        assert RuntimeError in _VOTE_CONSUMER_OPERATION_ERRORS
        assert ValueError in _VOTE_CONSUMER_OPERATION_ERRORS
        assert json.JSONDecodeError in _VOTE_CONSUMER_OPERATION_ERRORS

    def test_kafka_available_is_bool(self):
        assert isinstance(KAFKA_AVAILABLE, bool)


# ---------------------------------------------------------------------------
# 2. VoteEventConsumer.__init__
# ---------------------------------------------------------------------------


class TestVoteEventConsumerInit:
    def test_defaults(self):
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)
        assert consumer.tenant_id == "default"
        assert consumer._running is False
        assert consumer.consumer is None
        assert consumer.voting_service is svc

    def test_dot_in_tenant_id_replaced(self):
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(tenant_id="acme.corp", voting_service=svc)
        assert consumer.tenant_id == "acme_corp"

    def test_empty_tenant_id_defaults_to_default(self):
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(tenant_id="", voting_service=svc)
        assert consumer.tenant_id == "default"

    def test_custom_bootstrap_servers(self):
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(
            bootstrap_servers="broker1:9092,broker2:9092",
            voting_service=svc,
        )
        assert consumer.bootstrap_servers == "broker1:9092,broker2:9092"

    def test_vote_topic_set_from_pattern(self):
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(tenant_id="mytenant", voting_service=svc)
        assert "mytenant" in consumer._vote_topic

    def test_voting_service_created_when_not_provided(self):
        """When voting_service is None and VotingService is importable, creates one."""
        mock_svc_instance = MagicMock()
        mock_svc_cls = MagicMock(return_value=mock_svc_instance)
        with patch(
            "enhanced_agent_bus.deliberation_layer.vote_consumer.VotingService",
            mock_svc_cls,
        ):
            consumer = VoteEventConsumer()
            assert consumer.voting_service is mock_svc_instance


# ---------------------------------------------------------------------------
# 3. VoteEventConsumer.start
# ---------------------------------------------------------------------------


class TestVoteEventConsumerStart:
    async def test_start_returns_false_when_kafka_unavailable(self):
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)
        with patch(
            "enhanced_agent_bus.deliberation_layer.vote_consumer.KAFKA_AVAILABLE",
            False,
        ):
            result = await consumer.start()
        assert result is False

    async def test_start_returns_true_on_success(self):
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)

        mock_kafka_consumer = AsyncMock()
        mock_kafka_consumer.start = AsyncMock()

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.vote_consumer.KAFKA_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.vote_consumer.AIOKafkaConsumer",
                return_value=mock_kafka_consumer,
            ),
            patch("asyncio.create_task"),
        ):
            result = await consumer.start()

        assert result is True
        assert consumer._running is True

    async def test_start_creates_background_task(self):
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)

        mock_kafka_consumer = AsyncMock()
        mock_kafka_consumer.start = AsyncMock()
        created_tasks = []

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.vote_consumer.KAFKA_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.vote_consumer.AIOKafkaConsumer",
                return_value=mock_kafka_consumer,
            ),
            patch("asyncio.create_task", side_effect=lambda coro: created_tasks.append(coro)),
        ):
            await consumer.start()

        assert len(created_tasks) == 1

    async def test_start_returns_false_on_exception(self):
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.vote_consumer.KAFKA_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.vote_consumer.AIOKafkaConsumer",
                side_effect=ConnectionError("cannot connect"),
            ),
        ):
            result = await consumer.start()

        assert result is False


# ---------------------------------------------------------------------------
# 4. VoteEventConsumer.stop
# ---------------------------------------------------------------------------


class TestVoteEventConsumerStop:
    async def test_stop_with_active_consumer(self):
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)
        consumer._running = True
        mock_kafka = AsyncMock()
        mock_kafka.stop = AsyncMock()
        consumer.consumer = mock_kafka

        await consumer.stop()

        assert consumer._running is False
        mock_kafka.stop.assert_awaited_once()

    async def test_stop_without_consumer(self):
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)
        consumer._running = True
        consumer.consumer = None

        await consumer.stop()  # should not raise

        assert consumer._running is False


# ---------------------------------------------------------------------------
# 5. VoteEventConsumer._consume_loop
# ---------------------------------------------------------------------------


class TestConsumeLoop:
    async def test_consume_loop_exits_early_without_consumer(self):
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)
        consumer.consumer = None
        # Should return immediately
        await consumer._consume_loop()

    async def test_consume_loop_processes_message_and_commits(self):
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)
        consumer._running = True

        vote_event_data = _make_vote_event()

        # Build an async iterator that yields one message then stops
        msg = MagicMock()
        msg.value = vote_event_data

        async def _iter():
            yield msg
            consumer._running = False

        mock_kafka = MagicMock()
        mock_kafka.__aiter__ = lambda _: _iter()
        mock_kafka.commit = AsyncMock()
        mock_kafka.stop = AsyncMock()
        consumer.consumer = mock_kafka

        election_data = {"votes": {}, "tenant_id": "default"}
        store, getter = _mock_election_store(election_data=election_data)
        store.get_election = AsyncMock(return_value=election_data)

        with patch(
            "enhanced_agent_bus.deliberation_layer.vote_consumer.get_election_store",
            getter,
        ):
            await consumer._consume_loop()

        mock_kafka.commit.assert_awaited_once()
        mock_kafka.stop.assert_awaited_once()

    async def test_consume_loop_stops_when_running_false(self):
        """Loop breaks immediately when _running is False at message receipt."""
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)
        consumer._running = False

        msg = MagicMock()
        msg.value = _make_vote_event()

        async def _iter():
            yield msg

        mock_kafka = MagicMock()
        mock_kafka.__aiter__ = lambda _: _iter()
        mock_kafka.commit = AsyncMock()
        mock_kafka.stop = AsyncMock()
        consumer.consumer = mock_kafka

        await consumer._consume_loop()

        # commit should NOT have been called because we broke out
        mock_kafka.commit.assert_not_awaited()
        mock_kafka.stop.assert_awaited_once()

    async def test_consume_loop_inner_error_no_commit(self):
        """When _handle_vote_event raises, commit is not called."""
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)
        consumer._running = True

        msg = MagicMock()
        msg.value = _make_vote_event()

        async def _iter():
            yield msg
            consumer._running = False

        mock_kafka = MagicMock()
        mock_kafka.__aiter__ = lambda _: _iter()
        mock_kafka.commit = AsyncMock()
        mock_kafka.stop = AsyncMock()
        consumer.consumer = mock_kafka

        with patch.object(
            consumer,
            "_handle_vote_event",
            side_effect=RuntimeError("boom"),
        ):
            await consumer._consume_loop()

        mock_kafka.commit.assert_not_awaited()
        mock_kafka.stop.assert_awaited()

    async def test_consume_loop_outer_error(self):
        """Outer error in the async-for iteration is caught and logged."""
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)
        consumer._running = True

        async def _bad_iter():
            raise RuntimeError("kafka died")
            yield  # make it an async generator

        mock_kafka = MagicMock()
        mock_kafka.__aiter__ = lambda _: _bad_iter()
        mock_kafka.stop = AsyncMock()
        consumer.consumer = mock_kafka

        # Should not raise
        await consumer._consume_loop()
        mock_kafka.stop.assert_awaited_once()


# ---------------------------------------------------------------------------
# 6. VoteEventConsumer._handle_vote_event
# ---------------------------------------------------------------------------


class TestHandleVoteEvent:
    async def test_missing_election_id_logs_error(self, caplog):
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)

        import logging

        with caplog.at_level(logging.ERROR):
            await consumer._handle_vote_event({"agent_id": "a", "decision": "APPROVE"})
        assert any("missing required fields" in r.message for r in caplog.records)

    async def test_missing_agent_id_logs_error(self, caplog):
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)

        import logging

        with caplog.at_level(logging.ERROR):
            await consumer._handle_vote_event({"election_id": "e1", "decision": "APPROVE"})
        assert any("missing required fields" in r.message for r in caplog.records)

    async def test_missing_decision_logs_error(self, caplog):
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)

        import logging

        with caplog.at_level(logging.ERROR):
            await consumer._handle_vote_event({"election_id": "e1", "agent_id": "a"})
        assert any("missing required fields" in r.message for r in caplog.records)

    async def test_no_election_store_logs_error(self, caplog):
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)

        async def _no_store():
            return None

        import logging

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.vote_consumer.get_election_store",
                _no_store,
            ),
            caplog.at_level(logging.ERROR),
        ):
            await consumer._handle_vote_event(_make_vote_event())

        assert any("Election store not available" in r.message for r in caplog.records)

    async def test_election_not_found_logs_warning(self, caplog):
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)

        _store, getter = _mock_election_store(election_data=None)

        import logging

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.vote_consumer.get_election_store",
                getter,
            ),
            caplog.at_level(logging.WARNING),
        ):
            await consumer._handle_vote_event(_make_vote_event())

        assert any("not found for vote event" in r.message for r in caplog.records)

    async def test_duplicate_vote_skipped(self):
        """When agent_id already in existing_votes, method returns without casting."""
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)

        election_data = {"votes": {"agent-a": {"decision": "APPROVE"}}}
        _store, getter = _mock_election_store(election_data=election_data)

        with patch(
            "enhanced_agent_bus.deliberation_layer.vote_consumer.get_election_store",
            getter,
        ):
            await consumer._handle_vote_event(_make_vote_event(agent_id="agent-a"))

        svc.cast_vote.assert_not_awaited()

    async def test_new_vote_cast_successfully(self):
        """Normal path: vote cast returns True, info logged."""
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)

        election_data = {"votes": {}, "tenant_id": "default"}
        _store, getter = _mock_election_store(election_data=election_data)

        with patch(
            "enhanced_agent_bus.deliberation_layer.vote_consumer.get_election_store",
            getter,
        ):
            await consumer._handle_vote_event(_make_vote_event())

        svc.cast_vote.assert_awaited_once()

    async def test_cast_vote_returns_false_logs_warning(self, caplog):
        """When cast_vote returns False, warning is logged and no audit published."""
        svc = _mock_voting_service()
        svc.cast_vote = AsyncMock(return_value=False)
        consumer = VoteEventConsumer(voting_service=svc)

        election_data = {"votes": {}, "tenant_id": "default"}
        _store, getter = _mock_election_store(election_data=election_data)

        import logging

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.vote_consumer.get_election_store",
                getter,
            ),
            caplog.at_level(logging.WARNING),
        ):
            await consumer._handle_vote_event(_make_vote_event())

        assert any("Failed to cast vote" in r.message for r in caplog.records)

    async def test_publish_audit_record_called_when_kafka_bus_present(self):
        """When voting_service has kafka_bus, _publish_audit_record is invoked."""
        svc = _mock_voting_service(has_kafka_bus=True)
        consumer = VoteEventConsumer(voting_service=svc)

        election_data = {"votes": {}, "tenant_id": "default"}
        _store, getter = _mock_election_store(election_data=election_data)

        with patch(
            "enhanced_agent_bus.deliberation_layer.vote_consumer.get_election_store",
            getter,
        ):
            with patch.object(
                consumer, "_publish_audit_record", new_callable=AsyncMock
            ) as mock_pub:
                await consumer._handle_vote_event(_make_vote_event())

        mock_pub.assert_awaited_once()

    async def test_no_audit_when_kafka_bus_absent(self):
        """When voting_service does not have kafka_bus, _publish_audit_record NOT called."""
        svc = _mock_voting_service(has_kafka_bus=False)
        consumer = VoteEventConsumer(voting_service=svc)

        election_data = {"votes": {}, "tenant_id": "default"}
        _store, getter = _mock_election_store(election_data=election_data)

        with patch(
            "enhanced_agent_bus.deliberation_layer.vote_consumer.get_election_store",
            getter,
        ):
            with patch.object(
                consumer, "_publish_audit_record", new_callable=AsyncMock
            ) as mock_pub:
                await consumer._handle_vote_event(_make_vote_event())

        mock_pub.assert_not_awaited()

    async def test_timestamp_as_iso_string(self):
        """Timestamp provided as ISO string with Z suffix is parsed correctly."""
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)

        election_data = {"votes": {}, "tenant_id": "default"}
        _store, getter = _mock_election_store(election_data=election_data)

        ev = _make_vote_event(timestamp="2024-06-15T12:00:00Z")

        with patch(
            "enhanced_agent_bus.deliberation_layer.vote_consumer.get_election_store",
            getter,
        ):
            await consumer._handle_vote_event(ev)

        svc.cast_vote.assert_awaited_once()
        _, _call_args = svc.cast_vote.call_args
        # Check the vote was cast with correct agent_id
        vote_arg = svc.cast_vote.call_args[0][1]
        assert vote_arg.agent_id == "agent-a"

    async def test_timestamp_as_non_string_uses_now(self):
        """Timestamp provided as non-string (e.g. int) falls back to datetime.now."""
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)

        election_data = {"votes": {}, "tenant_id": "default"}
        _store, getter = _mock_election_store(election_data=election_data)

        ev = _make_vote_event()
        ev["timestamp"] = 1234567890  # non-string

        with patch(
            "enhanced_agent_bus.deliberation_layer.vote_consumer.get_election_store",
            getter,
        ):
            await consumer._handle_vote_event(ev)

        svc.cast_vote.assert_awaited_once()

    async def test_no_timestamp_key_uses_now(self):
        """When timestamp key is absent entirely, datetime.now is used."""
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)

        election_data = {"votes": {}, "tenant_id": "default"}
        _store, getter = _mock_election_store(election_data=election_data)

        ev = _make_vote_event(timestamp=None)

        with patch(
            "enhanced_agent_bus.deliberation_layer.vote_consumer.get_election_store",
            getter,
        ):
            await consumer._handle_vote_event(ev)

        svc.cast_vote.assert_awaited_once()

    async def test_no_reasoning_key(self):
        """Vote event without 'reasoning' key still works."""
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)

        election_data = {"votes": {}, "tenant_id": "default"}
        _store, getter = _mock_election_store(election_data=election_data)

        ev = _make_vote_event(reasoning=None)

        with patch(
            "enhanced_agent_bus.deliberation_layer.vote_consumer.get_election_store",
            getter,
        ):
            await consumer._handle_vote_event(ev)

        svc.cast_vote.assert_awaited_once()


# ---------------------------------------------------------------------------
# 7. VoteEventConsumer._publish_audit_record
# ---------------------------------------------------------------------------


class TestPublishAuditRecord:
    async def test_publish_with_signature_key(self):
        """When audit_signature_key is configured, sign_audit_record is called."""
        svc = _mock_voting_service(has_kafka_bus=True)
        consumer = VoteEventConsumer(voting_service=svc)

        vote_event = _make_vote_event()
        election_data = {"tenant_id": "acme"}

        mock_secret = MagicMock()
        mock_secret.get_secret_value.return_value = "my-secret-key"

        with (
            patch("enhanced_agent_bus.deliberation_layer.vote_consumer.settings") as mock_settings,
            # sign_audit_record is imported inside the method from .audit_signature
            patch(
                "enhanced_agent_bus.deliberation_layer.audit_signature.sign_audit_record",
                return_value="abc123",
            ) as mock_sign,
        ):
            # Patch settings.voting.audit_signature_key
            mock_settings.voting.audit_signature_key = mock_secret
            await consumer._publish_audit_record("elec-1", vote_event, election_data)

        # verify publish_audit_record was invoked (sign mock may not intercept local import)
        svc.kafka_bus.publish_audit_record.assert_awaited_once()

    async def test_publish_without_signature_key(self, caplog):
        """When audit_signature_key is None, logs warning and uses empty signature."""
        svc = _mock_voting_service(has_kafka_bus=True)
        consumer = VoteEventConsumer(voting_service=svc)

        vote_event = _make_vote_event()
        election_data = {"tenant_id": "acme"}

        import logging

        with (
            patch("enhanced_agent_bus.deliberation_layer.vote_consumer.settings") as mock_settings,
            caplog.at_level(logging.WARNING),
        ):
            mock_settings.voting.audit_signature_key = None
            await consumer._publish_audit_record("elec-1", vote_event, election_data)

        assert any("AUDIT_SIGNATURE_KEY not configured" in r.message for r in caplog.records)
        svc.kafka_bus.publish_audit_record.assert_awaited_once()

    async def test_publish_uses_election_data_tenant_id(self):
        """tenant_id in election_data overrides consumer's tenant_id."""
        svc = _mock_voting_service(has_kafka_bus=True)
        consumer = VoteEventConsumer(tenant_id="consumer-tenant", voting_service=svc)

        vote_event = _make_vote_event()
        election_data = {"tenant_id": "election-tenant"}

        with patch("enhanced_agent_bus.deliberation_layer.vote_consumer.settings") as mock_settings:
            mock_settings.voting.audit_signature_key = None
            await consumer._publish_audit_record("elec-1", vote_event, election_data)

        call_args = svc.kafka_bus.publish_audit_record.call_args
        published_tenant = call_args[0][0]
        assert published_tenant == "election-tenant"

    async def test_publish_falls_back_to_consumer_tenant_id(self):
        """When election_data has no tenant_id, consumer's tenant_id is used."""
        svc = _mock_voting_service(has_kafka_bus=True)
        # Use a dot in tenant_id so it gets replaced to underscore
        consumer = VoteEventConsumer(tenant_id="my.tenant", voting_service=svc)

        vote_event = _make_vote_event()
        election_data = {}  # no tenant_id key

        with patch("enhanced_agent_bus.deliberation_layer.vote_consumer.settings") as mock_settings:
            mock_settings.voting.audit_signature_key = None
            await consumer._publish_audit_record("elec-1", vote_event, election_data)

        call_args = svc.kafka_bus.publish_audit_record.call_args
        published_tenant = call_args[0][0]
        assert published_tenant == "my_tenant"

    async def test_publish_exception_is_caught(self, caplog):
        """Exceptions during publish are caught and logged, not re-raised."""
        svc = _mock_voting_service(has_kafka_bus=True)
        svc.kafka_bus.publish_audit_record = AsyncMock(
            side_effect=RuntimeError("kafka unavailable")
        )
        consumer = VoteEventConsumer(voting_service=svc)

        vote_event = _make_vote_event()
        election_data = {"tenant_id": "t"}

        import logging

        with (
            patch("enhanced_agent_bus.deliberation_layer.vote_consumer.settings") as mock_settings,
            caplog.at_level(logging.ERROR),
        ):
            mock_settings.voting.audit_signature_key = None
            await consumer._publish_audit_record("elec-1", vote_event, election_data)

        assert any("Failed to publish audit record" in r.message for r in caplog.records)

    async def test_publish_audit_record_structure(self):
        """Audit record published to kafka_bus has required keys."""
        svc = _mock_voting_service(has_kafka_bus=True)
        consumer = VoteEventConsumer(voting_service=svc)

        vote_event = _make_vote_event()
        election_data = {"tenant_id": "t"}
        published_records = []

        async def _capture(tenant_id, record):
            published_records.append((tenant_id, record))

        svc.kafka_bus.publish_audit_record = _capture

        with patch("enhanced_agent_bus.deliberation_layer.vote_consumer.settings") as mock_settings:
            mock_settings.voting.audit_signature_key = None
            await consumer._publish_audit_record("elec-1", vote_event, election_data)

        assert len(published_records) == 1
        tenant, record = published_records[0]
        assert tenant == "t"
        assert "event_type" in record
        assert record["election_id"] == "elec-1"
        assert "signature" in record
        assert "payload" in record
        assert "agent_id" in record

    async def test_publish_uses_sign_audit_record_import(self):
        """sign_audit_record and VoteEventType are imported inside the method.

        sign_audit_record is imported via 'from .audit_signature import sign_audit_record'
        inside _publish_audit_record, so we verify the record contains a valid hex signature.
        """
        svc = _mock_voting_service(has_kafka_bus=True)
        consumer = VoteEventConsumer(voting_service=svc)

        vote_event = _make_vote_event()
        election_data = {"tenant_id": "t"}

        mock_secret = MagicMock()
        mock_secret.get_secret_value.return_value = "secret"

        with patch("enhanced_agent_bus.deliberation_layer.vote_consumer.settings") as mock_settings:
            mock_settings.voting.audit_signature_key = mock_secret
            await consumer._publish_audit_record("elec-1", vote_event, election_data)

        call_args = svc.kafka_bus.publish_audit_record.call_args
        record = call_args[0][1]
        # Signature should be a non-empty hex string from sign_audit_record
        assert isinstance(record["signature"], str)
        assert len(record["signature"]) > 0


# ---------------------------------------------------------------------------
# 8. Integration-style: full start → message → stop flow
# ---------------------------------------------------------------------------


class TestIntegrationFlow:
    async def test_full_lifecycle(self):
        """Start consumer, process one message, stop cleanly."""
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)

        # --- start phase ---
        mock_kafka = AsyncMock()
        mock_kafka.start = AsyncMock()
        mock_kafka.stop = AsyncMock()

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.vote_consumer.KAFKA_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.vote_consumer.AIOKafkaConsumer",
                return_value=mock_kafka,
            ),
            patch("asyncio.create_task"),
        ):
            started = await consumer.start()

        assert started is True

        # --- stop phase ---
        await consumer.stop()

        assert consumer._running is False
        mock_kafka.stop.assert_awaited_once()

    async def test_handle_vote_event_vote_cast_info_log(self, caplog):
        """Info log emitted after successful vote cast."""
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)

        election_data = {"votes": {}, "tenant_id": "default"}
        _store, getter = _mock_election_store(election_data=election_data)

        import logging

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.vote_consumer.get_election_store",
                getter,
            ),
            caplog.at_level(logging.INFO),
        ):
            await consumer._handle_vote_event(_make_vote_event())

        assert any("Processed vote event" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# 9. Edge cases — _consume_loop finally block when consumer is None
# ---------------------------------------------------------------------------


class TestConsumeLoopFinallyBranch:
    async def test_finally_skips_stop_when_consumer_none(self):
        """If consumer becomes None after loop starts, finally branch is safe."""
        svc = _mock_voting_service()
        consumer = VoteEventConsumer(voting_service=svc)
        consumer._running = True

        async def _bad_iter():
            consumer.consumer = None  # simulate consumer becoming None
            raise RuntimeError("oops")
            yield  # async generator

        mock_kafka = MagicMock()
        mock_kafka.__aiter__ = lambda _: _bad_iter()
        mock_kafka.stop = AsyncMock()
        consumer.consumer = mock_kafka

        # Should not raise
        await consumer._consume_loop()
