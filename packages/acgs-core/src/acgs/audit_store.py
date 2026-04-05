"""AuditStore ABC — pluggable audit persistence for ACGS.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AuditStore(ABC):
    """Abstract base for audit trail persistence.

    Uses TYPE_CHECKING import for AuditEntry to avoid a hard runtime
    dependency on acgs-lite. Consumers must have acgs-lite installed
    to use concrete implementations.
    """

    @abstractmethod
    def append(self, entry: Any) -> str:
        """Persist an audit entry. Returns the entry ID."""

    @abstractmethod
    def get(self, entry_id: str) -> Any | None:
        """Retrieve a single entry by ID."""

    @abstractmethod
    def list_entries(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        agent_id: str | None = None,
    ) -> list[Any]:
        """Paginated listing with optional agent_id filter."""

    @abstractmethod
    def count(self) -> int:
        """Total number of stored entries."""

    @abstractmethod
    def verify_chain(self) -> bool:
        """Verify hash chain integrity of all stored entries."""
