"""
ACGS-2 Core Service Interfaces
Constitutional Hash: 608508a9bd224290

Interface abstractions for external dependencies to support DIP and testability.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Protocol

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict[str, object]  # type: ignore[misc, assignment]
from uuid import UUID


class CacheClient(Protocol):
    """Protocol for cache client operations."""

    async def get(self, key: str) -> str | None:
        """Get a value from cache."""
        ...

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        """Set a value in cache with optional expiration."""
        ...

    async def setex(self, key: str, time: int, value: str) -> bool:
        """Set a value with expiration time."""
        ...

    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        ...

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        ...

    async def expire(self, key: str, time: int) -> bool:
        """Set expiration time for a key."""
        ...


class PolicyEvaluator(Protocol):
    """Protocol for policy evaluation operations."""

    async def evaluate(
        self,
        policy_path: str,
        input_data: JSONDict,
        *,
        strict: bool = True,
    ) -> JSONDict:
        """Evaluate a policy against input data."""
        ...

    async def evaluate_batch(
        self,
        policy_path: str,
        _input_data_list: list[JSONDict],
        *,
        strict: bool = True,
    ) -> list[JSONDict]:
        """Evaluate a policy against multiple input data sets."""
        ...

    async def get_policy(self, policy_path: str) -> JSONDict | None:
        """Get policy definition."""
        ...

    async def list_policies(self, path: str | None = None) -> list[str]:
        """List available policies."""
        ...


class AuditService(Protocol):
    """Protocol for audit logging operations."""

    async def log_event(
        self,
        event_type: str,
        actor: str,
        action: str,
        resource: str,
        outcome: str,
        *,
        details: JSONDict | None = None,
        tenant_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> UUID:
        """Log an audit event."""
        ...

    async def log_events_batch(
        self,
        events: list[JSONDict],
    ) -> list[UUID]:
        """Log multiple audit events in batch."""
        ...

    async def get_event(self, event_id: UUID) -> JSONDict | None:
        """Get an audit event by ID."""
        ...

    async def query_events(
        self,
        *,
        event_type: str | None = None,
        actor: str | None = None,
        action: str | None = None,
        resource: str | None = None,
        tenant_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int | None = None,
    ) -> list[JSONDict]:
        """Query audit events with filters."""
        ...

    async def verify_integrity(self) -> JSONDict:
        """Verify audit trail integrity."""
        ...


class DatabaseSession(Protocol):
    """Protocol for database session operations."""

    async def execute(self, query: object, params: JSONDict | None = None) -> object:
        """Execute a database query."""
        ...

    async def commit(self) -> None:
        """Commit the transaction."""
        ...

    async def rollback(self) -> None:
        """Rollback the transaction."""
        ...

    async def close(self) -> None:
        """Close the session."""
        ...


class NotificationService(Protocol):
    """Protocol for notification operations."""

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        html: bool = False,
        cc: list[str] | None = None,
        _bcc: list[str] | None = None,
    ) -> bool:
        """Send an email notification."""
        ...

    async def send_sms(self, to: str, message: str) -> bool:
        """Send an SMS notification."""
        ...

    async def send_webhook(self, url: str, payload: JSONDict) -> bool:
        """Send a webhook notification."""
        ...

    async def send_in_app(
        self,
        user_id: str,
        message: str,
        *,
        title: str | None = None,
        data: JSONDict | None = None,
    ) -> bool:
        """Send an in-app notification."""
        ...


class MessageProcessor(Protocol):
    """Protocol for message processing operations."""

    async def process(self, message: JSONDict) -> JSONDict:
        """Process a single message."""
        ...

    async def process_batch(self, messages: list[JSONDict]) -> list[JSONDict]:
        """Process multiple messages in batch."""
        ...


class RetryStrategy(ABC):
    """Abstract base class for retry strategies."""

    @abstractmethod
    async def should_retry(self, attempt: int, error: Exception) -> bool:
        """Determine if an operation should be retried."""
        ...

    @abstractmethod
    async def get_delay(self, attempt: int) -> float:
        """Get delay before next retry attempt."""
        ...


class CircuitBreaker(Protocol):
    """Protocol for circuit breaker operations."""

    async def record_success(self) -> None:
        """Record a successful operation."""
        ...

    async def record_failure(self) -> None:
        """Record a failed operation."""
        ...

    async def allow_request(self) -> bool:
        """Check if a request should be allowed through the circuit breaker."""
        ...

    async def get_state(self) -> str:
        """Get the current circuit breaker state."""
        ...


class MetricsCollector(Protocol):
    """Protocol for metrics collection operations."""

    async def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Increment a counter metric."""
        ...

    async def record_timing(
        self,
        name: str,
        value_ms: float,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Record a timing metric."""
        ...

    async def record_gauge(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Record a gauge metric."""
        ...

    async def get_metrics(self) -> JSONDict:
        """Get all collected metrics."""
        ...
