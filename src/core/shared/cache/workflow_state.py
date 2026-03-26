"""
ACGS-2 Workflow State Cache
Constitutional Hash: 608508a9bd224290

Provides a Redis-backed caching layer for active workflow state,
ensuring fast access to workflow context and step data while
running across distributed nodes.
"""

import json

from src.core.shared.cache.manager import TieredCacheManager
from src.core.shared.cache.models import CacheTier, TieredCacheConfig
from src.core.shared.types import JSONDict


class WorkflowStateCache:
    """Caching layer for durable workflow execution.

    Uses TieredCacheManager to provide:
    - L1 Cache: In-memory for extremely fast access to current workflow state on the active node
    - L2 Cache: Redis for distributed access and short-term resilience
    - L3 Cache: Disabled (fallback to PostgreSQL persistence layer)
    """

    def __init__(self) -> None:
        # High promotion threshold so we only keep extremely active workflows in L1
        # Short L1 TTL so we don't read stale state from another node's updates
        # L2 TTL set to 2 hours (assumes most workflows complete within this time)
        config = TieredCacheConfig(
            l1_maxsize=500,
            l1_ttl=5,  # 5 seconds L1 TTL to avoid stale distributed state
            l2_ttl=7200,  # 2 hours L2 TTL for active workflow state
            l3_enabled=False,  # Persistence layer (PostgreSQL) handles L3
            serialize=True,
            promotion_threshold=5,
        )

        self.cache_manager = TieredCacheManager(
            config=config,
            name="workflow_state",
        )

    async def initialize(self) -> bool:
        """Initialize the Redis connection for workflow cache."""
        return await self.cache_manager.initialize()

    async def close(self) -> None:
        """Close the Redis connection."""
        await self.cache_manager.close()

    def _get_workflow_key(self, workflow_id: str) -> str:
        """Generate a consistent cache key for a workflow instance."""
        return f"workflow:state:{workflow_id}"

    def _get_step_key(self, workflow_id: str, step_name: str) -> str:
        """Generate a consistent cache key for a workflow step."""
        return f"workflow:step:{workflow_id}:{step_name}"

    async def get_workflow_state(self, workflow_id: str) -> JSONDict | None:
        """Retrieve active workflow state from cache."""
        key = self._get_workflow_key(workflow_id)
        result = await self.cache_manager.get_async(key)
        if result and isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                pass
        elif isinstance(result, dict):
            return result
        return None

    async def set_workflow_state(
        self, workflow_id: str, state_data: JSONDict, ttl: int | None = None
    ) -> None:
        """Store active workflow state in cache."""
        key = self._get_workflow_key(workflow_id)
        # Store in Redis (L2) and optionally L1
        await self.cache_manager.set(key, state_data, ttl=ttl, tier=CacheTier.L2)

    async def invalidate_workflow_state(self, workflow_id: str) -> bool:
        """Remove workflow state from cache (e.g. upon completion)."""
        key = self._get_workflow_key(workflow_id)
        return await self.cache_manager.delete(key)

    async def get_step_result(self, workflow_id: str, step_name: str) -> JSONDict | None:
        """Retrieve a specific step's result from cache."""
        key = self._get_step_key(workflow_id, step_name)
        result = await self.cache_manager.get_async(key)
        if result and isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                pass
        elif isinstance(result, dict):
            return result
        return None

    async def set_step_result(
        self, workflow_id: str, step_name: str, result_data: JSONDict, ttl: int | None = None
    ) -> None:
        """Store a step's result in cache."""
        key = self._get_step_key(workflow_id, step_name)
        await self.cache_manager.set(key, result_data, ttl=ttl, tier=CacheTier.L2)


# Global singleton instance
workflow_cache = WorkflowStateCache()
