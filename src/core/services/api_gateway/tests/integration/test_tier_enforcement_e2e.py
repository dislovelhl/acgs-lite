"""
Integration tests for the autonomy-tier enforcement pipeline (end-to-end).
Constitutional Hash: cdd01ef066bc6cf2

Test mapping:
  T010 (this file) -- no-tier-assignment → HTTP 403 / NO_TIER_ASSIGNED
  T015             -- advisory-tier agent → HITL queue (PENDING response)
  T018             -- bounded-tier in-boundary → APPROVED (HTTP 200)
                     bounded-tier out-of-boundary → BLOCKED (HTTP 403)
                     empty boundaries → BLOCKED (HTTP 403)
                     store outage during bounded request → HTTP 503
  T021             -- human-approved-tier → HITL queue for all action types
  T022             -- audit trail completeness: 10 requests across all tiers,
                     10 TierEnforcementDecision records with all required fields
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import ClassVar
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.services.api_gateway.middleware.autonomy_tier import (
    AutonomyTierEnforcementMiddleware,
)
from src.core.services.api_gateway.models.tier_assignment import AgentTierAssignment, AutonomyTier
from src.core.services.api_gateway.repositories.tier_assignment import TierAssignmentRepository
from src.core.services.api_gateway.routes.autonomy_tiers import get_tier_repo
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.security.auth import UserClaims, get_current_user

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_TENANT_ID = "tenant-enforce-test"
_AGENT_ID = "agent-enforce-001"

_AGENT_USER = UserClaims(
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
        assigned_by="admin-user",
        assigned_at=now,
        created_at=now,
    )


def _make_enforcement_client(
    repo: TierAssignmentRepository,
    user: UserClaims = _AGENT_USER,
) -> TestClient:
    """
    Build a test client against the full API Gateway application with the
    enforcement middleware active and the tier repository overridden.

    When the enforcement middleware is implemented it will depend on the
    same ``get_tier_repo`` dependency, allowing clean override in tests.
    """
    from src.core.services.api_gateway.main import app

    app.dependency_overrides[get_tier_repo] = lambda: repo
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app, raise_server_exceptions=False)
    return client


# ---------------------------------------------------------------------------
# T010 -- Agent with no tier assignment is rejected with HTTP 403
# ---------------------------------------------------------------------------


class TestNoTierAssignmentRejected:
    """
    US-001: An agent with no tier assignment must be rejected at the gateway.

    Expected enforcement behaviour (implemented in a subsequent phase):
      - Enforcement middleware looks up tier via get_tier_repo
      - Assignment not found → immediate HTTP 403
      - Response body: {"reason": "NO_TIER_ASSIGNED"}
      - Audit log entry: outcome=BLOCKED, reason=NO_TIER_ASSIGNED,
                        constitutional_hash=cdd01ef066bc6cf2

    RED test: this test will FAIL until AutonomyTierEnforcementMiddleware
    is wired into main.py.
    """

    @pytest.mark.integration
    @pytest.mark.constitutional
    def test_agent_with_no_tier_gets_403(self) -> None:
        """POST /api/v1/messages from agent with no tier assignment → HTTP 403.

        The enforcement middleware must return:
            HTTP 403
            body: {"reason": "NO_TIER_ASSIGNED"}
        """
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = None  # no assignment in store

        client = _make_enforcement_client(repo)
        response = client.post(
            "/api/v1/messages",
            json={"message_type": "command", "content": "do something"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 403
        body = response.json()
        assert body.get("reason") == "NO_TIER_ASSIGNED"

    @pytest.mark.integration
    @pytest.mark.constitutional
    def test_no_tier_rejection_emits_audit_record(self) -> None:
        """Audit log entry is recorded for rejected no-tier request.

        The enforcement middleware must emit a TierEnforcementDecision with:
            outcome=BLOCKED
            reason=NO_TIER_ASSIGNED
            constitutional_hash=cdd01ef066bc6cf2
        """
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = None

        # Capture structured log output to verify the audit event fields.
        with patch("src.core.services.api_gateway.middleware.autonomy_tier.logger") as mock_logger:
            client = _make_enforcement_client(repo)
            client.post(
                "/api/v1/messages",
                json={"message_type": "command", "content": "do something"},
                headers={"Authorization": "Bearer test-token"},
            )

            # Verify audit log call contains required fields.
            # (Exact call signature depends on middleware implementation.)
            logged = any(
                call_args
                for call_args in mock_logger.info.call_args_list
                if "NO_TIER_ASSIGNED" in str(call_args) and CONSTITUTIONAL_HASH in str(call_args)
            )
            assert logged, (
                "Expected an audit log entry with outcome=BLOCKED, "
                f"reason=NO_TIER_ASSIGNED, constitutional_hash={CONSTITUTIONAL_HASH}"
            )


# ---------------------------------------------------------------------------
# T015 -- Advisory-tier agent routes to HITL queue
# ---------------------------------------------------------------------------


def _make_advisory_client(
    hitl_client=None,
    user: UserClaims = _AGENT_USER,
) -> TestClient:
    """
    Build a test client for advisory-tier enforcement integration tests.

    Overrides:
      - get_tier_repo  → AsyncMock returning ADVISORY assignment
      - get_current_user → fixed agent UserClaims
      - app.state.hitl_client → provided mock (or AsyncMock if None)
    """
    from src.core.services.api_gateway.main import app
    from src.core.services.api_gateway.middleware.autonomy_tier import HitlSubmissionClient

    repo = AsyncMock(spec=TierAssignmentRepository)
    repo.get_by_agent.return_value = _make_assignment(AutonomyTier.ADVISORY)

    app.dependency_overrides[get_tier_repo] = lambda: repo
    app.dependency_overrides[get_current_user] = lambda: user

    if hitl_client is None:
        hitl_client = AsyncMock(spec=HitlSubmissionClient)
    app.state.hitl_client = hitl_client

    return TestClient(app, raise_server_exceptions=False), repo, hitl_client


class TestAdvisoryTierEnforcement:
    """
    US-002: Advisory-tier agents must have all actions queued for HITL review.

    The middleware intercepts POST /api/v1/messages, detects ADVISORY tier,
    submits to the HITL review queue, and returns PENDING without forwarding.
    """

    @pytest.mark.integration
    @pytest.mark.constitutional
    def test_advisory_agent_returns_pending(self) -> None:
        """POST /api/v1/messages from advisory-tier agent → response body decision=PENDING."""
        from src.core.services.api_gateway.middleware.autonomy_tier import HitlSubmissionClient

        mock_hitl = AsyncMock(spec=HitlSubmissionClient)
        client, _repo, _ = _make_advisory_client(hitl_client=mock_hitl)

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "command", "content": "advisory action"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code in (200, 202), response.text
        body = response.json()
        assert body.get("decision") == "PENDING", f"Expected PENDING, got: {body}"

    @pytest.mark.integration
    @pytest.mark.constitutional
    def test_advisory_hitl_receives_one_submission(self) -> None:
        """Mocked HITL service endpoint receives exactly one submission with correct fields."""
        from src.core.services.api_gateway.middleware.autonomy_tier import HitlSubmissionClient

        mock_hitl = AsyncMock(spec=HitlSubmissionClient)
        client, _repo, _ = _make_advisory_client(hitl_client=mock_hitl)

        client.post(
            "/api/v1/messages",
            json={"message_type": "command", "content": "advisory action"},
            headers={"Authorization": "Bearer test-token"},
        )

        mock_hitl.submit.assert_awaited_once()
        kwargs = mock_hitl.submit.call_args.kwargs
        assert kwargs["agent_id"] == _AGENT_ID
        assert kwargs["action_type"] == "command"
        assert kwargs["tier"] == "ADVISORY"

    @pytest.mark.integration
    @pytest.mark.constitutional
    def test_advisory_audit_log_contains_required_fields(self) -> None:
        """Audit log entry recorded with tier_at_decision=ADVISORY, outcome=PENDING,
        reason=ADVISORY_QUEUED, and constitutional_hash present."""
        from src.core.services.api_gateway.middleware.autonomy_tier import HitlSubmissionClient

        mock_hitl = AsyncMock(spec=HitlSubmissionClient)
        client, _repo, _ = _make_advisory_client(hitl_client=mock_hitl)

        with patch("src.core.services.api_gateway.middleware.autonomy_tier.logger") as mock_logger:
            client.post(
                "/api/v1/messages",
                json={"message_type": "command", "content": "advisory action"},
                headers={"Authorization": "Bearer test-token"},
            )

            log_calls_str = str(mock_logger.info.call_args_list)
            assert "ADVISORY" in log_calls_str, "Expected tier_at_decision=ADVISORY in audit log"
            assert "PENDING" in log_calls_str, "Expected outcome=PENDING in audit log"
            assert "ADVISORY_QUEUED" in log_calls_str, (
                "Expected reason=ADVISORY_QUEUED in audit log"
            )
            assert CONSTITUTIONAL_HASH in log_calls_str, (
                f"Expected constitutional_hash={CONSTITUTIONAL_HASH!r} in audit log"
            )

    @pytest.mark.integration
    @pytest.mark.constitutional
    def test_advisory_action_not_forwarded_to_proxy(self) -> None:
        """Action is deferred; it must NOT be forwarded to the Agent Bus (proxy)."""
        from src.core.services.api_gateway.middleware.autonomy_tier import HitlSubmissionClient

        mock_hitl = AsyncMock(spec=HitlSubmissionClient)
        client, _repo, _ = _make_advisory_client(hitl_client=mock_hitl)

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "command", "content": "advisory action"},
            headers={"Authorization": "Bearer test-token"},
        )

        # The middleware must intercept and return before reaching the proxy.
        # A PENDING response with no proxy forwarding means no 502 (proxy failure) occurs.
        body = response.json()
        assert body.get("decision") == "PENDING"
        # Proxy forwarding would result in a 502 (no real agent bus in CI).
        # PENDING response confirms proxy was skipped.
        assert response.status_code != 502


# ---------------------------------------------------------------------------
# T018 helpers -- minimal app for bounded tier tests
# ---------------------------------------------------------------------------


def _make_bounded_app(
    boundaries: list[str] | None,
    user: UserClaims = _AGENT_USER,
    raise_on_get: BaseException | None = None,
) -> tuple[TestClient, AsyncMock]:
    """Build a minimal test app for BOUNDED-tier enforcement integration tests.

    Uses a FastAPI app with a passthrough route so approved requests return HTTP 200.
    The real proxy is NOT involved.

    Args:
        boundaries: action_boundaries for the BOUNDED tier assignment (None treated as []).
        user: UserClaims override for authentication.
        raise_on_get: If set, repo.get_by_agent raises this exception (for store outage tests).

    Returns:
        (TestClient, repo_mock) tuple.
    """
    repo = AsyncMock(spec=TierAssignmentRepository)
    if raise_on_get is not None:
        repo.get_by_agent.side_effect = raise_on_get
    else:
        repo.get_by_agent.return_value = _make_assignment(
            AutonomyTier.BOUNDED,
            action_boundaries=boundaries,
        )

    app = FastAPI()
    app.add_middleware(AutonomyTierEnforcementMiddleware)
    app.dependency_overrides[get_tier_repo] = lambda: repo
    app.dependency_overrides[get_current_user] = lambda: user
    app.state.hitl_client = None

    @app.post("/api/v1/messages")
    async def _passthrough():
        return {"status": "ok"}

    return TestClient(app, raise_server_exceptions=False), repo


# ---------------------------------------------------------------------------
# T018 -- Bounded-tier enforcement tests
# ---------------------------------------------------------------------------


class TestBoundedTierInBoundary:
    """
    US-003: Bounded-tier agents may execute actions within configured boundaries.
    """

    @pytest.mark.integration
    @pytest.mark.constitutional
    def test_bounded_in_boundary_approved(self) -> None:
        """BOUNDED agent with action inside boundary → HTTP 200, APPROVED headers."""
        client, _ = _make_bounded_app(boundaries=["read:*"])

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "read:documents", "content": ""},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        assert response.headers.get("x-enforcement-decision") == "APPROVED"
        assert response.headers.get("x-autonomy-tier") == "bounded"

    @pytest.mark.integration
    @pytest.mark.constitutional
    def test_bounded_in_boundary_audit_log(self) -> None:
        """Audit record emitted with outcome=APPROVED, reason=IN_BOUNDARY, constitutional_hash."""
        client, _ = _make_bounded_app(boundaries=["read:*"])

        with patch("src.core.services.api_gateway.middleware.autonomy_tier.logger") as mock_logger:
            client.post(
                "/api/v1/messages",
                json={"message_type": "read:documents", "content": ""},
                headers={"Authorization": "Bearer test-token"},
            )

            log_str = str(mock_logger.info.call_args_list)
            assert "APPROVED" in log_str, "Expected outcome=APPROVED in audit log"
            assert "IN_BOUNDARY" in log_str, "Expected reason=IN_BOUNDARY in audit log"
            assert CONSTITUTIONAL_HASH in log_str, (
                f"Expected constitutional_hash={CONSTITUTIONAL_HASH!r} in audit log"
            )


class TestBoundedTierOutOfBoundary:
    """
    US-003: Bounded-tier agents are blocked when action exceeds configured boundaries.
    """

    @pytest.mark.integration
    @pytest.mark.constitutional
    def test_bounded_out_of_boundary_blocked(self) -> None:
        """BOUNDED agent with action outside boundary → HTTP 403, decision=BLOCKED."""
        client, _ = _make_bounded_app(boundaries=["read:*"])

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "write:documents", "content": ""},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 403
        body = response.json()
        assert body.get("decision") == "BLOCKED"
        assert body.get("reason") == "BOUNDARY_EXCEEDED"

    @pytest.mark.integration
    @pytest.mark.constitutional
    def test_bounded_out_of_boundary_audit_log(self) -> None:
        """Audit record emitted with outcome=BLOCKED, reason=BOUNDARY_EXCEEDED."""
        client, _ = _make_bounded_app(boundaries=["read:*"])

        with patch("src.core.services.api_gateway.middleware.autonomy_tier.logger") as mock_logger:
            client.post(
                "/api/v1/messages",
                json={"message_type": "write:documents", "content": ""},
                headers={"Authorization": "Bearer test-token"},
            )

            log_str = str(mock_logger.info.call_args_list)
            assert "BLOCKED" in log_str, "Expected outcome=BLOCKED in audit log"
            assert "BOUNDARY_EXCEEDED" in log_str, "Expected reason=BOUNDARY_EXCEEDED in audit log"
            assert CONSTITUTIONAL_HASH in log_str, (
                f"Expected constitutional_hash={CONSTITUTIONAL_HASH!r} in audit log"
            )

    @pytest.mark.integration
    @pytest.mark.constitutional
    def test_bounded_out_of_boundary_headers(self) -> None:
        """Response headers correctly indicate BLOCKED decision for out-of-boundary action."""
        client, _ = _make_bounded_app(boundaries=["read:*"])

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "write:documents", "content": ""},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.headers.get("x-enforcement-decision") == "BLOCKED"
        assert response.headers.get("x-autonomy-tier") == "bounded"

    @pytest.mark.integration
    @pytest.mark.constitutional
    def test_bounded_empty_boundaries_blocked(self) -> None:
        """BOUNDED agent with empty action_boundaries → HTTP 403 for any action (fail-closed)."""
        client, _ = _make_bounded_app(boundaries=[])

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "read:documents", "content": ""},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 403
        body = response.json()
        assert body.get("decision") == "BLOCKED"

    @pytest.mark.integration
    @pytest.mark.constitutional
    def test_store_unavailable_bounded_returns_503(self) -> None:
        """Store timeout during bounded request → HTTP 503; no action executed, alert log emitted."""
        client, _ = _make_bounded_app(boundaries=None, raise_on_get=TimeoutError("store timeout"))

        with patch("src.core.services.api_gateway.middleware.autonomy_tier.logger") as mock_logger:
            response = client.post(
                "/api/v1/messages",
                json={"message_type": "read:documents", "content": ""},
                headers={"Authorization": "Bearer test-token"},
            )

            assert response.status_code == 503
            assert response.json().get("reason") == "STORE_UNAVAILABLE"

            error_calls = [
                call
                for call in mock_logger.error.call_args_list
                if "store_unavailable" in str(call).lower() or "STORE_UNAVAILABLE" in str(call)
            ]
            assert error_calls, "Expected structured alert log for store unavailability"


# ---------------------------------------------------------------------------
# T022 (placeholder) -- Human-approved-tier routes to HITL queue
# ---------------------------------------------------------------------------


def _make_human_approved_app(
    user: UserClaims = _AGENT_USER,
    hitl_client=None,
) -> tuple[TestClient, AsyncMock, object]:
    """Build a minimal test app for HUMAN_APPROVED-tier enforcement integration tests.

    Args:
        user: UserClaims override for authentication.
        hitl_client: Optional HITL client override. Defaults to AsyncMock.

    Returns:
        (TestClient, repo_mock, hitl_client) tuple.
    """
    from src.core.services.api_gateway.middleware.autonomy_tier import HitlSubmissionClient

    repo = AsyncMock(spec=TierAssignmentRepository)
    repo.get_by_agent.return_value = _make_assignment(AutonomyTier.HUMAN_APPROVED)

    if hitl_client is None:
        hitl_client = AsyncMock(spec=HitlSubmissionClient)

    app = FastAPI()
    app.add_middleware(AutonomyTierEnforcementMiddleware)
    app.dependency_overrides[get_tier_repo] = lambda: repo
    app.dependency_overrides[get_current_user] = lambda: user
    app.state.hitl_client = hitl_client

    @app.post("/api/v1/messages")
    async def _passthrough():
        return {"status": "ok"}

    return TestClient(app, raise_server_exceptions=False), repo, hitl_client


class TestHumanApprovedTierEnforcement:
    """
    US-004: Human-approved-tier agents require explicit HITL approval for every action.

    Every action type -- regardless of content -- must be routed to the HITL review queue
    and return PENDING with reason=HUMAN_APPROVAL_REQUIRED. No autonomous execution occurs.
    """

    _DIVERSE_ACTION_TYPES: ClassVar[list] = [
        "read:documents",
        "write:records",
        "delete:entities",
        "execute:pipeline",
        "configure:settings",
    ]

    @pytest.mark.integration
    @pytest.mark.constitutional
    def test_human_approved_all_action_types_return_pending(self) -> None:
        """Human-approved agent submitting 5 diverse action types → all return PENDING."""
        from src.core.services.api_gateway.middleware.autonomy_tier import HitlSubmissionClient

        mock_hitl = AsyncMock(spec=HitlSubmissionClient)
        client, _repo, _ = _make_human_approved_app(hitl_client=mock_hitl)

        for action_type in self._DIVERSE_ACTION_TYPES:
            response = client.post(
                "/api/v1/messages",
                json={"message_type": action_type, "content": ""},
                headers={"Authorization": "Bearer test-token"},
            )

            assert response.status_code in (200, 202), (
                f"action_type={action_type!r}: expected 200/202, got {response.status_code}"
            )
            body = response.json()
            assert body.get("decision") == "PENDING", (
                f"action_type={action_type!r}: expected PENDING, got {body}"
            )
            assert body.get("reason") == "HUMAN_APPROVAL_REQUIRED", (
                f"action_type={action_type!r}: expected HUMAN_APPROVAL_REQUIRED reason"
            )

    @pytest.mark.integration
    @pytest.mark.constitutional
    def test_human_approved_hitl_receives_one_submission_per_request(self) -> None:
        """Mocked HITL service receives exactly 5 separate submission calls, one per request."""
        from src.core.services.api_gateway.middleware.autonomy_tier import HitlSubmissionClient

        mock_hitl = AsyncMock(spec=HitlSubmissionClient)
        client, _repo, _ = _make_human_approved_app(hitl_client=mock_hitl)

        for action_type in self._DIVERSE_ACTION_TYPES:
            client.post(
                "/api/v1/messages",
                json={"message_type": action_type, "content": ""},
                headers={"Authorization": "Bearer test-token"},
            )

        assert mock_hitl.submit.await_count == len(self._DIVERSE_ACTION_TYPES), (
            f"Expected {len(self._DIVERSE_ACTION_TYPES)} HITL submissions, "
            f"got {mock_hitl.submit.await_count}"
        )
        for call in mock_hitl.submit.call_args_list:
            assert call.kwargs["tier"] == "HUMAN_APPROVED"
            assert call.kwargs["agent_id"] == _AGENT_ID

    @pytest.mark.integration
    @pytest.mark.constitutional
    def test_human_approved_zero_autonomous_executions(self) -> None:
        """Zero actions executed autonomously: no proxy forwarding for any action type."""
        from src.core.services.api_gateway.middleware.autonomy_tier import HitlSubmissionClient

        mock_hitl = AsyncMock(spec=HitlSubmissionClient)
        client, _repo, _ = _make_human_approved_app(hitl_client=mock_hitl)

        for action_type in self._DIVERSE_ACTION_TYPES:
            response = client.post(
                "/api/v1/messages",
                json={"message_type": action_type, "content": ""},
                headers={"Authorization": "Bearer test-token"},
            )
            body = response.json()
            # Proxy would return {"status": "ok"} -- PENDING confirms proxy was skipped
            assert body.get("status") != "ok", (
                f"action_type={action_type!r}: request was forwarded to proxy (autonomous execution)"
            )

    @pytest.mark.integration
    @pytest.mark.constitutional
    def test_human_approved_sla_escalation_simulation(self) -> None:
        """SLA window expiry simulation: HITL service escalates after SLA expires.

        Simulates the accelerated-clock scenario: a custom HITL client records
        the submission and immediately marks the decision as ESCALATED, matching
        what the HITL service does when the standard 30-minute SLA window expires
        with no reviewer action (per CLAUDE.md §Governance Thresholds).
        """
        escalated_decisions: list[dict] = []

        class EscalatingHitlMock:
            """Simulates HITL service that escalates immediately (accelerated clock)."""

            async def submit(
                self,
                *,
                decision_id: str,
                agent_id: str,
                tenant_id: str,
                action_type: str,
                tier: str,
                context: dict,
            ) -> None:
                # Simulate SLA expiry: HITL transitions decision to ESCALATED
                escalated_decisions.append(
                    {
                        "decision_id": decision_id,
                        "status": "ESCALATED",
                        "agent_id": agent_id,
                        "tier": tier,
                        "action_type": action_type,
                    }
                )

        mock_hitl = EscalatingHitlMock()
        client, _repo, _ = _make_human_approved_app(hitl_client=mock_hitl)

        response = client.post(
            "/api/v1/messages",
            json={"message_type": "execute:critical-pipeline", "content": ""},
            headers={"Authorization": "Bearer test-token"},
        )

        # Middleware returns PENDING immediately
        assert response.status_code in (200, 202)
        body = response.json()
        assert body.get("decision") == "PENDING"
        assert body.get("reason") == "HUMAN_APPROVAL_REQUIRED"

        # HITL service (simulated) recorded the escalation after SLA expiry
        assert len(escalated_decisions) == 1, "Expected 1 HITL submission that escalated"
        escalated = escalated_decisions[0]
        assert escalated["status"] == "ESCALATED"
        assert escalated["agent_id"] == _AGENT_ID
        assert escalated["tier"] == "HUMAN_APPROVED"
        assert escalated["action_type"] == "execute:critical-pipeline"

    @pytest.mark.integration
    @pytest.mark.constitutional
    def test_human_approved_audit_log_fields(self) -> None:
        """Audit log contains tier_at_decision=HUMAN_APPROVED, outcome=PENDING,
        reason=HUMAN_APPROVAL_REQUIRED, and constitutional_hash."""
        from src.core.services.api_gateway.middleware.autonomy_tier import HitlSubmissionClient

        mock_hitl = AsyncMock(spec=HitlSubmissionClient)
        client, _repo, _ = _make_human_approved_app(hitl_client=mock_hitl)

        with patch("src.core.services.api_gateway.middleware.autonomy_tier.logger") as mock_logger:
            client.post(
                "/api/v1/messages",
                json={"message_type": "write:records", "content": ""},
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


# ---------------------------------------------------------------------------
# T022 -- Audit trail completeness: 10 requests across all tiers
# ---------------------------------------------------------------------------


def _make_audit_test_client(
    tier: AutonomyTier | None,
    action_boundaries: list[str] | None = None,
    hitl_client=None,
) -> TestClient:
    """Build a self-contained test client for audit completeness tests.

    Uses a fresh FastAPI instance per tier to avoid shared app-state contamination.

    Args:
        tier: Autonomy tier for the agent assignment, or None for no-tier.
        action_boundaries: Boundary patterns for BOUNDED tier.
        hitl_client: Optional mock HITL client.

    Returns:
        Configured TestClient.
    """
    from src.core.services.api_gateway.middleware.autonomy_tier import HitlSubmissionClient

    repo = AsyncMock(spec=TierAssignmentRepository)
    if tier is None:
        repo.get_by_agent.return_value = None
    else:
        repo.get_by_agent.return_value = _make_assignment(tier, action_boundaries)

    if hitl_client is None:
        hitl_client = AsyncMock(spec=HitlSubmissionClient)

    app = FastAPI()
    app.add_middleware(AutonomyTierEnforcementMiddleware)
    app.dependency_overrides[get_tier_repo] = lambda: repo
    app.dependency_overrides[get_current_user] = lambda: _AGENT_USER
    app.state.hitl_client = hitl_client

    @app.post("/api/v1/messages")
    async def _passthrough():
        return {"status": "ok"}

    return TestClient(app, raise_server_exceptions=False)


class TestAuditTrailCompleteness:
    """
    US-005: Every enforcement decision must be recorded in the audit trail with
    all required fields and the constitutional hash present on every record.

    Submits 10 requests spanning all tier paths (APPROVED, PENDING, BLOCKED) and
    validates that 10 TierEnforcementDecision structured log records are emitted,
    each containing every required field validated via a Pydantic model.
    """

    # Required fields for every TierEnforcementDecision audit record.
    # 'tier' is the wire-name for tier_at_decision in the structured log.
    _REQUIRED_FIELDS = frozenset(
        {
            "agent_id",
            "tenant_id",
            "tier",
            "action_type",
            "outcome",
            "reason",
            "constitutional_hash",
            "timestamp",
            "request_id",
        }
    )

    @pytest.mark.integration
    @pytest.mark.constitutional
    def test_ten_requests_produce_ten_audit_records(self) -> None:
        """10 requests across all tier paths → 10 TierEnforcementDecision records in audit log.

        Request breakdown (2 per path to ensure thorough coverage):
          - 2 x NO_TIER  → BLOCKED (NO_TIER_ASSIGNED)
          - 2 x ADVISORY → PENDING (ADVISORY_QUEUED)
          - 2 x BOUNDED in-boundary → APPROVED (IN_BOUNDARY)
          - 2 x BOUNDED out-of-boundary → BLOCKED (BOUNDARY_EXCEEDED)
          - 2 x HUMAN_APPROVED → PENDING (HUMAN_APPROVAL_REQUIRED)
        """
        from pydantic import BaseModel

        class _AuditRecord(BaseModel):
            agent_id: str
            tenant_id: str
            tier: str
            action_type: str
            outcome: str
            reason: str
            constitutional_hash: str
            timestamp: str
            request_id: str

        client_no_tier = _make_audit_test_client(tier=None)
        client_advisory = _make_audit_test_client(tier=AutonomyTier.ADVISORY)
        client_bounded_in = _make_audit_test_client(
            tier=AutonomyTier.BOUNDED, action_boundaries=["read:*"]
        )
        client_bounded_out = _make_audit_test_client(
            tier=AutonomyTier.BOUNDED, action_boundaries=["read:*"]
        )
        client_human = _make_audit_test_client(tier=AutonomyTier.HUMAN_APPROVED)

        with patch("src.core.services.api_gateway.middleware.autonomy_tier.logger") as mock_logger:
            # 2 x NO_TIER → BLOCKED
            client_no_tier.post(
                "/api/v1/messages",
                json={"message_type": "read:docs", "content": ""},
                headers={"Authorization": "Bearer test-token"},
            )
            client_no_tier.post(
                "/api/v1/messages",
                json={"message_type": "write:records", "content": ""},
                headers={"Authorization": "Bearer test-token"},
            )

            # 2 x ADVISORY → PENDING
            client_advisory.post(
                "/api/v1/messages",
                json={"message_type": "command:search", "content": ""},
                headers={"Authorization": "Bearer test-token"},
            )
            client_advisory.post(
                "/api/v1/messages",
                json={"message_type": "command:analyse", "content": ""},
                headers={"Authorization": "Bearer test-token"},
            )

            # 2 x BOUNDED in-boundary → APPROVED
            client_bounded_in.post(
                "/api/v1/messages",
                json={"message_type": "read:documents", "content": ""},
                headers={"Authorization": "Bearer test-token"},
            )
            client_bounded_in.post(
                "/api/v1/messages",
                json={"message_type": "read:audit-log", "content": ""},
                headers={"Authorization": "Bearer test-token"},
            )

            # 2 x BOUNDED out-of-boundary → BLOCKED
            client_bounded_out.post(
                "/api/v1/messages",
                json={"message_type": "write:documents", "content": ""},
                headers={"Authorization": "Bearer test-token"},
            )
            client_bounded_out.post(
                "/api/v1/messages",
                json={"message_type": "delete:entities", "content": ""},
                headers={"Authorization": "Bearer test-token"},
            )

            # 2 x HUMAN_APPROVED → PENDING
            client_human.post(
                "/api/v1/messages",
                json={"message_type": "execute:pipeline", "content": ""},
                headers={"Authorization": "Bearer test-token"},
            )
            client_human.post(
                "/api/v1/messages",
                json={"message_type": "configure:settings", "content": ""},
                headers={"Authorization": "Bearer test-token"},
            )

            # Collect only "tier_enforcement.decision" audit records
            audit_records = [
                call
                for call in mock_logger.info.call_args_list
                if call.args and call.args[0] == "tier_enforcement.decision"
            ]

            assert len(audit_records) == 10, (
                f"Expected 10 TierEnforcementDecision records, got {len(audit_records)}. "
                f"All info calls: {[c.args[0] for c in mock_logger.info.call_args_list if c.args]}"
            )

            # Validate each record against the Pydantic model
            for i, call in enumerate(audit_records):
                kwargs = call.kwargs
                record = _AuditRecord(**kwargs)  # raises ValidationError if field missing
                assert record.constitutional_hash == CONSTITUTIONAL_HASH, (
                    f"Record {i}: constitutional_hash mismatch: "
                    f"expected {CONSTITUTIONAL_HASH!r}, got {record.constitutional_hash!r}"
                )
                assert record.agent_id == _AGENT_ID, (
                    f"Record {i}: agent_id mismatch: expected {_AGENT_ID!r}"
                )
                assert record.tenant_id == _TENANT_ID, (
                    f"Record {i}: tenant_id mismatch: expected {_TENANT_ID!r}"
                )

    @pytest.mark.integration
    @pytest.mark.constitutional
    def test_audit_records_cover_all_outcomes(self) -> None:
        """The 10 audit records include all three outcome values: APPROVED, PENDING, BLOCKED."""
        client_no_tier = _make_audit_test_client(tier=None)
        client_advisory = _make_audit_test_client(tier=AutonomyTier.ADVISORY)
        client_bounded_in = _make_audit_test_client(
            tier=AutonomyTier.BOUNDED, action_boundaries=["read:*"]
        )
        client_bounded_out = _make_audit_test_client(
            tier=AutonomyTier.BOUNDED, action_boundaries=["read:*"]
        )
        client_human = _make_audit_test_client(tier=AutonomyTier.HUMAN_APPROVED)

        with patch("src.core.services.api_gateway.middleware.autonomy_tier.logger") as mock_logger:
            for client, action in [
                (client_no_tier, "read:docs"),
                (client_no_tier, "write:records"),
                (client_advisory, "command:search"),
                (client_advisory, "command:analyse"),
                (client_bounded_in, "read:documents"),
                (client_bounded_in, "read:audit-log"),
                (client_bounded_out, "write:documents"),
                (client_bounded_out, "delete:entities"),
                (client_human, "execute:pipeline"),
                (client_human, "configure:settings"),
            ]:
                client.post(
                    "/api/v1/messages",
                    json={"message_type": action, "content": ""},
                    headers={"Authorization": "Bearer test-token"},
                )

            audit_records = [
                call.kwargs
                for call in mock_logger.info.call_args_list
                if call.args and call.args[0] == "tier_enforcement.decision"
            ]

            outcomes = {r["outcome"] for r in audit_records}
            assert "APPROVED" in outcomes, "Expected at least one APPROVED outcome"
            assert "PENDING" in outcomes, "Expected at least one PENDING outcome"
            assert "BLOCKED" in outcomes, "Expected at least one BLOCKED outcome"

            # Every record must carry the constitutional hash
            for i, record in enumerate(audit_records):
                assert record.get("constitutional_hash") == CONSTITUTIONAL_HASH, (
                    f"Record {i} (outcome={record.get('outcome')!r}) missing constitutional_hash"
                )
