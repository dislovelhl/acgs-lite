"""
Modular Constitutional Storage Service for ACGS-2.
Constitutional Hash: 608508a9bd224290

Orchestrates caching, persistence, and locking for constitutional metadata.
"""

from typing import Literal

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from ..amendment_model import AmendmentProposal
from ..version_model import ConstitutionalStatus, ConstitutionalVersion
from .cache import CacheManager
from .config import StorageConfig
from .locking import LockManager
from .persistence import PersistenceManager

logger = get_logger(__name__)


class ConstitutionalStorageService:
    """
    Facade for constitutional storage orchestrating cache and persistence.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        config: StorageConfig | None = None,
        cache: CacheManager | None = None,
        persistence: PersistenceManager | None = None,
        lock: LockManager | None = None,
    ):
        self.config = config or StorageConfig()
        self.cache = cache or CacheManager(self.config)
        self.persistence = persistence or PersistenceManager(self.config)
        self.lock = lock or LockManager(self.config, self.cache)

    async def connect(self) -> bool:
        """Connect to all storage backends."""
        cache_ok = await self.cache.connect()
        persist_ok = await self.persistence.connect()
        return cache_ok and persist_ok

    async def disconnect(self) -> None:
        """Disconnect from all storage backends."""
        await self.cache.disconnect()
        await self.persistence.disconnect()

    async def save_version(self, version: ConstitutionalVersion, tenant_id: str) -> bool:
        """Save a version to persistence."""
        return await self.persistence.save_version(version, tenant_id)

    async def get_version(self, version_id: str, tenant_id: str) -> ConstitutionalVersion | None:
        """Get version with caching."""
        cached = await self.cache.get_version(version_id, tenant_id)
        if cached:
            return cached

        version = await self.persistence.get_version(version_id, tenant_id)
        if version:
            await self.cache.set_version(version, tenant_id)
        return version

    async def get_active_version(self, tenant_id: str) -> ConstitutionalVersion | None:
        """Get active version with hot-path caching."""
        active_id = await self.cache.get_active_version_id(tenant_id)
        if active_id:
            version = await self.cache.get_version(active_id, tenant_id)
            if version:
                return version

        version = await self.persistence.get_active_version(tenant_id)
        if version:
            await self.cache.set_version(version, tenant_id)
            await self.cache.set_active_version(version.version_id, tenant_id)
        return version

    async def activate_version(self, version_id: str, tenant_id: str) -> bool:
        """Activate a version atomically using distributed locks."""
        if not await self.lock.acquire_lock(tenant_id):
            return False

        try:
            version = await self.get_version(version_id, tenant_id)
            if not version:
                return False

            # Transition state
            current = await self.get_active_version(tenant_id)
            if current:
                current.deactivate(reason="superseded")
                await self.persistence.update_version(current, tenant_id)

            version.activate()
            await self.persistence.update_version(version, tenant_id)

            await self.cache.set_version(version, tenant_id)
            await self.cache.set_active_version(version_id, tenant_id)
            return True
        finally:
            await self.lock.release_lock(tenant_id)

    async def save_amendment(self, amendment: AmendmentProposal, tenant_id: str) -> bool:
        """Save an amendment proposal."""
        return await self.persistence.save_amendment(amendment, tenant_id)

    async def get_amendment(self, proposal_id: str, tenant_id: str) -> AmendmentProposal | None:
        """Get an amendment proposal."""
        return await self.persistence.get_amendment(proposal_id, tenant_id)

    async def list_versions(
        self, tenant_id: str, limit: int = 50, offset: int = 0, status: str | None = None
    ) -> list[ConstitutionalVersion]:
        """list versions."""
        return await self.persistence.list_versions(tenant_id, limit, offset, status)

    async def list_amendments(
        self,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        proposer_id: str | None = None,
    ) -> tuple[list[AmendmentProposal], int]:
        """list amendments."""
        return await self.persistence.list_amendments(tenant_id, limit, offset, status, proposer_id)
