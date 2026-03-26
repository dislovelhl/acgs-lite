"""Coverage gap tests for AutonomyTierEnforcementMiddleware.
Constitutional Hash: 608508a9bd224290

Targets uncovered code paths identified by pytest-cov:
  - HITL submit exception handling (advisory + human-approved)
  - No repo configured → 503
  - Resolve_repo timeout / ConnectionError → 503
  - Unauthenticated request on enforced path → 401
  - Unknown/future tier value → forward to proxy
  - Invalid JSON body → action_type fallback
  - Empty request body → action_type fallback
  - Async dependency overrides (coroutine branch)
  - HttpHitlSubmissionClient real implementation
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.services.api_gateway.middleware.autonomy_tier import (
    AutonomyTierEnforcementMiddleware,
    HitlSubmissionClient,
    HttpHitlSubmissionClient,
)
from src.core.services.api_gateway.models.tier_assignment import (
    AgentTierAssignment,
    AutonomyTier,
)
from src.core.services.api_gateway.repositories.tier_assignment import (
    TierAssignmentRepository,
)
from src.core.services.api_gateway.routes.autonomy_tiers import get_tier_repo
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.security.auth import UserClaims, get_current_user

CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH  # pragma: allowlist secret

_AGENT_ID = "agent-cov-001"
_TENANT_ID = "tenant-cov-test"

_AGENT_CLAIMS = UserClaims(
    sub=_AGENT_ID,
    tenant_id=_TENANT_ID,
    roles=["agent"],
    permissions=[],
    exp=9_999_999_999,
    iat=1_000_000_000,
)


def _make_assignment(
    tier: AutonomyTier,
    action_boundaries: list[str] | None = None,
) -> AgentTierAssignment:
    now = datetime.now(UTC)
    return AgentTierAssignment(
        id=uuid.uuid4(),
        agent_id=_AGENT_ID,
        tenant_id=_TENANT_ID,
        tier=tier,
        action_boundaries=action_boundaries,
        assigned_by="admin",
        assigned_at=now,
        created_at=now,
    )


def _make_test_app(
    repo: TierAssignmentRepository | None,
    user: UserClaims = _AGENT_CLAIMS,
    hitl_client: HitlSubmissionClient | None = None,
    store_timeout: float = 2.0,
) -> FastAPI:
    """Build a minimal FastAPI test app with the enforcement middleware."""
    app = FastAPI()
    app.add_middleware(AutonomyTierEnforcementMiddleware, store_timeout=store_timeout)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_tier_repo] = lambda: repo
    app.state.hitl_client = hitl_client

    @app.post("/api/v1/messages")
    async def _dummy_messages():
        return {"status": "ok"}

    return app


# ---------------------------------------------------------------------------
# HITL submit exception handling (advisory + human-approved)
# ---------------------------------------------------------------------------


class TestHitlSubmitExceptionHandling:
    """HITL client exceptions must be logged but not break the enforcement flow."""

    @pytest.mark.unit
    def test_advisory_hitl_submit_exception_still_returns_pending(self) -> None:
        """Advisory: HITL submit raises → still returns PENDING (exception logged)."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)
        mock_hitl.submit.side_effect = Exception("HITL service down")

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("src.core.services.api_gateway.middleware.autonomy_tier.logger") as mock_logger:
            response = client.post(
                "/api/v1/messages",
                json={"message_type": "command", "content": "test"},
                headers={"Authorization": "Bearer test-token"},
            )

            assert response.status_code in (200, 202)
            assert response.json().get("decision") == "PENDING"

            # Verify the exception was logged
            error_calls = [
                c for c in mock_logger.error.call_args_list if "hitl_submit_failed" in str(c)
            ]
            assert error_calls, "Expected a log entry for HITL submit failure"

    @pytest.mark.unit
    def test_human_approved_hitl_submit_exception_still_returns_pending(self) -> None:
        """Human-approved: HITL submit raises → still returns PENDING."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.HUMAN_APPROVED)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)
        mock_hitl.submit.side_effect = RuntimeError("Connection refused")

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("src.core.services.api_gateway.middleware.autonomy_tier.logger") as mock_logger:
            response = client.post(
                "/api/v1/messages",
                json={"message_type": "command", "content": "test"},
                headers={"Authorization": "Bearer test-token"},
            )

            assert response.status_code in (200, 202)
            body = response.json()
            assert body.get("decision") == "PENDING"
            assert body.get("reason") == "HUMAN_APPROVAL_REQUIRED"

            error_calls = [
                c for c in mock_logger.error.call_args_list if "hitl_submit_failed" in str(c)
            ]
            assert error_calls, "Expected a log entry for HITL submit failure"


# ---------------------------------------------------------------------------
# No repo configured (resolve_repo returns None)
# ---------------------------------------------------------------------------


class TestNoRepoConfigured:
    """When _resolve_repo returns None (misconfiguration), must fail closed."""

    @pytest.mark.unit
    def test_no_repo_returns_503(self) -> None:
        """resolve_repo returning None → HTTP 503 STORE_UNAVAILABLE."""
        app = _make_test_app(repo=None, hitl_client=None)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "command"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 503
        assert response.json().get("reason") == "STORE_UNAVAILABLE"

    @pytest.mark.unit
    def test_no_repo_emits_error_log(self) -> None:
        """Misconfigured repo → structured error log emitted."""
        app = _make_test_app(repo=None, hitl_client=None)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("src.core.services.api_gateway.middleware.autonomy_tier.logger") as mock_logger:
            client.post(
                "/api/v1/messages",
                json={"message_type": "command"},
                headers={"Authorization": "Bearer test-token"},
            )

            error_calls = [
                c for c in mock_logger.error.call_args_list if "no_repo_configured" in str(c)
            ]
            assert error_calls, "Expected error log for no_repo_configured"


# ---------------------------------------------------------------------------
# Resolve_repo timeout / ConnectionError (step 3 in dispatch)
# ---------------------------------------------------------------------------


class TestResolveRepoStoreFailure:
    """Timeout or connection error on _resolve_repo itself → 503."""

    @pytest.mark.unit
    def test_resolve_repo_timeout_returns_503(self) -> None:
        """When _resolve_repo hangs beyond store_timeout → 503."""

        async def slow_repo_override():
            await asyncio.sleep(100)
            return AsyncMock(spec=TierAssignmentRepository)

        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware, store_timeout=0.01)
        app.dependency_overrides[get_current_user] = lambda: _AGENT_CLAIMS
        app.dependency_overrides[get_tier_repo] = slow_repo_override
        app.state.hitl_client = None

        @app.post("/api/v1/messages")
        async def _dummy():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/messages",
            json={"message_type": "command"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 503
        assert response.json().get("reason") == "STORE_UNAVAILABLE"

    @pytest.mark.unit
    def test_resolve_repo_connection_error_returns_503(self) -> None:
        """ConnectionError during _resolve_repo → 503."""

        def raise_conn_error():
            raise ConnectionError("Redis connection refused")

        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware)
        app.dependency_overrides[get_current_user] = lambda: _AGENT_CLAIMS
        app.dependency_overrides[get_tier_repo] = raise_conn_error
        app.state.hitl_client = None

        @app.post("/api/v1/messages")
        async def _dummy():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/messages",
            json={"message_type": "command"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 503
        assert response.json().get("reason") == "STORE_UNAVAILABLE"

    @pytest.mark.unit
    def test_resolve_repo_os_error_returns_503(self) -> None:
        """OSError during _resolve_repo → 503."""

        def raise_os_error():
            raise OSError("Network unreachable")

        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware)
        app.dependency_overrides[get_current_user] = lambda: _AGENT_CLAIMS
        app.dependency_overrides[get_tier_repo] = raise_os_error
        app.state.hitl_client = None

        @app.post("/api/v1/messages")
        async def _dummy():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/messages",
            json={"message_type": "command"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 503


# ---------------------------------------------------------------------------
# Unauthenticated request on enforced path → 401
# ---------------------------------------------------------------------------


class TestUnauthenticatedRequest:
    """Requests with no valid user must receive 401."""

    @pytest.mark.unit
    def test_unauthenticated_returns_401(self) -> None:
        """No user resolved → HTTP 401 UNAUTHORIZED."""
        repo = AsyncMock(spec=TierAssignmentRepository)

        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware)
        # Override returns None → no authenticated user
        app.dependency_overrides[get_current_user] = lambda: None
        app.dependency_overrides[get_tier_repo] = lambda: repo
        app.state.hitl_client = None

        @app.post("/api/v1/messages")
        async def _dummy():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/messages",
            json={"message_type": "command"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 401
        assert response.json().get("reason") == "UNAUTHORIZED"


# ---------------------------------------------------------------------------
# Unknown/future tier value → forward to proxy (default case)
# ---------------------------------------------------------------------------


class TestUnknownTierCase:
    """Unrecognized tier values are forwarded to the proxy with an audit record."""

    @pytest.mark.unit
    def test_unknown_tier_forwards_to_proxy_approved(self) -> None:
        """Assignment with a non-standard tier value → forward, APPROVED."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        # Use MagicMock for assignment so we can set an arbitrary tier string
        assignment = MagicMock()
        assignment.tier = "EXPERIMENTAL"
        assignment.action_boundaries = None
        repo.get_by_agent.return_value = assignment

        app = _make_test_app(repo, hitl_client=None)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "command", "content": "test"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        assert response.headers.get("x-enforcement-decision") == "APPROVED"
        assert response.headers.get("x-autonomy-tier") == "experimental"

    @pytest.mark.unit
    @pytest.mark.constitutional
    def test_unknown_tier_emits_audit_record(self) -> None:
        """Unknown tier → audit record with TIER_FORWARDED reason."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        assignment = MagicMock()
        assignment.tier = "FUTURE_TIER"
        assignment.action_boundaries = None
        repo.get_by_agent.return_value = assignment

        app = _make_test_app(repo, hitl_client=None)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("src.core.services.api_gateway.middleware.autonomy_tier.logger") as mock_logger:
            client.post(
                "/api/v1/messages",
                json={"message_type": "command"},
                headers={"Authorization": "Bearer test-token"},
            )

            log_str = str(mock_logger.info.call_args_list)
            assert "TIER_FORWARDED" in log_str
            assert CONSTITUTIONAL_HASH in log_str


# ---------------------------------------------------------------------------
# Action type extraction edge cases
# ---------------------------------------------------------------------------


class TestActionTypeEdgeCases:
    """Edge cases in _extract_action_type method."""

    @pytest.mark.unit
    def test_invalid_json_body_falls_back_to_method_path(self) -> None:
        """Malformed JSON body → action_type = METHOD:path_segment."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/messages",
            content=b"not-valid-json{{{",
            headers={
                "Authorization": "Bearer test-token",
                "Content-Type": "application/json",
            },
        )

        assert response.status_code in (200, 202)
        call_kwargs = mock_hitl.submit.call_args.kwargs
        assert call_kwargs["action_type"] == "POST:messages"

    @pytest.mark.unit
    def test_empty_body_uses_method_path_fallback(self) -> None:
        """Empty request body → action_type = METHOD:path_segment."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/messages",
            content=b"",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code in (200, 202)
        call_kwargs = mock_hitl.submit.call_args.kwargs
        assert call_kwargs["action_type"] == "POST:messages"

    @pytest.mark.unit
    def test_non_dict_json_body_uses_fallback(self) -> None:
        """JSON array body (not dict) → action_type = METHOD:path_segment."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/messages",
            content=b'["not", "a", "dict"]',
            headers={
                "Authorization": "Bearer test-token",
                "Content-Type": "application/json",
            },
        )

        assert response.status_code in (200, 202)
        call_kwargs = mock_hitl.submit.call_args.kwargs
        assert call_kwargs["action_type"] == "POST:messages"


# ---------------------------------------------------------------------------
# Async dependency overrides (coroutine branch)
# ---------------------------------------------------------------------------


class TestAsyncDependencyOverrides:
    """Verify that async dependency overrides (returning coroutines) work."""

    @pytest.mark.unit
    def test_async_user_override_works(self) -> None:
        """get_current_user override returning coroutine is properly awaited."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware)

        async def async_user():
            return _AGENT_CLAIMS

        app.dependency_overrides[get_current_user] = async_user
        app.dependency_overrides[get_tier_repo] = lambda: repo
        app.state.hitl_client = mock_hitl

        @app.post("/api/v1/messages")
        async def _dummy():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/messages",
            json={"message_type": "command"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code in (200, 202)
        assert response.json().get("decision") == "PENDING"

    @pytest.mark.unit
    def test_async_repo_override_works(self) -> None:
        """get_tier_repo override returning coroutine is properly awaited."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware)

        async def async_repo():
            return repo

        app.dependency_overrides[get_current_user] = lambda: _AGENT_CLAIMS
        app.dependency_overrides[get_tier_repo] = async_repo
        app.state.hitl_client = mock_hitl

        @app.post("/api/v1/messages")
        async def _dummy():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/messages",
            json={"message_type": "command"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code in (200, 202)
        assert response.json().get("decision") == "PENDING"


# ---------------------------------------------------------------------------
# HttpHitlSubmissionClient real implementation
# ---------------------------------------------------------------------------


class TestHttpHitlSubmissionClient:
    """Test the real HTTP HITL submission client implementation."""

    @pytest.mark.unit
    def test_init_strips_trailing_slash(self) -> None:
        """HttpHitlSubmissionClient strips trailing slash from URL."""
        client = HttpHitlSubmissionClient(url="http://hitl:8002/")
        assert client._url == "http://hitl:8002"

    @pytest.mark.unit
    def test_init_preserves_clean_url(self) -> None:
        """HttpHitlSubmissionClient preserves URL without trailing slash."""
        client = HttpHitlSubmissionClient(url="http://hitl:8002")
        assert client._url == "http://hitl:8002"

    @pytest.mark.unit
    async def test_submit_posts_to_reviews_endpoint(self) -> None:
        """submit() POSTs to /api/v1/reviews with correct payload."""
        client_instance = HttpHitlSubmissionClient(url="http://fake-hitl:8002")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "src.core.services.api_gateway.middleware.autonomy_tier.httpx.AsyncClient",
            return_value=mock_http,
        ):
            await client_instance.submit(
                decision_id="dec-001",
                agent_id="agent-001",
                tenant_id="tenant-001",
                action_type="read:status",
                tier="ADVISORY",
                context={"constitutional_hash": CONSTITUTIONAL_HASH},
            )

            mock_http.post.assert_awaited_once()
            call_args = mock_http.post.call_args
            assert "http://fake-hitl:8002/api/v1/reviews" == call_args.args[0]

            payload = call_args.kwargs["json"]
            assert payload["decision_id"] == "dec-001"
            assert payload["tenant_id"] == "tenant-001"
            assert payload["requested_by"] == "agent-001"
            assert payload["priority"] == "standard"
            assert payload["context"]["agent_id"] == "agent-001"
            assert payload["context"]["tier"] == "ADVISORY"
            assert payload["context"]["action_type"] == "read:status"
            assert payload["context"]["constitutional_hash"] == CONSTITUTIONAL_HASH

    @pytest.mark.unit
    async def test_submit_raises_for_http_error(self) -> None:
        """submit() propagates httpx.HTTPStatusError on 4xx/5xx."""
        import httpx as httpx_lib

        client_instance = HttpHitlSubmissionClient(url="http://fake-hitl:8002")

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx_lib.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "src.core.services.api_gateway.middleware.autonomy_tier.httpx.AsyncClient",
                return_value=mock_http,
            ),
            pytest.raises(httpx_lib.HTTPStatusError),
        ):
            await client_instance.submit(
                decision_id="dec-002",
                agent_id="agent-002",
                tenant_id="tenant-002",
                action_type="write:config",
                tier="HUMAN_APPROVED",
                context={},
            )


# ---------------------------------------------------------------------------
# Production resolve paths (no dependency override set)
# ---------------------------------------------------------------------------


class TestProductionResolvePaths:
    """Test the production (non-override) resolve paths for user and repo."""

    @pytest.mark.unit
    def test_resolve_user_with_invalid_bearer_returns_none(self) -> None:
        """Bearer token that fails verify_token → user=None → 401."""
        repo = AsyncMock(spec=TierAssignmentRepository)

        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware)
        # Do NOT set get_current_user override — force production path
        app.dependency_overrides[get_tier_repo] = lambda: repo
        app.state.hitl_client = None

        @app.post("/api/v1/messages")
        async def _dummy():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)

        # Mock verify_token to raise (invalid token)
        with patch(
            "src.core.shared.security.auth.verify_token",
            side_effect=ValueError("Invalid token"),
        ):
            response = client.post(
                "/api/v1/messages",
                json={"message_type": "command"},
                headers={"Authorization": "Bearer invalid-jwt-token"},
            )

        assert response.status_code == 401
        assert response.json().get("reason") == "UNAUTHORIZED"

    @pytest.mark.unit
    def test_resolve_user_no_auth_header_returns_none(self) -> None:
        """No Authorization header → user=None → 401."""
        repo = AsyncMock(spec=TierAssignmentRepository)

        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware)
        # Do NOT set get_current_user override
        app.dependency_overrides[get_tier_repo] = lambda: repo
        app.state.hitl_client = None

        @app.post("/api/v1/messages")
        async def _dummy():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/messages",
            json={"message_type": "command"},
        )

        assert response.status_code == 401

    @pytest.mark.unit
    def test_resolve_user_with_valid_bearer_token(self) -> None:
        """Valid Bearer token → verify_token returns UserClaims → proceeds."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware)
        # Do NOT set get_current_user override — force production path
        app.dependency_overrides[get_tier_repo] = lambda: repo
        app.state.hitl_client = mock_hitl

        @app.post("/api/v1/messages")
        async def _dummy():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)

        with patch(
            "src.core.shared.security.auth.verify_token",
            return_value=_AGENT_CLAIMS,
        ):
            response = client.post(
                "/api/v1/messages",
                json={"message_type": "command"},
                headers={"Authorization": "Bearer valid-jwt-token"},
            )

        assert response.status_code in (200, 202)
        assert response.json().get("decision") == "PENDING"

    @pytest.mark.unit
    def test_resolve_repo_via_app_state_factory(self) -> None:
        """No get_tier_repo override → falls back to app.state.tier_repo_factory."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware)
        app.dependency_overrides[get_current_user] = lambda: _AGENT_CLAIMS
        # Do NOT set get_tier_repo override — use app.state.tier_repo_factory
        app.state.tier_repo_factory = lambda: repo
        app.state.hitl_client = mock_hitl

        @app.post("/api/v1/messages")
        async def _dummy():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/messages",
            json={"message_type": "command"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code in (200, 202)
        assert response.json().get("decision") == "PENDING"

    @pytest.mark.unit
    def test_resolve_repo_via_async_app_state_factory(self) -> None:
        """app.state.tier_repo_factory returns async → properly awaited."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware)
        app.dependency_overrides[get_current_user] = lambda: _AGENT_CLAIMS
        # Do NOT set get_tier_repo override — use async app.state.tier_repo_factory

        async def async_factory():
            return repo

        app.state.tier_repo_factory = async_factory
        app.state.hitl_client = mock_hitl

        @app.post("/api/v1/messages")
        async def _dummy():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/messages",
            json={"message_type": "command"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code in (200, 202)
        assert response.json().get("decision") == "PENDING"

    @pytest.mark.unit
    def test_resolve_repo_no_factory_returns_none(self) -> None:
        """No get_tier_repo override and no tier_repo_factory → repo=None → 503."""
        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware)
        app.dependency_overrides[get_current_user] = lambda: _AGENT_CLAIMS
        # Do NOT set get_tier_repo override and do NOT set tier_repo_factory
        app.state.hitl_client = None

        @app.post("/api/v1/messages")
        async def _dummy():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/messages",
            json={"message_type": "command"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 503
        assert response.json().get("reason") == "STORE_UNAVAILABLE"
