"""
Real-time Collaboration Module for ACGS-2.

Enables multiple users to simultaneously edit policies and workflows with
presence tracking, cursor synchronization, and live updates.

Constitutional Hash: 608508a9bd224290
"""

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH: str = CONSTITUTIONAL_HASH  # pragma: allowlist secret

from enhanced_agent_bus.collaboration.models import (
    CollaborationSession,
    Collaborator,
    Comment,
    CommentReply,
    CursorPosition,
    EditOperation,
    PresenceStatus,
    UserPermissions,
)
from enhanced_agent_bus.collaboration.permissions import PermissionController
from enhanced_agent_bus.collaboration.presence import PresenceManager
from enhanced_agent_bus.collaboration.server import CollaborationServer
from enhanced_agent_bus.collaboration.sync_engine import OperationalTransform, SyncEngine

__all__ = [
    "CollaborationServer",
    "CollaborationSession",
    "Collaborator",
    "Comment",
    "CommentReply",
    "CursorPosition",
    "EditOperation",
    "OperationalTransform",
    "PermissionController",
    "PresenceManager",
    "PresenceStatus",
    "SyncEngine",
    "UserPermissions",
]
