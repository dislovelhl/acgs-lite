"""Shim for src.core.shared.types."""

from __future__ import annotations

from typing import Any

try:
    from src.core.shared.types import *  # noqa: F403
    from src.core.shared.types import (  # explicit re-exports for high-frequency names
        CONSTITUTIONAL_HASH,
        AgentContext,
        AgentID,
        AgentIdentity,
        AgentInfo,
        AgentMetadata,
        AgentState,
        AuditEntry,
        AuditTrail,
        AuthContext,
        AuthCredentials,
        AuthToken,
        CacheKey,
        CacheTTL,
        CacheValue,
        ConfigDict,
        ConfigValue,
        ConstitutionalContext,
        ContextData,
        CorrelationID,
        DecisionData,
        ErrorCode,
        ErrorContext,
        ErrorDetails,
        EventContext,
        EventData,
        EventID,
        JSONDict,
        JSONList,
        JSONPrimitive,
        JSONType,
        JSONValue,
        KafkaMessage,
        MemoryData,
        MessageHeaders,
        MessageID,
        MessageMetadata,
        MessagePayload,
        MetadataDict,
        ModelID,
        ModelMetadata,
        ModelParameters,
        NestedDict,
        PerformanceMetrics,
        PermissionSet,
        PolicyContext,
        PolicyData,
        PolicyDecision,
        PolicyID,
        RecursiveDict,
        RedisValue,
        SecurityContext,
        SessionData,
        StepParameters,
        StepResult,
        TelemetryData,
        TenantID,
        Timestamp,
        TopicName,
        TraceID,
        ValidationContext,
        ValidationErrors,
        WorkflowContext,
        WorkflowID,
        WorkflowState,
    )
except ImportError:
    # Standalone type alias fallbacks
    JSONPrimitive = str | int | float | bool | None
    JSONValue = Any
    JSONDict = dict[str, Any]  # type: ignore[misc,assignment]
    JSONList = list[Any]  # type: ignore[misc,assignment]
    JSONType = JSONDict | JSONList  # type: ignore[misc,assignment]
    MetadataDict = dict[str, Any]  # type: ignore[misc,assignment]
    NestedDict = dict[str, Any]  # type: ignore[misc,assignment]
    RecursiveDict = dict[str, Any]  # type: ignore[misc,assignment]

    # Agent types
    AgentID = str  # type: ignore[misc,assignment]
    AgentInfo = dict[str, Any]  # type: ignore[misc,assignment]
    AgentIdentity = str  # type: ignore[misc,assignment]
    AgentMetadata = dict[str, Any]  # type: ignore[misc,assignment]
    AgentState = dict[str, Any]  # type: ignore[misc,assignment]
    AgentContext = dict[str, Any]  # type: ignore[misc,assignment]
    ContextData = dict[str, Any]  # type: ignore[misc,assignment]

    # Message types
    MessageID = str  # type: ignore[misc,assignment]
    MessagePayload = dict[str, Any]  # type: ignore[misc,assignment]
    MessageHeaders = dict[str, str]  # type: ignore[misc,assignment]
    MessageMetadata = dict[str, Any]  # type: ignore[misc,assignment]
    KafkaMessage = dict[str, Any]  # type: ignore[misc,assignment]

    # Event types
    EventID = str  # type: ignore[misc,assignment]
    EventData = dict[str, Any]  # type: ignore[misc,assignment]
    EventContext = dict[str, Any]  # type: ignore[misc,assignment]

    # Workflow types
    WorkflowID = str  # type: ignore[misc,assignment]
    WorkflowState = dict[str, Any]  # type: ignore[misc,assignment]
    WorkflowContext = dict[str, Any]  # type: ignore[misc,assignment]
    SessionData = dict[str, Any]  # type: ignore[misc,assignment]
    StepParameters = dict[str, Any]  # type: ignore[misc,assignment]
    StepResult = dict[str, Any]  # type: ignore[misc,assignment]
    TopicName = str  # type: ignore[misc,assignment]
    MemoryData = dict[str, Any]  # type: ignore[misc,assignment]

    # Governance types
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
