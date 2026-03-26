# Constitutional Hash: 608508a9bd224290
"""Protocol types, TypeVar definitions, and functional type aliases for ACGS-2."""

from collections.abc import Callable, Coroutine
from typing import Protocol, TypeVar

from .governance_types import CacheValue
from .json_types import JSONDict, JSONValue

# ============================================================================
# Protocol Types for Structural Typing
# ============================================================================


class SupportsCache(Protocol):
    """Protocol for objects that support caching."""

    def get(self, key: str) -> CacheValue | None:
        """Get value from cache."""
        ...

    def set(self, key: str, value: CacheValue, ttl: int | None = None) -> None:
        """Set value in cache."""
        ...


class SupportsValidation(Protocol):
    """Protocol for objects that support validation."""

    def validate(self) -> bool:
        """Validate the object."""
        ...


class SupportsAuthentication(Protocol):
    """Protocol for objects that support authentication."""

    async def authenticate(self) -> bool:
        """Perform authentication."""
        ...


class SupportsSerialization(Protocol):
    """Protocol for objects that support JSON serialization."""

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        ...

    @classmethod
    def from_dict(cls, data: JSONDict) -> "SupportsSerialization":
        """Create from dictionary."""
        ...


class SupportsLogging(Protocol):
    """Protocol for logger-like objects."""

    def info(self, msg: str, **kwargs: JSONValue) -> None:
        """Log info message."""
        ...

    def error(self, msg: str, **kwargs: JSONValue) -> None:
        """Log error message."""
        ...

    def warning(self, msg: str, **kwargs: JSONValue) -> None:
        """Log warning message."""
        ...

    def debug(self, msg: str, **kwargs: JSONValue) -> None:
        """Log debug message."""
        ...


class SupportsMiddleware(Protocol):
    """Protocol for middleware/ASGI applications."""

    async def __call__(self, scope: dict[str, object], receive: Callable, send: Callable) -> None:
        """Process ASGI request."""
        ...


class SupportsHealthCheck(Protocol):
    """Protocol for objects that support health checking."""

    async def health_check(self) -> JSONDict:
        """Perform health check and return status."""
        ...


class SupportsCircuitBreaker(Protocol):
    """Protocol for circuit breaker implementations."""

    def is_open(self) -> bool:
        """Check if circuit is open (failing)."""
        ...

    def record_success(self) -> None:
        """Record a successful call."""
        ...

    def record_failure(self) -> None:
        """Record a failed call."""
        ...


class SupportsAudit(Protocol):
    """Protocol for audit logging implementations."""

    async def log_event(
        self,
        event_type: str,
        details: JSONDict,
        correlation_id: str | None = None,
    ) -> None:
        """Log an audit event."""
        ...


class AgentBus(Protocol):
    """Structural interface for the Enhanced Agent Bus service."""

    async def send_message(self, message: JSONDict) -> JSONDict:
        """Send a message through the bus."""
        ...

    async def receive_message(self, timeout: float = 1.0) -> JSONDict | None:
        """Receive a message from the bus."""
        ...


class GovernanceService(Protocol):
    """Structural interface for the Constitutional Governance service."""

    async def evaluate_policy(self, policy_id: str, context: JSONDict) -> JSONDict:
        """Evaluate a policy against a context."""
        ...

    async def register_policy(self, policy_data: JSONDict) -> bool:
        """Register a new policy."""
        ...


# Define T before it's used in SupportsRegistry
T = TypeVar("T")  # Generic type variable


class SupportsRegistry(Protocol[T]):
    """Protocol for registry implementations."""

    def register(self, key: str, value: T) -> None:
        """Register a value."""
        ...

    def get(self, key: str) -> T | None:
        """Get a registered value."""
        ...

    def unregister(self, key: str) -> None:
        """Unregister a value."""
        ...


class SupportsExecution(Protocol):
    """Protocol for executable operations."""

    async def execute(self, *args: JSONValue, **kwargs: JSONValue) -> JSONDict:
        """Execute the operation."""
        ...


class SupportsCompensation(Protocol):
    """Protocol for compensatable saga operations."""

    async def execute(self, context: JSONDict) -> JSONDict:
        """Execute forward operation."""
        ...

    async def compensate(self, context: JSONDict) -> JSONDict:
        """Compensate (rollback) operation."""
        ...


# ============================================================================
# Generic Type Variables
# ============================================================================

T_co = TypeVar("T_co", covariant=True)  # Covariant type variable
T_contra = TypeVar("T_contra", contravariant=True)  # Contravariant type variable

# Specific type variables
ModelT = TypeVar("ModelT")  # For Pydantic models
ConfigT = TypeVar("ConfigT")  # For configuration objects
ResponseT = TypeVar("ResponseT")  # For API responses
EventT = TypeVar("EventT")  # For event types
StateT = TypeVar("StateT")  # For state objects
ContextT = TypeVar("ContextT")  # For context objects

# ============================================================================
# Pydantic-specific Types
# ============================================================================

ValidatorValue = JSONValue  # Input value to validator
ValidatorContext = JSONDict  # Pydantic validation context object
ModelContext = JSONDict  # Pydantic model_post_init __context parameter

# ============================================================================
# Decorator and Wrapper Types
# ============================================================================

ArgsType = tuple[JSONValue, ...]  # *args tuple
KwargsType = JSONDict  # **kwargs dict
DecoratorFunc = Callable[[Callable[..., T]], Callable[..., T]]  # Function decorator
AsyncFunc = Callable[..., Coroutine[object, object, object]]  # Async function type

# ============================================================================
# Validation and Transformation function types
# ============================================================================

TransformFunc = Callable[[JSONValue], JSONValue]  # Generic transformation function
ValidatorFunc = Callable[[JSONValue], bool]  # Generic validator function

__all__ = [
    "AgentBus",
    "ArgsType",
    "AsyncFunc",
    "ConfigT",
    "ContextT",
    "DecoratorFunc",
    "EventT",
    "GovernanceService",
    "KwargsType",
    "ModelContext",
    "ModelT",
    "ResponseT",
    "StateT",
    "SupportsAudit",
    "SupportsAuthentication",
    "SupportsCache",
    "SupportsCircuitBreaker",
    "SupportsCompensation",
    "SupportsExecution",
    "SupportsHealthCheck",
    "SupportsLogging",
    "SupportsMiddleware",
    "SupportsRegistry",
    "SupportsSerialization",
    "SupportsValidation",
    "T",
    "T_co",
    "T_contra",
    "TransformFunc",
    "ValidatorContext",
    "ValidatorFunc",
    "ValidatorValue",
]
