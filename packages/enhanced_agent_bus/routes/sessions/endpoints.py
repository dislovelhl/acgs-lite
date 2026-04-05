"""
ACGS-2 Session Governance - API Endpoints
Constitutional Hash: 608508a9bd224290

FastAPI endpoint handlers for session governance operations.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from fastapi import HTTPException, status

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger

from ._fallbacks import RiskLevel, SessionContextManager, SessionGovernanceConfig
from .models import (
    CreateSessionRequest,
    PolicySelectionRequest,
    PolicySelectionResponse,
    SelectedPolicy,
    SessionMetricsResponse,
    SessionResponse,
    UpdateGovernanceRequest,
)

logger = get_logger(__name__)
ENDPOINT_ERRORS: tuple[type[Exception], ...] = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
)


# =============================================================================
# API Endpoint Handlers
# =============================================================================


async def create_session(
    request: CreateSessionRequest,
    tenant_id: str,
    x_user_id: str | None,
    manager: SessionContextManager,
) -> SessionResponse:
    """Create a new session with governance configuration."""
    try:
        if request.tenant_id and request.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"tenant_id in body '{request.tenant_id}' must match X-Tenant-ID header '{tenant_id}'",
            )
        effective_tenant_id = tenant_id
        effective_user_id = request.user_id or x_user_id

        # Map string risk level to enum
        risk_level_map = {
            "low": RiskLevel.LOW,
            "medium": RiskLevel.MEDIUM,
            "high": RiskLevel.HIGH,
            "critical": RiskLevel.CRITICAL,
        }
        risk_level = risk_level_map.get(request.risk_level, RiskLevel.MEDIUM)

        # Create governance config
        governance_config = SessionGovernanceConfig(
            session_id=request.session_id or "",
            tenant_id=effective_tenant_id,
            user_id=effective_user_id,
            risk_level=risk_level,
            policy_id=request.policy_id,
            policy_overrides=request.policy_overrides,
            enabled_policies=request.enabled_policies,
            disabled_policies=request.disabled_policies,
            require_human_approval=request.require_human_approval,
            max_automation_level=request.max_automation_level,
        )

        # Create session context
        session_context = await manager.create(
            governance_config=governance_config,
            session_id=request.session_id,
            tenant_id=effective_tenant_id,
            metadata=request.metadata,
            ttl=request.ttl_seconds,
        )

        # Get remaining TTL
        ttl_remaining = await manager.store.get_ttl(session_context.session_id, effective_tenant_id)

        logger.info(
            f"Created session {session_context.session_id} for tenant {effective_tenant_id}"
        )

        return SessionResponse.from_session_context(session_context, ttl_remaining)

    except ValueError as e:
        logger.warning(f"Invalid session creation request: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e
    except ENDPOINT_ERRORS as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session: {e!s}",
        ) from e


async def get_session(
    session_id: str,
    tenant_id: str,
    manager: SessionContextManager,
) -> SessionResponse:
    """Get session governance configuration by ID."""
    try:
        session_context = await manager.get(session_id, tenant_id)

        if not session_context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        # Verify tenant access
        if session_context.governance_config.tenant_id != tenant_id:
            logger.warning(
                f"Tenant {tenant_id} attempted to access session {session_id} "
                f"belonging to tenant {session_context.governance_config.tenant_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: session belongs to different tenant",
            )

        # Get remaining TTL
        ttl_remaining = await manager.store.get_ttl(session_id, tenant_id)

        return SessionResponse.from_session_context(session_context, ttl_remaining)

    except HTTPException:
        raise
    except ENDPOINT_ERRORS as e:
        logger.error(f"Failed to get session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve session: {e!s}",
        ) from e


async def update_session_governance(
    session_id: str,
    request: UpdateGovernanceRequest,
    tenant_id: str,
    manager: SessionContextManager,
) -> SessionResponse:
    """Update session governance configuration."""
    try:
        # Get existing session
        existing = await manager.get(session_id, tenant_id)

        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        # Verify tenant access
        if existing.governance_config.tenant_id != tenant_id:
            logger.warning(
                f"Tenant {tenant_id} attempted to update session {session_id} "
                f"belonging to tenant {existing.governance_config.tenant_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: session belongs to different tenant",
            )

        # Build updated governance config
        current_config = existing.governance_config
        risk_level_map = {
            "low": RiskLevel.LOW,
            "medium": RiskLevel.MEDIUM,
            "high": RiskLevel.HIGH,
            "critical": RiskLevel.CRITICAL,
        }

        updated_config = SessionGovernanceConfig(
            session_id=session_id,
            tenant_id=current_config.tenant_id,
            user_id=current_config.user_id,
            risk_level=(
                risk_level_map.get(request.risk_level, current_config.risk_level)
                if request.risk_level
                else current_config.risk_level
            ),
            policy_id=(
                request.policy_id if request.policy_id is not None else current_config.policy_id
            ),
            policy_overrides=(
                request.policy_overrides
                if request.policy_overrides is not None
                else current_config.policy_overrides
            ),
            enabled_policies=(
                request.enabled_policies
                if request.enabled_policies is not None
                else current_config.enabled_policies
            ),
            disabled_policies=(
                request.disabled_policies
                if request.disabled_policies is not None
                else current_config.disabled_policies
            ),
            require_human_approval=(
                request.require_human_approval
                if request.require_human_approval is not None
                else current_config.require_human_approval
            ),
            max_automation_level=(
                request.max_automation_level
                if request.max_automation_level is not None
                else current_config.max_automation_level
            ),
        )

        # Update session
        updated = await manager.update(
            session_id=session_id,
            tenant_id=tenant_id,
            governance_config=updated_config,
            metadata=request.metadata,
            ttl=request.extend_ttl_seconds,
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update session",
            )

        # Get remaining TTL
        ttl_remaining = await manager.store.get_ttl(session_id, tenant_id)

        logger.info(f"Updated governance for session {session_id}")

        return SessionResponse.from_session_context(updated, ttl_remaining)

    except HTTPException:
        raise
    except ENDPOINT_ERRORS as e:
        logger.error(f"Failed to update session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update session: {e!s}",
        ) from e


async def delete_session(
    session_id: str,
    tenant_id: str,
    manager: SessionContextManager,
) -> None:
    """Delete a session."""
    try:
        # Get existing session to verify tenant access
        existing = await manager.get(session_id, tenant_id)

        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        # Verify tenant access
        if existing.governance_config.tenant_id != tenant_id:
            logger.warning(
                f"Tenant {tenant_id} attempted to delete session {session_id} "
                f"belonging to tenant {existing.governance_config.tenant_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: session belongs to different tenant",
            )

        # Delete session
        success = await manager.delete(session_id, tenant_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete session",
            )

        logger.info(f"Deleted session {session_id}")

    except HTTPException:
        raise
    except ENDPOINT_ERRORS as e:
        logger.error(f"Failed to delete session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session: {e!s}",
        ) from e


async def extend_session_ttl(
    session_id: str,
    ttl_seconds: int,
    tenant_id: str,
    manager: SessionContextManager,
) -> SessionResponse:
    """Extend session TTL."""
    try:
        # Get existing session
        existing = await manager.get(session_id, tenant_id)

        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        # Verify tenant access
        if existing.governance_config.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: session belongs to different tenant",
            )

        # Extend TTL
        success = await manager.extend_ttl(session_id, tenant_id, ttl_seconds)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to extend session TTL",
            )

        # Get updated session and remaining TTL
        updated = await manager.get(session_id, tenant_id)
        ttl_remaining = await manager.store.get_ttl(session_id, tenant_id)

        logger.info(f"Extended TTL for session {session_id} to {ttl_seconds}s")

        return SessionResponse.from_session_context(updated, ttl_remaining)

    except HTTPException:
        raise
    except ENDPOINT_ERRORS as e:
        logger.error(f"Failed to extend session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extend session: {e!s}",
        ) from e


def _normalize_policy_selection_request(
    request: PolicySelectionRequest | None,
) -> PolicySelectionRequest:
    """Return the provided policy request or defaults."""
    return request if request is not None else PolicySelectionRequest()


async def _get_authorized_session_governance_config(
    session_id: str,
    tenant_id: str,
    manager: SessionContextManager,
) -> SessionGovernanceConfig:
    """Fetch session governance config and enforce tenant access."""
    session = await manager.get(session_id, tenant_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    if session.governance_config.tenant_id != tenant_id:
        logger.warning(
            f"Tenant {tenant_id} attempted policy selection for session "
            f"{session_id} belonging to {session.governance_config.tenant_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: session belongs to different tenant",
        )

    return session.governance_config


def _resolve_effective_risk_level(
    config: SessionGovernanceConfig,
    request: PolicySelectionRequest,
) -> str:
    """Resolve the effective risk level from override or session config."""
    if request.risk_level_override:
        return request.risk_level_override

    risk_level = config.risk_level
    if hasattr(risk_level, "value"):
        return risk_level.value  # type: ignore[no-any-return]

    return str(risk_level)


def _apply_policy_candidate(
    policy: SelectedPolicy,
    include_all_candidates: bool,
    selected_policy: SelectedPolicy | None,
    candidate_policies: list[SelectedPolicy],
) -> SelectedPolicy | None:
    """Apply one candidate policy to selection state."""
    if selected_policy is None:
        selected_policy = policy

    if include_all_candidates:
        candidate_policies.append(policy)

    return selected_policy


def _build_policy_selection(
    config: SessionGovernanceConfig,
    request: PolicySelectionRequest,
    tenant_id: str,
    risk_level: str,
) -> tuple[SelectedPolicy | None, list[SelectedPolicy]]:
    """Build selected policy and ordered candidate policies."""
    candidate_policies: list[SelectedPolicy] = []
    selected_policy: SelectedPolicy | None = None

    if config.policy_id:
        selected_policy = _apply_policy_candidate(
            policy=SelectedPolicy(
                policy_id=config.policy_id,
                name=config.policy_id,
                version=None,
                source="session",
                priority=100,
                reasoning=f"Session policy_id override: {config.policy_id}",
                metadata=config.policy_overrides,
            ),
            include_all_candidates=request.include_all_candidates,
            selected_policy=selected_policy,
            candidate_policies=candidate_policies,
        )

    if config.policy_overrides and "policy_id" in config.policy_overrides:
        override_policy_id = config.policy_overrides["policy_id"]
        selected_policy = _apply_policy_candidate(
            policy=SelectedPolicy(
                policy_id=override_policy_id,
                name=override_policy_id,
                version=None,
                source="session",
                priority=95,
                reasoning=f"Session policy_overrides.policy_id: {override_policy_id}",
                metadata={k: v for k, v in config.policy_overrides.items() if k != "policy_id"},
            ),
            include_all_candidates=request.include_all_candidates,
            selected_policy=selected_policy,
            candidate_policies=candidate_policies,
        )

    for i, policy_id in enumerate(config.enabled_policies):
        if not request.include_disabled and policy_id in config.disabled_policies:
            continue

        selected_policy = _apply_policy_candidate(
            policy=SelectedPolicy(
                policy_id=policy_id,
                name=policy_id,
                version=None,
                source="session",
                priority=90 - i,
                reasoning=f"Session enabled_policies list (index {i})",
                metadata={},
            ),
            include_all_candidates=request.include_all_candidates,
            selected_policy=selected_policy,
            candidate_policies=candidate_policies,
        )

    if request.include_all_candidates or selected_policy is None:
        selected_policy = _apply_policy_candidate(
            policy=SelectedPolicy(
                policy_id=f"policy-tenant-{tenant_id}-default",
                name=f"Default Tenant Policy ({tenant_id})",
                version="1.0.0",
                source="tenant",
                priority=50,
                reasoning=f"Tenant default policy for risk_level={risk_level}",
                metadata={"risk_level": risk_level},
            ),
            include_all_candidates=request.include_all_candidates,
            selected_policy=selected_policy,
            candidate_policies=candidate_policies,
        )

    if request.include_all_candidates or selected_policy is None:
        selected_policy = _apply_policy_candidate(
            policy=SelectedPolicy(
                policy_id="policy-global-default",
                name="Global Default Policy",
                version="1.0.0",
                source="global",
                priority=10,
                reasoning="Global fallback policy",
                metadata={"constitutional_hash": CONSTITUTIONAL_HASH},
            ),
            include_all_candidates=request.include_all_candidates,
            selected_policy=selected_policy,
            candidate_policies=candidate_policies,
        )

    return selected_policy, candidate_policies


def _build_policy_selection_response(
    session_id: str,
    tenant_id: str,
    risk_level: str,
    selected_policy: SelectedPolicy | None,
    candidate_policies: list[SelectedPolicy],
    config: SessionGovernanceConfig,
    request: PolicySelectionRequest,
    elapsed_ms: float,
) -> PolicySelectionResponse:
    """Create a policy selection response payload."""
    return PolicySelectionResponse(
        session_id=session_id,
        tenant_id=tenant_id,
        risk_level=risk_level,
        selected_policy=selected_policy,
        candidate_policies=candidate_policies if request.include_all_candidates else [],
        enabled_policies=config.enabled_policies,
        disabled_policies=config.disabled_policies,
        selection_metadata={
            "elapsed_ms": round(elapsed_ms, 3),
            "cache_hit": False,
            "policy_name_filter": request.policy_name_filter,
            "include_disabled": request.include_disabled,
            "risk_level_source": "override" if request.risk_level_override else "session",
        },
        timestamp=datetime.now(UTC).isoformat(),
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


async def select_session_policies(
    session_id: str,
    request: PolicySelectionRequest | None,
    tenant_id: str,
    manager: SessionContextManager,
) -> PolicySelectionResponse:
    """Select applicable policies based on session context."""
    start_time = time.perf_counter()

    try:
        config = await _get_authorized_session_governance_config(
            session_id,
            tenant_id,
            manager,
        )
        request = _normalize_policy_selection_request(request)
        risk_level = _resolve_effective_risk_level(config, request)
        selected_policy, candidate_policies = _build_policy_selection(
            config=config,
            request=request,
            tenant_id=tenant_id,
            risk_level=risk_level,
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        response = _build_policy_selection_response(
            session_id=session_id,
            tenant_id=tenant_id,
            risk_level=risk_level,
            selected_policy=selected_policy,
            candidate_policies=candidate_policies,
            config=config,
            request=request,
            elapsed_ms=elapsed_ms,
        )

        logger.info(
            f"Policy selection for session {session_id}: "
            f"selected={selected_policy.policy_id if selected_policy else 'none'} "
            f"({elapsed_ms:.3f}ms)"
        )

        return response

    except HTTPException:
        raise
    except ENDPOINT_ERRORS as e:
        logger.error(f"Failed to select policies for session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to select policies: {e!s}",
        ) from e


async def get_session_metrics(
    manager: SessionContextManager,
) -> SessionMetricsResponse:
    """Get session manager performance metrics."""
    try:
        metrics = manager.get_metrics()
        return SessionMetricsResponse(
            cache_hits=metrics.get("cache_hits", 0),
            cache_misses=metrics.get("cache_misses", 0),
            cache_hit_rate=metrics.get("cache_hit_rate", 0.0),
            cache_size=metrics.get("cache_size", 0),
            cache_capacity=metrics.get("cache_capacity", 0),
            creates=metrics.get("creates", 0),
            reads=metrics.get("reads", 0),
            updates=metrics.get("updates", 0),
            deletes=metrics.get("deletes", 0),
            errors=metrics.get("errors", 0),
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
    except ENDPOINT_ERRORS as e:
        logger.error(f"Failed to get session metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get metrics: {e!s}",
        ) from e


__all__ = [
    "create_session",
    "delete_session",
    "extend_session_ttl",
    "get_session",
    "get_session_metrics",
    "select_session_policies",
    "update_session_governance",
]
