"""
Unit tests for healing actions in actions.py.
Constitutional Hash: 608508a9bd224290

TDD RED: Tests for GracefulRestarter, QuarantineManager, HITLRequestor, and
SupervisorNotifier. The latter three fail (RED) until actions.py provides them.

Tests mock the Agent Bus and HTTP interfaces; no real connections required.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

from enhanced_agent_bus.agent_health.actions import (
    GracefulRestarter,
    HITLRequestor,
    QuarantineManager,
    SupervisorNotifier,
)
from enhanced_agent_bus.agent_health.models import (
    AgentHealthRecord,
    AgentHealthThresholds,
    AutonomyTier,
    HealingAction,
    HealingActionType,
    HealingTrigger,
    HealthState,
)
from enhanced_agent_bus.agent_health.store import AgentHealthStore

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

AGENT_ID = "test-agent-001"

# Patch target for asyncio.wait_for inside the actions module
_WAIT_FOR_TARGET = "enhanced_agent_bus.agent_health.actions.asyncio.wait_for"


def _thresholds(drain_timeout_seconds: int = 30) -> AgentHealthThresholds:
    return AgentHealthThresholds(drain_timeout_seconds=drain_timeout_seconds)


def _record(health_state: HealthState = HealthState.DEGRADED) -> AgentHealthRecord:
    return AgentHealthRecord(
        agent_id=AGENT_ID,
        health_state=health_state,
        consecutive_failure_count=5,
        memory_usage_pct=60.0,
        last_event_at=datetime.now(UTC),
        autonomy_tier=AutonomyTier.HUMAN_APPROVED,
    )


class _FakeBus:
    """Test double for the agent bus re-queue interface.

    Controls:
    - drain_duration: how long drain() awaits before returning
    - in_flight: messages returned by get_in_flight_messages()
    - requeue_calls: records every (message, headers) pair passed to requeue()
    """

    def __init__(
        self,
        in_flight: list[Any] | None = None,
        drain_duration: float = 0.0,
    ) -> None:
        self._in_flight = in_flight or []
        self._drain_duration = drain_duration
        self.requeue_calls: list[tuple[Any, dict[str, str]]] = []
        self.drain_called_for: list[str] = []

    async def drain(self, agent_id: str) -> None:
        """Simulate draining; sleeps for drain_duration to allow timeout testing."""
        self.drain_called_for.append(agent_id)
        await asyncio.sleep(self._drain_duration)

    async def get_in_flight_messages(self, agent_id: str) -> list[Any]:
        return list(self._in_flight)

    async def requeue(self, message: Any, headers: dict[str, str]) -> None:
        self.requeue_calls.append((message, headers))


def _make_store(record: AgentHealthRecord | None = None) -> AsyncMock:
    """Return an AsyncMock for AgentHealthStore, pre-loaded with an optional record."""
    store = AsyncMock(spec=AgentHealthStore)
    store.get_health_record.return_value = record or _record()
    store.upsert_health_record.return_value = None
    return store


# ---------------------------------------------------------------------------
# T016-AC1: GracefulRestarter stops accepting new messages before draining
# ---------------------------------------------------------------------------


class TestSetsRestartingStateBeforeDrain:
    """health_state → RESTARTING is written to the store before drain begins (AC1)."""

    async def test_health_state_set_to_restarting_before_drain(self) -> None:
        store = _make_store()
        drain_started = asyncio.Event()
        restarting_set_before_drain = False

        # Intercept store.upsert_health_record to capture RESTARTING write
        original_upsert = store.upsert_health_record

        async def _capturing_upsert(record: AgentHealthRecord) -> None:
            if record.health_state == HealthState.RESTARTING:
                nonlocal restarting_set_before_drain
                restarting_set_before_drain = not drain_started.is_set()

        store.upsert_health_record.side_effect = _capturing_upsert

        async def _slow_drain(agent_id: str) -> None:
            drain_started.set()
            await asyncio.sleep(0)

        bus = _FakeBus()
        bus.drain = _slow_drain  # type: ignore[assignment]

        restarter = GracefulRestarter(store=store, bus=bus)
        await restarter.execute(agent_id=AGENT_ID, thresholds=_thresholds())

        assert restarting_set_before_drain, (
            "RESTARTING must be written to the store before drain() is called"
        )

    async def test_upsert_called_with_restarting_state(self) -> None:
        store = _make_store()
        bus = _FakeBus()
        restarter = GracefulRestarter(store=store, bus=bus)
        await restarter.execute(agent_id=AGENT_ID, thresholds=_thresholds())

        written_states = [
            call_args.args[0].health_state
            for call_args in store.upsert_health_record.call_args_list
            if call_args.args
        ]
        assert HealthState.RESTARTING in written_states, (
            "upsert_health_record must be called with health_state=RESTARTING"
        )


# ---------------------------------------------------------------------------
# T016-AC2: Drain completes successfully within drain_timeout_seconds
# ---------------------------------------------------------------------------


class TestDrainCompletesWithinTimeout:
    """Drain completes → no requeue called; lifecycle ends cleanly (AC2)."""

    async def test_no_requeue_when_drain_succeeds(self) -> None:
        store = _make_store()
        bus = _FakeBus(in_flight=["msg-1", "msg-2"], drain_duration=0.0)
        restarter = GracefulRestarter(store=store, bus=bus)
        await restarter.execute(agent_id=AGENT_ID, thresholds=_thresholds(drain_timeout_seconds=5))

        assert bus.requeue_calls == [], (
            "requeue must NOT be called when drain completes within timeout"
        )

    async def test_drain_called_with_correct_agent_id(self) -> None:
        store = _make_store()
        bus = _FakeBus(drain_duration=0.0)
        restarter = GracefulRestarter(store=store, bus=bus)
        await restarter.execute(agent_id=AGENT_ID, thresholds=_thresholds())

        assert AGENT_ID in bus.drain_called_for, "drain() must be called with the correct agent_id"

    async def test_execute_returns_none_on_successful_drain(self) -> None:
        store = _make_store()
        bus = _FakeBus(drain_duration=0.0)
        restarter = GracefulRestarter(store=store, bus=bus)
        result = await restarter.execute(agent_id=AGENT_ID, thresholds=_thresholds())
        assert result is None


# ---------------------------------------------------------------------------
# T016-AC3: Force re-queue path on drain timeout (FR-005)
# ---------------------------------------------------------------------------


class TestDrainTimeoutRequeuesMessages:
    """On timeout: remaining in-flight messages are re-queued (AC3, FR-005)."""

    async def test_requeue_called_for_each_remaining_message_on_timeout(self) -> None:
        store = _make_store()
        messages = ["msg-alpha", "msg-beta", "msg-gamma"]
        bus = _FakeBus(in_flight=messages, drain_duration=0.0)
        restarter = GracefulRestarter(store=store, bus=bus)

        # Patch asyncio.wait_for to raise TimeoutError — simulates drain timeout
        with patch(_WAIT_FOR_TARGET, side_effect=asyncio.TimeoutError):
            await restarter.execute(
                agent_id=AGENT_ID,
                thresholds=_thresholds(),
            )

        requeued_messages = [msg for msg, _ in bus.requeue_calls]
        for msg in messages:
            assert msg in requeued_messages, f"Message {msg!r} must be re-queued on drain timeout"
        assert len(bus.requeue_calls) == len(messages)

    async def test_uses_asyncio_wait_for_for_timeout(self) -> None:
        """GracefulRestarter must use asyncio.wait_for internally (AC3).

        Verified by confirming requeue fires only on the timeout path, not the
        success path — a structural guarantee that wait_for semantics apply.
        """
        store = _make_store()
        bus_success = _FakeBus(in_flight=["msg-x"], drain_duration=0.0)
        restarter = GracefulRestarter(store=store, bus=bus_success)
        await restarter.execute(agent_id=AGENT_ID, thresholds=_thresholds())
        assert bus_success.requeue_calls == []

        # Force timeout path via patch
        bus_timeout = _FakeBus(in_flight=["msg-x"], drain_duration=0.0)
        restarter2 = GracefulRestarter(store=store, bus=bus_timeout)
        with patch(_WAIT_FOR_TARGET, side_effect=asyncio.TimeoutError):
            await restarter2.execute(
                agent_id=AGENT_ID,
                thresholds=_thresholds(),
            )
        assert len(bus_timeout.requeue_calls) == 1


# ---------------------------------------------------------------------------
# T016-AC4: Retry marker header is X-ACGS-Retry: true
# ---------------------------------------------------------------------------


class TestRetryMarkerHeader:
    """Requeued messages carry the X-ACGS-Retry: true header (AC4)."""

    async def test_requeued_messages_have_retry_header(self) -> None:
        store = _make_store()
        bus = _FakeBus(in_flight=["msg-1"], drain_duration=0.0)
        restarter = GracefulRestarter(store=store, bus=bus)
        with patch(_WAIT_FOR_TARGET, side_effect=asyncio.TimeoutError):
            await restarter.execute(agent_id=AGENT_ID, thresholds=_thresholds())

        assert bus.requeue_calls, "Expected at least one requeue call"
        _, headers = bus.requeue_calls[0]
        assert headers.get("X-ACGS-Retry") == "true", (
            "Requeued messages must carry X-ACGS-Retry: true header"
        )

    async def test_retry_header_present_on_all_requeued_messages(self) -> None:
        store = _make_store()
        messages = ["m1", "m2", "m3"]
        bus = _FakeBus(in_flight=messages, drain_duration=0.0)
        restarter = GracefulRestarter(store=store, bus=bus)
        with patch(_WAIT_FOR_TARGET, side_effect=asyncio.TimeoutError):
            await restarter.execute(agent_id=AGENT_ID, thresholds=_thresholds())

        for msg, headers in bus.requeue_calls:
            assert headers.get("X-ACGS-Retry") == "true", (
                f"Message {msg!r} must be requeued with X-ACGS-Retry: true"
            )

    async def test_retry_header_value_is_string_true(self) -> None:
        """Header value must be the string 'true', not boolean True."""
        store = _make_store()
        bus = _FakeBus(in_flight=["only-msg"], drain_duration=0.0)
        restarter = GracefulRestarter(store=store, bus=bus)
        with patch(_WAIT_FOR_TARGET, side_effect=asyncio.TimeoutError):
            await restarter.execute(agent_id=AGENT_ID, thresholds=_thresholds())
        _, headers = bus.requeue_calls[0]
        assert headers["X-ACGS-Retry"] == "true"
        assert isinstance(headers["X-ACGS-Retry"], str)


# ---------------------------------------------------------------------------
# T016-AC5: Completes lifecycle without raising when agent process is a mock
# ---------------------------------------------------------------------------


class TestLifecycleWithMockProcess:
    """GracefulRestarter completes without raising when backed by mocks (AC5)."""

    async def test_no_exception_raised_with_mock_store_and_bus(self) -> None:
        store = _make_store()
        bus = _FakeBus(drain_duration=0.0)
        restarter = GracefulRestarter(store=store, bus=bus)
        # Must not raise
        await restarter.execute(agent_id=AGENT_ID, thresholds=_thresholds())

    async def test_no_exception_on_timeout_path_with_mock(self) -> None:
        store = _make_store()
        bus = _FakeBus(in_flight=["msg"], drain_duration=0.0)
        restarter = GracefulRestarter(store=store, bus=bus)
        with patch(_WAIT_FOR_TARGET, side_effect=asyncio.TimeoutError):
            await restarter.execute(agent_id=AGENT_ID, thresholds=_thresholds())

    async def test_restart_callback_invoked_after_drain(self) -> None:
        """If a restart_callback is provided, it must be called after drain/requeue."""
        store = _make_store()
        bus = _FakeBus(drain_duration=0.0)
        callback_called = False

        async def _mock_restart() -> None:
            nonlocal callback_called
            callback_called = True

        restarter = GracefulRestarter(store=store, bus=bus, restart_callback=_mock_restart)
        await restarter.execute(agent_id=AGENT_ID, thresholds=_thresholds())
        assert callback_called, "restart_callback must be invoked after drain completes"

    async def test_restart_callback_invoked_after_timeout_requeue(self) -> None:
        """restart_callback fires even on the timeout/requeue path."""
        store = _make_store()
        bus = _FakeBus(in_flight=["msg"], drain_duration=0.0)
        callback_called = False

        async def _mock_restart() -> None:
            nonlocal callback_called
            callback_called = True

        restarter = GracefulRestarter(store=store, bus=bus, restart_callback=_mock_restart)
        with patch(_WAIT_FOR_TARGET, side_effect=asyncio.TimeoutError):
            await restarter.execute(agent_id=AGENT_ID, thresholds=_thresholds())
        assert callback_called

    async def test_no_exception_when_no_restart_callback(self) -> None:
        """GracefulRestarter works fine without a restart_callback."""
        store = _make_store()
        bus = _FakeBus(drain_duration=0.0)
        restarter = GracefulRestarter(store=store, bus=bus)
        # restart_callback defaults to None — must not raise
        await restarter.execute(agent_id=AGENT_ID, thresholds=_thresholds())


# ---------------------------------------------------------------------------
# T016-AC6: Bus re-queue interface is mocked; no real connection required
# ---------------------------------------------------------------------------


class TestNoBusConnectionRequired:
    """All tests use _FakeBus; no real Agent Bus connection is made (AC6)."""

    async def test_uses_injected_bus_not_real_connection(self) -> None:
        """GracefulRestarter accepts bus via constructor injection (no singletons)."""
        store = _make_store()
        bus = _FakeBus()
        # Constructing with an injected bus must succeed without network access
        restarter = GracefulRestarter(store=store, bus=bus)
        await restarter.execute(agent_id=AGENT_ID, thresholds=_thresholds())
        # Bus drain was called through the fake, not a real connection
        assert AGENT_ID in bus.drain_called_for


# ===========================================================================
# T018: QuarantineManager, HITLRequestor, SupervisorNotifier
# ===========================================================================

# ---------------------------------------------------------------------------
# Helpers for new action tests
# ---------------------------------------------------------------------------

_ACTIONS_MODULE = "enhanced_agent_bus.agent_health.actions"
_HTTPX_MODULE = f"{_ACTIONS_MODULE}.httpx"


def _make_healing_action(agent_id: str = AGENT_ID) -> HealingAction:
    return HealingAction(
        agent_id=agent_id,
        trigger=HealingTrigger.FAILURE_LOOP,
        action_type=HealingActionType.HITL_REQUEST,
        tier_determined_by=AutonomyTier.ADVISORY,
        initiated_at=datetime.now(UTC),
        audit_event_id="audit-001",
    )


def _make_httpx_response(status_code: int, json_data: dict[str, Any]) -> MagicMock:
    """Build a fake httpx response object."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


class _FakeQuarantineBus:
    """Test double for the AgentBusGateway with reroute_agent support."""

    def __init__(self, reroute_delay: float = 0.0) -> None:
        self._reroute_delay = reroute_delay
        self.reroute_calls: list[str] = []

    async def drain(self, agent_id: str) -> None:  # pragma: no cover
        pass

    async def get_in_flight_messages(self, agent_id: str) -> list[Any]:  # pragma: no cover
        return []

    async def requeue(self, message: Any, headers: dict[str, str]) -> None:  # pragma: no cover
        pass

    async def reroute_agent(self, agent_id: str) -> None:
        self.reroute_calls.append(agent_id)
        if self._reroute_delay:
            await asyncio.sleep(self._reroute_delay)


# ---------------------------------------------------------------------------
# QuarantineManager tests (T018-AC1, AC2, AC3)
# ---------------------------------------------------------------------------


class TestQuarantineManagerSetsQuarantinedState:
    """QuarantineManager sets health_state=QUARANTINED in the store (AC1)."""

    async def test_upsert_called_with_quarantined_state(self) -> None:
        store = _make_store()
        bus = _FakeQuarantineBus()
        manager = QuarantineManager(bus=bus)
        await manager.execute(agent_id=AGENT_ID, store=store)

        written_states = [
            call_args.args[0].health_state
            for call_args in store.upsert_health_record.call_args_list
            if call_args.args
        ]
        assert HealthState.QUARANTINED in written_states, (
            "upsert_health_record must be called with health_state=QUARANTINED"
        )

    async def test_returns_none(self) -> None:
        store = _make_store()
        bus = _FakeQuarantineBus()
        manager = QuarantineManager(bus=bus)
        result = await manager.execute(agent_id=AGENT_ID, store=store)
        assert result is None


class TestQuarantineManagerSignalsBusReroute:
    """QuarantineManager signals the bus to re-route messages (AC2, FR-006)."""

    async def test_reroute_agent_called_with_correct_agent_id(self) -> None:
        store = _make_store()
        bus = _FakeQuarantineBus()
        manager = QuarantineManager(bus=bus)
        await manager.execute(agent_id=AGENT_ID, store=store)

        assert AGENT_ID in bus.reroute_calls, (
            "reroute_agent() must be called with the correct agent_id"
        )

    async def test_reroute_completes_within_500ms(self) -> None:
        """Entire execute() must complete within the 500ms FR-006 budget."""
        store = _make_store()
        bus = _FakeQuarantineBus(reroute_delay=0.0)
        manager = QuarantineManager(bus=bus)
        # asyncio.wait_for raises TimeoutError if it takes > 500ms
        await asyncio.wait_for(
            manager.execute(agent_id=AGENT_ID, store=store),
            timeout=0.5,
        )

    async def test_quarantine_set_before_reroute(self) -> None:
        """health_state=QUARANTINED must be written to store before reroute is called."""
        store = _make_store()
        quarantine_set_before_reroute = False
        upsert_call_count = 0

        async def _capturing_upsert(record: AgentHealthRecord) -> None:
            nonlocal upsert_call_count
            if record.health_state == HealthState.QUARANTINED:
                upsert_call_count += 1

        store.upsert_health_record.side_effect = _capturing_upsert

        class _OrderTrackingBus(_FakeQuarantineBus):
            async def reroute_agent(self, agent_id: str) -> None:
                nonlocal quarantine_set_before_reroute
                quarantine_set_before_reroute = upsert_call_count > 0
                await super().reroute_agent(agent_id)

        bus = _OrderTrackingBus()
        manager = QuarantineManager(bus=bus)
        await manager.execute(agent_id=AGENT_ID, store=store)

        assert quarantine_set_before_reroute, (
            "QUARANTINED must be written to the store before reroute_agent() is called"
        )


# ---------------------------------------------------------------------------
# HITLRequestor tests (T018-AC4, AC5)
# ---------------------------------------------------------------------------


class TestHITLRequestorPostsToHITLService:
    """HITLRequestor sends HTTP POST to hitl_approvals service (AC4)."""

    async def test_post_called_when_no_existing_review(self) -> None:
        action = _make_healing_action()
        no_existing = _make_httpx_response(200, {"items": []})
        created = _make_httpx_response(201, {"review_id": "rev-new-001"})

        with patch(_HTTPX_MODULE) as mock_httpx:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=no_existing)
            mock_client.post = AsyncMock(return_value=created)
            mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)

            requestor = HITLRequestor(hitl_service_url="http://test-hitl:8002")
            result = await requestor.execute(
                agent_id=AGENT_ID,
                trigger=HealingTrigger.FAILURE_LOOP,
                action=action,
            )

        mock_client.post.assert_called_once()
        assert result == "rev-new-001"

    async def test_post_body_includes_agent_id_and_trigger(self) -> None:
        action = _make_healing_action()
        no_existing = _make_httpx_response(200, {"items": []})
        created = _make_httpx_response(201, {"review_id": "rev-new-002"})

        with patch(_HTTPX_MODULE) as mock_httpx:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=no_existing)
            mock_client.post = AsyncMock(return_value=created)
            mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)

            requestor = HITLRequestor(hitl_service_url="http://test-hitl:8002")
            await requestor.execute(
                agent_id=AGENT_ID,
                trigger=HealingTrigger.FAILURE_LOOP,
                action=action,
            )

        _, kwargs = mock_client.post.call_args
        body = kwargs.get("json", {})
        assert body.get("agent_id") == AGENT_ID, "POST body must include agent_id"
        assert body.get("trigger") == HealingTrigger.FAILURE_LOOP.value, (
            "POST body must include trigger"
        )


class TestHITLRequestorDeduplication:
    """HITLRequestor updates existing review rather than creating a duplicate (AC5)."""

    async def test_updates_existing_review_instead_of_posting_new(self) -> None:
        action = _make_healing_action()
        existing = _make_httpx_response(200, {"items": [{"review_id": "rev-existing-001"}]})
        updated = _make_httpx_response(200, {"review_id": "rev-existing-001"})

        with patch(_HTTPX_MODULE) as mock_httpx:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=existing)
            mock_client.patch = AsyncMock(return_value=updated)
            mock_client.post = AsyncMock()  # must NOT be called
            mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)

            requestor = HITLRequestor(hitl_service_url="http://test-hitl:8002")
            result = await requestor.execute(
                agent_id=AGENT_ID,
                trigger=HealingTrigger.FAILURE_LOOP,
                action=action,
            )

        mock_client.post.assert_not_called()
        mock_client.patch.assert_called_once()
        assert result == "rev-existing-001"

    async def test_returns_existing_review_id_on_deduplication(self) -> None:
        action = _make_healing_action()
        existing = _make_httpx_response(200, {"items": [{"review_id": "rev-dedup-999"}]})
        updated = _make_httpx_response(200, {"review_id": "rev-dedup-999"})

        with patch(_HTTPX_MODULE) as mock_httpx:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=existing)
            mock_client.patch = AsyncMock(return_value=updated)
            mock_client.post = AsyncMock()
            mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)

            requestor = HITLRequestor(hitl_service_url="http://test-hitl:8002")
            result = await requestor.execute(
                agent_id=AGENT_ID,
                trigger=HealingTrigger.MEMORY_EXHAUSTION,
                action=action,
            )

        assert result == "rev-dedup-999"


# ---------------------------------------------------------------------------
# SupervisorNotifier tests (T018-AC6)
# ---------------------------------------------------------------------------


class TestSupervisorNotifierPostsToSupervisor:
    """SupervisorNotifier sends HTTP POST to supervisor endpoint (AC6)."""

    async def test_post_called_with_supervisor_url(self) -> None:
        posted = _make_httpx_response(200, {"notification_id": "notif-001"})

        with patch(_HTTPX_MODULE) as mock_httpx:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=posted)
            mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)

            notifier = SupervisorNotifier(supervisor_url="http://test-supervisor:8003")
            await notifier.notify(
                agent_id=AGENT_ID,
                tier=AutonomyTier.BOUNDED,
                trigger=HealingTrigger.FAILURE_LOOP,
            )

        mock_client.post.assert_called_once()

    async def test_post_body_includes_agent_id_tier_and_trigger(self) -> None:
        posted = _make_httpx_response(200, {"notification_id": "notif-002"})

        with patch(_HTTPX_MODULE) as mock_httpx:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=posted)
            mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)

            notifier = SupervisorNotifier(supervisor_url="http://test-supervisor:8003")
            await notifier.notify(
                agent_id=AGENT_ID,
                tier=AutonomyTier.BOUNDED,
                trigger=HealingTrigger.MEMORY_EXHAUSTION,
            )

        _, kwargs = mock_client.post.call_args
        body = kwargs.get("json", {})
        assert body.get("agent_id") == AGENT_ID, "POST body must include agent_id"
        assert body.get("tier") == AutonomyTier.BOUNDED.value, "POST body must include tier"
        assert body.get("trigger") == HealingTrigger.MEMORY_EXHAUSTION.value, (
            "POST body must include trigger"
        )

    async def test_returns_none(self) -> None:
        posted = _make_httpx_response(200, {"notification_id": "notif-003"})

        with patch(_HTTPX_MODULE) as mock_httpx:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=posted)
            mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)

            notifier = SupervisorNotifier(supervisor_url="http://test-supervisor:8003")
            result = await notifier.notify(
                agent_id=AGENT_ID,
                tier=AutonomyTier.BOUNDED,
                trigger=HealingTrigger.FAILURE_LOOP,
            )

        assert result is None

    async def test_reads_supervisor_url_from_env_when_not_provided(self) -> None:
        """SupervisorNotifier falls back to SUPERVISOR_URL env var."""
        posted = _make_httpx_response(200, {"notification_id": "notif-004"})

        with patch(_HTTPX_MODULE) as mock_httpx:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=posted)
            mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch.dict("os.environ", {"SUPERVISOR_URL": "http://env-supervisor:9000"}):
                # supervisor_url not passed — should use env var
                notifier = SupervisorNotifier()
                await notifier.notify(
                    agent_id=AGENT_ID,
                    tier=AutonomyTier.BOUNDED,
                    trigger=HealingTrigger.FAILURE_LOOP,
                )

        call_args_url = mock_client.post.call_args[0][0]
        assert "env-supervisor:9000" in call_args_url
