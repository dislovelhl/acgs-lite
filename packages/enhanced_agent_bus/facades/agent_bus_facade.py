"""Public Agent Bus facade for service-layer imports.

Constitutional Hash: 608508a9bd224290

This module defines the stable import surface that service packages should use
instead of importing from ``packages.enhanced_agent_bus`` internals directly.
It centralizes dependency paths and provides lazy symbol loading so heavy
dependencies are only imported when needed.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH

if TYPE_CHECKING:
    from enhanced_agent_bus.agents.chatops_executor import handle_chatops_command
    from enhanced_agent_bus.bundle_registry import (
        BasicAuthProvider,
        BundleManifest,
        OCIRegistryClient,
        RegistryType,
    )
    from enhanced_agent_bus.enums import MessageType
    from enhanced_agent_bus.explanation_service import (
        ExplanationService,
        ExplanationServiceAdapter,
    )
    from enhanced_agent_bus.message_processor import MessageProcessor
    from enhanced_agent_bus.models import DecisionLog
    from enhanced_agent_bus.multi_tenancy.orm_models import (
        EnterpriseIntegrationORM,
        MigrationJobORM,
        TenantAuditLogORM,
        TenantORM,
        TenantRoleMappingORM,
    )
    from enhanced_agent_bus.session_context import SessionContext, SessionContextManager
    from enhanced_agent_bus.validators import ValidationResult


_SYMBOL_SOURCES: dict[str, tuple[str, str]] = {
    "ExplanationService": (
        "enhanced_agent_bus.explanation_service",
        "ExplanationService",
    ),
    "ExplanationServiceAdapter": (
        "enhanced_agent_bus.explanation_service",
        "ExplanationServiceAdapter",
    ),
    "DecisionLog": ("enhanced_agent_bus.models", "DecisionLog"),
    "ValidationResult": ("enhanced_agent_bus.validators", "ValidationResult"),
    "BundleManifest": ("enhanced_agent_bus.bundle_registry", "BundleManifest"),
    "OCIRegistryClient": (
        "enhanced_agent_bus.bundle_registry",
        "OCIRegistryClient",
    ),
    "RegistryType": ("enhanced_agent_bus.bundle_registry", "RegistryType"),
    "BasicAuthProvider": (
        "enhanced_agent_bus.bundle_registry",
        "BasicAuthProvider",
    ),
    "SessionContext": ("enhanced_agent_bus.session_context", "SessionContext"),
    "SessionContextManager": (
        "enhanced_agent_bus.session_context",
        "SessionContextManager",
    ),
    "EnterpriseIntegrationORM": (
        "enhanced_agent_bus.multi_tenancy.orm_models",
        "EnterpriseIntegrationORM",
    ),
    "MigrationJobORM": (
        "enhanced_agent_bus.multi_tenancy.orm_models",
        "MigrationJobORM",
    ),
    "TenantAuditLogORM": (
        "enhanced_agent_bus.multi_tenancy.orm_models",
        "TenantAuditLogORM",
    ),
    "TenantORM": ("enhanced_agent_bus.multi_tenancy.orm_models", "TenantORM"),
    "TenantRoleMappingORM": (
        "enhanced_agent_bus.multi_tenancy.orm_models",
        "TenantRoleMappingORM",
    ),
    "handle_chatops_command": (
        "enhanced_agent_bus.agents.chatops_executor",
        "handle_chatops_command",
    ),
    "MessageType": ("enhanced_agent_bus.enums", "MessageType"),
    "MessageProcessor": (
        "enhanced_agent_bus.message_processor",
        "MessageProcessor",
    ),
}


def __getattr__(name: str) -> object:
    source = _SYMBOL_SOURCES.get(name)
    if source is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, symbol_name = source
    module = import_module(module_name)
    value = getattr(module, symbol_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + list(_SYMBOL_SOURCES.keys()))


__all__ = [
    "CONSTITUTIONAL_HASH",
    "BasicAuthProvider",
    "BundleManifest",
    "DecisionLog",
    "EnterpriseIntegrationORM",
    "ExplanationService",
    "ExplanationServiceAdapter",
    "MessageProcessor",
    "MessageType",
    "MigrationJobORM",
    "OCIRegistryClient",
    "RegistryType",
    "SessionContext",
    "SessionContextManager",
    "TenantAuditLogORM",
    "TenantORM",
    "TenantRoleMappingORM",
    "ValidationResult",
    "handle_chatops_command",
]
