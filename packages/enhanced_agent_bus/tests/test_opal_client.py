"""
Tests for enhanced_agent_bus.opal_client — OPAL Policy Client.
Constitutional Hash: 608508a9bd224290

Covers:
- OPALPolicyClient init / defaults / env override
- connect / disconnect lifecycle
- evaluate (with OPA client, direct HTTP fallback, fail-closed)
- _handle_ws_message parsing and dispatch
- _invalidate_opa_cache
- _audit_policy_update
- wait_for_propagation (success + timeout)
- status snapshot
- context manager protocol
- Model construction (PolicyUpdateEvent, OPALClientStatus, OPALConnectionState)
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from enhanced_agent_bus.opal_client import (
    OPAL_DEFAULT_PROPAGATION_TIMEOUT,
    OPAL_DEFAULT_SERVER_URL,
    OPALClientStatus,
    OPALConnectionState,
    OPALPolicyClient,
    PolicyUpdateEvent,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(**overrides) -> OPALPolicyClient:
    """Build an OPALPolicyClient with sane test defaults (OPAL disabled)."""
    defaults = {
        "opa_url": "http://test-opa:8181",
        "opal_server_url": "http://test-opal:7002",
        "opal_token": "test-token",
        "opal_enabled": False,
    }
    defaults.update(overrides)
    return OPALPolicyClient(**defaults)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestOPALConnectionState:
    """Enum values are stable strings."""

    def test_enum_values(self):
        assert OPALConnectionState.DISCONNECTED == "disconnected"
        assert OPALConnectionState.CONNECTING == "connecting"
        assert OPALConnectionState.CONNECTED == "connected"
        assert OPALConnectionState.RECONNECTING == "reconnecting"
        assert OPALConnectionState.FAILED == "failed"

    def test_enum_is_str_subclass(self):
        assert isinstance(OPALConnectionState.CONNECTED, str)


class TestPolicyUpdateEvent:
    """Pydantic model construction and defaults."""

    def test_defaults(self):
        evt = PolicyUpdateEvent(event_type="policy_update")
        assert evt.event_type == "policy_update"
        assert evt.event_id  # auto-generated uuid
        assert evt.policy_id is None
        assert evt.timestamp  # auto-generated
        assert evt.raw_payload == {}
        assert evt.opal_server_url == ""

    def test_explicit_fields(self):
        evt = PolicyUpdateEvent(
            event_type="data_update",
            policy_id="pol-42",
            opal_server_url="http://opal:7002",
            raw_payload={"key": "value"},
        )
        assert evt.policy_id == "pol-42"
        assert evt.raw_payload == {"key": "value"}


class TestOPALClientStatus:
    """Status snapshot model."""

    def test_construction(self):
        status = OPALClientStatus(
            enabled=True,
            connection_state=OPALConnectionState.CONNECTED,
            opal_server_url="http://opal:7002",
        )
        assert status.enabled is True
        assert status.connection_state == OPALConnectionState.CONNECTED
        assert status.total_updates_received == 0
        assert status.fallback_active is False
        assert status.last_update_at is None


# ---------------------------------------------------------------------------
# Client init tests
# ---------------------------------------------------------------------------


class TestOPALPolicyClientInit:
    """Constructor defaults and env var handling."""

    def test_explicit_params(self):
        client = _make_client()
        assert client.opa_url == "http://test-opa:8181"
        assert client.opal_server_url == "http://test-opal:7002"
        assert client.opal_token == "test-token"
        assert client.opal_enabled is False
        assert client.propagation_timeout == OPAL_DEFAULT_PROPAGATION_TIMEOUT
        assert client.fail_closed is True

    def test_trailing_slash_stripped(self):
        client = OPALPolicyClient(
            opa_url="http://opa:8181/",
            opal_server_url="http://opal:7002/",
            opal_enabled=False,
        )
        assert client.opa_url == "http://opa:8181"
        assert client.opal_server_url == "http://opal:7002"

    @patch.dict(
        "os.environ", {"OPA_URL": "http://env-opa:9999", "OPAL_SERVER_URL": "http://env-opal:7777"}
    )
    def test_env_fallback(self):
        client = OPALPolicyClient(opal_enabled=False)
        assert client.opa_url == "http://env-opa:9999"
        assert client.opal_server_url == "http://env-opal:7777"

    @patch.dict("os.environ", {"OPAL_ENABLED": "false"})
    def test_env_disables_opal(self):
        client = OPALPolicyClient(opal_enabled=True)
        assert client.opal_enabled is False

    def test_default_opal_server_url_constant(self):
        assert OPAL_DEFAULT_SERVER_URL == "http://opal-server:7002"


# ---------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestConnectDisconnect:
    """connect() / disconnect() lifecycle management."""

    @patch("enhanced_agent_bus.opal_client.OPAClient", None)
    @patch("enhanced_agent_bus.opal_client.AuditClient", None)
    async def test_connect_disconnect_opal_disabled(self):
        client = _make_client(opal_enabled=False)
        await client.connect()

        assert client._http_client is not None
        assert client._fallback_active is True
        assert client._ws_task is None

        await client.disconnect()
        assert client._http_client is None
        assert client._connection_state == OPALConnectionState.DISCONNECTED

    @patch("enhanced_agent_bus.opal_client.OPAClient", None)
    @patch("enhanced_agent_bus.opal_client.AuditClient", None)
    async def test_disconnect_idempotent(self):
        client = _make_client()
        await client.disconnect()
        assert client._connection_state == OPALConnectionState.DISCONNECTED

    @patch("enhanced_agent_bus.opal_client.AuditClient", None)
    async def test_connect_with_opa_client(self):
        mock_opa_cls = MagicMock()
        mock_opa_instance = AsyncMock()
        mock_opa_cls.return_value = mock_opa_instance

        with patch("enhanced_agent_bus.opal_client.OPAClient", mock_opa_cls):
            client = _make_client(opal_enabled=False)
            await client.connect()

            mock_opa_cls.assert_called_once_with(opa_url="http://test-opa:8181")
            mock_opa_instance.initialize.assert_awaited_once()
            assert client._opa_client is mock_opa_instance

            await client.disconnect()
            mock_opa_instance.close.assert_awaited_once()

    @patch("enhanced_agent_bus.opal_client.OPAClient", None)
    async def test_connect_with_audit_client(self):
        mock_audit_cls = MagicMock()
        mock_audit_instance = AsyncMock()
        mock_audit_cls.return_value = mock_audit_instance

        with patch("enhanced_agent_bus.opal_client.AuditClient", mock_audit_cls):
            client = _make_client(opal_enabled=False)
            await client.connect()

            mock_audit_instance.start.assert_awaited_once()
            assert client._audit_client is mock_audit_instance

            await client.disconnect()
            mock_audit_instance.stop.assert_awaited_once()

    @patch("enhanced_agent_bus.opal_client.OPAClient", None)
    async def test_connect_audit_failure_nonfatal(self):
        mock_audit_cls = MagicMock()
        mock_audit_instance = AsyncMock()
        mock_audit_instance.start.side_effect = ConnectionError("no audit")
        mock_audit_cls.return_value = mock_audit_instance

        with patch("enhanced_agent_bus.opal_client.AuditClient", mock_audit_cls):
            client = _make_client(opal_enabled=False)
            await client.connect()
            assert client._audit_client is None
            await client.disconnect()

    @patch("enhanced_agent_bus.opal_client.AuditClient", None)
    async def test_connect_opa_failure_nonfatal(self):
        mock_opa_cls = MagicMock()
        mock_opa_instance = AsyncMock()
        mock_opa_instance.initialize.side_effect = TimeoutError("no opa")
        mock_opa_cls.return_value = mock_opa_instance

        with patch("enhanced_agent_bus.opal_client.OPAClient", mock_opa_cls):
            client = _make_client(opal_enabled=False)
            await client.connect()
            assert client._opa_client is None
            await client.disconnect()


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestContextManager:
    @patch("enhanced_agent_bus.opal_client.OPAClient", None)
    @patch("enhanced_agent_bus.opal_client.AuditClient", None)
    async def test_aenter_aexit(self):
        client = _make_client(opal_enabled=False)
        async with client as c:
            assert c is client
            assert c._http_client is not None
        assert client._http_client is None


# ---------------------------------------------------------------------------
# Evaluate tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEvaluate:
    """Policy evaluation via OPA client or direct HTTP fallback."""

    async def test_evaluate_with_opa_client_allow(self):
        client = _make_client()
        client._opa_client = AsyncMock()
        client._opa_client.evaluate.return_value = True

        result = await client.evaluate("data.acgs.allow", {"action": "read"})
        assert result is True
        client._opa_client.evaluate.assert_awaited_once_with("data.acgs.allow", {"action": "read"})

    async def test_evaluate_with_opa_client_deny(self):
        client = _make_client()
        client._opa_client = AsyncMock()
        client._opa_client.evaluate.return_value = False

        result = await client.evaluate("data.acgs.allow", {"action": "delete"})
        assert result is False

    async def test_evaluate_opa_error_fail_closed(self):
        client = _make_client(fail_closed=True)
        client._opa_client = AsyncMock()
        client._opa_client.evaluate.side_effect = ConnectionError("down")

        result = await client.evaluate("data.acgs.allow", {})
        assert result is False  # fail-closed => deny

    async def test_evaluate_opa_error_fail_open(self):
        client = _make_client(fail_closed=False)
        client._opa_client = AsyncMock()
        client._opa_client.evaluate.side_effect = TimeoutError("slow")

        result = await client.evaluate("data.acgs.allow", {})
        assert result is True  # fail-open => allow

    async def test_evaluate_opa_error_default_deny_override(self):
        client = _make_client(fail_closed=True)
        client._opa_client = AsyncMock()
        client._opa_client.evaluate.side_effect = ConnectionError("down")

        result = await client.evaluate("data.acgs.allow", {}, default_deny=False)
        assert result is True  # override fail-closed to open


# ---------------------------------------------------------------------------
# Direct HTTP fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEvaluateDirectHTTP:
    """_evaluate_direct_http fallback when no OPA client."""

    async def test_no_http_client_fail_closed(self):
        client = _make_client(fail_closed=True)
        client._opa_client = None
        client._http_client = None

        result = await client.evaluate("data.acgs.allow", {})
        assert result is False

    async def test_http_success_allow(self):
        client = _make_client(fail_closed=True)
        client._opa_client = None

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": True}

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        client._http_client = mock_http

        result = await client.evaluate("data.acgs.allow", {"action": "read"})
        assert result is True
        mock_http.post.assert_awaited_once_with(
            "http://test-opa:8181/v1/data/acgs/allow",
            json={"input": {"action": "read"}},
        )

    async def test_http_success_deny(self):
        client = _make_client()
        client._opa_client = None

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": False}

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        client._http_client = mock_http

        result = await client.evaluate("data.acgs.allow", {})
        assert result is False

    async def test_http_non_200_fail_closed(self):
        client = _make_client(fail_closed=True)
        client._opa_client = None

        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        client._http_client = mock_http

        result = await client.evaluate("data.acgs.allow", {})
        assert result is False

    async def test_http_error_fail_closed(self):
        client = _make_client(fail_closed=True)
        client._opa_client = None

        mock_http = AsyncMock()
        mock_http.post.side_effect = httpx.ConnectError("refused")
        client._http_client = mock_http

        result = await client.evaluate("data.acgs.allow", {})
        assert result is False


# ---------------------------------------------------------------------------
# Websocket message handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHandleWSMessage:
    """_handle_ws_message parsing and side-effects."""

    async def test_valid_json_creates_event(self):
        client = _make_client()
        client._opa_client = None
        client._audit_client = None

        payload = {"type": "policy_update", "policy_id": "pol-1"}
        await client._handle_ws_message(json.dumps(payload))

        assert client._total_updates == 1
        assert client._last_update_at is not None

    async def test_invalid_json_ignored(self):
        client = _make_client()
        await client._handle_ws_message("not-json{{{")
        assert client._total_updates == 0

    async def test_binary_json_accepted(self):
        client = _make_client()
        client._opa_client = None
        client._audit_client = None

        payload = b'{"type": "data_update"}'
        await client._handle_ws_message(payload)
        assert client._total_updates == 1

    async def test_notifies_listeners(self):
        client = _make_client()
        client._opa_client = None
        client._audit_client = None

        queue: asyncio.Queue[PolicyUpdateEvent] = asyncio.Queue(maxsize=1)
        client._update_listeners.append(queue)

        await client._handle_ws_message(json.dumps({"type": "policy_update"}))

        event = queue.get_nowait()
        assert event.event_type == "policy_update"

    async def test_full_queue_does_not_block(self):
        client = _make_client()
        client._opa_client = None
        client._audit_client = None

        queue: asyncio.Queue[PolicyUpdateEvent] = asyncio.Queue(maxsize=1)
        # Pre-fill the queue
        queue.put_nowait(PolicyUpdateEvent(event_type="old"))
        client._update_listeners.append(queue)

        # Should not raise
        await client._handle_ws_message(json.dumps({"type": "new_event"}))
        assert client._total_updates == 1


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestInvalidateOPACache:
    async def test_calls_clear_cache(self):
        client = _make_client()
        mock_opa = AsyncMock()
        mock_opa.clear_cache = AsyncMock()
        client._opa_client = mock_opa

        evt = PolicyUpdateEvent(event_type="policy_update")
        await client._invalidate_opa_cache(evt)
        mock_opa.clear_cache.assert_awaited_once()

    async def test_no_opa_client_noop(self):
        client = _make_client()
        client._opa_client = None
        evt = PolicyUpdateEvent(event_type="policy_update")
        await client._invalidate_opa_cache(evt)  # no error

    async def test_clear_cache_error_nonfatal(self):
        client = _make_client()
        mock_opa = AsyncMock()
        mock_opa.clear_cache = AsyncMock(side_effect=ConnectionError("err"))
        client._opa_client = mock_opa

        evt = PolicyUpdateEvent(event_type="policy_update")
        await client._invalidate_opa_cache(evt)  # no raise

    async def test_no_clear_cache_method_noop(self):
        client = _make_client()
        client._opa_client = MagicMock(spec=[])  # no clear_cache attr
        evt = PolicyUpdateEvent(event_type="policy_update")
        await client._invalidate_opa_cache(evt)  # no error


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAuditPolicyUpdate:
    async def test_logs_to_audit_client(self):
        client = _make_client()
        mock_audit = AsyncMock()
        client._audit_client = mock_audit

        evt = PolicyUpdateEvent(event_type="policy_update", policy_id="pol-1")
        await client._audit_policy_update(evt)

        mock_audit.log.assert_awaited_once()
        call_kwargs = mock_audit.log.call_args[1]
        assert call_kwargs["event_type"] == "opal_policy_update"
        assert call_kwargs["data"]["policy_id"] == "pol-1"

    async def test_audit_error_nonfatal(self):
        client = _make_client()
        mock_audit = AsyncMock()
        mock_audit.log.side_effect = ConnectionError("audit down")
        client._audit_client = mock_audit

        evt = PolicyUpdateEvent(event_type="policy_update")
        await client._audit_policy_update(evt)  # no raise

    async def test_no_audit_client_noop(self):
        client = _make_client()
        client._audit_client = None
        evt = PolicyUpdateEvent(event_type="policy_update")
        await client._audit_policy_update(evt)  # no error


# ---------------------------------------------------------------------------
# Propagation tracking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestWaitForPropagation:
    async def test_receives_event_returns_true(self):
        client = _make_client()

        async def _push_event():
            await asyncio.sleep(0.01)
            for q in client._update_listeners:
                q.put_nowait(PolicyUpdateEvent(event_type="policy_update"))

        task = asyncio.create_task(_push_event())
        result = await client.wait_for_propagation(timeout=2)
        assert result is True
        assert len(client._update_listeners) == 0  # cleaned up
        await task

    async def test_timeout_returns_false(self):
        client = _make_client()
        result = await client.wait_for_propagation(timeout=0)
        assert result is False
        assert len(client._update_listeners) == 0

    async def test_uses_default_timeout(self):
        client = _make_client(propagation_timeout=0)
        result = await client.wait_for_propagation()
        assert result is False


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_snapshot(self):
        client = _make_client()
        client._total_updates = 5
        client._last_update_at = "2026-01-01T00:00:00+00:00"
        client._fallback_active = True

        s = client.status()
        assert isinstance(s, OPALClientStatus)
        assert s.enabled is False
        assert s.connection_state == OPALConnectionState.DISCONNECTED
        assert s.opal_server_url == "http://test-opal:7002"
        assert s.total_updates_received == 5
        assert s.last_update_at == "2026-01-01T00:00:00+00:00"
        assert s.fallback_active is True


# ---------------------------------------------------------------------------
# Websocket listener (no-websockets branch)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestConnectWebsocketNoLib:
    """When websockets library is not available."""

    async def test_falls_back_when_no_websockets(self):
        client = _make_client()
        client._stop_event = asyncio.Event()

        with patch("enhanced_agent_bus.opal_client.WEBSOCKETS_AVAILABLE", False):
            # Set stop event immediately so _connect_websocket returns
            client._stop_event.set()
            await client._connect_websocket()

        assert client._connection_state == OPALConnectionState.FAILED
        assert client._fallback_active is True
