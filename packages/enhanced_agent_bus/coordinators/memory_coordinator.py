"""
Memory Coordinator - Manages SAFLA neural memory operations.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import importlib
import sys

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
_MODULE = sys.modules[__name__]
sys.modules.setdefault("enhanced_agent_bus.coordinators.memory_coordinator", _MODULE)
sys.modules.setdefault("packages.enhanced_agent_bus.coordinators.memory_coordinator", _MODULE)
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
            OrchestratorConfig = _resolve_orchestrator_config()
            SAFLANeuralMemory = _resolve_fallback_memory_class()
            config = OrchestratorConfig(constitutional_hash=self.constitutional_hash)
            self._memory_fallback = SAFLANeuralMemory(config)
            self._initialized = True
            logger.info("MemoryCoordinator: Fallback memory initialized")
        except ImportError as e:
            logger.error(f"Memory initialization failed: {e}")
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
                MemoryTier = _resolve_memory_tier()

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
        except ImportError as e:
            logger.error(f"Memory store failed: {e}")
            return False
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
        except ImportError as e:
            logger.error(f"Memory retrieve failed: {e}")
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
        except ImportError as e:
            logger.error(f"Memory search failed: {e}")
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


def _resolve_memory_tier() -> object:
    for module_name in (
        "enhanced_agent_bus.memory",
        "packages.enhanced_agent_bus.memory",
    ):
        module = sys.modules.get(module_name)
        if module is None:
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                continue
        memory_tier = getattr(module, "MemoryTier", None)
        if memory_tier is not None:
            return memory_tier

    try:
        from .. import memory as memory_module

        memory_tier = getattr(memory_module, "MemoryTier", None)
        if memory_tier is not None:
            return memory_tier
    except ImportError:
        pass

    from .. import meta_orchestrator as memory_module

    return memory_module.MemoryTier


def _resolve_orchestrator_config() -> object:
    for module_name in (
        "enhanced_agent_bus.models",
        "packages.enhanced_agent_bus.models",
        "enhanced_agent_bus.meta_orchestrator.config",
        "packages.enhanced_agent_bus.meta_orchestrator.config",
    ):
        module = sys.modules.get(module_name)
        if module is None:
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                continue
        orchestrator_config = getattr(module, "OrchestratorConfig", None)
        if orchestrator_config is not None:
            return orchestrator_config

    from ..meta_orchestrator.config import OrchestratorConfig

    return OrchestratorConfig


def _resolve_fallback_memory_class() -> object:
    for module_name in (
        "enhanced_agent_bus.memory",
        "packages.enhanced_agent_bus.memory",
        "enhanced_agent_bus.meta_orchestrator.memory",
        "packages.enhanced_agent_bus.meta_orchestrator.memory",
    ):
        module = sys.modules.get(module_name)
        if module is None:
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                continue
        memory_class = getattr(module, "SAFLANeuralMemory", None)
        if memory_class is not None:
            return memory_class

    from ..meta_orchestrator.memory import SAFLANeuralMemory

    return SAFLANeuralMemory
