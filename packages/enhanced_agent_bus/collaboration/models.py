"""
Data Models for Real-time Collaboration.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

try:
    from enhanced_agent_bus._compat.types import (
        JSONDict,
        JSONValue,
    )
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    JSONValue = object  # type: ignore[misc,assignment]


class PresenceStatus(str, Enum):
    """User presence status in a collaborative session."""

    ACTIVE = "active"
    IDLE = "idle"
    TYPING = "typing"
    AWAY = "away"


class UserPermissions(str, Enum):
    """Permission levels for collaborative editing."""

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class CursorPosition(BaseModel):
    """Cursor position within a document."""

    x: float = Field(..., description="X coordinate (for canvas-based editing)")
    y: float = Field(..., description="Y coordinate (for canvas-based editing)")
    line: int | None = Field(None, description="Line number (for text-based editing)")
    column: int | None = Field(None, description="Column number (for text-based editing)")
    selection_start: int | None = Field(None, description="Selection start offset")
    selection_end: int | None = Field(None, description="Selection end offset")
    node_id: str | None = Field(None, description="Node ID (for visual workflow editing)")


class Collaborator(BaseModel):
    """Represents a user participating in a collaborative session."""

    user_id: str = Field(..., description="Unique user identifier")
    name: str = Field(..., description="Display name")
    email: str | None = Field(None, description="User email")
    avatar: str | None = Field(None, description="Avatar URL")
    color: str = Field(..., description="Assigned color for cursor/selection")
    cursor: CursorPosition | None = Field(None, description="Current cursor position")
    status: PresenceStatus = Field(default=PresenceStatus.ACTIVE)
    permissions: UserPermissions = Field(default=UserPermissions.READ)
    tenant_id: str = Field(..., description="Tenant for isolation")
    joined_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_anonymous: bool = Field(default=False)
    client_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        """Ensure color is a valid hex color."""
        if not v.startswith("#") or len(v) not in (4, 7):
            raise ValueError("Color must be a valid hex color (e.g., #FF5733)")
        return v

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for JSON serialization."""
        return {
            "user_id": self.user_id,
            "name": self.name,
            "email": self.email,
            "avatar": self.avatar,
            "color": self.color,
            "cursor": self.cursor.model_dump() if self.cursor else None,
            "status": self.status.value,
            "permissions": self.permissions.value,
            "joined_at": self.joined_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "is_anonymous": self.is_anonymous,
            "client_id": self.client_id,
        }


class DocumentType(str, Enum):
    """Types of documents that support collaboration."""

    POLICY = "policy"
    WORKFLOW = "workflow"
    TEMPLATE = "template"
    RULE = "rule"


class CollaborationSession(BaseModel):
    """Active collaboration session for a document."""

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str = Field(..., description="Document being edited")
    document_type: DocumentType = Field(..., description="Type of document")
    tenant_id: str = Field(..., description="Tenant for isolation")
    users: dict[str, Collaborator] = Field(
        default_factory=dict, description="Active users by client_id"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = Field(default_factory=lambda: datetime.now(UTC))
    version: int = Field(default=0, description="Document version counter")
    is_locked: bool = Field(default=False, description="If true, no edits allowed")
    locked_by: str | None = Field(None, description="User who locked the document")
    max_users: int = Field(default=50, description="Maximum concurrent users")

    def get_active_users(self) -> list[Collaborator]:
        """Get list of active (non-idle) users."""
        return [u for u in self.users.values() if u.status != PresenceStatus.AWAY]

    def can_join(self) -> bool:
        """Check if new users can join the session."""
        return len(self.users) < self.max_users and not self.is_locked

    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.now(UTC)


class EditOperationType(str, Enum):
    """Types of edit operations."""

    INSERT = "insert"
    DELETE = "delete"
    REPLACE = "replace"
    MOVE = "move"
    SET_PROPERTY = "set_property"
    DELETE_PROPERTY = "delete_property"


class EditOperation(BaseModel):
    """Single edit operation for operational transform."""

    operation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: EditOperationType = Field(..., description="Operation type")
    path: str = Field(..., description="JSON path to the target")
    value: JSONValue = Field(None, description="New value (for insert/replace/set)")
    old_value: JSONValue = Field(None, description="Previous value (for validation)")
    position: int | None = Field(None, description="Position for text operations")
    length: int | None = Field(None, description="Length for delete operations")
    timestamp: float = Field(default_factory=lambda: datetime.now(UTC).timestamp())
    user_id: str = Field(..., description="User who made the edit")
    client_id: str = Field(..., description="Client session ID")
    version: int = Field(..., description="Document version at time of edit")
    parent_version: int | None = Field(None, description="Parent version for conflict resolution")

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for JSON serialization."""
        return {
            "operation_id": self.operation_id,
            "type": self.type.value,
            "path": self.path,
            "value": self.value,
            "old_value": self.old_value,
            "position": self.position,
            "length": self.length,
            "timestamp": self.timestamp,
            "user_id": self.user_id,
            "client_id": self.client_id,
            "version": self.version,
            "parent_version": self.parent_version,
        }


class CommentReply(BaseModel):
    """Reply to a comment."""

    reply_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = Field(..., description="User who replied")
    user_name: str = Field(..., description="Display name")
    text: str = Field(..., min_length=1, max_length=5000)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Comment(BaseModel):
    """Inline comment on a document."""

    comment_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = Field(..., description="User who created the comment")
    user_name: str = Field(..., description="Display name")
    user_avatar: str | None = Field(None, description="User avatar URL")
    text: str = Field(..., min_length=1, max_length=10000)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved: bool = Field(default=False)
    resolved_by: str | None = Field(None)
    resolved_at: datetime | None = Field(None)
    replies: list[CommentReply] = Field(default_factory=list)
    position: CursorPosition | None = Field(None, description="Position in document")
    selection_text: str | None = Field(None, description="Selected text context")
    mentions: list[str] = Field(default_factory=list, description="User IDs mentioned")

    def resolve(self, user_id: str) -> None:
        """Mark comment as resolved."""
        self.resolved = True
        self.resolved_by = user_id
        self.resolved_at = datetime.now(UTC)

    def add_reply(self, reply: CommentReply) -> None:
        """Add a reply to the comment."""
        self.replies.append(reply)


class ActivityEventType(str, Enum):
    """Types of activity events."""

    USER_JOINED = "user_joined"
    USER_LEFT = "user_left"
    DOCUMENT_EDITED = "document_edited"
    COMMENT_ADDED = "comment_added"
    COMMENT_RESOLVED = "comment_resolved"
    CURSOR_MOVED = "cursor_moved"
    DOCUMENT_LOCKED = "document_locked"
    DOCUMENT_UNLOCKED = "document_unlocked"
    VERSION_SAVED = "version_saved"


class ActivityEvent(BaseModel):
    """Activity feed event."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: ActivityEventType = Field(...)
    user_id: str = Field(...)
    user_name: str = Field(...)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    document_id: str = Field(...)
    details: JSONDict = Field(default_factory=dict)


class ChatMessage(BaseModel):
    """Chat message within a collaborative session."""

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = Field(...)
    user_name: str = Field(...)
    user_avatar: str | None = Field(None)
    text: str = Field(..., min_length=1, max_length=2000)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    mentions: list[str] = Field(default_factory=list)
    is_system: bool = Field(default=False)


class DocumentSnapshot(BaseModel):
    """Snapshot of document state for versioning."""

    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str = Field(...)
    version: int = Field(...)
    content: JSONDict = Field(...)
    created_by: str = Field(...)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    operation_history: list[EditOperation] = Field(default_factory=list)
    comment_count: int = Field(default=0)


class CollaborationConfig(BaseModel):
    """Configuration for collaboration service."""

    max_users_per_document: int = Field(default=50)
    max_documents_per_tenant: int = Field(default=1000)
    cursor_sync_interval_ms: int = Field(default=50, description="Cursor sync interval")
    operation_batch_size: int = Field(default=10)
    history_retention_hours: int = Field(default=24)
    enable_chat: bool = Field(default=True)
    enable_comments: bool = Field(default=True)
    enable_presence: bool = Field(default=True)
    lock_timeout_seconds: int = Field(default=300)
    idle_timeout_seconds: int = Field(default=300)
    away_timeout_seconds: int = Field(default=600)


class CollaborationError(Exception):
    """Base exception for collaboration errors."""

    def __init__(self, message: str, code: str = "COLLABORATION_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class PermissionDeniedError(CollaborationError):
    """Raised when user lacks required permissions."""

    def __init__(self, message: str = "Permission denied"):
        super().__init__(message, "PERMISSION_DENIED")


class DocumentLockedError(CollaborationError):
    """Raised when document is locked."""

    def __init__(self, message: str = "Document is locked"):
        super().__init__(message, "DOCUMENT_LOCKED")


class SessionFullError(CollaborationError):
    """Raised when session is at capacity."""

    def __init__(self, message: str = "Session is full"):
        super().__init__(message, "SESSION_FULL")


class ConflictError(CollaborationError):
    """Raised when there's a conflict that can't be resolved."""

    def __init__(self, message: str = "Edit conflict detected"):
        super().__init__(message, "CONFLICT")


class CollaborationValidationError(CollaborationError):
    """Raised when operation validation fails."""

    def __init__(self, message: str = "Validation failed"):
        super().__init__(message, "VALIDATION_ERROR")
