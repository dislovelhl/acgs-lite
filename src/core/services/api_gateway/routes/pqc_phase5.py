# Constitutional Hash: 608508a9bd224290
"""ACGS-2 PQC Phase 5 Admin API Routes

Constitutional Hash: 608508a9bd224290

FastAPI routes for PQC-only mode activation and status queries.

Endpoints:
    POST /api/v1/admin/pqc/pqc-only-mode/activate
        Activate system-wide PQC-only enforcement. Requires platform-operator role
        AND a valid council-consensus-token (2/3 ML-DSA council signatures, FR-011).
        Writes PQC_ONLY_ACTIVATED audit event with constitutional_hash=608508a9bd224290.

    GET  /api/v1/admin/pqc/pqc-only-mode/status
        Query current PQC-only mode status. Requires admin role.

Registration::

    from .pqc_phase5 import pqc_phase5_router
    app.include_router(pqc_phase5_router, prefix="/api/v1/admin/pqc")
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.security.auth import UserClaims, require_role
from src.core.shared.structured_logging import get_logger
from src.core.tools.pqc_migration.phase5.models import CouncilConsensusToken

logger = get_logger(__name__)

# Router — prefix /api/v1/admin/pqc applied at include_router() call
pqc_phase5_router = APIRouter(
    prefix="/pqc-only-mode",
    tags=["PQC Phase 5 Admin"],
)

# Redis key for the PQC_ONLY_MODE flag
_REDIS_KEY = "pqc:config:pqc_only_mode"
_REDIS_META_KEY = "pqc:config:pqc_only_mode_meta"

# OPA endpoint for pqc_governance policy (FR-012)
_OPA_URL = os.environ.get("OPA_URL", "http://localhost:8181")
_OPA_POLICY_PATH = "/v1/data/pqc_governance/allow"

# Minimum quorum fraction for the consensus token (2/3)
_QUORUM_FRACTION: float = 2 / 3


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ActivatePQCOnlyModeRequest(BaseModel):
    operator_id: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1, max_length=1000)
    consensus_token: CouncilConsensusToken = Field(
        ...,
        description=(
            "Signed council-consensus-token proving >= 2/3 Governance Council "
            "approval via ML-DSA-65 signatures (FR-011)."
        ),
    )


class PQCOnlyModeStatusResponse(BaseModel):
    pqc_only_mode: bool
    activation_timestamp: str | None = None
    activated_by: str | None = None
    audit_event_id: str | None = None


# ---------------------------------------------------------------------------
# OPA guard
# ---------------------------------------------------------------------------


async def _opa_allow(
    user: UserClaims,
    proposal_id: str,
    consensus_token: CouncilConsensusToken,
) -> bool:
    """Call pqc_governance.rego and return True iff OPA allows the request.

    Input document shape matches the pqc_governance.rego policy:
      input.user.roles                          — list of role strings
      input.proposal.proposal_id                — proposal UUID
      input.consensus_token.signature_count     — integer count of ML-DSA-65 sigs
      input.council_size                        — integer total council members

    Returns False (deny) if the HTTP call fails for any reason so that
    failures are fail-closed rather than fail-open.
    """
    try:
        import httpx

        opa_input = {
            "input": {
                "user": {"roles": list(getattr(user, "roles", []))},
                "proposal": {"proposal_id": proposal_id},
                "consensus_token": {
                    "signature_count": consensus_token.signature_count,
                },
                "council_size": consensus_token.council_size,
            }
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{_OPA_URL}{_OPA_POLICY_PATH}", json=opa_input)
            if resp.status_code == 200:
                return bool(resp.json().get("result", False))
    except Exception as exc:
        logger.warning("opa_guard_failed", error=str(exc))

    return False


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------


async def _get_redis() -> aioredis.Redis | None:
    """Return a Redis client, or None if REDIS_URL is not configured."""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    try:
        client = aioredis.from_url(redis_url, decode_responses=True)
        return client
    except Exception as exc:
        logger.warning("pqc_phase5_redis_unavailable", error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@pqc_phase5_router.post(
    "/activate",
    response_model=PQCOnlyModeStatusResponse,
    summary="Activate PQC-only enforcement mode",
    description=(
        "Activate system-wide PQC-only enforcement. "
        "Requires platform-operator role. "
        "Writes PQC_ONLY_ACTIVATED audit event with "
        "constitutional_hash=608508a9bd224290."
    ),
)
async def activate_pqc_only_mode(
    request: ActivatePQCOnlyModeRequest,
    user: UserClaims = Depends(require_role("platform-operator")),
) -> PQCOnlyModeStatusResponse:
    """Activate PQC-only enforcement mode system-wide.

    Requires a valid ``consensus_token`` proving >= 2/3 Governance Council
    approval (FR-011).  The token is validated by the OPA pqc_governance.rego
    policy which checks the judicial-validator role and quorum threshold (FR-012).
    Returns HTTP 403 if either check fails.
    """
    import math

    # FR-011: Validate quorum inline before hitting OPA
    min_sigs = math.ceil(_QUORUM_FRACTION * request.consensus_token.council_size)
    if request.consensus_token.signature_count < min_sigs:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Insufficient council signatures: need {min_sigs}, "
                f"got {request.consensus_token.signature_count}"
            ),
        )

    # FR-012: OPAGuard — pqc_governance.rego must allow the transition
    allowed = await _opa_allow(
        user=user,
        proposal_id=request.consensus_token.proposal_id,
        consensus_token=request.consensus_token,
    )
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail="OPA policy denied PQC-only mode activation (pqc_governance.rego)",
        )

    redis_client = await _get_redis()
    if redis_client is None:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    try:
        async with redis_client as rc:
            # Check if already active
            current = await rc.get(_REDIS_KEY)
            if current == "true":
                raise HTTPException(
                    status_code=400,
                    detail="PQC_ONLY_MODE already active",
                )

            activation_ts = datetime.now(UTC).isoformat()
            audit_event_id = str(uuid.uuid4())

            # Persist the flag and metadata
            await rc.set(_REDIS_KEY, "true")
            meta: dict[str, Any] = {
                "activation_timestamp": activation_ts,
                "activated_by": request.operator_id,
                "audit_event_id": audit_event_id,
            }
            await rc.hset(_REDIS_META_KEY, mapping=meta)  # type: ignore[arg-type]

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("pqc_only_mode_activation_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to activate PQC-only mode") from exc

    # Emit governance audit event (FR-009)
    logger.info(
        "PQC_ONLY_ACTIVATED",
        operator_id=request.operator_id,
        timestamp=activation_ts,
        action_type="PQC_ONLY_ACTIVATED",
        entity_id=_REDIS_KEY,
        constitutional_hash=CONSTITUTIONAL_HASH,  # pragma: allowlist secret
        audit_event_id=audit_event_id,
        reason=request.reason,
    )

    return PQCOnlyModeStatusResponse(
        pqc_only_mode=True,
        activation_timestamp=activation_ts,
        activated_by=request.operator_id,
        audit_event_id=audit_event_id,
    )


@pqc_phase5_router.get(
    "/status",
    response_model=PQCOnlyModeStatusResponse,
    summary="Query PQC-only mode status",
    description="Return the current PQC-only mode status. Requires admin role.",
)
async def get_pqc_only_mode_status(
    user: UserClaims = Depends(require_role("admin")),
) -> PQCOnlyModeStatusResponse:
    """Return current PQC-only enforcement mode status."""
    redis_client = await _get_redis()
    if redis_client is None:
        # Degrade gracefully: return unknown state rather than 503
        logger.warning("pqc_only_mode_status_redis_unavailable")
        return PQCOnlyModeStatusResponse(pqc_only_mode=False)

    try:
        async with redis_client as rc:
            raw = await rc.get(_REDIS_KEY)
            active = raw == "true" if raw is not None else False

            activation_timestamp: str | None = None
            activated_by: str | None = None
            audit_event_id: str | None = None

            if active:
                meta = await rc.hgetall(_REDIS_META_KEY)
                if meta:
                    activation_timestamp = meta.get("activation_timestamp")
                    activated_by = meta.get("activated_by")
                    audit_event_id = meta.get("audit_event_id")

    except Exception as exc:
        logger.warning("pqc_only_mode_status_failed", error=str(exc))
        return PQCOnlyModeStatusResponse(pqc_only_mode=False)

    return PQCOnlyModeStatusResponse(
        pqc_only_mode=active,
        activation_timestamp=activation_timestamp,
        activated_by=activated_by,
        audit_event_id=audit_event_id,
    )
