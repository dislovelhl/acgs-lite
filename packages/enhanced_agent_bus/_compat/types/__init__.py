"""Shim package for src.core.shared.types.

This package marker enables ``from enhanced_agent_bus._compat.types.protocol_types import X``
patterns. It re-exports all names from the flat ``_compat/types.py`` module via a relative
import so that ``from enhanced_agent_bus._compat.types import CONSTITUTIONAL_HASH`` also works
when the package form is resolved.

NOTE: Python resolves ``_compat.types`` as this directory package (not the sibling
``_compat/types.py`` flat module) once the directory exists, so we must replicate the
flat module exports here.
"""
from __future__ import annotations

from typing import Any

try:
    from src.core.shared.types import *  # noqa: F403
except ImportError:
    # Standalone type alias fallbacks — mirrors _compat/types.py
    JSONPrimitive = str | int | float | bool | None
    JSONValue = Any
    JSONDict = dict[str, Any]  # type: ignore[misc,assignment]
    JSONList = list[Any]  # type: ignore[misc,assignment]
    JSONType = JSONDict | JSONList  # type: ignore[misc,assignment]
    MetadataDict = dict[str, Any]  # type: ignore[misc,assignment]
    NestedDict = dict[str, Any]  # type: ignore[misc,assignment]
    RecursiveDict = dict[str, Any]  # type: ignore[misc,assignment]

    AgentID = str  # type: ignore[misc,assignment]
    AgentInfo = dict[str, Any]  # type: ignore[misc,assignment]
    AgentIdentity = str  # type: ignore[misc,assignment]
    AgentMetadata = dict[str, Any]  # type: ignore[misc,assignment]
    AgentState = dict[str, Any]  # type: ignore[misc,assignment]
    AgentContext = dict[str, Any]  # type: ignore[misc,assignment]
    ContextData = dict[str, Any]  # type: ignore[misc,assignment]

    MessageID = str  # type: ignore[misc,assignment]
    MessagePayload = dict[str, Any]  # type: ignore[misc,assignment]
    MessageHeaders = dict[str, str]  # type: ignore[misc,assignment]
    MessageMetadata = dict[str, Any]  # type: ignore[misc,assignment]
    KafkaMessage = dict[str, Any]  # type: ignore[misc,assignment]

    EventID = str  # type: ignore[misc,assignment]
    EventData = dict[str, Any]  # type: ignore[misc,assignment]
    EventContext = dict[str, Any]  # type: ignore[misc,assignment]

    WorkflowID = str  # type: ignore[misc,assignment]
    WorkflowState = dict[str, Any]  # type: ignore[misc,assignment]
    WorkflowContext = dict[str, Any]  # type: ignore[misc,assignment]
    SessionData = dict[str, Any]  # type: ignore[misc,assignment]
    StepParameters = dict[str, Any]  # type: ignore[misc,assignment]
    StepResult = dict[str, Any]  # type: ignore[misc,assignment]
    TopicName = str  # type: ignore[misc,assignment]
    MemoryData = dict[str, Any]  # type: ignore[misc,assignment]

    CorrelationID = str  # type: ignore[misc,assignment]
    TenantID = str  # type: ignore[misc,assignment]
    Timestamp = str  # type: ignore[misc,assignment]
    TraceID = str  # type: ignore[misc,assignment]
    ErrorCode = str  # type: ignore[misc,assignment]
    ErrorContext = dict[str, Any]  # type: ignore[misc,assignment]
    ErrorDetails = dict[str, Any]  # type: ignore[misc,assignment]
    PolicyID = str  # type: ignore[misc,assignment]
    PolicyContext = dict[str, Any]  # type: ignore[misc,assignment]
    PolicyData = dict[str, Any]  # type: ignore[misc,assignment]
    PolicyDecision = dict[str, Any]  # type: ignore[misc,assignment]
    DecisionData = dict[str, Any]  # type: ignore[misc,assignment]
    SecurityContext = dict[str, Any]  # type: ignore[misc,assignment]
    ValidationContext = dict[str, Any]  # type: ignore[misc,assignment]
    ValidationErrors = list[dict[str, Any]]  # type: ignore[misc,assignment]
    PermissionSet = set[str]  # type: ignore[misc,assignment]
    ModelID = str  # type: ignore[misc,assignment]
    ModelMetadata = dict[str, Any]  # type: ignore[misc,assignment]
    ModelParameters = dict[str, Any]  # type: ignore[misc,assignment]
    PerformanceMetrics = dict[str, int | float | str | None]  # type: ignore[misc,assignment]
    TelemetryData = dict[str, Any]  # type: ignore[misc,assignment]
    AuditEntry = dict[str, Any]  # type: ignore[misc,assignment]
    AuditTrail = list[dict[str, Any]]  # type: ignore[misc,assignment]
    AuthContext = dict[str, Any]  # type: ignore[misc,assignment]
    AuthCredentials = dict[str, Any]  # type: ignore[misc,assignment]
    AuthToken = str  # type: ignore[misc,assignment]
    CacheKey = str  # type: ignore[misc,assignment]
    CacheTTL = int  # type: ignore[misc,assignment]
    CacheValue = Any  # type: ignore[misc,assignment]
    ConfigDict = dict[str, Any]  # type: ignore[misc,assignment]
    ConfigValue = Any  # type: ignore[misc,assignment]
    ConstitutionalContext = dict[str, Any]  # type: ignore[misc,assignment]
    RedisValue = str | bytes  # type: ignore[misc,assignment]
    EventMetadata = dict[str, Any]  # type: ignore[misc,assignment]

    CONSTITUTIONAL_HASH = "608508a9bd224290"
