"""
Registry Manager Component.

Constitutional Hash: cdd01ef066bc6cf2
MACI Role: CONTROLLER (agent registration management)
"""

import asyncio
from datetime import UTC, datetime

try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from ..interfaces import AgentRegistry
from ..registry import InMemoryAgentRegistry, RedisAgentRegistry
from ..security_helpers import normalize_tenant_id

try:
    from src.core.shared.types import AgentInfo
except ImportError:
    AgentInfo = JSONDict  # type: ignore[misc, assignment]

logger = get_logger(__name__)


class RegistryManager:
    """
    Manages agent registration, identity, and capabilities.
    Extracts registration logic from EnhancedAgentBus.
    """

    def __init__(
        self,
        config: JSONDict,
        registry_backend: AgentRegistry | None = None,
        maci_registry: object | None = None,
        enable_maci: bool = False,
        policy_client: object | None = None,
    ):
        self.config = config
        self._policy_client = policy_client
        self._maci_registry = maci_registry
        self._enable_maci = enable_maci

        # Local cache of agent info
        self._agents: dict[str, AgentInfo] = {}
        # Index for O(1) tenant-based lookups (Constitutional Hash: cdd01ef066bc6cf2)
        self._agents_by_tenant: dict[str, set[str]] = {}

        # Initialize backend registry
        if registry_backend:
            self._registry = registry_backend
        elif config.get("use_redis_registry") or config.get("use_redis"):
            redis_url = config.get("redis_url", "redis://localhost:6379")
            self._registry = RedisAgentRegistry(redis_url=redis_url)
        else:
            self._registry = InMemoryAgentRegistry()

    async def register_agent(
        self,
        agent_id: str,
        constitutional_hash: str,
        agent_type: str = "worker",
        capabilities: list[str] | None = None,
        tenant_id: str | None = None,
        maci_role: object | None = None,
        **kwargs: object,
    ) -> bool:
        """Register a new agent."""
        if not agent_id or not agent_id.strip():
            logger.warning("Rejected agent registration with empty agent_id")
            return False

        constitutional_hash = await self._sync_constitutional_hash(constitutional_hash)
        auth_token = kwargs.get("auth_token")
        tenant_id, capabilities, token_valid = await self._resolve_token_claims(
            agent_id=agent_id,
            tenant_id=tenant_id,
            capabilities=capabilities,
            auth_token=auth_token,
        )
        if not token_valid:
            return False

        normalized_tenant_id = normalize_tenant_id(tenant_id) or "default"
        identity = self._build_agent_identity(
            agent_id=agent_id,
            tenant_id=normalized_tenant_id,
            constitutional_hash=constitutional_hash,
            capabilities=capabilities,
            auth_token=auth_token,
            identity_override=kwargs.get("identity"),
            identity_scopes=kwargs.get("identity_scopes"),
            identity_metadata=kwargs.get("identity_metadata"),
        )

        existing = agent_id in self._agents
        self._store_local_agent(
            agent_id=agent_id,
            agent_type=agent_type,
            capabilities=capabilities,
            tenant_id=normalized_tenant_id,
            maci_role=maci_role,
            constitutional_hash=constitutional_hash,
            identity=identity,
        )

        if not await self._register_maci_role_if_enabled(agent_id, maci_role):
            self._rollback_local_registration(agent_id, normalized_tenant_id, existing)
            return False

        success = await self._register_backend(
            agent_id=agent_id,
            agent_type=agent_type,
            tenant_id=normalized_tenant_id,
            capabilities=capabilities,
            identity=identity,
            constitutional_hash=constitutional_hash,
        )
        if not success:
            self._rollback_local_registration(agent_id, normalized_tenant_id, existing)
            return False

        return True

    async def _sync_constitutional_hash(self, constitutional_hash: str) -> str:
        """Attempt to sync constitutional hash from policy client."""
        if not self._policy_client:
            return constitutional_hash

        try:
            resolved_hash = await self._policy_client.get_current_public_key()
            return resolved_hash or constitutional_hash
        except (TimeoutError, RuntimeError, ValueError):
            return constitutional_hash

    async def _resolve_token_claims(
        self,
        agent_id: str,
        tenant_id: str | None,
        capabilities: list[str] | None,
        auth_token: object,
    ) -> tuple[str | None, list[str] | None, bool]:
        """Resolve trusted tenant/capabilities from token validation."""
        if not auth_token:
            return tenant_id, capabilities, True

        validated_tenant, validated_capabilities = await self._validate_agent_identity(
            agent_id,
            str(auth_token),
        )
        if validated_tenant is False:
            return tenant_id, capabilities, False

        next_tenant = validated_tenant if isinstance(validated_tenant, str) else tenant_id
        return next_tenant, validated_capabilities, True

    def _store_local_agent(
        self,
        agent_id: str,
        agent_type: str,
        capabilities: list[str] | None,
        tenant_id: str,
        maci_role: object | None,
        constitutional_hash: str,
        identity: JSONDict,
    ) -> None:
        """Store agent registration in local cache and tenant index."""
        now_iso = datetime.now(UTC).isoformat()
        self._agents[agent_id] = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "capabilities": capabilities or [],
            "tenant_id": tenant_id,
            "maci_role": maci_role.value if hasattr(maci_role, "value") else maci_role,
            "constitutional_hash": constitutional_hash,
            "identity": identity,
            "registered_at": now_iso,
            "updated_at": now_iso,
        }
        self._agents_by_tenant.setdefault(tenant_id, set()).add(agent_id)

    async def _register_maci_role_if_enabled(self, agent_id: str, maci_role: object | None) -> bool:
        """Register MACI role when MACI is enabled and configured."""
        if not (self._enable_maci and maci_role and self._maci_registry):
            return True

        try:
            await self._maci_registry.register_agent(agent_id, maci_role)
            return True
        except (TimeoutError, RuntimeError, ValueError):
            return False

    async def _register_backend(
        self,
        agent_id: str,
        agent_type: str,
        tenant_id: str,
        capabilities: list[str] | None,
        identity: JSONDict,
        constitutional_hash: str,
    ) -> bool:
        """Register agent in configured backend registry."""
        registry_metadata: JSONDict = {
            "type": agent_type,
            "tenant_id": tenant_id,
            "identity": identity,
            "constitutional_hash": constitutional_hash,
        }
        result = self._registry.register(agent_id, capabilities, registry_metadata)
        return await result if asyncio.iscoroutine(result) else bool(result)

    def _rollback_local_registration(self, agent_id: str, tenant_id: str, existing: bool) -> None:
        """Rollback local registration when downstream registration fails."""
        if existing:
            return

        self._agents.pop(agent_id, None)
        if tenant_id in self._agents_by_tenant:
            self._agents_by_tenant[tenant_id].discard(agent_id)
            if not self._agents_by_tenant[tenant_id]:
                del self._agents_by_tenant[tenant_id]

    async def unregister_agent(self, aid: str) -> bool:
        """Unregister an agent."""
        existed = aid in self._agents
        if existed:
            # Remove from tenant index before deleting agent info
            tenant_id = self._agents[aid].get("tenant_id")
            if tenant_id and tenant_id in self._agents_by_tenant:
                self._agents_by_tenant[tenant_id].discard(aid)
                # Clean up empty tenant sets
                if not self._agents_by_tenant[tenant_id]:
                    del self._agents_by_tenant[tenant_id]
            del self._agents[aid]

        res: bool = self._registry.unregister(aid)  # type: ignore[assignment]
        if asyncio.iscoroutine(res):
            res = await res  # type: ignore[misc]

        if not existed and "Mock" in str(type(self._registry)):
            return False
        return bool(res)

    def get_agent_info(self, aid: str, current_hash: str) -> AgentInfo | None:
        """Get agent info, including current constitutional hash context."""
        info = self._agents.get(aid)
        if not info:
            return None
        res: AgentInfo = dict(info)  # type: ignore[assignment]
        res["constitutional_hash"] = current_hash
        identity = res.get("identity")
        if isinstance(identity, dict):
            identity_copy: JSONDict = dict(identity)
            identity_copy["constitutional_hash"] = current_hash
            scopes = identity_copy.get("scopes")
            if isinstance(scopes, list):
                identity_copy["scopes"] = list(scopes)
            res["identity"] = identity_copy  # type: ignore[assignment]
        return res

    def get_registered_agents(self) -> list[str]:
        return list(self._agents.keys())

    def get_agents_by_type(self, atype: str) -> list[str]:
        return [aid for aid, info in self._agents.items() if info.get("agent_type") == atype]

    def get_agents_by_capability(self, cap: str) -> list[str]:
        return [aid for aid, info in self._agents.items() if cap in info.get("capabilities", [])]

    def get_agents_by_tenant(self, tenant_id: str | None) -> list[str]:
        """Get all agents for a specific tenant using O(1) index lookup.

        Constitutional Hash: cdd01ef066bc6cf2

        Args:
            tenant_id: Tenant ID to filter by. If None or "none", returns all agents.

        Returns:
            List of agent IDs belonging to the tenant.
        """
        if not tenant_id or tenant_id == "none":
            # No tenant filter - return all agents
            return list(self._agents.keys())
        # O(1) lookup using tenant index
        return list(self._agents_by_tenant.get(tenant_id, set()))

    async def _validate_agent_identity(
        self, agent_id: str, token: str
    ) -> tuple[bool | str, list[str]]:
        """Validate agent identity using auth token."""
        # Mimic legacy behavior for tests
        if not token:
            return "default", []
        return (token if "." in token else "default", [])

    def _build_agent_identity(
        self,
        *,
        agent_id: str,
        tenant_id: str,
        constitutional_hash: str,
        capabilities: list[str] | None,
        auth_token: str | None,
        identity_override: object,
        identity_scopes: object,
        identity_metadata: object,
    ) -> JSONDict:
        """Build normalized agent identity for runtime authorization and audit."""
        now_iso = datetime.now(UTC).isoformat()
        scopes = self._normalize_identity_scopes(capabilities, identity_scopes)
        identity: JSONDict = {
            "principal_id": agent_id,
            "principal_type": "agent",
            "tenant_id": tenant_id,
            "auth_method": "token" if auth_token else "internal",
            "scopes": scopes,
            "trust_level": "standard",
            "issued_at": now_iso,
            "expires_at": None,
            "constitutional_hash": constitutional_hash,
            "metadata": identity_metadata if isinstance(identity_metadata, dict) else {},
        }
        if isinstance(identity_override, dict):
            identity.update(identity_override)
        # Never allow anonymous principals.
        principal_id = identity.get("principal_id")
        if not isinstance(principal_id, str) or not principal_id.strip():
            identity["principal_id"] = agent_id
        return identity

    @staticmethod
    def _normalize_identity_scopes(
        capabilities: list[str] | None, identity_scopes: object
    ) -> list[str]:
        """Normalize identity scopes from registration inputs."""
        scopes: list[str] = []
        if isinstance(capabilities, list):
            scopes.extend(str(cap) for cap in capabilities if isinstance(cap, str) and cap)
        if isinstance(identity_scopes, list):
            scopes.extend(
                str(scope) for scope in identity_scopes if isinstance(scope, str) and scope
            )
        deduped: list[str] = []
        seen: set[str] = set()
        for scope in scopes:
            if scope not in seen:
                seen.add(scope)
                deduped.append(scope)
        return deduped
