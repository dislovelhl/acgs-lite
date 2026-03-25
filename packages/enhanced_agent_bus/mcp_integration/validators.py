"""
MCP Constitutional Validators for ACGS-2.

Provides constitutional validation for all MCP operations, ensuring
compliance with governance principles and MACI role-based access control.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import hmac
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum
from typing import ClassVar

# Import centralized constitutional hash
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.bus_types import JSONDict
from enhanced_agent_bus.observability.structured_logging import get_logger

# Configuration constants
DEFAULT_MAX_AUDIT_LOG = 10000

# Import MACI enforcement
try:
    from ..maci_enforcement import (
        MACIAction,
        MACIEnforcer,
        MACIRole,
        MACIRoleRegistry,
        MACIValidationResult,
    )

    MACI_AVAILABLE = True
except ImportError:
    MACI_AVAILABLE = False
    MACIAction = object
    MACIEnforcer = object
    MACIRole = object
    MACIRoleRegistry = object
    MACIValidationResult = object

logger = get_logger(__name__)
_MCP_VALIDATOR_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class OperationType(Enum):
    """Types of MCP operations requiring validation."""

    # Tool operations
    TOOL_CALL = "tool_call"
    TOOL_REGISTER = "tool_register"
    TOOL_UNREGISTER = "tool_unregister"
    TOOL_DISCOVER = "tool_discover"

    # Resource operations
    RESOURCE_READ = "resource_read"
    RESOURCE_WRITE = "resource_write"
    RESOURCE_SUBSCRIBE = "resource_subscribe"

    # Protocol operations
    PROTOCOL_INITIALIZE = "protocol_initialize"
    PROTOCOL_SHUTDOWN = "protocol_shutdown"

    # Connection operations
    CONNECTION_ESTABLISH = "connection_establish"
    CONNECTION_TERMINATE = "connection_terminate"

    # Governance operations
    GOVERNANCE_REQUEST = "governance_request"
    GOVERNANCE_APPROVE = "governance_approve"
    GOVERNANCE_DENY = "governance_deny"


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ValidationIssue:
    """A single validation issue or violation."""

    code: str
    message: str
    severity: ValidationSeverity
    principle: str | None = None
    details: JSONDict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "principle": self.principle,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class MCPValidationResult:
    """Result of MCP constitutional validation."""

    is_valid: bool
    operation_type: OperationType
    issues: list[ValidationIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    maci_result: object | None = None  # MACIValidationResult if MACI enabled
    constitutional_hash: str = CONSTITUTIONAL_HASH
    validated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    latency_ms: float = 0.0
    metadata: JSONDict = field(default_factory=dict)

    def add_issue(
        self,
        code: str,
        message: str,
        severity: ValidationSeverity = ValidationSeverity.ERROR,
        principle: str | None = None,
        details: JSONDict | None = None,
    ) -> None:
        """Add a validation issue."""
        self.issues.append(
            ValidationIssue(
                code=code,
                message=message,
                severity=severity,
                principle=principle,
                details=details or {},
            )
        )
        if severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL):
            self.is_valid = False

    def add_warning(self, warning: str) -> None:
        """Add a warning."""
        self.warnings.append(warning)

    def add_recommendation(self, recommendation: str) -> None:
        """Add a recommendation."""
        self.recommendations.append(recommendation)

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        result = {
            "is_valid": self.is_valid,
            "operation_type": self.operation_type.value,
            "issues": [issue.to_dict() for issue in self.issues],
            "warnings": self.warnings,
            "recommendations": self.recommendations,
            "constitutional_hash": self.constitutional_hash,
            "validated_at": self.validated_at.isoformat(),
            "latency_ms": self.latency_ms,
            "metadata": self.metadata,
        }
        if self.maci_result:
            result["maci_result"] = (
                self.maci_result.to_audit_dict()
                if hasattr(self.maci_result, "to_audit_dict")
                else str(self.maci_result)
            )
        return result


@dataclass
class MCPOperationContext:
    """Context for an MCP operation requiring validation."""

    operation_type: OperationType
    agent_id: str
    target_id: str | None = None
    tool_name: str | None = None
    resource_uri: str | None = None
    arguments: JSONDict = field(default_factory=dict)
    session_id: str | None = None
    tenant_id: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH
    request_id: str | None = None
    metadata: JSONDict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "operation_type": self.operation_type.value,
            "agent_id": self.agent_id,
            "target_id": self.target_id,
            "tool_name": self.tool_name,
            "resource_uri": self.resource_uri,
            "arguments": self.arguments,
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "constitutional_hash": self.constitutional_hash,
            "request_id": self.request_id,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class MCPValidationConfig:
    """Configuration for MCP validation."""

    strict_mode: bool = True
    enable_maci: bool = True
    enable_audit_logging: bool = True
    enable_rate_limiting: bool = True
    max_requests_per_minute: int = 1000
    blocked_operations: set[OperationType] = field(default_factory=set)
    allowed_tools: set[str] | None = None  # None means all allowed
    blocked_tools: set[str] = field(default_factory=set)
    require_constitutional_hash: bool = True
    constitutional_hash: str = CONSTITUTIONAL_HASH
    custom_validators: list[Callable] = field(default_factory=list)


# Operation to MACI Action mapping
OPERATION_MACI_MAPPING: dict[OperationType, object] = {}

if MACI_AVAILABLE:
    OPERATION_MACI_MAPPING = {
        OperationType.TOOL_CALL: MACIAction.SYNTHESIZE,
        OperationType.TOOL_REGISTER: MACIAction.PROPOSE,
        OperationType.TOOL_UNREGISTER: MACIAction.MANAGE_POLICY,
        OperationType.TOOL_DISCOVER: MACIAction.QUERY,
        OperationType.RESOURCE_READ: MACIAction.QUERY,
        OperationType.RESOURCE_WRITE: MACIAction.SYNTHESIZE,
        OperationType.RESOURCE_SUBSCRIBE: MACIAction.QUERY,
        OperationType.PROTOCOL_INITIALIZE: MACIAction.QUERY,
        OperationType.PROTOCOL_SHUTDOWN: MACIAction.QUERY,
        OperationType.CONNECTION_ESTABLISH: MACIAction.QUERY,
        OperationType.CONNECTION_TERMINATE: MACIAction.QUERY,
        OperationType.GOVERNANCE_REQUEST: MACIAction.PROPOSE,
        OperationType.GOVERNANCE_APPROVE: MACIAction.VALIDATE,
        OperationType.GOVERNANCE_DENY: MACIAction.VALIDATE,
    }


class MCPConstitutionalValidator:
    """
    Constitutional validator for MCP operations.

    Validates all MCP operations against constitutional principles,
    MACI role-based access control, and governance policies.

    Constitutional Hash: 608508a9bd224290
    """

    CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH

    # Core constitutional principles for MCP operations
    PRINCIPLES: ClassVar[dict] = {
        "transparency": "MCP operations must be transparent and auditable",
        "accountability": "All MCP actions must be traceable to agents",
        "safety": "MCP operations must not compromise system safety",
        "authorization": "MCP operations require proper authorization",
        "isolation": "MCP operations must respect tenant boundaries",
        "integrity": "MCP operations must preserve data integrity",
        "non_maleficence": "MCP operations must not cause harm",
        "governance": "MCP operations must comply with governance policies",
    }

    # High-risk tools that require additional validation
    HIGH_RISK_TOOLS: ClassVar[set] = {
        "execute_command",
        "delete_data",
        "modify_policy",
        "admin_action",
        "system_config",
        "user_management",
    }

    # Sensitive resource patterns
    SENSITIVE_RESOURCE_PATTERNS: ClassVar[list] = [
        "*/credentials/*",
        "*/secrets/*",
        "*/admin/*",
        "*/config/*",
        "*/policy/*",
    ]

    def __init__(
        self,
        config: MCPValidationConfig | None = None,
        maci_enforcer: object | None = None,
        max_audit_log: int = DEFAULT_MAX_AUDIT_LOG,
    ):
        """
        Initialize the MCP constitutional validator.

        Args:
            config: Validation configuration
            maci_enforcer: Optional MACI enforcer instance for role-based validation
            max_audit_log: Maximum number of audit log entries to retain (default 10000)
        """
        self.config = config or MCPValidationConfig()
        self.maci_enforcer = maci_enforcer
        self._validation_count = 0
        self._violation_count = 0
        self._rate_limit_buckets: dict[str, list[datetime]] = {}
        self._lock = asyncio.Lock()
        self._audit_log: list[JSONDict] = []
        self._max_audit_log = max_audit_log

    async def validate(self, context: MCPOperationContext) -> MCPValidationResult:
        """
        Validate an MCP operation against constitutional principles.

        Args:
            context: Operation context containing all relevant details

        Returns:
            MCPValidationResult with validation outcome
        """
        start_time = datetime.now(UTC)
        self._validation_count += 1

        result = MCPValidationResult(
            is_valid=True,
            operation_type=context.operation_type,
        )

        try:
            # Execute validation pipeline
            await self._execute_core_validation_pipeline(context, result)

        except _MCP_VALIDATOR_OPERATION_ERRORS as e:
            self._handle_validation_error(e, result)

        return self._finalize_result(result, start_time, context)

    async def _execute_core_validation_pipeline(
        self, context: MCPOperationContext, result: MCPValidationResult
    ) -> None:
        """Execute the core validation pipeline with early exit on strict mode failures."""
        # Core security validations
        await self._execute_security_validations(context, result)
        if not result.is_valid and self.config.strict_mode:
            return

        # Access control validations
        await self._execute_access_control_validations(context, result)
        if not result.is_valid and self.config.strict_mode:
            return

        # Operation-specific and custom validations
        await self._execute_extended_validations(context, result)

    async def _execute_security_validations(
        self, context: MCPOperationContext, result: MCPValidationResult
    ) -> None:
        """Execute fundamental security validations."""
        # Constitutional hash validation
        if self.config.require_constitutional_hash:
            self._validate_constitutional_hash(context, result)
            if not result.is_valid and self.config.strict_mode:
                return

        # Operation blocking check
        self._validate_operation_allowed(context, result)
        if not result.is_valid and self.config.strict_mode:
            return

        # Rate limiting
        if self.config.enable_rate_limiting:
            await self._validate_rate_limit(context, result)

    async def _execute_access_control_validations(
        self, context: MCPOperationContext, result: MCPValidationResult
    ) -> None:
        """Execute access control and authorization validations."""
        # Tool/resource access validation
        self._validate_access(context, result)
        if not result.is_valid and self.config.strict_mode:
            return

        # MACI role-based validation
        if self.config.enable_maci and self.maci_enforcer:
            await self._validate_maci(context, result)

    async def _execute_extended_validations(
        self, context: MCPOperationContext, result: MCPValidationResult
    ) -> None:
        """Execute operation-specific and custom validations."""
        # Operation-specific rules
        await self._validate_operation_specific(context, result)
        if not result.is_valid and self.config.strict_mode:
            return

        # Custom validators
        await self._run_custom_validators(context, result)

    def _handle_validation_error(self, error: Exception, result: MCPValidationResult) -> None:
        """Handle validation errors with proper fail-closed semantics."""
        logger.error(f"Validation error: {error}")
        result.add_issue(
            code="VALIDATION_ERROR",
            message=f"Validation error: {error}",
            severity=ValidationSeverity.CRITICAL,
        )
        if self.config.strict_mode:
            result.is_valid = False

    def _validate_constitutional_hash(
        self, context: MCPOperationContext, result: MCPValidationResult
    ) -> None:
        """Validate the constitutional hash."""
        if not context.constitutional_hash:
            result.add_issue(
                code="HASH_MISSING",
                message="Constitutional hash is required but not provided",
                severity=ValidationSeverity.CRITICAL,
                principle="integrity",
            )
            return

        # Use constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(context.constitutional_hash, self.CONSTITUTIONAL_HASH):
            safe_provided = (
                context.constitutional_hash[:8] + "..."
                if len(context.constitutional_hash) > 8
                else context.constitutional_hash
            )
            result.add_issue(
                code="HASH_MISMATCH",
                message=f"Constitutional hash mismatch (provided: {safe_provided})",
                severity=ValidationSeverity.CRITICAL,
                principle="integrity",
            )

    def _validate_operation_allowed(
        self, context: MCPOperationContext, result: MCPValidationResult
    ) -> None:
        """Validate that the operation is not blocked."""
        if context.operation_type in self.config.blocked_operations:
            result.add_issue(
                code="OPERATION_BLOCKED",
                message=f"Operation {context.operation_type.value} is blocked by policy",
                severity=ValidationSeverity.ERROR,
                principle="authorization",
            )

    async def _validate_rate_limit(
        self, context: MCPOperationContext, result: MCPValidationResult
    ) -> None:
        """Validate rate limiting."""
        agent_key = f"{context.tenant_id or 'default'}:{context.agent_id}"

        async with self._lock:
            now = datetime.now(UTC)
            one_minute_ago = now - timedelta(minutes=1)

            if agent_key not in self._rate_limit_buckets:
                self._rate_limit_buckets[agent_key] = []

            # Clean old entries
            self._rate_limit_buckets[agent_key] = [
                ts for ts in self._rate_limit_buckets[agent_key] if ts > one_minute_ago
            ]

            # Check rate limit
            if len(self._rate_limit_buckets[agent_key]) >= self.config.max_requests_per_minute:
                result.add_issue(
                    code="RATE_LIMITED",
                    message=f"Rate limit exceeded: {self.config.max_requests_per_minute}/minute",
                    severity=ValidationSeverity.ERROR,
                    principle="safety",
                    details={"limit": self.config.max_requests_per_minute},
                )
                return

            # Record this request
            self._rate_limit_buckets[agent_key].append(now)

    def _validate_access(self, context: MCPOperationContext, result: MCPValidationResult) -> None:
        """Validate tool and resource access."""
        # Check tool access
        if context.tool_name:
            if context.tool_name in self.config.blocked_tools:
                result.add_issue(
                    code="TOOL_BLOCKED",
                    message=f"Tool '{context.tool_name}' is blocked by policy",
                    severity=ValidationSeverity.ERROR,
                    principle="authorization",
                )

            if (
                self.config.allowed_tools is not None
                and context.tool_name not in self.config.allowed_tools
            ):
                result.add_issue(
                    code="TOOL_NOT_ALLOWED",
                    message=f"Tool '{context.tool_name}' is not in the allowed list",
                    severity=ValidationSeverity.ERROR,
                    principle="authorization",
                )

            # Check high-risk tools
            if context.tool_name in self.HIGH_RISK_TOOLS:
                result.add_warning(f"Tool '{context.tool_name}' is classified as high-risk")
                result.add_recommendation("Ensure proper authorization for high-risk operations")

        # Check resource access
        if context.resource_uri:
            for pattern in self.SENSITIVE_RESOURCE_PATTERNS:
                if self._match_pattern(context.resource_uri, pattern):
                    result.add_warning(
                        f"Resource '{context.resource_uri}' matches sensitive pattern"
                    )
                    result.add_recommendation("Verify authorization for sensitive resource access")
                    break

    async def _validate_maci(
        self, context: MCPOperationContext, result: MCPValidationResult
    ) -> None:
        """Validate using MACI role-based access control."""
        if not MACI_AVAILABLE or not self.maci_enforcer:
            return

        maci_action = OPERATION_MACI_MAPPING.get(context.operation_type)
        if not maci_action:
            result.add_warning(f"No MACI mapping for operation {context.operation_type.value}")
            return

        try:
            maci_result = await self.maci_enforcer.validate_action(
                agent_id=context.agent_id,
                action=maci_action,
                target_output_id=context.target_id,
                target_agent_id=context.target_id,
                session_id=context.session_id,
            )
            result.maci_result = maci_result

            if not maci_result.is_valid:
                result.add_issue(
                    code="MACI_VIOLATION",
                    message=f"MACI validation failed: {maci_result.error_message or 'Role violation'}",
                    severity=ValidationSeverity.ERROR,
                    principle="authorization",
                    details=(
                        maci_result.to_audit_dict() if hasattr(maci_result, "to_audit_dict") else {}
                    ),
                )

        except _MCP_VALIDATOR_OPERATION_ERRORS as e:
            logger.warning(f"MACI validation error: {e}")
            if self.config.strict_mode:
                result.add_issue(
                    code="MACI_ERROR",
                    message=f"MACI validation error: {e}",
                    severity=ValidationSeverity.ERROR,
                    principle="authorization",
                )

    async def _validate_operation_specific(
        self, context: MCPOperationContext, result: MCPValidationResult
    ) -> None:
        """Validate operation-specific rules."""
        if context.operation_type == OperationType.TOOL_CALL:
            await self._validate_tool_call(context, result)
        elif context.operation_type == OperationType.GOVERNANCE_REQUEST:
            await self._validate_governance_request(context, result)
        elif context.operation_type in (
            OperationType.GOVERNANCE_APPROVE,
            OperationType.GOVERNANCE_DENY,
        ):
            await self._validate_governance_decision(context, result)

    async def _validate_tool_call(
        self, context: MCPOperationContext, result: MCPValidationResult
    ) -> None:
        """Validate tool call specific rules."""
        # Check for required arguments
        if not context.arguments:
            result.add_warning("Tool call has no arguments")

        # Check for harmful patterns in arguments
        harmful_patterns = ["drop", "delete", "truncate", "exec", "system", "eval"]
        args_str = str(context.arguments).lower()
        for pattern in harmful_patterns:
            if pattern in args_str:
                result.add_warning(f"Potentially harmful pattern '{pattern}' in arguments")
                result.add_recommendation("Review arguments for potentially harmful content")
                break

    async def _validate_governance_request(
        self, context: MCPOperationContext, result: MCPValidationResult
    ) -> None:
        """Validate governance request specific rules."""
        # Ensure proper context for governance requests
        if not context.session_id:
            result.add_warning("Governance request without session context")

    async def _validate_governance_decision(
        self, context: MCPOperationContext, result: MCPValidationResult
    ) -> None:
        """Validate governance decision (approve/deny) specific rules."""
        # Decisions should have a target
        if not context.target_id:
            result.add_issue(
                code="MISSING_TARGET",
                message="Governance decision requires a target request ID",
                severity=ValidationSeverity.ERROR,
                principle="accountability",
            )

    async def _run_custom_validators(
        self, context: MCPOperationContext, result: MCPValidationResult
    ) -> None:
        """Run custom validators."""
        for validator in self.config.custom_validators:
            try:
                if inspect.iscoroutinefunction(validator):
                    await validator(context, result)
                else:
                    validator(context, result)
            except _MCP_VALIDATOR_OPERATION_ERRORS as e:
                logger.warning(f"Custom validator error: {e}")
                result.add_warning(f"Custom validator failed: {e}")

    def _match_pattern(self, value: str, pattern: str) -> bool:
        """Simple wildcard pattern matching."""
        if "*" not in pattern:
            return value == pattern

        parts = pattern.split("*")
        if len(parts) == 2:
            prefix, suffix = parts
            return value.startswith(prefix) and value.endswith(suffix)

        return False

    def _finalize_result(
        self,
        result: MCPValidationResult,
        start_time: datetime,
        context: MCPOperationContext,
    ) -> MCPValidationResult:
        """Finalize the validation result."""
        end_time = datetime.now(UTC)
        result.latency_ms = (end_time - start_time).total_seconds() * 1000

        if not result.is_valid:
            self._violation_count += 1

        # Audit logging
        if self.config.enable_audit_logging:
            audit_entry = {
                "timestamp": end_time.isoformat(),
                "operation": context.operation_type.value,
                "agent_id": context.agent_id,
                "session_id": context.session_id,
                "is_valid": result.is_valid,
                "issues_count": len(result.issues),
                "latency_ms": result.latency_ms,
                "constitutional_hash": self.CONSTITUTIONAL_HASH,
            }
            self._audit_log.append(audit_entry)
            self._trim_audit_log()

        return result

    async def validate_batch(
        self,
        contexts: list[MCPOperationContext],
        max_concurrency: int = 10,
    ) -> list[MCPValidationResult]:
        """
        Validate multiple operations in batch with bounded concurrency.

        Args:
            contexts: List of operation contexts
            max_concurrency: Maximum concurrent validations (default 10)

        Returns:
            List of validation results
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _validate_with_semaphore(
            ctx: MCPOperationContext,
        ) -> MCPValidationResult:
            async with semaphore:
                return await self.validate(ctx)

        tasks = [_validate_with_semaphore(ctx) for ctx in contexts]
        return await asyncio.gather(*tasks)

    def _trim_audit_log(self) -> None:
        """
        Trim audit log when exceeding max size.

        Removes oldest entries (FIFO) when the collection exceeds the limit.
        """
        if len(self._audit_log) > self._max_audit_log:
            excess = len(self._audit_log) - self._max_audit_log
            self._audit_log = self._audit_log[excess:]
            logger.warning(
                f"Audit log trimmed: removed {excess} oldest entries (limit: {self._max_audit_log})"
            )

    def get_metrics(self) -> JSONDict:
        """Get validator metrics."""
        return {
            "validation_count": self._validation_count,
            "violation_count": self._violation_count,
            "violation_rate": (
                self._violation_count / self._validation_count
                if self._validation_count > 0
                else 0.0
            ),
            "audit_log_size": len(self._audit_log),
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
        }

    def get_audit_log(
        self,
        limit: int = 100,
        session_id: str | None = None,
    ) -> list[JSONDict]:
        """
        Get audit log entries.

        Args:
            limit: Maximum number of entries to return
            session_id: Optional session filter

        Returns:
            List of audit log entries
        """
        log = self._audit_log
        if session_id:
            log = [entry for entry in log if entry.get("session_id") == session_id]
        return log[-limit:]

    def clear_audit_log(self) -> int:
        """Clear the audit log and return count of cleared entries."""
        count = len(self._audit_log)
        self._audit_log = []
        return count


def create_mcp_validator(
    config: MCPValidationConfig | None = None,
    maci_enforcer: object | None = None,
    max_audit_log: int = DEFAULT_MAX_AUDIT_LOG,
) -> MCPConstitutionalValidator:
    """
    Factory function to create an MCP constitutional validator.

    Args:
        config: Validation configuration
        maci_enforcer: Optional MACI enforcer instance
        max_audit_log: Maximum number of audit log entries to retain (default 10000)

    Returns:
        Configured MCPConstitutionalValidator instance
    """
    return MCPConstitutionalValidator(
        config=config, maci_enforcer=maci_enforcer, max_audit_log=max_audit_log
    )


__all__ = [
    "OPERATION_MACI_MAPPING",
    "MCPConstitutionalValidator",
    "MCPOperationContext",
    "MCPValidationConfig",
    "MCPValidationResult",
    "OperationType",
    "ValidationIssue",
    "ValidationSeverity",
    "create_mcp_validator",
]
