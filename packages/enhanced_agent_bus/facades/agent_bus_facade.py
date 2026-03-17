"""Public Agent Bus facade for service-layer imports.

Constitutional Hash: cdd01ef066bc6cf2

This module defines the stable import surface that service packages should use
instead of importing from ``packages.enhanced_agent_bus`` internals directly.
It centralizes dependency paths and provides lazy symbol loading so heavy
dependencies are only imported when needed.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from src.core.shared.constants import CONSTITUTIONAL_HASH

CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH

if TYPE_CHECKING:
    from packages.enhanced_agent_bus.agents.chatops_executor import handle_chatops_command
    from packages.enhanced_agent_bus.bundle_registry import (
        BasicAuthProvider,
        BundleManifest,
        OCIRegistryClient,
        RegistryType,
    )
    from packages.enhanced_agent_bus.enums import MessageType
    from packages.enhanced_agent_bus.explanation_service import (
        ExplanationService,
        ExplanationServiceAdapter,
    )
    from packages.enhanced_agent_bus.message_processor import MessageProcessor
    from packages.enhanced_agent_bus.models import DecisionLog
    from packages.enhanced_agent_bus.multi_tenancy.orm_models import (
        EnterpriseIntegrationORM,
        MigrationJobORM,
        TenantAuditLogORM,
        TenantORM,
        TenantRoleMappingORM,
    )
    from packages.enhanced_agent_bus.session_context import SessionContext, SessionContextManager
    from packages.enhanced_agent_bus.validators import ValidationResult


_SYMBOL_SOURCES: dict[str, tuple[str, str]] = {
    "ExplanationService": (
        "packages.enhanced_agent_bus.explanation_service",
        "ExplanationService",
    ),
    "ExplanationServiceAdapter": (
        "packages.enhanced_agent_bus.explanation_service",
        "ExplanationServiceAdapter",
    ),
    "DecisionLog": ("packages.enhanced_agent_bus.models", "DecisionLog"),
    "ValidationResult": ("packages.enhanced_agent_bus.validators", "ValidationResult"),
    "BundleManifest": ("packages.enhanced_agent_bus.bundle_registry", "BundleManifest"),
    "OCIRegistryClient": (
        "packages.enhanced_agent_bus.bundle_registry",
        "OCIRegistryClient",
    ),
    "RegistryType": ("packages.enhanced_agent_bus.bundle_registry", "RegistryType"),
    "BasicAuthProvider": (
        "packages.enhanced_agent_bus.bundle_registry",
        "BasicAuthProvider",
    ),
    "SessionContext": ("packages.enhanced_agent_bus.session_context", "SessionContext"),
    "SessionContextManager": (
        "packages.enhanced_agent_bus.session_context",
        "SessionContextManager",
    ),
    "EnterpriseIntegrationORM": (
        "packages.enhanced_agent_bus.multi_tenancy.orm_models",
        "EnterpriseIntegrationORM",
    ),
    "MigrationJobORM": (
        "packages.enhanced_agent_bus.multi_tenancy.orm_models",
        "MigrationJobORM",
    ),
    "TenantAuditLogORM": (
        "packages.enhanced_agent_bus.multi_tenancy.orm_models",
        "TenantAuditLogORM",
    ),
    "TenantORM": ("packages.enhanced_agent_bus.multi_tenancy.orm_models", "TenantORM"),
    "TenantRoleMappingORM": (
        "packages.enhanced_agent_bus.multi_tenancy.orm_models",
        "TenantRoleMappingORM",
    ),
    "handle_chatops_command": (
        "packages.enhanced_agent_bus.agents.chatops_executor",
        "handle_chatops_command",
    ),
    "MessageType": ("packages.enhanced_agent_bus.enums", "MessageType"),
    "MessageProcessor": (
        "packages.enhanced_agent_bus.message_processor",
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
