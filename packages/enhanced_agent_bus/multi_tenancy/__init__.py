"""
ACGS-2 Multi-Tenancy Module
Constitutional Hash: 608508a9bd224290

Provides enterprise-grade multi-tenant isolation using PostgreSQL Row-Level Security (RLS).
This module implements Phase 10 Task 1: Multi-Tenant Database Foundation.

Features:
- Request-scoped TenantContext for automatic tenant identification
- PostgreSQL RLS policies for data isolation
- Tenant-aware query utilities
- Tenant lifecycle management
"""

import sys

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

# Ensure package aliasing across import paths
_module = sys.modules.get(__name__)
if _module is not None:
    sys.modules.setdefault("enhanced_agent_bus.multi_tenancy", _module)
    sys.modules.setdefault("enhanced_agent_bus.multi_tenancy", _module)
    sys.modules.setdefault("core.enhanced_agent_bus.multi_tenancy", _module)

from .context import (
    TenantContext,
    clear_tenant_context,
    get_current_tenant,
    get_current_tenant_id,
    require_tenant_context,
    set_current_tenant,
    tenant_context,
)
from .db_repository import DatabaseTenantRepository, TenantRepositoryDB
from .manager import (
    TenantEvent,
    TenantManager,
    TenantManagerError,
    TenantNotFoundError,
    TenantQuotaExceededError,
    TenantValidationError,
    get_tenant_manager,
    set_tenant_manager,
)
from .middleware import TenantMiddleware, extract_tenant_from_request
from .models import (
    Tenant,
    TenantConfig,
    TenantQuota,
    TenantStatus,
    TenantUsage,
)
from .orm_models import (
    EnterpriseIntegrationORM,
    MigrationJobORM,
    TenantAuditLogORM,
    TenantORM,
    TenantRoleMappingORM,
    TenantStatusEnum,
)
from .repository import TenantAwareRepository, TenantRepository
from .rls import (
    RLSPolicy,
    RLSPolicyManager,
    create_tenant_rls_policies,
    disable_rls_for_table,
    enable_rls_for_table,
)
from .session_vars import (
    SESSION_VAR_IS_ADMIN,
    SESSION_VAR_TENANT_ID,
    admin_session,
    clear_tenant_session_vars,
    get_current_tenant_from_session,
    get_is_admin_from_session,
    set_tenant_for_request,
    set_tenant_session_vars,
    system_tenant_session,
    tenant_session,
)
from .system_tenant import (
    SYSTEM_TENANT_ID,
    SYSTEM_TENANT_NAME,
    SYSTEM_TENANT_SLUG,
    ensure_system_tenant,
    get_system_tenant,
    get_system_tenant_defaults,
    get_tenant_id_or_system,
    is_system_tenant,
    is_system_tenant_slug,
)

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "SESSION_VAR_IS_ADMIN",
    # Session Variables
    "SESSION_VAR_TENANT_ID",
    # System Tenant
    "SYSTEM_TENANT_ID",
    "SYSTEM_TENANT_NAME",
    "SYSTEM_TENANT_SLUG",
    "DatabaseTenantRepository",
    "EnterpriseIntegrationORM",
    "MigrationJobORM",
    # RLS management
    "RLSPolicy",
    "RLSPolicyManager",
    # Pydantic Models
    "Tenant",
    "TenantAuditLogORM",
    "TenantAwareRepository",
    "TenantConfig",
    # Context management
    "TenantContext",
    "TenantEvent",
    # Manager
    "TenantManager",
    "TenantManagerError",
    # Middleware
    "TenantMiddleware",
    "TenantNotFoundError",
    # SQLAlchemy ORM Models
    "TenantORM",
    "TenantQuota",
    "TenantQuotaExceededError",
    # Repository
    "TenantRepository",
    "TenantRepositoryDB",
    "TenantRoleMappingORM",
    "TenantStatus",
    "TenantStatusEnum",
    "TenantUsage",
    "TenantValidationError",
    "admin_session",
    "clear_tenant_context",
    "clear_tenant_session_vars",
    "create_tenant_rls_policies",
    "disable_rls_for_table",
    "enable_rls_for_table",
    "ensure_system_tenant",
    "extract_tenant_from_request",
    "get_current_tenant",
    "get_current_tenant_from_session",
    "get_current_tenant_id",
    "get_is_admin_from_session",
    "get_system_tenant",
    "get_system_tenant_defaults",
    "get_tenant_id_or_system",
    "get_tenant_manager",
    "is_system_tenant",
    "is_system_tenant_slug",
    "require_tenant_context",
    "set_current_tenant",
    "set_tenant_for_request",
    "set_tenant_manager",
    "set_tenant_session_vars",
    "system_tenant_session",
    "tenant_context",
    "tenant_session",
]
