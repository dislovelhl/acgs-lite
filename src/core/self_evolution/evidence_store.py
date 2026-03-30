"""Repository-backed evidence access for self-evolution admin APIs."""

from __future__ import annotations

from enhanced_agent_bus.data_flywheel.models import EvidenceBundle
from enhanced_agent_bus.persistence.repository import WorkflowRepository


class SelfEvolutionEvidenceStore:
    """Tenant-scoped read access to durable evidence bundles."""

    def __init__(self, repository: WorkflowRepository) -> None:
        self._repository = repository

    async def list_records(
        self,
        *,
        tenant_id: str,
        workload_key: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EvidenceBundle]:
        return await self._repository.list_evidence_bundles(
            tenant_id=tenant_id,
            workload_key=workload_key,
            limit=limit,
            offset=offset,
        )

    async def get(self, evidence_id: str, *, tenant_id: str) -> EvidenceBundle | None:
        evidence = await self._repository.get_evidence_bundle(evidence_id)
        if evidence is None or evidence.tenant_id != tenant_id:
            return None
        return evidence


__all__ = ["SelfEvolutionEvidenceStore"]
