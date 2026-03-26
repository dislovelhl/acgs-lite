"""Tests for enhanced_agent_bus.session_governance_sdk module.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from enhanced_agent_bus.session_governance_sdk import (
    AutomationLevel,
    GovernanceConfig,
    PolicySelectionResult,
    RiskLevel,
    SelectedPolicy,
    ServiceUnavailableError,
    Session,
    SessionGovernanceClient,
    SessionMetrics,
    SessionNotFoundError,
    SessionSDKError,
    SessionValidationError,
    TenantAccessDeniedError,
    create_client,
)

# ---------------------------------------------------------------------------
# Tests: Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_risk_levels(self):
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_automation_levels(self):
        assert AutomationLevel.FULL.value == "full"
        assert AutomationLevel.PARTIAL.value == "partial"
        assert AutomationLevel.NONE.value == "none"

    def test_risk_level_is_str(self):
        assert isinstance(RiskLevel.LOW, str)
        assert RiskLevel.LOW == "low"


# ---------------------------------------------------------------------------
# Tests: Exception classes
# ---------------------------------------------------------------------------


class TestExceptions:
    def test_session_sdk_error(self):
        err = SessionSDKError("test error", status_code=500, response_body={"detail": "fail"})
        assert "test error" in str(err)
        assert err.status_code == 500
        assert err.response_body == {"detail": "fail"}

    def test_session_not_found_error(self):
        err = SessionNotFoundError("not found", status_code=404)
        assert err.http_status_code == 404
        assert err.error_code == "SESSION_NOT_FOUND"

    def test_tenant_access_denied_error(self):
        err = TenantAccessDeniedError("denied", status_code=403)
        assert err.http_status_code == 403

    def test_session_validation_error(self):
        err = SessionValidationError("invalid", status_code=400)
        assert err.http_status_code == 400

    def test_service_unavailable_error(self):
        err = ServiceUnavailableError("unavailable", status_code=503)
        assert err.http_status_code == 503


# ---------------------------------------------------------------------------
# Tests: GovernanceConfig
# ---------------------------------------------------------------------------


class TestGovernanceConfig:
    def test_default_values(self):
        cfg = GovernanceConfig(tenant_id="t1")
        assert cfg.tenant_id == "t1"
        assert cfg.risk_level == RiskLevel.MEDIUM
        assert cfg.require_human_approval is False
        assert cfg.enabled_policies == []
        assert cfg.disabled_policies == []

    def test_to_dict_minimal(self):
        cfg = GovernanceConfig(tenant_id="t1")
        d = cfg.to_dict()
        assert d["tenant_id"] == "t1"
        assert d["risk_level"] == "medium"
        assert "user_id" not in d
        assert "policy_id" not in d

    def test_to_dict_full(self):
        cfg = GovernanceConfig(
            tenant_id="t1",
            user_id="u1",
            risk_level=RiskLevel.HIGH,
            policy_id="p1",
            policy_overrides={"key": "val"},
            enabled_policies=["a"],
            disabled_policies=["b"],
            require_human_approval=True,
            max_automation_level=AutomationLevel.PARTIAL,
        )
        d = cfg.to_dict()
        assert d["tenant_id"] == "t1"
        assert d["user_id"] == "u1"
        assert d["risk_level"] == "high"
        assert d["policy_id"] == "p1"
        assert d["policy_overrides"] == {"key": "val"}
        assert d["enabled_policies"] == ["a"]
        assert d["disabled_policies"] == ["b"]
        assert d["require_human_approval"] is True
        assert d["max_automation_level"] == "partial"

    def test_to_dict_with_string_risk_level(self):
        cfg = GovernanceConfig(tenant_id="t1", risk_level="custom")
        d = cfg.to_dict()
        assert d["risk_level"] == "custom"


# ---------------------------------------------------------------------------
# Tests: Session
# ---------------------------------------------------------------------------


class TestSession:
    def test_from_dict_minimal(self):
        data = {"session_id": "s1", "tenant_id": "t1"}
        session = Session.from_dict(data)
        assert session.session_id == "s1"
        assert session.tenant_id == "t1"
        assert session.risk_level == "medium"
        assert session.enabled_policies == []

    def test_from_dict_full(self):
        data = {
            "session_id": "s1",
            "tenant_id": "t1",
            "risk_level": "high",
            "policy_id": "p1",
            "policy_overrides": {"x": 1},
            "enabled_policies": ["a", "b"],
            "disabled_policies": ["c"],
            "require_human_approval": True,
            "max_automation_level": "full",
            "metadata": {"foo": "bar"},
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-02T00:00:00Z",
            "expires_at": "2025-01-03T00:00:00Z",
            "ttl_remaining": 3600,
            "constitutional_hash": "608508a9bd224290",
        }
        session = Session.from_dict(data)
        assert session.risk_level == "high"
        assert session.policy_id == "p1"
        assert session.require_human_approval is True
        assert session.ttl_remaining == 3600


# ---------------------------------------------------------------------------
# Tests: SessionMetrics
# ---------------------------------------------------------------------------


class TestSessionMetrics:
    def test_from_dict(self):
        data = {
            "cache_hits": 100,
            "cache_misses": 10,
            "creates": 50,
            "reads": 200,
            "updates": 30,
            "deletes": 5,
            "errors": 2,
            "cache_hit_rate": 0.91,
            "cache_size": 45,
            "cache_capacity": 1000,
        }
        metrics = SessionMetrics.from_dict(data)
        assert metrics.cache_hits == 100
        assert metrics.cache_hit_rate == pytest.approx(0.91)
        assert metrics.cache_capacity == 1000

    def test_from_dict_defaults(self):
        metrics = SessionMetrics.from_dict({})
        assert metrics.cache_hits == 0
        assert metrics.errors == 0
        assert metrics.cache_capacity == 1000


# ---------------------------------------------------------------------------
# Tests: SessionGovernanceClient
# ---------------------------------------------------------------------------


class TestSessionGovernanceClient:
    def test_init(self):
        client = SessionGovernanceClient(
            base_url="http://localhost:8000",
            timeout=10.0,
            default_tenant_id="t1",
        )
        assert client.base_url == "http://localhost:8000"
        assert client.timeout == 10.0
        assert client.default_tenant_id == "t1"
        assert client._client is None

    def test_init_strips_trailing_slash(self):
        client = SessionGovernanceClient(base_url="http://localhost:8000/")
        assert client.base_url == "http://localhost:8000"

    def test_get_headers(self):
        client = SessionGovernanceClient(default_tenant_id="t1")
        headers = client._get_headers()
        assert headers["X-Tenant-ID"] == "t1"
        assert headers["Content-Type"] == "application/json"

    def test_get_headers_override_tenant(self):
        client = SessionGovernanceClient(default_tenant_id="t1")
        headers = client._get_headers(tenant_id="t2")
        assert headers["X-Tenant-ID"] == "t2"

    def test_get_headers_no_tenant_raises(self):
        client = SessionGovernanceClient()
        with pytest.raises(ValueError, match="tenant_id is required"):
            client._get_headers()

    def test_handle_error_404(self):
        client = SessionGovernanceClient()
        response = MagicMock()
        response.status_code = 404
        response.json.return_value = {"detail": "not found"}
        with pytest.raises(SessionNotFoundError):
            client._handle_error(response)

    def test_handle_error_403(self):
        client = SessionGovernanceClient()
        response = MagicMock()
        response.status_code = 403
        response.json.return_value = {"detail": "forbidden"}
        with pytest.raises(TenantAccessDeniedError):
            client._handle_error(response)

    def test_handle_error_400(self):
        client = SessionGovernanceClient()
        response = MagicMock()
        response.status_code = 400
        response.json.return_value = {"detail": "bad request"}
        with pytest.raises(SessionValidationError):
            client._handle_error(response)

    def test_handle_error_422(self):
        client = SessionGovernanceClient()
        response = MagicMock()
        response.status_code = 422
        response.json.return_value = {"detail": "unprocessable"}
        with pytest.raises(SessionValidationError):
            client._handle_error(response)

    def test_handle_error_503(self):
        client = SessionGovernanceClient()
        response = MagicMock()
        response.status_code = 503
        response.json.return_value = {"detail": "unavailable"}
        with pytest.raises(ServiceUnavailableError):
            client._handle_error(response)

    def test_handle_error_generic(self):
        client = SessionGovernanceClient()
        response = MagicMock()
        response.status_code = 500
        response.json.return_value = {"detail": "server error"}
        with pytest.raises(SessionSDKError):
            client._handle_error(response)

    def test_handle_error_unparseable_json(self):
        client = SessionGovernanceClient()
        response = MagicMock()
        response.status_code = 500
        response.json.side_effect = ValueError("bad json")
        response.text = "Internal Server Error"
        with pytest.raises(SessionSDKError):
            client._handle_error(response)


# ---------------------------------------------------------------------------
# Tests: async methods
# ---------------------------------------------------------------------------


class TestAsyncMethods:
    @pytest.mark.asyncio
    async def test_connect_and_close(self):
        client = SessionGovernanceClient()
        await client.connect()
        assert client._client is not None
        await client.close()
        assert client._client is None

    @pytest.mark.asyncio
    async def test_close_when_not_connected(self):
        client = SessionGovernanceClient()
        await client.close()  # Should not raise
        assert client._client is None

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with SessionGovernanceClient() as client:
            assert client._client is not None
        assert client._client is None

    @pytest.mark.asyncio
    async def test_create_session_no_tenant_raises(self):
        client = SessionGovernanceClient()
        with pytest.raises(ValueError, match="tenant_id is required"):
            await client.create_session()

    @pytest.mark.asyncio
    async def test_create_session_success(self):
        client = SessionGovernanceClient(default_tenant_id="t1")
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "session_id": "s1",
            "tenant_id": "t1",
            "risk_level": "medium",
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._client = mock_http

        session = await client.create_session(risk_level=RiskLevel.MEDIUM)
        assert session.session_id == "s1"
        assert session.tenant_id == "t1"

    @pytest.mark.asyncio
    async def test_create_session_auto_connects(self):
        client = SessionGovernanceClient(default_tenant_id="t1")
        assert client._client is None

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "session_id": "s1",
            "tenant_id": "t1",
        }

        with patch.object(client, "connect", new_callable=AsyncMock) as mock_connect:
            # After connect is called, set up the mock client
            async def set_client():
                mock_http = AsyncMock()
                mock_http.post = AsyncMock(return_value=mock_response)
                client._client = mock_http

            mock_connect.side_effect = set_client
            session = await client.create_session()
            mock_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_session_success(self):
        client = SessionGovernanceClient(default_tenant_id="t1")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "session_id": "s1",
            "tenant_id": "t1",
        }

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        client._client = mock_http

        session = await client.get_session("s1")
        assert session.session_id == "s1"

    @pytest.mark.asyncio
    async def test_delete_session_success(self):
        client = SessionGovernanceClient(default_tenant_id="t1")
        mock_response = MagicMock()
        mock_response.status_code = 204

        mock_http = AsyncMock()
        mock_http.delete = AsyncMock(return_value=mock_response)
        client._client = mock_http

        result = await client.delete_session("s1")
        assert result is True

    @pytest.mark.asyncio
    async def test_extend_ttl_success(self):
        client = SessionGovernanceClient(default_tenant_id="t1")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "session_id": "s1",
            "tenant_id": "t1",
            "ttl_remaining": 7200,
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._client = mock_http

        session = await client.extend_ttl("s1", ttl_seconds=7200)
        assert session.ttl_remaining == 7200

    @pytest.mark.asyncio
    async def test_update_governance_success(self):
        client = SessionGovernanceClient(default_tenant_id="t1")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "session_id": "s1",
            "tenant_id": "t1",
            "risk_level": "high",
        }

        mock_http = AsyncMock()
        mock_http.put = AsyncMock(return_value=mock_response)
        client._client = mock_http

        session = await client.update_governance("s1", risk_level=RiskLevel.HIGH)
        assert session.risk_level == "high"

    @pytest.mark.asyncio
    async def test_get_metrics_success(self):
        client = SessionGovernanceClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "cache_hits": 10,
            "cache_misses": 2,
        }

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        client._client = mock_http

        metrics = await client.get_metrics()
        assert metrics.cache_hits == 10

    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        client = SessionGovernanceClient()
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        client._client = mock_http

        result = await client.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self):
        client = SessionGovernanceClient()
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=ConnectionError("down"))
        client._client = mock_http

        result = await client.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_select_policies_success(self):
        client = SessionGovernanceClient(default_tenant_id="t1")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "session_id": "s1",
            "tenant_id": "t1",
            "risk_level": "medium",
            "selected_policy": {
                "policy_id": "p1",
                "name": "Policy One",
                "source": "builtin",
                "priority": 1,
                "reasoning": "Best match",
            },
            "candidate_policies": [],
            "enabled_policies": ["p1"],
            "disabled_policies": [],
            "selection_metadata": {},
            "timestamp": "2025-01-01T00:00:00Z",
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._client = mock_http

        result = await client.select_policies("s1")
        assert isinstance(result, PolicySelectionResult)
        assert result.selected_policy.name == "Policy One"
        assert result.session_id == "s1"

    @pytest.mark.asyncio
    async def test_select_policies_no_selected(self):
        client = SessionGovernanceClient(default_tenant_id="t1")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "session_id": "s1",
            "tenant_id": "t1",
            "risk_level": "low",
            "selected_policy": None,
            "candidate_policies": [
                {
                    "policy_id": "p2",
                    "name": "Candidate",
                    "source": "custom",
                    "priority": 2,
                    "reasoning": "Fallback",
                }
            ],
            "enabled_policies": [],
            "disabled_policies": [],
            "selection_metadata": {},
            "timestamp": "2025-01-01T00:00:00Z",
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._client = mock_http

        result = await client.select_policies("s1")
        assert result.selected_policy is None
        assert len(result.candidate_policies) == 1
        assert result.candidate_policies[0].name == "Candidate"


# ---------------------------------------------------------------------------
# Tests: create_client convenience function
# ---------------------------------------------------------------------------


class TestCreateClient:
    def test_create_client(self):
        client = create_client(base_url="http://example.com", tenant_id="t1")
        assert isinstance(client, SessionGovernanceClient)
        assert client.base_url == "http://example.com"
        assert client.default_tenant_id == "t1"

    def test_create_client_defaults(self):
        client = create_client()
        assert client.base_url == "http://localhost:8000"
