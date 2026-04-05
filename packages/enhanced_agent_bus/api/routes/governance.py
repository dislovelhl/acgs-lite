"""
ACGS-2 Enhanced Agent Bus Governance Routes
Constitutional Hash: 608508a9bd224290

This module provides governance-related endpoints including stability metrics
and MACI record operations with PQC enforcement gates.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Any, Protocol, cast

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)

from ..rate_limiting import limiter
from pydantic import BaseModel, Field

from enhanced_agent_bus._compat.security.auth import UserClaims, get_current_user
from enhanced_agent_bus.observability.structured_logging import get_logger

from ...api_models import StabilityMetricsResponse
from ...maci_enforcement import (
    MACIAction,
    MACIAgentRecord,
    MACIEnforcer,
    MACIRole,
    MACIRoleRegistry,
)
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
@limiter.limit("60/minute")
async def get_stability_metrics(
    request: Request,
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
    from enhanced_agent_bus._compat.security.pqc import (
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


@dataclass(slots=True)
class StoredMACIRecord:
    """Tenant-scoped MACI record used by the sandbox governance API."""

    record_id: str
    tenant_id: str
    data: dict[str, Any] = field(default_factory=dict)
    key_type: str | None = None
    key_algorithm: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def clone(self) -> "StoredMACIRecord":
        """Return a detached copy safe for API responses."""
        return StoredMACIRecord(
            record_id=self.record_id,
            tenant_id=self.tenant_id,
            data=deepcopy(self.data),
            key_type=self.key_type,
            key_algorithm=self.key_algorithm,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class MACIRecordStore:
    """Async in-memory store for MACI records."""

    def __init__(self) -> None:
        import asyncio

        self._records: dict[tuple[str, str], StoredMACIRecord] = {}
        self._lock = asyncio.Lock()

    async def create_record(
        self,
        *,
        record_id: str,
        tenant_id: str,
        data: dict[str, Any],
        key_type: str | None,
        key_algorithm: str | None,
    ) -> StoredMACIRecord | None:
        """Create a record or return None if the tenant-scoped id already exists."""
        async with self._lock:
            key = (tenant_id, record_id)
            if key in self._records:
                return None

            now = datetime.now(UTC)
            record = StoredMACIRecord(
                record_id=record_id,
                tenant_id=tenant_id,
                data=deepcopy(data),
                key_type=key_type,
                key_algorithm=key_algorithm,
                created_at=now,
                updated_at=now,
            )
            self._records[key] = record
            return record.clone()

    async def get_record(self, *, record_id: str, tenant_id: str) -> StoredMACIRecord | None:
        """Fetch a record by tenant-scoped id."""
        async with self._lock:
            record = self._records.get((tenant_id, record_id))
            return None if record is None else record.clone()

    async def update_record(
        self,
        *,
        record_id: str,
        tenant_id: str,
        data: dict[str, Any],
    ) -> StoredMACIRecord | None:
        """Replace a record payload and bump the update timestamp."""
        async with self._lock:
            key = (tenant_id, record_id)
            record = self._records.get(key)
            if record is None:
                return None

            record.data = deepcopy(data)
            record.updated_at = datetime.now(UTC)
            return record.clone()

    async def delete_record(self, *, record_id: str, tenant_id: str) -> StoredMACIRecord | None:
        """Delete a record by tenant-scoped id."""
        async with self._lock:
            record = self._records.pop((tenant_id, record_id), None)
            return None if record is None else record.clone()


class RedisMACIRecordStore(MACIRecordStore):
    """Redis-backed MACI record store shared across workers."""

    def __init__(self, redis_client: Any, *, key_prefix: str = "maci:records") -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix

    def _record_key(self, *, record_id: str, tenant_id: str) -> str:
        return f"{self._key_prefix}:{tenant_id}:{record_id}"

    @staticmethod
    def _decode_text(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode()
        return str(value)

    def _serialize_record(self, record: StoredMACIRecord) -> str:
        return json.dumps(
            {
                "record_id": record.record_id,
                "tenant_id": record.tenant_id,
                "data": deepcopy(record.data),
                "key_type": record.key_type,
                "key_algorithm": record.key_algorithm,
                "created_at": record.created_at.isoformat(),
                "updated_at": record.updated_at.isoformat(),
            }
        )

    def _deserialize_record(self, payload: str) -> StoredMACIRecord:
        data = json.loads(payload)
        return StoredMACIRecord(
            record_id=data["record_id"],
            tenant_id=data["tenant_id"],
            data=deepcopy(data.get("data", {})),
            key_type=data.get("key_type"),
            key_algorithm=data.get("key_algorithm"),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )

    async def create_record(
        self,
        *,
        record_id: str,
        tenant_id: str,
        data: dict[str, Any],
        key_type: str | None,
        key_algorithm: str | None,
    ) -> StoredMACIRecord | None:
        """Create a record atomically or return None if it already exists."""
        now = datetime.now(UTC)
        record = StoredMACIRecord(
            record_id=record_id,
            tenant_id=tenant_id,
            data=deepcopy(data),
            key_type=key_type,
            key_algorithm=key_algorithm,
            created_at=now,
            updated_at=now,
        )
        created = await self._redis.set(
            self._record_key(record_id=record_id, tenant_id=tenant_id),
            self._serialize_record(record),
            nx=True,
        )
        return record.clone() if created else None

    async def get_record(self, *, record_id: str, tenant_id: str) -> StoredMACIRecord | None:
        """Fetch a record by tenant-scoped id."""
        raw = await self._redis.get(self._record_key(record_id=record_id, tenant_id=tenant_id))
        if raw is None:
            return None
        return self._deserialize_record(self._decode_text(raw))

    async def update_record(
        self,
        *,
        record_id: str,
        tenant_id: str,
        data: dict[str, Any],
    ) -> StoredMACIRecord | None:
        """Replace a record payload and bump the update timestamp."""
        record = await self.get_record(record_id=record_id, tenant_id=tenant_id)
        if record is None:
            return None

        record.data = deepcopy(data)
        record.updated_at = datetime.now(UTC)
        await self._redis.set(
            self._record_key(record_id=record_id, tenant_id=tenant_id),
            self._serialize_record(record),
            xx=True,
        )
        return record.clone()

    async def delete_record(self, *, record_id: str, tenant_id: str) -> StoredMACIRecord | None:
        """Delete a record by tenant-scoped id."""
        key = self._record_key(record_id=record_id, tenant_id=tenant_id)
        raw = await self._redis.get(key)
        if raw is None:
            return None

        await self._redis.delete(key)
        return self._deserialize_record(self._decode_text(raw))


class MACIRegistryConflictError(RuntimeError):
    """Raised when a MACI agent already exists in the shared registry."""


class RedisMACIRoleRegistry(MACIRoleRegistry):
    """Redis-backed MACI registry shared across workers."""

    def __init__(self, redis_client: Any, *, key_prefix: str = "maci") -> None:
        super().__init__()
        self._redis = redis_client
        self._key_prefix = key_prefix

    @staticmethod
    def _decode_text(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode()
        return str(value)

    @staticmethod
    def _scope(session_id: str | None) -> str:
        return session_id or "__global__"

    def _agent_key(self, agent_id: str, session_id: str | None = None) -> str:
        return f"{self._key_prefix}:agents:{self._scope(session_id)}:{agent_id}"

    def _agent_outputs_key(self, agent_id: str, session_id: str | None = None) -> str:
        return f"{self._key_prefix}:agent_outputs:{self._scope(session_id)}:{agent_id}"

    def _output_key(self, output_id: str, session_id: str | None = None) -> str:
        return f"{self._key_prefix}:outputs:{self._scope(session_id)}:{output_id}"

    def _serialize_agent_record(self, record: MACIAgentRecord) -> str:
        return json.dumps(
            {
                "agent_id": record.agent_id,
                "role": record.role.value,
                "metadata": deepcopy(record.metadata),
                "constitutional_hash": record.constitutional_hash,
                "registered_at": record.registered_at.isoformat(),
                "session_id": record.session_id,
            }
        )

    def _deserialize_agent_record(self, payload: str, *, outputs: list[str]) -> MACIAgentRecord:
        data = json.loads(payload)
        return MACIAgentRecord(
            agent_id=data["agent_id"],
            role=MACIRole(data["role"]),
            outputs=list(outputs),
            registered_at=datetime.fromisoformat(data["registered_at"]),
            metadata=deepcopy(data.get("metadata", {})),
            constitutional_hash=data.get("constitutional_hash", self.constitutional_hash),
            session_id=data.get("session_id"),
        )

    async def _scan_keys(self, pattern: str) -> list[str]:
        scan_iter = getattr(self._redis, "scan_iter", None)
        if callable(scan_iter):
            keys: list[str] = []
            async for key in scan_iter(match=pattern):
                keys.append(self._decode_text(key))
            return keys

        keys = await self._redis.keys(pattern)
        return [self._decode_text(key) for key in keys]

    async def _load_agent_record(
        self,
        agent_id: str,
        *,
        session_id: str | None = None,
    ) -> MACIAgentRecord | None:
        raw = await self._redis.get(self._agent_key(agent_id, session_id=session_id))
        if raw is None:
            return None

        outputs = await self._redis.smembers(
            self._agent_outputs_key(agent_id, session_id=session_id)
        )
        decoded_outputs = [self._decode_text(output_id) for output_id in outputs]
        return self._deserialize_agent_record(
            self._decode_text(raw),
            outputs=sorted(decoded_outputs),
        )

    async def register_agent(
        self,
        agent_id: str,
        role: MACIRole,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> MACIAgentRecord:
        """Register an agent in Redis for the provided tenant/session scope."""
        safe_metadata = deepcopy(metadata) if metadata is not None else {}
        record = MACIAgentRecord(
            agent_id=agent_id,
            role=role,
            metadata=safe_metadata,
            session_id=session_id,
        )
        created = await self._redis.set(
            self._agent_key(agent_id, session_id=session_id),
            self._serialize_agent_record(record),
            nx=True,
        )
        if not created:
            raise MACIRegistryConflictError(
                f"MACI agent '{agent_id}' already exists for session '{session_id or 'global'}'"
            )
        return record

    async def unregister_agent(
        self,
        agent_id: str,
        session_id: str | None = None,
    ) -> MACIAgentRecord | None:
        """Unregister an agent and clean up its output ownership mappings."""
        record = await self.get_agent(agent_id, session_id=session_id)
        if record is None:
            return None

        outputs_key = self._agent_outputs_key(agent_id, session_id=session_id)
        output_ids = await self._redis.smembers(outputs_key)
        output_keys = [
            self._output_key(self._decode_text(output_id), session_id=session_id)
            for output_id in output_ids
        ]

        delete_keys = [
            self._agent_key(agent_id, session_id=session_id),
            outputs_key,
            *output_keys,
        ]
        await self._redis.delete(*delete_keys)
        return record

    async def get_agent(
        self, agent_id: str, session_id: str | None = None
    ) -> MACIAgentRecord | None:
        """Get agent by ID, optionally scoped to a session."""
        return await self._load_agent_record(agent_id, session_id=session_id)

    async def get_agents_by_role(
        self, role: MACIRole, session_id: str | None = None
    ) -> list[MACIAgentRecord]:
        """Get all agents with a specific role."""
        agents = await self.get_session_agents(self._scope(session_id))
        return [agent for agent in agents.values() if agent.role == role]

    async def get_session_agents(self, session_id: str) -> dict[str, MACIAgentRecord]:
        """Get all agents registered for a session."""
        scope = self._scope(None if session_id == "__global__" else session_id)
        keys = await self._scan_keys(f"{self._key_prefix}:agents:{scope}:*")
        records: dict[str, MACIAgentRecord] = {}
        for key in keys:
            agent_id = key.rsplit(":", 1)[-1]
            record = await self._load_agent_record(
                agent_id,
                session_id=None if scope == "__global__" else scope,
            )
            if record is not None:
                records[agent_id] = record
        return records

    async def clear_session(self, session_id: str) -> int:
        """Clear all agents registered for a session."""
        agents = await self.get_session_agents(session_id)
        removed = 0
        for agent_id in list(agents):
            record = await self.unregister_agent(agent_id, session_id=session_id)
            if record is not None:
                removed += 1
        return removed

    async def record_output(
        self,
        agent_id: str,
        output_id: str,
        session_id: str | None = None,
    ) -> None:
        """Record an output produced by an agent."""
        if await self.get_agent(agent_id, session_id=session_id) is None:
            return

        await self._redis.sadd(
            self._agent_outputs_key(agent_id, session_id=session_id),
            output_id,
        )
        await self._redis.set(self._output_key(output_id, session_id=session_id), agent_id)

    async def get_output_producer(
        self,
        output_id: str,
        session_id: str | None = None,
    ) -> str | None:
        """Get the agent ID that produced a specific output."""
        raw = await self._redis.get(self._output_key(output_id, session_id=session_id))
        if raw is None:
            return None
        return self._decode_text(raw)

    async def is_self_output(
        self,
        agent_id: str,
        output_id: str,
        session_id: str | None = None,
    ) -> bool:
        """Check if an output was produced by a specific agent."""
        producer_id = await self.get_output_producer(output_id, session_id=session_id)
        return producer_id == agent_id

    async def batch_record_outputs(
        self,
        agent_id: str,
        output_ids: list[str],
        session_id: str | None = None,
    ) -> None:
        """Batch record output ownership for an agent."""
        if await self.get_agent(agent_id, session_id=session_id) is None:
            return

        outputs_key = self._agent_outputs_key(agent_id, session_id=session_id)
        await self._redis.sadd(outputs_key, *output_ids)
        for output_id in output_ids:
            await self._redis.set(self._output_key(output_id, session_id=session_id), agent_id)


class InMemoryPQCConfigBackend:
    """Minimal async backend for the sandbox PQC enforcement service."""

    def __init__(self) -> None:
        import asyncio

        self._hashes: dict[str, dict[str, str]] = {}
        self._lock = asyncio.Lock()

    async def hget(self, key: str, field: str) -> str | None:
        async with self._lock:
            return self._hashes.get(key, {}).get(field)

    async def hset(self, key: str, field: str, value: str) -> int:
        async with self._lock:
            self._hashes.setdefault(key, {})[field] = value
        return 1

    async def publish(self, _channel: str, _message: str) -> int:
        return 1


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
    tenant_id: str | None = None
    key_type: str | None = None
    key_algorithm: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MACIAgentRegisterRequest(BaseModel):
    """Request body for registering a tenant-scoped MACI agent."""

    agent_id: str = Field(..., description="MACI agent identifier")
    role: MACIRole = Field(..., description="MACI role assigned to the agent")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Agent metadata")


class MACIAgentResponse(BaseModel):
    """Response for MACI agent registration."""

    agent_id: str
    role: MACIRole
    status: str = "registered"
    tenant_id: str
    outputs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    registered_at: datetime | None = None


class MACIOutputRecordRequest(BaseModel):
    """Request body for recording a MACI-governed output."""

    agent_id: str = Field(..., description="Agent that produced the output")
    output_id: str = Field(..., description="Output identifier to record")


class MACIOutputRecordResponse(BaseModel):
    """Response for MACI output recording."""

    agent_id: str
    output_id: str
    status: str = "recorded"
    tenant_id: str


class MACIActionValidationRequest(BaseModel):
    """Request body for validating a MACI-governed action."""

    agent_id: str = Field(..., description="Agent requesting the action")
    action: MACIAction = Field(..., description="Action to validate")
    target_output_id: str | None = Field(None, description="Optional output under review")
    target_agent_id: str | None = Field(None, description="Optional target agent under review")


class MACIActionValidationResponse(BaseModel):
    """Response for MACI action validation."""

    allowed: bool
    agent_id: str
    action: str
    status: str = "validated"
    tenant_id: str
    target_output_id: str | None = None
    target_agent_id: str | None = None
    constitutional_hash: str | None = None
    validated_at: datetime | None = None
    details: dict[str, Any] = Field(default_factory=dict)


async def _get_maci_record_store(request: Request) -> MACIRecordStore | None:
    """Return the app-scoped MACI record store when the runtime wires one in."""
    app_state = getattr(request.app, "state", None)
    if app_state is None:
        return None

    store = getattr(app_state, "maci_record_store", None)
    return store if isinstance(store, MACIRecordStore) else None


async def _get_enforcement_config(request: Request) -> EnforcementConfigServiceType | None:
    """Return the app-scoped PQC enforcement service when available."""
    if _EnforcementModeConfigService is None:
        return None

    app_state = getattr(request.app, "state", None)
    if app_state is None:
        return None

    service = getattr(app_state, "pqc_enforcement_service", None)
    if isinstance(service, _EnforcementModeConfigService):
        return cast(EnforcementConfigServiceType, service)
    return None


async def _get_maci_registry(request: Request) -> MACIRoleRegistry:
    """Return the app-scoped MACI registry."""
    app_state = getattr(request.app, "state", None)
    if app_state is None:
        raise HTTPException(status_code=503, detail="MACI registry not initialized")

    registry = getattr(app_state, "maci_role_registry", None)
    if isinstance(registry, MACIRoleRegistry):
        return registry

    enforcer = getattr(app_state, "maci_enforcer", None)
    if isinstance(enforcer, MACIEnforcer):
        app_state.maci_role_registry = enforcer.registry
        return enforcer.registry

    raise HTTPException(status_code=503, detail="MACI registry not initialized")


async def _get_maci_enforcer(
    request: Request,
    registry: Annotated[MACIRoleRegistry, Depends(_get_maci_registry)],
) -> MACIEnforcer:
    """Return the app-scoped MACI enforcer, creating one on first use."""
    app_state = getattr(request.app, "state", None)
    if app_state is None:
        raise HTTPException(status_code=503, detail="MACI enforcer not initialized")

    enforcer = getattr(app_state, "maci_enforcer", None)
    if isinstance(enforcer, MACIEnforcer):
        if enforcer.registry is not registry:
            enforcer.registry = registry
        return enforcer

    enforcer = MACIEnforcer(registry=registry, strict_mode=True)
    app_state.maci_enforcer = enforcer
    return enforcer


def _record_not_found(record_id: str, tenant_id: str) -> HTTPException:
    """Build the canonical not-found response for MACI records."""
    return HTTPException(
        status_code=404,
        detail=f"MACI record '{record_id}' not found for tenant '{tenant_id}'",
    )


def _record_response(record: StoredMACIRecord, *, status: str) -> MACIRecordResponse:
    """Serialize a stored MACI record into an API response."""
    return MACIRecordResponse(
        record_id=record.record_id,
        status=status,
        tenant_id=record.tenant_id,
        key_type=record.key_type,
        key_algorithm=record.key_algorithm,
        data=deepcopy(record.data),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _agent_not_found(agent_id: str, tenant_id: str) -> HTTPException:
    """Build the canonical not-found response for tenant-scoped MACI agents."""
    return HTTPException(
        status_code=404,
        detail=f"MACI agent '{agent_id}' not found for tenant '{tenant_id}'",
    )


def _maci_agent_response(
    record: MACIAgentRecord,
    *,
    tenant_id: str,
    status: str,
) -> MACIAgentResponse:
    """Serialize a MACI agent record into an API response."""
    return MACIAgentResponse(
        agent_id=record.agent_id,
        role=record.role,
        status=status,
        tenant_id=tenant_id,
        outputs=list(record.outputs),
        metadata=deepcopy(record.metadata),
        registered_at=record.registered_at,
    )


def _maci_validation_response(
    *,
    tenant_id: str,
    agent_id: str,
    action: MACIAction,
    target_output_id: str | None,
    target_agent_id: str | None,
    result: Any,
) -> MACIActionValidationResponse:
    """Serialize a MACI validation result into an API response."""
    return MACIActionValidationResponse(
        allowed=bool(result.is_valid),
        agent_id=agent_id,
        action=action.value,
        tenant_id=tenant_id,
        target_output_id=target_output_id,
        target_agent_id=target_agent_id,
        constitutional_hash=result.constitutional_hash,
        validated_at=result.validated_at,
        details=deepcopy(result.details),
    )


@router.post(
    "/api/v1/maci/agents",
    response_model=MACIAgentResponse,
    tags=["MACI"],
    status_code=201,
)
@limiter.limit("20/minute")
async def register_maci_agent(
    request: Request,
    body: MACIAgentRegisterRequest,
    _tenant_id: str = Depends(get_tenant_id),
    registry: Annotated[MACIRoleRegistry, Depends(_get_maci_registry)] = None,
) -> MACIAgentResponse:
    """Register a MACI agent within the requesting tenant scope."""
    existing_record = await registry.get_agent(body.agent_id, session_id=_tenant_id)
    if existing_record is not None:
        raise HTTPException(
            status_code=409,
            detail=(f"MACI agent '{body.agent_id}' already exists for tenant '{_tenant_id}'"),
        )

    try:
        record = await registry.register_agent(
            agent_id=body.agent_id,
            role=body.role,
            metadata=body.metadata,
            session_id=_tenant_id,
        )
    except MACIRegistryConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=(f"MACI agent '{body.agent_id}' already exists for tenant '{_tenant_id}'"),
        ) from exc
    return _maci_agent_response(record, tenant_id=_tenant_id, status="registered")


@router.post(
    "/api/v1/maci/outputs",
    response_model=MACIOutputRecordResponse,
    tags=["MACI"],
    status_code=201,
)
@limiter.limit("20/minute")
async def record_maci_output(
    request: Request,
    body: MACIOutputRecordRequest,
    _tenant_id: str = Depends(get_tenant_id),
    registry: Annotated[MACIRoleRegistry, Depends(_get_maci_registry)] = None,
) -> MACIOutputRecordResponse:
    """Record tenant-scoped output ownership for later MACI validation."""
    agent_record = await registry.get_agent(body.agent_id, session_id=_tenant_id)
    if agent_record is None:
        raise _agent_not_found(body.agent_id, _tenant_id)

    await registry.record_output(body.agent_id, body.output_id, session_id=_tenant_id)
    return MACIOutputRecordResponse(
        agent_id=body.agent_id,
        output_id=body.output_id,
        tenant_id=_tenant_id,
    )


@router.post(
    "/api/v1/maci/actions/validate",
    response_model=MACIActionValidationResponse,
    tags=["MACI"],
)
@limiter.limit("20/minute")
async def validate_maci_action(
    request: Request,
    body: MACIActionValidationRequest,
    _tenant_id: str = Depends(get_tenant_id),
    enforcer: Annotated[MACIEnforcer, Depends(_get_maci_enforcer)] = None,
) -> MACIActionValidationResponse:
    """Validate a tenant-scoped MACI action using the core enforcement engine."""
    result = await enforcer.validate_action(
        agent_id=body.agent_id,
        action=body.action,
        target_output_id=body.target_output_id,
        target_agent_id=body.target_agent_id,
        session_id=_tenant_id,
    )
    return _maci_validation_response(
        tenant_id=_tenant_id,
        agent_id=body.agent_id,
        action=body.action,
        target_output_id=body.target_output_id,
        target_agent_id=body.target_agent_id,
        result=result,
    )


@router.post(
    "/api/v1/maci/records",
    response_model=MACIRecordResponse,
    tags=["MACI"],
    status_code=201,
)
@limiter.limit("20/minute")
async def create_maci_record(
    body: MACIRecordCreateRequest,
    request: Request,
    _tenant_id: str = Depends(get_tenant_id),
    enforcement_svc: EnforcementConfigServiceType | None = Depends(_get_enforcement_config),
    store: Annotated[MACIRecordStore | None, Depends(_get_maci_record_store)] = None,
) -> MACIRecordResponse:
    """Create a new MACI record with PQC enforcement gate.

    Under strict mode, classical keys are rejected and PQC keys are validated
    against the approved algorithm set (ML-DSA-*, ML-KEM-*).
    """
    require_sandbox_endpoint(
        "MACI record write endpoint",
        "record CRUD currently returns placeholder responses without a persistent MACI store",
    )
    if store is not None:
        existing_record = await store.get_record(record_id=body.record_id, tenant_id=_tenant_id)
        if existing_record is not None:
            raise HTTPException(
                status_code=409,
                detail=f"MACI record '{body.record_id}' already exists for tenant '{_tenant_id}'",
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

    if store is None:
        return MACIRecordResponse(record_id=body.record_id, status="created")

    record = await store.create_record(
        record_id=body.record_id,
        tenant_id=_tenant_id,
        data=body.data,
        key_type=body.key_type,
        key_algorithm=body.key_algorithm,
    )
    if record is None:
        raise HTTPException(
            status_code=409,
            detail=f"MACI record '{body.record_id}' already exists for tenant '{_tenant_id}'",
        )

    return _record_response(record, status="created")


@router.patch(
    "/api/v1/maci/records/{record_id}",
    response_model=MACIRecordResponse,
    tags=["MACI"],
)
@limiter.limit("20/minute")
async def update_maci_record(
    record_id: str,
    body: MACIRecordUpdateRequest,
    request: Request,
    _tenant_id: str = Depends(get_tenant_id),
    enforcement_svc: EnforcementConfigServiceType | None = Depends(_get_enforcement_config),
    store: Annotated[MACIRecordStore | None, Depends(_get_maci_record_store)] = None,
) -> MACIRecordResponse:
    """Update an existing MACI record with PQC enforcement gate.

    Under strict mode, records using classical keys must be migrated first.
    Pass X-Migration-Context: true header with migration-service role to bypass.
    """
    require_sandbox_endpoint(
        "MACI record write endpoint",
        "record CRUD currently returns placeholder responses without a persistent MACI store",
    )
    existing_key_type = "classical"
    if store is not None:
        existing_record = await store.get_record(record_id=record_id, tenant_id=_tenant_id)
        if existing_record is None:
            raise _record_not_found(record_id, _tenant_id)

        existing_key_type = existing_record.key_type or "classical"

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

    if store is None:
        return MACIRecordResponse(record_id=record_id, status="updated")

    updated_record = await store.update_record(
        record_id=record_id, tenant_id=_tenant_id, data=body.data
    )
    if updated_record is None:
        raise _record_not_found(record_id, _tenant_id)

    return _record_response(updated_record, status="updated")


@router.get(
    "/api/v1/maci/records/{record_id}",
    response_model=MACIRecordResponse,
    tags=["MACI"],
)
@limiter.limit("60/minute")
async def get_maci_record(
    record_id: str,
    request: Request,
    _tenant_id: str = Depends(get_tenant_id),
    store: Annotated[MACIRecordStore | None, Depends(_get_maci_record_store)] = None,
) -> MACIRecordResponse:
    """Read a MACI record. No PQC enforcement check — reads are always allowed."""
    require_sandbox_endpoint(
        "MACI record read endpoint",
        "record CRUD currently returns placeholder responses without a persistent MACI store",
    )
    if store is None:
        return MACIRecordResponse(record_id=record_id, status="ok")

    record = await store.get_record(record_id=record_id, tenant_id=_tenant_id)
    if record is None:
        raise _record_not_found(record_id, _tenant_id)

    return _record_response(record, status="ok")


@router.delete(
    "/api/v1/maci/records/{record_id}",
    response_model=MACIRecordResponse,
    tags=["MACI"],
)
@limiter.limit("20/minute")
async def delete_maci_record(
    record_id: str,
    request: Request,
    _tenant_id: str = Depends(get_tenant_id),
    store: Annotated[MACIRecordStore | None, Depends(_get_maci_record_store)] = None,
) -> MACIRecordResponse:
    """Delete a MACI record. No PQC enforcement check — deletes are key-type agnostic."""
    require_sandbox_endpoint(
        "MACI record delete endpoint",
        "record CRUD currently returns placeholder responses without a persistent MACI store",
    )
    if store is None:
        return MACIRecordResponse(record_id=record_id, status="deleted")

    record = await store.delete_record(record_id=record_id, tenant_id=_tenant_id)
    if record is None:
        raise _record_not_found(record_id, _tenant_id)

    return _record_response(record, status="deleted")


__all__ = [
    "InMemoryPQCConfigBackend",
    "MACIRecordStore",
    "RedisMACIRecordStore",
    "RedisMACIRoleRegistry",
    "StoredMACIRecord",
    "create_maci_record",
    "delete_maci_record",
    "get_maci_record",
    "get_stability_metrics",
    "record_maci_output",
    "register_maci_agent",
    "router",
    "update_maci_record",
    "validate_maci_action",
]
