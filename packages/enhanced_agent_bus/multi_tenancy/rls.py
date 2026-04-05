"""
ACGS-2 Row-Level Security (RLS) Policy Management
Constitutional Hash: 608508a9bd224290

Implements PostgreSQL Row-Level Security for enterprise multi-tenant data isolation.
Provides automatic tenant isolation for all database operations.

Phase 10 Task 1: Multi-Tenant Database Foundation
"""

import re
from dataclasses import dataclass, field
from enum import Enum

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
# SQL identifier validation pattern (PostgreSQL)
# Identifiers must start with letter or underscore, contain only alphanumeric and underscore
_VALID_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Maximum PostgreSQL identifier length
_MAX_IDENTIFIER_LENGTH = 63

# Reserved PostgreSQL keywords that cannot be used as unquoted identifiers
_RESERVED_KEYWORDS: set[str] = {
    "all",
    "analyse",
    "analyze",
    "and",
    "any",
    "array",
    "as",
    "asc",
    "asymmetric",
    "authorization",
    "binary",
    "both",
    "case",
    "cast",
    "check",
    "collate",
    "collation",
    "column",
    "concurrently",
    "constraint",
    "create",
    "cross",
    "current_catalog",
    "current_date",
    "current_role",
    "current_schema",
    "current_time",
    "current_timestamp",
    "current_user",
    "default",
    "deferrable",
    "desc",
    "distinct",
    "do",
    "else",
    "end",
    "except",
    "false",
    "fetch",
    "for",
    "foreign",
    "from",
    "grant",
    "group",
    "having",
    "in",
    "initially",
    "inner",
    "intersect",
    "into",
    "is",
    "isnull",
    "join",
    "lateral",
    "leading",
    "left",
    "like",
    "limit",
    "localtime",
    "localtimestamp",
    "natural",
    "not",
    "notnull",
    "null",
    "offset",
    "on",
    "only",
    "or",
    "order",
    "outer",
    "overlaps",
    "placing",
    "primary",
    "references",
    "returning",
    "right",
    "select",
    "session_user",
    "similar",
    "some",
    "symmetric",
    "table",
    "tablesample",
    "then",
    "to",
    "trailing",
    "true",
    "union",
    "unique",
    "user",
    "using",
    "variadic",
    "verbose",
    "when",
    "where",
    "window",
    "with",
}

# Allowed tables for RLS operations (whitelist approach for extra security)
ALLOWED_RLS_TABLES: set[str] = {
    # Constitutional governance tables
    "constitutional_versions",
    "amendment_proposals",
    "policies",
    "policy_versions",
    "agents",
    "agent_messages",
    "audit_logs",
    "decision_logs",
    "governance_sessions",
    "maci_records",
    # SSO and authentication tables
    "users",
    "sso_providers",
    "sso_role_mappings",
    "saml_outstanding_requests",
    # Multi-tenancy tables (self-isolation not needed for tenants table)
    "enterprise_integrations",
    "tenant_role_mappings",
    "migration_jobs",
    "tenant_audit_logs",
    # Schema-qualified names - Constitutional governance
    "public.constitutional_versions",
    "public.amendment_proposals",
    "public.policies",
    "public.policy_versions",
    "public.agents",
    "public.agent_messages",
    "public.audit_logs",
    "public.decision_logs",
    "public.governance_sessions",
    "public.maci_records",
    # Schema-qualified names - SSO
    "public.users",
    "public.sso_providers",
    "public.sso_role_mappings",
    "public.saml_outstanding_requests",
    # Schema-qualified names - Multi-tenancy
    "public.enterprise_integrations",
    "public.tenant_role_mappings",
    "public.migration_jobs",
    "public.tenant_audit_logs",
}


class SQLIdentifierError(ValueError):
    """Raised when an invalid SQL identifier is provided."""

    pass


def validate_sql_identifier(
    identifier: str,
    identifier_type: str = "identifier",
    max_length: int = _MAX_IDENTIFIER_LENGTH,
    allow_schema_qualified: bool = False,
) -> str:
    """
    Validate a PostgreSQL identifier to prevent SQL injection.

    Args:
        identifier: The identifier to validate.
        identifier_type: Type of identifier for error messages (e.g., "table name", "policy name").
        max_length: Maximum allowed length (default: 63 for PostgreSQL).
        allow_schema_qualified: Allow schema.table format (e.g., "public.users").

    Returns:
        The validated identifier.

    Raises:
        SQLIdentifierError: If the identifier is invalid.
    """
    if not identifier:
        raise SQLIdentifierError(f"Empty {identifier_type} is not allowed")

    if len(identifier) > max_length:
        raise SQLIdentifierError(
            f"{identifier_type} exceeds maximum length of {max_length}: {identifier}"
        )

    # Handle schema-qualified names (schema.table)
    if allow_schema_qualified and "." in identifier:
        parts = identifier.split(".")
        if len(parts) != 2:
            raise SQLIdentifierError(f"Invalid schema-qualified {identifier_type}: {identifier}")
        schema, name = parts
        validate_sql_identifier(schema, "schema name", max_length, allow_schema_qualified=False)
        validate_sql_identifier(name, identifier_type, max_length, allow_schema_qualified=False)
        return identifier

    # Check pattern
    if not _VALID_IDENTIFIER_PATTERN.match(identifier):
        raise SQLIdentifierError(
            f"Invalid {identifier_type} '{identifier}': must start with letter or underscore "
            "and contain only alphanumeric characters and underscores"
        )

    # Check reserved keywords
    if identifier.lower() in _RESERVED_KEYWORDS:
        raise SQLIdentifierError(
            f"Invalid {identifier_type} '{identifier}': cannot use reserved keyword"
        )

    return identifier


def quote_sql_identifier(identifier: str) -> str:
    """
    Quote a SQL identifier for safe use in SQL statements.

    Uses PostgreSQL double-quote syntax with proper escaping.
    Double quotes within the identifier are escaped by doubling.

    Args:
        identifier: The identifier to quote.

    Returns:
        The quoted identifier.
    """
    # Escape any existing double quotes by doubling them
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def validate_table_name(table_name: str, strict: bool = True) -> str:
    """
    Validate a table name for RLS operations.

    Args:
        table_name: The table name to validate.
        strict: If True, only allow tables in ALLOWED_RLS_TABLES whitelist.

    Returns:
        The validated table name.

    Raises:
        SQLIdentifierError: If the table name is invalid.
    """
    # First, validate as a SQL identifier
    validated = validate_sql_identifier(
        table_name,
        identifier_type="table name",
        allow_schema_qualified=True,
    )

    # In strict mode, check against whitelist
    if strict and validated not in ALLOWED_RLS_TABLES:
        raise SQLIdentifierError(
            f"Table '{validated}' is not in the allowed RLS tables list. "
            f"Add it to ALLOWED_RLS_TABLES if this is intentional."
        )

    return validated


def validate_role_name(role: str) -> str:
    """
    Validate a PostgreSQL role name.

    Args:
        role: The role name to validate.

    Returns:
        The validated role name.

    Raises:
        SQLIdentifierError: If the role name is invalid.
    """
    # Special case: PUBLIC is a valid role keyword
    if role.upper() == "PUBLIC":
        return "PUBLIC"

    return validate_sql_identifier(role, identifier_type="role name")


class RLSPolicyType(str, Enum):
    """Types of RLS policies."""

    SELECT = "select"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    ALL = "all"


@dataclass
class RLSPolicy:
    """Row-Level Security policy definition.

    Constitutional Hash: 608508a9bd224290

    All identifiers (name, table_name, roles) are validated to prevent SQL injection.
    """

    name: str
    table_name: str
    policy_type: RLSPolicyType
    using_expression: str
    with_check_expression: str | None = None
    roles: list[str] = field(default_factory=lambda: ["PUBLIC"])
    enabled: bool = True
    strict_table_validation: bool = True  # If True, table must be in ALLOWED_RLS_TABLES

    def __post_init__(self) -> None:
        """Validate all identifiers after initialization."""
        # Validate policy name
        validate_sql_identifier(self.name, identifier_type="policy name")

        # Validate table name
        validate_table_name(self.table_name, strict=self.strict_table_validation)

        # Validate all role names
        validated_roles = []
        for role in self.roles:
            validated_roles.append(validate_role_name(role))
        # Update roles with validated versions (handles PUBLIC normalization)
        object.__setattr__(self, "roles", validated_roles)

    def to_sql_create(self) -> str:
        """Generate SQL CREATE POLICY statement with quoted identifiers."""
        # Use quoted identifiers for safety
        quoted_name = quote_sql_identifier(self.name)
        quoted_table = quote_sql_identifier(self.table_name)
        role_spec = ", ".join(quote_sql_identifier(r) if r != "PUBLIC" else r for r in self.roles)

        policy_for = (
            self.policy_type.value.upper() if self.policy_type != RLSPolicyType.ALL else "ALL"
        )

        sql = f"""
CREATE POLICY {quoted_name} ON {quoted_table}
    FOR {policy_for}
    TO {role_spec}
    USING ({self.using_expression})"""

        if self.with_check_expression:
            sql += f"\n    WITH CHECK ({self.with_check_expression})"

        return sql.strip() + ";"

    def to_sql_drop(self) -> str:
        """Generate SQL DROP POLICY statement with quoted identifiers."""
        quoted_name = quote_sql_identifier(self.name)
        quoted_table = quote_sql_identifier(self.table_name)
        return f"DROP POLICY IF EXISTS {quoted_name} ON {quoted_table};"


class RLSPolicyManager:
    """Manages RLS policies for multi-tenant isolation.

    Constitutional Hash: 608508a9bd224290

    This manager provides utilities for:
    - Creating tenant isolation policies
    - Managing policy lifecycle
    - Generating migration scripts
    """

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH) -> None:
        """Initialize the RLS policy manager."""
        if constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(
                f"Invalid constitutional hash. Expected {CONSTITUTIONAL_HASH}, "
                f"got {constitutional_hash}"
            )
        self.constitutional_hash = constitutional_hash
        self._policies: dict[str, RLSPolicy] = {}

    def register_policy(self, policy: RLSPolicy) -> None:
        """Register an RLS policy."""
        key = f"{policy.table_name}.{policy.name}"
        self._policies[key] = policy
        logger.debug(f"[{CONSTITUTIONAL_HASH}] Registered RLS policy: {key}")

    def get_policy(self, table_name: str, policy_name: str) -> RLSPolicy | None:
        """Get a registered policy."""
        key = f"{table_name}.{policy_name}"
        return self._policies.get(key)

    def list_policies(self, table_name: str | None = None) -> list[RLSPolicy]:
        """List registered policies, optionally filtered by table."""
        if table_name:
            return [p for p in self._policies.values() if p.table_name == table_name]
        return list(self._policies.values())

    def generate_migration_up(self) -> str:
        """Generate SQL migration script for enabling RLS."""
        lines = [
            "-- ACGS-2 Multi-Tenant RLS Migration",
            f"-- Constitutional Hash: {CONSTITUTIONAL_HASH}",
            "-- Generated by RLSPolicyManager",
            "",
        ]

        # Group policies by table
        tables: dict[str, list[RLSPolicy]] = {}
        for policy in self._policies.values():
            if policy.table_name not in tables:
                tables[policy.table_name] = []
            tables[policy.table_name].append(policy)

        for table_name, policies in tables.items():
            # Use quoted identifier for SQL safety
            quoted_table = quote_sql_identifier(table_name)
            lines.append(f"-- Enable RLS on {table_name}")
            lines.append(f"ALTER TABLE {quoted_table} ENABLE ROW LEVEL SECURITY;")
            lines.append(f"ALTER TABLE {quoted_table} FORCE ROW LEVEL SECURITY;")
            lines.append("")

            for policy in policies:
                lines.append(f"-- Policy: {policy.name}")
                lines.append(policy.to_sql_create())
                lines.append("")

        return "\n".join(lines)

    def generate_migration_down(self) -> str:
        """Generate SQL migration script for disabling RLS."""
        lines = [
            "-- ACGS-2 Multi-Tenant RLS Rollback",
            f"-- Constitutional Hash: {CONSTITUTIONAL_HASH}",
            "",
        ]

        tables = set(p.table_name for p in self._policies.values())

        for table_name in tables:
            # Use quoted identifier for SQL safety
            quoted_table = quote_sql_identifier(table_name)
            lines.append(f"-- Disable RLS on {table_name}")
            for policy in self._policies.values():
                if policy.table_name == table_name:
                    lines.append(policy.to_sql_drop())
            lines.append(f"ALTER TABLE {quoted_table} DISABLE ROW LEVEL SECURITY;")
            lines.append("")

        return "\n".join(lines)


def create_tenant_isolation_policy(
    table_name: str,
    tenant_column: str = "tenant_id",
    policy_name: str | None = None,
    strict_table_validation: bool = True,
) -> RLSPolicy:
    """Create a standard tenant isolation policy.

    Args:
        table_name: Name of the table to protect.
        tenant_column: Column containing tenant ID (default: tenant_id).
        policy_name: Custom policy name (default: {table}_tenant_isolation).
        strict_table_validation: Whether to validate table names strictly.

    Returns:
        RLSPolicy for tenant isolation.
    """
    name = policy_name or f"{table_name.replace('.', '_')}_tenant_isolation"

    return RLSPolicy(
        name=name,
        table_name=table_name,
        policy_type=RLSPolicyType.ALL,
        using_expression=f"{tenant_column} = current_setting('app.current_tenant_id', true)",
        with_check_expression=f"{tenant_column} = current_setting('app.current_tenant_id', true)",
        strict_table_validation=strict_table_validation,
    )


def create_admin_bypass_policy(
    table_name: str,
    policy_name: str | None = None,
    strict_table_validation: bool = True,
) -> RLSPolicy:
    """Create admin bypass policy for super-admin access.

    Args:
        table_name: Name of the table.
        policy_name: Custom policy name.
        strict_table_validation: Whether to validate table names strictly.

    Returns:
        RLSPolicy allowing admin access to all rows.
    """
    name = policy_name or f"{table_name.replace('.', '_')}_admin_bypass"

    return RLSPolicy(
        name=name,
        table_name=table_name,
        policy_type=RLSPolicyType.ALL,
        using_expression="current_setting('app.is_admin', true)::boolean = true",
        with_check_expression="current_setting('app.is_admin', true)::boolean = true",
        strict_table_validation=strict_table_validation,
    )


def create_tenant_rls_policies(
    tables: list[str],
    tenant_column: str = "tenant_id",
    include_admin_bypass: bool = True,
    strict_table_validation: bool = True,
) -> list[RLSPolicy]:
    """Create RLS policies for multiple tables.

    Args:
        tables: List of table names to protect.
        tenant_column: Column containing tenant ID.
        include_admin_bypass: Whether to include admin bypass policies.
        strict_table_validation: Whether to validate table names strictly.

    Returns:
        List of RLSPolicy objects.
    """
    policies = []

    for table in tables:
        # Tenant isolation policy
        policies.append(
            create_tenant_isolation_policy(
                table_name=table,
                tenant_column=tenant_column,
                strict_table_validation=strict_table_validation,
            )
        )

        # Admin bypass policy
        if include_admin_bypass:
            policies.append(
                create_admin_bypass_policy(
                    table_name=table,
                    strict_table_validation=strict_table_validation,
                )
            )

    logger.info(
        f"[{CONSTITUTIONAL_HASH}] Created {len(policies)} RLS policies for {len(tables)} tables"
    )
    return policies


def enable_rls_for_table(table_name: str, force: bool = True, strict: bool = True) -> str:
    """Generate SQL to enable RLS for a table.

    Args:
        table_name: Name of the table.
        force: Whether to force RLS even for table owner.
        strict: If True, only allow tables in ALLOWED_RLS_TABLES whitelist.

    Returns:
        SQL statement.

    Raises:
        SQLIdentifierError: If the table name is invalid.
    """
    # Validate and quote for SQL injection prevention
    validated_name = validate_table_name(table_name, strict=strict)
    quoted_table = quote_sql_identifier(validated_name)

    sql = f"ALTER TABLE {quoted_table} ENABLE ROW LEVEL SECURITY;"
    if force:
        sql += f"\nALTER TABLE {quoted_table} FORCE ROW LEVEL SECURITY;"
    return sql


def disable_rls_for_table(table_name: str, strict: bool = True) -> str:
    """Generate SQL to disable RLS for a table.

    Args:
        table_name: Name of the table.
        strict: If True, only allow tables in ALLOWED_RLS_TABLES whitelist.

    Returns:
        SQL statement.

    Raises:
        SQLIdentifierError: If the table name is invalid.
    """
    # Validate and quote for SQL injection prevention
    validated_name = validate_table_name(table_name, strict=strict)
    quoted_table = quote_sql_identifier(validated_name)
    return f"ALTER TABLE {quoted_table} DISABLE ROW LEVEL SECURITY;"


# Standard ACGS-2 tables requiring RLS
ACGS2_RLS_TABLES = [
    # Constitutional governance tables
    "constitutional_versions",
    "amendment_proposals",
    "policies",
    "policy_versions",
    "agents",
    "agent_messages",
    "audit_logs",
    "decision_logs",
    "governance_sessions",
    "maci_records",
    # SSO and authentication tables
    "users",
    "sso_providers",
    "sso_role_mappings",
    "saml_outstanding_requests",
]

# Tables that need RLS for tenant isolation from enterprise integrations
ENTERPRISE_RLS_TABLES = [
    "enterprise_integrations",
    "tenant_role_mappings",
    "migration_jobs",
    "tenant_audit_logs",
]


def create_acgs2_rls_policies() -> RLSPolicyManager:
    """Create standard ACGS-2 RLS policies.

    Constitutional Hash: 608508a9bd224290

    Returns:
        Configured RLSPolicyManager with all ACGS-2 policies.
    """
    manager = RLSPolicyManager()

    # Create policies for all standard tables
    policies = create_tenant_rls_policies(
        tables=ACGS2_RLS_TABLES,
        tenant_column="tenant_id",
        include_admin_bypass=True,
    )

    for policy in policies:
        manager.register_policy(policy)

    logger.info(
        f"[{CONSTITUTIONAL_HASH}] Initialized ACGS-2 RLS policy manager with "
        f"{len(manager.list_policies())} policies"
    )

    return manager
