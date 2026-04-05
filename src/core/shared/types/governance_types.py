# Constitutional Hash: 608508a9bd224290
"""Policy, governance, auth, security, and config type aliases for ACGS-2."""

from .json_types import JSONDict, JSONValue

# Policy and Governance
PolicyID = str  # Policy identifier
PolicyData = dict[str, JSONValue]  # Policy definition data
PolicyContext = dict[str, JSONValue]  # Policy evaluation context
PolicyDecision = dict[str, JSONValue]  # Policy decision result

# ABAC/RBAC
AttributeMap = dict[str, JSONValue]  # Attribute-based access control attributes
RoleData = dict[str, JSONValue]  # Role definition
PermissionSet = set[str]  # Set of permission strings

# Constitutional governance
ConstitutionalContext = dict[str, JSONValue]  # Constitutional decision context
DecisionData = dict[str, JSONValue]  # Decision data
VerificationResult = dict[str, JSONValue]  # Verification result

# Configuration and Settings
ConfigDict = dict[str, JSONValue]  # Configuration dictionaries
ConfigValue = JSONValue  # Individual configuration value
EnvVars = dict[str, str]  # Environment variables
SecretData = dict[str, str]  # Secret/credential data

# Authentication and Security
AuthToken = str  # Authentication token
AuthCredentials = dict[str, str]  # Authentication credentials
AuthContext = dict[str, JSONValue]  # Authentication context
UserAttributes = dict[str, JSONValue]  # User attribute data (SAML, OIDC)

# Security types
TenantID = str  # Tenant identifier
CorrelationID = str  # Request correlation ID
SecurityContext = dict[str, JSONValue]  # Security context

# Cache and Storage
CacheKey = str  # Cache key
CacheValue = JSONValue  # Cached value (prefer more specific types when possible)
CacheTTL = int  # Cache time-to-live in seconds
RedisValue = str | bytes | None  # Redis stored value

# Audit and Logging
AuditEntry = dict[str, JSONValue]  # Single audit log entry
AuditTrail = list[AuditEntry]  # List of audit entries
LogContext = dict[str, JSONValue]  # Structured logging context
LogRecord = dict[str, JSONValue]  # Log record data
MetricData = dict[str, int | float]  # Metric measurements

# Temporal and Time-Series
Timestamp = float  # Unix timestamp
TimelineData = dict[str, JSONValue]  # Timeline/temporal data
ScheduleData = dict[str, JSONValue]  # Schedule information

# ML and AI
ModelID = str  # ML model identifier
ModelParameters = dict[str, int | float | str]  # Model parameters
ModelMetadata = dict[str, JSONValue]  # Model metadata
PredictionResult = dict[str, JSONValue]  # Prediction output
FeatureVector = list[float] | dict[str, float]  # Feature data
TrainingData = dict[str, JSONValue]  # Training dataset metadata

# Error and Exception
ErrorDetails = dict[str, JSONValue]  # Error details for exceptions
ErrorContext = dict[str, JSONValue]  # Additional error context
ErrorCode = str  # Error code identifier

# Validation and Transformation
ValidationContext = dict[str, JSONValue]  # Context for validation operations
ValidationErrors = list[dict[str, str]]  # Validation error list

# Observability and Telemetry
SpanContext = dict[str, JSONValue]  # Distributed tracing span context
TraceID = str  # Trace identifier
TelemetryData = dict[str, int | float | str]  # Telemetry metrics
PerformanceMetrics = dict[str, float]  # Performance measurements

# Document and Template
TemplateData = dict[str, JSONValue]  # Template rendering data
TemplateContext = dict[str, JSONValue]  # Template context
DocumentData = dict[str, JSONValue]  # Document data

# Database and ORM
DatabaseRow = JSONDict  # Database row/record
QueryParams = JSONDict  # Query parameters
FilterCriteria = JSONDict  # Filter/where criteria

__all__ = [
    "AttributeMap",
    "AuditEntry",
    "AuditTrail",
    "AuthContext",
    "AuthCredentials",
    "AuthToken",
    "CacheKey",
    "CacheTTL",
    "CacheValue",
    "ConfigDict",
    "ConfigValue",
    "ConstitutionalContext",
    "CorrelationID",
    "DatabaseRow",
    "DecisionData",
    "DocumentData",
    "EnvVars",
    "ErrorCode",
    "ErrorContext",
    "ErrorDetails",
    "FeatureVector",
    "FilterCriteria",
    "LogContext",
    "LogRecord",
    "MetricData",
    "ModelID",
    "ModelMetadata",
    "ModelParameters",
    "PerformanceMetrics",
    "PermissionSet",
    "PolicyContext",
    "PolicyData",
    "PolicyDecision",
    "PolicyID",
    "PredictionResult",
    "QueryParams",
    "RedisValue",
    "RoleData",
    "ScheduleData",
    "SecretData",
    "SecurityContext",
    "SpanContext",
    "TelemetryData",
    "TemplateContext",
    "TemplateData",
    "TenantID",
    "TimelineData",
    "Timestamp",
    "TraceID",
    "TrainingData",
    "UserAttributes",
    "ValidationContext",
    "ValidationErrors",
    "VerificationResult",
]
