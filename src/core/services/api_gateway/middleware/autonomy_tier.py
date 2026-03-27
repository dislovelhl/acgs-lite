"""Autonomy Tier Enforcement Middleware for the API Gateway.
Constitutional Hash: 608508a9bd224290

# ============================================================================
# HITL Integration Reference (T011)
# ============================================================================
#
# Endpoint: POST /api/v1/reviews
# Host: HITL Approvals service (env: HITL_URL, default http://localhost:8002)
#
# ApprovalRequestCreate payload schema
# (from src/core/services/hitl_approvals/app/schemas/approval.py):
#
#   {
#     "decision_id": str,      # unique ID for this enforcement decision (UUID)
#     "tenant_id":  str,       # tenant scope of the requesting agent
#     "requested_by": str,     # agent_id of the submitting agent
#     "title": str,            # human-readable summary, e.g. "Advisory action: <action_type>"
#     "description": str | None,
#     "priority": str,         # "standard" | "critical" — use "standard" for advisory tier
#     "context": dict,         # {agent_id, tier, action_type, constitutional_hash, ...}
#     "chain_id": UUID | None, # None → HITL service selects default chain
#   }
#
# action_type inference strategy:
#   primary  : payload.get('message_type')
#   fallback : f'{request.method}:{request.url.path.split("/")[-1]}'
#
# ============================================================================
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import uuid
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from src.core.services.api_gateway.models.tier_assignment import AutonomyTier
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)

# ============================================================================
# Constants
# ============================================================================

# Paths that require tier enforcement (proxy-forwarded paths only)
_ENFORCED_PATH_PREFIXES = (
    "/api/v1/messages",
    "/api/v1/agents",
    "/api/v1/deliberations",
)

# Default timeout for store lookups (seconds)
_DEFAULT_STORE_TIMEOUT: float = 2.0


# ============================================================================
# HitlSubmissionClient — Protocol + implementations
# ============================================================================


@runtime_checkable
class HitlSubmissionClient(Protocol):
    """Protocol for submitting advisory/human-approved actions to the HITL review queue.

    Stub implementations can be injected in tests via AsyncMock.
    The real implementation posts to POST /api/v1/reviews on the HITL Approvals service.
    """

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
        """Submit an action to the HITL review queue.

        Args:
            decision_id: UUID string for the enforcement decision record.
            agent_id: Requesting agent's identity.
            tenant_id: Tenant scope.
            action_type: Machine-readable action type string.
            tier: Autonomy tier value (ADVISORY | HUMAN_APPROVED).
            context: Additional audit context (constitutional_hash, etc.).

        Raises:
            httpx.HTTPError: On network or HTTP-level errors.
        """
        ...


class HttpHitlSubmissionClient:
    """Real HITL submission client that POSTs to the HITL Approvals service."""

    def __init__(self, url: str) -> None:
        self._url = url.rstrip("/")

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
        payload = {
            "decision_id": decision_id,
            "tenant_id": tenant_id,
            "requested_by": agent_id,
            "title": f"Autonomy tier review: {action_type}",
            "description": f"Agent {agent_id!r} ({tier}) requested action {action_type!r}",
            "priority": "standard",
            "context": {
                **context,
                "agent_id": agent_id,
                "tier": tier,
                "action_type": action_type,
                "constitutional_hash": CONSTITUTIONAL_HASH,  # pragma: allowlist secret
            },
            "chain_id": None,
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(f"{self._url}/api/v1/reviews", json=payload)
            response.raise_for_status()

        logger.info(
            "hitl.submitted",
            decision_id=decision_id,
            agent_id=agent_id,
            tier=tier,
            action_type=action_type,
        )


# ============================================================================
# AutonomyTierEnforcementMiddleware
# ============================================================================


class AutonomyTierEnforcementMiddleware(BaseHTTPMiddleware):
    """Enforcement middleware that intercepts proxied agent requests and applies
    the configured autonomy tier rules before forwarding to backend services.

    Tier paths:
      ADVISORY        → PENDING; action submitted to HITL review queue; proxy skipped.
      BOUNDED         → APPROVED (in boundary, forwarded to proxy) or BLOCKED (HTTP 403).
      HUMAN_APPROVED  → PENDING; every action submitted to HITL; proxy skipped.
      NO_TIER         → HTTP 403 {reason: NO_TIER_ASSIGNED}.
      STORE_OUTAGE    → HTTP 503 {reason: STORE_UNAVAILABLE}; alert log emitted.

    Audit: every evaluation emits a structured TierEnforcementDecision log record
    including constitutional_hash=608508a9bd224290.

    Testability: User identity and TierAssignmentRepository are resolved via
    request.app.dependency_overrides when set (allows AsyncMock injection in tests),
    falling back to real JWT parsing and app.state for production.
    """

    def __init__(self, app: ASGIApp, store_timeout: float = _DEFAULT_STORE_TIMEOUT) -> None:
        super().__init__(app)
        self._store_timeout = store_timeout

    # ------------------------------------------------------------------
    # Path gating
    # ------------------------------------------------------------------

    @staticmethod
    def _should_enforce(path: str) -> bool:
        return any(path.startswith(prefix) for prefix in _ENFORCED_PATH_PREFIXES)

    # ------------------------------------------------------------------
    # Dependency resolution (supports FastAPI dependency_overrides)
    # ------------------------------------------------------------------

    @staticmethod
    async def _resolve_user(request: Request):  # -> UserClaims | None
        """Resolve authenticated user, honouring FastAPI dependency_overrides for tests."""
        from src.core.shared.security.auth import get_current_user, verify_token

        override = request.app.dependency_overrides.get(get_current_user)
        if override is not None:
            result = override()
            if asyncio.iscoroutine(result):
                return await result
            return result

        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            try:
                return verify_token(auth[7:])
            except Exception:
                logger.debug("Bearer token verification failed during autonomy-tier resolution")
        return None

    @staticmethod
    async def _resolve_repo(request: Request):  # -> TierAssignmentRepository | None
        """Resolve TierAssignmentRepository, honouring FastAPI dependency_overrides for tests."""
        from src.core.services.api_gateway.routes.autonomy_tiers import get_tier_repo

        override = request.app.dependency_overrides.get(get_tier_repo)
        if override is not None:
            result = override()
            if asyncio.iscoroutine(result):
                return await result
            return result

        # Production path: use factory stored in app.state
        state = request.app.state
        if hasattr(state, "tier_repo_factory"):
            factory = state.tier_repo_factory
            result = factory()
            if asyncio.iscoroutine(result):
                return await result
            return result

        return None

    @staticmethod
    def _get_hitl_client(request: Request) -> HitlSubmissionClient | None:
        """Retrieve HITL client from app.state (overridable in tests)."""
        return getattr(request.app.state, "hitl_client", None)

    # ------------------------------------------------------------------
    # Action type inference
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_action_type(request: Request, body: bytes) -> str:
        """Extract action_type from request body or infer from HTTP method + path.

        Primary: payload.get('message_type')
        Fallback: f'{method}:{path.split("/")[-1]}'
        """
        if body:
            try:
                payload = json.loads(body)
                if isinstance(payload, dict) and payload.get("message_type"):
                    return str(payload["message_type"])
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        path_segment = request.url.path.rstrip("/").split("/")[-1]
        return f"{request.method}:{path_segment}"

    # ------------------------------------------------------------------
    # Boundary matching (BOUNDED tier)
    # ------------------------------------------------------------------

    @staticmethod
    def _is_action_allowed(action_type: str | None, boundaries: list[str]) -> bool:
        """Return True if action_type matches any pattern in boundaries via fnmatch.

        Fail-closed: returns False when action_type is None/empty or boundaries is empty.
        Uses stdlib fnmatch — no regex, no eval, no user-controlled code execution.

        Args:
            action_type: Machine-readable action type string to evaluate.
            boundaries: List of fnmatch glob patterns (e.g. 'read:*', 'agent.*').

        Returns:
            True if at least one pattern matches; False otherwise (fail-closed).
        """
        if not action_type or not boundaries:
            return False
        return any(fnmatch.fnmatch(action_type, pattern) for pattern in boundaries)

    # ------------------------------------------------------------------
    # Audit emission
    # ------------------------------------------------------------------

    @staticmethod
    def _emit_audit(
        *,
        request_id: str,
        agent_id: str,
        tenant_id: str,
        tier_at_decision: str,
        action_type: str,
        outcome: str,
        reason: str,
    ) -> None:
        """Emit a structured TierEnforcementDecision audit record."""
        logger.info(
            "tier_enforcement.decision",
            request_id=request_id,
            agent_id=agent_id,
            tenant_id=tenant_id,
            tier=tier_at_decision,
            action_type=action_type,
            outcome=outcome,
            reason=reason,
            constitutional_hash=CONSTITUTIONAL_HASH,  # pragma: allowlist secret
            timestamp=datetime.now(UTC).isoformat(),
        )

    # ------------------------------------------------------------------
    # Helpers for building responses
    # ------------------------------------------------------------------

    @staticmethod
    def _error_response(
        status_code: int,
        reason: str,
        request_id: str,
        tier: str = "unknown",
        decision: str = "ERROR",
    ) -> JSONResponse:
        response = JSONResponse(
            {"reason": reason, "request_id": request_id},
            status_code=status_code,
        )
        response.headers["X-Autonomy-Tier"] = tier
        response.headers["X-Enforcement-Decision"] = decision
        return response

    # ------------------------------------------------------------------
    # Main dispatch
    # ------------------------------------------------------------------

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        if not self._should_enforce(request.url.path):
            return await call_next(request)

        request_id = str(uuid.uuid4())

        # 1. Resolve user identity ----------------------------------------
        user = await self._resolve_user(request)
        if user is None:
            return self._error_response(401, "UNAUTHORIZED", request_id)

        agent_id = user.sub
        tenant_id = user.tenant_id

        # 2. Read body for action_type extraction (async, non-blocking) ----
        body = await request.body()
        action_type = self._extract_action_type(request, body)

        # 3. Resolve tier assignment with fail-closed timeout ---------------
        try:
            repo = await asyncio.wait_for(
                self._resolve_repo(request),
                timeout=self._store_timeout,
            )
        except (TimeoutError, ConnectionError, OSError) as exc:
            logger.error(
                "tier_enforcement.store_unavailable",
                agent_id=agent_id,
                tenant_id=tenant_id,
                action_type=action_type,
                error=str(exc),
                constitutional_hash=CONSTITUTIONAL_HASH,  # pragma: allowlist secret
            )
            self._emit_audit(
                request_id=request_id,
                agent_id=agent_id,
                tenant_id=tenant_id,
                tier_at_decision="UNKNOWN",
                action_type=action_type,
                outcome="ERROR",
                reason="STORE_UNAVAILABLE",
            )
            return self._error_response(503, "STORE_UNAVAILABLE", request_id)

        if repo is None:
            # Misconfiguration: no repo available — fail closed
            logger.error(
                "tier_enforcement.no_repo_configured",
                agent_id=agent_id,
                constitutional_hash=CONSTITUTIONAL_HASH,  # pragma: allowlist secret
            )
            return self._error_response(503, "STORE_UNAVAILABLE", request_id)

        # 4. Lookup tier assignment with timeout ----------------------------
        try:
            assignment = await asyncio.wait_for(
                repo.get_by_agent(agent_id=agent_id, tenant_id=tenant_id),
                timeout=self._store_timeout,
            )
        except (TimeoutError, ConnectionError, OSError) as exc:
            logger.error(
                "tier_enforcement.store_unavailable",
                agent_id=agent_id,
                tenant_id=tenant_id,
                action_type=action_type,
                error=str(exc),
                constitutional_hash=CONSTITUTIONAL_HASH,  # pragma: allowlist secret
            )
            self._emit_audit(
                request_id=request_id,
                agent_id=agent_id,
                tenant_id=tenant_id,
                tier_at_decision="UNKNOWN",
                action_type=action_type,
                outcome="ERROR",
                reason="STORE_UNAVAILABLE",
            )
            return self._error_response(503, "STORE_UNAVAILABLE", request_id)

        # 5. No tier assignment → fail closed (HTTP 403) -------------------
        if assignment is None:
            self._emit_audit(
                request_id=request_id,
                agent_id=agent_id,
                tenant_id=tenant_id,
                tier_at_decision="NONE",
                action_type=action_type,
                outcome="BLOCKED",
                reason="NO_TIER_ASSIGNED",
            )
            response = self._error_response(403, "NO_TIER_ASSIGNED", request_id, "none", "BLOCKED")
            return response

        tier = assignment.tier

        # 6. Tier dispatch --------------------------------------------------
        match tier:
            case AutonomyTier.ADVISORY:
                return await self._handle_advisory(
                    request=request,
                    request_id=request_id,
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                    action_type=action_type,
                )

            case AutonomyTier.BOUNDED:
                return await self._handle_bounded(
                    request=request,
                    call_next=call_next,
                    request_id=request_id,
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                    action_type=action_type,
                    assignment=assignment,
                )

            case AutonomyTier.HUMAN_APPROVED:
                return await self._handle_human_approved(
                    request=request,
                    request_id=request_id,
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                    action_type=action_type,
                )

            case _:
                # Unknown/future tier values: forward to proxy with audit record.
                self._emit_audit(
                    request_id=request_id,
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                    tier_at_decision=str(tier),
                    action_type=action_type,
                    outcome="APPROVED",
                    reason="TIER_FORWARDED",
                )
                response = await call_next(request)
                response.headers["X-Autonomy-Tier"] = str(tier).lower()
                response.headers["X-Enforcement-Decision"] = "APPROVED"
                return response

    # ------------------------------------------------------------------
    # HITL-routed tier handlers (Advisory & Human-Approved)
    # ------------------------------------------------------------------

    async def _handle_hitl_routed_tier(
        self,
        *,
        request: Request,
        request_id: str,
        agent_id: str,
        tenant_id: str,
        action_type: str,
        tier: str,
        reason: str,
        log_event: str,
        header_tier: str,
        include_reason_in_response: bool = False,
    ) -> JSONResponse:
        """Shared logic for routing actions to the HITL queue."""
        hitl_client = self._get_hitl_client(request)
        if hitl_client is not None:
            try:
                await hitl_client.submit(
                    decision_id=request_id,
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                    action_type=action_type,
                    tier=tier,
                    context={
                        "constitutional_hash": CONSTITUTIONAL_HASH
                    },  # pragma: allowlist secret
                )
            except Exception as exc:
                logger.error(
                    "tier_enforcement.hitl_submit_failed",
                    agent_id=agent_id,
                    action_type=action_type,
                    tier=tier,
                    error=str(exc),
                )

        self._emit_audit(
            request_id=request_id,
            agent_id=agent_id,
            tenant_id=tenant_id,
            tier_at_decision=tier,
            action_type=action_type,
            outcome="PENDING",
            reason=reason,
        )
        logger.info(
            log_event,
            agent_id=agent_id,
            tenant_id=tenant_id,
            action_type=action_type,
            request_id=request_id,
            constitutional_hash=CONSTITUTIONAL_HASH,  # pragma: allowlist secret
        )

        response_body = {"decision": "PENDING", "request_id": request_id}
        if include_reason_in_response:
            response_body["reason"] = reason

        response = JSONResponse(response_body, status_code=202)
        response.headers["X-Autonomy-Tier"] = header_tier
        response.headers["X-Enforcement-Decision"] = "PENDING"
        return response

    async def _handle_advisory(
        self,
        *,
        request: Request,
        request_id: str,
        agent_id: str,
        tenant_id: str,
        action_type: str,
    ) -> JSONResponse:
        """Route advisory-tier action to HITL queue; return PENDING without forwarding."""
        return await self._handle_hitl_routed_tier(
            request=request,
            request_id=request_id,
            agent_id=agent_id,
            tenant_id=tenant_id,
            action_type=action_type,
            tier="ADVISORY",
            reason="ADVISORY_QUEUED",
            log_event="tier_enforcement.advisory_queued",
            header_tier="advisory",
            include_reason_in_response=False,
        )

    async def _handle_human_approved(
        self,
        *,
        request: Request,
        request_id: str,
        agent_id: str,
        tenant_id: str,
        action_type: str,
    ) -> JSONResponse:
        """Route human-approved-tier action to HITL queue; return PENDING without forwarding.

        Every action from a HUMAN_APPROVED agent requires explicit human approval
        regardless of action type or action boundaries. This is more restrictive
        than BOUNDED tier: no autonomous execution is permitted.
        """
        return await self._handle_hitl_routed_tier(
            request=request,
            request_id=request_id,
            agent_id=agent_id,
            tenant_id=tenant_id,
            action_type=action_type,
            tier="HUMAN_APPROVED",
            reason="HUMAN_APPROVAL_REQUIRED",
            log_event="tier_enforcement.human_approved_queued",
            header_tier="human-approved",
            include_reason_in_response=True,
        )

    # ------------------------------------------------------------------
    # Bounded tier handler
    # ------------------------------------------------------------------

    async def _handle_bounded(
        self,
        *,
        request: Request,
        call_next,
        request_id: str,
        agent_id: str,
        tenant_id: str,
        action_type: str,
        assignment,
    ) -> Response:
        """Evaluate a BOUNDED-tier action against configured action_boundaries.

        APPROVED: action matches a boundary pattern → forward to proxy.
        BLOCKED:  action outside boundaries (or boundaries empty) → HTTP 403.
        """
        boundaries: list[str] = assignment.action_boundaries or []

        if not boundaries:
            logger.warning(
                "tier_enforcement.bounded_empty_boundaries",
                agent_id=agent_id,
                tenant_id=tenant_id,
                action_type=action_type,
                constitutional_hash=CONSTITUTIONAL_HASH,  # pragma: allowlist secret
            )

        if self._is_action_allowed(action_type, boundaries):
            self._emit_audit(
                request_id=request_id,
                agent_id=agent_id,
                tenant_id=tenant_id,
                tier_at_decision="BOUNDED",
                action_type=action_type,
                outcome="APPROVED",
                reason="IN_BOUNDARY",
            )
            response = await call_next(request)
            response.headers["X-Autonomy-Tier"] = "bounded"
            response.headers["X-Enforcement-Decision"] = "APPROVED"
            return response

        self._emit_audit(
            request_id=request_id,
            agent_id=agent_id,
            tenant_id=tenant_id,
            tier_at_decision="BOUNDED",
            action_type=action_type,
            outcome="BLOCKED",
            reason="BOUNDARY_EXCEEDED",
        )
        response = JSONResponse(
            {
                "decision": "BLOCKED",
                "reason": "BOUNDARY_EXCEEDED",
                "request_id": request_id,
            },
            status_code=403,
        )
        response.headers["X-Autonomy-Tier"] = "bounded"
        response.headers["X-Enforcement-Decision"] = "BLOCKED"
        return response
