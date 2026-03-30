"""Admin API for durable self-evolution evidence bundles.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from enhanced_agent_bus.data_flywheel.models import EvidenceBundle
from src.core.self_evolution.evidence_store import SelfEvolutionEvidenceStore
from src.core.self_evolution.models import (
    FlywheelEvidenceBundleListResponse,
)
from src.core.shared.security.auth import UserClaims, get_current_user

router = APIRouter(prefix="/evolution/bounded-experiments", tags=["self-evolution-evidence"])

_STATE_STORE_ATTRIBUTE = "self_evolution_evidence_store"


def _get_store(request: Request) -> SelfEvolutionEvidenceStore:
    store = getattr(request.app.state, _STATE_STORE_ATTRIBUTE, None)
    if isinstance(store, SelfEvolutionEvidenceStore):
        return store
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Self-evolution evidence store is not configured",
    )


@router.get("", response_model=FlywheelEvidenceBundleListResponse)
async def list_bounded_experiment_evidence(
    user: UserClaims = Depends(get_current_user),
    store: SelfEvolutionEvidenceStore = Depends(_get_store),
) -> FlywheelEvidenceBundleListResponse:
    records = await store.list_records(tenant_id=user.tenant_id)
    return FlywheelEvidenceBundleListResponse(total=len(records), records=records)


@router.get("/{evidence_id}", response_model=EvidenceBundle)
async def get_bounded_experiment_evidence(
    evidence_id: str,
    user: UserClaims = Depends(get_current_user),
    store: SelfEvolutionEvidenceStore = Depends(_get_store),
) -> EvidenceBundle:
    record = await store.get(evidence_id, tenant_id=user.tenant_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence record not found",
        )
    return record


__all__ = ["router"]
