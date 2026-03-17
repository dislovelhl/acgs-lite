"""
ACGS-2 Enhanced Agent Bus - Models
Constitutional Hash: cdd01ef066bc6cf2

Data models for agent communication and message handling.

NOTE: This file has been refactored. Models are now organized into:
- enums.py: All enumeration types
- agent_models.py: SwarmAgent and agent-related models
- batch_models.py: Batch processing models
- session_models.py: Session governance models
- core_models.py: Core message and routing models

This file re-exports all models for backward compatibility.
New code should import directly from the specific modules.
"""

import sys
from typing import TypeAlias, Union

# Ensure module aliasing across package import paths
_module = sys.modules.get(__name__)
if _module is not None:
    sys.modules.setdefault("enhanced_agent_bus.models", _module)
    sys.modules.setdefault("packages.enhanced_agent_bus.models", _module)
    sys.modules.setdefault("core.enhanced_agent_bus.models", _module)
    sys.modules.setdefault("models", _module)

# Import constitutional hash
from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402

# Import type aliases from shared types
try:
    from src.core.shared.types import (
        JSONDict,
        JSONValue,
        MetadataDict,
        PerformanceMetrics,
        SecurityContext,
    )
except ImportError:
    # Fallback for standalone usage
    JSONValue: TypeAlias = object  # type: ignore[misc, no-redef]
    JSONDict: TypeAlias = JSONDict  # type: ignore[misc, no-redef]
    SecurityContext = JSONDict  # type: ignore[misc, no-redef]
    MetadataDict = JSONDict  # type: ignore[misc, no-redef]
    PerformanceMetrics: TypeAlias = dict[str, int | float | str | None]  # type: ignore[misc, no-redef]

# Import constitutional version models
try:
    from .constitutional.version_model import (
        ConstitutionalStatus,
        ConstitutionalVersion,
    )
except ImportError:
    # Constitutional module not yet available
    ConstitutionalVersion = None  # type: ignore[assignment]
    ConstitutionalStatus = None  # type: ignore[assignment]

# Re-export enums
# Re-export agent models
from .agent_models import SwarmAgent  # noqa: E402

# Re-export batch models
from .batch_models import (  # noqa: E402
    BatchRequest,
    BatchRequestItem,
    BatchResponse,
    BatchResponseItem,
    BatchResponseStats,
)

# Re-export core models
from .core_models import (  # noqa: E402
    AgentMessage,
    ConversationMessage,
    ConversationState,
    DecisionLog,
    EnumOrString,
    MessageContent,
    PQCMetadata,
    RoutingContext,
    get_enum_value,
)
from .enums import (  # noqa: E402
    AgentCapability,
    AutonomyTier,
    BatchItemStatus,
    MessageStatus,
    MessageType,
    Priority,
    RiskLevel,
    TaskComplexity,
    TaskType,
    ValidationStatus,
)

# Re-export schema evolution (T012: Event Schema Evolution)
from .schema_evolution import (  # noqa: E402
    AGENT_MESSAGE_SCHEMA_V1,
    AGENT_MESSAGE_SCHEMA_V1_1,
    AGENT_MESSAGE_SCHEMA_V1_2,
    CompatibilityChecker,
    EvolutionType,
    MigrationStatus,
    SchemaCompatibility,
    SchemaDefinition,
    SchemaEvolutionChange,
    SchemaFieldDefinition,
    SchemaMigration,
    SchemaMigrator,
    SchemaRegistry,
    SchemaVersion,
    VersionedMessageBase,
    create_default_registry,
)

# Re-export session models
from .session_models import (  # noqa: E402
    SessionContext,
    SessionGovernanceConfig,
)

# Constants for message constraints
MAX_PAYLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10MB default cap

__all__ = [
    "AGENT_MESSAGE_SCHEMA_V1",
    "AGENT_MESSAGE_SCHEMA_V1_1",
    "AGENT_MESSAGE_SCHEMA_V1_2",
    # Constants
    "CONSTITUTIONAL_HASH",
    "MAX_PAYLOAD_SIZE_BYTES",
    "AgentCapability",
    "AgentMessage",
    "AutonomyTier",
    "BatchItemStatus",
    # Batch processing models
    "BatchRequest",
    "BatchRequestItem",
    "BatchResponse",
    "BatchResponseItem",
    "BatchResponseStats",
    "CompatibilityChecker",
    "ConstitutionalStatus",
    # Constitutional models
    "ConstitutionalVersion",
    # Pydantic models for multi-turn conversation support
    "ConversationMessage",
    "ConversationState",
    "DecisionLog",
    "EnumOrString",
    "EvolutionType",
    # type aliases
    "MessageContent",
    "MessageStatus",
    # Enums
    "MessageType",
    "MetadataDict",
    "MigrationStatus",
    "PQCMetadata",
    "PerformanceMetrics",
    "Priority",
    "RiskLevel",
    # Data classes
    "RoutingContext",
    "SchemaCompatibility",
    "SchemaDefinition",
    "SchemaEvolutionChange",
    "SchemaFieldDefinition",
    "SchemaMigration",
    "SchemaMigrator",
    "SchemaRegistry",
    # Schema Evolution (T012)
    "SchemaVersion",
    "SecurityContext",
    "SessionContext",
    # Session governance models
    "SessionGovernanceConfig",
    "SwarmAgent",
    "TaskComplexity",
    "TaskType",
    "ValidationStatus",
    "VersionedMessageBase",
    "create_default_registry",
    # Utility functions
    "get_enum_value",
]
