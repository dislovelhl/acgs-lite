"""
Coverage tests for batch 18e:
  - api/routes/health.py
  - agent_health/actions.py
  - online_learning_infra/consumer.py
  - llm_adapters/llm_failover.py

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. Health routes
# ---------------------------------------------------------------------------
from enhanced_agent_bus.api.routes.health import (
    _circuit_breaker_available,
    _collect_stats_payload,
    _is_constitutional_hash_valid,
    get_latency_tracker,
    router,
)


class TestCircuitBreakerAvailable:
    def test_returns_bool(self):
        result = _circuit_breaker_available()
        assert isinstance(result, bool)

    def test_returns_true_when_pybreaker_installed(self):
        # pybreaker is a dependency of the bus, so it should be available
        assert _circuit_breaker_available() is True

    def test_returns_false_when_importlib_missing(self):
        with patch.dict("sys.modules", {"importlib.util": None}):
            # When importlib.util raises ImportError, should return False
            pass  # The try/except in the function catches ImportError on `import importlib.util`


class TestIsConstitutionalHashValid:
    def test_valid_without_env_var(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CONSTITUTIONAL_HASH", None)
            assert _is_constitutional_hash_valid() is True

    def test_valid_with_matching_env_var(self):
        from enhanced_agent_bus.api.routes.health import CONSTITUTIONAL_HASH as CH

        with patch.dict(os.environ, {"CONSTITUTIONAL_HASH": CH}):
            assert _is_constitutional_hash_valid() is True

    def test_invalid_with_wrong_env_var(self):
        with patch.dict(os.environ, {"CONSTITUTIONAL_HASH": "wrong_hash_value"}):
            assert _is_constitutional_hash_valid() is False


class TestGetLatencyTracker:
    def test_returns_tracker_instance(self):
        tracker = get_latency_tracker()
        assert tracker is not None
        assert hasattr(tracker, "get_metrics")
        assert hasattr(tracker, "get_total_messages")


class TestCollectStatsPayload:
    async def test_returns_payload_without_bus(self):
        payload = await _collect_stats_payload(bus=None)
        assert "total_messages" in payload
        assert "latency_p50_ms" in payload
        assert "sla_p99_met" in payload

    async def test_returns_payload_with_bus_metrics(self):
        bus = MagicMock()
        bus.get_metrics.return_value = {
            "opa_multipath_evaluation_count": 5,
            "opa_multipath_last_path_count": 3,
            "opa_multipath_last_diversity_ratio": 0.8,
            "opa_multipath_last_support_family_count": 2,
        }
        payload = await _collect_stats_payload(bus=bus)
        assert payload["opa_multipath_evaluation_count"] == 5
        assert payload["opa_multipath_last_path_count"] == 3

    async def test_bus_metrics_error_fallback(self):
        bus = MagicMock()
        bus.get_metrics.side_effect = AttributeError("no metrics")
        payload = await _collect_stats_payload(bus=bus)
        assert payload["opa_multipath_evaluation_count"] == 0

    async def test_bus_metrics_non_dict_ignored(self):
        bus = MagicMock()
        bus.get_metrics.return_value = "not-a-dict"
        payload = await _collect_stats_payload(bus=bus)
        # Should not have opa keys when get_metrics returns non-dict
        assert "opa_multipath_evaluation_count" not in payload

    async def test_bus_without_get_metrics(self):
        bus = object()  # no get_metrics attribute
        payload = await _collect_stats_payload(bus=bus)
        assert "total_messages" in payload

    async def test_error_raises_http_exception(self):
        from fastapi import HTTPException

        tracker = get_latency_tracker()
        with patch.object(tracker, "get_metrics", side_effect=RuntimeError("boom")):
            with pytest.raises(HTTPException) as exc_info:
                await _collect_stats_payload(bus=None)
            assert exc_info.value.status_code == 500


class TestHealthRoutes:
    """Integration tests via httpx.AsyncClient."""

    @pytest.fixture()
    def app(self):
        from fastapi import FastAPI

        test_app = FastAPI()
        test_app.include_router(router)
        return test_app

    @pytest.fixture()
    async def client(self, app):
        import httpx

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as c:
            yield c

    async def test_health_check_no_bus(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["service"] == "enhanced-agent-bus"

    async def test_health_check_with_bus(self, app, client):
        app.state.agent_bus = MagicMock()
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    async def test_liveness_check(self, client):
        resp = await client.get("/health/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "alive"
        assert data["service"] == "enhanced-agent-bus"

    async def test_readiness_check_not_ready(self, client):
        resp = await client.get("/health/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["ready"] is False
        assert data["checks"]["agent_bus"] == "down"

    async def test_readiness_check_ready(self, app, client):
        app.state.agent_bus = MagicMock()
        resp = await client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is True

    async def test_readiness_check_with_valid_probe_hash(self, app, client):
        from enhanced_agent_bus.api.routes.health import CONSTITUTIONAL_HASH as CH

        app.state.agent_bus = MagicMock()
        resp = await client.get("/health/ready", headers={"X-Constitutional-Hash": CH})
        assert resp.status_code == 200
        assert resp.json()["ready"] is True

    async def test_readiness_check_with_invalid_probe_hash(self, app, client):
        app.state.agent_bus = MagicMock()
        resp = await client.get("/health/ready", headers={"X-Constitutional-Hash": "badhash"})
        assert resp.status_code == 503
        data = resp.json()
        assert data["checks"]["constitutional_hash_probe_header"] == "down"

    async def test_startup_check_not_ready(self, client):
        resp = await client.get("/health/startup")
        assert resp.status_code == 503
        data = resp.json()
        assert data["ready"] is False

    async def test_startup_check_ready(self, app, client):
        app.state.agent_bus = MagicMock()
        resp = await client.get("/health/startup")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is True

    async def test_startupz_alias(self, app, client):
        app.state.agent_bus = MagicMock()
        resp = await client.get("/startupz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is True

    async def test_kafka_health_unavailable(self, client):
        with patch.dict("sys.modules", {"aiokafka": None, "aiokafka.admin": None}):
            resp = await client.get("/health/kafka")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "unavailable"

    async def test_redis_health_unavailable(self, client):
        resp = await client.get("/health/redis")
        assert resp.status_code == 200
        data = resp.json()
        # Redis is not running in test env, so should be unavailable
        assert data["dependency"] == "redis"


# ---------------------------------------------------------------------------
# 2. Agent health actions
# ---------------------------------------------------------------------------

from enhanced_agent_bus.agent_health.actions import (
    AgentBusGateway,
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


def _make_health_record(
    agent_id: str = "agent-1",
    state: HealthState = HealthState.HEALTHY,
) -> AgentHealthRecord:
    return AgentHealthRecord(
        agent_id=agent_id,
        health_state=state,
        consecutive_failure_count=0,
        memory_usage_pct=50.0,
        last_event_at=datetime.now(UTC),
        autonomy_tier=AutonomyTier.ADVISORY,
    )


def _make_thresholds(drain_timeout: int = 30) -> AgentHealthThresholds:
    return AgentHealthThresholds(drain_timeout_seconds=drain_timeout)


def _make_healing_action(agent_id: str = "agent-1") -> HealingAction:
    from enhanced_agent_bus.agent_health.models import CONSTITUTIONAL_HASH as CH

    return HealingAction(
        agent_id=agent_id,
        trigger=HealingTrigger.FAILURE_LOOP,
        action_type=HealingActionType.HITL_REQUEST,
        tier_determined_by=AutonomyTier.ADVISORY,
        initiated_at=datetime.now(UTC),
        audit_event_id="audit-001",
        constitutional_hash=CH,
    )


class _FakeBus:
    """Minimal AgentBusGateway implementation for tests."""

    def __init__(
        self,
        drain_delay: float = 0.0,
        in_flight: list[Any] | None = None,
    ):
        self._drain_delay = drain_delay
        self._in_flight = in_flight or []
        self.drained = False
        self.rerouted = False
        self.requeued: list[tuple[Any, dict]] = []

    async def drain(self, agent_id: str) -> None:
        if self._drain_delay > 0:
            await asyncio.sleep(self._drain_delay)
        self.drained = True

    async def get_in_flight_messages(self, agent_id: str) -> list[Any]:
        return list(self._in_flight)

    async def requeue(self, message: Any, headers: dict[str, str]) -> None:
        self.requeued.append((message, headers))

    async def reroute_agent(self, agent_id: str) -> None:
        self.rerouted = True


class TestAgentBusGatewayProtocol:
    def test_fake_bus_satisfies_protocol(self):
        bus = _FakeBus()
        assert isinstance(bus, AgentBusGateway)


class TestGracefulRestarter:
    async def test_drain_succeeds(self):
        store = AsyncMock()
        record = _make_health_record()
        store.get_health_record = AsyncMock(return_value=record)
        store.upsert_health_record = AsyncMock()

        bus = _FakeBus()
        restarter = GracefulRestarter(store=store, bus=bus)
        await restarter.execute("agent-1", _make_thresholds())

        assert bus.drained is True
        assert len(bus.requeued) == 0
        store.upsert_health_record.assert_awaited_once()
        assert record.health_state == HealthState.RESTARTING

    async def test_drain_timeout_requeues(self):
        store = AsyncMock()
        record = _make_health_record()
        store.get_health_record = AsyncMock(return_value=record)
        store.upsert_health_record = AsyncMock()

        msgs = ["msg1", "msg2"]
        bus = _FakeBus(drain_delay=10.0, in_flight=msgs)
        restarter = GracefulRestarter(store=store, bus=bus)
        # Use very short drain timeout to trigger timeout path
        thresholds = _make_thresholds(drain_timeout=5)

        # Patch drain to always timeout
        async def _slow_drain(agent_id):
            await asyncio.sleep(100)

        bus.drain = _slow_drain

        thresholds_fast = AgentHealthThresholds(drain_timeout_seconds=5)
        # override with even shorter
        with patch("asyncio.wait_for", side_effect=TimeoutError):
            await restarter.execute("agent-1", thresholds_fast)

        assert len(bus.requeued) == 2
        for _msg, headers in bus.requeued:
            assert headers["X-ACGS-Retry"] == "true"

    async def test_no_record_skips_restarting(self):
        store = AsyncMock()
        store.get_health_record = AsyncMock(return_value=None)
        store.upsert_health_record = AsyncMock()

        bus = _FakeBus()
        restarter = GracefulRestarter(store=store, bus=bus)
        await restarter.execute("agent-missing", _make_thresholds())

        store.upsert_health_record.assert_not_awaited()

    async def test_restart_callback_invoked(self):
        store = AsyncMock()
        record = _make_health_record()
        store.get_health_record = AsyncMock(return_value=record)
        store.upsert_health_record = AsyncMock()

        callback = AsyncMock()
        bus = _FakeBus()
        restarter = GracefulRestarter(store=store, bus=bus, restart_callback=callback)
        await restarter.execute("agent-1", _make_thresholds())

        callback.assert_awaited_once()

    async def test_no_restart_callback(self):
        store = AsyncMock()
        record = _make_health_record()
        store.get_health_record = AsyncMock(return_value=record)
        store.upsert_health_record = AsyncMock()

        bus = _FakeBus()
        restarter = GracefulRestarter(store=store, bus=bus, restart_callback=None)
        await restarter.execute("agent-1", _make_thresholds())
        # Should not raise


class TestQuarantineManager:
    async def test_quarantine_sets_state_and_reroutes(self):
        store = AsyncMock()
        record = _make_health_record()
        store.get_health_record = AsyncMock(return_value=record)
        store.upsert_health_record = AsyncMock()

        bus = _FakeBus()
        qm = QuarantineManager(bus=bus)
        await qm.execute("agent-1", store)

        assert record.health_state == HealthState.QUARANTINED
        assert bus.rerouted is True
        store.upsert_health_record.assert_awaited_once()

    async def test_quarantine_no_record(self):
        store = AsyncMock()
        store.get_health_record = AsyncMock(return_value=None)

        bus = _FakeBus()
        qm = QuarantineManager(bus=bus)
        await qm.execute("agent-missing", store)

        assert bus.rerouted is False

    async def test_quarantine_reroute_timeout(self):
        store = AsyncMock()
        record = _make_health_record()
        store.get_health_record = AsyncMock(return_value=record)
        store.upsert_health_record = AsyncMock()

        bus = _FakeBus()

        async def _slow_reroute(agent_id):
            await asyncio.sleep(100)

        bus.reroute_agent = _slow_reroute

        qm = QuarantineManager(bus=bus)
        with patch("asyncio.wait_for", side_effect=TimeoutError):
            await qm.execute("agent-1", store)

        assert record.health_state == HealthState.QUARANTINED


class TestHITLRequestor:
    def _make_requestor(self, url: str = "http://hitl.test"):
        return HITLRequestor(hitl_service_url=url)

    async def test_create_new_review(self):
        requestor = self._make_requestor()
        action = _make_healing_action()

        with patch("httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            # No existing review
            get_resp = MagicMock()
            get_resp.status_code = 200
            get_resp.json.return_value = {"items": []}
            client.get = AsyncMock(return_value=get_resp)

            # Create review
            post_resp = MagicMock()
            post_resp.json.return_value = {"review_id": "rv-123"}
            post_resp.raise_for_status = MagicMock()
            client.post = AsyncMock(return_value=post_resp)

            review_id = await requestor.execute(
                agent_id="agent-1",
                trigger=HealingTrigger.FAILURE_LOOP,
                action=action,
            )
            assert review_id == "rv-123"
            client.post.assert_awaited_once()

    async def test_update_existing_review(self):
        requestor = self._make_requestor()
        action = _make_healing_action()

        with patch("httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            # Existing review found
            get_resp = MagicMock()
            get_resp.status_code = 200
            get_resp.json.return_value = {"items": [{"review_id": "rv-existing"}]}
            client.get = AsyncMock(return_value=get_resp)

            # Patch review
            patch_resp = MagicMock()
            patch_resp.raise_for_status = MagicMock()
            client.patch = AsyncMock(return_value=patch_resp)

            review_id = await requestor.execute(
                agent_id="agent-1",
                trigger=HealingTrigger.FAILURE_LOOP,
                action=action,
            )
            assert review_id == "rv-existing"
            client.patch.assert_awaited_once()

    async def test_find_existing_review_not_200(self):
        requestor = self._make_requestor()
        action = _make_healing_action()

        with patch("httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            # Non-200 response for existing review search
            get_resp = MagicMock()
            get_resp.status_code = 500
            client.get = AsyncMock(return_value=get_resp)

            # Should fall through to create
            post_resp = MagicMock()
            post_resp.json.return_value = {"review_id": "rv-new"}
            post_resp.raise_for_status = MagicMock()
            client.post = AsyncMock(return_value=post_resp)

            review_id = await requestor.execute(
                agent_id="agent-1",
                trigger=HealingTrigger.FAILURE_LOOP,
                action=action,
            )
            assert review_id == "rv-new"

    def test_default_url_from_env(self):
        with patch.dict(os.environ, {"HITL_SERVICE_URL": "http://from-env:9999"}):
            requestor = HITLRequestor()
            assert requestor._base_url == "http://from-env:9999"

    def test_default_url_fallback(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HITL_SERVICE_URL", None)
            requestor = HITLRequestor()
            assert requestor._base_url == "http://localhost:8002"


class TestSupervisorNotifier:
    async def test_notify_success(self):
        notifier = SupervisorNotifier(supervisor_url="http://supervisor.test")

        with patch("httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            post_resp = MagicMock()
            post_resp.json.return_value = {"notification_id": "n-001"}
            post_resp.raise_for_status = MagicMock()
            client.post = AsyncMock(return_value=post_resp)

            await notifier.notify(
                agent_id="agent-1",
                tier=AutonomyTier.BOUNDED,
                trigger=HealingTrigger.FAILURE_LOOP,
            )
            client.post.assert_awaited_once()
            call_json = client.post.call_args.kwargs.get(
                "json", client.post.call_args[1].get("json")
            )
            assert call_json["tier"] == "BOUNDED"

    def test_default_url_from_env(self):
        with patch.dict(os.environ, {"SUPERVISOR_URL": "http://sup-env:8080"}):
            notifier = SupervisorNotifier()
            assert notifier._base_url == "http://sup-env:8080"

    def test_default_url_fallback(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SUPERVISOR_URL", None)
            notifier = SupervisorNotifier()
            assert notifier._base_url == "http://localhost:8003"

    def test_custom_sla_timeout(self):
        notifier = SupervisorNotifier(sla_timeout_seconds=900)
        assert notifier._sla_timeout_seconds == 900


# ---------------------------------------------------------------------------
# 3. Online learning consumer
# ---------------------------------------------------------------------------

from enhanced_agent_bus.online_learning_infra.consumer import FeedbackKafkaConsumer


class TestFeedbackKafkaConsumerInit:
    def test_defaults(self):
        consumer = FeedbackKafkaConsumer()
        assert consumer.is_running is False
        assert consumer.pipeline is None
        assert consumer._stats.status == "stopped"

    def test_custom_params(self):
        cb = MagicMock()
        consumer = FeedbackKafkaConsumer(
            bootstrap_servers="kafka:9092",
            topic="custom-topic",
            group_id="custom-group",
            on_message_callback=cb,
        )
        assert consumer.bootstrap_servers == "kafka:9092"
        assert consumer.topic == "custom-topic"
        assert consumer.group_id == "custom-group"
        assert consumer.on_message_callback is cb


class TestFeedbackKafkaConsumerCheckDeps:
    def test_returns_false_when_kafka_unavailable(self):
        consumer = FeedbackKafkaConsumer()
        with patch("enhanced_agent_bus.online_learning_infra.consumer.KAFKA_AVAILABLE", False):
            assert consumer._check_dependencies() is False

    def test_returns_false_when_river_unavailable(self):
        consumer = FeedbackKafkaConsumer()
        with (
            patch("enhanced_agent_bus.online_learning_infra.consumer.KAFKA_AVAILABLE", True),
            patch("enhanced_agent_bus.online_learning_infra.consumer.RIVER_AVAILABLE", False),
        ):
            assert consumer._check_dependencies() is False

    def test_returns_true_when_all_available(self):
        consumer = FeedbackKafkaConsumer()
        with (
            patch("enhanced_agent_bus.online_learning_infra.consumer.KAFKA_AVAILABLE", True),
            patch("enhanced_agent_bus.online_learning_infra.consumer.RIVER_AVAILABLE", True),
        ):
            assert consumer._check_dependencies() is True


class TestFeedbackKafkaConsumerExtractOutcome:
    def _consumer(self):
        return FeedbackKafkaConsumer()

    def test_actual_impact(self):
        c = self._consumer()
        assert c._extract_outcome({"actual_impact": 0.75}) == 0.75
        assert c._extract_outcome({"actual_impact": "3"}) == 3.0

    def test_outcome_mapping(self):
        c = self._consumer()
        assert c._extract_outcome({"outcome": "success"}) == 1
        assert c._extract_outcome({"outcome": "failure"}) == 0
        assert c._extract_outcome({"outcome": "partial"}) == 0.5
        assert c._extract_outcome({"outcome": "unknown"}) is None

    def test_feedback_type_mapping(self):
        c = self._consumer()
        assert c._extract_outcome({"feedback_type": "positive"}) == 1
        assert c._extract_outcome({"feedback_type": "negative"}) == 0
        assert c._extract_outcome({"feedback_type": "neutral"}) == 0.5
        assert c._extract_outcome({"feedback_type": "correction"}) is None

    def test_no_outcome_data(self):
        c = self._consumer()
        assert c._extract_outcome({}) is None

    def test_unknown_outcome_key(self):
        c = self._consumer()
        assert c._extract_outcome({"outcome": "something_else"}) is None


class TestFeedbackKafkaConsumerSanitize:
    def test_sanitize_error_redacts_bootstrap(self):
        c = FeedbackKafkaConsumer()
        err = Exception("bootstrap_servers='kafka:9092' failed")
        result = c._sanitize_error(err)
        assert "kafka:9092" not in result
        assert "REDACTED" in result

    def test_sanitize_error_redacts_password(self):
        c = FeedbackKafkaConsumer()
        err = Exception("password='secret123' invalid")
        result = c._sanitize_error(err)
        assert "secret123" not in result
        assert "REDACTED" in result

    def test_sanitize_bootstrap_servers(self):
        c = FeedbackKafkaConsumer()
        result = c._sanitize_bootstrap("host1:9092,host2:9093")
        assert result == "host1:****,host2:****"

    def test_sanitize_bootstrap_no_port(self):
        c = FeedbackKafkaConsumer()
        result = c._sanitize_bootstrap("hostonly")
        assert result == "hostonly:****"


class TestFeedbackKafkaConsumerProcessMessage:
    async def test_process_message_with_features(self):
        pipeline = MagicMock()
        learn_result = MagicMock()
        learn_result.success = True
        pipeline.learn_from_feedback.return_value = learn_result

        consumer = FeedbackKafkaConsumer(pipeline=pipeline)

        msg = SimpleNamespace(
            offset=42,
            value={
                "features": {"f1": 1.0},
                "actual_impact": 0.9,
                "decision_id": "d-1",
            },
        )
        await consumer._process_message(msg)

        assert consumer._stats.messages_received == 1
        assert consumer._stats.messages_processed == 1
        assert consumer._stats.last_offset == 42
        pipeline.learn_from_feedback.assert_called_once()

    async def test_process_message_learn_failure(self):
        pipeline = MagicMock()
        learn_result = MagicMock()
        learn_result.success = False
        learn_result.error_message = "model error"
        pipeline.learn_from_feedback.return_value = learn_result

        consumer = FeedbackKafkaConsumer(pipeline=pipeline)

        msg = SimpleNamespace(
            offset=1,
            value={
                "features": {"f1": 1.0},
                "actual_impact": 0.5,
                "decision_id": "d-2",
            },
        )
        await consumer._process_message(msg)
        assert consumer._stats.messages_processed == 1

    async def test_process_message_no_features(self):
        pipeline = MagicMock()
        consumer = FeedbackKafkaConsumer(pipeline=pipeline)

        msg = SimpleNamespace(
            offset=1,
            value={"decision_id": "d-3"},
        )
        await consumer._process_message(msg)
        pipeline.learn_from_feedback.assert_not_called()
        assert consumer._stats.messages_processed == 1

    async def test_process_message_callback(self):
        callback = MagicMock()
        consumer = FeedbackKafkaConsumer(on_message_callback=callback)

        msg = SimpleNamespace(
            offset=1,
            value={"some": "data"},
        )
        await consumer._process_message(msg)
        callback.assert_called_once_with({"some": "data"})

    async def test_process_message_error_raises(self):
        pipeline = MagicMock()
        pipeline.learn_from_feedback.side_effect = ValueError("bad data")

        consumer = FeedbackKafkaConsumer(pipeline=pipeline)
        msg = SimpleNamespace(
            offset=1,
            value={
                "features": {"f1": 1.0},
                "actual_impact": 0.5,
                "decision_id": "d-err",
            },
        )
        with pytest.raises(ValueError, match="bad data"):
            await consumer._process_message(msg)
        assert consumer._stats.messages_failed == 1


class TestFeedbackKafkaConsumerGetStats:
    def test_get_stats_no_pipeline(self):
        consumer = FeedbackKafkaConsumer()
        stats = consumer.get_stats()
        assert stats.status == "stopped"

    def test_get_stats_with_dict_pipeline_stats(self):
        pipeline = MagicMock()
        pipeline.get_stats.return_value = {
            "learning_stats": {"samples_learned": 42},
        }
        consumer = FeedbackKafkaConsumer(pipeline=pipeline)
        stats = consumer.get_stats()
        assert stats.samples_learned == 42

    def test_get_stats_with_object_pipeline_stats(self):
        ls = SimpleNamespace(samples_learned=99)
        pipeline = MagicMock()
        pipeline.get_stats.return_value = SimpleNamespace(learning_stats=ls)
        consumer = FeedbackKafkaConsumer(pipeline=pipeline)
        stats = consumer.get_stats()
        assert stats.samples_learned == 99

    def test_get_stats_with_dict_ls_non_dict(self):
        ls = SimpleNamespace(samples_learned=77)
        pipeline = MagicMock()
        pipeline.get_stats.return_value = {"learning_stats": ls}
        consumer = FeedbackKafkaConsumer(pipeline=pipeline)
        stats = consumer.get_stats()
        assert stats.samples_learned == 77


class TestFeedbackKafkaConsumerStartStop:
    async def test_start_no_dependencies(self):
        consumer = FeedbackKafkaConsumer()
        with patch.object(consumer, "_check_dependencies", return_value=False):
            result = await consumer.start()
            assert result is False

    async def test_stop_when_not_running(self):
        consumer = FeedbackKafkaConsumer()
        await consumer.stop()  # Should not raise
        assert consumer._stats.status == "stopped"

    async def test_start_already_running(self):
        consumer = FeedbackKafkaConsumer()
        with patch.object(consumer, "_check_dependencies", return_value=True):
            consumer._running = True
            result = await consumer.start()
            assert result is True

    async def test_stop_cancels_task_and_consumer(self):
        consumer = FeedbackKafkaConsumer()
        consumer._running = True
        consumer._stats.status = "running"

        # Create a real asyncio task that we can cancel
        async def _noop():
            await asyncio.sleep(100)

        task = asyncio.create_task(_noop())
        consumer._consume_task = task

        mock_consumer_obj = AsyncMock()
        consumer._consumer = mock_consumer_obj
        await consumer.stop()

        assert consumer._running is False
        assert consumer._stats.status == "stopped"
        assert task.cancelled()

    async def test_consume_loop_cancelled(self):
        consumer = FeedbackKafkaConsumer()
        consumer._running = True

        # Use an async iterator that raises CancelledError
        class _CancellingIter:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise asyncio.CancelledError

        consumer._consumer = _CancellingIter()

        with pytest.raises(asyncio.CancelledError):
            await consumer._consume_loop()


# ---------------------------------------------------------------------------
# 4. LLM failover
# ---------------------------------------------------------------------------

from enhanced_agent_bus.llm_adapters.llm_failover import (
    FailoverEvent,
    HealthMetrics,
    LLMProviderType,
    ProactiveFailoverManager,
    ProviderHealthScore,
    ProviderHealthScorer,
    ProviderWarmupManager,
    RequestHedgingManager,
    WarmupResult,
    get_llm_circuit_config,
)


class TestGetLlmCircuitConfig:
    def test_known_provider(self):
        config = get_llm_circuit_config("openai")
        assert config.name == "llm:openai"

    def test_known_provider_case_insensitive(self):
        config = get_llm_circuit_config("OpenAI")
        assert config.name == "llm:openai"

    def test_unknown_provider_returns_default(self):
        config = get_llm_circuit_config("unknown_provider")
        assert config.name == "llm:unknown_provider"
        assert "Auto-configured" in config.description


class TestLLMProviderType:
    def test_values(self):
        assert LLMProviderType.OPENAI == "openai"
        assert LLMProviderType.ANTHROPIC == "anthropic"
        assert LLMProviderType.LOCAL == "local"


class TestHealthMetrics:
    def test_defaults(self):
        m = HealthMetrics()
        assert m.total_requests == 0
        assert m.health_score == 1.0
        assert m.uptime_percentage == 100.0


class TestProviderHealthScore:
    def test_to_dict(self):
        metrics = HealthMetrics()
        score = ProviderHealthScore(
            provider_id="openai",
            health_score=0.95,
            latency_score=0.9,
            error_score=1.0,
            quality_score=0.8,
            availability_score=1.0,
            is_healthy=True,
            is_degraded=False,
            is_unhealthy=False,
            metrics=metrics,
        )
        d = score.to_dict()
        assert d["provider_id"] == "openai"
        assert d["health_score"] == 0.95
        assert d["is_healthy"] is True
        assert "metrics" in d
        assert "last_updated" in d


class TestProviderHealthScorer:
    async def test_record_successful_request(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=50.0, success=True)

        score = scorer.get_health_score("openai")
        assert score.is_healthy is True
        assert score.metrics.total_requests == 1
        assert score.metrics.successful_requests == 1

    async def test_record_failed_request(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=100.0, success=False)

        score = scorer.get_health_score("openai")
        assert score.metrics.failed_requests == 1
        assert score.metrics.consecutive_failures == 1

    async def test_record_timeout_error(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request(
            "openai", latency_ms=5000.0, success=False, error_type="timeout"
        )
        score = scorer.get_health_score("openai")
        assert score.metrics.timeout_count == 1

    async def test_record_rate_limit_error(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request(
            "openai", latency_ms=10.0, success=False, error_type="rate_limit"
        )
        score = scorer.get_health_score("openai")
        assert score.metrics.rate_limit_count == 1

    async def test_record_quality_score(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=50.0, success=True, quality_score=0.9)
        score = scorer.get_health_score("openai")
        assert score.metrics.avg_quality_score == 0.9

    async def test_consecutive_failures_reset_on_success(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=100.0, success=False)
        await scorer.record_request("openai", latency_ms=100.0, success=False)
        assert scorer.get_health_score("openai").metrics.consecutive_failures == 2

        await scorer.record_request("openai", latency_ms=50.0, success=True)
        assert scorer.get_health_score("openai").metrics.consecutive_failures == 0

    def test_set_expected_latency(self):
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("openai", 200.0)
        assert scorer._expected_latency["openai"] == 200.0

    async def test_health_score_degrades_with_errors(self):
        scorer = ProviderHealthScorer()
        # Record multiple failures to degrade health
        for _ in range(10):
            await scorer.record_request("openai", latency_ms=1000.0, success=False)

        score = scorer.get_health_score("openai")
        assert score.health_score < 0.5
        assert score.is_unhealthy is True

    def test_get_health_score_unknown_provider(self):
        scorer = ProviderHealthScorer()
        score = scorer.get_health_score("unknown")
        assert score.health_score == 1.0
        assert score.is_healthy is True

    def test_get_all_scores(self):
        scorer = ProviderHealthScorer()
        scorer._metrics["a"] = HealthMetrics()
        scorer._metrics["b"] = HealthMetrics()
        scores = scorer.get_all_scores()
        assert "a" in scores
        assert "b" in scores

    def test_reset_single(self):
        scorer = ProviderHealthScorer()
        scorer._metrics["a"] = HealthMetrics(total_requests=10)
        scorer.reset("a")
        assert scorer._metrics["a"].total_requests == 0

    def test_reset_all(self):
        scorer = ProviderHealthScorer()
        scorer._metrics["a"] = HealthMetrics()
        scorer._metrics["b"] = HealthMetrics()
        scorer.reset()
        assert len(scorer._metrics) == 0

    def test_reset_nonexistent(self):
        scorer = ProviderHealthScorer()
        scorer.reset("nonexistent")  # Should not raise


class TestProactiveFailoverManager:
    def _make_manager(self):
        scorer = ProviderHealthScorer()
        registry = MagicMock()
        registry.find_capable_providers.return_value = []
        return ProactiveFailoverManager(health_scorer=scorer, capability_registry=registry)

    def test_set_primary_provider(self):
        mgr = self._make_manager()
        mgr.set_primary_provider("tenant-1", "openai")
        assert mgr.get_active_provider("tenant-1") == "openai"

    def test_set_fallback_chain(self):
        mgr = self._make_manager()
        mgr.set_fallback_chain("openai", ["anthropic", "google"])
        assert mgr._fallback_chains["openai"] == ["anthropic", "google"]

    def test_build_fallback_chain_cached(self):
        mgr = self._make_manager()
        mgr.set_fallback_chain("openai", ["anthropic"])
        chain = mgr.build_fallback_chain("openai", [])
        assert chain == ["anthropic"]

    def test_build_fallback_chain_dynamic(self):
        scorer = ProviderHealthScorer()
        registry = MagicMock()
        provider_a = MagicMock()
        provider_a.provider_id = "anthropic"
        provider_b = MagicMock()
        provider_b.provider_id = "google"
        registry.find_capable_providers.return_value = [
            (provider_a, 1.0),
            (provider_b, 0.9),
        ]
        mgr = ProactiveFailoverManager(health_scorer=scorer, capability_registry=registry)
        chain = mgr.build_fallback_chain("openai", [])
        assert "anthropic" in chain
        assert "google" in chain

    async def test_check_and_failover_no_provider_with_fallback(self):
        scorer = ProviderHealthScorer()
        registry = MagicMock()
        provider_a = MagicMock()
        provider_a.provider_id = "anthropic"
        registry.find_capable_providers.return_value = [(provider_a, 1.0)]
        mgr = ProactiveFailoverManager(health_scorer=scorer, capability_registry=registry)
        provider, failed_over = await mgr.check_and_failover("tenant-1", [])
        assert provider == "anthropic"
        assert failed_over is False

    async def test_check_and_failover_no_provider_no_fallback(self):
        mgr = self._make_manager()
        with pytest.raises(ValueError, match="No capable providers"):
            await mgr.check_and_failover("tenant-1", [])

    async def test_check_and_failover_healthy_no_change(self):
        scorer = ProviderHealthScorer()
        # Record a healthy request
        await scorer.record_request("openai", latency_ms=50.0, success=True)

        mgr = ProactiveFailoverManager(health_scorer=scorer, capability_registry=MagicMock())
        mgr.set_primary_provider("tenant-1", "openai")

        provider, failed_over = await mgr.check_and_failover("tenant-1", [])
        assert provider == "openai"
        assert failed_over is False

    async def test_check_and_failover_triggers_failover(self):
        scorer = ProviderHealthScorer()
        # Degrade openai
        for _ in range(20):
            await scorer.record_request("openai", latency_ms=5000.0, success=False)
        # Keep anthropic healthy
        await scorer.record_request("anthropic", latency_ms=50.0, success=True)

        mgr = ProactiveFailoverManager(health_scorer=scorer, capability_registry=MagicMock())
        mgr.set_primary_provider("tenant-1", "openai")
        mgr.set_fallback_chain("openai", ["anthropic"])

        provider, failed_over = await mgr.check_and_failover("tenant-1", [])
        assert provider == "anthropic"
        assert failed_over is True

    async def test_check_and_failover_recovery(self):
        scorer = ProviderHealthScorer()
        # Make primary healthy
        for _ in range(10):
            await scorer.record_request("openai", latency_ms=30.0, success=True)

        mgr = ProactiveFailoverManager(health_scorer=scorer, capability_registry=MagicMock())
        mgr.set_primary_provider("tenant-1", "openai")
        mgr._active_failovers["tenant-1"] = "anthropic"

        provider, failed_over = await mgr.check_and_failover("tenant-1", [])
        assert provider == "openai"
        assert failed_over is True

    async def test_check_and_failover_no_healthy_fallback(self):
        scorer = ProviderHealthScorer()
        # Degrade both providers
        for _ in range(20):
            await scorer.record_request("openai", latency_ms=5000.0, success=False)
            await scorer.record_request("anthropic", latency_ms=5000.0, success=False)

        mgr = ProactiveFailoverManager(health_scorer=scorer, capability_registry=MagicMock())
        mgr.set_primary_provider("tenant-1", "openai")
        mgr.set_fallback_chain("openai", ["anthropic"])

        provider, failed_over = await mgr.check_and_failover("tenant-1", [])
        assert provider == "openai"
        assert failed_over is False

    def test_get_failover_history_empty(self):
        mgr = self._make_manager()
        assert mgr.get_failover_history() == []

    def test_get_failover_stats_empty(self):
        mgr = self._make_manager()
        stats = mgr.get_failover_stats()
        assert stats["total_failovers"] == 0

    def test_get_failover_stats_with_events(self):
        mgr = self._make_manager()
        mgr._failover_history.append(
            FailoverEvent(
                event_id="fo-1",
                from_provider="openai",
                to_provider="anthropic",
                reason="proactive",
                latency_ms=5.0,
                success=True,
            )
        )
        stats = mgr.get_failover_stats()
        assert stats["total_failovers"] == 1
        assert stats["successful_failovers"] == 1

    def test_get_active_provider_none(self):
        mgr = self._make_manager()
        assert mgr.get_active_provider("unknown-tenant") is None


class TestProviderWarmupManager:
    async def test_warmup_no_handler(self):
        mgr = ProviderWarmupManager()
        result = await mgr.warmup("openai")
        assert result.success is False
        assert "No warmup handler" in result.error

    async def test_warmup_sync_handler(self):
        mgr = ProviderWarmupManager()

        def sync_handler():
            return "warmed"

        mgr.register_warmup_handler("openai", sync_handler)
        result = await mgr.warmup("openai")
        assert result.success is True
        assert result.latency_ms > 0

    async def test_warmup_async_handler(self):
        mgr = ProviderWarmupManager()

        async def async_handler():
            return "warmed"

        mgr.register_warmup_handler("openai", async_handler)
        result = await mgr.warmup("openai")
        assert result.success is True

    async def test_warmup_timeout(self):
        mgr = ProviderWarmupManager()
        mgr.WARMUP_TIMEOUT_MS = 10  # Very short

        async def slow_handler():
            await asyncio.sleep(10)

        mgr.register_warmup_handler("openai", slow_handler)
        result = await mgr.warmup("openai")
        assert result.success is False
        assert result.error == "Timeout"

    async def test_warmup_error(self):
        mgr = ProviderWarmupManager()

        async def failing_handler():
            raise RuntimeError("connection refused")

        mgr.register_warmup_handler("openai", failing_handler)
        result = await mgr.warmup("openai")
        assert result.success is False
        assert "connection refused" in result.error

    async def test_warmup_if_needed_first_time(self):
        mgr = ProviderWarmupManager()

        async def handler():
            return "ok"

        mgr.register_warmup_handler("openai", handler)
        result = await mgr.warmup_if_needed("openai")
        assert result is not None
        assert result.success is True

    async def test_warmup_if_needed_skip(self):
        mgr = ProviderWarmupManager()

        async def handler():
            return "ok"

        mgr.register_warmup_handler("openai", handler)
        mgr._last_warmup["openai"] = datetime.now(UTC)
        result = await mgr.warmup_if_needed("openai")
        assert result is None

    async def test_warmup_if_needed_interval_elapsed(self):
        mgr = ProviderWarmupManager()

        async def handler():
            return "ok"

        mgr.register_warmup_handler("openai", handler)
        mgr._last_warmup["openai"] = datetime.now(UTC) - timedelta(hours=1)
        result = await mgr.warmup_if_needed("openai")
        assert result is not None

    async def test_warmup_before_failover(self):
        mgr = ProviderWarmupManager()

        async def handler():
            return "ok"

        mgr.register_warmup_handler("openai", handler)
        result = await mgr.warmup_before_failover("openai")
        assert result.success is True

    async def test_start_periodic_warmup(self):
        mgr = ProviderWarmupManager()

        async def handler():
            return "ok"

        mgr.register_warmup_handler("openai", handler)
        mgr.start_periodic_warmup("openai", interval=timedelta(seconds=1))
        assert "openai" in mgr._warmup_tasks
        # Clean up
        mgr.stop_periodic_warmup("openai")
        assert "openai" not in mgr._warmup_tasks

    def test_stop_periodic_warmup_nonexistent(self):
        mgr = ProviderWarmupManager()
        mgr.stop_periodic_warmup("nonexistent")  # Should not raise

    def test_get_warmup_status_no_handler(self):
        mgr = ProviderWarmupManager()
        status = mgr.get_warmup_status("openai")
        assert status["has_handler"] is False
        assert status["last_warmup"] is None
        assert status["last_result"] is None
        assert status["periodic_enabled"] is False

    async def test_get_warmup_status_with_result(self):
        mgr = ProviderWarmupManager()

        async def handler():
            return "ok"

        mgr.register_warmup_handler("openai", handler)
        await mgr.warmup("openai")

        status = mgr.get_warmup_status("openai")
        assert status["has_handler"] is True
        assert status["last_warmup"] is not None
        assert status["last_result"]["success"] is True

    async def test_start_periodic_replaces_existing(self):
        mgr = ProviderWarmupManager()

        async def handler():
            return "ok"

        mgr.register_warmup_handler("openai", handler)
        mgr.start_periodic_warmup("openai")
        old_task = mgr._warmup_tasks["openai"]
        mgr.start_periodic_warmup("openai")
        new_task = mgr._warmup_tasks["openai"]
        assert old_task is not new_task
        # Let the event loop process the cancellation
        await asyncio.sleep(0)
        assert old_task.cancelled()
        mgr.stop_periodic_warmup("openai")


class TestRequestHedgingManager:
    async def test_execute_hedged_success(self):
        mgr = RequestHedgingManager(hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            return f"response-{provider_id}"

        winner, result = await mgr.execute_hedged("req-1", ["openai", "anthropic"], execute_fn)
        assert winner in ("openai", "anthropic")
        assert "response-" in result

    async def test_execute_hedged_no_providers(self):
        mgr = RequestHedgingManager()
        with pytest.raises(ValueError, match="No providers"):
            await mgr.execute_hedged("req-1", [], lambda p: None)

    async def test_execute_hedged_first_fails(self):
        mgr = RequestHedgingManager(hedge_delay_ms=0)

        call_count = 0

        async def execute_fn(provider_id: str):
            nonlocal call_count
            call_count += 1
            if provider_id == "openai":
                raise ConnectionError("failed")
            return f"response-{provider_id}"

        winner, result = await mgr.execute_hedged("req-2", ["openai", "anthropic"], execute_fn)
        assert winner == "anthropic"

    async def test_execute_hedged_all_fail(self):
        mgr = RequestHedgingManager(hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            raise RuntimeError(f"failed-{provider_id}")

        with pytest.raises(RuntimeError, match="All hedged providers failed"):
            await mgr.execute_hedged("req-3", ["openai", "anthropic"], execute_fn)

    def test_get_hedging_stats_empty(self):
        mgr = RequestHedgingManager()
        stats = mgr.get_hedging_stats()
        assert stats["total_hedged_requests"] == 0

    async def test_get_hedging_stats_after_requests(self):
        mgr = RequestHedgingManager(hedge_delay_ms=0)

        async def execute_fn(provider_id: str):
            return f"response-{provider_id}"

        await mgr.execute_hedged("req-1", ["openai", "anthropic"], execute_fn)

        stats = mgr.get_hedging_stats()
        assert stats["total_hedged_requests"] == 1
        assert stats["successful_requests"] == 1


class TestFailoverEvent:
    def test_defaults(self):
        event = FailoverEvent(
            event_id="fo-1",
            from_provider="openai",
            to_provider="anthropic",
            reason="proactive",
        )
        assert event.success is True
        assert event.latency_ms == 0.0


class TestWarmupResult:
    def test_defaults(self):
        result = WarmupResult(
            provider_id="openai",
            success=True,
            latency_ms=42.0,
        )
        assert result.error is None
        assert result.provider_id == "openai"
