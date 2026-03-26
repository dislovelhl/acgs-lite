"""Unit tests for AutonomyTierEnforcementMiddleware.
Constitutional Hash: 608508a9bd224290

Covers:
  - Advisory tier path: returns PENDING + submits to HITL
  - No-tier path: returns HTTP 403, HITL NOT called
  - Fail-closed path: store timeout → HTTP 503, HITL NOT called
  - Audit record field completeness (constitutional_hash present)
  - X-Autonomy-Tier response header on PENDING response
  - T019: Human-approved tier path — PENDING, HITL called, no proxy forwarding
  - T023: Alert threshold — 5 BOUNDARY_EXCEEDED events emit structured log fields
  - T027 coverage additions:
    - HttpHitlSubmissionClient construction and submit (httpx mock)
    - Async dependency override paths (_resolve_user, _resolve_repo)
    - app.state.tier_repo_factory fallback path
    - _extract_action_type: empty body and invalid JSON body
    - Unauthenticated request (no user) → 401
    - _resolve_repo itself raises ConnectionError → 503
    - repo is None (no factory in state) → 503
    - Unknown tier dispatch → APPROVED forward
    - Advisory HITL submit exception → still returns PENDING
    - Human-approved HITL submit exception → still returns PENDING
    - Bounded APPROVED path (in-boundary action → forward to proxy)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.services.api_gateway.middleware.autonomy_tier import (
    AutonomyTierEnforcementMiddleware,
    HitlSubmissionClient,
    HttpHitlSubmissionClient,
)
from src.core.services.api_gateway.models.tier_assignment import AgentTierAssignment, AutonomyTier
from src.core.services.api_gateway.repositories.tier_assignment import TierAssignmentRepository
from src.core.services.api_gateway.routes.autonomy_tiers import get_tier_repo
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.security.auth import UserClaims, get_current_user

CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Fixtures / Helpers
# ---------------------------------------------------------------------------

_AGENT_ID = "agent-unit-001"
_TENANT_ID = "tenant-unit-test"

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
    repo: TierAssignmentRepository,
    user: UserClaims = _AGENT_CLAIMS,
    hitl_client: HitlSubmissionClient | None = None,
) -> FastAPI:
    """Build a minimal FastAPI test app with the enforcement middleware registered.

    Dependency overrides are used so no real DB or Redis connections are made.
    """
    app = FastAPI()
    app.add_middleware(AutonomyTierEnforcementMiddleware)

    # Override auth and repo dependencies so the middleware can resolve them
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_tier_repo] = lambda: repo

    # Store HITL client override on app.state
    app.state.hitl_client = hitl_client

    # Minimal passthrough route to confirm middleware lets approved requests through
    @app.post("/api/v1/messages")
    async def _dummy_messages():
        return {"status": "ok"}

    return app


# ---------------------------------------------------------------------------
# T014-A: Advisory tier → PENDING, HitlSubmissionClient called once
# ---------------------------------------------------------------------------


class TestAdvisoryTierPath:
    """Advisory-tier requests must be queued for HITL review and return PENDING."""

    @pytest.mark.unit
    def test_advisory_returns_pending_response(self) -> None:
        """POST /api/v1/messages from advisory-tier agent → body decision=PENDING."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "command", "content": "do something"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code in (200, 202), response.text
        body = response.json()
        assert body.get("decision") == "PENDING"
        assert "request_id" in body

    @pytest.mark.unit
    def test_advisory_calls_hitl_client_once(self) -> None:
        """HitlSubmissionClient.submit is called exactly once with correct agent_id and action_type."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        client.post(
            "/api/v1/messages",
            json={"message_type": "command", "content": "do something"},
            headers={"Authorization": "Bearer test-token"},
        )

        mock_hitl.submit.assert_awaited_once()
        call_kwargs = mock_hitl.submit.call_args.kwargs
        assert call_kwargs["agent_id"] == _AGENT_ID
        assert call_kwargs["action_type"] == "command"
        assert call_kwargs["tier"] == "ADVISORY"

    @pytest.mark.unit
    def test_advisory_response_header_set(self) -> None:
        """X-Autonomy-Tier header must be 'advisory' on PENDING response."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "command", "content": "do something"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.headers.get("x-autonomy-tier") == "advisory"
        assert response.headers.get("x-enforcement-decision") == "PENDING"

    @pytest.mark.unit
    def test_advisory_action_type_fallback(self) -> None:
        """When message_type is absent, action_type falls back to METHOD:path_segment."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        client.post(
            "/api/v1/messages",
            json={"content": "no message_type here"},
            headers={"Authorization": "Bearer test-token"},
        )

        call_kwargs = mock_hitl.submit.call_args.kwargs
        # Fallback: POST:messages
        assert call_kwargs["action_type"] == "POST:messages"


# ---------------------------------------------------------------------------
# T014-B: No-tier path → HTTP 403, HITL NOT called
# ---------------------------------------------------------------------------


class TestNoTierPath:
    """Agents with no tier assignment must be rejected with HTTP 403."""

    @pytest.mark.unit
    def test_no_tier_returns_403(self) -> None:
        """get_by_agent returns None → HTTP 403, reason=NO_TIER_ASSIGNED."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = None
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "command"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 403
        assert response.json().get("reason") == "NO_TIER_ASSIGNED"

    @pytest.mark.unit
    def test_no_tier_hitl_not_called(self) -> None:
        """HITL client must NOT be called when the agent has no tier assignment."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = None
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        client.post(
            "/api/v1/messages",
            json={"message_type": "command"},
            headers={"Authorization": "Bearer test-token"},
        )

        mock_hitl.submit.assert_not_awaited()


# ---------------------------------------------------------------------------
# T014-C: Fail-closed path — store timeout → HTTP 503, HITL NOT called
# ---------------------------------------------------------------------------


class TestFailClosedPath:
    """Store timeout / connection errors must result in HTTP 503 with no action execution."""

    @pytest.mark.unit
    def test_store_timeout_returns_503(self) -> None:
        """asyncio.TimeoutError on store lookup → HTTP 503, reason=STORE_UNAVAILABLE."""

        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.side_effect = TimeoutError()
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = _make_test_app(repo, hitl_client=mock_hitl)
        # Use very short timeout so the test is fast
        # Access middleware instance and patch timeout
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "command"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 503
        assert response.json().get("reason") == "STORE_UNAVAILABLE"

    @pytest.mark.unit
    def test_store_timeout_hitl_not_called(self) -> None:
        """HITL client must NOT be called when the store is unavailable."""

        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.side_effect = TimeoutError()
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        client.post(
            "/api/v1/messages",
            json={"message_type": "command"},
            headers={"Authorization": "Bearer test-token"},
        )

        mock_hitl.submit.assert_not_awaited()

    @pytest.mark.unit
    def test_store_timeout_emits_alert_log(self) -> None:
        """A structured alert log must be emitted when the store is unavailable."""

        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.side_effect = TimeoutError()
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("src.core.services.api_gateway.middleware.autonomy_tier.logger") as mock_logger:
            client.post(
                "/api/v1/messages",
                json={"message_type": "command"},
                headers={"Authorization": "Bearer test-token"},
            )
            # Expect at least one error-level log mentioning store unavailability
            error_calls = [
                call
                for call in mock_logger.error.call_args_list
                if "store_unavailable" in str(call).lower() or "STORE_UNAVAILABLE" in str(call)
            ]
            assert error_calls, "Expected a structured alert log for store unavailability"


# ---------------------------------------------------------------------------
# T014-D: Audit record field completeness
# ---------------------------------------------------------------------------


class TestAuditRecord:
    """Every enforcement evaluation must emit a TierEnforcementDecision with constitutional_hash."""

    @pytest.mark.unit
    @pytest.mark.constitutional
    def test_audit_contains_constitutional_hash(self) -> None:
        """Advisory tier audit log must include constitutional_hash=608508a9bd224290."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("src.core.services.api_gateway.middleware.autonomy_tier.logger") as mock_logger:
            client.post(
                "/api/v1/messages",
                json={"message_type": "command"},
                headers={"Authorization": "Bearer test-token"},
            )
            # Check that the audit log call includes the constitutional hash
            logged_with_hash = any(
                CONSTITUTIONAL_HASH in str(call) for call in mock_logger.info.call_args_list
            )
            assert logged_with_hash, (
                f"Expected an audit log entry containing "
                f"constitutional_hash={CONSTITUTIONAL_HASH!r}"
            )

    @pytest.mark.unit
    @pytest.mark.constitutional
    def test_no_tier_audit_contains_constitutional_hash(self) -> None:
        """No-tier audit log must also include constitutional_hash."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = None
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("src.core.services.api_gateway.middleware.autonomy_tier.logger") as mock_logger:
            client.post(
                "/api/v1/messages",
                json={"message_type": "command"},
                headers={"Authorization": "Bearer test-token"},
            )
            logged_with_hash = any(
                CONSTITUTIONAL_HASH in str(call) for call in mock_logger.info.call_args_list
            )
            assert logged_with_hash, (
                f"Expected audit log with constitutional_hash={CONSTITUTIONAL_HASH!r} "
                f"for NO_TIER_ASSIGNED outcome"
            )


# ---------------------------------------------------------------------------
# T014-E: Non-enforced paths pass through unchanged
# ---------------------------------------------------------------------------


class TestNonEnforcedPaths:
    """Requests to non-proxied paths must bypass tier enforcement."""

    @pytest.mark.unit
    def test_health_path_not_enforced(self) -> None:
        """GET /health must pass through without enforcement (no tier lookup)."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware)
        app.dependency_overrides[get_current_user] = lambda: _AGENT_CLAIMS
        app.dependency_overrides[get_tier_repo] = lambda: repo
        app.state.hitl_client = mock_hitl

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health")

        assert response.status_code == 200
        repo.get_by_agent.assert_not_awaited()


# ---------------------------------------------------------------------------
# T019: Human-approved tier path — PENDING, HITL called, no proxy forwarding
# ---------------------------------------------------------------------------


class TestHumanApprovedTierPath:
    """Human-approved-tier requests must route to HITL for every action type
    and return PENDING with reason=HUMAN_APPROVAL_REQUIRED without proxy forwarding."""

    @pytest.mark.unit
    def test_human_approved_returns_pending_with_reason(self) -> None:
        """POST /api/v1/messages from human-approved agent → decision=PENDING,
        reason=HUMAN_APPROVAL_REQUIRED."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.HUMAN_APPROVED)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "read:documents", "content": "human action"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code in (200, 202), response.text
        body = response.json()
        assert body.get("decision") == "PENDING"
        assert body.get("reason") == "HUMAN_APPROVAL_REQUIRED"
        assert "request_id" in body

    @pytest.mark.unit
    def test_human_approved_calls_hitl_client_once_with_correct_payload(self) -> None:
        """HitlSubmissionClient.submit is called exactly once with agent_id,
        action_type, and tier=HUMAN_APPROVED."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.HUMAN_APPROVED)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        client.post(
            "/api/v1/messages",
            json={"message_type": "execute:job", "content": "human action"},
            headers={"Authorization": "Bearer test-token"},
        )

        mock_hitl.submit.assert_awaited_once()
        call_kwargs = mock_hitl.submit.call_args.kwargs
        assert call_kwargs["agent_id"] == _AGENT_ID
        assert call_kwargs["action_type"] == "execute:job"
        assert call_kwargs["tier"] == "HUMAN_APPROVED"

    @pytest.mark.unit
    @pytest.mark.constitutional
    def test_human_approved_audit_record_fields(self) -> None:
        """Audit record: outcome=PENDING, reason=HUMAN_APPROVAL_REQUIRED,
        tier_at_decision=HUMAN_APPROVED, constitutional_hash present."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.HUMAN_APPROVED)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("src.core.services.api_gateway.middleware.autonomy_tier.logger") as mock_logger:
            client.post(
                "/api/v1/messages",
                json={"message_type": "configure:settings", "content": ""},
                headers={"Authorization": "Bearer test-token"},
            )

            log_str = str(mock_logger.info.call_args_list)
            assert "HUMAN_APPROVED" in log_str, "Expected tier_at_decision=HUMAN_APPROVED in audit"
            assert "PENDING" in log_str, "Expected outcome=PENDING in audit"
            assert "HUMAN_APPROVAL_REQUIRED" in log_str, (
                "Expected reason=HUMAN_APPROVAL_REQUIRED in audit"
            )
            assert CONSTITUTIONAL_HASH in log_str, (
                f"Expected constitutional_hash={CONSTITUTIONAL_HASH!r} in audit"
            )

    @pytest.mark.unit
    def test_human_approved_no_proxy_forwarding(self) -> None:
        """Human-approved request must NOT be forwarded to the downstream service."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.HUMAN_APPROVED)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "delete:records", "content": ""},
            headers={"Authorization": "Bearer test-token"},
        )

        body = response.json()
        # Proxy passthrough would return {"status": "ok"} — PENDING response confirms skip
        assert body.get("decision") == "PENDING"
        assert body.get("reason") == "HUMAN_APPROVAL_REQUIRED"
        # If accidentally forwarded, downstream mock returns {"status": "ok"}
        assert body.get("status") != "ok"


# ---------------------------------------------------------------------------
# T023 — Alert threshold: repeated BOUNDARY_EXCEEDED events → structured logs
# ---------------------------------------------------------------------------


class TestBoundaryExceededAlertThreshold:
    """
    US-005: Repeated BOUNDARY_EXCEEDED decisions from the same agent must emit
    structured log entries with all required fields so that Prometheus alert rules
    can aggregate them without additional code changes.

    Verifies field names explicitly (not just message text) so that the log schema
    is sufficient for alerting.
    """

    _BLOCKED_ACTION_TYPES: ClassVar[list] = [
        "write:documents",
        "delete:records",
        "execute:pipeline",
        "configure:settings",
        "admin:users",
    ]

    @pytest.mark.unit
    def test_five_boundary_exceeded_events_emitted(self) -> None:
        """5 consecutive BOUNDARY_EXCEEDED decisions → 5 structured log events."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(
            AutonomyTier.BOUNDED,
            action_boundaries=["read:*"],
        )

        app = _make_test_app(repo, hitl_client=None)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("src.core.services.api_gateway.middleware.autonomy_tier.logger") as mock_logger:
            for action_type in self._BLOCKED_ACTION_TYPES:
                response = client.post(
                    "/api/v1/messages",
                    json={"message_type": action_type, "content": ""},
                    headers={"Authorization": "Bearer test-token"},
                )
                assert response.status_code == 403, (
                    f"action_type={action_type!r}: expected 403, got {response.status_code}"
                )

            boundary_exceeded_calls = [
                call
                for call in mock_logger.info.call_args_list
                if call.args
                and call.args[0] == "tier_enforcement.decision"
                and call.kwargs.get("reason") == "BOUNDARY_EXCEEDED"
            ]

            assert len(boundary_exceeded_calls) == 5, (
                f"Expected 5 BOUNDARY_EXCEEDED log events, got {len(boundary_exceeded_calls)}. "
                f"All decision calls: "
                f"{[c.kwargs.get('reason') for c in mock_logger.info.call_args_list if c.args and c.args[0] == 'tier_enforcement.decision']}"
            )

    @pytest.mark.unit
    def test_boundary_exceeded_log_fields_present(self) -> None:
        """Each BOUNDARY_EXCEEDED log event contains all required structured fields.

        Asserts on specific kwarg field names — not just message text — so that
        Prometheus alert rules aggregating on these fields will function correctly
        without any additional code changes.
        """
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(
            AutonomyTier.BOUNDED,
            action_boundaries=["read:*"],
        )

        app = _make_test_app(repo, hitl_client=None)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("src.core.services.api_gateway.middleware.autonomy_tier.logger") as mock_logger:
            for action_type in self._BLOCKED_ACTION_TYPES:
                client.post(
                    "/api/v1/messages",
                    json={"message_type": action_type, "content": ""},
                    headers={"Authorization": "Bearer test-token"},
                )

            boundary_exceeded_calls = [
                call
                for call in mock_logger.info.call_args_list
                if call.args
                and call.args[0] == "tier_enforcement.decision"
                and call.kwargs.get("reason") == "BOUNDARY_EXCEEDED"
            ]

            assert len(boundary_exceeded_calls) == 5

            for i, call in enumerate(boundary_exceeded_calls):
                kwargs = call.kwargs
                # Verify each field by name — not just string presence in serialised repr
                assert kwargs.get("agent_id") == _AGENT_ID, (
                    f"Event {i}: agent_id={kwargs.get('agent_id')!r}, expected {_AGENT_ID!r}"
                )
                assert kwargs.get("tenant_id") == _TENANT_ID, (
                    f"Event {i}: tenant_id={kwargs.get('tenant_id')!r}, expected {_TENANT_ID!r}"
                )
                assert kwargs.get("outcome") == "BLOCKED", (
                    f"Event {i}: outcome={kwargs.get('outcome')!r}, expected 'BLOCKED'"
                )
                assert kwargs.get("reason") == "BOUNDARY_EXCEEDED", (
                    f"Event {i}: reason={kwargs.get('reason')!r}, expected 'BOUNDARY_EXCEEDED'"
                )
                assert kwargs.get("action_type") in self._BLOCKED_ACTION_TYPES, (
                    f"Event {i}: action_type={kwargs.get('action_type')!r} not in expected set"
                )
                assert kwargs.get("constitutional_hash") == CONSTITUTIONAL_HASH, (
                    f"Event {i}: constitutional_hash={kwargs.get('constitutional_hash')!r}, "
                    f"expected {CONSTITUTIONAL_HASH!r}"
                )


# ---------------------------------------------------------------------------
# T027 coverage: HttpHitlSubmissionClient construction and submit
# ---------------------------------------------------------------------------


class TestHttpHitlSubmissionClient:
    """Unit tests for the real HttpHitlSubmissionClient implementation."""

    @pytest.mark.unit
    def test_init_strips_trailing_slash(self) -> None:
        """HttpHitlSubmissionClient strips trailing slash from URL on construction."""
        client = HttpHitlSubmissionClient(url="http://hitl:8002/")
        assert client._url == "http://hitl:8002"

    @pytest.mark.unit
    async def test_submit_posts_to_hitl_reviews_endpoint(self) -> None:
        """submit() POSTs to /api/v1/reviews and raises on HTTP error."""

        client = HttpHitlSubmissionClient(url="http://hitl:8002")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_async_client = AsyncMock()
            mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
            mock_async_client.__aexit__ = AsyncMock(return_value=False)
            mock_async_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_async_client

            await client.submit(
                decision_id="req-123",
                agent_id="agent-1",
                tenant_id="tenant-1",
                action_type="read:status",
                tier="ADVISORY",
                context={"constitutional_hash": CONSTITUTIONAL_HASH},
            )

            mock_async_client.post.assert_awaited_once()
            call_args = mock_async_client.post.call_args
            assert "/api/v1/reviews" in str(call_args)


# ---------------------------------------------------------------------------
# T027 coverage: async dependency override paths
# ---------------------------------------------------------------------------


class TestAsyncDependencyOverrides:
    """Coverage for coroutine-returning dependency overrides in _resolve_user and _resolve_repo."""

    @pytest.mark.unit
    def test_async_user_override_resolved(self) -> None:
        """_resolve_user accepts async overrides (coroutine-returning callables)."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware)

        # Use an async callable as the dependency override
        async def async_user_override():
            return _AGENT_CLAIMS

        app.dependency_overrides[get_current_user] = async_user_override
        app.dependency_overrides[get_tier_repo] = lambda: repo
        app.state.hitl_client = mock_hitl

        @app.post("/api/v1/messages")
        async def _dummy():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/messages",
            json={"message_type": "query"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code in (200, 202)
        assert response.json().get("decision") == "PENDING"

    @pytest.mark.unit
    def test_async_repo_override_resolved(self) -> None:
        """_resolve_repo accepts async overrides (coroutine-returning callables)."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware)
        app.dependency_overrides[get_current_user] = lambda: _AGENT_CLAIMS

        # Use an async callable as the repo override
        async def async_repo_override():
            return repo

        app.dependency_overrides[get_tier_repo] = async_repo_override
        app.state.hitl_client = mock_hitl

        @app.post("/api/v1/messages")
        async def _dummy():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/messages",
            json={"message_type": "query"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code in (200, 202)

    @pytest.mark.unit
    def test_tier_repo_factory_in_app_state(self) -> None:
        """_resolve_repo uses app.state.tier_repo_factory when no dependency override is set."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = None  # → 403 NO_TIER_ASSIGNED
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware)
        # Only override user, NOT the repo — let it fall through to factory
        app.dependency_overrides[get_current_user] = lambda: _AGENT_CLAIMS

        # Set factory on app.state (the production fallback)
        app.state.tier_repo_factory = lambda: repo
        app.state.hitl_client = mock_hitl

        @app.post("/api/v1/messages")
        async def _dummy():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/messages",
            json={"message_type": "query"},
            headers={"Authorization": "Bearer test-token"},
        )
        # With no tier assignment the factory path returns repo → get_by_agent returns None → 403
        assert response.status_code == 403
        assert response.json().get("reason") == "NO_TIER_ASSIGNED"


# ---------------------------------------------------------------------------
# T027 coverage: _extract_action_type edge cases
# ---------------------------------------------------------------------------


class TestExtractActionType:
    """Coverage for _extract_action_type: empty body and invalid JSON."""

    @pytest.mark.unit
    def test_empty_body_falls_back_to_method_path(self) -> None:
        """Empty request body falls back to METHOD:path_segment."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        # Send request with no body (empty bytes)
        response = client.post(
            "/api/v1/messages",
            content=b"",
            headers={"Authorization": "Bearer test-token", "Content-Type": "application/json"},
        )
        assert response.status_code in (200, 202)
        # HITL should have been called with fallback action_type
        call_kwargs = mock_hitl.submit.call_args.kwargs
        # Fallback: POST:messages
        assert call_kwargs["action_type"] == "POST:messages"

    @pytest.mark.unit
    def test_invalid_json_body_falls_back_to_method_path(self) -> None:
        """Invalid JSON body falls back to METHOD:path_segment action type."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = _make_test_app(repo, hitl_client=mock_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/messages",
            content=b"not-valid-json{{{",
            headers={"Authorization": "Bearer test-token", "Content-Type": "application/json"},
        )
        assert response.status_code in (200, 202)
        call_kwargs = mock_hitl.submit.call_args.kwargs
        assert call_kwargs["action_type"] == "POST:messages"


# ---------------------------------------------------------------------------
# T027 coverage: unauthenticated request → 401
# ---------------------------------------------------------------------------


class TestUnauthenticatedRequest:
    """Requests with no resolvable user identity must return 401."""

    @pytest.mark.unit
    def test_no_user_returns_401(self) -> None:
        """Middleware returns 401 when _resolve_user returns None."""
        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware)
        # Override returns None (no authenticated user)
        app.dependency_overrides[get_current_user] = lambda: None

        @app.post("/api/v1/messages")
        async def _dummy():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/messages",
            json={"message_type": "query"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# T027 coverage: _resolve_repo itself raises (ConnectionError → 503)
# ---------------------------------------------------------------------------


class TestRepoResolveError:
    """ConnectionError during _resolve_repo must return 503 (fail-closed)."""

    @pytest.mark.unit
    def test_repo_resolve_connection_error_returns_503(self) -> None:
        """ConnectionError in the repo override returns 503 STORE_UNAVAILABLE."""
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware)
        app.dependency_overrides[get_current_user] = lambda: _AGENT_CLAIMS

        def _bad_repo_override():
            raise ConnectionError("Redis connection refused")

        app.dependency_overrides[get_tier_repo] = _bad_repo_override
        app.state.hitl_client = mock_hitl

        @app.post("/api/v1/messages")
        async def _dummy():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/messages",
            json={"message_type": "query"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 503
        assert response.json().get("reason") == "STORE_UNAVAILABLE"

    @pytest.mark.unit
    def test_no_repo_configured_returns_503(self) -> None:
        """When _resolve_repo returns None (no override, no factory), middleware returns 503."""
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware)
        # Only override user; no get_tier_repo override and no tier_repo_factory in state
        app.dependency_overrides[get_current_user] = lambda: _AGENT_CLAIMS
        app.state.hitl_client = mock_hitl
        # Explicitly ensure no tier_repo_factory is set
        if hasattr(app.state, "tier_repo_factory"):
            del app.state.tier_repo_factory

        @app.post("/api/v1/messages")
        async def _dummy():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/messages",
            json={"message_type": "query"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 503
        assert response.json().get("reason") == "STORE_UNAVAILABLE"


# ---------------------------------------------------------------------------
# T027 coverage: unknown tier dispatch → APPROVED forward
# ---------------------------------------------------------------------------


class TestUnknownTierDispatch:
    """Unknown/future tier values must forward to proxy with APPROVED audit record."""

    @pytest.mark.unit
    def test_unknown_tier_forwards_to_proxy(self) -> None:
        """A tier value not in the known match/case arms is forwarded with APPROVED."""

        # Manufacture an assignment with a tier value that won't match any known case.
        # We patch the tier attribute directly to bypass the StrEnum constraint.
        assignment = _make_assignment(AutonomyTier.ADVISORY)
        assignment.tier = "FUTURE_TIER"  # type: ignore[assignment]

        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = assignment

        app = _make_test_app(repo, hitl_client=None)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "query"},
            headers={"Authorization": "Bearer test-token"},
        )
        # Forwarded to proxy → dummy endpoint returns {"status": "ok"}
        assert response.status_code == 200
        assert response.headers.get("x-enforcement-decision") == "APPROVED"


# ---------------------------------------------------------------------------
# T027 coverage: HITL submit exception handling (advisory and human-approved)
# ---------------------------------------------------------------------------


class TestHitlSubmitExceptionHandling:
    """HITL submission failures must not prevent the PENDING response from being returned."""

    @pytest.mark.unit
    def test_advisory_hitl_exception_still_returns_pending(self) -> None:
        """Advisory path: HITL submit raises → middleware still returns PENDING."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)

        failing_hitl = AsyncMock(spec=HitlSubmissionClient)
        failing_hitl.submit.side_effect = Exception("HITL service unreachable")

        app = _make_test_app(repo, hitl_client=failing_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "command"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code in (200, 202)
        assert response.json().get("decision") == "PENDING"

    @pytest.mark.unit
    def test_human_approved_hitl_exception_still_returns_pending(self) -> None:
        """Human-approved path: HITL submit raises → middleware still returns PENDING."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.HUMAN_APPROVED)

        failing_hitl = AsyncMock(spec=HitlSubmissionClient)
        failing_hitl.submit.side_effect = Exception("HITL service unreachable")

        app = _make_test_app(repo, hitl_client=failing_hitl)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "delete:records"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code in (200, 202)
        assert response.json().get("decision") == "PENDING"
        assert response.json().get("reason") == "HUMAN_APPROVAL_REQUIRED"


# ---------------------------------------------------------------------------
# T027 coverage: bounded APPROVED path (in-boundary action → forward to proxy)
# ---------------------------------------------------------------------------


class TestBoundedApprovedPath:
    """Bounded agent with a matching boundary must be forwarded to proxy (APPROVED)."""

    @pytest.mark.unit
    def test_bounded_in_boundary_action_approved_and_forwarded(self) -> None:
        """In-boundary action → proxy receives request, response decision=APPROVED."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(
            AutonomyTier.BOUNDED,
            action_boundaries=["read:*", "query"],
        )

        app = _make_test_app(repo, hitl_client=None)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "read:documents", "content": "fetch docs"},
            headers={"Authorization": "Bearer test-token"},
        )
        # Proxy (dummy endpoint) returns 200 {"status": "ok"}
        assert response.status_code == 200
        assert response.headers.get("x-autonomy-tier") == "bounded"
        assert response.headers.get("x-enforcement-decision") == "APPROVED"

    @pytest.mark.unit
    def test_bounded_empty_boundaries_blocked(self) -> None:
        """Bounded agent with empty action_boundaries → all actions BLOCKED (fail-closed)."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(
            AutonomyTier.BOUNDED,
            action_boundaries=[],
        )

        app = _make_test_app(repo, hitl_client=None)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "read:documents"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 403
        assert response.json().get("reason") == "BOUNDARY_EXCEEDED"


# ---------------------------------------------------------------------------
# T027 coverage: remaining branch gaps
# ---------------------------------------------------------------------------


class TestRemainingBranchCoverage:
    """Cover the remaining uncovered branches and lines for >= 95% target."""

    @pytest.mark.unit
    def test_advisory_no_hitl_client_skips_submit(self) -> None:
        """Advisory path with hitl_client=None skips HITL submit and still returns PENDING."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)

        # hitl_client=None → the `if hitl_client is not None:` branch is False
        app = _make_test_app(repo, hitl_client=None)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "query"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code in (200, 202)
        assert response.json().get("decision") == "PENDING"

    @pytest.mark.unit
    def test_human_approved_no_hitl_client_skips_submit(self) -> None:
        """Human-approved path with hitl_client=None skips HITL submit and still returns PENDING."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.HUMAN_APPROVED)

        # hitl_client=None → the `if hitl_client is not None:` branch is False
        app = _make_test_app(repo, hitl_client=None)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "delete:records"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code in (200, 202)
        assert response.json().get("decision") == "PENDING"
        assert response.json().get("reason") == "HUMAN_APPROVAL_REQUIRED"

    @pytest.mark.unit
    def test_resolve_user_non_override_bearer_token_path(self) -> None:
        """_resolve_user falls back to verify_token when no dependency override is set."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)
        mock_hitl = AsyncMock(spec=HitlSubmissionClient)

        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware)
        # Deliberately do NOT set get_current_user override — forces real Bearer path
        app.dependency_overrides[get_tier_repo] = lambda: repo
        app.state.hitl_client = mock_hitl

        @app.post("/api/v1/messages")
        async def _dummy():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)

        # Patch verify_token so the token resolves successfully
        with patch(
            "src.core.shared.security.auth.verify_token",
            return_value=_AGENT_CLAIMS,
        ):
            response = client.post(
                "/api/v1/messages",
                json={"message_type": "command"},
                headers={"Authorization": "Bearer valid-test-token"},
            )
        assert response.status_code in (200, 202)
        assert response.json().get("decision") == "PENDING"

    @pytest.mark.unit
    def test_resolve_repo_async_tier_repo_factory(self) -> None:
        """_resolve_repo awaits the result of an async tier_repo_factory callable."""

        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = None  # → 403 NO_TIER_ASSIGNED

        app = FastAPI()
        app.add_middleware(AutonomyTierEnforcementMiddleware)
        app.dependency_overrides[get_current_user] = lambda: _AGENT_CLAIMS
        # No get_tier_repo override — falls through to factory

        # Use an async-returning factory (covers line 231: return await result)
        async def _async_factory():
            return repo

        app.state.tier_repo_factory = _async_factory
        app.state.hitl_client = None

        @app.post("/api/v1/messages")
        async def _dummy():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/messages",
            json={"message_type": "query"},
            headers={"Authorization": "Bearer test-token"},
        )
        # repo.get_by_agent returns None → NO_TIER_ASSIGNED → 403
        assert response.status_code == 403
        assert response.json().get("reason") == "NO_TIER_ASSIGNED"
