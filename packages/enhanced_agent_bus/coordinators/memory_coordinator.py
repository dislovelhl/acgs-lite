"""
Memory Coordinator - Manages SAFLA neural memory operations.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.types import JSONDict

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
_MEMORY_COORDINATOR_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class MemoryCoordinator:
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __init__(
        self,
        persistence_enabled: bool = True,
        use_v3: bool = True,
    ):
        self._persistence_enabled = persistence_enabled
        self._use_v3 = use_v3
        self._memory_v3: object | None = None
        self._memory_fallback: object | None = None
        self._initialized = False

        self._initialize_memory()

    def _initialize_memory(self) -> None:
        if self._use_v3:
            try:
                from ..safla_memory import create_safla_memory

                self._memory_v3 = create_safla_memory(
                    persistence_enabled=self._persistence_enabled,
                    constitutional_hash=self.constitutional_hash,
                )
                self._initialized = True
                logger.info("MemoryCoordinator: SAFLA v3.0 initialized")
                return
            except ImportError:
                logger.info("SAFLA v3.0 not available, using fallback")
            except _MEMORY_COORDINATOR_ERRORS as e:
                logger.warning(f"SAFLA v3.0 init failed: {e}")

        try:
            from packages.enhanced_agent_bus.models import (
                OrchestratorConfig,  # type: ignore[attr-defined]
            )

            from ..memory import SAFLANeuralMemory

            config = OrchestratorConfig(constitutional_hash=self.constitutional_hash)
            self._memory_fallback = SAFLANeuralMemory(config)
            self._initialized = True
            logger.info("MemoryCoordinator: Fallback memory initialized")
        except _MEMORY_COORDINATOR_ERRORS as e:
            logger.error(f"Memory initialization failed: {e}")

    @property
    def is_v3_enabled(self) -> bool:
        return self._memory_v3 is not None

    async def store(
        self,
        key: str,
        value: JSONDict,
        tier: str = "ephemeral",
        ttl_seconds: int | None = None,
    ) -> bool:
        if not self._initialized:
            return False

        try:
            if self._memory_v3:
                await self._memory_v3.store(
                    tier=tier,
                    key=key,
                    value=value,
                    ttl_seconds=ttl_seconds,
                )
            elif self._memory_fallback:
                from ..memory import MemoryTier

                tier_map = {
                    "ephemeral": MemoryTier.EPHEMERAL,
                    "working": MemoryTier.WORKING,
                    "semantic": MemoryTier.SEMANTIC,
                    "persistent": MemoryTier.PERSISTENT,
                }
                await self._memory_fallback.store(
                    tier_map.get(tier, MemoryTier.EPHEMERAL),
                    key,
                    value,
                )
            return True
        except _MEMORY_COORDINATOR_ERRORS as e:
            logger.error(f"Memory store failed: {e}")
            return False

    async def retrieve(self, key: str) -> JSONDict | None:
        if not self._initialized:
            return None

        try:
            if self._memory_v3:
                return await self._memory_v3.retrieve(key)
            elif self._memory_fallback:
                return await self._memory_fallback.retrieve(key)
        except _MEMORY_COORDINATOR_ERRORS as e:
            logger.error(f"Memory retrieve failed: {e}")
        return None

    async def search(
        self,
        query: str,
        limit: int = 10,
        tier: str | None = None,
    ) -> list[JSONDict]:
        if not self._initialized:
            return []

        try:
            if self._memory_v3:
                return await self._memory_v3.search(query, limit=limit)  # type: ignore[no-any-return]
            elif self._memory_fallback:
                results = await self._memory_fallback.search(query, k=limit)
                return [r for r in results if r]
        except _MEMORY_COORDINATOR_ERRORS as e:
            logger.error(f"Memory search failed: {e}")
        return []

    def get_stats(self) -> JSONDict:
        stats: JSONDict = {
            "constitutional_hash": self.constitutional_hash,
            "initialized": self._initialized,
            "v3_enabled": self.is_v3_enabled,
            "persistence_enabled": self._persistence_enabled,
        }

        if self._memory_v3 and hasattr(self._memory_v3, "get_stats"):
            stats["v3_stats"] = self._memory_v3.get_stats()
        elif self._memory_fallback and hasattr(self._memory_fallback, "get_stats"):
            stats["fallback_stats"] = self._memory_fallback.get_stats()

        return stats
