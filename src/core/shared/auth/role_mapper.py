"""
ACGS-2 Role Mapping Service for IdP Group Translation
Constitutional Hash: cdd01ef066bc6cf2

Provides role mapping functionality to translate identity provider (IdP) groups
to internal ACGS-2 roles during SSO authentication flows. Supports both
database-backed mappings (using SSORoleMapping model) and in-memory defaults.

Usage:
    from src.core.shared.auth.role_mapper import RoleMapper

    # Create role mapper with default settings
    role_mapper = RoleMapper()

    # Map IdP groups to ACGS-2 roles
    roles = role_mapper.map_groups(
        groups=["Engineering", "Administrators"],
        provider_name="okta"
    )

    # Map with database session for persistent mappings
    roles = await role_mapper.map_groups_async(
        groups=["Engineering"],
        provider_id="sso-provider-uuid",
        session=db_session,
    )

    # Get or create the singleton instance
    mapper = get_role_mapper()
"""

from dataclasses import dataclass, field

from src.core.shared.errors.exceptions import ACGSBaseError
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)
# Constitutional hash constant

from src.core.shared.constants import CONSTITUTIONAL_HASH

# Default role mappings for common IdP group patterns
# These are used when no database mappings are configured
DEFAULT_ROLE_MAPPINGS: dict[str, str] = {
    # Admin groups
    "admins": "admin",
    "administrators": "admin",
    "admin": "admin",
    "super-admins": "admin",
    "superadmins": "admin",
    # Developer groups
    "engineering": "developer",
    "engineers": "developer",
    "developers": "developer",
    "development": "developer",
    "dev": "developer",
    # Viewer groups
    "viewers": "viewer",
    "readonly": "viewer",
    "read-only": "viewer",
    "guests": "viewer",
    # Analyst groups
    "analysts": "analyst",
    "data-analysts": "analyst",
    "analytics": "analyst",
    # Operator groups
    "operators": "operator",
    "operations": "operator",
    "ops": "operator",
}


@dataclass
class MappingResult:
    """Result of a role mapping operation.

    Attributes:
        roles: List of mapped ACGS-2 roles.
        unmapped_groups: Groups that did not match any mapping.
        source: Source of the mappings ("database" or "default").
    """

    roles: list[str]
    unmapped_groups: list[str] = field(default_factory=list)
    source: str = "default"


class RoleMappingError(ACGSBaseError):
    """Base exception for role mapping errors (Q-H4 migration)."""

    http_status_code = 400
    error_code = "ROLE_MAPPING_ERROR"


class ProviderNotFoundError(RoleMappingError):
    """SSO provider not found in database (Q-H4 migration)."""

    http_status_code = 404
    error_code = "PROVIDER_NOT_FOUND"


class RoleMapper:
    """Role mapping service for IdP group to ACGS-2 role translation.

    Translates identity provider group memberships to internal ACGS-2 roles.
    Supports both database-backed mappings (via SSORoleMapping model) and
    in-memory default mappings for testing or initial setup.

    Features:
    - Database-backed mappings with priority-based conflict resolution
    - Default mappings for common group naming patterns
    - Case-insensitive group matching
    - Provider-specific or global default mappings
    - Fallback role assignment when no mappings match

    Example:
        mapper = RoleMapper()

        # Simple synchronous mapping (uses defaults)
        roles = mapper.map_groups(["admins", "engineering"], "okta")
        logger.debug(roles)  # ["admin", "developer"]

        # Async mapping with database session
        roles = await mapper.map_groups_async(
            groups=["Engineering", "Admin"],
            provider_id="provider-uuid",
            session=db_session,
        )

    Attributes:
        default_mappings: Dictionary of default group->role mappings.
        fallback_role: Role to assign when no mappings match (None = no fallback).
        case_sensitive: Whether group matching is case-sensitive.
    """

    def __init__(
        self,
        default_mappings: dict[str, str] | None = None,
        fallback_role: str | None = None,
        case_sensitive: bool = False,
    ) -> None:
        """Initialize the role mapper.

        Args:
            default_mappings: Override default group->role mappings.
                              If None, uses DEFAULT_ROLE_MAPPINGS.
            fallback_role: Role to assign when no mappings match.
                           If None, unmatched groups are ignored.
            case_sensitive: Whether to perform case-sensitive group matching.
        """
        self.default_mappings = (
            default_mappings if default_mappings is not None else DEFAULT_ROLE_MAPPINGS.copy()
        )
        self.fallback_role = fallback_role
        self.case_sensitive = case_sensitive

        logger.debug(
            "RoleMapper initialized",
            extra={
                "default_mapping_count": len(self.default_mappings),
                "fallback_role": fallback_role,
                "case_sensitive": case_sensitive,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

    def _normalize_group(self, group: str) -> str:
        """Normalize a group name for matching.

        Args:
            group: Group name to normalize.

        Returns:
            Normalized group name (lowercase if case-insensitive).
        """
        if self.case_sensitive:
            return group.strip()
        return group.strip().lower()

    def _match_default_mapping(self, group: str) -> str | None:
        """Match a group against default mappings.

        Args:
            group: Group name to match.

        Returns:
            Mapped role if found, None otherwise.
        """
        normalized = self._normalize_group(group)

        for mapping_group, role in self.default_mappings.items():
            if self.case_sensitive:
                if mapping_group == normalized:
                    return role
            else:
                if mapping_group.lower() == normalized:
                    return role

        return None

    def map_groups(
        self,
        groups: list[str],
        provider_name: str | None = None,
    ) -> list[str]:
        """Map IdP groups to ACGS-2 roles using default mappings.

        This is the synchronous method for mapping groups using only
        the in-memory default mappings. For database-backed mappings,
        use map_groups_async().

        Args:
            groups: List of IdP group names to map.
            provider_name: SSO provider name (for logging only in sync mode).

        Returns:
            List of unique mapped ACGS-2 roles, sorted alphabetically.

        Example:
            mapper = RoleMapper()
            roles = mapper.map_groups(["admins", "engineering"], "okta")
            # Returns: ["admin", "developer"]
        """
        if not groups:
            logger.debug(
                "No groups provided for mapping",
                extra={
                    "provider_name": provider_name,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )
            return []

        mapped_roles: set[str] = set()
        unmapped: list[str] = []

        for group in groups:
            role = self._match_default_mapping(group)
            if role:
                mapped_roles.add(role)
            else:
                unmapped.append(group)

        # Apply fallback role if configured and some groups went unmapped
        if unmapped and self.fallback_role:
            mapped_roles.add(self.fallback_role)
            logger.debug(
                "Applied fallback role for unmapped groups",
                extra={
                    "fallback_role": self.fallback_role,
                    "unmapped_groups": unmapped,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

        result = sorted(mapped_roles)

        logger.info(
            "Role mapping completed",
            extra={
                "input_groups": groups,
                "mapped_roles": result,
                "unmapped_groups": unmapped,
                "provider_name": provider_name,
                "source": "default",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

        return result

    async def map_groups_async(
        self,
        groups: list[str],
        provider_id: str | None = None,
        session: object | None = None,
    ) -> MappingResult:
        """Map IdP groups to ACGS-2 roles with database lookup.

        Looks up mappings in the database first (if provider_id and session
        are provided), then falls back to default mappings for any unmatched
        groups.

        Args:
            groups: List of IdP group names to map.
            provider_id: UUID of the SSO provider for database lookup.
            session: SQLAlchemy AsyncSession for database queries.

        Returns:
            MappingResult with mapped roles, unmapped groups, and source.

        Example:
            result = await mapper.map_groups_async(
                groups=["Engineering", "Admin"],
                provider_id="provider-uuid",
                session=db_session,
            )
            logger.debug(result.roles)  # ["admin", "developer"]
            logger.debug(result.unmapped_groups)  # []
            logger.debug(result.source)  # "database"
        """
        if not groups:
            return MappingResult(roles=[], unmapped_groups=[], source="none")

        mapped_roles: set[str] = set()
        unmapped: list[str] = []
        source = "default"

        # Try database lookup if session and provider_id provided
        db_mappings: dict[str, tuple[str, int]] = {}  # group -> (role, priority)

        if session is not None and provider_id:
            try:
                db_mappings = await self._fetch_provider_mappings(provider_id, session)
                if db_mappings:
                    source = "database"
            except Exception as e:
                logger.warning(
                    "Failed to fetch database mappings, using defaults",
                    extra={
                        "provider_id": provider_id,
                        "error": str(e),
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                    },
                )

        # Map each group
        for group in groups:
            normalized = self._normalize_group(group)

            # Check database mappings first
            if db_mappings:
                for db_group, (role, _priority) in db_mappings.items():
                    db_normalized = db_group if self.case_sensitive else db_group.lower()
                    if db_normalized == normalized:
                        mapped_roles.add(role)
                        break
                else:
                    # No database match, try defaults
                    role = self._match_default_mapping(group)
                    if role:
                        mapped_roles.add(role)
                    else:
                        unmapped.append(group)
            else:
                # No database mappings, use defaults only
                role = self._match_default_mapping(group)
                if role:
                    mapped_roles.add(role)
                else:
                    unmapped.append(group)

        # Apply fallback role if configured
        if unmapped and self.fallback_role:
            mapped_roles.add(self.fallback_role)

        result = MappingResult(
            roles=sorted(mapped_roles),
            unmapped_groups=unmapped,
            source=source,
        )

        logger.info(
            "Async role mapping completed",
            extra={
                "input_groups": groups,
                "mapped_roles": result.roles,
                "unmapped_groups": result.unmapped_groups,
                "provider_id": provider_id,
                "source": result.source,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

        return result

    async def _fetch_provider_mappings(
        self,
        provider_id: str,
        session: object,
    ) -> dict[str, tuple[str, int]]:
        """Fetch role mappings for a provider from the database.

        Args:
            provider_id: UUID of the SSO provider.
            session: SQLAlchemy AsyncSession.

        Returns:
            Dictionary mapping group names to (role, priority) tuples.
        """
        # Import here to avoid circular dependencies
        from sqlalchemy import select

        from src.core.shared.models.sso_role_mapping import SSORoleMapping

        stmt = (
            select(SSORoleMapping)
            .where(SSORoleMapping.provider_id == provider_id)
            .order_by(SSORoleMapping.priority.desc())
        )

        result = await session.execute(stmt)
        mappings = result.scalars().all()

        return {m.idp_group: (m.acgs_role, m.priority) for m in mappings}

    def add_default_mapping(self, group: str, role: str) -> None:
        """Add a default group->role mapping.

        Args:
            group: IdP group name.
            role: ACGS-2 role to assign.
        """
        key = group if self.case_sensitive else group.lower()
        self.default_mappings[key] = role

        logger.debug(
            "Default mapping added",
            extra={
                "group": group,
                "role": role,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

    def remove_default_mapping(self, group: str) -> bool:
        """Remove a default group->role mapping.

        Args:
            group: IdP group name to remove.

        Returns:
            True if mapping was removed, False if not found.
        """
        key = group if self.case_sensitive else group.lower()
        if key in self.default_mappings:
            del self.default_mappings[key]
            logger.debug(
                "Default mapping removed",
                extra={
                    "group": group,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )
            return True
        return False

    def get_default_mappings(self) -> dict[str, str]:
        """Get all default mappings.

        Returns:
            Copy of the default mappings dictionary.
        """
        return self.default_mappings.copy()

    async def create_mapping(
        self,
        provider_id: str,
        idp_group: str,
        acgs_role: str,
        session: object,
        priority: int = 0,
        description: str | None = None,
    ) -> object:
        """Create a new role mapping in the database.

        Args:
            provider_id: UUID of the SSO provider.
            idp_group: IdP group name to map.
            acgs_role: ACGS-2 role to assign.
            session: SQLAlchemy AsyncSession.
            priority: Mapping priority for conflict resolution.
            description: Optional description.

        Returns:
            Created SSORoleMapping instance.
        """
        from src.core.shared.models.sso_role_mapping import SSORoleMapping

        mapping = SSORoleMapping.create_mapping(
            provider_id=provider_id,
            idp_group=idp_group,
            acgs_role=acgs_role,
            priority=priority,
            description=description,
        )

        session.add(mapping)

        logger.info(
            "Role mapping created",
            extra={
                "mapping_id": mapping.id,
                "provider_id": provider_id,
                "idp_group": idp_group,
                "acgs_role": acgs_role,
                "priority": priority,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

        return mapping

    async def delete_mapping(
        self,
        mapping_id: str,
        session: object,
    ) -> bool:
        """Delete a role mapping from the database.

        Args:
            mapping_id: UUID of the mapping to delete.
            session: SQLAlchemy AsyncSession.

        Returns:
            True if mapping was deleted, False if not found.
        """
        from sqlalchemy import select

        from src.core.shared.models.sso_role_mapping import SSORoleMapping

        stmt = select(SSORoleMapping).where(SSORoleMapping.id == mapping_id)
        result = await session.execute(stmt)
        mapping = result.scalar_one_or_none()

        if mapping is None:
            return False

        await session.delete(mapping)

        logger.info(
            "Role mapping deleted",
            extra={
                "mapping_id": mapping_id,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

        return True

    async def get_provider_mappings(
        self,
        provider_id: str,
        session: object,
    ) -> list[dict]:
        """Get all role mappings for a provider.

        Args:
            provider_id: UUID of the SSO provider.
            session: SQLAlchemy AsyncSession.

        Returns:
            List of mapping dictionaries.
        """
        from sqlalchemy import select

        from src.core.shared.models.sso_role_mapping import SSORoleMapping

        stmt = (
            select(SSORoleMapping)
            .where(SSORoleMapping.provider_id == provider_id)
            .order_by(SSORoleMapping.priority.desc(), SSORoleMapping.idp_group)
        )

        result = await session.execute(stmt)
        mappings = result.scalars().all()

        return [
            {
                "id": m.id,
                "provider_id": m.provider_id,
                "idp_group": m.idp_group,
                "acgs_role": m.acgs_role,
                "priority": m.priority,
                "description": m.description,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "updated_at": m.updated_at.isoformat() if m.updated_at else None,
            }
            for m in mappings
        ]


# Module-level singleton for convenience
_default_mapper: RoleMapper | None = None


def get_role_mapper(
    default_mappings: dict[str, str] | None = None,
    fallback_role: str | None = None,
    case_sensitive: bool = False,
) -> RoleMapper:
    """Get or create the default role mapper.

    Creates a singleton instance if not already initialized.
    Subsequent calls return the same instance unless reset.

    Args:
        default_mappings: Override default group->role mappings.
        fallback_role: Role to assign when no mappings match.
        case_sensitive: Whether group matching is case-sensitive.

    Returns:
        RoleMapper instance.
    """
    global _default_mapper

    if _default_mapper is None:
        _default_mapper = RoleMapper(
            default_mappings=default_mappings,
            fallback_role=fallback_role,
            case_sensitive=case_sensitive,
        )

    return _default_mapper


def reset_role_mapper() -> None:
    """Reset the default role mapper singleton.

    Useful for testing or reconfiguration.
    """
    global _default_mapper
    _default_mapper = None
