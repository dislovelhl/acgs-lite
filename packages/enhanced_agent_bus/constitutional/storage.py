"""
ACGS-2 Enhanced Agent Bus - Constitutional Storage Layer (Facade)
Constitutional Hash: cdd01ef066bc6cf2

Storage service for persisting constitutional versions with Redis caching
and PostgreSQL persistence. Supports atomic version transitions with locking.
Delegates to specialized modules in .storage_infra.
"""

try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .amendment_model import AmendmentProposal
from .storage_infra.config import StorageConfig
from .storage_infra.service import ConstitutionalStorageService as ModularStorageService
from .version_model import ConstitutionalStatus, ConstitutionalVersion

logger = get_logger(__name__)
__all__ = ["ConstitutionalStorageService", "StorageConfig"]


class ConstitutionalStorageService:
    """
    Facade for constitutional storage service (Backward Compatible).

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        redis_url: str | None = None,
        database_url: str | None = None,
        cache_ttl: int = 3600,
        lock_timeout: int = 30,
        enable_multi_tenancy: bool = True,
        default_tenant_id: str = "system",
    ):
        config = StorageConfig(
            redis_url=redis_url or "redis://localhost:6379",
            database_url=database_url or "postgresql+asyncpg://localhost/acgs2",
            cache_ttl=cache_ttl,
            lock_timeout=lock_timeout,
            enable_multi_tenancy=enable_multi_tenancy,
            default_tenant_id=default_tenant_id,
        )
        self._service = ModularStorageService(config=config)
        self.enable_multi_tenancy = enable_multi_tenancy
        self.default_tenant_id = default_tenant_id

    @property
    def engine(self):
        return self._service.persistence.engine

    @property
    def redis_client(self):
        return self._service.cache.redis_client

    def _get_tenant_id(self) -> str:
        """Get current tenant ID (delegated)."""
        from ..multi_tenancy.context import get_current_tenant_id

        if self.enable_multi_tenancy:
            tid = get_current_tenant_id()
            if tid:
                return tid
        return self.default_tenant_id

    async def connect(self) -> bool:
        return await self._service.connect()

    async def disconnect(self) -> None:
        await self._service.disconnect()

    async def save_version(
        self, version: ConstitutionalVersion, tenant_id: str | None = None
    ) -> bool:
        return await self._service.save_version(version, tenant_id or self._get_tenant_id())

    async def get_version(
        self, version_id: str, tenant_id: str | None = None
    ) -> ConstitutionalVersion | None:
        return await self._service.get_version(version_id, tenant_id or self._get_tenant_id())

    async def get_active_version(
        self, tenant_id: str | None = None
    ) -> ConstitutionalVersion | None:
        return await self._service.get_active_version(tenant_id or self._get_tenant_id())

    async def activate_version(
        self,
        version_id: str,
        _deactivate_current: bool = True,
        tenant_id: str | None = None,
    ) -> bool:
        return await self._service.activate_version(version_id, tenant_id or self._get_tenant_id())

    async def save_amendment(
        self, amendment: AmendmentProposal, tenant_id: str | None = None
    ) -> bool:
        return await self._service.save_amendment(amendment, tenant_id or self._get_tenant_id())

    async def get_amendment(
        self, proposal_id: str, tenant_id: str | None = None
    ) -> AmendmentProposal | None:
        return await self._service.get_amendment(proposal_id, tenant_id or self._get_tenant_id())

    async def list_versions(
        self,
        limit: int = 50,
        offset: int = 0,
        status: ConstitutionalStatus | None = None,
        tenant_id: str | None = None,
    ) -> list[ConstitutionalVersion]:
        return await self._service.list_versions(
            tenant_id or self._get_tenant_id(), limit, offset, status.value if status else None
        )

    async def list_amendments(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        proposer_agent_id: str | None = None,
        tenant_id: str | None = None,
    ) -> tuple[list[AmendmentProposal], int]:
        return await self._service.list_amendments(
            tenant_id or self._get_tenant_id(), limit, offset, status, proposer_agent_id
        )

    async def compute_diff(self, from_version_id: str, to_version_id: str) -> JSONDict | None:
        """Compute diff (legacy inline implementation)."""
        from_v = await self.get_version(from_version_id)
        to_v = await self.get_version(to_version_id)

        if not from_v or not to_v:
            return None

        added = {k: v for k, v in to_v.content.items() if k not in from_v.content}
        removed = {k: v for k, v in from_v.content.items() if k not in to_v.content}
        modified = {
            k: {"from": from_v.content[k], "to": to_v.content[k]}
            for k in from_v.content
            if k in to_v.content and from_v.content[k] != to_v.content[k]
        }

        return {
            "from_version": from_v.version,
            "to_version": to_v.version,
            "content_diff": {"added": added, "removed": removed, "modified": modified},
        }
