"""
MACI Role Mapping Service for Enterprise SSO Integration.
Constitutional Hash: 608508a9bd224290

This module provides role mapping from IdP sources (LDAP groups, SAML attributes,
OAuth scopes) to MACI roles with priority-based conflict resolution and caching.

Phase 10 Task 6: MACI Role Mapping

Features:
- LDAP group → MACI role mapping
- SAML attribute → MACI role mapping
- OAuth scope → MACI role mapping
- Priority-based conflict resolution
- Role mapping cache with configurable TTL
- CRUD operations for role mappings
"""

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    from ..maci_enforcement import MACIRole
except ImportError:
    from maci_enforcement import MACIRole  # type: ignore[no-redef]

logger = get_logger(__name__)
# Constitutional Hash for all MACI operations
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"


class RoleMappingSource(Enum):
    """Source type for role mapping."""

    LDAP_GROUP = "ldap_group"
    SAML_ATTRIBUTE = "saml_attribute"
    OAUTH_SCOPE = "oauth_scope"
    CUSTOM = "custom"


@dataclass
class RoleMapping:
    """A mapping from an identity source to a MACI role.

    Constitutional Hash: 608508a9bd224290
    """

    id: str
    source_type: RoleMappingSource
    source_value: str  # e.g., "CN=Admins,OU=Groups,DC=example,DC=com" or "admin"
    maci_role: MACIRole
    priority: int = 0  # Higher priority wins in conflicts
    tenant_id: str | None = None
    conditions: JSONDict = field(default_factory=dict)
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def matches(self, source_values: list[str], attributes: JSONDict | None = None) -> bool:
        """Check if this mapping matches the provided source values and attributes."""
        if not self.enabled:
            return False

        if self.source_value not in source_values:
            return False

        # Check additional conditions
        if self.conditions and attributes:
            for key, expected_value in self.conditions.items():
                if isinstance(expected_value, list):
                    if attributes.get(key) not in expected_value:
                        return False
                elif attributes.get(key) != expected_value:
                    return False

        return True

    def to_dict(self) -> JSONDict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "source_type": self.source_type.value,
            "source_value": self.source_value,
            "maci_role": self.maci_role.value,
            "priority": self.priority,
            "tenant_id": self.tenant_id,
            "conditions": self.conditions,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "RoleMapping":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            source_type=RoleMappingSource(data["source_type"]),
            source_value=data["source_value"],
            maci_role=MACIRole(data["maci_role"]),
            priority=data.get("priority", 0),
            tenant_id=data.get("tenant_id"),
            conditions=data.get("conditions", {}),
            enabled=data.get("enabled", True),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if "created_at" in data
                else datetime.now(UTC)
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if "updated_at" in data
                else datetime.now(UTC)
            ),
        )


@dataclass
class RoleMappingResult:
    """Result of role mapping resolution.

    Constitutional Hash: 608508a9bd224290
    """

    roles: list[MACIRole]
    matched_mappings: list[RoleMapping]
    primary_role: MACIRole | None = None
    resolution_time_ms: float = 0.0
    from_cache: bool = False
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Serialize to dictionary."""
        return {
            "roles": [r.value for r in self.roles],
            "matched_mappings": [m.to_dict() for m in self.matched_mappings],
            "primary_role": self.primary_role.value if self.primary_role else None,
            "resolution_time_ms": self.resolution_time_ms,
            "from_cache": self.from_cache,
            "constitutional_hash": self.constitutional_hash,
        }


class RoleMappingCache:
    """In-memory cache for role mapping results with TTL.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, ttl_seconds: int = 300):  # Default 5 minute TTL
        """Initialize cache with TTL."""
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[RoleMappingResult, float]] = {}
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
        }

    def _make_key(
        self,
        tenant_id: str,
        source_type: RoleMappingSource,
        source_values: list[str],
        attributes: JSONDict | None = None,
    ) -> str:
        """Create a cache key from parameters including attributes."""
        sorted_values = sorted(source_values)
        base_key = f"{tenant_id}:{source_type.value}:{','.join(sorted_values)}"

        # Include attributes hash in key if provided
        if attributes:
            # Create deterministic hash from sorted attributes
            sorted_attrs = sorted((k, str(v)) for k, v in attributes.items())
            attrs_str = ";".join(f"{k}={v}" for k, v in sorted_attrs)
            return f"{base_key}:{attrs_str}"

        return base_key

    def get(
        self,
        tenant_id: str,
        source_type: RoleMappingSource,
        source_values: list[str],
        attributes: JSONDict | None = None,
    ) -> RoleMappingResult | None:
        """Get cached result if valid."""
        key = self._make_key(tenant_id, source_type, source_values, attributes)

        if key in self._cache:
            result, timestamp = self._cache[key]
            if time.time() - timestamp < self.ttl_seconds:
                self._stats["hits"] += 1
                # Return copy with from_cache flag set
                return RoleMappingResult(
                    roles=result.roles,
                    matched_mappings=result.matched_mappings,
                    primary_role=result.primary_role,
                    resolution_time_ms=result.resolution_time_ms,
                    from_cache=True,
                    constitutional_hash=result.constitutional_hash,
                )
            else:
                # Expired entry
                del self._cache[key]
                self._stats["evictions"] += 1

        self._stats["misses"] += 1
        return None

    def set(
        self,
        tenant_id: str,
        source_type: RoleMappingSource,
        source_values: list[str],
        result: RoleMappingResult,
        attributes: JSONDict | None = None,
    ) -> None:
        """Cache a result."""
        key = self._make_key(tenant_id, source_type, source_values, attributes)
        self._cache[key] = (result, time.time())

    def invalidate(
        self, tenant_id: str | None = None, source_type: RoleMappingSource | None = None
    ) -> int:
        """Invalidate cache entries matching criteria."""
        if tenant_id is None and source_type is None:
            count = len(self._cache)
            self._cache.clear()
            return count

        keys_to_delete = []
        for key in self._cache:
            parts = key.split(":", 2)
            if len(parts) >= 2:
                key_tenant = parts[0]
                key_source = parts[1]

                if tenant_id and key_tenant != tenant_id:
                    continue
                if source_type and key_source != source_type.value:
                    continue

                keys_to_delete.append(key)

        for key in keys_to_delete:
            del self._cache[key]

        return len(keys_to_delete)

    def get_stats(self) -> JSONDict:
        """Get cache statistics."""
        return {
            **self._stats,
            "size": len(self._cache),
            "ttl_seconds": self.ttl_seconds,
        }

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()


class RoleMappingService:
    """Service for managing and resolving MACI role mappings.

    Constitutional Hash: 608508a9bd224290

    Provides:
    - CRUD operations for role mappings
    - Priority-based role resolution
    - Support for LDAP groups, SAML attributes, and OAuth scopes
    - Caching with configurable TTL
    """

    def __init__(
        self, cache_ttl_seconds: int = 300, constitutional_hash: str = CONSTITUTIONAL_HASH
    ):
        """Initialize the role mapping service."""
        if constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(
                f"Invalid constitutional hash. Expected {CONSTITUTIONAL_HASH}, "
                f"got {constitutional_hash}"
            )

        self._mappings: dict[str, RoleMapping] = {}
        self._cache = RoleMappingCache(ttl_seconds=cache_ttl_seconds)
        self._constitutional_hash = constitutional_hash
        self._next_id = 1

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    def create_mapping(
        self,
        source_type: RoleMappingSource,
        source_value: str,
        maci_role: MACIRole,
        priority: int = 0,
        tenant_id: str | None = None,
        conditions: JSONDict | None = None,
        mapping_id: str | None = None,
    ) -> RoleMapping:
        """Create a new role mapping."""
        if mapping_id is None:
            mapping_id = f"mapping-{self._next_id}"
            self._next_id += 1

        if mapping_id in self._mappings:
            raise ValueError(f"Mapping with ID {mapping_id} already exists")

        mapping = RoleMapping(
            id=mapping_id,
            source_type=source_type,
            source_value=source_value,
            maci_role=maci_role,
            priority=priority,
            tenant_id=tenant_id,
            conditions=conditions or {},
        )

        self._mappings[mapping_id] = mapping

        # Invalidate cache for this tenant/source type
        self._cache.invalidate(tenant_id=tenant_id, source_type=source_type)

        logger.info(
            f"Created role mapping: {source_type.value}:{source_value} -> "
            f"{maci_role.value} (priority={priority})"
        )

        return mapping

    def get_mapping(self, mapping_id: str) -> RoleMapping | None:
        """Get a role mapping by ID."""
        return self._mappings.get(mapping_id)

    def list_mappings(
        self,
        tenant_id: str | None = None,
        source_type: RoleMappingSource | None = None,
        maci_role: MACIRole | None = None,
        enabled_only: bool = True,
    ) -> list[RoleMapping]:
        """List role mappings with optional filters."""
        mappings = list(self._mappings.values())

        if tenant_id is not None:
            mappings = [m for m in mappings if m.tenant_id == tenant_id]

        if source_type is not None:
            mappings = [m for m in mappings if m.source_type == source_type]

        if maci_role is not None:
            mappings = [m for m in mappings if m.maci_role == maci_role]

        if enabled_only:
            mappings = [m for m in mappings if m.enabled]

        return sorted(mappings, key=lambda m: (-m.priority, m.source_value))

    def update_mapping(self, mapping_id: str, **updates) -> RoleMapping | None:
        """Update an existing role mapping."""
        mapping = self._mappings.get(mapping_id)
        if not mapping:
            return None

        # Update allowed fields
        allowed_fields = {"source_value", "maci_role", "priority", "conditions", "enabled"}

        for key, value in updates.items():
            if key in allowed_fields:
                setattr(mapping, key, value)

        mapping.updated_at = datetime.now(UTC)

        # Invalidate cache
        self._cache.invalidate(tenant_id=mapping.tenant_id, source_type=mapping.source_type)

        return mapping

    def delete_mapping(self, mapping_id: str) -> bool:
        """Delete a role mapping."""
        mapping = self._mappings.pop(mapping_id, None)
        if mapping:
            self._cache.invalidate(tenant_id=mapping.tenant_id, source_type=mapping.source_type)
            return True
        return False

    # =========================================================================
    # Role Resolution
    # =========================================================================

    def resolve_roles(
        self,
        source_type: RoleMappingSource,
        source_values: list[str],
        tenant_id: str | None = None,
        attributes: JSONDict | None = None,
        use_cache: bool = True,
    ) -> RoleMappingResult:
        """Resolve MACI roles from source values.

        Uses priority-based conflict resolution: higher priority mappings
        take precedence. The primary_role is the highest priority matched role.
        """
        start_time = time.time()

        # Check cache first
        if use_cache:
            cached_result = self._get_cached_result(
                tenant_id, source_type, source_values, attributes
            )
            if cached_result:
                return cached_result

        # Find and filter matching mappings
        matched_mappings = self._find_matching_mappings(
            source_type, source_values, tenant_id, attributes
        )

        # Extract unique roles with priority resolution
        roles, primary_role = self._resolve_roles_with_priority(matched_mappings)

        # Build and cache result
        result = self._build_resolution_result(roles, matched_mappings, primary_role, start_time)

        if use_cache:
            self._cache_result(tenant_id, source_type, source_values, attributes, result)

        return result

    def _get_cached_result(
        self,
        tenant_id: str | None,
        source_type: RoleMappingSource,
        source_values: list[str],
        attributes: JSONDict | None,
    ) -> RoleMappingResult | None:
        """Get cached role resolution result."""
        return self._cache.get(
            tenant_id=tenant_id or "",
            source_type=source_type,
            source_values=source_values,
            attributes=attributes,
        )

    def _find_matching_mappings(
        self,
        source_type: RoleMappingSource,
        source_values: list[str],
        tenant_id: str | None,
        attributes: JSONDict | None,
    ) -> list[RoleMapping]:
        """Find all mappings that match the given criteria."""
        matched_mappings: list[RoleMapping] = []

        for mapping in self._mappings.values():
            if self._mapping_matches_criteria(
                mapping, source_type, source_values, tenant_id, attributes
            ):
                matched_mappings.append(mapping)

        # Sort by priority (descending) for deterministic resolution
        matched_mappings.sort(key=lambda m: -m.priority)
        return matched_mappings

    def _mapping_matches_criteria(
        self,
        mapping: RoleMapping,
        source_type: RoleMappingSource,
        source_values: list[str],
        tenant_id: str | None,
        attributes: JSONDict | None,
    ) -> bool:
        """Check if a mapping matches the resolution criteria."""
        # Filter by tenant
        if tenant_id is not None and mapping.tenant_id != tenant_id:
            if mapping.tenant_id is not None:  # Skip non-global mappings
                return False

        # Filter by source type
        if mapping.source_type != source_type:
            return False

        # Check if mapping matches source values and attributes
        return mapping.matches(source_values, attributes)

    def _resolve_roles_with_priority(
        self, matched_mappings: list[RoleMapping]
    ) -> tuple[list[MACIRole], MACIRole | None]:
        """Extract unique roles maintaining priority order."""
        seen_roles: set[MACIRole] = set()
        roles: list[MACIRole] = []

        for mapping in matched_mappings:
            if mapping.maci_role not in seen_roles:
                seen_roles.add(mapping.maci_role)
                roles.append(mapping.maci_role)

        primary_role = roles[0] if roles else None
        return roles, primary_role

    def _build_resolution_result(
        self,
        roles: list[MACIRole],
        matched_mappings: list[RoleMapping],
        primary_role: MACIRole | None,
        start_time: float,
    ) -> RoleMappingResult:
        """Build the role resolution result."""
        resolution_time = (time.time() - start_time) * 1000

        return RoleMappingResult(
            roles=roles,
            matched_mappings=matched_mappings,
            primary_role=primary_role,
            resolution_time_ms=resolution_time,
            from_cache=False,
            constitutional_hash=self._constitutional_hash,
        )

    def _cache_result(
        self,
        tenant_id: str | None,
        source_type: RoleMappingSource,
        source_values: list[str],
        attributes: JSONDict | None,
        result: RoleMappingResult,
    ) -> None:
        """Cache the role resolution result."""
        self._cache.set(
            tenant_id=tenant_id or "",
            source_type=source_type,
            source_values=source_values,
            result=result,
            attributes=attributes,
        )

    def resolve_from_ldap_groups(
        self,
        groups: list[str],
        tenant_id: str | None = None,
        attributes: JSONDict | None = None,
        use_cache: bool = True,
    ) -> RoleMappingResult:
        """Resolve MACI roles from LDAP groups."""
        return self.resolve_roles(
            source_type=RoleMappingSource.LDAP_GROUP,
            source_values=groups,
            tenant_id=tenant_id,
            attributes=attributes,
            use_cache=use_cache,
        )

    def resolve_from_saml_attributes(
        self,
        groups: list[str],
        tenant_id: str | None = None,
        attributes: JSONDict | None = None,
        use_cache: bool = True,
    ) -> RoleMappingResult:
        """Resolve MACI roles from SAML groups/attributes."""
        return self.resolve_roles(
            source_type=RoleMappingSource.SAML_ATTRIBUTE,
            source_values=groups,
            tenant_id=tenant_id,
            attributes=attributes,
            use_cache=use_cache,
        )

    def resolve_from_oauth_scopes(
        self,
        scopes: list[str],
        tenant_id: str | None = None,
        attributes: JSONDict | None = None,
        use_cache: bool = True,
    ) -> RoleMappingResult:
        """Resolve MACI roles from OAuth scopes."""
        return self.resolve_roles(
            source_type=RoleMappingSource.OAUTH_SCOPE,
            source_values=scopes,
            tenant_id=tenant_id,
            attributes=attributes,
            use_cache=use_cache,
        )

    # =========================================================================
    # Utilities
    # =========================================================================

    def get_cache_stats(self) -> JSONDict:
        """Get cache statistics."""
        return self._cache.get_stats()

    def invalidate_cache(
        self, tenant_id: str | None = None, source_type: RoleMappingSource | None = None
    ) -> int:
        """Invalidate cache entries."""
        return self._cache.invalidate(tenant_id=tenant_id, source_type=source_type)

    def clear_cache(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()

    def to_dict(self) -> JSONDict:
        """Serialize service state to dictionary."""
        return {
            "mappings": [m.to_dict() for m in self._mappings.values()],
            "cache_stats": self._cache.get_stats(),
            "constitutional_hash": self._constitutional_hash,
        }

    @classmethod
    def from_dict(cls, data: JSONDict, cache_ttl_seconds: int = 300) -> "RoleMappingService":
        """Deserialize service state from dictionary."""
        service = cls(cache_ttl_seconds=cache_ttl_seconds)

        for mapping_data in data.get("mappings", []):
            mapping = RoleMapping.from_dict(mapping_data)
            service._mappings[mapping.id] = mapping
            service._next_id = max(service._next_id, int(mapping.id.split("-")[-1]) + 1)

        return service


__all__ = [
    "CONSTITUTIONAL_HASH",
    "RoleMapping",
    "RoleMappingCache",
    "RoleMappingResult",
    "RoleMappingService",
    "RoleMappingSource",
]
