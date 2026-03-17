"""
ACGS-2 Enhanced Agent Bus Governance Routes
Constitutional Hash: cdd01ef066bc6cf2

This module provides governance-related endpoints including stability metrics
and MACI record operations with PQC enforcement gates.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, cast

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from pydantic import BaseModel, Field
from src.core.shared.security.auth import UserClaims, get_current_user

from enhanced_agent_bus.observability.structured_logging import get_logger

from ...api_models import StabilityMetricsResponse
from ..runtime_guards import require_sandbox_endpoint
from ._tenant_auth import get_tenant_id

logger = get_logger(__name__)

router = APIRouter()

if TYPE_CHECKING:
    from ...pqc_enforcement_config import (
        EnforcementModeConfigService as EnforcementConfigServiceType,
    )
else:
    EnforcementConfigServiceType = Any


class StabilityLayerProtocol(Protocol):
    """Typed view of the stability layer used by API responses."""

    last_stats: dict[str, float | str] | None


class GovernanceProtocol(Protocol):
    """Typed view of governance dependency surface used by this route."""

    stability_layer: StabilityLayerProtocol | None


GovernanceFactory = Callable[[], GovernanceProtocol | None]


def _load_governance_dependency() -> GovernanceFactory:
    """Load governance factory with fallback import paths."""
    try:
        from ...governance.ccai_framework import get_ccai_governance as _get_ccai_governance

        return cast(GovernanceFactory, _get_ccai_governance)
    except ImportError:
        pass

    try:
        from governance.ccai_framework import get_ccai_governance as _get_ccai_governance

        return cast(GovernanceFactory, _get_ccai_governance)
    except ImportError:
        pass

    def _missing_governance() -> GovernanceProtocol | None:
        return None

    return _missing_governance


def _default_stability_metrics() -> StabilityMetricsResponse:
    """Build default stability response when no stats are available."""
    return StabilityMetricsResponse(
        spectral_radius_bound=1.0,
        divergence=0.0,
        max_weight=0.0,
        stability_hash="mhc_init",
        input_norm=0.0,
        output_norm=0.0,
    )


get_ccai_governance = _load_governance_dependency()


@router.get(
    "/api/v1/governance/stability/metrics",
    response_model=StabilityMetricsResponse,
    tags=["Governance"],
)
async def get_stability_metrics(
    _user: UserClaims = Depends(get_current_user),
) -> StabilityMetricsResponse:
    """
    Get real-time stability metrics from the Manifold-Constrained HyperConnection (mHC) layer.

    Returns:
    - Spectral radius bound (guaranteed <= 1.0)
    - Divergence metrics
    - Stability hash for auditability
    """
    if not (gov := get_ccai_governance()):
        raise HTTPException(status_code=503, detail="Governance framework not initialized")

    if not (stability_layer := gov.stability_layer):
        raise HTTPException(status_code=503, detail="Stability layer not active")

    if not (stats := stability_layer.last_stats):
        return _default_stability_metrics()

    return StabilityMetricsResponse(**stats)


# ---------------------------------------------------------------------------
# PQC Enforcement Integration (Phase 3)
# ---------------------------------------------------------------------------

try:
    from ...pqc_enforcement_config import (
        EnforcementModeConfigService as _EnforcementModeConfigService,
    )
    from ...pqc_validators import check_enforcement_for_create, check_enforcement_for_update
except ImportError:
    # Fallback for isolated test runs
    try:
        from pqc_enforcement_config import (  # type: ignore[no-redef]
            EnforcementModeConfigService as _EnforcementModeConfigService,
        )
        from pqc_validators import (  # type: ignore[no-redef]
            check_enforcement_for_create,
            check_enforcement_for_update,
        )
    except ImportError:
        _EnforcementModeConfigService = None
        check_enforcement_for_create = None  # type: ignore[assignment]
        check_enforcement_for_update = None  # type: ignore[assignment]

try:
    from src.core.shared.security.pqc import (
        ClassicalKeyRejectedError,
        MigrationRequiredError,
        PQCKeyRequiredError,
        UnsupportedPQCAlgorithmError,
    )

    from ...pqc_enforcement_models import PQCRejectionError
except ImportError:
    ClassicalKeyRejectedError = None  # type: ignore[assignment,misc]
    MigrationRequiredError = None  # type: ignore[assignment,misc]
    PQCKeyRequiredError = None  # type: ignore[assignment,misc]
    UnsupportedPQCAlgorithmError = None  # type: ignore[assignment,misc]
    PQCRejectionError = None  # type: ignore[assignment,misc]


_PQC_ENFORCEMENT_ERRORS = tuple(
    e
    for e in (
        ClassicalKeyRejectedError,
        PQCKeyRequiredError,
        UnsupportedPQCAlgorithmError,
        MigrationRequiredError,
    )
    if e is not None
)


def _enforcement_error_to_422(exc: Exception) -> HTTPException:
    """Convert a PQC enforcement error into an HTTP 422 response."""
    error_code = getattr(exc, "error_code", "PQC_ERROR")
    supported = getattr(exc, "supported_algorithms", [])
    body = {
        "error_code": error_code,
        "message": str(exc),
        "supported_algorithms": supported,
    }
    return HTTPException(status_code=422, detail=body)


class MACIRecordCreateRequest(BaseModel):
    """Request body for creating a MACI record with PQC enforcement."""

    record_id: str = Field(..., description="MACI record identifier")
    key_type: str | None = Field(None, description="Key type: 'pqc', 'classical', or None")
    key_algorithm: str | None = Field(None, description="Algorithm (e.g. ML-DSA-65, RSA-2048)")
    data: dict[str, Any] = Field(default_factory=dict, description="Record payload")


class MACIRecordUpdateRequest(BaseModel):
    """Request body for updating a MACI record with PQC enforcement."""

    data: dict[str, Any] = Field(default_factory=dict, description="Updated record payload")


class MACIRecordResponse(BaseModel):
    """Response for MACI record operations."""

    record_id: str
    status: str = "ok"


def _get_enforcement_config() -> EnforcementConfigServiceType | None:
    """FastAPI dependency returning the enforcement config service, or None."""
    return None


@router.post(
    "/api/v1/maci/records",
    response_model=MACIRecordResponse,
    tags=["MACI"],
    status_code=201,
)
async def create_maci_record(
    body: MACIRecordCreateRequest,
    request: Request,
    _tenant_id: str = Depends(get_tenant_id),
    enforcement_svc: EnforcementConfigServiceType | None = Depends(_get_enforcement_config),
) -> MACIRecordResponse:
    """Create a new MACI record with PQC enforcement gate.

    Under strict mode, classical keys are rejected and PQC keys are validated
    against the approved algorithm set (ML-DSA-*, ML-KEM-*).
    """
    require_sandbox_endpoint(
        "MACI record write endpoint",
        "record CRUD currently returns placeholder responses without a persistent MACI store",
    )
    if enforcement_svc is not None and check_enforcement_for_create is not None:
        migration_ctx = request.headers.get("X-Migration-Context", "").lower() == "true"
        try:
            await check_enforcement_for_create(
                key_type=body.key_type,
                key_algorithm=body.key_algorithm,
                enforcement_config=enforcement_svc,
                migration_context=migration_ctx,
            )
        except _PQC_ENFORCEMENT_ERRORS as exc:
            raise _enforcement_error_to_422(exc) from exc

    return MACIRecordResponse(record_id=body.record_id, status="created")


@router.patch(
    "/api/v1/maci/records/{record_id}",
    response_model=MACIRecordResponse,
    tags=["MACI"],
)
async def update_maci_record(
    record_id: str,
    body: MACIRecordUpdateRequest,
    request: Request,
    _tenant_id: str = Depends(get_tenant_id),
    enforcement_svc: EnforcementConfigServiceType | None = Depends(_get_enforcement_config),
) -> MACIRecordResponse:
    """Update an existing MACI record with PQC enforcement gate.

    Under strict mode, records using classical keys must be migrated first.
    Pass X-Migration-Context: true header with migration-service role to bypass.
    """
    require_sandbox_endpoint(
        "MACI record write endpoint",
        "record CRUD currently returns placeholder responses without a persistent MACI store",
    )
    existing_key_type = "classical"  # In production, fetched from record store

    if enforcement_svc is not None and check_enforcement_for_update is not None:
        migration_ctx = request.headers.get("X-Migration-Context", "").lower() == "true"
        try:
            await check_enforcement_for_update(
                existing_key_type=existing_key_type,
                enforcement_config=enforcement_svc,
                migration_context=migration_ctx,
            )
        except _PQC_ENFORCEMENT_ERRORS as exc:
            raise _enforcement_error_to_422(exc) from exc

    return MACIRecordResponse(record_id=record_id, status="updated")


@router.get(
    "/api/v1/maci/records/{record_id}",
    response_model=MACIRecordResponse,
    tags=["MACI"],
)
async def get_maci_record(
    record_id: str,
    _tenant_id: str = Depends(get_tenant_id),
) -> MACIRecordResponse:
    """Read a MACI record. No PQC enforcement check — reads are always allowed."""
    require_sandbox_endpoint(
        "MACI record read endpoint",
        "record CRUD currently returns placeholder responses without a persistent MACI store",
    )
    return MACIRecordResponse(record_id=record_id, status="ok")


@router.delete(
    "/api/v1/maci/records/{record_id}",
    response_model=MACIRecordResponse,
    tags=["MACI"],
)
async def delete_maci_record(
    record_id: str,
    _tenant_id: str = Depends(get_tenant_id),
) -> MACIRecordResponse:
    """Delete a MACI record. No PQC enforcement check — deletes are key-type agnostic."""
    require_sandbox_endpoint(
        "MACI record delete endpoint",
        "record CRUD currently returns placeholder responses without a persistent MACI store",
    )
    return MACIRecordResponse(record_id=record_id, status="deleted")


__all__ = [
    "create_maci_record",
    "delete_maci_record",
    "get_maci_record",
    "get_stability_metrics",
    "router",
    "update_maci_record",
]
